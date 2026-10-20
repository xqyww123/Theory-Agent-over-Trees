"""Where a plugin's node may stand (PLUGIN_SYSTEM §2): `placement_refusal`
on stand-ins, its two sentences against RENDER_BASELINES §2 and §3, the
check at evaluation — a misplaced `Leaf` and a misplaced `StdBlock`, the
hook never run — and at edit time under a `Session` and under the root,
against the fake state slot table.  The registration and load checks are
test_plugin.py's; the shipped classes' declarations test_common.py's.
Run: python -m pytest test/test_placement.py
"""

import pytest

import stand_ins
import test_model as tm
import test_session_theory as ts
from baselines import DOCS, fenced_lines
from invariants import assert_invariants, assert_store_mirrors
from isabelle_theory_agent import edit, model as M
from isabelle_theory_agent.exceptions import BadPlacement
from isabelle_theory_agent.model import NOT_EVALUATED, READY_CLEAN, placement_refusal
from test_model import locked, run
from test_session_theory import Forest_Under_Test, session, theory

table = ts.table                    # the fake state slot table and the fake wire, per test
BASELINES = DOCS / "RENDER_BASELINES.md"


class Note(tm.T):
    placement = M.Placement(within="Theory", through=("Section_Block",))

class Top(tm.T):
    placement = M.Placement(within="Theory", through=())

class Section_Block(tm.Block):      # a class of two kinds, nesting in itself
    placement = M.Placement(within="Theory", through=("Section_Block",))

class Top_Block(tm.Block):
    placement = M.Placement(within="Theory", through=())


KINDS = {**ts.KINDS, "note": Note, "top": Top, "section": Section_Block, "subsection": Section_Block,
         "top_block": Top_Block}


def insert(f, parent, index, raws):
    return run(locked(f, edit.insert(parent, index, raws, KINDS)))


def node(kind, name, *children, **fields):
    return {"kind": kind, "name": name, **({"children": list(children)} if children else {}), **fields}


def arith(theory_kind="theory"):
    """session_Arith > theory_X > section_S > block_B; the forest and the four."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind=theory_kind) | {"children": [
        node("section", "S", node("block", "B"))]})])
    (x,) = s.sub_nodes
    (sec,) = x.sub_nodes
    (b,) = sec.sub_nodes
    return f, s, x, sec, b


def inv(f):
    assert_invariants(f, tm.TABLE)
    assert_store_mirrors(f, KINDS, shape=ts.shape)


# --- the function and its sentences -----------------------------------------

def test_the_sentences_are_render_baselines():
    """§2's edit-time pair and §3's evaluation pair, verbatim: `{through}`
    the two kinds of one class in table order, an empty `through` ending
    at "directly"; ids full."""
    f, s, x, sec, b = arith()
    edit_time = fenced_lines(BASELINES, "2.")
    evaluation = fenced_lines(BASELINES, "3.")
    for line in (placement_refusal(Note, "note", s), placement_refusal(Top, "top", f)):
        assert line in edit_time
    for line in (placement_refusal(Note, "note", b), placement_refusal(Top, "top", sec)):
        assert line in evaluation
    with pytest.raises(BadPlacement) as e:
        insert(f, s, 0, [node("note", "n")])
    assert e.value.sentence == placement_refusal(Note, "note", s)


def test_the_walk_admits_within_through_and_names_the_nearest_blocker():
    """Admitted at the theory and under any depth of the classes `through`,
    the class naming itself included; refused at the nearest ancestor of
    another class — two nested ones, the inner named; the framework's
    classes declare nothing and are never refused."""
    f, s, x, sec, b = arith()
    (sub,) = insert(f, sec, 0, [node("subsection", "T", node("section", "U"))])
    (u,) = sub.sub_nodes
    for place in (x, sec, sub, u):
        assert placement_refusal(Note, "note", place) is None
    (c,) = insert(f, b, 0, [node("block", "C")])
    refusal = placement_refusal(Note, "note", c)
    assert refusal is not None and f"`{f.full_id(c)}`, a node of kind `block`" in refusal
    assert placement_refusal(Top, "top", sec) is not None and placement_refusal(Top, "top", x) is None
    assert placement_refusal(M.Theory, "theory", b) is None and placement_refusal(M.Session, "session", x) is None


def test_the_blocker_is_named_by_its_full_id_which_resolves_to_it():
    """The id in a refusal is the full one: a second `block_B` elsewhere
    leaves it unchanged, and it resolves to the node named."""
    f, s, x, sec, b = arith()
    (other,) = insert(f, x, 1, [node("block", "B")])
    for blocker in (b, other):
        full = f.full_id(blocker)
        assert f.resolve(full) is blocker
        assert f"inside `{full}`," in placement_refusal(Note, "note", blocker)
    assert f.full_id(other) == "session_Arith.theory_X.block_B"
    assert f.full_id(b) == "session_Arith.theory_X.section_S.block_B"


# --- at evaluation ----------------------------------------------------------

def test_a_misplaced_leaf_is_refused_at_evaluation_and_a_move_makes_it_pass():
    """Inside a theory a misplaced node is built and kept; evaluating it
    gives a `CannotEvaluate` carrying the refusal, the hook never run, its
    `operation` record carrying the messages (LOGGING.md §4); moved to
    where its class admits it, it runs."""
    f, s, x, sec, b = arith("fake_theory")
    (n,) = insert(f, b, 0, [node("note", "n")])
    run(x.evaluate_to(None, True))
    assert n.runs == 0
    assert isinstance(n._status, M.CannotEvaluate)
    assert [m.unicode for m in n._status.messages] == [placement_refusal(Note, "note", b)]
    [record] = [r["data"] for r in stand_ins.records("evaluation") if r["data"].get("node") == f.full_id(n)]
    assert record["ran"] is False and record["status"] == "cannot_evaluate"
    assert record["messages"] == [placement_refusal(Note, "note", b)]       # logged though no hook ran
    inv(f)
    run(locked(f, edit.move(n, sec, 0)))
    assert n._status is NOT_EVALUATED
    run(x.evaluate_to(None, True))
    assert n.runs == 1 and n._status == READY_CLEAN
    inv(f)


def test_a_misplaced_block_is_refused_at_its_beginning_and_its_children_do_not_run():
    """A misplaced `StdBlock`: its beginning's hook never runs, the status
    carries the refusal, its children stay `not_evaluated`; moved to the
    theory's top level, it and its children run."""
    f, s, x, sec, b = arith("fake_theory")
    (blk,) = insert(f, sec, 0, [node("top_block", "K", node("t", "inner"))])
    (inner,) = blk.sub_nodes
    run(x.evaluate_to(None, True))
    assert blk.begin_runs == 0 and inner.runs == 0
    assert isinstance(blk.evaluation_status_beginning, M.CannotEvaluate)
    assert [m.unicode for m in blk.evaluation_status_beginning.messages] == [
        placement_refusal(Top_Block, "top_block", sec)]
    assert inner._status is NOT_EVALUATED
    inv(f)
    run(locked(f, edit.move(blk, x, 0)))
    run(x.evaluate_to(None, True))
    assert blk.begin_runs == 1 and inner.runs == 1
    assert blk.evaluation_status_beginning == READY_CLEAN and inner._status == READY_CLEAN
    inv(f)


