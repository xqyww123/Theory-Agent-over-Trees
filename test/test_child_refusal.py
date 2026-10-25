"""A nesting node that refuses children (MODULE_STRUCTURE §4.1; PLUGIN_SYSTEM
§2), on a stand-in answering as a `Lifting_Closing` block whose setup was
not made does: `refuses_children()` true once its beginning recorded so,
its `cannot_hold` the sentence for every descendant then — a child it
holds refused at its first own operation, the head and the sentence, the
hook never run; an append, an insert, a move in and an amend accepted at
the edit, the gate fired, the children refused at evaluation; `print`
writing no empty node's line under it —; the gate `on_adding_child` fired
wherever `on_added_child` fires after it, with the same child and mode;
and a gate's veto; all against the fake state slot table.  The plugin's
block is test_typedef.py's.
Run: python -m pytest test/test_child_refusal.py
"""

import pytest

import stand_ins
import test_model as tm
import test_session_theory as ts
from baselines import composed_refusal
from invariants import assert_invariants, assert_store_mirrors
from isabelle_theory_agent import edit, model as M
from isabelle_theory_agent.exceptions import BadEdit
from isabelle_theory_agent.model import NOT_EVALUATED, READY_CLEAN
from test_model import locked, run
from test_session_theory import Forest_Under_Test, session, theory

table = ts.table                    # the fake state slot table and the fake wire, per test
REASON = "This block takes no child."         # the stand-in's remedy, as `LIFTING_REFUSAL` is `Lifting_Closing`'s


class Gate_Block(tm.Block):
    """A block recording its gate's calls beside its completed hook's."""
    def __init__(self, parent, state, name="", **rest):
        super().__init__(parent, state, name, **rest)
        self.adding, self.added = [], []
    def on_adding_child(self, child, mode):
        self.adding.append((child.name, mode))
    def on_added_child(self, child, mode):
        self.added.append((child.name, mode))


class Refusing_Block(Gate_Block):
    """A block refusing children as a `Lifting_Closing` block with `lifting`
    false does: `refuses_children()` once its beginning has recorded
    `refuse`, the construct's field — a fresh node refuses nothing —, and
    its `cannot_hold` the sentence for every descendant then; its gate
    recorded, so that an admitted child is seen to pass it."""
    construct_schema = {**tm.BLOCK_SCHEMA, "properties": {**tm.BLOCK_SCHEMA["properties"], "refuse": {"type": "boolean"}}}
    def __init__(self, parent, state, name="", refuse=False):
        super().__init__(parent, state, name)
        self.refuse, self.recorded = refuse, None
    @classmethod
    async def gen(cls, config, raw):
        return cls(config.parent, config.state, raw["name"], refuse=raw.get("refuse", False))
    def to_store(self, rows):
        super().to_store(rows)
        rows.put("refuse", self.refuse)
        rows.put("recorded", self.recorded)
    @classmethod
    def from_store(cls, config, rows):
        node = cls(config.parent, config.state, rows.get("name"), refuse=rows.get("refuse"))
        node.recorded = rows.get("recorded")
        return node
    async def _eval_beginning_opr(self):
        self.recorded = self.refuse
        return await super()._eval_beginning_opr()
    def refuses_children(self):
        return bool(self.recorded)
    def cannot_hold(self, descendant, depth):
        return REASON if self.refuses_children() else None


class Veto(BadEdit):
    def _cause(self):
        return "vetoed"


class Vetoing_Block(tm.Block):
    """A block whose gate vetoes a child named `x`."""
    def on_adding_child(self, child, mode):
        if child.name == "x":
            raise Veto()


KINDS = {**ts.KINDS, "refusing": Refusing_Block, "gate": Gate_Block, "veto": Vetoing_Block}


def insert(f, parent, index, raws):
    return run(locked(f, edit.insert(parent, index, raws)))


def node(kind, name, *children, **fields):
    return {"kind": kind, "name": name, **({"children": list(children)} if children else {}), **fields}


def arith(*children):
    """session_S > theory_T > `children`; the forest, the session and the theory."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("S", theory("T", kind="fake_theory") | {"children": list(children)})])
    (t,) = s.sub_nodes
    return f, s, t


def inv(f):
    assert_invariants(f, tm.TABLE)
    assert_store_mirrors(f, shape=ts.shape)


def refused(child, block):
    """The message a child of `block` is told, RENDER_BASELINES §3's form."""
    return composed_refusal(child.kind, child.forest().full_id(block), REASON)


