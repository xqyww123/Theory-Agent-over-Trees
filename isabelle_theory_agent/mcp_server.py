"""The Streamable HTTP MCP server (MODULE_STRUCTURE §4.6): the endpoint
`http://127.0.0.1:<port>/mcp`, the path `/on-compaction` the agent
clients' hooks call (CLIENT_HOOKS.md); the tool boundary of EXCEPTIONS.md
§1; the conversation's ending.

TAT's own transport code, on the Python `mcp` SDK's low-level server and
session manager and on uvicorn.  Two lessons from AoA's server
(`contrib/Isa-Mini/IsaMini/AoA/mcp_http_server.py`): the session
manager's lifetime stays inside one asyncio task, and the port is bound
before anything is announced, never waited for.
"""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import Callable, Coroutine
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, NoReturn
from urllib.parse import parse_qs

import anyio
import anyio.lowlevel
import uvicorn
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecurityMiddleware, TransportSecuritySettings
from starlette.requests import Request

from .exceptions import TAT_DisasterError, TAT_Error, TAT_InternalError, TAT_StartupError
from .model import JSON_Schema

HOST = "127.0.0.1"
PATH = "/mcp"
ON_COMPACTION = "/on-compaction"


def _hook_specific_output(briefing: str) -> Any:
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": briefing}}


def _additional_context(briefing: str) -> Any:
    return {"additional_context": briefing}


# The clients whose hooks call `/on-compaction`, each with the shape it
# takes the briefing in — a JSON body, or None for the text alone
# (CLIENT_HOOKS.md); the order is the refusal line's.
CLIENTS: dict[str, Callable[[str], Any] | None] = {
    "claude-code": _hook_specific_output,
    "codex": _hook_specific_output,
    "gemini-cli": _hook_specific_output,
    "cursor": _additional_context,
    "opencode": None,
}


def unknown_client(client: str) -> str:
    known = list(CLIENTS)
    return f"TAT does not know the client `{client}`; it knows {', '.join(known[:-1])} and {known[-1]}"


def envelope(client: str | None, briefing: str) -> tuple[bytes, str]:
    """The answer's body and content type for the client, the text alone
    for none (CLIENT_HOOKS.md)."""
    shape = CLIENTS[client] if client is not None else None
    if shape is None:
        return briefing.encode(), "text/plain; charset=utf-8"
    return json.dumps(shape(briefing)).encode(), "application/json"


@dataclass(frozen=True)
class Tool:
    """One tool as the server advertises and runs it (`mcp.py` builds
    them): `run` takes the call's arguments and returns the result's text,
    or raises — a `TAT_Error` for the agent, anything else ending the
    conversation."""
    name: str
    description: str
    input_schema: JSON_Schema
    run: Callable[[dict[str, Any]], Coroutine[Any, Any, str]]


def stopped(ended_by: BaseException) -> str:
    """The one answer while the conversation is ending (RENDER_BASELINES
    §4), by what ended it: a `TAT_DisasterError`; the connection error a
    dead wire answers a round trip with, or the RPC host's cancellation of
    `launch_TAT` when the connection is gone; else a bug."""
    if isinstance(ended_by, TAT_DisasterError):
        reason = "the forest could not be saved"
    elif isinstance(ended_by, (ConnectionError, asyncio.CancelledError)):
        reason = "Isabelle is gone"
    else:
        reason = "an internal error"
    return f"TAT has stopped: {reason}; this call did not complete."


