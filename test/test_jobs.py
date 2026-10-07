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
from isabelle_theory_agent import edit, isabelle_driver, jobs, model as M, plugin
from isabelle_theory_agent.exceptions import BadAnswer, NoQuestionPending, TAT_InternalError, TAT_StartupError
from isabelle_theory_agent.jobs import NOT_STARTED, PASSED, RUNNING, Answered, Failed, Message, Succeeded
from isabelle_theory_agent.log import current_agent
from isabelle_theory_agent.store import Forest_Store
from test_model import CONN, READY, Block, T, add, locked, run, slot


async def until(agent, holds) -> None:
    """The agent's sleep until `holds()`, bounded: a wrong implementation
    fails the case instead of hanging the suite."""
    await asyncio.wait_for(agent.sleep_until(holds), 2.0)

CANCELS: list[list[int]] = []               # every `TAT.job_cancel` round trip's ids


def isolated(monkeypatch):
    """A case's jobs with no Isabelle: `TAT.job_cancel`'s round trips land
    in CANCELS, and the process's table of evaluation jobs is the case's
    own.  For a fixture's `yield from`."""
    CANCELS.clear()

    async def job_cancel(conversation, ids):
        CANCELS.append(list(ids))
    monkeypatch.setattr(isabelle_driver, "job_cancel", job_cancel)
    jobs._evaluation_jobs.clear()
    yield
    jobs._evaluation_jobs.clear()


@pytest.fixture(autouse=True)
def table(monkeypatch):
    tm.TABLE.clear()
    tm.TABLE.install(monkeypatch)
    yield from isolated(monkeypatch)


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


class Check(jobs.Evaluation_Job):
    """A check whose work is the case's to end: `_start` begins nothing, the
    report settles it."""

    @classmethod
    def title(cls, plural=False):
        return "proof checks" if plural else "proof check"

    @classmethod
    def failure_header(cls, failure):
        return "The proof no longer holds:"

    @classmethod
    def failure_notification(cls, ids, automatic):
        head = jobs.listed(ids, lambda on: f"The proof {on} no longer holds",
                           "The following proofs no longer hold:")
        return head + (", so its proof construction was started automatically." if automatic
                       else ". Call `construct` to prove it again.")

    def __init__(self, node, starter):
        super().__init__(node, starter)
        self.began = False

    async def _start(self):
        self.began = True


class Checked(Lemma):
    evaluation_job_class = Check


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


KINDS = {"block": Block, "t": T, "lemma": Lemma, "carrying": Carrying, "checked": Checked}
P, Q = "block_Theory.lemma_P", "block_Theory.lemma_Q"
P_CHECKED, Q_CHECKED = "block_Theory.checked_P", "block_Theory.checked_Q"


def build(lemma=Lemma):
    """Theory > [T1, lemma P, lemma Q], the ending knowing the forest as the
    start does (MODULE_STRUCTURE §4.6)."""
    f = tm.OneTreeForest(CONN, kinds=KINDS)
    f.conversation.ending.forest = f
    thy = add(f, Block(f, slot(), "Theory", slot()))
    t1 = add(thy, T(thy, slot(), "T1"))
    kind = {Carrying: "carrying", Checked: "checked"}.get(lemma, "lemma")
    p = add(thy, lemma(thy, slot(), "P"), kind)
    q = add(thy, lemma(thy, slot(), "Q"), kind)
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
        await until(owner,lambda: job.outcome is not RUNNING)
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
        await until(owner,lambda: job.outcome is not RUNNING)
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
        await until(owner,lambda: job.pending_question is not None)
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
        await until(owner,lambda: job.outcome is not RUNNING)
        assert job.outcome == Succeeded("by simp") and job.asked is first
        assert [r["outcome"] for r in records("question_answered")] == ["replaced", "refused", "accepted"]
        assert records("question_withdrawn") == []
        with pytest.raises(TAT_InternalError, match="no pending question"):
            job.receive_answer({"verdict": "accept"})
        deliver(f, owner)
        job.release = asyncio.Event()                        # accepted at once: the default notice
        job.start(owner)
        job.release.set()
        await until(owner,lambda: job.pending_question is not None)
        assert job.receive_answer({"verdict": "accept"}) == (
            f"Answered the proof construction on `{P}`; call `check_construct` before you exit.")
        await until(owner,lambda: job.outcome is not RUNNING)
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
        await until(owner,lambda: job.pending_question is not None)
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
            await asyncio.wait_for(branches[0], 2.0)
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
        await until(owner,lambda: job.outcome is not RUNNING)
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
        await thy.evaluate_to(None, False)                         # takes the lock itself
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
        await until(owner,lambda: job.outcome is not RUNNING)
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
        await until(owner,lambda: q.job().outcome is not RUNNING)
        assert q.job().outcome == Succeeded("by simp")
    run(scenario())


# --- the evaluation jobs (§3.3; ARCHITECTURE §4.1) ---------------------------

async def report(job, errors=()):
    """The ML side's report of the job's work, as `job_finished` hands it on."""
    await jobs.job_finished((job.id, ["messages", list(errors)] if errors else ["ok"]), None)   # type: ignore[arg-type]


