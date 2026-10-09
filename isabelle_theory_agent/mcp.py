"""The tools of MCP_SPECIFICATION §1 (MODULE_STRUCTURE §4.6): `tools`
builds what the server advertises and runs for one conversation.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import jsoncomment

from . import edit
from .exceptions import (
    ConstructNotSupported, ConstructOwnedByAnother, HoldsNoChildren, MoveBesideItself, NoQuestionPending,
    ProtectedNode, TAT_Error, TAT_InternalError)
from .jobs import RUNNING, Agent, Construction_Job, Job_Class, Standing, by_title, series, standing, state_lines
from .mcp_server import Body, Tool, Trailer, With_Trailer
from .model import (
    BRIEFING, Evaluation, Forest, JSON_Schema, Node, NonLeaf_Node, RECALL, Relative_Focus, Theory)
from .plugin import Loaded, check_call, validate_call_schema

# `check_construct`'s clamps on `wait_seconds` (CONSTRUCT_INTERACTION §5, §8): at
# least 3 seconds, and a minute under the clients' twelve-hour tool limit
WAIT_AT_LEAST = 3
WAIT_AT_MOST = 12 * 3600 - 60
NO_JOB = "No job is running."     # `check_construct`'s one-line body when nothing stands (CONSTRUCT_INTERACTION §5)

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
    quickview (PRINT.md §5).  `evaluate_to` (MCP_SPECIFICATION §4), the
    walk under the lock, its opening line over the quickview.  And
    `recall` (RECALL.md), which renders the node in `Recall`, or the
    briefing when no node is named, under no lock.  Every rendering is
    for the calling agent; every call is checked against its tool's
    schema before the entry runs (`_tool`)."""

    async def run_edit(agent: Agent, arguments: dict[str, Any]) -> str | With_Trailer:
        action, target_id = arguments["action"], arguments["target_id"]
        constructs = arguments["constructs"]
        auto_construct = arguments.get("auto_construct", False)     # off when left out (TOOL_SCHEMAS.md §1)
        async with forest.lock:
            with _operation(action, target_id) as what:
                if action == "amend":
                    nodes = await edit.amend(_resolve(forest, target_id), constructs, loaded.kinds, auto_construct)
                elif action in _ACTION_POSITION:
                    parent, index = _location(forest, _ACTION_POSITION[action], target_id)
                    nodes = await edit.insert(parent, index, constructs, loaded.kinds, auto_construct)
                else:
                    raise TAT_InternalError(f"unknown action {action!r}")
            ev = await _evaluate(forest, nodes[-1], agent) if arguments["evaluate"] else None
            return _done(forest, agent, what, ev, nodes, -1)

    async def run_move(agent: Agent, arguments: dict[str, Any]) -> str | With_Trailer:
        source_id, location = arguments["source_id"], arguments["location"]
        position, node_id = location["position"], location["node_id"]
        where = f"{source_id} {position} {node_id}"   # the target phrase (TOOL_SCHEMAS.md §4)
        async with forest.lock:
            with _operation("move", where) as what:
                node = _resolve(forest, source_id)
                parent, index = _location(forest, position, node_id, moving=node)
                await edit.move(node, parent, index)
            ev = await _evaluate(forest, node, agent) if arguments["evaluate"] else None
            return _done(forest, agent, what, ev, [node], -1)

    async def run_evaluate_to(agent: Agent, arguments: dict[str, Any]) -> str | With_Trailer:
        """The walk up to the node named — the root and a session standing
        for their trees (ARCHITECTURE §3.5) — under the lock, held through
        `blocking`'s wait and the quickview; the opening line over the
        quickview of the destination at depth 0 (TOOL_SCHEMAS.md §4, PRINT.md
        §5)."""
        async with forest.lock:
            node = forest.resolve(arguments["node_id"])
            ev = Evaluation(destination=node, ignore_error=arguments.get("ignore_error", False),
                            starter=agent, checks=arguments.get("checks", "quick"))
            await forest._run(ev)
            line = f"Evaluation reached {forest.id_of(node)}." if ev.stopped_at is None \
                else f"Evaluation stopped at {forest.id_of(ev.stopped_at)}."
            return _answer(forest, agent, line, ev, [node], 0)

    async def run_delete(agent: Agent, arguments: dict[str, Any]) -> str | With_Trailer:
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

    def quickview(named: list[Node], agent: Agent) -> str:
        """The nodes the call named as focuses at depth 0, an id under
        another named id left out."""
        focuses = [n for n in named if not any(n._is_under(other) for other in named)]
        return forest.render(forest, Relative_Focus(frozenset(focuses), 0), agent)

    def jobs_of_call(ids: list[str]) -> tuple[list[Construction_Job], list[Node]]:
        """The construction jobs of the nodes the ids name — a non-leaf node
        standing for every node under it — each once, in tree order, and
        the named nodes; `ConstructNotSupported` when there is none."""
        named = [_resolve(forest, id, root_ok=True) for id in ids]   # the root stands for every tree (CI §5)
        nodes = dict.fromkeys(n for root in named for n in root._tree_order())
        jobs = [job for n in nodes if (job := n.job()) is not None]
        if not jobs:
            raise ConstructNotSupported(ids[0] if len(ids) == 1 else None)
        return jobs, named

    async def run_construct(agent: Agent, arguments: dict[str, Any]) -> str:
        """`auto_construct` written on every job of the call and stored on
        every node — by the start on those it starts, here on the skipped —
        the `Started …` line over the quickview (CONSTRUCT_INTERACTION §5)."""
        jobs, named = jobs_of_call(arguments["node_ids"])
        started: list[Construction_Job] = []
        for job in jobs:
            job.auto_construct = arguments.get("auto_construct", False)
            if job.can_start():                   # not ready, constructed, running: skipped, the mark says
                job.start(agent)
                started.append(job)
            else:
                job.node._store_alone()
        notice = _notices(started, lambda cls, ids: cls.starting_notice(ids)) or "No construction job was started."
        return notice + "\n" + quickview(named, agent)

    async def run_cancel_construct(agent: Agent, arguments: dict[str, Any]) -> str:
        """`auto_construct` written and stored on every node of the call,
        every run of the caller's among them cancelled, the `Cancelled …`
        line over the quickview (CONSTRUCT_INTERACTION §5)."""
        jobs, named = jobs_of_call(arguments["node_ids"])
        cancelled: list[Construction_Job] = []
        for job in jobs:
            job.auto_construct = arguments.get("auto_construct", False)
            if job.outcome is RUNNING and job.owner is agent:   # another agent's run is skipped and goes on
                job.cancel(None)
                cancelled.append(job)
            job.node._store_alone()
        notice = _notices(cancelled, lambda cls, ids: cls.cancelling_notice(ids)) or "No construction job was running."
        return notice + "\n" + quickview(named, agent)

    async def run_check_construct(agent: Agent, arguments: dict[str, Any]) -> str | With_Trailer:
        """Returns on one of four conditions, judged at the start and on every
        wake of the caller: an interrupting message waiting; a question
        waiting — delivered again where the mailbox no longer holds it; a
        title the caller had a job of during the call and has none of now;
        the deadline (CONSTRUCT_INTERACTION §5)."""
        wait = min(max(arguments["wait_seconds"], WAIT_AT_LEAST), WAIT_AT_MOST)
        if not standing(forest, agent).jobs:
            return NO_JOB
        had: dict[str, Job_Class] = {}            # the titles the caller had a job of during the call, each with the class wording it

        def finished(stands: Standing) -> list[Job_Class]:
            """The classes of the titles the caller had and has none of now,
            construction titles first, then evaluation titles, alphabetical within."""
            for job in stands.jobs:
                had.setdefault(type(job).title(), type(job))
            left = {type(job).title() for job in stands.jobs}
            return sorted((cls for title, cls in had.items() if title not in left),
                          key=lambda cls: (not issubclass(cls, Construction_Job), cls.title()))

        def returns() -> bool:
            stands = standing(forest, agent)
            return bool(stands.waiting or any(m.interrupts for m in stands.messages) or finished(stands))
        try:
            await asyncio.wait_for(agent.sleep_until(returns), wait)
        except TimeoutError:
            pass
        for job in standing(forest, agent).waiting:
            job.repeat_question()

        def trailer() -> str:
            stands = standing(forest, agent)
            return "\n".join([*state_lines(stands),
                              *(f"All {cls.title(plural=True)} have finished." for cls in finished(stands))])
        return With_Trailer("", trailer)

    async def run_answer(agent: Agent, arguments: dict[str, Any]) -> str:
        node_id = arguments["node_id"]
        node = _resolve(forest, node_id, root_ok=True)       # the root answers NoQuestionPending (CI §5)
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
    evaluate_schema = _schema("evaluate_to")
    if checks:                                    # `checks` completed at start, absent without a class (TOOL_SCHEMAS.md §5)
        property = evaluate_schema["properties"]["checks"]
        property["description"] = property["description"].replace(
            "{titles}", _joined([cls.title(plural=True) for cls in checks], "and"))
    else:
        del evaluate_schema["properties"]["checks"]
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
            _tool("evaluate_to", "Evaluate Isabelle theory constructs up to a node. Already evaluated"
                  " constructs are skipped.", evaluate_schema, run_evaluate_to, read_only=False),
            *construct_tools]


