"""The Streamable HTTP MCP server (MODULE_STRUCTURE §4.6): the endpoint
`http://127.0.0.1:<port>/mcp`, the path `/hook` the conversation's hooks
post to (CLIENT_HOOKS.md) and the path `/on-compaction`; the tool
boundary of EXCEPTIONS.md §1; the conversation's ending, `Ending`; one
subclass of the server per agent client (CONSTRUCT_INTERACTION §8),
which names the calling agent and judges the hooks.

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
import re
import shlex
import socket
import sys
import time
import weakref
from collections.abc import Callable, Coroutine
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Literal, NamedTuple, NoReturn, TypeVar
from urllib.parse import parse_qs

import anyio
import anyio.lowlevel
import uvicorn
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.lowlevel.server import NotificationOptions, request_ctx
from mcp.server.models import InitializationOptions
from mcp.server.session import ServerSession
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecurityMiddleware, TransportSecuritySettings
from starlette.requests import Request

from .compile import _create, _is_folder
from .exceptions import TAT_DisasterError, TAT_Error, TAT_InternalError, TAT_StartupError
from .guard import ALLOW
from .jobs import Agent
from .log import Judged, Log, current_agent, current_call
from .model import CannotUseWorkingDirectory, Forest, JSON_Schema

HOST = "127.0.0.1"
PATH = "/mcp"
HOOK = "/hook"
ON_COMPACTION = "/on-compaction"
SERVER_NAME = "TAT"                     # the client's name for TAT's server entry (CONSTRUCT_INTERACTION §8)
TOOL_PREFIX = f"mcp__{SERVER_NAME}__"   # a TAT tool's name as the client sees it

# A call no `PreToolUse` announced (CONSTRUCT_INTERACTION §8): the client's
# hooks do not reach TAT; the `unannounced` record's message, never shown.
UNANNOUNCED = ("This call was not announced by the client's hooks, so TAT cannot tell which agent "
               "is calling.")


def second_announcement(tool_use_id: str) -> str:
    """The message of the bug a `tool_use_id` announced again before its
    call arrived is: the ids are unique by the clients' measured behaviour,
    so a repeat breaks TAT's premise about the client's hooks."""
    return (f"TAT received a second announcement of the call {tool_use_id} before that call arrived; "
            "the client's hooks cannot be trusted.")

AGENTS = "TAT.agents"                   # the agent directory (ARCHITECTURE §1)
DOT_TAT = ".tat"                        # the logs and the hooks' scripts (LOGGING.md §2, CLIENT_HOOKS.md §1)
HOOK_TIMEOUT = 10                       # seconds a client gives a hook
RESOLV_CONF = "/etc/resolv.conf"
# the system directories Codex's `:minimal` reads (CLIENT_HOOKS.md §5)
MINIMAL = ("/bin", "/sbin", "/usr", "/etc", "/lib", "/lib64", "/nix/store", "/run/current-system/sw")
SANDBOX_STATE = "codex/sandbox-state-meta"      # the capability, and the `_meta` key it brings (§5)


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
    return None if any(Path(real).is_relative_to(root) for root in MINIMAL) else real


def sandbox_is_the_profile(policy: Any, working_directory: Path) -> bool:
    """Whether the sandbox policy a Codex call carries is the profile TAT
    configured, recognised by its `deny` entry on the working directory
    (CLIENT_HOOKS.md §5): another profile, a disabled sandbox, no policy or
    one of another shape is not."""
    try:
        return any(entry["access"] == "deny" and entry["path"]["type"] == "path"
                   and os.path.realpath(entry["path"]["path"]) == os.path.realpath(working_directory)
                   for entry in policy["permissionProfile"]["file_system"]["entries"])
    except (KeyError, TypeError):
        return False


def _replaced(directory: Path, name: str, text: str) -> None:
    """`text` as the file `name` below `directory`, which is made when
    absent; below it, whatever is not a directory and stands at the name or
    at a directory on its way — a symbolic link included — is removed first,
    never written through; a directory at the name stays, and the write
    fails, as compile's does (COMPILATION.md §2)."""
    directory.mkdir(exist_ok=True)
    *folders, file = Path(name).parts
    path = directory
    for folder in folders:
        path /= folder
        if not _is_folder(path):
            path.unlink(missing_ok=True)
            path.mkdir()
    (path / file).unlink(missing_ok=True)
    _create(path / file, text)


