"""The three forest-changing tools of `mcp.py` (TOOL_SCHEMAS.md,
MODULE_STRUCTURE §4.6) and `recall` (RECALL.md) on `test_model`'s fake
classes: the advertised schemas against the documents, where each action
and position puts or takes a node, the `evaluate` flag, the `Done` line
and the quickview that follow, what `recall` renders, and every refusal
— its class and fields, and the opening line the entry adds
(RENDER_BASELINES §1); a malformed call's lines are read from
TOOL_SCHEMAS §4 and RECALL.md §3.  The call check itself, on a schema of
every shape it reads, is `test_plugin`'s.  Nothing here crosses the wire.
Run: python -m pytest test/test_mcp.py
"""

import asyncio
import typing

import jsoncomment
import pytest

import test_model as tm
from baselines import DOCS, fenced_blocks, fenced_lines, stated
from test_model import T, add, slot

from isabelle_theory_agent import mcp, plugin
from isabelle_theory_agent.jobs import Agent
from isabelle_theory_agent.exceptions import (
    AmbiguousId, HoldsNoChildren, InvalidField, MissingField, MoveBesideItself,
    MoveIntoOwnSubtree, NodeNotFound, ProtectedNode, RawASTError, TAT_Error, TAT_InternalError,
    UnexpectedField)
from isabelle_theory_agent.model import NOT_EVALUATED
from test_model import CANNOT_EVALUATE, READY


class Block(tm.Block):                  # omissible like a `Theory`, so the tests' ids stay short
    output_omissible = input_omissible = True


KINDS = {"t": T, "block": Block}
EDIT_SCHEMA = mcp._schema("edit")       # the envelope, its `$defs` empty: the check reads no construct
TOOL_SCHEMAS = DOCS / "TOOL_SCHEMAS.md"
RECALL = DOCS / "RECALL.md"


@pytest.fixture(autouse=True)
def table(monkeypatch):
    tm.TABLE.clear()
    tm.TABLE.install(monkeypatch)


def build():
    """Theory > [Section > [a, b], c]; the tools over it, by name."""
    f = tm.OneTreeForest(tm.CONN)
    thy = add(f, Block(f, slot(), "Theory", slot()))
    sec = add(thy, Block(thy, slot(), "Section", slot()))
    a = add(sec, T(sec, slot(), "a")); b = add(sec, T(sec, slot(), "b"))
    c = add(thy, T(thy, slot(), "c"))
    tools = {t.name: t for t in mcp.tools(f, plugin.Loaded(KINDS, EDIT_SCHEMA))}
    return f, thy, sec, a, b, c, tools


def agent() -> Agent:
    """The caller, fresh for every call: no case here reads a seen set."""
    return Agent("main", True)


def call(tool, **arguments) -> list[str]:
    return asyncio.run(tool.run(agent(), arguments)).splitlines()


_E = typing.TypeVar("_E", bound=TAT_Error)


def refused(tool, cls: type[_E], **arguments) -> tuple[_E, list[str]]:
    """A refusal: the exception, to assert by its class and fields, and
    the lines it renders — the first the entry's own (RENDER_BASELINES §1)."""
    with pytest.raises(cls) as e:
        asyncio.run(tool.run(agent(), arguments))
    return e.value, str(e.value).splitlines()


def t(name, **fields):
    return {"kind": "t", "name": name, **fields}


def block(name, *children):
    return {"kind": "block", "name": name, **({"children": list(children)} if children else {})}


def names(parent):
    return [n.name for n in parent.sub_nodes]


# --- what the server is given ------------------------------------------------

