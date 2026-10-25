"""The placement check (PLUGIN_SYSTEM §2; MODULE_STRUCTURE §4.1) on stand-ins
against the fake state slot table: the walk — the node and every ancestor
in its tree, outermost first, the ancestor's `cannot_hold` then the node's
`cannot_stand_under`, with the depth —, the first refusal as the message,
its head RENDER_BASELINES §3's form line with the kind's article, the hook
never run, a refused block's children `not_evaluated`; an insert, a move
and an amend into a refused place accepted at the edit and refused at
evaluation, neither method asked at the edit; a theory's own beginning
never refused.  The forest's shape at the edit is test_session_theory.py's;
the plugin's answers are test_common.py's.
Run: python -m pytest test/test_placement.py
"""

import stand_ins
import test_model as tm
import test_session_theory as ts
from baselines import composed_refusal
from invariants import assert_invariants, assert_store_mirrors
from isabelle_theory_agent import edit, model as M
from isabelle_theory_agent.model import NOT_EVALUATED, READY_CLEAN
from test_model import locked, run
from test_session_theory import Forest_Under_Test, session, theory

table = ts.table                    # the fake state slot table and the fake wire, per test

CALLS: list[tuple] = []             # every question asked of a stand-in, in order: (receiver, method, argument, depth)


class Asked:
    """What the stand-ins record and answer: `hold`, the remedy the node's
    `cannot_hold` answers for every descendant; `stand`, the remedies its
    `cannot_stand_under` answers, by ancestor; None admits."""
    def __init__(self, *args, **rest):
        super().__init__(*args, **rest)
        self.hold, self.stand = None, {}

    def cannot_hold(self, descendant, depth):
        CALLS.append((self, "cannot_hold", descendant, depth))
        return self.hold

    def cannot_stand_under(self, ancestor, depth):
        CALLS.append((self, "cannot_stand_under", ancestor, depth))
        return self.stand.get(ancestor)


class Asking_Block(Asked, tm.Block):
    pass


class Asking_Leaf(Asked, tm.T):
    pass


class Asking_Theory(Asked, ts.Fake_Theory):
    pass


KINDS = {**ts.KINDS, "theory": Asking_Theory, "block": Asking_Block, "t": Asking_Leaf, "owl": Asking_Leaf}


def insert(f, parent, index, raws):
    return run(locked(f, edit.insert(parent, index, raws)))


def node(kind, name, *children):
    return {"kind": kind, "name": name, **({"children": list(children)} if children else {})}


