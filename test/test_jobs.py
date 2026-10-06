"""`jobs.py` with no Isabelle: the construction jobs — the run and its
settlement, the cancels and what they tell, the questions, what delivery
drops, the context change, the carry on an amend, the store's image, the
ending's cancel and the bound on runs (CONSTRUCT_INTERACTION §3.1, §3.2,
§3.4, §9) — and the process's table of evaluation jobs with the report
`job_finished` hands to a job (§3.3), whose wire is test_fork_job.py's.
The node classes are the case's own, as test_model.py's are: the leaf of
kind `lemma` carries the construction job titled `proof construction`.
Run: python -m pytest test/test_jobs.py
"""

import asyncio
import dataclasses
import json
from types import SimpleNamespace

import pytest

import invariants
import stand_ins
import test_model as tm
from isabelle_theory_agent import edit, jobs, model as M
from isabelle_theory_agent.exceptions import BadAnswer, NoQuestionPending, TAT_InternalError, TAT_StartupError
from isabelle_theory_agent.jobs import NOT_STARTED, RUNNING, Answered, Failed, Message, Succeeded
from isabelle_theory_agent.store import Forest_Store
from test_model import CONN, READY, Block, T, add, locked, run, slot


@pytest.fixture(autouse=True)
def table(monkeypatch):
    tm.TABLE.clear()
    tm.TABLE.install(monkeypatch)
    jobs._evaluation_jobs.clear()
    yield
    jobs._evaluation_jobs.clear()


# --- the case's classes -----------------------------------------------------

async def proven(job):
    return Succeeded("by simp")


def ends(outcome):
    async def ending(job):
        return outcome
    return ending


def raises(exn):
    async def ending(job):
        raise exn
    return ending


class Proof(jobs.Construction_Job):
    """A run the case drives: it begins, waits for `release`, then ends as
    `ends_with` says — an outcome returned, an exception, a question
    asked first — and counts its cleanup, which `unwind` can hold."""

    @classmethod
    def title(cls, plural=False):
        return "proof constructions" if plural else "proof construction"

    @classmethod
    def failure_header(cls, failure):
        return "No proof was found:"

    def __init__(self, node):
        super().__init__(node)
        self.release = asyncio.Event()
        self.unwind = asyncio.Event()
        self.unwind.set()
        self.ends_with = proven
        self.swallows_cancel = False
        self.began = 0
        self.cleaned = 0

    async def _run(self):
        self.began += 1
        try:
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                if not self.swallows_cancel:
                    raise
            return await self.ends_with(self)
        finally:
            try:                                   # bounded, so a wrong implementation fails instead of hanging
                await asyncio.wait_for(self.unwind.wait(), 1.0)
            except TimeoutError:
                pass
            self.cleaned += 1


class Lemma(T):
    construction_job_class = Proof


class Carrying(Lemma):
    """A class whose amend carries the old job's outcome, as `Theorem` does
    when the statement is unchanged (THEOREM.md §4); its `gen` takes a
    moment, in which the old run may settle."""
    @classmethod
    async def gen(cls, config, raw):
        node = await super().gen(config, raw)
        old = config.replaces()
        if old is not None:
            node.carry_job_from(old)
            await asyncio.sleep(0.02)
        return node


class Verdict(jobs.Interactive_Question):
    text = "Accept the proof?"
    schema = {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["accept", "reject"]}},
              "required": ["verdict"], "additionalProperties": False}

    def receive(self, answer):
        if answer["verdict"] == "accept":
            return Answered()
        return Why()


class Why(jobs.Interactive_Question):
    text = "Why not?"
    schema = {"type": "object", "properties": {"reason": {"type": "string"}},
              "required": ["reason"], "additionalProperties": False}

    def receive(self, answer):
        if not answer["reason"]:
            raise BadAnswer("A rejection needs a reason.")
        self.reason = answer["reason"]
        return Answered("Noted.")


KINDS = {"block": Block, "t": T, "lemma": Lemma, "carrying": Carrying}
P = "block_Theory.lemma_P"


def build(lemma=Lemma):
    """Theory > [T1, lemma P, lemma Q], the ending knowing the forest as the
    start does (MODULE_STRUCTURE §4.6)."""
    f = tm.OneTreeForest(CONN, kinds=KINDS)
    f.conversation.ending.forest = f
    thy = add(f, Block(f, slot(), "Theory", slot()))
    t1 = add(thy, T(thy, slot(), "T1"))
    p = add(thy, lemma(thy, slot(), "P"), "carrying" if lemma is Carrying else "lemma")
    q = add(thy, Lemma(thy, slot(), "Q"), "lemma")
    return f, thy, t1, p, q


