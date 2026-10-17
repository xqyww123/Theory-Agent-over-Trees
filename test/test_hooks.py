"""`POST /hook` and the agents (CONSTRUCT_INTERACTION §4, §7, §8;
MODULE_STRUCTURE §4.6): the announcement that names a call's agent, the
unannounced call, the two clients' agents, the working-call count, the
path while the conversation is ending and on a bug, the `clientInfo`
check, Codex's sandbox check, the compaction events — Codex's three
hooks, and Claude Code's transcripts read at each announcement with the
two checks (CLIENT_HOOKS.md §2, §3) — and the two judgements of §7, the
stop rule and the interruption, over a forest of test_jobs's job classes.
The payloads and the transcript lines are written in the shapes
AGENT_CLIENTS_MEASURED.md records, with invented ids (the Claude Code
builders are the harness's).
Run: python -m pytest test/test_hooks.py
"""

import asyncio
import json
import os
from collections.abc import Generator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError

import stand_ins
import test_jobs
import test_model as tm
from baselines import DOCS, fenced_blocks
from harness import (
    CLIENT_INFO, SESSION_ID, claude_code, client, compact_boundary, free_port, hook_url, post_hook, text_of,
    transcript, transcript_line)
from isabelle_theory_agent.exceptions import TAT_InternalError
from isabelle_theory_agent.jobs import BLOCKED, Message, post
from isabelle_theory_agent.mcp_server import (
    AGENTS, INTERRUPTION_DENIED, SANDBOX_STATE, SAVES_NO_TRANSCRIPT, TOOL_PREFIX, Claude_Code_Server,
    ClientRefused, Codex_Server, Interruption, Tool, boundary_before_announcement,
    post_compact_without_boundary, sandbox_is_the_profile)
from test_jobs import Checked, report
from test_mcp import Block, asked, forest
from test_mcp_server import (
    INTERNAL, NO_TRANSCRIPT, NOT_CONNECTED, NOT_SANDBOXED, SCHEMA, Bodies, ended, hold_accepting, run,
    serving)
from test_model import add, slot

CC_SUBAGENT = "a9f3c2d1e4b5"
CC_OTHER_SUBAGENT = "b7e2d4c6a8f0"
CX_SESSION = "019a7c3e-5b2d-7f41-8e6a-3c9d1b0f2a47"
CX_SUBAGENT = "019a7c3e-9d8c-7a12-b4f0-6e1d2c3b4a59"
CI = DOCS / "CONSTRUCT_INTERACTION.md"


@pytest.fixture(autouse=True)
def table(monkeypatch):
    """`test_model`'s stand-ins and `test_jobs`'s isolation, for the cases
    that build a forest with jobs."""
    tm.TABLE.clear()
    tm.TABLE.install(monkeypatch)
    yield from test_jobs.isolated(monkeypatch)

# The two messages of CONSTRUCT_INTERACTION §8 and CONSTRUCT_DECISIONS §10
# for the client's hooks failing TAT; the launcher prints them.
UNANNOUNCED = ("This call was not announced by the client's hooks, so TAT cannot tell which agent "
               "is calling.")
SECOND_ANNOUNCEMENT = ("TAT received a second announcement of the call {id} before that call arrived; "
                       "the client's hooks cannot be trusted.")


@pytest.fixture
def transcript_path() -> Generator[str]:
    """The main conversation's transcript, written before its first
    announcement as Claude Code writes it; its session directory is where a
    subagent's file goes (`subagent_file`)."""
    with transcript() as path:
        yield str(path)


def subagent_file(transcript_path: str, agent_id: str, *below: str) -> Path:
    """A subagent's transcript under the session directory (CLIENT_HOOKS.md
    §2): `subagents/<below...>/agent-<id>.jsonl`, with one line."""
    path = Path(transcript_path).with_suffix("") / "subagents" / Path(*below) / f"agent-{agent_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(transcript_line("user"))
    return path


def append(path, text: str) -> None:
    with open(path, "a") as file:
        file.write(text)


def codex(tool: str, call_id: str, agent_id: str | None = None) -> dict:
    """Codex's `PreToolUse` on a TAT tool: `tool_use_id` is the call's
    `_meta.callId`; a subagent's carries its thread id as `agent_id` and
    its own rollout file (CLIENT_HOOKS.md §3)."""
    thread = agent_id or CX_SESSION
    payload = {"session_id": CX_SESSION,
               "transcript_path": f"/home/agent/.codex/sessions/rollout-{thread}.jsonl",
               "cwd": "/work/TAT.agents", "hook_event_name": "PreToolUse",
               "tool_name": TOOL_PREFIX + tool, "tool_input": {}, "tool_use_id": call_id}
    if agent_id is not None:
        payload |= {"agent_id": agent_id, "agent_type": "default"}
    return payload


def codex_meta(call_id: str, thread: str, working_directory) -> dict:
    """A Codex call's `_meta` in the measured shape: the call's id, the
    thread's own id, the session's, and the sandbox policy in force (§5)."""
    return {"callId": call_id, "threadId": thread, "sessionId": CX_SESSION, "progressToken": 3,
            SANDBOX_STATE: the_profile(working_directory)}


def info(server_class) -> types.Implementation:
    return types.Implementation(name=server_class.client_name, version=server_class.measured_version)


@asynccontextmanager
async def plain_client(url: str, client_info: types.Implementation = CLIENT_INFO):
    """A client session that announces nothing by itself: the test does."""
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write, client_info=client_info) as session:
            await session.initialize()
            yield session


def records(category: str) -> list[tuple]:
    """Each record's event, `agent` and `call`."""
    return [(r["event"], r.get("agent"), r.get("call")) for r in stand_ins.records(category)]


def tool_records() -> list[tuple]:
    return records("tool")


def answers() -> list[tuple]:
    """Each `hook.answer`'s `judged` — None when absent — and status."""
    return [(r["data"].get("judged"), r["data"]["status"]) for r in stand_ins.records("hook")
            if r["event"] == "answer"]


def test_an_announced_call_is_served_and_its_records_name_the_call_and_the_agent(transcript_path):
    """CONSTRUCT_INTERACTION §8; LOGGING.md §3: the announcement is answered
    the grant and creates the agent; the call it named is served; the
    records of the hook request, of the agent's creation and of the call
    carry the call's id and the agent; the client's `clientInfo` is
    recorded once, belonging to no call."""
    async def scenario():
        bodies = Bodies()
        async with serving(free_port(), bodies.tools()) as (server, serve), \
                plain_client(server.url) as session:
            payload = claude_code("echo", "toolu_01", transcript_path=transcript_path)
            r = await post_hook(hook_url(server.url), payload)
            assert r.status_code == 200 and r.json() == Claude_Code_Server.announcement_answer
            result = await session.call_tool("echo", {"text": "hi"},
                                             meta={"claudecode/toolUseId": "toolu_01", "progressToken": 1})
            assert (text_of(result), result.isError) == ("echo hi", False) and not serve.done()
            assert list(server.agents) == ["main"] and server.agents["main"].main
            assert tool_records() == [("call", "main", "toolu_01"), ("result", "main", "toolu_01")]
            assert records("hook") == [("request", "main", "toolu_01"), ("answer", "main", "toolu_01")]
            request, answer = stand_ins.records("hook")
            assert request["data"] == {"payload": payload}
            assert {k: answer["data"][k] for k in ("judged", "status", "body")} == {
                "judged": "announcement", "status": 200, "body": Claude_Code_Server.announcement_answer}
            created, read = stand_ins.records("agent")
            assert (created["event"], created["agent"], created["call"], created["data"]) == (
                "created", "main", "toolu_01", {"identity": "main", "main": True, "first": "hook"})
            assert (read["event"], read["level"], read["agent"], read["call"]) == (
                "transcript_read", "debug", "main", "toolu_01")
            assert read["data"] == {"file": transcript_path, "offset": 0, "lines": 1, "boundaries": [],
                                    "bytes": Path(transcript_path).stat().st_size}
            [connected] = stand_ins.records("conversation")
            assert (connected["event"], connected["data"]) == (
                "client_connected", {"name": "claude-code", "version": "2.1.296"})
            assert "call" not in connected and "agent" not in connected
    run(scenario)


@pytest.mark.parametrize("meta", [None, {"claudecode/toolUseId": "toolu_unknown"},
                                  {"claudecode/toolUseId": "toolu_00"}],
                         ids=["no id", "an id no announcement named", "an id already spent"])
def test_an_unannounced_call_ends_the_conversation(meta, transcript_path):
    """CONSTRUCT_INTERACTION §8: TAT never guesses, an agent at hand or
    not — a call carrying no id, one no announcement named, or one whose
    announcement a first call has spent, ends the conversation with a
    `TAT_InternalError`; the call is answered the first line of
    RENDER_BASELINES §4, after `call` the `unannounced` record is written,
    naming no agent."""
    async def scenario():
        bodies = Bodies()
        async with serving(free_port(), bodies.tools()) as (server, serve), \
                plain_client(server.url) as session:
            url = hook_url(server.url)
            await post_hook(url, claude_code("echo", "toolu_00", transcript_path=transcript_path))
            served = await session.call_tool("echo", {"text": "first"}, meta={"claudecode/toolUseId": "toolu_00"})
            assert text_of(served) == "echo first"
            result = await session.call_tool("echo", {"text": "hi"}, meta=meta)
            assert (text_of(result), result.isError) == (INTERNAL, True)
            exn = await ended(serve)
            assert isinstance(exn, TAT_InternalError) and str(exn) == UNANNOUNCED
            call = None if meta is None else meta["claudecode/toolUseId"]
            assert tool_records()[2:] == [("call", None, call), ("unannounced", None, call),
                                          ("while_ending", None, call)]
            unannounced = stand_ins.records("tool")[3]
            assert unannounced["level"] == "error"
            assert unannounced["data"] == {"tool": "echo", "message": UNANNOUNCED} | (
                {} if meta is None else {"_meta": meta})
            assert list(server.agents) == ["main"]
    run(scenario)


