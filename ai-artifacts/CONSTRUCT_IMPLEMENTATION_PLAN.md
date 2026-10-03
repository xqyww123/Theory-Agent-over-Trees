> **Obsolete (2026-10-03).** Withdrawn by the owner before any step began:
> the compilation system and the logging system are implemented first,
> by their sessions; this session's implementation comes after, from a
> plan rewritten then. This text is kept only for what it lists; its
> check, ai-artifacts/review/IMPLEMENTATION_PLAN_REVIEW.md, found 19
> rules it did not cover, 15 wrong citations and several overlaps with
> ai-artifacts/LOGGING_IMPLEMENTATION_PLAN.md, and the rewrite starts
> from that check, not from this text.

# Implementation plan: jobs, agents, hooks, the construct tools and `Theorem` (2026-10-02)

The order the owner chose (2026-10-02): the framework first, AoA after —
everything that does not depend on how AoA is driven is built and tested
now; `Proof_Job._run` and what it needs from AoA wait for the AoA round
(CONSTRUCT_INTERACTION §10). This plan names, for each step, what is built,
the sections that specify it, the files, the tests and the exit check. It
repeats nothing of the documents: where a section is cited, the section is
the specification. The record of the decisions is CONSTRUCT_DECISIONS.md;
what is still open is OPEN_QUESTIONS.md and DOC_SYNC_LIST.md's last entries.

