"""The MCP server (MODULE_STRUCTURE §4.6): the endpoint and its transport
security, the tool boundary (EXCEPTIONS.md §1), the conversation's
ending (RENDER_BASELINES §4), against the `mcp` SDK's own Streamable
HTTP client.  Run: python -m pytest test/test_mcp_server.py
"""

import asyncio
import json
import shlex
import shutil
import sys
import tomllib
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import uvicorn
from mcp import types
from mcp.shared.exceptions import McpError

import stand_ins
from baselines import DOCS, fenced_blocks, fenced_lines
from harness import client, free_port, text_of
from isabelle_theory_agent import log, mcp, mcp_server, plugin, toplevel
from isabelle_theory_agent.mcp import EDIT_DESCRIPTION
from isabelle_theory_agent.exceptions import (
    NodeNotFound, TAT_DisasterError, TAT_InternalError, TAT_StartupError)
from isabelle_theory_agent.jobs import Agent, Message, post
from isabelle_theory_agent.mcp_server import (
    AGENTS, DOT_TAT, HOST, Claude_Code_Server, Codex_Server, TAT_Server, Tool, With_Trailer, _bind,
    agent_directory, resolver_entry, stopped, stopped_for, toml_string)
from isabelle_theory_agent.model import CannotUseWorkingDirectory

# The seven server lines, in document order; an eighth, a missing one or a
# reordering fails here, an edited one fails the assertions below.
SERVER_LINES = fenced_lines(DOCS / "RENDER_BASELINES.md", "4.")
(INTERNAL, UNSAVED, GONE, NO_TRANSCRIPT, NOT_SANDBOXED, NOT_CONNECTED,
 NO_WORKING_DIRECTORY) = SERVER_LINES

SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}
STRICT_SCHEMA = {"type": "object", "properties": {"field": {"type": "string"}},
                 "required": ["field"], "additionalProperties": False}


def run(scenario):
    """One deadline for every test, so a hang is a red test."""
    asyncio.run(asyncio.wait_for(scenario(), 30))


class Bodies:
    """The stub tools' bodies, with what the tests need to see of them: a
    body holding on `release` reports that it `began`, and every body its
    end in `finished`."""
    def __init__(self):
        self.release = asyncio.Event()
        self.finished: set[str] = set()
        self._began: dict[str, asyncio.Event] = {}

    def began(self, name: str) -> asyncio.Event:
        return self._began.setdefault(name, asyncio.Event())

    async def echo(self, agent, arguments):
        return "echo " + arguments["text"]

    async def strict(self, agent, arguments):         # its schema requires `field`
        return "got " + repr(sorted(arguments))

    async def slow(self, agent, arguments):
        self.began("slow").set()
        await self.release.wait()
        self.finished.add("slow")
        return "slow done"

    async def slow_bug(self, agent, arguments):       # a bug after the client gave up
        self.began("slow_bug").set()
        await self.release.wait()
        self.finished.add("slow_bug")
        raise RuntimeError("late-bug")

    async def stubborn(self, agent, arguments):       # completes after ignoring the ending's cancellation
        self.began("stubborn").set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            await self.release.wait()
        self.finished.add("stubborn")
        return "stubborn done"

    async def refused(self, agent, arguments):
        raise NodeNotFound("theory_X", [])

    async def bug(self, agent, arguments):
        raise RuntimeError("tat-bug")

    async def disaster(self, agent, arguments):
        raise TAT_DisasterError("disk full")

    async def wire_dead(self, agent, arguments):
        raise ConnectionResetError("peer closed connection")

    async def escapes(self, agent, arguments):        # lets a cancellation escape
        raise asyncio.CancelledError()

    async def not_text(self, agent, arguments):       # the boundary's own failure
        return {"not": "text"}                        # type: ignore[return-value]

    def plain(self, agent, arguments):                # a malformed tool: not a coroutine
        return "plain"

    def tools(self) -> list[Tool]:
        names = ("echo", "strict", "slow", "slow_bug", "stubborn", "refused", "bug",
                 "disaster", "wire_dead", "escapes", "not_text", "plain")
        return [Tool(name, f"the {name} tool", STRICT_SCHEMA if name == "strict" else SCHEMA,
                     getattr(self, name), read_only=name == "echo") for name in names]


@asynccontextmanager
async def serving(port: int, tools: list[Tool],
                  server_class: type[TAT_Server] = Claude_Code_Server):
    """A server on a socket bound here, accepting and serving in a task, on
    an ending object and an agents dict of its own — Claude Code's by
    default, the client the harness's `client()` is; yields the server and
    the serving task, which raises what ended the conversation (`ended`)."""
    with _bind(port) as sock:
        async with stand_ins.ending() as ending, server_class(ending, sock, tools, {}) as server:
            serve = asyncio.create_task(server.serve())
            try:
                yield server, serve
            finally:
                if not serve.done():
                    serve.cancel()
                await asyncio.wait({serve})
                if not serve.cancelled():
                    serve.exception()                 # retrieved: the tests inspect it themselves


async def launched(tools: list[Tool], block: Callable[[TAT_Server], Awaitable[Any]]
                   ) -> tuple[TAT_Server, asyncio.Task]:
    """`launch_TAT`'s shape: a socket bound, an ending object and a server
    entered in a task of their own, running `block` inside them — the task
    the RPC host cancels; returned once the server accepts."""
    ending = stand_ins.ending()
    accepting: asyncio.Future[TAT_Server] = asyncio.get_running_loop().create_future()

    async def launch_TAT():
        with _bind(free_port()) as sock:
            server = Claude_Code_Server(ending, sock, tools, {})
            async with ending, server:
                accepting.set_result(server)
                await block(server)
    task = asyncio.create_task(launch_TAT())
    return await accepting, task


async def ended(serve: asyncio.Task):
    """What `serve` raised: the exception, or `CancelledError` itself."""
    await asyncio.wait({serve})
    return asyncio.CancelledError if serve.cancelled() else serve.exception()


def hold_accepting(server: TAT_Server) -> asyncio.Event:
    """Keep the server accepting after the ending is entered until the
    returned event is set: `serve` stops accepting once uvicorn's main
    loop returns, and the loop polls every 0.1 s, so a test that needs the
    accepting window holds it open instead of racing the tick."""
    released = asyncio.Event()
    main_loop = server._uvicorn.main_loop

    async def held():
        await main_loop()                             # returns once `end` has run
        await released.wait()
    server._uvicorn.main_loop = held                  # type: ignore[method-assign]
    return released


async def refused_at_the_transport(url: str):
    """Nothing accepts a connection at `url`."""
    async with httpx.AsyncClient() as http:
        with pytest.raises(httpx.ConnectError):
            await http.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                            headers={"Accept": "application/json, text/event-stream"})