class TAT_Server:
    """The server of one conversation, constructed on the running loop:
    `async with` binds the port (`TAT_StartupError` when it cannot be),
    starts the session manager and listens, and on leaving stops; `serve`
    runs the conversation until its ending and raises what ended it."""

    def __init__(self, port: int, tools: list[Tool], on_compaction: Callable[[], str]):
        """`on_compaction` is what `/on-compaction` does — the seen set
        cleared, the briefing returned (`mcp.py`); anything it raises ends
        the conversation, as a tool body's would."""
        self._port = port
        self._tools = {tool.name: tool for tool in tools}
        self._on_compaction = on_compaction
        self.url = f"http://{HOST}:{port}{PATH}"

        # The conversation's ending: what ended it, once entered; the
        # bodies it cancels; the requests it waits for.
        self._ending: asyncio.Future[BaseException] = asyncio.get_running_loop().create_future()
        self._bodies: set[asyncio.Task[str]] = set()
        self._requests = 0                  # in flight, the standalone GET stream excepted
        self._idle = asyncio.Event()        # no request in flight
        self._idle.set()

        app: Server[Any, Any] = Server("TAT")
        app.list_tools()(self._list_tools)
        app.call_tool(validate_input=False)(self._call_tool)
        # the SDK checks Host and Origin only when told what to accept;
        # the spelling is the printed URL's, and `/on-compaction` checks
        # with the same settings, so the two paths cannot drift
        authority = f"{HOST}:{port}"
        security = TransportSecuritySettings(
            allowed_hosts=[authority], allowed_origins=["http://" + authority])
        self._security = TransportSecurityMiddleware(security)
        self._manager = StreamableHTTPSessionManager(app, security_settings=security)
        self._running = AsyncExitStack()    # holds the manager's `run` while the endpoint is open

        # not `uvicorn.Server.serve`: it takes over SIGINT and SIGTERM for
        # the whole process, which are the RPC host's
        config = uvicorn.Config(
            self._asgi, host=HOST, port=port,
            interface="asgi3",              # uvicorn's detection reads a bound method as ASGI 2
            lifespan="off", ws="none",
            log_config=None, log_level="warning", access_log=False)
        config.load()
        self._uvicorn = uvicorn.Server(config)
        self._uvicorn.lifespan = config.lifespan_class(config)   # `serve` would set it; nothing else does

    async def __aenter__(self) -> TAT_Server:
        self._socket = _bind(self._port)
        try:
            await self._running.enter_async_context(self._manager.run())
            await self._uvicorn.startup(sockets=[self._socket])
        except BaseException:
            await self._running.aclose()
            # cancelled inside `create_server`: uvicorn has no server to
            # close yet, but the loop has a reader on this descriptor
            asyncio.get_running_loop().remove_reader(self._socket.fileno())
            self._socket.close()
            raise
        return self

    async def __aexit__(self, *_: object) -> None:
        self._stop_listening()              # nothing accepts while the manager unwinds
        # the manager first: joining its handlers ends every stream a client
        # held open, so the connections close and uvicorn's shutdown returns,
        # and it is where a body the ending cancelled is waited out (§4.3)
        await self._running.aclose()
        await self._uvicorn.shutdown(sockets=[self._socket])

    async def serve(self) -> NoReturn:
        """Serve until the conversation's ending; then stop accepting, let
        what is still in flight be answered, and raise what ended the
        conversation.  Cancelled — the RPC host ending `launch_TAT`'s call
        because the connection is gone — it enters the ending itself and
        raises that cancellation the same way."""
        try:
            await self._uvicorn.main_loop()          # returns once `end` has run
        except asyncio.CancelledError as gone:
            self.end(gone)
        self._stop_accepting()
        while self._requests:
            await self._idle.wait()
        raise self._ending.result()

    def end(self, ended_by: BaseException) -> None:
        """Enter the conversation's ending, unless it is entered: cancel
        every working call's body — each handler answers its own call —
        and have `serve` stop once they have."""
        if self._ending.done():
            return
        self._ending.set_result(ended_by)
        for body in self._bodies:
            body.cancel()
        self._uvicorn.should_exit = True

    def _stop_listening(self) -> None:
        for server in self._uvicorn.servers:
            server.close()
        self._socket.close()

    def _stop_accepting(self) -> None:
        """The first steps of uvicorn's own `shutdown`: no new connection,
        every idle one closed, one mid-response closed after it."""
        self._stop_listening()
        for connection in list(self._uvicorn.server_state.connections):
            connection.shutdown()

    # --- the endpoint ----------------------------------------------------

    async def _asgi(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":         # cannot fire: lifespan off, ws none
            return
        if scope["path"] == ON_COMPACTION:
            await self._counted(self._compaction(scope, receive, send))
            return
        if scope["path"] != PATH:
            await _answer(send, 404, b"", "text/plain")
            return
        if scope["method"] == "GET":        # the standalone stream, held as long as the client likes
            await self._manager.handle_request(scope, receive, send)
            return
        await self._counted(self._manager.handle_request(scope, receive, send))

    async def _counted(self, handling: Coroutine[Any, Any, None]) -> None:
        """A request the conversation's ending waits for."""
        self._requests += 1
        self._idle.clear()
        try:
            await handling
        finally:
            self._requests -= 1
            if self._requests == 0:
                self._idle.set()

    async def _compaction(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """`POST /on-compaction?client=<name>` (MODULE_STRUCTURE §4.6): the
        transport check as for `/mcp`, less the content type the hooks do
        not send; an unknown client refused before anything is touched;
        an empty 503 while the conversation is ending, which touches no
        forest; then the closure once, its answer in the client's shape —
        or, if it raises, the conversation's ending and an empty 500, so
        the hook reports a failure and nothing half-rendered reaches the
        agent."""
        refused = await self._security.validate_request(Request(scope, receive), is_post=False)
        if refused is not None:
            await refused(scope, receive, send)
            return
        if scope["method"] != "POST":
            await _answer(send, 405, b"", "text/plain")
            return
        client = parse_qs(scope["query_string"].decode()).get("client", [None])[0]
        if client is not None and client not in CLIENTS:
            await _answer(send, 400, unknown_client(client).encode(), "text/plain; charset=utf-8")
            return
        if self._ending.done():             # nothing left to brief
            await _answer(send, 503, b"", "text/plain")
            return
        try:
            briefing = self._on_compaction()
        except Exception as bug:
            self.end(bug)
            await _answer(send, 500, b"", "text/plain")
            return
        await _answer(send, 200, *envelope(client, briefing))

    # --- the tool boundary (EXCEPTIONS.md §1) ----------------------------

    async def _list_tools(self) -> list[types.Tool]:
        return [types.Tool(name=tool.name, description=tool.description,
                           inputSchema=tool.input_schema)
                for tool in self._tools.values()]

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        if self._ending.done():
            return _result(stopped(self._ending.result()), is_error=True)
        tool = self._tools.get(name)
        if tool is None:
            return _result(f"unknown tool `{name}`", is_error=True)
        # The body runs as a task of its own, outside the request's cancel
        # scope, and the wait is shielded: neither a client's cancellation
        # nor the SDK's unwind reaches it mid-edit.  `asyncio.wait` never
        # cancels what it waits on.
        body = asyncio.create_task(_run(tool, arguments))
        self._bodies.add(body)
        body.add_done_callback(self._bodies.discard)
        with anyio.CancelScope(shield=True):
            await asyncio.wait({body})
        answer = self._answer(name, body)
        # a cancellation that arrived meanwhile passes here: the SDK has
        # answered the client itself, and this call is nobody's to answer
        await anyio.lowlevel.checkpoint()
        return answer

    def _answer(self, name: str, body: asyncio.Task[str]) -> types.CallToolResult:
        """What the body did decides (MODULE_STRUCTURE §4.6): its text; a
        `TAT_Error`, rendered; anything else enters the ending, which
        answers.  The boundary itself failing is a bug like any other."""
        try:
            if body.cancelled():            # the ending's, or a cancellation the body let escape
                self.end(TAT_InternalError(f"the body of `{name}` was cancelled"))
            else:
                exn = body.exception()
                if exn is None:
                    return _result(body.result(), is_error=False)
                if isinstance(exn, TAT_Error):
                    return _result(str(exn), is_error=True)
                self.end(exn)
        except Exception as bug:
            self.end(bug)
        return _result(stopped(self._ending.result()), is_error=True)


async def _run(tool: Tool, arguments: dict[str, Any]) -> str:
    return await tool.run(arguments)        # a malformed tool fails as its body fails


def _result(text: str, is_error: bool) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)],
                                isError=is_error)


async def _answer(send: Any, status: int, body: bytes, content_type: str) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", content_type.encode()),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


def _bind(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((HOST, port))
    except OSError as e:
        sock.close()
        raise TAT_StartupError(f"TAT cannot serve on {HOST}:{port}: {e.strerror}") from e
    return sock