def test_an_evaluation_job_is_attached_started_and_settled_by_its_report():
    """`start_evaluation_job`: `make`, the attach — the job on its node with
    its id before any work begins, the node stored in a transaction of its
    own — `evaluation_started`, `_start`; the report settles it: the
    outcome the node's stored check, stored in a transaction of its own,
    `evaluation_reported`, a failure posted to the starter, not
    interrupting, a success silent.  `_unfinished` follows §3.1's table;
    another job attached in its place drops the first, cancelling its work
    at once, and clears the stored check."""
    async def scenario():
        f, thy, t1, p, q = build(Checked)
        starter = stand_ins.agent(f.conversation)
        p._status = READY
        assert p._unfinished() == jobs.Unfinished_Construction(p.job())
        p.job().outcome = Succeeded("by simp")
        assert p._unfinished() == jobs.Unchecked(Check) and not p.is_finished()
        assert p._unfinished().title(plural=True) == "proof checks"
        tm.TABLE.clear_writes()
        await p.start_evaluation_job(starter)
        job = p.evaluation_job()
        assert isinstance(job, Check) and job.began and job.starter is starter and job.id in jobs._evaluation_jobs
        assert p.check_outcome() is RUNNING and p._unfinished() == jobs.Unfinished_Check(RUNNING, Check)
        assert tm.TABLE.transactions == 1 and "check" not in f.store.fields(p.identity)
        assert records("evaluation_started") == [{"node": P_CHECKED, "id": job.id, "starter": "main"}]
        await report(job)
        assert job.outcome is PASSED and job.ended and p.check_outcome() is PASSED
        assert p._unfinished() is None and p.is_finished()
        assert f.store.get(p.identity, "check") == ["PASSED"] and tm.TABLE.transactions == 2
        assert records("evaluation_reported") == [{"id": job.id, "outcome": "PASSED"}]
        assert deliver(f, starter) == [] and job.id not in jobs._evaluation_jobs
        await p.start_evaluation_job(starter)                 # another in its place
        second = p.evaluation_job()
        assert second is not job and p.check_outcome() is RUNNING and "check" not in f.store.fields(p.identity)
        assert records("evaluation_dropped") == [{"id": job.id, "dropped_by": "attached"}]
        await asyncio.sleep(0)
        assert CANCELS == []                                  # a settled job's work is not cancelled
        await report(second, ["bad", "worse"])
        assert second.outcome == Failed("bad\nworse") and p.check_outcome() == Failed("bad\nworse")
        assert p._unfinished() == jobs.Unfinished_Check(Failed("bad\nworse"), Check) and not p.is_finished()
        assert f.store.get(p.identity, "check") == ["FAILED", "bad\nworse"]
        assert records("evaluation_reported")[-1] == {"id": second.id, "outcome": "FAILED", "failure": ["bad", "worse"]}
        assert deliver(f, starter) == [f"The proof on `{P_CHECKED}` no longer holds. Call `construct` to prove it again."]
        posted = records("message_posted")[-1]
        assert (posted["kind"], posted["interrupts"], posted["source"]) == (
            "notification", False, f"proof check {second.id} on `{P_CHECKED}`")
        q._status = READY
        q.job().compulsory = False
        assert q._unfinished() is None                        # not compulsory: nothing owed, check or none
    run(scenario())


def test_failures_of_one_class_merge_at_delivery():
    """§3.4: one sentence for the nodes whose construction the failure
    started, one for the others; a message of another kind keeps its
    place; a failure whose job is no longer on its node is dropped."""
    async def scenario():
        f, thy, t1, p, q = build(Checked)
        starter = stand_ins.agent(f.conversation)
        for node in (p, q):
            await node.start_evaluation_job(starter)
        await report(p.evaluation_job(), ["no"])
        jobs.post(f.conversation.log, Message(starter, "meanwhile", interrupts=False))
        q.evaluation_job().started_construction = True
        await report(q.evaluation_job(), ["no"])
        r = add(thy, Checked(thy, slot(), "R"), "checked")
        await r.start_evaluation_job(starter)
        await report(r.evaluation_job(), ["no"])
        assert deliver(f, starter) == [
            f"The proof on `{P_CHECKED}` and on `block_Theory.checked_R` no longer holds. Call `construct` to prove it again.",
            "meanwhile",
            f"The proof on `{Q_CHECKED}` no longer holds, so its proof construction was started automatically."]
        await p.start_evaluation_job(starter)
        await report(p.evaluation_job(), ["again"])
        p.drop_evaluation_job("status_write", M.Evaluation(None, False))
        assert deliver(f, starter) == []
        assert records("message_dropped")[-1]["reason"] == "the evaluation job is no longer on its node"
    run(scenario())