def test_tools_are_advertised_and_a_result_is_the_bodys_text():
    async def scenario():
        port = free_port()
        bodies = Bodies()
        async with serving(port, bodies.tools()) as (server, _), client(server.url) as session:
            listed = await session.list_tools()
            assert [t.name for t in listed.tools] == [t.name for t in bodies.tools()]
            assert listed.tools[0].description == "the echo tool"
            assert listed.tools[0].inputSchema == SCHEMA
            assert [t.annotations for t in listed.tools[:2]] == [
                types.ToolAnnotations(readOnlyHint=True), types.ToolAnnotations(readOnlyHint=False)]
            result = await session.call_tool("echo", {"text": "hi"})
            assert (text_of(result), result.isError) == ("echo hi", False)
            # the SDK's input validation is off: a call the schema would
            # refuse reaches the body, and no SDK message reaches the agent
            unchecked = await session.call_tool("strict", {})
            assert (text_of(unchecked), unchecked.isError) == ("got []", False)
    run(scenario)


def test_a_tat_error_is_rendered_and_nothing_else_is():
    """A `TAT_Error` becomes the result's text; a bug ends the conversation:
    the call that raised it and a call in flight are answered the one
    line, and so is a tool call arriving while the server still accepts,
    while `tools/list` answers as ever; a body that completed after
    ignoring the ending's cancellation is answered what it did
    (MODULE_STRUCTURE §4.6); `serve` raises the bug."""
    async def scenario():
        port = free_port()
        bodies = Bodies()
        async with serving(port, bodies.tools()) as (server, serve):
            accepting = hold_accepting(server)
            async with client(server.url) as session:
                # the SDK asks for the tool list after a first success it
                # has no schema for; asked here, so no request of its own
                # races the assertions below
                await session.list_tools()
                refused = await session.call_tool("refused", {})
                assert refused.isError and text_of(refused) == str(NodeNotFound("theory_X", []))

                in_flight = asyncio.create_task(session.call_tool("slow", {}))
                kept = asyncio.create_task(session.call_tool("stubborn", {}))
                await bodies.began("slow").wait()
                await bodies.began("stubborn").wait()
                ended_by = await session.call_tool("bug", {})
                assert ended_by.isError and text_of(ended_by) == INTERNAL
                waiting = await in_flight
                assert waiting.isError and text_of(waiting) == INTERNAL
                assert "slow" not in bodies.finished   # cancelled, not run to its end
                late = await session.call_tool("echo", {"text": "late"})
                assert late.isError and text_of(late) == INTERNAL
                listed = await session.list_tools()   # not a tool call: answered as ever
                assert [t.name for t in listed.tools] == [t.name for t in bodies.tools()]
                accepting.set()
                exn = await ended(serve)              # `serve` raises at once; the drain is the exit's
                assert isinstance(exn, RuntimeError) and str(exn) == "tat-bug"
                assert not kept.done()                # `stubborn` is still in flight, still to be answered
                bodies.release.set()
                stubborn = await kept
                assert (text_of(stubborn), stubborn.isError) == ("stubborn done", False)
                # The records (LOGGING.md §4): every call has its `call`
                # record, a call arriving during the ending included; then
                # `result`, a `TAT_Error`'s with its class, or, for the three
                # calls answered the ending's line, `while_ending`, written
                # after `ending`.
                tool_records = stand_ins.records("tool")
                assert [(r["event"], r["data"]["tool"]) for r in tool_records] == [
                    ("call", "refused"), ("result", "refused"), ("call", "slow"), ("call", "stubborn"),
                    ("call", "bug"), ("while_ending", "bug"), ("while_ending", "slow"),
                    ("call", "echo"), ("while_ending", "echo"), ("result", "stubborn")]
                refused_record = tool_records[1]["data"]
                assert (refused_record["is_error"], refused_record["class"]) == (True, "NodeNotFound")
                assert refused_record["text"] == str(NodeNotFound("theory_X", []))
                assert tool_records[0]["data"]["arguments"] == {}
                assert tool_records[-1]["data"]["is_error"] is False and "class" not in tool_records[-1]["data"]
                [ending_record] = [r for r in stand_ins.records("conversation") if r["event"] == "ending"]
                assert ending_record["level"] == "error"
                assert ending_record["data"]["message"] == "RuntimeError: tat-bug"
                assert ending_record["ts"] <= tool_records[5]["ts"]
                await refused_at_the_transport(server.url)   # it stopped accepting
        # `ended` once the unwinding is over: after the last call's answer
        [ended_record] = [r for r in stand_ins.records("conversation") if r["event"] == "ended"]
        assert ended_record["ts"] >= stand_ins.records("tool")[-1]["ts"]
        assert list(ended_record["data"]) == ["duration"]
    run(scenario)


def test_the_conversation_ends_with_the_client_still_attached():
    """The deployed shape: the agent is still connected, holding the
    standalone stream, when the conversation ends (§4.6).  The server
    leaves regardless — the manager's streams end before uvicorn waits for
    the connections to close."""
    async def scenario():
        port = free_port()
        bodies = Bodies()
        attached, let_go = asyncio.Event(), asyncio.Event()

        async def agent(url):                         # its own task: its own process
            async with client(url) as session:
                result = await session.call_tool("bug", {})
                assert result.isError and text_of(result) == INTERNAL
                attached.set()
                await let_go.wait()

        async with serving(port, bodies.tools()) as (server, serve):
            still_there = asyncio.create_task(agent(server.url))
            await attached.wait()
            exn = await ended(serve)
            assert isinstance(exn, RuntimeError) and str(exn) == "tat-bug"
        let_go.set()                                  # reached: the server left
        await still_there
    run(scenario)


def test_the_stopped_line_names_the_reason():
    assert stopped(TAT_DisasterError("x")) == UNSAVED
    assert stopped(ConnectionResetError()) == GONE
    assert stopped(asyncio.CancelledError()) == GONE
    assert stopped(CannotUseWorkingDirectory("x")) == NO_WORKING_DIRECTORY
    assert stopped(RuntimeError()) == INTERNAL
    # one form for every reason, those no branch chooses yet included
    for line in SERVER_LINES:
        reason = line.removeprefix("TAT has stopped: ").split(";")[0]
        assert stopped_for(reason) == line


@pytest.mark.parametrize("tool, ended_type, line", [
    ("disaster", TAT_DisasterError, UNSAVED), ("wire_dead", ConnectionResetError, GONE)])
def test_a_disaster_and_a_dead_wire_end_the_conversation_too(tool, ended_type, line):
    async def scenario():
        port = free_port()
        async with serving(port, Bodies().tools()) as (server, serve), client(server.url) as session:
            result = await session.call_tool(tool, {})
            assert result.isError and text_of(result) == line
            assert isinstance(await ended(serve), ended_type)
    run(scenario)


@pytest.mark.parametrize("tool, ended_type, message", [
    ("escapes", TAT_InternalError, "the body of `escapes` was cancelled"),
    ("not_text", TAT_InternalError, "the body of `not_text` returned a dict, not a text"),
    ("plain", TypeError, None)])