def tree():
    """session_Arith > theory_X > block_B1 > block_B2 > t_n; the forest and the four."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X") | {"children": [
        node("block", "B1", node("block", "B2", node("t", "n")))]})])
    (x,) = s.sub_nodes
    (b1,) = x.sub_nodes
    (b2,) = b1.sub_nodes
    (n,) = b2.sub_nodes
    CALLS.clear()
    return f, x, b1, b2, n


def inv(f):
    assert_invariants(f, tm.TABLE)
    assert_store_mirrors(f, shape=ts.shape)


# --- the walk ---------------------------------------------------------------

def test_the_walk_asks_every_ancestor_in_the_tree_outermost_first_both_sides_with_the_depth():
    """For `n` under theory > B1 > B2: six questions, the theory's first and
    its parent's last, at each ancestor the ancestor's `cannot_hold` of `n`
    then `n`'s `cannot_stand_under` of the ancestor, the depth the distance;
    for `B2`, four; a theory has no ancestor in its tree, and a session is
    never asked."""
    f, x, b1, b2, n = tree()
    assert n._refusal() is None
    assert CALLS == [(x, "cannot_hold", n, 3), (n, "cannot_stand_under", x, 3),
                     (b1, "cannot_hold", n, 2), (n, "cannot_stand_under", b1, 2),
                     (b2, "cannot_hold", n, 1), (n, "cannot_stand_under", b2, 1)]
    CALLS.clear()
    assert b2._refusal() is None
    assert CALLS == [(x, "cannot_hold", b2, 2), (b2, "cannot_stand_under", x, 2),
                     (b1, "cannot_hold", b2, 1), (b2, "cannot_stand_under", b1, 1)]
    CALLS.clear()
    (s,) = f.sub_nodes
    assert x._refusal() is None and s._refusal() is None and CALLS == []


def test_the_first_refusal_ends_the_check_and_is_told_with_the_head():
    """The first remedy answered ends the check: nothing below the refusing
    ancestor is asked, and at that ancestor the container's answer comes
    before the node's; the message is RENDER_BASELINES §3's form line, the
    ancestor by its full id.  An outer ancestor's refusal is told before an
    inner one's; the node's own side refuses under an admitting
    `cannot_hold`."""
    f, x, b1, b2, n = tree()
    b1.hold = "Hold off."
    assert n._refusal() == composed_refusal("t", f.full_id(b1), "Hold off.")
    assert CALLS == [(x, "cannot_hold", n, 3), (n, "cannot_stand_under", x, 3), (b1, "cannot_hold", n, 2)]
    CALLS.clear()
    n.stand[b1] = "Stand off."                                   # both sides at one ancestor: the container's is told
    assert n._refusal() == composed_refusal("t", f.full_id(b1), "Hold off.") and len(CALLS) == 3
    CALLS.clear()
    b1.hold = None                                               # the node's own side, under an admitting `cannot_hold`
    assert n._refusal() == composed_refusal("t", f.full_id(b1), "Stand off.")
    assert CALLS == [(x, "cannot_hold", n, 3), (n, "cannot_stand_under", x, 3),
                     (b1, "cannot_hold", n, 2), (n, "cannot_stand_under", b1, 2)]
    CALLS.clear()
    n.stand.clear()
    b2.hold, x.hold = "Inner.", "Outer."                         # outermost first
    assert n._refusal() == composed_refusal("t", f.full_id(x), "Outer.")
    assert CALLS == [(x, "cannot_hold", n, 3)]


def test_the_head_takes_the_kind_s_article():
    f, x, b1, b2, n = tree()
    (owl,) = insert(f, b2, 1, [node("owl", "o")])
    b2.hold = "Hold off."
    assert owl._refusal() == composed_refusal("owl", f.full_id(b2), "Hold off.")
    assert owl._refusal().startswith("An `owl` cannot stand under `")
    assert n._refusal().startswith("A `t` cannot stand under `")


# --- at evaluation ----------------------------------------------------------

def test_a_refused_leaf_is_cannot_evaluate_without_running_and_a_move_makes_it_pass():
    """A refused node is built and kept; evaluating it gives a `CannotEvaluate`
    carrying the refusal, the hook never run, its `operation` record carrying
    the message (LOGGING.md §4); moved where no answer refuses it, it runs."""
    f, x, b1, b2, n = tree()
    b2.hold = "Hold off."
    run(x.evaluate_to(None, True))
    expected = composed_refusal("t", f.full_id(b2), "Hold off.")
    assert n.runs == 0 and isinstance(n._status, M.CannotEvaluate)
    assert [m.unicode for m in n._status.messages] == [expected]
    [record] = [r["data"] for r in stand_ins.records("evaluation")
                if r["data"].get("node") == f.full_id(n) and "ran" in r["data"]]
    assert record["ran"] is False and record["status"] == "cannot_evaluate" and record["messages"] == [expected]
    inv(f)
    run(locked(f, edit.move(n, b1, 0)))
    assert n._status is NOT_EVALUATED
    run(x.evaluate_to(None, True))
    assert n.runs == 1 and n._status == READY_CLEAN
    inv(f)


def test_a_refused_block_is_refused_at_its_beginning_and_its_children_do_not_run():
    """A refused `StdBlock`: its beginning's hook never runs, the status
    carries the refusal, its children stay `not_evaluated`; moved out of
    the refusing ancestor, it and its children run."""
    f, x, b1, b2, n = tree()
    b1.hold = "Hold off."
    run(x.evaluate_to(None, True))
    assert b2.begin_runs == 0 and n.runs == 0
    assert isinstance(b2.evaluation_status_beginning, M.CannotEvaluate)
    assert [m.unicode for m in b2.evaluation_status_beginning.messages] == [composed_refusal("block", f.full_id(b1), "Hold off.")]
    assert n._status is NOT_EVALUATED
    inv(f)
    run(locked(f, edit.move(b2, x, 0)))
    run(x.evaluate_to(None, True))
    assert b2.begin_runs == 1 and n.runs == 1
    assert b2.evaluation_status_beginning == READY_CLEAN and n._status == READY_CLEAN
    inv(f)


def test_a_theory_s_own_beginning_is_never_refused():
    """A theory refusing everything below it, and refusing to stand under its
    session: its beginning runs, its child is refused."""
    f, x, b1, b2, n = tree()
    (s,) = f.sub_nodes
    x.hold, x.stand[s] = "Hold off.", "Stand off."
    run(x.evaluate_to(None, True))
    assert x.evaluation_status_beginning == ts.READY and b1.begin_runs == 0
    assert [m.unicode for m in b1.evaluation_status_beginning.messages] == [composed_refusal("block", f.full_id(x), "Hold off.")]
    inv(f)


# --- at the edit ------------------------------------------------------------

def test_an_insert_a_move_and_an_amend_into_a_refused_place_succeed_at_the_edit_and_are_refused_at_evaluation():
    """Neither method is asked at the edit: a node inserted, moved or amended
    into a place an ancestor refuses enters the forest, and each is refused
    at evaluation, the ancestor named."""
    f, x, b1, b2, n = tree()
    b1.hold = "Hold off."
    (m,) = insert(f, b1, 1, [node("t", "m")])
    (outside,) = insert(f, x, 1, [node("t", "outside")])
    run(locked(f, edit.move(outside, b1, 2)))
    (m2,) = run(locked(f, edit.amend(m, [node("t", "m2")])))
    assert CALLS == [] and b1.sub_nodes == [b2, m2, outside] and x.sub_nodes == [b1]
    inv(f)
    run(x.evaluate_to(None, True))
    expected = composed_refusal("t", f.full_id(b1), "Hold off.")
    for refused in (m2, outside):
        assert refused.runs == 0 and [m_.unicode for m_ in refused._status.messages] == [expected]
    assert b2.begin_runs == 0 and n._status is NOT_EVALUATED
    inv(f)


def test_an_amend_passing_children_on_checks_them_at_their_new_parent():
    """An amend replacing a block passes its children on: a child the
    replacement refuses is refused at the next evaluation; the other way, a
    child refused under the old parent runs under the new."""
    f, x, b1, b2, n = tree()
    run(x.evaluate_to(None, True))
    assert n.runs == 1
    (c,) = run(locked(f, edit.amend(b2, [node("block", "C")])))
    assert n.parent is c
    c.hold = "Hold off."
    run(x.evaluate_to(None, True))
    assert n.runs == 1 and [m.unicode for m in n._status.messages] == [composed_refusal("t", f.full_id(c), "Hold off.")]
    (back,) = run(locked(f, edit.amend(c, [node("block", "B2")])))
    assert n.parent is back
    run(x.evaluate_to(None, True))
    assert n.runs == 2 and n._status == READY_CLEAN
    inv(f)
