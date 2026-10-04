"""The two scripts `configure` copies into `.tat/` (CLIENT_HOOKS.md §1,
§5), run on piped payloads with no client: `guard.py`'s write, launch and
worktree answers and the answers of its own failures; `hook.py` against a
stub server answering `/hook` and against no server, through every state
`toplevel._held` leaves `tat.lock` in.  The sentences are the documents'
fenced lines.
Run: python -m pytest test/test_scripts.py
"""

import json
import os
import shutil
import subprocess
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

import isabelle_theory_agent
from baselines import DOCS, fenced_blocks
from harness import free_port
from isabelle_theory_agent.toplevel import _held

PACKAGE = Path(isabelle_theory_agent.__file__).parent
[[OUTSIDE, CLIENTS_FILES], [WORKTREES]] = fenced_blocks(DOCS / "CLIENT_HOOKS.md", "5.")
[[NOT_RUNNING]] = fenced_blocks(DOCS / "CLIENT_HOOKS.md", "1.")

ALLOW = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}


def deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


@pytest.fixture
def working_directory(tmp_path) -> Path:
    """`.tat/` holding the two scripts, and the agent directory beside it,
    as `configure` leaves them; reached through a symbolic link, as a
    user's working directory may be."""
    real = tmp_path / "real"
    (real / ".tat").mkdir(parents=True)
    for script in ("hook.py", "guard.py"):
        shutil.copy(PACKAGE / script, real / ".tat" / script)
    (real / "TAT.agents").mkdir()
    (tmp_path / "link").symlink_to(real)
    return tmp_path / "link"


def run(working_directory: Path, script: str, payload: bytes, env: dict[str, str] | None = None,
        stderr: int = subprocess.PIPE) -> subprocess.CompletedProcess[bytes]:
    """The script as the client runs it: in the agent directory, the
    interpreter in isolated mode, the payload on its standard input."""
    return subprocess.run([sys.executable, "-I", str(working_directory / ".tat" / script)],
                          input=payload, stdout=subprocess.PIPE, stderr=stderr,
                          env={**os.environ, **(env or {})}, cwd=working_directory / "TAT.agents",
                          timeout=30)


def pre_tool_use(tool: str, tool_input) -> bytes:
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool,
                       "tool_input": tool_input}).encode()


WORKTREE_CREATE = json.dumps({"hook_event_name": "WorktreeCreate", "name": "w"}).encode()


def guard(working_directory: Path, payload: bytes) -> tuple[dict | None, bytes, int]:
    """The guard's answer: its stdout as JSON (None when empty), its stderr,
    its exit status."""
    r = run(working_directory, "guard.py", payload)
    return json.loads(r.stdout) if r.stdout else None, r.stderr, r.returncode


# --- guard.py (CLIENT_HOOKS §5) ------------------------------------------------

def test_a_write_is_allowed_inside_the_agent_directory_and_refused_outside(working_directory):
    """The one rule, on the canonical path: inside, allowed — a file not yet
    existing too; the directory itself, a path leaving by `..` or by a
    symbolic link, a relative path, a path elsewhere: refused."""
    agents = working_directory / "TAT.agents"
    outside = OUTSIDE.replace("<agent directory>", str(agents.resolve()))
    (agents / "notes").mkdir()
    (agents / "away").symlink_to(working_directory)
    for tool, key in (("Write", "file_path"), ("Edit", "file_path"), ("MultiEdit", "file_path"),
                      ("NotebookEdit", "notebook_path")):
        assert guard(working_directory, pre_tool_use(tool, {key: str(agents / "notes" / "a.md")})) == (
            ALLOW, b"", 0), tool
        assert guard(working_directory, pre_tool_use(tool, {key: str(agents / "new" / "deep" / "b")})) == (
            ALLOW, b"", 0), tool
    for path in (str(agents), str(agents / ".." / "ROOT"), str(agents / "away" / "x"),
                 "a.md", str(working_directory / "TAT.sqlite"), "/etc/passwd"):
        assert guard(working_directory, pre_tool_use("Write", {"file_path": path})) == (
            deny(outside), b"", 0), path


def test_the_clients_own_files_are_refused(working_directory):
    """`.mcp.json` and `.claude/` in the agent directory; a name that only
    begins like `.claude` is a file like any other."""
    agents = working_directory / "TAT.agents"
    for path in (agents / ".mcp.json", agents / ".claude", agents / ".claude" / "settings.json",
                 agents / ".claude" / "deep" / "x"):
        assert guard(working_directory, pre_tool_use("Edit", {"file_path": str(path)})) == (
            deny(CLIENTS_FILES), b"", 0), path
    assert guard(working_directory, pre_tool_use("Edit", {"file_path": str(agents / ".claudex")})) == (
        ALLOW, b"", 0)


def test_a_launch_with_worktree_isolation_is_refused_and_any_other_left_undecided(working_directory):
    for tool in ("Agent", "Task"):
        assert guard(working_directory, pre_tool_use(tool, {"isolation": "worktree", "prompt": "p"})) == (
            deny(WORKTREES), b"", 0), tool
        assert guard(working_directory, pre_tool_use(tool, {"prompt": "p"})) == (None, b"", 0), tool


