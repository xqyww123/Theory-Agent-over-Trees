"""The tools of MCP_SPECIFICATION §1 (MODULE_STRUCTURE §4.6): `tools`
builds what the server advertises and runs for one conversation.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import jsoncomment

from . import edit
from .exceptions import (
    ConstructNotSupported, ConstructOwnedByAnother, HoldsNoChildren, MoveBesideItself, NoQuestionPending,
    ProtectedNode, TAT_Error, TAT_InternalError)
from .jobs import NO_JOB, RUNNING, Agent, Construction_Job, Standing, standing, state_lines
from .mcp_server import Body, Tool, With_Trailer
from .model import BRIEFING, Forest, JSON_Schema, Node, NonLeaf_Node, RECALL, Relative_Focus
from .plugin import Loaded, check_call, validate_call_schema

# `check_construct`'s clamps on `wait_seconds` (CONSTRUCT_INTERACTION §5, §8): at
# least 3 seconds, and a minute under the clients' twelve-hour tool limit
WAIT_AT_LEAST = 3
WAIT_AT_MOST = 12 * 3600 - 60

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
    node in `Recall`, or the briefing when no node is named, under no lock.
    Every rendering is for the calling agent; every call is checked
    against its tool's schema before the entry runs (`_tool`)."""

    async def run_edit(agent: Agent, arguments: dict[str, Any]) -> str:
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
            return _done(forest, agent, what, stopped, nodes, -1)

    async def run_move(agent: Agent, arguments: dict[str, Any]) -> str:
        source_id, location = arguments["source_id"], arguments["location"]
        position, node_id = location["position"], location["node_id"]
        where = f"{source_id} {position} {node_id}"   # the target phrase (TOOL_SCHEMAS.md §4)
        async with forest.lock:
            with _operation("move", where) as what:
                node = _resolve(forest, source_id)
                parent, index = _location(forest, position, node_id, moving=node)
                await edit.move(node, parent, index)
            stopped = await _evaluate(forest, node) if arguments["evaluate"] else None
            return _done(forest, agent, what, stopped, [node], -1)

    async def run_delete(agent: Agent, arguments: dict[str, Any]) -> str:
        node_id = arguments["node_id"]
        async with forest.lock:
            with _operation("delete", node_id) as what:
                parent = await edit.delete(_resolve(forest, node_id))
            return _done(forest, agent, what, None, [parent], 0)

    async def run_recall(agent: Agent, arguments: dict[str, Any]) -> str:
        if "node_id" not in arguments:
            return forest.render(forest, BRIEFING, agent)
        # `Forest.resolve`, not `_resolve`: a read may name the root
        return forest.render(forest.resolve(arguments["node_id"]), RECALL, agent)

    # --- the construct tools (CONSTRUCT_INTERACTION §5): no lock, each
    # synchronous from its checks to its change, the quickview as `recall`'s

    def quickview(named: list[Node]) -> str:
        """The nodes the call named as focuses at depth 0, an id under
        another named id left out."""
        focuses = [n for n in named if not any(n._is_under(other) for other in named)]
        return forest.render(forest, Relative_Focus(frozenset(focuses), 0), agent_of_rendering[0])

    agent_of_rendering: list[Agent] = []

    def nodes_of_call(agent: Agent, arguments: dict[str, Any]) -> tuple[list[Node], list[Node]]:
        """The nodes the ids name — a non-leaf node standing for every node
        under it — those without a construction job left out, and the
        named nodes themselves; `ConstructNotSupported` when none has a
        job.  Each job takes the call's `auto_construct`, stored at once."""
        agent_of_rendering[:] = [agent]
        ids = arguments["node_ids"]
        named = [_resolve(forest, id) for id in ids]
        nodes = [n for root in named for n in root._tree_order() if n.job() is not None]
        nodes = list(dict.fromkeys(nodes))
        if not nodes:
            raise ConstructNotSupported(ids[0] if len(ids) == 1 else None)
        for node in nodes:
            job = node.job()
            assert job is not None
            job.auto_construct = arguments.get("auto_construct", False)
            node._store_alone()
        return nodes, named

    def notices(jobs_: list[Construction_Job], notice: str, none: str) -> str:
        if not jobs_:
            return none
        by_class: dict[type[Construction_Job], list[str]] = {}
        for job in jobs_:
            by_class.setdefault(type(job), []).append(job.node_id)
        return "\n".join(getattr(cls, notice)(ids) for cls, ids in by_class.items())

    async def run_construct(agent: Agent, arguments: dict[str, Any]) -> str:
        nodes, named = nodes_of_call(agent, arguments)
        started: list[Construction_Job] = []
        for node in nodes:
            job = node.job()
            assert job is not None
            if job.can_start():                   # not ready, constructed, running: skipped, the mark says
                job.start(agent)
                started.append(job)
        return notices(started, "starting_notice", "No construction job was started.") + "\n" + quickview(named)

    async def run_cancel_construct(agent: Agent, arguments: dict[str, Any]) -> str:
        nodes, named = nodes_of_call(agent, arguments)
        cancelled: list[Construction_Job] = []
        for node in nodes:
            job = node.job()
            assert job is not None
            if job.outcome is RUNNING and job.owner is agent:   # another agent's run is skipped and goes on
                job.cancel(None)
                cancelled.append(job)
        return notices(cancelled, "cancelling_notice", "No construction job was running.") + "\n" + quickview(named)

    async def run_check_construct(agent: Agent, arguments: dict[str, Any]) -> str | With_Trailer:
        """Returns on one of four conditions, judged at the start and on every
        wake of the caller: an interrupting message waiting; a question
        waiting — delivered again when the mailbox no longer holds it; a
        job of the caller's ended since the start with none of its title
        left running; the deadline (CONSTRUCT_INTERACTION §5)."""
        wait = min(max(arguments["wait_seconds"], WAIT_AT_LEAST), WAIT_AT_MOST)
        at_start = standing(forest._tree_order(), agent)
        if not (at_start.waiting or at_start.running or at_start.checks):
            return NO_JOB
        had = {*at_start.waiting, *at_start.running, *at_start.checks}
        titles_had = {type(job).title() for job in had}

        def now() -> Standing:
            return standing(forest._tree_order(), agent)

        def returns() -> bool:
            stands = now()
            for job in stands.waiting:
                if not any(m.question is job.pending_question for m in agent.mailbox):
                    job.repeat_question()
            if any(m.interrupts for m in stands.messages):
                return True
            left = {*stands.waiting, *stands.running, *stands.checks}
            titles_left = {type(job).title() for job in left}
            return any(type(job).title() not in titles_left for job in had - left)
        try:
            await asyncio.wait_for(agent.sleep_until(returns), wait)
        except TimeoutError:
            pass

        def trailer() -> str:
            stands = now()
            lines = state_lines(stands)
            titles_left = {type(job).title() for job in (*stands.waiting, *stands.running, *stands.checks)}
            for job in sorted(had, key=lambda job: type(job).title()):
                title = type(job).title()
                if title in titles_had and title not in titles_left:
                    lines.append(f"All {type(job).title(plural=True)} have finished.")
                    titles_had.discard(title)
            return "\n".join(lines)
        return With_Trailer("", trailer)

    async def run_answer(agent: Agent, arguments: dict[str, Any]) -> str:
        node_id = arguments["node_id"]
        node = _resolve(forest, node_id)
        job = node.job()
        if job is None or job.pending_question is None:
            raise NoQuestionPending(node_id)
        if job.owner is not agent:
            raise ConstructOwnedByAnother(node_id, job.owned_by_another_refusal())
        shaped = dict(answer_schema)
        shaped["properties"] = dict(answer_schema["properties"]) | {"answer": job.pending_question.schema}
        check_call(shaped, "answer", arguments)
        return job.receive_answer(arguments["answer"]) or ""

    constructions, checks = loaded.construction_job_classes, loaded.evaluation_job_classes
    answer_schema = _schema("answer")
    construct_tools: list[Tool] = []
    if constructions:
        construct_tools += [
            _tool("construct", "Start the construction jobs of nodes, such as "
                  f"{_joined([cls.title(plural=True) for cls in constructions], 'and')}.",
                  _schema("construct"), run_construct, read_only=False),
            _tool("cancel_construct", "Cancel the running construction jobs of nodes.",
                  _schema("cancel_construct"), run_cancel_construct, read_only=False)]
    if constructions or checks:
        construct_tools.append(_tool("check_construct", _check_construct_description(constructions, checks),
                                     _schema("check_construct"), run_check_construct, read_only=True))
    if constructions:
        construct_tools.append(_tool("answer", "Answer the question a construction job asked you",
                                     answer_schema, run_answer, read_only=False))

    return [_tool("edit", "Edit Isabelle theory constructs", loaded.edit_schema, run_edit,
                  read_only=False),
            _tool("move", "Move an Isabelle theory construct", _schema("move"), run_move,
                  read_only=False),
            _tool("delete", "Delete an Isabelle theory construct", _schema("delete"), run_delete,
                  read_only=False),
            _tool("recall", "Read an Isabelle theory construct with what is under it, briefer the"
                  " deeper, or an outline of everything.", _schema("recall"), run_recall,
                  read_only=True),
            *construct_tools]