def records(event):
    return [r["data"] for r in stand_ins.records("job") if r["event"] == event]


def deliver(f, agent):
    return jobs.deliver(f.conversation.log, agent)


async def run_to_end(job, owner):
    """One run that ends as `ends_with` says, awaited to its settlement or
    the conversation's ending."""
    job.release = asyncio.Event()
    job.start(owner)
    job.release.set()
    while job.outcome is RUNNING and not job._conversation.ending.entered:   # polled: no wake-up relied on
        await asyncio.sleep(0.005)


async def runs_unwound(job):
    """Every run's task of the job has ended; bounded, as `Proof`'s cleanup is."""
    if job._runs:
        await asyncio.wait(set(job._runs), timeout=2.0)


# --- the run and its settlement (CONSTRUCT_INTERACTION §3.2) --------------

def test_a_run_settles_and_its_owner_is_told():
    """`start` sets `RUNNING`, stores the node in a transaction of its own
    and spawns the run; a run that returns settles — the outcome stored in
    a transaction of its own, `construction_settled`, `finished_notification`
    posted to the owner, interrupting — succeeded, or failed with the
    message under the sentence, an empty one ending it with a period.  The
    lemma owes its proof until the job succeeded (§3.1)."""
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        job = p.job()
        p._status = READY
        assert job.outcome is NOT_STARTED and job.can_start() and not p.is_finished()
        assert p._unfinished() == jobs.Unfinished_Construction(job) and p._unfinished().title() == "proof construction"
        tm.TABLE.clear_writes()
        job.start(owner)
        assert job.outcome is RUNNING and not job.can_start() and job.owner is owner
        assert (tm.TABLE.transactions, tm.TABLE.touched) == (1, {p.identity})
        assert f.store.get(p.identity, "job") == ["NOT_STARTED"]        # a loaded forest holds no run
        assert records("construction_started") == [{"node": P, "owner": "main"}]
        await asyncio.sleep(0)
        assert job.began == 1
        job.release.set()
        await owner.sleep_until(lambda: job.outcome is not RUNNING)
        assert job.outcome == Succeeded("by simp") and job.can_start() and p.is_finished()
        assert (tm.TABLE.transactions, f.store.get(p.identity, "job")) == (2, ["SUCCEEDED", "by simp"])
        assert records("construction_settled") == [{"node": P, "outcome": "SUCCEEDED"}]   # no message: none recorded
        assert deliver(f, owner) == [f"The proof construction on `{P}` succeeded."]
        assert records("message_posted")[-1]["interrupts"] is True
        job.ends_with = ends(Failed("Sledgehammer timed out on every prover."))
        await run_to_end(job, owner)
        assert job.outcome == Failed("Sledgehammer timed out on every prover.") and not p.is_finished()
        assert f.store.get(p.identity, "job") == ["FAILED", "Sledgehammer timed out on every prover."]
        assert records("construction_settled")[-1] == {
            "node": P, "outcome": "FAILED", "message": "Sledgehammer timed out on every prover."}
        assert deliver(f, owner) == [
            f"The proof construction on `{P}` failed:\n  Sledgehammer timed out on every prover."]
        job.ends_with = ends(Failed(""))
        await run_to_end(job, owner)
        assert deliver(f, owner) == [f"The proof construction on `{P}` failed."]
        job.ends_with = ends("by simp")                      # no outcome: a bug
        await run_to_end(job, owner)
        assert isinstance(f.conversation.ending.ended_by, TAT_InternalError)
        assert "which is no outcome" in str(f.conversation.ending.ended_by)
        assert q.job().outcome is NOT_STARTED and not q.is_finished()
        q._status = READY
        q.job().compulsory = False                           # the class's: not compulsory, nothing owed
        assert q._unfinished() is None and q.is_finished()
    run(scenario())


