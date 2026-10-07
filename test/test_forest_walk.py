"""The forest walk (ARCHITECTURE §3.5; ai-artifacts/FOREST_WALK_PLAN.md
§3–§6) on `test_session_theory.py`'s fakes over the real `Forest`: the
import graph, imports run before their importer, the order constraint,
the stop crossing an import dependency, the per-tree flush, the `Theory`
ending's rule and the record every edit compares, and the whole-node
invalidation.  Every fake records the order it ran in.
Run: python -m pytest test/test_forest_walk.py
"""

import pytest

import stand_ins
import test_model as tm
import test_session_theory as ts
from baselines import DOCS, fenced_lines
from invariants import assert_invariants, assert_store_mirrors
from test_model import locked, run, st

import isabelle_theory_agent.model as M
from isabelle_theory_agent import edit, mcp, plugin
from isabelle_theory_agent.jobs import Agent
from isabelle_theory_agent.model import BRIEFING, NOT_EVALUATED, EvaluationResult, Session
from isabelle_theory_agent.store import Forest_Store
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
         "t": Rt, "block": tm.Block}

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
    r = run(c.evaluate_to(None, False))
    assert r == EvaluationResult(None, None)
    assert RUNS == ["begin A", "end A", "begin B", "end B", "begin C", "end C"]
    assert f.is_finished()
    inv(f)
    # a bare cross-session name creates no dependency: `A` written in U asks
    # for U.A (the plan's §1 item 4)
    (d,) = insert(f, u, 1, [theory("D", "A")])
    assert f._resolved_imports(d) == [] and f._importers(a) == [b]
    RUNS.clear()
    run(d.evaluate_to(None, False))
    assert RUNS == ["begin D", "end D"]
    inv(f)


def test_a_session_and_the_root_as_destination():
    f = forest(session("S", theory("A"), theory("B", "A")),
               session("U", theory("C", "S.A"), theory("D")),
               session("V", theory("E")))
    s, u, v = f.sub_nodes
    a, b = s.sub_nodes
    (e,) = v.sub_nodes
    run(e.evaluate_to(None, False))
    RUNS.clear()
    # every tree under the Session to its end, an import outside it first;
    # a tree no target imports is not touched, evaluated or not
    assert run(u.evaluate_to(None, False)) == EvaluationResult(None, None)
    assert RUNS == ["begin A", "end A", "begin C", "end C", "begin D", "end D"]
    assert u.is_finished() and st(b) == (NOT_EVALUATED, NOT_EVALUATED)
    assert st(e) == (READY, READY)
    inv(f)
    # the root: every tree, the ready ones not rerun
    RUNS.clear()
    assert run(f.evaluate_to(None, False)) == EvaluationResult(None, None)
    assert RUNS == ["begin B", "end B"] and f.is_finished()
    inv(f)


# --- the order constraint ----------------------------------------------------

def test_the_order_constraint():
    f = forest(session("S", theory("B", "S.C"), theory("C")))
    (s,) = f.sub_nodes
    b, c = s.sub_nodes
    (x,) = insert(f, b, 0, [t("x")])
    r = run(b.evaluate_to(None, False))
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
    r = run(c.evaluate_to(None, False))
    assert r.stopped_at is y and f._order_violation(y) is None
    # the repairing move: the same call runs the tree
    run(locked(f, edit.move(b, s, 1)))
    RUNS.clear()
    assert f._order_violation(b) is None
    r = run(b.evaluate_to(None, True))
    assert r == EvaluationResult(None, None)
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
    run(d.evaluate_to(None, False))
    assert f.is_finished()
    # the reorder itself invalidates nothing; the next walk finds the
    # violation and invalidates the ready tree whole, its importer blocked
    run(locked(f, edit.move(b, s, 0)))
    assert f.is_finished() and f._order_violation(b) == "S.C"
    assert tm.TABLE.theory_deletes == []
    RUNS.clear()
    r = run(d.evaluate_to(None, False))
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
    r = run(b.evaluate_to(None, False))
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
    r = run(a.evaluate_to(None, False))
    assert r.stopped_at is a and RUNS == [] and f._order_violation(a) == "A"
    not_evaluated(a)
    inv(f)
    # the sentence's variant for an item naming the tree itself, on the
    # document's own example: RENDER_BASELINES §3's second line verbatim
    f = forest(session("S", theory("B", "S.B")))
    (b,) = f.sub_nodes[0].sub_nodes
    item = f._order_violation(b)
    assert item == "S.B" and f._resolved_imports(b) == [b]   # what tells the renderer to use the variant
    composed = f"`{f.id_of(b)}` imports itself. Remove `{item}` from its imports."
    assert composed == fenced_lines(DOCS / "RENDER_BASELINES.md", "3.")[1]