def test_the_four_tools_their_descriptions_and_schemas_as_the_documents_state_them():
    f, *_, tools = build()
    assert list(tools) == ["edit", "move", "delete", "recall"]
    assert [t.description for t in tools.values()] == \
        stated(TOOL_SCHEMAS, "Tool description") + stated(RECALL, "Tool description")
    assert [t.read_only for t in tools.values()] == [False, False, False, True]
    parse = jsoncomment.JsonComment().loads
    [edit], [move], [delete] = (fenced_blocks(TOOL_SCHEMAS, s) for s in ("1.", "2.", "3."))
    recall, _ = fenced_blocks(RECALL, "3.")
    assert EDIT_SCHEMA == parse("\n".join(edit))            # the envelope `Loaded.edit_schema` fills
    assert tools["move"].input_schema == parse("\n".join(move))
    assert tools["delete"].input_schema == parse("\n".join(delete))
    assert tools["recall"].input_schema == parse("\n".join(recall))
    assert tools["edit"].input_schema is EDIT_SCHEMA       # `Loaded.edit_schema`, as given
    # `tools` validates what it advertises (`plugin.validate_call_schema`), naming the tool.
    broken = {**EDIT_SCHEMA, "properties": {**EDIT_SCHEMA["properties"], "extra": {"type": "null"}}}
    with pytest.raises(TAT_InternalError, match=r"edit\.extra: not of one JSON type"):
        mcp.tools(f, plugin.Loaded(KINDS, broken))


def test_the_success_lines_of_render_baselines_section_6():
    kinds = {"theory": Block, "section": Block, "lemma": T, "definition": T}
    [lines] = fenced_blocks(DOCS / "RENDER_BASELINES.md", "6.")
    f = tm.OneTreeForest(tm.CONN, kinds=kinds)
    x = add(f, Block(f, slot(), "X", slot()), "theory")
    add(x, Block(x, slot(), "Basics", slot()), "section")
    add(x, T(x, slot(), "P"), "lemma")
    add(f, Block(f, slot(), "Sorting", slot()), "theory")
    tools = {t.name: t for t in mcp.tools(f, plugin.Loaded(kinds, EDIT_SCHEMA))}
    assert lines == [
        call(tools["edit"], action="append", target_id="theory_X",
             constructs=[{"kind": "lemma", "name": "Q"}], evaluate=False)[0],
        call(tools["edit"], action="insert_after", target_id="theory_X.lemma_P",
             constructs=[{"kind": "definition", "name": "f", "fail": True}], evaluate=True)[0],
        call(tools["move"], source_id="theory_Sorting",
             location={"position": "after", "node_id": "theory_X.section_Basics"}, evaluate=False)[0],
        call(tools["delete"], node_id="theory_X.section_Basics")[0],
    ]


# --- edit ---------------------------------------------------------------------

def test_append_links_at_the_end_and_shows_the_new_nodes_whole():
    f, thy, sec, a, b, c, tools = build()
    out = call(tools["edit"], action="append", target_id="block_Theory",
               constructs=[block("S2", t("x")), t("y")], evaluate=False)
    assert names(thy) == ["Section", "c", "S2", "y"]
    assert out == [
        "Done: append block_Theory.",
        "block_Theory (not evaluated)",             # on the path: the lone tree, dashless
        "- block_Section (not evaluated)",          # beside the focus: lines
        "- t_c (not evaluated)",
        "- block_S2 (not evaluated)",               # the batch, whole
        "  - t_x (not evaluated)",
        "- t_y (not evaluated)",
    ]


def test_the_roots_first_layer_takes_an_append_and_is_ordered_like_any_other():
    """TOOL_SCHEMAS §1: `append` on `Sessions` — the call the empty
    forest's hint instructs — and an insertion beside a first-layer node;
    then the root's other permission, a `move … into` it (TOOL_SCHEMAS §2,
    EXCEPTIONS §3's `ProtectedNode` row), whose index is counted after the
    node's removal."""
    f, thy, *_, tools = build()
    out = call(tools["edit"], action="append", target_id="Sessions", constructs=[block("Two")],
               evaluate=False)
    assert names(f) == ["Theory", "Two"]
    assert out == ["Done: append Sessions.", "Sessions:",
                   "- block_Theory (not evaluated)", "- block_Two (not evaluated)"]
    call(tools["edit"], action="insert_before", target_id="block_Theory", constructs=[block("One")],
         evaluate=False)
    assert names(f) == ["One", "Theory", "Two"]
    out = call(tools["move"], source_id="block_Theory",
               location={"position": "into", "node_id": "Sessions"}, evaluate=False)
    assert names(f) == ["One", "Two", "Theory"]           # `into` the root: to the end of the first layer
    assert out[0] == "Done: move block_Theory into Sessions."


