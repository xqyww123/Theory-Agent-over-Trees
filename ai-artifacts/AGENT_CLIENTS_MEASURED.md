# What the agent clients do: measured and read (2026-09-23)

Facts gathered for the design of `construct`'s interaction with the agent
(the messages a running proof search sends back, and how they reach the
agent). Each item says how it was established: *measured* (a probe on this
host), *source* (read in the client's source at the installed version), or
*docs* (the client's documentation, fetched 2026-09-23). Nothing here is
a decision.

## Claude Code (2.1.280)

- *measured* — A subagent that references an MCP server by name shares the
  parent conversation's connection: the server sees the main conversation's
  `Mcp-Session-Id` on the subagent's `tools/call`. Measured twice: a stdio
  server spawned no second process for a subagent's call; a streamable-HTTP
  probe server logged the same session id for the main conversation and a
  `"mcpServers": ["tat"]` subagent.
- *measured* — A subagent whose definition carries an inline `mcpServers`
  entry under a **different** server name (`tat2`, same URL) opens its own
  connection when the subagent starts (`initialize`, `notifications/
  initialized`, the standalone `GET`, `tools/list`), 1.7 s before its
  first tool call, and its `tools/call` carries that connection's own
  `Mcp-Session-Id`. Its tools are named `mcp__tat2__<tool>`.
- *measured* — An inline entry under the **same** name as the main
  conversation's server opens and initializes a connection, then never
  uses it: the subagent's `tools/call` still travels on the main
  conversation's session. Same name = wasted connection, no error.
- *measured* — Claude Code never sent a `DELETE` for any session: not when a
  subagent finished, not when the `claude -p` process exited. A session's
  end is not announced.
- *measured* — Before every connection Claude Code POSTs a
  `server/discover` request; the `mcp` SDK (1.26.0) answers 400 and still
  issues a fresh `Mcp-Session-Id`, so every connection leaves one orphan
  session in the SDK's table besides the one it uses.
- *measured* 2026-10-13 (2.1.296, interactive) — Claude Code's MCP log
  names no `server/discover`; it connected over HTTP (protocol
  2025-11-25) and the first request of the session to reach TAT after
  `initialize` was `tools/list`. Whether it still sends the request is
  not seen: the SDK would handle it before it reaches TAT, and Claude
  Code's log does not list it.
- *measured* — `--agents` accepts `mcpServers` as a list whose items are a
  server name or a one-key object `{name: definition}`; such inline
  servers are exempt from the folder-trust check (*docs*).
- *measured* — Every MCP `tools/call` Claude Code sends carries
  `"_meta": {"claudecode/toolUseId": "toolu_…", "progressToken": N}`, and
  the `toolu_…` string is byte-identical to the `tool_use_id` the
  `PreToolUse` and `PostToolUse` hooks receive for that call (3 of 3
  calls, one of them from a subagent). The hooks fire for a subagent's
  MCP calls too, with `agent_id` and `agent_type` present and the
  parent's `session_id`; the main conversation's calls carry neither key.
  The hook's stdin also names the server: `"mcp_server": {"name": "tat",
  "source": "dynamic"}`. A `PreToolUse` hook runs to completion before the
  request is sent (a `sleep 1` in the hook delayed the request by 1.03 s
  in every case); `PostToolUse` fires about 10 ms after the request, with
  `tool_response` and `duration_ms`. The hook's environment is the
  process's (`TAT_AGENT` identical for the subagent's call). The `mcp` SDK
  keeps the unknown `_meta` key (`RequestParams.Meta` is
  `extra="allow"`) and exposes it as `request_context.meta`.
- *docs* — Hook stdin carries `session_id` (the process's session) and,
  inside a subagent, `agent_id` and `agent_type`. No environment variable
  carries the session id. `PreToolUse`'s `updatedInput` merges fields
  into the tool call's arguments but "cannot add fields the tool doesn't
  accept"; whether it applies to MCP tools is not stated.
- *docs* — `Stop` fires when Claude finishes responding; the hook runs
  synchronously; `{"decision": "block", "reason": …}` or exit 2 with
  stderr prevents the stop and the reason reaches the model, which "may
  choose to continue". `stop_hook_active` marks a stop already continued
  once. Command hooks time out after 600 s by default (no documented
  maximum); a timed-out hook's output is discarded. `async: true` hooks
  run without timeout; `asyncRewake: true` wakes Claude on exit 2 with
  the hook's stderr as a system reminder. `UserPromptSubmit` adds
  `additionalContext`.
- *docs + measured* — `SubagentStop` **can block** (the earlier note that it
  cannot came from a summarising fetch and was wrong; the raw page's
  exit-code table says "Prevents the subagent from stopping"): `{"decision":
  "block", "reason": …}` or exit 2 keeps the subagent running and delivers
  the reason into its transcript as `Stop hook feedback: …` (and again as a
  hook-error system reminder). Measured. `SubagentStart` cannot block.
  A `Stop` hook in an agent definition is converted to `SubagentStop`;
  `Stop` itself fires once, for the main conversation, without `agent_id`.
  `hooks` is accepted in `--agents` JSON; a project-level agent file's
  frontmatter hooks are skipped until the folder is trusted, and "a `-p`
  session doesn't count as trusted".
- *docs + measured* — Two hard ceilings on holding a subagent: (1) after
  **8 consecutive blocks** Claude Code overrides the hook and the subagent
  stops (documented for `Stop`, measured for `SubagentStop`: 9 events, the
  9th block ignored); (2) `CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS`, default
  600000 ms, aborts a subagent that shows no streaming progress — measured
  at 15 s: a `SubagentStop` hook sleeping 40 s was killed at 16 s, the
  subagent marked `failed`, its work lost, and the parent's `Agent` result
  was `[Request interrupted by user for tool use]` (`is_error: true`), on
  which the parent stopped and asked the user. A sleeping hook otherwise
  holds the subagent for exactly its sleep (40 s measured) with no model
  turn. `maxTurns` counts turns, not time. Async hooks cannot block.
- *measured* — The block's reason is an instruction, not a constraint:
  with a reason about a job the subagent had not been told of, it judged
  the text a prompt injection and refused (still consuming a block); with
  a system prompt saying it registers long jobs and a plausible reason, it
  complied, waited in a Bash `until … sleep 10` loop for 56 s and finished
  after one block.
- *measured* — `PostToolUse` with matcher `Agent` fires in the parent when
  a subagent returns; its `tool_response` carries `agentId`, `agentType`,
  `status`, `content`; `reason` and `additionalContext` both reach the
  parent verbatim. It cannot reopen the subagent.
- *measured* 2026-09-28 (2.1.283, all 33 hook events logged) — **a
  subagent that ends abnormally gets no hook of its own**, and a
  `SubagentStop` hook still running at that moment is sent SIGTERM
  (`TaskStop`: ~30 ms after the call; the stall watchdog: at its timeout;
  Escape: 74 ms after the key). What the *parent* sees: `TaskStop` on a
  background subagent → the parent's `PreToolUse`/`PostToolUse(TaskStop)`
  (`task_id`, `task_type: "local_agent"`) and a `UserPromptSubmit` carrying
  the task-notification with `<status>killed</status>`; the stall watchdog,
  foreground → `PostToolUseFailure(Agent)` (`tool_use_id`, `error:
  "[Request interrupted by user for tool use]"`, `is_interrupt: true`, no
  agent id, no status), background → `UserPromptSubmit` with
  `<status>failed</status>`; `maxTurns` → the parent's `PostToolUse(Agent)`
  with `status: "completed"` and a harness NOTE in `content` (background:
  the notification says `completed`, "stopped at its 2-turn limit"), no
  `SubagentStop`; a block at the limit is recorded and ignored; Escape on a
  foreground subagent (interactive; needs
  `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, otherwise the Agent call is
  backgrounded and Escape does nothing to it) → nothing at all, for the
  subagent or the parent, until `SessionEnd`. Never fired: `TaskCreated`,
  `TaskCompleted`, `StopFailure`, `Notification`. A background subagent's
  normal completion reaches the parent only as a `UserPromptSubmit` with
  the task-notification (`PostToolUse(Agent)` fired at launch,
  `async_launched`). A plain `sleep N` is sometimes refused before any
  hook. Probe: `ai-artifacts/probes/departure_hooks_claude_code/`.
- *measured* 2026-09-28 (2.1.283, round 2 of the same probe) — **the
  parent's hooks identify a departed subagent in every ending but Escape.**
  `TaskStop`: `PostToolUse(TaskStop)` `tool_input.task_id` = the subagent's
  `agent_id` (= the launch-time `tool_response.agentId` =
  `SubagentStart.agent_id`), 16 ms after the kill; the same message comes
  whether or not the task still ran. Stall, foreground:
  `PostToolUseFailure(Agent)` carries only `tool_use_id`, but
  `<transcript_path minus .jsonl>/subagents/agent-<id>.meta.json` (written
  15–20 ms after `SubagentStart`, never rewritten) maps `toolUseId` →
  `agent_id`, and is present when the failure hook runs (37–40 ms after
  the kill). Background endings of every kind reach the parent as a
  `UserPromptSubmit` whose `prompt` is the task-notification:
  `<task-id>` = `agent_id`, `<tool-use-id>`, `<status>killed|failed|
  completed</status>`, `<summary>`, `<result>`; queued while the parent is
  inside a tool call (7.9 s behind a 20 s Bash call). Turn limit: the
  parent's `PostToolUse(Agent)` says `status: "completed"` with
  `harnessNoteCount ≥ 1` and a NOTE in `content` as the only sign; the
  notification's summary says "…turn limit…". Escape on a foreground
  subagent: no hook, no `meta.json` change; the transcripts gain the Agent
  `tool_result` "The user doesn't want to proceed…" + `[Request
  interrupted by user for tool use]` about 175 ms after the key (the stall
  kill writes the same text). `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` in
  the settings `env` applies under `-p` and via `--settings`: every Agent
  call runs foreground, so every ending but Escape yields
  `PostToolUse`/`PostToolUseFailure(Agent)`; the parent is then blocked for
  each subagent's whole life (no parallel subagents, no `TaskStop`).
  Agent-definition `hooks` add nothing at an abnormal end;
  `TaskCreated`/`TaskCompleted` are task-list events; `Notification` never
  fired. Not measured: `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` from
  interactive project settings; how a user stops a background agent from
  the UI.
