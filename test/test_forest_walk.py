"""The forest walk (ARCHITECTURE §3.5; ai-artifacts/FOREST_WALK_PLAN.md
§3–§6) on `test_session_theory.py`'s fakes over the real `Forest`: the
import graph, imports run before their importer, the order constraint,
the stop crossing an import dependency, the per-tree flush, the `Theory`
ending's rule and the record every edit compares, and the whole-node
invalidation.  Every fake records the order it ran in.
Run: python -m pytest test/test_forest_walk.py
"""

import pytest

import test_model as tm
import test_session_theory as ts
from baselines import DOCS, fenced_lines
from invariants import assert_invariants, assert_store_mirrors
from test_model import locked, run, st

import isabelle_theory_agent.model as M
from isabelle_theory_agent import edit
from isabelle_theory_agent.model import (
    BRIEFING, INVALIDATING, NOT_EVALUATED, EvaluationResult, Session)
from test_model import CANNOT_EVALUATE, READY

table = ts.table                     # the fake state slot table and the fake wire, per test

RUNS: list[str] = []                 # every operation the fakes ran, in order
EVENTS: list[tuple] = []             # every `on_invalidated`


@pytest.fixture(autouse=True)
def records():
    RUNS.clear()
    EVENTS.clear()


class Recording:
    async def _eval_beginning_opr(self):
        RUNS.append(f"begin {self.name}")
        return await super()._eval_beginning_opr()

    async def _eval_ending_opr(self):
        RUNS.append(f"end {self.name}")
        return await super()._eval_ending_opr()

    def on_invalidated(self, operation):
        EVENTS.append((self.name, operation))


class Good(Recording, ts.Fake_Theory): ...
class Bad_Header(Recording, ts.Failing_Header_Theory): ...
class Bad_End(Recording, ts.Failing_End_Theory): ...

class Rt(tm.T):
    async def _eval_opr(self):
        RUNS.append(self.name)
        return await super()._eval_opr()


KINDS = {"session": Session, "theory": Good, "bad_header": Bad_Header, "bad_end": Bad_End,
         "t": Rt}

theory, session = ts.theory, ts.session


def t(name, fail=False):
    return {"kind": "t", "name": name, "fail": fail}


def forest(*sessions):
    f = ts.Forest_Under_Test(kinds=KINDS)
    insert(f, f, 0, list(sessions))
    return f


def insert(f, parent, index, raws):
    return run(locked(f, edit.insert(parent, index, raws, KINDS)))


def inv(f):
    assert_invariants(f, tm.TABLE)
    assert_store_mirrors(f, KINDS, shape=ts.shape)


def deletes():
    return [set(c[1]) for c in tm.TABLE.calls if c[0] == "delete"]


def mark(n):
    return n.mark(BRIEFING, 0)


NE = (NOT_EVALUATED, NOT_EVALUATED)                  # a Theory node's two statuses


def not_evaluated(*trees):
    """Every node `not_evaluated`, the owned resulting slot released."""
    for tree in trees:
        for n in tree._tree_order():
            assert st(n) in (NOT_EVALUATED, NE), (tree, n)
        assert tree._state_after_ending.name not in tm.TABLE.values, tree


# --- the graph, and imports before their importer ----------------------------

def test_an_importer_runs_its_imports_first():
    f = forest(session("S", theory("A"), theory("B", "A")),
               session("U", theory("C", "S.B", "Main")))
    s, u = f.sub_nodes
    a, b = s.sub_nodes
    (c,) = u.sub_nodes
    # bare within a Session, dotted from another; an external name creates
    # no dependency
    assert (f._resolved_imports(a), f._resolved_imports(b), f._resolved_imports(c)) == \
        ([], [a], [b])
    assert (f._importers(a), f._importers(b), f._importers(c)) == ([b], [c], [])
    assert f._closure([c]) == [a, b, c]
    assert c.header() == 'theory C\n  imports "S.B" "Main"\nbegin'          # every item quoted
    r = run(c.evaluate_to(False))
    assert r == EvaluationResult(None, INVALIDATING)
    assert RUNS == ["begin A", "end A", "begin B", "end B", "begin C", "end C"]
    assert f.is_finished()
    inv(f)
    # a bare cross-session name creates no dependency: `A` written in U asks
    # for U.A (the plan's §1 item 4)
    (d,) = insert(f, u, 1, [theory("D", "A")])
    assert f._resolved_imports(d) == [] and f._importers(a) == [b]
    RUNS.clear()
    run(d.evaluate_to(False))
    assert RUNS == ["begin D", "end D"]
    inv(f)