def test_the_boundary_failing_is_a_bug_that_ends_the_conversation(tool, ended_type, message):
    """A body letting a cancellation escape, returning what is not a text,
    or not being a coroutine at all: the agent gets the internal-error
    line, never an SDK rendering, and the conversation ends."""
    async def scenario():
        port = free_port()
        async with serving(port, Bodies().tools()) as (server, serve), client(server.url) as session:
            result = await session.call_tool(tool, {})
            assert result.isError and text_of(result) == INTERNAL
            exn = await ended(serve)
            assert isinstance(exn, ended_type)
            if message is not None:
                assert str(exn) == message
    run(scenario)


@pytest.mark.parametrize("another_door_first", [False, True])
def test_uvicorns_loop_failing_on_its_own_still_drains(another_door_first):
    """uvicorn's loop failing on its own is a bug that enters the ending,
    unless another door was reached first (MODULE_STRUCTURE §4.6) — then it
    is written `while_ending` (LOGGING.md §4): `serve` raises what ended the
    conversation and stops accepting, and the call in flight is still
    answered."""
    async def scenario():
        port = free_port()
        bodies = Bodies()
        loop_fails = asyncio.Event()

        async def failing():
            await loop_fails.wait()
            raise RuntimeError("loop-bug")

        async with serving(port, bodies.tools()) as (server, serve):
            server._uvicorn.main_loop = failing          # type: ignore[method-assign]
            async with client(server.url) as session:
                # the SDK's `call_tool` lists the tools once, to check the
                # result's shape: here, not after the answer, when nothing
                # accepts
                await session.list_tools()
                kept = asyncio.create_task(session.call_tool("stubborn", {}))
                await bodies.began("stubborn").wait()
                first = RuntimeError("first") if another_door_first else None
                if first is not None:
                    server.ending.end(first)
                loop_fails.set()
                exn = await ended(serve)
                bodies.release.set()                  # before any assertion: the exit waits for it
                stubborn = await kept
                assert (text_of(stubborn), stubborn.isError) == ("stubborn done", False)
                if first is not None:
                    assert exn is first
                else:
                    assert isinstance(exn, RuntimeError) and str(exn) == "loop-bug"
                await refused_at_the_transport(server.url)
            assert stand_ins.events("tool")[-1] == "result"
        if another_door_first:
            [record] = [r for r in stand_ins.records("conversation") if r["event"] == "while_ending"]
            assert record["data"]["message"] == "RuntimeError: loop-bug"
            assert 'raise RuntimeError("loop-bug")' in record["data"]["traceback"]
            assert stand_ins.events("conversation") == ["client_connected", "ending", "while_ending", "ended"]
        else:
            assert stand_ins.events("conversation") == ["client_connected", "ending", "ended"]
    run(scenario)


def test_the_ending_waits_for_a_task_still_unwinding_before_ended():
    """On `Ending` alone (MODULE_STRUCTURE §4.6): a spawned task that
    catches its cancellation and keeps unwinding is waited for; `ended`
    comes after."""
    seen: list[str] = []

    async def scenario():
        released = asyncio.Event()
        async with stand_ins.ending() as ending:
            async def body():
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    await released.wait()
                    seen.extend(stand_ins.events("conversation"))
            ending.spawn(body())
            await asyncio.sleep(0)
            ending.end(RuntimeError("over"))
            asyncio.get_running_loop().call_later(0.05, released.set)
        assert seen == ["ending"]
        assert stand_ins.events("conversation") == ["ending", "ended"]
    run(scenario)


def test_an_exception_whose_str_fails_still_enters_the_ending():
    """`end` enters the ending in one synchronous stretch whatever the
    exception (MODULE_STRUCTURE §4.6): `wait` returns and the spawned task
    is cancelled."""
    class Unspeakable(Exception):
        def __str__(self):
            raise RuntimeError("no words")

    async def scenario():
        async with stand_ins.ending() as ending:
            spawned = ending.spawn(asyncio.Event().wait())
            ending.end(Unspeakable())
            await ending.wait()
            assert ending.entered
            await asyncio.wait({spawned})
            assert spawned.cancelled()
    run(scenario)


def test_a_task_spawned_after_the_ending_is_cancelled_at_once():
    """A task spawned once the ending is entered — the unwinding's own
    work reaching `spawn` — is cancelled as the others were (MODULE_STRUCTURE
    §4.6): it raises `CancelledError` at its first await, and `unwound`
    waits only for its unwinding."""
    async def scenario():
        async with stand_ins.ending() as ending:
            ending.end(RuntimeError("over"))
            late = ending.spawn(asyncio.Event().wait())
            await asyncio.wait({late})
            assert late.cancelled()
            await ending.unwound()
    run(scenario)


def test_the_ending_counts_as_cancelled_only_the_tasks_its_cancel_reached():
    """`cancelled` (MODULE_STRUCTURE §4.6): a task still running when the
    ending was entered, or spawned after, the ending cancelled; one that
    finished before — here letting its own cancellation escape, its removal
    from the ending's tasks still queued — it did not."""
    async def scenario():
        async def escapes():
            raise asyncio.CancelledError()

        async with stand_ins.ending() as ending:
            early = ending.spawn(escapes())
            running = ending.spawn(asyncio.Event().wait())
            await asyncio.sleep(0)
            assert early.done() and early in ending._tasks    # finished, its removal callback still queued
            ending.end(RuntimeError("over"))
            late = ending.spawn(asyncio.Event().wait())
            await asyncio.wait({early, running, late})
            assert not ending.cancelled(early)
            assert ending.cancelled(running) and ending.cancelled(late)
    run(scenario)


def test_a_cause_reaching_the_entered_ending_is_recorded_once_and_changes_nothing():
    """A cause reaching `end` once the ending is entered, whenever it arose
    — for example a tool body's failure read only after another door
    entered the ending, the unwinding's own work failing, a cancellation —
    is written `while_ending` (LOGGING.md §4; MODULE_STRUCTURE §4.6), the
    end staying the first cause's; a cause arriving again by another door,
    the first included, is written once: the same object, not the same
    class and message."""
    async def scenario():
        async with stand_ins.ending() as ending:
            first = RuntimeError("first")
            ending.end(first)
            try:
                raise RuntimeError("first")
            except RuntimeError as raised:  # the name is unbound past the clause
                second = raised
            ending.end(second)
            ending.end(first)
            ending.end(second)
            ending.end(asyncio.CancelledError())
            assert ending.ended_by is first
            second_record, cancelled = [r for r in stand_ins.records("conversation") if r["event"] == "while_ending"]
            assert second_record["level"] == "error"
            assert second_record["data"]["class"] == "RuntimeError"
            assert second_record["data"]["message"] == "RuntimeError: first"
            assert "Traceback (most recent call last)" in second_record["data"]["traceback"]
            assert 'raise RuntimeError("first")' in second_record["data"]["traceback"]
            assert cancelled["data"]["class"] == "CancelledError"
            assert cancelled["data"]["message"] == log.CANCELLED
        assert stand_ins.events("conversation") == ["ending", "while_ending", "while_ending", "ended"]
    run(scenario)


