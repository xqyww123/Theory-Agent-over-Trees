"""`launch_TAT` (MODULE_STRUCTURE §4.6): the start in its layers — the
working directory's lock, the log directory (LOGGING.md §2), the ending
object, the store — the served line, the conversation's ending when the
RPC host cancels the call, the records of `conversation.jsonl`, and the
lock's release.  The Isabelle side is a recorder standing in for the
connection; nothing here crosses the wire.
Run: python -m pytest test/test_toplevel.py
"""

import asyncio
import logging
import os
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import stand_ins
from harness import free_port
from isabelle_theory_agent import toplevel
from isabelle_theory_agent.exceptions import TAT_StartupError
from isabelle_theory_agent.mcp_server import HOST

DIRECTORY_NAME = re.compile(r"^\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d\.\d{6}Z$")


class Recorder:
    """What `launch_TAT` says to the Isabelle side — the lines, and the
    round trips, answered with nothing; `served` once it has served; the RPC
    host's logger, which the `Log` reports to."""
    def __init__(self):
        self.lines: list[str] = []
        self.calls: list[tuple[str, Any]] = []
        self.served = asyncio.Event()
        self.server = SimpleNamespace(logger=logging.getLogger("tat.test.toplevel"))

    async def writeln(self, msg: str) -> None:
        self.lines.append(msg)
        self.served.set()

    async def callback(self, name: str, args: Any) -> None:
        self.calls.append((name, args))


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


def log_directories(working_directory) -> list[Path]:
    return sorted((working_directory / ".tat" / "log").iterdir())


def conversation_records(log_directory) -> list[dict]:
    return stand_ins.records("conversation", log_directory)


def test_a_conversation_serves_until_the_host_cancels_it_and_releases_the_lock(tmp_path):
    async def scenario():
        port = free_port()
        first, connection = await launch(tmp_path, port)
        assert connection.lines == [f"TAT is serving on http://{HOST}:{port}/mcp"]
        assert (tmp_path / "TAT.sqlite").is_file()
        # pid then port, one line each: the refusal reads the first, the
        # hooks the second (CLIENT_HOOKS.md)
        assert (tmp_path / "tat.lock").read_text() == f"{os.getpid()}\n{port}\n"
        # a fresh working directory: `.tat/log/` made, one directory in it,
        # named by its moment (LOGGING.md §2), the start recorded in order
        [log_directory] = log_directories(tmp_path)
        assert DIRECTORY_NAME.match(log_directory.name)
        # the Isabelle side told the directory, absolute, right after `start`
        assert connection.calls == [("TAT.log_directory", str(log_directory.absolute()))]
        records = conversation_records(log_directory)
        assert [r["event"] for r in records] == ["start", "store_opened", "plugins_loaded", "serving"]
        start, store_opened, plugins_loaded, serving = (r["data"] for r in records)
        assert start == {"version": start["version"], "pid": os.getpid(),
                         "working_directory": str(tmp_path), "python_packages": [], "port": port}
        assert store_opened == {"schema_version": 1, "nodes": 0}
        assert plugins_loaded["kinds"]["session"] == "isabelle_theory_agent.model"
        assert serving == {"url": f"http://{HOST}:{port}/mcp"}

        # a second conversation on the directory is refused while the first
        # holds it, and told who holds it (here: this very process); refused
        # at the lock, it writes no log
        with pytest.raises(TAT_StartupError) as refused:
            await launch(tmp_path, free_port())
        assert str(refused.value) == (f"another TAT conversation holds {tmp_path}"
                                      f" (its Python process is pid {os.getpid()})")
        assert log_directories(tmp_path) == [log_directory]

        # the connection gone: the RPC host cancels the call, which ends by
        # raising the cancellation; the pid goes with the lock; `ending` at
        # `info`, then `ended` once the unwinding is over
        await cancelled_by_the_host(first)
        assert (tmp_path / "tat.lock").read_bytes() == b""
        ending, ended = conversation_records(log_directory)[4:]
        assert (ending["event"], ending["level"]) == ("ending", "info")
        assert ending["data"]["class"] == "CancelledError"
        assert ended["event"] == "ended" and list(ended["data"]) == ["duration"]

        # the lock is released: the next conversation on the directory
        # starts, with a log directory of its own
        again, _ = await launch(tmp_path, port)
        assert len(log_directories(tmp_path)) == 2
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


def test_a_start_that_fails_after_the_log_exists_writes_ending_and_ended(tmp_path):
    """The store refusing the database (`TAT_StartupError`): the ending
    object's exit enters the ending and writes `ending` at `error` and
    `ended` with zero counts; the error is raised out of the procedure."""
    (tmp_path / "TAT.sqlite").write_text("not a database")
    async def scenario():
        with pytest.raises(TAT_StartupError):
            await launch(tmp_path, free_port())
    run(scenario)
    [log_directory] = log_directories(tmp_path)
    records = conversation_records(log_directory)
    assert [(r["event"], r["level"]) for r in records] == [
        ("start", "info"), ("ending", "error"), ("ended", "info")]
    assert records[1]["data"]["class"] == "TAT_StartupError"
    assert "Traceback" in records[1]["data"]["traceback"]
    assert list(records[2]["data"]) == ["duration"]
    assert (tmp_path / "tat.lock").read_bytes() == b""


MOMENT = "2026-10-01T07:24:05.039123Z"


def a_file_at_the_logs(wd):
    (wd / ".tat").mkdir()
    (wd / ".tat" / "log").write_text("")


def the_leaf_existing(wd):
    (wd / ".tat" / "log" / MOMENT.replace(":", "-")).mkdir(parents=True)


@pytest.mark.parametrize("obstacle", [a_file_at_the_logs, the_leaf_existing])
def test_a_log_directory_that_cannot_be_made_is_a_startup_error(tmp_path, monkeypatch, obstacle):
    """`.tat/log` taken by a file, or the directory existing already (it is
    made exclusively): refused with LOGGING §2's sentence, after the lock
    and before the store, which is never opened."""
    monkeypatch.setattr(toplevel, "now", lambda: MOMENT)
    obstacle(tmp_path)
    async def scenario():
        with pytest.raises(TAT_StartupError) as refused:
            await launch(tmp_path, free_port())
        assert str(refused.value) == f"TAT cannot write its log under {tmp_path}: File exists"
    run(scenario)
    assert not (tmp_path / "TAT.sqlite").exists()
    assert (tmp_path / "tat.lock").read_bytes() == b""
    assert not list((tmp_path / ".tat").rglob("*.jsonl"))       # the existing leaf gained nothing


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
