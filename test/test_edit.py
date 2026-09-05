"""The four-step edit build (MODULE_STRUCTURE §4.1): construct detached,
gates, commit, completed events — atomicity, hook order, the exception
paths, amend inheritance, move.  Run: python -m pytest test/test_edit.py
"""

import random
from typing import NotRequired, TypedDict

import pytest

import test_model as tm
from invariants import assert_invariants
from test_model import Block, T, locked, run, slot, st

import isabelle_theory_agent.model as M
from isabelle_theory_agent.exceptions import (
    BadEdit, ChildrenNotInheritable, DuplicateName, InvalidField,
    InvalidName, MalformedRawAST, MissingField, MoveIntoOwnSubtree,
    TAT_InternalError, UnexpectedChildren, UnexpectedField, UnknownKind)
from isabelle_theory_agent.model import (
    NOT_EVALUATED, READY, CannotEvaluate, Location)


@pytest.fixture(autouse=True)
def table(monkeypatch):
    tm.TABLE.clear()
    tm.TABLE.install(monkeypatch)
    EVENTS.clear()


def inv(f):
    assert_invariants(f, tm.TABLE)


def deletes():
    return [c for c in tm.TABLE.calls if c[0] == "delete"]


# --- recording node classes -------------------------------------------------

EVENTS: list[tuple] = []

class Recording:
    def on_invalidated(self, operation):
        EVENTS.append((self.name, "invalidated", operation))
        super().on_invalidated(operation)
    def on_deleting(self, reason): EVENTS.append((self.name, "deleting", reason))
    def on_deleted(self, reason): EVENTS.append((self.name, "deleted", reason))
    def on_inserted(self): EVENTS.append((self.name, "inserted"))
    def on_inheriting(self, new_parent):
        EVENTS.append((self.name, "inheriting", new_parent.name))
    def on_inherited(self, old_parent):
        EVENTS.append((self.name, "inherited", old_parent.name))
    def on_moving(self, new_location):
        EVENTS.append((self.name, "moving",
                       new_location.parent.name, new_location.index))
    def on_moved(self, old_location):
        EVENTS.append((self.name, "moved",
                       old_location.parent.name, old_location.index))

class RT(Recording, T):
    pass

class RBlock(Recording, Block):
    def on_removing_child(self, child, mode):
        EVENTS.append((self.name, "removing_child", child.name, mode))
    def on_added_child(self, child, mode):
        EVENTS.append((self.name, "added_child", child.name, mode))


KINDS = {"t": RT, "block": RBlock}


class Nesting_RawAST(TypedDict):             # a declaration that nests itself
    child: NotRequired["Nesting_RawAST"]


def rbuild():
    """Theory > [Section > [a, b], c], every class recording."""
    f = tm.OneTreeForest(tm.CONN)
    thy = RBlock(f, slot(), "Theory", slot()); f.sub_nodes.append(thy)
    sec = RBlock(thy, slot(), "Section", slot())
    a = RT(sec, slot(), "a"); b = RT(sec, slot(), "b")
    sec.sub_nodes += [a, b]
    c = RT(thy, slot(), "c")
    thy.sub_nodes += [sec, c]
    return f, thy, sec, a, b, c


def events(*types):
    return [e for e in EVENTS if e[1] in types]


# --- insert -----------------------------------------------------------------

def test_insert_nested_and_completed_order():
    f, thy, sec, a, b, c = rbuild()
    raws = [{"kind": "block", "name": "S2",
             "children": [{"kind": "t", "name": "x"},
                          {"kind": "t", "name": "y"}]}]
    (s2,) = run(locked(f, thy._insert_children(2, raws, KINDS)))
    assert thy.sub_nodes == [sec, c, s2]
    assert [n.name for n in s2.sub_nodes] == ["x", "y"]
    assert all(n.parent is s2 for n in s2.sub_nodes)
    assert EVENTS == [                        # tree order over what entered
        ("Theory", "added_child", "S2", "insert_or_delete"),
        ("S2", "inserted"),
        ("S2", "added_child", "x", "insert_or_delete"),
        ("x", "inserted"),
        ("S2", "added_child", "y", "insert_or_delete"),
        ("y", "inserted"),
    ]

