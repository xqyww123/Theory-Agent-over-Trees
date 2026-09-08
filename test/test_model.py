"""The recursion of `model.py` on `Theory > [Section > [T1, T2], T3, T4]`,
against a fake state slot table and a real `Forest_Store`; and the forest's
round trip through the store.  Run: python -m pytest test/test_model.py
"""

import asyncio
import sys
import types
import typing
from contextlib import contextmanager
from typing import NotRequired, TypedDict

try:
    import Isabelle_RPC_Host  # noqa: F401
except ImportError:                       # the test needs no Isabelle
    m = types.ModuleType("Isabelle_RPC_Host")
    m.Connection = object  # type: ignore[attr-defined]
    sys.modules["Isabelle_RPC_Host"] = m

import pytest

from isabelle_theory_agent import edit, isabelle_driver, model as M
from isabelle_theory_agent.exceptions import (
    TAT_DisasterError, TAT_InternalError, TAT_StartupError)
from isabelle_theory_agent.model import (
    NOT_EVALUATED, READY, INVALIDATING, CannotEvaluate, Isar_State_Slot)
from isabelle_theory_agent.store import Forest_Store


# --- a fake state slot table ------------------------------------------------

class Table:
    """The fake state slot table, and a recorder of every store's writes:
    how many transactions opened, which nodes they touched, and which
    stores are inside one right now."""

    def __init__(self):
        self.values: dict[str, str] = {}
        self.deleted: list[str] = []
        self.calls: list[tuple] = []        # every round trip, in order
        self.transactions = 0
        self.touched: set[int] = set()      # nodes written or deleted
        self.open_stores: set = set()

    def clear(self):
        self.values.clear(); self.deleted.clear(); self.calls.clear()
        self.clear_writes()

    def clear_writes(self):
        self.transactions = 0
        self.touched.clear()

    def _no_transaction_open(self):
        """Every round trip is an `await`, and no transaction may span one
        (store.py, `transaction`)."""
        assert not self.open_stores, "a store transaction is open across an await"

    def install(self, monkeypatch):
        async def state_delete(conn, names):
            self._no_transaction_open()
            self.calls.append(("delete", tuple(names)))
            for n in names:
                self.values.pop(n, None); self.deleted.append(n)
        async def state_exists(conn, name):
            self._no_transaction_open()
            return name in self.values
        async def state_copy(conn, src, dst):
            self._no_transaction_open()
            self.calls.append(("copy", src, dst))
            if src in self.values: self.values[dst] = self.values[src]
            else: self.values.pop(dst, None)
        for f in (state_delete, state_exists, state_copy):
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
            return False
        self.consumed = got
        TABLE.values[self.resulting_state().name] = f"after {self.name}" + run_tag(self.runs)
        return True
    def on_invalidated(self, operation): self.consumed = NOT_RUN
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
                   Isar_State_Slot.assign(config.state.connection),
                   fail_beginning=raw.get("fail", False))
    def to_store(self, rows):
        rows.put("name", self.name)
        rows.put("fail_beginning", self.fail_beginning)
        rows.put("fail_ending", self.fail_ending)
    @classmethod
    def from_store(cls, config, rows):
        return cls(config.parent, config.state, rows.get("name"),
                   Isar_State_Slot.assign(config.state.connection),
                   fail_beginning=rows.get("fail_beginning"),
                   fail_ending=rows.get("fail_ending"))
    async def _eval_beginning_opr(self):
        self.begin_runs += 1
        self.consumed_begin = (NOT_RUN if self.fail_beginning
                               else TABLE.values.get(self.state.name))
        if self.fail_beginning: return False
        TABLE.values[self._state_after_beginning().name] = \
            f"begin {self.name}" + run_tag(self.begin_runs)
        return True
    async def _eval_ending_opr(self):
        self.end_runs += 1
        got = TABLE.values.get(self._state_before_ending.name)
        if self.fail_ending:
            self.consumed_end, self.copied_end = NOT_RUN, got
            return False
        self.consumed_end = got
        TABLE.values[self.resulting_state().name] = f"end {self.name}" + run_tag(self.end_runs)
        return True
    def on_invalidated(self, operation):
        if operation == "beginning": self.consumed_begin = NOT_RUN
        else: self.consumed_end = NOT_RUN
    def __repr__(self): return self.name


