"""The two RPC entry points Isabelle calls into (MODULE_STRUCTURE §4.6).

`TAT_Framework.start` on the ML side calls the procedure `launch_TAT`, which
builds the conversation and serves until its ending; it does not return
(ARCHITECTURE §9): everything the conversation does, it does through this
call's callbacks, and the call ends only by raising what ended the
conversation.  `TAT_Framework.compile` calls `compile_TAT`, which writes
the stored forest and returns (COMPILATION.md §5).  The start is three
layers of context managers: `conversation()` is the first two, which a
compile shares; `served()` adds the third, the server.
"""

from __future__ import annotations

import fcntl
import os
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import asynccontextmanager, contextmanager
from importlib.metadata import version
from pathlib import Path
from typing import NoReturn

from Isabelle_RPC_Host import Connection, isabelle_remote_procedure

from . import isabelle_driver, mcp, plugin
from .compile import compile, report_lines
from .exceptions import TAT_StartupError
from .log import Log, now
from .mcp_server import DOT_TAT, SERVERS, Ending, TAT_Server, _bind, agent_directory
from .model import Conversation, Forest
from .store import SCHEMA_VERSION, Forest_Store

DATABASE = "TAT.sqlite"                 # the launcher's, shared with the plugins table (§5)
LOCK = "tat.lock"
LOG = Path(DOT_TAT) / "log"             # the logs' directory, under the working directory (LOGGING.md §2)

Announce = Callable[[int], None]        # the lock's port line, written once the server listens


@contextmanager
def _held(working_directory: Path) -> Generator[Announce]:
    """The working directory's lock: an exclusive `flock` on a descriptor
    kept open for the life of the conversation or the compile, so the
    kernel releases it when the process dies and the `finally` when it
    ends any other way.  `flock`, not a POSIX record lock, because only
    `flock` conflicts between two descriptors in one process — what
    refuses a second holder in this host as well as in another.  The holder
    writes its pid into the file when it takes the lock and, a conversation
    only, through the `announce` it yields, its port once the server is
    listening, one line each, and clears the file on release; each reader
    takes the line it needs — the refusal here the first, the hooks of
    CLIENT_HOOKS.md the second, and the first to see the holder is alive.
    Between taking the lock and writing, the file is still empty or still
    a crashed holder's, and between clearing it on release and closing the
    descriptor it is empty."""
    try:
        fd = os.open(working_directory / LOCK, os.O_RDWR | os.O_CREAT, 0o644)
    except OSError as e:
        raise TAT_StartupError(
            f"TAT cannot use {working_directory} as its working directory: {e.strerror}") from e
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            holder = os.pread(fd, 64, 0).decode(errors="replace").split("\n")[0].strip()
            raise TAT_StartupError(
                f"{working_directory} is held by another TAT conversation or compile"
                + (f" (its Python process is pid {holder})" if holder.isdigit() else "")) from e
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())

        def announce(port: int) -> None:
            os.write(fd, f"{port}\n".encode())      # the descriptor stands after the pid line

        try:
            yield announce
        finally:
            os.ftruncate(fd, 0)
    finally:
        os.close(fd)


def _log_directory(working_directory: Path) -> Path:
    """A fresh directory under `.tat/log/`, named by this moment and made
    exclusively, under the lock (LOGGING.md §2)."""
    try:
        (working_directory / LOG).mkdir(parents=True, exist_ok=True)
        directory = working_directory / LOG / now().replace(":", "-")
        directory.mkdir()
    except OSError as e:
        raise TAT_StartupError(
            f"TAT cannot write its log under {working_directory}: {e.strerror}") from e
    return directory


def _max_concurrent_construction_jobs(text: str) -> int | None:
    """The bound on the construction jobs running at once, from the text of
    `TAT_MAX_CONCURRENT_CONSTRUCTION_JOBS` as the Isabelle side read it
    (MODULE_STRUCTURE §4.6): empty is no bound, and any other text that is
    not a positive integer refuses the start."""
    if text == "":
        return None
    if not (text.isascii() and text.isdecimal()) or int(text) == 0:
        raise TAT_StartupError("TAT requires TAT_MAX_CONCURRENT_CONSTRUCTION_JOBS to be a positive "
                               f"integer, but it is {text}")
    return int(text)