- *measured* 2026-09-29 (2.1.283) — **the eight-block ceiling counts
  consecutive blocks with no tool call between them**: a block whose reason
  makes the agent run a tool (`echo`, so equally `check_construct`)
  restarts the count, and 15 such blocks were honoured with the variable
  absent, for `SubagentStop` and `Stop` alike; only text-only replies
  between blocks reach the 9th-block override. A resumed subagent
  (`SendMessage`) starts the count afresh. A `SubagentStop` override
  produces no text anywhere; the main `Stop`'s override text is the
  "A hook blocked the turn from ending 9 consecutive times — overriding …"
  line (stream `system`/`notification` `stop-hook-block-cap`).
  **`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` works**: `"0"` or `"1000"` in the
  project `.claude/settings.json` `env` under `-p`, `0` in the process
  environment, and `"0"` through `--settings` in interactive mode all had
  15 text-only blocks honoured with no override; the settings `env` is
  exported to the hook process and read by the ceiling logic (probe:
  `ai-artifacts/probes/block_cap_and_hook_cwd_claude_code/`). *measured*
  2026-10-13 (2.1.296, interactive, the project folder trusted through
  an enclosing git repository): `"0"` in the project
  `.claude/settings.json` honoured 164 consecutive text-only `Stop`
  blocks (`ai-artifacts/probes/live17/claude-code-5/`).
- *measured* 2026-09-29 (2.1.283) — **a hook command's cwd is the
  conversation's cwd**, equal to the payload's `cwd`: the launch directory,
  moved by a Bash `cd` in the main conversation to a directory inside the
  working or added directories (`CwdChanged` fires with `old_cwd`,
  `new_cwd`; every later hook runs there); a subagent's `cd` moves
  nothing; `CLAUDE_PROJECT_DIR` stays at the launch directory. **The
  project `.claude/settings.json` is loaded only when launched from the
  project root**: from a subdirectory (git root or not) and through
  `--add-dir` it is not loaded at all, so no hooks run; `--settings <file>`
  loads it from anywhere. Same probe.
- *docs* — A finished subagent can be resumed by `SendMessage` to its
  agent id or name, "without a new `Agent` invocation", keeping its full
  history; a subagent cancelled by the user or `stop_task` refuses the
  message; a resume takes a fresh concurrency slot. There is no built-in
  `wait` tool. Background subagents keep every MCP tool.
- *docs* — `SubagentStop` also fires for Claude Code's own internal agents
  (prompt suggestions, `/btw`), with an empty `agent_type`; an omitted,
  `""` or `"*"` matcher catches those too.
- *measured* 2026-10-13 (2.1.296, interactive) — such a `SubagentStop` of
  an internal agent follows every main-conversation turn, with a new
  `agent_id`, `agent_type` `""`, an `agent_transcript_path` naming a file
  that does not exist, and a suggested next prompt as
  `last_assistant_message`; the compaction summariser is another
  (`ai-artifacts/probes/live17/REPORT.md` §3.4).
- *measured* 2026-10-13 (2.1.296, interactive) — twice a `PreToolUse` on
  a TAT tool came under an `agent_id` found in no transcript, MCP log or
  file under `~/.claude`, the key `agent_type` absent: once while a
  blocked subagent waited in `check_construct`, once after 164 blocked
  `Stop`s of the main conversation; neither call reached TAT
  (`ai-artifacts/probes/live17/REPORT.md` §4.1). *source* (the 2.1.296
  bundle, `ai-artifacts/review/steps_16_17/orphan_agent_static.md`):
  these are Claude Code's internal agents — forked helper queries, the
  prompt suggestion after a turn and the progress summary of a running
  background subagent every 30 s — run on a copy of a conversation under
  a fresh agent id with no `agentType` and no transcript
  (`skipTranscript`); a tool call an internal agent's model emits runs
  the `PreToolUse` hooks first and is then refused by the internal
  agent's own permission function, whatever the hook answered. A
  `SubagentStop` of an internal agent carries `agent_type` `""`; its
  `PreToolUse` carries no `agent_type` key; every real subagent, teammate
  and workflow agent carries one. *source* (the 2.1.296 bundle,
  `ai-artifacts/review/steps_16_17/option_b_code.md` §4) — the key is
  `agent_type: s?.agentType ?? Kv()`, `Kv()` the main thread's agent
  type: under `--agent`, the setting `agent` or a pane teammate's custom
  type, an internal agent's `PreToolUse` and `SubagentStop` carry that
  type; the progress-summary internal agent (`Forked agent
  [agent_summary]`) fires no `SubagentStop` (*measured* 2026-10-13,
  2.1.296, `ai-artifacts/probes/orphan_agent/B4_summary_repeat/`).
  *measured* 2026-10-13 (2.1.296, interactive,
  `ai-artifacts/probes/option_b/`): 107 of 107 `PreToolUse` payloads
  with an `agent_id` and no `agent_type` were internal agents'
  (`Forked agent [prompt_suggestion]` ×106, `[agent_summary]` ×1); a
  background, a foreground, a custom (`probe-worker`) and a `fork`
  subagent carried `agent_type` on every payload; after a hook's allow,
  deny or empty answer the call never ran, a deny reason reaching only
  the internal agent's own model; `CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION=false`
  in the project settings' `env` left 0 internal agents and 0
  `SubagentStop`s over 26 blocked `Stop`s; a `fork` subagent's
  transcript file appeared 2.7 s after its first `PreToolUse`.
  *measured* 2026-10-13 (2.1.296,
  interactive, `--debug`, `ai-artifacts/probes/orphan_agent/`): 25 such
  `PreToolUse` in 125 blocked `Stop`s, each inside `Forked agent
  [prompt_suggestion]` in the debug log and refused there ("Hook
  approved tool use …, but canUseTool is required"); 0 in 207 with
  `CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION=false`; 30 in 99 with
  `CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1`;
  one inside `Forked agent [agent_summary]` 20.5 s into a blocked
  background subagent's follow-up call.
- *measured* 2026-10-13 (2.1.296, interactive, the agent directory inside
  a trusted git repository) — the agents' context held the `CLAUDE.md`
  of the enclosing repository and its auto-memory index (`MEMORY.md`
  under `~/.claude/projects/<repository>/memory/`): a run's compaction
  summary names both, and a subagent ran on Opus by that `CLAUDE.md`'s
  rule (`ai-artifacts/probes/live17/claude-code/`).
- *measured* — Hierarchy (main → child → grandchild, nesting allowed by
  default): no hook payload names a parent. `SubagentStart` carries only
  `session_id`, `transcript_path`, `cwd`, `prompt_id`, `agent_id`,
  `agent_type`; `PreToolUse` inside a grandchild carries the grandchild's
  id only; `transcript_path` is the main session's on every line;
  `agent_transcript_path` exists only on `SubagentStop`, pointing at the
  stopping agent's own file. The parent is recorded on disk beside that
  file, `…/subagents/agent-<id>.meta.json`: `{"agentType", "description",
  "toolUseId", "parentAgentId" (absent for a top-level child),
  "spawnDepth", …}`. A child's `SubagentStop` fires after its
  grandchild's; the main `Stop` after every `SubagentStop`.
- *docs* — `claude -p` runs the project's hooks and `.mcp.json` unless
  `--bare`; MCP tool calls: 28 h wall clock by default (`MCP_TOOL_TIMEOUT`,
  per-server `timeout`), 5 min idle for HTTP servers unless progress
  notifications arrive (`CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT`) — the idle
  part superseded by the *source* item below; a
  main-conversation call still running after 2 min moves to a background
  task and its result returns as a task notification (interactive mode;
  `CLAUDE_AUTO_BACKGROUND_TASKS=1` for `-p`).
- *source* (review 1's A13, ai-artifacts/review/CONSTRUCT_RULING.md;
  recorded here 2026-10-02) — Claude Code's window for an MCP tool call
  is `min(max(idle, serverTimeout, 1000), wallClock)`: the per-server
  `timeout` floors the idle window, so a call is waited for at least
  that long, progress notifications or not. Codex's `tool_timeout_sec`
  is a single wall clock.
- *docs* — What "progress" means for `CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS`:
  "The timer resets on each streaming progress event" (env-vars), "on
  each stream event" (SDK page) — an event of the subagent's model
  response stream. The default is `CLAUDE_STREAM_IDLE_TIMEOUT_MS` (300000,
  the floor) plus 5 minutes. Time inside a tool call is silence: "Claude
  Code doesn't emit heartbeats for tool calls inside a subagent" (it does
  in the main conversation, every 30 s). Measured: a hook sleeping past
  the window killed the subagent; a 56 s Bash loop under the 10-minute
  default survived. Whether an MCP `notifications/progress` resets it is
  not measured. The stream watchdogs proper (`network-config`) watch the
  API response only.