# --- the stop crossing an import dependency ----------------------------------

def test_blocked_by_a_failed_header():
    f = forest(session("S", theory("A", kind="bad_header"), theory("B", "A")))
    a, b = f.sub_nodes[0].sub_nodes
    walk_start = len(stand_ins.records("evaluation"))
    r = run(b.evaluate_to(None, False))
    assert RUNS == ["begin A"]                                   # no stop of A's own
    assert isinstance(st(a)[0], M.CannotEvaluate) and st(a)[1] is READY
    assert st(b) == NE and r.stopped_at is a                     # the import's Theory node
    assert mark(a) == "failed" and mark(b) == "not evaluated"
    inv(f)
    # The walk's records (LOGGING.md §4): a run writes `operation` with its
    # messages, a write no run produced — the copy that stands in for a
    # failed beginning's ending — without them; the stop names the import
    # whose theory value is missing, and the tree it kept from running.
    records = stand_ins.records("evaluation")[walk_start:]
    id_a, id_b = f.full_id(a), f.full_id(b)
    assert records[0]["event"] == "walk_started" and records[0]["data"] == {
        "destination": id_b, "ignore_error": False, "checks": "no"}
    operations = {(r["data"]["node"], r["data"]["operation"]): r["data"]
                  for r in records if r["event"] == "operation"}
    begin_a = operations[id_a, "beginning"]
    assert begin_a["ran"] and begin_a["status"] == "cannot_evaluate" and "duration" in begin_a
    assert begin_a["messages"] == ["No such file: TAT_Nowhere.thy"]   # the fake header's failure
    end_a = operations[id_a, "ending"]
    assert not end_a["ran"] and end_a["status"] == "ready" and "messages" not in end_a
    [stop] = [r["data"] for r in records if r["event"] == "stopped"]
    assert stop == {"node": id_a, "reason": "import_without_theory", "tree": id_b}
    assert records[-1]["event"] == "walk_ended" and records[-1]["data"]["outcome"] == id_a
    assert records[-1]["data"]["slots_released"] == 0 and "duration" in records[-1]["data"]


def test_blocked_by_a_failed_end():
    f = forest(session("S", theory("A", kind="bad_end"), theory("B", "A")))
    a, b = f.sub_nodes[0].sub_nodes
    r = run(b.evaluate_to(None, False))
    assert RUNS == ["begin A", "end A"]
    assert st(a)[0] is READY and isinstance(st(a)[1], M.CannotEvaluate) and st(b) == NE
    assert r.stopped_at is a                                     # the import's stop, once
    inv(f)


def test_blocked_by_a_leaf_inside_the_import():
    f = forest(session("S", theory("A"), theory("B", "A"), theory("C", "B")))
    a, b, c = f.sub_nodes[0].sub_nodes
    (x,) = insert(f, a, 0, [t("x", fail=True)])
    r = run(c.evaluate_to(None, False))
    assert r.stopped_at is x and RUNS == ["begin A", "x"]        # the leaf, reported once
    assert st(a) == (READY, NOT_EVALUATED)
    # one `stopped` per tree that stopped (LOGGING.md §4): the leaf's own
    # stop; then, for each importer, the import with no theory value
    assert [r["data"] for r in stand_ins.records("evaluation") if r["event"] == "stopped"] == [
        {"node": f.full_id(x), "reason": "command_failed"},
        {"node": f.full_id(a), "reason": "import_without_theory", "tree": f.full_id(b)},
        {"node": f.full_id(b), "reason": "import_without_theory", "tree": f.full_id(c)}]
    # the importer, and a third tree importing it, are blocked: not run
    not_evaluated(b, c)
    assert mark(b) == mark(c) == "not evaluated"
    inv(f)