def _joined(words: list[str], last: str) -> str:
    """Distinct words, alphabetical, joined with commas and `last` before
    the last (CONSTRUCT_INTERACTION §5)."""
    return series(sorted(set(words)), last)


def _notices(jobs: list[Construction_Job],
             notice: Callable[[type[Construction_Job], list[str]], str]) -> str:
    """The jobs' nodes named by their classes' `notice` — `starting_notice`,
    `cancelling_notice`, `automatic_notice` — one line or list per class
    (CONSTRUCT_INTERACTION §5); empty for none."""
    by_class: dict[type[Construction_Job], list[str]] = {}
    for job in jobs:
        by_class.setdefault(type(job), []).append(job.shown_id)
    return "\n".join(notice(cls, ids) for cls, ids in by_class.items())


def _order_constraint_sentence(forest: Forest, stop: Node | None) -> list[str]:
    """RENDER_BASELINES §3's sentence under the order constraint's stop —
    a tree importing a forest tree placed after it, or itself — composed
    from the forest's answer; nothing under any other stop."""
    item = forest._order_violation(stop) if stop is not None else None
    if not isinstance(stop, Theory) or item is None:
        return []
    if forest._resolved_imports(stop) == [stop]:
        return [f"`{forest.id_of(stop)}` imports itself. Remove `{item}` from its imports."]
    return [f"Since `{forest.id_of(stop)}` imports `{item}`, you cannot put it before `{item}`. Move it later."]


