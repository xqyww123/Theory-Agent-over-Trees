"""The recursion of `model.py` on `Theory > [Section > [T1, T2], T3, T4]`,
against a fake state slot table and a real `Forest_Store`; and the forest's
round trip through the store.  Run: python -m pytest test/test_model.py
"""

import asyncio
import typing
from contextlib import contextmanager
from typing import NotRequired, TypedDict

import pytest

import stand_ins
from isabelle_theory_agent import edit, isabelle_driver, jobs, model as M
from isabelle_theory_agent.exceptions import (
    InvalidName, TAT_DisasterError, TAT_InternalError, TAT_StartupError)
from isabelle_theory_agent.model import NOT_EVALUATED, Isar_State_Slot
from isabelle_theory_agent.store import Forest_Store

# The two status values the fakes' runs leave, one object each, so a test
# may compare by identity; a `Theory`'s carry messages and are compared
# with `==`.
READY = M.READY_CLEAN
CANNOT_EVALUATE = M.CannotEvaluate()


# --- a fake state slot table ------------------------------------------------

class Table:
    """The fake state slot table, the fake theory table beside it, and a
    recorder of every store's writes: how many transactions opened, which
    nodes they touched, and which stores are inside one right now."""

    def __init__(self):
        self.values: dict[str, str] = {}
        self.deleted: list[str] = []
        self.calls: list[tuple] = []        # every state slot round trip, in order
        self.theories: set[str] = set()     # the fake theory table: the qualified names
                                            # the fakes' endings wrote (test_session_theory)
        self.theory_deletes: list[tuple[str, ...]] = []   # every theory_delete round trip
        self.transactions = 0
        self.touched: set[int] = set()      # nodes written or deleted
        self.open_stores: set = set()

    def clear(self):
        self.values.clear(); self.deleted.clear(); self.calls.clear()
        self.theories.clear(); self.theory_deletes.clear()
        self.clear_writes()

    def clear_writes(self):
        self.transactions = 0
        self.touched.clear()

    def _no_transaction_open(self):
        """Every round trip is an `await`, and no transaction may span one
        (store.py, `transaction`)."""
        assert not self.open_stores, "a store transaction is open across an await"

    def install(self, monkeypatch):
        async def state_delete(conversation, names):
            self._no_transaction_open()
            self.calls.append(("delete", tuple(names)))
            for n in names:
                self.values.pop(n, None); self.deleted.append(n)
        async def state_exists(conversation, name):
            self._no_transaction_open()
            return name in self.values
        async def state_copy(conversation, src, dst):
            self._no_transaction_open()
            self.calls.append(("copy", src, dst))
            if src in self.values: self.values[dst] = self.values[src]
            else: self.values.pop(dst, None)
        async def theory_delete(conversation, names):
            self._no_transaction_open()
            self.theory_deletes.append(tuple(names))
            self.theories.difference_update(names)
        for f in (state_delete, state_exists, state_copy, theory_delete):
            monkeypatch.setattr(isabelle_driver, f.__name__, f)
        # Wrap the store itself, so every store is watched whoever made it.
        transaction, put, delete_node = (
            Forest_Store.transaction, Forest_Store.put, Forest_Store.delete_node)
        @contextmanager
        def recording_transaction(store):
            with transaction(store):
                self.transactions += 1
                self.open_stores.add(store)
                try:
                    yield
                finally:
                    self.open_stores.discard(store)
        def recording_put(store, node, field, value):
            self.touched.add(node); put(store, node, field, value)
        def recording_delete_node(store, node):
            self.touched.add(node); delete_node(store, node)
        monkeypatch.setattr(Forest_Store, "transaction", recording_transaction)
        monkeypatch.setattr(Forest_Store, "put", recording_put)
        monkeypatch.setattr(Forest_Store, "delete_node", recording_delete_node)


# --- concrete node classes ------------------------------------------------------

class T_RawAST(TypedDict):
    name: str
    fail: NotRequired[bool]

class T(M.Leaf):                    # a leaf whose operation succeeds unless told to fail
    argument_schema = T_RawAST
    def __init__(self, parent, state, name, fail=False):
        super().__init__(parent, state)
        self.name, self.fail, self.runs = name, fail, 0
        self.consumed = NOT_RUN     # what the last successful run read from `state`
        self.copied = NOT_RUN       # what the last failing run copied through
    @classmethod
    async def gen(cls, config, raw: T_RawAST):
        return cls(config.parent, config.state, raw["name"], raw.get("fail", False))
    def to_store(self, rows):
        rows.put("name", self.name); rows.put("fail", self.fail)
    @classmethod
    def from_store(cls, config, rows):
        return cls(config.parent, config.state, rows.get("name"), rows.get("fail"))
    async def _eval_opr(self):
        self.runs += 1
        got = TABLE.values.get(self.state.name)
        if self.fail:
            self.consumed, self.copied = NOT_RUN, got
            return CANNOT_EVALUATE
        self.consumed = got
        TABLE.values[self.resulting_state().name] = f"after {self.name}" + run_tag(self.runs)
        return READY
    def on_invalidated(self, operation): self.consumed = NOT_RUN
    def emit(self, indent, out):
        out.write(M.INDENT * indent + f"text ‹{self.name}›\n")
        return indent
    def __repr__(self): return self.name


class Block(M.StdBlock):
    argument_schema = T_RawAST
    def __init__(self, parent, state, name, sbe, fail_beginning=False, fail_ending=False):
        super().__init__(parent, state, [], sbe)
        self.name, self.fail_beginning, self.fail_ending = name, fail_beginning, fail_ending
        self.begin_runs = self.end_runs = 0
        self.consumed_begin = self.consumed_end = NOT_RUN
        self.copied_end = NOT_RUN   # what the last failing ending copied through
    @classmethod
    async def gen(cls, config, raw: T_RawAST):
        return cls(config.parent, config.state, raw["name"],
                   Isar_State_Slot.assign(config.state.conversation),
                   fail_beginning=raw.get("fail", False))
    def to_store(self, rows):
        rows.put("name", self.name)
        rows.put("fail_beginning", self.fail_beginning)
        rows.put("fail_ending", self.fail_ending)
    @classmethod
    def from_store(cls, config, rows):
        return cls(config.parent, config.state, rows.get("name"),
                   Isar_State_Slot.assign(config.state.conversation),
                   fail_beginning=rows.get("fail_beginning"),
                   fail_ending=rows.get("fail_ending"))
    async def _eval_beginning_opr(self):
        self.begin_runs += 1
        self.consumed_begin = (NOT_RUN if self.fail_beginning
                               else TABLE.values.get(self.state.name))
        if self.fail_beginning: return CANNOT_EVALUATE
        TABLE.values[self._state_after_beginning().name] = \
            f"begin {self.name}" + run_tag(self.begin_runs)
        return READY
    async def _eval_ending_opr(self):
        self.end_runs += 1
        got = TABLE.values.get(self._state_before_ending.name)
        if self.fail_ending:
            self.consumed_end, self.copied_end = NOT_RUN, got
            return CANNOT_EVALUATE
        self.consumed_end = got
        TABLE.values[self.resulting_state().name] = f"end {self.name}" + run_tag(self.end_runs)
        return READY
    def on_invalidated(self, operation):
        if operation == "beginning": self.consumed_begin = NOT_RUN
        else: self.consumed_end = NOT_RUN
    def emit_beginning(self, indent, out):
        out.write(M.INDENT * indent + f"section ‹{self.name}›\n")
        return indent
    def emit_ending(self, indent, out):               # the fake has an ending command
        out.write(M.INDENT * indent + f"text ‹end of {self.name}›\n")
        return indent
    def __repr__(self): return self.name


