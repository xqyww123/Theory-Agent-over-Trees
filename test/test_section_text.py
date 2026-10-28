"""`Section` and `Text` (node_classes/SECTION_AND_TEXT.md): with no
Isabelle, the schemas and the descriptions (§2, §3), `gen`'s refusals and
the field check (§4), the fields as the nodes hold, store and print them
(§1, §2, §8), the level rule and the copy (§6), the caption and the
renderings (§8), the emitted text (§5), the id properties (§9); through
the std harness, a theory of headings and passages evaluated and
recalled, a level refused, the file rendered (§5, §6, §8).
Run: python -m pytest test/test_section_text.py
"""

import io
import json

import jsoncomment
import pytest

import stand_ins
import test_model as tm
import test_session_theory as ts
from baselines import DOCS, fenced_blocks, fenced_lines
from harness import text_of
from baselines import composed_refusal
from Isabelle_RPC_Host.unicode import IsaTerm
from isabelle_theory_agent import compile as C, edit, model as M
from isabelle_theory_agent.exceptions import (
    GRAMMARS, DuplicateName, InvalidField, InvalidName, RawASTError, UnexpectedChildren)
from isabelle_theory_agent.jobs import NOT_STARTED, PASSED
from isabelle_theory_agent.std import section, text as text_module
from isabelle_theory_agent.std.section import USE_A_LOWER_LEVEL, Section
from isabelle_theory_agent.std.text import Text
from isabelle_theory_agent.store import Forest_Store
from std_forest import KINDS, assert_a_missing_row_is_refused_at_start, field_check, forest, insert, inv, refused
from test_descriptions import descriptions
from test_model import locked, run
from test_session_theory import Forest_Under_Test, session, theory
from test_theorem import PROVED, lemma, with_proof

table = ts.table                    # the fake state slot table and the fake wire, per test
DOC = DOCS / "node_classes" / "SECTION_AND_TEXT.md"

BASICS, OVERVIEW = (json.loads("\n".join(block)) for block in fenced_blocks(DOC, "2.")[:2])     # §2's two constructs
INTRO, REV_REV, LENGTHS = BASICS["children"]
(REV_LENGTH,) = LENGTHS["children"]
[TITLE_EMPTY, TEXT_EMPTY] = fenced_blocks(DOC, "4.")[0]          # §4's two sentences
[LEVEL_SENTENCE] = fenced_blocks(DOC, "6.")[0]                   # §6's refusal, a `section` under `section_A`


def heading(name="Basics", title="Basic lemmas about reversal", kind="section", **fields):
    return {"kind": kind, "name": name, "title": title, **fields}


def passage(name="intro", text="We start with the two lemmas every later proof uses.", **fields):
    return {"kind": "text", "name": name, "text": text, **fields}


# --- the schemas and the descriptions (§2, §3) ------------------------------

def test_the_schemas_and_the_descriptions_are_the_documents():
    [_, _, section_schema, text_schema] = fenced_blocks(DOC, "2.")
    assert Section.construct_schema == jsoncomment.JsonComment().loads("\n".join(section_schema))
    assert Text.construct_schema == jsoncomment.JsonComment().loads("\n".join(text_schema))
    assert list(section.KINDS) == ["chapter", "section", "subsection", "subsubsection", "paragraph", "subparagraph"]
    assert list(text_module.KINDS) == ["text"]
    documented = set(fenced_lines(DOC, "3."))
    assert set(descriptions(Section.construct_schema)) | set(descriptions(Text.construct_schema)) == documented
    assert BASICS == heading(children=[INTRO, REV_REV, LENGTHS]) and INTRO == passage()
    assert LENGTHS == heading("Lengths", "Length is preserved", "subsection", children=[REV_LENGTH])
    assert OVERVIEW == passage("overview", "Insertion sort, and its correctness.\n\nSortedness is @{const sorted} of the list library.")
    assert issubclass(Section, M.StdBlock) and issubclass(Text, M.Leaf)
    for cls in (Section, Text):
        assert cls.construction_job_class is None and cls.evaluation_job_class is None     # no jobs
        assert "english" not in (cls.construct_schema or {})["properties"]                  # no `text` line (§1)
        assert "mark" not in vars(cls)                                                      # the framework's (§7)
    assert {"_eval_beginning_opr", "emit_beginning", "caption", "children_header"} <= set(vars(Section))
    assert not {"_eval_ending_opr", "emit_ending", "print_fields"} & set(vars(Section))    # no ending command; nothing under the line
    assert {"_eval_opr", "emit", "print_fields"} <= set(vars(Text)) and "caption" not in vars(Text)
    assert Section.children_header(None) == "declarations" == M.THEORY_CHILDREN_HEADER  # type: ignore[arg-type]