def test_insert_before_and_after_place_beside_the_target():
    f, thy, sec, a, b, c, tools = build()
    call(tools["edit"], action="insert_before", target_id="t_b", constructs=[t("p")], evaluate=False)
    call(tools["edit"], action="insert_after", target_id="t_b", constructs=[t("q"), t("r")],
         evaluate=False)
    assert names(sec) == ["a", "p", "b", "q", "r"]
    out = call(tools["edit"], action="insert_after", target_id="block_Section", constructs=[t("s")],
               evaluate=False)
    assert names(thy) == ["Section", "s", "c"]
    assert out[:3] == ["Done: insert_after block_Section.", "block_Theory (not evaluated)",
                       "- block_Section (not evaluated)"]
    assert out[3:] == ["- t_s (not evaluated)", "- t_c (not evaluated)"]


def test_amend_focuses_the_replacement_and_what_follows_it():
    f, thy, sec, a, b, c, tools = build()
    out = call(tools["edit"], action="amend", target_id="block_Section",
               constructs=[block("Renamed"), t("z")], evaluate=False)
    assert names(thy) == ["Renamed", "z", "c"] and names(thy.sub_nodes[0]) == ["a", "b"]
    assert out == [
        "Done: amend block_Section.",
        "block_Theory (not evaluated)",
        "- block_Renamed (not evaluated)",          # inherited children, printed whole
        "  - t_a (not evaluated)",
        "  - t_b (not evaluated)",
        "- t_z (not evaluated)",
        "- t_c (not evaluated)",
    ]


def test_the_quickview_prints_what_a_call_added_whole_and_no_deeper_than_its_depth():
    """PRINT.md §5's table: every node of an `edit`'s batch and all under
    it (-1); the moved node's subtree (-1); a deleted node's parent with
    its children as lines (0)."""
    f, thy, sec, a, b, c, tools = build()
    out = call(tools["edit"], action="append", target_id="block_Theory",
               constructs=[block("S2", block("S3", t("x")), t("z")), block("S4", t("y"))],
               evaluate=False)
    assert out[4:] == ["- block_S2 (not evaluated)", "  - block_S3 (not evaluated)",
                       "    - t_x (not evaluated)", "  - t_z (not evaluated)",
                       "- block_S4 (not evaluated)", "  - t_y (not evaluated)"]
    out = call(tools["move"], source_id="block_S2",
               location={"position": "before", "node_id": "block_Section"}, evaluate=False)
    assert names(thy) == ["S2", "Section", "c", "S4"]
    assert out == ["Done: move block_S2 before block_Section.", "block_Theory (not evaluated)",
                   "- block_S2 (not evaluated)", "  - block_S3 (not evaluated)",
                   "    - t_x (not evaluated)", "  - t_z (not evaluated)",
                   "- block_Section (not evaluated)", "- t_c (not evaluated)",
                   "- block_S4 (not evaluated)"]
    out = call(tools["delete"], node_id="t_z")
    assert out == ["Done: delete t_z.", "block_Theory (not evaluated)",
                   "- block_S2 (not evaluated)", "  - block_S3 (not evaluated)",   # no t_x: depth 0
                   "- block_Section (not evaluated)", "- t_c (not evaluated)",
                   "- block_S4 (not evaluated)"]


