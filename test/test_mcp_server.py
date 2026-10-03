"""The MCP server (MODULE_STRUCTURE §4.6): the endpoint and its transport
security, the tool boundary (EXCEPTIONS.md §1), the conversation's
ending (RENDER_BASELINES §4), against the `mcp` SDK's own Streamable
HTTP client.  Run: python -m pytest test/test_mcp_server.py
"""

import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest
import uvicorn
from mcp import types
from mcp.shared.exceptions import McpError

import stand_ins
from baselines import DOCS, fenced_lines
from harness import client, free_port, text_of
from isabelle_theory_agent.exceptions import (
    NodeNotFound, TAT_DisasterError, TAT_InternalError, TAT_StartupError)
from isabelle_theory_agent.mcp_server import (
    CLIENTS, HOST, ON_COMPACTION, TAT_Server, Tool, stopped, unknown_client)


def no_briefing() -> str:
    return ""

# The six server lines, in document order; a seventh, a missing one or a
# reordering fails here, an edited one fails the assertions below.
INTERNAL, UNSAVED, GONE, NO_TRANSCRIPT, NOT_SANDBOXED, NOT_CONNECTED = fenced_lines(
    DOCS / "RENDER_BASELINES.md", "4.")

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
                try:                                  # it waits for `stubborn`'s call
                    done, _ = await asyncio.wait({serve}, timeout=0.5)
                    assert not done
                finally:
                    bodies.release.set()
                stubborn = await kept
                assert (text_of(stubborn), stubborn.isError) == ("stubborn done", False)
                exn = await ended(serve)
                assert isinstance(exn, RuntimeError) and str(exn) == "tat-bug"
                # The records (LOGGING.md §4): a call then its result, a
                # `TAT_Error` with its class; the three calls answered the
                # ending's line, `while_ending`, written after `ending`; a
                # call arriving during the ending has no `call` record.
                tool_records = stand_ins.records("tool")
                assert [(r["event"], r["data"]["tool"]) for r in tool_records] == [
                    ("call", "refused"), ("result", "refused"), ("call", "slow"), ("call", "stubborn"),
                    ("call", "bug"), ("while_ending", "bug"), ("while_ending", "slow"),
                    ("while_ending", "echo"), ("result", "stubborn")]
                refused_record = tool_records[1]["data"]
                assert (refused_record["is_error"], refused_record["error"]) == (True, "NodeNotFound")
                assert refused_record["text"] == str(NodeNotFound("theory_X", []))
                assert tool_records[0]["data"]["arguments"] == {}
                assert tool_records[-1]["data"]["is_error"] is False and "error" not in tool_records[-1]["data"]
                [ending_record] = [r for r in stand_ins.records("conversation") if r["event"] == "ending"]
                assert ending_record["level"] == "error" and ending_record["data"]["message"] == "tat-bug"
                assert ending_record["ts"] <= tool_records[5]["ts"]
                async with httpx.AsyncClient() as http:   # it stopped accepting
                    with pytest.raises(httpx.ConnectError):
                        await http.post(server.url,
                                        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                                        headers={"Accept": "application/json, text/event-stream"})
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
    assert stopped(RuntimeError()) == INTERNAL


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


@pytest.mark.parametrize("tool, ended_type", [
    ("escapes", TAT_InternalError), ("not_text", Exception), ("plain", TypeError)])
def test_the_boundary_failing_is_a_bug_that_ends_the_conversation(tool, ended_type):
    """A body letting a cancellation escape, returning what no result can
    hold, or not being a coroutine at all: the agent gets the
    internal-error line, never an SDK rendering, and the conversation
    ends."""
    async def scenario():
        port = free_port()
        async with serving(port, Bodies().tools()) as (server, serve), client(server.url) as session:
            result = await session.call_tool(tool, {})
            assert result.isError and text_of(result) == INTERNAL
            exn = await ended(serve)
            assert isinstance(exn, ended_type)
            if tool == "escapes":
                assert str(exn) == "the body of `escapes` was cancelled"
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