# --- `gen` (§2, §4) ----------------------------------------------------------

def test_gen_keeps_the_fields_and_names_the_nodes():
    """§2: the title normalised, the text kept as written, antiquotations
    and all; the ids."""
    f, x = forest(BASICS, OVERVIEW, heading("Spaced", "  A\n title\t with   room  "), passage("raw", " kept\n\n as written \n"),
                  heading("Anti", "The \\<^const>‹sorted› list, @{term \"rev xs\"} and @{noindent}then"),
                  passage("anti", "By \\<^emph>‹‹nested› too› and @{cite \"key\"}; @{term rev\nleft open"))
    basics, overview, spaced, raw, anti_title, anti_text = x.sub_nodes
    assert isinstance(basics, Section) and basics.kind == "section" and basics.name == "Basics"
    assert basics.title == "Basic lemmas about reversal" and f.id_of(basics) == "section_Basics"
    intro, rev_rev, lengths = basics.sub_nodes
    assert isinstance(intro, Text) and intro.text == INTRO["text"] and f.id_of(intro) == "text_intro"
    assert f.id_of(rev_rev) == "lemma_rev_rev"
    assert isinstance(lengths, Section) and lengths.kind == "subsection" and f.id_of(lengths) == "subsection_Lengths"
    assert f.id_of(lengths.sub_nodes[0]) == "lemma_rev_length"
    assert overview.text == OVERVIEW["text"]                                # the blank line kept
    assert spaced.title == "A title with room"                                # normalised (§2)
    assert raw.text == " kept\n\n as written \n"                              # not normalised (§2)
    assert anti_title.title == 'The \\<^const>‹sorted› list, @{term "rev xs"} and @{noindent}then'
    assert anti_text.text == 'By \\<^emph>‹‹nested› too› and @{cite "key"}; @{term rev\nleft open'
    assert basics._state_before_ending in basics._states_inside() and intro.state is not basics.state
    (dashed,) = insert(f, x, 4, [heading("intro-duction", "Hyphens", "chapter")])     # the framework's grammar (§1)
    assert dashed.kind == "chapter" and f.id_of(dashed) == "chapter_intro-duction"
    inv(f)


def test_gen_refuses_as_section_4_says():
    """§4: `gen` refuses nothing; the node's name, which the framework
    judges after `gen`; a missing field, an `english`, a `children` on a
    passage, by the framework."""
    f, x = forest()
    e = refused(f, x, [heading("Basic lemmas")], InvalidName)
    assert (e.name, e.grammar) == ("Basic lemmas", "name")
    assert str(e) == "At `constructs[0]`: `Basic lemmas` is not a valid name: a name " + GRAMMARS["name"] + "."
    for name in ("1st", "intro_", "intro-", "", "α"):
        assert refused(f, x, [heading(name)], InvalidName).grammar == "name"
        assert refused(f, x, [passage(name)], InvalidName).grammar == "name"
    assert refused(f, x, [heading("Basic lemmas", title="")], InvalidName).name == "Basic lemmas"    # `gen` judges no title
    for raw in ({"kind": "section", "name": "n"},                       # no `title`
                {"kind": "section", "title": "t"},                      # no `name`
                {"kind": "text", "name": "n"},                          # no `text`
                {**heading(), "title": 1}, {**passage(), "text": ["a"]},
                heading(english="e"), passage(english="e"),             # no `english` (§2)
                {"kind": "sections", "name": "n", "title": "t"}):       # no such kind
        refused(f, x, [raw], RawASTError)
    refused(f, x, [passage(children=[])], UnexpectedChildren)           # a leaf
    assert x.sub_nodes == []
    inv(f)