def test_a_second_announcement_of_a_pending_call_is_a_bug_of_the_path(transcript_path):
    """CONSTRUCT_DECISIONS §10: the ids are unique by the clients' measured
    behaviour, so a `tool_use_id` announced again before its call arrived
    breaks TAT's premise about the hooks — the conversation ends with the
    approved message, the hook is answered an empty 500, and the answer's
    record carries no `judged`."""
    async def scenario():
        async with serving(free_port(), []) as (server, serve):
            url = hook_url(server.url)
            payload = claude_code("echo", "toolu_05", transcript_path=transcript_path)
            assert (await post_hook(url, payload)).status_code == 200
            r = await post_hook(url, payload)
            assert r.status_code == 500 and r.content == b""
            exn = await ended(serve)
            assert isinstance(exn, TAT_InternalError)
            assert str(exn) == SECOND_ANNOUNCEMENT.format(id="toolu_05")
            assert answers() == [("announcement", 200), (None, 500)]
    run(scenario)


@pytest.mark.parametrize("server_class, payload, meta, main_identity, subagent, created", [
    (Claude_Code_Server, claude_code, lambda call_id, thread, wd: {"claudecode/toolUseId": call_id},
     "main", CC_SUBAGENT, [("main", True, "hook"), (CC_SUBAGENT, False, "hook")]),
    (Codex_Server, lambda tool, call_id, agent_id=None, transcript_path=None: codex(tool, call_id, agent_id),
     codex_meta, CX_SESSION, CX_SUBAGENT, [(CX_SUBAGENT, False, "call"), (CX_SESSION, True, "call")])],
    ids=["claude-code", "codex"])
def test_the_main_conversation_and_a_subagent_are_two_agents_on_each_client(
        tmp_path, transcript_path, server_class, payload, meta, main_identity, subagent, created):
    """CONSTRUCT_INTERACTION §4, §8; CLIENT_HOOKS.md §2, §3.  On Claude Code
    the announcement names the agent — `agent_id`, or `main` — and
    creates it; on Codex the announcement names the call alone, and the
    call's `_meta.threadId` names the agent, created at the call, the main
    conversation when it is the session's own thread.  Each call reaches
    its agent in whatever order the calls come; the hook records carry the
    identity the payload gives; Codex's announcements are answered
    nothing, and its calls carry the sandbox policy (§5)."""
    async def scenario():
        bodies = Bodies()
        subagent_file(transcript_path, CC_SUBAGENT)
        async with serving(free_port(), bodies.tools(), server_class=server_class) as (server, serve), \
                plain_client(server.url, info(server_class)) as session:
            server.configure(tmp_path)
            url = hook_url(server.url)
            for r in (await post_hook(url, payload("echo", "id-main", transcript_path=transcript_path)),
                      await post_hook(url, payload("echo", "id-sub", agent_id=subagent,
                                                   transcript_path=transcript_path))):
                assert r.status_code == 200
                if server_class.announcement_answer is None:
                    assert r.content == b"" and r.headers["content-type"].startswith("text/plain")
                else:
                    assert r.json() == server_class.announcement_answer
            assert records("hook") == [("request", main_identity, "id-main"), ("answer", main_identity, "id-main"),
                                       ("request", subagent, "id-sub"), ("answer", subagent, "id-sub")]
            for call_id, identity in (("id-sub", subagent), ("id-main", main_identity)):
                result = await session.call_tool("echo", {"text": identity},
                                                 meta=meta(call_id, identity, tmp_path))
                assert (text_of(result), result.isError) == ("echo " + identity, False)
            assert not serve.done()
            assert {identity: agent.main for identity, agent in server.agents.items()} == {
                main_identity: True, subagent: False}
            assert tool_records() == [
                ("call", subagent, "id-sub"), ("result", subagent, "id-sub"),
                ("call", main_identity, "id-main"), ("result", main_identity, "id-main")]
            assert [(r["data"]["identity"], r["data"]["main"], r["data"]["first"])
                    for r in stand_ins.records("agent") if r["event"] == "created"] == created
    run(scenario)


def test_the_working_call_count_follows_the_body_not_the_client():
    """CONSTRUCT_INTERACTION §4: the count rises as soon as the agent is
    named and falls when the body ends — after the client gave up on the
    call, the body still running, it still counts; the `given_up` record
    carries the call and the agent (LOGGING.md §3)."""
    async def scenario():
        bodies = Bodies()
        async with serving(free_port(), bodies.tools()) as (server, serve), client(server.url) as session:
            request_id = session._request_id             # the id the next request takes
            call = asyncio.create_task(session.call_tool("slow", {}))
            await bodies.began("slow").wait()
            [agent] = server.agents.values()
            assert agent.working_calls == 1
            await session.send_notification(types.ClientNotification(types.CancelledNotification(
                method="notifications/cancelled",
                params=types.CancelledNotificationParams(requestId=request_id))))
            with pytest.raises(McpError, match="Request cancelled"):
                await call
            assert agent.working_calls == 1 and "slow" not in bodies.finished
            bodies.release.set()
            later = await session.call_tool("echo", {"text": "on"})
            assert text_of(later) == "echo on" and "slow" in bodies.finished
            assert agent.working_calls == 0 and not serve.done()
            (_, _, slow_id), given_up = tool_records()[0], tool_records()[1]
            assert given_up == ("given_up", "main", slow_id) and slow_id is not None
    run(scenario)


def test_the_path_answers_503_while_ending_and_500_on_a_bug_and_ignores_other_hooks():
    """MODULE_STRUCTURE §4.6: a hook TAT has no rule for yet is answered
    nothing, its records naming the agent the payload names; the transport
    check is `/mcp`'s, with no content type asked; a payload that breaks the
    client's documented shape, or that is no JSON object, is a bug on the
    path — the conversation ends and the hook gets an empty 500, exit 1 for
    the script, no block; an empty 503 while the conversation is ending.
    Neither a 500 nor a 503 records a `judged`."""
    async def scenario():
        async with serving(free_port(), []) as (server, serve):
            url = hook_url(server.url)
            stop = {"session_id": CX_SESSION, "hook_event_name": "Stop", "stop_hook_active": False}
            r = await post_hook(url, stop)
            assert r.status_code == 200 and r.content == b""
            assert records("hook") == [("request", "main", None), ("answer", "main", None)]
            async with httpx.AsyncClient(trust_env=False) as http:
                assert (await http.get(url)).status_code == 405
                assert (await http.post(url, json=stop, headers={"Host": "localhost"})).status_code == 421
                assert (await http.post(url, content=b"{}")).status_code == 200   # no content type
            broken = claude_code("echo", "toolu_02")
            del broken["tool_use_id"]
            r = await post_hook(url, broken)
            assert r.status_code == 500 and r.content == b""
            exn = await ended(serve)
            assert isinstance(exn, TAT_InternalError) and "tool_use_id" in str(exn)
        # a `Stop` of an agent TAT has not met is judged, and allowed with nothing answered (CI §7)
        assert answers() == [("stop", 200), ("ignored", 200), (None, 500)]

        async with serving(free_port(), []) as (server, serve):
            r = await post_hook(hook_url(server.url), [1, 2])
            assert r.status_code == 500 and r.content == b""
            assert isinstance(await ended(serve), TAT_InternalError)
        assert answers()[-1] == (None, 500)

        async with serving(free_port(), []) as (server, serve):
            accepting = hold_accepting(server)
            server.ending.end(RuntimeError("ended"))
            r = await post_hook(hook_url(server.url), claude_code("echo", "toolu_03"))
            assert r.status_code == 503 and r.content == b"" and server.agents == {}
            accepting.set()
            assert isinstance(await ended(serve), RuntimeError)
        assert answers()[-1] == (None, 503)
    run(scenario)


@pytest.mark.parametrize("server_class, name, version, served", [
    (Claude_Code_Server, "claude-code", "2.1.296", True), (Claude_Code_Server, "claude-code", "2.1.300", True),
    (Claude_Code_Server, "claude-code", "3.0.0-beta", True),
    (Claude_Code_Server, "claude-code", "2.1.295", False), (Claude_Code_Server, "claude-code", "2.1", False),
    (Claude_Code_Server, "claude-code", "dev", False), (Claude_Code_Server, "codex-mcp-client", "2.1.296", False),
    (Codex_Server, "codex-mcp-client", "0.163.0", True), (Codex_Server, "codex-mcp-client", "0.162.9", False),
    (Codex_Server, "claude-code", "2.1.296", False)])