def test_the_hosts_cancellation_enters_the_ending_and_is_raised():
    """The RPC host cancelling `launch_TAT` (the connection gone): a call in
    flight is answered `Isabelle is gone`, and `serve` raises the
    cancellation for `launch_TAT` to pass on; the `ending` record says it in
    a sentence; the body the ending cancelled is no cause, so no
    `while_ending` (LOGGING.md §4)."""
    async def scenario():
        port = free_port()
        bodies = Bodies()
        async with serving(port, bodies.tools()) as (server, serve), client(server.url) as session:
            in_flight = asyncio.create_task(session.call_tool("slow", {}))
            await bodies.began("slow").wait()
            serve.cancel()
            waiting = await in_flight
            assert waiting.isError and text_of(waiting) == GONE
            assert await ended(serve) is asyncio.CancelledError
        assert stand_ins.events("conversation") == ["client_connected", "ending", "ended"]
        [ending_record] = [r for r in stand_ins.records("conversation") if r["event"] == "ending"]
        assert ending_record["data"]["class"] == "CancelledError"
        assert ending_record["data"]["message"] == log.CANCELLED
        assert "CancelledError" in ending_record["data"]["traceback"]
    run(scenario)


def test_an_escaped_cancellation_is_a_bug_once_another_door_entered_the_ending_too():
    """Two bodies woken together, the first a bug that enters the ending,
    the second letting a cancellation escape before its call resumes: it was
    not the ending that cancelled the second (MODULE_STRUCTURE §4.6), so its
    escape is the boundary's bug still, written `while_ending` (LOGGING.md
    §4); both calls get the internal-error line."""
    async def scenario():
        bodies = Bodies()
        go = asyncio.Event()

        async def bug_on_go(agent, arguments):
            bodies.began("bug_on_go").set()
            await go.wait()
            raise RuntimeError("other-door")

        async def escape_on_go(agent, arguments):
            bodies.began("escape_on_go").set()
            await go.wait()
            raise asyncio.CancelledError()

        tools = bodies.tools() + [Tool("bug_on_go", "the bug_on_go tool", SCHEMA, bug_on_go, read_only=False),
                                  Tool("escape_on_go", "the escape_on_go tool", SCHEMA, escape_on_go, read_only=False)]
        async with serving(free_port(), tools) as (server, serve), client(server.url) as session:
            await session.list_tools()      # the SDK's one listing, while something accepts
            first = asyncio.create_task(session.call_tool("bug_on_go", {}))
            await bodies.began("bug_on_go").wait()
            second = asyncio.create_task(session.call_tool("escape_on_go", {}))
            await bodies.began("escape_on_go").wait()
            go.set()
            for answer in (await first, await second):
                assert answer.isError and text_of(answer) == INTERNAL
            exn = await ended(serve)
            assert isinstance(exn, RuntimeError) and str(exn) == "other-door"
            [record] = [r for r in stand_ins.records("conversation") if r["event"] == "while_ending"]
            assert record["data"]["class"] == "TAT_InternalError"
            assert record["data"]["message"].endswith("the body of `escape_on_go` was cancelled")
        assert stand_ins.events("conversation") == ["client_connected", "ending", "while_ending", "ended"]
    run(scenario)


def test_what_escapes_the_servers_block_before_serve_enters_the_ending_at_its_exit():
    """The connection gone before `serve` ran: the server's exit enters the
    ending and drains (MODULE_STRUCTURE §4.6) — the call in flight is
    answered `Isabelle is gone`, between `ending` and `ended`."""
    async def scenario():
        bodies = Bodies()

        async def gone_before_serve(_):
            await bodies.began("slow").wait()
            raise ConnectionResetError("peer closed connection")

        server, launch = await launched(bodies.tools(), gone_before_serve)
        async with client(server.url) as session:
            result = await session.call_tool("slow", {})
        assert result.isError and text_of(result) == GONE
        assert isinstance(await ended(launch), ConnectionResetError)
        assert "slow" not in bodies.finished
        call_record, while_ending = stand_ins.records("tool")
        connected, ending_record, ended_record = stand_ins.records("conversation")
        assert [r["event"] for r in (connected, call_record, ending_record, while_ending, ended_record)] == [
            "client_connected", "call", "ending", "while_ending", "ended"]
        assert call_record["ts"] <= ending_record["ts"] <= while_ending["ts"] <= ended_record["ts"]
    run(scenario)


def test_a_task_unwinding_after_the_ending_still_reads_the_store(tmp_path):
    """The server's exit waits for the spawned tasks to unwind before it
    stops, so before the store closes (MODULE_STRUCTURE §4.6)."""
    read = []

    async def reader(forest):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # past where the server would stop without waiting: uvicorn's
            # loop tick and its shutdown take 0.1 s each
            await asyncio.sleep(0.3)
            read.append(forest.store.nodes())
            raise

    async def scenario():
        async with toplevel.served([], str(tmp_path), free_port(), "claude-code", "",
                                   cast(Any, stand_ins.Recorder())) as (forest, _, server):
            forest.conversation.ending.spawn(reader(forest))
            serve = asyncio.create_task(server.serve())
            await asyncio.sleep(0)                    # the reader and `serve` waiting
            await stand_ins.cancelled_by_the_host(serve)
    run(scenario)
    assert read == [[]]


def test_a_cancellation_during_the_drain_still_stops_the_server(caplog):
    """The RPC host's cancellation reaching `launch_TAT` while the server's
    exit waits for a call in flight (MODULE_STRUCTURE §4.6): the server
    stops regardless — nothing accepts, no connection is left, the session
    manager's run is closed."""
    async def scenario():
        bodies = Bodies()
        server, launch = await launched(bodies.tools(), TAT_Server.serve)
        draining = asyncio.Event()
        idle_wait = server._idle.wait

        async def waiting_for_the_calls():
            draining.set()
            await idle_wait()
        server._idle.wait = waiting_for_the_calls     # type: ignore[method-assign]

        async def agent():
            async with client(server.url) as session:
                await session.call_tool("stubborn", {})

        calling = asyncio.create_task(agent())
        await bodies.began("stubborn").wait()
        server.ending.end(RuntimeError("tat-bug"))
        await draining.wait()
        launch.cancel()
        bodies.release.set()
        assert await ended(launch) is asyncio.CancelledError
        await refused_at_the_transport(server.url)
        assert not server._uvicorn.server_state.connections
        assert server._manager._task_group is None
        calling.cancel()                              # its call is answered by nobody: the server stopped
        await asyncio.wait({calling})
    run(scenario)
    # the manager's run was closed in its own task: nothing left for the
    # loop to close, which anyio refuses from another task
    assert [r for r in caplog.records if r.exc_info and "cancel scope" in str(r.exc_info[1])] == []