def test_a_session_and_the_root_as_destination():
    f = forest(session("S", theory("A"), theory("B", "A")),
               session("U", theory("C", "S.A"), theory("D")),
               session("V", theory("E")))
    s, u, v = f.sub_nodes
    a, b = s.sub_nodes
    (e,) = v.sub_nodes
    run(e.evaluate_to(False))
    RUNS.clear()
    # every tree under the Session to its end, an import outside it first;
    # a tree no target imports is not touched, evaluated or not
    assert run(u.evaluate_to(False)) == EvaluationResult(None, INVALIDATING)
    assert RUNS == ["begin A", "end A", "begin C", "end C", "begin D", "end D"]
    assert u.is_finished() and st(b) == (NOT_EVALUATED, NOT_EVALUATED)
    assert st(e) == (READY, READY)
    inv(f)
    # the root: every tree, the ready ones not rerun
    RUNS.clear()
    assert run(f.evaluate_to(False)) == EvaluationResult(None, INVALIDATING)
    assert RUNS == ["begin B", "end B"] and f.is_finished()
    inv(f)


# --- the order constraint ----------------------------------------------------

def test_the_order_constraint():
    f = forest(session("S", theory("B", "S.C"), theory("C")))
    (s,) = f.sub_nodes
    b, c = s.sub_nodes
    (x,) = insert(f, b, 0, [t("x")])
    r = run(b.evaluate_to(False))
    # the importer placed before its import is `not_evaluated` throughout
    # and the stop; the import itself runs
    assert r.stopped_at is b and RUNS == ["begin C", "end C"]
    not_evaluated(b)
    assert st(c) == (READY, READY)
    assert f._order_violation(b) == "S.C" and f._order_violation(c) is None
    # the sentence the renderer composes from the answer, RENDER_BASELINES
    # §3's line verbatim
    item = f._order_violation(b)
    composed = (f"Since `{f.id_of(b)}` imports `{item}`, you cannot put it before `{item}`."
                " Move it later.")
    assert composed == fenced_lines(DOCS / "RENDER_BASELINES.md", "3.")[0]
    inv(f)
    # `None` on the leaf a case-3 stop reports
    (y,) = insert(f, c, 0, [t("y", fail=True)])
    r = run(c.evaluate_to(False))
    assert r.stopped_at is y and f._order_violation(y) is None
    # the repairing move: the same call runs the tree
    run(locked(f, edit.move(b, s, 1)))
    RUNS.clear()
    assert f._order_violation(b) is None
    r = run(b.evaluate_to(True))
    assert r == EvaluationResult(None, INVALIDATING)
    assert RUNS == ["end C", "begin B", "x", "end B"] and b.is_finished()
    inv(f)


def test_the_order_constraint_answers_the_offending_item_written_first():
    f = forest(session("S", theory("A"), theory("B", "A", "S.D", "S.C"), theory("C"), theory("D")))
    assert f._order_violation(f.sub_nodes[0].sub_nodes[1]) == "S.D"


def test_a_reorder_into_a_violation_invalidates_the_tree_at_the_next_walk():
    f = forest(session("S", theory("C"), theory("B", "S.C"), theory("D", "B")))
    (s,) = f.sub_nodes
    c, b, d = s.sub_nodes
    (x,) = insert(f, b, 0, [t("x")])
    run(d.evaluate_to(False))
    assert f.is_finished()
    # the reorder itself invalidates nothing; the next walk finds the
    # violation and invalidates the ready tree whole, its importer blocked
    run(locked(f, edit.move(b, s, 0)))
    assert f.is_finished() and f._order_violation(b) == "S.C"
    assert tm.TABLE.theory_deletes == []
    RUNS.clear()
    r = run(d.evaluate_to(False))
    assert r.stopped_at is b and RUNS == []
    not_evaluated(b, d)                                          # d blocked: not run, not evaluated
    assert st(c) == (READY, READY)
    inv(f)