def test_batch_aborts_whole_with_the_path(  ):
    f, thy, sec, a, b, c = rbuild()
    run(c.evaluate_to(False))
    EVENTS.clear()
    before = list(thy.sub_nodes)
    before_table = dict(tm.TABLE.values)
    before_deleted = list(tm.TABLE.deleted)
    raws = [{"kind": "t", "name": "u"},
            {"kind": "block", "name": "S2",
             "children": [{"kind": "wrong", "name": "x"}]}]
    with pytest.raises(UnknownKind) as e:
        run(locked(f, thy._insert_children(2, raws, KINDS)))
    assert e.value.raw_ast_path == "constructs[1].children[0]"
    assert e.value.kind == "wrong" and e.value.available_kinds == ["t", "block"]
    assert thy.sub_nodes == before and EVENTS == []      # forest untouched
    assert tm.TABLE.values == before_table               # and nothing remote
    assert tm.TABLE.deleted == before_deleted

def test_duplicate_name_against_sibling_and_batch():
    f, thy, sec, a, b, c = rbuild()
    with pytest.raises(DuplicateName) as e:
        run(locked(f, thy._insert_children(
            2, [{"kind": "t", "name": "c"}], KINDS)))
    assert e.value.taken_by == "Theory.c" and e.value.raw_ast_path == "constructs[0]"
    with pytest.raises(DuplicateName) as e:
        run(locked(f, thy._insert_children(
            2, [{"kind": "t", "name": "z"}, {"kind": "t", "name": "z"}], KINDS)))
    assert e.value.taken_by == "constructs[0]" and e.value.raw_ast_path == "constructs[1]"

def test_the_rawast_error_family():
    f, thy, sec, a, b, c = rbuild()
    def insert(raw):
        return locked(f, thy._insert_children(2, [raw], KINDS))
    with pytest.raises(MalformedRawAST) as e:
        run(insert(42))
    assert not e.value.missing_kind
    with pytest.raises(MalformedRawAST) as e:
        run(insert({"name": "x"}))
    assert e.value.missing_kind
    with pytest.raises(MissingField) as e:
        run(insert({"kind": "t"}))
    assert (e.value.kind, e.value.field) == ("t", "name")
    with pytest.raises(InvalidField) as e:
        run(insert({"kind": "t", "name": 5}))
    assert e.value.reason == "must be a string"
    with pytest.raises(InvalidField):
        run(insert({"kind": "t", "name": True}))     # a flag is not a string
    with pytest.raises(InvalidName) as e:
        run(insert({"kind": "t", "name": "bad name"}))
    assert e.value.raw_ast_path == "constructs[0]"
    with pytest.raises(UnexpectedChildren) as e:
        run(insert({"kind": "t", "name": "x", "children": []}))
    assert e.value.is_leaf

def test_schema_typed_dict_forms():
    from typing import NotRequired, TypedDict

    class Fact(TypedDict):
        name: str

    class Rich_RawAST(TypedDict):
        name: str
        priority: NotRequired[int]
        note: NotRequired[str | int]
        facts: NotRequired[list[Fact]]
        tags: NotRequired[list[str]]

    class Rich(RT):
        argument_schema = Rich_RawAST

    def check_ok(raw):
        M._check_schema(Rich, "t", raw)
    def check_bad(raw, field, reason):
        with pytest.raises((MissingField, InvalidField)) as e:
            M._check_schema(Rich, "t", raw)
        got = e.value
        assert (got.field if isinstance(got, InvalidField)
                else got.field) == field
        if reason is not None:
            assert got.reason == reason

    check_ok({"kind": "t", "name": "x"})                 # optionals absent
    check_ok({"kind": "t", "name": "x", "priority": 3,
              "note": "n", "facts": [{"name": "f"}]})
    check_ok({"kind": "t", "name": "x", "note": 7})      # the union's other arm
    check_bad({"kind": "t"}, "name", None)               # required missing
    check_bad({"kind": "t", "name": "x", "priority": True},
              "priority", "must be a number")            # a flag is not a number
    check_bad({"kind": "t", "name": "x", "note": []},
              "note", "must be a string or a number")
    check_bad({"kind": "t", "name": "x", "facts": [{"name": 1}]},
              "facts[0].name", "must be a string")
    check_bad({"kind": "t", "name": "x", "facts": [{}]},
              "facts[0].name", None)                     # nested required
    check_bad({"kind": "t", "name": "x", "tags": ["a", 5]},
              "tags[1]", "must be a string")             # the element, not the list
    check_bad({"kind": "t", "name": "x", "tags": "a"},
              "tags", "must be a list")
    # undeclared fields are refused, the typo before its own hole
    with pytest.raises(UnexpectedField) as e:
        M._check_schema(Rich, "t", {"kind": "t", "namee": "x"})
    assert (e.value.holder, e.value.field) == ("t", "namee")
    assert e.value.takes == ["name", "priority", "note", "facts", "tags"]
    assert e.value.holder_is_kind
    with pytest.raises(UnexpectedField) as e:
        M._check_schema(Rich, "t", {"kind": "t", "name": "x",
                                    "facts": [{"name": "f", "extra": 1}]})
    assert (e.value.holder, e.value.field) == ("facts[0]", "extra")
    assert e.value.takes == ["name"] and not e.value.holder_is_kind
    # no declaration, no check
    class Loose(RT):
        argument_schema = None
    M._check_schema(Loose, "t", {"kind": "t", "whatever": 1})
    M.validate_argument_schema(None)