@pytest.mark.parametrize("tool", ["slow", "slow_bug"])
def test_a_clients_cancellation_leaves_the_body_to_finish(tool):
    """`notifications/cancelled`: the SDK answers the client itself and
    cancels the handler's scope.  The body runs to its end regardless, the
    handler answers nobody — and what the body did still counts: a bug
    after the client gave up ends the conversation."""
    async def scenario():
        port = free_port()
        bodies = Bodies()
        async with serving(port, bodies.tools()) as (server, serve), client(server.url) as session:
            request_id = session._request_id           # the id the next request takes
            call = asyncio.create_task(session.call_tool(tool, {}))
            await bodies.began(tool).wait()
            await session.send_notification(types.ClientNotification(types.CancelledNotification(
                method="notifications/cancelled",
                params=types.CancelledNotificationParams(requestId=request_id))))
            with pytest.raises(McpError, match="Request cancelled"):
                await call
            assert tool not in bodies.finished and not serve.done()   # the body is still running
            bodies.release.set()
            if tool == "slow":
                later = await session.call_tool("echo", {"text": "on"})
                assert (text_of(later), later.isError) == ("echo on", False)
                assert "slow" in bodies.finished and not serve.done()
                # the body's answer, received by nobody: `given_up`, not `result`
                assert [(r["event"], r["data"]["tool"]) for r in stand_ins.records("tool")] == [
                    ("call", "slow"), ("given_up", "slow"), ("call", "echo"), ("result", "echo")]
                assert stand_ins.records("tool")[1]["data"]["text"] == "slow done"
            else:
                exn = await ended(serve)
                assert isinstance(exn, RuntimeError) and str(exn) == "late-bug"
                # the body produced no answer: `given_up` without a text
                records = stand_ins.records("tool")
                assert [(r["event"], r["data"]["tool"]) for r in records] == [
                    ("call", "slow_bug"), ("given_up", "slow_bug")]
                assert "text" not in records[1]["data"]
    run(scenario)


def test_codex_is_shown_the_schema_without_recursion_and_claude_code_the_assembled_one():
    """PLUGIN_SYSTEM §4: each server holds its tools with the schema its
    client is shown; the body, which checks a call against the assembled
    schema, is the same."""
    schema = plugin.load(["isabelle_theory_agent.std"]).edit_schema

    async def body(agent, arguments):
        return ""
    tool = Tool("edit", EDIT_DESCRIPTION, schema, body, False)
    for server_class, shown in ((Claude_Code_Server, schema), (Codex_Server, plugin.given_later_inlined(schema))):
        with _bind(0) as sock:
            server = server_class(stand_ins.ending(), sock, [tool], {})
        assert server._tools["edit"].input_schema == shown and server._tools["edit"].run is body


def test_an_empty_tool_list_and_an_unknown_tool():
    """What `launch_TAT` serves today: no tools, and the provisional refusal
    of a name no tool bears."""
    async def scenario():
        port = free_port()
        async with serving(port, []) as (server, _), client(server.url) as session:
            assert (await session.list_tools()).tools == []
            result = await session.call_tool("nothing", {})
            assert result.isError and text_of(result) == "unknown tool `nothing`"
    run(scenario)


def test_the_endpoint_answers_as_soon_as_it_accepts():
    """The session manager runs from `async with` on, not from `serve`: a
    request between the two is answered normally."""
    async def scenario():
        with _bind(free_port()) as sock:
            async with stand_ins.ending() as ending, Claude_Code_Server(ending, sock, [], {}) as server, \
                    client(server.url) as session:
                assert (await session.list_tools()).tools == []
    run(scenario)


def test_another_host_or_origin_is_refused_and_another_path_is_not_found():
    async def scenario():
        port = free_port()
        async with serving(port, []) as (server, _):
            async with httpx.AsyncClient() as http:
                body = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
                accept = {"Accept": "application/json, text/event-stream"}
                other_host = await http.post(
                    server.url, json=body, headers=accept | {"Host": f"localhost:{port}"})
                assert other_host.status_code == 421
                other_origin = await http.post(
                    server.url, json=body, headers=accept | {"Origin": "http://evil.example"})
                assert other_origin.status_code == 403
                elsewhere = await http.get(f"http://{HOST}:{port}/elsewhere")
                assert elsewhere.status_code == 404
    run(scenario)


def test_a_port_that_cannot_be_bound_is_a_startup_error():
    """`_bind` listens, so a second bind on its port is refused with the
    sentence — which, under `SO_REUSEADDR`, a bound socket that does not
    listen would let through."""
    port = free_port()
    with _bind(port):
        with pytest.raises(TAT_StartupError, match=f"TAT cannot serve on {HOST}:{port}: "):
            _bind(port)


def test_a_failed_startup_leaves_no_reader_on_the_socket(monkeypatch):
    """`startup` failing, or being cancelled at its one cancellation point
    (`create_server`'s final tick, with the loop's reader already
    registered and no server uvicorn could close): no reader of the loop
    is left on the socket it was lent; closing the socket is `served`'s."""
    real_startup = uvicorn.Server.startup
    reached_the_window = False

    async def failing(self, sockets=None):
        raise RuntimeError("startup failed")

    async def cancelled_at_the_tick(self, sockets=None):
        task = asyncio.current_task()
        assert task is not None
        asyncio.get_running_loop().call_soon(task.cancel)
        try:
            return await real_startup(self, sockets=sockets)
        except asyncio.CancelledError:
            nonlocal reached_the_window           # cancelled inside `create_server`,
            reached_the_window = self.servers == []   # past `_start_serving`
            raise

    async def enter():                                # a task of its own takes the cancellation
        with _bind(0) as sock:
            try:
                async with stand_ins.ending() as ending, TAT_Server(ending, sock, [], {}):
                    pass
            finally:                                  # no reader left on the descriptor
                assert not asyncio.get_running_loop().remove_reader(sock.fileno())

    async def scenario():
        for broken, raised in ((failing, RuntimeError), (cancelled_at_the_tick, asyncio.CancelledError)):
            monkeypatch.setattr(uvicorn.Server, "startup", broken)
            with pytest.raises(raised):
                await asyncio.create_task(enter())
        assert reached_the_window
    run(scenario)


# --- configure (CLIENT_HOOKS §2, §3, §5) -----------------------------------------

PACKAGE = Path(mcp_server.__file__).parent
RESOLVER = "<the real path of /etc/resolv.conf, when outside :minimal>"


def filled(text: str, placeholders: dict[str, str]) -> str:
    for placeholder, value in placeholders.items():
        text = text.replace(placeholder, value)
    return text


def as_the_shell_reads_it(value: Any, placeholders: dict[str, str]) -> Any:
    """A parsed file with its placeholders filled, keys included — a hook
    `command` as its `shlex` tokens, each filled, so that a quoted path
    compares as the shell reads it, however it was quoted."""
    if isinstance(value, dict):
        return {filled(key, placeholders): (
            [filled(token, placeholders) for token in shlex.split(item)] if key == "command"
            else as_the_shell_reads_it(item, placeholders)) for key, item in value.items()}
    if isinstance(value, list):
        return [as_the_shell_reads_it(item, placeholders) for item in value]
    return filled(value, placeholders) if isinstance(value, str) else value


def documented(block: list[str], placeholders: dict[str, str], loads: Callable[[str], Any] = json.loads
               ) -> Any:
    """The document's block, parsed first and its placeholders filled after,
    so that a value needing the format's escapes compares all the same."""
    return as_the_shell_reads_it(loads("\n".join(block)), placeholders)


