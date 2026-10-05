"""The evaluation jobs' wire, through the harness (MODULE_STRUCTURE §2.4,
§2.6; CONSTRUCT_INTERACTION §3.3; LOGGING.md §4, `isabelle`): the test
plugin's `TAT_test.fork_job` forks a work that passes, fails, raises a
`Bug` or waits; a stand-in job in the process's table takes the report
`job_finished` brings; `TAT.job_cancel` and `TAT.reset` cancel the futures;
a library theory loads from source beside a running work.
Run: python -m pytest test/test_fork_job.py
"""

import asyncio
from types import SimpleNamespace

import stand_ins
from isabelle_theory_agent import isabelle_driver, jobs
from isabelle_theory_agent.exceptions import TAT_InternalError
from isabelle_theory_agent.isabelle_driver import call
from test_conversation import Probes, errors


class Recorded_Ending:
    """In place of a conversation's ending object: what a report ends the
    conversation with is kept here, and the harness's conversation, which
    the run's later cases need, goes on."""

    def __init__(self):
        self.ended_by: BaseException | None = None
        self.entered = asyncio.Event()

    def end(self, ended_by: BaseException) -> None:
        if self.ended_by is None:
            self.ended_by = ended_by
            self.entered.set()


class Job:
    """A stand-in for an evaluation job: in the process's table from its
    making, it keeps the report it is given."""

    def __init__(self):
        self.ending = Recorded_Ending()
        self.conversation = SimpleNamespace(ending=self.ending)
        self.reported = asyncio.Event()
        self.errors: list[str] | None = None
        self.id = jobs.register(self)       # type: ignore[arg-type]

    def _report(self, errors: list[str]) -> None:
        self.errors = errors
        self.reported.set()


async def fork(conversation, job: Job, outcome: str, path="") -> None:
    await call(conversation, "TAT_test.fork_job", (job.id, (outcome, str(path))))


def records(log_directory, event: str, id: int | None = None) -> list[dict]:
    """The Isabelle side's records of one event, a job's when `id` is given."""
    return [r["data"] for r in stand_ins.records("isabelle", log_directory)
            if r["event"] == event and (id is None or id in (r["data"].get("id"), r["data"].get("job")))]


async def until(condition, seconds: float = 30.0) -> None:
    async with asyncio.timeout(seconds):
        while not condition():
            await asyncio.sleep(0.05)


async def test_a_work_that_passes_and_one_that_fails_are_reported_to_their_jobs(conversation):
    """`fork_job` reports the work's end through `job_finished`: no error
    when it passed, the exception's messages when it failed; the report
    takes the job out of the table; each job leaves `job_forked` and one
    `job_ended` carrying what was reported."""
    conv, log = conversation.forest.conversation, conversation.log.directory
    passed, failed = Job(), Job()
    await fork(conv, passed, "pass")
    await fork(conv, failed, "fail")
    await asyncio.wait_for(asyncio.gather(passed.reported.wait(), failed.reported.wait()), 30)
    assert (passed.errors, failed.errors) == ([], ["tat-job-error"])
    assert passed.ending.ended_by is None and failed.ending.ended_by is None
    assert not {passed.id, failed.id} & set(jobs._evaluation_jobs)
    for job, failure in ((passed, ["ok"]), (failed, ["messages", ["tat-job-error"]])):
        assert records(log, "job_forked", job.id) == [{"id": job.id}]
        [ended] = records(log, "job_ended", job.id)
        assert ended == {"id": job.id, "failure": failure, "cancelled": False, "duration": ended["duration"]}
        assert ended["duration"] >= 0
    assert records(log, "report_undelivered") == [] and records(log, "bug") == []