def test_the_client_info_check(server_class, name, version, served):
    """CONSTRUCT_INTERACTION §8; MODULE_STRUCTURE §4.6: at a session's first
    request the `clientInfo` is checked — the name against the one the
    subclass expects, the leading dotted numbers of the version against the
    measured one.  Equal or higher is served, with `client_connected` once
    per session; lower, unreadable or another client's name is refused: no
    tool is served, every call is answered the sixth line, the conversation
    ends with the `ClientRefused` the launcher prints — naming the client
    `-c` takes — and `client_refused` is recorded."""
    async def scenario():
        bodies = Bodies()
        async with serving(free_port(), bodies.tools(), server_class=server_class) as (server, serve):
            accepting = hold_accepting(server)
            async with plain_client(server.url, types.Implementation(name=name, version=version)) as session:
                if served:
                    listed = await session.list_tools()
                    assert [t.name for t in listed.tools] == [t.name for t in bodies.tools()]
                    assert (await session.list_tools()).tools == listed.tools and not serve.done()
                    [connected] = stand_ins.records("conversation")
                    assert (connected["event"], connected["data"]) == (
                        "client_connected", {"name": name, "version": version})
                else:
                    result = await session.call_tool("echo", {"text": "a"})      # the first request
                    assert (text_of(result), result.isError) == (NOT_CONNECTED, True)
                    assert (await session.list_tools()).tools == []
                    accepting.set()
                    exn = await ended(serve)
                    sentence = (f"TAT cannot serve this client: it is {name} {version}; "
                                f"TAT requires {server_class.name} {server_class.measured_version} or newer.")
                    assert isinstance(exn, ClientRefused) and str(exn) == sentence
                    assert exn.line == NOT_CONNECTED
                    [refused] = [r for r in stand_ins.records("conversation") if r["event"] == "client_refused"]
                    assert refused["level"] == "error" and "call" not in refused
                    assert refused["data"] == {"name": name, "version": version, "message": sentence}
                    assert tool_records() == [("call", None, None), ("while_ending", None, None)]
            accepting.set()
    run(scenario)


def test_the_check_is_per_session_and_a_refused_session_alone_is_served_no_tool(transcript_path):
    """CONSTRUCT_INTERACTION §8: every MCP session is checked at its first
    request, `tools/list` or `tools/call`; a session that passed lists the
    tools even while the conversation ends for a session that failed, which
    is answered an empty list."""
    async def scenario():
        bodies = Bodies()
        async with serving(free_port(), bodies.tools()) as (server, serve):
            accepting = hold_accepting(server)
            lower = types.Implementation(name="claude-code", version="2.1.0")
            async with plain_client(server.url) as first, plain_client(server.url) as second:
                assert len((await first.list_tools()).tools) == len(bodies.tools())
                await post_hook(hook_url(server.url),
                                claude_code("echo", "toolu_06", transcript_path=transcript_path))
                result = await first.call_tool("echo", {"text": "a"}, meta={"claudecode/toolUseId": "toolu_06"})
                assert text_of(result) == "echo a"
                assert len((await second.list_tools()).tools) == len(bodies.tools())
                assert [r["event"] for r in stand_ins.records("conversation")] == [
                    "client_connected", "client_connected"]
                async with plain_client(server.url, lower) as third:
                    refused = await third.call_tool("echo", {"text": "b"})       # its first request, a call
                    assert (text_of(refused), refused.isError) == (NOT_CONNECTED, True)
                    assert (await third.list_tools()).tools == []
                    assert len((await first.list_tools()).tools) == len(bodies.tools())
                    accepting.set()
                    assert isinstance(await ended(serve), ClientRefused)
    run(scenario)


def the_profile(working_directory) -> dict:
    """Codex's `_meta["codex/sandbox-state-meta"]` under TAT's profile as
    recorded on a host running systemd-resolved (AGENT_CLIENTS_MEASURED.md,
    the final files), Codex's own install paths left out: the `deny` on the
    working directory, which TAT recognises it by (CLIENT_HOOKS.md §5),
    comes after the resolver's read entry."""
    agents = working_directory / AGENTS
    return {"permissionProfile": {"type": "managed", "file_system": {"type": "restricted", "entries": [
        {"path": {"type": "path", "path": "/run/systemd/resolve/stub-resolv.conf"}, "access": "read"},
        {"path": {"type": "path", "path": str(working_directory)}, "access": "deny"},
        {"path": {"type": "special", "value": {"kind": "minimal"}}, "access": "read"},
        {"path": {"type": "path", "path": str(agents)}, "access": "write"}]},
        "network": "enabled"},
        "sandboxCwd": agents.as_uri(), "useLegacyLandlock": False}


def test_the_profile_is_recognised_by_real_path(tmp_path):
    """A working directory reached through a link: the profile is recognised
    whether Codex sends back the path configure wrote or its real path."""
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    assert sandbox_is_the_profile(the_profile(link), link)
    assert sandbox_is_the_profile(the_profile(real), link)
    assert not sandbox_is_the_profile(the_profile(tmp_path), link)


def restricted(*entries) -> dict:
    return {"permissionProfile": {"type": "managed", "file_system": {"type": "restricted", "entries": list(entries)}}}


ROOT_READ = {"path": {"type": "special", "value": {"kind": "root"}}, "access": "read"}


@pytest.mark.parametrize("policy", [
    lambda wd: None, lambda wd: {"type": "disabled"},
    lambda wd: restricted(ROOT_READ),
    lambda wd: restricted({"path": {"type": "path", "path": "/elsewhere"}, "access": "deny"}),
    lambda wd: restricted(ROOT_READ, {"path": {"type": "path", "path": str(wd / AGENTS)}, "access": "write"},
                          {"path": {"type": "path", "path": str(wd)}, "access": "write"})],
    ids=["no policy", "disabled", "read-only", "another directory denied", "the working directory writable"])
def test_the_codex_sandbox_check(tmp_path, policy):
    """CLIENT_HOOKS.md §5; CONSTRUCT_INTERACTION §8: the Codex server
    declares the capability under which every call carries the sandbox
    policy in force; a call under TAT's profile is served, one whose policy
    is anything else refuses the session — every call in flight and after
    is answered the fifth line, the conversation ends with the
    `ClientRefused` the launcher prints, `client_refused` carries the
    call's `_meta`.  Claude Code declares no such capability."""
    async def scenario():
        bodies = Bodies()
        async with serving(free_port(), bodies.tools(), server_class=Codex_Server) as (server, serve):
            server.configure(tmp_path)
            async with plain_client(server.url, info(Codex_Server)) as session:
                url = hook_url(server.url)
                good = the_profile(tmp_path)
                await post_hook(url, codex("echo", "c1"))
                result = await session.call_tool("echo", {"text": "a"}, meta={
                    "callId": "c1", "threadId": CX_SESSION, "sessionId": CX_SESSION, SANDBOX_STATE: good})
                assert (text_of(result), result.isError) == ("echo a", False)
                await post_hook(url, codex("slow", "c2"))
                in_flight = asyncio.create_task(session.call_tool("slow", {}, meta={
                    "callId": "c2", "threadId": CX_SESSION, "sessionId": CX_SESSION, SANDBOX_STATE: good}))
                await bodies.began("slow").wait()
                await post_hook(url, codex("echo", "c3"))
                refusing = policy(tmp_path)
                meta = {"callId": "c3"} | ({} if refusing is None else {SANDBOX_STATE: refusing})
                refused = await session.call_tool("echo", {"text": "b"}, meta=meta)
                assert (text_of(refused), refused.isError) == (NOT_SANDBOXED, True)
                slow = await in_flight
                assert (text_of(slow), slow.isError) == (NOT_SANDBOXED, True)
                exn = await ended(serve)
                sentence = ("TAT refuses this Codex session: its sandbox is not the one TAT configured. "
                            f"Start Codex in {tmp_path / AGENTS} without a sandbox option.")
                assert isinstance(exn, ClientRefused) and str(exn) == sentence and exn.line == NOT_SANDBOXED
                [record] = [r for r in stand_ins.records("conversation") if r["event"] == "client_refused"]
                assert record["data"] == {"name": Codex_Server.client_name, "version": Codex_Server.measured_version,
                                          "message": sentence, "_meta": meta}
                assert [e for e, _, _ in tool_records()] == [
                    "call", "result", "call", "call", "while_ending", "while_ending"]
        async with serving(free_port(), [], server_class=Codex_Server) as (server, _), \
                streamable_http_client(server.url) as (r, w, _), \
                ClientSession(r, w, client_info=info(Codex_Server)) as session:
            assert (await session.initialize()).capabilities.experimental == {SANDBOX_STATE: {}}
        async with serving(free_port(), []) as (server, _), streamable_http_client(server.url) as (r, w, _), \
                ClientSession(r, w, client_info=CLIENT_INFO) as session:
            assert not (await session.initialize()).capabilities.experimental
    run(scenario)


# --- the compaction events (CONSTRUCT_INTERACTION §8; CLIENT_HOOKS.md §2, §3) ------

def compactions() -> list[tuple]:
    """Each `agent.compaction` record's agent and data."""
    return [(r["agent"], r["data"]) for r in stand_ins.records("agent") if r["event"] == "compaction"]


def check_failures() -> list[dict]:
    return [r for r in stand_ins.records("agent") if r["event"] == "check_failed"]


def reads(file) -> list[dict]:
    """The `transcript_read` records of one file."""
    return [r["data"] for r in stand_ins.records("agent")
            if r["event"] == "transcript_read" and r["data"]["file"] == str(file)]


def uuid_of(line: str) -> str:
    return json.loads(line)["uuid"]


async def announce(url: str, tool_use_id: str, transcript_path: str, agent_id: str | None = None) -> None:
    """A Claude Code announcement, answered the grant."""
    r = await post_hook(url, claude_code("echo", tool_use_id, agent_id, transcript_path=transcript_path))
    assert r.status_code == 200 and r.json() == Claude_Code_Server.announcement_answer, r.text