- *measured* 2026-09-28 (2.1.283) — **Time a subagent spends inside a
  blocking MCP tool call does not count toward the stall timeout.** With
  `CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS=20000`, a subagent's 60 s MCP call
  (no progress notifications) and another with a notification every 3 s
  both ran to completion and returned normally (completed 1, failed 0);
  the main-conversation control did too. Positive control on the same
  version with the variable at 15000: a `SubagentStop` hook sleeping 40 s
  was sent SIGTERM at 15.0 s, the subagent marked failed, the parent
  given `[Request interrupted by user for tool use]`. So the watchdog
  covers a hook's silence, not a tool call's; whether progress
  notifications count remains unmeasured (they made no visible
  difference). Implementation note: `mcp` 1.26.0's
  `Context.report_progress` sends without `related_request_id`, so the
  notification goes to the standalone GET stream; to put it on the
  call's own stream use `session.send_progress_notification(…,
  related_request_id=ctx.request_id)`. Probe:
  `ai-artifacts/probes/stall_timeout_mcp/`.
- *docs* — 20 concurrent subagents by default
  (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`), nesting 3 layers
  (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`), no total limit.
- *measured* 2026-09-30 (2.1.285, `-p`, sonnet) — **A `PreToolUse` hook
  can deny `TaskStop`**, and all three forms work identically:
  `hookSpecificOutput` `permissionDecision: "deny"` with
  `permissionDecisionReason`, top-level `{"decision":"block","reason":…}`,
  and exit 2 with the reason on stderr. The background subagent keeps
  running, its in-flight MCP call returns normally (60 s `hold`, no
  cancel, no disconnect) and it acts on the result; `killed` stays 0.
  The parent's tool result for the call is `is_error: true`, text
  `PreToolUse:TaskStop hook error: <reason>` (exit 2 adds `[<hook
  command>]: `). No `PostToolUse`, `PostToolUseFailure` or
  `PermissionDenied` fires; the stream's `permission_denials` lists the
  call. In 3 of 3 runs the parent carried out an instruction found only
  in the reason (`SendMessage` "CORMORANT" to the subagent) and did not
  retry the stop; its prompt said TAT's hooks may refuse calls and say
  what to do instead. Not measured: repeated denials, a foreground
  subagent. Probe: `ai-artifacts/probes/interrupt_denial_claude_code/`.
  *measured* 2026-10-13 (2.1.296, interactive): the denial of a
  `TaskStop` on a background subagent holding work reached the parent
  (`ai-artifacts/probes/live17/claude-code-5/`, 01:58:00).
- *measured* 2026-09-30 (2.1.285) — **`TaskStop`'s `tool_input.task_id`
  is the subagent's `agent_id`**, the same value as
  `SubagentStart`/`SubagentStop` `agent_id`, `PostToolUse(Agent)`
  `tool_response.agentId`, and the `agent_id` in the subagent's own
  `PreToolUse`/`PostToolUse`. The MCP server sees no agent field, only
  `_meta` `{claudecode/toolUseId, progressToken}` on the main
  conversation's session; the subagent's `PreToolUse(mcp__…)` payload
  carries both `tool_use_id` (= `claudecode/toolUseId`) and `agent_id`
  before the request is sent, so the announcement alone maps every call
  to its agent, and a `TaskStop` target to an `Agent`, with no
  transcript file read — **but only when the parent passes the id.**
- *measured* 2026-09-30 (2.1.285, review 4, probes
  `review4_refusal_facts/logs/N1_named` and
  `review4_defend/named_target/logs/C1_name_case`) — **`TaskStop`
  accepts the launch name too, and the hook sees it unresolved**:
  `PreToolUse(TaskStop)` carried `{"task_id": "prover"}`, `PostToolUse`
  then reported the resolved id, and the in-flight MCP call was
  cancelled 16 ms after the hook; `{"task_id": "Prover"}` stopped the
  subagent named `prover`, and `{"shell_id": "<id>"}` with no `task_id`
  stopped another. So a hook keyed by `agent_id` meets a string it has
  never seen, or no `task_id` at all.
- *measured* 2026-09-30 (2.1.285, `review4_refusal_facts/logs/N2_nested_fg`
  and `N3_nested_bg`) — **Nesting is on by default, and `TaskStop` on a
  subagent stops its foreground children with it**: main → `mid`
  (background) → `worker` (foreground, `spawn_depth: 2`); `TaskStop` on
  `mid` at 22.95 s; `worker`'s in-flight MCP call cancelled at 22.97 s;
  the stream carried `task_notification … status: "stopped"` for `mid`
  and for `worker`; no `SubagentStop` for either. A background
  grandchild (`N3_nested_bg`) survives the same stop and finishes. No
  hook payload names a parent; the parent is on disk only
  (`agent-<id>.meta.json`, `parentAgentId`, `spawnDepth`,
  `requestShape`). *docs*: `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`
  (default 3) and `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` (default 20)
  are environment variables; their exact semantics were not measured.
- *measured* 2026-09-30 (review 4, `review4_defend/taskstop_empty_answer`,
  Claude Code 2.1.285, `-p`, the main conversation as caller) — **An
  empty `PreToolUse` answer lets `TaskStop` through**: the task was
  stopped with `TaskStop` not in the allowed tools and `permission_denials:
  []`; the static read agrees, `TaskStop` defines no permission check
  of its own. Not measured: a subagent as the caller. *measured*
  2026-10-13 (2.1.296, interactive): the main conversation's `TaskStop`
  answered with nothing was allowed
  (`ai-artifacts/probes/live17/claude-code/`, 21:59:25). A `TaskStop` on
  a task already completed fires no `PreToolUse` (`…/claude-code-3/`,
  01:02:18, "not running (status: completed)").
- *source* 2026-09-30 (Codex 0.156.1, `hooks/src/engine/output_parser.rs`
  ~455; unit test `permission_decision_allow_without_updated_input_fails_open`)
  — **Codex answers a bare `permissionDecision: allow` (no
  `updatedInput`) with "unsupported permissionDecision:allow"**, marks
  the hook run failed (the TUI shows "Hook failed") and lets the call
  proceed. Hence TAT answers an allowed interruption with an empty
  answer on both clients.
- *measured* 2026-09-30 (review 4, `review4_defend/hook_exit_codes`,
  curl 8.5.0 and an old-curl stand-in) — **The hook script's exit
  codes**: with `exit $rc` after `curl --fail-with-body`, status 503 and
  500 exited 22, and a curl older than 7.76 rejects `--fail-with-body`
  and exits 2, which both clients read as a block; with `-f` and `||
  { [ $? -eq 7 ] && not_running; exit 1; }`, every failure — 200 is not
  one; 503, 500, a refused port, a missing lock file, a curl exiting 2 —
  exits 1.
- *measured* 2026-09-30 (2.1.285, sonnet, probe
  `ai-artifacts/probes/claude_code_subagent_compaction/`, 36 subagent
  and 13 main-conversation compactions) — **A subagent's compaction
  fires `PreCompact`, `SessionStart` (`source: compact`) and
  `PostCompact`, none naming the agent**: no `agent_id`, `session_id`
  and `transcript_path` the main conversation's, key sets identical to
  a main-conversation compaction (66 `SessionStart` payloads, none with
  `agent_id`). `SessionStart`'s `additionalContext` reaches exactly the
  agent that compacted (36 of 36), never another. The compacting agent's
  own transcript gains a `compact_boundary` entry, on disk before that
  agent's next `PreToolUse` (39 of 39; not yet while the compaction
  hooks run). An instruction in the briefing to call a TAT tool at once
  was obeyed 6 of 6 times. Nothing changes on the MCP side. `startup`,
  `resume` (also `-c`) and `clear` `SessionStart`s reach the model;
  `clear` gives a new `session_id` after a `SessionEnd`. Too-large tool
  results make Claude Code abort a subagent ("Autocompact is
  thrashing"). Not measured: the `fork` source, a subagent resumed
  after compaction.
- *measured* 2026-09-30 (Codex 0.156.1, `gpt-6-luna`, probe
  `ai-artifacts/probes/codex_subagent_compaction/`, 6 main and 6
  subagent compactions) — **`PreCompact` and `PostCompact` fire for
  every thread that compacts, a subagent's payload carrying `agent_id`**
  (= its `_meta.threadId`), `session_id` the root thread's;
  `SessionStart(compact)` fires for the main conversation only
  (`hook_runtime.rs:148` returns for a subagent), at once after an
  automatic compaction and at the next prompt after `/compact`, and its
  `additionalContext` reaches the model; what `PreCompact`/`PostCompact`
  answer never does (`systemMessage` shown to the user only,
  `additionalContext` rejected as "Hook failed"). `PreToolUse`'s
  `additionalContext` and the tool result reach a subagent after its
  compaction. `_meta.windowId` is `<thread id>:<n>`, n rising by one per
  compaction. A compacted subagent given a follow-up task had forgotten
  its `SubagentStart` briefing. `SessionStart` sources measured:
  `resume`, `fork`, `clear` reach the model; `/new` gives `startup`.
- *measured* 2026-09-30 (2.1.285) — **`SendMessage` to a busy subagent
  waits for its next tool round.** The sender is told "Message queued
  for delivery … at its next tool round". Sent during a 60 s MCP call,
  the message is injected 40–100 ms after the call's result, as a
  `queued_command` system reminder ("The coordinator sent a message
  while you were working: … Address this before completing your current
  task."), and the subagent acts on it before its next call. Sent while
  the model is still writing a response, it waits until the tool call in
  that response returns (a whole 20 s `hold`). If that response is the
  final reply, the subagent completes (the parent gets a `completed`
  notification) and is resumed 131 ms later with the message:
  `SubagentStart` fires again with the same `agent_id`, and a second
  notification follows without `<tool-use-id>`. Sent to a completed
  subagent, the message resumes it at once ("Resuming agent …",
  `resumedAgentId`, a new `SubagentStart`), and the next notification's
  `<tool-use-id>` is the `SendMessage` call's id.

## Codex (codex-cli 0.153.2, source tag `rust-v0.153.2`)

- *source* — Every thread owns its MCP runtime and connection set
  (`session/session.rs`: "one stable thread-owned MCP runtime handle";
  `codex-mcp/src/runtime.rs`: "the thread-owned MCP runtime"). A spawned
  subagent is a new thread with a new `Session`, so each subagent has its
  own `Mcp-Session-Id`. *measured* 2026-10-13 (0.156.1): a subagent
  thread's first TAT call opened a second MCP session; `clientInfo` is
  `{name: "codex-mcp-client", version: "0.156.1"}` on each.
- *measured* 2026-10-13 (0.156.1) — the hook payloads: every hook carries
  `hook_event_name`, `session_id`, `transcript_path`, `cwd`, `model`;
  every hook but `SessionStart` carries `turn_id`, and every hook but
  `PreCompact`/`PostCompact` carries `permission_mode`. `PreToolUse` adds
  `tool_name`, `tool_input`, `tool_use_id`, and in a subagent thread
  `agent_id` and `agent_type`; `Stop` adds `last_assistant_message` and
  `stop_hook_active`; `SubagentStop` adds those two and `agent_id`,
  `agent_type`, `agent_transcript_path`; `PreCompact`/`PostCompact` add
  `trigger`; `SessionStart` adds `source`.
- *source* — `env_http_headers` reads the process environment
  (`rmcp_client.rs`, `env::var`): the same value for every thread; it
  identifies the launch, not the subagent.
- *source* — Default cap on spawned threads: 4
  (`DEFAULT_MULTI_AGENT_V2_MAX_CONCURRENT_THREADS_PER_SESSION`), config
  `agents.max_concurrent_threads_per_session`. Nesting depth:
  `agents.max_depth`, `DEFAULT_AGENT_MAX_DEPTH = 1` in `config/mod.rs`,
  refused with "Agent depth limit reached. Solve the task yourself." —
  but `config.schema.json` says "Maximum nesting depth for V1 agent
  threads. Ignored by V2", and the measured run (V2 tools,
  `collaborationspawn_agent`) spawned a grandchild with no depth setting.
  No V2 depth limit found in the source searched.
- *measured* — Hooks are silently inert until trusted: a first `codex exec`
  ran to completion with every hook registered and wrote nothing, no
  warning anywhere. Trust is per hook, written by the TUI's "Hooks need
  review" dialog into `config.toml` as `[hooks.state."<path>:<event>:<group>:
  <handler>"] trusted_hash = "sha256:…"`; the CLI flag
  `--dangerously-bypass-hook-trust` exists for automation. Once trusted,
  `codex exec` runs all hooks (`SessionStart`, `PreToolUse`,
  `SubagentStart`, `SubagentStop`, `Stop` all fired). Hooks and
  multi-agent are on by default (`codex features list`).
- *measured* — Hierarchy: `agent_id`s are UUIDs; `session_id` is the
  main session's on every line; `transcript_path` is the rollout file
  whose name embeds an id — the agent's own on `SubagentStart` and on a
  `PreToolUse` inside it, the **parent's** on `SubagentStop`, where
  `agent_transcript_path` is the stopping agent's own. So the tree is
  reconstructable from the `SubagentStop` stream, not at start. The
  spawning agent's `PreToolUse` shows `tool_name`
  `collaborationspawn_agent` with `task_name` and an encrypted `message`;
  the parent then blocks in `collaborationwait_agent` (`timeout_ms`
  3600000). `agent_type` is `default` without custom roles. A
  grandchild's `SubagentStop` fires before the child's; the main `Stop`
  after every `SubagentStop`.
- *docs* — Hooks: `Stop` runs synchronously "when a turn stops";
  `{"decision": "block", "reason": …}` "automatically creates a new
  continuation prompt that acts as a new user prompt, using your reason
  as that prompt text"; `stop_hook_active` = "whether this turn was
  already continued by Stop"; default timeout 600 s; async hooks cannot
  block. `SubagentStop` carries `agent_id` and the parent's `session_id`.
  `PreToolUse` can deny and add context; the docs say it cannot rewrite
  arguments, but on 0.156.1 `updatedInput` with `permissionDecision:
  allow` does (measured 2026-09-30, below). MCP tool calls time out
  after 60 s by default (`tool_timeout_sec` per server).
  Whether hooks run under `codex exec` is not documented.

## Both clients: a tool argument declared as a bare object (*measured* 2026-09-27)

A tool `answer` declared with `answer: {"type": "object"}` (no
`properties`), whose actual shape a previous tool result states as an
embedded JSON schema:

- Claude Code 2.1.283 (Opus) advertised the declaration unchanged (the
  model's rendering equals the server's `tools/list` byte for byte up to
  key order); Codex 0.156.1 (`gpt-5.6-sol`) rendered it with an extra
  `"additionalProperties": true` inside `answer` (not sent by the server;
  whether Codex injects it or the model added it in rendering is not
  distinguished).
- Both models called `answer` with `answer` as a nested JSON object of the
  stated shape (`verdict`, `constraints: [{name, term}]`, `reason`), not a
  string, not flattened; both clients passed it to the server unchanged
  (`raw_body`); `≠` survived as UTF-8 both ways.
- On a deliberate `isError: true` one-line rejection both retried once:
  Codex rewrote the named field, Claude Code resubmitted byte-identical
  arguments (the rejection was false, so neither had a real fault to
  fix). Codex labels an `isError` result `(failed)` in its transcript and
  still feeds the text to the model.
- Both invented `node_id` = `lemma_P` from the question's text: the
  question must state the node's id.
- Codex **`_meta` on every `tools/call`** carries `callId`,
  `x-codex-turn-metadata` (`session_id`, `thread_id`, `turn_id`, `model`,
  `thread_source`, …), `threadId`, `sessionId`, `windowId`, `itemId`,
  `progressToken`. `thread_id` is the thread's UUID — the value the hooks
  report as `agent_id` — so Codex's calls are attributable to a thread
  without any announcement. Measured on the main thread only
  (`thread_id` = `session_id` there); a subagent thread's value is not yet
  measured.
- *measured* 2026-09-28 (0.156.1, `codex exec --dangerously-bypass-hook-trust`,
  hooks ran): a **subagent thread's** `tools/call` carries
  `x-codex-turn-metadata.thread_id` = top-level `threadId` = the
  subagent's own thread id = the `agent_id` its `SubagentStart`/
  `SubagentStop`/`PreToolUse` hooks report; `session_id`/`sessionId` stay
  the main session's; `thread_source` is `"subagent"` (`"user"` on the
  main thread); also `parent_thread_id`, `forked_from_thread_id`,
  `subagent_kind: "thread_spawn"`. The subagent's call went over its own
  `Mcp-Session-Id` (own `initialize` + `tools/list` about 6 s after
  `SubagentStart`); both sessions got a `DELETE` at the end. Each `whoami`
  `PreToolUse`'s `tool_use_id` equals the call's `_meta.callId`. So
  Codex's `agent_of_call` reads `thread_id` from `_meta`; no announcement
  needed. Probe: `ai-artifacts/probes/codex_thread_meta/`.
- *source + docs* 2026-09-28 (tag `rust-v0.156.1`, identical in 0.153.2
  and `main`): **no config key or environment variable replaces
  `--dangerously-bypass-hook-trust`** — it is a runtime-only override
  ("not from config files", `core/src/config/mod.rs:942`), read in
  `hooks/src/engine/discovery.rs:713-719`; searched `trust_all`,
  `bypass_trust`, `trust_hooks`, `auto_trust`, `skip_trust`, env reads.
  Trust entries (`[hooks.state."<abs path of hooks.json>:<event
  snake_case>:<group>:<handler>"] trusted_hash`) are read only from the
  user layer (`$CODEX_HOME/config.toml`) and `-c` launch flags
  (`hooks/src/config_rules.rs:8-29`); entries in a project's
  `.codex/config.toml` are ignored. A project's `.codex/hooks.json` loads
  only when the project is trusted (`projects.<path>.trust_level`). The
  hash is `sha256:` of the compact sorted JSON of one normalized handler
  (`{"event_name", "matcher"?, "hooks": [{"async", "command",
  "timeout", "type", …}]}`, `discovery.rs:766-792`,
  `config/src/fingerprint.rs:54-84`); recomputed offline, matched all 5
  measured hashes. Undocumented; tied to the file's absolute path and
  handler positions. Managed layers (`/etc/codex/`, MDM,
  `requirements.toml`) need no hash. Probe:
  `ai-artifacts/probes/codex_hook_trust/` (`recompute_hash.py`).
- Codex under `approval_policy = "never"` blocks every MCP tool call
  (`MCP tool call requires approval, but approval policy is never`)
  unless the server entry has `default_tools_approval_mode = "approve"`
  (`auto` does not suffice; allowed values `auto`, `prompt`, `writes`,
  `approve`); project `trust_level` does not cover MCP tools. Codex sends
  a `DELETE` at session teardown; Claude Code calls `prompts/list` and
  `resources/list` at connect, Codex does not.
- *measured* 2026-09-28 (Codex 0.156.1, `gpt-5.6-sol`, all 12 hook events
  logged) — **a Codex subagent that ends abnormally fires no hook**: no
  `SubagentStop`, no `Interrupt` in its name. Cases: the parent's
  `interrupt_agent` (the only stop tool; there is no close/kill; a following
  `wait_agent` does not return on the interruption, `list_agents` shows
  `interrupted`); a `wait_agent` timeout (nothing fires; the subagent runs on
  and gets a normal `SubagentStop` only if it finishes while the session
  lives); the parent's session ending (the subagent is aborted silently at
  `SessionEnd`); SIGINT to `codex exec` and Escape in the TUI (`Interrupt`
  fires once, for the main thread, without `agent_id`; the subagent is
  untouched until the session ends). No turn or time limit exists for
  subagents (`agents.*` keys, `--help`, `features list`). A blocking
  `SubagentStop` holds a subagent that completes normally, in both forms
  (`{"decision":"block"}` and exit 2; the second `SubagentStop` carries
  `stop_hook_active: true`). In every abnormal case the subagent's shell
  command lived on as an orphan. `SubagentStop`'s `transcript_path` is the
  parent's rollout, `agent_transcript_path` the subagent's; `wait_agent`
  returns only `{message, timed_out}`. Not measured: blocking after a
  timeout, whether `Interrupt` can block, grandchildren, other models.
  Probe: `ai-artifacts/probes/departure_hooks_codex/`.