def test_the_field_check_refuses_as_section_4_says():
    """§4's field check, each sentence told alone, no path before it: an
    empty `title`, after normalisation, and a `text` of whitespace alone;
    a `title` and a `text` with a character admitted."""
    f, x = forest()
    for title in ("", " ", "\n\t "):
        e = field_check(f, x, [heading(title=title)])
        assert str(e) == TITLE_EMPTY and e.field == "title"
    for text in ("", "   ", "\n\n"):
        e = field_check(f, x, [passage(text=text)])
        assert str(e) == TEXT_EMPTY and e.field == "text"
    assert field_check(f, x, [heading(title=" a ")]) is None and field_check(f, x, [passage(text="\na\n")]) is None
    assert x.sub_nodes == []
    inv(f)


def test_a_sibling_bearing_the_node_s_id_component_is_the_framework_s_duplicate_name():
    f, x = forest(BASICS, OVERVIEW)
    e = refused(f, x, [heading(title="Another")], DuplicateName)
    assert e.id_component == "section_Basics" and e.taken_by == "section_Basics"
    e = refused(f, x, [passage("overview", "Another")], DuplicateName)
    assert e.id_component == "text_overview"
    (other,) = insert(f, x, 0, [heading(kind="chapter", title="Another")])          # another kind: another component
    assert f.id_of(other) == "chapter_Basics"
    inv(f)


# --- the store (§1) ---------------------------------------------------------------

def test_the_fields_are_stored_and_a_missing_row_is_refused_at_start(tmp_path):
    path = tmp_path / "TAT.sqlite"
    f, x = forest(BASICS, OVERVIEW, store=Forest_Store(path, ts.stand_ins.log()))
    basics, overview = x.sub_nodes
    rows = f.store.fields(basics.identity)
    assert rows["name"] == "Basics" and rows["title"] == "Basic lemmas about reversal"
    rows = f.store.fields(overview.identity)
    assert rows["name"] == "overview" and rows["text"] == OVERVIEW["text"]
    f.store.close()
    f2 = Forest_Under_Test(store=Forest_Store(path, ts.stand_ins.log()), kinds=KINDS)
    basics2, overview2 = f2.sub_nodes[0].sub_nodes[0].sub_nodes
    assert isinstance(basics2, Section) and (basics2.kind, basics2.name, basics2.title) == ("section", "Basics", basics.title)
    assert isinstance(overview2, Text) and (overview2.name, overview2.text) == ("overview", OVERVIEW["text"])
    assert [c.name for c in basics2.sub_nodes] == ["intro", "rev_rev", "Lengths"]
    f2.store.close()
    assert_a_missing_row_is_refused_at_start(path, basics.identity, ("name", "title"))
    assert_a_missing_row_is_refused_at_start(path, overview.identity, ("name", "text"))


# --- the beginning, the level and the copy (§6), the mark (§7) ----------------------