class _App(Server[Any, Any]):
    """The SDK's server, declaring in its `initialize` result the
    experimental capabilities the client subclass states (CLIENT_HOOKS.md §5)."""

    def __init__(self, experimental: dict[str, dict[str, Any]]):
        super().__init__(SERVER_NAME)
        self._experimental = experimental

    def create_initialization_options(
            self, notification_options: NotificationOptions | None = None,
            experimental_capabilities: dict[str, dict[str, Any]] | None = None) -> InitializationOptions:
        return super().create_initialization_options(
            notification_options, {**self._experimental, **(experimental_capabilities or {})})


def _dumped(meta: types.RequestParams.Meta | None) -> Any:
    """A call's `_meta` as a record carries it; None when the call has none."""
    return meta.model_dump(by_alias=True, exclude_none=True) if meta is not None else None


def _extra(meta: types.RequestParams.Meta | None) -> dict[str, Any]:
    """The client's own keys of a call's `_meta`; empty when there are none."""
    return (meta.model_extra if meta is not None else None) or {}


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


class ClientRefused(TAT_StartupError):
    """A refusal raised while serving (EXCEPTIONS.md §3): the client's
    version or name, Codex's sandbox, an agent with no transcript.  `line`
    is the ending's answer to every tool call meanwhile (RENDER_BASELINES
    §4), required here so that no refusal is answered as an internal
    error; the message is what the launcher prints."""

    def __init__(self, message: str, line: str):
        super().__init__(message)
        self.line = line


def stopped(ended_by: BaseException) -> str:
    """The one answer while the conversation is ending (RENDER_BASELINES
    §4), by what ended it: a refusal, which carries its line; a
    `TAT_DisasterError`; the connection gone; a `Session`'s folder that
    cannot be made; else a bug."""
    if isinstance(ended_by, ClientRefused):
        return ended_by.line
    if isinstance(ended_by, TAT_DisasterError):
        return stopped_for("the sessions could not be saved")
    if connection_went(ended_by):
        return stopped_for("Isabelle is gone")
    if isinstance(ended_by, CannotUseWorkingDirectory):
        return stopped_for("it cannot use its working directory")
    return stopped_for("an internal error")


T = TypeVar("T")


@dataclass(frozen=True)
class Announcement:
    """A `PreToolUse` on a TAT tool (CONSTRUCT_INTERACTION §8), as the
    payload states it: the call's `tool_use_id`, the identity the payload
    gives the announcing agent — None when it gives none — and whether that
    is the main conversation."""
    tool_use_id: str
    identity: str | None
    main: bool


def _field(payload: dict[str, Any], name: str) -> Any:
    """A field the client documents for the hook; its absence breaks TAT's
    premise about the client, a bug like any other on the path."""
    try:
        return payload[name]
    except KeyError:
        raise TAT_InternalError(
            f"the {payload.get('hook_event_name')} payload carries no {name}") from None


def _text(value: Any) -> str | None:
    return str(value) if value is not None else None