def test_schema_grammar_is_closed_at_registration():
    from typing import Any, Literal, NotRequired, TypedDict

    class Fact(TypedDict):
        name: str

    class Fine(TypedDict):
        kind: Literal["t"]                   # kind: the framework's, unchecked
        a: str
        b: NotRequired[bool]
        n: NotRequired[float]
        anything: NotRequired[Any]
        facts: NotRequired[list[Fact]]
        either: NotRequired[Fact | str]
    M.validate_argument_schema(Fine)

    def refused(td):
        with pytest.raises(TAT_InternalError):
            M.validate_argument_schema(td)
    class HasChildren(TypedDict):
        children: list
    class Optional(TypedDict):
        a: str | None                        # no JSON word for null
    class Dicty(TypedDict):
        a: dict
    class Lit(TypedDict):
        a: Literal["x", "y"]
    class TwoObjects(TypedDict):
        a: Fact | Fine
    class TwoObjectsInLists(TypedDict):
        a: list[Fact] | list[Fine]           # indistinguishable arms
    class TwoObjectsThroughAUnionInAList(TypedDict):
        a: list[str | Fact] | list[Fine]
    class AnyArm(TypedDict):
        a: Any | Fact                        # Any would make the object moot
    class Dangling(TypedDict):
        a: "NoSuchType"                      # a forward reference nothing resolves
    for td in (HasChildren, Optional, Dicty, Lit, TwoObjects,
               TwoObjectsInLists, TwoObjectsThroughAUnionInAList, AnyArm,
               Dangling, Nesting_RawAST):
        refused(td)
    refused(dict)                            # not a TypedDict at all

    # what the grammar admits, the checker renders within the approved words
    class R(RT):
        argument_schema = Fine
    M._check_schema(R, "t", {"kind": "t", "a": "x", "n": 3})         # an int is a number
    M._check_schema(R, "t", {"kind": "t", "a": "x", "either": "s"})
    with pytest.raises(InvalidField) as e:
        M._check_schema(R, "t", {"kind": "t", "a": "x", "either": 5})
    assert e.value.reason == "must be an object or a string"
    with pytest.raises(UnexpectedField) as e:                          # D5: through a union arm
        M._check_schema(R, "t", {"kind": "t", "a": "x", "either": {"bogus": 1}})
    assert (e.value.holder, e.value.field) == ("either", "bogus")
    class Nums(TypedDict):
        n: int | float
    class N(RT):
        argument_schema = Nums
    with pytest.raises(InvalidField) as e:
        M._check_schema(N, "t", {"kind": "t", "n": "3"})
    assert e.value.reason == "must be a number"                        # deduplicated


def test_children_field_must_be_a_list():
    f, thy, sec, a, b, c = rbuild()
    for bad in (None, 5, {}, "xy"):
        with pytest.raises(InvalidField) as e:
            run(locked(f, thy._insert_children(
                2, [{"kind": "block", "name": "S2", "children": bad}],
                KINDS)))
        assert e.value.field == "children"

def test_insert_moves_the_value_from_the_source_slot():
    f, thy, sec, a, b, c = rbuild()
    run(c.evaluate_to(False))
    (u,) = run(locked(f, thy._insert_children(
        1, [{"kind": "t", "name": "u"}], KINDS)))
    # The predecessor's result moved: it is u's input now, and the slot it
    # came from — written by u after the commit — is empty.
    assert tm.TABLE.values[u.state.name] == "end Section"
    assert c.state.name not in tm.TABLE.values