KINDS = {"t": T, "block": Block}


class OneTreeForest(M.Forest):
    """Enough of `Forest` to drive one tree.  Unlike the real root it chains
    its children — `NonLeaf_Node`'s slot chain, into a slot after them,
    `_end` — so the fake `Block` at the top, whose beginning reads its
    input as a `Theory`'s never does, is an ordinary chained block.  Like
    the real root it is an `Unchained_Node` to an invalidation, which
    marks nothing at its level: an edit among its top-level blocks
    invalidates no later block, though this double chains them — no case
    evaluates two top-level blocks."""
    def __init__(self, conn, store=None, kinds=KINDS):
        super().__init__(stand_ins.conversation(conn),          # nothing here touches the directory
                         store if store is not None else Forest_Store(":memory:", stand_ins.log()), kinds)
        self._end = Isar_State_Slot.assign(self.conversation)
    _resulting_state_of_child = M.NonLeaf_Node._resulting_state_of_child
    _predecessor_wrote = M.NonLeaf_Node._predecessor_wrote
    _source_before = M.NonLeaf_Node._source_before
    _carry_forward = M.NonLeaf_Node._carry_forward
    def _resulting_state_of_all_children(self): return self._end
    async def _evaluate(self, ev, mode):
        """The destination's tree — every top-level block when the
        destination is the root, ending at the first stop — each by the
        real `_evaluate_tree`."""
        trees = self.sub_nodes if ev.destination is self else [self._tree_of(ev.destination)]
        stop = None
        for tree in trees:
            stop = await self._evaluate_tree(ev, tree)
            if stop is not None:
                break
        return M.EvaluationResult(stop, None)


TABLE = Table()
CONN = typing.cast(typing.Any, object())     # stands in for a Connection
NOT_RUN = object()                           # "this operation has not run since it was last current"


def run_tag(n):
    """Every run writes a distinct value, so a stale copy is visible; the
    first run's value stays bare for the tests that spell it out."""
    return "" if n == 1 else f"#{n}"


def slot(): return Isar_State_Slot.assign(stand_ins.conversation(CONN))


_N = typing.TypeVar("_N", bound=M.Node)


def add(parent, node: _N, kind: str | None = None) -> _N:
    """Append a directly built node the way the framework would have entered
    it: identity and kind set, its rows and the parent's `children` row
    stored — so the store mirrors the forest from the start."""
    f = parent.forest()
    node.parent = parent
    node.kind = kind or ("block" if isinstance(node, M.NonLeaf_Node) else "t")
    node.identity = f.store.next_identity()
    parent.sub_nodes.append(node)
    with f.store.transaction():
        f._store_node(node)
        f._store_children(parent)
    return node


def build(**flags):
    """Theory > [Section > [T1, T2], T3, T4]; flags name a node and a failure."""
    f = OneTreeForest(CONN)
    thy = add(f, Block(f, slot(), "Theory", slot()))
    sec = add(thy, Block(thy, slot(), "Section", slot(),
                         fail_beginning=flags.get("Section") == "begin",
                         fail_ending=flags.get("Section") == "end"))
    t1 = add(sec, T(sec, slot(), "T1", fail=flags.get("T1", False)))
    t2 = add(sec, T(sec, slot(), "T2", fail=flags.get("T2", False)))
    t3 = add(thy, T(thy, slot(), "T3", fail=flags.get("T3", False)))
    t4 = add(thy, T(thy, slot(), "T4", fail=flags.get("T4", False)))
    return f, thy, sec, t1, t2, t3, t4


def st(n):
    if isinstance(n, M.StdBlock):
        return (n.evaluation_status_beginning, n.evaluation_status_ending)
    return n._status


def run(coro): return asyncio.run(coro)


async def locked(f, coro):
    """The tool entry's lock hold, for driving an edit operation directly."""
    async with f.lock:
        return await coro


async def _invalidate(node):
    """An edit's invalidation by itself, with the store and the flush an
    edit ends on: from `node`'s position to the end of its tree — a node
    nothing chains, whole."""
    f = node.forest()
    async with f.lock:
        ev = M.Evaluation(None, False)
        if node.parent is None or isinstance(node.parent, M.Unchained_Node):
            node._invalidate(ev)
        else:
            f._invalidate_from(M.Location(node.parent, node.index_of()), ev)
        f._store_written(ev)
        await ev.flush(f.conversation)


def invalidate(node): run(_invalidate(node))


@pytest.fixture(autouse=True)
def table(monkeypatch):
    TABLE.clear()
    TABLE.install(monkeypatch)


# --- scenarios -----------------------------------------------------------------

def test_a_evaluate_inside_block():
    f, thy, sec, t1, t2, t3, t4 = build()
    r = run(t2.evaluate_to(None, False))
    assert r == M.EvaluationResult(None, None)
    assert st(thy) == (READY, NOT_EVALUATED) and st(sec) == (READY, NOT_EVALUATED)
    assert st(t1) is READY and st(t2) is READY and st(t3) is NOT_EVALUATED
    # (e) a later call runs the ending, never the beginning again
    r = run(t3.evaluate_to(None, False))
    assert sec.begin_runs == 1 and sec.end_runs == 1 and thy.begin_runs == 1
    assert st(sec) == (READY, READY) and st(t3) is READY and st(t4) is NOT_EVALUATED
    run(t3.evaluate_to(None, False))
    assert t3.runs == 1 and sec.end_runs == 1        # nothing reruns