KINDS = {"t": T, "block": Block}


class OneTreeForest(M.Forest):      # enough of `Forest` to drive one tree
    def __init__(self, conn, store=None, kinds=KINDS):
        super().__init__(Isar_State_Slot.assign(conn),
                         store if store is not None else Forest_Store(":memory:"), kinds)
        self._end = Isar_State_Slot.assign(conn)
    def _resulting_state_of_all_children(self): return self._end
    async def _evaluate(self, ev, mode): return await self._evaluate_children(ev, mode)


TABLE = Table()
CONN = typing.cast(typing.Any, object())     # stands in for a Connection
NOT_RUN = object()                           # "this operation has not run since it was last current"


def run_tag(n):
    """Every run writes a distinct value, so a stale copy is visible; the
    first run's value stays bare for the tests that spell it out."""
    return "" if n == 1 else f"#{n}"


def slot(): return Isar_State_Slot.assign(CONN)


def add(parent, node):
    """Append a directly built node the way the framework would have entered
    it: identity and kind set, its rows and the parent's `children` row
    stored — so the store mirrors the forest from the start."""
    f = parent.forest()
    node.parent = parent
    node.kind = "block" if isinstance(node, M.NonLeaf_Node) else "t"
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


@pytest.fixture(autouse=True)
def table(monkeypatch):
    TABLE.clear()
    TABLE.install(monkeypatch)


# --- scenarios -----------------------------------------------------------------

def test_a_evaluate_inside_block():
    f, thy, sec, t1, t2, t3, t4 = build()
    r = run(t2.evaluate_to(False))
    assert r == M.EvaluationResult(None, INVALIDATING)
    assert st(thy) == (READY, NOT_EVALUATED) and st(sec) == (READY, NOT_EVALUATED)
    assert st(t1) is READY and st(t2) is READY and st(t3) is NOT_EVALUATED
    # (e) a later call runs the ending, never the beginning again
    r = run(t3.evaluate_to(False))
    assert sec.begin_runs == 1 and sec.end_runs == 1 and thy.begin_runs == 1
    assert st(sec) == (READY, READY) and st(t3) is READY and st(t4) is NOT_EVALUATED
    run(t3.evaluate_to(False))
    assert t3.runs == 1 and sec.end_runs == 1        # nothing reruns


def test_b_own_stop_strict_then_ignore():
    f, thy, sec, t1, t2, t3, t4 = build(T1=True)
    r = run(t1.evaluate_to(False))
    assert r.stopped_at is t1 and st(t1) == CannotEvaluate(None)
    assert TABLE.values[t1.resulting_state().name] == "begin Section"   # the input copied through
    r = run(t4.evaluate_to(False))
    assert r.stopped_at is t1 and t1.runs == 1                          # not rerun
    assert st(t2) == CannotEvaluate(t1) and st(t3) == CannotEvaluate(t1) and st(t4) == CannotEvaluate(t1)
    assert st(sec) == (READY, CannotEvaluate(t1))
    r = run(t4.evaluate_to(True))
    assert r == M.EvaluationResult(None, INVALIDATING)
    assert st(t2) is READY and st(t3) is READY and st(t4) is READY and st(sec) == (READY, READY)
    # a strict call again reports the stop and tears the tail down (R2 stance)
    r = run(t4.evaluate_to(False))
    assert r.stopped_at is t1 and st(t4) == CannotEvaluate(t1)
    assert t4.resulting_state().name in TABLE.deleted


