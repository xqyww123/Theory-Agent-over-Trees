"""A nesting node that refuses children (MODULE_STRUCTURE §4.1; PLUGIN_SYSTEM
§2): `children_refusal()` asked by the framework just before the gate
`on_adding_child` at every edit that lets a child in — the refusal
`ChildRefused`, RENDER_BASELINES §2's form, the forest unchanged —, before
a child's first own operation once its placement is admitted — the
`CannotEvaluate` of RENDER_BASELINES §3's form, the hook never run — and in
`print`, which writes no empty node's line under such a node; the gate
fired wherever `on_added_child` fires after it, with the same child and
mode, and a gate's veto; all on stand-ins against the fake state slot
table.  The plugin's block on it is test_typedef.py's.
Run: python -m pytest test/test_child_refusal.py
"""

import pytest

import stand_ins
import test_model as tm
import test_session_theory as ts
from baselines import DOCS, fenced_lines
from invariants import assert_invariants, assert_store_mirrors
from isabelle_theory_agent import edit, model as M
from isabelle_theory_agent.exceptions import BadEdit, BadTheoryNodeParent, ChildRefused
from isabelle_theory_agent.model import NOT_EVALUATED, READY_CLEAN, child_refusal, placement_refusal
from test_model import locked, run
from test_session_theory import Forest_Under_Test, session, theory

table = ts.table                    # the fake state slot table and the fake wire, per test
BASELINES = DOCS / "RENDER_BASELINES.md"
[EDIT_TIME] = [line for line in fenced_lines(BASELINES, "2.") if line.startswith("A node of kind `lift_definition` cannot be placed")]
[EVALUATION] = [line for line in fenced_lines(BASELINES, "3.") if line.startswith("A node of kind `lift_definition` cannot stand")]
REASON = EDIT_TIME.split(". ", 1)[1]              # the parent's sentence, after the framework's own


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
    """A block answering `children_refusal()` as a `Lifting_Closing` block
    with `lifting` false does: the sentence once its beginning has
    recorded `refuse`, the construct's field — a fresh node answers None;
    its gate recorded, so that a refusal is seen to come before it."""
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
    def children_refusal(self):
        return REASON if self.recorded else None


class Veto(BadEdit):
    def _cause(self):
        return "vetoed"


class Vetoing_Block(tm.Block):
    """A block whose gate refuses a child named `x` — a refusal by the child,
    the one reason to override the gate."""
    def on_adding_child(self, child, mode):
        if child.name == "x":
            raise Veto()


class Top(tm.T):                     # admitted directly in a theory alone
    placement = M.Placement(within="Theory", through=())


KINDS = {**ts.KINDS, "refusing": Refusing_Block, "gate": Gate_Block, "veto": Vetoing_Block, "top": Top}


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


# --- the two sentences --------------------------------------------------------

def test_the_sentences_are_render_baselines():
    """§2's edit-time sentence from a real append, §3's from `child_refusal`,
    composed by the framework from the parent's full id and kind and the
    parent's sentence, a period between; the baseline's kinds and ids
    substituted."""
    f, s, t = arith(node("refusing", "fm", node("t", "c"), refuse=True))
    (fm,) = t.sub_nodes
    (c,) = fm.sub_nodes
    assert child_refusal(c) is None and fm.children_refusal() is None          # fresh: nothing recorded
    run(t.evaluate_to(None, True))
    with pytest.raises(ChildRefused) as e:
        insert(f, fm, 1, [node("t", "d")])
    expected = EDIT_TIME.replace("`lift_definition`", "`t`").replace("session_S.theory_T.typedef_fm", f.full_id(fm))
    assert str(e.value) == expected and e.value.raw_ast_path is None
    assert (e.value.kind, e.value.parent_id, e.value.reason) == ("t", "session_S.fake_theory_T.refusing_fm", REASON)
    assert child_refusal(c) == EVALUATION.replace("`lift_definition`", "`t`").replace(
        "session_S.theory_T.typedef_fm", f.full_id(fm)).replace("a node of kind `typedef`", "a node of kind `refusing`")


# --- at the edit ------------------------------------------------------------------

