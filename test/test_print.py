"""Rendering (PRINT.md): the marks, the four print modes and the depth, the
fields and errors `Session` and `Theory` write (SESSION_AND_THEORY §4),
the seen set, the forest root's three forms, `Forest.render` and its id
index — pinned to the documents' own examples (PRINT.md §6, §7,
RENDER_BASELINES §5, RECALL.md §2).  Nothing here crosses the wire.
Run: python -m pytest test/test_print.py
"""

import io
import typing

import pytest

import stand_ins
from baselines import DOCS, fenced_blocks
from isabelle_theory_agent import isabelle_driver, jobs, model as M
from isabelle_theory_agent.exceptions import TAT_InternalError
from isabelle_theory_agent.model import (
    BRIEFING, NOT_EVALUATED, OUT_FOCUS, RECALL, Isar_State_Slot,
    Relative_Focus, print_error)
from Isabelle_RPC_Host.unicode import IsaTerm
from isabelle_theory_agent.store import Forest_Store

READY = M.READY_CLEAN
CANNOT_EVALUATE = M.CannotEvaluate()


def failing(*messages: str) -> M.CannotEvaluate:
    """A `CannotEvaluate` carrying `messages`, as a run's leaves."""
    return M.CannotEvaluate(tuple(IsaTerm.from_agent(m) for m in messages))

CONN = typing.cast(typing.Any, object())
PRINT = DOCS / "PRINT.md"


def slot(): return Isar_State_Slot.assign(stand_ins.conversation(CONN))


# --- the node classes of the examples --------------------------------------
# `Session` and `Theory` are the real ones; a lemma owes its proof until its
# construction job succeeds, as `Theorem` does; a definition reads `invalid
# definition` where Isabelle refused it, as `Define` does (node_classes/
# DEFINE.md §7), and prints its errors in every mode but the briefing, §7's
# example; a datatype keeps the framework's default marks.

class Stub:
    name: str
    def to_store(self, rows): rows.put("name", self.name)
    @classmethod
    def from_store(cls, config, rows): raise NotImplementedError
    async def _eval_opr(self): raise NotImplementedError
    def __repr__(self): return self.name


class Proof_Construction(jobs.Construction_Job):
    @classmethod
    def title(cls, plural=False): return "proof constructions" if plural else "proof construction"
    def failure_header(self, failure): return "No proof was found:"
    async def _run(self): raise NotImplementedError


class Proof_Check(jobs.Evaluation_Job):
    @classmethod
    def title(cls, plural=False): return "proof checks" if plural else "proof check"
    @classmethod
    def failure_header(cls, failure): return "The proof no longer holds:"
    @classmethod
    def failure_notification(cls, ids, automatic): raise NotImplementedError
    async def _start(self): raise NotImplementedError


class Lemma(Stub, M.Leaf):
    construction_job_class = Proof_Construction
    evaluation_job_class = Proof_Check
    def emit(self, indent, out): raise NotImplementedError

    def mark(self, mode, depth):
        """`Theorem`'s two slots (node_classes/THEOREM.md §7), which the
        documents' examples read."""
        (status,) = self.evaluation_statuses()
        if isinstance(status, M.CannotEvaluate):
            return "invalid statement"
        statement = "valid statement" if isinstance(status, M.Ready) else "not evaluated"
        outcome = self.job().outcome
        if outcome is jobs.NOT_STARTED:
            proof = "proof not started"
        elif outcome is jobs.RUNNING:
            proof = "proving"
        elif isinstance(outcome, jobs.Failed):
            proof = "failed to prove"
        else:
            check = self.check_outcome()
            proof = ("unchecked proof" if check is None else "proof checking" if check is jobs.RUNNING
                     else "proven" if check is jobs.PASSED else "bad proof")
            if statement == "not evaluated":
                return statement                    # a stored proof is left out
        return f"{statement}, {proof}"


def proven(lemma) -> None:
    """The lemma's proof construction succeeded and its check passed: it
    owes nothing more."""
    lemma.job().outcome = jobs.Succeeded("by simp")
    lemma._check_outcome = jobs.PASSED


class Definition(Stub, M.Leaf):          # its messages are the framework's (PRINT.md §3)
    def mark(self, mode, depth):
        invalid = isinstance(self.job_operation_status(), M.CannotEvaluate)
        return "invalid definition" if invalid else super().mark(mode, depth)
    def emit(self, indent, out): raise NotImplementedError


class Datatype(Stub, M.Leaf):            # the default marks (PRINT.md §1)
    def emit(self, indent, out): raise NotImplementedError


class Section(Stub, M.StdBlock):
    output_omissible = input_omissible = True
    async def _eval_beginning_opr(self): raise NotImplementedError
    def emit_beginning(self, indent, out): raise NotImplementedError


KINDS = {"session": M.Session, "theory": M.Theory, "lemma": Lemma,
         "definition": Definition, "datatype": Datatype, "section": Section}


def enter(parent, n, kind):
    f = parent.forest()
    n.parent, n.kind, n.identity = parent, kind, f.store.next_identity()
    parent.sub_nodes.append(n)
    with f.store.transaction():
        f._store_node(n); f._store_children(parent)
    return n


def new_forest():
    return M.Forest(stand_ins.conversation(CONN), Forest_Store(":memory:", stand_ins.log()), KINDS)


def session(forest, name, parent_session="HOL", options=(), description=""):
    return enter(forest, M.Session(forest, slot(), name, parent_session, list(options),
                                   description), "session")


def theory(sess, name, imports=("Main",), beginning: M.EvaluationStatus = NOT_EVALUATED,
           ending: M.EvaluationStatus = NOT_EVALUATED, description=""):
    t = enter(sess, M.Theory(sess, slot(), name, list(imports), description), "theory")
    t.evaluation_status_beginning, t.evaluation_status_ending = beginning, ending
    return t


def leaf(cls, parent, kind, name, status: M.EvaluationStatus = NOT_EVALUATED, errors=()):
    n = cls(parent, slot()); n.name = name
    n._status = failing(*errors) if errors else status
    return enter(parent, n, kind)


def section(parent, name, beginning: M.EvaluationStatus = READY,
            ending: M.EvaluationStatus = READY):
    s = Section(parent, slot()); s.name = name
    s.evaluation_status_beginning, s.evaluation_status_ending = beginning, ending
    return enter(parent, s, "section")


def agent(forest):
    """The forest's main agent, whom a rendering is for unless a case says
    otherwise, and whose seen set the cases read."""
    return stand_ins.agent(forest.conversation)


def render(forest, node, mode, to=None) -> list[str]:
    return forest.render(node, mode, agent(forest) if to is None else to).splitlines()


