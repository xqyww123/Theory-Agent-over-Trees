# Implementing the log and the agent directory

The design is in `docs/LOGGING.md` and `docs/CLIENT_HOOKS.md` §5, with the
sentences they tie to in MODULE_STRUCTURE §2.4–§2.6, §4.1, §4.3, §4.6 and
§5, CONSTRUCT_INTERACTION §1, §3.3 and §8, EXCEPTIONS §1 and §3,
RENDER_BASELINES §4, ARCHITECTURE §1 and §9, PLUGIN_SYSTEM §2. This plan
adds only the order of the work and what each step is tested with. The
owner's decisions are in LOGGING_DECISIONS.md; the reviews' rulings in
review/LOGGING_AGENT_DIRECTORY_RULING.md, `_2.md` and
review/LOGGING_IMPLEMENTATION_PLAN_RULING.md (whose corrections K2–K13
this revision carries).

Nothing here is implemented. No step runs `isabelle build`; the ML side is
exercised through the test harness, which drives a real `isabelle
TAT_mcp`, and the launcher is rebuilt with `isabelle scala_build` (the
owner's standing exception) after steps 8 and 12.

**Division of work** (agreed with the jobs session [682d5e], 2026-10-03,
its DOC_SYNC_LIST.md entry 16): that session builds the client machinery
of CONSTRUCT_INTERACTION §4, §7, §8 — `-c` from `TAT_mcp` through
`TAT.boot`, `TAT.start` and `start` to `launch_TAT`; the two `TAT_Server`
subclasses, each naming the `clientInfo.name` it expects (`claude-code`,
`codex-mcp-client`); `POST /hook` in place of `/on-compaction` and the
`CLIENTS` table; `agent_of_call`, `event_of_hook`; the `Agent` objects,
mailboxes and seen sets; the stop and interruption rules; the
`clientInfo` check; retiring `TAT_new`'s old hook files and their tests;
step 7's `fork_job` work, which this session reviews; `ClientRefused`
with its `line`, `stopped()`'s branch for it and the one refusing method
that writes `client_refused` — on the ending object and
`conversation.log` of Batch 1. The order (2026-10-03): step 9 now; step
10 after that session's step 1 (`-c`, the two subclasses, the
`configure` call point); step 11 after its step 2 (the announcement,
`agent_of_call`, `ClientRefused`); step 13 is one live run with its
smoke run.

*(author)* The `Log`'s shape: `Log(directory, logger)`; one attribute
per category, one typed method per event, mirroring the files —
`log.tool.call(tool, arguments)`, `log.job.message_posted(...)`,
`log.conversation.start(...)` — each category with `note(message,
**fields)`; `current_agent` and `current_call` are `ContextVar`s in
`log.py`. The `job` events are written by the jobs session's code.

## Batch 1 — the log, Python side

1. **`log.py`.** `Log(directory, logger)`, `logger` the RPC host's
   (`connection.server.logger`): the methods above, their parameters the
   event's fields of LOGGING §4; `ts`, `agent`, `call` stamped from the
   two context variables; the line encoded as LOGGING §5 says
   (`ensure_ascii=False`, surrogates escaped, an `IsaTerm` as its
   `.unicode`, any other value JSON cannot hold as its `str`) and appended
   with `open(path, "ab")`; encoding and writing under one `try`, whose
   failure is reported once to the logger with LOGGING §5's sentence and
   never raised; `warning` and `error` records mirrored to the logger.
   *Test:* `test_log.py`, a temporary directory: every method writes one
   parsable line into its category's file with the stamped fields; a
   `note` lands in the named category; a lone surrogate round-trips; a
   record holding an `IsaTerm` is written as `.unicode`; a record holding
   an object whose `str` raises is reported once and raises nothing; a
   file made read-only makes the first failure report once and later ones
   silent.
2. **Start order and the ending object** (MODULE_STRUCTURE §4.6, LOGGING
   §2). `toplevel.conversation()` in the three layers: the lock; the log
   directory — `os.makedirs(<wd>/.tat/log, exist_ok=True)`, then the leaf
   named by its creation moment to the microsecond made with `os.mkdir`,
   either failure the `TAT_StartupError` of LOGGING §2 — and the `Log`;
   the ending object, a context given the `Log`, entered right after it,
   holding what `TAT_Server` keeps today (the ending future, `end`,
   `spawn`, the bodies) so that `TAT_Server` is given it and keeps no
   ending state of its own; its exit calls `end` for an escaping exception
   and writes `ended` once the ending was entered; the `Forest` handed to
   it when built; `Conversation` gains `log` and the ending object. The
   `start` record is written without the client's name until `-c`
   reaches `launch_TAT`. `TAT.log_directory` is NOT called here yet: it
   lands with its ML half in step 8.
   *Test:* the harness (`test/harness.py`, `test_launcher.py`,
   `test_conversation.py`, `test_mcp_server.py`, which build `TAT_Server`
   and call `server.end`) adjusted to the ending object; test_toplevel's
   `Recorder` gains `server.logger`; the records `start`, `store_opened`,
   `plugins_loaded`, `ending`, `ended` appear in that order; a
   `TAT_StartupError` at the store writes `ending` and `ended` (the
   duration alone); a conversation ended by the connection going writes `ending`
   at level `info`; a fresh working directory starts.
