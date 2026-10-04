"""The Streamable HTTP MCP server (MODULE_STRUCTURE §4.6): the endpoint
`http://127.0.0.1:<port>/mcp`, the path `/on-compaction` the agent
clients' hooks call (CLIENT_HOOKS.md); the tool boundary of EXCEPTIONS.md
§1; the conversation's ending, `Ending`; one subclass of the server per
agent client (CONSTRUCT_INTERACTION §8).

TAT's own transport code, on the Python `mcp` SDK's low-level server and
session manager and on uvicorn.  Two lessons from AoA's server
(`contrib/Isa-Mini/IsaMini/AoA/mcp_http_server.py`): the session
manager's lifetime stays inside one asyncio task, and the port is bound
before anything is announced, never waited for.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import socket
import sys
import time
from collections.abc import Callable, Coroutine
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, NamedTuple, NoReturn, TypeVar
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
from .log import Log
from .model import CannotUseWorkingDirectory, Forest, JSON_Schema

HOST = "127.0.0.1"
PATH = "/mcp"
ON_COMPACTION = "/on-compaction"

AGENTS = "TAT.agents"                   # the agent directory (ARCHITECTURE §1)
SCRIPTS = ".tat"                        # where the hooks' scripts go (CLIENT_HOOKS.md §1)
HOOK_TIMEOUT = 10                       # seconds a client gives a hook
RESOLV_CONF = "/etc/resolv.conf"
# the system directories Codex's `:minimal` reads (CLIENT_HOOKS.md §5)
MINIMAL = ("/bin", "/sbin", "/usr", "/etc", "/lib", "/lib64", "/nix/store", "/run/current-system/sw")


def toml_string(value: str) -> str:
    """The TOML basic string for `value` (TOML 1.0): `"` and `\\` escaped,
    every control character and DEL as `\\uXXXX`."""
    def escaped(c: str) -> str:
        if c in '"\\':
            return "\\" + c
        return f"\\u{ord(c):04X}" if ord(c) < 0x20 or ord(c) == 0x7F else c
    return '"' + "".join(map(escaped, value)) + '"'


def resolver_entry(resolv_conf: str) -> str | None:
    """The real path of the resolver's file when it lies outside the
    `:minimal` directories — the one read entry Codex's profile adds, never
    the symbolic link — else None (CLIENT_HOOKS.md §5)."""
    real = os.path.realpath(resolv_conf)
    if any(real == root or real.startswith(root + os.sep) for root in MINIMAL):
        return None
    return real


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


Body = Callable[[dict[str, Any]], Coroutine[Any, Any, str]]


@dataclass(frozen=True)
class Tool:
    """One tool as the server advertises and runs it (`mcp.py` builds
    them): `run` takes the call's arguments and returns the result's text,
    or raises — a `TAT_Error` for the agent, anything else ending the
    conversation; `read_only` is advertised as MCP's `readOnlyHint`
    (MCP_SPECIFICATION §5)."""
    name: str
    description: str
    input_schema: JSON_Schema
    run: Body
    read_only: bool


def connection_went(ended_by: BaseException) -> bool:
    """Whether what ended the conversation is the connection going: the
    connection error a dead wire answers a round trip with, or the RPC
    host's cancellation of `launch_TAT`."""
    return isinstance(ended_by, (ConnectionError, asyncio.CancelledError))


def stopped_for(reason: str) -> str:
    """The form every line of RENDER_BASELINES §4 has, for one reason."""
    return (f"TAT has stopped: {reason}; this is a critical error, and this call did not complete. "
            "Stop now and call TAT no more. If another agent started you, tell it to stop as well; "
            "otherwise tell the user that TAT has stopped.")


def stopped(ended_by: BaseException) -> str:
    """The one answer while the conversation is ending (RENDER_BASELINES
    §4), by what ended it: a `TAT_DisasterError`; the connection gone; a
    `Session`'s folder that cannot be made; else a bug."""
    if isinstance(ended_by, TAT_DisasterError):
        return stopped_for("the sessions could not be saved")
    if connection_went(ended_by):
        return stopped_for("Isabelle is gone")
    if isinstance(ended_by, CannotUseWorkingDirectory):
        return stopped_for("it cannot use its working directory")
    return stopped_for("an internal error")


T = TypeVar("T")