def test_two_importers_of_one_import_without_theory_each_name_their_tree():
    """Two trees importing one failed header (LOGGING.md §4): their
    `stopped` records name the same import, and each the tree it kept from
    running."""
    f = forest(session("S", theory("A", kind="bad_header"), theory("B", "A"), theory("C", "A")))
    a, b, c = f.sub_nodes[0].sub_nodes
    run(f.evaluate_to(None, False))
    assert [r["data"] for r in stand_ins.records("evaluation") if r["event"] == "stopped"] == [
        {"node": f.full_id(a), "reason": "import_without_theory", "tree": f.full_id(b)},
        {"node": f.full_id(a), "reason": "import_without_theory", "tree": f.full_id(c)}]
    not_evaluated(b, c)
    inv(f)


def test_blocked_by_the_obstacle_of_the_item_written_first():
    f = forest(session("S", theory("A", kind="bad_header"), theory("B", kind="bad_header"),
                       theory("C", "B", "A")))
    a, b, c = f.sub_nodes[0].sub_nodes
    r = run(c.evaluate_to(None, False))
    assert r.stopped_at is b and st(c) == NE and a is not b
    inv(f)


def test_ignore_error_passes_a_leafs_stop_but_not_a_missing_theory_value():
    f = forest(session("S", theory("A"), theory("B", "A")))
    a, b = f.sub_nodes[0].sub_nodes
    x, y = insert(f, a, 0, [t("x", fail=True), t("y")])
    # the leaf's stop is carried past: the import's `end` runs and the
    # importer runs after it
    r = run(b.evaluate_to(None, True))
    assert r == EvaluationResult(None, None)
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
        r = run(b.evaluate_to(None, True))
        assert r == EvaluationResult(None, None), kind
        assert "begin B" not in RUNS
        not_evaluated(b)
        inv(f)
    # the order constraint's stop is reported under the flag
    f = forest(session("S", theory("B", "S.C"), theory("C")))
    b, c = f.sub_nodes[0].sub_nodes
    assert run(b.evaluate_to(None, True)).stopped_at is b
    inv(f)


def test_a_destination_inside_a_blocked_tree():
    f = forest(session("S", theory("A", kind="bad_header"), theory("B", "A")))
    a, b = f.sub_nodes[0].sub_nodes
    p, q = insert(f, b, 0, [t("p"), t("q")])
    r = run(p.evaluate_to(None, False))
    assert r.stopped_at is a and "begin B" not in RUNS
    not_evaluated(b)
    inv(f)


def test_the_first_stop_in_tree_order_is_reported():
    f = forest(session("S", theory("A"), theory("B")))
    a, b = f.sub_nodes[0].sub_nodes
    (x,) = insert(f, a, 0, [t("x", fail=True)])
    (y,) = insert(f, b, 0, [t("y", fail=True)])
    r = run(f.evaluate_to(None, False))
    assert r.stopped_at is x and RUNS == ["begin A", "x", "begin B", "y"]
    inv(f)


def test_each_tree_flushes_what_its_walk_released():
    f = forest(session("S", theory("A"), theory("B")))
    a, b = f.sub_nodes[0].sub_nodes
    x, x2 = insert(f, a, 0, [t("x", fail=True), t("x2")])
    y, y2 = insert(f, b, 0, [t("y", fail=True), t("y2")])
    run(f.evaluate_to(None, True))                                     # both trees written whole
    assert a.evaluation_status_ending is READY and b.evaluation_status_ending is READY
    inv(f)
    tm.TABLE.calls.clear()
    r = run(f.evaluate_to(None, False))                                # each stop releases its tree's
    assert r.stopped_at is x
    released = deletes()
    assert len(released) == 2 and released[0] and released[1], released
    assert released[0].isdisjoint(released[1])
    # `walk_ended` counts the slots deleted over the trees' own flushes
    assert stand_ins.records("evaluation")[-1]["data"]["slots_released"] == sum(map(len, released))
    assert released[0] == {x2.resulting_state().name, a._state_after_ending.name}
    assert released[1] == {y2.resulting_state().name, b._state_after_ending.name}
    inv(f)