def test_a_run_that_raises_is_a_bug_the_ending_takes_and_cancels():
    """Anything a run raises while it is the job's — a cancellation it
    brought on itself included — is a bug: the conversation ends, and the
    ending cancels the job through `cancel(None)`, nothing told."""
    for exn, in_message in ((RuntimeError("the prover vanished"), None),
                            (asyncio.CancelledError(), "cancelled itself")):
        async def scenario():
            f, thy, t1, p, q = build()
            owner = stand_ins.agent(f.conversation)
            job = p.job()
            job.ends_with = raises(exn)
            job.start(owner)
            job.release.set()
            await f.conversation.ending.wait()
            ended_by = f.conversation.ending.ended_by
            assert type(ended_by) is (TAT_InternalError if in_message else type(exn))
            if in_message:
                assert in_message in str(ended_by)
            assert job.outcome is NOT_STARTED and records("construction_settled") == []
            assert records("construction_cancelled")[-1] == {"node": P}   # no reason: none recorded
            await runs_unwound(job)
            assert deliver(f, owner) == [] and job.cleaned == 1
        run(scenario())


def test_a_cancelled_run_that_returns_settles_nothing():
    """A run that is no longer the job's was cancelled: whatever it returns
    after swallowing the cancellation, the wrapper does nothing."""
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        job = p.job()
        job.swallows_cancel = True
        job.start(owner)
        await asyncio.sleep(0)
        job.cancel(None)
        await runs_unwound(job)
        assert (job.began, job.cleaned, job.outcome) == (1, 1, NOT_STARTED)
        assert records("construction_settled") == [] and deliver(f, owner) == []
        assert f.store.get(p.identity, "job") == ["NOT_STARTED"] and not f.conversation.ending.entered
    run(scenario())


def test_a_rerun_waits_for_the_earlier_runs_task_to_unwind():
    """The wrapper waits for every earlier run of the job that has not
    unwound — a cancelled run's cleanup included — before the work
    begins; the new run is `RUNNING` meanwhile."""
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        job = p.job()
        job.unwind.clear()                                   # the first run's cleanup holds
        job.start(owner)
        await asyncio.sleep(0)
        job.cancel(None)
        job.release = asyncio.Event()
        job.start(owner)                                     # a second run at once
        await asyncio.sleep(0.01)
        assert job.outcome is RUNNING and (job.began, job.cleaned) == (1, 0)
        job.unwind.set()
        await asyncio.sleep(0.01)
        assert (job.began, job.cleaned) == (2, 1)
        job.release.set()
        await owner.sleep_until(lambda: job.outcome is not RUNNING)
        assert job.outcome == Succeeded("by simp") and job.cleaned == 2
    run(scenario())


# --- the cancels (§3.2) -----------------------------------------------------

@pytest.mark.parametrize("reason, why", [
    ("NODE_DELETED", "the node was deleted."), ("NODE_AMENDED", "the node was amended."),
    ("CONTEXT_CHANGED", "its context changed.")])
def test_a_cancel_by_the_framework_tells_the_owner_why_and_writes_nothing(reason, why):
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        job = p.job()
        job.start(owner)
        await asyncio.sleep(0)
        tm.TABLE.clear_writes()
        job.cancel(reason)
        assert job.outcome is NOT_STARTED and job.can_start() and tm.TABLE.transactions == 0
        assert records("construction_cancelled") == [{"node": P, "reason": reason}]
        assert deliver(f, owner) == [f"The proof construction on `{P}` was cancelled: {why}"]
        await runs_unwound(job)
        assert job.cleaned == 1
        job.cancel(reason)                                   # nothing runs: nothing to cancel
        assert len(records("construction_cancelled")) == 1 and deliver(f, owner) == []
    run(scenario())


def test_cancel_construct_and_the_ending_tell_nothing():
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        p.job().start(owner)
        p.job().cancel(None)
        assert records("construction_cancelled") == [{"node": P}] and deliver(f, owner) == []
    run(scenario())


# --- the questions (§3.4) ----------------------------------------------------

async def asking(job):
    question = Verdict()
    await job.ask(question)
    job.asked = question
    return Succeeded("by simp")


def question_text(title_on, question):
    return (f"The proof construction on `{P}` asks:\n{question.text}\n"
            f"Answer with the `answer` tool, node_id `{P}`; the answer must follow the JSON schema:\n"
            + json.dumps(question.schema, indent=2))


