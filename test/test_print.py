"""Rendering (PRINT.md): the marks, the four print modes and the depth, the
fields and errors `Session` and `Theory` write (SESSION_AND_THEORY §4),
the seen set, the forest root's three forms, `Forest.render` and its id
index — pinned to the documents' own examples (PRINT.md §6, §7,
RENDER_BASELINES §5, RECALL.md §2).  Nothing here crosses the wire.
Run: python -m pytest test/test_print.py
"""

import io
import typing
from pathlib import Path

import pytest

from baselines import DOCS, fenced_blocks
from isabelle_theory_agent import isabelle_driver, model as M
from isabelle_theory_agent.exceptions import TAT_InternalError
from isabelle_theory_agent.model import (
    BRIEFING, CANNOT_EVALUATE, NOT_EVALUATED, OUT_FOCUS, RECALL, Isar_State_Slot,
    Relative_Focus, print_error)
from isabelle_theory_agent.store import Forest_Store

CONN = typing.cast(typing.Any, object())
PRINT = DOCS / "PRINT.md"


def slot(): return Isar_State_Slot.assign(CONN)


# --- the node classes of the examples --------------------------------------
# `Session` and `Theory` are the real ones; a lemma owes its proof until a
# `Theorem` exists, and a definition prints its errors in every mode but
# the briefing — a stand-in for `Define`, whose rule is undecided
# (PRINT.md §8), shaped by §7's example.

class Stub:
    name: str
    def to_store(self, rows): rows.put("name", self.name)
    @classmethod
    def from_store(cls, config, rows): raise NotImplementedError
    async def _eval_opr(self): raise NotImplementedError
    def __repr__(self): return self.name


class Lemma(Stub, M.Leaf):
    def _owes_nothing(self): return False


class Definition(Stub, M.Leaf):
    errors: list[str] = []
    def print_fields(self, indent, out, mode, depth):
        if mode is not BRIEFING and self._status is CANNOT_EVALUATE:
            for message in self.errors:
                print_error(indent, out, message)


class Section(Stub, M.StdBlock):
    output_omissible = input_omissible = True
    async def _eval_beginning_opr(self): raise NotImplementedError


KINDS = {"session": M.Session, "theory": M.Theory, "lemma": Lemma,
         "definition": Definition, "section": Section}


def enter(parent, n, kind):
    f = parent.forest()
    n.parent, n.kind, n.identity = parent, kind, f.store.next_identity()
    parent.sub_nodes.append(n)
    with f.store.transaction():
        f._store_node(n); f._store_children(parent)
    return n


def new_forest():
    return M.Forest(M.Conversation(CONN, Path(".")), Forest_Store(":memory:"), KINDS)


def session(forest, name, parent_session="HOL", options=(), description=""):
    return enter(forest, M.Session(forest, slot(), name, parent_session, list(options),
                                   description), "session")


def theory(sess, name, imports=("Main",), beginning: M.EvaluationStatus = NOT_EVALUATED,
           ending: M.EvaluationStatus = NOT_EVALUATED):
    t = enter(sess, M.Theory(sess, slot(), name, list(imports), slot(), slot()), "theory")
    t.evaluation_status_beginning, t.evaluation_status_ending = beginning, ending
    return t


def leaf(cls, parent, kind, name, status: M.EvaluationStatus = NOT_EVALUATED, errors=()):
    n = cls(parent, slot()); n.name = name; n._status = status
    if errors:
        n.errors = list(errors)
    return enter(parent, n, kind)


def section(parent, name, beginning: M.EvaluationStatus = M.READY,
            ending: M.EvaluationStatus = M.READY):
    s = Section(parent, slot(), [], slot()); s.name = name
    s.evaluation_status_beginning, s.evaluation_status_ending = beginning, ending
    return enter(parent, s, "section")


def render(forest, node, mode) -> list[str]:
    return forest.render(node, mode).splitlines()


def focus(*nodes, depth=0):
    return Relative_Focus(frozenset(nodes), depth)


# --- the documents' examples ------------------------------------------------

def example_forest():
    """PRINT.md §7's forest: one session, three theories."""
    f = new_forest()
    a = session(f, "A")
    theory(a, "Base", beginning=M.READY, ending=M.READY)
    x = theory(a, "X", beginning=M.READY)
    leaf(Lemma, x, "lemma", "A", status=M.READY)
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
    base = theory(a, "Base", beginning=M.READY, ending=M.READY)
    proven = leaf(Lemma, base, "lemma", "A", status=M.READY)
    proven._owes_nothing = lambda: True                    # type: ignore[method-assign]
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
    theory(a, "Base", beginning=M.READY, ending=M.READY)
    x = theory(a, "X")
    assert render(f, f, focus(x)) == lone_session

    f = new_forest()
    for mode in (BRIEFING, RECALL, focus(f)):
        assert render(f, f, mode) == empty
    assert empty[1].strip() == M.EMPTY_FOREST