def test_insert_after_own_stop_receives_the_written_input():
    f, thy, sec, t1, t2, t3, t4 = tm.build(T1=True)
    run(t4.evaluate_to(True))
    assert st(t1) == CannotEvaluate(None)
    (n,) = run(locked(f, sec._insert_children(
        1, [{"kind": "t", "name": "N"}], {"t": T})))
    # An own stop wrote its resulting state (the input copied through), so
    # the one ARCHITECTURE-§3.4 copy happens.
    assert tm.TABLE.values[n.state.name] == "begin Section"
    assert t2.state.name not in tm.TABLE.values


class Fussy(RT):
    @classmethod
    async def gen(cls, config, raw):
        raise InvalidField("name", "never good enough")    # raised bare

def test_gen_raises_bare_and_the_framework_prefixes_the_path():
    f, thy, sec, a, b, c = rbuild()
    with pytest.raises(InvalidField) as e:
        run(locked(f, thy._insert_children(
            2, [{"kind": "block", "name": "S2",
                 "children": [{"kind": "t", "name": "x"},
                              {"kind": "fussy", "name": "y"}]}],
            KINDS | {"fussy": Fussy})))
    assert e.value.raw_ast_path == "constructs[0].children[1]"

def test_duplicate_name_inside_a_children_list():
    f, thy, sec, a, b, c = rbuild()
    with pytest.raises(DuplicateName) as e:
        run(locked(f, thy._insert_children(
            2, [{"kind": "block", "name": "S2",
                 "children": [{"kind": "t", "name": "x"},
                              {"kind": "t", "name": "x"}]}], KINDS)))
    assert e.value.taken_by == "children[0]"
    assert e.value.raw_ast_path == "constructs[0].children[1]"


# --- amend ------------------------------------------------------------------

def test_amend_inherits_position_slot_identity_children():
    f, thy, sec, a, b, c = rbuild()
    run(c.evaluate_to(False))
    old_slot, old_identity, old_sbe = sec.state.name, sec.identity, \
        sec._state_before_ending.name
    EVENTS.clear()
    (s9,) = run(locked(f, thy._amend_children(
        sec, [{"kind": "block", "name": "S9"}], KINDS)))
    assert thy.sub_nodes[0] is s9 and s9.parent is thy
    assert s9.state.name == old_slot and s9.identity == old_identity
    assert s9.sub_nodes == [a, b] and a.parent is s9 and b.parent is s9
    assert sec.parent is None and sec.sub_nodes == []
    assert old_sbe in tm.TABLE.deleted            # the orphaned slot released
    # what old's own operations wrote is released too: its result (the
    # successor's input) and its beginning's output (a's input)
    assert c.state.name not in tm.TABLE.values
    assert a.state.name not in tm.TABLE.values
    gates_and_completed = [e for e in EVENTS if e[1] != "invalidated"]
    assert gates_and_completed == [
        ("Section", "deleting", "amend"),
        ("Theory", "removing_child", "Section", "amend"),
        ("Section", "removing_child", "a", "inheritance"),
        ("a", "inheriting", "S9"),
        ("Section", "removing_child", "b", "inheritance"),
        ("b", "inheriting", "S9"),
        ("Section", "deleted", "amend"),
        ("a", "inherited", "Section"),
        ("S9", "added_child", "a", "inheritance"),
        ("b", "inherited", "Section"),
        ("S9", "added_child", "b", "inheritance"),
        ("Theory", "added_child", "S9", "amend"),
        ("S9", "inserted"),
    ]
    # invalidated from the first child: exactly the ready a, b and c left ready
    assert set(events("invalidated")) == {("a", "invalidated", None),
                                          ("b", "invalidated", None),
                                          ("c", "invalidated", None)}
    assert st(a) is NOT_EVALUATED and st(b) is NOT_EVALUATED
    assert len(deletes()) == 1                    # one round trip releases all
    inv(f)

def test_amend_may_keep_the_name():
    f, thy, sec, a, b, c = rbuild()
    (s,) = run(locked(f, thy._amend_children(
        sec, [{"kind": "block", "name": "Section"}], KINDS)))
    assert thy.sub_nodes[0] is s

def test_amend_batch_follows_the_replacement():
    f, thy, sec, a, b, c = rbuild()
    s9, u = run(locked(f, thy._amend_children(
        sec, [{"kind": "block", "name": "S9"}, {"kind": "t", "name": "u"}],
        KINDS)))
    assert thy.sub_nodes == [s9, u, c] and u.parent is thy
    assert u.state.name not in tm.TABLE.values    # its predecessor is fresh