def test_the_questions_round_trip():
    """`ask` posts the question, interrupting, in its delivered form and
    suspends the run; `receive` may ask another question instead, which
    replaces the pending one and is delivered the same way, refuse with
    `BadAnswer`, the question staying, or accept — the `answer` tool's
    text its response, by default `answered_notice` — and the run goes
    on."""
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        job = p.job()
        job.ends_with = asking
        job.start(owner)
        job.release.set()
        await owner.sleep_until(lambda: job.pending_question is not None)
        first = job.pending_question
        assert isinstance(first, Verdict) and job.outcome is RUNNING
        assert deliver(f, owner) == [question_text(P, first)]
        posted = records("message_posted")[-1]
        assert (posted["kind"], posted["interrupts"], posted["source"]) == (
            "question", True, f"run of the proof construction on `{P}`")
        assert job.receive_answer({"verdict": "reject"}) is None
        second = job.pending_question
        assert isinstance(second, Why) and first is not second
        assert deliver(f, owner) == [question_text(P, second)]
        with pytest.raises(BadAnswer, match="A rejection needs a reason."):
            job.receive_answer({"reason": ""})
        assert job.pending_question is second and job.outcome is RUNNING
        assert job.receive_answer({"reason": "too long"}) == "Noted."
        assert job.pending_question is None and second.reason == "too long"
        await owner.sleep_until(lambda: job.outcome is not RUNNING)
        assert job.outcome == Succeeded("by simp") and job.asked is first
        assert [r["outcome"] for r in records("question_answered")] == ["replaced", "refused", "accepted"]
        assert records("question_withdrawn") == []
        with pytest.raises(TAT_InternalError, match="no pending question"):
            job.receive_answer({"verdict": "accept"})
        deliver(f, owner)
        job.release = asyncio.Event()                        # accepted at once: the default notice
        job.start(owner)
        job.release.set()
        await owner.sleep_until(lambda: job.pending_question is not None)
        assert job.receive_answer({"verdict": "accept"}) == (
            f"Answered the proof construction on `{P}`; call `check_construct` before you exit.")
        await owner.sleep_until(lambda: job.outcome is not RUNNING)
        assert job.outcome == Succeeded("by simp")
    run(scenario())


def test_a_question_is_withdrawn_by_a_cancel_and_by_the_settlement_and_delivery_drops_it():
    """A cancel withdraws the pending question — `question_withdrawn`, the
    `ask` cancelled — and delivery drops the question, the run being no
    longer its job's, while the framework's notification stands; a stray
    asking branch ends with the settlement, which withdraws its question."""
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        job = p.job()
        job.ends_with = asking
        job.start(owner)
        job.release.set()
        await owner.sleep_until(lambda: job.pending_question is not None)
        job.cancel("CONTEXT_CHANGED")
        assert job.pending_question is None and records("question_withdrawn") == [{"node": P}]
        await runs_unwound(job)
        assert job.cleaned == 1
        assert deliver(f, owner) == [f"The proof construction on `{P}` was cancelled: its context changed."]
        assert records("message_dropped") == [{"recipient": "main", "reason": "the run is no longer its job's"}]
        branches = []

        async def stray(job):
            branches.append(asyncio.ensure_future(job.ask(Verdict())))
            await asyncio.sleep(0)
            return Succeeded("by simp")
        job.ends_with = stray
        await run_to_end(job, owner)
        assert job.outcome == Succeeded("by simp") and job.pending_question is None
        assert len(records("question_withdrawn")) == 2
        with pytest.raises(asyncio.CancelledError):
            await branches[0]
        assert deliver(f, owner) == [f"The proof construction on `{P}` succeeded."]
        assert records("message_dropped")[-1]["reason"] == "the question is no longer its job's pending question"
    run(scenario())


def test_a_question_asks_only_within_the_grammar_and_from_a_run():
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        job = p.job()

        class Loose(Verdict):
            schema = {"type": "object", "properties": {"verdict": {"type": "string"}},
                      "required": ["verdict"], "additionalProperties": False, "$defs": {"X": {}}}
        job.ends_with = raises(None)                         # replaced below

        async def asks_loosely(job):
            await job.ask(Loose())
            return Succeeded("by simp")
        job.ends_with = asks_loosely
        job.start(owner)
        job.release.set()
        await f.conversation.ending.wait()
        assert "carries `$defs`" in str(f.conversation.ending.ended_by)
        assert job.pending_question is None and deliver(f, owner) == []
    run(scenario())


def test_a_runs_own_notification_is_dropped_once_the_run_is_cancelled():
    """A message a run posts of its own stands while the run is the job's,
    and after its settlement; a cancelled run leaves none behind (§3.4)."""
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        job = p.job()
        gate = asyncio.Event()

        async def telling(job):
            jobs.post(f.conversation.log, Message(owner, "halfway", interrupts=False, source=job._current))
            await gate.wait()
            return Succeeded("by simp")
        job.ends_with = telling
        job.start(owner)
        job.release.set()
        await asyncio.sleep(0)
        assert jobs.waiting(owner) == ["halfway"]
        job.cancel(None)
        assert deliver(f, owner) == [] and records("message_dropped")[-1]["reason"] == "the run is no longer its job's"
        job.release = asyncio.Event()
        job.start(owner)
        job.release.set()
        await asyncio.sleep(0)
        gate.set()
        await owner.sleep_until(lambda: job.outcome is not RUNNING)
        assert deliver(f, owner) == ["halfway", f"The proof construction on `{P}` succeeded."]
    run(scenario())


