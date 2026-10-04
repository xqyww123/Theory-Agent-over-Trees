"""`launch_TAT` (MODULE_STRUCTURE §4.6): the start in its layers — the
working directory's lock, the log directory (LOGGING.md §2), the ending
object, the store — the served line, the conversation's ending when the
RPC host cancels the call, the records of `conversation.jsonl`, and the
lock's release; and `compile_TAT` (COMPILATION.md §5) on a directory a
conversation left.  The Isabelle side is a recorder standing in for the
connection; nothing here crosses the wire.
Run: python -m pytest test/test_toplevel.py
"""

import asyncio
import importlib
import logging
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import stand_ins
from baselines import DOCS, fenced_blocks
from harness import free_port
from isabelle_theory_agent import edit, plugin, toplevel
from isabelle_theory_agent.exceptions import TAT_DisasterError, TAT_StartupError
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
        records = stand_ins.records("conversation", log_directory)
        assert [r["event"] for r in records] == ["start", "store_opened", "plugins_loaded", "serving"]
        start, store_opened, plugins_loaded, serving = (r["data"] for r in records)
        assert start == {"version": start["version"], "pid": os.getpid(),
                         "working_directory": str(tmp_path), "python_packages": [], "port": port}
        assert store_opened == {"schema_version": 1, "nodes": 0}
        assert plugins_loaded["kinds"]["session"] == "isabelle_theory_agent.model"
        assert serving == {"url": f"http://{HOST}:{port}/mcp"}

        # a second conversation on the directory, and a compile, are refused
        # while the first holds it, and told who holds it (here: this very
        # process), in COMPILATION.md §7's sentence; refused at the lock,
        # neither writes a log
        held = (f"{tmp_path} is held by another TAT conversation or compile"
                f" (its Python process is pid {os.getpid()})")
        with pytest.raises(TAT_StartupError) as refused:
            await launch(tmp_path, free_port())
        assert str(refused.value) == held
        with pytest.raises(TAT_StartupError) as refused:
            await toplevel.compile_TAT(([], str(tmp_path)), cast(Any, Recorder()))
        assert str(refused.value) == held
        assert log_directories(tmp_path) == [log_directory]
        assert not (tmp_path / "ROOT").exists()

        # the connection gone: the RPC host cancels the call, which ends by
        # raising the cancellation; the pid goes with the lock; `ending`,
        # then `ended` once the unwinding is over
        await cancelled_by_the_host(first)
        assert (tmp_path / "tat.lock").read_bytes() == b""
        ending, ended = stand_ins.records("conversation", log_directory)[4:]
        assert (ending["event"], ending["level"]) == ("ending", "error")
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
    `ended`, which carries only the duration; the error is raised out of
    the procedure."""
    (tmp_path / "TAT.sqlite").write_text("not a database")
    async def scenario():
        with pytest.raises(TAT_StartupError):
            await launch(tmp_path, free_port())
    run(scenario)
    [log_directory] = log_directories(tmp_path)
    records = stand_ins.records("conversation", log_directory)
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


# --- `compile_TAT` ------------------------------------------------------------

BROKEN = "Type unification failed"


class Wire(Recorder):
    """The Isabelle side of the conversation that leaves a forest behind:
    creation's checks pass, and so does every operation of a `Theory` but
    the header of one named `Broken`."""
    async def callback(self, name: str, args: Any) -> Any:
        self.calls.append((name, args))
        match name:
            case "TAT.check_session":
                return ["ok"]
            case "TAT.check_new_theory_short_name":
                return ["free"]
            case "TAT.Theory.begin":
                _slot, (_session, _master_dir, header) = args
                return ([BROKEN], []) if header.startswith("theory Broken") else ([], ["HOL"])
            case "TAT.Theory.end":
                return []


async def leave(directory: Path, *theories: str) -> None:
    """A conversation on `directory` that builds `session_S` holding the
    theories named, evaluates them all, and ends: what a compile finds."""
    async with toplevel.conversation([], str(directory), cast(Any, Wire())) as (forest, loaded, _):
        async with forest.lock:
            (session,) = await edit.insert(forest, 0, [
                {"kind": "session", "name": "S", "parent_session": "HOL",
                 "children": [{"kind": "theory", "name": name, "imports": ["Main"]}
                              for name in theories]}], loaded.kinds)
        await session.evaluate_to(True)


def test_a_compile_writes_the_stored_forest_and_returns_its_report(tmp_path):
    """COMPILATION.md §5: on a directory a conversation left, `compile_TAT`
    writes the files and returns whether every tree was written and the
    report's lines; its one round trip is `TAT.log_directory`, it writes
    nothing to the database, and a compile that returns writes neither
    `ending` nor `ended` (LOGGING.md §4)."""
    async def scenario():
        await leave(tmp_path, "A", "Broken")
        database = (tmp_path / "TAT.sqlite").read_bytes()
        connection = Recorder()
        answer = await toplevel.compile_TAT(([], str(tmp_path)), cast(Any, connection))
        assert answer == (False, ["S/A.thy written",
                                  "S/Broken.thy not written: theory_Broken failed",
                                  f"  {BROKEN}",
                                  "ROOT written"])
        assert (tmp_path / "S" / "A.thy").read_text() == 'theory A\n  imports "Main"\nbegin\nend\n'
        assert not (tmp_path / "S" / "Broken.thy").exists()
        assert (tmp_path / "ROOT").read_text() == \
            'session "S" in "S" = "HOL" +\n  theories\n    "A"\n'
        _, log_directory = log_directories(tmp_path)        # the conversation's, the compile's
        assert connection.calls == [("TAT.log_directory", str(log_directory.absolute()))]
        records = stand_ins.records("conversation", log_directory)
        assert [r["event"] for r in records] == ["start", "store_opened", "plugins_loaded"]
        assert "port" not in records[0]["data"]             # a conversation's (LOGGING.md §4)
        assert (tmp_path / "TAT.sqlite").read_bytes() == database
        assert (tmp_path / "tat.lock").read_bytes() == b""  # held with the pid line alone, released
    run(scenario)


def test_a_compile_of_a_forest_written_whole_answers_true(tmp_path):
    async def scenario():
        await leave(tmp_path, "A", "B")
        answer = await toplevel.compile_TAT(([], str(tmp_path)), cast(Any, Recorder()))
        assert answer == (True, ["S/A.thy written", "S/B.thy written", "ROOT written"])
    run(scenario)


def test_a_compile_cannot_write_the_database(tmp_path):
    """COMPILATION.md §5: a compile's store is read-only — a database
    `TAT_new` made, which holds the launcher's table alone, is read as the
    empty forest and left byte for byte as it was; and once a conversation
    has set the store up, a compile reads its nodes and cannot write."""
    import sqlite3
    from isabelle_theory_agent.store import Forest_Store
    with sqlite3.connect(tmp_path / "TAT.sqlite") as fresh:
        fresh.execute("CREATE TABLE plugins (theory TEXT PRIMARY KEY)")
    fresh.close()
    database = (tmp_path / "TAT.sqlite").read_bytes()
    async def scenario():
        assert await toplevel.compile_TAT(([], str(tmp_path)), cast(Any, Recorder())) == \
            (True, ["ROOT written"])
        assert (tmp_path / "TAT.sqlite").read_bytes() == database
        await leave(tmp_path, "A")
    run(scenario)
    with Forest_Store(tmp_path / "TAT.sqlite", stand_ins.log(), read_only=True) as store:
        assert store.nodes() == [0, 1, 2]                   # the root, the session, the theory
        with pytest.raises(TAT_DisasterError) as refused:   # a write is what the store's transaction raises
            with store.transaction():
                store.put(1, "name", "renamed")
        assert "readonly" in str(refused.value.__cause__)


def test_a_compile_runs_the_hooks_of_the_packages_it_is_given(tmp_path, monkeypatch):
    """COMPILATION.md §5: `compile_TAT` hands `compile` the hooks the
    packages of its call define — not those of a package the process
    merely holds."""
    monkeypatch.setattr(plugin, "compile_hooks", {})
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("listed_hook_pkg", "held_hook_pkg"):
        (tmp_path / f"{name}.py").write_text(
            "from isabelle_theory_agent import plugin\n"
            "@plugin.TAT_compile_hook\n"
            "def mark(forest):\n"
            f"    (forest.conversation.working_directory / '{name}.ran').write_text('')\n")
        monkeypatch.delitem(sys.modules, name, raising=False)
    importlib.import_module("held_hook_pkg")
    directory = tmp_path / "work"
    directory.mkdir()
    async def scenario():
        await leave(directory, "A")
        await toplevel.compile_TAT((["listed_hook_pkg"], str(directory)), cast(Any, Recorder()))
    run(scenario)
    assert (directory / "listed_hook_pkg.ran").exists()
    assert not (directory / "held_hook_pkg.ran").exists()


def test_what_escapes_a_compile_enters_its_ending(tmp_path):
    """A `Session` folder's path holding a file: refused with COMPILATION.md
    §7's sentence, raised out of the procedure; the compile's log gains
    `ending` and `ended`."""
    _, (_, not_a_directory, _), _ = fenced_blocks(DOCS / "COMPILATION.md", "7.")
    async def scenario():
        await leave(tmp_path, "A")
        (tmp_path / "S").rmdir()
        (tmp_path / "S").write_text("not a directory")
        with pytest.raises(TAT_StartupError) as refused:
            await toplevel.compile_TAT(([], str(tmp_path)), cast(Any, Recorder()))
        assert str(refused.value) == (not_a_directory.replace("<working directory>", str(tmp_path))
                                      .replace("<Session name>", "S"))
    run(scenario)
    _, log_directory = log_directories(tmp_path)
    records = stand_ins.records("conversation", log_directory)
    assert [(r["event"], r["level"]) for r in records[3:]] == [("ending", "error"), ("ended", "info")]
    assert records[3]["data"]["class"] == "TAT_StartupError"
    assert (tmp_path / "tat.lock").read_bytes() == b""


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
