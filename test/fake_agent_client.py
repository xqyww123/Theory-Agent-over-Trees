"""test_launcher.py's fake agent client: the program installed as `claude`
and `codex` (`#!` this interpreter, then this file).  It writes a report of
what it was given — its pid, `cwd`, `argv`, TAT's URL from the file the
client reads, the HTTP status of a request to it, the signals it got, the
children it started — prints one line on stdout and acts as TAT_FAKE_ACT
says.  A signal is recorded, and SIGTERM then ends the fake as it ends a
client, unless the act says otherwise.  test_launcher.py imports the
constants."""

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
import tomllib
import tty
import urllib.error
import urllib.request
from pathlib import Path

LINE = "the fake agent client is running"               # the one line on stdout
SIGTERM_LINE = "the fake agent client got SIGTERM"      # on stderr, by `refused`
MARKER_EXIT = 7                                         # `exit_on_marker`'s code
RAW_EXIT = 5                                            # `raw`'s code
VERSION = "0.0.1"                                       # below `measured_version`: refused
SIGTERM_DELAY = 5.0                                     # `hold_a_child` obeys SIGTERM this many seconds after it

report: dict = {"signals": [], "children": []}


def write_report() -> None:
    path = Path(os.environ["TAT_FAKE_REPORT"])
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(report))
    os.replace(tmp, path)


def url() -> str:
    """TAT's URL from the file the client reads: the one Claude Code's
    `--mcp-config` names, Codex's `.codex/config.toml`."""
    if Path(sys.argv[0]).name == "claude":
        servers = json.loads(Path(sys.argv[sys.argv.index("--mcp-config") + 1]).read_text())["mcpServers"]
    else:
        servers = tomllib.loads(Path(".codex/config.toml").read_text())["mcp_servers"]
    (server,) = servers.values()
    return server["url"]


def on_signal(signum: int, _frame) -> None:
    report["signals"].append(signal.Signals(signum).name)
    write_report()
    if signum == signal.SIGTERM:
        on_sigterm()


def on_sigterm() -> None:
    sys.exit(128 + signal.SIGTERM)


def started() -> None:
    """What every act does first: the report, the request to TAT's URL — to
    the address itself, whatever proxy the environment names — and the line."""
    report.update(pid=os.getpid(), cwd=os.getcwd(), argv=sys.argv, url=url(), status=None)
    write_report()
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(report["url"], timeout=30) as answer:
            report["status"] = answer.status
    except urllib.error.HTTPError as e:
        report["status"] = e.code
    write_report()


def exit_on_marker() -> None:
    """The terminal's mode sane while it runs; exits once TAT_FAKE_MARKER exists."""
    started()
    subprocess.run(["stty", "sane"], check=True)
    print(LINE, flush=True)
    marker = Path(os.environ["TAT_FAKE_MARKER"])
    while not marker.exists():
        time.sleep(0.05)
    sys.exit(MARKER_EXIT)


def hold_a_child() -> None:
    """A `sleep` started and reported; SIGTERM obeyed after SIGTERM_DELAY —
    within the launcher's bound, after Isabelle's own termination."""
    global on_sigterm

    def obey_late() -> None:
        time.sleep(SIGTERM_DELAY)
        sys.exit(0)
    on_sigterm = obey_late
    started()
    report["children"] = [subprocess.Popen(["sleep", "3600"]).pid]
    write_report()
    print(LINE, flush=True)
    while True:
        signal.pause()


def refused() -> None:
    """Refused as a client: a `sh` holding a `sleep`; an MCP session as
    Claude Code opens one at a version TAT refuses, a `warning` record
    appended to the conversation's log before `tools/list`.  SIGTERM writes
    SIGTERM_LINE, SIGKILLs the `sh` (orphaning its `sleep`), starts a second
    `sleep`, reports both, and is otherwise ignored."""
    global on_sigterm
    pidfile = os.environ["TAT_FAKE_PIDFILE"]
    sh = subprocess.Popen(["sh", "-c", 'sleep 3600 & echo $! > "$1"; wait', "sh", pidfile])

    def kill_the_sh() -> None:
        os.write(2, (SIGTERM_LINE + "\n").encode())
        os.kill(sh.pid, signal.SIGKILL)
        report["children"] = [int(Path(pidfile).read_text()), subprocess.Popen(["sleep", "3600"]).pid]
        write_report()
    on_sigterm = kill_the_sh
    started()
    print(LINE, flush=True)
    session()
    while True:
        signal.pause()


def session() -> None:
    """initialize, initialized, the warning, a second, tools/list.  A failure
    before tools/list is raised; what follows it is the refusal's."""
    from mcp import ClientSession, types
    from mcp.client.streamable_http import streamable_http_client
    requested = False

    async def run() -> None:
        nonlocal requested
        async with streamable_http_client(report["url"]) as (read, write, _):
            async with ClientSession(read, write, client_info=types.Implementation(
                    name="claude-code", version=VERSION)) as s:
                await s.initialize()
                append_warning()
                await asyncio.sleep(1)
                requested = True
                await s.list_tools()
    try:
        asyncio.run(run())
    except Exception:
        if not requested:
            raise


def append_warning() -> None:
    """A `warning` record in the conversation's log: under isabelle TAT the
    launcher echoes none (MODULE_STRUCTURE §5)."""
    from isabelle_theory_agent.toplevel import LOG
    (directory,) = (Path.cwd().parent / LOG).iterdir()
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()), "category": "conversation",
              "event": "note", "level": "warning", "data": {"message": "a warning the fake agent client wrote"}}
    with (directory / "conversation.jsonl").open("a") as log:
        log.write(json.dumps(record) + "\n")


def raw() -> None:
    """The terminal left raw; exits at once."""
    started()
    print(LINE, flush=True)
    tty.setraw(0)
    sys.exit(RAW_EXIT)


ACTS = {act.__name__: act for act in (exit_on_marker, hold_a_child, refused, raw)}

if __name__ == "__main__":
    logging.disable(logging.CRITICAL)       # stderr carries this fake's lines alone, not the MCP client's logging
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    ACTS[os.environ["TAT_FAKE_ACT"]]()