def focus(*nodes, depth=0):
    return Relative_Focus(frozenset(nodes), depth)


def empty(node_id, indent=1):
    """The empty node's line (PRINT.md §2) at `indent`."""
    return M.INDENT * indent + M.EMPTY_NODE.format(id=node_id)


# --- the documents' examples ------------------------------------------------

def example_forest():
    """PRINT.md §7's forest: one session, three theories."""
    f = new_forest()
    a = session(f, "A")
    theory(a, "Base", beginning=READY, ending=READY)
    x = theory(a, "X", beginning=READY)
    leaf(Lemma, x, "lemma", "A", status=READY)
    leaf(Definition, x, "definition", "f", status=CANNOT_EVALUATE, errors=[
        'Type unification failed: Clash of types "nat" and "bool"\n'
        'Type error in application: incompatible operand type'])
    leaf(Lemma, x, "lemma", "P", status=NOT_EVALUATED)              # blocked by definition_f
    x.evaluation_status_ending = NOT_EVALUATED
    theory(a, "Y")
    return f, a, x


def test_the_quickview_of_print_md_section_7():
    f, a, x = example_forest()
    [example] = fenced_blocks(PRINT, "7.")
    assert render(f, f, focus(x)) == example


def test_the_recall_of_recall_md_section_2():
    """RECALL.md §2's forest: two sessions, the first finished."""
    f = new_forest()
    a = session(f, "A")
    base = theory(a, "Base", beginning=READY, ending=READY)
    proven(leaf(Lemma, base, "lemma", "A", status=READY))
    b = session(f, "B", description="Sorting, verified.")
    x = theory(b, "X", imports=("Main", "A.Base"))
    leaf(Lemma, x, "lemma", "P")
    [example] = fenced_blocks(DOCS / "RECALL.md", "2.")
    assert render(f, f, RECALL) == example


def test_the_root_forms_of_print_md_section_6():
    two_sessions, lone_session, empty = fenced_blocks(PRINT, "6.")

    f = new_forest()
    session(f, "A")                                    # nothing under it: finished
    b = session(f, "B")
    x = theory(b, "X")
    assert render(f, f, focus(x)) == two_sessions

    f = new_forest()
    a = session(f, "A")
    theory(a, "Base", beginning=READY, ending=READY)
    x = theory(a, "X")
    assert render(f, f, focus(x)) == lone_session

    f = new_forest()
    for mode in (BRIEFING, RECALL, focus(f)):
        assert render(f, f, mode) == empty
    assert empty[1].strip() == M.EMPTY_FOREST


def test_the_lines_of_render_baselines_section_5():
    """RB §5's seven blocks: the default marks' four lines; the two tags, for
    every agent and for the owner alone; the error and notice blocks; a
    job's failure block; the children header; the summary under a cut-off
    nesting node."""
    node_lines, tag_lines, error_block, notice_block, failure_block, children_header, summary = fenced_blocks(
        DOCS / "RENDER_BASELINES.md", "5.")
    g = new_forest()                                   # the header: a theory's `imports` over its one lemma, under recall
    gx = theory(session(g, "A"), "X", beginning=READY, ending=READY)
    proven(leaf(Lemma, gx, "lemma", "A", status=READY))
    assert render(g, gx, RECALL)[2:] == children_header
    f = new_forest()
    a = session(f, "A")
    x = theory(a, "X", beginning=READY, ending=READY)
    basics = section(x, "Basics")
    tree = leaf(Datatype, x, "datatype", "tree")
    color = leaf(Datatype, x, "datatype", "color", status=CANNOT_EVALUATE, errors=["e"])
    lines = [render(f, basics, OUT_FOCUS)[0]]
    basics.evaluation_status_ending = NOT_EVALUATED
    lines += [render(f, n, OUT_FOCUS)[0] for n in (basics, tree, color)]
    assert lines == node_lines
    f_ = leaf(Definition, x, "definition", "f", status=CANNOT_EVALUATE, errors=["e"])
    assert render(f, f_, OUT_FOCUS)[0] == "- definition_f (invalid definition)"     # the class's word, not `failed`
    q = leaf(Lemma, x, "lemma", "Q", status=READY)
    proven(q)
    q.job().auto_construct = True
    rev = leaf(Lemma, x, "lemma", "rev_length", status=READY)
    rev.job().outcome = jobs.RUNNING
    rev.job()._questions.append(jobs._Pending(object(), None))  # type: ignore[arg-type]  # a pending question, for the tag
    rev.job().owner = agent(f)
    other = stand_ins.agent(f.conversation, "other", False)
    assert render(f, rev, OUT_FOCUS, to=other) == ["- lemma_rev_length (valid statement, proving)"]
    lines = [render(f, q, OUT_FOCUS)[0], render(f, rev, OUT_FOCUS)[0]]
    rev.job().auto_construct = True
    lines.append(render(f, rev, OUT_FOCUS)[0])
    assert lines == tag_lines
    out = io.StringIO()
    print_error(0, out, "Type unification failed: ...")
    assert out.getvalue().splitlines() == error_block
    out = io.StringIO()
    print_error(0, out, "Ignoring duplicate rewrite rule: ...", "Notice:")
    assert out.getvalue().splitlines() == notice_block
    p = leaf(Lemma, x, "lemma", "P", status=READY)
    p.job().outcome = jobs.Failed("Sledgehammer timed out on every prover.")
    assert render(f, p, focus(p))[1:] == failure_block
    assert render(f, p, OUT_FOCUS) == ["- lemma_P (valid statement, failed to prove)"]   # not detailed: no block
    p.job().outcome = jobs.Failed("")
    assert render(f, p, focus(p))[1:] == ["  No proof was found."]        # an empty message: a period, nothing below
    p._status = failing("e")                                             # itself an obstacle: its own block alone
    assert render(f, p, focus(p))[1:] == ["  Error:", "    e"]
    # the summary: under Recall from the root, a section at depth 3
    s = section(x, "Summary")
    leaf(Lemma, s, "lemma", "A", status=READY)
    leaf(Lemma, s, "lemma", "C", status=READY)
    c = section(s, "C"); c.kind = "context"
    leaf(Lemma, c, "lemma", "B", status=READY)
    for i in range(12):
        checked = leaf(Lemma, s, "lemma", f"K{i}", status=READY)
        checked.job().outcome = jobs.Succeeded("by simp")
    leaf(Definition, s, "definition", "f", status=CANNOT_EVALUATE, errors=["e"])
    leaf(Lemma, s, "lemma", "E")
    leaf(Lemma, s, "lemma", "F")
    rendered = render(f, f, RECALL)
    at = rendered.index("      - section_Summary (incomplete)")          # under `theories:` and `declarations:`
    assert [line[6:] for line in rendered[at + 1:at + 5]] == summary    # the block, less the section's own indent
    assert len(rendered) == at + 5                                        # nothing below depth 3