def test_the_lines_of_render_baselines_section_5():
    node_lines, error_block = fenced_blocks(DOCS / "RENDER_BASELINES.md", "5.")
    f = new_forest()
    a = session(f, "A")
    x = theory(a, "X", beginning=M.READY, ending=M.READY)
    f_ = leaf(Definition, x, "definition", "f", status=CANNOT_EVALUATE, errors=["e"])
    p = leaf(Lemma, x, "lemma", "P")
    lines = []
    for status, owes in ((M.READY, False), (NOT_EVALUATED, True), (M.READY, True)):
        p._status = status
        p._owes_nothing = lambda owes=owes: not owes          # type: ignore[method-assign]
        lines.append(render(f, p, OUT_FOCUS)[0])
    lines.insert(2, render(f, f_, OUT_FOCUS)[0])
    assert lines == node_lines
    out = io.StringIO()
    print_error(0, out, "Type unification failed: ...")
    assert out.getvalue().splitlines() == error_block


# --- the mark ---------------------------------------------------------------

def test_the_default_mark_first_row_wins():
    f = new_forest()
    a = session(f, "A")
    base = theory(a, "Base", beginning=M.READY, ending=M.READY)
    g = leaf(Definition, base, "definition", "g", status=M.READY)
    x = theory(a, "X", beginning=M.READY)
    p = leaf(Lemma, x, "lemma", "P", status=M.READY)
    q = leaf(Lemma, x, "lemma", "Q")
    mark = lambda n: n.mark(OUT_FOCUS, 1)             # noqa: E731
    assert mark(base) == "success" and mark(g) == "success" and mark(a) is None
    assert mark(p) is None                             # ran, owes its proof
    assert mark(q) == "not evaluated"
    assert mark(x) == "not evaluated"                  # its ending has not run
    x.evaluation_status_beginning = CANNOT_EVALUATE
    assert mark(x) == "failed"                         # an own stop beats the ending's not evaluated
    empty = session(f, "Empty")
    assert mark(empty) == "success"                    # nothing under it, nothing owed


def test_the_field_lines_of_session_and_theory_section_4():
    [lines] = fenced_blocks(DOCS / "node_classes" / "SESSION_AND_THEORY.md", "4.")
    f = new_forest()
    a = session(f, "A", options=[{"name": "quick_and_dirty", "value": "true"},
                                 {"name": "document", "value": "false"}],
                description="Sorting, verified.")
    theory(a, "X", imports=("Main", "HOL-Library.Multiset"))
    assert render(f, f, RECALL)[1:] == lines[:4] + ["- theory_X (not evaluated)", "  " + lines[4]]
    bare = new_forest()
    session(bare, "B")
    assert render(bare, bare, RECALL) == ["session_B (success)", "parent_session: HOL"]


def test_a_class_may_say_more_than_the_default():
    class Theorem(Lemma):
        def mark(self, mode, depth):
            return super().mark(mode, depth) or "not proven"
    f = new_forest()
    a = session(f, "A")
    x = theory(a, "X", beginning=M.READY, ending=M.READY)
    n = Theorem(x, slot()); n.name = "P"; n._status = M.READY
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
    x = theory(a, "X", imports=("Main", "HOL-Library.Multiset"), beginning=M.READY)
    s = section(x, "S")
    p = leaf(Lemma, s, "lemma", "P", status=M.READY)
    return f, a, x, s, p


def test_briefing_is_every_line_to_the_bottom_with_the_briefing_fields():
    f, *_ = deep_forest()
    assert render(f, f, BRIEFING) == [
        "session_A",
        "parent_session: HOL",
        "- theory_X (not evaluated)",
        "  imports: Main HOL-Library.Multiset",
        "  - section_S",
        "    - lemma_P",
    ]


def test_recall_descends_three_levels_with_the_fields_thinning_out():
    f, a, x, s, p = deep_forest()
    assert render(f, f, RECALL) == [                   # the root: sessions detailed, theories short
        "session_A",
        "parent_session: HOL",
        "options: quick_and_dirty = true",
        "description:",
        "  Sorting,",
        "  verified.",
        "- theory_X (not evaluated)",
        "  imports: Main HOL-Library.Multiset",
        "  - section_S",                               # depth 3: a line, nothing under it
    ]
    assert render(f, x, RECALL) == [                   # the theory: itself and its children detailed
        "- theory_X (not evaluated)",
        "  imports: Main HOL-Library.Multiset",
        "  - section_S",
        "    - lemma_P",
    ]
    assert render(f, a, RECALL)[0] == "- session_A"    # not reached from the root: the dash stays