- *measured* 2026-09-28 (0.156.1, round 2 of the same probe) — **an MCP
  server learns nothing from its own traffic when a Codex subagent is
  interrupted**: no `notifications/cancelled` (never, in any run), no
  connection drop, no `DELETE`; the in-flight `tools/call` stays open until
  the whole session ends, when both sessions get a `DELETE` and their
  connections drop, the same for a normal and an abnormal ending. **An
  interrupt is a pause, not an end**: `followup_task` resumes the thread
  (rollout `task_started`, no new `SubagentStart`) and it then ends with a
  normal `SubagentStop`. The parent's `PreToolUse`/`PostToolUse` on
  `collaborationinterrupt_agent` fire every time, with `tool_input.target`
  the agent *path* (`/root/probe_child`), not the thread id; the link is
  the subagent's rollout file's first line (`session_meta`: `id`,
  `agent_path`, `parent_thread_id`, `agent_nickname`), the file being
  `SubagentStart.transcript_path`, which exists about 2 s before the hook.
  The rollout records every abnormal ending within ~20 ms
  (`{"type":"turn_aborted","reason":"interrupted"}` at an interrupt, at
  session end, at SIGINT; for TUI Escape only when the TUI quits, since
  Escape does not interrupt the subagent; `task_complete` for a normal
  end); undocumented format. `agents.interrupt_message` only toggles the
  `<turn_aborted>` marker in the history. The app-server protocol (`codex
  app-server`, JSON-RPC, 82 notification kinds) reports it explicitly —
  `subAgentActivity` items of kind `started|interrupted|completed` with
  `agentThreadId`, `turn/completed` with status `interrupted`,
  `thread/status/changed` — and a second client on a shared `ws://`
  app-server sees every thread's notifications; but `codex exec` and the
  TUI run no app-server TAT could join, and closing the app-server sends
  nothing for a running subagent. Not measured: `send_message` as a
  resume, nested subagents, the app-server with hooks, the managed daemon
  (socket path too long here), whether the TUI runs an internal
  app-server.