def test_a_compaction_boundary_clears_the_compacting_agents_set_at_its_next_announcement(transcript_path):
    """CLIENT_HOOKS.md §2; PRINT.md §4: a `compact_boundary` line TAT has not
    recorded, read at the agent's next announcement, clears that agent's
    seen set and no other's, with the `compaction` record naming the
    line; a recorded boundary is not counted again; a last line without
    its newline waits until it is complete; a workflow agent's file is
    found under `subagents/workflows/<run>/`."""
    async def scenario():
        file = subagent_file(transcript_path, CC_SUBAGENT, "workflows", "wf_01")
        async with serving(free_port(), []) as (server, serve):
            url = hook_url(server.url)
            await announce(url, "toolu_m1", transcript_path)
            await announce(url, "toolu_s1", transcript_path, CC_SUBAGENT)
            main, sub = server.agents["main"], server.agents[CC_SUBAGENT]
            main.seen.add((1, None))
            sub.seen.add((2, "beginning"))
            first = compact_boundary()
            append(file, first)
            await announce(url, "toolu_s2", transcript_path, CC_SUBAGENT)
            assert sub.seen == set() and main.seen == {(1, None)}
            assert compactions() == [(CC_SUBAGENT, {"learned_from": "compact_boundary", "seen_cleared": 1,
                                                    "uuid": uuid_of(first)})]
            sub.seen.add((3, None))
            await announce(url, "toolu_s3", transcript_path, CC_SUBAGENT)   # the boundary is recorded
            assert sub.seen == {(3, None)} and len(compactions()) == 1
            # a line not yet complete; a record of another type is no boundary, whatever its subtype
            append(file, transcript_line("assistant", subtype="compact_boundary").rstrip("\n"))
            await announce(url, "toolu_s4", transcript_path, CC_SUBAGENT)
            assert sub.seen == {(3, None)} and len(compactions()) == 1
            second = compact_boundary()
            append(file, "\n" + second)
            await announce(url, "toolu_s5", transcript_path, CC_SUBAGENT)
            assert sub.seen == set() and not serve.done()
            assert [(agent, data["uuid"]) for agent, data in compactions()] == [
                (CC_SUBAGENT, uuid_of(first)), (CC_SUBAGENT, uuid_of(second))]
            read = reads(file)
            assert [(r["lines"], r["boundaries"]) for r in read] == [
                (1, []), (1, [uuid_of(first)]), (0, []), (0, []), (2, [uuid_of(second)])]
            assert [r["offset"] for r in read] == [0, *(r["offset"] + r["bytes"] for r in read[:3]),
                                                  read[3]["offset"]]   # the incomplete line was not consumed
    run(scenario)


def agent_file(transcript_path, agent_id: str | None) -> Path:
    """The agent's own transcript under a session: the main conversation's
    is the session's, a subagent's is made."""
    return Path(transcript_path) if agent_id is None else subagent_file(str(transcript_path), agent_id)


@pytest.mark.parametrize("agent_id", [None, CC_SUBAGENT], ids=["the main conversation", "a subagent"])
def test_a_changed_transcript_path_is_a_compaction_and_what_a_file_first_holds_is_none(transcript_path, agent_id):
    """CLIENT_HOOKS.md §2: `/clear` and `/resume` give the conversation a new
    transcript; the announcement carrying it clears the agent's set — a
    subagent's as the main conversation's — and the agent's file under it
    is read from its first line.  The boundaries a file holds when it is
    first read are recorded and are no event: nothing was shown under it
    yet.  A return to an earlier path counts nothing twice; a boundary
    written after it is an event."""
    identity = agent_id or "main"

    async def scenario():
        with transcript() as new_path:
            await across(new_path)

    async def across(new_path):
        old, new = agent_file(transcript_path, agent_id), agent_file(new_path, agent_id)
        append(old, compact_boundary())           # there before TAT first reads the file
        async with serving(free_port(), []) as (server, serve):
            url = hook_url(server.url)
            await announce(url, "toolu_1", transcript_path, agent_id)
            agent = server.agents[identity]
            assert compactions() == []
            counted = compact_boundary()
            append(old, counted)
            await announce(url, "toolu_2", transcript_path, agent_id)
            agent.seen.add((1, None))
            held = compact_boundary()
            append(new, held)                     # in the new file before its first reading
            await announce(url, "toolu_3", str(new_path), agent_id)
            assert agent.seen == set()
            agent.seen.add((2, None))
            await announce(url, "toolu_4", transcript_path, agent_id)   # back: nothing counted twice
            assert agent.seen == set()
            agent.seen.add((3, None))
            after = compact_boundary()
            append(old, after)
            await announce(url, "toolu_5", transcript_path, agent_id)
            assert agent.seen == set() and not serve.done()
            assert compactions() == [
                (identity, {"learned_from": "compact_boundary", "seen_cleared": 0, "uuid": uuid_of(counted)}),
                (identity, {"learned_from": "transcript_path_changed", "seen_cleared": 1,
                            "previous": transcript_path, "current": str(new_path)}),
                (identity, {"learned_from": "transcript_path_changed", "seen_cleared": 1,
                            "previous": str(new_path), "current": transcript_path}),
                (identity, {"learned_from": "compact_boundary", "seen_cleared": 1, "uuid": uuid_of(after)})]
            assert [(r["offset"], r["boundaries"]) for r in reads(new)] == [(0, [uuid_of(held)])]
            # the file is kept across the agent's absence: read on from where the reading stopped
            assert [r["offset"] == 0 for r in reads(old)] == [True, False, False, False]
    run(scenario)


def test_a_transcript_whose_read_part_is_gone_is_a_compaction_and_is_read_again(transcript_path):
    """CLIENT_HOOKS.md §2; PRINT.md §4: Claude Code cuts the main transcript
    in place when a message is removed, and can rewrite it under its name
    (AGENT_CLIENTS_MEASURED.md) — a file no longer holding what TAT read
    of it, or another file at the path, is that agent's compaction event,
    `transcript_changed` naming the file, and is read again from its
    first line, so a boundary written after the cut is found and one
    recorded before is not counted again."""
    async def scenario():
        path = Path(transcript_path)
        async with serving(free_port(), []) as (server, serve):
            url = hook_url(server.url)
            await announce(url, "toolu_1", transcript_path)
            main = server.agents["main"]
            first = compact_boundary()
            append(path, first)
            await announce(url, "toolu_2", transcript_path)
            main.seen.add((1, None))
            path.write_text(path.read_text().splitlines(keepends=True)[0])     # cut in place
            await announce(url, "toolu_3", transcript_path)
            assert main.seen == set()
            main.seen.add((2, None))
            second = compact_boundary()
            append(path, second)
            await announce(url, "toolu_4", transcript_path)
            main.seen.add((3, None))
            replacement = path.with_suffix(".new")
            third = compact_boundary()
            replacement.write_text(path.read_text() + third)                    # rewritten under its name
            os.replace(replacement, path)
            await announce(url, "toolu_5", transcript_path)
            assert main.seen == set() and not serve.done() and check_failures() == []
            assert [(d["learned_from"], d.get("uuid", d.get("file")), d["seen_cleared"]) for _, d in compactions()] == [
                ("compact_boundary", uuid_of(first), 0), ("transcript_changed", transcript_path, 1),
                ("compact_boundary", uuid_of(second), 1), ("transcript_changed", transcript_path, 1),
                ("compact_boundary", uuid_of(third), 0)]      # `second`, read again, is not counted again
            assert [(r["offset"] == 0, r["boundaries"]) for r in reads(path)] == [
                (True, []), (False, [uuid_of(first)]), (True, []), (False, [uuid_of(second)]),
                (True, [uuid_of(second), uuid_of(third)])]
    run(scenario)


@pytest.mark.parametrize("case", ["the main conversation's file is not there",
                                  "the main conversation's file is not there, after an internal announcement",
                                  "the payload names no transcript", "the file is gone after it was read",
                                  "a subagent's file is gone after it was read"])
def test_an_agent_without_a_transcript_cannot_be_served(transcript_path, case):
    """CONSTRUCT_INTERACTION §8; CLIENT_HOOKS.md §2: a main conversation
    whose transcript TAT does not find at an announcement — its file not
    there, an internal agent's announcement before or not, a payload
    naming none — and an agent, main or subagent, whose file was there and
    is gone, end the conversation with the `ClientRefused` the launcher
    prints and `client_refused`; every call is answered the fourth line of
    RENDER_BASELINES §4."""
    async def scenario():
        bodies = Bodies()
        async with serving(free_port(), bodies.tools()) as (server, serve):
            accepting = hold_accepting(server)
            url = hook_url(server.url)
            payload = claude_code("echo", "toolu_1", transcript_path=transcript_path)
            if case.startswith("the main conversation's file is not there"):
                if case.endswith("announcement"):
                    await post_hook(url, internal("toolu_i", transcript_path))
                payload["transcript_path"] = "/nowhere/" + Path(transcript_path).name
            elif case == "the payload names no transcript":
                del payload["transcript_path"]
            elif case == "a subagent's file is gone after it was read":
                file = subagent_file(transcript_path, CC_SUBAGENT)
                await announce(url, "toolu_0", transcript_path, CC_SUBAGENT)
                os.unlink(file)
                payload = claude_code("echo", "toolu_1", CC_SUBAGENT, transcript_path=transcript_path)
            else:
                await announce(url, "toolu_0", transcript_path)
                os.unlink(transcript_path)
            async with plain_client(server.url) as session:
                await session.list_tools()
                r = await post_hook(url, payload)
                assert r.status_code == 200 and r.json() == Claude_Code_Server.announcement_answer
                result = await session.call_tool("echo", {"text": "a"}, meta={"claudecode/toolUseId": "toolu_1"})
                assert (text_of(result), result.isError) == (NO_TRANSCRIPT, True)
                accepting.set()
                exn = await ended(serve)
                assert isinstance(exn, ClientRefused) and str(exn) == SAVES_NO_TRANSCRIPT
                assert exn.line == NO_TRANSCRIPT
                [refused] = [r for r in stand_ins.records("conversation") if r["event"] == "client_refused"]
                assert refused["data"] == {"name": CLIENT_INFO.name, "version": CLIENT_INFO.version,
                                           "message": SAVES_NO_TRANSCRIPT}
                assert compactions() == []
    run(scenario)