def _evaluation_trailer(forest: Forest, agent: Agent, ev: Evaluation) -> Trailer:
    """What a call that ran an evaluation adds after its messages
    (CONSTRUCT_INTERACTION §5): the constructions the walk started
    automatically, by class, then the background line."""
    def trailer() -> str:
        parts = [_notices(ev.started, lambda cls, ids: cls.automatic_notice(ids)), _background_line(forest, agent)]
        return "\n\n".join(part for part in parts if part)
    return trailer


def _background_line(forest: Forest, agent: Agent) -> str:
    """The caller's running evaluation jobs, all of them, counted by title
    (CONSTRUCT_INTERACTION §5) — nothing at zero; the first time for the
    agent, keyed `(0, "background")` in its seen set, the line also says
    what to call."""
    groups = by_title(standing(forest, agent).checks)
    if not groups:
        return ""
    words = [f"{len(ids)} {cls.title(plural=len(ids) > 1)}" for _, cls, ids in groups]
    total = sum(len(ids) for _, _, ids in groups)
    line = f"{series(words, 'and')} {'are' if total > 1 else 'is'} running in the background"
    key = (0, "background")
    if key in agent.seen:
        return line + "."
    agent.seen.add(key)
    forest.conversation.log.agent.seen(key=key)
    return line + "; call `check_construct` to wait for them."


def _check_construct_description(constructions: tuple[Any, ...], checks: tuple[Any, ...]) -> str:
    """Completed at start (TOOL_SCHEMAS.md §5): the construction titles
    singular, the evaluation titles plural, the `or all …` part absent
    without evaluation job classes — the verb then singular —, the first
    slot absent without construction job classes."""
    slots = []
    if constructions:
        slots.append("any " + _joined([cls.title() for cls in constructions], "or"))
    if checks:
        slots.append("all " + _joined([cls.title(plural=True) for cls in checks], "or"))
    return (f"Wait until {' or '.join(slots)} {'have' if checks else 'has'} finished, or a message arrives."
            " Returns at once when nothing is running. To ensure all jobs have finished, call it repeatedly.")


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
    """The node an id names: `Sessions` only where the caller says
    `root_ok` — `into` for `_location`, and `construct`/`cancel_construct`/
    `answer`, for which the root stands for every tree (CI §5) —,
    `ProtectedNode` elsewhere (TOOL_SCHEMAS.md §1, §2).  A tool that reads
    the root (`recall`, `evaluate_to`) resolves through `forest.resolve`,
    not here."""
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


async def _evaluate(forest: Forest, destination: Node, agent: Agent) -> Evaluation:
    """`evaluate` true (MCP_SPECIFICATION §3.2): run up to the change's
    natural destination under the lock the call holds, `ignore_error`
    unset, the checks `quick` (MODULE_STRUCTURE §4.2 step 4); the walk,
    with where it stopped and what it started."""
    ev = Evaluation(destination=destination, ignore_error=False, starter=agent, checks="quick")
    await forest._run(ev)
    return ev


def _done(forest: Forest, agent: Agent, what: str, ev: Evaluation | None, nodes: list[Node],
          depth: int) -> str | With_Trailer:
    """A successful change's result (TOOL_SCHEMAS.md §4): the `Done` line,
    naming the stop when evaluation did not reach its destination, over
    the quickview."""
    line = f"Done: {what}"
    if ev is not None and ev.stopped_at is not None:
        line += f"; evaluation stopped at {forest.id_of(ev.stopped_at)}"
    return _answer(forest, agent, line + ".", ev, nodes, depth)


def _answer(forest: Forest, agent: Agent, line: str, ev: Evaluation | None, focuses: list[Node],
            depth: int) -> str | With_Trailer:
    """A successful call's result over the quickview (TOOL_SCHEMAS.md §4,
    PRINT.md §5): its opening line, the order constraint's sentence under
    a stop of that kind, the quickview of `focuses` at `depth` for the
    caller; a call that evaluated asks for the evaluation's trailer
    (CONSTRUCT_INTERACTION §5)."""
    assert forest.lock.locked(), "a call's answer is rendered under the forest lock"
    stop = ev.stopped_at if ev is not None else None
    text = "\n".join([line, *_order_constraint_sentence(forest, stop),
                      forest.render(forest, Relative_Focus(frozenset(focuses), depth), agent)])
    return text if ev is None else With_Trailer(text, _evaluation_trailer(forest, agent, ev))
