"""`jobs.py` with no Isabelle: the process's table of evaluation jobs and the
report `job_finished` hands to a job (CONSTRUCT_INTERACTION §3.3).  The
wire itself is test_fork_job.py's.  Run: python -m pytest test/test_jobs.py
"""

import asyncio
from types import SimpleNamespace

import pytest

from isabelle_theory_agent import jobs
from isabelle_theory_agent.exceptions import TAT_InternalError


class Ending:
    def __init__(self):
        self.ended_by: BaseException | None = None

    @property
    def entered(self) -> bool:
        return self.ended_by is not None

    def end(self, ended_by: BaseException) -> None:
        self.ended_by = self.ended_by or ended_by


class Job:
    """A stand-in for an evaluation job; `_report` notes whether the table
    still held the job when its body ran."""

    def __init__(self, raises: BaseException | None = None):
        self.conversation = SimpleNamespace(ending=Ending())
        self.reports: list[list[str]] = []
        self.in_the_table_at_the_report: bool | None = None
        self.raises = raises
        self.id = jobs.register(self)       # type: ignore[arg-type]

    def _report(self, errors: list[str]) -> None:
        self.in_the_table_at_the_report = self.id in jobs._evaluation_jobs
        self.reports.append(errors)
        if self.raises is not None:
            raise self.raises


@pytest.fixture(autouse=True)
def an_empty_table():
    jobs._evaluation_jobs.clear()
    yield
    jobs._evaluation_jobs.clear()


def finished(id: int, failure: list) -> None:
    asyncio.run(jobs.job_finished((id, failure), None))        # type: ignore[arg-type]


def test_a_report_is_handed_to_its_job_alone_and_takes_it_out_of_the_table():
    one, other = Job(), Job()
    finished(one.id, ["ok"])
    finished(other.id, ["messages", ["first", "second"]])
    assert (one.reports, other.reports) == ([[]], [["first", "second"]])
    assert one.in_the_table_at_the_report is False      # taken out before the body runs
    assert jobs._evaluation_jobs == {} and not one.conversation.ending.entered
    finished(one.id, ["messages", ["again"]])            # a second report is nobody's
    assert one.reports == [[]]


def test_a_bug_ends_the_conversation_of_its_job_and_no_other():
    one, other = Job(), Job()
    finished(one.id, ["bug", "the work caught itself out"])
    exn = one.conversation.ending.ended_by
    assert isinstance(exn, TAT_InternalError) and str(exn) == "the work caught itself out"
    assert one.reports == [] and not other.conversation.ending.entered
    assert set(jobs._evaluation_jobs) == {other.id}


def test_what_the_body_raises_and_a_report_of_no_known_shape_end_the_conversation():
    raising, malformed = Job(raises=RuntimeError("body-bug")), Job()
    finished(raising.id, ["ok"])
    assert isinstance(raising.conversation.ending.ended_by, RuntimeError)
    finished(malformed.id, ["passed"])
    assert isinstance(malformed.conversation.ending.ended_by, TAT_InternalError) and malformed.reports == []


def test_a_report_for_no_job_or_for_a_conversation_that_ended_is_dropped():
    gone, ended = Job(), Job()
    jobs.discard(gone.id)
    jobs.discard(gone.id)                                # not there: no error
    finished(gone.id, ["bug", "nobody hears"])           # nobody's
    finished(10 ** 9, ["ok"])
    ended.conversation.ending.end(RuntimeError("ended"))
    finished(ended.id, ["messages", ["late"]])
    assert gone.reports == [] and ended.reports == [] and not gone.conversation.ending.entered


def test_an_id_is_never_handed_out_twice():
    first = Job()
    jobs.discard(first.id)
    second = Job()
    assert second.id > first.id
    finished(first.id, ["ok"])                           # the discarded job's late report
    assert second.reports == [] and set(jobs._evaluation_jobs) == {second.id}