async def test_a_bug_in_the_work_ends_the_conversation_of_the_job(conversation):
    """A work that raises a `Bug` reports its message, which ends the
    conversation of the job the table holds; the job's body never sees
    the report; the Isabelle side records `bug` beside `job_ended`."""
    conv, log = conversation.forest.conversation, conversation.log.directory
    job = Job()
    await fork(conv, job, "bug")
    await asyncio.wait_for(job.ending.entered.wait(), 30)
    exn = job.ending.ended_by
    assert isinstance(exn, TAT_InternalError) and str(exn) == "tat-job-bug"
    assert not job.reported.is_set() and job.id not in jobs._evaluation_jobs
    assert records(log, "bug", job.id) == [{"message": "tat-job-bug", "job": job.id}]
    [ended] = records(log, "job_ended", job.id)
    assert (ended["failure"], ended["cancelled"]) == (["bug", "tat-job-bug"], False)


async def test_a_cancelled_work_ends_without_a_report(conversation, tmp_path):
    """`TAT.job_cancel` cancels the futures of the ids it is given, an id
    that is not there being no error: the work is interrupted, `job_ended`
    says so, and nothing is reported."""
    conv, log = conversation.forest.conversation, conversation.log.directory
    job = Job()
    await fork(conv, job, "wait", tmp_path / "never")
    await isabelle_driver.job_cancel(conv, [job.id, 10 ** 9])
    await until(lambda: records(log, "job_ended", job.id))
    [ended] = records(log, "job_ended", job.id)
    assert ended == {"id": job.id, "cancelled": True, "duration": ended["duration"]}
    await asyncio.sleep(0.5)
    assert not job.reported.is_set() and job.ending.ended_by is None
    assert job.id in jobs._evaluation_jobs      # its report will not come: the framework's to discard
    jobs.discard(job.id)
    assert job.id not in jobs._evaluation_jobs
    await isabelle_driver.job_cancel(conv, [job.id])       # cancelled already: no error


async def test_a_reset_cancels_the_jobs_and_their_records_stay_in_their_conversations_log(
        conversation, tmp_path):
    """`TAT.reset` cancels every job's future first and counts them in its
    record; the task that ends afterwards writes into the log it found at
    its fork, the log of the conversation that forked it, and reports
    nothing."""
    conv, old = conversation.forest.conversation, conversation.log.directory
    job = Job()
    await fork(conv, job, "wait", tmp_path / "never")
    renewed = await conversation.restart()
    new = renewed.log.directory
    assert new != old
    await until(lambda: records(old, "job_ended", job.id))
    [reset] = records(old, "reset")
    assert reset["futures_cancelled"] == 1
    assert [e["cancelled"] for e in records(old, "job_ended", job.id)] == [True]
    assert records(new, "job_forked") == [] and records(new, "job_ended") == []
    assert not job.reported.is_set()
    jobs.discard(job.id)


async def test_a_library_theory_loads_from_source_beside_a_running_work(conversation, tmp_path):
    """EVALUATOR_DESIGN §6, verified: the load of a theory in no heap, with
    its `Execution.reset`, neither waits for a job's work nor cancels it —
    the load completes while the work still runs, and the work then ends
    as it would have.  TAT_Lib_Job_Helper.thy is this case's alone: `Thy_Info`
    is the process's, so a second load would be skipped."""
    conv, log = conversation.forest.conversation, conversation.log.directory
    probes = Probes(conv)
    helper = "Theory_Agent_over_Trees.TAT_Lib_Job_Helper"
    assert await probes.short_name("TAT_Lib_Job_Helper") == isabelle_driver.Free(), (
        "TAT_Lib_Job_Helper is already loaded: another case imports it")
    job, gate = Job(), tmp_path / "gate"
    await fork(conv, job, "wait", gate)
    v = await probes.begun(f"theory TAT_Test_J imports {helper} begin")
    recs = await probes.run(v, v, 'lemma "tat_lib_z = 2" by (simp add: tat_lib_z_def)')
    assert not errors(recs), recs
    assert [r["name"] for r in records(log, "theory_loaded")] == [helper]
    assert not job.reported.is_set() and records(log, "job_ended", job.id) == []   # still running
    gate.write_text("")
    await asyncio.wait_for(job.reported.wait(), 30)
    assert job.errors == []
    assert [e["cancelled"] for e in records(log, "job_ended", job.id)] == [False]
