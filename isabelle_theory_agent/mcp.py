"""The tools of MCP_SPECIFICATION §1 (MODULE_STRUCTURE §4.6): `tools`
builds what the server advertises and runs for one conversation, and
`on_compaction` what `/on-compaction` does for it.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import jsoncomment

from . import edit
from .exceptions import (
    HoldsNoChildren, MoveBesideItself, ProtectedNode, TAT_Error, TAT_InternalError)
from .mcp_server import Body, Tool
from .model import BRIEFING, Forest, JSON_Schema, Node, NonLeaf_Node, RECALL, Relative_Focus
from .plugin import Loaded, check_call, validate_call_schema

_TOOLS = Path(__file__).parent / "tools"


def _schema(tool: str) -> JSON_Schema:
    return jsoncomment.JsonComment().loads((_TOOLS / f"{tool}.jsonc").read_text())


# `edit`'s adding actions as the Location they name (TOOL_SCHEMAS.md §1, §2)
_ACTION_POSITION = {"append": "into", "insert_before": "before", "insert_after": "after"}


def tools(forest: Forest, loaded: Loaded) -> list[Tool]:
    """`edit`, `move` and `delete` (TOOL_SCHEMAS.md): each holds the
    forest's lock across the change, the evaluation the call asks for and
    the quickview, names the refused operation on a `TAT_Error` the change
    raises (EXCEPTIONS.md §4), and answers the `Done` line over the
    quickview (PRINT.md §5).  And `recall` (RECALL.md), which renders the
    node in `Recall` under no lock.  Every call is checked against its
    tool's schema before the entry runs (`_tool`)."""

    async def run_edit(arguments: dict[str, Any]) -> str:
        action, target_id = arguments["action"], arguments["target_id"]
        constructs = arguments["constructs"]
        async with forest.lock:
            with _operation(action, target_id) as what:
                if action == "amend":
                    nodes = await edit.amend(_resolve(forest, target_id), constructs, loaded.kinds)
                elif action in _ACTION_POSITION:
                    parent, index = _location(forest, _ACTION_POSITION[action], target_id)
                    nodes = await edit.insert(parent, index, constructs, loaded.kinds)
                else:
                    raise TAT_InternalError(f"unknown action {action!r}")
            stopped = await _evaluate(forest, nodes[-1]) if arguments["evaluate"] else None
            return _done(forest, what, stopped, nodes, -1)

    async def run_move(arguments: dict[str, Any]) -> str:
        source_id, location = arguments["source_id"], arguments["location"]
        position, node_id = location["position"], location["node_id"]
        where = f"{source_id} {position} {node_id}"   # the target phrase (TOOL_SCHEMAS.md §4)
        async with forest.lock:
            with _operation("move", where) as what:
                node = _resolve(forest, source_id)
                parent, index = _location(forest, position, node_id, moving=node)
                await edit.move(node, parent, index)
            stopped = await _evaluate(forest, node) if arguments["evaluate"] else None
            return _done(forest, what, stopped, [node], -1)

    async def run_delete(arguments: dict[str, Any]) -> str:
        node_id = arguments["node_id"]
        async with forest.lock:
            with _operation("delete", node_id) as what:
                parent = await edit.delete(_resolve(forest, node_id))
            return _done(forest, what, None, [parent], 0)

    async def run_recall(arguments: dict[str, Any]) -> str:
        # `Forest.resolve`, not `_resolve`: a read may name the root
        node = forest.resolve(arguments["node_id"]) if "node_id" in arguments else forest
        return forest.render(node, RECALL)

    return [_tool("edit", "Edit Isabelle theory constructs", loaded.edit_schema, run_edit,
                  read_only=False),
            _tool("move", "Move an Isabelle theory construct", _schema("move"), run_move,
                  read_only=False),
            _tool("delete", "Delete an Isabelle theory construct", _schema("delete"), run_delete,
                  read_only=False),
            _tool("recall", "Read an Isabelle theory construct with what is under it, briefer the"
                  " deeper; read a construct itself to see it in full.", _schema("recall"),
                  run_recall, read_only=True)]