def test_evaluate_runs_to_the_last_new_node_and_names_a_stop():
    f, thy, sec, a, b, c, tools = build()
    out = call(tools["edit"], action="append", target_id="block_Section", constructs=[t("x")],
               evaluate=True)
    x = sec.sub_nodes[-1]
    assert [tm.st(n) for n in (a, b, x, c)] == [READY, READY, READY, tm.NOT_EVALUATED]
    assert out[0] == "Done: append block_Section." and "  - t_x (success)" in out
    out = call(tools["edit"], action="insert_after", target_id="t_x",
               constructs=[t("bad", fail=True), t("after")], evaluate=True)
    bad, after = sec.sub_nodes[-2:]
    assert tm.st(bad) is CANNOT_EVALUATE and tm.st(after) is NOT_EVALUATED
    assert out[0] == "Done: insert_after t_x; evaluation stopped at t_bad."
    assert out[-3:] == ["  - t_bad (failed)", "  - t_after (not evaluated)", "- t_c (not evaluated)"]


def test_edit_refusals_open_with_the_operation_and_leave_the_forest_alone():
    f, thy, sec, a, b, c, tools = build()
    edit = tools["edit"]
    e, lines = refused(edit, HoldsNoChildren, action="append", target_id="t_c", constructs=[t("x")],
                       evaluate=False)
    assert lines[0] == "Cannot append t_c" and (e.id, e.kind) == ("t_c", "t")
    for action in ("insert_before", "insert_after", "amend"):
        e, lines = refused(edit, ProtectedNode, action=action, target_id="Sessions",
                           constructs=[t("x")], evaluate=False)
        assert lines[0] == f"Cannot {action} Sessions" and e.id == "Sessions"
    e, lines = refused(edit, NodeNotFound, action="append", target_id="t_zzz", constructs=[t("x")],
                       evaluate=False)
    assert lines[0] == "Cannot append t_zzz" and e.id == "t_zzz"
    e, lines = refused(edit, MissingField, action="append", target_id="block_Theory",
                       constructs=[t("a"), {"kind": "t"}], evaluate=False)
    assert lines[0] == "Cannot append block_Theory"
    assert (e.holder, e.field, e.of_tool, e.raw_ast_path) == ("t", "name", False, "constructs[1]")
    assert names(thy) == ["Section", "c"] and names(sec) == ["a", "b"]


def test_a_malformed_call_is_refused_on_its_own_shape_with_no_opening_line():
    """TOOL_SCHEMAS §4's block, both ways: every line of it comes from a
    call in the loop below, and every call in the loop renders a line of
    it; the cases after it fall outside the block and are asserted by
    class and fields."""
    f, thy, sec, *_, tools = build()
    edit, move, delete = tools["edit"], tools["move"], tools["delete"]
    malformed, = fenced_blocks(TOOL_SCHEMAS, "4.")
    rendered = set()
    for tool, arguments in [
        (edit, dict(action="append", target_id="t_c", constructs=[t("x")])),
        (edit, dict(action="append", target_id="t_c", constructs=[t("x")], evaluate=False, kind="t")),
        (edit, dict(action="append", target_id="t_c", constructs=t("x"), evaluate=False)),
        (edit, dict(action="append", target_id="block_Theory", constructs=[], evaluate=False)),
        (edit, dict(action="amend", target_id="block_Section", constructs=[], evaluate=True)),
        (edit, dict(action="prepend", target_id="t_c", constructs=[t("x")], evaluate=False)),
        (move, dict(source_id="t_a", location={"position": "under", "node_id": "t_c"}, evaluate=False)),
    ]:
        e, lines = refused(tool, RawASTError, **arguments)
        assert isinstance(e, (MissingField, UnexpectedField, InvalidField)) and e.of_tool
        assert len(lines) == 1 and lines[0] in malformed, arguments
        rendered.add(lines[0])
    assert rendered == set(malformed)
    # Beyond the block, asserted by class and fields: a nested argument's
    # shape errors, and a missing top-level one on another tool.
    for tool, arguments, field in [
        (edit, dict(action="append", target_id="t_c", constructs=[t("x")], evaluate="yes"), "evaluate"),
        (move, dict(source_id="t_a", location=5, evaluate=False), "location"),
        (move, dict(source_id="t_a", location={"position": 5, "node_id": "t_c"}, evaluate=False),
         "location.position"),
    ]:
        e, lines = refused(tool, InvalidField, **arguments)
        assert (e.field, e.of_tool, len(lines)) == (field, True, 1)
    e, lines = refused(move, UnexpectedField, source_id="t_a",
                       location={"position": "before", "node_id": "t_c", "x": 1}, evaluate=False)
    assert (e.holder, e.field, e.holder_is_top, e.of_tool) == ("location", "x", False, True)
    e, lines = refused(move, MissingField, source_id="t_a", location={"position": "before"},
                       evaluate=False)
    assert (e.holder, e.field, e.of_tool) == ("move", "location.node_id", True)
    e, lines = refused(delete, MissingField)
    assert (e.holder, e.field, e.of_tool) == ("delete", "node_id", True)
    assert names(thy) == ["Section", "c"] and names(sec) == ["a", "b"]