# --- the mark ---------------------------------------------------------------

def test_the_default_mark_first_row_wins():
    f = new_forest()
    a = session(f, "A")
    base = theory(a, "Base", beginning=READY, ending=READY)
    g = leaf(Definition, base, "definition", "g", status=READY)
    x = theory(a, "X", beginning=READY)
    p = leaf(Lemma, x, "lemma", "P", status=READY)
    q = leaf(Lemma, x, "lemma", "Q")
    mark = lambda n: M.Node.mark(n, OUT_FOCUS, 1)     # noqa: E731  # the framework's default, `Lemma`'s own aside
    assert mark(base) == "complete" and mark(g) == "complete" and mark(a) == "incomplete"
    assert mark(p) == "incomplete"                     # ran, owes its proof
    proven(p)
    assert mark(p) == "complete"
    assert mark(q) == "not evaluated"
    assert mark(x) == "incomplete"                     # its beginning ran, its ending has not: stopped inside
    x.evaluation_status_beginning = CANNOT_EVALUATE
    assert mark(x) == "failed"                         # an obstacle beats the ending's not evaluated
    x.evaluation_status_beginning = NOT_EVALUATED
    assert mark(x) == "not evaluated"                  # its first own operation did not run
    empty = session(f, "Empty")
    assert mark(empty) == "complete"                   # nothing under it, nothing owed


def test_the_field_lines_of_session_and_theory_section_4():
    [lines] = fenced_blocks(DOCS / "node_classes" / "SESSION_AND_THEORY.md", "4.")
    f = new_forest()
    a = session(f, "A", options=[{"name": "quick_and_dirty", "value": "true"},
                                 {"name": "document", "value": "false"}],
                description="Sorting, verified.")
    x = theory(a, "X", imports=("Main", "HOL-Library.Multiset"), description="Sorting, verified.")
    assert render(f, f, RECALL)[1:] == lines[:2] + ["theories:", "  - theory_X (not evaluated)", "    " + lines[4],
                                                    "    declarations:", empty("theory_X", 3)]
    assert render(f, a, RECALL)[1:] == ["  " + line for line in lines[:4]] + [   # depth 0: the description too
        "  theories:", "    - theory_X (not evaluated)", "      " + lines[4],      # the theory at depth 1: imports alone
        "      declarations:", empty("theory_X", 4)]
    assert render(f, x, RECALL)[1:] == ["  " + line for line in lines[2:]] + [   # depth 0 likewise; `imports` keyed:
        "  declarations:", empty("theory_X", 2)]                                  # the header (PRINT.md §2)
    x.description = ""
    assert render(f, x, RECALL)[1:] == ["  " + lines[4], "  declarations:", empty("theory_X", 2)]   # left out when empty
    bare = new_forest()
    session(bare, "B")
    assert render(bare, bare, RECALL) == ["session_B (complete)", "parent_session: HOL",   # the lone session: no dash
                                          "theories:", empty("session_B", 1)]


def test_a_class_may_say_more_than_the_default():
    class Theorem(Lemma):
        def mark(self, mode, depth):                   # the default never says nothing: a class refines it
            default = M.Node.mark(self, mode, depth)
            return "not proven" if default == "incomplete" else default
    f = new_forest()
    a = session(f, "A")
    x = theory(a, "X", beginning=READY, ending=READY)
    n = Theorem(x, slot()); n.name = "P"; n._status = READY
    enter(x, n, "lemma")
    assert render(f, n, OUT_FOCUS) == ["- lemma_P (not proven)"]
    n._status = NOT_EVALUATED
    assert render(f, n, OUT_FOCUS) == ["- lemma_P (not evaluated)"]


# --- the modes and the depth ------------------------------------------------

def deep_forest():
    """root / session_A / theory_X / section_S / lemma_P: five depths."""
    f = new_forest()
    a = session(f, "A", options=[{"name": "quick_and_dirty", "value": "true"}],
                description="Sorting,\nverified.")
    x = theory(a, "X", imports=("Main", "HOL-Library.Multiset"), beginning=READY)
    s = section(x, "S")
    p = leaf(Lemma, s, "lemma", "P", status=READY)
    return f, a, x, s, p


def test_the_empty_node_s_line_stands_where_its_children_would():
    """PRINT.md §2: a nesting node with no children writes the line where
    its children would go — in the briefing, as a focus, in a recall above
    the last printed depth — and nowhere else; under the lone session's
    line it stays at the session's indent."""
    f, a, x, s, p = deep_forest()
    t = section(x, "T")                                # depth 3 from the root
    y = theory(a, "Y")
    t_id = f.id_of(t)
    lines = lambda rendering: [line for line in rendering if "Empty so far" in line]   # noqa: E731
    assert lines(render(f, f, BRIEFING)) == [empty(t_id, 2), empty("theory_Y")]
    assert lines(render(f, f, focus(x))) == []         # t and y out of focus
    assert lines(render(f, f, focus(y))) == [empty("theory_Y")]
    assert lines(render(f, f, RECALL)) == [empty("theory_Y", 3)]   # t at the last printed depth; y under two headers
    assert lines(render(f, x, RECALL)) == [empty(t_id, 3)]   # t under the theory's `declarations:`; its own line unkeyed
    g = new_forest()
    b = session(g, "B")
    assert render(g, g, focus(b)) == ["session_B (complete)", empty("session_B", 0)]


def test_the_briefing_is_every_line_to_the_bottom_with_no_field():
    f, *_ = deep_forest()
    assert render(f, f, BRIEFING) == [
        "session_A (incomplete)",
        "- theory_X (incomplete)",                     # its beginning ran, its ending did not
        "  - section_S (incomplete)",                  # ran whole; the lemma under it owes its proof
        "    - lemma_P (valid statement, proof not started)",
    ]


def test_the_briefing_calls_no_print_fields():
    """PRINT.md §2's table: `Briefing` calls `print_fields` on no class; the
    same class writes under `Recall`."""
    f, a, x, s, p = deep_forest()
    calls = []

    class Loud(Lemma):
        def print_fields(self, indent, out, mode, depth):
            calls.append((type(mode).__name__, depth))
            out.write(M.INDENT * indent + "field: value\n")
            return True
    loud = Loud(s, slot()); loud.name = "Q"; loud._status = NOT_EVALUATED
    enter(s, loud, "lemma")
    assert render(f, f, BRIEFING)[-1] == "    - lemma_Q (not evaluated, proof not started)" and calls == []
    assert render(f, s, RECALL)[-2:] == ["  - lemma_Q (not evaluated, proof not started)", "    field: value"]
    assert calls == [("Recall", 1)]


