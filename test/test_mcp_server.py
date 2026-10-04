"""The MCP server (MODULE_STRUCTURE §4.6): the endpoint and its transport
security, the tool boundary (EXCEPTIONS.md §1), the conversation's
ending (RENDER_BASELINES §4), against the `mcp` SDK's own Streamable
HTTP client.  Run: python -m pytest test/test_mcp_server.py
"""

import asyncio
import json
import shlex
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
from isabelle_theory_agent import mcp_server, toplevel
from isabelle_theory_agent.exceptions import (
    NodeNotFound, TAT_DisasterError, TAT_InternalError, TAT_StartupError)
from isabelle_theory_agent.mcp_server import (
    AGENTS, CLIENTS, HOST, ON_COMPACTION, SCRIPTS, Claude_Code_Server, Codex_Server, TAT_Server,
    Tool, resolver_entry, stopped, stopped_for, toml_string, unknown_client)
from isabelle_theory_agent.model import CannotUseWorkingDirectory
from test_toplevel import Recorder, cancelled_by_the_host


def no_briefing() -> str:
    return ""

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

    async def echo(self, arguments):
        return "echo " + arguments["text"]

    async def strict(self, arguments):                # its schema requires `field`
        return "got " + repr(sorted(arguments))

    async def slow(self, arguments):
        self.began("slow").set()
        await self.release.wait()
        self.finished.add("slow")
        return "slow done"

    async def slow_bug(self, arguments):              # a bug after the client gave up
        self.began("slow_bug").set()
        await self.release.wait()
        self.finished.add("slow_bug")
        raise RuntimeError("late-bug")

    async def stubborn(self, arguments):              # completes after ignoring the ending's cancellation
        self.began("stubborn").set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            await self.release.wait()
        self.finished.add("stubborn")
        return "stubborn done"

    async def refused(self, arguments):
        raise NodeNotFound("theory_X", [])

    async def bug(self, arguments):
        raise RuntimeError("tat-bug")

    async def disaster(self, arguments):
        raise TAT_DisasterError("disk full")

    async def wire_dead(self, arguments):
        raise ConnectionResetError("peer closed connection")

    async def escapes(self, arguments):               # lets a cancellation escape
        raise asyncio.CancelledError()

    async def not_text(self, arguments):              # the boundary's own failure
        return {"not": "text"}                        # type: ignore[return-value]

    def plain(self, arguments):                       # a malformed tool: not a coroutine
        return "plain"

    def tools(self) -> list[Tool]:
        names = ("echo", "strict", "slow", "slow_bug", "stubborn", "refused", "bug",
                 "disaster", "wire_dead", "escapes", "not_text", "plain")
        return [Tool(name, f"the {name} tool", STRICT_SCHEMA if name == "strict" else SCHEMA,
                     getattr(self, name), read_only=name == "echo") for name in names]


@asynccontextmanager
async def serving(port: int, tools: list[Tool], on_compaction=no_briefing):
    """A server listening and serving in a task, on an ending object of its
    own; yields the server and the serving task, which raises what ended
    the conversation (`ended`)."""
    async with stand_ins.ending() as ending, TAT_Server(ending, port, tools, on_compaction) as server:
        serve = asyncio.create_task(server.serve())
        try:
            yield server, serve
        finally:
            if not serve.done():
                serve.cancel()
            await asyncio.wait({serve})
            if not serve.cancelled():
                serve.exception()                     # retrieved: the tests inspect it themselves


