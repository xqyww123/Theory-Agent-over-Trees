"""The harness of the Isabelle-backed cases (ai-artifacts/TEST_HARNESS_PLAN.md
§3, §4): one RPC host in the test process, one `isabelle TAT_mcp` per run, a
fresh conversation per case through `TAT.reset`.  `conftest.py` builds one
`Harness` inside the session-scoped fixture and hands each case a `Handle`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import subprocess
import traceback
import uuid
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any, NoReturn

import anyio
import httpx
from Isabelle_RPC_Host import Connection, Server, isabelle_remote_procedure
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client

from isabelle_theory_agent import isabelle_driver, toplevel
from isabelle_theory_agent.mcp_server import HOOK, HOST, PATH, TOOL_PREFIX, Claude_Code_Server, Ending

PLUGIN = "Theory_Agent_over_Trees.Test_TAT_Framework"
PACKAGES = ["tat_test_plugin"]          # what the plugin's registrations name, deduplicated
DEADLINE = 120.0                        # a case's, in seconds; the marker may override it
STARTUP = 900.0                         # the first run on a machine may build the base heap
TERMINATION = 10.0                      # a child that outlived SIGINT: after SIGTERM, before SIGKILL

# The client the suite is: Claude Code, at the version the subclass requires,
# its main conversation announcing every call (CONSTRUCT_INTERACTION §8).
CLIENT_INFO = types.Implementation(name=Claude_Code_Server.client_name,
                                   version=Claude_Code_Server.measured_version)
SESSION_ID = "6c1f0e4a-2b7d-4f3e-9a58-0d2c7b1e8f90"            # invented, as the payloads' other ids
TRANSCRIPT_PATH = f"/home/agent/.claude/projects/-work-TAT-agents/{SESSION_ID}.jsonl"   # named, not read


def free_port() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


# A process the harness starts leads a process group of its own
# (`start_new_session`), so that a signal reaches the JVM and its Isabelle
# process together, and takes `SIGINT` as a terminal's foreground process
# does: this is its `preexec_fn`.
def default_sigint() -> None:
    signal.signal(signal.SIGINT, signal.SIG_DFL)


def signal_group(process: subprocess.Popen[Any], sig: int) -> None:
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:              # the group is gone already
        pass


def group_alive(process: subprocess.Popen[Any]) -> bool:
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return False
    return True


async def end_group(process: subprocess.Popen[Any], exited: asyncio.Future[Any]) -> None:
    """A group that outlived its wait after `SIGINT`: terminated — the
    JVM's shutdown hook then running Isabelle's own termination of the ML
    process's group — and killed if it outlives that too, so that the run
    always ends."""
    signal_group(process, signal.SIGTERM)
    with anyio.move_on_after(TERMINATION):
        await asyncio.wait({exited})
    if group_alive(process):
        signal_group(process, signal.SIGKILL)
    await asyncio.wait({exited})                # unbounded: the waiting thread must end


def hook_url(url: str) -> str:
    """`/hook` beside the endpoint `url`."""
    return url.removesuffix(PATH) + HOOK


async def announce(url: str, payload: Any) -> httpx.Response:
    """One hook payload posted to `/hook` as the hook script does
    (CLIENT_HOOKS.md §1)."""
    async with httpx.AsyncClient() as http:
        return await http.post(url, json=payload)


class Announcing_Session(ClientSession):
    """An `mcp` client session that announces each tool call to `/hook`
    the way Claude Code's main conversation does — a `PreToolUse` payload
    in the measured shape, with an invented `tool_use_id` — and then sends
    the call with the matching `_meta` (CONSTRUCT_INTERACTION §8).  An
    announcement the ending answers 503 does not stop the call, as it does
    not stop an interactive client whose user allows it: the call is sent,
    and the ending answers it (RENDER_BASELINES §4)."""

    def __init__(self, read: Any, write: Any, url: str, **kwargs: Any):
        super().__init__(read, write, **kwargs)
        self._hook_url = hook_url(url)

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None,
                        read_timeout_seconds: Any = None, progress_callback: Any = None, *,
                        meta: dict[str, Any] | None = None) -> types.CallToolResult:
        tool_use_id = "toolu_" + uuid.uuid4().hex
        answer = await announce(self._hook_url, {
            "session_id": SESSION_ID, "transcript_path": TRANSCRIPT_PATH, "cwd": "/work/TAT.agents",
            "permission_mode": "default", "hook_event_name": "PreToolUse",
            "tool_name": TOOL_PREFIX + name, "tool_input": arguments or {}, "tool_use_id": tool_use_id,
            "mcp_server": {"name": "TAT", "source": "dynamic"}})
        assert answer.status_code in (200, 503), (answer, answer.text)
        return await super().call_tool(name, arguments, read_timeout_seconds, progress_callback,
                                       meta={Claude_Code_Server.call_key: tool_use_id, **(meta or {})})


@asynccontextmanager
async def client(url: str, client_info: types.Implementation = CLIENT_INFO
                 ) -> AsyncGenerator[ClientSession]:
    """An initialised `mcp` client session on the endpoint, stating
    `client_info` and announcing its calls."""
    async with streamable_http_client(url) as (read, write, _):
        async with Announcing_Session(read, write, url, client_info=client_info) as session:
            await session.initialize()
            yield session


def text_of(result) -> str:
    """A tool result's text; one text block is what every tool answers."""
    assert len(result.content) == 1 and result.content[0].type == "text", result.content
    return result.content[0].text