def test_a_cycle_is_the_earlier_trees_stop():
    f = forest(session("S", theory("A", "B"), theory("B", "A")))
    (s,) = f.sub_nodes
    a, b = s.sub_nodes
    (x,) = insert(f, b, 0, [t("x")])
    # every reading terminates
    assert f._closure([a]) == [a, b] and f._importers(a) == [b] and f._importers(b) == [a]
    r = run(b.evaluate_to(False))
    assert r.stopped_at is a and RUNS == []
    not_evaluated(a)
    # the later tree is not run: blocked, `not_evaluated` throughout, while
    # the result names the earlier tree's `Theory` node
    not_evaluated(b)
    assert mark(b) == mark(x) == "not evaluated"
    inv(f)


def test_a_self_import_is_a_stop():
    f = forest(session("S", theory("A", "A")))
    (a,) = f.sub_nodes[0].sub_nodes
    assert f._resolved_imports(a) == [a] and f._importers(a) == [a] and f._closure([a]) == [a]
    r = run(a.evaluate_to(False))
    assert r.stopped_at is a and RUNS == [] and f._order_violation(a) == "A"
    not_evaluated(a)
    inv(f)


# --- the stop crossing an import dependency ----------------------------------

def test_blocked_by_a_failed_header():
    f = forest(session("S", theory("A", kind="bad_header"), theory("B", "A")))
    a, b = f.sub_nodes[0].sub_nodes
    r = run(b.evaluate_to(False))
    assert RUNS == ["begin A"]                                   # no stop of A's own
    assert isinstance(st(a)[0], M.CannotEvaluate) and st(a)[1] is READY
    assert st(b) == NE and r.stopped_at is a                     # the import's Theory node
    assert mark(a) == "failed" and mark(b) == "not evaluated"
    inv(f)


def test_blocked_by_a_failed_end():
    f = forest(session("S", theory("A", kind="bad_end"), theory("B", "A")))
    a, b = f.sub_nodes[0].sub_nodes
    r = run(b.evaluate_to(False))
    assert RUNS == ["begin A", "end A"]
    assert st(a)[0] is READY and isinstance(st(a)[1], M.CannotEvaluate) and st(b) == NE
    assert r.stopped_at is a                                     # the import's own stop, once
    inv(f)


def test_blocked_by_a_leaf_inside_the_import():
    f = forest(session("S", theory("A"), theory("B", "A"), theory("C", "B")))
    a, b, c = f.sub_nodes[0].sub_nodes
    (x,) = insert(f, a, 0, [t("x", fail=True)])
    r = run(c.evaluate_to(False))
    assert r.stopped_at is x and RUNS == ["begin A", "x"]        # the leaf, reported once
    assert st(a) == (READY, NOT_EVALUATED)
    # the importer, and a third tree importing it, are blocked: not run
    not_evaluated(b, c)
    assert mark(b) == mark(c) == "not evaluated"
    inv(f)


def test_blocked_by_the_obstacle_of_the_item_written_first():
    f = forest(session("S", theory("A", kind="bad_header"), theory("B", kind="bad_header"),
                       theory("C", "B", "A")))
    a, b, c = f.sub_nodes[0].sub_nodes
    r = run(c.evaluate_to(False))
    assert r.stopped_at is b and st(c) == NE and a is not b
    inv(f)