def test_a_subagents_file_not_found_yet_is_read_from_the_first_announcement_at_which_it_exists(transcript_path):
    """CLIENT_HOOKS.md §2: a subagent whose file TAT does not find at an
    announcement is served, its transcript not read; the file is read from
    the first announcement at which it exists, from its first line — what
    it holds then is no event — and a boundary written after that is the
    subagent's compaction event."""
    async def scenario():
        bodies = Bodies()
        async with serving(free_port(), bodies.tools()) as (server, serve), plain_client(server.url) as session:
            url = hook_url(server.url)
            await announce(url, "toolu_s1", transcript_path, CC_SUBAGENT)          # no file yet
            served = await session.call_tool("echo", {"text": "a"}, meta={"claudecode/toolUseId": "toolu_s1"})
            assert text_of(served) == "echo a" and list(server.agents) == [CC_SUBAGENT] and not serve.done()
            assert [r for r in stand_ins.records("agent") if r["event"] == "transcript_read"] == []
            file = subagent_file(transcript_path, CC_SUBAGENT)
            earlier = compact_boundary()
            append(file, earlier)
            sub = server.agents[CC_SUBAGENT]
            sub.seen.add((1, None))
            await announce(url, "toolu_s2", transcript_path, CC_SUBAGENT)          # read from its first line
            assert [(r["offset"], r["lines"], r["boundaries"]) for r in reads(file)] == [(0, 2, [uuid_of(earlier)])]
            assert sub.seen == {(1, None)} and compactions() == []               # what the file first held
            later = compact_boundary()
            append(file, later)
            await announce(url, "toolu_s3", transcript_path, CC_SUBAGENT)
            assert sub.seen == set() and not serve.done()
            assert compactions() == [(CC_SUBAGENT, {"learned_from": "compact_boundary", "seen_cleared": 1,
                                                    "uuid": uuid_of(later)})]
    run(scenario)


def test_a_boundary_older_than_the_agents_previous_announcement_fails_the_first_check(transcript_path):
    """CONSTRUCT_INTERACTION §8, the first check: a boundary whose own
    timestamp precedes the agent's previous served announcement — that
    agent's own, the latest — means TAT rendered a result into a context
    that was then replaced unseen: the conversation ends with the check's
    message, every call is answered the first line of RENDER_BASELINES §4,
    `check_failed` is recorded, and no set is cleared.  A boundary older
    than another agent's announcement alone is that agent's compaction."""
    async def scenario():
        bodies = Bodies()
        subagent_file(transcript_path, CC_SUBAGENT)
        async with serving(free_port(), bodies.tools()) as (server, serve), \
                plain_client(server.url) as session:
            accepting = hold_accepting(server)
            url = hook_url(server.url)
            await announce(url, "toolu_m1", transcript_path)
            await asyncio.sleep(0.02)
            between = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            await asyncio.sleep(0.02)
            await announce(url, "toolu_s1", transcript_path, CC_SUBAGENT)      # later than `between`
            main = server.agents["main"]
            fine, stale = compact_boundary(timestamp=between), compact_boundary(timestamp=between)
            append(transcript_path, fine)                  # after main's last announcement: its compaction
            await announce(url, "toolu_m2", transcript_path)
            assert check_failures() == [] and [d["uuid"] for _, d in compactions()] == [uuid_of(fine)]
            main.seen.add((1, None))
            append(transcript_path, stale)                 # before main's last announcement, toolu_m2
            await announce(url, "toolu_m3", transcript_path)
            result = await session.call_tool("echo", {"text": "a"}, meta={"claudecode/toolUseId": "toolu_m3"})
            assert (text_of(result), result.isError) == (INTERNAL, True)
            accepting.set()
            exn = await ended(serve)
            assert isinstance(exn, TAT_InternalError) and str(exn) == boundary_before_announcement("main")
            assert main.seen == {(1, None)} and len(compactions()) == 1
            [failed] = check_failures()
            assert (failed["level"], failed["agent"], failed["call"]) == ("error", "main", "toolu_m3")
            data = failed["data"]
            assert data == {"check": "boundary_before_previous_announcement", "message": str(exn),
                            "uuid": uuid_of(stale), "timestamp": data["timestamp"],
                            "previous_announcement": data["previous_announcement"]}
            assert datetime.fromisoformat(data["timestamp"]) == datetime.fromisoformat(between)
            assert datetime.fromisoformat(data["previous_announcement"]) > datetime.fromisoformat(between)
    run(scenario)


def test_the_body_is_handed_the_agent_that_called(transcript_path):
    """MODULE_STRUCTURE §4.6: the tool boundary hands each body the `Agent`
    of its call — the object the server keeps for that agent, whose seen
    set the body's rendering is for."""
    handed = []

    async def who(agent, arguments):
        handed.append(agent)
        return "ok"

    async def scenario():
        subagent_file(transcript_path, CC_SUBAGENT)
        tool = Tool("who", "the who tool", SCHEMA, who, read_only=True)
        async with serving(free_port(), [tool]) as (server, serve), plain_client(server.url) as session:
            url = hook_url(server.url)
            for tool_use_id, agent_id in (("toolu_s", CC_SUBAGENT), ("toolu_m", None)):
                r = await post_hook(url, claude_code("who", tool_use_id, agent_id, transcript_path=transcript_path))
                assert r.status_code == 200
                await session.call_tool("who", {}, meta={"claudecode/toolUseId": tool_use_id})
            assert len(handed) == 2
            assert handed[0] is server.agents[CC_SUBAGENT] and handed[1] is server.agents["main"]
    run(scenario)


def post_compact(transcript_path: str) -> dict:
    """Claude Code's `PostCompact` in the measured shape: it names the
    session by `transcript_path`, and no agent (CLIENT_HOOKS.md §2)."""
    return {"session_id": SESSION_ID, "transcript_path": transcript_path, "cwd": "/work/TAT.agents",
            "hook_event_name": "PostCompact", "trigger": "auto", "compact_summary": "The conversation so far..."}


def test_a_post_compact_is_matched_with_a_boundary_of_its_session_or_fails_the_second_check(
        transcript_path, monkeypatch):
    """CONSTRUCT_INTERACTION §8, the second check: a `PostCompact` is
    answered nothing and, for a session TAT reads, matched with one
    boundary of that session's — written within the wait before the hook,
    or appearing within the wait after it, in the main conversation's
    file or a subagent's — else the conversation ends with the check's
    message and `check_failed`, no set cleared.  A boundary matches one
    hook; one older than the wait matches none.  The boundary the check
    reads is its agent's compaction event at that agent's next
    announcement still, and none for an agent nothing was shown to.  A
    `PostCompact` for a session TAT does not read starts no check."""
    assert post_compact_without_boundary(Claude_Code_Server.boundary_wait) == (
        "TAT received a PostCompact hook but found no compaction boundary in its session's transcripts within "
        "10 seconds; its reading of Claude Code's transcripts cannot be trusted.")
    monkeypatch.setattr(Claude_Code_Server, "boundary_wait", 0.4)
    monkeypatch.setattr(Claude_Code_Server, "boundary_poll", 0.05)
    hook = post_compact(transcript_path)

    async def hooked(url: str, times: int = 1) -> None:
        for _ in range(times):
            r = await post_hook(url, hook)
            assert r.status_code == 200 and r.content == b""

    async def failed(serve, unmatched: int) -> None:
        """The conversation ends with the check's failure, `unmatched` hooks
        still waiting."""
        exn = await ended(serve)
        assert isinstance(exn, TAT_InternalError) and str(exn) == post_compact_without_boundary(0.4)
        assert check_failures()[-1]["data"] == {
            "check": "post_compact_without_boundary", "message": str(exn), "session": transcript_path,
            "waited": 0.4, "unmatched": unmatched}

    async def scenario():
        async with serving(free_port(), []) as (server, serve):          # no boundary: fails
            url = hook_url(server.url)
            await announce(url, "toolu_1", transcript_path)
            main = server.agents["main"]
            main.seen.add((1, None))
            await hooked(url)
            await failed(serve, 1)
            assert main.seen == {(1, None)} and compactions() == []
            [record] = check_failures()
            assert "agent" not in record                # the hook names nobody
            assert answers()[-1] == ("compaction", 200)
        async with serving(free_port(), []) as (server, serve):          # a boundary after the hook
            url = hook_url(server.url)
            await announce(url, "toolu_1", transcript_path)
            await hooked(url)
            await asyncio.sleep(0.1)
            append(transcript_path, compact_boundary())
            await asyncio.sleep(0.6)
            assert not serve.done() and len(check_failures()) == 1       # the first block's alone
            await announce(url, "toolu_2", transcript_path)
            assert [d["learned_from"] for _, d in compactions()] == ["compact_boundary"]
        async with serving(free_port(), []) as (server, serve):          # a boundary before the hook, read before it
            url = hook_url(server.url)
            append(transcript_path, compact_boundary())
            await announce(url, "toolu_1", transcript_path)
            await hooked(url)
            await asyncio.sleep(0.6)
            assert not serve.done() and len(check_failures()) == 1
            append(transcript_path, compact_boundary())
            await announce(url, "toolu_2", transcript_path)
            await asyncio.sleep(0.6)                    # read, and older than the wait by the time of its hook
            await hooked(url)
            await failed(serve, 1)
        async with serving(free_port(), []) as (server, serve):          # a boundary older than the wait
            url = hook_url(server.url)
            await announce(url, "toolu_1", transcript_path)
            await hooked(url)
            stale = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="milliseconds")
            append(subagent_file(transcript_path, CC_SUBAGENT), compact_boundary(timestamp=stale))
            await failed(serve, 1)                      # a file's past, found while the hook waits
        async with serving(free_port(), []) as (server, serve):          # the boundary in a subagent's file
            url = hook_url(server.url)
            await announce(url, "toolu_1", transcript_path)
            file = subagent_file(transcript_path, CC_SUBAGENT, "workflows", "wf_01")
            await hooked(url)
            await asyncio.sleep(0.1)
            append(file, compact_boundary())
            await asyncio.sleep(0.6)
            assert not serve.done() and len(check_failures()) == 3
            file.write_text(file.read_text().splitlines(keepends=True)[0])    # cut, as read by the check
            await announce(url, "toolu_s1", transcript_path, CC_SUBAGENT)   # nothing was shown to it: no event
            assert len(compactions()) == 2              # the second block's, and this block's main's below
        async with serving(free_port(), []) as (server, serve):          # hooks close together, in either order
            url = hook_url(server.url)
            await announce(url, "toolu_1", transcript_path)
            await hooked(url, 2)
            await asyncio.sleep(0.1)
            append(transcript_path, compact_boundary() + compact_boundary() + compact_boundary())
            await asyncio.sleep(0.1)                    # two matched; the third waits for its hook
            await hooked(url)
            await asyncio.sleep(0.6)
            assert not serve.done() and len(check_failures()) == 3
            await hooked(url)                           # a fourth: nothing is left to match it
            await failed(serve, 1)
        async with serving(free_port(), []) as (server, serve):          # a session TAT does not read
            url = hook_url(server.url)
            assert (await post_hook(url, hook)).status_code == 200      # none read yet
            await announce(url, "toolu_1", transcript_path)
            other = post_compact("/nowhere/" + Path(transcript_path).name)
            assert (await post_hook(url, other)).status_code == 200
            nameless = {k: v for k, v in hook.items() if k != "transcript_path"}
            assert (await post_hook(url, nameless)).status_code == 200
            await asyncio.sleep(0.6)
            assert not serve.done() and len(check_failures()) == 4
            assert answers()[-2:] == [("compaction", 200)] * 2
    run(scenario)


