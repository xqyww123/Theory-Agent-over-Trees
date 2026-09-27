"""`isabelle TAT_new` (MODULE_STRUCTURE §5): the directory it takes, the
database, and the agent clients' hook files, which must equal
CLIENT_HOOKS.md's fenced blocks verbatim — and the script they call,
against a serving `TAT_Server` and on every failure path.  Runs the real
tool, so it needs `isabelle` on the path and the component registered.
Run: python -m pytest test/test_launcher.py
"""

import asyncio
import json
import os
import shutil
import subprocess
import threading

import pytest

from baselines import DOCS, fenced_blocks
from isabelle_theory_agent.mcp_server import TAT_Server
from harness import free_port

pytestmark = pytest.mark.skipif(
    shutil.which("isabelle") is None or shutil.which("curl") is None,
    reason="isabelle and curl must be on the path")

HOOK_FILES = [".tat/on-compaction.sh", ".claude/settings.json", ".codex/hooks.json",
              ".gemini/settings.json", ".cursor/hooks.json", ".opencode/plugins/tat.js"]
JSON_FILES = HOOK_FILES[1:5]


def tat_new(*args):
    return subprocess.run(["isabelle", "TAT_new", *args], capture_output=True, text=True)


def tat(*args):
    return subprocess.run(["isabelle", "TAT", *args], capture_output=True, text=True)


def hook_blocks() -> list[list[str]]:
    """The six files as CLIENT_HOOKS.md shows them: the script's section
    holds a second block, the failure line, which is not a file."""
    script, _failure_line, *files = fenced_blocks(
        DOCS / "CLIENT_HOOKS.md", "The script", "Claude Code", "Codex", "Gemini CLI",
        "Cursor", "OpenCode")
    return [script, *files]


def failure_line() -> str:
    [_script, [line]] = fenced_blocks(DOCS / "CLIENT_HOOKS.md", "The script")
    return line


def script(wd, *args):
    return subprocess.run(["sh", ".tat/on-compaction.sh", *args], cwd=wd,
                          capture_output=True, text=True)


def test_a_fresh_directory_gets_the_database_the_script_and_the_hook_files(tmp_path):
    wd = tmp_path / "fresh"
    assert tat_new(str(wd)).returncode == 0
    assert (wd / "TAT.sqlite").is_file()
    for path, block in zip(HOOK_FILES, hook_blocks(), strict=True):
        assert (wd / path).read_text().splitlines() == block, path
    for path in JSON_FILES:
        assert isinstance(json.loads((wd / path).read_text()), dict), path


def test_a_directory_that_is_not_tats_is_refused(tmp_path):
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "README").write_text("")
    refused = tat_new(str(busy))
    assert refused.returncode == 2
    assert refused.stderr.strip() == f"*** {busy} is not empty and is not a TAT working directory"
    assert not (busy / "TAT.sqlite").exists()
    empty = tmp_path / "empty"
    empty.mkdir()
    assert tat_new(str(empty)).returncode == 0 and (empty / "TAT.sqlite").is_file()


def test_on_a_working_directory_only_the_absent_hook_files_are_written(tmp_path):
    wd = tmp_path / "wd"
    assert tat_new(str(wd)).returncode == 0
    (wd / ".codex" / "hooks.json").unlink()
    (wd / ".cursor" / "hooks.json").write_text("mine\n")
    assert tat_new("-P", "My_Nodes.X", str(wd)).returncode == 0
    assert (wd / ".codex" / "hooks.json").is_file()
    assert (wd / ".cursor" / "hooks.json").read_text() == "mine\n"


def test_a_session_under_the_working_directory_is_refused(tmp_path):
    """MODULE_STRUCTURE §5 step 3: the Isabelle session layout is checked
    before anything is built or started.  The session's folder need not
    exist: it is never selected."""
    wd = tmp_path / "wd"
    assert tat_new(str(wd)).returncode == 0
    (wd / "ROOT").write_text('session Foo in "Foo" = HOL +\n')
    r = tat("-d", str(wd), str(wd))
    assert r.returncode == 2 and r.stdout == "", r
    assert r.stderr.strip() == (
        f"*** Isabelle session Foo is declared under the working directory {wd};"
        " TAT never loads theories from there")


def test_the_script_fails_readably_without_a_running_conversation(tmp_path):
    wd = tmp_path / "wd"
    assert tat_new(str(wd)).returncode == 0
    dead = subprocess.run(["sh", "-c", "echo $$"], capture_output=True, text=True).stdout.strip()
    # absent; cleared; the port not yet written; left by a killed
    # conversation; a port nothing accepts on
    for lock in (None, "", "12345\n", f"{dead}\n8191\n", f"{os.getpid()}\n1\n"):
        if lock is not None:
            (wd / "tat.lock").write_text(lock)
        r = script(wd, "codex")
        assert r.returncode == 1 and r.stdout == "", lock
        assert r.stderr.strip().splitlines()[-1] == failure_line(), lock


def test_the_script_reaches_a_serving_conversation(tmp_path):
    """The seam where the Scala-written script meets the Python path: the
    real files, a real `TAT_Server`, the port from `tat.lock`, `curl`."""
    wd = tmp_path / "wd"
    assert tat_new(str(wd)).returncode == 0
    port = free_port()
    briefing = "session_A\n- theory_X (not evaluated)\n"
    up, stop = threading.Event(), threading.Event()

    async def serve():
        async with TAT_Server(port, [], lambda: briefing):
            up.set()
            while not stop.is_set():
                await asyncio.sleep(0.02)

    thread = threading.Thread(target=lambda: asyncio.run(serve()))
    thread.start()
    try:
        assert up.wait(10)
        (wd / "tat.lock").write_text(f"{os.getpid()}\n{port}\n")
        r = script(wd, "codex")
        assert r.returncode == 0 and json.loads(r.stdout) == {"hookSpecificOutput": {
            "hookEventName": "SessionStart", "additionalContext": briefing}}
        r = script(wd, "opencode")
        assert r.returncode == 0 and r.stdout == briefing
        r = script(wd)
        assert r.returncode == 0 and r.stdout == ""
        r = script(wd, "emacs")
        [refusal] = fenced_blocks(DOCS / "CLIENT_HOOKS.md", "An unknown client")[0]
        assert r.returncode != 0 and r.stdout == refusal
    finally:
        stop.set()
        thread.join(10)