# --- the refusal, at evaluation ------------------------------------------------

def test_a_block_s_refusal_of_children_is_told_at_a_child_s_first_own_operation():
    """A fresh block refuses nothing; once its beginning recorded the
    refusal, `refuses_children()` is true and every child is refused at its
    first own operation — the head with the block's full id, then the
    sentence —, the hook never run."""
    f, s, t = arith(node("refusing", "fm", node("t", "c"), refuse=True))
    (fm,) = t.sub_nodes
    (c,) = fm.sub_nodes
    assert fm.refuses_children() is False and c._refusal() is None                # fresh: nothing recorded
    run(t.evaluate_to(None, True))
    assert fm.refuses_children() is True
    assert c._refusal() == refused(c, fm) and f.full_id(fm) == "session_S.fake_theory_T.refusing_fm"
    assert c.runs == 0 and isinstance(c._status, M.CannotEvaluate) and [m.unicode for m in c._status.messages] == [refused(c, fm)]


def test_a_child_held_when_the_beginning_records_is_refused_at_its_first_own_operation():
    """A child placed before the beginning recorded its refusal: its first
    own operation is `cannot_evaluate` without running, the message the
    refusal, the `evaluation` record `ran: false` (LOGGING.md §4); the walk
    stops there, the ending not run; the child gone, the ending runs; a
    block whose beginning records no refusal runs its children."""
    f, s, t = arith(node("refusing", "fm", node("t", "c"), node("t", "d"), refuse=True), node("refusing", "open", node("t", "e")))
    fm, open_ = t.sub_nodes
    c, d = fm.sub_nodes
    (e,) = open_.sub_nodes
    run(t.evaluate_to(None, False))
    assert fm.begin_runs == 1 and c.runs == 0 and d.runs == 0 and fm.end_runs == 0
    assert isinstance(c._status, M.CannotEvaluate) and [m.unicode for m in c._status.messages] == [refused(c, fm)]
    assert d._status is NOT_EVALUATED and open_.begin_runs == 0
    [record] = [r["data"] for r in stand_ins.records("evaluation")
                if r["data"].get("node") == f.full_id(c) and "ran" in r["data"]]          # the operation's record
    assert record["ran"] is False and record["status"] == "cannot_evaluate" and record["messages"] == [refused(c, fm)]
    inv(f)
    run(locked(f, edit.delete(c)))
    run(t.evaluate_to(None, False))
    assert d.runs == 0 and isinstance(d._status, M.CannotEvaluate) and fm.end_runs == 0        # the next child, likewise
    run(locked(f, edit.delete(d)))
    run(t.evaluate_to(None, False))
    assert fm.end_runs == 1 and fm.evaluation_status_ending == READY_CLEAN and e.runs == 1 and open_.end_runs == 1
    inv(f)


# --- at the edit ------------------------------------------------------------------

def test_every_edit_letting_a_child_in_is_accepted_and_the_child_is_refused_at_evaluation():
    """An append, an insert before the held child, a move in, an amend of a
    node the block holds, an amend's inheritance into a replacement that
    refuses from birth, and a construct's inline children under a fresh node
    that refuses from birth: each enters the forest, the gate fired for it,
    and each is refused at evaluation, the block named."""
    f, s, t = arith(node("refusing", "fm", node("t", "c"), refuse=True), node("t", "outside"), node("refusing", "open"))
    fm, outside, open_ = t.sub_nodes
    (c,) = fm.sub_nodes
    run(t.evaluate_to(None, True))
    assert fm.recorded is True and open_.recorded is False and c.runs == 0
    (ok,) = insert(f, open_, 0, [node("t", "ok")])                           # a block that does not refuse takes children
    (d,) = insert(f, fm, 1, [node("t", "d")])
    (e,) = insert(f, fm, 0, [node("t", "e")])
    run(locked(f, edit.move(outside, fm, 3)))
    (c2,) = run(locked(f, edit.amend(c, [node("t", "c2")])))
    assert fm.sub_nodes == [e, c2, d, outside] and t.sub_nodes == [fm, open_]
    assert fm.adding == [("c", "insert_or_delete"), ("d", "insert_or_delete"), ("e", "insert_or_delete"),
                         ("outside", "move"), ("c2", "amend")] == fm.added
    inv(f)
    assert outside.runs == 1 and outside._status is NOT_EVALUATED           # it ran outside; the move invalidated it
    run(t.evaluate_to(None, True))
    for child, runs in ((e, 0), (c2, 0), (d, 0), (outside, 1)):
        assert child.runs == runs and [m.unicode for m in child._status.messages] == [refused(child, fm)]
    assert ok.runs == 1
    # an amend whose replacement refuses from birth — a stand-in's liberty — refuses the inherited child at evaluation
    class Born_Refusing(Refusing_Block):
        def __init__(self, parent, state, name="", refuse=False):
            super().__init__(parent, state, name, refuse)
            self.recorded = refuse
    f.kinds["born"] = Born_Refusing                                      # the forest's one table
    (born,) = run(locked(f, edit.amend(open_, [node("born", "open", refuse=True)])))
    assert born.sub_nodes == [ok] and ok.parent is born and f.resolve("born_open") is born
    run(t.evaluate_to(None, True))
    assert ok.runs == 1 and [m.unicode for m in ok._status.messages] == [refused(ok, born)]
    # a construct's own children under a fresh node that refuses from birth
    (fresh,) = insert(f, t, 2, [node("born", "fresh", node("t", "inline"), refuse=True)])
    (inline,) = fresh.sub_nodes
    run(t.evaluate_to(None, True))
    assert inline.runs == 0 and [m.unicode for m in inline._status.messages] == [refused(inline, fresh)]
    inv(f)


