"""`isabelle TAT_new` (MODULE_STRUCTURE §5): the directory it takes, the
database, and the agent clients' hook files, which must equal
CLIENT_HOOKS.md's fenced blocks verbatim — and the script they call,
against a serving `TAT_Server` and on every failure path; what `TAT_mcp`
and `TAT_compile` refuse before any process starts; and `isabelle
TAT_compile` (COMPILATION.md) on a directory a conversation left.  Runs the
real tools, so it needs `isabelle` on the path and the component registered.
Run: python -m pytest test/test_launcher.py
"""

import asyncio
import json
import os
import shutil
import subprocess
import threading

import pytest

import stand_ins
from baselines import DOCS, fenced_blocks
from isabelle_theory_agent import edit
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


def tat_mcp(*args):
    return subprocess.run(["isabelle", "TAT_mcp", *args], capture_output=True, text=True)


def tat_compile(*args):
    return subprocess.run(["isabelle", "TAT_compile", *args], capture_output=True, text=True)


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


def test_a_path_with_a_bracket_is_refused_by_every_tool(tmp_path):
    """MODULE_STRUCTURE §5: both clients read `[` and `]` as pattern syntax
    in the entries that hide the working directory from the agents, so
    no tool takes such a path — before anything is made or read."""
    for name in ("a[1]", "b]"):
        wd = tmp_path / name
        sentence = f"*** {wd} contains [ or ], which TAT cannot use in a working directory path"
        for tool in (tat_new, tat_mcp, tat_compile):
            r = tool(str(wd))
            assert r.returncode == 2 and r.stdout == "" and r.stderr.strip() == sentence, (tool, r)
        assert not wd.exists()


def test_a_client_the_launcher_does_not_know_is_refused(tmp_path):
    """MODULE_STRUCTURE §5: `-c` takes `claude-code` and `codex`; any other
    name is refused in one sentence before anything is built or started,
    and a known one passes on to the directory's checks."""
    r = tat_mcp("-c", "emacs", str(tmp_path))
    assert r.returncode == 2 and r.stdout == "", r
    assert r.stderr.strip() == "*** TAT knows no client emacs"
    r = tat_mcp("-c", "codex", str(tmp_path))
    assert r.returncode == 2 and r.stdout == "", r
    assert r.stderr.strip() == f"*** {tmp_path} holds no TAT.sqlite; run isabelle TAT_new first"


@pytest.mark.parametrize("tool", [tat_mcp, tat_compile])
def test_a_session_under_the_working_directory_is_refused(tmp_path, tool):
    """MODULE_STRUCTURE §5 step 3, which the two tools share: the Isabelle
    session layout is checked before anything is built or started.  The
    session's folder need not exist: it is never selected."""
    wd = tmp_path / "wd"
    assert tat_new(str(wd)).returncode == 0
    (wd / "ROOT").write_text('session Foo in "Foo" = HOL +\n')
    r = tool("-d", str(wd), str(wd))
    assert r.returncode == 2 and r.stdout == "", r
    assert r.stderr.strip() == (
        f"*** Isabelle session Foo is declared under the working directory {wd};"
        " TAT never loads theories from there")


@pytest.mark.parametrize("tool", [tat_mcp, tat_compile])
def test_every_refusal_before_the_process_exits_2(tmp_path, tool):
    """MODULE_STRUCTURE §5: a usage error — no argument, an option the tool
    does not know — and a directory `TAT_new` did not make each exit 2,
    so that a 1 from `TAT_compile` can only be its report's."""
    for args in ((), ("-x", str(tmp_path))):
        r = tool(*args)
        assert r.returncode == 2 and r.stdout == "", (args, r)
        assert f"*** Usage: isabelle {tool.__name__.replace('tat', 'TAT')} " in r.stderr, (args, r)
    r = tool(str(tmp_path))
    assert r.returncode == 2 and r.stdout == "", r
    assert r.stderr.strip() == f"*** {tmp_path} holds no TAT.sqlite; run isabelle TAT_new first"


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
        async with TAT_Server(stand_ins.ending(), port, [], lambda: briefing):
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


# --- `isabelle TAT_compile` on a directory a conversation left -------------------
#
# Isabelle-backed: the directory is left by a conversation of the run's
# `isabelle TAT_mcp`, and the tool's own Isabelle process calls the product's
# `compile_TAT` on the run's RPC host.

