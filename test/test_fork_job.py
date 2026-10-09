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

import pytest

import stand_ins
from isabelle_theory_agent import edit, isabelle_driver, jobs, model as M
from isabelle_theory_agent.exceptions import TAT_InternalError
from isabelle_theory_agent.isabelle_driver import call
from test_conversation import Probes, errors


class Recorded_Ending:
    """In place of a conversation's ending object: what a report ends the
    conversation with is kept here, and the harness's conversation, which
    the run's later cases need, goes on."""

    def __init__(self):
        self.ended_by: BaseException | None = None
        self.ended = asyncio.Event()

    @property
    def entered(self) -> bool:
        return self.ended_by is not None

    def end(self, ended_by: BaseException) -> None:
        if self.ended_by is None:
            self.ended_by = ended_by
            self.ended.set()


class Job:
    """A stand-in for an evaluation job: in the process's table from its
    making, it keeps the report it is given."""

    def __init__(self):
        self.ending = Recorded_Ending()
        self.conversation = SimpleNamespace(ending=self.ending)
        self.reported = asyncio.Event()
        self.errors: list[str] | None = None
        self.id = next(jobs._ids)
        jobs.register(self)                 # type: ignore[arg-type]  # a started job: in the table

    def _report(self, errors: list[str], product=None) -> None:
        self.errors = errors
        self.reported.set()


@pytest.fixture(autouse=True)
def an_empty_table():
    """No stand-in outlives its case in the process's table, however the
    case ends."""
    yield
    jobs._evaluation_jobs.clear()


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
    passed, failed, empty = Job(), Job(), Job()
    await fork(conv, passed, "pass")
    await fork(conv, failed, "fail")
    await fork(conv, empty, "empty")                     # an `ERROR` with no text: one empty message
    await asyncio.wait_for(asyncio.gather(passed.reported.wait(), failed.reported.wait(), empty.reported.wait()), 30)
    assert (passed.errors, failed.errors, empty.errors) == ([], ["tat-job-error"], [""])
    assert passed.ending.ended_by is None and failed.ending.ended_by is None and empty.ending.ended_by is None
    assert not {passed.id, failed.id, empty.id} & set(jobs._evaluation_jobs)
    for job, failure in ((passed, ["ok"]), (failed, ["messages", ["tat-job-error"]]), (empty, ["messages", [""]])):
        assert records(log, "job_forked", job.id) == [{"id": job.id}]
        [ended] = records(log, "job_ended", job.id)
        assert set(ended) == {"id", "failure", "cancelled", "duration"}
        assert (ended["id"], ended["failure"], ended["cancelled"]) == (job.id, failure, False)
        assert isinstance(ended["duration"], float)
    assert records(log, "report_undelivered") == [] and records(log, "bug") == []


async def test_a_bug_in_the_work_ends_the_conversation_of_the_job(conversation):
    """A work that raises a `Bug` reports its message, which ends the
    conversation of the job the table holds; the job's body never sees
    the report; the Isabelle side records `bug` beside `job_ended`."""
    conv, log = conversation.forest.conversation, conversation.log.directory
    job = Job()
    await fork(conv, job, "bug")
    await asyncio.wait_for(job.ending.ended.wait(), 30)
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
    assert set(ended) == {"id", "cancelled", "duration"} and (ended["id"], ended["cancelled"]) == (job.id, True)
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


async def test_a_work_interrupted_by_anything_but_tats_cancel_is_reported_as_a_bug(conversation):
    """A work that is interrupted while TAT has not cancelled it would leave
    a job Python waits for: it is reported as a bug, which ends the job's
    conversation, and `job_ended` does not call it cancelled."""
    conv, log = conversation.forest.conversation, conversation.log.directory
    job = Job()
    await fork(conv, job, "interrupt")
    await asyncio.wait_for(job.ending.ended.wait(), 30)
    message = "fork_job: the work was interrupted, and TAT had not cancelled it"
    assert isinstance(job.ending.ended_by, TAT_InternalError) and str(job.ending.ended_by) == message
    [ended] = records(log, "job_ended", job.id)
    assert (ended["failure"], ended["cancelled"]) == (["bug", message], False)


# --- the test plugin's node class: both jobs over the wire (the jobs plan, step 9)

def note(name: str, work: str = "pass") -> dict:
    return {"kind": "note", "name": name, "text": f"the note {name}", "work": work}


async def test_the_notes_jobs_over_the_wire(conversation):
    """The test plugin's `note` (tat_test_plugin): its evaluation job's work
    is forked by `TAT_test.fork_job` and settles by the report — `PASSED`,
    or `FAILED` with the work's message posted to the starter; one dropped
    by an edit has its future cancelled on the Isabelle side; its
    construction job asks one question and settles by the answer."""
    forest, kinds, log = conversation.forest, conversation.kinds, conversation.log.directory
    conv = forest.conversation
    agent = stand_ins.agent(conv)

    async def insert(parent, index, raws):
        async with forest.lock:
            return await edit.insert(parent, index, raws, kinds)

    (sess,) = await insert(forest, 0, [
        {"kind": "session", "name": "TAT_NOTES", "parent_session": "HOL",
         "children": [{"kind": "theory", "name": "TAT_NOTES_A", "imports": ["Main"],
                       "children": [note("P"), note("Q", "fail"), note("R", "wait")]}]}])
    (thy,) = sess.sub_nodes
    p, q, r = thy.sub_nodes
    await thy.evaluate_to(None, False)
    assert all(isinstance(n._status, M.Ready) for n in (p, q, r)), [n._status for n in (p, q, r)]
    for n in (p, q, r):
        await n.start_evaluation_job(agent)
    checks = [n.evaluation_job() for n in (p, q, r)]
    await until(lambda: checks[0].ended and checks[1].ended)
    assert p.check_outcome() is jobs.PASSED and q.check_outcome() == jobs.Failed("tat-job-error")
    assert jobs.deliver(conv.log, agent) == [f"The note check on `{forest.id_of(q)}` failed."]
    assert records(log, "job_ended", checks[0].id)[0]["failure"] == ["ok"]
    # the waiting work: dropped by the edit that deletes its node, cancelled on the Isabelle side
    await until(lambda: records(log, "job_forked", checks[2].id))
    async with forest.lock:
        await edit.delete(r)
    assert checks[2].ended and r.evaluation_job() is None
    await until(lambda: records(log, "job_ended", checks[2].id))
    [ended] = records(log, "job_ended", checks[2].id)
    assert ended["cancelled"] is True
    assert checks[2].id not in jobs._evaluation_jobs             # the drop discarded it (§3.3, R9); a late report is nobody's
    # the construction job: one question, settled by the answer
    job = p.job()
    assert job.can_start()
    job.start(agent)
    await until(lambda: job.pending_question is not None)
    assert jobs.deliver(conv.log, agent)[0].startswith(f"The note construction on `{forest.id_of(p)}` asks:\nAccept the note?")
    assert job.receive_answer({"verdict": "accept"}) == (
        f"Answered the note construction on `{forest.id_of(p)}`; call `check_construct` before you exit.")
    await until(lambda: job.outcome is not jobs.RUNNING)
    assert job.outcome == jobs.Succeeded("accept") and p.is_finished() is False   # its check was dropped by the start
    assert p.check_outcome() is None