def written(path: Path, loads: Callable[[str], Any] = json.loads) -> Any:
    return as_the_shell_reads_it(loads(path.read_text()), {})


@pytest.fixture
def working_directory(tmp_path: Path) -> Path:
    """Its path holds a space and DEL, which the TOML must escape
    (Isabelle's path syntax allows no `"` or `\\`)."""
    path = tmp_path / "work dir\x7f"
    path.mkdir()
    return path


def configured(server_class: type[TAT_Server], working_directory: Path, monkeypatch) -> TAT_Server:
    """`configure` under an interpreter whose path holds a space and both
    quotes, on a socket closed at once: the files alone are under test."""
    monkeypatch.setattr(sys, "executable", '/opt/my "python\'s"/bin/python3')
    with _bind(0) as sock:
        server = server_class(stand_ins.ending(), sock, [], {})
        server.configure(working_directory)
    return server


def test_configure_writes_claude_codes_files_and_the_scripts(working_directory, monkeypatch):
    """The two files of CLIENT_HOOKS §2 as the document shows them, the
    placeholders filled; the two scripts into `.tat/`, where the log and a
    file of the user's are left alone and a stale script is overwritten;
    the `configured` record; a later launch rewrites the files and leaves
    the agents' own alone."""
    (working_directory / DOT_TAT / "log").mkdir(parents=True)
    (working_directory / DOT_TAT / "mine").write_text("the user's")
    (working_directory / DOT_TAT / "hook.py").write_text("stale")
    server = configured(Claude_Code_Server, working_directory, monkeypatch)
    agents, scripts = working_directory / AGENTS, working_directory / DOT_TAT
    placeholders = {"<port>": str(server.port), "<python>": sys.executable,
                    "<working directory>": str(working_directory)}
    mcp_json, settings = fenced_blocks(DOCS / "CLIENT_HOOKS.md", "2.")
    assert written(agents / ".mcp.json") == documented(mcp_json, placeholders)
    assert written(agents / ".claude" / "settings.json") == documented(settings, placeholders)
    # the command as written: `shlex`'s quoting of each token
    [command] = {hook["command"] for group in json.loads((agents / ".claude" / "settings.json").read_text())
                 ["hooks"].values() for entry in group for hook in entry["hooks"] if "guard" in hook["command"]}
    assert command == f"""'/opt/my "python'"'"'s"/bin/python3' -I '{scripts / 'guard.py'}'"""
    for script in ("hook.py", "guard.py"):
        assert (scripts / script).read_bytes() == (PACKAGE / script).read_bytes()
    assert sorted(p.name for p in scripts.iterdir()) == ["guard.py", "hook.py", "log", "mine"]
    assert (scripts / "mine").read_text() == "the user's"
    [record] = stand_ins.records("conversation")
    assert record["event"] == "configured" and record["data"] == {"files": [
        f"{AGENTS}/.mcp.json", f"{AGENTS}/.claude/settings.json", f"{DOT_TAT}/hook.py", f"{DOT_TAT}/guard.py"]}
    (agents / "notes.md").write_text("an agent's")
    (agents / ".mcp.json").write_text("{}")
    server.configure(working_directory)
    assert (agents / "notes.md").read_text() == "an agent's"
    assert written(agents / ".mcp.json") == documented(mcp_json, placeholders)


def test_configure_replaces_what_stands_at_its_names_and_writes_through_nothing(
        tmp_path, working_directory, monkeypatch):
    """Whatever an agent left at one of TAT's names in the agent directory
    — a link to a file or a directory of the user's, a file where a
    directory goes — is replaced, and what a link pointed to is untouched
    (CLIENT_HOOKS.md); what stands at other names stays."""
    users = tmp_path / "users"
    (users / ".claude").mkdir(parents=True)
    (users / ".claude" / "settings.json").write_text("the user's settings")
    (users / ".claude.json").write_text("the user's state")
    (users / ".codex").mkdir()
    (users / ".codex" / "config.toml").write_text("the user's config")
    agents = working_directory / AGENTS
    agents.mkdir()
    (agents / ".mcp.json").symlink_to(users / ".claude.json")
    (agents / ".claude").symlink_to(users / ".claude")
    (agents / ".codex").write_text("an agent's note")
    (agents / "skills").mkdir()
    for server_class in (Claude_Code_Server, Codex_Server):
        configured(server_class, working_directory, monkeypatch)
    assert (users / ".claude" / "settings.json").read_text() == "the user's settings"
    assert (users / ".claude.json").read_text() == "the user's state"
    for name in (".mcp.json", ".claude", ".claude/settings.json", ".codex", ".codex/config.toml"):
        assert not (agents / name).is_symlink(), name
    assert (agents / ".claude").is_dir() and (agents / ".codex").is_dir() and (agents / "skills").is_dir()
    assert json.loads((agents / ".mcp.json").read_text())["mcpServers"]["TAT"]["type"] == "http"
    # a link where a directory goes, and the replacement below a real directory too
    shutil.rmtree(agents / ".codex")
    (agents / ".codex").symlink_to(users / ".codex")
    (agents / ".claude" / "settings.json").unlink()
    (agents / ".claude" / "settings.json").symlink_to(users / ".claude" / "settings.json")
    for server_class in (Claude_Code_Server, Codex_Server):
        configured(server_class, working_directory, monkeypatch)
    assert (users / ".claude" / "settings.json").read_text() == "the user's settings"
    assert (users / ".codex" / "config.toml").read_text() == "the user's config"
    assert sorted(p.name for p in (users / ".codex").iterdir()) == ["config.toml"]
    for name in (".claude/settings.json", ".codex"):
        assert not (agents / name).is_symlink(), name


@pytest.mark.parametrize("planted, reason", [(AGENTS, "File exists"), (f"{AGENTS}/.mcp.json/", "Is a directory")],
                         ids=["a file at the agent directory", "a directory at a file's name"])
def test_a_file_configure_cannot_write_is_a_startup_error(working_directory, monkeypatch, planted, reason):
    """MODULE_STRUCTURE §4.6: the agent directory's name taken by a file —
    nothing below it can be made; a directory at a file's name stays."""
    if planted.endswith("/"):
        (working_directory / planted).mkdir(parents=True)
    else:
        (working_directory / planted).write_text("a file")
    with pytest.raises(TAT_StartupError) as refused:
        configured(Claude_Code_Server, working_directory, monkeypatch)
    assert str(refused.value) == f"TAT cannot write {working_directory / AGENTS / '.mcp.json'}: {reason}"
    assert stand_ins.records("conversation") == []