def test_a_worktree_creation_fails_with_the_sentence(working_directory):
    assert guard(working_directory, WORKTREE_CREATE) == (None, (WORKTREES + "\n").encode(), 1)


def test_a_hook_the_guard_does_not_serve_gets_no_decision(working_directory):
    assert guard(working_directory, pre_tool_use("Bash", {"command": "ls"})) == (None, b"", 0)


def test_the_guards_own_failure_answers_as_the_hook_needs(working_directory):
    """A malformed `tool_input`, or no JSON at all: a write refused, a
    launch left undecided with exit 1; a worktree creation whose sentence
    cannot be written still fails — never exit 2."""
    agents = working_directory / "TAT.agents"
    outside = OUTSIDE.replace("<agent directory>", str(agents.resolve()))
    assert guard(working_directory, pre_tool_use("Write", [1])) == (deny(outside), b"", 0)
    assert guard(working_directory, pre_tool_use("Agent", [1])) == (None, b"", 1)
    assert guard(working_directory, b"not json") == (deny(outside), b"", 0)
    reader, writer = os.pipe()
    os.close(reader)                                  # a standard error nobody reads
    try:
        r = run(working_directory, "guard.py", WORKTREE_CREATE, stderr=writer)
    finally:
        os.close(writer)
    assert r.stdout == b"" and r.returncode not in (0, 2)


# --- hook.py (CLIENT_HOOKS §1) -------------------------------------------------

class Stub(BaseHTTPRequestHandler):
    """Answers every POST with the status and body it was given, keeping
    the request."""
    status: int
    body: bytes
    requests: list[tuple[str, str | None, bytes]]

    def do_POST(self):
        payload = self.rfile.read(int(self.headers["Content-Length"]))
        self.requests.append((self.path, self.headers["Content-Type"], payload))
        self.send_response(self.status)
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, format, *args):
        pass


@contextmanager
def stub_server(status: int, body: bytes):
    """A server on a free port answering `status` with `body`; yields the
    port and the requests it received."""
    class Handler(Stub):
        pass
    Handler.status, Handler.body, Handler.requests = status, body, []
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], Handler.requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(10)


# A holder that dies holding the lock, its port announced: `os._exit` skips
# `_held`'s release as a crash does, and the kernel drops the `flock`.
DIES_HOLDING = """
import os, sys
from pathlib import Path
from isabelle_theory_agent.toplevel import _held
with _held(Path(sys.argv[1])) as announce:
    announce(int(sys.argv[2]))
    os._exit(0)
"""


def hook(working_directory: Path, payload: bytes, **env: str) -> tuple[bytes, bytes, int]:
    r = run(working_directory, "hook.py", payload, env)
    return r.stdout, r.stderr, r.returncode


def test_the_hook_posts_its_payload_and_prints_a_200_answers_body(working_directory):
    """The payload byte for byte as JSON to `/hook` at the port the lock's
    holder announced, the answer's body unchanged; an empty body is an
    empty answer; the address itself whatever proxy the environment names."""
    payload = b'{"hook_event_name": "Stop", "session_id": "s", "note": "\xe2\x80\xa6"}'
    body = b'{"decision": "block", "reason": "\xe2\x80\xa6"}'
    with stub_server(200, body) as (port, requests), _held(working_directory) as announce:
        announce(port)
        assert hook(working_directory, payload) == (body, b"", 0)
        assert requests == [("/hook", "application/json", payload)]
        # a proxy named, no host exempted
        assert hook(working_directory, payload, http_proxy="http://127.0.0.1:1",
                    HTTP_PROXY="http://127.0.0.1:1", no_proxy="", NO_PROXY="") == (body, b"", 0)
    with stub_server(200, b"") as (port, _), _held(working_directory) as announce:
        announce(port)
        assert hook(working_directory, payload) == (b"", b"", 0)


@pytest.mark.parametrize("status", [503, 500, 204])
def test_any_answer_but_200_is_tat_not_running(working_directory, status):
    with stub_server(status, b"ignored") as (port, _), _held(working_directory) as announce:
        announce(port)
        assert hook(working_directory, b"{}") == (b"", (NOT_RUNNING + "\n").encode(), 1)


def test_the_hook_fails_readably_without_a_running_conversation(working_directory):
    """`toplevel._held`'s states: the lock absent; held, the port not yet
    written; a port nothing accepts on; cleared on release; left by a
    holder that died, another server on its port — exit 1, the sentence,
    nothing on stdout, nothing posted."""
    def fails():
        assert hook(working_directory, b"{}") == (b"", (NOT_RUNNING + "\n").encode(), 1)
    fails()
    with _held(working_directory) as announce:
        fails()
        announce(free_port())
        fails()
    fails()
    with stub_server(200, b"{}") as (port, requests):
        subprocess.run([sys.executable, "-c", DIES_HOLDING, str(working_directory), str(port)],
                       check=True, timeout=30)
        fails()
        assert requests == []