def test_the_level_rule_and_the_beginning_s_copy():
    """§6: a heading under headings of higher levels alone, through other
    blocks, runs, levels skipped; one under a heading of the same or a
    lower level is an obstacle with the refusal naming that heading, its
    children `not_evaluated`, its ending `Ready` by the copy; a `Text` and
    a heading that runs copy their input slot into their resulting slot;
    a move is judged anew; the marks the framework's (§7)."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        heading("Ch", "One", "chapter", children=[
            passage("p1", "First."),
            heading("Sub", "Skipped", "subsubsection", children=[passage("p2", "Second.")]),
            {"kind": "block", "name": "B", "children": [heading("Deep", "Through a block", "paragraph")]}]),
        heading("Sec", "Two", children=[
            heading("Same", "Same level", children=[passage("p3", "Third.")]),
            {"kind": "block", "name": "C", "children": [heading("Up", "Higher", "chapter")]}]),
        passage("p4", "Fourth.")]})])
    (x,) = s.sub_nodes
    ch, sec, p4 = x.sub_nodes
    p1, sub, b = ch.sub_nodes
    (deep,) = b.sub_nodes
    same, c = sec.sub_nodes
    (up,) = c.sub_nodes                                                         # refused through a block too
    run(x.evaluate_to(None, True))
    for node in (ch, sub, deep, sec):
        assert node.evaluation_status_beginning == M.READY_CLEAN and node.evaluation_status_ending == M.READY_CLEAN, node.name
    for node in (p1, sub.sub_nodes[0], p4):
        assert node._status == M.READY_CLEAN, node.name
    for node in (same, up):
        assert isinstance(node.evaluation_status_beginning, M.CannotEvaluate), node.name
        assert [m.unicode for m in node.evaluation_status_beginning.messages] == [
            composed_refusal(node.kind, f.full_id(sec), USE_A_LOWER_LEVEL)]
        assert node.evaluation_status_ending == M.READY_CLEAN                   # the framework's copy past the block
        assert all(c._status is M.NOT_EVALUATED for c in node.sub_nodes)
    copies = [(src, dst) for name, src, dst in tm.TABLE.calls if name == "copy"]
    assert (ch.state.name, p1.state.name) in copies                              # the beginning: into the first child's slot
    assert (deep.state.name, deep._state_before_ending.name) in copies           # no child: into the slot before the ending
    assert (p4.state.name, p4.resulting_state().name) in copies                  # a passage
    assert (same.state.name, same.sub_nodes[0].state.name) not in copies         # refused: nothing written
    assert (ch.mark(M.BRIEFING, 0), same.mark(M.BRIEFING, 0), p4.mark(M.BRIEFING, 0)) == ("complete", "failed", "complete")
    assert sec.mark(M.BRIEFING, 0) == "incomplete" and not sec.is_finished() and ch.is_finished()
    # moved under a deeper heading, the heading is judged anew: `Sub` under `Deep`
    run(locked(f, edit.move(sub, deep, 0)))
    assert sub.evaluation_status_beginning is M.NOT_EVALUATED
    run(x.evaluate_to(None, True))
    assert [m.unicode for m in sub.evaluation_status_beginning.messages] == [
        composed_refusal("subsubsection", f.full_id(deep), USE_A_LOWER_LEVEL)]
    run(locked(f, edit.move(same, x, 3)))                                        # and back to the theory: no heading above
    run(x.evaluate_to(None, True))
    assert same.evaluation_status_beginning == M.READY_CLEAN
    (fresh,) = insert(f, x, 0, [heading("Fresh", "New")])
    assert fresh.mark(M.BRIEFING, 0) == "not evaluated"
    inv(f)


def test_the_level_rule_names_the_outermost_heading():
    """§6's refusal, as the placement check composes it: a `section` under
    a `subsection` under a `section` names the outermost heading it
    cannot stand under, `section_A`; the `subsection` stands."""
    f = Forest_Under_Test(kinds=KINDS)
    insert(f, f, 0, [session("S", theory("X") | {"children": [
        heading("A", "A", children=[heading("B", "B", "subsection", children=[heading("C", "C")])])]})])
    (x,) = f.sub_nodes[0].sub_nodes
    (a,) = x.sub_nodes
    (b,) = a.sub_nodes
    (c,) = b.sub_nodes
    assert b._refusal() is None and c._refusal() == LEVEL_SENTENCE
    assert LEVEL_SENTENCE == composed_refusal("section", f.full_id(a), USE_A_LOWER_LEVEL)
    inv(f)


# --- the caption, the fields and the renderings (§8) --------------------------------

def basics_forest():
    """§2's heading in `theory_X` of `session_A`, in the states §8's
    renderings show: `rev_rev` proven, `rev_length` owing its proof, the
    theory's ending not yet run.  The statuses are set by hand, so the
    invariants are not asserted on this forest."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("A", theory("X") | {"children": [BASICS]})])
    (x,) = s.sub_nodes
    (basics,) = x.sub_nodes
    intro, rev_rev, lengths = basics.sub_nodes
    (rev_length,) = lengths.sub_nodes
    x.evaluation_status_beginning, x.evaluation_status_ending = M.READY_CLEAN, M.NOT_EVALUATED
    for node in (basics, lengths):
        node.evaluation_status_beginning = node.evaluation_status_ending = M.READY_CLEAN
    intro._status = M.READY_CLEAN
    with_proof(rev_rev, M.READY_CLEAN, PROVED, PASSED)
    with_proof(rev_length, M.READY_CLEAN, NOT_STARTED)
    return f, x, basics, intro, rev_rev, lengths, rev_length


