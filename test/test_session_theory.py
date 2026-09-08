"""`Session`, `Theory` and `Unchained_Node` (node_classes/SESSION_AND_THEORY.md,
the plan's §6) against the fake state slot table: gen's checks and their
approved wording, the unchained container under edits, moves, ids, the
store round trip, and the slot chain of a tree whose header failed.
Running a real header needs Isabelle: test/tat_framework_ml_test.py.
Run: python -m pytest test/test_session_theory.py
"""

from pathlib import Path

import pytest

import test_model as tm
from baselines import DOCS, fenced_lines
from invariants import assert_invariants, assert_store_mirrors
from routing_forest import Routing_Forest
from test_model import CONN, locked, run

import isabelle_theory_agent.model as M
from isabelle_theory_agent import edit, isabelle_driver
from isabelle_theory_agent.exceptions import (
    BadSessionNodeParent, BadTheoryNodeParent, DuplicateTheoryShortName,
    InvalidField, InvalidName, TAT_InternalError)
from isabelle_theory_agent.model import (
    INVALIDATING, NOT_EVALUATED, READY, CannotEvaluate, EvaluationResult, Session, Theory)
from isabelle_theory_agent.store import Forest_Store

HEAP = {"List": "HOL.List"}       # the fake base heap: short name -> long name


# Three `Theory` fakes against the fake state slot table, each standing for
# one outcome of the real class's two operations (the plan's §6).

class Fake_Theory(Theory):
    """Header and `end` both pass: the beginning writes the first child's
    slot, the ending writes the owned resulting slot."""
    async def _eval_beginning_opr(self):
        tm.TABLE.values[self._state_after_beginning().name] = f"begin {self.name}"
        return True
    async def _eval_ending_opr(self):
        tm.TABLE.values[self._state_after_ending.name] = f"end {self.name}"
        return True

class Failing_Header_Theory(Fake_Theory):
    """The header fails: the beginning writes nothing and answers False, as
    the real one does on a bad import."""
    async def _eval_beginning_opr(self):
        self.beginning_errors = ["No such file: TAT_Nowhere.thy"]
        return False

class Failing_End_Theory(Fake_Theory):
    """`end` fails: the ending writes nothing and answers False; the
    framework copies the open theory's state through."""
    async def _eval_ending_opr(self):
        self.ending_errors = ["Bad theory ending"]
        return False


KINDS = {"session": Session, "theory": Theory, "fake_theory": Fake_Theory,
         "failing_header_theory": Failing_Header_Theory,
         "failing_end_theory": Failing_End_Theory,
         "t": tm.T}                                          # `t`: a theory's child


class Forest_Under_Test(Routing_Forest):
    def __init__(self, conn=CONN, store=None, kinds=KINDS):
        super().__init__(M.Conversation(conn, Path(".")),
                         store if store is not None else Forest_Store(":memory:"), kinds)


@pytest.fixture(autouse=True)
def table(monkeypatch):
    tm.TABLE.clear()
    tm.TABLE.install(monkeypatch)
    async def check_new_theory_short_name(conn, name):
        return HEAP.get(name)
    monkeypatch.setattr(isabelle_driver, "check_new_theory_short_name",
                        check_new_theory_short_name)


def shape(forest):
    def fields(n):
        if isinstance(n, Session):
            return (n.parent_session, n.options, n.description)
        if isinstance(n, Theory):
            return tuple(n.imports)
        return n.fail
    return [(n.identity, n.kind, n.name, fields(n),
             len(n.sub_nodes) if isinstance(n, M.NonLeaf_Node) else None)
            for n in forest._all_nodes()]


def inv(f):
    assert_invariants(f, tm.TABLE)
    assert_store_mirrors(f, KINDS, shape=shape)


def theory(name, *imports, kind="theory"):
    return {"kind": kind, "name": name, "imports": list(imports) or ["Main"]}


def session(name, *children, **fields):
    raw = {"kind": "session", "name": name, "parent_session": "HOL", **fields}
    if children:
        raw["children"] = list(children)
    return raw


def insert(f, parent, index, raws):
    return run(locked(f, edit.insert(parent, index, raws, KINDS)))


def arith():
    """Sessions > [session_Arith > [theory_X, theory_Y > [t_a]]]."""
    f = Forest_Under_Test()
    (s,) = insert(f, f, 0, [session("Arith", theory("X"), theory("Y", "Arith.X"))])
    x, y = s.sub_nodes
    (a,) = insert(f, y, 0, [{"kind": "t", "name": "a"}])
    return f, s, x, y, a


