"""`POST /hook` and the agents (CONSTRUCT_INTERACTION §4, §8; MODULE_STRUCTURE
§4.6): the announcement that names a call's agent, the unannounced call,
the two clients' agents, the working-call count, the path while the
conversation is ending and on a bug, and the `clientInfo` check.  The
payloads are written here in the shapes AGENT_CLIENTS_MEASURED.md records,
with invented ids.  Run: python -m pytest test/test_hooks.py
"""

import asyncio
from contextlib import asynccontextmanager

import pytest
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError

import stand_ins
from harness import CLIENT_INFO, announce, client, free_port, hook_url, text_of
from isabelle_theory_agent.exceptions import TAT_InternalError
from isabelle_theory_agent.mcp_server import (
    TOOL_PREFIX, UNANNOUNCED, Claude_Code_Server, ClientRefused, Codex_Server)
from test_mcp_server import INTERNAL, NOT_CONNECTED, Bodies, ended, hold_accepting, no_briefing, run

CC_SESSION = "6c1f0e4a-2b7d-4f3e-9a58-0d2c7b1e8f90"
CC_SUBAGENT = "a9f3c2d1e4b5"
CX_SESSION = "019a7c3e-5b2d-7f41-8e6a-3c9d1b0f2a47"
CX_SUBAGENT = "019a7c3e-9d8c-7a12-b4f0-6e1d2c3b4a59"


def claude_code(tool: str, tool_use_id: str, agent_id: str | None = None) -> dict:
    """Claude Code's `PreToolUse` on a TAT tool: the subagent's carries
    `agent_id`, the main conversation's does not (CLIENT_HOOKS.md §2)."""
    payload = {"session_id": CC_SESSION,
               "transcript_path": f"/home/agent/.claude/projects/-work-TAT-agents/{CC_SESSION}.jsonl",
               "cwd": "/work/TAT.agents", "permission_mode": "default", "hook_event_name": "PreToolUse",
               "tool_name": TOOL_PREFIX + tool, "tool_input": {}, "tool_use_id": tool_use_id,
               "mcp_server": {"name": "TAT", "source": "dynamic"}}
    if agent_id is not None:
        payload |= {"agent_id": agent_id, "agent_type": "general-purpose"}
    return payload


def codex(tool: str, call_id: str, agent_id: str | None = None) -> dict:
    """Codex's: `tool_use_id` is the call's `_meta.callId`; a subagent's
    carries its thread id as `agent_id` (CLIENT_HOOKS.md §3)."""
    payload = {"session_id": CX_SESSION,
               "transcript_path": f"/home/agent/.codex/sessions/rollout-{CX_SESSION}.jsonl",
               "cwd": "/work/TAT.agents", "hook_event_name": "PreToolUse",
               "tool_name": TOOL_PREFIX + tool, "tool_input": {}, "tool_use_id": call_id}
    if agent_id is not None:
        payload |= {"agent_id": agent_id, "agent_type": "default"}
    return payload


@asynccontextmanager
async def serving(server_class, tools):
    """A server of the class, listening and serving in a task, on an
    ending object of its own; yields the server and the serving task."""
    async with stand_ins.ending() as ending, \
            server_class(ending, free_port(), tools, no_briefing) as server:
        serve = asyncio.create_task(server.serve())
        try:
            yield server, serve
        finally:
            if not serve.done():
                serve.cancel()
            await asyncio.wait({serve})
            if not serve.cancelled():
                serve.exception()


@asynccontextmanager
async def plain_client(url: str, client_info: types.Implementation = CLIENT_INFO):
    """A client session that announces nothing by itself: the test does."""
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write, client_info=client_info) as session:
            await session.initialize()
            yield session


def tool_records():
    return [(r["event"], r.get("agent"), r.get("call")) for r in stand_ins.records("tool")]


def test_an_announced_call_is_served_and_its_records_name_the_call_and_the_agent():
    """CONSTRUCT_INTERACTION §8; LOGGING.md §3: the announcement is answered
    the grant and creates the agent; the call it named is served, and its
    `call` and `result` records carry the same `call` and `agent`; the
    client's `clientInfo` is recorded once."""
    async def scenario():
        bodies = Bodies()
        async with serving(Claude_Code_Server, bodies.tools()) as (server, serve), \
                plain_client(server.url) as session:
            payload = claude_code("echo", "toolu_01")
            r = await announce(hook_url(server.url), payload)
            assert r.status_code == 200 and r.json() == Claude_Code_Server.announcement_answer
            result = await session.call_tool("echo", {"text": "hi"},
                                             meta={"claudecode/toolUseId": "toolu_01", "progressToken": 1})
            assert (text_of(result), result.isError) == ("echo hi", False) and not serve.done()
            assert list(server.agents) == ["main"] and server.agents["main"].main
            assert tool_records() == [("call", "main", "toolu_01"), ("result", "main", "toolu_01")]
            request, answer = stand_ins.records("hook")
            assert (request["event"], request["data"]) == ("request", {"payload": payload})
            assert (answer["event"], answer["agent"]) == ("answer", "main")
            assert {k: answer["data"][k] for k in ("judged", "status", "body")} == {
                "judged": "announcement", "status": 200, "body": Claude_Code_Server.announcement_answer}
            [created] = stand_ins.records("agent")
            assert (created["event"], created["agent"], created["data"]) == (
                "created", "main", {"identity": "main", "main": True, "first": "hook"})
            assert [(r["event"], r["data"]) for r in stand_ins.records("conversation")] == [
                ("client_connected", {"name": "claude-code", "version": "2.1.286"})]
    run(scenario)