def test_what_session_and_theory_print_section_4_mode_by_mode():
    """SESSION_AND_THEORY §4's table, row by row, through `print_fields`
    itself: fields under `Recall` alone, thinning with the depth."""
    f, a, x, s, p = deep_forest()

    def fields(node, mode, depth):
        out = io.StringIO()
        node.print_fields(0, out, mode, depth)
        return out.getvalue().splitlines()
    session = ["parent_session: HOL", "options: quick_and_dirty = true"]
    description = ["description:", "  Sorting,", "  verified."]
    for mode in (OUT_FOCUS, focus(p), focus(a), focus(x)):   # Out_Focus; on the path; a focus
        assert fields(a, mode, 0) == [] and fields(x, mode, 1) == []
    assert [fields(a, RECALL, d) for d in range(4)] == [session + description, session, [], []]
    assert [fields(x, RECALL, d) for d in range(4)] == [["imports: Main HOL-Library.Multiset"]] * 3 + [[]]


def test_recall_descends_three_levels_with_the_fields_thinning_out():
    f, a, x, s, p = deep_forest()
    assert render(f, f, RECALL) == [                   # the root: the session at depth 1, the theory at 2
        "session_A (incomplete)",
        "parent_session: HOL",
        "options: quick_and_dirty = true",
        "theories:",                                   # the lone session's header at its own indent (PRINT.md §2, §6)
        "  - theory_X (incomplete)",
        "    imports: Main HOL-Library.Multiset",
        "    declarations:",
        "      - section_S (incomplete)",              # depth 3: a line, and the summary of what is below
        "        1 proof construction incomplete: lemma_P",
    ]
    assert render(f, a, RECALL) == [                   # the session at depth 0: its description too,
        "- session_A (incomplete)",                    # and the dash, not reached from the root
        "  parent_session: HOL",
        "  options: quick_and_dirty = true",
        "  description:",
        "    Sorting,",
        "    verified.",
        "  theories:",
        "    - theory_X (incomplete)",
        "      imports: Main HOL-Library.Multiset",
        "      declarations:",
        "        - section_S (incomplete)",
        "          - lemma_P (valid statement, proof not started)",
    ]
    assert render(f, x, RECALL) == [                   # the theory: itself and its children detailed, under its header
        "- theory_X (incomplete)",
        "  imports: Main HOL-Library.Multiset",
        "  declarations:",
        "    - section_S (incomplete)",
        "      - lemma_P (valid statement, proof not started)",
    ]


def test_the_quickview_expands_the_path_to_the_focus_only():
    f, a, x, s, p = deep_forest()
    q = leaf(Lemma, s, "lemma", "Q")
    y = theory(a, "Y")
    assert render(f, f, focus(s)) == [
        "session_A (incomplete)",
        "- theory_X (incomplete)",                     # on the path: no fields
        "  - section_S (incomplete)",                  # the focus
        "    - lemma_P (valid statement, proof not started)",                  # its children: lines only
        "    - lemma_Q (not evaluated, proof not started)",
        "- theory_Y (not evaluated)",                  # off the path: the line
    ]
    assert render(f, f, focus(x)) == [
        "session_A (incomplete)",
        "- theory_X (incomplete)",                     # the focus: no field either (PRINT.md §3)
        "  - section_S (incomplete)",
        "- theory_Y (not evaluated)",
    ]
    with pytest.raises(TAT_InternalError, match="a focus outside the rendered node"):
        render(f, y, focus(s))                         # a bug in the caller
    with pytest.raises(TAT_InternalError, match="a focus under another focus"):
        render(f, f, focus(x, s))
    with pytest.raises(TAT_InternalError, match="a Relative_Focus with no focus"):
        render(f, f, focus())


def test_the_depth_is_how_far_under_a_focus_every_node_is_detailed():
    """PRINT.md §2: the focus and `depth` levels under it are detailed,
    the layer below is lines only, -1 is the whole subtree."""
    f, a, x, s, p = deep_forest()
    t = section(x, "T")
    leaf(Lemma, t, "lemma", "R")
    y = theory(a, "Y")
    subtree = [
        "- theory_X (incomplete)",
        "  - section_S (incomplete)",
        "    - lemma_P (valid statement, proof not started)",
        "  - section_T (incomplete)",
        "    - lemma_R (not evaluated, proof not started)",
    ]
    top = "session_A (incomplete)"
    assert render(f, f, focus(x, depth=1)) == [top, *subtree, "- theory_Y (not evaluated)"]
    assert render(f, f, focus(x, depth=2)) == render(f, f, focus(x, depth=-1)) \
        == [top, *subtree, "- theory_Y (not evaluated)"]
    assert render(f, f, focus(x, depth=0)) == [
        top, *subtree[:2], "  - section_T (incomplete)", "- theory_Y (not evaluated)"]
    assert render(f, f, focus(s, t, depth=-1)) == [   # several focuses: siblings, an edit's batch
        top, *subtree, "- theory_Y (not evaluated)"]
    assert render(f, f, focus(f)) == [top]             # the root as the focus: a deleted session's parent
    assert render(f, f, focus(f, depth=-1)) == [top, *subtree, "- theory_Y (not evaluated)",
                                                 empty("theory_Y")]


def test_detailed_is_a_focus_and_recall_above_the_grandchildren():
    f, a, x, s, p = deep_forest()
    assert x.detailed(focus(x), 2) and x.detailed(RECALL, 1)
    assert not x.detailed(RECALL, 2) and not x.detailed(OUT_FOCUS, 0) and not x.detailed(BRIEFING, 0)
    assert not x.detailed(focus(s), 2)                 # above the focus: on the path


# --- errors and the seen set --------------------------------------------

def failing_theory():
    f = new_forest()
    a = session(f, "A")
    x = theory(a, "X", beginning=failing("header broke"), ending=READY)
    return f, a, x


def test_a_theory_prints_its_error_once_per_run_in_a_quickview_and_whole_in_recall():
    f, a, x = failing_theory()
    block = ["  Error:", "    header broke", "  declarations:", empty("theory_X", 2)]   # the block keyed: the header (PRINT.md §2)
    first = render(f, f, focus(x))
    assert first[-4:] == block and (x.identity, "beginning") in agent(f).seen
    assert render(f, f, focus(x)) == ["session_A (incomplete)", "- theory_X (failed)",   # seen: not again, and nothing keyed
                                      empty("theory_X")]
    assert render(f, x, RECALL)[-4:] == block                         # whole under recall
    assert render(f, x, RECALL)[-4:] == block                         # every time
    assert "Error:" not in "".join(render(f, f, BRIEFING))
    agent(f).seen.clear()                                             # the context replaced
    assert render(f, f, focus(x))[-4:] == block