3. **`isabelle_driver`** (MODULE_STRUCTURE §4.3). The private function of
   a connection; `call(conversation, name, args)` = that function plus the
   record, written from the trip's done-callback where `_dropped` runs
   today, so it is written whether or not the caller still waits —
   `round_trip`, with the result or the error, the connection error
   included; `reset` on a bare connection;
   `Isar_State_Slot` holds the `Conversation`. Every caller updated.
   *Test:* `test_isabelle_driver.py`: a round trip writes one
   `round_trip` record with the duration, an error one with the error;
   `test_a_cancelled_caller_unwinds_while_the_round_trip_completes`
   asserts the record once the trip completes.
4. **The funnels this session owns.** The tool boundary (`tool`
   `call`/`result`/`given_up`/`while_ending`; the two context variables
   are the jobs session's to set, in its `TAT_Server` subclasses:
   `current_call` from the call's own `_meta`, each client's key, at the
   top of the handler, and `current_agent` from `agent_of_call`, before
   `tool.call` is written — not reset in the body's `finally`, which
   would strip `result` and `given_up`),
   the status setters (`operation`, with the duration argument and the
   status's messages), `Forest_Store.transaction` (`store`), the edit's
   commit block (`edit` `committed`), the walk (`evaluation`
   `walk_started`/`stopped`/`walk_ended`). `unannounced`, the `hook`
   events and the `agent` events are written by the jobs session's `/hook`
   and `agent_of_call`.
   *Test:* each existing test module gains one assertion that the records
   its scenario produces are present and well-formed; `test_forest_walk.py`
   checks `operation` records for a run, a blocked write and an
   invalidation (messages present, absent, absent); `test_mcp_server.py`
   asserts `ending` before `while_ending`.

## Batch 2 — the Isabelle side and the launcher

5. **The Isabelle-side log.** The never-raising writer factored out of
   `Event_Log.append_string` (`contrib/Performant_Isabelle_ML/library/event_log.ML`)
   into a function both call; TAT's JSON string function; one cell for the
   whole process holding the current log, an empty in-memory log when
   `TAT_Framework.ML` loads, so the loader's `theory_loaded` records (one
   per theory new in `Thy_Info` after a load) have a log at `TAT.start`;
   `TAT.reset` writes `reset` into the old log and installs a fresh one.
   (`fork_job` capturing the current log at the fork: step 7.)
6. **`register_callback`** takes the callback record (MODULE_STRUCTURE
   §2.5); the framework's wrapper around `function` (`callback`, `bug`);
   `mk_callback` called by the framework; the framework's own callbacks
   through the same path; `bug_message : exn -> string option` in
   `TAT_Framework` — the first `Bug` found bare, in a `Par_Exn` or in an
   `Exn.EXCEPTIONS`, a `Bug` winning over an interrupt — used by the
   wrapper, by `operation` (whose `escapes` becomes `is_some (bug_message
   e) orelse Exn.is_interrupt e`, local to it) and by `fork_job`;
   `TAT_Common_Nodes` and the test plugin `Test_TAT_Framework.thy` drop
   `mk_callback`.
7. **`fork_job`** — the jobs session's whole: the report carries `failure`
   on the wire as `["ok"]`, `["messages", [...]]` or `["bug", <message>]`
   (MODULE_STRUCTURE §2.4); the Python `job_finished` raises
   `TAT_InternalError` on `["bug", …]` before the process-wide job lookup
   (CONSTRUCT_INTERACTION §3.3); `job_forked`, `job_ended`,
   `report_undelivered` records into the log captured at the fork. This
   session's step: the review of that code against LOGGING §4.