def test_the_drops_and_the_stored_checks_clearings():
    """§3.3: a job is dropped by a status write (a rerun's rewrite of
    `ready` included), a delete, an amend, a construction starting, another
    job attached, the ending — one synchronous step each, `evaluation_dropped`,
    the starter woken; the walk and the edit send one `cancel(ids)` at
    their flush, any other drop sends at once, the ending none.  The
    stored check is cleared when the stored status leaves `Ready`, when a
    construction starts and when another job is attached — not by a rerun
    confirming `Ready`, nor by a drop by itself."""
    async def scenario():
        f, thy, t1, p, q = build(Checked)
        starter = stand_ins.agent(f.conversation)
        await thy.evaluate_to(None, False)
        assert p._status == READY and q._status == READY
        for node in (p, q):
            await node.start_evaluation_job(starter)
            await report(node.evaluation_job())              # settled, still on its node, PASSED stored
        CANCELS.clear()
        settled = [p.evaluation_job(), q.evaluation_job()]
        ev = M.Evaluation(None, False)
        p._set_status(ev, M.Ready(), 0.1)                     # `ready` over `ready`: dropped, the check kept
        assert p.evaluation_job() is None and settled[0].ended and p.check_outcome() is PASSED
        q._set_status(ev, M.NOT_EVALUATED, None)              # leaves `Ready`: dropped, the check cleared
        assert q.evaluation_job() is None and q.check_outcome() is None
        assert ev.dropped == [] and CANCELS == []             # a settled job's work is not cancelled
        assert [(r["id"], r["dropped_by"]) for r in records("evaluation_dropped")] == [
            (settled[0].id, "status_write"), (settled[1].id, "status_write")]
        await thy.evaluate_to(None, False)                          # q rerun, p kept
        assert p.check_outcome() is PASSED and q.check_outcome() is None
        for node in (p, q):
            await node.start_evaluation_job(starter)          # running: a drop cancels the work
        running = [p.evaluation_job(), q.evaluation_job()]
        assert p.check_outcome() is RUNNING                   # the attach cleared the stored PASSED
        p._set_status(ev, M.Ready(), 0.1)
        q._set_status(ev, M.NOT_EVALUATED, None)
        assert ev.dropped == [running[0].id, running[1].id] and CANCELS == []
        await ev.flush(f.conversation)
        assert CANCELS == [[running[0].id, running[1].id]] and ev.dropped == []
        assert records("cancel_sent") == [{"ids": [running[0].id, running[1].id]}]
        await thy.evaluate_to(None, False)                          # q rerun again
        p.job().start(starter)                                # a construction start clears the stored check
        assert p.check_outcome() is None
        p.job().cancel(None)
        await p.start_evaluation_job(starter)                 # and drops the job on the node
        third = p.evaluation_job()
        p.job().start(starter)
        assert p.evaluation_job() is None and p.check_outcome() is None and third.ended
        assert records("evaluation_dropped")[-1] == {"id": third.id, "dropped_by": "construction_start"}
        await asyncio.sleep(0)
        assert CANCELS[-1] == [third.id]
        p.job().cancel(None)
        await q.start_evaluation_job(starter)
        fourth = q.evaluation_job()
        await locked(f, edit.delete(q))                       # the edit's one cancel after its block
        assert fourth.ended and records("evaluation_dropped")[-1] == {"id": fourth.id, "dropped_by": "delete"}
        assert CANCELS[-1] == [fourth.id]
        await p.start_evaluation_job(starter)
        fifth = p.evaluation_job()
        (p2,) = await locked(f, edit.amend(p, [{"kind": "checked", "name": "P2"}], KINDS))
        assert fifth.ended and records("evaluation_dropped")[-1] == {"id": fifth.id, "dropped_by": "amend"}
        assert CANCELS[-1] == [fifth.id] and p2.evaluation_job() is None
        await p2.start_evaluation_job(starter)
        sixth = p2.evaluation_job()
        CANCELS.clear()
        f.conversation.ending.end(RuntimeError("over"))
        assert sixth.ended and p2.evaluation_job() is None
        assert records("evaluation_dropped")[-1] == {"id": sixth.id, "dropped_by": "ending"}
        await asyncio.sleep(0)
        assert CANCELS == []
        await report(sixth)                                   # a dropped job's report, the conversation ended
        assert records("report_ignored") == [] and sixth.outcome is RUNNING
    run(scenario())


def test_a_report_for_a_job_off_its_node_is_ignored_and_a_stuck_finished_is_a_bug():
    async def scenario():
        f, thy, t1, p, q = build(Checked)
        starter = stand_ins.agent(f.conversation)
        await p.start_evaluation_job(starter)
        job = p.evaluation_job()
        p.drop_evaluation_job("status_write", M.Evaluation(None, False))
        tm.TABLE.clear_writes()
        await report(job)
        assert records("report_ignored") == [{"id": job.id}] and job.outcome is RUNNING
        assert tm.TABLE.transactions == 0 and p.check_outcome() is None and not f.conversation.ending.entered

        class Stuck(Check):
            def _finished(self, errors):
                pass
        q.__class__ = type("Stuck_Checked", (Checked,), {"evaluation_job_class": Stuck})
        await q.start_evaluation_job(starter)
        await report(q.evaluation_job())
        ended_by = f.conversation.ending.ended_by
        assert isinstance(ended_by, TAT_InternalError) and "left the job RUNNING" in str(ended_by)
    run(scenario())