def test_a_recall_that_writes_an_error_whole_records_it():
    """RECALL.md §2: the quickview after a `recall` does not repeat it."""
    f, a, x = failing_theory()
    assert render(f, x, RECALL)[-4:] == ["  Error:", "    header broke", "  declarations:", empty("theory_X", 2)]
    assert render(f, f, focus(x)) == ["session_A (incomplete)", "- theory_X (failed)", empty("theory_X")]


def test_a_theory_reports_its_error_where_the_agent_is_not_looking():
    """SESSION_AND_THEORY §4's `Out_Focus` and on-the-path rows: a failed
    theory beside the focus, and one carrying the path to a focused
    child, both show the block once, and neither writes `imports`."""
    f, a, x = failing_theory()
    y = theory(a, "Y")
    p = leaf(Lemma, x, "lemma", "P")
    block = ["  Error:", "    header broke"]
    beside = render(f, f, focus(y))       # x in Out_Focus
    assert beside[1:5] == ["- theory_X (failed)", *block, "- theory_Y (not evaluated)"]
    agent(f).seen.clear()
    on_the_path = render(f, f, focus(p))   # x with a non-empty path: the block keyed, its child under the header
    assert on_the_path[1:6] == ["- theory_X (failed)", *block, "  declarations:",
                                "    - lemma_P (not evaluated, proof not started)"]
    assert "Error:" not in "".join(render(f, f, focus(p)))   # once per run


def test_a_message_shown_to_one_agent_is_shown_again_to_another_and_forget_reaches_both():
    """PRINT.md §4: the seen set is the agent's; `Conversation.forget`
    removes a key from every agent's; every key a rendering adds is the
    record `agent.seen` (LOGGING.md §4)."""
    f, a, x = failing_theory()
    other = stand_ins.agent(f.conversation, "a9f3c2d1e4b5", main=False)
    block = ["  Error:", "    header broke", "  declarations:", empty("theory_X", 2)]
    key = (x.identity, "beginning")
    assert render(f, f, focus(x))[-4:] == block
    assert render(f, f, focus(x), to=other)[-4:] == block
    assert key in agent(f).seen and key in other.seen
    assert "Error:" not in "".join(render(f, f, focus(x)) + render(f, f, focus(x), to=other))
    f.conversation.forget(key)
    assert key not in agent(f).seen and key not in other.seen
    assert render(f, f, focus(x))[-4:] == block
    assert [r["data"]["key"] for r in stand_ins.records("agent") if r["event"] == "seen"] \
        == [list(key)] * 3


def rerun(x, operation):
    """Rerun one operation of `x` as the walk does: the hook, then its
    setter, which writes the status the run left and discards the seen
    set's key (PRINT.md §4)."""
    import asyncio

    async def go():
        ev = M.Evaluation(None, False)
        if operation == "beginning":
            x._set_beginning(ev, *await M._timed(x._eval_beginning_opr()))
        else:
            x._set_ending(ev, *await M._timed(x._eval_ending_opr()))
    asyncio.run(go())


def test_a_rerun_of_the_ending_shows_its_messages_again(monkeypatch):
    f, a, x = failing_theory()
    x.evaluation_status_beginning = READY
    x.evaluation_status_ending = failing("end broke")
    render(f, f, focus(x))
    assert (x.identity, "ending") in agent(f).seen
    inside = []

    async def fails_the_same_way(conversation, name, arg):
        inside.append(render(f, x, RECALL)[-4:])      # a recall inside the round trip
        return ["end broke"]
    monkeypatch.setattr(isabelle_driver, "call", fails_the_same_way)
    rerun(x, "ending")
    assert inside == [["  Error:", "    end broke", "  declarations:", empty("theory_X", 2)]]   # the previous run's, still standing
    assert (x.identity, "ending") not in agent(f).seen
    assert render(f, f, focus(x))[-4:] == ["  Error:", "    end broke", "  declarations:", empty("theory_X", 2)]


def test_a_rerun_shows_the_messages_again_identical_or_not(monkeypatch):
    f, a, x = failing_theory()
    render(f, f, focus(x))
    assert (x.identity, "beginning") in agent(f).seen

    async def fails_the_same_way(conversation, name, arg):
        return (["header broke"], [], [])             # `TAT.Theory.begin`: the messages, nothing recorded
    monkeypatch.setattr(isabelle_driver, "call", fails_the_same_way)
    rerun(x, "beginning")
    assert (x.identity, "beginning") not in agent(f).seen and x.keywords is None   # recorded on a pass alone
    assert render(f, f, focus(x))[-4:] == ["  Error:", "    header broke", "  declarations:", empty("theory_X", 2)]


def test_a_rendering_inside_the_rerun_reads_the_previous_run_s_messages(monkeypatch):
    """PRINT.md §4: the setter writes the run's status, messages and all,
    and discards their key after the call — so a `recall`, which takes
    no lock, landing inside the round trip reads the previous run's
    messages, and the quickview after the rerun shows the new ones."""
    f, a, x = failing_theory()
    render(f, f, focus(x))
    inside = []

    async def fails_anew(conversation, name, arg):
        inside.append(render(f, x, RECALL))
        return (["header broke anew"], [], [])        # `TAT.Theory.begin`: the messages, nothing recorded
    monkeypatch.setattr(isabelle_driver, "call", fails_anew)
    rerun(x, "beginning")
    assert inside == [["- theory_X (failed)", "  imports: Main", "  Error:", "    header broke",   # a recall: depth 0
                       "  declarations:", empty("theory_X", 2)]]
    assert render(f, f, focus(x))[-4:] == ["  Error:", "    header broke anew", "  declarations:", empty("theory_X", 2)]


def test_messages_follow_the_status_that_stands():
    """PRINT.md §3: the block is the standing status's — `Error:` under a
    `CannotEvaluate`, `Notice:` under a `Ready` that reported something,
    nothing under a clean `Ready` or `not_evaluated`."""
    f, a, x = failing_theory()
    for status in (READY, NOT_EVALUATED):
        x.evaluation_status_beginning = status         # the header's message: not standing
        assert "header broke" not in "".join(render(f, x, RECALL))
    assert "Error:" not in "".join(render(f, x, RECALL))   # the ending is READY: copied through
    x.evaluation_status_ending = M.Ready((IsaTerm.from_agent("end warned"),))
    assert render(f, x, RECALL)[-4:] == ["  Notice:", "    end warned", "  declarations:", empty("theory_X", 2)]
    x.evaluation_status_ending = failing("end broke")
    assert render(f, x, RECALL)[-4:] == ["  Error:", "    end broke", "  declarations:", empty("theory_X", 2)]