def test_b_a_stop_strict_then_ignore():
    f, thy, sec, t1, t2, t3, t4 = build(T1=True)
    r = run(t1.evaluate_to(None, False))
    assert r.stopped_at is t1 and st(t1) is CANNOT_EVALUATE
    assert TABLE.values[t1.resulting_state().name] == "begin Section"   # the input copied through
    # the walk's outcome names the stop (LOGGING.md §4); the `stopped` record
    # is `Forest._handle_tree`'s, which this one-tree fake bypasses
    assert stand_ins.events("evaluation")[-1] == "walk_ended"
    assert stand_ins.records("evaluation")[-1]["data"]["outcome"] == f.full_id(t1)
    written = len(stand_ins.records("evaluation"))
    r = run(t4.evaluate_to(None, False))
    assert r.stopped_at is t1 and t1.runs == 1                          # not rerun
    assert st(t2) is NOT_EVALUATED and st(t3) is NOT_EVALUATED and st(t4) is NOT_EVALUATED
    assert st(sec) == (READY, NOT_EVALUATED)
    # past the same stop again: what is already stored as not evaluated is
    # not written again (MODULE_STRUCTURE §4.1)
    assert stand_ins.events("evaluation")[written:] == ["walk_started", "walk_ended"]
    r = run(t4.evaluate_to(None, True))
    assert r == M.EvaluationResult(None, None)
    assert st(t2) is READY and st(t3) is READY and st(t4) is READY and st(sec) == (READY, READY)
    # a strict call again reports the stop and tears the tail down (R2 stance)
    written = len(stand_ins.records("evaluation"))
    r = run(t4.evaluate_to(None, False))
    assert r.stopped_at is t1 and st(t4) is NOT_EVALUATED
    assert t4.resulting_state().name in TABLE.deleted
    # each status it changed is written, by no run: no messages, no duration
    # (LOGGING.md §4)
    assert [r["data"] for r in stand_ins.records("evaluation")[written:] if r["event"] == "operation"] == [
        {"node": f.full_id(n), "operation": operation, "ran": False, "status": "not_evaluated"}
        for n, operation in ((t2, "own"), (sec, "ending"), (t3, "own"), (t4, "own"))]


def test_c_failed_opening():
    f, thy, sec, t1, t2, t3, t4 = build(Section="begin")
    # a destination under the failed opening: the tree's walk ends at the
    # block, the stop this call reports (ARCHITECTURE §3.3)
    r = run(t2.evaluate_to(None, False))
    assert r == M.EvaluationResult(sec, None)
    assert st(sec) == (CANNOT_EVALUATE, NOT_EVALUATED)
    assert st(t1) is NOT_EVALUATED and st(t2) is NOT_EVALUATED
    # a destination after the block: the walk goes on past it
    r = run(t4.evaluate_to(None, False))
    assert r == M.EvaluationResult(None, None) and sec.begin_runs == 1   # not rerun
    assert st(sec) == (CANNOT_EVALUATE, READY) and st(t3) is READY and st(t4) is READY
    assert TABLE.values[sec.resulting_state().name] == "begin Theory"           # input stands as result
    # under it again: no rerun of the opening, and everything after the
    # destination is invalidated, the block's ending included
    r = run(t1.evaluate_to(None, False))
    assert r.stopped_at is sec and st(t1) is NOT_EVALUATED and sec.begin_runs == 1
    assert st(sec) == (CANNOT_EVALUATE, NOT_EVALUATED)
    assert st(t3) is NOT_EVALUATED and st(t4) is NOT_EVALUATED
    # with ignore_error the destination stays not evaluated and no stop is reported
    r = run(t1.evaluate_to(None, True))
    assert r == M.EvaluationResult(None, None) and st(t1) is NOT_EVALUATED
    assert sec.begin_runs == 1


def test_d_invalidate_only():
    f, thy, sec, t1, t2, t3, t4 = build()
    run(t4.evaluate_to(None, False))
    assert all(st(n) is READY for n in (t1, t2, t3, t4))
    TABLE.deleted.clear()
    invalidate(t1)
    assert st(t1) is NOT_EVALUATED and st(t4) is NOT_EVALUATED
    assert st(sec) == (READY, NOT_EVALUATED) and st(thy) == (READY, NOT_EVALUATED)
    assert sec._state_after_beginning().name not in TABLE.deleted        # the opening's state stands
    assert t1.resulting_state().name in TABLE.deleted
    # deletion of the last child: the destination is the block itself
    run(t4.evaluate_to(None, False))
    run(locked(f, edit.delete(t2)))
    assert sec.sub_nodes == [t1] and st(t1) is READY
    assert st(sec) == (READY, NOT_EVALUATED) and st(t3) is NOT_EVALUATED
    assert TABLE.values[t1.resulting_state().name] == "after T1#2"      # the value (of T1's second run) moved with the position


def test_insert_into_evaluated_tree():
    f, thy, sec, t1, t2, t3, t4 = build()
    run(t4.evaluate_to(None, False))
    kinds = {"t": T}

    async def insert_and_run(parent, index, raws):     # the tool entry's flow
        async with f.lock:
            nodes = await edit.insert(parent,index, raws, kinds)
            return nodes, await f._run(M.Evaluation(nodes[-1], False))

    (new,), r = run(insert_and_run(sec, 1, [{"kind": "t", "name": "N"}]))
    assert r == M.EvaluationResult(None, None)
    assert new.runs == 1 and st(new) is READY and sec.sub_nodes == [t1, new, t2]
    assert st(t2) is NOT_EVALUATED and st(t3) is NOT_EVALUATED
    assert st(sec) == (READY, NOT_EVALUATED) and st(thy) == (READY, NOT_EVALUATED)
    assert t1.runs == 1                                                  # the predecessor untouched
    # a predecessor not ready: the new slot stays empty, no copy
    (new2,) = run(locked(f, edit.insert(sec,3, [{"kind": "t", "name": "N2"}], kinds)))
    assert new2.state.name not in TABLE.values and sec.sub_nodes == [t1, new, t2, new2]


def test_states_inside_gathers_the_subtree_into_the_accumulator():
    f, thy, sec, t1, t2, t3, t4 = build()
    assert sec._states_inside() == [sec.state, t1.state, t2.state, sec._state_before_ending]
    out = ["x"]
    assert t1._states_inside(out) is out and out == ["x", t1.state]   # extended in place


def test_finished_is_derived_and_owes_nothing_is_the_classes_part():
    f, thy, sec, t1, t2, t3, t4 = build()
    assert not thy.is_finished() and not f.is_finished()
    run(t4.evaluate_to(None, False))
    assert sec.is_finished() and not thy.is_finished()   # the theory's ending has not run
    run(thy.evaluate_to(None, False))
    assert thy.is_finished() and f.is_finished()
    class Owing(jobs.Unfinished):
        def title(self, plural=False): return "debts" if plural else "debt"
    t2._unfinished = lambda: Owing()             # type: ignore[method-assign]  # one leaf still owing something
    assert t1.is_finished() and not t2.is_finished()
    assert not sec.is_finished() and not thy.is_finished() and not f.is_finished()
    assert t3.is_finished()                      # the debt does not spread sideways