class Ending:
    """The conversation's ending (MODULE_STRUCTURE §4.6), the one state a
    conversation has besides running.  `toplevel.conversation()` enters it
    as a context right after the `Log` and hands it to the `Conversation`
    and to the server.  It holds the `Log`, the `Forest` once that is
    built, and the tasks it cancels and `unwound` waits for: the tool
    bodies the server runs through `spawn`, later a construction job's run.
    Whichever door is reached first calls `end`, which enters the ending
    once; the server's exit drains (the calls answered, the tasks unwound);
    the context's exit enters it for an exception escaping the start and
    writes `ended`."""

    def __init__(self, log: Log):
        self.log = log
        self.forest: Forest | None = None
        self._ended_by: BaseException | None = None
        self._entered = asyncio.Event()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._since = 0.0                   # when `end` ran

    @property
    def entered(self) -> bool:
        return self._ended_by is not None

    @property
    def ended_by(self) -> BaseException:
        """What ended the conversation; asked once the ending is entered."""
        if self._ended_by is None:
            raise TAT_InternalError("the conversation is not ending")
        return self._ended_by

    async def wait(self) -> None:
        await self._entered.wait()

    def spawn(self, coroutine: Coroutine[Any, Any, T]) -> asyncio.Task[T]:
        """A task of the conversation's: cancelled by `end`, waited for by
        `unwound`."""
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def end(self, ended_by: BaseException) -> None:
        """Enter the ending, unless it is entered, in one synchronous
        stretch: write the `ending` record (LOGGING.md §4) and cancel every
        spawned task — each tool handler answers its own call."""
        if self._ended_by is not None:
            return
        self._ended_by = ended_by
        self._since = time.monotonic()
        self.log.conversation.ending(ended_by)
        for task in self._tasks:
            task.cancel()
        self._entered.set()

    async def unwound(self) -> None:
        """Every spawned task has ended: the server waits for this before it
        stops, so before the store closes (MODULE_STRUCTURE §4.6)."""
        while self._tasks:
            await asyncio.wait(set(self._tasks))

    async def __aenter__(self) -> Ending:
        return self

    async def __aexit__(self, _: object, exc: BaseException | None, __: object) -> None:
        if exc is not None:
            self.end(exc)
        if self._ended_by is None:          # a compile that returned
            return
        await self.unwound()                # nothing left on the serving path
        self.log.conversation.ended(duration=time.monotonic() - self._since)