def test_each_tree_is_stored_at_its_end(tmp_path):
    """ARCHITECTURE §3.4: a walk stores what it wrote at each tree's end, so
    a conversation that ends inside a later tree keeps the earlier trees'
    statuses."""
    f = forest(session("S", theory("A"), theory("B")))
    tm.TABLE.clear_writes()
    run(f.evaluate_to(None, False))
    assert tm.TABLE.transactions == 2             # one per tree; nothing is left for the walk's end

    class Crashing(Rt):
        async def _eval_opr(self):
            raise ZeroDivisionError("the conversation ends here")
    kinds = KINDS | {"crashing": Crashing}
    path = tmp_path / "TAT.sqlite"
    f = ts.Forest_Under_Test(store=Forest_Store(path, stand_ins.log()), kinds=kinds)
    run(locked(f, edit.insert(f, 0, [session("S", theory("A"), theory("B", "A"))], kinds)))
    a, b = f.sub_nodes[0].sub_nodes
    run(locked(f, edit.insert(b, 0, [{"kind": "crashing", "name": "z"}], kinds)))
    with pytest.raises(ZeroDivisionError):
        run(b.evaluate_to(None, False))
    f.store.close()
    f2 = ts.Forest_Under_Test(store=Forest_Store(path, stand_ins.log()), kinds=kinds)
    a2, b2 = f2.sub_nodes[0].sub_nodes
    assert a2.last_evaluation_statuses() == (READY, READY)
    assert b2.last_evaluation_statuses() == NE    # its header ran; the walk ended before B's store


# --- the Theory ending's rule (the plan's §4.1) -------------------------------

def chain():
    """S: A > [x], B imports A, C imports B; C evaluated."""
    f = forest(session("S", theory("A"), theory("B", "A"), theory("C", "B")))
    a, b, c = f.sub_nodes[0].sub_nodes
    (x,) = insert(f, a, 0, [t("x")])
    run(c.evaluate_to(None, False))
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
    run(c.evaluate_to(None, False))
    assert RUNS == ["y", "end A", "begin B", "end B", "begin C", "end C"]
    inv(f)


def test_evaluate_to_inside_an_import_invalidates_its_importers_whole():
    f, a, b, c, x = chain()
    written = len(stand_ins.records("evaluation"))
    run(x.evaluate_to(None, False))
    assert RUNS == [] and st(a) == (READY, NOT_EVALUATED)
    not_evaluated(b, c)
    assert ("C", "ending") in EVENTS
    # what the walk invalidated — the import's ending and both importers
    # whole — each written by no run: no messages, no duration (LOGGING.md §4)
    assert [r["data"] for r in stand_ins.records("evaluation")[written:] if r["event"] == "operation"] == [
        {"node": f.full_id(n), "operation": operation, "ran": False, "status": "not_evaluated"}
        for n, operation in ((a, "ending"), (b, "beginning"), (b, "ending"),
                             (c, "beginning"), (c, "ending"))]
    inv(f)


def test_an_ending_leaving_ready_for_a_stop_invalidates_its_importers():
    f = forest(session("S", theory("A"), theory("B", "A"), theory("C", "B")))
    a, b, c = f.sub_nodes[0].sub_nodes
    (x,) = insert(f, a, 0, [t("x", fail=True)])
    (z,) = insert(f, c, 0, [t("z", fail=True)])
    run(c.evaluate_to(None, True))                                     # every ending ready, past the obstacles
    assert b.is_finished() and st(c) == (READY, READY) and st(z) is CANNOT_EVALUATE
    EVENTS.clear()
    r = run(a.evaluate_to(None, False))                                # A's ending: ready -> not evaluated
    assert r.stopped_at is x and st(a) == (READY, NOT_EVALUATED)
    not_evaluated(b, c)                                          # both outside the walk; C's obstacle reset
    assert {("B", "ending"), ("C", "ending")} <= set(EVENTS)
    inv(f)