def test_ignore_error_passes_a_leafs_stop_but_not_a_missing_theory_value():
    f = forest(session("S", theory("A"), theory("B", "A")))
    a, b = f.sub_nodes[0].sub_nodes
    x, y = insert(f, a, 0, [t("x", fail=True), t("y")])
    # the leaf's own stop is carried past: the import's `end` runs and the
    # importer runs after it
    r = run(b.evaluate_to(True))
    assert r == EvaluationResult(None, INVALIDATING)
    assert RUNS == ["begin A", "x", "y", "end A", "begin B", "end B"]
    assert st(x) is CANNOT_EVALUATE and b.is_finished()
    inv(f)
    # a failed header and a failed `end` still block the importer, which
    # is not run, while the result reports nothing
    for kind in ("bad_header", "bad_end"):
        tm.TABLE.clear()
        f = forest(session("S", theory("A", kind=kind), theory("B", "A")))
        a, b = f.sub_nodes[0].sub_nodes
        (z,) = insert(f, b, 0, [t("z")])
        RUNS.clear()
        r = run(b.evaluate_to(True))
        assert r == EvaluationResult(None, INVALIDATING), kind
        assert "begin B" not in RUNS
        not_evaluated(b)
        inv(f)
    # the order constraint's stop is reported under the flag
    f = forest(session("S", theory("B", "S.C"), theory("C")))
    b, c = f.sub_nodes[0].sub_nodes
    assert run(b.evaluate_to(True)).stopped_at is b
    inv(f)


def test_a_destination_inside_a_blocked_tree():
    f = forest(session("S", theory("A", kind="bad_header"), theory("B", "A")))
    a, b = f.sub_nodes[0].sub_nodes
    p, q = insert(f, b, 0, [t("p"), t("q")])
    r = run(p.evaluate_to(False))
    assert r.stopped_at is a and "begin B" not in RUNS
    not_evaluated(b)
    inv(f)


def test_the_first_stop_in_tree_order_is_reported():
    f = forest(session("S", theory("A"), theory("B")))
    a, b = f.sub_nodes[0].sub_nodes
    (x,) = insert(f, a, 0, [t("x", fail=True)])
    (y,) = insert(f, b, 0, [t("y", fail=True)])
    r = run(f.evaluate_to(False))
    assert r.stopped_at is x and RUNS == ["begin A", "x", "begin B", "y"]
    inv(f)


def test_each_tree_flushes_what_its_walk_released():
    f = forest(session("S", theory("A"), theory("B")))
    a, b = f.sub_nodes[0].sub_nodes
    x, x2 = insert(f, a, 0, [t("x", fail=True), t("x2")])
    y, y2 = insert(f, b, 0, [t("y", fail=True), t("y2")])
    run(f.evaluate_to(True))                                     # both trees written whole
    assert a.evaluation_status_ending is READY and b.evaluation_status_ending is READY
    inv(f)
    tm.TABLE.calls.clear()
    r = run(f.evaluate_to(False))                                # each own stop releases its tree's
    assert r.stopped_at is x
    released = deletes()
    assert len(released) == 2 and released[0] and released[1], released
    assert released[0].isdisjoint(released[1])
    assert released[0] == {x2.resulting_state().name, a._state_after_ending.name}
    assert released[1] == {y2.resulting_state().name, b._state_after_ending.name}
    inv(f)


# --- the Theory ending's rule (the plan's §4.1) -------------------------------

def chain():
    """S: A > [x], B imports A, C imports B; C evaluated."""
    f = forest(session("S", theory("A"), theory("B", "A"), theory("C", "B")))
    a, b, c = f.sub_nodes[0].sub_nodes
    (x,) = insert(f, a, 0, [t("x")])
    run(c.evaluate_to(False))
    assert f.is_finished()
    RUNS.clear()
    EVENTS.clear()
    return f, a, b, c, x


def test_an_edit_inside_an_import_invalidates_its_importers_whole():
    f, a, b, c, x = chain()
    (y,) = insert(f, a, 1, [t("y")])
    not_evaluated(b, c)
    assert st(a) == (READY, NOT_EVALUATED) and st(x) is READY
    assert {("A", "ending"), ("B", "ending"), ("C", "ending")} <= set(EVENTS)
    inv(f)
    run(c.evaluate_to(False))
    assert RUNS == ["y", "end A", "begin B", "end B", "begin C", "end C"]
    inv(f)


def test_evaluate_to_inside_an_import_invalidates_its_importers_whole():
    f, a, b, c, x = chain()
    run(x.evaluate_to(False))
    assert RUNS == [] and st(a) == (READY, NOT_EVALUATED)
    not_evaluated(b, c)
    assert ("C", "ending") in EVENTS
    inv(f)