def test_c_failed_opening():
    f, thy, sec, t1, t2, t3, t4 = build(Section="begin")
    r = run(t2.evaluate_to(False))
    assert r == M.EvaluationResult(None, INVALIDATING)
    assert st(sec) == (CannotEvaluate(None), NOT_EVALUATED)
    assert st(t1) == CannotEvaluate(sec) and st(t2) == CannotEvaluate(sec)
    r = run(t4.evaluate_to(False))
    assert r == M.EvaluationResult(None, INVALIDATING) and sec.begin_runs == 1   # not rerun
    assert st(sec) == (CannotEvaluate(None), READY) and st(t3) is READY and st(t4) is READY
    assert TABLE.values[sec.resulting_state().name] == "begin Theory"           # input stands as result
    # a destination under the failed opening: visited, stays blocked, no rerun of the opening
    r = run(t1.evaluate_to(False))
    assert r == M.EvaluationResult(None, INVALIDATING) and st(t1) == CannotEvaluate(sec)
    assert sec.begin_runs == 1


def test_d_invalidate_only():
    f, thy, sec, t1, t2, t3, t4 = build()
    run(t4.evaluate_to(False))
    assert all(st(n) is READY for n in (t1, t2, t3, t4))
    TABLE.deleted.clear()
    r = run(t1.evaluate_to(False, evaluate=False))
    assert r == M.EvaluationResult(None, INVALIDATING)
    assert st(t1) is NOT_EVALUATED and st(t4) is NOT_EVALUATED
    assert st(sec) == (READY, NOT_EVALUATED) and st(thy) == (READY, NOT_EVALUATED)
    assert sec._state_after_beginning().name not in TABLE.deleted        # the opening's state stands
    assert t1.resulting_state().name in TABLE.deleted
    # deletion of the last child: the destination is the block itself
    run(t4.evaluate_to(False))
    run(locked(f, edit.delete(t2)))
    assert sec.sub_nodes == [t1] and st(t1) is READY
    assert st(sec) == (READY, NOT_EVALUATED) and st(t3) is NOT_EVALUATED
    assert TABLE.values[t1.resulting_state().name] == "after T1#2"      # the value (of T1's second run) moved with the position


def test_insert_into_evaluated_tree():
    f, thy, sec, t1, t2, t3, t4 = build()
    run(t4.evaluate_to(False))
    kinds = {"t": T}

    async def insert_and_run(parent, index, raws):     # the tool entry's flow
        async with f.lock:
            nodes = await edit.insert(parent,index, raws, kinds)
            return nodes, await f._run(M.Evaluation(nodes[-1], False), M.Evaluating())

    (new,), r = run(insert_and_run(sec, 1, [{"kind": "t", "name": "N"}]))
    assert r == M.EvaluationResult(None, INVALIDATING)
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
    run(t4.evaluate_to(False))
    assert sec.is_finished() and not thy.is_finished()   # the theory's ending has not run
    run(thy.evaluate_to(False))
    assert thy.is_finished() and f.is_finished()
    t2._owes_nothing = lambda: False             # one leaf still owing something
    assert t1.is_finished() and not t2.is_finished()
    assert not sec.is_finished() and not thy.is_finished() and not f.is_finished()
    assert t3.is_finished()                      # the debt does not spread sideways


def test_failed_ending_is_a_stop():
    f, thy, sec, t1, t2, t3, t4 = build(Section="end")
    r = run(t4.evaluate_to(False))
    assert r.stopped_at is sec and st(sec) == (READY, CannotEvaluate(None))
    assert st(t3) == CannotEvaluate(sec)
    r = run(t4.evaluate_to(False))
    assert r.stopped_at is sec and sec.end_runs == 1


# --- persistence (the plan's §2) ---------------------------------------------

def shape(forest):
    """What a round trip must preserve, node by node in tree order."""
    return [(n.identity, n.kind, n.name, n.fail if isinstance(n, T)
             else (n.fail_beginning, n.fail_ending),
             len(n.sub_nodes) if isinstance(n, M.NonLeaf_Node) else None)
            for n in forest._all_nodes()]