def test_the_caption_and_print_fields_by_mode():
    f, x, basics, intro, rev_rev, lengths, rev_length = basics_forest()
    on = M.Relative_Focus(frozenset({basics}), 0)
    path = M.Relative_Focus(frozenset({rev_rev}), 0)
    assert [basics.caption(M.RECALL, d) for d in range(4)] == [basics.title, basics.title, None, None]
    assert basics.caption(on, 0) == basics.title and basics.caption(path, 0) is None
    assert basics.caption(M.OUT_FOCUS, 0) is None and basics.caption(M.BRIEFING, 0) is None

    def fields(node, mode, depth):
        out = io.StringIO()
        keyed = node.print_fields(1, out, mode, depth)
        return keyed, out.getvalue()
    assert all(fields(basics, mode, d) == (False, "") for mode in (M.RECALL, M.OUT_FOCUS, on) for d in range(4))
    assert [fields(intro, M.RECALL, d) for d in range(4)] == [
        (False, "  We start with the two lemmas every later proof uses.\n")] * 2 + [(False, "")] * 2
    assert fields(intro, M.OUT_FOCUS, 0) == (False, "") and fields(intro, M.Relative_Focus(frozenset({intro}), 0), 0) == (False, "")
    (overview,) = insert(f, x, 1, [OVERVIEW])
    assert fields(overview, M.RECALL, 1) == (False, "  Insertion sort, and its correctness.\n  \n  Sortedness is @{const sorted} of the list library.\n")
    (trailing,) = insert(f, x, 2, [passage("trailing", "Ends with a line break.\n\n")])
    assert fields(trailing, M.RECALL, 0) == (False, "  Ends with a line break.\n")


def test_section_8_s_renderings():
    [recall_heading, recall_theory, quickview, refused_heading] = fenced_blocks(DOC, "8.")
    f, x, basics, intro, rev_rev, lengths, rev_length = basics_forest()
    me = stand_ins.agent(f.conversation)
    assert f.render(basics, M.RECALL, me).splitlines() == recall_heading
    assert f.render(x, M.RECALL, me).splitlines() == recall_theory
    # the quickview: a second heading appended, with a passage, a subsection and a lemma, all not evaluated;
    # a second theory, complete
    (sorting,) = insert(f, x, 1, [heading("Sorting", "Insertion sort", children=[
        passage("overview", "Insertion sort, and its correctness."),
        heading("Correctness", "Sortedness and permutation", "subsection", children=[
            lemma("isort_sorted", "sorted (isort xs)", "The sort sorts", premises=())])])])
    (s,) = f.sub_nodes
    (y,) = insert(f, s, 1, [theory("Y")])
    y.evaluation_status_beginning = y.evaluation_status_ending = M.READY_CLEAN
    assert f.render(f, M.Relative_Focus(frozenset({sorting}), -1), me).splitlines() == quickview
    # a `section` under a `subsection`, refused: the `Error:` block, then the children under `declarations:`
    g = Forest_Under_Test(kinds=KINDS)
    insert(g, g, 0, [session("A", theory("X") | {"children": [
        heading("Lengths", "Length is preserved", "subsection", children=[
            heading("Details", "The details", children=[REV_LENGTH])])]})])
    (details,) = g.sub_nodes[0].sub_nodes[0].sub_nodes[0].sub_nodes
    assert details._refusal() == composed_refusal("section", g.full_id(details.parent), USE_A_LOWER_LEVEL)
    details.evaluation_status_beginning = M.CannotEvaluate((IsaTerm.from_agent(details._refusal()),))
    details.evaluation_status_ending = M.READY_CLEAN
    with_proof(details.sub_nodes[0], M.NOT_EVALUATED, NOT_STARTED)
    assert g.render(details, M.RECALL, stand_ins.agent(g.conversation)).splitlines() == refused_heading