@pytest.mark.parametrize("resolver_outside_minimal", [True, False])
def test_configure_writes_codexs_files(tmp_path, working_directory, monkeypatch, resolver_outside_minimal):
    """The two files of CLIENT_HOOKS §3 as the document shows them, on a
    working directory without `.tat/` yet; the profile's read entry for the
    resolver's real path when that lies outside `:minimal` — a path with
    `"` and `\\` in it, escaped — no such line otherwise (§5)."""
    resolv_conf = tmp_path / "etc" / "resolv.conf"
    resolv_conf.parent.mkdir()
    if resolver_outside_minimal:
        target = tmp_path / 'run "systemd"' / 'back\\slash' / "stub-resolv.conf"
        target.parent.mkdir(parents=True)
        target.write_text("nameserver 127.0.0.53\n")
    else:
        target = Path("/etc/hosts")
    resolv_conf.symlink_to(target)
    monkeypatch.setattr(mcp_server, "RESOLV_CONF", str(resolv_conf))
    server = configured(Codex_Server, working_directory, monkeypatch)
    codex = working_directory / AGENTS / ".codex"
    placeholders = {"<port>": str(server.port), "<python>": sys.executable,
                    "<working directory>": str(working_directory), RESOLVER: str(target.resolve())}
    config, hooks, _ = fenced_blocks(DOCS / "CLIENT_HOOKS.md", "3.")
    expected = [line for line in config if resolver_outside_minimal or RESOLVER not in line]
    assert written(codex / "config.toml", tomllib.loads) == documented(expected, placeholders, tomllib.loads)
    assert written(codex / "hooks.json") == documented(hooks, placeholders)
    for script in ("hook.py", "guard.py"):
        assert (working_directory / DOT_TAT / script).read_bytes() == (PACKAGE / script).read_bytes()
    [record] = stand_ins.records("conversation")
    assert record["data"]["files"][:2] == [f"{AGENTS}/.codex/config.toml", f"{AGENTS}/.codex/hooks.json"]


def test_the_launch_arguments_are_the_documented_ones(working_directory):
    """CLIENT_HOOKS §3's third block, one argument per line, the agent
    directory's canonical path filled in — Codex's flag and the project
    trust, whose TOML names that path, which `agent_directory` gives with
    symbolic links resolved; Claude Code takes `--strict-mcp-config` with
    the agent directory's `.mcp.json` as its `--mcp-config` (§2)."""
    directory = agent_directory(working_directory)
    link = working_directory.parent / "link"
    link.symlink_to(working_directory)
    assert directory == (working_directory / AGENTS).resolve() == agent_directory(link)
    _, _, block = fenced_blocks(DOCS / "CLIENT_HOOKS.md", "3.")
    flag, option, trust = block
    given_flag, given_option, given_trust = Codex_Server.launch_arguments(directory)
    assert (given_flag, given_option) == (flag, option)
    assert tomllib.loads(given_trust) == documented([trust], {"<agent directory>": str(directory)}, tomllib.loads) \
        == {"projects": {str(directory): {"trust_level": "trusted"}}}
    assert Claude_Code_Server.launch_arguments(directory) == [
        "--strict-mcp-config", "--mcp-config", str(directory / ".mcp.json")]


def test_the_resolvers_entry_is_its_real_path_outside_minimal(tmp_path):
    """The real path, never the link; none for a file under a `:minimal`
    directory, the link's target or the file itself; a directory that only
    begins like one is not it."""
    outside = tmp_path / "stub-resolv.conf"
    outside.write_text("")
    link = tmp_path / "resolv.conf"
    link.symlink_to(outside)
    assert resolver_entry(str(link)) == str(outside.resolve())
    assert resolver_entry(str(outside)) == str(outside.resolve())
    into_etc = tmp_path / "into_etc"
    into_etc.symlink_to("/etc/hosts")
    assert resolver_entry(str(into_etc)) is None
    assert resolver_entry("/usr/bin/env") is None
    assert resolver_entry("/etcetera/resolv.conf") == "/etcetera/resolv.conf"


def test_a_toml_string_escapes_what_toml_cannot_hold_raw():
    """`"`, `\\`, every control character and DEL (TOML 1.0); what is
    written reads back as the value."""
    value = 'a "quoted" \\ path\twith\nnewline, \x01 and \x7f, and ü'
    string = toml_string(value)
    assert all(ord(c) >= 0x20 and ord(c) != 0x7F for c in string)
    assert string == '"a \\"quoted\\" \\\\ path\\u0009with\\u000Anewline, \\u0001 and \\u007F, and ü"'
    assert tomllib.loads(f"k = {string}")["k"] == value


# --- the messages on a tool result (CONSTRUCT_INTERACTION §3.4, §5; MODULE_STRUCTURE §4.6) ----

def test_a_message_rides_on_its_recipients_next_result_between_the_body_and_the_trailer():
    """CONSTRUCT_INTERACTION §5: every tool result is the body's text, then
    the caller's undelivered messages, then the trailer the body asked
    for, each separated from the one before by one blank line — whatever
    the tool, a rendered `TAT_Error` included; a result with neither is
    the body's text as it is.  The trailer is made once the mailbox is
    taken.  `message_posted`, `message_delivered` and `tool.result` say
    what went where (LOGGING.md §4)."""
    mailbox_at_the_trailer = []

    async def trailed(agent, arguments):
        def trailer():
            mailbox_at_the_trailer.append(list(agent.mailbox))
            return "the trailer"
        return With_Trailer("the body\n", trailer)

    async def scenario():
        bodies = Bodies()
        tools = [*bodies.tools(), Tool("trailed", "the trailed tool", SCHEMA, trailed, read_only=True)]
        async with serving(free_port(), tools) as (server, serve), client(server.url) as session:
            assert text_of(await session.call_tool("echo", {"text": "hi"})) == "echo hi"   # nothing waits: as it is
            main, log = server.agents["main"], server.ending.log
            post(log, Message(main, "first message", interrupts=False))
            a_run = type("A_Run", (), {"dropped_for": lambda self, message: None,       # a source that stands
                                       "__repr__": lambda self: "a run"})()
            post(log, Message(main, "second message\nits second line", interrupts=True,
                              subject=a_run))                                     # type: ignore[arg-type]
            result = await session.call_tool("trailed", {})
            assert text_of(result).split("\n") == [
                "the body", "", "first message", "", "second message", "its second line", "", "the trailer"]
            assert mailbox_at_the_trailer == [[]] and main.mailbox == []
            assert text_of(await session.call_tool("trailed", {})) == "the body\n\nthe trailer"
            post(log, Message(main, "third message", interrupts=False))
            refused = await session.call_tool("refused", {})
            error = str(NodeNotFound("theory_X", []))
            assert refused.isError and text_of(refused) == error + "\n\nthird message"
            assert text_of(await session.call_tool("echo", {"text": "on"})) == "echo on" and not serve.done()
            post(log, Message(main, "a question", interrupts=True, question=object()))   # type: ignore[arg-type]
            unknown = await session.call_tool("no_such_tool", {})      # whatever the tool
            assert unknown.isError and text_of(unknown) == "unknown tool `no_such_tool`\n\na question"
            results = [r["data"] for r in stand_ins.records("tool") if r["event"] == "result"][:5]
            assert [(r["text"], r["messages"], r.get("trailer")) for r in results] == [
                ("echo hi", [], None),
                ("the body\n", ["first message", "second message\nits second line"], "the trailer"),
                ("the body\n", [], "the trailer"),
                (error, ["third message"], None),
                ("echo on", [], None)]
            job = stand_ins.records("job")
            assert (job[-2]["event"], job[-2]["data"]["kind"]) == ("message_posted", "question")
            assert [(r["event"], r["data"]) for r in job[:-2]] == [
                ("message_posted", {"recipient": "main", "kind": "notification", "interrupts": False,
                                    "text": "first message"}),
                ("message_posted", {"recipient": "main", "kind": "notification", "source": "a run",
                                    "interrupts": True, "text": "second message\nits second line"}),
                ("message_delivered", {"recipient": "main"}), ("message_delivered", {"recipient": "main"}),
                ("message_posted", {"recipient": "main", "kind": "notification", "interrupts": False,
                                    "text": "third message"}),
                ("message_delivered", {"recipient": "main"})]
    run(scenario)