def test_an_ending_leaving_ready_for_a_stop_invalidates_its_importers():
    f = forest(session("S", theory("A"), theory("B", "A"), theory("C", "B")))
    a, b, c = f.sub_nodes[0].sub_nodes
    (x,) = insert(f, a, 0, [t("x", fail=True)])
    (z,) = insert(f, c, 0, [t("z", fail=True)])
    run(c.evaluate_to(True))                                     # every ending ready, past the own stops
    assert b.is_finished() and st(c) == (READY, READY) and st(z) is CANNOT_EVALUATE
    EVENTS.clear()
    r = run(a.evaluate_to(False))                                # A's ending: ready -> not evaluated
    assert r.stopped_at is x and st(a) == (READY, NOT_EVALUATED)
    not_evaluated(b, c)                                          # both outside the walk; C's own stop reset
    assert {("B", "ending"), ("C", "ending")} <= set(EVENTS)
    inv(f)


def test_a_tree_moved_onto_its_own_dotted_import():
    f = forest(session("S", theory("A")), session("U", theory("B", "S.B")))
    s, u = f.sub_nodes
    (b,) = u.sub_nodes
    run(b.evaluate_to(False))
    assert b.is_finished() and f._resolved_imports(b) == []
    run(locked(f, edit.move(b, s, 0)))
    assert f._resolved_imports(b) == [b] and f._importers(b) == [b]
    not_evaluated(b)
    assert tm.TABLE.theory_deletes == [("U.B",)]
    inv(f)


# --- the record every edit compares (the plan's §4.2) ------------------------

def two_sessions():
    """S: A, B imports A; U: C imports S.A; all evaluated."""
    f = forest(session("S", theory("A"), theory("B", "A")), session("U", theory("C", "S.A")))
    s, u = f.sub_nodes
    a, b = s.sub_nodes
    (c,) = u.sub_nodes
    run(f.evaluate_to(False))
    assert f.is_finished() and tm.TABLE.theories == {"S.A", "S.B", "U.C"}
    return f, s, u, a, b, c


def test_renaming_a_tree():
    f, s, u, a, b, c = two_sessions()
    (a2,) = run(locked(f, edit.amend(a, [theory("A2")], KINDS)))
    not_evaluated(a2, b, c)
    assert tm.TABLE.theory_deletes == [("S.A",)] and tm.TABLE.theories == {"S.B", "U.C"}
    inv(f)


def test_the_record_holds_the_imported_nodes_not_their_names():
    # the one edit that tells the nodes from their names: A renamed and a
    # fresh tree named A in the same call — every name stays, the tree
    # behind `A` does not
    f, s, u, a, b, c = two_sessions()
    a2, a_new = run(locked(f, edit.amend(a, [theory("A2"), theory("A")], KINDS)))
    assert f._resolved_imports(b) == [a_new] and f._resolved_imports(c) == [a_new]
    not_evaluated(a2, a_new, b, c)
    assert tm.TABLE.theory_deletes == []
    inv(f)


def test_renaming_a_session():
    f, s, u, a, b, c = two_sessions()
    run(locked(f, edit.amend(s, [session("S2")], KINDS)))
    not_evaluated(a, b, c)
    assert tm.TABLE.theory_deletes == [("S.A", "S.B")] and tm.TABLE.theories == {"U.C"}
    inv(f)


def test_moving_a_tree_into_another_session():
    f, s, u, a, b, c = two_sessions()
    run(locked(f, edit.move(a, u, 0)))
    not_evaluated(a, b, c)
    assert tm.TABLE.theory_deletes == [("S.A",)]
    inv(f)


def test_deleting_a_tree():
    f, s, u, a, b, c = two_sessions()
    run(locked(f, edit.delete(a)))
    not_evaluated(b, c)
    assert tm.TABLE.theory_deletes == [("S.A",)] and tm.TABLE.theories == {"S.B", "U.C"}
    inv(f)


