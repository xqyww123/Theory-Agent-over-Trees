"""`isabelle TAT_new` (MODULE_STRUCTURE §5): the directory it takes and
the database, which is all it writes; what `TAT_mcp`, `TAT_compile` and
`TAT` refuse before any process starts; `isabelle TAT_compile`
(COMPILATION.md) on a directory a conversation left; and `isabelle TAT`
with fake agent clients, outside the shared harness, on the tool's own
attached RPC host, through the `launcher` fixture — with the self-tests of
harness.py's `tool`, which every launcher case holds its tool by.  Runs the
real tools, so it needs `isabelle` on the path and the component registered.
Run: python -m pytest test/test_launcher.py
"""

import asyncio
import json
import os
import pty
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import termios
import time
import traceback
import tty
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import anyio
import pytest

import fake_agent_client as fake
import harness as H
from harness import STARTUP, deadline, group, proc, run_tool, running, tool, until
from isabelle_theory_agent import edit
from isabelle_theory_agent.mcp_server import AGENTS, HOST, Claude_Code_Server, Codex_Server, agent_directory
from isabelle_theory_agent.toplevel import LOG

pytestmark = pytest.mark.skipif(
    shutil.which("isabelle") is None, reason="isabelle must be on the path")

WAITING_LINE = "Starting TAT... It may take a while"    # isabelle TAT's first line (MODULE_STRUCTURE §5)
URL_LINE = "TAT is serving on "                          # what precedes the URL


def isabelle(tool_name: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["isabelle", tool_name, *args], capture_output=True, text=True, env=env)


def tat_new(*args, env=None):
    return isabelle("TAT_new", *args, env=env)


def tat_mcp(*args, env=None):
    return isabelle("TAT_mcp", *args, env=env)


def tat_compile(*args, env=None):
    return isabelle("TAT_compile", *args, env=env)


def tat(*args, env=None):
    return isabelle("TAT", *args, env=env)


def test_a_fresh_directory_gets_the_database_and_nothing_else(tmp_path):
    """MODULE_STRUCTURE §5: `TAT_new` writes no client file; those are the
    server's `configure` at every launch (CLIENT_HOOKS.md)."""
    wd = tmp_path / "fresh"
    assert tat_new(str(wd)).returncode == 0
    assert [p.name for p in wd.iterdir()] == ["TAT.sqlite"]


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


def test_on_a_working_directory_nothing_but_the_database_is_touched(tmp_path):
    wd = tmp_path / "wd"
    assert tat_new(str(wd)).returncode == 0
    (wd / "mine").write_text("mine\n")
    assert tat_new("-P", "My_Nodes.X", str(wd)).returncode == 0
    assert sorted(p.name for p in wd.iterdir()) == ["TAT.sqlite", "mine"]
    assert (wd / "mine").read_text() == "mine\n"


def test_a_path_with_a_bracket_is_refused_by_every_tool(fake_clients, tmp_path):
    """MODULE_STRUCTURE §5: both clients read `[` and `]` as pattern syntax
    in the entries that hide the working directory from the agents, so
    no tool takes such a path — before anything is made or read."""
    for name in ("a[1]", "b]"):
        wd = tmp_path / name
        sentence = f"*** {wd} contains [ or ], which TAT cannot use in a working directory path"
        for tool_ in (tat_new, tat_mcp, tat_compile, tat):
            r = tool_(str(wd), env=fake_clients.env)
            assert r.returncode == 2 and r.stdout == "" and r.stderr.strip() == sentence, (tool_, r)
        assert not wd.exists()


def test_a_client_the_launcher_does_not_know_is_refused(fake_clients, tmp_path):
    """MODULE_STRUCTURE §5: `-c` takes `claude-code` and `codex`; any other
    name is refused in one sentence before anything is built or started,
    and a known one passes on to the directory's checks."""
    r = tat_mcp("-c", "emacs", str(tmp_path))
    assert r.returncode == 2 and r.stdout == "", r
    assert r.stderr.strip() == "*** TAT doesn't know the agent client emacs"
    r = tat_mcp("-c", "codex", str(tmp_path))
    assert r.returncode == 2 and r.stdout == "", r
    assert r.stderr.strip() == f"*** {tmp_path} holds no TAT.sqlite; run isabelle TAT_new first"
    wd = tmp_path / "wd"
    r = tat("-c", "other", str(wd), env=fake_clients.env)
    assert r.returncode == 2 and r.stdout == "", r
    assert r.stderr.strip() == "*** TAT doesn't know the agent client other"
    assert not wd.exists()