def test_an_attach_from_inside_a_run_takes_effect_at_the_settlement():
    """§3.3: from inside `_run`, `attach_evaluation_job` accepts a settled job
    only, and the attach takes effect at the run's settlement, with the
    outcome as the stored check; it is discarded with a cancelled run."""
    async def scenario():
        f, thy, t1, p, q = build(Checked)
        owner = stand_ins.agent(f.conversation)
        job = p.job()
        gate = asyncio.Event()

        async def checking(job):
            check = Check(p, owner)
            check._finished([])
            p.attach_evaluation_job(check)
            assert p.evaluation_job() is None             # not yet
            await gate.wait()
            return Succeeded("by simp")
        job.ends_with = checking
        gate.set()
        await run_to_end(job, owner)
        check = p.evaluation_job()
        assert isinstance(check, Check) and check.outcome is PASSED and p.check_outcome() is PASSED
        assert f.store.get(p.identity, "check") == ["PASSED"] and p._status is M.NOT_EVALUATED
        p._status = READY
        assert p.is_finished()
        gate.clear()
        job.release = asyncio.Event()
        job.start(owner)                                      # drops the check on the node, clears the stored one
        assert p.evaluation_job() is None and p.check_outcome() is None
        job.release.set()
        await asyncio.sleep(0)
        job.cancel(None)                                      # the attach goes with the run
        await runs_unwound(job)
        assert p.evaluation_job() is None and p.check_outcome() is None
        gate.set()

        async def attaching_a_running_one(job):
            p.attach_evaluation_job(Check(p, owner))
            return Succeeded("by simp")
        job.ends_with = attaching_a_running_one
        await run_to_end(job, owner)
        assert "a settled evaluation job alone" in str(f.conversation.ending.ended_by)
    run(scenario())


def test_a_job_class_raising_a_tat_error_at_its_start_is_a_bug():
    async def scenario():
        f, thy, t1, p, q = build(Checked)

        class Fussy(Check):
            async def _start(self):
                raise NoQuestionPending("x")
        p.__class__ = type("Fussy_Checked", (Checked,), {"evaluation_job_class": Fussy})
        with pytest.raises(TAT_InternalError, match="_start raised a TAT_Error"):
            await p.start_evaluation_job(stand_ins.agent(f.conversation))
        with pytest.raises(TAT_InternalError, match="names no evaluation job class"):
            await t1.start_evaluation_job(stand_ins.agent(f.conversation))
    run(scenario())


def test_the_check_row_across_a_reload():
    async def scenario():
        f, thy, t1, p, q = build(Checked)
        starter = stand_ins.agent(f.conversation)
        await p.start_evaluation_job(starter)
        invariants.assert_store_mirrors(f, KINDS)
        twin = tm.OneTreeForest(CONN, f.store, KINDS)
        loaded = twin.sub_nodes[0].sub_nodes[1]
        assert loaded.evaluation_job() is None and loaded.check_outcome() is None   # a run is not stored
        await report(p.evaluation_job(), ["no"])
        twin = tm.OneTreeForest(CONN, f.store, KINDS)
        assert twin.sub_nodes[0].sub_nodes[1].check_outcome() == Failed("no")
        invariants.assert_store_mirrors(f, KINDS)
        with f.store.transaction():
            f.store.put(p.identity, "check", ["RUNNING"])
        with pytest.raises(TAT_StartupError, match="not a check's image"):
            tm.OneTreeForest(CONN, f.store, KINDS)
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


# --- the cases of the tests reader of steps 8 and 9 (STEPS_8_9_REVIEW.md §3) -------

async def woken_by(agent, holds, action):
    """Whether `action()` wakes a sleeper on `agent` that waits for `holds()`
    (which `action` makes true): no wake-up, no return."""
    sleeper = asyncio.ensure_future(agent.sleep_until(holds))
    await asyncio.sleep(0)
    assert not sleeper.done()
    action()
    try:
        await asyncio.wait_for(sleeper, 0.5)
        return True
    except TimeoutError:
        return False


# listed_bound_4, listed_bound_2, on_each_and_everywhere, listed_bullet_indent,
# starting_header_singular, cancelling_header_singular, owned_refusal_reworded
def test_the_default_wording_in_the_three_forms_of_section_5():
    ids = ["theory_X.lemma_P", "theory_X.lemma_Q", "theory_X.lemma_R", "theory_Y.lemma_S"]
    exit_ = "; call `check_construct` before you exit"
    assert Proof.starting_notice(ids[:1]) == f"Started the proof construction on `theory_X.lemma_P`{exit_}."
    assert Proof.starting_notice(ids[:2]) == (
        f"Started the proof construction on `theory_X.lemma_P` and on `theory_X.lemma_Q`{exit_}.")
    assert Proof.starting_notice(ids[:3]) == (
        "Started the proof construction on `theory_X.lemma_P`, on `theory_X.lemma_Q`"
        f" and on `theory_X.lemma_R`{exit_}.")
    assert Proof.starting_notice(ids) == (
        f"Started the following proof constructions{exit_}:\n"
        "  - theory_X.lemma_P\n  - theory_X.lemma_Q\n  - theory_X.lemma_R\n  - theory_Y.lemma_S")
    assert Proof.cancelling_notice(ids[:3]) == (
        "Cancelled the proof construction on `theory_X.lemma_P`, on `theory_X.lemma_Q` and on `theory_X.lemma_R`.")
    assert Proof.cancelling_notice(ids) == (
        "Cancelled the following proof constructions:\n"
        "  - theory_X.lemma_P\n  - theory_X.lemma_Q\n  - theory_X.lemma_R\n  - theory_Y.lemma_S")

    async def scenario():
        f, thy, t1, p, q = build()
        job = p.job()
        job.start(stand_ins.agent(f.conversation))
        assert job.owned_by_another_refusal() == f"The proof construction on `{P}` belongs to another agent."
        job.cancel(None)
    run(scenario())