# --- move ---------------------------------------------------------------------

def test_move_before_after_and_into_count_the_index_after_the_removal():
    f, thy, sec, a, b, c, tools = build()
    move = tools["move"]
    out = call(move, source_id="t_a", location={"position": "after", "node_id": "t_b"}, evaluate=False)
    assert names(sec) == ["b", "a"]
    assert out == ["Done: move t_a after t_b.", "block_Theory (not evaluated)",
                   "- block_Section (not evaluated)", "  - t_b (not evaluated)",
                   "  - t_a (not evaluated)", "- t_c (not evaluated)"]
    call(move, source_id="t_a", location={"position": "before", "node_id": "t_b"}, evaluate=False)
    assert names(sec) == ["a", "b"]
    call(move, source_id="t_c", location={"position": "into", "node_id": "block_Section"}, evaluate=False)
    assert names(sec) == ["a", "b", "c"] and names(thy) == ["Section"]
    call(move, source_id="t_a", location={"position": "into", "node_id": "block_Section"}, evaluate=False)
    assert names(sec) == ["b", "c", "a"]                  # into its own parent: to the end


def test_move_evaluates_the_moved_subtree_when_asked():
    f, thy, sec, a, b, c, tools = build()
    out = call(tools["move"], source_id="block_Section", location={"position": "after", "node_id": "t_c"},
               evaluate=True)
    assert names(thy) == ["c", "Section"]
    assert (c._status, a._status, b._status) == (READY, READY, READY)
    assert out == ["Done: move block_Section after t_c.", "block_Theory (not evaluated)",
                   "- t_c (success)", "- block_Section (success)", "  - t_a (success)", "  - t_b (success)"]


def test_move_refusals():
    f, thy, sec, a, b, c, tools = build()
    move = tools["move"]
    e, lines = refused(move, HoldsNoChildren, source_id="t_a",
                       location={"position": "into", "node_id": "t_c"}, evaluate=False)
    assert lines[0] == "Cannot move t_a into t_c" and (e.id, e.kind) == ("t_c", "t")
    e, lines = refused(move, MoveIntoOwnSubtree, source_id="block_Section",
                       location={"position": "after", "node_id": "t_a"}, evaluate=False)
    assert lines[0] == "Cannot move block_Section after t_a"
    assert (e.id, e.destination) == ("block_Section", "block_Section")
    e, lines = refused(move, MoveBesideItself, source_id="t_a",
                       location={"position": "after", "node_id": "t_a"}, evaluate=False)
    assert lines[0] == "Cannot move t_a after t_a" and e.id == "t_a"
    e, lines = refused(move, ProtectedNode, source_id="Sessions",
                       location={"position": "into", "node_id": "block_Section"}, evaluate=False)
    assert lines[0] == "Cannot move Sessions into block_Section" and e.id == "Sessions"
    e, lines = refused(move, ProtectedNode, source_id="t_a",
                       location={"position": "before", "node_id": "Sessions"}, evaluate=False)
    assert lines[0] == "Cannot move t_a before Sessions" and e.id == "Sessions"
    assert names(sec) == ["a", "b"] and names(thy) == ["Section", "c"]


# --- delete -------------------------------------------------------------------