# --- what a session and its theories are -------------------------------------

def test_a_session_with_its_theories_in_one_call():
    f, s, x, y, a = arith()
    assert (s.name, x.name, y.name) == ("Arith", "X", "Y")            # as the agent wrote them
    assert [n.id_component() for n in (s, x, y, a)] == \
        ["session_Arith", "theory_X", "theory_Y", "t_a"]
    assert (s.parent_session, s.options, s.description) == ("HOL", [], "")
    assert x.imports == ["Main"] and y.imports == ["Arith.X"]
    assert (s.kind, x.kind) == ("session", "theory")
    assert [f.id_of(n) for n in (s, x, y, a)] == ["session_Arith", "theory_X", "theory_Y", "t_a"]
    assert f.resolve("session_Arith.theory_Y.t_a") is a
    assert x.header() == "theory X\n  imports Main\nbegin"
    assert not f.is_finished() and s._operations_ready() and not x._operations_ready()
    inv(f)


def test_the_fields_are_kept_and_stored(tmp_path):
    store = Forest_Store(tmp_path / "theory_forest.sqlite")
    f = Forest_Under_Test(store=store)
    (s,) = insert(f, f, 0, [session(
        "Arith", theory("X", "Main", "HOL-Library.Multiset", '"lib/Rel"'),
        options=[{"name": "document", "value": "pdf"}, {"name": "timeout", "value": "600"}],
        description="Arithmetic")])
    assert s.options == [{"name": "document", "value": "pdf"}, {"name": "timeout", "value": "600"}]
    assert s.description == "Arithmetic"
    assert s.sub_nodes[0].header() == 'theory X\n  imports Main HOL-Library.Multiset "lib/Rel"\nbegin'
    before = shape(f)
    store.close()
    f2 = Forest_Under_Test(store=Forest_Store(tmp_path / "theory_forest.sqlite"))
    assert shape(f2) == before
    s2 = f2.sub_nodes[0]
    assert isinstance(s2, Session) and s2.parent is f2
    assert isinstance(s2.sub_nodes[0], Theory) and s2.sub_nodes[0].parent is s2
    assert tm.st(s2.sub_nodes[0]) == (NOT_EVALUATED, NOT_EVALUATED)


# --- the unchained container -------------------------------------------------

def test_children_are_not_chained():
    f, s, x, y, a = arith()
    # a tree owns its resulting slot; the container names none, before or after its children
    assert x.resulting_state() is x._state_after_ending and x._state_after_ending is not x.state
    for container, child in ((s, x), (f, s)):
        with pytest.raises(TAT_InternalError):
            container._resulting_state_of_child(child)
        with pytest.raises(TAT_InternalError):
            container._resulting_state_of_all_children()
    with pytest.raises(TAT_InternalError):
        s.resulting_state()
    # inside the tree the chain is the ordinary one
    assert a.resulting_state() is y._state_before_ending
    assert s._states_inside() == [s.state, x.state, x._state_before_ending, x._state_after_ending,
                                  y.state, a.state, y._state_before_ending, y._state_after_ending]
    # no operation of its own: nothing written, nothing owed, nothing to take or carry
    assert s._last_status() is NOT_EVALUATED and s._operations_ready()
    assert not s._predecessor_wrote(1) and s._source_before(1) is None
    # no edit around it copies a state: every call so far was a delete of what left
    assert all(c[0] == "delete" for c in tm.TABLE.calls), tm.TABLE.calls


def test_a_walk_never_reaches_a_session():
    f, s, x, y, a = arith()
    with pytest.raises(TAT_InternalError, match="reached a Session"):
        run(s._evaluate(M.Evaluation(None, False), INVALIDATING))