class TAT_Server:
    """The server of one conversation, constructed on the running loop:
    `async with` binds the port (`TAT_StartupError` when it cannot be),
    starts the session manager and listens, and on leaving stops; `serve`
    runs the conversation until its ending and raises what ended it.  The
    ending is `ending`'s, given; the server keeps no ending state of its
    own.  One subclass per agent client (CONSTRUCT_INTERACTION §8), each
    stating the `clientInfo.name` its client's MCP sessions open with and
    the client's version its facts were measured on."""

    client_name: ClassVar[str]
    measured_version: ClassVar[str]

    def __init__(self, ending: Ending, port: int, tools: list[Tool],
                 on_compaction: Callable[[], str]):
        """`on_compaction` is what `/on-compaction` does — the seen set
        cleared, the briefing returned (`mcp.py`); anything it raises ends
        the conversation, as a tool body's would."""
        self.ending = ending
        self._port = port
        self._tools = {tool.name: tool for tool in tools}
        self._on_compaction = on_compaction
        self.url = f"http://{HOST}:{port}{PATH}"

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

    def configure(self, working_directory: Path) -> None:
        """The client's files, written whole into the agent directory, and
        the scripts its hooks run into `.tat/` (CLIENT_HOOKS.md); called
        before the port is bound (MODULE_STRUCTURE §4.6)."""
        agents = working_directory / AGENTS
        agents.mkdir(exist_ok=True)
        written: list[str] = []
        for name, text in self._client_files(working_directory).items():
            (agents / name).parent.mkdir(parents=True, exist_ok=True)
            (agents / name).write_text(text)
            written.append(f"{AGENTS}/{name}")
        for script in ("hook.py", "guard.py"):
            shutil.copy(Path(__file__).parent / script, working_directory / SCRIPTS / script)
            written.append(f"{SCRIPTS}/{script}")
        self.ending.log.conversation.configured(files=written)

    def _client_files(self, working_directory: Path) -> dict[str, str]:
        """The client's files, by name within the agent directory, each the
        text its format's one encoder gives (MODULE_STRUCTURE §4.6)."""
        raise NotImplementedError

    def _hook(self, working_directory: Path, script: str, matcher: str | None = None) -> dict[str, Any]:
        """One hook entry as both clients take it: the script run under the
        interpreter TAT's Python side runs under, each path quoted."""
        command = (f"{shlex.quote(sys.executable)} -I "
                   f"{shlex.quote(str(working_directory / SCRIPTS / script))}")
        entry: dict[str, Any] = {} if matcher is None else {"matcher": matcher}
        entry["hooks"] = [{"type": "command", "timeout": HOOK_TIMEOUT, "command": command}]
        return entry

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

    async def __aexit__(self, _: object, exc: BaseException | None, __: object) -> None:
        """The one drain (MODULE_STRUCTURE §4.6): whatever escapes the block
        enters the ending; once it is entered, nothing new is accepted, the
        calls in flight are answered and the spawned tasks unwound, and only
        then does the server stop — so the store is still open for them.
        The stop comes even when the drain is cancelled."""
        if exc is not None:
            self.ending.end(exc)
        try:
            if self.ending.entered:
                self._stop_accepting()
                while self._requests:
                    await self._idle.wait()
                await self.ending.unwound()
        finally:
            self._stop_listening()          # nothing accepts while the manager unwinds
            # the manager first: joining its handlers ends every stream a client
            # held open, so the connections close and uvicorn's shutdown returns
            await self._running.aclose()
            await self._uvicorn.shutdown(sockets=[self._socket])

    async def serve(self) -> NoReturn:
        """Serve until the conversation's ending, then raise what ended it;
        the drain is the exit's.  Cancelled — the RPC host ending
        `launch_TAT`'s call because the connection is gone — it enters the
        ending itself and raises that cancellation the same way."""
        main_loop = asyncio.ensure_future(self._uvicorn.main_loop())
        main_loop.add_done_callback(self._main_loop_done)
        try:
            await self.ending.wait()
        except asyncio.CancelledError as gone:
            self.ending.end(gone)
        self._uvicorn.should_exit = True
        # returns once the loop was told to exit, or once it failed on its
        # own, which `_main_loop_done` has entered as a bug
        await asyncio.wait({main_loop})
        self._stop_accepting()              # the exit does the rest of the drain
        raise self.ending.ended_by

    def _main_loop_done(self, main_loop: asyncio.Task[None]) -> None:
        """uvicorn's loop failing on its own is a bug, which ends the
        conversation like any other."""
        if not main_loop.cancelled() and (bug := main_loop.exception()) is not None:
            self.ending.end(bug)

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
        if self.ending.entered:             # nothing left to brief
            await _answer(send, 503, b"", "text/plain")
            return
        try:
            briefing = self._on_compaction()
        except Exception as bug:
            self.ending.end(bug)
            await _answer(send, 500, b"", "text/plain")
            return
        await _answer(send, 200, *envelope(client, briefing))

    # --- the tool boundary (EXCEPTIONS.md §1) ----------------------------

    async def _list_tools(self) -> list[types.Tool]:
        return [types.Tool(name=tool.name, description=tool.description,
                           inputSchema=tool.input_schema,
                           annotations=types.ToolAnnotations(readOnlyHint=tool.read_only))
                for tool in self._tools.values()]

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        """Every call writes `call`, then exactly one of `result`,
        `given_up` and `while_ending` (LOGGING.md §4)."""
        log = self.ending.log.tool
        log.call(tool=name, arguments=arguments)
        started = time.monotonic()
        tool = self._tools.get(name)
        if self.ending.entered:
            result: Result | None = None    # the ending answers
        elif tool is None:
            result = Result(f"unknown tool `{name}`", True, None)
        else:
            # The body runs as a task of its own, outside the request's
            # cancel scope, and the wait is shielded: neither a client's
            # cancellation nor the SDK's unwind reaches it mid-edit.
            # `asyncio.wait` never cancels what it waits on.
            body = self.ending.spawn(_run(tool, arguments))
            with anyio.CancelScope(shield=True):
                await asyncio.wait({body})
            result = self._result_of(name, body)
        duration = time.monotonic() - started
        try:
            # a cancellation that arrived meanwhile passes here: the SDK has
            # answered the client itself, and this call is nobody's to answer
            await anyio.lowlevel.checkpoint()
        except asyncio.CancelledError:
            log.given_up(tool=name, text=None if result is None else result.text, messages=[],
                         duration=duration)
            raise
        if result is None:
            log.while_ending(tool=name)
            return _call_tool_result(stopped(self.ending.ended_by), is_error=True)
        log.result(tool=name, is_error=result.is_error, text=result.text, messages=[],
                   trailer=None, class_=result.class_, duration=duration)
        return _call_tool_result(result.text, result.is_error)

    def _result_of(self, name: str, body: asyncio.Task[str]) -> Result | None:
        """What the body did decides (MODULE_STRUCTURE §4.6): its text; a
        `TAT_Error`, rendered; anything else enters the ending, which
        answers — None.  The boundary itself failing is a bug like any
        other."""
        try:
            if body.cancelled():            # the ending's, or a cancellation the body let escape
                self.ending.end(TAT_InternalError(f"the body of `{name}` was cancelled"))
            else:
                exn = body.exception()
                if exn is None:
                    return Result(body.result(), False, None)
                if isinstance(exn, TAT_Error):
                    return Result(str(exn), True, type(exn).__name__)
                self.ending.end(exn)
        except Exception as bug:
            self.ending.end(bug)
        return None