- *measured* 2026-09-29 (0.156.1, `gpt-6-luna`, hooks POSTing to a local
  HTTP server) — **`SessionStart` fires at the first prompt, once per
  process**, never for a subagent thread (`SubagentStart` instead); fields
  `session_id`, `transcript_path`, `cwd`, `model`, `permission_mode`,
  `source: "startup"`, no thread id. **The main thread's MCP `initialize`
  and `tools/list` precede it** by 2.5–5.3 s (in the TUI with no prompt
  given, by as long as the user takes to type one); it precedes the first
  `tools/call` by 4–6 s. **Every `tools/call`, main or subagent, is
  preceded by its own `PreToolUse`** reaching the server 5–8 ms earlier;
  a subagent's `SubagentStart` precedes its own MCP session's
  `initialize` by 4–5 s. Without the flag: no hook fires, nothing says so,
  the MCP calls proceed. A failing hook (exit 1/2, server down) has no
  visible effect in `exec` (the TUI shows a non-blocking "Hook failed"
  line), except that exit 2 on `UserPromptSubmit` silently blocks the
  prompt. After Ctrl-C in the TUI neither `SessionEnd` nor an MCP `DELETE`
  appears (both do in `exec`). **A hook's cwd is the session's cwd**, equal
  to the payload's `cwd`: the `-C` directory, else the launch directory,
  not the git root; a subagent's hooks run in the parent's cwd. Not
  measured: `SessionStart` on resume/`/new`/compaction, nested subagents,
  a hanging hook. Probe: `ai-artifacts/probes/session_start_and_hook_cwd_codex/`.