async def compiled(harness, *args):
    return await harness.run_tool(["isabelle", "TAT_compile", *args])


def theory(name, *imports):
    return {"kind": "theory", "name": name, "imports": list(imports)}


async def leave(harness, request, wd, session, *theories, evaluate):
    """What a conversation leaves on `wd`: `session` holding `theories`, the
    first `evaluate` of them evaluated; ended on every path, so the lock is
    released and the run goes on to its next conversation."""
    handle = await harness.converse(wd, request.node.nodeid)
    try:
        forest = handle.forest
        async with forest.lock:
            (created,) = await edit.insert(forest, 0, [
                {"kind": "session", "name": session, "parent_session": "HOL",
                 "children": list(theories)}], handle.kinds)
        result = await created.sub_nodes[evaluate - 1].evaluate_to(False)
        assert result.stopped_at is None, result
    finally:
        await harness.await_ending()


@pytest.mark.isabelle(deadline=300)
async def test_a_compile_writes_what_a_conversation_left_and_isabelle_reads_it(
        harness, request, tmp_path):
    """COMPILATION.md §2, §5: the `Log:` line, the report, exit 0, and the
    files; then the same directory under a session layout that changed —
    Isabelle refuses what was written, after the report, and the tool
    exits 2."""
    wd = tmp_path / "wd"
    wd.mkdir()
    await leave(harness, request, wd, "TAT_C",
                theory("TAT_C_A", "Main"), theory("TAT_C_B", "TAT_C_A"), evaluate=2)
    r = await compiled(harness, str(wd))
    assert r.returncode == 0 and r.stderr == "", r
    log, *report = r.stdout.splitlines()
    assert log == f"Log: {sorted((wd / '.tat' / 'log').iterdir())[-1]}"
    assert report == ["TAT_C/TAT_C_A.thy written", "TAT_C/TAT_C_B.thy written", "ROOT written"]
    assert (wd / "ROOT").read_text() == \
        'session "TAT_C" in "TAT_C" = "HOL" +\n  theories\n    "TAT_C_A"\n    "TAT_C_B"\n'
    assert (wd / "TAT_C" / "TAT_C_B.thy").read_text() == \
        'theory TAT_C_B\n  imports "TAT_C_A"\nbegin\nend\n'
    assert (wd / "tat.lock").read_bytes() == b""

    extra = tmp_path / "extra"
    extra.mkdir()
    (extra / "ROOT").write_text('session TAT_C in "TAT_C" = HOL +\n')
    r = await compiled(harness, "-d", str(extra), str(wd))
    assert r.returncode == 2, r
    assert r.stdout.splitlines()[1:] == report
    assert r.stderr.startswith('*** Duplicate session "TAT_C"'), r.stderr


async def test_a_theory_that_is_not_written_exits_1(harness, request, tmp_path):
    wd = tmp_path / "wd"
    wd.mkdir()
    await leave(harness, request, wd, "TAT_D",
                theory("TAT_D_A", "Main"), theory("TAT_D_B", "Main"), evaluate=1)
    r = await compiled(harness, str(wd))
    assert r.returncode == 1 and r.stderr == "", r
    assert r.stdout.splitlines()[1:] == [
        "TAT_D/TAT_D_A.thy written",
        "TAT_D/TAT_D_B.thy not written: theory_TAT_D_B is not evaluated",
        "ROOT written"]
    assert (wd / "ROOT").read_text() == 'session "TAT_D" in "TAT_D" = "HOL" +\n  theories\n    "TAT_D_A"\n'
    assert not (wd / "TAT_D" / "TAT_D_B.thy").exists()


async def test_a_compile_is_refused_while_a_conversation_holds_the_directory(harness, conversation):
    """COMPILATION.md §7 item 2: the lock's sentence, as the last line of
    what ended the compile — printed as errors, which the tool's progress
    writes to the standard output — and exit 2; nothing is written."""
    wd = conversation.working_directory
    r = await compiled(harness, str(wd))
    assert r.returncode == 2 and r.stderr == "", r
    lines = r.stdout.splitlines()
    assert all(line.startswith("***") for line in lines), r.stdout
    assert lines[-1].endswith(
        f"{wd} is held by another TAT conversation or compile"
        f" (its Python process is pid {os.getpid()})"), r.stdout
    assert not (wd / "ROOT").exists()