def test_failed_ending_is_a_stop():
    f, thy, sec, t1, t2, t3, t4 = build(Section="end")
    r = run(t4.evaluate_to(None, False))
    assert r.stopped_at is sec and st(sec) == (READY, CANNOT_EVALUATE)
    assert st(t3) is NOT_EVALUATED
    r = run(t4.evaluate_to(None, False))
    assert r.stopped_at is sec and sec.end_runs == 1


def test_a_tat_error_from_an_evaluation_hook_is_the_classes_bug():
    """EXCEPTIONS.md §1: a `TAT_Error` escaping an evaluation hook is raised
    as `TAT_InternalError` from it, so that none is rendered to the agent;
    anything else passes as it is."""
    class Raising(T):
        async def _eval_opr(self):
            raise InvalidName("oops")
    class Crashing(T):
        async def _eval_opr(self):
            raise ZeroDivisionError("a bug of another kind")
    for cls, raised, cause in ((Raising, TAT_InternalError, InvalidName),
                               (Crashing, ZeroDivisionError, None)):
        f = OneTreeForest(CONN)
        thy = add(f, Block(f, slot(), "Theory", slot()))
        x = add(thy, cls(thy, slot(), "x"))
        with pytest.raises(raised) as e:
            run(x.evaluate_to(None, False))
        assert cause is None or isinstance(e.value.__cause__, cause)


def test_the_nodes_a_walk_passes():
    """`Evaluation.passed` (MODULE_STRUCTURE §4.1): the nodes the walk
    reached, a leaf when reached and a nesting node at its ending — one
    whose beginning failed when the walk goes on after it, and not when the
    destination lies under it."""
    async def passed(f, destination):
        async with f.lock:
            ev = M.Evaluation(destination, False)
            await f._evaluate(ev, M.Evaluating())
            f._store_written(ev)
            await ev.flush(f.conversation)
            return ev.passed
    f, thy, sec, t1, t2, t3, t4 = build()
    assert run(passed(f, t4)) == [t1, t2, sec, t3, t4]
    assert run(passed(f, sec)) == [t1, t2, sec]       # reached, though nothing ran again
    f, thy, sec, t1, t2, t3, t4 = build(Section="begin")
    assert run(passed(f, t4)) == [sec, t3, t4]
    assert run(passed(f, t2)) == []


def test_on_invalidated_sees_both_fields_written():
    """MODULE_STRUCTURE §4.1, "Events": a completed hook fires after the
    write, so `on_invalidated` finds the instant and the stored status of
    its operation both `not_evaluated`."""
    seen = []
    class Looking_T(T):
        def on_invalidated(self, operation):
            seen.append((self.name, operation, self._own_statuses(), self.last_evaluation_statuses()))
    class Looking_Block(Block):
        def on_invalidated(self, operation):
            seen.append((self.name, operation, self._own_statuses(), self.last_evaluation_statuses()))
    f = OneTreeForest(CONN)
    thy = add(f, Block(f, slot(), "Theory", slot()))
    blk = add(thy, Looking_Block(thy, slot(), "B", slot()))
    x = add(blk, Looking_T(blk, slot(), "x"))
    run(thy.evaluate_to(None, False))
    invalidate(blk)
    NE = NOT_EVALUATED
    assert seen == [("B", "beginning", [NE, READY], (NE, READY)),
                    ("x", None, [NE], (NE,)),
                    ("B", "ending", [NE, NE], (NE, NE))]


def test_a_status_write_forgets_the_operations_seen_key_for_every_agent():
    """`Conversation.forget` (PRINT.md §4): every write of an operation's
    status removes the seen set's key for its messages from every agent's
    set; an operation the guard leaves unwritten keeps its key."""
    f, thy, sec, t1, t2, t3, t4 = build()
    agents = [stand_ins.agent(f.conversation), stand_ins.agent(f.conversation, "a9f3", main=False)]
    kept = {(sec.identity, "ending"), (t3.identity, None)}
    for agent in agents:
        agent.seen.update(kept | {(thy.identity, "beginning"), (sec.identity, "beginning"),
                                  (t1.identity, None)})
    run(t1.evaluate_to(None, False))         # writes both beginnings and T1; what follows is unwritten already
    assert [agent.seen for agent in agents] == [kept, kept]
    f.conversation.forget((t3.identity, None))
    f.conversation.forget((t3.identity, None))        # a key not there is no error
    assert [agent.seen for agent in agents] == [{(sec.identity, "ending")}] * 2


class Owning(T):
    """A leaf with a slot of its own besides `state`, which its run writes:
    the class mints it — the constructor serves `gen` and `from_store`
    alike — appends it in `_states_inside`, and names it as written by its
    operation (MODULE_STRUCTURE §4.1, "States")."""
    def __init__(self, parent, state, name, fail=False):
        super().__init__(parent, state, name, fail)
        self.goal_state = Isar_State_Slot.assign(state.conversation)
    def _states_inside(self, out=None):
        out = super()._states_inside(out)
        out.append(self.goal_state)
        return out
    def _slots_written_by(self, operation):
        return (self.goal_state,)
    async def _eval_opr(self):
        TABLE.values[self.goal_state.name] = f"goal {self.name}"
        return await super()._eval_opr()

class Owning_Block(Block):
    """A nesting node whose beginning writes a slot of the class's own,
    which its ending reads."""
    def __init__(self, parent, state, name, sbe, fail_beginning=False, fail_ending=False):
        super().__init__(parent, state, name, sbe, fail_beginning, fail_ending)
        self.scratch = Isar_State_Slot.assign(state.conversation)
        self.read_at_the_ending = NOT_RUN
    def _states_inside(self, out=None):
        out = super()._states_inside(out)
        out.append(self.scratch)
        return out
    def _slots_written_by(self, operation):
        return (self.scratch,) if operation == "beginning" else ()
    async def _eval_beginning_opr(self):
        TABLE.values[self.scratch.name] = f"scratch {self.name}" + run_tag(self.begin_runs + 1)
        return await super()._eval_beginning_opr()
    async def _eval_ending_opr(self):
        self.read_at_the_ending = TABLE.values.get(self.scratch.name)
        return await super()._eval_ending_opr()