def test_recall_shows_a_theory_s_errors_whole_at_depth_one_and_once_per_run_at_depth_two():
    f, a, x = failing_theory()
    assert render(f, f, RECALL)[-4:] == ["    Error:", "      header broke", "    declarations:",   # depth 2: once
                                         empty("theory_X", 3)]
    assert "Error:" not in "".join(render(f, f, RECALL))
    assert render(f, a, RECALL)[-4:] == ["      Error:", "        header broke", "      declarations:",   # depth 1: whole
                                         empty("theory_X", 4)]


# --- Forest.render and the id index ----------------------------------------

def test_the_index_lives_as_long_as_the_rendering_and_changes_no_id():
    f, a, x, s, p = deep_forest()
    q = leaf(Lemma, s, "lemma", "Q")
    y = theory(a, "Y")
    leaf(Lemma, y, "lemma", "P")                       # a second lemma_P: the first must say its theory
    without = {n: f.id_of(n) for n in f._all_nodes()}
    seen_index = {}
    class Peek(Lemma):
        def print_fields(self, indent, out, mode, depth):
            seen_index["index"] = f._index
            seen_index["ids"] = {n: f.id_of(n) for n in f._all_nodes()}
            return False
    peek = Peek(s, slot()); peek.name = "R"; peek._status = NOT_EVALUATED
    enter(s, peek, "lemma")
    without[peek] = f.id_of(peek)
    render(f, f, focus(peek))
    assert seen_index["index"] is not None and seen_index["ids"] == without
    assert f._index is None and f._agent is None
    assert without[p] == "theory_X.lemma_P" and without[q] == "lemma_Q"
    with pytest.raises(TAT_InternalError, match="outside a rendering"):
        f.agent

    class Broken(Lemma):
        def print_fields(self, indent, out, mode, depth):
            raise RuntimeError("render-bug")
    broken = Broken(s, slot()); broken.name = "Z"; broken._status = NOT_EVALUATED
    enter(s, broken, "lemma")
    with pytest.raises(RuntimeError):
        render(f, f, focus(broken))
    assert f._index is None and f._agent is None       # dropped on the way out too


# --- the summary's bounds and the check's failure block (the review of steps 10–11, §3) --

# A section at depth 3 under the lone session, recalled from the root: under `theories:` and `declarations:`
# (PRINT.md §2), and its summary one level deeper
SECTION_S = M.INDENT * 3 + "- section_S (incomplete)"
UNDER_S = M.INDENT * 4


def test_the_summary_names_five_ids_and_counts_six_each_title_in_its_number():
    """PRINT.md §2: ids up to five, the count alone past five; a group of
    one node in the singular."""
    f = new_forest()
    a = session(f, "A")
    x = theory(a, "X", beginning=READY, ending=READY)
    s = section(x, "S")
    for i in range(5):
        leaf(Lemma, s, "lemma", f"A{i}", status=READY)                     # owes its construction
    for i in range(6):
        leaf(Lemma, s, "lemma", f"K{i}", status=READY).job().outcome = jobs.Succeeded("by simp")   # owes its check
    leaf(Lemma, s, "lemma", "E")
    rendered = render(f, f, RECALL)
    at = rendered.index(SECTION_S)
    assert rendered[at + 1:] == [
        UNDER_S + "5 proof constructions incomplete: lemma_A0, lemma_A1, lemma_A2, lemma_A3, lemma_A4",
        UNDER_S + "6 proof checks incomplete",
        UNDER_S + "1 node not evaluated: lemma_E"]


def test_the_summary_s_groups_come_construction_titles_first_whatever_the_tree_order():
    """PRINT.md §2, CONSTRUCT_INTERACTION §6: the groups in the order
    construction titles, then evaluation titles, alphabetical within — a
    node owing its check before one owing its construction in tree order
    does not put the checks first."""
    f = new_forest()
    a = session(f, "A")
    x = theory(a, "X", beginning=READY, ending=READY)
    s = section(x, "S")
    leaf(Lemma, s, "lemma", "K", status=READY).job().outcome = jobs.Succeeded("by simp")   # owes its check
    leaf(Lemma, s, "lemma", "A", status=READY)                                             # owes its construction
    rendered = render(f, f, RECALL)
    at = rendered.index(SECTION_S)
    assert rendered[at + 1:] == [UNDER_S + "1 proof construction incomplete: lemma_A",
                                 UNDER_S + "1 proof check incomplete: lemma_K"]


class Constructed_Section(Section):     # a nesting node that owes a construction of its own
    construction_job_class = Proof_Construction


def test_the_summary_reads_a_nesting_node_stopped_inside_as_in_no_group():
    """PRINT.md §1, §2: a nesting node whose beginning ran and whose ending
    did not is `incomplete`, not `not evaluated`, and, its jobs depending
    on both operations, its `job_operation_status()` is not `ready`, so it
    is counted in no group, whatever it owes."""
    f = new_forest()
    a = session(f, "A")
    x = theory(a, "X", beginning=READY, ending=READY)
    s = section(x, "S")
    section(s, "T", ending=NOT_EVALUATED)
    u = Constructed_Section(s, slot()); u.name = "U"
    u.evaluation_status_beginning, u.evaluation_status_ending = READY, NOT_EVALUATED
    enter(s, u, "section")
    leaf(Lemma, s, "lemma", "P", status=READY)
    rendered = render(f, f, RECALL)
    at = rendered.index(SECTION_S)
    assert rendered[at + 1:] == [UNDER_S + "1 proof construction incomplete: lemma_P"]


def test_the_checks_failure_block_under_its_own_header_after_the_constructions():
    """CONSTRUCT_INTERACTION §6, PRINT.md §2: one block for the
    construction job when its outcome is `FAILED` and one for the check
    when `check_outcome()` is `FAILED`, each under its job class's header,
    the construction's first; a header without its colon is the class's
    bug."""
    f = new_forest()
    a = session(f, "A")
    x = theory(a, "X", beginning=READY, ending=READY)
    p = leaf(Lemma, x, "lemma", "P", status=READY)
    p.job().outcome = jobs.Succeeded("by simp")
    p._check_outcome = jobs.Failed("the replay broke")
    assert render(f, p, focus(p)) == [
        "- lemma_P (valid statement, bad proof)", "  The proof no longer holds:", "    the replay broke"]
    p.job().outcome = jobs.Failed("Sledgehammer timed out.")         # a later run failed; the stored check stays
    assert render(f, p, focus(p))[1:] == [
        "  No proof was found:", "    Sledgehammer timed out.", "  The proof no longer holds:", "    the replay broke"]
    with pytest.raises(TAT_InternalError, match="a failure header ends in a colon"):
        jobs.with_message("No proof was found", "Sledgehammer timed out.")