@asynccontextmanager
async def conversation(python_packages: list[str], working_directory: str, connection: Connection,
                       port: int | None = None, client: str | None = None,
                       max_concurrent_construction_jobs: int | None = None, read_only: bool = False
                       ) -> AsyncGenerator[tuple[Forest, plugin.Loaded, Announce]]:
    """The first two layers of the start (MODULE_STRUCTURE §4.6), which a
    conversation and a compile share, torn down in reverse when the block
    ends: the lock; the log directory and the `Log`; the ending object,
    which whatever escapes from here on enters; the `Conversation`; then
    the store — `read_only` for a compile — the plugins and the `Forest`.
    `port`, `client` and the bound are a conversation's, the first two
    recorded in `start`; a compile has none.  Yields the `Forest`, the
    loaded plugins and the lock's `announce` for the third layer."""
    directory = Path(working_directory)
    with _held(directory) as announce:
        log = Log(_log_directory(directory), connection.server.logger)
        async with Ending(log) as ending:
            conv = Conversation(connection, directory, log, ending,
                                max_concurrent_construction_jobs=max_concurrent_construction_jobs)
            log.conversation.start(
                version=version("isabelle_theory_agent"), pid=os.getpid(),
                working_directory=str(directory), python_packages=python_packages, port=port,
                client=client)
            await isabelle_driver.log_directory(conv, log.directory)
            with Forest_Store(directory / DATABASE, log, read_only=read_only) as store:
                log.conversation.store_opened(schema_version=SCHEMA_VERSION, nodes=len(store.nodes()))
                loaded = plugin.load(python_packages)
                log.conversation.plugins_loaded(
                    kinds={kind: cls.__module__ for kind, cls in loaded.kinds.items()})
                forest = Forest(conv, store, loaded.kinds, loaded.imports)
                ending.forest = forest
                yield forest, loaded, announce


@asynccontextmanager
async def served(python_packages: list[str], working_directory: str, port: int, client: str,
                 max_concurrent_construction_jobs: str, connection: Connection
                 ) -> AsyncGenerator[tuple[Forest, plugin.Loaded, TAT_Server]]:
    """All three layers: a conversation; the port bound, 0 for one the
    system assigns; its server — the `TAT_Server` subclass `client` names
    — which writes the client's files and accepts, the bound port then
    announced in the lock and the Isabelle side told.  Whoever holds the
    block serves it.  The bound's text is checked first, before anything
    is touched."""
    bound = _max_concurrent_construction_jobs(max_concurrent_construction_jobs)
    async with conversation(python_packages, working_directory, connection, port, client, bound
                            ) as (forest, loaded, announce):
        with _bind(port) as sock:           # the port is TAT's from here on: the files name its URL
            server = SERVERS[client](forest.conversation.ending, sock, mcp.tools(forest, loaded),
                                     forest.conversation.agents)
            server.configure(forest.conversation.working_directory)
            async with server:
                announce(server.port)       # accepting: the hooks may call
                forest.conversation.log.conversation.serving(url=server.url)
                # the launcher starts the client on this message, after the port line
                agents = agent_directory(forest.conversation.working_directory)
                await isabelle_driver.serving(forest.conversation, server.url, agents,
                                              server.launch_arguments(agents))
                yield forest, loaded, server


@isabelle_remote_procedure("launch_TAT")
async def launch_TAT(arg: tuple[list[str], str, int, str, str], connection: Connection) -> NoReturn:
    """`arg` as `TAT_Framework.start'` packs it: the packages the node class
    theories registered, the working directory, the port, the client's name
    and the text of `TAT_MAX_CONCURRENT_CONSTRUCTION_JOBS` (MODULE_STRUCTURE
    §2.6).  The conversation, served until its ending."""
    python_packages, working_directory, port, client, max_concurrent_construction_jobs = arg
    async with served(python_packages, working_directory, port, client,
                      max_concurrent_construction_jobs, connection) as (_, _, server):
        await server.serve()


@isabelle_remote_procedure("compile_TAT")
async def compile_TAT(arg: tuple[list[str], str], connection: Connection) -> tuple[bool, list[str]]:
    """`arg` as `TAT_Framework.compile` packs it: the packages, the working
    directory.  The stored forest written under the working directory
    (COMPILATION.md §5): whether every tree was written, and the report's
    lines.  Its one call over the connection is `TAT.log_directory`, and
    its store cannot write."""
    python_packages, working_directory = arg
    async with conversation(python_packages, working_directory, connection, read_only=True
                            ) as (forest, loaded, _):
        report = compile(forest, loaded.compile_hooks)
        return all(reason is None for _, reason in report.trees), report_lines(report)