# --- emission (§5) ------------------------------------------------------------

def test_the_emitted_text_is_section_5_s():
    [heading_text, passage_text] = fenced_blocks(DOC, "5.")
    f, x, basics, intro, rev_rev, lengths, rev_length = basics_forest()
    x.keywords = frozenset()                                 # recorded by a header run, which emission presupposes
    with_proof(rev_length, M.READY_CLEAN, PROVED, PASSED)
    (overview,) = insert(f, x, 1, [OVERVIEW])
    overview._status = M.READY_CLEAN

    def emitted(node, indent=0) -> list[str]:
        """In the `unicode` spelling; the file's `\\<name>` form is the
        compile's conversion (COMPILATION.md §2)."""
        out = io.StringIO()
        assert node.emit(indent, out) == indent
        assert "\\<" not in out.getvalue()
        return out.getvalue().splitlines()

    def expected(*unicode_lines: str, indent=0) -> list[str]:
        return ["  " * indent + line if line else "" for line in unicode_lines]
    assert emitted(basics) == expected(*heading_text)
    assert emitted(basics, 1) == expected(*heading_text, indent=1)          # the children at the heading's indent
    assert emitted(overview) == expected(*passage_text)
    assert emitted(intro) == expected("text ‹We start with the two lemmas every later proof uses.›")
    (alone,) = insert(f, x, 2, [heading("Alone", "No ‹child› \\<open>here\\<close> ›", "paragraph")])
    assert emitted(alone) == expected("paragraph ‹No ‹child› ‹here› {\\isasymclose}›")   # no empty line without children; paired marks kept
    (quoted,) = insert(f, x, 3, [passage("quoted", "A ‹quoted› word.\n\nAnd \\<close> more.")])
    assert emitted(quoted) == expected("text ‹A ‹quoted› word.", "", "And {\\isasymclose} more.›")   # a stray mark a symbol
    (trailing,) = insert(f, x, 4, [passage("trailing", "Ends with a line break.\n\n")])
    assert emitted(trailing) == expected("text ‹Ends with a line break.", "", "›")   # the breaks kept (§5), unlike in print (§8)
    (listed,) = insert(f, x, 5, [passage("listed", "Two items:\n▪ one\n▪ two")])
    assert emitted(listed, 1) == expected("text ‹", "Two items:", "▪ one", "▪ two›", indent=1)   # a list: one line each item
    (itemed,) = insert(f, x, 6, [heading("Itemed", "▪ a", "paragraph")])
    assert emitted(itemed) == expected("paragraph ‹ a›")                     # no list in a heading
    (commented,) = insert(f, x, 7, [heading("Commented", "Comments", "subsection", children=[
        lemma("c", "True ― ‹x₁›", "A comment", for_any=(), premises=())])])
    assert '  shows "True ― ‹‹x₁››"' in emitted(commented)                                  # a term's comment translated
    assert "can_emit" not in vars(Section) and "can_emit" not in vars(Text)     # the framework's default (§5)


# --- the id properties (§9) ----------------------------------------------------

def test_section_9_s_id_properties():
    assert (Section.output_omissible, Section.input_omissible, Section.drop_priority) == (True, True, 0)
    assert (Text.output_omissible, Text.input_omissible, Text.drop_priority) == (False, False, 0)
    f, x = forest(BASICS)
    (basics,) = x.sub_nodes
    intro, rev_rev, lengths = basics.sub_nodes
    (rev_length,) = lengths.sub_nodes
    assert f.id_of(basics) == "section_Basics" and f.id_of(rev_length) == "lemma_rev_length"
    for form in ("lemma_rev_length", "subsection_Lengths.lemma_rev_length", "section_Basics.lemma_rev_length",
                 "theory_X.lemma_rev_length", "session_Arith.theory_X.section_Basics.subsection_Lengths.lemma_rev_length"):
        assert f.resolve(form) is rev_length
    assert f.resolve("text_intro") is intro and f.resolve("section_Basics.text_intro") is intro
    # the same lemma directly under the theory: the heading's component tells the inner one apart
    (outer,) = insert(f, x, 1, [REV_REV])
    assert f.id_of(rev_rev) == "section_Basics.lemma_rev_rev"
    assert f.id_of(outer) == "session_Arith.theory_X.lemma_rev_rev" and f.resolve(f.id_of(outer)) is outer
    run(locked(f, edit.delete(outer)))
    # before `Theory`'s: the same lemma directly in another theory — the heading's component dropped, the theory's kept
    (s,) = f.sub_nodes
    (y,) = insert(f, s, 1, [theory("Y") | {"children": [REV_REV]}])
    assert f.id_of(rev_rev) == "theory_X.lemma_rev_rev"
    assert f.id_of(y.sub_nodes[0]) == "theory_Y.lemma_rev_rev"
    inv(f)