def test_amend_replacement_refuses_children_and_leaves():
    f, thy, sec, a, b, c = rbuild()
    with pytest.raises(UnexpectedChildren) as e:
        run(locked(f, thy._amend_children(
            sec, [{"kind": "block", "name": "S9",
                   "children": [{"kind": "t", "name": "x"}]}], KINDS)))
    assert not e.value.is_leaf
    with pytest.raises(ChildrenNotInheritable) as e:
        run(locked(f, thy._amend_children(
            sec, [{"kind": "t", "name": "L"}], KINDS)))
    assert (e.value.old_id, e.value.new_kind, e.value.children_count) == \
        ("Theory.Section", "t", 2)


# --- delete -----------------------------------------------------------------

def test_delete_fires_children_first_and_a_gate_can_veto():
    f, thy, sec, a, b, c = rbuild()
    run(locked(f, thy._delete_child(sec)))
    assert [e for e in EVENTS if e[1] in ("deleting", "deleted",
                                          "removing_child")] == [
        ("a", "deleting", "delete"),
        ("b", "deleting", "delete"),
        ("Section", "deleting", "delete"),
        ("Theory", "removing_child", "Section", "insert_or_delete"),
        ("a", "deleted", "delete"),
        ("b", "deleted", "delete"),
        ("Section", "deleted", "delete"),
    ]
    assert thy.sub_nodes == [c] and sec.parent is None
    assert len(deletes()) == 1                    # the subtree's states, one round trip
    inv(f)

class Veto(BadEdit):
    def _cause(self): return "vetoed."

class Stubborn(RT):
    def on_deleting(self, reason):
        raise Veto()

def test_gate_veto_aborts_with_forest_untouched():
    f, thy, sec, a, b, c = rbuild()
    s = Stubborn(sec, slot(), "s")
    sec.sub_nodes.append(s)
    with pytest.raises(Veto):
        run(locked(f, sec._delete_child(s)))
    assert s in sec.sub_nodes and s.parent is sec
    assert events("deleted") == []

class Buggy(RT):
    def on_inserted(self):
        raise InvalidName("oops")                # a TAT_Error from a completed hook

def test_completed_hook_raise_is_the_class_bug():
    f, thy, sec, a, b, c = rbuild()
    with pytest.raises(TAT_InternalError):
        run(locked(f, thy._insert_children(
            2, [{"kind": "t", "name": "u"}], {"t": Buggy})))


# --- move -------------------------------------------------------------------

def test_move_between_parents():
    f, thy, sec, a, b, c = rbuild()
    run(c.evaluate_to(False))
    EVENTS.clear()
    run(locked(f, sec._move_child(b, thy, 0)))   # to the front of the theory
    assert sec.sub_nodes == [a] and thy.sub_nodes == [b, sec, c]
    assert b.parent is thy
    # The destination-side copy survives: b's new input is written by the
    # theory's beginning, which stays ready.
    assert tm.TABLE.values[b.state.name] == "begin Theory"
    # Everything after b is downstream of the move and left ready, its
    # values released — "slot holds a value iff its writer is ready".
    assert st(b) is NOT_EVALUATED and st(a) is NOT_EVALUATED
    assert st(sec) == (NOT_EVALUATED, NOT_EVALUATED) and st(c) is NOT_EVALUATED
    assert sec._state_before_ending.name not in tm.TABLE.values
    assert [e for e in EVENTS if e[1] in ("moving", "removing_child",
                                          "added_child", "moved")] == [
        ("b", "moving", "Theory", 0),
        ("Section", "removing_child", "b", "move"),
        ("Theory", "added_child", "b", "move"),
        ("b", "moved", "Section", 1),
    ]

def test_move_within_one_parent():
    f, thy, sec, a, b, c = rbuild()
    run(c.evaluate_to(False))
    run(locked(f, sec._move_child(a, sec, 1)))
    assert sec.sub_nodes == [b, a]
    # b's input survives, written by the section's still-ready beginning;
    # a's input was copied from b's result and released with b.
    assert tm.TABLE.values[b.state.name] == "begin Section"
    assert a.state.name not in tm.TABLE.values
    assert st(a) is NOT_EVALUATED and st(b) is NOT_EVALUATED
    # the gate sees the post-removal index, the completed hook the old one
    assert ("a", "moving", "Section", 1) in EVENTS
    assert ("a", "moved", "Section", 0) in EVENTS
    inv(f)