- *measured* 2026-09-30 (0.156.1, `gpt-6-luna`, `codex exec --json`) — **A
  blocking `Stop` or `SubagentStop` hook's reason reaches the model** in
  both forms, stdout `{"decision":"block","reason":…}` and exit 2 with the
  reason on stderr. It arrives as a new user-role message in the blocked
  agent's own conversation, within the same turn, as `<hook_prompt
  hook_run_id="stop:…|subagent-stop:…">REASON</hook_prompt>` with no other
  framing; for `SubagentStop` that is the subagent's conversation, and the
  parent never sees it. The model cannot tell the two forms apart. Proven
  by marker files with random names that only the reason gave, and by the
  rollouts. Probe: `ai-artifacts/probes/stop_hook_reason_codex/`.
- *measured* 2026-09-30 (0.156.1) — **The reason arrives verbatim with two
  exceptions**: the whole text is trimmed of leading and trailing
  whitespace, and `&`, `<`, `>` become `&amp;`, `&lt;`, `&gt;`. Interior
  newlines, indentation, backticks, quotes, multi-line JSON, `\r\n` and
  non-ASCII are unchanged. **A ~100 KB reason was cut to ~10 KB**: a
  warning header, the head, a `…N tokens truncated…` mark, the tail, then
  a pointer to `/tmp/hook_outputs/<session>/<uuid>.txt` holding the full
  text (the model did not open it). The threshold is not measured.
- *measured* 2026-09-30 (0.156.1) — **Repeated blocks keep working**: seven
  consecutive `Stop` blocks were all honoured and every reason delivered;
  each earlier reason stays in the context. The hook input has
  `stop_hook_active: false` on the first stop and `true` on every later
  one in the same turn, for `Stop` and `SubagentStop` alike. Under `codex
  exec --json` the reason never appears in stdout or stderr. Not measured:
  the TUI and app-server front ends, the truncation threshold, escaping
  and truncation on `SubagentStop`, an empty reason, more than seven
  blocks.
- *measured* 2026-09-30 (0.156.1, `gpt-6-luna`, `codex exec`) — **A Codex
  subagent never sees an MCP result that arrives after `interrupt_agent`.**
  Codex keeps reading the open `tools/call` and records the late answer
  within about 1 ms as a rollout `event_msg` `item_completed`
  (`McpToolCall`, `status: completed`, full result) stamped with the
  **aborted** `turn_id`, then fires a normal `PostToolUse` (old `turn_id`,
  full `tool_response`, `tool_use_id` = `_meta.callId`); but no
  `response_item` is written: the model saw only "aborted by user after
  Ns" at the interrupt. Proven by a marker instruction carried only by
  the late result: no file was created and no reply mentioned it, both
  when the answer came before `followup_task` (2 runs) and when it came
  during the resumed turn while the subagent was inside a new call (2
  runs). Nothing marks the response as discarded: stdout, default stderr
  and `logs_2.sqlite` are silent, and at `RUST_LOG=debug` it is logged as
  `codex.tool_result success=true` / `tool_result_ready`. The resumed
  subagent's new call uses the same `Mcp-Session-Id` and `thread_id` with
  a new `turn_id`, and the subagent ends with one normal `SubagentStop`
  (`stop_hook_active: false`). So a server cannot hand work to a resumed
  subagent through the old call, and cannot learn from its own traffic
  that the answer was dropped; the only in-band sign is that the answered
  request carries the old `turn_id` (`x-codex-turn-metadata`) while newer
  calls carry a different one. Not measured: a late `isError` result, a
  result after the subagent finished, the TUI and app-server, other
  models. Probe: `ai-artifacts/probes/late_result_after_followup_codex/`.
- *measured* 2026-09-30 (0.156.1, `gpt-6-luna`) — **MCP tools are reachable
  only through code mode**: every subagent MCP call ran inside the model's
  `exec` JavaScript cell (`code_mode.broker.invoke_tool`). With `--disable
  code_mode_host`, `exec` answers "code-mode host is disabled" and no
  `mcp__*` tool is offered, so the model cannot call MCP at all. A call
  longer than the cell's yield returns "Script running with cell ID n",
  and the model polls with `wait {cell_id, yield_time_ms}`.
- *measured* 2026-09-30 (0.156.1, `gpt-6-luna`) — **A `PreToolUse` hook
  can deny `collaborationinterrupt_agent`.** `{"hookSpecificOutput":
  {"hookEventName":"PreToolUse","permissionDecision":"deny",
  "permissionDecisionReason":R}}`, `{"decision":"block","reason":R}` and
  exit 2 with R on stderr all work identically. The subagent is
  untouched: no `turn_aborted`, its open MCP call returns into the same
  turn, and it acts on the result. The parent's tool output is the
  literal string `Tool call blocked by PreToolUse hook: R. Tool:
  collaborationinterrupt_agent` (a trailing full stop in R gives `..`).
  No `PostToolUse` fires for the denied call; stderr logs one `ERROR
  codex_core::tools::router` line. Whether the parent then does what R
  says is up to the model: it sent the requested `send_message` in 1 of 3
  runs (reasoning effort low). Probe:
  `ai-artifacts/probes/interrupt_denial_codex/`, runs 02–04.
- *measured* 2026-09-30 (0.156.1) — **No hook or `_meta` field carries
  both an agent path and a thread id.** The path appears only in the
  parent's `PostToolUse` on `spawn_agent` (`tool_response`
  `{"task_name":"/root/probe_child"}`) and in `interrupt_agent`'s
  `tool_input.target`, which the model writes either as
  `/root/probe_child` or as a bare `probe_child`. The thread id appears
  as `agent_id` in `SubagentStart` (no path, no nickname) and in
  `_meta.threadId`; `_meta`'s `x-codex-turn-metadata` also carries
  `parent_thread_id` (the spawner), `turn_id`, `subagent_kind`,
  `thread_source`. The hook's `tool_use_id` equals `_meta.callId`. The
  thread id is a UUIDv7: in 6 of 6 subagents its millisecond timestamp
  fell inside its own spawn call's `PreToolUse`→`PostToolUse` window
  (85–100 ms) and inside no other, so path and thread id can be matched
  by time; `SubagentStart` does not come directly after its own spawn's
  `PostToolUse`, though first-in-first-out order held. (runs 02–05, 09)
  **The one deterministic source of both names is the thread's own
  rollout file**, whose path every hook fired for the thread hands over
  (`transcript_path`; on `SubagentStop`, `agent_transcript_path`): its
  first line is a `session_meta` record with `payload.id` (the thread
  id), `payload.session_id`, `payload.agent_path` (absent on the main
  thread, i.e. `/root`) and `payload.cli_version`; Codex writes it when
  it opens the file, and the hook's path is produced only after the
  file is on disk. Verified 157/157 hook records, 15/15 MCP calls, 11/11
  interrupts, including two spawns 3 ms apart with the same bare name
  under different parents, resume, reload after idle unload, forks and
  grandchildren; `codex exec --ephemeral` has no rollout and a null
  `transcript_path`. Codex resolves an `interrupt_agent` target as a
  UUID first, then an absolute path, else a name under the caller's
  path (`agent_resolver.rs`, `agent_path.rs`). A `PreToolUse` answer of
  `permissionDecision: allow` with `updatedInput: {target: …}` rewrites
  the argument (6/6; the docs say `PreToolUse` cannot rewrite
  arguments). Researched for the design and not adopted; ruling and
  probes: `ai-artifacts/review/CODEX_PATH_MAPPING_RULING.md`,
  `ai-artifacts/probes/codex_path_mapping_*`.
- *measured* 2026-09-30 (0.156.1) — **`send_message` to a subagent
  blocked in a long MCP call is appended to its context** (an
  `agent_message`, `trigger_turn: false`) **at the next yield of its
  code-mode `exec` or `wait` call**, while the MCP call is still open,
  but only once the current `yield_time_ms` window ends: 31 s for the
  first yield, then a model-chosen 10–30 s (a message sent during a
  `wait` waited 25 s). If the call returns before a yield, the message
  follows the result at once. To a subagent whose turn has ended, the
  message is not written anywhere and starts no turn; it is delivered at
  the start of the next turn, just before the `followup_task` payload.
  (runs 03, 05–08)

## Isabelle: Unicode in command text (*measured* 2026-09-28)

Isar text fed to Isabelle/ML as a string — TAT's `run_commands` path
(`Outer_Syntax.parse_spans` + `Toplevel.command_errors`), and equally the
ML `.thy` loader (`Resources.check_thy`, `File.read`, no conversion) —
**rejects every Unicode symbol tried**: `≠ ⟶ ⟹ ∀ λ ⋀ ∈ ¬ ∧ ₁ α ⇒`
inside `"…"` give `Inner lexical error`; `‹ ›` as cartouche brackets fail
in the outer syntax before any command runs. The ASCII forms
(`\<noteq>`, `\<forall>`, `\<^sub>1`, `\<open>…\<close>`) all work on the
same path. Cause: Isabelle/ML has no Unicode→`\<name>` table
(`Pure/General/symbol.ML`: `Symbol.decode` labels a UTF-8 sequence
`UTF8` and passes it through; `open_`/`close` are only `\<open>`/
`\<close>`); the table lives in Isabelle/Scala (`symbol.scala`
`Symbol.encode`), applied to protocol messages in `prover.scala:305`, which
TAT's text never passes through. Consequence: TAT must convert agent text
with `Isabelle_RPC_Host.unicode.ascii_of_unicode` (as AoA does) before
`run_commands`, for terms and for `text ‹…›` alike. Probe:
`ai-artifacts/probes/unicode_terms/` (`probe.ML`, `REPORT.md`).

## Both clients: what tells whose context was replaced (2026-10-01)

From the eleven repair agents' probes
(`ai-artifacts/probes/compaction_identity_repair/<candidate>/`, results
in `ai-artifacts/review/COMPACTION_IDENTITY_REPAIR_RESULTS.md`) and the
judge's re-runs (`ai-artifacts/review/COMPACTION_IDENTITY_REPAIR.md`
§2). Claude Code 2.1.285 and 2.1.286 (the client updated itself from the
one to the other during 2026-10-01), model sonnet unless said; Codex
codex-cli 0.156.1. Facts found by one agent only are in its result, not
here.

Claude Code, an agent's transcript:

- *docs* (sub-agents.md) + *measured*: the main conversation's
  transcript is the hook payload's `transcript_path`; subagent X's is
  `<transcript_path minus .jsonl>/subagents/agent-X.jsonl`. *measured*:
  a workflow agent's is one directory deeper,
  `subagents/workflows/wf_<run>/agent-X.jsonl`; an in-process teammate's
  is `subagents/agent-a<name>-<hex>.jsonl` (one run, read offline). A
  census of this machine (about 9,600 files): these layouts only, no
  agent id twice within one session directory.
- *measured*: every compaction — automatic, manual `/compact`, reactive
  (1 of 1), and both partial kinds of the rewind menu — appends exactly
  one line `{"type":"system","subtype":"compact_boundary",…}` with its
  own `uuid` and `timestamp` to the compacting agent's own transcript
  (30 of 30, 24 of 24, 19 of 19 live in three independent probes; main
  conversation, foreground, background, resumed-by-SendMessage and
  workflow agents). The line is on disk 0.06–0.18 s after `PostCompact`
  arrives; the same agent's next `PreToolUse` comes at least 1.07 s
  after the line lands (n = 23, 17, 18) and at least 1.19 s after the
  line's own `timestamp` (n = 136). *binary*: the transcript writer
  flushes on a 100 ms timer.
- *measured*: one `PostCompact` per compaction (24 of 24; the two counts
  equal at all 151 announcements of one probe). A `PreCompact` proves no
  compaction: 637 `PreCompact` hooks against 607 compactions over all
  logs.
- *measured*: an agent's transcript exists at least 1.42 s before its
  first `PreToolUse` on an MCP tool (15 of 15; 59 further first
  announcements, none missing); `SessionStart(startup)` fires before the
  main file exists (9 of 9).
- *measured*: at `/clear` the main conversation gets a new
  `transcript_path`; a background subagent that keeps running keeps its
  context, its earlier lines stay in the old file and its later lines go
  to a new file (new inode) under the new session directory, the two
  files sharing no `uuid` (5 of 5 moves); the new file can appear after
  the agent's next announcement (91 ms after it, once). *binary*: a
  message removal cuts the main file in place; an opt-in local clean-up
  rewrites it by rename.
- *measured*: the compaction's summary (`PostCompact`'s
  `compact_summary`, *docs*) is in the agent's own transcript verbatim,
  in a message marked `isCompactSummary`, by that agent's next call
  (52 of 52); never yet on disk when `PostCompact` runs (31 of 31).

Claude Code, when no transcript is written:

- *measured*: `--no-session-persistence` writes none and no environment
  variable undoes it. An inherited `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1`
  writes none; `"0"` (or `""`) in the settings `env` turns transcripts
  back on (four probes; under `-p`, and interactively through
  `--settings`; an interactive session reading a trusted project's
  settings file: measured 2026-10-13 (2.1.296): the transcript was
  written under an inherited `=1`
  (`ai-artifacts/probes/live17/claude-code-env/`)).
  An interactive session that inherits
  `CLAUDE_CODE_CHILD_SESSION=1` (started from inside another Claude
  Code) writes none ("Transcript saving is off — inherited
  CLAUDE_CODE_CHILD_SESSION marker"); `CLAUDE_CODE_FORCE_SESSION_PERSISTENCE=1`
  turns them back on (*docs* env-vars.md says the same; *measured*
  2026-10-13 (2.1.296) interactively from a trusted project's settings
  file: the transcript written and read under an inherited
  `CLAUDE_CODE_CHILD_SESSION=1` and `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1`,
  `ai-artifacts/probes/live17/claude-code-env2/`), and does not
  undo SKIP or the flag; under `-p` the marker suppresses nothing.

Claude Code, context removed without a compaction:

- *measured* (two interactive runs): a plain rewind — the rewind menu's
  "Restore conversation", or Esc Esc to edit an earlier prompt and send
  it again — fires no hook of any kind and removes later tool results
  from the context. Read offline in those two transcripts: the prompt
  sent after it is a user entry whose `parentUuid` equals an earlier
  user-prompt entry's. A partial compaction from the same menu fires
  `PreCompact` with `trigger: manual` and writes a `compact_boundary`
  line with a `preservedSegment`.
- *binary*, not run: client-side microcompaction and the server-side
  `clear_tool_uses_20250919` edit clear the results of built-in tools
  only; MCP tools are excluded.

Claude Code, other channels measured on the way:

- `PreCompact`'s stdout at exit 0 is appended to the summarizer's
  instructions (*binary*, the `/hooks` menu text; *measured* on both
  versions): a `PreCompact` hook of TAT's must print nothing.
- With `CLAUDE_CODE_GATEWAY_HINT_HEADERS=1` the client's model requests
  carry `x-claude-code-session-id`, `x-claude-code-agent-id` (a
  subagent's), `x-claude-code-request-class` (main, subagent, workflow)
  and, on a compaction's summary request, `x-claude-code-compaction`
  (*measured*, 2.1.286).
- Early-access function hooks (`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`, a
  plugin's JavaScript module): a `tool.call` hook runs before the
  command `PreToolUse` hook of the same call (30–109 ms earlier, 172 of
  172); `$.session.messages({as: 'api', agentId})` returns the calling
  agent's context and is refused for the agents of a workflow run (12 of
  12); `session.compact` does not fire for a partial compaction from the
  rewind menu (*measured*).
- With tracing on, each hook process gets a `TRACEPARENT` whose span is
  the agent's own, except that the agents of one Workflow run share one
  span (*measured*, 2.1.286).

Codex (0.156.1):

- *measured*: the model makes every MCP call from inside a code-mode
  cell (112 of 112 calls in the logs); a call's `_meta.windowId` is the
  window current when its cell started, not when the call is made. A
  call can be open across a compaction of its own thread (4 of 101
  calls) and end between `PreCompact` and `PostCompact`, its result then
  delivered into the new window (main conversation and subagent, one run
  each); a cell can keep a result and print it only after a compaction
  (one run), or discard it (one run).
- *source* (`compact.rs`, `turn.rs:1605`) + *measured*: `PostCompact` is
  awaited before the thread's next model request; a cell's tool calls
  are dispatched only while a model request runs (2 of 2); a failed
  compaction runs `PreCompact` and no `PostCompact` (*source* only).
- *source* (`sess.hook_transcript_path()`) + *measured*: `PreToolUse`,
  `PostCompact` and `SessionStart(compact)` carry the thread's own
  rollout path as `transcript_path` (18 of 18 and 10 of 10 paired; 40 of
  40 by the file name `rollout-<time>-<thread id>.jsonl`); one path per
  thread, never shared (22 and 28 threads); `resume` keeps it.
- *source* only: threads not spawned as subagents (`/review`, guardian,
  memory) carry no `agent_id`; `--ephemeral` gives no `transcript_path`;
  `[features.code_mode]`'s `direct_only_tool_namespaces` lists tool
  namespaces kept as direct model tools outside the code-mode surface.
- *source* (tag `rust-v0.156.1`, `core/src/config/mod.rs`
  `multi_agent_version_for_model`, `features/src/lib.rs`,
  `models-manager/models.json`), read 2026-10-01 — which multi-agent
  implementation a thread gets, in this order: the feature
  `multi_agent_v2` (default off) on gives V2; else `agents.enabled =
  false` gives none; else the model's own `multi_agent_version` in the
  model catalog; else the feature `multi_agent` (internal name `Collab`,
  default on) gives V1, and none when it is off. The bundled catalog
  declares `v2` for `gpt-6-astra`, `gpt-6-sol`, `gpt-6-luna`,
  `gpt-5.6-sol`, `gpt-5.6-terra` and the two `gpt-daybreak-*` models,
  `v1` for `gpt-5.6-luna` and `codex-auto-review`, and nothing for
  `gpt-5.5` and `gpt-5.4`. V1's tools (`handlers/multi_agents/`):
  `spawn_agent`, `send_input`, `wait`, `resume_agent`, `close_agent`;
  its `spawn_agent` and `resume_agent` refuse beyond `agents.max_depth`
  (default 1). V2's tools (`handlers/multi_agents_v2/`): `spawn_agent`,
  `send_message`, `followup_task`, `wait_agent`, `interrupt_agent`,
  `list_agents`; its `spawn_agent` computes the child's depth and checks
  no limit. Review threads switch both features off
  (`core/src/tasks/review.rs`). *measured* 2026-10-13 (0.156.1,
  `features.multi_agent_v2 = true`, `gpt-5.6-sol`): the interruption
  tool is `collaborationinterrupt_agent`, `tool_input` `{"target":
  "/root/<name>"}`, and a `PreToolUse` hook matching that name fires and
  can deny it; the model is V2 by the catalog, so the run does not
  separate the flag's effect.

## Both clients: confining the agents to the agent directory (2026-10-01)

Measured on Claude Code 2.1.286 (model haiku; auto mode with
`claude-sonnet-5-5`) and Codex 0.156.1 (model `gpt-5.6-sol`), 113 runs,
the main conversation and a subagent each, the working directory under
`/home` inside a git repository, under `/home` outside one, and under
`/tmp`; host Ubuntu 24.04.5, bubblewrap 0.9.0, socat 1.8.0.0. Full
reports and every run's evidence:
`ai-artifacts/probes/agent_directory/REPORT.md`, `REPORT2.md`, `runs/`.
The design they fix is CLIENT_HOOKS.md §5.

**Both.** Hook commands run outside the sandbox: `sh <wd>/.tat/hook.sh`
read `tat.lock` and reached the server while `<wd>` was hidden from the
agent's shell and the server's port unreachable from it (`curl` exit 7).
The client's MCP requests are made outside the sandbox. A subagent is
bound exactly as the main conversation is. Programs under `/home` are
not found by the agent's shell.

- *measured* 2026-10-13 (Claude Code 2.1.296, Codex 0.156.1, interactive
  under `isabelle TAT`) — besides TAT, each client started the MCP
  servers of the user's own configuration and account: Claude Code its
  claude.ai connectors (docs, Gmail), claude-in-chrome, debugmcp and
  isabelle-mcp (the last one launched in the agent's session,
  `~/.cache/claude-cli-nodejs/<project>/mcp-logs-isabelle-mcp/`); Codex
  `codex_apps`, `isabelle-lsp`, `isabelle-mcp`. Claude Code's
  `--strict-mcp-config` limits it to the project's `.mcp.json`; not
  measured under `isabelle TAT`.

**Claude Code.**

- The sandbox turns on from the project's `.claude/settings.json` under
  `-p` with no trust dialog, even when the user's own settings switch it
  off; `--settings '{"sandbox":{"enabled":false}}'` at launch switches it
  off. With `socat` missing and `failIfUnavailable`: exit 1, "sandbox
  required but unavailable …".
- On this host (`kernel.apparmor_restrict_unprivileged_userns = 1`, the
  profile `bwrap-userns-restrict`) every sandboxed command fails with
  `apply-seccomp: write /proc/self/setgroups (nested userns is
  capability-restricted …)` and `failIfUnavailable` does not catch it;
  `sandbox.network.allowAllUnixSockets: true` makes commands run. With
  it, `systemd-run --user --pipe --wait cat <wd>/TAT.sqlite` printed the
  hidden file through the D-Bus socket under `/run/user/<uid>`, and the
  libvirt socket answered; `/run` in `denyRead` closes both.
- `blockReadsOutsideWorkingDirectories` with the sandbox hides a working
  directory under `/home` and exposes one under `/tmp`; `denyRead` on the
  working directory hides it and leaves the launch directory inside it
  readable and writable; `allowRead: ["."]` changes nothing. `/tmp` is
  readable until it is in `denyRead`; `/tmp/claude-<uid>`, Claude Code's
  own temp directory, stays readable and writable.
- Under those settings: shell reads of the working directory, `..`, `~`
  answer "No such file or directory"; a `touch` outside lands in the
  sandbox's own filesystem, not on disk; the Read tool answers "… is
  outside <agent dir>; the permissions.blockReadsOutsideWorkingDirectories
  setting blocks reads outside the working directories."; a
  `dangerouslyDisableSandbox` call runs sandboxed under
  `allowUnsandboxedCommands: false`. This build has no Grep, Glob or
  MultiEdit tool.
- The block does not cover the file tools' writes: under
  `--dangerously-skip-permissions` Write wrote into the working
  directory. An `Edit(//<wd>/*)` deny rule blocks the launch directory
  too. In default `-p` mode Write is refused even inside the launch
  directory ("… but you haven't granted it yet.").
- A `PreToolUse` hook on `Write|Edit|NotebookEdit|MultiEdit` answering
  `permissionDecision` `allow` lets the write through in default,
  `acceptEdits`, bypass and auto mode, for the main conversation, a
  foreground and a background subagent, with no allow rule and no
  `defaultMode`; answering `deny` it holds in all of them, against
  `permissions.allow` rules and bypass mode. The hook receives
  `file_path` absolute, `~` expanded, `..` removed, symbolic links
  unresolved. The model sees `PreToolUse:<Tool> hook error: <reason>`,
  or `<reason>` alone for a path Claude Code had to rewrite.
- `.claude/settings.json`, `.claude/settings.local.json`, `.mcp.json`
  and `.claude/agents/x.md` in the launch directory, the hook allowing:
  refused by Claude Code itself in default and `acceptEdits` mode;
  written in bypass mode, and the change in force at once — after
  `sandbox.enabled` was set to false a shell command created a file in
  the working directory on disk; in auto mode the two settings writes
  are refused and the other two land. A sandboxed shell command cannot
  change them. Claude Code creates `.claude/.cc-writes/` by itself.
- A command with a subshell or several `cd`s is refused in default and
  `acceptEdits` mode ("Contains shell syntax (;) that cannot be
  statically analyzed"), sandboxed or not, whatever
  `autoAllowBashIfSandboxed` and the block are set to.
  `permissions.allow: ["Bash"]` in the project file makes it run,
  sandboxed, where the folder is trusted; under `-p` in an untrusted
  folder Claude Code ignores the project's allow rules ("Ignoring 1
  permissions.allow entry … this workspace has not been trusted") while
  it honours its hooks, sandbox settings and `env`; `--allowedTools
  Bash` works anywhere; bypass mode runs the command.
- Nothing TAT receives differs with the sandbox on or off: hook
  payloads, `initialize`, `tools/call` `_meta`.
- The `CLAUDE.md` of the launch directory's parent is in the context of
  the main conversation and of the subagent.

**Codex.**

- Under a profile with `":minimal" = "read"`, the workspace root
  writable, the network off and the working directory denied: shell
  reads of the working directory and `..` answer "Permission denied" or
  "No such file"; `touch <wd>/x` "Read-only file system"; `apply_patch`
  outside "patch rejected: writing outside of the project; rejected by
  user approval settings"; `systemd-run` "Failed to connect to bus:
  Operation not permitted"; the subshell command runs; hooks fire; the
  MCP tool works.
- `":slash_tmp" = "write"` mounts the host's `/tmp` read-write: an agent
  read a working directory under `/tmp` and wrote `/tmp/p_probe`.
  `":tmpdir"` had no visible effect. Without both, `/tmp` does not exist
  inside for a workspace under `/home`.
- `_meta["codex/sandbox-state-meta"]` arrives on every `tools/call` once
  the server declares `capabilities.experimental["codex/sandbox-state-meta"]`,
  identical for the main thread and the subagent: under the profile
  `permissionProfile.type` is `managed` with the profile's entries, the
  `deny` on the working directory among them; under `-s read-only` one
  entry, root read; under `-s workspace-write` root read and the
  workspace write; under `-s danger-full-access` and
  `--dangerously-bypass-approvals-and-sandbox` `{"type":"disabled"}`. In
  each of the four the hidden files were readable. Under the final files
  (REPORT5, `runs/x5_*/requests.jsonl`, 8 calls in 5 runs) the value is
  `managed` with the `deny` on the working directory, the resolver's read
  entry and the network enabled.
- Under the profile the parent's `AGENTS.md` is not loaded; with
  `-s danger-full-access` or `-s workspace-write`, inside a git
  repository, it is.
- `codex exec` outside a git repository exits 1, "Not inside a trusted
  directory and --skip-git-repo-check was not specified."
- Codex leaves empty `.git/` and `.agents/` directories in the launch
  directory after a sandboxed run.

Not measured: interactive sessions of either client; a host without the
AppArmor restriction; an escalation on Codex, which the model would not
request; whether a changed `.mcp.json` takes effect in a running Claude
Code session; Claude Code's `plan` and `dontAsk` modes.

### Later runs (2026-10-02): `REPORT3.md`, `REPORT4.md`, `REPORT5.md`

99 more runs in the same probe directory; Claude Code 2.1.286 for the
third, 2.1.287 for the fourth and fifth (the client updated itself),
Codex 0.156.1; default `-p` and bypass mode, the main conversation and a
subagent; a working directory under `/tmp`, in a scratch git repository,
and with a space in its path. The fifth run is the regression of the
files CLIENT_HOOKS.md §2, §3 and §5 give, and it passed in every cell.

**A script as the hooks' command, without TAT.** A Python script that
reads the hook's JSON and opens no connection, registered on
`PreToolUse` for `Write|Edit|NotebookEdit|MultiEdit`: its `allow` lets a
write inside the launch directory through and its `deny` holds, with
TAT's server stopped as with it running, in both modes, for both agents.
With its interpreter path wrong, in bypass mode, an outside write landed:
a hook that cannot start does not block. `hook.sh` exiting 1 (TAT gone)
does not block a Stop ("Failed with non-blocking status code"); TAT's own
tools are then refused in default `-p`, where only the announcement's
answer grants them.

**Quoting.** With every path in a hook command single-quoted, all hooks
fire from a directory with a space in its path, Claude Code's `denyRead`
entry and Codex's `deny` entry hide it, and the MCP entry works. Unquoted
on Claude Code, `sh` (dash) exits 2 on the missing path and every hooked
tool call is blocked; a Stop is not — Claude Code 2.1.286 reads a hook
that exits 2 with "cannot open" as a missing script and goes on.

**Worktrees (Claude Code).** With `permissions.deny: ["EnterWorktree"]`
the tool is absent from the init tool list. Without it, `EnterWorktree`
and a subagent launched with `isolation: "worktree"` make a worktree
under `<repository root>/.claude/worktrees/` on a new branch, in default
`-p` too, with no permission asked. The tool that launches a subagent is
`Task` in the init list and `Agent` in the hook's `tool_name`; its
`tool_input` carries `isolation: "worktree"` when the call asks for it,
and nothing when a subagent definition's frontmatter does. A `PreToolUse`
`deny` on such a call reaches the model as
`PreToolUse:Agent hook error: <reason>`, from the main conversation and
from a subagent launching a nested one. A `WorktreeCreate` hook that
prints nothing and exits 0 fails the creation with
`WorktreeCreate hook failed: hook succeeded but returned no worktree path (…)`;
one that prints a sentence on stderr and exits 1 fails it with
`WorktreeCreate hook failed: <the hook's command line>: <the sentence>`;
on stdout the sentence does not arrive. The repository is unchanged in
every refused case. Claude Code's sandbox creates an empty
`.git/config.worktree` and `.claude/.cc-writes/` in a git repository
that encloses the launch directory.

**Other MCP servers.** A `.mcp.json` in a directory above the launch
directory loads (source `project`), as `--mcp-config` does (source
`dynamic`), with no approval under `-p`; the account's connectors load
with source `claudeai`. Claude Code, default `-p`: another server's tool
is refused for want of a permission; its resources are read by
`ListMcpResourcesTool` and `ReadMcpResourceTool` with no prompt. Bypass:
both work. A `PreToolUse` hook receives `mcp_server: {name, source}` for
an MCP tool and only `tool_input.server` for a resource tool; of two
hooks on one call a `deny` wins over an `allow`. `allowedMcpServers` in
the project file is honoured in an untrusted folder and blocks the
connectors too. Codex: the hook's `tool_name` is `mcp__<server>__<tool>`
with no server or source field; the model makes its MCP calls from a
code-mode script, and `PreToolUse` fires for each; a tool without
`readOnlyHint` is refused under `approval_policy = never`
("MCP tool call requires approval"), its resources are readable; the
account's apps are tools of the built-in server `codex_apps`.

**The network, Claude Code.** Sandboxed commands reach the network
through a proxy whose socket is `/tmp/srt-mux-<pid>-0.sock`: with `/tmp`
in `denyRead` every outbound connection fails ("Proxy CONNECT aborted"),
and no project setting re-opens the socket. With `allowedDomains: ["*"]`
outside hosts are reached with no prompt, in an untrusted folder too.
`NO_PROXY` holds loopback and the private ranges, so a plain `curl` to a
local address goes direct into the sandbox's own network namespace and
fails; through the proxy (`--noproxy '' -x "$HTTP_PROXY"`) TAT's `/hook`,
a loopback listener and a listener on the host's LAN address are
reached. A name that resolves to loopback is refused by a check of the
proxy's own. A `deniedDomains` list refuses the listed addresses in
every spelling but cannot cover 127.0.0.2 … 127.255.255.254.

**The network, Codex.** `[permissions.<name>.network] enabled = true`
keeps the host's network namespace: local services are reached
directly. No outside name resolves, because `/etc/resolv.conf` is a
symbolic link into `/run`, which the profile's empty filesystem lacks; a
read entry for the link's real path
(`/run/systemd/resolve/stub-resolv.conf` here) makes `curl`, `git` and
Python reach outside hosts, the hidden files staying hidden; an entry
for the path `/etc/resolv.conf` itself makes bubblewrap fail every
command. `[features] network_proxy = true`, experimental and off by
default, reaches outside hosts and refuses every loopback and private
address.

Not measured: interactive sessions and auto mode in these runs;
`WebFetch` and `WebSearch` toward local addresses; a resolver layout
other than systemd-resolved; a background subagent with isolation;
`claude --worktree`.

## The other clients (*docs*)

Gemini CLI: `AfterAgent` with `decision: deny` retries a turn with the
reason as the prompt; `BeforeAgent` adds `additionalContext`; MCP
`headers` exist, environment expansion documented only for `env`. Cursor:
`stop` with `followup_message` submits a next user message;
`beforeSubmitPrompt` cannot add context; `headers` expand `${env:NAME}`.
OpenCode: a plugin's `client.session.prompt({path: {id}, body})` sends a
message into a session (`noReply: true` for context only); `headers`
expand `{env:VAR}`.

## Where the probes are

Scratchpad of session 57dbb3d3: `subagent_mcp_probe/` (`probe_server.py`,
`requests.jsonl`, `run_stdout.json`, `REPORT.md`); the Codex sources under
`codex_src/`. The scratchpad is temporary; this file is the record.