def test_amending_a_tree_invalidates_its_importers():
    for imports in (["Main"], ["A", "HOL.Rat"], ["A"]):        # a forest import, an external one, nothing
        tm.TABLE.clear()
        f, s, u, a, b, c = two_sessions()
        d, e = insert(f, s, 2, [theory("D", "B"), theory("E", "D")])
        run(e.evaluate_to(False))
        tm.TABLE.theory_deletes.clear()
        (b2,) = run(locked(f, edit.amend(b, [theory("B", *imports)], KINDS)))
        not_evaluated(b2, d, e)                                  # the importers, and theirs
        assert st(a) == (READY, READY) and st(c) == (READY, READY)
        assert tm.TABLE.theory_deletes == []
        f.render(f, BRIEFING)
        inv(f)
    # an amend of the obstacle itself: the importers, blocked by the
    # replaced node, run on the next call
    tm.TABLE.clear()
    f = forest(session("S", theory("A", kind="bad_header"), theory("B", "A"), theory("C", "B")))
    a, b, c = f.sub_nodes[0].sub_nodes
    run(c.evaluate_to(False))
    assert mark(a) == "failed" and st(b) == NE and st(c) == NE
    (a2,) = run(locked(f, edit.amend(a, [theory("A")], KINDS)))
    not_evaluated(a2, b, c)
    f.render(f, BRIEFING)
    inv(f)
    run(c.evaluate_to(False))
    assert f.is_finished()
    inv(f)
    # while the tree was blocked or `not_evaluated`
    tm.TABLE.clear()
    f = forest(session("S", theory("A"), theory("B", "A"), theory("C", "B")))
    a, b, c = f.sub_nodes[0].sub_nodes
    (x,) = insert(f, a, 0, [t("x", fail=True)])
    run(c.evaluate_to(False))
    assert st(x) is CANNOT_EVALUATE and st(c) == NE
    (b2,) = run(locked(f, edit.amend(b, [theory("B", "A")], KINDS)))
    not_evaluated(b2, c)
    assert tm.TABLE.theory_deletes == []
    inv(f)
    (b3,) = run(locked(f, edit.amend(b2, [theory("B", "A")], KINDS)))
    not_evaluated(b3, c)
    f.render(f, BRIEFING)
    inv(f)


def test_deleting_the_head_of_a_blocked_chain():
    f = forest(session("S", theory("A"), theory("B", "A"), theory("C", "B"), theory("D", "C")))
    a, b, c, d = f.sub_nodes[0].sub_nodes
    (x,) = insert(f, a, 0, [t("x", fail=True)])
    run(d.evaluate_to(False))
    assert st(x) is CANNOT_EVALUATE and st(d) == NE
    run(locked(f, edit.delete(a)))
    not_evaluated(b, c, d)
    assert tm.TABLE.theory_deletes == [("S.A",)]
    f.render(f, BRIEFING)
    inv(f)


def test_inserting_a_tree_an_import_already_names():
    f = forest(session("S", theory("B", "A")))
    (s,) = f.sub_nodes
    (b,) = s.sub_nodes
    run(b.evaluate_to(False))
    assert b.is_finished() and f._resolved_imports(b) == []
    (a,) = insert(f, s, 0, [theory("A")])
    assert f._resolved_imports(b) == [a]
    not_evaluated(b)
    assert tm.TABLE.theory_deletes == []
    inv(f)


def test_reorders_and_edits_inside_a_tree_change_no_record():
    f = forest(session("S", theory("A"), theory("B")), session("U", theory("C")))
    s, u = f.sub_nodes
    a, b = s.sub_nodes
    run(f.evaluate_to(False))
    run(locked(f, edit.move(b, s, 0)))                           # within a Session
    run(locked(f, edit.move(u, f, 0)))                           # of the Sessions
    assert f.is_finished() and tm.TABLE.theory_deletes == []
    inv(f)
    insert(f, a, 0, [t("x")])                                    # inside a tree
    assert tm.TABLE.theory_deletes == [] and st(b) == (READY, READY)
    inv(f)


# --- evaluate_to(evaluate=False) on a node nothing chains (the plan's §6) ---

def test_invalidating_a_session_whole():
    f = forest(session("S", theory("A"), theory("B")))
    (s,) = f.sub_nodes
    a, b = s.sub_nodes
    run(f.evaluate_to(False))
    assert f.is_finished()
    r = run(s.evaluate_to(False, evaluate=False))
    assert r == EvaluationResult(None, INVALIDATING)
    not_evaluated(a, b)
    inv(f)