def test_a_slot_of_the_classes_own_is_released_with_its_writers_result_and_deleted_with_the_node(tmp_path):
    """MODULE_STRUCTURE §4.1, "States": a class may own a further slot,
    which it mints itself, on construction and afresh on load; the
    framework releases it with the result of the operation the class
    names as its writer, when that operation goes from written to
    unwritten, never on a rewrite; and deletes it with the node."""
    kinds = KINDS | {"owning": Owning}
    path = tmp_path / "TAT.sqlite"
    f = OneTreeForest(CONN, Forest_Store(path, stand_ins.log()), kinds)
    (thy,) = run(locked(f, edit.insert(f, 0, [
        {"kind": "block", "name": "Theory", "children": [
            {"kind": "owning", "name": "o"}, {"kind": "owning", "name": "p"},
            {"kind": "t", "name": "x"}]}], kinds)))
    o, p, x = thy.sub_nodes
    assert o._states_inside() == [o.state, o.goal_state]
    names = [s.name for s in thy._states_inside()]
    assert len(set(names)) == len(names)              # no other slot's name
    run(x.evaluate_to(None, False))
    assert TABLE.values[o.goal_state.name] == "goal o" and TABLE.values[p.goal_state.name] == "goal p"
    ev = M.Evaluation(None, False)
    p._set_status(ev, READY, 0.0)                     # a rerun's rewrite releases nothing
    assert ev._released == set()
    f._store_written(ev)
    TABLE.deleted.clear()
    invalidate(p)                                     # written -> unwritten: with the result
    assert {p.goal_state.name, p.resulting_state().name} <= set(TABLE.deleted)
    assert o.goal_state.name in TABLE.values and p.goal_state.name not in TABLE.values
    TABLE.deleted.clear()
    run(locked(f, edit.delete(p)))                    # with the node
    assert p.goal_state.name in TABLE.deleted
    TABLE.deleted.clear()
    old = o.goal_state.name
    (o2,) = run(locked(f, edit.amend(o, [{"kind": "owning", "name": "o2"}], kinds)))
    assert old in TABLE.deleted and o2.goal_state.name != old
    before = {s.name for s in thy._states_inside()}
    f.store.close()
    f2 = OneTreeForest(CONN, Forest_Store(path, stand_ins.log()), kinds)
    o3 = f2.sub_nodes[0].sub_nodes[0]
    assert isinstance(o3, Owning) and o3.goal_state.name not in before
    after = [s.name for s in f2.sub_nodes[0]._states_inside()]
    assert len(set(after)) == len(after) and not before & set(after)


def test_slots_released_counts_each_deleted_name_once():
    """`walk_ended`'s `slots_released` (LOGGING.md §4) is the number of
    names the walk's `state_delete`s named: a slot released twice on one
    `Evaluation` is deleted, and counted, once."""
    kinds = KINDS | {"owning_block": Owning_Block}
    f = OneTreeForest(CONN, kinds=kinds)
    ev = M.Evaluation(None, False)
    twice = slot()
    ev.release(twice); ev.release(twice)
    run(ev.flush(f.conversation))
    assert TABLE.calls == [("delete", (twice.name,))] and ev.releases == 1
    # on a walk: a nesting node invalidated whole, the slot of its own
    # released with its beginning's result
    (thy,) = run(locked(f, edit.insert(f, 0, [
        {"kind": "block", "name": "Theory", "children": [
            {"kind": "t", "name": "d"},
            {"kind": "owning_block", "name": "O", "children": [{"kind": "t", "name": "z"}]}]}], kinds)))
    d, o = thy.sub_nodes
    run(thy.evaluate_to(None, False))
    assert st(o) == (READY, READY)
    TABLE.calls.clear()
    run(d.evaluate_to(None, False))                         # everything after d is invalidated
    [(_, names)] = [c for c in TABLE.calls if c[0] == "delete"]
    assert o.scratch.name in names and len(set(names)) == len(names) == 5
    walk_ended = stand_ins.records("evaluation")[-1]
    assert walk_ended["event"] == "walk_ended" and walk_ended["data"]["slots_released"] == len(names)


def test_a_nesting_class_names_the_operation_that_writes_its_slot():
    """`_slots_written_by` (MODULE_STRUCTURE §4.1, "States"): a slot the
    beginning writes is released with the beginning's result and not with
    the ending's — a walk to a node inside the block invalidates the
    ending alone, and the ending, run again, finds what the still-`ready`
    beginning wrote."""
    kinds = KINDS | {"owning_block": Owning_Block}
    f = OneTreeForest(CONN, kinds=kinds)
    (thy,) = run(locked(f, edit.insert(f, 0, [
        {"kind": "block", "name": "Theory", "children": [
            {"kind": "owning_block", "name": "P", "children": [
                {"kind": "t", "name": "a"}, {"kind": "t", "name": "b"}]},
            {"kind": "t", "name": "d"}]}], kinds)))
    p, d = thy.sub_nodes
    a, b = p.sub_nodes
    run(d.evaluate_to(None, False))
    assert p.read_at_the_ending == "scratch P"
    TABLE.deleted.clear()
    run(a.evaluate_to(None, False))                 # past a: b, P's ending and d are invalidated
    assert st(p) == (READY, NOT_EVALUATED)
    assert p.scratch.name not in TABLE.deleted and TABLE.values[p.scratch.name] == "scratch P"
    run(d.evaluate_to(None, False))                 # the ending runs again, the beginning does not
    assert (p.begin_runs, p.end_runs) == (1, 2) and p.read_at_the_ending == "scratch P"
    invalidate(p)                             # the beginning goes unwritten: its slot with its result
    assert p.scratch.name in TABLE.deleted and p.scratch.name not in TABLE.values


# --- persistence (the plan's §2) ---------------------------------------------

def shape(forest):
    """What a round trip must preserve, node by node in tree order."""
    return [(n.identity, n.kind, n.name, n.fail if isinstance(n, T)
             else (n.fail_beginning, n.fail_ending),
             len(n.sub_nodes) if isinstance(n, M.NonLeaf_Node) else None,
             n.last_evaluation_statuses())
            for n in forest._all_nodes()]