def test_a_tree_moved_onto_its_own_dotted_import():
    f = forest(session("S", theory("A")), session("U", theory("B", "S.B")))
    s, u = f.sub_nodes
    (b,) = u.sub_nodes
    run(b.evaluate_to(None, False))
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
    run(f.evaluate_to(None, False))
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
    old_a = f.full_id(a)
    a2, a_new = run(locked(f, edit.amend(a, [theory("A2"), theory("A")], KINDS)))
    assert f._resolved_imports(b) == [a_new] and f._resolved_imports(c) == [a_new]
    not_evaluated(a2, a_new, b, c)
    assert tm.TABLE.theory_deletes == []
    # the amend's `committed` record (LOGGING.md §4): invalidated, in tree
    # order, the replacement, renamed, and both importers of the node
    # behind `A`, whose names did not change
    assert stand_ins.records("edit")[-1]["data"] == {
        "operation": "amend", "parent": f.full_id(s), "index": 0,
        "created": [[f.full_id(a2), "theory"], [f.full_id(a_new), "theory"]],
        "removed": [old_a], "moved": [],
        "invalidated": [f.full_id(a2), f.full_id(b), f.full_id(c)]}
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
        run(e.evaluate_to(None, False))
        tm.TABLE.theory_deletes.clear()
        (b2,) = run(locked(f, edit.amend(b, [theory("B", *imports)], KINDS)))
        not_evaluated(b2, d, e)                                  # the importers, and theirs
        assert st(a) == (READY, READY) and st(c) == (READY, READY)
        assert tm.TABLE.theory_deletes == []
        f.render(f, BRIEFING, stand_ins.agent(f.conversation))
        inv(f)
    # an amend of the obstacle itself: the importers, blocked by the
    # replaced node, run on the next call
    tm.TABLE.clear()
    f = forest(session("S", theory("A", kind="bad_header"), theory("B", "A"), theory("C", "B")))
    a, b, c = f.sub_nodes[0].sub_nodes
    run(c.evaluate_to(None, False))
    assert mark(a) == "failed" and st(b) == NE and st(c) == NE
    (a2,) = run(locked(f, edit.amend(a, [theory("A")], KINDS)))
    not_evaluated(a2, b, c)
    f.render(f, BRIEFING, stand_ins.agent(f.conversation))
    inv(f)
    run(c.evaluate_to(None, False))
    assert f.is_finished()
    inv(f)
    # while the tree was blocked or `not_evaluated`
    tm.TABLE.clear()
    f = forest(session("S", theory("A"), theory("B", "A"), theory("C", "B")))
    a, b, c = f.sub_nodes[0].sub_nodes
    (x,) = insert(f, a, 0, [t("x", fail=True)])
    run(c.evaluate_to(None, False))
    assert st(x) is CANNOT_EVALUATE and st(c) == NE
    (b2,) = run(locked(f, edit.amend(b, [theory("B", "A")], KINDS)))
    not_evaluated(b2, c)
    assert tm.TABLE.theory_deletes == []
    inv(f)
    (b3,) = run(locked(f, edit.amend(b2, [theory("B", "A")], KINDS)))
    not_evaluated(b3, c)
    f.render(f, BRIEFING, stand_ins.agent(f.conversation))
    inv(f)


def test_deleting_the_head_of_a_blocked_chain():
    f = forest(session("S", theory("A"), theory("B", "A"), theory("C", "B"), theory("D", "C")))
    a, b, c, d = f.sub_nodes[0].sub_nodes
    (x,) = insert(f, a, 0, [t("x", fail=True)])
    run(d.evaluate_to(None, False))
    assert st(x) is CANNOT_EVALUATE and st(d) == NE
    run(locked(f, edit.delete(a)))
    not_evaluated(b, c, d)
    assert tm.TABLE.theory_deletes == [("S.A",)]
    f.render(f, BRIEFING, stand_ins.agent(f.conversation))
    inv(f)


def test_inserting_a_tree_an_import_already_names():
    f = forest(session("S", theory("B", "A")))
    (s,) = f.sub_nodes
    (b,) = s.sub_nodes
    run(b.evaluate_to(None, False))
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
    run(f.evaluate_to(None, False))
    run(locked(f, edit.move(b, s, 0)))                           # within a Session
    run(locked(f, edit.move(u, f, 0)))                           # of the Sessions
    assert f.is_finished() and tm.TABLE.theory_deletes == []
    inv(f)
    insert(f, a, 0, [t("x")])                                    # inside a tree
    assert tm.TABLE.theory_deletes == [] and st(b) == (READY, READY)
    inv(f)