# --- the context (§3.2; MODULE_STRUCTURE §4.1) ------------------------------

def test_a_write_of_the_status_by_the_walk_tells_the_running_job():
    """Every write of the node's own status while the job runs — a rerun's
    rewrite of `ready` included — calls `_on_context_change`, which cancels
    by default with `CONTEXT_CHANGED`; a class that can carry on overrides
    it; one that raises a `TAT_Error` is the class's bug, under an edit as
    under a walk."""
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        await thy.evaluate_to(False)                         # takes the lock itself
        assert p._status == READY
        job = p.job()
        job.start(owner)
        ev = M.Evaluation(None, False)
        p._set_status(ev, M.Ready(), 0.1)                    # `ready` over `ready`: a rerun
        assert job.outcome is NOT_STARTED
        assert records("construction_cancelled") == [{"node": P, "reason": "CONTEXT_CHANGED"}]
        assert deliver(f, owner) == [f"The proof construction on `{P}` was cancelled: its context changed."]
        noticed = []
        job._on_context_change = lambda: noticed.append(p._status)   # type: ignore[method-assign]
        job.start(owner)
        p._set_status(ev, M.NOT_EVALUATED, None)
        assert noticed == [M.NOT_EVALUATED] and job.outcome is RUNNING
        job.cancel(None)

        def fussy():
            raise NoQuestionPending("x")
        q.job()._on_context_change = fussy                   # type: ignore[method-assign]
        q.job().start(owner)
        with pytest.raises(TAT_InternalError, match="completed hook"):
            await locked(f, edit.delete(t1))                 # invalidates P and Q: the hook raises
    run(scenario())


# --- the edit (§3.1, §9; MODULE_STRUCTURE §4.2) ------------------------------

def test_a_delete_or_an_amend_cancels_the_running_job_naming_the_node_it_belonged_to():
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        p.job().start(owner)
        q.job().start(owner)
        await asyncio.sleep(0)
        await locked(f, edit.delete(p))
        assert p.job().outcome is NOT_STARTED and q.job().outcome is RUNNING
        assert records("construction_cancelled") == [{"node": P, "reason": "NODE_DELETED"}]
        (q2,) = await locked(f, edit.amend(q, [{"kind": "lemma", "name": "Q2"}], KINDS))
        assert q.job().outcome is NOT_STARTED and q2.job().outcome is NOT_STARTED
        assert records("construction_cancelled")[-1] == {"node": "block_Theory.lemma_Q", "reason": "NODE_AMENDED"}
        assert deliver(f, owner) == [
            f"The proof construction on `{P}` was cancelled: the node was deleted.",
            "The proof construction on `block_Theory.lemma_Q` was cancelled: the node was amended."]
        assert q2.job().auto_construct is False
        invariants.assert_store_mirrors(f, KINDS)
    run(scenario())


def test_an_amend_carries_the_old_jobs_image_where_gen_asked():
    """`carry_job_from(old)` in `gen` has the commit copy the old job's image
    — a settlement between `gen` and the commit is in it; a run still going
    reads as `NOT_STARTED` — and nothing without the call."""
    async def scenario():
        f, thy, t1, p, q = build(Carrying)
        owner = stand_ins.agent(f.conversation)
        p.job().outcome = Succeeded("by simp")
        (p2,) = await locked(f, edit.amend(p, [{"kind": "carrying", "name": "P2"}], KINDS))
        assert p2.job().outcome == Succeeded("by simp") and f.store.get(p2.identity, "job") == ["SUCCEEDED", "by simp"]
        p2.job().start(owner)                                # settles during the next gen
        p2.job().release.set()
        (p3,) = await locked(f, edit.amend(p2, [{"kind": "carrying", "name": "P3"}], KINDS))
        assert p2.job().outcome == Succeeded("by simp") and p3.job().outcome == Succeeded("by simp")
        assert records("construction_cancelled") == []
        p3.job().start(owner)                                # still running at the commit
        (p4,) = await locked(f, edit.amend(p3, [{"kind": "carrying", "name": "P4"}], KINDS))
        assert p4.job().outcome is NOT_STARTED
        assert records("construction_cancelled") == [{"node": "block_Theory.carrying_P3", "reason": "NODE_AMENDED"}]
        q.job().outcome = Succeeded("by auto")
        (q2,) = await locked(f, edit.amend(q, [{"kind": "lemma", "name": "Q2"}], KINDS))
        assert q2.job().outcome is NOT_STARTED               # a plain class carries nothing
        invariants.assert_store_mirrors(f, KINDS)
    run(scenario())