async def launched(tools: list[Tool], block: Callable[[TAT_Server], Awaitable[Any]]
                   ) -> tuple[TAT_Server, asyncio.Task]:
    """`launch_TAT`'s shape: an ending object and a server entered in a task
    of their own, running `block` inside them — the task the RPC host
    cancels; returned once the server listens."""
    ending = stand_ins.ending()
    server = TAT_Server(ending, free_port(), tools, no_briefing)
    listening = asyncio.Event()

    async def launch_TAT():
        async with ending, server:
            listening.set()
            await block(server)
    task = asyncio.create_task(launch_TAT())
    await listening.wait()
    return server, task


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
    unless another door was reached first (MODULE_STRUCTURE §4.6): `serve`
    raises what ended the conversation and stops accepting, and the call
    in flight is still answered."""
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


def test_the_hosts_cancellation_enters_the_ending_and_is_raised():
    """The RPC host cancelling `launch_TAT` (the connection gone): a call in
    flight is answered `Isabelle is gone`, and `serve` raises the
    cancellation for `launch_TAT` to pass on."""
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
        ending_record, ended_record = stand_ins.records("conversation")
        assert [r["event"] for r in (call_record, ending_record, while_ending, ended_record)] == [
            "call", "ending", "while_ending", "ended"]
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
                                   cast(Any, Recorder())) as (forest, _, server):
            forest.conversation.ending.spawn(reader(forest))
            serve = asyncio.create_task(server.serve())
            await asyncio.sleep(0)                    # the reader and `serve` waiting
            await cancelled_by_the_host(serve)
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


def test_the_endpoint_answers_as_soon_as_it_listens():
    """The session manager runs from `async with` on, not from `serve`: a
    request between the two is answered normally."""
    async def scenario():
        port = free_port()
        async with stand_ins.ending() as ending, TAT_Server(ending, port, [], no_briefing) as server, \
                client(server.url) as session:
            assert (await session.list_tools()).tools == []
    run(scenario)


def test_on_compaction_answers_the_briefing_in_the_clients_shape():
    """CLIENT_HOOKS.md's table, and MODULE_STRUCTURE §4.6's refusals: an
    unknown client before the closure runs, the transport check as for
    `/mcp` without the content type, only POST."""
    briefing = "session_A\n- theory_X (not evaluated)\n"
    calls = []

    def on_compaction():
        calls.append(1)
        return briefing

    async def scenario():
        port = free_port()
        async with serving(port, [], on_compaction) as (server, _), httpx.AsyncClient() as http:
            url = f"http://{HOST}:{port}{ON_COMPACTION}"
            for name in ("claude-code", "codex", "gemini-cli"):
                r = await http.post(url, params={"client": name})
                assert r.status_code == 200 and r.json() == {"hookSpecificOutput": {
                    "hookEventName": "SessionStart", "additionalContext": briefing}}
            r = await http.post(url, params={"client": "cursor"})
            assert r.status_code == 200 and r.json() == {"additional_context": briefing}
            for params in ({"client": "opencode"}, {}):
                r = await http.post(url, params=params)
                assert r.status_code == 200 and r.text == briefing
                assert r.headers["content-type"].startswith("text/plain")
            assert len(calls) == 6 and set(CLIENTS) == {
                "claude-code", "codex", "gemini-cli", "cursor", "opencode"}
            r = await http.post(url, params={"client": "emacs"})
            [refusal] = fenced_lines(DOCS / "CLIENT_HOOKS.md", "An unknown client")
            assert r.status_code == 400 and r.text == unknown_client("emacs") == refusal
            assert len(calls) == 6                                 # refused before the closure
            assert (await http.get(url)).status_code == 405
            other_host = await http.post(url, headers={"Host": f"localhost:{port}"})
            assert other_host.status_code == 421
            other_origin = await http.post(url, headers={"Origin": "http://evil.example"})
            assert other_origin.status_code == 403
            assert len(calls) == 6
    run(scenario)


def test_a_briefing_that_raises_ends_the_conversation_with_an_empty_500():
    def broken():
        raise RuntimeError("render-bug")

    async def scenario():
        port = free_port()
        async with serving(port, [], broken) as (server, serve), httpx.AsyncClient() as http:
            r = await http.post(f"http://{HOST}:{port}{ON_COMPACTION}", params={"client": "codex"})
            assert r.status_code == 500 and r.content == b""
            assert isinstance(await ended(serve), RuntimeError)
    run(scenario)


def test_on_compaction_answers_an_empty_503_while_the_conversation_is_ending():
    """The ending touches no forest: a hook arriving while the server
    still accepts gets nothing to brief, and the closure is not run."""
    calls = []

    def on_compaction():
        calls.append(1)
        return ""

    async def scenario():
        port = free_port()
        async with serving(port, [], on_compaction) as (server, serve), httpx.AsyncClient() as http:
            accepting = hold_accepting(server)
            server.ending.end(RuntimeError("ended"))
            r = await http.post(f"http://{HOST}:{port}{ON_COMPACTION}", params={"client": "codex"})
            assert r.status_code == 503 and r.content == b"" and calls == []
            accepting.set()
            assert isinstance(await ended(serve), RuntimeError)
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
    async def scenario():
        port = free_port()
        async with serving(port, []):
            with pytest.raises(TAT_StartupError, match=f"TAT cannot serve on {HOST}:{port}: "):
                async with stand_ins.ending() as ending, TAT_Server(ending, port, [], no_briefing):
                    pass
    run(scenario)


def test_a_failure_after_the_bind_releases_the_port(monkeypatch):
    """`startup` failing, or being cancelled at its one cancellation point
    (`create_server`'s final tick, with the loop's reader already
    registered and no server uvicorn could close): the port is free again
    and the next conversation on it is served."""
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

    async def enter(port):                            # a task of its own takes the cancellation
        async with stand_ins.ending() as ending, TAT_Server(ending, port, [], no_briefing):
            pass

    async def scenario():
        port = free_port()
        for broken, raised in ((failing, RuntimeError), (cancelled_at_the_tick, asyncio.CancelledError)):
            monkeypatch.setattr(uvicorn.Server, "startup", broken)
            with pytest.raises(raised):
                await asyncio.create_task(enter(port))
            monkeypatch.setattr(uvicorn.Server, "startup", real_startup)
            async with stand_ins.ending() as ending, TAT_Server(ending, port, [], no_briefing) as again, \
                    client(again.url) as session:
                assert (await session.list_tools()).tools == []
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
    """A hook file's JSON value with its placeholders filled — a `command`
    as its `shlex` tokens, each filled, so that a quoted path compares as
    the shell reads it, however it was quoted."""
    if isinstance(value, dict):
        return {key: ([filled(token, placeholders) for token in shlex.split(item)] if key == "command"
                      else as_the_shell_reads_it(item, placeholders)) for key, item in value.items()}
    if isinstance(value, list):
        return [as_the_shell_reads_it(item, placeholders) for item in value]
    return filled(value, placeholders) if isinstance(value, str) else value


def documented_json(block: list[str], placeholders: dict[str, str]) -> Any:
    return as_the_shell_reads_it(json.loads("\n".join(block)), placeholders)


def written_json(path: Path) -> Any:
    return as_the_shell_reads_it(json.loads(path.read_text()), {})


def configured(server_class: type[TAT_Server], tmp_path: Path) -> tuple[TAT_Server, Path]:
    """`configure` as `served()` reaches it: `.tat/` holds the log already
    (and here a file of the user's and a stale script), the agent
    directory does not exist yet."""
    working_directory = tmp_path / "work dir"
    (working_directory / SCRIPTS / "log").mkdir(parents=True)
    (working_directory / SCRIPTS / "mine").write_text("the user's")
    (working_directory / SCRIPTS / "hook.py").write_text("stale")
    server = server_class(stand_ins.ending(), free_port(), [], no_briefing)
    server.configure(working_directory)
    return server, working_directory


def test_configure_writes_claude_codes_files_and_the_scripts(tmp_path, monkeypatch):
    """The two files of CLIENT_HOOKS §2 as the document shows them, the
    placeholders filled — the interpreter's path with a space and a quote
    in it, the working directory's with a space; the two scripts copied
    into `.tat/`, where nothing else is touched; the `configured` record."""
    monkeypatch.setattr(sys, "executable", "/opt/my python's/bin/python3")
    server, working_directory = configured(Claude_Code_Server, tmp_path)
    agents = working_directory / AGENTS
    placeholders = {"<port>": str(server._port), "<python>": sys.executable,
                    "<working directory>": str(working_directory)}
    mcp_json, settings = fenced_blocks(DOCS / "CLIENT_HOOKS.md", "2.")
    assert written_json(agents / ".mcp.json") == documented_json(mcp_json, placeholders)
    assert written_json(agents / ".claude" / "settings.json") == documented_json(settings, placeholders)
    # the command as written: the quoting is `shlex.quote`'s
    [command] = {hook["command"] for group in json.loads((agents / ".claude" / "settings.json").read_text())
                 ["hooks"].values() for entry in group for hook in entry["hooks"] if "guard" in hook["command"]}
    assert command == f"'/opt/my python'\"'\"'s/bin/python3' -I '{working_directory / SCRIPTS / 'guard.py'}'"
    for script in ("hook.py", "guard.py"):
        assert (working_directory / SCRIPTS / script).read_bytes() == (PACKAGE / script).read_bytes()
    assert sorted(p.name for p in (working_directory / SCRIPTS).iterdir()) == ["guard.py", "hook.py", "log", "mine"]
    assert (working_directory / SCRIPTS / "mine").read_text() == "the user's"
    [record] = stand_ins.records("conversation")
    assert record["event"] == "configured" and record["data"] == {"files": [
        f"{AGENTS}/.mcp.json", f"{AGENTS}/.claude/settings.json", f"{SCRIPTS}/hook.py", f"{SCRIPTS}/guard.py"]}
    # a later launch rewrites the files and leaves the agents' own alone
    (agents / "notes.md").write_text("an agent's")
    server.configure(working_directory)
    assert (agents / "notes.md").read_text() == "an agent's"
    assert written_json(agents / ".mcp.json") == documented_json(mcp_json, placeholders)


@pytest.mark.parametrize("resolver_outside_minimal", [True, False])
def test_configure_writes_codexs_files(tmp_path, monkeypatch, resolver_outside_minimal):
    """The two files of CLIENT_HOOKS §3 as the document shows them; the
    profile's read entry for the resolver's real path when that lies
    outside `:minimal`, no such line otherwise (§5)."""
    resolv_conf = tmp_path / "etc" / "resolv.conf"
    resolv_conf.parent.mkdir()
    if resolver_outside_minimal:
        target = tmp_path / "run" / "systemd" / "resolve" / "stub-resolv.conf"
        target.parent.mkdir(parents=True)
        target.write_text("nameserver 127.0.0.53\n")
    else:
        target = Path("/etc/hosts")
    resolv_conf.symlink_to(target)
    monkeypatch.setattr(mcp_server, "RESOLV_CONF", str(resolv_conf))
    server, working_directory = configured(Codex_Server, tmp_path)
    codex = working_directory / AGENTS / ".codex"
    placeholders = {"<port>": str(server._port), "<python>": sys.executable,
                    "<working directory>": str(working_directory), RESOLVER: str(target.resolve())}
    config, hooks = fenced_blocks(DOCS / "CLIENT_HOOKS.md", "3.")
    expected = [line for line in config if resolver_outside_minimal or RESOLVER not in line]
    assert tomllib.loads((codex / "config.toml").read_text()) == tomllib.loads(
        filled("\n".join(expected), placeholders))
    assert written_json(codex / "hooks.json") == documented_json(hooks, placeholders)
    [record] = stand_ins.records("conversation")
    assert record["data"]["files"][:2] == [f"{AGENTS}/.codex/config.toml", f"{AGENTS}/.codex/hooks.json"]


def test_the_resolvers_entry_is_its_real_path_outside_minimal(tmp_path):
    """The real path, never the link; none for a file under a `:minimal`
    directory, the link's target or the file itself."""
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


def test_a_toml_string_escapes_what_toml_cannot_hold_raw():
    """`"`, `\\`, every control character and DEL (TOML 1.0); what is
    written reads back as the value."""
    value = 'a "quoted" \\ path\twith\nnewline, \x01 and \x7f, and ü'
    string = toml_string(value)
    assert all(ord(c) >= 0x20 and ord(c) != 0x7F for c in string)
    assert string == '"a \\"quoted\\" \\\\ path\\u0009with\\u000Anewline, \\u0001 and \\u007F, and ü"'
    assert tomllib.loads(f"k = {string}")["k"] == value