def test_delete_shows_the_old_parent_with_what_is_left():
    f, thy, sec, a, b, c, tools = build()
    out = call(tools["delete"], node_id="t_a")
    assert names(sec) == ["b"]
    assert out == ["Done: delete t_a.", "block_Theory (not evaluated)",
                   "- block_Section (not evaluated)", "  - t_b (not evaluated)", "- t_c (not evaluated)"]
    out = call(tools["delete"], node_id="block_Section")
    assert names(thy) == ["c"]
    assert out == ["Done: delete block_Section.", "block_Theory (not evaluated)", "- t_c (not evaluated)"]
    e, lines = refused(tools["delete"], ProtectedNode, node_id="Sessions")
    assert lines[0] == "Cannot delete Sessions" and e.id == "Sessions"
    e, lines = refused(tools["delete"], NodeNotFound, node_id="t_a")
    assert lines[0] == "Cannot delete t_a" and e.id == "t_a"


# --- recall -------------------------------------------------------------------

def test_recall_renders_the_node_in_recall_and_the_briefing_without_an_id():
    """RECALL.md §2, §3: with an id the lines are the framework's at
    `Recall`'s depths — `t_x`, four levels down, is what tells `Recall`
    from the briefing, which goes to the bottom; `Sessions` as the id
    renders the root in `Recall`; a read takes no lock (MCP_SPECIFICATION
    §5)."""
    f, thy, sec, *_, tools = build()
    inner = add(sec, Block(sec, slot(), "Inner", slot()))
    add(inner, T(inner, slot(), "x"))
    sessions = ["block_Theory (not evaluated)", "- block_Section (not evaluated)",
                "  - t_a (not evaluated)", "  - t_b (not evaluated)",
                "  - block_Inner (not evaluated)", "- t_c (not evaluated)"]
    briefing = [*sessions[:5], "    - t_x (not evaluated)", sessions[5]]
    assert call(tools["recall"]) == briefing
    assert call(tools["recall"], node_id="Sessions") == sessions
    assert call(tools["recall"], node_id="block_Section") == [
        "- block_Section (not evaluated)", "  - t_a (not evaluated)", "  - t_b (not evaluated)",
        "  - block_Inner (not evaluated)", "    - t_x (not evaluated)"]

    async def under_the_lock():
        async with f.lock:
            return await asyncio.wait_for(tools["recall"].run(agent(), {}), timeout=1)
    assert asyncio.run(under_the_lock()).splitlines() == briefing


def test_recall_refusals_render_the_cause_alone():
    """RECALL.md §3's block: its first two lines are RENDER_BASELINES §2's,
    which test_exceptions ties to the classes; the third is `recall`'s
    own.  Every refusal by class and fields, one line, no opening line,
    the forest untouched."""
    f, thy, sec, *_, tools = build()
    other = add(thy, Block(thy, slot(), "Other", slot()))
    add(other, T(other, slot(), "a"))                       # a second `a`: `t_a` is ambiguous
    recall = tools["recall"]
    _, [not_found, ambiguous, unexpected] = fenced_blocks(RECALL, "3.")
    assert {not_found, ambiguous} <= set(fenced_lines(DOCS / "RENDER_BASELINES.md", "2."))
    e, lines = refused(recall, NodeNotFound, node_id="t_z")
    assert (e.id, e.opr, len(lines)) == ("t_z", None, 1)
    e, lines = refused(recall, AmbiguousId, node_id="t_a")
    assert (e.id, e.candidates, len(lines)) == ("t_a", ["block_Section.t_a", "block_Other.t_a"], 1)
    e, lines = refused(recall, InvalidField, node_id=3)
    assert (e.field, e.of_tool, len(lines)) == ("node_id", True, 1)
    e, lines = refused(recall, UnexpectedField, id="t_c")
    assert (e.holder, e.field, e.of_tool) == ("recall", "id", True) and lines == [unexpected]
    assert names(thy) == ["Section", "c", "Other"] and names(sec) == ["a", "b"]