class Next(BaseException):
    """`Harness.await_ending` ends the conversation the harness is serving;
    the loop goes round.  The only ending that does."""


class Suite_Over(Exception):
    """The suite has run its last Isabelle-backed case: the loop's end,
    through the product's own ending chain (an `Exception`, which the host
    writes back to the ML side as its traceback)."""


class Run_Ended(Exception):
    """The Isabelle-backed part of the run ended for another reason: the
    cause is `__cause__`, the text names the case and carries the child's
    output as it stands when the exception is rendered.  Every wait of the
    harness raises it first."""

    def __init__(self, text: str, output: Callable[[], str]):
        super().__init__(text)
        self.text, self.output = text, output

    def __str__(self) -> str:
        return f"{self.text}\n--- isabelle TAT_mcp's output ---\n{self.output()}"


class Request:
    """One conversation: its working directory, the case's node id and the
    two settlements — the hand-over, which the case's setup awaits, and
    `ended`, which its teardown awaits; both carry success values only."""

    def __init__(self, working_directory: Path, nodeid: str):
        loop = asyncio.get_running_loop()
        self.working_directory = working_directory
        self.nodeid = nodeid
        self.handed_over: asyncio.Future[Handle] = loop.create_future()
        self.ended: asyncio.Future[None] = loop.create_future()
        self.successor: Handle | None = None    # the handle `restart()` returned


class Handle:
    """What a case gets.  Every attribute is read through one guard: a
    handle has ended exactly when its request is no longer the one the
    harness is serving, and then every read raises — the recorded
    `Run_Ended` when there is one, else a sentence naming the successor."""

    def __init__(self, harness: Harness, request: Request, **fields: Any):
        self.__dict__.update(_harness=harness, _request=request, _fields=fields)

    def _live(self) -> tuple[Harness, Request]:
        harness, request = self.__dict__["_harness"], self.__dict__["_request"]
        if harness.serving is None or harness.serving[0] is not request:
            harness.raise_if_ended()
            raise RuntimeError("this conversation has ended"
                               + ("; use the handle `restart()` returned"
                                  if request.successor is not None else ""))
        return harness, request

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        self._live()
        try:
            return self.__dict__["_fields"][name]
        except KeyError:
            raise AttributeError(name) from None

    @asynccontextmanager
    async def client(self) -> AsyncGenerator[ClientSession]:
        async with client(self.url) as session:
            yield session

    async def restart(self) -> Handle:
        """End this conversation, and once it has ended — the directory's
        lock is released only then — begin the next on the same working
        directory (ARCHITECTURE §9): the returned handle's."""
        harness, request = self._live()
        await harness.await_ending()
        request.successor = await harness.converse(request.working_directory, request.nodeid)
        return request.successor