class Claude_Code_Server(TAT_Server):
    client_name = "claude-code"
    measured_version = "2.1.286"

    def _client_files(self, working_directory: Path) -> dict[str, str]:
        """CLIENT_HOOKS.md §2: the server entry; the environment, the
        permissions and sandbox settings of §5, and the hooks."""
        def hook(script: str, matcher: str | None = None) -> dict[str, Any]:
            return self._hook(working_directory, script, matcher)
        settings = {
            "env": {"CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS": "0", "CLAUDE_CODE_STOP_HOOK_BLOCK_CAP": "0",
                    "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "0", "CLAUDE_CODE_FORCE_SESSION_PERSISTENCE": "1"},
            "permissions": {"allow": ["Bash"], "deny": ["EnterWorktree"],
                            "blockReadsOutsideWorkingDirectories": True},
            "sandbox": {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False,
                        "network": {"allowAllUnixSockets": True, "allowedDomains": ["*"]},
                        "filesystem": {"denyRead": [str(working_directory), "/run"]}},
            "hooks": {
                "PreToolUse": [hook("hook.py", "mcp__TAT__.*"), hook("hook.py", "TaskStop"),
                               hook("guard.py", "Write|Edit|NotebookEdit|MultiEdit"),
                               hook("guard.py", "Agent|Task")],
                "Stop": [hook("hook.py")],
                "SubagentStop": [hook("hook.py")],
                "PostCompact": [hook("hook.py")],
                "WorktreeCreate": [hook("guard.py")]}}
        return {".mcp.json": _json({"mcpServers": {"TAT": {"type": "http", "url": self.url,
                                                           "timeout": 43_200_000}}}),
                ".claude/settings.json": _json(settings)}


class Codex_Server(TAT_Server):
    client_name = "codex-mcp-client"
    measured_version = "0.156.1"

    def _client_files(self, working_directory: Path) -> dict[str, str]:
        """CLIENT_HOOKS.md §3: the configuration with the permission profile
        of §5 and the server entry; the hooks."""
        resolver = resolver_entry(RESOLV_CONF)
        config = [
            "check_for_update_on_startup = false",
            'default_permissions = "tat-agent"',
            "",
            "[features]",
            "multi_agent_v2 = true",
            "",
            "[permissions.tat-agent.filesystem]",
            '":minimal" = "read"',
            f'{toml_string(str(working_directory))} = "deny"',
            *([f'{toml_string(resolver)} = "read"'] if resolver is not None else []),
            "",
            '[permissions.tat-agent.filesystem.":workspace_roots"]',
            '"." = "write"',
            "",
            "[permissions.tat-agent.network]",
            "enabled = true",
            "",
            "[mcp_servers.TAT]",
            f"url = {toml_string(self.url)}",
            "tool_timeout_sec = 43200",
            'default_tools_approval_mode = "approve"',
            ""]
        hook = self._hook(working_directory, "hook.py")
        hooks = {"hooks": {
            "PreToolUse": [self._hook(working_directory, "hook.py", "mcp__TAT__.*"),
                           self._hook(working_directory, "hook.py", "collaborationinterrupt_agent")],
            "Stop": [hook], "SubagentStop": [hook], "SessionStart": [hook],
            "PreCompact": [hook], "PostCompact": [hook]}}
        return {".codex/config.toml": "\n".join(config), ".codex/hooks.json": _json(hooks)}


def _json(value: Any) -> str:
    return json.dumps(value, indent=2) + "\n"


# The subclass for each name `isabelle TAT_mcp -c` takes; the launcher
# refuses any other (MODULE_STRUCTURE §5).
SERVERS: dict[str, type[TAT_Server]] = {"claude-code": Claude_Code_Server, "codex": Codex_Server}


class Result(NamedTuple):
    """A tool call's result as the boundary decides it — what the client is
    answered and what the `tool.result` record carries: the text, whether
    it is an error, and the `TAT_Error`'s class when one refused the call."""
    text: str
    is_error: bool
    class_: str | None


async def _run(tool: Tool, arguments: dict[str, Any]) -> str:
    text = await tool.run(arguments)        # a malformed tool fails as its body fails
    if not isinstance(text, str):
        raise TAT_InternalError(
            f"the body of `{tool.name}` returned a {type(text).__name__}, not a text")
    return text


def _call_tool_result(text: str, is_error: bool) -> types.CallToolResult:
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