def test_a_client_that_is_not_on_the_path_is_refused(fake_clients, tmp_path):
    """MODULE_STRUCTURE §5: the client's executable is looked up on `PATH`
    as the shell looks it up, before anything is created — entries that
    are not Isabelle paths included: one with an apostrophe, one that is
    literally `$TAT_UNDEFINED/bin`, and an empty one, the current directory."""
    system = [entry for entry in ("/usr/bin", "/bin") if Path(entry).is_dir()]
    if shutil.which("claude", path=os.pathsep.join(system)) is not None:
        pytest.skip("the system directories hold a claude")
    odd = tmp_path / "it's"
    odd.mkdir()
    wd = tmp_path / "wd"
    env = {**fake_clients.env, "PATH": os.pathsep.join([*system, str(odd), "$TAT_UNDEFINED/bin", ""])}
    isabelle_path = shutil.which("isabelle")
    assert isabelle_path is not None
    r = subprocess.run([isabelle_path, "TAT", str(wd)], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r.returncode == 2 and r.stdout == "", r
    assert r.stderr.strip() == "*** TAT cannot find claude on the path"
    assert not wd.exists()


@pytest.mark.parametrize("tool_", [tat_mcp, tat_compile])
def test_a_session_under_the_working_directory_is_refused(tmp_path, tool_):
    """MODULE_STRUCTURE §5 step 3, which the two tools share: the Isabelle
    session layout is checked before anything is built or started.  The
    session's folder need not exist: it is never selected."""
    wd = tmp_path / "wd"
    assert tat_new(str(wd)).returncode == 0
    (wd / "ROOT").write_text('session Foo in "Foo" = HOL +\n')
    r = tool_("-d", str(wd), str(wd))
    assert r.returncode == 2 and r.stdout == "", r
    assert r.stderr.strip() == (
        f"*** Isabelle session Foo is declared under the working directory {wd};"
        " TAT never loads theories from there")


@pytest.mark.parametrize("tool_", [tat_mcp, tat_compile])
def test_every_refusal_before_the_process_exits_2(tmp_path, tool_):
    """MODULE_STRUCTURE §5: a usage error — no argument, an option the tool
    does not know — and a directory `TAT_new` did not make each exit 2,
    so that a 1 from `TAT_compile` can only be its report's."""
    for args in ((), ("-x", str(tmp_path))):
        r = tool_(*args)
        assert r.returncode == 2 and r.stdout == "", (args, r)
        assert f"*** Usage: isabelle {tool_.__name__.replace('tat', 'TAT')} " in r.stderr, (args, r)
    r = tool_(str(tmp_path))
    assert r.returncode == 2 and r.stdout == "", r
    assert r.stderr.strip() == f"*** {tmp_path} holds no TAT.sqlite; run isabelle TAT_new first"


def test_a_usage_error_of_tat_creates_nothing(fake_clients, tmp_path):
    """MODULE_STRUCTURE §5: `isabelle TAT`'s usage errors — no argument, an
    option it does not know — exit 2 with the usage text and create
    nothing: the options stop at the working directory, so the error is
    seen before it."""
    wd = tmp_path / "wd"
    for args in ((), ("-x", str(wd))):
        r = tat(*args, env=fake_clients.env)
        assert r.returncode == 2 and r.stdout == "", (args, r)
        assert "*** Usage: isabelle TAT " in r.stderr, (args, r)
    assert not wd.exists()


def test_a_refusal_of_the_launch_leaves_the_directory_made_and_starts_no_client(fake_clients, tmp_path):
    """MODULE_STRUCTURE §5: `isabelle TAT` creates the directory as `TAT_new`
    does, the plugins recorded, and then a refusal of the launch — here
    the options' — exits 2 before any process and before the client."""
    wd = tmp_path / "wd"
    report = tmp_path / "report.json"
    r = tat("-o", "parallel_proofs=3", "-P", "Some.Plugin", str(wd),
            env={**fake_clients.env, **fake.variables("exit_on_marker", report)})
    assert r.returncode == 2 and r.stdout == "", r
    assert r.stderr.splitlines() == [WAITING_LINE,
                                     "*** TAT requires parallel_proofs below 3, but the options give 3"]
    with sqlite3.connect(wd / "TAT.sqlite") as db:
        assert db.execute("SELECT theory FROM plugins").fetchall() == [("Some.Plugin",)]
    assert not report.exists()


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
        result = await created.sub_nodes[evaluate - 1].evaluate_to(None, False)
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
        'theory "TAT_C_B"\n  imports "TAT_C_A"\nbegin\nend\n'
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


# --- harness.py's `tool`: its contract, on processes of the test's own ------------
#
# Unmarked: no Isabelle; the bounds monkeypatched down.

MARGIN = 3.0                                    # seconds a bounded wait may overrun: start-up, polling
CHILD_STDOUT_LINE = "the child is running"
CHILD_STDERR_LINE = "the child got SIGTERM"
CHILD_LAST_LINE = "the child is exiting"
CHILD_EXIT = 3

# Laid out as a tool is under `lib/Tools/java`: a bash between the pid and
# the program.  The program is not bash's last command — bash would exec it
# in its own place — so `exit $?` follows.  The child ignores SIGINT and, on
# SIGTERM, writes its line, waits, writes its last line and the marker, and exits.
CHILD = f'''
import os, signal, sys, time
signal.signal(signal.SIGINT, signal.SIG_IGN)
def on_sigterm(*_):
    sys.stderr.write({CHILD_STDERR_LINE!r} + "\\n")
    sys.stderr.flush()
    time.sleep(0.2)
    sys.stderr.write({CHILD_LAST_LINE!r} + "\\n")
    sys.stderr.flush()
    open(sys.argv[1], "w").close()
    sys.exit({CHILD_EXIT})
signal.signal(signal.SIGTERM, on_sigterm)
print({CHILD_STDOUT_LINE!r}, flush=True)
while True:
    signal.pause()
'''


@pytest.mark.anyio
async def test_a_process_left_in_the_group_fails_the_block(monkeypatch):
    """A process left in the group at the bound fails the block's normal
    exit, named, within `TERMINATION`; the texts are not readable inside
    the block."""
    monkeypatch.setattr(H, "TERMINATION", 1.0)
    argv = ["bash", "-c", "sleep 60 & exit 0"]
    started = time.monotonic()
    with pytest.raises(AssertionError, match=r"left in the group of .*sleep 60"):
        async with tool(argv, dict(os.environ)) as h:
            with pytest.raises(RuntimeError, match="complete only after"):
                h.stdout
            assert await h.exited == 0
    assert time.monotonic() - started < 1.0 + MARGIN


@pytest.mark.anyio
@pytest.mark.parametrize("waiting_on", ["exited", "line"])
async def test_the_exit_ends_the_group_and_notes_the_output(monkeypatch, tmp_path, waiting_on):
    """The exceptional path — a deadline expiring inside the block, in either
    wait a case makes there: SIGINT, which the child ignores, the bound,
    then `end_group`'s SIGTERM, which the child answers within its grace
    (the marker proves it was not killed); the `TimeoutError` reaches the
    caller carrying both texts, every line the child wrote while the block
    was ending included; the leader's code is still readable."""
    monkeypatch.setattr(H, "TERMINATION", 2.0)
    child = tmp_path / "child.py"
    child.write_text(CHILD)
    marker = tmp_path / "marker"
    argv = ["bash", "-c", '"$@"; exit $?', "bash", sys.executable, str(child), str(marker)]
    with pytest.raises(TimeoutError) as expired:
        with deadline(2.0, "the child's run"):
            async with tool(argv, dict(os.environ)) as h:
                await h.line("stdout", lambda line: line == CHILD_STDOUT_LINE)
                leader = proc(h.pid)
                assert leader is not None and leader.comm == "bash", leader
                members = group(h.pid)
                (other,) = [p for p in members if p.pid != h.pid]
                assert len(members) == 2 and other.ppid == h.pid, members
                if waiting_on == "exited":
                    await h.exited
                else:
                    await h.line("stderr", lambda line: False)
    assert marker.exists()
    assert not group(h.pid)
    formatted = "".join(traceback.format_exception(expired.value))
    assert all(line in formatted for line in (CHILD_STDOUT_LINE, CHILD_STDERR_LINE, CHILD_LAST_LINE)), formatted
    assert h.exited.result() == -signal.SIGTERM


@pytest.mark.anyio
async def test_a_cancellation_at_the_start_reaches_the_block(monkeypatch):
    """A cancellation already pending when `tool` starts its process lands
    in the block, so the exit ends the group: nothing started escapes it."""
    monkeypatch.setattr(H, "TERMINATION", 1.0)
    pids = []
    with anyio.move_on_after(0) as scope:
        async with tool(["bash", "-c", "sleep 60; exit 0"], dict(os.environ)) as h:
            pids.append(h.pid)
            await h.exited
    assert scope.cancelled_caught and pids and not group(pids[0])


def test_a_process_whose_name_is_cut_mid_character_is_listed(tmp_path):
    """The kernel cuts a process's name to 15 bytes, which can split a
    character; `group` reads every process on the machine, and such a name
    must not stop it."""
    sleep = tmp_path / "a测试工具脚"                   # 16 bytes: its name is cut inside the last character
    sleep.symlink_to(shutil.which("sleep"))
    process = subprocess.Popen([str(sleep), "60"], start_new_session=True)
    try:
        assert [p.pid for p in group(process.pid)] == [process.pid]
    finally:
        process.kill()
        process.wait()


@pytest.mark.anyio
async def test_a_pipe_held_outside_the_group_fails_the_block(monkeypatch, tmp_path):
    """A process outside the group holding the pipes: the group has exited,
    the readers' join expires, and the block fails naming both pipes
    within `JOIN`, the readers stopped and the pipes closed on this side."""
    monkeypatch.setattr(H, "JOIN", 1.0)
    pidfile = tmp_path / "pid"
    argv = ["bash", "-c", f'setsid sleep 60 & echo $! > "{pidfile}"; exit 0']
    before = set(os.listdir("/proc/self/fd"))
    started = time.monotonic()
    try:
        with pytest.raises(AssertionError, match="stdout and stderr still open"):
            async with tool(argv, dict(os.environ)) as h:
                opened = set(os.listdir("/proc/self/fd")) - before      # the pipes' read ends
                assert await h.exited == 0
        assert time.monotonic() - started < 1.0 + MARGIN
        await asyncio.sleep(0)              # a transport closes its pipe on the loop's next turn
        assert not opened & set(os.listdir("/proc/self/fd")), opened
    finally:
        os.kill(int(pidfile.read_text()), signal.SIGKILL)


# --- `isabelle TAT` with fake agent clients -------------------------------------
#
# Isabelle-backed through `launcher` (conftest's `HARNESSES`): each case
# boots the Isabelle processes it names, holds every tool inside
# `async with launcher.tool(...)`, and ends with the conversation's pid not
# running.  A case with a controlling terminal asserts nothing about the
# tool's descendants: when its bash, the session leader, exits, the kernel's
# hangup to the foreground group would hide leftovers.

# tat.scala's escape_sequence_modes_off, which the tool writes after the stty restore
ESCAPE_SEQUENCE_MODES_OFF = (b"\x1b[<99u\x1b[>4m\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l"
                             b"\x1b[?2004l\x1b[?1004l\x1b[?2031l\x1b[?25h")


def environment(path_first: Path | None = None) -> dict[str, str]:
    """A tool's environment: the test's without `RPC_Host`, so the tool's
    Isabelle process starts the attached RPC host, under this interpreter
    (`ISABELLE_RPC_PYTHON`), which has the package; AoA's gate shut
    (`AOA_ALLOW_NONINTERACTIVE=no`), so no case calls a language model;
    `path_first` before everything on `PATH`."""
    env = {name: value for name, value in os.environ.items() if name != "RPC_Host"}
    env["ISABELLE_RPC_PYTHON"] = sys.executable
    env["AOA_ALLOW_NONINTERACTIVE"] = "no"
    if path_first is not None:
        env["PATH"] = f"{path_first}{os.pathsep}{env['PATH']}"
    return env


def executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(0o755)


class Fake_Clients:
    """`directory` holds the fakes `claude` and `codex` (fake_agent_client.py);
    `broken` a `claude`
    whose shebang names no interpreter; `env` is the tools' environment
    with `directory` first on `PATH`."""

    def __init__(self, root: Path):
        self.directory = root / "bin"
        self.broken = root / "broken"
        self.directory.mkdir()
        self.broken.mkdir()
        program = f"#!{sys.executable}\n" + Path(fake.__file__).read_text()
        for name in ("claude", "codex"):
            executable(self.directory / name, program)
        executable(self.broken / "claude", "#!/nonexistent/interpreter\n")
        self.env = environment(self.directory)



class Launcher:
    """What a launcher case gets: the tools' environment and `tool` and
    `run_tool` on it, `variables` adding to it; `deadline`, under which
    conftest runs the case."""

    deadline = staticmethod(deadline)

    def __init__(self, fakes: Fake_Clients):
        self.env = fakes.env

    def tool(self, argv: list[str], variables: dict[str, str] | None = None, **kwargs: Any):
        return tool(argv, {**self.env, **(variables or {})}, **kwargs)

    async def run_tool(self, argv: list[str], variables: dict[str, str] | None = None
                       ) -> subprocess.CompletedProcess[str]:
        return await run_tool(argv, {**self.env, **(variables or {})})


def is_url_line(line: str) -> bool:
    return line.startswith(URL_LINE)


def url_of(line: str) -> str:
    assert is_url_line(line), line
    return line.removeprefix(URL_LINE)


def port_of(url: str) -> int:
    port = urlsplit(url).port
    assert port is not None, url
    return port


def log_directory(wd: Path) -> Path:
    """The one log directory the working directory holds."""
    (directory,) = (wd / LOG).iterdir()
    return directory


def conversation_pid(wd: Path) -> int:
    """The conversation's Python process, from the `start` record, the log's
    first — written under the lock and never cleared, the pid `tat.lock`
    names; the lock file itself is emptied on release."""
    first = json.loads((log_directory(wd) / "conversation.jsonl").read_text().splitlines()[0])
    assert first["event"] == "start", first
    return first["data"]["pid"]


def report_of(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


async def conversation_exits(pid: int) -> None:
    """After a SIGTERM ended the JVM: its shutdown hooks end the Isabelle
    process, and the JVM exits without waiting for the attached RPC host,
    which exits on its lifeline — measured up to 0.15 s after the group.
    After the client's exit the host is gone when the group is: there
    `session.stop()` returns only once it has been terminated."""
    await until(lambda: not running(pid), "the conversation's exit after the JVM's")


@pytest.fixture(scope="session")
async def warm_up(anyio_backend, tmp_path_factory):
    """One `isabelle TAT_mcp` on a scratch directory, no fakes, before any
    case with one: the base heap built (a first run may build it) and the
    tools known to work, within `STARTUP`.  A failure carries the tool's
    texts, so every launcher case errors at setup with the reason."""
    env = environment()
    wd = tmp_path_factory.mktemp("warm_up") / "wd"
    made = await run_tool(["isabelle", "TAT_new", str(wd)], env)
    assert made.returncode == 0, made
    async with tool(["isabelle", "TAT_mcp", str(wd)], env) as h:
        with deadline(STARTUP, "the warm-up's isabelle TAT_mcp"):
            await h.line("stdout", is_url_line)
        h.signal_group(signal.SIGTERM)


@pytest.fixture(scope="session")
def fake_clients(tmp_path_factory):
    return Fake_Clients(tmp_path_factory.mktemp("fake_clients"))


@pytest.fixture
def launcher(warm_up, fake_clients):
    return Launcher(fake_clients)


async def test_claude_code_runs_in_the_agent_directory_until_it_exits(launcher, tmp_path):
    """MODULE_STRUCTURE §5: the client started in the agent directory once
    the conversation serves, on a URL it can reach, stdout its own; a
    Ctrl-C at the terminal is the client's; a second `isabelle TAT` on the
    directory is refused by the lock and starts no client; the client's
    exit, first, ends the conversation and is the tool's code, nothing
    printed after the URL line.  The pty is the tool's terminal and its
    stdin, but its stdout is the pipe, so no mode is saved: the mode the
    client set stays after the tool (a save would write the raw mode back)."""
    wd = tmp_path / "wd"
    report, second_report, marker = tmp_path / "report.json", tmp_path / "second.json", tmp_path / "marker"
    master, slave = pty.openpty()
    try:
        tty.setraw(slave)
        raw = termios.tcgetattr(slave)
        async with launcher.tool(["isabelle", "TAT", str(wd)],
                                 fake.variables("exit_on_marker", report, marker),
                                 stdin=slave, terminal=slave) as h:
            await h.line("stdout", lambda line: line == fake.LINE)
            pid = conversation_pid(wd)
            h.signal_group(signal.SIGINT)
            await until(lambda: report.exists() and "SIGINT" in report_of(report)["signals"],
                        "the client's record of the interrupt")
            assert running(h.pid) and running(pid)
            second = await launcher.run_tool(["isabelle", "TAT", str(wd)],
                                             fake.variables("exit_on_marker", second_report))
            assert second.returncode == 2 and second.stdout == "", second
            lines = second.stderr.splitlines()
            assert lines[0] == WAITING_LINE and all(line.startswith("***") for line in lines[1:]), second
            assert lines[-1].endswith(f"{wd} is held by another TAT conversation or compile"
                                      f" (its Python process is pid {pid})"), second
            assert not second_report.exists()
            marker.touch()
            assert await h.exited == fake.MARKER_EXIT
        assert h.stdout == fake.LINE + "\n"
        waiting, log, url = h.stderr.splitlines()
        assert (waiting, log) == (WAITING_LINE, f"Log: {log_directory(wd)}")
        given = report_of(report)
        assert given["cwd"] == str(wd / AGENTS) and given["url"] == url_of(url), given
        assert isinstance(given["status"], int) and given["signals"] == ["SIGINT"], given
        assert not running(pid)
        with pytest.raises(ConnectionRefusedError):
            socket.create_connection((HOST, port_of(given["url"])))
        after = termios.tcgetattr(slave)
        assert after != raw and after[3] & termios.ICANON and after[3] & termios.ECHO
    finally:
        os.close(master)
        os.close(slave)


async def test_codex_gets_the_launch_arguments_and_the_sweep_reaches_its_child(launcher, fake_clients, tmp_path):
    """MODULE_STRUCTURE §5: Codex started with its launch arguments and then
    the user's, the URL in its configuration; a SIGTERM to the JVM alone
    ends the client — the shutdown hook's `terminate()`, which alone keeps
    the JVM alive past Isabelle's own termination until the client has
    obeyed, within the bound — and the SIGKILL that follows reaches the
    child it left, through the snapshot taken before the SIGTERM; and the
    conversation with it."""
    wd = tmp_path / "wd"
    report = tmp_path / "report.json"
    users = ["exec", "--skip-git-repo-check", "foo"]
    async with launcher.tool(["isabelle", "TAT", "-c", "codex", str(wd), *users],
                             fake.variables("hold_a_child", report)) as h:
        await h.line("stdout", lambda line: line == fake.LINE)
        pid = conversation_pid(wd)
        (java,) = [p for p in group(h.pid) if p.comm == "java"]
        os.kill(java.pid, signal.SIGTERM)
    given = report_of(report)
    assert given["argv"] == [str(fake_clients.directory / "codex"),
                             *Codex_Server.launch_arguments(agent_directory(wd)), *users]
    assert given["url"] == url_of(next(line for line in h.stderr.splitlines() if is_url_line(line)))
    assert given["signals"] == ["SIGTERM"], given
    (child,) = given["children"]
    assert not running(given["pid"]) and not running(child)
    await conversation_exits(pid)


async def test_the_conversation_ending_first_ends_the_client(launcher, tmp_path):
    """MODULE_STRUCTURE §5: a client TAT refuses ends the conversation, and
    the conversation's end, first, ends the client — SIGTERM, which it
    ignores, then SIGKILL after the bound, reaching the sleep it orphaned
    before the SIGTERM and the one it started after — and the tool prints
    the end's messages, no `warning` echoed, and exits 2."""
    wd = tmp_path / "wd"
    report = tmp_path / "report.json"
    async with launcher.tool(["isabelle", "TAT", str(wd)],
                             fake.variables("refused", report)) as h:
        assert await h.exited == 2
    lines = h.stderr.splitlines()
    assert lines[:2] == [WAITING_LINE, f"Log: {log_directory(wd)}"], lines
    assert is_url_line(lines[2]) and lines[3] == fake.SIGTERM_LINE, lines
    assert all(line.startswith("***") for line in lines[4:]), lines
    assert lines[-1].endswith(f"TAT cannot serve this client: it is claude-code {fake.VERSION}; "
                              f"TAT requires claude-code {Claude_Code_Server.measured_version} or newer."), lines
    assert not any(line.startswith("###") for line in lines), lines
    given = report_of(report)
    assert given["signals"] == ["SIGTERM"] and len(given["children"]) == 2, given
    assert not running(given["pid"]) and not any(running(child) for child in given["children"])
    assert not running(conversation_pid(wd))


async def test_the_terminal_mode_is_restored_after_the_client_exits(launcher, tmp_path):
    """MODULE_STRUCTURE §5: the pty the tool's stdin, stdout and terminal,
    so the mode is saved; the client leaves it raw and exits on its own;
    the tool exits with the client's code, the mode is back, and after the
    client's line the escape-sequence modes were switched off.  Here the
    tool's bash leads the session and the group, so the case cannot tell
    the group from the session; step 4's probe does."""
    wd = tmp_path / "wd"
    report = tmp_path / "report.json"
    master, slave = pty.openpty()
    try:
        before = termios.tcgetattr(slave)
        async with launcher.tool(["isabelle", "TAT", str(wd)], fake.variables("raw", report),
                                 stdin=slave, stdout=slave, terminal=slave) as h:
            assert await h.exited == fake.RAW_EXIT
        assert termios.tcgetattr(slave) == before
        # the group has exited, so every write has returned; one read may hand
        # back only part, but a read flushes the pty's pending input before EAGAIN
        received = bytearray()
        os.set_blocking(master, False)
        with suppress(BlockingIOError):
            while chunk := os.read(master, 4096):
                received += chunk
        assert bytes(received) == (fake.LINE + "\r\n").encode() + ESCAPE_SEQUENCE_MODES_OFF
        assert not running(conversation_pid(wd))
    finally:
        os.close(master)
        os.close(slave)


async def test_a_client_that_cannot_be_started_ends_the_conversation(launcher, fake_clients, tmp_path):
    """MODULE_STRUCTURE §5: a client found on `PATH` that cannot be started
    is the conversation's end, one line and exit 2.  The pty is the tool's
    terminal and `/dev/null` both its stdin and stdout, so the save is
    attempted and `stty` fails, silently."""
    wd = tmp_path / "wd"
    master, slave = pty.openpty()
    devnull = os.open(os.devnull, os.O_RDWR)
    try:
        async with launcher.tool(["isabelle", "TAT", str(wd)],
                                 {"PATH": f"{fake_clients.broken}{os.pathsep}{launcher.env['PATH']}"},
                                 stdin=devnull, stdout=devnull, terminal=slave) as h:
            assert await h.exited == 2
        waiting, log, url, failure = h.stderr.splitlines()
        assert (waiting, log) == (WAITING_LINE, f"Log: {log_directory(wd)}") and is_url_line(url)
        assert failure.startswith("*** TAT cannot start claude: "), failure
        assert not running(conversation_pid(wd))
    finally:
        os.close(devnull)
        os.close(master)
        os.close(slave)


async def test_tat_mcp_serves_on_a_port_the_system_assigns(launcher, tmp_path):
    """MODULE_STRUCTURE §5: without `-p` the port is one the system assigns;
    a SIGTERM to the group ends the tool, the conversation with it."""
    wd = tmp_path / "wd"
    made = await launcher.run_tool(["isabelle", "TAT_new", str(wd)])
    assert made.returncode == 0, made
    async with launcher.tool(["isabelle", "TAT_mcp", str(wd)]) as h:
        line = await h.line("stdout", is_url_line)
        assert port_of(url_of(line)) != 8191
        h.signal_group(signal.SIGTERM)
    await conversation_exits(conversation_pid(wd))