def _version_numbers(version: str) -> tuple[int, ...]:
    """The leading dotted numbers of a version, `2.1.286` of `2.1.286-beta`;
    empty when it starts with none, which is lower than any version."""
    m = re.match(r"\d+(?:\.\d+)*", version)
    return tuple(int(n) for n in m.group().split(".")) if m else ()


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
    stating the name `isabelle TAT_mcp -c` takes for it, the
    `clientInfo.name` its client's MCP sessions open with, the client's
    version its facts were measured on, the `_meta` key under which a call
    carries the id its announcement named, and what the announcement is
    answered; each names the agent of a call its own way.  The server keeps
    the client's agents, by the identity the client gives them, and the
    calls announced and not yet sent."""

    name: ClassVar[str]
    client_name: ClassVar[str]
    measured_version: ClassVar[str]
    call_key: ClassVar[str]
    announcement_answer: ClassVar[Any]
    experimental: ClassVar[dict[str, dict[str, Any]]] = {}     # declared in `initialize`

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

        self.agents: dict[str, Agent] = {}
        # tool_use_id -> the agent the announcement named, or None where the
        # call names it; an entry whose call never comes stays, small and unique
        self._announced: dict[str, Agent | None] = {}
        # the MCP sessions checked, and whether each passed
        self._checked: weakref.WeakKeyDictionary[ServerSession, bool] = weakref.WeakKeyDictionary()
        self.client: types.Implementation | None = None     # the clientInfo that passed the check
        self._working_directory: Path | None = None  # `configure`'s: what the sandbox policy is checked against

        self._requests = 0                  # in flight, the standalone GET stream excepted
        self._idle = asyncio.Event()        # no request in flight
        self._idle.set()

        app: Server[Any, Any] = _App(self.experimental)
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
        before the port is bound (MODULE_STRUCTURE §4.6).  Each file replaces
        whatever stands at its name; one that cannot be written is a
        `TAT_StartupError`."""
        self._working_directory = working_directory
        files = {(AGENTS, name): text for name, text in self._client_files(working_directory).items()}
        files |= {(DOT_TAT, script): (Path(__file__).parent / script).read_text(encoding="utf-8")
                  for script in ("hook.py", "guard.py")}
        for (directory, name), text in files.items():
            try:
                _replaced(working_directory / directory, name, text)
            except OSError as e:
                raise TAT_StartupError(
                    f"TAT cannot write {working_directory / directory / name}: {e.strerror}") from e
        self.ending.log.conversation.configured(files=[f"{directory}/{name}" for directory, name in files])

    def _client_files(self, working_directory: Path) -> dict[str, str]:
        """The client's files, by name within the agent directory, each the
        text its format's one encoder gives (MODULE_STRUCTURE §4.6)."""
        raise NotImplementedError

    def _hook(self, working_directory: Path, script: str, matcher: str | None = None) -> dict[str, Any]:
        """One hook entry as both clients take it: the script run under the
        interpreter TAT's Python side runs under, each path quoted."""
        command = shlex.join([sys.executable, "-I", str(working_directory / DOT_TAT / script)])
        entry: dict[str, Any] = {} if matcher is None else {"matcher": matcher}
        entry["hooks"] = [{"type": "command", "timeout": HOOK_TIMEOUT, "command": command}]
        return entry

    # --- the agents (CONSTRUCT_INTERACTION §4, §8) ------------------------

    def _main_identity(self, payload: dict[str, Any]) -> str | None:
        """How the client names its main conversation in a hook payload,
        which carries no `agent_id` for it (CLIENT_HOOKS.md §2, §3); None
        when the payload does not say."""
        raise NotImplementedError

    def _identity(self, payload: dict[str, Any]) -> str | None:
        """The agent a hook payload names: `agent_id`, else the main
        conversation's."""
        agent_id = payload.get("agent_id")
        return str(agent_id) if agent_id else self._main_identity(payload)

    def event_of_hook(self, payload: dict[str, Any]) -> Announcement | None:
        """The client's JSON as an event (CONSTRUCT_INTERACTION §8): a
        `PreToolUse` on a TAT tool is the announcement of a call; every
        other hook is consumed — None.  Reads the payload and changes
        nothing; `_judge` acts on the event."""
        if (payload.get("hook_event_name") != "PreToolUse"
                or not str(payload.get("tool_name", "")).startswith(TOOL_PREFIX)):
            return None
        return Announcement(str(_field(payload, "tool_use_id")), self._identity(payload),
                            main=not payload.get("agent_id"))

    def _announcing_agent(self, event: Announcement) -> Agent | None:
        """The agent an announcement names, created at it when new; None on
        a client whose calls name their agent themselves."""
        raise NotImplementedError

    def _agent(self, identity: str, main: bool, first: Literal["call", "hook"]) -> Agent:
        """The agent so named, created when its first call or hook reaches
        TAT (CONSTRUCT_INTERACTION §4) and never discarded."""
        agent = self.agents.get(identity)
        if agent is None:
            agent = self.agents[identity] = Agent(identity, main)
            self.ending.log.agent.created(identity=identity, main=main, first=first)
        return agent

    def call_id(self, meta: types.RequestParams.Meta | None) -> str | None:
        """The client's id of a tool call, under the subclass's key of its
        `_meta`; None when the call carries none."""
        return _text(_extra(meta).get(self.call_key))

    def _take_announcement(self, meta: types.RequestParams.Meta | None) -> tuple[bool, Agent | None]:
        """Whether an announcement named this call, and the agent it named
        when the client's announcements name one; the announcement is
        spent, so a second call under it is unannounced."""
        call_id = self.call_id(meta)
        if call_id is None or call_id not in self._announced:
            return False, None
        return True, self._announced.pop(call_id)

    def agent_of_call(self, meta: types.RequestParams.Meta | None) -> Agent | None:
        """The agent making the call its `_meta` belongs to; None when no
        announcement named the call — TAT never guesses
        (CONSTRUCT_INTERACTION §8)."""
        raise NotImplementedError

    # --- the client (CONSTRUCT_INTERACTION §8) ----------------------------

    def _check_client(self, session: ServerSession) -> None:
        """At the first request of an MCP session that reaches TAT: its
        `clientInfo` against the client `-c` chose and the version TAT's
        facts were measured on; a session that fails is refused, which ends
        the conversation.  Nothing once the ending is entered."""
        if self.ending.entered or session in self._checked:
            return
        if session.client_params is None:   # the SDK serves no request before `initialize`
            self.ending.end(TAT_InternalError("a request reached TAT before its session's initialize"))
            return
        client = session.client_params.clientInfo
        passes = (client.name == self.client_name
                  and _version_numbers(client.version) >= _version_numbers(self.measured_version))
        self._checked[session] = passes
        if passes:
            self.client = client
            self.ending.log.conversation.client_connected(name=client.name, version=client.version)
        else:
            self._refuse(f"TAT cannot serve this client: it is {client.name} {client.version}; "
                         f"TAT requires {self.name} {self.measured_version} or newer.",
                         "a client TAT does not serve connected", client)

    def _refuse(self, message: str, reason: str, client: types.Implementation | None = None,
                meta: Any = None) -> None:
        """The one way a client is refused (CONSTRUCT_INTERACTION §8): the
        `client_refused` record — for the `clientInfo` given, else the one
        that passed the check — then the ending entered with the
        `ClientRefused`: `message` for the launcher, `reason` completing
        the line of RENDER_BASELINES §4 every tool call is answered
        meanwhile, `meta` the call's when a call's policy refused."""
        info = client or self.client or types.Implementation(name="", version="")
        self.ending.log.conversation.client_refused(
            name=info.name, version=info.version, message=message, _meta=meta)
        self.ending.end(ClientRefused(message, stopped_for(reason)))

    def _caller(self, meta: types.RequestParams.Meta | None) -> Agent | None:
        """The agent making this call, `current_agent` set to it; None once
        the ending is entered, or when no announcement named the call."""
        agent = self.agent_of_call(meta) if not self.ending.entered else None
        if agent is not None:
            current_agent.set(agent.identity)
        return agent

    def _check_sandbox(self, session: ServerSession, meta: types.RequestParams.Meta | None) -> None:
        """At every tool call, the sandbox the client runs its agents in,
        where the client tells it (CLIENT_HOOKS.md §5): Codex does, Claude
        Code does not."""

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
        if scope["path"] == HOOK:
            await self._counted(self._hook_request(scope, receive, send))
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

    async def _post(self, scope: dict[str, Any], receive: Any, send: Any) -> Request | None:
        """A request on a path of TAT's own: the transport check as for
        `/mcp` — `Host` and `Origin`, no content type — and POST alone;
        None when it was answered here."""
        request = Request(scope, receive)
        refused = await self._security.validate_request(request, is_post=False)
        if refused is not None:
            await refused(scope, receive, send)
            return None
        if scope["method"] != "POST":
            await _answer(send, 405, b"", "text/plain")
            return None
        return request

    async def _hook_request(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """`POST /hook` (MODULE_STRUCTURE §4.6; CLIENT_HOOKS.md §1): the
        payload read, the agent and the call it names set for the records
        (LOGGING.md §3), the payload recorded, then in one synchronous step
        under no lock the ending tested — an empty 503 while the
        conversation is ending — and the event judged, its answer the
        client's JSON or nothing; anything the judgement raises, a payload
        that is no JSON object included, enters the ending and is answered
        an empty 500."""
        started = time.monotonic()
        request = await self._post(scope, receive, send)
        if request is None:
            return
        body = await request.body()
        try:
            payload: Any = json.loads(body)
        except ValueError:
            payload = body.decode(errors="replace")
        if isinstance(payload, dict):
            current_agent.set(self._identity(payload))
            current_call.set(_text(payload.get("tool_use_id")))
        log = self.ending.log.hook
        log.request(payload=payload)
        judged: Judged | None = None
        answer = None
        if self.ending.entered:
            status = 503
        else:
            try:
                if not isinstance(payload, dict):
                    raise TAT_InternalError("the hook's payload is not a JSON object")
                judged, answer = self._judge(payload)
                status = 200
            except Exception as bug:
                self.ending.end(bug)
                status = 500
        if answer is None:
            await _answer(send, status, b"", "text/plain")
        else:
            await _answer(send, status, json.dumps(answer).encode(), "application/json")
        log.answer(judged=judged, status=status, body=answer, duration=time.monotonic() - started)

    def _judge(self, payload: dict[str, Any]) -> tuple[Judged, Any]:
        """What the hook is and what it is answered (CLIENT_HOOKS.md §1's
        table): an announcement records the call for `agent_of_call`; one
        of a call still announced and not arrived is a bug of the path."""
        event = self.event_of_hook(payload)
        if event is None:
            return "ignored", None
        if event.tool_use_id in self._announced:
            raise TAT_InternalError(second_announcement(event.tool_use_id))
        self._announced[event.tool_use_id] = self._announcing_agent(event)
        return "announcement", self.announcement_answer

    async def _compaction(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """`POST /on-compaction?client=<name>` (MODULE_STRUCTURE §4.6): an
        unknown client refused before anything is touched; an empty 503
        while the conversation is ending, which touches no forest; then
        the closure once, its answer in the client's shape — or, if it
        raises, the conversation's ending and an empty 500, so the hook
        reports a failure and nothing half-rendered reaches the agent."""
        if await self._post(scope, receive, send) is None:
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
        session = request_ctx.get().session
        self._check_client(session)
        if self._checked.get(session) is False:
            return []                       # no tool is served to a refused client
        return [types.Tool(name=tool.name, description=tool.description,
                           inputSchema=tool.input_schema,
                           annotations=types.ToolAnnotations(readOnlyHint=tool.read_only))
                for tool in self._tools.values()]

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        """Every call writes `call`, then exactly one of `result`,
        `given_up` and `while_ending` (LOGGING.md §4), each carrying the
        call's id and its agent (§3), both set before `call` is written —
        the id so that a `while_ending` carries it too.  The client's
        checks come first, their records belonging to no call.  A call no
        announcement named ends the conversation (CONSTRUCT_INTERACTION
        §8).  The SDK runs each request in a task of its own, so the two
        context variables are this call's alone and need no reset."""
        context = request_ctx.get()
        self._check_client(context.session)
        if not self.ending.entered:
            self._check_sandbox(context.session, context.meta)
        current_call.set(self.call_id(context.meta))
        agent = self._caller(context.meta)
        log = self.ending.log.tool
        log.call(tool=name, arguments=arguments)
        if agent is None and not self.ending.entered:
            log.unannounced(tool=name, _meta=_dumped(context.meta), message=UNANNOUNCED)
            self.ending.end(TAT_InternalError(UNANNOUNCED))
        started = time.monotonic()
        tool = self._tools.get(name)
        if agent is None:
            result: Result | None = None    # the ending answers
        elif tool is None:
            result = Result(f"unknown tool `{name}`", True, None)
        else:
            # The body runs as a task of its own, outside the request's
            # cancel scope, and the wait is shielded: neither a client's
            # cancellation nor the SDK's unwind reaches it mid-edit.
            # `asyncio.wait` never cancels what it waits on.  The agent's
            # working-call count holds for exactly as long (CONSTRUCT_INTERACTION §4).
            with agent.working():
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
    name = "claude-code"
    client_name = "claude-code"
    measured_version = "2.1.286"
    call_key = "claudecode/toolUseId"
    announcement_answer = ALLOW             # the grant, without which Claude Code refuses the call under -p
    main_identity = "main"                  # LOGGING.md §3

    def _main_identity(self, payload: dict[str, Any]) -> str:
        return self.main_identity

    def _announcing_agent(self, event: Announcement) -> Agent:
        """The announcement names the agent: `agent_id`, or the main
        conversation (CLIENT_HOOKS.md §2)."""
        return self._agent(event.identity or self.main_identity, event.main, first="hook")

    def agent_of_call(self, meta: types.RequestParams.Meta | None) -> Agent | None:
        return self._take_announcement(meta)[1]

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
                "PreToolUse": [hook("hook.py", TOOL_PREFIX + ".*"), hook("hook.py", "TaskStop"),
                               hook("guard.py", "Write|Edit|NotebookEdit|MultiEdit"),
                               hook("guard.py", "Agent|Task")],
                "Stop": [hook("hook.py")],
                "SubagentStop": [hook("hook.py")],
                "PostCompact": [hook("hook.py")],
                "WorktreeCreate": [hook("guard.py")]}}
        return {".mcp.json": _json({"mcpServers": {SERVER_NAME: {"type": "http", "url": self.url,
                                                                 "timeout": 43_200_000}}}),
                ".claude/settings.json": _json(settings)}