# with_message_first_line_only
def test_a_failure_message_of_several_lines_is_indented_line_by_line():
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        job = p.job()
        job.ends_with = ends(Failed("first line\nsecond line"))
        await run_to_end(job, owner)
        assert deliver(f, owner) == [f"The proof construction on `{P}` failed:\n  first line\n  second line"]
    run(scenario())


# failed_image_any_message, check_image_any_message, restore_auto_any_type
@pytest.mark.parametrize("field, row, match", [
    ("job", ["FAILED", 3], "not a job's image"),
    ("check", ["FAILED", 3], "not a check's image"),
    ("auto_construct", "yes", "not a boolean")])
def test_a_row_of_the_right_tag_but_the_wrong_value_is_refused(field, row, match):
    async def scenario():
        f, thy, t1, p, q = build(Checked)
        with f.store.transaction():
            f.store.put(p.identity, field, row)
        with pytest.raises(TAT_StartupError, match=match):
            tm.OneTreeForest(CONN, f.store, KINDS)
    run(scenario())


# carry_drops_failure
def test_an_amend_carries_a_failure_too():
    async def scenario():
        f, thy, t1, p, q = build(Carrying)
        p.job().outcome = Failed("no proof")
        (p2,) = await locked(f, edit.amend(p, [{"kind": "carrying", "name": "P2"}], KINDS))
        assert p2.job().outcome == Failed("no proof")
        assert f.store.get(p2.identity, "job") == ["FAILED", "no proof"]
    run(scenario())


# can_start_ignores_check
def test_can_start_asks_the_class():
    class Refusing(Proof):
        def _check(self):
            return False

    class Guarded(Lemma):
        construction_job_class = Refusing

    async def scenario():
        f, thy, t1, p, q = build(Guarded)
        job = p.job()
        assert job.outcome is NOT_STARTED and not job.can_start()
        with pytest.raises(TAT_InternalError, match="cannot be started now"):
            job.start(stand_ins.agent(f.conversation))
        assert job.outcome is NOT_STARTED and records("construction_started") == []
    run(scenario())


# start_wakes_nobody, cancel_none_wakes_nobody
def test_a_start_and_a_silent_cancel_wake_the_owner():
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        job = p.job()
        assert await woken_by(owner, lambda: job.outcome is RUNNING, lambda: job.start(owner))
        await asyncio.sleep(0)
        assert await woken_by(owner, lambda: job.outcome is not RUNNING, lambda: job.cancel(None))
        await runs_unwound(job)
    run(scenario())


# report_wakes_nobody, drop_wakes_nobody
def test_a_passing_report_and_a_drop_wake_the_starter():
    async def scenario():
        f, thy, t1, p, q = build(Checked)
        starter = stand_ins.agent(f.conversation)
        await p.start_evaluation_job(starter)
        job = p.evaluation_job()
        loop = asyncio.get_running_loop()
        assert await woken_by(starter, lambda: job.ended,
                              lambda: loop.create_task(report(job)))          # PASSED: nothing posted
        await q.start_evaluation_job(starter)
        other = q.evaluation_job()
        assert await woken_by(starter, lambda: other.ended,
                              lambda: q.drop_evaluation_job("status_write", M.Evaluation(None, False)))
    run(scenario())


# start_stores_stale_image, start_stores_stale_check
def test_a_start_stores_the_cleared_failure_and_the_cleared_check():
    async def scenario():
        f, thy, t1, p, q = build(Checked)
        owner = stand_ins.agent(f.conversation)
        job = p.job()
        job.ends_with = ends(Failed("no proof"))
        await run_to_end(job, owner)
        await p.start_evaluation_job(owner)
        await report(p.evaluation_job())
        assert f.store.get(p.identity, "job") == ["FAILED", "no proof"] and f.store.get(p.identity, "check") == ["PASSED"]
        job.release = asyncio.Event()
        job.start(owner)
        assert f.store.get(p.identity, "job") == ["NOT_STARTED"]
        assert "check" not in f.store.fields(p.identity)
        invariants.assert_store_mirrors(f, KINDS)
        job.cancel(None)
        await runs_unwound(job)
    run(scenario())


# run_agent_not_set
def test_the_runs_records_name_its_owner_whoever_started_it():
    async def scenario():
        f, thy, t1, p, q = build()
        stand_ins.agent(f.conversation)
        sub = stand_ins.agent(f.conversation, "sub", main=False)
        current_agent.set("main")                     # the context the start is made in
        job = p.job()
        await run_to_end(job, sub)
        settled = [r for r in stand_ins.records("job") if r["event"] == "construction_settled"]
        assert [r.get("agent") for r in settled] == ["sub"]
    run(scenario())