def test_codex_compaction_hooks_clear_the_named_threads_set_and_are_answered_nothing(tmp_path):
    """CLIENT_HOOKS.md §3: `PreCompact` and `PostCompact` clear the set of the
    thread `agent_id` names, the main conversation's when there is none;
    a `SessionStart` of any source clears the main conversation's, whatever
    the payload names; a thread TAT has not met has nothing to clear and
    is not created; every answer is empty."""
    def hook(name: str, agent_id: str | None = None, **fields) -> dict:
        thread = agent_id or CX_SESSION
        payload = {"session_id": CX_SESSION, "transcript_path": f"/home/agent/.codex/sessions/rollout-{thread}.jsonl",
                   "cwd": "/work/TAT.agents", "hook_event_name": name, **fields}
        return payload | ({"agent_id": agent_id, "agent_type": "default"} if agent_id else {})

    async def scenario():
        bodies = Bodies()
        async with serving(free_port(), bodies.tools(), server_class=Codex_Server) as (server, serve), \
                plain_client(server.url, info(Codex_Server)) as session:
            server.configure(tmp_path)
            url = hook_url(server.url)
            for call_id, thread in (("c1", CX_SESSION), ("c2", CX_SUBAGENT)):
                await post_hook(url, codex("echo", call_id, None if thread == CX_SESSION else thread))
                await session.call_tool("echo", {"text": "a"}, meta=codex_meta(call_id, thread, tmp_path))
            main, sub = server.agents[CX_SESSION], server.agents[CX_SUBAGENT]
            seen = {(1, None), (2, "ending")}
            sources = ("startup", "resume", "clear", "compact", "fork")
            for payload, cleared, kept in (
                    (hook("PreCompact", CX_SUBAGENT, trigger="auto"), sub, main),
                    (hook("PostCompact", CX_SUBAGENT, compact_summary="..."), sub, main),
                    (hook("PreCompact", trigger="manual"), main, sub),
                    (hook("PostCompact", compact_summary="..."), main, sub),
                    *((hook("SessionStart", source=source), main, sub) for source in sources),
                    (hook("SessionStart", CX_SUBAGENT, source="resume"), main, sub)):
                cleared.seen.update(seen)
                kept.seen.update(seen)
                r = await post_hook(url, payload)
                assert r.status_code == 200 and r.content == b"", payload
                assert cleared.seen == set() and kept.seen == seen, payload
            r = await post_hook(url, hook("PreCompact", "019a7c3e-0000-7a12-b4f0-6e1d2c3b4a59", trigger="auto"))
            assert r.status_code == 200 and r.content == b"" and set(server.agents) == {CX_SESSION, CX_SUBAGENT}
            assert not serve.done()
            assert compactions() == [
                (CX_SUBAGENT, {"learned_from": "pre_compact", "seen_cleared": 2}),
                (CX_SUBAGENT, {"learned_from": "post_compact", "seen_cleared": 2}),
                (CX_SESSION, {"learned_from": "pre_compact", "seen_cleared": 2}),
                (CX_SESSION, {"learned_from": "post_compact", "seen_cleared": 2}),
                *((CX_SESSION, {"learned_from": "session_start", "seen_cleared": 2, "source": source})
                  for source in sources),
                (CX_SUBAGENT, {"learned_from": "session_start", "seen_cleared": 2, "source": "resume"}),
                ("019a7c3e-0000-7a12-b4f0-6e1d2c3b4a59", {"learned_from": "pre_compact", "seen_cleared": 0})]
            assert [judged for judged, _ in answers()[2:]] == [
                "compaction"] * 4 + ["session_start"] * 6 + ["compaction"]
    run(scenario)


def test_a_message_reaches_its_recipient_alone(transcript_path):
    """CONSTRUCT_INTERACTION §3.4: a message is delivered with its
    recipient's next tool result and on no other agent's."""
    async def scenario():
        bodies = Bodies()
        subagent_file(transcript_path, CC_SUBAGENT)
        async with serving(free_port(), bodies.tools()) as (server, serve), plain_client(server.url) as session:
            url = hook_url(server.url)

            async def call(tool_use_id: str, agent_id: str | None) -> str:
                await announce(url, tool_use_id, transcript_path, agent_id)
                return text_of(await session.call_tool("echo", {"text": "a"},
                                                       meta={"claudecode/toolUseId": tool_use_id}))
            assert await call("toolu_m1", None) == "echo a" and await call("toolu_s1", CC_SUBAGENT) == "echo a"
            post(server.ending.log, Message(server.agents[CC_SUBAGENT], "for the subagent", interrupts=False))
            assert await call("toolu_m2", None) == "echo a"
            assert await call("toolu_s2", CC_SUBAGENT) == "echo a\n\nfor the subagent"
            assert await call("toolu_s3", CC_SUBAGENT) == "echo a"
            [delivered] = [r for r in stand_ins.records("job") if r["event"] == "message_delivered"]
            assert (delivered["agent"], delivered["call"], delivered["data"]) == (
                CC_SUBAGENT, "toolu_s2", {"recipient": CC_SUBAGENT})
    run(scenario)


# --- leaving (CONSTRUCT_INTERACTION §7) ------------------------------------------

def stop(agent_id: str | None = None, transcript_path: str = "/work/none.jsonl") -> dict:
    """Claude Code's `Stop` of the main conversation, or a subagent's
    `SubagentStop`, in the measured shape."""
    payload = {"session_id": SESSION_ID, "transcript_path": transcript_path, "cwd": "/work/TAT.agents",
               "permission_mode": "default", "hook_event_name": "Stop", "stop_hook_active": False}
    if agent_id is not None:
        payload |= {"hook_event_name": "SubagentStop", "agent_id": agent_id, "agent_type": "general-purpose",
                    "agent_transcript_path": f"/work/subagents/agent-{agent_id}.jsonl"}
    return payload


def task_stop(agent_id: str | None = None, target: str = CC_SUBAGENT) -> dict:
    """The parent's `PreToolUse` on `TaskStop`, the caller `agent_id` or the
    main conversation."""
    return {**claude_code("echo", "toolu_ts", agent_id), "tool_name": "TaskStop", "tool_input": {"task_id": target}}


def lemmas(*names: str):
    """theory_X > lemmas of `names`, each carrying both jobs (test_jobs's
    `Checked`); the forest and the lemmas."""
    f = forest({"theory": Block, "lemma": Checked})
    x = add(f, Block(f, slot(), "X"), "theory")
    return f, [add(x, Checked(x, slot(), name), "lemma") for name in names]


def judgements(event: str) -> list[tuple]:
    """Each `agent.<event>` record's agent and data."""
    return [(r["agent"], r["data"]) for r in stand_ins.records("agent") if r["event"] == event]


