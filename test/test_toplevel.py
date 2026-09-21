"""`launch_TAT` (MODULE_STRUCTURE §4.6): the working directory's lock, the
served line, the conversation's ending when the RPC host cancels the call,
and the lock's release.  The Isabelle side is a recorder standing in for
the connection; nothing here crosses the wire.
Run: python -m pytest test/test_toplevel.py
"""

import asyncio
import os
import socket
from typing import Any, cast

import pytest

from isabelle_theory_agent import toplevel
from isabelle_theory_agent.exceptions import TAT_StartupError
from isabelle_theory_agent.mcp_server import HOST


class Recorder:
    """What `launch_TAT` says to the Isabelle side; `served` once it has."""
    def __init__(self):
        self.lines: list[str] = []
        self.served = asyncio.Event()

    async def writeln(self, msg: str) -> None:
        self.lines.append(msg)
        self.served.set()


def free_port() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def run(scenario):
    asyncio.run(asyncio.wait_for(scenario(), 30))


async def launch(directory, port):
    """A conversation started and serving: its task and recorder — or what
    refused it, raised."""
    connection = Recorder()
    task = asyncio.create_task(cast(Any, toplevel.launch_TAT(
        ([], str(directory), port), cast(Any, connection))))
    served = asyncio.create_task(connection.served.wait())
    await asyncio.wait({task, served}, return_when=asyncio.FIRST_COMPLETED)
    if task.done():
        served.cancel()
        task.result()
    return task, connection


async def cancelled_by_the_host(task):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_a_conversation_serves_until_the_host_cancels_it_and_releases_the_lock(tmp_path):
    async def scenario():
        port = free_port()
        first, connection = await launch(tmp_path, port)
        assert connection.lines == [f"TAT is serving on http://{HOST}:{port}/mcp"]
        assert (tmp_path / "TAT.sqlite").is_file()
        # pid then port, one line each: the refusal reads the first, the
        # hooks the second (CLIENT_HOOKS.md)
        assert (tmp_path / "tat.lock").read_text() == f"{os.getpid()}\n{port}\n"

        # a second conversation on the directory is refused while the first
        # holds it, and told who holds it (here: this very process)
        with pytest.raises(TAT_StartupError) as refused:
            await launch(tmp_path, free_port())
        assert str(refused.value) == (f"another TAT conversation holds {tmp_path}"
                                      f" (its Python process is pid {os.getpid()})")

        # the connection gone: the RPC host cancels the call, which ends by
        # raising the cancellation; the pid goes with the lock
        await cancelled_by_the_host(first)
        assert (tmp_path / "tat.lock").read_bytes() == b""

        # the lock is released: the next conversation on the directory starts
        again, _ = await launch(tmp_path, port)
        await cancelled_by_the_host(again)
    run(scenario)


def test_a_port_in_use_is_refused_and_leaves_no_lock_behind(tmp_path):
    async def scenario():
        port = free_port()
        (tmp_path / "one").mkdir()
        (tmp_path / "two").mkdir()
        holder, _ = await launch(tmp_path / "one", port)
        with pytest.raises(TAT_StartupError, match=f"TAT cannot serve on {HOST}:{port}: "):
            await launch(tmp_path / "two", port)
        await cancelled_by_the_host(holder)
        # `two`'s lock was released on the way out
        second, _ = await launch(tmp_path / "two", port)
        await cancelled_by_the_host(second)
    run(scenario)


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes anywhere")
def test_a_directory_tat_cannot_write_is_a_startup_error(tmp_path):
    directory = tmp_path / "sealed"
    directory.mkdir(mode=0o500)
    async def scenario():
        with pytest.raises(TAT_StartupError) as refused:
            await launch(directory, free_port())
        assert str(refused.value) == \
            f"TAT cannot use {directory} as its working directory: Permission denied"
    try:
        run(scenario)
    finally:
        directory.chmod(0o700)