8. **`TAT.log_directory`**: the callback stores the directory's absolute
   path and sends the protocol message of the same name; `toplevel`'s
   layer 1 calls it through `isabelle_driver.call` right after the
   `Conversation` (both procedures); `tat.scala` gains the handler beside
   `TAT.finished`, prints `Log: <path>`, follows the directory's files for
   `warning` records, skipping a line that is not JSON, until whichever
   ending comes first, draining the old directory before it moves to a new
   one; `TAT_compile` the same (COMPILATION §5). Then `isabelle
   scala_build` for `lib/tat.jar`.
   *Test (5, 6, 8):* `Test_TAT_Framework.thy` through the harness: a
   conversation's `isabelle.jsonl` holds `callback` records for every
   callback it ran and a `theory_loaded` for `TAT_Lib_Helper` when it is
   loaded from source; the test plugin's callback raising a `Bug` yields
   the `bug` record together with the `round_trip` error record on the
   Python side; one case makes `isabelle.jsonl` unwritable and the probes
   still answer; `Event_Log_Test.thy` re-run in the REPL after the
   factoring; an Isabelle-backed launcher case appends a `warning` record
   to a file of the conversation's log directory itself — no Python-side
   event is a `warning`; the Isabelle side's `report_undelivered` is the
   only one — and polls the harness child's output for the `Log:` line
   and the `### …` line.

## Batch 3 — `configure`, `hook.py`, `guard.py`

Step 10 waits for the jobs session's `TAT_Server` subclasses (its step
1), step 11 for its `ClientRefused` and refusing method (its step 2).

9. **The scripts** `hook.py` and `guard.py` in the package, copied into
   `.tat/` by `configure`; `guard.py` from
   `ai-artifacts/probes/agent_directory/tat_guard5.py` with the probe-only
   parts removed, the agent directory found beside the script, and the
   failure answers hook by hook (CLIENT_HOOKS §5) — the handler keeps the
   tool as well as the event; `hook.py` as CLIENT_HOOKS §1 describes.
   *Test:* the scripts run on piped payloads, no client: the write
   `allow`/`deny` cases, the `Agent` launch with and without isolation,
   `WorktreeCreate`, a payload with `"tool_input": [1]` for each of the
   three (a Write: the write deny; an `Agent` launch: empty stdout, exit
   1; `WorktreeCreate`: the sentence, exit 1), a payload that is not
   JSON (the write deny); `hook.py` against a stub server (200 → the body;
   503, 500 → exit 1 and the sentence) and against no server (exit 1, the
   sentence).
10. **`configure`** per client: the agent directory made when absent;
    the files of CLIENT_HOOKS §2 and §3 written through `json.dumps` and
    the TOML string function (TOML 1.0 escapes, `\uXXXX` for control
    characters and DEL); the hook commands built by one base-class
    function with `shlex.quote`; the Codex subclass's resolver entry from
    `os.path.realpath("/etc/resolv.conf")` when outside the `:minimal`
    directories; `configure` overwrites the two scripts and touches
    nothing else in `.tat/`.
    *Test:* `test_mcp_server.py`: the written files parse (`json`,
    `tomllib`) and, compared token by token with `shlex.split`, equal the
    documented ones with the placeholders substituted, for an interpreter
    path with a space and a `'` in it (a working directory cannot hold
    `'`); the TOML with and without the resolver line; the resolver rule
    on a fake layout; the `configured` record.
11. **The Codex sandbox check** (CLIENT_HOOKS §5, CONSTRUCT_INTERACTION
    §8, RENDER_BASELINES §4): the capability declared in `initialize`; a
    call whose `_meta` lacks `codex/sandbox-state-meta` or whose policy is
    not the profile's — recognised by its `deny` entry on the working
    directory — refuses the session through the jobs session's one
    refusing method, with the fifth line (`ClientRefused`, `stopped()`'s
    branch and the `client_refused` record are that session's).
    *Test:* `test_mcp_server.py`: such a call ends the conversation, the
    `client_refused` record carries its `_meta`, and every call in flight
    is answered the fifth line.
12. **`TAT_new` and `TAT_mcp`** refuse a path with `[` or `]` (Scala),
    then `isabelle scala_build`.
    *Test:* `test_launcher.py`: the refusal's sentence and exit code.
13. **One live run** of each client against a real `isabelle TAT_mcp`,
    repeating the regression of REPORT5 §D.4 with the shipped files — the
    one measurement left for the end, since everything before it was
    measured with the probe's stand-ins.

## Open at implementation

- Whether a configured `WorktreeCreate` hook makes Claude Code advise
  agents to use worktree isolation (RULING_2 D16): check on the live run.
- The exact names of the project-level files and the interactive
  session's reading of the `env` entries (CLIENT_HOOKS §4).