# --- a nesting node whose jobs read its beginning (CONSTRUCT_INTERACTION §3.1) --

class Goal_Section(Section):
    """A nesting node whose jobs read what its beginning wrote, with both
    job classes."""
    construction_job_class = Proof_Construction
    evaluation_job_class = Proof_Check
    job_operation = "beginning"


def test_the_failure_block_is_printed_unless_an_operation_the_jobs_depend_on_is_an_obstacle():
    """PRINT.md §2, CONSTRUCT_INTERACTION §6: under a nesting node whose jobs
    read its beginning, the `FAILED` construction's block is printed below
    the ending's `Error:` block when the ending is the obstacle, and on
    the node not evaluated, and not when the beginning is the obstacle."""
    f = new_forest()
    a = session(f, "A")
    x = theory(a, "X", beginning=READY, ending=READY)
    u = Goal_Section(x, slot()); u.name = "U"
    u.evaluation_status_beginning, u.evaluation_status_ending = READY, failing("end broke")
    enter(x, u, "section")
    u.job().outcome = jobs.Failed("no proof")
    assert render(f, u, focus(u)) == ["- section_U (failed)", "  Error:", "    end broke",
                                      "  No proof was found:", "    no proof", empty("section_U")]
    u.evaluation_status_beginning, u.evaluation_status_ending = NOT_EVALUATED, NOT_EVALUATED
    assert render(f, u, focus(u)) == ["- section_U (not evaluated)", "  No proof was found:", "    no proof",
                                      empty("section_U")]
    u.evaluation_status_beginning, u.evaluation_status_ending = failing("begin broke"), READY
    assert render(f, u, focus(u)) == ["- section_U (failed)", "  Error:", "    begin broke", empty("section_U")]


class Constructed_Goal_Section(Constructed_Section):
    job_operation = "beginning"


def test_the_summary_counts_a_nesting_node_whose_jobs_can_start_under_its_job_s_title():
    """PRINT.md §2: the twin of
    `test_the_summary_reads_a_nesting_node_stopped_inside_as_in_no_group`
    with `U` declaring `job_operation = "beginning"`: `incomplete` still,
    but its `job_operation_status()` is `ready`, so it is counted under the
    title of what it owes, beside the leaf; with its ending refused it is
    `failed`, and counted there alone."""
    f = new_forest()
    a = session(f, "A")
    x = theory(a, "X", beginning=READY, ending=READY)
    s = section(x, "S")
    section(s, "T", ending=NOT_EVALUATED)
    u = Constructed_Goal_Section(s, slot()); u.name = "U"
    u.evaluation_status_beginning, u.evaluation_status_ending = READY, NOT_EVALUATED
    enter(s, u, "section")
    leaf(Lemma, s, "lemma", "P", status=READY)
    rendered = render(f, f, RECALL)
    at = rendered.index(SECTION_S)
    assert rendered[at + 1:] == [UNDER_S + "2 proof constructions incomplete: section_U, lemma_P"]
    u.evaluation_status_ending = failing("end broke")
    rendered = render(f, f, RECALL)
    at = rendered.index(SECTION_S)
    assert rendered[at + 1:] == [UNDER_S + "1 proof construction incomplete: lemma_P", UNDER_S + "1 node failed: section_U"]


# --- the owing line (PRINT.md §2; node_classes/COMMON.md §3) -----------------

class Standing(Lemma):
    """A leaf answering a owing line while `ready`, as a class that defines
    does (node_classes/COMMON.md §3)."""
    def owing_line(self):
        (status,) = self.evaluation_statuses()
        return "The definition is unverified until termination is proven." if isinstance(status, M.Ready) else None


def test_the_owing_line_stands_after_the_messages_and_before_the_failure_blocks_where_detailed():
    """PRINT.md §2: the class's `owing_line()` is written under the line
    after the messages and before the failure blocks, wherever the node is
    detailed — `Recall` below depth 2, a focus — and nowhere else; `None`,
    `Node`'s default, writes nothing."""
    from Isabelle_RPC_Host.unicode import IsaTerm
    f = new_forest()
    a = session(f, "A")
    x = theory(a, "X", beginning=READY)
    p = leaf(Standing, x, "lemma", "P", status=M.Ready((IsaTerm.from_agent("Lifting is off."),)))
    p.job().outcome = jobs.Failed("Sledgehammer timed out.")
    q = leaf(Standing, x, "lemma", "Q", status=NOT_EVALUATED)
    s = section(x, "S")
    r = leaf(Standing, s, "lemma", "R", status=READY)
    line = "The definition is unverified until termination is proven."
    assert render(f, p, RECALL) == ["- lemma_P (valid statement, failed to prove)", "  Notice:", "    Lifting is off.",
                                    "  " + line, "  No proof was found:", "    Sledgehammer timed out."]
    assert render(f, q, RECALL) == ["- lemma_Q (not evaluated, proof not started)"]
    assert M.Node.owing_line(p) is None and leaf(Lemma, x, "lemma", "T", status=READY).owing_line() is None
    whole = render(f, x, RECALL)                                                  # the children under `declarations:`
    assert whole.count("      " + line) == 1 and "        " + line not in whole    # P at depth 1; R at depth 2 is not detailed
    assert whole.index("      " + line) == whole.index("        Lifting is off.") + 1 == whole.index("      No proof was found:") - 1
    assert all(line not in l for l in render(f, x, focus(x)))                     # the children in Out_Focus: lines only
    quickview = render(f, x, focus(p))                              # P a focus; its notice was seen in the recall above
    assert [l.strip() for l in quickview].count(line) == 1
    assert quickview[quickview.index("  - lemma_P (valid statement, failed to prove)") + 1] == "    " + line
    deep = render(f, x, focus(r))                                                   # R a focus at depth 2: detailed
    assert "      " + line in deep and "    " + line not in deep
    assert all(line not in l for l in render(f, x, M.BRIEFING))
    assert all(line not in l for l in render(f, a, focus(a, depth=0)))


# --- the children header (PRINT.md §2) ---------------------------------------

class Keyed_Section(Section):
    """A nesting node writing a keyed field under `Recall` and answering a
    children header, as `Theory` does."""
    def print_fields(self, indent, out, mode, depth):
        if mode is not RECALL:
            return False
        out.write(M.INDENT * indent + "parameter: x\n")
        return True

    def children_header(self):
        return "contents"