def _tool(name: str, description: str, schema: JSON_Schema, run: Body, read_only: bool) -> Tool:
    """One object per tool is what the agent is told and what a call is
    held to: the schema validated as the tool is built
    (`plugin.validate_call_schema`), and every call checked against it
    before `run` sees it (`plugin.check_call`); the constructs inside
    `edit`'s are `edit.py`'s to check, element by element."""
    validate_call_schema(schema, name)

    async def checked(arguments: dict[str, Any]) -> str:
        check_call(schema, name, arguments)
        return await run(arguments)
    return Tool(name, description, schema, checked, read_only)


@contextmanager
def _operation(opr: str, target: str) -> Generator[str]:
    """The operation's phrase, which the `Done` line and the `Cannot` line
    both carry: yielded to the entry, and written onto a `TAT_Error` the
    change raises (EXCEPTIONS.md §4)."""
    try:
        yield f"{opr} {target}"
    except TAT_Error as e:
        e._set_operation(opr, target)
        raise


def _resolve(forest: Forest, id: str, *, root_ok: bool = False) -> Node:
    """The node an id names — one the call edits: `Sessions` only where the
    call may take the root, `ProtectedNode` elsewhere (TOOL_SCHEMAS.md §1,
    §2).  `_location` is the one caller that says `root_ok`; a tool that
    reads, and so may name the root, must not resolve through here."""
    node = forest.resolve(id)
    if node is forest and not root_ok:
        raise ProtectedNode(id)
    return node


def _location(forest: Forest, position: str, anchor_id: str,
              moving: Node | None = None) -> tuple[NonLeaf_Node, int]:
    """A Location (ARCHITECTURE §1) resolved: the anchor the call names,
    and the parent and the index a batch is inserted at, or the node
    `moving` lands at — that one counted after the node's removal
    (TOOL_SCHEMAS.md §2).  `Sessions` is an anchor only for `into`, the
    one position that needs no parent (TOOL_SCHEMAS.md §1, §2)."""
    anchor = _resolve(forest, anchor_id, root_ok=position == "into")
    if position == "into":
        if not isinstance(anchor, NonLeaf_Node):
            raise HoldsNoChildren(anchor_id, anchor.kind)
        return anchor, len(anchor.sub_nodes) - (1 if moving is not None and moving.parent is anchor else 0)
    if position not in ("before", "after"):
        raise TAT_InternalError(f"unknown position {position!r}")
    if anchor is moving:
        raise MoveBesideItself(forest.id_of(anchor))
    parent = edit.parent_of(anchor)
    index = anchor.index_of()
    if moving is not None and moving.parent is parent and moving.index_of() < index:
        index -= 1
    return parent, index + (1 if position == "after" else 0)


async def _evaluate(forest: Forest, destination: Node) -> Node | None:
    """`evaluate` true (MCP_SPECIFICATION §3.2): run up to the change's
    natural destination under the lock the call holds, `ignore_error`
    unset; the node the walk stopped at, if it stopped."""
    return (await forest._run(destination, False)).stopped_at


def _done(forest: Forest, what: str, stopped: Node | None, nodes: list[Node], depth: int) -> str:
    """A successful call's result (TOOL_SCHEMAS.md §4): the `Done` line,
    naming the stop when evaluation did not reach its destination, over
    the quickview (PRINT.md §5)."""
    assert forest.lock.locked(), "a call's answer is rendered under the forest lock"
    line = f"Done: {what}"
    if stopped is not None:
        line += f"; evaluation stopped at {forest.id_of(stopped)}"
    return f"{line}.\n" + forest.render(forest, Relative_Focus(frozenset(nodes), depth))


def on_compaction(forest: Forest) -> Callable[[], str]:
    """The agent's context was replaced (PRINT.md §4, §5): forget what it
    was shown, and give its client the briefing."""
    def briefing() -> str:
        forest.conversation.seen.clear()
        return forest.render(forest, BRIEFING)
    return briefing