def test_reopen_restores_the_forest_not_evaluated(tmp_path):
    path = tmp_path / "theory_forest.sqlite"
    store = Forest_Store(path)
    f = OneTreeForest(CONN, store)
    (thy,) = run(locked(f, edit.insert(f,0, [
        {"kind": "block", "name": "Theory", "children": [
            {"kind": "block", "name": "Section", "children": [
                {"kind": "t", "name": "T1", "fail": True},
                {"kind": "t", "name": "T2"}]},
            {"kind": "t", "name": "T3"}]}], KINDS)))
    t3 = thy.sub_nodes[1]
    run(t3.evaluate_to(True))
    assert st(t3) is READY
    slots_before = {s.name for n in f._all_nodes() for s in n._states_inside()}
    store.close()

    f2 = OneTreeForest(CONN, Forest_Store(path))
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
    r = run(thy2.sub_nodes[1].evaluate_to(True))
    assert r == M.EvaluationResult(None, INVALIDATING)
    assert st(thy2) == (READY, NOT_EVALUATED) and st(thy2.sub_nodes[0]) == (READY, READY)
    assert st(thy2.sub_nodes[0].sub_nodes[0]) == CannotEvaluate(None)   # T1 still fails
    assert_invariants(f2, TABLE)
    # a fresh identity after the reopen collides with no loaded one
    (new,) = run(locked(f2, edit.insert(thy2,0, [{"kind": "t", "name": "N"}], KINDS)))
    assert new.identity not in {i for i, *_ in shape(f)}


def test_a_fresh_database_is_an_empty_forest():
    f = OneTreeForest(CONN)
    assert f.sub_nodes == [] and f.store.nodes() == []


def test_the_trees_keep_their_order_across_a_reopen(tmp_path):
    path = tmp_path / "theory_forest.sqlite"
    f = OneTreeForest(CONN, Forest_Store(path))
    a, b = run(locked(f, edit.insert(f,0, [
        {"kind": "block", "name": "A", "children": [{"kind": "t", "name": "x"}]},
        {"kind": "block", "name": "B"}], KINDS)))
    run(locked(f, edit.move(a, f, 1)))                      # -> [B, A]
    assert f.sub_nodes == [b, a]
    assert set(f.store.fields(f.identity)) == {"children"}       # the root's one row
    f.store.close()
    f2 = OneTreeForest(CONN, Forest_Store(path))
    assert shape(f2) == shape(f)
    assert [t.name for t in f2.sub_nodes] == ["B", "A"]


def test_delete_and_amend_at_the_root_reach_the_store(tmp_path):
    path = tmp_path / "theory_forest.sqlite"
    f = OneTreeForest(CONN, Forest_Store(path))
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
    f2 = OneTreeForest(CONN, Forest_Store(path))
    assert shape(f2) == shape(f)
    assert [t.name for t in f2.sub_nodes] == ["A2"]
    assert [c.name for c in f2.sub_nodes[0].sub_nodes] == ["x"]


def test_the_loader_places_the_node_whatever_from_store_passed():
    class Careless(T):
        @classmethod
        def from_store(cls, config, rows):
            return cls(None, config.state, rows.get("name"), rows.get("fail"))
    store = Forest_Store(":memory:")
    f = OneTreeForest(CONN, store)
    run(locked(f, edit.insert(f,0, [
        {"kind": "block", "name": "B", "children": [{"kind": "t", "name": "a"}]}], KINDS)))
    f2 = OneTreeForest(CONN, store, kinds={"block": Block, "t": Careless})
    a = f2.sub_nodes[0].sub_nodes[0]
    assert isinstance(a, Careless) and a.parent is f2.sub_nodes[0]
    assert f2.id_of(a) == "B.a"


class Bare(M.Leaf):                 # a class that wrote neither persistence method
    argument_schema = T_RawAST
    @classmethod
    async def gen(cls, config, raw):
        n = cls(config.parent, config.state); n.name = raw["name"]; return n
    async def _eval_opr(self): return True

class WriteOnly(Bare):              # ... and one that wrote only to_store
    def to_store(self, rows): rows.put("name", self.name)