@pytest.mark.parametrize("meta", [None, {"claudecode/toolUseId": "toolu_unknown"}])
def test_an_unannounced_call_ends_the_conversation(meta):
    """CONSTRUCT_INTERACTION §8: TAT never guesses — a call carrying no id,
    or one no announcement named, ends the conversation with a
    `TAT_InternalError`; the call is answered the first line of
    RENDER_BASELINES §4 and the `unannounced` record written."""
    async def scenario():
        bodies = Bodies()
        async with serving(Claude_Code_Server, bodies.tools()) as (server, serve), \
                plain_client(server.url) as session:
            result = await session.call_tool("echo", {"text": "hi"}, meta=meta)
            assert (text_of(result), result.isError) == (INTERNAL, True)
            exn = await ended(serve)
            assert isinstance(exn, TAT_InternalError) and str(exn) == UNANNOUNCED
            call = None if meta is None else "toolu_unknown"
            assert tool_records() == [("unannounced", None, call), ("call", None, call),
                                      ("while_ending", None, call)]
            unannounced = stand_ins.records("tool")[0]
            assert unannounced["level"] == "error"
            assert unannounced["data"] == {"tool": "echo", "message": UNANNOUNCED} | (
                {} if meta is None else {"_meta": meta})
            assert server.agents == {}
    run(scenario)


@pytest.mark.parametrize("server_class, payload, meta, main_identity, subagent", [
    (Claude_Code_Server, claude_code, lambda call_id: {"claudecode/toolUseId": call_id},
     "main", CC_SUBAGENT),
    (Codex_Server, codex, lambda call_id: {"callId": call_id, "threadId": CX_SESSION,
                                           "sessionId": CX_SESSION, "progressToken": 3},
     CX_SESSION, CX_SUBAGENT)])
def test_the_main_conversation_and_a_subagent_are_two_agents_on_each_client(
        server_class, payload, meta, main_identity, subagent):
    """CONSTRUCT_INTERACTION §4, §8; CLIENT_HOOKS.md §2, §3: an agent is
    told apart by the client's identity for it — Claude Code's `agent_id`
    and `main`, Codex's thread ids, the main conversation's being the
    payload's `session_id` — and each call reaches the agent that announced
    it, in whatever order the calls come; Codex's announcements are
    answered nothing."""
    async def scenario():
        bodies = Bodies()
        info = types.Implementation(name=server_class.client_name, version=server_class.measured_version)
        async with serving(server_class, bodies.tools()) as (server, serve), \
                plain_client(server.url, info) as session:
            url = hook_url(server.url)
            for r in (await announce(url, payload("echo", "id-main")),
                      await announce(url, payload("echo", "id-sub", agent_id=subagent))):
                assert r.status_code == 200
                if server_class.announcement_answer is None:
                    assert r.content == b"" and r.headers["content-type"].startswith("text/plain")
                else:
                    assert r.json() == server_class.announcement_answer
            assert {identity: agent.main for identity, agent in server.agents.items()} == {
                main_identity: True, subagent: False}
            for call_id, identity in (("id-sub", subagent), ("id-main", main_identity)):
                result = await session.call_tool("echo", {"text": identity}, meta=meta(call_id))
                assert (text_of(result), result.isError) == ("echo " + identity, False)
            assert not serve.done()
            assert tool_records() == [
                ("call", subagent, "id-sub"), ("result", subagent, "id-sub"),
                ("call", main_identity, "id-main"), ("result", main_identity, "id-main")]
            assert [(r["data"]["identity"], r["data"]["main"]) for r in stand_ins.records("agent")] == [
                (main_identity, True), (subagent, False)]
    run(scenario)


def test_the_working_call_count_follows_the_body_not_the_client():
    """CONSTRUCT_INTERACTION §4: the count rises as soon as the agent is
    named and falls when the body ends — after the client gave up on the
    call, the body still running, it still counts."""
    async def scenario():
        bodies = Bodies()
        async with serving(Claude_Code_Server, bodies.tools()) as (server, serve), \
                client(server.url) as session:
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
    run(scenario)