# cancelled_not_interrupting
def test_the_cancelled_notification_interrupts():
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        p.job().start(owner)
        await asyncio.sleep(0)
        p.job().cancel("NODE_DELETED")
        posted = records("message_posted")[-1]
        assert (posted["kind"], posted["interrupts"]) == ("notification", True)
        await runs_unwound(p.job())
    run(scenario())


# attach_survives_cancel
def test_an_attach_of_a_cancelled_run_never_lands_at_a_later_settlement():
    async def scenario():
        f, thy, t1, p, q = build(Checked)
        owner = stand_ins.agent(f.conversation)
        job = p.job()
        gate = asyncio.Event()

        async def checking(job):
            check = Check(p, owner)
            check._finished(["stale"])
            p.attach_evaluation_job(check)
            await gate.wait()
            return Succeeded("by simp")
        job.ends_with = checking
        job.start(owner)
        job.release.set()
        await asyncio.sleep(0)
        job.cancel(None)
        await runs_unwound(job)
        job.ends_with = ends(Succeeded("by auto"))
        await run_to_end(job, owner)
        assert p.evaluation_job() is None and p.check_outcome() is None
    run(scenario())


# replaced_releases_ask
def test_a_question_asked_instead_keeps_the_run_waiting():
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        job = p.job()
        job.ends_with = asking
        job.start(owner)
        job.release.set()
        await until(owner, lambda: job.pending_question is not None)
        assert job.receive_answer({"verdict": "reject"}) is None
        second = job.pending_question
        for _ in range(5):
            await asyncio.sleep(0)
        assert job.pending_question is second and isinstance(second, Why) and job.outcome is RUNNING
        assert job.receive_answer({"reason": "too long"}) == "Noted."
        await asyncio.wait_for(owner.sleep_until(lambda: job.outcome is not RUNNING), 1.0)
    run(scenario())


# accept_releases_nothing (bounded: the existing case hangs instead)
def test_an_accepted_answer_lets_the_run_go_on():
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        job = p.job()
        job.ends_with = asking
        job.start(owner)
        job.release.set()
        await until(owner, lambda: job.pending_question is not None)
        job.receive_answer({"verdict": "accept"})
        await asyncio.wait_for(owner.sleep_until(lambda: job.outcome is not RUNNING), 1.0)
        assert job.outcome == Succeeded("by simp")
    run(scenario())


# ask_keeps_question_on_its_cancel
def test_an_ask_cancelled_by_the_run_itself_withdraws_its_question():
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        job = p.job()
        gate = asyncio.Event()

        async def impatient(job):
            try:
                await asyncio.wait_for(job.ask(Verdict()), 0.01)
            except TimeoutError:
                pass
            await gate.wait()
            return Succeeded("by simp")
        job.ends_with = impatient
        job.start(owner)
        job.release.set()
        await until(owner, lambda: job.pending_question is not None)

        async def withdrawn():                                # polled: a withdrawal wakes nobody
            while job.pending_question is not None:
                await asyncio.sleep(0.005)
        await asyncio.wait_for(withdrawn(), 1.0)
        assert job.outcome is RUNNING
        assert records("question_withdrawn") == [{"node": P}]
        assert deliver(f, owner) == []                        # the question no longer pending: dropped
        gate.set()
        await asyncio.wait_for(owner.sleep_until(lambda: job.outcome is not RUNNING), 1.0)
    run(scenario())


# withdraw_releases_no_ask (bounded: the existing case hangs instead)
def test_the_settlement_ends_a_stray_asking_branch():
    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        job = p.job()
        branches = []

        async def stray(job):
            branches.append(asyncio.ensure_future(job.ask(Verdict())))
            await asyncio.sleep(0)
            return Succeeded("by simp")
        job.ends_with = stray
        await run_to_end(job, owner)
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(branches[0], 1.0)
    run(scenario())


# question_schema_unvalidated, question_without_a_run
def test_a_question_outside_the_grammar_or_with_no_run_is_a_bug():
    class Bare(Verdict):
        schema = {"type": "string"}

    async def scenario():
        f, thy, t1, p, q = build()
        owner = stand_ins.agent(f.conversation)
        job = p.job()
        await run_to_end(job, owner)                         # settled: no run is the job's
        with pytest.raises(TAT_InternalError, match="from no run of its"):
            await asyncio.wait_for(job.ask(Verdict()), 0.5)

        async def asks_barely(job):
            await job.ask(Bare())
            return Succeeded("by simp")
        g, _, _, p2, _ = build()
        job2 = p2.job()
        job2.ends_with = asks_barely
        job2.start(stand_ins.agent(g.conversation))
        job2.release.set()
        await asyncio.wait_for(g.conversation.ending.wait(), 1.0)
        assert isinstance(g.conversation.ending.ended_by, TAT_InternalError)
        assert job2.pending_question is None
    run(scenario())


# drop_cancels_twice
def test_a_walks_drop_sends_nothing_before_its_flush():
    async def scenario():
        f, thy, t1, p, q = build(Checked)
        starter = stand_ins.agent(f.conversation)
        await p.start_evaluation_job(starter)
        job = p.evaluation_job()
        ev = M.Evaluation(None, False)
        p.drop_evaluation_job("status_write", ev)
        await asyncio.sleep(0.01)                            # any task spawned has run
        assert CANCELS == []
        await ev.flush(f.conversation)
        assert CANCELS == [[job.id]]
    run(scenario())