def test_the_quickview_expands_the_path_to_the_focus_only():
    f, a, x, s, p = deep_forest()
    q = leaf(Lemma, s, "lemma", "Q")
    y = theory(a, "Y")
    assert render(f, f, focus(s)) == [
        "session_A",
        "- theory_X (not evaluated)",                  # on the path: no fields
        "  - section_S",                               # the focus
        "    - lemma_P",                               # its children: lines only
        "    - lemma_Q (not evaluated)",
        "- theory_Y (not evaluated)",                  # off the path: the line
    ]
    assert render(f, f, focus(x)) == [
        "session_A",
        "- theory_X (not evaluated)",
        "  imports: Main HOL-Library.Multiset",        # the focus writes its fields
        "  - section_S",
        "- theory_Y (not evaluated)",
    ]
    with pytest.raises(TAT_InternalError, match="a focus outside the rendered node"):
        f.render(y, focus(s))                          # a bug in the caller
    with pytest.raises(TAT_InternalError, match="a focus under another focus"):
        f.render(f, focus(x, s))
    with pytest.raises(TAT_InternalError, match="a Relative_Focus with no focus"):
        f.render(f, focus())


def test_the_depth_is_how_far_under_a_focus_every_node_is_detailed():
    """PRINT.md §2: the focus and `depth` levels under it are detailed,
    the layer below is lines only, -1 is the whole subtree."""
    f, a, x, s, p = deep_forest()
    t = section(x, "T")
    leaf(Lemma, t, "lemma", "R")
    y = theory(a, "Y")
    subtree = [
        "- theory_X (not evaluated)",
        "  imports: Main HOL-Library.Multiset",
        "  - section_S",
        "    - lemma_P",
        "  - section_T",
        "    - lemma_R (not evaluated)",
    ]
    assert render(f, f, focus(x, depth=1)) == ["session_A", *subtree, "- theory_Y (not evaluated)"]
    assert render(f, f, focus(x, depth=2)) == render(f, f, focus(x, depth=-1)) \
        == ["session_A", *subtree, "- theory_Y (not evaluated)"]
    assert render(f, f, focus(x, depth=0)) == [
        "session_A", *subtree[:3], "  - section_T", "- theory_Y (not evaluated)"]
    assert render(f, f, focus(s, t, depth=-1)) == [   # several focuses: siblings, an edit's batch
        "session_A", "- theory_X (not evaluated)", *subtree[2:], "- theory_Y (not evaluated)"]
    assert render(f, f, focus(f)) == ["session_A"]     # the root as the focus: a deleted session's parent
    assert render(f, f, focus(f, depth=-1)) == [
        "session_A", "parent_session: HOL", "options: quick_and_dirty = true", "description:",
        "  Sorting,", "  verified.", *subtree, "- theory_Y (not evaluated)", "  imports: Main"]


def test_detailed_is_a_focus_and_recall_above_the_grandchildren():
    f, a, x, s, p = deep_forest()
    assert x.detailed(focus(x), 2) and x.detailed(RECALL, 1)
    assert not x.detailed(RECALL, 2) and not x.detailed(OUT_FOCUS, 0) and not x.detailed(BRIEFING, 0)
    assert not x.detailed(focus(s), 2)                 # above the focus: on the path


# --- errors and the seen set --------------------------------------------

def failing_theory():
    f = new_forest()
    a = session(f, "A")
    x = theory(a, "X", beginning=CANNOT_EVALUATE, ending=M.READY)
    x.beginning_errors = ["header broke"]
    return f, a, x


def test_a_theory_prints_its_error_once_per_run_in_a_quickview_and_whole_in_recall():
    f, a, x = failing_theory()
    block = ["  Error:", "    header broke"]
    first = render(f, f, focus(x))
    assert first[-2:] == block and (x.identity, "beginning") in f.conversation.seen
    assert render(f, f, focus(x))[-1] == "  imports: Main"   # seen: not again
    assert render(f, x, RECALL)[-2:] == block                         # whole under recall
    assert render(f, x, RECALL)[-2:] == block                         # every time
    assert "Error:" not in "".join(render(f, f, BRIEFING))
    f.conversation.seen.clear()                                       # the context replaced
    assert render(f, f, focus(x))[-2:] == block


def test_a_recall_that_writes_an_error_whole_records_it():
    """RECALL.md §2: the quickview after a `recall` does not repeat it."""
    f, a, x = failing_theory()
    assert render(f, x, RECALL)[-2:] == ["  Error:", "    header broke"]
    assert render(f, f, focus(x))[-1] == "  imports: Main"


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
    f.conversation.seen.clear()
    on_the_path = render(f, f, focus(p))   # x with a non-empty path
    assert on_the_path[1:5] == ["- theory_X (failed)", *block, "  - lemma_P (not evaluated)"]
    assert "Error:" not in "".join(render(f, f, focus(p)))   # once per run


