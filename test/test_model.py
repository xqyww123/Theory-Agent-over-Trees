"""The recursion of `model.py` on `Theory > [Section > [T1, T2], T3, T4]`,
against a fake state slot table.  Run: python -m pytest test/test_model.py
"""

import asyncio
import sys
import types
import typing

try:
    import Isabelle_RPC_Host  # noqa: F401
except ImportError:                       # the test needs no Isabelle
    m = types.ModuleType("Isabelle_RPC_Host")
    m.Connection = object  # type: ignore[attr-defined]
    sys.modules["Isabelle_RPC_Host"] = m

import pytest

from isabelle_theory_agent import isabelle_driver, model as M
from isabelle_theory_agent.model import (
    NOT_EVALUATED, READY, INVALIDATING, CannotEvaluate, Isar_State_Slot)


# --- a fake state slot table ------------------------------------------------

class Table:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.deleted: list[str] = []

    def install(self, monkeypatch):
        async def state_delete(conn, names):
            for n in names:
                self.values.pop(n, None); self.deleted.append(n)
        async def state_exists(conn, name):
            return name in self.values
        async def state_copy(conn, src, dst):
            if src in self.values: self.values[dst] = self.values[src]
            else: self.values.pop(dst, None)
        for f in (state_delete, state_exists, state_copy):
            monkeypatch.setattr(isabelle_driver, f.__name__, f)


# --- concrete node classes ------------------------------------------------------

class T(M.Leaf):                    # a leaf whose operation succeeds unless told to fail
    def __init__(self, parent, state, name, fail=False):
        super().__init__(parent, state)
        self.name, self.fail, self.runs = name, fail, 0
    def is_finished(self): return self._status is READY
    async def _eval_opr(self):
        self.runs += 1
        if self.fail: return False
        TABLE.values[self.resulting_state().name] = f"after {self.name}"
        return True
    def __repr__(self): return self.name


class Block(M.StdBlock):
    def __init__(self, parent, state, name, sbe, fail_beginning=False, fail_ending=False):
        super().__init__(parent, state, [], sbe)
        self.name, self.fail_beginning, self.fail_ending = name, fail_beginning, fail_ending
        self.begin_runs = self.end_runs = 0
    def is_finished(self):
        return (self.evaluation_status_ending is READY and self.evaluation_status_beginning is READY
                and all(c.is_finished() for c in self.sub_nodes))
    async def _eval_beginning_opr(self):
        self.begin_runs += 1
        if self.fail_beginning: return False
        TABLE.values[self._state_after_beginning().name] = f"begin {self.name}"
        return True
    async def _eval_ending_opr(self):
        self.end_runs += 1
        if self.fail_ending: return False
        TABLE.values[self.resulting_state().name] = f"end {self.name}"
        return True
    def __repr__(self): return self.name


class OneTreeForest(M.Forest):      # enough of `Forest` to drive one tree
    def __init__(self, conn):
        super().__init__(Isar_State_Slot.assign(conn), [])
        self._end = Isar_State_Slot.assign(conn)
    def _resulting_state_of_all_children(self): return self._end
    async def _evaluate(self, ev, mode): return await self._evaluate_children(ev, mode)


TABLE = Table()
CONN = typing.cast(typing.Any, object())     # stands in for a Connection


def slot(): return Isar_State_Slot.assign(CONN)


def build(**flags):
    """Theory > [Section > [T1, T2], T3, T4]; flags name a node and a failure."""
    f = OneTreeForest(CONN)
    thy = Block(f, slot(), "Theory", slot()); f.sub_nodes.append(thy)
    sec = Block(thy, slot(), "Section", slot(), fail_beginning=flags.get("Section") == "begin",
                fail_ending=flags.get("Section") == "end")
    t1 = T(sec, slot(), "T1", fail=flags.get("T1", False))
    t2 = T(sec, slot(), "T2", fail=flags.get("T2", False))
    sec.sub_nodes += [t1, t2]
    t3 = T(thy, slot(), "T3", fail=flags.get("T3", False))
    t4 = T(thy, slot(), "T4", fail=flags.get("T4", False))
    thy.sub_nodes += [sec, t3, t4]
    return f, thy, sec, t1, t2, t3, t4


def st(n):
    if isinstance(n, M.StdBlock):
        return (n.evaluation_status_beginning, n.evaluation_status_ending)
    return n._status


def run(coro): return asyncio.run(coro)


@pytest.fixture(autouse=True)
def table(monkeypatch):
    TABLE.values.clear(); TABLE.deleted.clear()
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
    run(sec._delete_child(t2))
    assert sec.sub_nodes == [t1] and st(t1) is READY
    assert st(sec) == (READY, NOT_EVALUATED) and st(t3) is NOT_EVALUATED
    assert TABLE.values[t1.resulting_state().name] == "after T1"        # the value moved with the position


def test_insert_into_evaluated_tree():
    f, thy, sec, t1, t2, t3, t4 = build()
    run(t4.evaluate_to(False))
    new = T(None, slot(), "N")
    r = run(sec._insert_child(1, new, False, True))
    assert r == M.EvaluationResult(None, INVALIDATING)
    assert new.runs == 1 and st(new) is READY and sec.sub_nodes == [t1, new, t2]
    assert st(t2) is NOT_EVALUATED and st(t3) is NOT_EVALUATED
    assert st(sec) == (READY, NOT_EVALUATED) and st(thy) == (READY, NOT_EVALUATED)
    assert t1.runs == 1                                                  # the predecessor untouched


def test_failed_ending_is_a_stop():
    f, thy, sec, t1, t2, t3, t4 = build(Section="end")
    r = run(t4.evaluate_to(False))
    assert r.stopped_at is sec and st(sec) == (READY, CannotEvaluate(None))
    assert st(t3) == CannotEvaluate(sec)
    r = run(t4.evaluate_to(False))
    assert r.stopped_at is sec and sec.end_runs == 1


def test_pickle_resets_status():
    import pickle
    f, thy, sec, t1, t2, t3, t4 = build(T1=True)
    run(t4.evaluate_to(True))
    thy2 = pickle.loads(pickle.dumps(thy))
    t1b = thy2.sub_nodes[0].sub_nodes[0]
    assert t1b._status is NOT_EVALUATED and st(thy2) == (NOT_EVALUATED, NOT_EVALUATED)
    assert t1b.state.name is None