def test_reopen_restores_the_forest_not_evaluated(tmp_path):
    path = tmp_path / "TAT.sqlite"
    store = Forest_Store(path, stand_ins.log())
    f = OneTreeForest(CONN, store)
    (thy,) = run(locked(f, edit.insert(f,0, [
        {"kind": "block", "name": "Theory", "children": [
            {"kind": "block", "name": "Section", "children": [
                {"kind": "t", "name": "T1", "fail": True},
                {"kind": "t", "name": "T2"}]},
            {"kind": "t", "name": "T3"}]}], KINDS)))
    t3 = thy.sub_nodes[1]
    run(t3.evaluate_to(None, True))
    assert st(t3) is READY
    slots_before = {s.name for n in f._all_nodes() for s in n._states_inside()}
    store.close()

    f2 = OneTreeForest(CONN, Forest_Store(path, stand_ins.log()))
    assert shape(f2) == shape(f)
    assert all(n.parent is not None and n in n.parent.sub_nodes for n in f2._all_nodes())
    slots_after = [s.name for t in f2.sub_nodes for s in t._states_inside()]
    for n in f2._all_nodes():                    # not_evaluated throughout, slots afresh
        assert st(n) in (NOT_EVALUATED, (NOT_EVALUATED, NOT_EVALUATED))
    assert not slots_before & set(slots_after)
    assert len(set(slots_after)) == len(slots_after)          # and pairwise distinct
    # the loaded forest evaluates like the original did
    from invariants import assert_invariants     # here: invariants.py imports this module
    thy2 = f2.sub_nodes[0]
    r = run(thy2.sub_nodes[1].evaluate_to(None, True))
    assert r == M.EvaluationResult(None, None)
    assert st(thy2) == (READY, NOT_EVALUATED) and st(thy2.sub_nodes[0]) == (READY, READY)
    assert st(thy2.sub_nodes[0].sub_nodes[0]) is CANNOT_EVALUATE      # T1 still fails
    assert_invariants(f2, TABLE)
    # a fresh identity after the reopen collides with no loaded one
    (new,) = run(locked(f2, edit.insert(thy2,0, [{"kind": "t", "name": "N"}], KINDS)))
    assert new.identity not in {i for i, *_ in shape(f)}


def test_reopen_restores_the_stored_statuses_and_a_walk_reruns_what_it_reaches(tmp_path):
    """COMPILATION.md §4: the stored statuses come back as the last run left
    them while every instant status is `not_evaluated`; a walk reruns and
    stores what it reaches, and past its destination marks the rest of the
    tree `not_evaluated` in both fields."""
    from invariants import assert_invariants, assert_store_mirrors
    path = tmp_path / "TAT.sqlite"
    store = Forest_Store(path, stand_ins.log())
    f = OneTreeForest(CONN, store)
    (thy,) = run(locked(f, edit.insert(f,0, [
        {"kind": "block", "name": "Theory", "children": [
            {"kind": "t", "name": "T1"},
            {"kind": "block", "name": "Section", "children": [
                {"kind": "t", "name": "T2", "fail": True},
                {"kind": "t", "name": "T3"}]},
            {"kind": "t", "name": "T4"}]}], KINDS)))
    t1, sec, t4 = thy.sub_nodes
    t2, t3 = sec.sub_nodes
    run(thy.evaluate_to(None, True))                        # the whole tree, past the obstacle
    stored = {n.name: n.last_evaluation_statuses() for n in f._all_nodes()}
    assert stored["T2"] == (CANNOT_EVALUATE,) and stored["T4"] == (READY,)
    assert stored["Theory"] == (READY, READY) and stored["Section"] == (READY, READY)
    store.close()

    invalidated = []
    class Telling_T(T):
        def on_invalidated(self, operation): invalidated.append(self.name)
    class Telling_Block(Block):
        def on_invalidated(self, operation): invalidated.append(self.name)
    f2 = OneTreeForest(CONN, Forest_Store(path, stand_ins.log()),
                       kinds={"t": Telling_T, "block": Telling_Block})
    by_name = {n.name: n for n in f2._all_nodes()}
    for name, statuses in stored.items():
        assert by_name[name].last_evaluation_statuses() == statuses
        assert all(s is NOT_EVALUATED for s in by_name[name]._own_statuses())
    TABLE.calls.clear()
    r = run(by_name["T1"].evaluate_to(None, True))
    assert r == M.EvaluationResult(None, None)
    # On a loaded node the setter finds nothing written: it releases
    # nothing, and no status "truly left `ready`" (COMPILATION.md §4).
    assert not [c for c in TABLE.calls if c[0] == "delete"] and invalidated == []
    assert stand_ins.records("evaluation")[-1]["data"]["slots_released"] == 0
    assert st(by_name["T1"]) is READY and by_name["T1"].last_evaluation_statuses() == (READY,)
    for name in ("T2", "T3", "T4"):
        assert st(by_name[name]) is NOT_EVALUATED
        assert by_name[name].last_evaluation_statuses() == (NOT_EVALUATED,)
    assert by_name["Section"].last_evaluation_statuses() == (NOT_EVALUATED, NOT_EVALUATED)
    assert by_name["Theory"].last_evaluation_statuses() == (READY, NOT_EVALUATED)
    assert_invariants(f2, TABLE)
    assert_store_mirrors(f2, KINDS)


def test_a_beginning_failing_after_a_restart_invalidates_what_its_children_stored(tmp_path):
    """ARCHITECTURE §3.3, COMPILATION.md §4: under a beginning that failed
    the children are `not_evaluated` in both fields — also the children a
    run before the restart left stored `ready`."""
    from invariants import assert_invariants, assert_store_mirrors
    for destination in ("c", "a"):                    # after the block, and under it
        path = tmp_path / f"{destination}.sqlite"
        f = OneTreeForest(CONN, Forest_Store(path, stand_ins.log()))
        (thy,) = run(locked(f, edit.insert(f, 0, [
            {"kind": "block", "name": "Theory", "children": [
                {"kind": "block", "name": "Section", "children": [
                    {"kind": "t", "name": "a"}, {"kind": "t", "name": "b"}]},
                {"kind": "t", "name": "c"}]}], KINDS)))
        run(thy.evaluate_to(None, False))
        sec = thy.sub_nodes[0]
        sec.fail_beginning = True                     # the verdict changes between the runs
        with f.store.transaction():
            f._store_node(sec)
        f.store.close()

        f2 = OneTreeForest(CONN, Forest_Store(path, stand_ins.log()))
        by_name = {n.name: n for n in f2._all_nodes()}
        def stored(name):
            return by_name[name].last_evaluation_statuses()
        assert stored("a") == stored("b") == (READY,)
        r = run(by_name[destination].evaluate_to(None, False))
        assert stored("a") == stored("b") == (NOT_EVALUATED,), destination
        if destination == "c":
            assert r == M.EvaluationResult(None, None)
            assert stored("Section") == (CANNOT_EVALUATE, READY) and stored("c") == (READY,)
        else:
            assert r.stopped_at is by_name["Section"]
            assert stored("Section") == (CANNOT_EVALUATE, NOT_EVALUATED)
            assert stored("c") == (NOT_EVALUATED,)
        assert_invariants(f2, TABLE)
        assert_store_mirrors(f2, KINDS)