class Harness:
    """One per run.  Holds everything shared — the host, its `run_server`
    task, the child and its exit task, the request queue, the record of the
    end of the Isabelle-backed part of the run — as attributes; nothing
    lives at module scope."""

    def __init__(self, logger: logging.Logger, directory: Path):
        loop = asyncio.get_running_loop()
        self.logger = logger
        self.launcher_directory = directory / "launcher"    # what `isabelle TAT_mcp` is started on
        self.log_path = directory / "isabelle_TAT_mcp.log"
        self.port = free_port()                             # the conversations' MCP port
        self.host_address = f"{HOST}:{free_port()}"         # the RPC host's
        self.requests: asyncio.Queue[Request | None] = asyncio.Queue()
        self.launched: asyncio.Future[None] = loop.create_future()
        self.run_end: asyncio.Future[BaseException] = loop.create_future()   # the record
        self.serving: tuple[Request, Ending] | None = None
        self.last_taken: Request | None = None              # the request the loop took last
        self.server = Server(self.host_address, logger)
        self.server_task: asyncio.Task[None] | None = None
        self.child: subprocess.Popen[bytes] | None = None
        self.child_exit: asyncio.Task[int] | None = None

    # -- the record of the end of the Isabelle-backed part of the run --------

    def end_run(self, cause: BaseException) -> None:
        """Enter the record; the first entry wins.  Any cause but `Suite_Over`
        also ends the conversation being served and signals the child: the
        run has failed, and a signal is the only thing that stops a running
        ML callback."""
        if self.run_end.done():
            return
        if isinstance(cause, Suite_Over):
            self.run_end.set_result(cause)
            return
        taken = self.last_taken
        if taken is None:
            when = "before any conversation"
        elif not taken.handed_over.done():
            when = f"while beginning {taken.nodeid}'s conversation"
        elif not taken.ended.done():
            when = f"during {taken.nodeid}"
        else:
            when = f"between conversations, after {taken.nodeid}"
        ended = Run_Ended(f"the Isabelle-backed part of the run ended {when}: "
                          f"{type(cause).__name__}: {cause}", self.child_output)
        ended.__cause__ = cause
        self.run_end.set_result(ended)
        self.end_conversation(ended)
        self.signal_child(signal.SIGINT)

    def raise_if_ended(self) -> None:
        """Raise the recorded `Run_Ended`, if there is one — afresh, so that
        its traceback does not grow with every case that reports it."""
        if self.run_end.done() and isinstance(self.run_end.result(), Run_Ended):
            raise self.run_end.result().with_traceback(None)

    def _child_done(self, task: asyncio.Task[int]) -> None:
        try:
            if task.cancelled():
                return
            self.end_run(RuntimeError(f"isabelle TAT_mcp exited with code {task.result()}"))
        except Exception:                       # a done-callback must not raise
            self.logger.exception("the child's exit could not be recorded")

    def _server_done(self, task: asyncio.Task[None]) -> None:
        try:
            if not task.cancelled() and task.exception() is not None:
                self.end_run(RuntimeError(f"the host could not serve on {self.host_address}: "
                                          f"{task.exception()!r}"))
        except Exception:
            self.logger.exception("the host's failure could not be recorded")

    # -- the two helpers -------------------------------------------------------

    async def wait(self, settlement: asyncio.Future[Any]) -> Any:
        """The only way the harness waits for a settlement: raced against
        the record, which wins when it holds `Run_Ended`; the settlement is
        never awaited directly (a deadline would cancel it)."""
        await asyncio.wait({settlement, self.run_end}, return_when=asyncio.FIRST_COMPLETED)
        self.raise_if_ended()
        return settlement.result()

    @contextmanager
    def deadline(self, seconds: float, what: str) -> Generator[None]:
        """Every deadline: an expiry enters the record and is raised, one
        `TimeoutError` naming what expired."""
        with anyio.move_on_after(seconds) as scope:
            yield
        if scope.cancelled_caught:
            expired = TimeoutError(f"{what} did not finish within {seconds:g} s")
            self.end_run(expired)
            raise expired

    # -- the conversation the harness is serving -------------------------------

    def end_conversation(self, ended_by: BaseException) -> Request | None:
        """End the conversation being served, if any, and answer its
        request; waiting on its `ended` is the caller's business."""
        if self.serving is None:
            return None
        request, ending = self.serving
        ending.end(ended_by)
        return request

    async def await_ending(self) -> None:
        """End the conversation being served with `Next` and wait until it
        has ended — the case's teardown, and the first half of `restart()`."""
        request = self.end_conversation(Next())
        if request is None:
            self.raise_if_ended()
            raise AssertionError("no conversation is being served")
        with self.deadline(DEADLINE, f"the ending of {request.nodeid}'s conversation"):
            await self.wait(request.ended)

    async def converse(self, working_directory: Path, nodeid: str) -> Handle:
        """The next conversation, on the directory given, for the case named."""
        self.raise_if_ended()
        request = Request(working_directory, nodeid)
        self.requests.put_nowait(request)
        with self.deadline(DEADLINE, f"the hand-over to {nodeid}"):
            return await self.wait(request.handed_over)

    # -- the procedure -----------------------------------------------------------

    async def launch_TAT(self, arg: list[Any], connection: Connection) -> NoReturn:
        """What the ML side calls under the product's wire name: one
        conversation per request, `TAT.reset` first, until the suite is over."""
        # the wire delivers a list; the child is started without -c, so the
        # default client arrives
        packages, launcher_directory, port, client, max_concurrent_construction_jobs = arg
        assert packages == PACKAGES, packages
        assert (launcher_directory, port, client) == \
            (str(self.launcher_directory), self.port, "claude-code"), (launcher_directory, port, client)
        self.launched.set_result(None)
        try:
            while True:
                request = await self.requests.get()
                if request is None:
                    raise Suite_Over("the suite has run its last Isabelle-backed case")
                self.last_taken = request
                try:
                    await isabelle_driver.reset(connection)
                    async with toplevel.served(packages, str(request.working_directory), port, client,
                                               max_concurrent_construction_jobs, connection
                                               ) as (forest, loaded, server):
                        self.serving = (request, forest.conversation.ending)
                        request.handed_over.set_result(Handle(
                            self, request, forest=forest, kinds=loaded.kinds, url=server.url,
                            working_directory=request.working_directory,
                            log=forest.conversation.log))
                        await server.serve()
                except Next:
                    pass
                finally:                                    # no await here
                    self.serving = None
                request.ended.set_result(None)              # the Next path only
        except BaseException as cause:
            self.end_run(cause)
            raise

    # -- the three stages: their starts, and their releases in reverse (§4) ------

    def start_host(self) -> None:
        """Stage 1: the host serving, and the harness's `launch_TAT` under
        the product's wire name.  Released by the `Server`'s own context
        manager."""
        self.server_task = asyncio.ensure_future(self.server.run_server())
        self.server_task.add_done_callback(self._server_done)
        isabelle_remote_procedure("launch_TAT")(self.launch_TAT)

    async def start_child(self) -> None:
        """Stage 2: `isabelle TAT_mcp` on a directory that carries the plugin
        list, its output to one log, its exit as a task."""
        await asyncio.to_thread(subprocess.run,
                                ["isabelle", "TAT_new", "-P", PLUGIN, str(self.launcher_directory)],
                                check=True)
        with self.log_path.open("wb") as log:
            self.child = subprocess.Popen(
                ["isabelle", "TAT_mcp", "-p", str(self.port), str(self.launcher_directory)],
                stdout=log, stderr=subprocess.STDOUT,
                env={**os.environ, "RPC_Host": self.host_address},
                start_new_session=True, preexec_fn=default_sigint)
        self.child_exit = asyncio.ensure_future(asyncio.to_thread(self.child.wait))
        self.child_exit.add_done_callback(self._child_done)

    async def run_tool(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        """An `isabelle` tool of a case's own, beside the child and on the
        run's RPC host, in a process group of its own.  When the caller's
        wait ends first — the case's deadline — the group is ended as the
        child's is; nothing may be left in it either way."""
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   env={**os.environ, "RPC_Host": self.host_address},
                                   start_new_session=True, preexec_fn=default_sigint)
        exited = asyncio.ensure_future(asyncio.to_thread(process.communicate))
        try:
            output, errors = await asyncio.shield(exited)
        except BaseException:
            with anyio.CancelScope(shield=True):
                signal_group(process, signal.SIGINT)
                with anyio.move_on_after(TERMINATION):
                    await asyncio.wait({exited})
                if not exited.done():
                    await end_group(process, exited)
            raise
        assert not group_alive(process), f"a process is left in the group of {argv}"
        return subprocess.CompletedProcess(argv, process.returncode, output, errors)

    async def await_launch(self) -> None:
        """Stage 3: the harness's `launch_TAT` called.  The child's exit and
        a `run_server` failure reach the record and end this wait as
        themselves; an expiry is reported as the record too, with the
        child's output."""
        try:
            with self.deadline(STARTUP, "isabelle TAT_mcp's start"):
                await self.wait(self.launched)
        except TimeoutError:
            self.raise_if_ended()
            raise

    def child_output(self) -> str:
        try:
            return self.log_path.read_text(errors="replace")
        except OSError:
            return ""

    def signal_child(self, sig: int) -> None:
        if self.child is not None:              # None: a host that could not bind, no child yet
            signal_group(self.child, sig)

    async def await_child(self, what: str) -> int:
        """The child's exit — not a settlement: waited on alone, whatever
        the record holds, so that after `Run_Ended` the child is still waited
        for and checked."""
        assert self.child_exit is not None
        with self.deadline(DEADLINE, what):
            await asyncio.wait({self.child_exit})
        return self.child_exit.result()

    async def release_run(self) -> None:
        """Stage 3's: the run's end through the product's ending chain."""
        self.raise_if_ended()
        self.requests.put_nowait(None)
        rc = await self.await_child("isabelle TAT_mcp's exit after the suite")
        self.raise_if_ended()
        over = self.run_end.result()
        echoed = "*** " + traceback.format_exception_only(over)[-1].rstrip("\n")
        output = self.child_output()
        assert rc == 2 and echoed in output, (rc, output)       # an exception: 2 (MODULE_STRUCTURE §5)

    async def release_child(self) -> None:
        """Stage 2's: a child still alive is signalled and waited for —
        `SIGINT`, as at a terminal; a child that outlives the wait is
        ended (`end_group`).  Nothing may be left in the child's process
        group."""
        assert self.child is not None and self.child_exit is not None
        if not self.child_exit.done():
            self.signal_child(signal.SIGINT)
            try:
                await self.await_child("isabelle TAT_mcp's exit after SIGINT")
            except TimeoutError as expired:
                await end_group(self.child, self.child_exit)
                raise expired
        assert not group_alive(self.child), "a process is left in isabelle TAT_mcp's group"