Conventions, as in FIRST_END_TO_END_RUN_PLAN.md and STEP5_HANDOFF.md:
every agent-facing sentence is read from the documents by the baseline
tests (`test/baselines.py`: `fenced_lines`, `fenced_blocks`), never typed
into a test; the design documents change only through the owner; a step
is done when its tests pass under `test/harness.py`'s one `isabelle
TAT_mcp` per run; no `isabelle build`; commits on `main` on the owner's
word only.

## 0. What exists and what does not

Exists (committed through step 5 and the compilation session's work):
`model.py`'s forest, nodes, walk and statuses; `edit.py`; `store.py`;
`plugin.py`; `mcp_server.py`'s tool boundary with the shielded body and
the checkpoint; `mcp.py`'s `edit`, `move`, `delete`, `recall`;
`toplevel.py`'s `launch_TAT`; `ML/TAT_Framework.ML` (`begin_theory`,
`end_theory`, the loader, `run_commands` marked DO NOT USE);
`ML/TAT_Common_Nodes.ML`; `src/scala/tat.scala`.

Does not exist: `jobs.py` (no `Agent`, mailbox, seen set, job classes),
the `/hook` endpoint and the server subclasses, `agent_of_call`, the
version check, compaction detection, the four construct tools and
`evaluate_to`'s `checks`, `edit`'s `auto_construct`, `fork_job` /
`job_finished` / `TAT.job_cancel` on the ML side, `theorem_node.py` (empty),
`builtins.py` (empty).

Owned elsewhere, and prerequisites here: the compilation session's code
for the stored statuses, `check_outcome()`, `Ready` / `CannotEvaluate`,
`_unfinished()`, the invalidation recursion and the compile tool
(COMPILATION.md §4–§6; frozen until its review passes); the logging
session's log, `ClientRefused` and `hook.py` (LOGGING.md); the rename to
`isabelle TAT_mcp` (done). Step 1 cannot start before the first lands.

## 1. The framework's jobs and agents — `jobs.py`, `model.py`

Build: `Agent` (seen set, mailbox, working-call count — CONSTRUCT_INTERACTION
§4, §6, PRINT.md §4); messages, notifications, `Interactive_Question`,
`Answered` (§3.4); `Construction_Job` with every member of §3.2's table,
`auto_construct` included, and the run's wrapper (§3.2 "The run": the
log's `agent` first, the settlement, the attach made from inside `_run`);
`Evaluation_Job` with §3.3's table, the id from a process counter, the
process's id→job table, the job holding its `Conversation` (§3.3 "The
report"); `Unfinished`, `Unfinished_Construction`, `Unfinished_Check`,
`Unchecked` and `_unfinished()` through `check_outcome()` (§3.1); on
`Node`: `construction_job_class`, `evaluation_job_class`, `job()`,
`attach_evaluation_job`, `carry_job_from(old)` and the commit's honouring
of it, the running and dropping rules (§3.3 "Running and dropping"); the
status setter's drop and `_on_context_change` call (§3.2, MODULE_STRUCTURE
§4.1); the three reserved rows `job`, `check` and the automatic
construction setting with their missing-row rules (ARCHITECTURE §4.1,
FIRST_END_TO_END_RUN_PLAN §2) and each job step's own store transaction
(§3.1–§3.3, EXCEPTIONS §1).

Files: new `isabelle_theory_agent/jobs.py`; `model.py` (`Node`, the
setters, `Conversation`); `store.py` (the rows); `edit.py` (the carry; the
cancel and drop in the completed events, `cancel(ids)` after the block —
MODULE_STRUCTURE §4.2 steps 3–4).

Tests: `test/test_jobs.py` with test job classes (the harness's way of
testing the framework without `Theorem`): start / settle / cancel / the
question round trip / `_on_context_change` on a rerun / drop on
invalidation and on delete and amend / the carry on an amend / the stored
rows across a reload / `_unfinished()`'s table. `test/invariants.py` gains
"a job's outcome on the node equals the stored row once settled".

Exit: the §3.1–§3.4 tables pass as written; no `TAT_Error` escapes a
settlement (EXCEPTIONS §1).

## 2. The walk starting jobs, and automatic construction — `model.py`

Build: `Evaluation`'s `starter`, `checks`, `passed`, `dropped`, `stored`
(MODULE_STRUCTURE §4.1 listing); `start_evaluation_job()` at a passed
node's last operation (CONSTRUCT_INTERACTION §3.3 "Where a job starts");
automatic construction at a passed node and on a `FAILED` report (§3.3
"Automatic construction"); `blocking` (§5 under `check_construct`);
`cancel(ids)` at the walk's flush.

Tests: in `test/test_forest_walk.py` and `test/test_jobs.py`: a check
started only when `_unfinished()` would answer `Unchecked`; `checks:
"no"` starting none; automatic construction at a `ready` node, not at a
failed-and-unchanged node, again after an invalidation; the owner of an
automatic run; `blocking` returning after the passed nodes' jobs end.

Exit: ARCHITECTURE §3.6's and CONSTRUCT_INTERACTION §3.3's rules hold.

## 3. The ML side — `ML/TAT_Framework.ML`, `ML/TAT_Common_Nodes.ML`

Build: `fork_job` (the Future task, the table under the job's id, the
report with interrupts deferred — MODULE_STRUCTURE §2.4), `TAT.job_cancel`
and the remote procedure `job_finished(id, errors)` (§2.6, declared with no
timeout through Isabelle_RPC's registry), `TAT.reset` cancelling the
futures first; `Theory`'s `end` as an ML-built `Toplevel.exit` transition
and the removal of `run_commands` with its two ML tests rewritten
(EVALUATOR_DESIGN §1, MODULE_STRUCTURE §2.4; CONSTRUCT_DECISIONS §11).

Tests: `test/Test_TAT_Framework.thy` (the two rewritten tests; a forked
job reporting; a cancel); `test/test_isabelle_driver.py` for the report
reaching the process table. Verify at this step, not assume: that a job's
work enters no execution table (EVALUATOR_DESIGN §6's fourth condition).

Exit: a report after `TAT.reset` or for a dropped id is ignored; a load
during a job neither waits for nor cancels it.

## 4. The server, the clients and the hooks — `mcp_server.py`, new `clients.py`

Build: `TAT_Server`'s subclasses `claude-code` and `codex`
(CONSTRUCT_INTERACTION §8; MODULE_STRUCTURE §4.6): `configure` writing
CLIENT_HOOKS §2 / §3's files whole (the hook script is the logging
session's `hook.py` — LOGGING.md; coordinate before writing), the `/hook`
endpoint and `event_of_hook` (CLIENT_HOOKS §1's table: the announcement's
grant, the stop's block, the interruption's refusal, Codex's compaction
hooks, the empty answers), `agent_of_call` pairing calls with
announcements (`tool_use_id` / `_meta.callId`; `_meta.threadId` on
Codex), the working-call count in a `try/finally` (§4), the version check
at the first request of a session from `initialize`'s `clientInfo` and the
`ClientRefused` doors (§8; EXCEPTIONS §1, §3; RENDER_BASELINES §4's lines);
compaction detection on Claude Code from the agent's transcript — the
file, the `compact_boundary` entries recorded by `uuid`, the path change,
the refusal (CLIENT_HOOKS §2, PRINT.md §4) — and on Codex from
`PreCompact` / `PostCompact` by `agent_id` (CLIENT_HOOKS §3); the stop rule
and the global interruption rule (§7); the mailbox taken after the
checkpoint (§3.4; MODULE_STRUCTURE §4.6); the ending's doors and what it
cancels, drops and answers (§9; RENDER_BASELINES §4). Not built: the
checks that report a broken premise and the log's reaction — deferred by
the owner to the logging session (CONSTRUCT_DECISIONS §10).

Tests: `test/test_mcp_server.py` and a new `test/test_hooks.py` driving
`/hook` with recorded payloads from `ai-artifacts/probes/*/` (announce →
call → result; a call without an announcement ends the conversation; the
stop rule's cases; the interruption rule; a compaction boundary appended
to a transcript file clears that agent's set and no other; a `/clear`'s
path change; a missing transcript → `ClientRefused` and the fourth ending
line; the version refusal). Live, against the real clients, only the
smoke run of step 8.

Exit: CONSTRUCT_INTERACTION §7–§9 hold against recorded payloads;
AGENT_CLIENTS_MEASURED.md's facts the tests rely on are cited in the tests.

## 5. The tools — `mcp.py`, `isabelle_theory_agent/tools/*.jsonc`

Build: `construct`, `cancel_construct`, `check_construct`, `answer`
(TOOL_SCHEMAS §5; CONSTRUCT_INTERACTION §5: the node sets, the skipping,
the one refusal, the `Started …` / `Cancelled …` forms, `check_construct`'s
conditions and state lines, `answer`'s two-phase check and its two
refusals), `evaluate_to`'s `checks` and its opening lines (TOOL_SCHEMAS §4,
§5; RENDER_BASELINES §6), `edit`'s `auto_construct` (TOOL_SCHEMAS §1),
`recall`'s no-id branch and its two descriptions (RECALL.md §2–§3),
`readOnlyHint` on `recall` and `check_construct` (MCP_SPECIFICATION §5),
the descriptions completed at start from the loaded titles (TOOL_SCHEMAS
§5; MODULE_STRUCTURE §4.6), the result's composition — body, messages,
the `Started …` line, the background line, the trailer (§5 "Every tool
result"); the four new `.jsonc` files and `edit.jsonc`'s new argument; the
tools exist only when a loaded class names the job class.

Tests: `test/test_mcp.py` and `test/test_descriptions.py` pinning every
description and line to the documents; the `it takes …` baseline line
with `auto_construct`; `test/test_conversation.py`'s result shapes.

Exit: every sentence of CONSTRUCT_INTERACTION §5–§6 and RENDER_BASELINES
§2, §4–§6 that the tools render is produced by the code verbatim.

## 6. Rendering — `model.py`'s `print`, `mark`, the blocks

Build: the framework's tags, in order (CONSTRUCT_INTERACTION §6; PRINT.md
§1; RENDER_BASELINES §5); the failure blocks from the construction job's
outcome and `check_outcome()`, the colon-to-period rule for an empty
message (§6; PRINT.md §2); the notifications' forms, merged where the
documents merge them (§3.4, §6); the summary under a cut-off nesting node
grouped by the `Unfinished`'s title (PRINT.md §2); `Sessions:` as a header
(PRINT.md §6); rendering for an agent — `Forest.render(node, mode, agent)`
and the seen set's keys (PRINT.md §4; §6).

Tests: `test/test_print.py` against PRINT.md §6–§7's and RENDER_BASELINES
§5's blocks (the §5 unpacking adjusted to the blocks the section now has —
DOC_SYNC_LIST "Tests"); `test/test_session_theory.py` unchanged in intent.

Exit: PRINT.md's examples render byte for byte.

## 7. `Theorem` without its jobs — `theorem_node.py`, `ML/TAT_Common_Nodes.ML`

Build: the class as THEOREM.md §1–§6 and §8 specify it — fields, the
construct schema with `STATEMENT_DEFS` and `IsaTerm` (moved to
`Isabelle_RPC_Host.unicode` from AoA; DOC_SYNC_LIST "Outside this
repository"), `gen` with its checks and the carry, the evaluation callback
`TAT.Theorem.evaluate` building one transition (§6), `reserved_names`,
emission with `sorry` (the `by aoa` case needs a stored `PASSED`, which no
run can produce yet), the marks and `print_fields`, the fact-name grammar.
`construction_job_class` and `evaluation_job_class` stay `None` until step
9 (the owner, 2026-10-02): the construct tools and `checks` then do not
exist for `Theorem`, its proofs are written `sorry`, and `_unfinished()`
answers `None` (CONSTRUCT_INTERACTION §3.1).

Tests: `test/test_theorem.py`: the schema and descriptions from THEOREM.md
§2–§3; `gen`'s refusals from RENDER_BASELINES §2; evaluation of a valid and
an invalid statement against the live Isabelle through the harness; the
emitted text of THEOREM.md §5; the marks of §7 reachable without jobs.

Exit: a theory with definitions and theorems evaluates, prints and
compiles to a `.thy` whose theorems end in `sorry`.

## 8. The smoke run

One session against the real Claude Code and the real Codex, in the
measured versions (CONSTRUCT_INTERACTION §1): the agent adds a theory and
theorems through the tools, evaluates, compacts (forced as the probes
force it), is stopped and interrupted, and leaves; the transcript of the
run is kept under `ai-artifacts/probes/smoke_<date>/` (never committed —
CONSTRUCT_DECISIONS §12's rule). The measurements DOC_SYNC_LIST marks "at
implementation" are taken here: the interactive session reading the two
transcript `env` entries from the project settings; `server/discover`
before `initialize`; the hooks' file names.

Exit: the run's hook log shows every rule of §7–§8 firing as specified.

## 9. The AoA round — after the plan

What it decides is CONSTRUCT_INTERACTION §10 and OPEN_QUESTIONS §2. What
it then adds here: `Proof_Job` (`_run`, the questions, the budget, the
bound on concurrent runs), `Proof_Check` through the function AoA exports
for replaying one record and `TAT.Theorem.check` (THEOREM.md §7), the
times handed over with the proof, `by aoa` emission from a stored
`PASSED`, and the `aoa` proof method's import. Only then does `Theorem`
name its two job classes.

## Open before step 1 starts

1. The hook script: the logging session's `hook.py` replaces CLIENT_HOOKS
   §1's `curl` script; step 4 writes what LOGGING.md and CLIENT_HOOKS
   agree on, and asks before writing if they differ.
2. The compilation session's code must be unfrozen and merged on `main`
   before step 1 (its `model.py` changes are the base of steps 1–2).