def test_a_store_failure_after_the_commit_is_a_disaster(tmp_path):
    """The transaction opens after the in-memory commit, so its failure
    parts memory from the database: `TAT_DisasterError`, from the cause;
    the database keeps the last committed forest (EXCEPTIONS.md §1)."""
    class Broken(T):
        def to_store(self, rows):
            raise ZeroDivisionError("to_store broke")
    path = tmp_path / "theory_forest.sqlite"
    f = OneTreeForest(CONN, Forest_Store(path))
    (thy,) = run(locked(f, edit.insert(f,0, [{"kind": "block", "name": "Theory"}], KINDS)))
    with pytest.raises(TAT_DisasterError, match="to_store broke") as e:
        run(locked(f, edit.insert(thy,0, [{"kind": "b", "name": "x"}], {"b": Broken})))
    assert isinstance(e.value.__cause__, ZeroDivisionError)
    assert [n.name for n in thy.sub_nodes] == ["x"]          # memory kept the change
    f.store.close()
    f2 = OneTreeForest(CONN, Forest_Store(path))              # the database did not
    assert [t.name for t in f2.sub_nodes] == ["Theory"] and f2.sub_nodes[0].sub_nodes == []


def test_a_class_without_to_store_fails_at_its_first_edit():
    f = OneTreeForest(CONN)
    # inside the store transaction, so a disaster whose cause is the class's bug
    with pytest.raises(TAT_DisasterError, match="Bare has no to_store") as e:
        run(locked(f, edit.insert(f,0, [{"kind": "bare", "name": "x"}], {"bare": Bare})))
    assert isinstance(e.value.__cause__, TAT_InternalError)


def test_a_class_without_from_store_fails_at_the_reopen():
    store = Forest_Store(":memory:")
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
    store = Forest_Store(":memory:")
    f = OneTreeForest(CONN, store)
    (x,) = run(locked(f, edit.insert(f,0, [{"kind": "t", "name": "x"}], KINDS)))
    with pytest.raises(TAT_StartupError, match=f"`colour` for node {x.identity}"):
        OneTreeForest(CONN, store, kinds={"t": Wants_More})


@pytest.mark.parametrize("blob", [b"\xc1\xc1\xc1",       # not MessagePack at all
                                  b"\x81\x90\x54"])      # a map keyed by a list
def test_a_corrupt_field_value_is_a_startup_error(blob):
    store = Forest_Store(":memory:")
    f = OneTreeForest(CONN, store)
    (x,) = run(locked(f, edit.insert(f,0, [{"kind": "t", "name": "x"}], KINDS)))
    store._conn.execute("UPDATE fields SET value = ? WHERE node = ? AND field = 'name'",
                        (blob, x.identity))
    with pytest.raises(TAT_StartupError, match=f"`name` of node {x.identity} is not readable"):
        OneTreeForest(CONN, store)


def test_a_kind_that_is_not_a_string_is_a_startup_error():
    store = Forest_Store(":memory:")
    f = OneTreeForest(CONN, store)
    (x,) = run(locked(f, edit.insert(f,0, [{"kind": "t", "name": "x"}], KINDS)))
    with store.transaction():
        store.put(x.identity, "kind", [1])
    with pytest.raises(TAT_StartupError, match="kind `\\[1\\]`"):
        OneTreeForest(CONN, store)


def _damaged(children_of, value):
    """A one-tree store whose `children` row of `children_of` ("root" or
    "block") is overwritten with `value`."""
    store = Forest_Store(":memory:")
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
    store = Forest_Store(":memory:")
    f = OneTreeForest(CONN, store)
    run(locked(f, edit.insert(f,0, [{"kind": "t", "name": "x"}], KINDS)))
    with store.transaction():
        store.delete_node(f.identity)
    with pytest.raises(TAT_StartupError, match="`children` for node 0"):
        OneTreeForest(CONN, store)


def test_a_kind_without_a_class_is_a_startup_error():
    store = Forest_Store(":memory:")
    f = OneTreeForest(CONN, store)
    run(locked(f, edit.insert(f,0, [{"kind": "t", "name": "x"}], KINDS)))
    with pytest.raises(TAT_StartupError, match="kind `t`"):
        OneTreeForest(CONN, store, kinds={"block": Block})


def test_a_missing_row_is_a_startup_error():
    store = Forest_Store(":memory:")
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
    store = Forest_Store(":memory:")
    f = OneTreeForest(CONN, store)
    run(locked(f, edit.insert(f,0, [{"kind": "block", "name": "B"}], KINDS)))
    with pytest.raises(TAT_InternalError, match="returned children"):
        OneTreeForest(CONN, store, kinds={"block": Greedy, "t": T})


