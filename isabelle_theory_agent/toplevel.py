"""The RPC entry point Isabelle calls into (MODULE_STRUCTURE §4.6).

`TAT_Framework.start` on the ML side calls the procedure `launch_TAT`, which
builds the conversation and serves until its ending; it does not return
(ARCHITECTURE §9): everything the conversation does, it does through this
call's callbacks, and the call ends only by raising what ended the
conversation.
"""

from __future__ import annotations

import fcntl
import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import NoReturn

from Isabelle_RPC_Host import Connection, isabelle_remote_procedure

from . import mcp, plugin
from .exceptions import TAT_StartupError
from .mcp_server import TAT_Server
from .model import Conversation, Forest
from .store import Forest_Store

DATABASE = "TAT.sqlite"                 # the launcher's, shared with the plugins table (§5)
LOCK = "tat.lock"


@contextmanager
def _held(working_directory: Path) -> Generator[None]:
    """The working directory's lock: an exclusive `flock` on a descriptor
    kept open for the life of the conversation, so the kernel releases it
    when the process dies and the `finally` when the conversation ends any
    other way.  `flock`, not a POSIX record lock, because only `flock`
    conflicts between two descriptors in one process — what refuses a
    second conversation in this host as well as in another.  The holder
    writes its pid into the file and clears it on release, so a refusal
    can name it; between taking the lock and writing, the file is still
    empty or still a crashed holder's, and between clearing it on release
    and closing the descriptor it is empty."""
    try:
        fd = os.open(working_directory / LOCK, os.O_RDWR | os.O_CREAT, 0o644)
    except OSError as e:
        raise TAT_StartupError(
            f"TAT cannot use {working_directory} as its working directory: {e.strerror}") from e
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            holder = os.pread(fd, 32, 0).decode(errors="replace").strip()
            raise TAT_StartupError(
                f"another TAT conversation holds {working_directory}"
                + (f" (its Python process is pid {holder})" if holder.isdigit() else "")) from e
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode())
        try:
            yield
        finally:
            os.ftruncate(fd, 0)
    finally:
        os.close(fd)


@isabelle_remote_procedure("launch_TAT")
async def launch_TAT(arg: tuple[list[str], str, int], connection: Connection) -> NoReturn:
    """`arg` as `TAT_Framework.start'` packs it: the packages the node class
    theories registered, the working directory, the port (MODULE_STRUCTURE
    §2.6).  In order: the lock, the store, the `Conversation`, the plugins,
    the `Forest`, the server; then the conversation, until its ending."""
    python_packages, working_directory, port = arg
    directory = Path(working_directory)
    with _held(directory), Forest_Store(directory / DATABASE) as store:
        conversation = Conversation(connection, directory)
        loaded = plugin.load(python_packages)
        forest = Forest(conversation, store, loaded.kinds)
        async with TAT_Server(port, mcp.tools(forest, loaded)) as server:
            # a line nothing depends on, and the launcher does not echo (§5)
            await connection.writeln(f"TAT is serving on {server.url}")
            await server.serve()