def test_a_statuses_row_missing_or_short_reads_not_evaluated_and_a_malformed_one_is_refused(tmp_path):
    """COMPILATION.md §4's missing-row rule."""
    path = tmp_path / "TAT.sqlite"
    store = Forest_Store(path, stand_ins.log())
    f = OneTreeForest(CONN, store)
    (thy,) = run(locked(f, edit.insert(f,0, [
        {"kind": "block", "name": "Theory", "children": [{"kind": "t", "name": "T1"}]}], KINDS)))
    t1 = thy.sub_nodes[0]
    run(thy.evaluate_to(None, True))
    assert thy.last_evaluation_statuses() == (READY, READY)
    with store.transaction():
        store.put(thy.identity, "last_evaluation_statuses", [["ready", []]])   # short: two operations
        store.delete_node(t1.identity)                                            # missing
        store.put(t1.identity, "kind", "t")
        store.put(t1.identity, "name", "T1")
        store.put(t1.identity, "fail", False)
    store.close()
    f2 = OneTreeForest(CONN, Forest_Store(path, stand_ins.log()))
    thy2 = f2.sub_nodes[0]
    assert thy2.last_evaluation_statuses() == (NOT_EVALUATED, NOT_EVALUATED)
    assert thy2.sub_nodes[0].last_evaluation_statuses() == (NOT_EVALUATED,)
    f2.store.close()
    with Forest_Store(path, stand_ins.log()) as s:
        with s.transaction():
            s.put(thy.identity, "last_evaluation_statuses", [["ready", []], ["elsewhere", []]])
    with pytest.raises(TAT_StartupError, match="last_evaluation_statuses"):
        OneTreeForest(CONN, Forest_Store(path, stand_ins.log()))


def test_a_fresh_database_is_an_empty_forest():
    f = OneTreeForest(CONN)
    assert f.sub_nodes == [] and f.store.nodes() == []


def test_the_trees_keep_their_order_across_a_reopen(tmp_path):
    path = tmp_path / "TAT.sqlite"
    f = OneTreeForest(CONN, Forest_Store(path, stand_ins.log()))
    a, b = run(locked(f, edit.insert(f,0, [
        {"kind": "block", "name": "A", "children": [{"kind": "t", "name": "x"}]},
        {"kind": "block", "name": "B"}], KINDS)))
    run(locked(f, edit.move(a, f, 1)))                      # -> [B, A]
    assert f.sub_nodes == [b, a]
    assert set(f.store.fields(f.identity)) == {"children"}       # the root's one row
    f.store.close()
    f2 = OneTreeForest(CONN, Forest_Store(path, stand_ins.log()))
    assert shape(f2) == shape(f)
    assert [t.name for t in f2.sub_nodes] == ["B", "A"]


def test_delete_and_amend_at_the_root_reach_the_store(tmp_path):
    path = tmp_path / "TAT.sqlite"
    f = OneTreeForest(CONN, Forest_Store(path, stand_ins.log()))
    a, b = run(locked(f, edit.insert(f,0, [
        {"kind": "block", "name": "A", "children": [{"kind": "t", "name": "x"}]},
        {"kind": "block", "name": "B", "children": [{"kind": "t", "name": "y"}]}], KINDS)))
    gone = {b.identity, b.sub_nodes[0].identity}
    run(locked(f, edit.delete(b)))
    assert f.store.get(f.identity, "children") == [a.identity]
    assert not gone & set(f.store.nodes())
    (a2,) = run(locked(f, edit.amend(a, [{"kind": "block", "name": "A2"}], KINDS)))
    assert a2.identity == a.identity and [c.name for c in a2.sub_nodes] == ["x"]
    f.store.close()
    f2 = OneTreeForest(CONN, Forest_Store(path, stand_ins.log()))
    assert shape(f2) == shape(f)
    assert [t.name for t in f2.sub_nodes] == ["A2"]
    assert [c.name for c in f2.sub_nodes[0].sub_nodes] == ["x"]


def test_the_loader_places_the_node_whatever_from_store_passed():
    class Careless(T):
        @classmethod
        def from_store(cls, config, rows):
            return cls(None, config.state, rows.get("name"), rows.get("fail"))
    store = Forest_Store(":memory:", stand_ins.log())
    f = OneTreeForest(CONN, store)
    run(locked(f, edit.insert(f,0, [
        {"kind": "block", "name": "B", "children": [{"kind": "t", "name": "a"}]}], KINDS)))
    f2 = OneTreeForest(CONN, store, kinds={"block": Block, "t": Careless})
    a = f2.sub_nodes[0].sub_nodes[0]
    assert isinstance(a, Careless) and a.parent is f2.sub_nodes[0]
    assert f2.id_of(a) == "block_B.t_a"


def test_a_block_threads_the_indent_through_what_it_emits():
    """COMPILATION.md §3: a block's children get the indent `emit_beginning`
    returns, each sibling the one the sibling before it returned, and
    `emit_ending` the block's own; the block returns what `emit_ending`
    returns."""
    import io
    class Deepening(T):
        def emit(self, indent, out):
            return super().emit(indent, out) + 5
    class Stepped(Block):
        def emit_beginning(self, indent, out):
            return super().emit_beginning(indent, out) + 1
        def emit_ending(self, indent, out):
            return super().emit_ending(indent, out) + 3
    kinds = {"t": Deepening, "block": Stepped}
    f = OneTreeForest(CONN, kinds=kinds)
    (blk,) = run(locked(f, edit.insert(f, 0, [{"kind": "block", "name": "B", "children": [
        {"kind": "t", "name": "a"}, {"kind": "t", "name": "b"}]}], kinds)))
    out = io.StringIO()
    assert blk.emit(2, out) == 5
    assert out.getvalue() == (M.INDENT * 2 + "section ‹B›\n"
                              + M.INDENT * 3 + "text ‹a›\n"
                              + "\n"
                              + M.INDENT * 8 + "text ‹b›\n"
                              + M.INDENT * 2 + "text ‹end of B›\n")


class Bare(M.Leaf):                 # a class that wrote neither persistence method
    argument_schema = T_RawAST
    @classmethod
    async def gen(cls, config, raw):
        n = cls(config.parent, config.state); n.name = raw["name"]; return n
    async def _eval_opr(self): return READY
    def emit(self, indent, out): return indent

class WriteOnly(Bare):              # ... and one that wrote only to_store
    def to_store(self, rows): rows.put("name", self.name)


def test_a_store_failure_after_the_commit_is_a_disaster(tmp_path):
    """The transaction opens after the in-memory commit, so its failure
    parts memory from the database: `TAT_DisasterError`, from the cause;
    the database keeps the last committed forest (EXCEPTIONS.md §1)."""
    class Broken(T):
        def to_store(self, rows):
            raise ZeroDivisionError("to_store broke")
    path = tmp_path / "TAT.sqlite"
    f = OneTreeForest(CONN, Forest_Store(path, stand_ins.log()))
    (thy,) = run(locked(f, edit.insert(f,0, [{"kind": "block", "name": "Theory"}], KINDS)))
    with pytest.raises(TAT_DisasterError, match="to_store broke") as e:
        run(locked(f, edit.insert(thy,0, [{"kind": "b", "name": "x"}], {"b": Broken})))
    assert isinstance(e.value.__cause__, ZeroDivisionError)
    assert [n.name for n in thy.sub_nodes] == ["x"]          # memory kept the change
    f.store.close()
    f2 = OneTreeForest(CONN, Forest_Store(path, stand_ins.log()))              # the database did not
    assert [t.name for t in f2.sub_nodes] == ["Theory"] and f2.sub_nodes[0].sub_nodes == []