def test_an_amend_passing_children_on_checks_them_at_their_new_parent():
    """An amend replacing a block by one of another class passes its
    children on: a child the new parent's class does not admit is refused
    at the next evaluation; the other way, a child refused under the old
    parent runs under the new."""
    f, s, x, sec, b = arith("fake_theory")
    (n,) = insert(f, sec, 0, [node("note", "n")])
    run(x.evaluate_to(None, True))
    assert n.runs == 1
    (blk,) = run(locked(f, edit.amend(sec, [node("block", "S")], KINDS)))
    assert n.parent is blk
    run(x.evaluate_to(None, True))
    assert n.runs == 1 and isinstance(n._status, M.CannotEvaluate)
    (back,) = run(locked(f, edit.amend(blk, [node("section", "S")], KINDS)))
    assert n.parent is back
    run(x.evaluate_to(None, True))
    assert n.runs == 2 and n._status == READY_CLEAN
    inv(f)


# --- at edit time -----------------------------------------------------------

@pytest.mark.parametrize("kind", ["note", "top", "section", "top_block"])
def test_under_a_session_or_the_root_every_edit_is_refused(kind):
    """Under an `Unchained_Node`, which no evaluation reaches, an insert,
    an amend, a move and a session's inline child are refused with
    `BadPlacement`, the parent named; the forest is unchanged."""
    f, s, x, sec, b = arith()
    cls = KINDS[kind]
    construct = node(kind, "n")
    for parent in (s, f):
        expected = placement_refusal(cls, kind, parent)
        with pytest.raises(BadPlacement) as e:
            insert(f, parent, 0, [construct])
        assert e.value.sentence == expected and e.value.raw_ast_path == "constructs[0]"
    (y,) = insert(f, s, 1, [theory("Y")])
    with pytest.raises(BadPlacement) as e:
        run(locked(f, edit.amend(y, [construct], KINDS)))
    assert e.value.sentence == placement_refusal(cls, kind, s)
    with pytest.raises(BadPlacement) as e:
        insert(f, f, 1, [session("Other", construct)])
    assert e.value.sentence == placement_refusal(cls, kind, s).replace("session_Arith", "session_Other")
    (n,) = insert(f, x, 0, [construct])
    for parent in (s, f):
        with pytest.raises(BadPlacement) as e:
            run(locked(f, edit.move(n, parent, 0)))
        assert e.value.sentence == placement_refusal(cls, kind, parent)
    assert n.parent is x and f.sub_nodes == [s] and s.sub_nodes == [x, y]
    inv(f)