def test_after_a_restart_an_import_losing_its_theory_value_invalidates_the_stored_importer(tmp_path):
    """COMPILATION.md §4: the `Theory` ending's rule reads the stored
    status, so on a loaded forest — every instant status `not_evaluated` —
    an import whose stored `ready` ending is invalidated, by a walk or by
    an edit, takes its importer's stored statuses with it."""
    for change in ("walk", "edit"):
        path = tmp_path / f"{change}.sqlite"
        f = ts.Forest_Under_Test(store=Forest_Store(path, stand_ins.log()), kinds=KINDS)
        insert(f, f, 0, [session("S", theory("A"), theory("B", "A"))])
        a, b = f.sub_nodes[0].sub_nodes
        insert(f, a, 0, [t("x"), t("y")])
        run(b.evaluate_to(None, False))
        assert b.last_evaluation_statuses() == (READY, READY)
        f.store.close()

        f2 = ts.Forest_Under_Test(store=Forest_Store(path, stand_ins.log()), kinds=KINDS)
        a2, b2 = f2.sub_nodes[0].sub_nodes
        assert b2.last_evaluation_statuses() == (READY, READY) and st(b2) == NE
        RUNS.clear()
        if change == "walk":
            run(a2.sub_nodes[0].evaluate_to(None, False))   # to x: A's ending lies past the destination
        else:
            insert(f2, a2, 1, [t("z")])
        assert a2.last_evaluation_statuses()[1] is NOT_EVALUATED
        assert b2.last_evaluation_statuses() == NE, change
        assert "begin B" not in RUNS and "end B" not in RUNS
        inv(f2)
        f2.store.close()
        f3 = ts.Forest_Under_Test(store=Forest_Store(path, stand_ins.log()), kinds=KINDS)
        assert f3.sub_nodes[0].sub_nodes[1].last_evaluation_statuses() == NE, change


def test_amending_a_theory_node_invalidates_its_inherited_children():
    """An amend that keeps the name and the imports changes no tree's
    record, and under a `Session` the replacement's own position marks
    nothing: the children it inherits are invalidated from the first
    (ARCHITECTURE §3.5), and the importers follow through the record, which
    holds the node itself."""
    f = forest(session("S", theory("A"), theory("B", "A")))
    a, b = f.sub_nodes[0].sub_nodes
    x, y = insert(f, a, 0, [t("x"), t("y")])
    run(b.evaluate_to(None, False))
    assert f.is_finished()
    (a2,) = run(locked(f, edit.amend(a, [theory("A")], KINDS)))
    assert a2.sub_nodes == [x, y]
    not_evaluated(a2, b)
    inv(f)
    RUNS.clear()
    run(b.evaluate_to(None, False))
    assert RUNS == ["begin A", "x", "y", "end A", "begin B", "end B"] and f.is_finished()
    inv(f)


# --- a move across trees; a nesting node inside a tree ------------------------

def test_a_move_across_trees_invalidates_from_both_positions():
    """ARCHITECTURE §3.5: a `move` invalidates from the position its
    successor holds where the node left — so that tree's ending and,
    through it, that tree's importers — and from the node's new position."""
    f = forest(session("S", theory("A"), theory("B", "A"), theory("C")))
    a, b, c = f.sub_nodes[0].sub_nodes
    x, y = insert(f, a, 0, [t("x"), t("y")])
    (z,) = insert(f, c, 0, [t("z")])
    run(f.evaluate_to(None, False))
    assert f.is_finished()
    tm.TABLE.clear_writes()
    run(locked(f, edit.move(x, c, 0)))
    assert a.sub_nodes == [y] and c.sub_nodes == [x, z]
    assert st(a) == (READY, NOT_EVALUATED) and st(y) is NOT_EVALUATED      # where it left
    not_evaluated(b)                                                       # A's importer, whole
    assert st(c) == (READY, NOT_EVALUATED)                                 # where it arrived
    assert st(x) is NOT_EVALUATED and st(z) is NOT_EVALUATED
    assert tm.TABLE.values[x.state.name] == "begin C" and tm.TABLE.values[y.state.name] == "begin A"
    assert tm.TABLE.transactions == 1
    inv(f)
    RUNS.clear()
    run(f.evaluate_to(None, False))
    assert RUNS == ["y", "end A", "begin B", "end B", "x", "z", "end C"] and f.is_finished()
    inv(f)