def test_the_owned_slot_under_each_outcome_of_a_tree():
    """The plan's §6, the release invariant of a tree's owned resulting
    slot: held after a successful `end`; held after a failed `end`, whose
    copy-through copies the open theory's state; empty after a failed
    header, whose copy-through copies an input nobody wrote — the ending
    `ready` all the same (ARCHITECTURE §3.2).  Its input slot is never
    held."""
    f = Forest_Under_Test()
    (s,) = insert(f, f, 0, [session(
        "Arith", theory("Good", kind="fake_theory"),
        theory("BadEnd", kind="failing_end_theory"),
        theory("BadHeader", kind="failing_header_theory"))])
    good, bad_end, bad_header = s.sub_nodes
    (a,) = insert(f, good, 0, [{"kind": "t", "name": "a"}])
    values = tm.TABLE.values

    r = run(good.evaluate_to(False))
    assert r == EvaluationResult(None, INVALIDATING)
    assert tm.st(good) == (READY, READY) and good.is_finished()
    assert values[a.state.name] == "begin Good" and a.consumed == "begin Good"
    assert values[good._state_after_ending.name] == "end Good"
    inv(f)

    r = run(bad_end.evaluate_to(False))
    assert r.stopped_at is bad_end                           # an own stop at the ending
    assert tm.st(bad_end) == (READY, CannotEvaluate(None)) and bad_end.ending_errors
    assert values[bad_end._state_after_ending.name] == "begin BadEnd"   # copied through
    inv(f)

    r = run(bad_header.evaluate_to(False))
    assert r == EvaluationResult(None, INVALIDATING)          # not a stop for its successors
    assert tm.st(bad_header) == (CannotEvaluate(None), READY)
    assert bad_header.beginning_errors and not bad_header.is_finished()
    assert bad_header._state_after_ending.name not in values
    inv(f)

    for tree in (good, bad_end, bad_header):
        assert tree.state.name not in values                 # nobody writes a tree's input
    # invalidating a tree releases what it wrote; deleting one, its whole slot set
    run(good.evaluate_to(False, evaluate=False))
    inv(f)
    for tree in (bad_end, bad_header):
        run(locked(f, edit.delete(tree)))
        inv(f)
    assert s.sub_nodes == [good]


def test_delete_and_amend_in_the_session_layer():
    f, s, x, y, a = arith()
    tm.TABLE.calls.clear()
    run(locked(f, edit.delete(x)))
    assert s.sub_nodes == [y] and x.parent is None
    assert [c[0] for c in tm.TABLE.calls] == ["delete"]        # x's three slots, no copy
    assert set(tm.TABLE.calls[0][1]) == {x.state.name, x._state_before_ending.name,
                                         x._state_after_ending.name}
    inv(f)
    # amending the session: its theories are inherited, nothing is copied
    tm.TABLE.calls.clear()
    (s2,) = run(locked(f, edit.amend(s, [session("Arith2", description="renamed")], KINDS)))
    assert f.sub_nodes == [s2] and s2.sub_nodes == [y] and y.parent is s2
    assert (s2.name, s2.description, s2.identity) == ("Arith2", "renamed", s.identity)
    assert f.id_of(a) == "t_a" and f.resolve("session_Arith2.theory_Y.t_a") is a
    assert not [c for c in tm.TABLE.calls if c[0] == "copy"]
    inv(f)


# --- moves ------------------------------------------------------------------

def test_moving_between_sessions_and_the_parent_gates():
    f, s, x, y, a = arith()
    (s2,) = insert(f, f, 1, [session("Algebra")])
    tm.TABLE.calls.clear()
    run(locked(f, edit.move(x, s2, 0)))
    assert s.sub_nodes == [y] and s2.sub_nodes == [x] and x.parent is s2
    assert not [c for c in tm.TABLE.calls if c[0] == "copy"]
    inv(f)
    run(locked(f, edit.move(s2, f, 0)))                        # reordering sessions
    assert f.sub_nodes == [s2, s]
    with pytest.raises(BadTheoryNodeParent) as e:
        run(locked(f, edit.move(x, f, 0)))
    assert (e.value.kind, e.value.parent_id) == ("theory", "Sessions")
    with pytest.raises(BadTheoryNodeParent) as e:
        run(locked(f, edit.move(x, y, 0)))
    assert e.value.parent_id == "theory_Y"
    with pytest.raises(BadSessionNodeParent) as e:
        run(locked(f, edit.move(s2, s, 0)))
    assert (e.value.kind, e.value.parent_id) == ("session", "session_Arith")
    assert f.sub_nodes == [s2, s] and s2.sub_nodes == [x]      # nothing moved
    inv(f)


# --- gen's checks ------------------------------------------------------------

def test_where_a_session_and_a_theory_may_live():
    f, s, x, y, a = arith()
    with pytest.raises(BadSessionNodeParent) as e:
        insert(f, x, 0, [session("Inner")])
    assert (e.value.kind, e.value.parent_id) == ("session", "theory_X")
    assert e.value.raw_ast_path == "constructs[0]"
    with pytest.raises(BadTheoryNodeParent) as e:
        insert(f, f, 0, [theory("Z")])
    assert e.value.parent_id == "Sessions"
    with pytest.raises(BadTheoryNodeParent) as e:
        insert(f, x, 0, [theory("Z")])
    assert e.value.parent_id == "theory_X"
    # a parent still under construction in the same call: its full id
    with pytest.raises(BadSessionNodeParent) as e:
        insert(f, f, 1, [session("Outer", session("Inner"))])
    assert e.value.parent_id == "session_Outer"
    assert e.value.raw_ast_path == "constructs[0].children[0]"
    assert f.sub_nodes == [s] and x.sub_nodes == []
    inv(f)