def test_the_briefing_closure_clears_the_seen_set_and_renders_the_root():
    from isabelle_theory_agent import mcp
    f, a, x = failing_theory()
    render(f, f, focus(x))
    assert f.conversation.seen
    answer = mcp.on_compaction(f)()
    assert not f.conversation.seen and answer == f.render(f, BRIEFING)


def test_a_rerun_of_the_ending_shows_its_messages_again(monkeypatch):
    f, a, x = failing_theory()
    x.evaluation_status_beginning, x.beginning_errors = M.READY, []
    x.evaluation_status_ending, x.ending_errors = CANNOT_EVALUATE, ["end broke"]
    render(f, f, focus(x))
    assert (x.identity, "ending") in f.conversation.seen
    inside = []

    async def fails_the_same_way(conn, name, arg):
        inside.append(render(f, x, RECALL)[-2:])      # a recall inside the round trip
        return ["end broke"]
    monkeypatch.setattr(isabelle_driver, "call", fails_the_same_way)

    async def rerun():
        assert not await x._eval_ending_opr()
    import asyncio
    asyncio.run(rerun())
    assert inside == [["  Error:", "    end broke"]]   # the previous run's, still standing
    assert (x.identity, "ending") not in f.conversation.seen
    assert render(f, f, focus(x))[-2:] == ["  Error:", "    end broke"]


def test_a_rerun_shows_the_messages_again_identical_or_not(monkeypatch):
    f, a, x = failing_theory()
    render(f, f, focus(x))
    assert (x.identity, "beginning") in f.conversation.seen

    async def fails_the_same_way(conn, name, arg):
        return ["header broke"]
    monkeypatch.setattr(isabelle_driver, "call", fails_the_same_way)

    async def rerun():
        assert not await x._eval_beginning_opr()
    import asyncio
    asyncio.run(rerun())
    assert (x.identity, "beginning") not in f.conversation.seen
    assert render(f, f, focus(x))[-2:] == ["  Error:", "    header broke"]


def test_a_rendering_inside_the_rerun_reads_the_previous_run_s_messages(monkeypatch):
    """PRINT.md §4: the hook records the run's messages and discards their
    key together, after the call — so a `recall`, which takes no lock,
    landing inside the round trip reads the previous run's messages, and
    the quickview after the rerun shows the new ones."""
    f, a, x = failing_theory()
    render(f, f, focus(x))
    inside = []

    async def fails_anew(conn, name, arg):
        inside.append(render(f, x, RECALL))
        return ["header broke anew"]
    monkeypatch.setattr(isabelle_driver, "call", fails_anew)
    import asyncio
    asyncio.run(x._eval_beginning_opr())
    assert inside == [["- theory_X (failed)", "  imports: Main", "  Error:", "    header broke"]]
    assert render(f, f, focus(x))[-2:] == ["  Error:", "    header broke anew"]


def test_messages_show_only_while_the_operation_is_an_own_stop():
    f, a, x = failing_theory()
    x.ending_errors = ["end broke"]                    # left by an earlier run
    for status in (M.READY, NOT_EVALUATED):
        x.evaluation_status_beginning = status         # the header's message: not standing
        assert "header broke" not in "".join(render(f, x, RECALL))
    assert "end broke" not in "".join(render(f, x, RECALL))   # the ending is READY: copied through
    x.evaluation_status_ending = CANNOT_EVALUATE
    assert render(f, x, RECALL)[-2:] == ["  Error:", "    end broke"]


def test_recall_shows_a_theory_s_errors_whole_at_depth_one_and_once_per_run_at_depth_two():
    f, a, x = failing_theory()
    assert render(f, f, RECALL)[-2:] == ["  Error:", "    header broke"]   # depth 2: once
    assert "Error:" not in "".join(render(f, f, RECALL))
    assert render(f, a, RECALL)[-2:] == ["    Error:", "      header broke"]   # depth 1: whole


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
    peek = Peek(s, slot()); peek.name = "R"; peek._status = NOT_EVALUATED
    enter(s, peek, "lemma")
    without[peek] = f.id_of(peek)
    f.render(f, BRIEFING)
    assert seen_index["index"] is not None and seen_index["ids"] == without
    assert f._index is None
    assert without[p] == "theory_X.lemma_P" and without[q] == "lemma_Q"

    class Broken(Lemma):
        def print_fields(self, indent, out, mode, depth):
            raise RuntimeError("render-bug")
    broken = Broken(s, slot()); broken.name = "Z"; broken._status = NOT_EVALUATED
    enter(s, broken, "lemma")
    with pytest.raises(RuntimeError):
        f.render(f, BRIEFING)
    assert f._index is None                            # dropped on the way out too