def test_a_failed_beginning_inside_a_tree():
    """ARCHITECTURE §3.3 on the real `Forest`: a nesting node whose
    beginning failed is passed by a walk going on after it, and is the stop
    of a call whose destination lies under it; there the tree's walk ends
    and everything after the destination is invalidated, the tree's ending
    and so its importer included."""
    f = forest(session("S", theory("T"), theory("W", "T")))
    tree, w = f.sub_nodes[0].sub_nodes
    s, d = insert(f, tree, 0, [
        {"kind": "block", "name": "S", "fail": True, "children": [t("a"), t("b")]}, t("d")])
    a, b = s.sub_nodes
    r = run(w.evaluate_to(None, True))
    assert r == EvaluationResult(None, None)
    assert st(s) == (CANNOT_EVALUATE, READY) and st(a) is st(b) is NOT_EVALUATED
    assert st(d) is READY and st(tree) == (READY, READY) and st(w) == (READY, READY)
    inv(f)
    # a destination under the failed beginning: the block is the stop
    walk_start = len(stand_ins.records("evaluation"))
    r = run(a.evaluate_to(None, False))
    assert r == EvaluationResult(s, None)
    assert [r["data"] for r in stand_ins.records("evaluation")[walk_start:] if r["event"] == "stopped"] == [
        {"node": f.full_id(s), "reason": "command_failed"}]
    def statuses():
        return [st(n) for n in (*tree._tree_order(), *w._tree_order())]
    after_the_strict_call = statuses()
    assert st(s) == (CANNOT_EVALUATE, NOT_EVALUATED) and st(b) is NOT_EVALUATED
    assert st(d) is NOT_EVALUATED and st(tree) == (READY, NOT_EVALUATED)
    not_evaluated(w)
    inv(f)
    # a destination after it: the ending is the copy again, and what follows runs
    RUNS.clear()
    r = run(tree.evaluate_to(None, False))
    assert r == EvaluationResult(None, None) and RUNS == ["d", "end T"]
    assert st(s) == (CANNOT_EVALUATE, READY) and st(tree) == (READY, READY)
    assert tm.TABLE.values[d.state.name] == tm.TABLE.values[s.state.name] == "begin T"
    inv(f)
    # under it with ignore_error: no stop is reported, and the same invalidation
    walk_start = len(stand_ins.records("evaluation"))
    r = run(a.evaluate_to(None, True))
    assert r == EvaluationResult(None, None)
    assert "stopped" not in [r["event"] for r in stand_ins.records("evaluation")[walk_start:]]
    assert statuses() == after_the_strict_call
    inv(f)


# --- `_invalidate` on a node nothing chains (the plan's §6) -------------------

def test_invalidating_a_session_whole():
    f = forest(session("S", theory("A"), theory("B")))
    (s,) = f.sub_nodes
    a, b = s.sub_nodes
    run(f.evaluate_to(None, False))
    assert f.is_finished()
    tm.invalidate(s)
    not_evaluated(a, b)
    inv(f)


# --- the order constraint's sentence through the tools (RENDER_BASELINES §3) -

def test_the_tools_compose_the_order_constraints_sentence():
    """RENDER_BASELINES §3's two lines, under `evaluate_to`'s stop line and
    under an edit's `Done` line (TOOL_SCHEMAS §4); none under a stop of
    another kind."""
    first, second = fenced_lines(DOCS / "RENDER_BASELINES.md", "3.")[:2]
    me = Agent("main", True)

    def tools_over(f):
        return {tool.name: tool for tool in mcp.tools(f, plugin.Loaded(KINDS, mcp._schema("edit")))}
    f = forest(session("S", theory("B", "S.C"), theory("C")))
    tools = tools_over(f)
    result = run(tools["evaluate_to"].run(me, {"node_id": "theory_B"}))
    assert result.text.splitlines()[:2] == ["Evaluation stopped at theory_B.", first]
    result = run(tools["edit"].run(me, dict(action="append", target_id="theory_B", constructs=[t("x")],
                                            evaluate=True)))
    assert result.text.splitlines()[:2] == ["Done: append theory_B; evaluation stopped at theory_B.", first]
    f = forest(session("S", theory("B", "S.B")))
    result = run(tools_over(f)["evaluate_to"].run(me, {"node_id": "theory_B"}))
    assert result.text.splitlines()[:2] == ["Evaluation stopped at theory_B.", second]
    # a tree as the stop with no violation: the import without a theory value
    f = forest(session("S", theory("C", kind="bad_header"), theory("B", "S.C")))
    result = run(tools_over(f)["evaluate_to"].run(me, {"node_id": "theory_B"}))
    assert result.text.splitlines()[0] == "Evaluation stopped at bad_header_C."
    assert result.text.splitlines()[1].startswith("session_S")
    f = forest(session("S", theory("C")))
    (c,) = f.sub_nodes[0].sub_nodes
    insert(f, c, 0, [t("y", fail=True)])
    result = run(tools_over(f)["evaluate_to"].run(me, {"node_id": "theory_C"}))
    assert result.text.splitlines()[1].startswith("session_S")       # no sentence: the quickview follows