def test_names():
    f, s, x, y, a = arith()
    # a theory's short name is an Isabelle identifier, judged by the class as
    # the agent spelt it, with the theory-name rendering; a trailing
    # underscore is legal there and is the framework's grammar to refuse,
    # with the rendering that names that rule
    for bad in ("Foo-Bar", "A.B", "1x", "", "x y"):
        with pytest.raises(InvalidName) as e:
            insert(f, s, 0, [theory(bad)])
        assert (e.value.name, e.value.theory_name) == (bad, True)
    with pytest.raises(InvalidName) as e:
        insert(f, s, 0, [theory("x_")])
    assert (e.value.name, e.value.theory_name) == ("x_", False)
    (p,) = insert(f, s, 0, [theory("P'_2")])
    assert p.id_component() == "theory_P'_2"
    # a session's name may carry hyphens: the framework's grammar, judged on
    # the agent's spelling, with the name rendering
    for bad in ("Ch 2", "x-", "-x", "Ch.2"):
        with pytest.raises(InvalidName) as e:
            insert(f, f, 0, [session(bad)])
        assert (e.value.name, e.value.theory_name) == (bad, False)
    (lib,) = insert(f, f, 0, [session("HOL-Library")])
    assert lib.name == "HOL-Library" and f.id_of(lib) == "session_HOL-Library"
    (sessions,) = insert(f, f, 0, [session("Sessions")])       # no name is reserved
    assert f.id_of(sessions) == "session_Sessions" and f.resolve("Sessions") is f
    inv(f)


def test_a_theory_short_name_is_unique_everywhere():
    f, s, x, y, a = arith()
    (s2,) = insert(f, f, 1, [session("Algebra")])
    with pytest.raises(DuplicateTheoryShortName) as e:       # the base heap
        insert(f, s2, 0, [theory("List")])
    assert (e.value.short_name, e.value.holder) == ("List", "HOL.List")
    with pytest.raises(DuplicateTheoryShortName) as e:       # another session's tree
        insert(f, s2, 0, [theory("X")])
    assert (e.value.short_name, e.value.holder) == ("X", "theory_X")
    with pytest.raises(DuplicateTheoryShortName) as e:       # the same call, across sessions
        insert(f, f, 2, [session("More", theory("Q")), session("Yet", theory("Q"))])
    assert e.value.holder == "constructs[0].children[0]"
    assert e.value.raw_ast_path == "constructs[1].children[0]"
    # an amend may keep the short name: the node it replaces is leaving
    (x2,) = run(locked(f, edit.amend(x, [theory("X", "Main", "HOL.Rat")], KINDS)))
    assert x2.imports == ["Main", "HOL.Rat"] and x2.identity == x.identity
    assert s.sub_nodes == [x2, y]
    inv(f)


# The approved renderings of the two classes' InvalidField reasons
# (SESSION_AND_THEORY.md §3), each asserted verbatim and each covered.
REASONS = set(fenced_lines(DOCS / "node_classes" / "SESSION_AND_THEORY.md", "3."))
COVERED = set()


def test_the_field_checks():
    f, s, x, y, a = arith()
    def refused(parent, raw, field, rendering=None):
        with pytest.raises(InvalidField) as e:
            insert(f, parent, 0, [raw])
        assert e.value.field == field
        if rendering is not None:
            e.value.raw_ast_path = None            # the cause line alone
            assert str(e.value) == rendering and rendering in REASONS
            COVERED.add(rendering)
    refused(s, theory("Z") | {"imports": []}, "imports")
    refused(s, theory("Z", "Main", ""), "imports[1]")
    refused(f, session("S") | {"parent_session": ""}, "parent_session",
            "The field `parent_session` must not be empty.")
    refused(f, session("S", options=[{"name": "", "value": "x"}]), "options[0].name")
    refused(f, session("S", options=[{"name": "document", "value": ""}]), "options[0].value")
    refused(f, session("S", options=[{"name": "document", "value": "pdf"},
                                     {"name": "document", "value": "false"}]),
            "options[1].name",
            "The field `options[1].name` sets the option `document` a second time.")
    assert f.sub_nodes == [s] and s.sub_nodes == [x, y]
    assert COVERED == REASONS
    inv(f)