def _joined(words: list[str], last: str) -> str:
    """Distinct words, alphabetical, joined with commas and `last` before
    the last (CONSTRUCT_INTERACTION §5)."""
    words = sorted(set(words))
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + f" {last} " + words[-1]


def _check_construct_description(constructions: tuple[Any, ...], checks: tuple[Any, ...]) -> str:
    """Completed at start (TOOL_SCHEMAS.md §5): the construction titles
    singular, the evaluation titles plural, the `or all …` part absent
    without evaluation job classes, the first slot absent without
    construction job classes."""
    slots = []
    if constructions:
        slots.append("any " + _joined([cls.title() for cls in constructions], "or"))
    if checks:
        slots.append("all " + _joined([cls.title(plural=True) for cls in checks], "or"))
    return (f"Wait until {' or '.join(slots)} have finished, or a message arrives. Returns at once when"
            " nothing is running. To ensure all jobs have finished, call it repeatedly.")


def _tool(name: str, description: str, schema: JSON_Schema, run: Body, read_only: bool) -> Tool:
    """One object per tool is what the agent is told and what a call is
    held to: the schema validated as the tool is built
    (`plugin.validate_call_schema`), and every call checked against it
    before `run` sees it (`plugin.check_call`); the constructs inside
    `edit`'s are `edit.py`'s to check, element by element."""
    validate_call_schema(schema, name)

    async def checked(agent: Agent, arguments: dict[str, Any]) -> str | With_Trailer:
        check_call(schema, name, arguments)
        return await run(agent, arguments)
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


def _done(forest: Forest, agent: Agent, what: str, stopped: Node | None, nodes: list[Node],
          depth: int) -> str:
    """A successful call's result (TOOL_SCHEMAS.md §4): the `Done` line,
    naming the stop when evaluation did not reach its destination, over
    the quickview for the caller (PRINT.md §5)."""
    assert forest.lock.locked(), "a call's answer is rendered under the forest lock"
    line = f"Done: {what}"
    if stopped is not None:
        line += f"; evaluation stopped at {forest.id_of(stopped)}"
    return f"{line}.\n" + forest.render(forest, Relative_Focus(frozenset(nodes), depth), agent)