def test_the_stop_rule_s_reason_per_row_of_section_7(transcript_path):
    """CONSTRUCT_INTERACTION §7: a stop is allowed, with nothing answered,
    when `check_construct` would answer `No job is running.` and deliver
    no message; else blocked with the opening line, the state lines and
    the instruction of the table's row — the two fenced examples among
    them.  Judged for the agent the hook names alone.  A message that no
    longer stands holds nobody."""
    async def scenario():
        subagent_file(transcript_path, CC_SUBAGENT)
        async with serving(free_port(), []) as (server, serve):
            url = hook_url(server.url)
            await announce(url, "toolu_m", transcript_path)
            await announce(url, "toolu_s", transcript_path, CC_SUBAGENT)
            main, sub = server.agents["main"], server.agents[CC_SUBAGENT]
            f, (p, a, b, c) = lemmas("P", "A", "B", "C")
            server.ending.forest = f
            first, second, _ = fenced_blocks(CI, "7.")

            async def judged(payload: dict):
                r = await post_hook(url, payload)
                assert r.status_code == 200
                return r.json() if r.content else None

            def blocked(*lines: str) -> dict:
                return {"decision": "block", "reason": "\n".join([BLOCKED, *lines])}
            assert await judged(stop()) is None and await judged(stop(CC_SUBAGENT)) is None
            # a question, and jobs running: the first example
            await asked(p.job(), main)
            await a.start_evaluation_job(main)
            await b.start_evaluation_job(main)
            assert await judged(stop()) == blocked(*first[1:]) == {"decision": "block", "reason": "\n".join(first)}
            assert await judged(stop(CC_SUBAGENT)) is None             # nothing of the subagent's stands
            # a question only; two questions
            await report(a.evaluation_job())
            await report(b.evaluation_job())
            assert await judged(stop()) == blocked(
                "The proof construction on `lemma_P` is waiting for your answer.",
                "Call `check_construct` to see the question; answer it before you exit.")
            await asked(c.job(), main)
            assert await judged(stop()) == blocked(
                "The proof construction on `lemma_P` and on `lemma_C` is waiting for your answer.",
                "Call `check_construct` to see the questions; answer them before you exit.")
            # jobs running only — the withdrawn questions still in the mailbox stand no more
            p.job().cancel(None)
            c.job().cancel(None)
            assert [m.question is not None for m in main.mailbox] == [True, True]
            a.job().start(main)
            assert await judged(stop()) == blocked(
                "The proof construction on `lemma_A` is still running.",
                "Call `check_construct` to wait for the running proof construction before you exit.")
            await b.start_evaluation_job(main)
            await c.start_evaluation_job(main)
            assert await judged(stop()) == blocked(
                "The proof construction on `lemma_A` is still running.",
                "The proof check on `lemma_B` and on `lemma_C` is still running.",
                "Call `check_construct` to wait for the running proof construction and proof checks before you exit.")
            # messages only: the second example, for each agent its own
            a.job().cancel(None)
            await report(b.evaluation_job())
            await report(c.evaluation_job())
            assert await judged(stop()) is None
            post(server.ending.log, Message(main, "for you", interrupts=False))
            assert await judged(stop()) == {"decision": "block", "reason": "\n".join(second)}
            assert await judged(stop(CC_SUBAGENT)) is None
            post(server.ending.log, Message(sub, "for the subagent", interrupts=False))
            assert await judged(stop(CC_SUBAGENT)) == {"decision": "block", "reason": "\n".join(second)}
            main.mailbox.clear()
            assert await judged(stop()) is None
            assert judgements("stop_judged")[:4] == [
                ("main", {"allowed": True}), (CC_SUBAGENT, {"allowed": True}),
                ("main", {"allowed": False, "stands": {      # the message: P's question
                    "waiting": ["theory_X.lemma_P"], "running": [], "checks": ["theory_X.lemma_A", "theory_X.lemma_B"],
                    "messages": 1}}),
                (CC_SUBAGENT, {"allowed": True})]
            assert judgements("stop_judged")[-2] == (CC_SUBAGENT, {"allowed": False, "stands": {
                "waiting": [], "running": [], "checks": [], "messages": 1}})
            assert set(answers()[2:]) == {("stop", 200)}
    run(scenario)


def test_an_interruption_is_denied_for_a_held_agent_and_for_a_working_call(transcript_path):
    """CONSTRUCT_INTERACTION §7: the parent's `TaskStop` is denied, with the
    two fenced lines as the reason, when any agent other than the caller
    and the main conversation would be held by the stop rule or has a call
    still working; else allowed with nothing answered.  On Codex the tool
    is `collaborationinterrupt_agent`."""
    async def scenario():
        bodies = Bodies()
        subagent_file(transcript_path, CC_SUBAGENT)
        subagent_file(transcript_path, CC_OTHER_SUBAGENT)
        async with serving(free_port(), bodies.tools()) as (server, serve), plain_client(server.url) as session:
            url = hook_url(server.url)
            for tool_use_id, agent_id in (("toolu_m", None), ("toolu_s", CC_SUBAGENT), ("toolu_o", CC_OTHER_SUBAGENT)):
                await announce(url, tool_use_id, transcript_path, agent_id)
            main, sub, other = server.agents["main"], server.agents[CC_SUBAGENT], server.agents[CC_OTHER_SUBAGENT]
            f, (p,) = lemmas("P")
            server.ending.forest = f
            denied = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": INTERRUPTION_DENIED}}
            assert INTERRUPTION_DENIED.splitlines() == fenced_blocks(CI, "7.")[2]

            async def judged(caller: str | None = None):
                r = await post_hook(url, task_stop(caller))
                assert r.status_code == 200
                return r.json() if r.content else None
            assert await judged() is None                               # nobody held
            p.job().start(sub)                                           # the subagent holds work
            assert await judged() == denied
            assert await judged(CC_SUBAGENT) is None                    # the caller itself counts for nothing
            assert await judged(CC_OTHER_SUBAGENT) == denied
            p.job().cancel(None)
            p.job().start(main)                                          # the main conversation counts for nothing
            assert await judged() is None and await judged(CC_SUBAGENT) is None
            p.job().cancel(None)
            post(server.ending.log, Message(other, "unread", interrupts=False))     # a message holds too
            assert await judged() == denied and await judged(CC_OTHER_SUBAGENT) is None
            other.mailbox.clear()
            # a call still working
            await announce(url, "toolu_slow", transcript_path, CC_SUBAGENT)
            call = asyncio.ensure_future(session.call_tool("slow", {}, meta={"claudecode/toolUseId": "toolu_slow"}))
            await asyncio.wait_for(bodies.began("slow").wait(), 2.0)
            assert await judged() == denied
            bodies.release.set()
            assert text_of(await asyncio.wait_for(call, 2.0)) == "slow done"
            assert await judged() is None
            assert judgements("interruption_judged") == [
                ("main", {"allowed": True}), ("main", {"allowed": False, "holding_work": [CC_SUBAGENT]}),
                (CC_SUBAGENT, {"allowed": True}), (CC_OTHER_SUBAGENT, {"allowed": False, "holding_work": [CC_SUBAGENT]}),
                ("main", {"allowed": True}), (CC_SUBAGENT, {"allowed": True}),
                ("main", {"allowed": False, "holding_work": [CC_OTHER_SUBAGENT]}), (CC_OTHER_SUBAGENT, {"allowed": True}),
                ("main", {"allowed": False, "holding_work": [CC_SUBAGENT]}), ("main", {"allowed": True})]
            assert set(answers()[3:]) == {("interruption", 200), ("announcement", 200)}
        async with serving(free_port(), [], server_class=Codex_Server) as (server, serve):
            payload = {**codex("echo", "c1"), "tool_name": "collaborationinterrupt_agent",
                       "tool_input": {"path": "/work/.codex/agents/worker"}}
            assert server.event_of_hook(payload) == Interruption(frozenset())
            assert server.event_of_hook({**payload, "tool_name": "TaskStop"}) is None
    run(scenario)


def test_an_interruption_by_a_caller_tat_never_met_is_judged_like_any_other(transcript_path):
    """CONSTRUCT_INTERACTION §7: the caller is looked up and never created;
    one TAT has not met is no agent to leave out, so the judgement still
    reads every agent but the main conversation."""
    async def scenario():
        subagent_file(transcript_path, CC_SUBAGENT)
        async with serving(free_port(), []) as (server, serve):
            url = hook_url(server.url)
            await announce(url, "toolu_m", transcript_path)
            await announce(url, "toolu_s", transcript_path, CC_SUBAGENT)
            f, (p,) = lemmas("P")
            server.ending.forest = f
            p.job().start(server.agents[CC_SUBAGENT])
            r = await post_hook(url, task_stop("c0ffee000000"))      # a caller TAT never met
            assert r.status_code == 200 and "c0ffee000000" not in server.agents
            assert r.json() == {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                       "permissionDecisionReason": INTERRUPTION_DENIED}}
            p.job().cancel(None)
    run(scenario)