def test_the_path_answers_503_while_ending_and_500_on_a_bug_and_ignores_other_hooks():
    """MODULE_STRUCTURE §4.6: an empty 503 while the conversation is ending;
    a payload that breaks the client's documented shape is a bug on the
    path — the conversation ends and the hook gets an empty 500, exit 1
    for the script, no block; a hook TAT has no rule for yet is answered
    nothing; a body that is no JSON object is refused with 400; the
    transport check is `/mcp`'s."""
    async def scenario():
        async with serving(Claude_Code_Server, []) as (server, serve):
            url = hook_url(server.url)
            stop = {"session_id": CC_SESSION, "hook_event_name": "Stop", "stop_hook_active": False}
            r = await announce(url, stop)
            assert r.status_code == 200 and r.content == b""
            assert (await announce(url, [1, 2])).status_code == 400
            import httpx
            async with httpx.AsyncClient() as http:
                assert (await http.get(url)).status_code == 405
                assert (await http.post(url, json=stop, headers={"Host": "localhost"})).status_code == 421
                assert (await http.post(url, content=b"{}")).status_code == 400   # no content type
            broken = claude_code("echo", "toolu_02")
            del broken["tool_use_id"]
            r = await announce(url, broken)
            assert r.status_code == 500 and r.content == b""
            exn = await ended(serve)
            assert isinstance(exn, TAT_InternalError) and "tool_use_id" in str(exn)
        answers = [(r["data"]["judged"], r["data"]["status"]) for r in stand_ins.records("hook")
                   if r["event"] == "answer"]
        assert answers == [("ignored", 200), ("ignored", 400), ("ignored", 500)]

        async with serving(Claude_Code_Server, []) as (server, serve):
            accepting = hold_accepting(server)
            server.ending.end(RuntimeError("ended"))
            r = await announce(hook_url(server.url), claude_code("echo", "toolu_03"))
            assert r.status_code == 503 and r.content == b"" and server.agents == {}
            accepting.set()
            assert isinstance(await ended(serve), RuntimeError)
        assert [(r["data"]["judged"], r["data"]["status"]) for r in stand_ins.records("hook")
                if r["event"] == "answer"][-1] == ("ignored", 503)
    run(scenario)


@pytest.mark.parametrize("name, version, served", [
    ("claude-code", "2.1.286", True), ("claude-code", "2.1.300", True), ("claude-code", "3.0.0-beta", True),
    ("claude-code", "2.1.285", False), ("claude-code", "2.1", False), ("claude-code", "dev", False),
    ("codex-mcp-client", "2.1.286", False)])
def test_the_client_info_check(name, version, served):
    """CONSTRUCT_INTERACTION §8; MODULE_STRUCTURE §4.6: at a session's first
    request the `clientInfo` is checked — the name against `-c`'s client,
    the leading dotted numbers of the version against the measured one.
    Equal or higher is served, with `client_connected` once per session;
    lower, unreadable or another client's name is refused: no tool is
    served, every call is answered the sixth line, the conversation ends
    with the `ClientRefused` the launcher prints, `client_refused`
    recorded."""
    async def scenario():
        bodies = Bodies()
        info = types.Implementation(name=name, version=version)
        async with serving(Claude_Code_Server, bodies.tools()) as (server, serve), \
                plain_client(server.url, info) as session:
            accepting = hold_accepting(server)
            if served:
                listed = await session.list_tools()
                assert [t.name for t in listed.tools] == [t.name for t in bodies.tools()]
                await announce(hook_url(server.url), claude_code("echo", "toolu_04"))
                result = await session.call_tool("echo", {"text": "a"}, meta={"claudecode/toolUseId": "toolu_04"})
                assert (text_of(result), result.isError) == ("echo a", False) and not serve.done()
                assert [(r["event"], r["data"]) for r in stand_ins.records("conversation")] == [
                    ("client_connected", {"name": name, "version": version})]
            else:
                result = await session.call_tool("echo", {"text": "a"})      # the first request
                assert (text_of(result), result.isError) == (NOT_CONNECTED, True)
                assert (await session.list_tools()).tools == []
                exn = await ended(serve)
                sentence = (f"TAT cannot serve this client: it is {name} {version}; "
                            "TAT requires claude-code 2.1.286 or newer.")
                assert isinstance(exn, ClientRefused) and str(exn) == sentence
                assert exn.line == NOT_CONNECTED
                [refused] = [r for r in stand_ins.records("conversation") if r["event"] == "client_refused"]
                assert refused["level"] == "error"
                assert refused["data"] == {"name": name, "version": version, "message": sentence}
                assert tool_records() == [("call", None, None), ("while_ending", None, None)]
            accepting.set()
    run(scenario)