def test_a_calls_strings_are_repaired_and_checked_inside_its_body():
    """A tool `mcp._tool` builds, over the wire: the input layer and the
    check run inside the body (MODULE_STRUCTURE §4.6), so a string
    Isabelle reads as source text reaches the body as that text, the
    `call` record holds the arguments as received, and a string left
    holding a markup character is refused as any `TAT_Error` is — its
    `result` record carrying the class, a waiting message delivered
    with it."""
    async def echo(agent, arguments):
        return "echo " + arguments["text"]
    framed, held = "\x05\x06input\x05hi\x05\x06\x05", "\x05\x06b\x05hi\x05\x06\x05"

    async def scenario():
        tool = mcp._tool("echo", "the echo tool", {"type": "object", "properties": {"text": {"type": "string"}},
                                                   "required": ["text"], "additionalProperties": False},
                         echo, read_only=True)
        async with serving(free_port(), [tool]) as (server, serve), client(server.url) as session:
            assert text_of(await session.call_tool("echo", {"text": framed})) == "echo hi"
            post(server.ending.log, Message(server.agents["main"], "a message", interrupts=False))
            refused = await session.call_tool("echo", {"text": held})
            assert refused.isError and text_of(refused) == (
                "The argument `text` cannot hold Isabelle's internal markup (U+0005 or U+0006).\n\na message")
            records = stand_ins.records("tool")
            assert [r["data"]["arguments"] for r in records if r["event"] == "call"] == [{"text": framed}, {"text": held}]
            assert [r["data"].get("class") for r in records if r["event"] == "result"] == [None, "InvalidField"]
    run(scenario)


def test_a_call_given_up_and_the_endings_line_leave_the_mailbox_as_it_was():
    """CONSTRUCT_INTERACTION §3.4: the handler takes the mailbox only past
    its checkpoint, so a call its client gave up leaves the messages for
    the next — `given_up` names what would have gone with it — and the
    ending's fixed line carries none."""
    async def scenario():
        bodies = Bodies()
        async with serving(free_port(), bodies.tools()) as (server, serve):
            accepting = hold_accepting(server)           # before anything is awaited: the main loop is not yet run
            async with client(server.url) as session:
                await given_up_then_ended(bodies, server, serve, session, accepting)

    async def given_up_then_ended(bodies, server, serve, session, accepting):
        await session.call_tool("echo", {"text": "hi"})
        main, log = server.agents["main"], server.ending.log
        request_id = session._request_id             # the id the next request takes
        call = asyncio.create_task(session.call_tool("slow", {}))
        await bodies.began("slow").wait()
        post(log, Message(main, "waiting", interrupts=False))
        await session.send_notification(types.ClientNotification(types.CancelledNotification(
            method="notifications/cancelled",
            params=types.CancelledNotificationParams(requestId=request_id))))
        with pytest.raises(McpError, match="Request cancelled"):
            await call
        bodies.release.set()
        assert text_of(await session.call_tool("echo", {"text": "on"})) == "echo on\n\nwaiting"
        [given_up] = [r["data"] for r in stand_ins.records("tool") if r["event"] == "given_up"]
        assert (given_up["text"], given_up["messages"]) == ("slow done", ["waiting"])
        assert [r["event"] for r in stand_ins.records("job")] == ["message_posted", "message_delivered"]

        post(log, Message(main, "too late", interrupts=False))
        server.ending.end(RuntimeError("ended"))
        stopped_line = await session.call_tool("echo", {"text": "after"})
        assert (text_of(stopped_line), stopped_line.isError) == (INTERNAL, True)
        assert [message.text for message in main.mailbox] == ["too late"]
        accepting.set()
        assert isinstance(await ended(serve), RuntimeError)
    run(scenario)


def test_posting_wakes_the_recipient():
    """CONSTRUCT_INTERACTION §4: a change to an agent's mailbox wakes whoever
    sleeps on the agent."""
    async def scenario():
        agent = Agent("main", True)
        post(stand_ins.log(), Message(agent, "before the sleeper began", interrupts=False))
        sleeper = asyncio.create_task(agent.sleep_until(lambda: len(agent.mailbox) == 2))
        await asyncio.sleep(0.05)
        assert not sleeper.done()
        post(stand_ins.log(), Message(agent, "a message", interrupts=True))
        await asyncio.wait_for(sleeper, 1)
        await asyncio.wait_for(agent.sleep_until(lambda: True), 1)      # what holds already: no sleep
        assert [message.text for message in agent.mailbox] == ["before the sleeper began", "a message"]
    run(scenario)


def test_an_empty_part_of_a_result_is_left_out():
    """CONSTRUCT_INTERACTION §5: the parts are separated by one blank line —
    a body that says nothing, as `check_construct`'s, opens with no blank
    line, and an empty message or trailer adds none."""
    composed = mcp_server._composed
    assert composed("", ["a message"], "the trailer") == "a message\n\nthe trailer"
    assert composed("", [], "the trailer") == "the trailer"
    assert composed("the body\n", ["", "a message"], "") == "the body\n\na message"
    assert composed("the body\n", [], None) == "the body\n" and composed("", [], None) == ""
    assert composed("the body", ["a message\n"], "the trailer") == "the body\n\na message\n\nthe trailer"


def raising_trailer():
    raise RuntimeError("trailer-bug")


@pytest.mark.parametrize("trailer, exception, text", [
    (lambda: 7, TAT_InternalError, "a trailer is a int"), (raising_trailer, RuntimeError, "trailer-bug")],
    ids=["no text", "raises"])
def test_a_trailer_that_is_no_text_or_raises_is_a_bug_that_ends_the_conversation(trailer, exception, text):
    """MODULE_STRUCTURE §4.6: the boundary renders a text and nothing else —
    a trailer that is none, or that raises, is a bug like a body's: the
    call is answered the ending's line and the conversation ends."""
    async def wrong(agent, arguments):
        return With_Trailer("the body", trailer)

    async def scenario():
        tool = Tool("wrong", "the wrong tool", SCHEMA, wrong, read_only=True)
        async with serving(free_port(), [tool]) as (server, serve):
            accepting = hold_accepting(server)
            async with client(server.url) as session:
                result = await session.call_tool("wrong", {})
                assert (text_of(result), result.isError) == (INTERNAL, True)
                accepting.set()
                exn = await ended(serve)
                assert isinstance(exn, exception) and text in str(exn)
    run(scenario)