def test_move_carries_the_subtree_reset():
    f, thy, sec, a, b, c = rbuild()
    run(c.evaluate_to(False))
    run(locked(f, thy._move_child(sec, thy, 1)))
    assert thy.sub_nodes == [c, sec]
    assert st(sec) == (NOT_EVALUATED, NOT_EVALUATED)
    assert st(a) is NOT_EVALUATED and st(b) is NOT_EVALUATED

def test_on_invalidated_distinguishes_the_operation():
    f, thy, sec, a, b, c = rbuild()
    run(c.evaluate_to(False))
    EVENTS.clear()
    run(a.evaluate_to(False, evaluate=False))    # invalidate from a on
    inv = events("invalidated")
    assert ("a", "invalidated", None) in inv
    assert ("Section", "invalidated", "ending") in inv
    # its opening still stands: the walk enters the block before a
    assert ("Section", "invalidated", "beginning") not in inv

def test_on_invalidated_fires_once_per_operation():
    f, thy, sec, a, b, c = rbuild()
    run(c.evaluate_to(False))
    EVENTS.clear()
    run(locked(f, thy._insert_children(         # everything after u leaves ready
        0, [{"kind": "t", "name": "u"}], KINDS)))
    inv = events("invalidated")
    assert inv.count(("Section", "invalidated", "beginning")) == 1
    assert inv.count(("Section", "invalidated", "ending")) == 1
    assert ("a", "invalidated", None) in inv and ("b", "invalidated", None) in inv


def test_blocked_beginning_reruns_when_unblocked():
    f = tm.OneTreeForest(tm.CONN)
    thy = Block(f, slot(), "Theory", slot()); f.sub_nodes.append(thy)
    d = T(thy, slot(), "d", fail=True)
    sec = Block(thy, slot(), "Sec", slot())
    a = T(sec, slot(), "a"); sec.sub_nodes.append(a)
    thy.sub_nodes += [d, sec]
    r = run(a.evaluate_to(False))                # strict: d stops, sec blocked
    assert r.stopped_at is d
    assert st(sec)[0] == CannotEvaluate(d) and sec.begin_runs == 0
    r = run(a.evaluate_to(True))                 # resumes past the obstacle
    assert sec.begin_runs == 1 and st(sec)[0] is READY and st(a) is READY
    assert tm.TABLE.values[a.state.name] == "begin Sec"

def test_failed_opening_repeated_pass_keeps_the_result():
    f, thy, sec, t1, t2, t3, t4 = tm.build(Section="begin")
    for _ in range(3):
        run(t4.evaluate_to(False))
    assert st(sec) == (CannotEvaluate(None), READY)
    assert tm.TABLE.values[sec.resulting_state().name] == "begin Theory"
    assert sec.begin_runs == 1                   # an own stop is not rerun


# --- the invariants, and the shapes that escaped every earlier sweep --------

def build_x_sec_c():
    """Theory > [x, Section > [a, b], c]: a nesting node right after x."""
    f = tm.OneTreeForest(tm.CONN)
    thy = Block(f, slot(), "Theory", slot()); f.sub_nodes.append(thy)
    x = T(thy, slot(), "x")
    sec = Block(thy, slot(), "Section", slot())
    a = T(sec, slot(), "a"); b = T(sec, slot(), "b"); sec.sub_nodes += [a, b]
    c = T(thy, slot(), "c")
    thy.sub_nodes += [x, sec, c]
    return f, thy, x, sec, a, b, c

def test_delete_before_a_nesting_successor_invalidates_it_whole():
    f, thy, x, sec, a, b, c = build_x_sec_c()
    run(c.evaluate_to(False)); inv(f)
    run(locked(f, thy._delete_child(x)))
    assert st(sec) == (NOT_EVALUATED, NOT_EVALUATED)
    assert st(a) is NOT_EVALUATED and st(b) is NOT_EVALUATED and st(c) is NOT_EVALUATED
    inv(f)
    run(c.evaluate_to(False))
    assert sec.begin_runs == 2 and a.runs == 2    # rerun against the new input
    inv(f)

def test_move_past_a_nesting_successor_invalidates_it_whole():
    f, thy, x, sec, a, b, c = build_x_sec_c()
    run(c.evaluate_to(False))
    run(locked(f, thy._move_child(x, thy, 2)))    # -> [Section, c, x]
    assert thy.sub_nodes == [sec, c, x]
    assert st(sec) == (NOT_EVALUATED, NOT_EVALUATED) and st(a) is NOT_EVALUATED
    assert len(deletes()) <= 2                    # one flush per walk
    inv(f)

