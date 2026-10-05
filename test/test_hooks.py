"""`POST /hook` and the agents (CONSTRUCT_INTERACTION §4, §8; MODULE_STRUCTURE
§4.6): the announcement that names a call's agent, the unannounced call,
the two clients' agents, the working-call count, the path while the
conversation is ending and on a bug, the `clientInfo` check and Codex's
sandbox check.  The payloads are written in the shapes
AGENT_CLIENTS_MEASURED.md records, with invented ids (the Claude Code
builder is the harness's).  Run: python -m pytest test/test_hooks.py
"""

import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError

import stand_ins
from harness import CLIENT_INFO, claude_code, client, free_port, hook_url, post_hook, text_of
from isabelle_theory_agent.exceptions import TAT_InternalError
from isabelle_theory_agent.mcp_server import (
    AGENTS, SANDBOX_STATE, TOOL_PREFIX, Claude_Code_Server, ClientRefused, Codex_Server,
    sandbox_is_the_profile)
from test_mcp_server import (
    INTERNAL, NOT_CONNECTED, NOT_SANDBOXED, Bodies, ended, hold_accepting, run, serving)

CC_SUBAGENT = "a9f3c2d1e4b5"
CX_SESSION = "019a7c3e-5b2d-7f41-8e6a-3c9d1b0f2a47"
CX_SUBAGENT = "019a7c3e-9d8c-7a12-b4f0-6e1d2c3b4a59"

# The two messages of CONSTRUCT_INTERACTION §8 and CONSTRUCT_DECISIONS §10
# for the client's hooks failing TAT; the launcher prints them.
UNANNOUNCED = ("This call was not announced by the client's hooks, so TAT cannot tell which agent "
               "is calling.")
SECOND_ANNOUNCEMENT = ("TAT received a second announcement of the call {id} before that call arrived; "
                       "the client's hooks cannot be trusted.")


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


def test_an_announced_call_is_served_and_its_records_name_the_call_and_the_agent():
    """CONSTRUCT_INTERACTION §8; LOGGING.md §3: the announcement is answered
    the grant and creates the agent; the call it named is served; the
    records of the hook request, of the agent's creation and of the call
    carry the call's id and the agent; the client's `clientInfo` is
    recorded once, belonging to no call."""
    async def scenario():
        bodies = Bodies()
        async with serving(free_port(), bodies.tools()) as (server, serve), \
                plain_client(server.url) as session:
            payload = claude_code("echo", "toolu_01")
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
            [created] = stand_ins.records("agent")
            assert (created["event"], created["agent"], created["call"], created["data"]) == (
                "created", "main", "toolu_01", {"identity": "main", "main": True, "first": "hook"})
            [connected] = stand_ins.records("conversation")
            assert (connected["event"], connected["data"]) == (
                "client_connected", {"name": "claude-code", "version": "2.1.286"})
            assert "call" not in connected and "agent" not in connected
    run(scenario)


@pytest.mark.parametrize("meta", [None, {"claudecode/toolUseId": "toolu_unknown"},
                                  {"claudecode/toolUseId": "toolu_00"}],
                         ids=["no id", "an id no announcement named", "an id already spent"])
def test_an_unannounced_call_ends_the_conversation(meta):
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
            await post_hook(url, claude_code("echo", "toolu_00"))
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


def test_a_second_announcement_of_a_pending_call_is_a_bug_of_the_path():
    """CONSTRUCT_DECISIONS §10: the ids are unique by the clients' measured
    behaviour, so a `tool_use_id` announced again before its call arrived
    breaks TAT's premise about the hooks — the conversation ends with the
    approved message, the hook is answered an empty 500, and the answer's
    record carries no `judged`."""
    async def scenario():
        async with serving(free_port(), []) as (server, serve):
            url = hook_url(server.url)
            assert (await post_hook(url, claude_code("echo", "toolu_05"))).status_code == 200
            r = await post_hook(url, claude_code("echo", "toolu_05"))
            assert r.status_code == 500 and r.content == b""
            exn = await ended(serve)
            assert isinstance(exn, TAT_InternalError)
            assert str(exn) == SECOND_ANNOUNCEMENT.format(id="toolu_05")
            assert answers() == [("announcement", 200), (None, 500)]
    run(scenario)


@pytest.mark.parametrize("server_class, payload, meta, main_identity, subagent, created", [
    (Claude_Code_Server, claude_code, lambda call_id, thread, wd: {"claudecode/toolUseId": call_id},
     "main", CC_SUBAGENT, [("main", True, "hook"), (CC_SUBAGENT, False, "hook")]),
    (Codex_Server, codex, codex_meta,
     CX_SESSION, CX_SUBAGENT, [(CX_SUBAGENT, False, "call"), (CX_SESSION, True, "call")])],
    ids=["claude-code", "codex"])
def test_the_main_conversation_and_a_subagent_are_two_agents_on_each_client(
        tmp_path, server_class, payload, meta, main_identity, subagent, created):
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
        async with serving(free_port(), bodies.tools(), server_class=server_class) as (server, serve), \
                plain_client(server.url, info(server_class)) as session:
            server.configure(tmp_path)
            url = hook_url(server.url)
            for r in (await post_hook(url, payload("echo", "id-main")),
                      await post_hook(url, payload("echo", "id-sub", agent_id=subagent))):
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
                    for r in stand_ins.records("agent")] == created
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
        assert answers() == [("ignored", 200), ("ignored", 200), (None, 500)]

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
    (Claude_Code_Server, "claude-code", "2.1.286", True), (Claude_Code_Server, "claude-code", "2.1.300", True),
    (Claude_Code_Server, "claude-code", "3.0.0-beta", True),
    (Claude_Code_Server, "claude-code", "2.1.285", False), (Claude_Code_Server, "claude-code", "2.1", False),
    (Claude_Code_Server, "claude-code", "dev", False), (Claude_Code_Server, "codex-mcp-client", "2.1.286", False),
    (Codex_Server, "codex-mcp-client", "0.156.1", True), (Codex_Server, "codex-mcp-client", "0.156.0", False),
    (Codex_Server, "claude-code", "2.1.286", False)])
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


def test_the_check_is_per_session_and_a_refused_session_alone_is_served_no_tool():
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
                await post_hook(hook_url(server.url), claude_code("echo", "toolu_06"))
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
