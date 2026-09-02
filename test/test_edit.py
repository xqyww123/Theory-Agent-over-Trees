"""The four-step edit build (MODULE_STRUCTURE §4.1): construct detached,
gates, commit, completed events — atomicity, hook order, the exception
paths, amend inheritance, move.  Run: python -m pytest test/test_edit.py
"""

import pytest

import test_model as tm
from test_model import Block, T, locked, run, slot, st

import isabelle_theory_agent.model as M
from isabelle_theory_agent.exceptions import (
    BadEdit, ChildrenNotInheritable, DuplicateName, InvalidField,
    InvalidName, MalformedRawAST, MissingField, MoveIntoOwnSubtree,
    TAT_InternalError, UnexpectedChildren, UnknownKind)
from isabelle_theory_agent.model import (
    NOT_EVALUATED, READY, CannotEvaluate, Location)


@pytest.fixture(autouse=True)
def table(monkeypatch):
    tm.TABLE.values.clear(); tm.TABLE.deleted.clear()
    tm.TABLE.install(monkeypatch)
    EVENTS.clear()


# --- recording node classes -------------------------------------------------

EVENTS: list[tuple] = []

class Recording:
    def on_invalidated(self): EVENTS.append((self.name, "invalidated"))
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
    assert e.value.raw_ast_path == "nodes[1].children[0]"
    assert e.value.kind == "wrong" and e.value.available_kinds == ["t", "block"]
    assert thy.sub_nodes == before and EVENTS == []      # forest untouched
    assert tm.TABLE.values == before_table               # and nothing remote
    assert tm.TABLE.deleted == before_deleted

def test_duplicate_name_against_sibling_and_batch():
    f, thy, sec, a, b, c = rbuild()
    with pytest.raises(DuplicateName) as e:
        run(locked(f, thy._insert_children(
            2, [{"kind": "t", "name": "c"}], KINDS)))
    assert e.value.taken_by == "Theory.c" and e.value.raw_ast_path == "nodes[0]"
    with pytest.raises(DuplicateName) as e:
        run(locked(f, thy._insert_children(
            2, [{"kind": "t", "name": "z"}, {"kind": "t", "name": "z"}], KINDS)))
    assert e.value.taken_by == "nodes[0]" and e.value.raw_ast_path == "nodes[1]"

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
    assert e.value.raw_ast_path == "nodes[0]"
    with pytest.raises(UnexpectedChildren) as e:
        run(insert({"kind": "t", "name": "x", "children": []}))
    assert e.value.is_leaf

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
    assert e.value.raw_ast_path == "nodes[0].children[1]"

def test_duplicate_name_inside_a_children_list():
    f, thy, sec, a, b, c = rbuild()
    with pytest.raises(DuplicateName) as e:
        run(locked(f, thy._insert_children(
            2, [{"kind": "block", "name": "S2",
                 "children": [{"kind": "t", "name": "x"},
                              {"kind": "t", "name": "x"}]}], KINDS)))
    assert e.value.taken_by == "children[0]"
    assert e.value.raw_ast_path == "nodes[0].children[1]"


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
    assert sec.parent is None
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
    # invalidated from the first child: the ready a, b and c all left ready
    assert set(events("invalidated")) >= {("a", "invalidated"),
                                          ("b", "invalidated"),
                                          ("c", "invalidated")}
    assert st(a) is NOT_EVALUATED and st(b) is NOT_EVALUATED

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

def test_move_carries_the_subtree_reset():
    f, thy, sec, a, b, c = rbuild()
    run(c.evaluate_to(False))
    run(locked(f, thy._move_child(sec, thy, 1)))
    assert thy.sub_nodes == [c, sec]
    assert st(sec) == (NOT_EVALUATED, NOT_EVALUATED)
    assert st(a) is NOT_EVALUATED and st(b) is NOT_EVALUATED

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