def test_amend_with_a_nesting_first_child_invalidates_it_whole():
    f = tm.OneTreeForest(tm.CONN)
    thy = Block(f, slot(), "Theory", slot()); f.sub_nodes.append(thy)
    sec = Block(thy, slot(), "Section", slot())
    inner = Block(sec, slot(), "Inner", slot())
    a = T(inner, slot(), "a"); inner.sub_nodes.append(a)
    b = T(sec, slot(), "b"); sec.sub_nodes += [inner, b]
    thy.sub_nodes.append(sec)
    run(b.evaluate_to(False)); inv(f)
    (s9,) = run(locked(f, thy._amend_children(
        sec, [{"kind": "block", "name": "S9"}], {"block": Block, "t": T})))
    assert s9.sub_nodes == [inner, b]
    assert st(inner) == (NOT_EVALUATED, NOT_EVALUATED) and st(a) is NOT_EVALUATED
    inv(f)

def test_failed_opening_after_failed_ending_keeps_its_result():
    """Theory > [A(fails), B > [z], Y]; B's ending fails, then its beginning
    fails on its second run: the copy-through must not be released."""
    f = tm.OneTreeForest(tm.CONN)
    thy = Block(f, slot(), "Theory", slot()); f.sub_nodes.append(thy)
    a = T(thy, slot(), "A", fail=True)
    b = Block(thy, slot(), "B", slot(), fail_ending=True)
    z = T(b, slot(), "z"); b.sub_nodes.append(z)
    y = T(thy, slot(), "Y")
    thy.sub_nodes += [a, b, y]
    run(y.evaluate_to(True)); inv(f)
    assert st(b) == (READY, CannotEvaluate(None))
    run(y.evaluate_to(False)); inv(f)            # A stops; B's ending keeps its own stop
    assert st(b) == (CannotEvaluate(a), CannotEvaluate(None))
    b.fail_beginning = True
    run(y.evaluate_to(True)); inv(f)             # B's beginning reruns and fails
    assert st(b) == (CannotEvaluate(None), READY) and st(y) is READY
    assert (tm.TABLE.values[b.resulting_state().name]
            == tm.TABLE.values[b.state.name])

def test_own_stop_reruns_when_its_input_is_rewritten():
    """Theory > [A(fails), P, X(fails), Y]: P, blocked then unblocked, reruns
    and rewrites X's input — X, an own stop, must run again on it."""
    f = tm.OneTreeForest(tm.CONN)
    thy = Block(f, slot(), "Theory", slot()); f.sub_nodes.append(thy)
    a = T(thy, slot(), "A", fail=True); p = T(thy, slot(), "P")
    x = T(thy, slot(), "X", fail=True); y = T(thy, slot(), "Y")
    thy.sub_nodes += [a, p, x, y]
    run(y.evaluate_to(True)); inv(f)
    assert (p.runs, x.runs) == (1, 1)
    run(y.evaluate_to(False)); inv(f)            # A stops: P blocked, X keeps its own stop
    assert st(p) == CannotEvaluate(a) and st(x) == CannotEvaluate(None)
    run(y.evaluate_to(True)); inv(f)             # P reruns, so X does too
    assert (p.runs, x.runs) == (2, 2) and st(x) == CannotEvaluate(None)
    run(y.evaluate_to(True)); inv(f)             # nothing rewritten: nothing reruns
    assert (p.runs, x.runs) == (2, 2)

def test_removing_an_own_stop_behind_a_blocked_predecessor_releases_its_copy():
    """Theory > [A(fails), S > [z], B(fails), C]: after a strict pass S's
    ending is blocked while B keeps its own stop; deleting or moving B must
    not leave B's copy-through in C's input, whose writer is now S."""
    def build():
        f = tm.OneTreeForest(tm.CONN)
        thy = Block(f, slot(), "Theory", slot()); f.sub_nodes.append(thy)
        a = T(thy, slot(), "A", fail=True)
        s = Block(thy, slot(), "S", slot())
        z = T(s, slot(), "z"); s.sub_nodes.append(z)
        b = T(thy, slot(), "B", fail=True); c = T(thy, slot(), "C")
        thy.sub_nodes += [a, s, b, c]
        run(c.evaluate_to(True)); run(c.evaluate_to(False)); inv(f)
        assert st(s)[1] == CannotEvaluate(a) and st(b) == CannotEvaluate(None)
        return f, thy, s, b, c
    f, thy, s, b, c = build()
    run(locked(f, thy._delete_child(b)))
    assert c.state.name not in tm.TABLE.values
    inv(f)
    f, thy, s, b, c = build()
    run(locked(f, thy._move_child(b, s, 1)))
    assert c.state.name not in tm.TABLE.values
    inv(f)