class Codex_Server(TAT_Server):
    name = "codex"
    client_name = "codex-mcp-client"
    measured_version = "0.156.1"
    call_key = "callId"
    announcement_answer = None              # Codex rejects a bare `allow`; nothing is needed
    experimental = {SANDBOX_STATE: {}}      # under which Codex sends the policy in force with every call

    def _main_identity(self, payload: dict[str, Any]) -> str | None:
        return _text(payload.get("session_id"))     # the main conversation's own thread id

    def _announcing_agent(self, event: Announcement) -> None:
        """The announcement names no agent: the call does, by its thread
        (CLIENT_HOOKS.md §3)."""
        return None

    def agent_of_call(self, meta: types.RequestParams.Meta | None) -> Agent | None:
        """The thread the call's `_meta.threadId` names (CONSTRUCT_INTERACTION
        §8), the main conversation when it is the session's own; created
        at the call."""
        announced, _ = self._take_announcement(meta)
        thread = _text(_extra(meta).get("threadId"))
        if not announced or thread is None:
            return None
        return self._agent(thread, main=thread == _text(_extra(meta).get("sessionId")), first="call")

    def _check_sandbox(self, session: ServerSession, meta: types.RequestParams.Meta | None) -> None:
        """The policy in force comes with every call under `SANDBOX_STATE`; a
        call whose policy is not the profile TAT configured — one without
        the key included — refuses the session (CLIENT_HOOKS.md §5,
        CONSTRUCT_INTERACTION §8)."""
        if self._working_directory is None or session.client_params is None:
            self.ending.end(TAT_InternalError("a call reached TAT before configure, or before initialize"))
            return
        if not sandbox_is_the_profile(_extra(meta).get(SANDBOX_STATE), self._working_directory):
            self._refuse(f"TAT refuses this Codex session: its sandbox is not the one TAT configured. "
                         f"Start Codex in {self._working_directory / AGENTS} without a sandbox option.",
                         "Codex's sandbox is not the one TAT configured",
                         session.client_params.clientInfo, meta=_dumped(meta))

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
            f"[mcp_servers.{SERVER_NAME}]",
            f"url = {toml_string(self.url)}",
            "tool_timeout_sec = 43200",
            'default_tools_approval_mode = "approve"',
            ""]
        hook = self._hook(working_directory, "hook.py")
        hooks = {"hooks": {
            "PreToolUse": [self._hook(working_directory, "hook.py", TOOL_PREFIX + ".*"),
                           self._hook(working_directory, "hook.py", "collaborationinterrupt_agent")],
            "Stop": [hook], "SubagentStop": [hook], "SessionStart": [hook],
            "PreCompact": [hook], "PostCompact": [hook]}}
        return {".codex/config.toml": "\n".join(config), ".codex/hooks.json": _json(hooks)}


def _json(value: Any) -> str:
    return json.dumps(value, indent=2) + "\n"


# The subclass for each name `isabelle TAT_mcp -c` takes; the launcher
# refuses any other (MODULE_STRUCTURE §5).
SERVERS: dict[str, type[TAT_Server]] = {cls.name: cls for cls in (Claude_Code_Server, Codex_Server)}


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
