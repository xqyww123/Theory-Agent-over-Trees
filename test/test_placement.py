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

class Inside_Top(tm.T):              # within a class other than `Theory`
    placement = M.Placement(within="Top_Block", through=())

class Chapter_Block(Section_Block):  # bears `Section_Block` through its base; its own kind is no `through` word
    pass

class Aside(tm.T):                   # its classes declared against the table's order
    placement = M.Placement(within="Theory", through=("Top_Block", "Section_Block"))


KINDS = {**ts.KINDS, "note": Note, "top": Top, "section": Section_Block, "subsection": Section_Block,
         "top_block": Top_Block, "inside_top": Inside_Top, "chapter": Chapter_Block, "aside": Aside}


def insert(f, parent, index, raws):
    return run(locked(f, edit.insert(parent, index, raws)))


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
    assert_store_mirrors(f, shape=ts.shape)


# --- the function and its sentences -----------------------------------------

def test_the_sentences_are_render_baselines():
    """§2's edit-time pair, from real edits, and §3's evaluation pair,
    verbatim: `{through}` the two kinds of one class, an empty `through`
    ending at "directly"; ids full.  The kinds of `{through}` come in the
    kind table's order, whatever order the declaration names its classes."""
    f, s, x, sec, b = arith()
    edit_time = fenced_lines(BASELINES, "2.")
    evaluation = fenced_lines(BASELINES, "3.")
    for parent, construct in ((s, node("note", "n")), (f, node("top", "t"))):
        with pytest.raises(BadPlacement) as e:
            insert(f, parent, 0, [construct])
        assert e.value._cause() in edit_time
    for line in (placement_refusal(Note, "note", b), placement_refusal(Top, "top", sec)):
        assert line in evaluation
    assert placement_refusal(Aside, "aside", b) == (
        "A node of kind `aside` cannot stand inside `session_Arith.theory_X.section_S.block_B`, a node of kind"
        " `block`; it stands inside a node of kind `theory`, directly or under nodes of kind `section`,"
        " `subsection` or `top_block`.")


def test_the_walk_admits_within_through_and_names_the_nearest_blocker():
    """Admitted at the theory and under any depth of the classes `through`,
    the class naming itself included, and under a subclass of one;
    refused at the nearest ancestor of another class — two nested ones,
    the inner named, also with an admitted node between it and the place;
    a `within` other than `Theory` admits under its class and names its
    own kind; the framework's classes declare nothing and are never
    refused."""
    f, s, x, sec, b = arith()
    (sub,) = insert(f, sec, 0, [node("subsection", "T", node("section", "U"))])
    (u,) = sub.sub_nodes
    for place in (x, sec, sub, u):
        assert placement_refusal(Note, "note", place) is None
    (c,) = insert(f, b, 0, [node("block", "C", node("section", "V"))])
    (v,) = c.sub_nodes
    for place in (c, v):
        refusal = placement_refusal(Note, "note", place)
        assert refusal is not None and f"inside `{f.full_id(c)}`, a node of kind `block`;" in refusal
    top_block, chapter = insert(f, x, 0, [node("top_block", "K"), node("chapter", "H")])
    assert placement_refusal(Note, "note", chapter) is None
    assert placement_refusal(Inside_Top, "inside_top", top_block) is None
    assert placement_refusal(Inside_Top, "inside_top", x) == (
        "A node of kind `inside_top` cannot stand inside `session_Arith.theory_X`, a node of kind `theory`;"
        " it stands inside a node of kind `top_block`, directly.")
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
    (blk,) = run(locked(f, edit.amend(sec, [node("block", "S")])))
    assert n.parent is blk
    run(x.evaluate_to(None, True))
    assert n.runs == 1 and isinstance(n._status, M.CannotEvaluate)
    (back,) = run(locked(f, edit.amend(blk, [node("section", "S")])))
    assert n.parent is back
    run(x.evaluate_to(None, True))
    assert n.runs == 2 and n._status == READY_CLEAN
    inv(f)


# --- at edit time -----------------------------------------------------------

@pytest.mark.parametrize("kind", ["note", "top", "section", "top_block"])
def test_under_a_session_or_the_root_every_edit_is_refused(kind):
    """Under an `Unchained_Node`, which no evaluation reaches, an insert,
    an amend, a move and a session's inline child are refused with
    `BadPlacement`, the parent's full id and the placement's kind words
    its fields; the forest is unchanged."""
    f, s, x, sec, b = arith()
    words = M.placement_kinds(KINDS[kind].placement, KINDS)
    construct = node(kind, "n")
    def refused(parent_id, call, raw_ast_path="constructs[0]"):
        with pytest.raises(BadPlacement) as e:
            run(locked(f, call))
        assert (e.value.kind, e.value.parent_id, e.value.raw_ast_path) == (kind, parent_id, raw_ast_path)
        assert (e.value.within, e.value.through) == words
    for parent, parent_id in ((s, "session_Arith"), (f, "Sessions")):
        refused(parent_id, edit.insert(parent, 0, [construct]))
    (y,) = insert(f, s, 1, [theory("Y")])
    refused("session_Arith", edit.amend(y, [construct]))
    refused("session_Other", edit.insert(f, 1, [session("Other", construct)]), "constructs[0].children[0]")
    (n,) = insert(f, x, 0, [construct])
    for parent, parent_id in ((s, "session_Arith"), (f, "Sessions")):
        refused(parent_id, edit.move(n, parent, 0), None)
    assert n.parent is x and f.sub_nodes == [s] and s.sub_nodes == [x, y]
    inv(f)