def test_the_root_has_no_position():
    f, thy, sec, a, b, c = rbuild()
    with pytest.raises(TAT_InternalError):
        run(f.evaluate_to(False, evaluate=False))

def test_own_stop_survives_being_blocked():
    f = tm.OneTreeForest(tm.CONN)
    thy = Block(f, slot(), "Theory", slot()); f.sub_nodes.append(thy)
    d = T(thy, slot(), "d", fail=True); e = T(thy, slot(), "e", fail=True)
    g = T(thy, slot(), "g")
    thy.sub_nodes += [d, e, g]
    for ignore in (True, True, False, True, False, True):
        run(g.evaluate_to(ignore))
        assert e.runs == 1 and st(e) == CannotEvaluate(None)   # never rerun, never misreported
        inv(f)

def test_random_interleavings_keep_the_invariants():
    kinds = {"t": T, "block": Block}
    for seed in range(300):
        rng = random.Random(seed)
        f, thy, sec, t1, t2, t3, t4 = tm.build(T1=rng.random() < 0.3)
        counter = 0

        def fresh(kind):
            nonlocal counter
            counter += 1
            raw = {"kind": kind, "name": f"n{counter}"}
            if rng.random() < 0.3:
                raw["fail"] = True
            return raw

        async def step():
            nodes = f._all_nodes()
            blocks = [n for n in nodes if isinstance(n, M.NonLeaf_Node)]
            movable = [n for n in nodes if n is not thy]
            op = rng.choice(["insert", "delete", "amend", "move",
                             "evaluate", "invalidate", "flip"])
            if op == "flip" and movable:     # a verdict changes between runs; not the
                n = rng.choice(movable)      # tree root's, whose input nobody writes (OPEN_QUESTIONS §1)
                if isinstance(n, Block):
                    which = rng.choice(["fail_beginning", "fail_ending"])
                    setattr(n, which, not getattr(n, which))
                else:
                    n.fail = not n.fail
            elif op == "insert":
                p = rng.choice(blocks)
                raws = [fresh(rng.choice(["t", "block"]))
                        for _ in range(rng.randint(1, 2))]
                async with f.lock:
                    await p._insert_children(rng.randint(0, len(p.sub_nodes)), raws, kinds)
            elif op == "delete" and movable:
                n = rng.choice(movable)
                async with f.lock:
                    await n.parent._delete_child(n)
            elif op == "amend" and movable:
                n = rng.choice(movable)
                kind = "block" if isinstance(n, M.NonLeaf_Node) else "t"
                async with f.lock:
                    await n.parent._amend_children(n, [fresh(kind)], kinds)
            elif op == "move" and movable:
                n = rng.choice(movable)
                dests = [b for b in blocks if b not in M._tree_order(n)]
                if dests:
                    p = rng.choice(dests)
                    i = rng.randint(0, len(p.sub_nodes) - (1 if p is n.parent else 0))
                    async with f.lock:
                        await n.parent._move_child(n, p, i)
            elif op == "evaluate":
                await rng.choice(nodes).evaluate_to(rng.random() < 0.5)
            elif op == "invalidate":
                await rng.choice(nodes).evaluate_to(False, evaluate=False)

        for _ in range(60):                  # the budget at which the invariants catch
            run(step())                      # each of the three release-side mechanisms
            inv(f)


def test_move_refusals():
    f, thy, sec, a, b, c = rbuild()
    with pytest.raises(MoveIntoOwnSubtree) as e:
        run(locked(f, thy._move_child(sec, sec, 0)))
    assert (e.value.id, e.value.destination) == \
        ("Theory.Section", "Theory.Section")
    mk = RT(sec, slot(), "c"); sec.sub_nodes.append(mk)   # a second "c"
    with pytest.raises(DuplicateName) as e:
        run(locked(f, sec._move_child(mk, thy, 2)))
    assert e.value.taken_by == "Theory.c"