class Keyed_Goal_Section(Goal_Section):
    def children_header(self):
        return "contents"


def keyed_section(parent, name, cls=Keyed_Section, beginning=READY, ending=READY):
    k = cls(parent, slot()); k.name = name
    k.evaluation_status_beginning, k.evaluation_status_ending = beginning, ending
    return enter(parent, k, "section")


def test_the_children_header_stands_over_the_children_where_a_keyed_line_was_written():
    """PRINT.md §2: a keyed line — a field, a message block — puts the
    children one level deeper under the class's phrase and a colon;
    nothing keyed puts them directly under what was written; the header is
    written only where the children would be — not at `Out_Focus`, not at
    `Recall`'s last depth — and never under a class answering None,
    `Node`'s default."""
    f = new_forest()
    a = session(f, "A")
    x = theory(a, "X", beginning=READY, ending=READY)
    k = keyed_section(x, "K")
    leaf(Lemma, k, "lemma", "P", status=READY)
    p_line = "- lemma_P (valid statement, proof not started)"
    assert render(f, k, RECALL) == ["- section_K (incomplete)", "  parameter: x", "  contents:", "    " + p_line]
    assert render(f, k, focus(k)) == ["- section_K (incomplete)", "  " + p_line]        # a quickview: no field, no header
    k.evaluation_status_ending = failing("end broke")
    assert render(f, k, OUT_FOCUS) == ["- section_K (failed)", "  Error:", "    end broke"]   # no children shown: no header
    agent(f).seen.clear()
    assert render(f, k, focus(k)) == ["- section_K (failed)", "  Error:", "    end broke", "  contents:", "    " + p_line]
    s = section(x, "S", ending=failing("end broke"))                                     # answering None: directly under
    leaf(Lemma, s, "lemma", "Q", status=READY)
    assert render(f, s, focus(s)) == ["- section_S (failed)", "  Error:", "    end broke",
                                      "  - lemma_Q (valid statement, proof not started)"]
    deep = keyed_section(keyed_section(keyed_section(x, "L1"), "L2"), "L3")
    leaf(Lemma, deep, "lemma", "R", status=READY)
    rendered = render(f, x, RECALL)                    # L3 at depth 3: its field, no children, so no header; the summary
    at = rendered.index(M.INDENT * 6 + "- section_L3 (incomplete)")
    assert rendered[at:] == [M.INDENT * 6 + "- section_L3 (incomplete)", M.INDENT * 7 + "parameter: x",
                             M.INDENT * 7 + "1 proof construction incomplete: lemma_R"]


def test_the_empty_node_s_line_stands_under_the_header_and_a_refusing_block_writes_neither():
    """PRINT.md §2: a block with no children writes the empty node's line
    under its header; a block refusing children writes neither."""
    f = new_forest()
    a = session(f, "A")
    x = theory(a, "X", beginning=READY, ending=READY)
    k = keyed_section(x, "K")
    assert render(f, k, RECALL) == ["- section_K (complete)", "  parameter: x", "  contents:", empty("section_K", 2)]

    class Refusing(Keyed_Section):
        def children_refusal(self): return "No children here."
    r = keyed_section(x, "R", cls=Refusing)
    assert render(f, r, RECALL) == ["- section_R (complete)", "  parameter: x"]


def test_a_failure_block_is_keyed_by_its_colon():
    """PRINT.md §2: a failure block over a message is a keyed line and brings
    the header; one whose header was written with a period, the message
    empty, is not."""
    f = new_forest()
    a = session(f, "A")
    x = theory(a, "X", beginning=READY, ending=READY)
    u = keyed_section(x, "U", cls=Keyed_Goal_Section)
    u.job().outcome = jobs.Failed("no proof")
    assert render(f, u, focus(u)) == ["- section_U (incomplete)", "  No proof was found:", "    no proof",
                                      "  contents:", empty("section_U", 2)]
    u.job().outcome = jobs.Failed("")
    assert render(f, u, focus(u)) == ["- section_U (incomplete)", "  No proof was found.", empty("section_U")]


def test_a_status_s_messages_stand_under_one_header():
    """PRINT.md §3: one block per operation, every message of the status
    under its header, each message's lines one level deeper."""
    f = new_forest()
    a = session(f, "A")
    x = theory(a, "X", beginning=failing("first broke", "second broke\n  on two lines"), ending=READY)
    assert render(f, x, RECALL) == ["- theory_X (failed)", "  imports: Main", "  Error:", "    first broke",
                                    "    second broke", "      on two lines", "  declarations:", empty("theory_X", 2)]
    x.evaluation_status_beginning = READY
    x.evaluation_status_ending = M.Ready((IsaTerm.from_agent("end warned"), IsaTerm.from_agent("twice")))
    assert render(f, x, RECALL)[2:5] == ["  Notice:", "    end warned", "    twice"]
    agent(f).seen.clear()                              # in a quickview too, the `Notice:` bringing the header
    assert render(f, f, focus(x))[1:] == ["- theory_X (complete)", "  Notice:", "    end warned", "    twice",
                                          "  declarations:", empty("theory_X", 2)]


class Keyed_Lemma(Lemma):
    """A leaf writing a keyed field under `Recall` and answering a phrase:
    the framework asks a leaf for no header."""
    def print_fields(self, indent, out, mode, depth):
        if mode is not RECALL:
            return False
        out.write(M.INDENT * indent + "parameter: x\n")
        return True

    def children_header(self):
        return "contents"


def test_a_leaf_gets_no_children_header_and_print_md_section_2_s_quickview_is_as_shown():
    """PRINT.md §2: never under a leaf, whatever it writes and answers; and
    §2's third fence, the failed theory in a quickview, rendered whole."""
    f = new_forest()
    a = session(f, "A")
    x = theory(a, "X", beginning=READY, ending=READY)
    k = leaf(Keyed_Lemma, x, "lemma", "K", status=READY)
    k.job().outcome = jobs.Failed("no proof")
    assert render(f, k, RECALL) == ["- lemma_K (valid statement, failed to prove)", "  parameter: x",
                                    "  No proof was found:", "    no proof"]
    assert render(f, k, focus(k)) == ["- lemma_K (valid statement, failed to prove)", "  No proof was found:", "    no proof"]
    g = new_forest()
    b = session(g, "B")
    y = theory(b, "X", beginning=failing("Fail to load `Nowhere.Nope` because it is not found."), ending=READY)
    [_, _, quickview] = fenced_blocks(PRINT, "2.")
    assert render(g, g, focus(y))[1:] == quickview