# unfinished_passed_first
def test_a_failed_construction_is_owed_whatever_the_check():
    async def scenario():
        f, thy, t1, p, q = build(Checked)
        owner = stand_ins.agent(f.conversation)
        job = p.job()

        async def checked_then_failed(job):
            check = Check(p, owner)
            check._finished([])
            p.attach_evaluation_job(check)
            return Failed("the replay broke")
        job.ends_with = checked_then_failed
        await run_to_end(job, owner)
        assert p.check_outcome() is PASSED and job.outcome == Failed("the replay broke")
        assert p._unfinished() == jobs.Unfinished_Construction(job)
    run(scenario())


# make_outside_the_guard
def test_a_tat_error_from_make_is_the_classs_bug():
    class Fussy(Check):
        @classmethod
        def make(cls, node, starter):
            raise NoQuestionPending("x")

    async def scenario():
        f, thy, t1, p, q = build(Checked)
        p.__class__ = type("Fussy_Make", (Checked,), {"evaluation_job_class": Fussy})
        with pytest.raises(TAT_InternalError, match="make raised a TAT_Error"):
            await p.start_evaluation_job(stand_ins.agent(f.conversation))
    run(scenario())


# restore_check_only_with_a_job
def test_the_check_row_of_a_node_with_no_construction_job_is_restored():
    class Only_Checked(T):
        evaluation_job_class = Check
    kinds = KINDS | {"only": Only_Checked}

    async def scenario():
        f = tm.OneTreeForest(CONN, kinds=kinds)
        f.conversation.ending.forest = f
        thy = add(f, tm.Block(f, slot(), "Theory", slot()))
        o = add(thy, Only_Checked(thy, slot(), "O"), "only")
        await o.start_evaluation_job(stand_ins.agent(f.conversation))
        await report(o.evaluation_job(), ["no"])
        twin = tm.OneTreeForest(CONN, f.store, kinds)
        assert twin.sub_nodes[0].sub_nodes[0].check_outcome() == Failed("no")
    run(scenario())


# job_class_own_dict_only
def test_a_framework_member_overridden_higher_up_is_refused(monkeypatch):
    import test_plugin as tp
    monkeypatch.setattr(plugin, "registry", {})
    monkeypatch.setattr(plugin, "compile_hooks", {})
    monkeypatch.setattr(M, "FRAMEWORK_NODE_CLASSES", [])

    class Overriding(Proof):
        def cancel(self, reason): pass

    class Inheriting(Overriding):
        pass
    tp.refused(tp.leaf("Inherits", ["inherits"], construction_job_class=Inheriting),
               "Inheriting overrides `cancel`, which is the framework's")


# --- the walk starting jobs (CONSTRUCT_INTERACTION §3.3; ARCHITECTURE §3.5) --

class Careful(Proof):
    """`Theorem`'s way (THEOREM.md §7): while a proof stands on the node it
    is checked, not constructed again; a `FAILED` check opens the way."""
    def _check(self):
        return not isinstance(self.outcome, Succeeded) or isinstance(self.node.check_outcome(), Failed)


class Careful_Lemma(Checked):
    construction_job_class = Careful


class Never(Proof):                     # a class whose own condition for a start never holds
    def _check(self):
        return False


class Never_Lemma(Checked):
    construction_job_class = Never


async def walk(node, agent, checks="no", ignore_error=False):
    return await node.evaluate_to(agent, ignore_error, checks)


def test_the_walk_starts_a_check_where_unchecked_and_none_under_no():
    """§3.3 "Where a job starts": on a node the walk passes that is ready,
    whose class names an evaluation job, with none on it and
    `_unfinished()` answering `Unchecked`, when `checks` allows — once;
    none under `"no"`, on an unproven node, on a node not ready, on a
    `PASSED` one, or for a walk with no caller."""
    async def scenario():
        f, thy, t1, p, q = build(Careful_Lemma)
        me = stand_ins.agent(f.conversation)
        p.job().outcome = Succeeded("by simp")
        await walk(thy, me, "no")
        assert p._operations_ready() and p.evaluation_job() is None and q.evaluation_job() is None
        await walk(thy, me, "quick")                      # P proven and unchecked; Q unproven; T1 names no class
        check = p.evaluation_job()
        assert isinstance(check, Check) and check.starter is me and check.began and check.outcome is RUNNING
        assert q.evaluation_job() is None and t1.evaluation_job() is None
        assert records("evaluation_started") == [{"node": P, "id": check.id, "starter": "main"}]
        await walk(thy, me, "quick")                      # a check on it already: no second
        assert p.evaluation_job() is check
        await report(check)
        await walk(thy, me, "quick")                      # `PASSED`, the settled job still on the node: nothing owed
        assert p.evaluation_job() is check and p.check_outcome() is PASSED
        r = add(thy, Careful_Lemma(thy, slot(), "R", fail=True), "lemma")
        s = add(thy, Careful_Lemma(thy, slot(), "S"), "lemma")
        for node in (r, s):
            node.job().outcome = Succeeded("by simp")
        await walk(thy, None, "quick", ignore_error=True)    # no caller: nothing started
        assert r.evaluation_job() is None and s.evaluation_job() is None
        await walk(thy, me, "quick", ignore_error=True)
        assert r.evaluation_job() is None and s.evaluation_job() is not None   # R is not ready
        await report(s.evaluation_job())
    run(scenario())