def test_every_edit_letting_a_child_in_is_refused_and_leaves_the_forest_unchanged():
    """An append, an insert before and after, a move in, an amend of a
    node the block holds, an amend's inheritance into a replacement that
    refuses, and a construct's inline children under a fresh node that
    refuses from birth — each `ChildRefused` with no `raw_ast_path` (a
    gate's refusal, §4.2's step 2), the forest as it was; a node the
    block holds already stays.  A theory moved into the refusing block is
    refused by its own gate first, `BadTheoryNodeParent`, as an insert
    there is."""
    f, s, t = arith(node("refusing", "fm", node("t", "c"), refuse=True), node("t", "outside"), node("refusing", "open"))
    fm, outside, open_ = t.sub_nodes
    (c,) = fm.sub_nodes
    run(t.evaluate_to(None, True))
    assert fm.recorded is True and open_.recorded is False
    (ok,) = insert(f, open_, 0, [node("t", "ok")])                           # a block that does not refuse takes children
    calls = [lambda: edit.insert(fm, 1, [node("t", "d")]), lambda: edit.insert(fm, 0, [node("t", "d")]),
             lambda: edit.move(outside, fm, 0), lambda: edit.move(ok, fm, 1),
             lambda: edit.amend(c, [node("t", "c2")])]
    for call in calls:
        with pytest.raises(ChildRefused) as e:
            run(locked(f, call()))
        assert e.value.parent_id == f.full_id(fm) and e.value.raw_ast_path is None
    assert fm.sub_nodes == [c] and t.sub_nodes == [fm, outside, open_] and open_.sub_nodes == [ok]
    assert fm.adding == [("c", "insert_or_delete")] == fm.added             # the gate never fired after a refusal
    # an amend whose replacement refuses from birth — a stand-in's liberty — refuses the inherited child
    class Born_Refusing(Refusing_Block):
        def __init__(self, parent, state, name="", refuse=False):
            super().__init__(parent, state, name, refuse)
            self.recorded = refuse
    f.kinds["born"] = Born_Refusing                                      # the forest's one table
    with pytest.raises(ChildRefused) as e:
        run(locked(f, edit.amend(open_, [node("born", "open", refuse=True)])))
    assert e.value.kind == "t" and e.value.reason == REASON and e.value.raw_ast_path is None
    assert open_.sub_nodes == [ok] and ok.parent is open_
    assert t.sub_nodes == [fm, outside, open_] and f.resolve("refusing_open") is open_
    # a construct's own children under a fresh node that refuses from birth
    with pytest.raises(ChildRefused) as e:
        insert(f, t, 3, [node("born", "fresh", node("t", "inline"), refuse=True)])
    assert e.value.kind == "t" and e.value.raw_ast_path is None and len(t.sub_nodes) == 3
    (fresh,) = insert(f, t, 3, [node("born", "fresh", refuse=True)])         # with no child, accepted; takes none after
    with pytest.raises(ChildRefused):
        insert(f, fresh, 0, [node("t", "late")])
    # the moved node's own gate first: a theory moved into the refusing block is refused as an insert there is
    (y,) = insert(f, s, 1, [theory("Y", kind="fake_theory")])
    with pytest.raises(BadTheoryNodeParent) as inserted:
        insert(f, fm, 0, [theory("Z", kind="fake_theory")])
    with pytest.raises(BadTheoryNodeParent) as moved:
        run(locked(f, edit.move(y, fm, 0)))
    assert moved.value.parent_id == inserted.value.parent_id == f.id_of(fm)
    assert y.parent is s and fm.sub_nodes == [c]
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


# --- at evaluation and in print --------------------------------------------------

def test_a_child_held_when_the_beginning_records_is_refused_at_its_first_own_operation():
    """A child placed before the beginning recorded its refusal: its first
    own operation is `cannot_evaluate` without running, the message §3's
    sentence, the `evaluation` record `ran: false` (LOGGING.md §4); the walk
    stops there, the ending not run; the child gone, the ending runs; a
    block whose beginning records no refusal runs its children."""
    f, s, t = arith(node("refusing", "fm", node("t", "c"), node("t", "d"), refuse=True), node("refusing", "open", node("t", "e")))
    fm, open_ = t.sub_nodes
    c, d = fm.sub_nodes
    (e,) = open_.sub_nodes
    run(t.evaluate_to(None, False))
    assert fm.begin_runs == 1 and c.runs == 0 and d.runs == 0 and fm.end_runs == 0
    assert isinstance(c._status, M.CannotEvaluate) and [m.unicode for m in c._status.messages] == [child_refusal(c)]
    assert d._status is NOT_EVALUATED and open_.begin_runs == 0
    [record] = [r["data"] for r in stand_ins.records("evaluation")
                if r["data"].get("node") == f.full_id(c) and "ran" in r["data"]]          # the operation's record
    assert record["ran"] is False and record["status"] == "cannot_evaluate" and record["messages"] == [child_refusal(c)]
    inv(f)
    run(locked(f, edit.delete(c)))
    run(t.evaluate_to(None, False))
    assert d.runs == 0 and isinstance(d._status, M.CannotEvaluate) and fm.end_runs == 0        # the next child, likewise
    run(locked(f, edit.delete(d)))
    run(t.evaluate_to(None, False))
    assert fm.end_runs == 1 and fm.evaluation_status_ending == READY_CLEAN and e.runs == 1 and open_.end_runs == 1
    inv(f)


def test_the_placement_check_comes_first():
    """A child whose class's `placement` does not admit it under the
    refusing block gets the placement sentence, not the refusal."""
    f, s, t = arith(node("refusing", "fm", node("top", "x"), node("t", "c"), refuse=True))
    (fm,) = t.sub_nodes
    x, c = fm.sub_nodes
    run(t.evaluate_to(None, False))
    assert [m.unicode for m in x._status.messages] == [placement_refusal(Top, "top", fm)]
    assert child_refusal(x) is not None and placement_refusal(Top, "top", fm) != child_refusal(x)
    assert c._status is NOT_EVALUATED
    inv(f)


def test_print_writes_no_empty_node_s_line_under_a_node_that_refuses_children():
    """PRINT.md §2: a refusing block with no child shows no empty node's line
    in the briefing, as a focus and under `recall`; a block that does not
    refuse shows it."""
    f, s, t = arith(node("refusing", "fm", refuse=True), node("refusing", "open"))
    fm, open_ = t.sub_nodes
    me = stand_ins.agent(f.conversation)
    run(t.evaluate_to(None, True))
    assert fm.children_refusal() == REASON and open_.children_refusal() is None
    for root, mode in ((f, M.BRIEFING), (t, M.RECALL), (f, M.Relative_Focus(frozenset({fm, open_}), 0))):
        lines = [line for line in f.render(root, mode, me).splitlines() if "Empty so far" in line]
        assert lines == [line for line in lines if "refusing_open" in line] and len(lines) == 1, (mode, lines)
    assert "Empty so far" not in f.render(fm, M.RECALL, me) and "Empty so far" in f.render(open_, M.RECALL, me)