# --- the store (ARCHITECTURE §4.1) -------------------------------------------

def test_the_rows_across_a_reload():
    """The `job` row is the outcome with `RUNNING` read as `NOT_STARTED`,
    `auto_construct` the setting; a missing row reads as `NOT_STARTED` and
    off, a row of another shape is refused."""
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        job = p.job()
        job.start(owner)
        invariants.assert_store_mirrors(f, KINDS)
        job.auto_construct = True
        job.release.set()
        await owner.sleep_until(lambda: job.outcome is not RUNNING)
        invariants.assert_store_mirrors(f, KINDS)
        twin = tm.OneTreeForest(CONN, f.store, KINDS)
        loaded = twin.sub_nodes[0].sub_nodes[1].job()
        assert (loaded.outcome, loaded.auto_construct) == (Succeeded("by simp"), True)
        job.ends_with = ends(Failed("no proof"))
        await run_to_end(job, owner)
        invariants.assert_store_mirrors(f, KINDS)
        with f.store.transaction():                          # rows a database before the jobs lacks
            f.store.delete_node(q.identity)
            f.store.put(q.identity, "kind", "lemma")
            f.store.put(q.identity, "name", "Q")
            f.store.put(q.identity, "fail", False)
        twin = tm.OneTreeForest(CONN, f.store, KINDS)
        bare = twin.sub_nodes[0].sub_nodes[2].job()
        assert (bare.outcome, bare.auto_construct) == (NOT_STARTED, False)
        with f.store.transaction():
            f.store.put(q.identity, "job", ["RUNNING"])
        with pytest.raises(TAT_StartupError, match="not a job's image"):
            tm.OneTreeForest(CONN, f.store, KINDS)
    run(scenario())


# --- the ending (§9) and the bound (CONSTRUCT_DECISIONS §15) ----------------

def test_the_ending_cancels_every_running_job_with_no_round_trip_and_no_write():
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        p.job().start(owner)
        q.job().start(owner)
        await asyncio.sleep(0)
        tm.TABLE.clear_writes()
        calls = len(tm.TABLE.calls)
        f.conversation.ending.end(RuntimeError("over"))
        assert p.job().outcome is NOT_STARTED and q.job().outcome is NOT_STARTED
        assert [r.get("reason") for r in records("construction_cancelled")] == [None, None]
        assert (tm.TABLE.transactions, len(tm.TABLE.calls)) == (0, calls)
        await runs_unwound(p.job())
        await runs_unwound(q.job())
        assert deliver(f, owner) == [] and p.job().cleaned == 1 and q.job().cleaned == 1
    run(scenario())


class Bounded(tm.OneTreeForest):
    """A forest of a conversation bounding its construction runs to one."""
    def __init__(self, conn):
        conversation = dataclasses.replace(stand_ins.conversation(conn), max_concurrent_construction_jobs=1)
        M.Forest.__init__(self, conversation, Forest_Store(":memory:", stand_ins.log()), KINDS)
        self._end = M.Isar_State_Slot.assign(self.conversation)


def test_the_bound_holds_a_run_which_is_running_meanwhile():
    async def scenario():
        f = Bounded(CONN)
        f.conversation.ending.forest = f
        thy = add(f, Block(f, slot(), "Theory", slot()))
        p = add(thy, Lemma(thy, slot(), "P"), "lemma")
        q = add(thy, Lemma(thy, slot(), "Q"), "lemma")
        owner = stand_ins.agent(f.conversation)
        p.job().start(owner)
        q.job().start(owner)
        await asyncio.sleep(0.01)
        assert (p.job().began, q.job().began) == (1, 0) and q.job().outcome is RUNNING
        p.job().cancel(None)                                 # frees the place
        await asyncio.sleep(0.01)
        assert q.job().began == 1
        q.job().release.set()
        await owner.sleep_until(lambda: q.job().outcome is not RUNNING)
        assert q.job().outcome == Succeeded("by simp")
    run(scenario())


# --- the evaluation jobs' wire (§3.3) ----------------------------------------

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