def test_a_class_without_to_store_fails_at_its_first_edit():
    f = OneTreeForest(CONN)
    # inside the store transaction, so a disaster whose cause is the class's bug
    with pytest.raises(TAT_DisasterError, match="Bare has no to_store") as e:
        run(locked(f, edit.insert(f,0, [{"kind": "bare", "name": "x"}], {"bare": Bare})))
    assert isinstance(e.value.__cause__, TAT_InternalError)


def test_a_class_without_from_store_fails_at_the_reopen():
    store = Forest_Store(":memory:", stand_ins.log())
    f = OneTreeForest(CONN, store, kinds={"w": WriteOnly})
    run(locked(f, edit.insert(f,0, [{"kind": "w", "name": "x"}], {"w": WriteOnly})))
    with pytest.raises(TAT_InternalError, match="WriteOnly has no from_store"):
        OneTreeForest(CONN, store, kinds={"w": WriteOnly})


def test_a_field_a_class_reads_but_the_database_lacks_is_a_startup_error():
    class Wants_More(T):
        @classmethod
        def from_store(cls, config, rows):
            rows.get("colour")
            return super().from_store(config, rows)
    store = Forest_Store(":memory:", stand_ins.log())
    f = OneTreeForest(CONN, store)
    (x,) = run(locked(f, edit.insert(f,0, [{"kind": "t", "name": "x"}], KINDS)))
    with pytest.raises(TAT_StartupError, match=f"`colour` for node {x.identity}"):
        OneTreeForest(CONN, store, kinds={"t": Wants_More})


@pytest.mark.parametrize("blob", [b"\xc1\xc1\xc1",       # not MessagePack at all
                                  b"\x81\x90\x54"])      # a map keyed by a list
def test_a_corrupt_field_value_is_a_startup_error(blob):
    store = Forest_Store(":memory:", stand_ins.log())
    f = OneTreeForest(CONN, store)
    (x,) = run(locked(f, edit.insert(f,0, [{"kind": "t", "name": "x"}], KINDS)))
    store._conn.execute("UPDATE fields SET value = ? WHERE node = ? AND field = 'name'",
                        (blob, x.identity))
    with pytest.raises(TAT_StartupError, match=f"`name` of node {x.identity} is not readable"):
        OneTreeForest(CONN, store)


def test_a_kind_that_is_not_a_string_is_a_startup_error():
    store = Forest_Store(":memory:", stand_ins.log())
    f = OneTreeForest(CONN, store)
    (x,) = run(locked(f, edit.insert(f,0, [{"kind": "t", "name": "x"}], KINDS)))
    with store.transaction():
        store.put(x.identity, "kind", [1])
    with pytest.raises(TAT_StartupError, match="kind `\\[1\\]`"):
        OneTreeForest(CONN, store)


def _damaged(children_of, value):
    """A one-tree store whose `children` row of `children_of` ("root" or
    "block") is overwritten with `value`."""
    store = Forest_Store(":memory:", stand_ins.log())
    f = OneTreeForest(CONN, store)
    (blk,) = run(locked(f, edit.insert(f,0, [
        {"kind": "block", "name": "B", "children": [{"kind": "t", "name": "a"}]}], KINDS)))
    node = f.identity if children_of == "root" else blk.identity
    with store.transaction():
        store.put(node, "children", value(f, blk))
    return store


@pytest.mark.parametrize("children_of,value,message", [
    ("root", lambda f, blk: 7, "not a list of identities"),
    ("root", lambda f, blk: "oops", "not a list of identities"),
    ("block", lambda f, blk: [True], "not a list of identities"),
    ("block", lambda f, blk: [blk.sub_nodes[0].identity] * 2, "already in the forest being loaded"),
    ("block", lambda f, blk: [blk.identity], "already in the forest being loaded"),   # a cycle
    ("block", lambda f, blk: [f.identity], "node 0 as a child, but it is already"),   # back to the root
    ("root", lambda f, blk: [blk.identity, blk.identity], "already in the forest being loaded"),
])
def test_a_damaged_children_row_is_refused_at_start(children_of, value, message):
    store = _damaged(children_of, value)
    with pytest.raises(TAT_StartupError, match=message):
        OneTreeForest(CONN, store)


def test_a_missing_root_row_over_a_populated_database_is_refused():
    store = Forest_Store(":memory:", stand_ins.log())
    f = OneTreeForest(CONN, store)
    run(locked(f, edit.insert(f,0, [{"kind": "t", "name": "x"}], KINDS)))
    with store.transaction():
        store.delete_node(f.identity)
    with pytest.raises(TAT_StartupError, match="`children` for node 0"):
        OneTreeForest(CONN, store)


def test_a_kind_without_a_class_is_a_startup_error():
    store = Forest_Store(":memory:", stand_ins.log())
    f = OneTreeForest(CONN, store)
    run(locked(f, edit.insert(f,0, [{"kind": "t", "name": "x"}], KINDS)))
    with pytest.raises(TAT_StartupError, match="kind `t`"):
        OneTreeForest(CONN, store, kinds={"block": Block})


def test_a_missing_row_is_a_startup_error():
    store = Forest_Store(":memory:", stand_ins.log())
    f = OneTreeForest(CONN, store)
    (x,) = run(locked(f, edit.insert(f,0, [{"kind": "t", "name": "x"}], KINDS)))
    with store.transaction():
        store.delete_node(x.identity)           # the root's `children` row still names it
    with pytest.raises(TAT_StartupError, match=f"`kind` for node {x.identity}"):
        OneTreeForest(CONN, store)


def test_from_store_may_not_return_children():
    class Greedy(Block):
        @classmethod
        def from_store(cls, config, rows):
            node = super().from_store(config, rows)
            node.sub_nodes.append(T(node, slot(), "stowaway"))
            return node
    store = Forest_Store(":memory:", stand_ins.log())
    f = OneTreeForest(CONN, store)
    run(locked(f, edit.insert(f,0, [{"kind": "block", "name": "B"}], KINDS)))
    with pytest.raises(TAT_InternalError, match="returned children"):
        OneTreeForest(CONN, store, kinds={"block": Greedy, "t": T})