def test_codex_s_stop_and_interruption_are_judged_end_to_end(tmp_path):
    """CLIENT_HOOKS.md §1 on Codex: a subagent's `Stop` answered the block
    with CONSTRUCT_INTERACTION §7's reason while its job runs, and the main
    conversation's `collaborationinterrupt_agent` denied meanwhile; both
    empty once the job is gone."""
    async def scenario():
        bodies = Bodies()
        async with serving(free_port(), bodies.tools(), server_class=Codex_Server) as (server, serve), \
                plain_client(server.url, info(Codex_Server)) as session:
            server.configure(tmp_path)
            url = hook_url(server.url)
            for call_id, thread in (("c1", CX_SESSION), ("c2", CX_SUBAGENT)):
                await post_hook(url, codex("echo", call_id, None if thread == CX_SESSION else thread))
                await session.call_tool("echo", {"text": "a"}, meta=codex_meta(call_id, thread, tmp_path))
            f, (p,) = lemmas("P")
            server.ending.forest = f
            p.job().start(server.agents[CX_SUBAGENT])
            stop = {**codex("echo", "c3", CX_SUBAGENT), "hook_event_name": "Stop", "stop_hook_active": False}
            interrupt = {**codex("echo", "c4"), "tool_name": "collaborationinterrupt_agent",
                         "tool_input": {"path": "/work/.codex/agents/worker"}}
            r = await post_hook(url, stop)
            assert r.json() == {"decision": "block", "reason": "\n".join([
                BLOCKED, "The proof construction on `lemma_P` is still running.",
                "Call `check_construct` to wait for the running proof construction before you exit."])}
            r = await post_hook(url, interrupt)
            assert r.json()["hookSpecificOutput"]["permissionDecision"] == "deny"
            p.job().cancel(None)
            for payload in (stop, interrupt):
                r = await post_hook(url, payload)
                assert r.status_code == 200 and r.content == b"", payload
    run(scenario)


# --- Claude Code's internal agents (CONSTRUCT_INTERACTION §8; CLIENT_HOOKS.md §2) ---

INTERNAL_ID = "a934e02378021a2c5"            # the measured shape, `a` + 16 hex


def internal(tool_use_id: str, transcript_path: str) -> dict:
    """An internal agent's `PreToolUse`: a subagent's payload without the
    `agent_type` key."""
    return {k: v for k, v in claude_code("echo", tool_use_id, INTERNAL_ID, transcript_path=transcript_path).items()
            if k != "agent_type"}


def test_an_internal_agents_announcement_is_granted_and_nothing_else_is_done(transcript_path):
    """CONSTRUCT_INTERACTION §8; CLIENT_HOOKS.md §2: an announcement with an
    `agent_id` and no `agent_type` is an internal agent's — granted,
    judged `internal_announcement`, no agent created, no transcript read,
    the conversation going on; a second one under the same id is no bug of
    the path; the internal agent's `SubagentStop` is allowed and creates
    no agent either; an interruption does not see it."""
    async def scenario():
        bodies = Bodies()
        async with serving(free_port(), bodies.tools()) as (server, serve), plain_client(server.url) as session:
            url = hook_url(server.url)
            for _ in range(2):
                r = await post_hook(url, internal("toolu_i", transcript_path))
                assert r.status_code == 200 and r.json() == Claude_Code_Server.announcement_answer
            assert server.agents == {} and not serve.done()
            assert answers()[-2:] == [("internal_announcement", 200)] * 2
            assert stand_ins.records("agent") == []
            assert [r for r in stand_ins.records("conversation") if r["event"] == "client_refused"] == []
            await announce(url, "toolu_m", transcript_path)
            served = await session.call_tool("echo", {"text": "hi"}, meta={"claudecode/toolUseId": "toolu_m"})
            assert text_of(served) == "echo hi" and list(server.agents) == ["main"]
            r = await post_hook(url, {**stop(INTERNAL_ID), "agent_type": ""})
            assert r.status_code == 200 and r.content == b""
            assert judgements("stop_judged") == [(INTERNAL_ID, {"allowed": True})] and list(server.agents) == ["main"]
            subagent_file(transcript_path, CC_SUBAGENT)
            await announce(url, "toolu_s", transcript_path, CC_SUBAGENT)
            assert server.event_of_hook(task_stop()) == Interruption(frozenset({server.agents[CC_SUBAGENT]}))
    run(scenario)


def test_a_call_under_an_internal_announcements_id_is_unannounced(transcript_path):
    """CONSTRUCT_INTERACTION §8: an internal agent's announcement records
    the call for nobody, so a call under its id — which Claude Code never
    sends — would be unannounced and end the conversation."""
    async def scenario():
        bodies = Bodies()
        async with serving(free_port(), bodies.tools()) as (server, serve), plain_client(server.url) as session:
            await post_hook(hook_url(server.url), internal("toolu_i", transcript_path))
            result = await session.call_tool("echo", {"text": "hi"}, meta={"claudecode/toolUseId": "toolu_i"})
            assert (text_of(result), result.isError) == (INTERNAL, True)
            exn = await ended(serve)
            assert isinstance(exn, TAT_InternalError) and str(exn) == UNANNOUNCED
            assert tool_records()[-3:] == [("call", None, "toolu_i"), ("unannounced", None, "toolu_i"),
                                           ("while_ending", None, "toolu_i")]
            assert server.agents == {}
    run(scenario)


def test_a_codex_announcement_without_agent_type_is_an_announcement(tmp_path):
    """The internal agents are Claude Code's: on Codex a `PreToolUse` with
    an `agent_id` and no `agent_type` is an announcement like any, the
    thread's agent created at its call."""
    async def scenario():
        bodies = Bodies()
        async with serving(free_port(), bodies.tools(), server_class=Codex_Server) as (server, serve), \
                plain_client(server.url, info(Codex_Server)) as session:
            server.configure(tmp_path)
            payload = {k: v for k, v in codex("echo", "c1", CX_SUBAGENT).items() if k != "agent_type"}
            r = await post_hook(hook_url(server.url), payload)
            assert r.status_code == 200 and answers()[-1] == ("announcement", 200)
            served = await session.call_tool("echo", {"text": "a"}, meta=codex_meta("c1", CX_SUBAGENT, tmp_path))
            assert text_of(served) == "echo a" and list(server.agents) == [CX_SUBAGENT] and not serve.done()
    run(scenario)


# --- the branches the live run did not reach (step 17's review) -----------

def test_a_stop_and_an_interruption_are_answered_503_while_ending_and_judged_nothing():
    """CONSTRUCT_INTERACTION §8: once the ending is entered every hook is
    answered 503 before it is judged — a `Stop`, a `SubagentStop`, a
    `TaskStop` and an internal agent's announcement alike — so no
    `stop_judged` or `interruption_judged` record is written for them."""
    async def scenario():
        async with serving(free_port(), []) as (server, serve):
            url = hook_url(server.url)
            accepting = hold_accepting(server)
            server.ending.end(RuntimeError("ended"))
            for payload in (stop(), stop(CC_SUBAGENT), task_stop(), internal("toolu_i", "/work/none.jsonl")):
                r = await post_hook(url, payload)
                assert r.status_code == 503 and r.content == b"", payload
            accepting.set()
            assert isinstance(await ended(serve), RuntimeError)
        assert answers()[-4:] == [(None, 503)] * 4
        assert judgements("stop_judged") == [] and judgements("interruption_judged") == []
        assert server.agents == {}
    run(scenario)


@pytest.mark.parametrize("case", ["no announcement", "no thread id"])
def test_an_unannounced_call_ends_the_conversation_on_codex(tmp_path, case):
    """CONSTRUCT_INTERACTION §8 on Codex: a call no announcement named,
    and an announced call whose `_meta` carries no `threadId`, name no
    agent — the conversation ends with the `TAT_InternalError`, the call
    is answered the first line of RENDER_BASELINES §4, and no agent is
    created at the call."""
    async def scenario():
        bodies = Bodies()
        async with serving(free_port(), bodies.tools(), server_class=Codex_Server) as (server, serve), \
                plain_client(server.url, info(Codex_Server)) as session:
            server.configure(tmp_path)
            url = hook_url(server.url)
            meta = codex_meta("c9", CX_SESSION, tmp_path)
            if case == "no thread id":
                await post_hook(url, codex("echo", "c9"))
                del meta["threadId"]
            result = await session.call_tool("echo", {"text": "hi"}, meta=meta)
            assert (text_of(result), result.isError) == (INTERNAL, True)
            exn = await ended(serve)
            assert isinstance(exn, TAT_InternalError) and str(exn) == UNANNOUNCED
            assert tool_records()[-3:] == [("call", None, "c9"), ("unannounced", None, "c9"),
                                           ("while_ending", None, "c9")]
            assert server.agents == {}
    run(scenario)


def test_a_subagent_stop_blocked_then_allowed_on_claude_code(transcript_path):
    """CONSTRUCT_INTERACTION §7 on Claude Code: a subagent's `SubagentStop`
    blocked while its construction runs, and the next one — the client's
    retry, `stop_hook_active` — allowed once the job is gone; the two
    verdicts recorded for the subagent alone."""
    async def scenario():
        subagent_file(transcript_path, CC_SUBAGENT)
        async with serving(free_port(), []) as (server, serve):
            url = hook_url(server.url)
            await announce(url, "toolu_s", transcript_path, CC_SUBAGENT)
            f, (p,) = lemmas("P")
            server.ending.forest = f
            p.job().start(server.agents[CC_SUBAGENT])
            r = await post_hook(url, stop(CC_SUBAGENT))
            assert r.json() == {"decision": "block", "reason": "\n".join([
                BLOCKED, "The proof construction on `lemma_P` is still running.",
                "Call `check_construct` to wait for the running proof construction before you exit."])}
            p.job().cancel(None)
            r = await post_hook(url, {**stop(CC_SUBAGENT), "stop_hook_active": True})
            assert r.status_code == 200 and r.content == b""
            assert [(agent, data["allowed"]) for agent, data in judgements("stop_judged")] == [
                (CC_SUBAGENT, False), (CC_SUBAGENT, True)]
    run(scenario)