# --- the evaluation, in the plugin's run of the harness (§5, §6, §8) ------------

@pytest.mark.isabelle(deadline=600)
async def test_headings_and_passages_pass_the_state_through(std_conversation):
    """§6 through the real wire: §2's heading and passage evaluated, every
    operation `Ready` and the lemmas admitted; a `section` under a
    `subsection` refused with §6's refusal, in a theory of its own, the
    copy made; `recall` as §8's first rendering shows but for the proofs;
    the file rendered as §5 shows, `sorry` for the unproven lemmas."""
    forest = std_conversation.forest
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [ts.session("TAT_Suite",
                ts.theory("TAT_Std_ST") | {"children": [BASICS, OVERVIEW]},
                ts.theory("TAT_Std_SL") | {"children": [
                    heading("Outer", "Outer", "subsection", children=[
                        heading("Inner", "Inner", children=[passage("blocked", "Never run.")])])]})]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 1, text
        (s,) = forest.sub_nodes
        (basics, overview), (outer,) = (t.sub_nodes for t in s.sub_nodes)
        (inner,) = outer.sub_nodes
        intro, rev_rev, lengths = basics.sub_nodes
        for node in (basics, lengths):
            assert node.evaluation_status_beginning == M.READY_CLEAN and node.evaluation_status_ending == M.READY_CLEAN
        assert intro._status == M.READY_CLEAN and overview._status == M.READY_CLEAN
        assert await basics.operation_slots("beginning")[1].is_initialized() and await intro.resulting_state().is_initialized()
        assert isinstance(rev_rev._status, M.Ready) and isinstance(lengths.sub_nodes[0]._status, M.Ready)   # admitted (THEOREM §6)
        assert isinstance(inner.evaluation_status_beginning, M.CannotEvaluate)
        assert [m.unicode for m in inner.evaluation_status_beginning.messages] == [
            composed_refusal("section", forest.full_id(outer), USE_A_LOWER_LEVEL)]
        assert not await inner.operation_slots("beginning")[1].is_initialized()
        assert await inner.resulting_state().is_initialized() and inner.sub_nodes[0]._status is M.NOT_EVALUATED
        [recall_heading, *_] = fenced_blocks(DOC, "8.")
        recalled = await session.call_tool("recall", {"node_id": "section_Basics"})
        lines = text_of(recalled).splitlines()
        assert lines[0] == recall_heading[0] and lines[1:3] == recall_heading[1:3], lines
        assert lines[3].startswith("  - lemma_rev_rev (valid statement, ") and lines[4:6] == recall_heading[4:6]
        assert lines[6] == recall_heading[6] and lines[7].startswith("    - lemma_rev_length (valid statement, ")
    rendered = C.render(forest)
    file = rendered.files[C.Path("TAT_Suite/TAT_Std_ST.thy")]
    [heading_text, passage_text] = fenced_blocks(DOC, "5.")
    assert "\n".join(heading_text).replace("by aoa", "sorry") in file.replace("\\<open>", "‹").replace("\\<close>", "›")
    assert "\n".join(passage_text) in file.replace("\\<open>", "‹").replace("\\<close>", "›")
    assert C.Path("TAT_Suite/TAT_Std_SL.thy") not in rendered.files