def test_the_gate_fires_wherever_on_added_child_fires_with_the_same_child_and_mode():
    """An insert with inline children, an amend with inherited children and
    followers with children, a move: each gate block's record of
    `on_adding_child` equals its record of `on_added_child`, in order."""
    f, s, t = arith(node("gate", "g"))
    (g,) = t.sub_nodes
    a, h = insert(f, g, 0, [node("t", "a"), node("gate", "h", node("t", "d"))])
    assert g.adding == [("a", "insert_or_delete"), ("h", "insert_or_delete")] == g.added
    assert h.adding == [("d", "insert_or_delete")] == h.added                 # the fresh node's, for its inline child
    run(locked(f, edit.move(a, h, 0)))
    assert h.adding[-1] == ("a", "move") == h.added[-1]
    (h2, e) = run(locked(f, edit.amend(h, [node("gate", "h2"), node("t", "e", fail=False)])))
    assert h2.adding == [("a", "inheritance"), ("d", "inheritance")] == h2.added
    assert g.adding[-2:] == [("h2", "amend"), ("e", "insert_or_delete")] == g.added[-2:]
    (e2, k) = run(locked(f, edit.amend(e, [node("t", "e2"), node("gate", "k", node("t", "under_k"))])))   # a follower's child
    assert k.adding == [("under_k", "insert_or_delete")] == k.added
    assert g.adding[-2:] == [("e2", "amend"), ("k", "insert_or_delete")] == g.added[-2:]
    for block in (g, h2, k):
        assert block.adding == block.added
    inv(f)


def test_a_gate_s_veto_leaves_the_forest_unchanged():
    f, s, t = arith(node("veto", "v"))
    (v,) = t.sub_nodes
    with pytest.raises(Veto):
        insert(f, v, 0, [node("t", "x")])
    assert v.sub_nodes == []
    (y,) = insert(f, v, 0, [node("t", "y")])
    assert v.sub_nodes == [y]
    inv(f)


# --- in print --------------------------------------------------------------------

def test_print_writes_no_empty_node_s_line_under_a_node_that_refuses_children():
    """PRINT.md §2: a refusing block with no child shows no empty node's line
    in the briefing, as a focus and under `recall`; a block that does not
    refuse shows it."""
    f, s, t = arith(node("refusing", "fm", refuse=True), node("refusing", "open"))
    fm, open_ = t.sub_nodes
    me = stand_ins.agent(f.conversation)
    run(t.evaluate_to(None, True))
    assert fm.refuses_children() is True and open_.refuses_children() is False
    for root, mode in ((f, M.BRIEFING), (t, M.RECALL), (f, M.Relative_Focus(frozenset({fm, open_}), 0))):
        lines = [line for line in f.render(root, mode, me).splitlines() if "Empty so far" in line]
        assert lines == [line for line in lines if "refusing_open" in line] and len(lines) == 1, (mode, lines)
    assert "Empty so far" not in f.render(fm, M.RECALL, me) and "Empty so far" in f.render(open_, M.RECALL, me)