def test_automatic_construction_at_a_passed_node():
    """§3.3 "Automatic construction": at a ready node whose `auto_construct`
    is on and whose job `can_start()`, the walk starts the construction,
    the caller its owner, whatever `checks` says; a job that failed is
    started again only after an invalidation since; nothing with the
    setting off or on a node that is not ready."""
    async def scenario():
        f, thy, t1, p, q = build()
        me = stand_ins.agent(f.conversation)
        other = stand_ins.agent(f.conversation, "a9f3c2d1e4b5", False)
        p.job().auto_construct = True
        await walk(thy, me)
        assert p.job().outcome is RUNNING and p.job().owner is me and q.job().outcome is NOT_STARTED
        p.job().cancel(None)
        p.job().outcome = Failed("no proof")             # as a run that failed leaves it
        await walk(thy, me)                              # ready and not invalidated since: not again
        assert p.job().outcome == Failed("no proof")
        await tm._invalidate(p)
        await walk(thy, me)                              # rerun to ready after the invalidation: again
        assert p.job().outcome is RUNNING
        p.job().cancel(None)
        p.job().outcome = Failed("no proof")
        await tm._invalidate(p)
        await walk(p, other)                             # the owner is the caller
        assert p.job().outcome is RUNNING and p.job().owner is other
        p.job().cancel(None)
        r = add(thy, Lemma(thy, slot(), "R", fail=True), "lemma")
        r.job().auto_construct = True
        await walk(thy, me, ignore_error=True)
        assert r.job().outcome is NOT_STARTED and p.job().outcome is RUNNING   # R not ready; P, `NOT_STARTED`, started
        for node in (p, q):
            node.job().cancel(None)
    run(scenario())


def test_a_failed_report_starts_the_construction_under_automatic_construction():
    """§3.3: a `FAILED` report on a node whose `auto_construct` is on and
    whose job `can_start()` — the check stored first, which `Careful`
    reads — starts the construction, the starter its owner; the
    notification says so and carries no job (§3.4), so it stands though
    the start dropped the job; with the setting off it carries the job."""
    async def scenario():
        f, thy, t1, p, q = build(Careful_Lemma)
        me = stand_ins.agent(f.conversation)
        for node in (p, q):
            node.job().outcome = Succeeded("by simp")
        p.job().auto_construct = True
        await walk(thy, me, "quick")
        check = p.evaluation_job()
        await report(check, ["broken"])
        assert check.started_construction and check.ended
        assert p.job().outcome is RUNNING and p.job().owner is me
        assert p.evaluation_job() is None and p.check_outcome() is None    # dropped by the start, the check cleared
        posted = records("message_posted")[-1]
        assert "source" not in posted and posted["kind"] == "notification"
        assert deliver(f, me) == [
            f"The proof on `{P}` no longer holds, so its proof construction was started automatically."]
        await report(q.evaluation_job(), ["broken"])
        assert not q.evaluation_job().started_construction and q.job().outcome == Succeeded("by simp")
        assert q.check_outcome() == Failed("broken")
        assert deliver(f, me) == [f"The proof on `{Q}` no longer holds. Call `construct` to prove it again."]
        r = add(thy, Never_Lemma(thy, slot(), "R"), "lemma")     # the setting on, the class's condition failing
        r.job().outcome = Succeeded("by simp")
        r.job().auto_construct = True
        await walk(thy, me, "quick")
        await report(r.evaluation_job(), ["broken"])
        assert not r.evaluation_job().started_construction and r.job().outcome == Succeeded("by simp")
        assert deliver(f, me) == [
            "The proof on `block_Theory.lemma_R` no longer holds. Call `construct` to prove it again."]
        p.job().cancel(None)
    run(scenario())


def test_blocking_waits_for_the_passed_nodes_checks_whoever_started_them():
    """§5 under `blocking`: the walk keeps the lock until every evaluation
    job running on a node it passed has ended, another agent's included;
    a failure goes to its starter."""
    async def scenario():
        f, thy, t1, p, q = build(Careful_Lemma)
        me = stand_ins.agent(f.conversation)
        other = stand_ins.agent(f.conversation, "a9f3c2d1e4b5", False)
        for node in (p, q):
            node.job().outcome = Succeeded("by simp")
        await walk(p, me)
        await p.start_evaluation_job(other)
        task = asyncio.ensure_future(walk(thy, me, "blocking"))
        await asyncio.sleep(0.05)
        assert not task.done() and f.lock.locked()
        assert q.evaluation_job().starter is me
        await report(p.evaluation_job())
        await asyncio.sleep(0.05)
        assert not task.done()
        await report(q.evaluation_job(), ["bad"])
        await asyncio.wait_for(task, 2.0)
        assert not f.lock.locked()
        assert deliver(f, me) == [f"The proof on `{Q}` no longer holds. Call `construct` to prove it again."]
        assert deliver(f, other) == []
    run(scenario())
