# Implementation plan: agents, hooks, jobs, the construct tools and `Theorem`

Written 2026-10-03, revised on 2026-10-04 after four readers' checks
(review/IMPLEMENTATION_PLAN_REVIEW_2.md). Steps 1 to 14 are committed since
2026-10-07, with the reviews of steps 1–2, 4–5, 6–7, 8–9 and 10–11
applied (review/DOC_SYNC_LIST.md entries 32–55; the second compaction
check rebuilt on 2026-10-06 on the owner's rulings; the detail questions
of the reviews of steps 8–9 and 10–11 verified and applied on 2026-10-08,
entry 54; the design questions they leave to the owner are
review/STEPS_8_9_REVIEW.md §4's R7, R9, R14 and
review/STEPS_10_11_REVIEW.md §4's R15, R16, plus R21 and whether a bug
raised once the ending is entered should be recorded); steps 15 to 17
are not implemented.
The design is in the documents under `docs/`; this plan gives only the
order of the work, what each step needs before it starts, the files it
touches, what it is tested with and when it is done. Where a section is
cited, the section is the specification, and the plan repeats none of
it. The record of the decisions is `CONSTRUCT_DECISIONS.md`.

Short names: **CI** = docs/CONSTRUCT_INTERACTION.md, **MS** =
docs/MODULE_STRUCTURE.md, **CH** = docs/CLIENT_HOOKS.md, **RB** =
docs/RENDER_BASELINES.md, **TS** = docs/TOOL_SCHEMAS.md, **TH** =
docs/node_classes/THEOREM.md, **ST** =
docs/node_classes/SESSION_AND_THEORY.md, **LIP** =
ai-artifacts/LOGGING_IMPLEMENTATION_PLAN.md, **LD** =
ai-artifacts/LOGGING_DECISIONS.md, **CP** =
ai-artifacts/COMPILATION_IMPLEMENTATION_PLAN.md, **DSL** =
ai-artifacts/review/DOC_SYNC_LIST.md. CP has two phases, and the names
are its own: Phase A, its steps A1 to A8, rewrites the walk, the
setters, the edit's commit and the store; Phase B, its steps B1 to B8,
is compilation itself.

Conventions. Every agent-facing sentence is read from the documents by
the baseline tests (`test/baselines.py`), never typed into a test. A
design document changes only through the owner; §5 lists the
corrections this plan makes to them. A step is done when the tests it
names pass, the suite has no failure that §2 does not list as waiting
for a later step, and `pyright isabelle_theory_agent` is clean. No
`isabelle build`; `lib/tat.jar` is rebuilt with `isabelle scala_build`
after a change to `tat.scala`. Commits are on `main`, on the owner's
word. A sentence marked *(author)* is a shape this plan chooses where
the documents leave one open.

## 1. What the steps stand on

| what | whose | state on 2026-10-04 |
| --- | --- | --- |
| the log, the ending object, `isabelle_driver.call`, the tool boundary's records, the Isabelle side's log, `register_callback` taking the callback record (LIP steps 1–6, 8) | the logging session | in, committed (bd48a93, 2e8f6e7, d9472b3, df271ca) |
| Phase A: the walk, the setters with `_slots_written_by`, the edit's commit block, the store's rows, `IsaTerm` in `Isabelle_RPC_Host.unicode` (CP §3) | the compilation session | approved to start; nothing in the tree |
| Phase B: `compile.py`, `Node.can_emit` and `emit`, the compile hooks' framework side, `isabelle TAT_compile`, the `Session`'s folder made before a theory begins (CP §4) | the compilation session | after Phase A |
| `hook.py`, `guard.py` (LIP step 9); `configure` (LIP step 10); the Codex sandbox check (LIP step 11); the launcher refusing a path with `[` or `]` (LIP step 12) | the logging session | steps 9 and 12 in, committed (ba5f999) — step 12 in `tat.scala`, `lib/tat.jar` and `test_launcher.py`, which steps 1 and 4 here edit on top of it; step 10 waits for step 1 here, step 11 for step 2 |

**Every step after Phase B.** Two sessions never edit one file at the
same time. Phase A, committed on 2026-10-04 (dfefca1), rewrote
`model.py`, `edit.py`, `store.py`, `plugin.py`, `isabelle_driver.py`
and `mcp.py`; Phase B edits `model.py`, `plugin.py`, `toplevel.py`,
`exceptions.py`, the two ML files, `ML/TAT_Boot.ML`, `tat.scala`, the
jar, `test/harness.py` and the test plugin's theory (CP §2). Steps 1 to
3 were to run beside Phase A and be in before Phase B's ML and Scala
steps; the owner had not allowed their start when the compilation
session reached those steps, so it took the files, and Phase B was
committed first (ee9e4f5). The owner allowed the start on 2026-10-05,
and steps 1 and 2 are in. Steps 1 and 3 build on what its B1, B2 and B7 leave
in `TAT.start`'s path and in `TAT_Common_Nodes`. Of this plan, steps 4 to 13 need
nothing of Phase B but its files; step 15 needs its folder (B5), and
step 16 its emission contract, `compile.py` and the hooks (B3, B4, B6).

**What Phase A leaves to this plan** (CP §2): `Evaluation`'s `starter`
and `dropped`; in the setters, the stored check's clearing,
`_on_context_change` and the evaluation job's drop; `cancel(ids)` at
each flush; `Node.evaluate_to`'s `agent` and `checks`;
`check_outcome()` and `_unfinished()`; the jobs' reserved rows;
`Conversation.forget` over the agents' sets, which that code writes
over the one set the conversation holds today; the test of an
`_on_context_change` that raises under an edit.

**The division with the logging session** (LD, its entries of
2026-10-03): this plan builds the client machinery of CI §4, §7 and §8
and `fork_job` with its records whole; the logging session builds
`configure`, the two scripts and the sandbox check, and reviews step 6
against LOGGING.md §4 (LIP step 7). `ClientRefused` and the branch of
`stopped()` that answers a refusal's own line are built in step 2; the
sandbox check and its line are added on the same class by LIP step 11.
The order agreed with that session: step 1 here, LIP steps 9 and 10,
step 2 here, LIP step 11.

**A real client between the steps.** In the agreed order two intervals
serve a real client wrongly, and in both the suite is TAT's only
correct client. Between LIP step 10 and step 2 the hooks post to a
path TAT does not have yet, the script fails, and under `-p` Claude
Code refuses every TAT call (CH §1). Between step 2 and step 5 the
calls are served, but the client, started in the agent directory, no
longer reads the old hook files: its compaction clears no seen set, and
an agent may miss a message it was shown before. No
shipped node class names a job class
before step 15, so until then no real agent owns a job, and the stop
hook's empty answer before step 11 holds nobody wrongly.

## 2. The tests that fail today

Measured on 2026-10-03: of the cases that need no Isabelle, 307 pass
and 18 fail, each because a document is ahead of the code. Measured
again on 2026-10-05 with step 1 in, the whole suite: 399 pass and 17
fail — the 18 less `test_the_field_checks`, which Phase B's B2 made
pass; with step 2 in, 418 pass and the same 17 fail; with step 4 in, 434
pass and 13 fail; with step 5 in, 441 pass and the same 13 fail; with
step 6 in, 446 pass and the same 13 fail; with the first fixes of
the review of steps 4 and 5, 453 pass and the same 13 fail; with step 7
in, 457 pass and the same 13 fail; with the fixes of the review of steps
6 and 7, 466 pass and the same 13 fail; with step 8 in, 491 pass and 8
fail; with step 9 in, 498 pass and the same 8 fail; with the fixes of
the review of steps 8 and 9, 522 pass and the same 8 fail; with step 10
in, 526 pass and 5 fail; with step 11 in, 541 pass and 2 fail; with
step 12 in, 548 pass and the same 2 fail; with the fixes of the review
of steps 10 and 11, 558 pass and the same 2 fail; with step 13 in, 560
pass and 1 fails; with step 14's Python half in, 572 pass and none
fails.

With step 14's Python half in, no case waits for a later step: every
baseline of RENDER_BASELINES §1–§2 and every description of the shipped
classes is covered.

## 3. The steps

### Steps 1 to 3: need only what is in

### Step 1. `-c`: the client's name from the command line to the server

Needs: what is in.

Build. `TAT_mcp [-c CLIENT]` and its refusal (MS §5); the name carried
as one more argument of `TAT.boot` (MS §5, step 4) and of `TAT.start`,
through `start` to `launch_TAT` (MS §2.6, step 5 and the last
paragraph; MS §4.6, `toplevel.py`) — the boot's dispatch on its first
argument comes with `isabelle TAT_compile`, and this step adds none;
`toplevel.served()` choosing the `TAT_Server` subclass by the name, and
the `start` record carrying it (CI §8; LOGGING.md §4, `conversation`).
The two subclasses, each stating the `clientInfo.name` it expects and
the version its facts were measured on (MS §4.6; CI §8); *(author)*
their class names are `Claude_Code_Server` and `Codex_Server`.
*(author)* `configure(working_directory)` is a method the base
declares and `served()` calls before the port is bound (MS §4.6, the
third layer); its body is LIP step 10's. With the name travels the
bound on concurrent construction jobs (CONSTRUCT_DECISIONS.md §15):
`start` reads the Isabelle environment variable
`TAT_MAX_CONCURRENT_CONSTRUCTION_JOBS` and hands its text to
`launch_TAT`, which takes unset or empty as no bound and refuses any
other value that is not a positive integer with a `TAT_StartupError`
carrying the approved sentence; step 8 uses the value.

Files: `src/scala/tat.scala`, `lib/tat.jar`, `ML/TAT_Boot.ML` (its
header), `ML/TAT_Framework.ML` (`TAT.start`, `start'`, `start`),
`toplevel.py`, `mcp_server.py`, `test/harness.py` (its `launch_TAT`
takes the two new arguments), `test/Test_TAT_Framework.thy` (its two
calls of `start'`).

Tests. `test_launcher.py`: `-c x` is refused with MS §5's sentence and
exit 2. `test_toplevel.py`: the `start` record carries the name; each
name selects its subclass; `0`, `-1` and `abc` as the bound are each
refused with the sentence read from CONSTRUCT_DECISIONS.md §15 until
MS states it, and `3` and the empty text are taken.

Done when: `isabelle TAT_mcp -c codex` serves through the Codex
subclass.

### Step 2. `POST /hook`, the announcement, the agents

Needs: step 1; LIP steps 9 and 10 land before it (§1).

Build.
- The path (MS §4.6, "The server has one path beside `/mcp`"): `POST
  /hook`, beside `/on-compaction`, which stays until step 4. The
  records `hook.request` and `hook.answer` (LOGGING.md §4).
- `Agent` (CI §4; MS §4 lists it in `jobs.py`): in this step its
  creation at the first call or hook and its working-call count. The
  record `agent.created`.
- `event_of_hook` (CI §8; CH §1's table), in this step the
  announcement: the call recorded, Claude Code answered the grant,
  Codex an empty answer. Every other hook is answered empty until
  step 5 (compaction) and step 11 (stop, interruption).
- `agent_of_call` (CI §8, "`agent_of_call` never guesses"; CH §2, §3)
  and the unannounced call (EXCEPTIONS.md §1; the record
  `tool.unannounced`).
- The handler (MS §4.6; DSL entry 22): `log.current_call` from the
  call's `_meta`, the subclass naming its client's key, set first;
  `log.current_agent` from `agent_of_call`, before `tool.call` is
  written; neither reset when the body ends; the working-call count
  in a `try/finally` around the body (CI §4). The rule rests on each
  request running in a task of its own, which holds in the SDK in use
  (mcp 1.26.0, `Server.run`: `tg.start_soon(self._handle_message, …)`).
  `/hook` sets `current_agent` to the hook's agent.
- The `clientInfo` check at the first request of an MCP session that
  reaches TAT (CI §8; MS §4.6) — *(author)* in the two handlers TAT
  registers, `tools/list` and `tools/call`. `ClientRefused`
  (EXCEPTIONS.md §3) with RB §4's sixth line and the launcher's
  sentence of MS §4.6; `stopped()` answering a refusal's own line —
  *(author)* tested before the connection's going. *(author)*
  One method of the server refuses a client: it writes
  `conversation.client_refused` and enters the ending with the
  `ClientRefused`; every refusal, the sandbox check's included, goes
  through it. A refusal's line is built from its reason by
  `mcp_server.stopped_for`, the one place the ending's sentence is
  written, and `stopped()`, whose branches the three sessions tell each
  other before editing, returns it. The record `client_connected`.
- The harness's client. `test/harness.py`'s `client()` states a
  `clientInfo` — `claude-code`, the measured version — and announces
  each call to `/hook` before sending it with the matching `_meta`;
  the tests that call tools through it are unchanged.

Files: `mcp_server.py` (`ClientRefused` lives here, where it is
raised, as EXCEPTIONS.md §3 places it), new `jobs.py`, `log.py` (the
`Judged` alias), `test/harness.py`, new `test/test_hooks.py`,
`test/test_mcp_server.py` (its cases build the Claude Code subclass).

Tests. New `test/test_hooks.py`, posting payloads straight to `/hook`.
The payloads are written by hand in the test module from the shapes
AGENT_CLIENTS_MEASURED.md records, with invented ids and paths; nothing
is copied from `ai-artifacts/probes/`. Cases: an announced call is
served, and its `tool.call` and `tool.result` records carry the same
`call` and `agent`; an unannounced call ends the conversation, is
answered RB §4's first line and writes `unannounced`; the main
conversation and a subagent are two agents, on each client; the count
is raised while a body runs and lowered when it ends after its client
gave up; 503 while ending; a raise on the path ends the conversation
and answers 500; a lower version, an unreadable one and another
client's name are each refused with the sixth line and the record, an
equal and a higher one served.

Done when: these pass, and the logging session can write LIP step 11
on the subclasses.

### Step 3. `Theory`'s `end` built in ML

Needs: what is in.

Build (EVALUATOR_DESIGN.md §1; MS §2.4; MS §3, the `Theory` row;
CONSTRUCT_DECISIONS.md §11, the entry of 2026-10-04): the ML-built
`Toplevel.exit` transition; `run_commands`, `run_span` and
`command_record` leave `TAT_Framework` and move into the test plugin's
`TAT_Test_Lib`, whose callbacks `TAT_test.run` and
`TAT_test.run_parallel` are how `test_conversation.py` runs Isar text
in seventeen places, under a comment saying to avoid `run_commands`
wherever possible; the framework's signature gains the two functions of
its output buffers that `run_span` calls, `Output_Routing.new_buffer`
and `take_buffer`.

Files: `ML/TAT_Framework.ML`, `ML/TAT_Common_Nodes.ML`,
`test/Test_TAT_Framework.thy`.

Tests: `test_session_theory.py` and `test_conversation.py`, unchanged,
with no new failure.

Done when: nothing under `ML/` or `isabelle_theory_agent/` names
`run_commands`; §5's corrections to MS and EVALUATOR_DESIGN.md are
made.

### Steps 4 to 17: need Phase A's code

### Step 4. Rendering for an agent

Needs: Phase A; step 2.

Build.
- The seen set per agent (MS §4.1; PRINT.md §4; CI §6): `Agent.seen`,
  the `Conversation` holding the agents, `Conversation.forget(key)`
  over all of them, `Forest.render(node, mode, agent)`, the messages'
  test reading that agent's set; the record `agent.seen`. *(author)*
  `Tool.run` takes the calling `Agent` beside the arguments; the
  boundary keeps its check that a body returns a text, and `tool.call`
  records the client's arguments alone.
- What a mode prints (PRINT.md §2's table; ST §4's table): the
  framework calls no `print_fields` under `Briefing`; `Session` and
  `Theory` write their fields under `Recall` alone, by depth.
- `recall` with no id renders `Briefing`, and its two descriptions
  become RECALL.md §3's (RECALL.md §2, §3).
- `/on-compaction`, `CLIENTS`, `envelope`, `unknown_client`, the
  server's `on_compaction` parameter and `mcp.on_compaction` go;
  `TAT_new` writes no client file — `write_hooks` and the six files'
  texts leave `tat.scala` (MS §5; CH, the opening).

Files: `model.py`, `mcp.py`, `mcp_server.py`, `jobs.py`, `toplevel.py`,
`tools/recall.jsonc`, `src/scala/tat.scala`, `lib/tat.jar`; of the
tests, also `test_mcp.py`'s helpers and `test_mcp_server.py`'s tool
bodies, which call a tool's `run`.

Tests. `test_print.py`: a message shown to one agent is shown again to
another, and `forget` removes a key from both; ST §4's table, mode by
mode; the briefing writes no field; the case on `mcp.on_compaction`
goes. `test_mcp.py`: `recall` without an id is the briefing, with
RECALL.md §3's lines. Every `render(node, mode)` in `test_print.py`
and `test_forest_walk.py` gains its agent. `test_launcher.py`:
`TAT_new` leaves none of the six files, and the cases on `HOOK_FILES`
and on `.tat/on-compaction.sh` go. `test_mcp_server.py`: the
`/on-compaction` cases go.

Done when: the cases of §2 whose last step this is pass or are gone.

### Step 5. Compaction events

Needs: step 4.

Build (CI §8, from "A compaction event" to the two checks; CH §1–§3;
MS §4.6; PRINT.md §4). Codex: `PreCompact`, `PostCompact` and
`SessionStart` as events on the agent the payload names. Claude Code:
at each announcement the agent's transcript — the file, the lines
gained, the `compact_boundary` lines recorded by `uuid`, the changed
`transcript_path` — and the refusal of an agent with no transcript,
with RB §4's fourth line; `PostCompact` counted; the two checks, each a
`TAT_InternalError` with its message — *(author)* the second's ten
seconds are waited in a task spawned on the ending object. The records
`agent.transcript_read`, `agent.compaction`, `agent.check_failed`. The
harness's client writes a transcript file for the agent it announces.

Files: `mcp_server.py`, `test/harness.py`, `test/test_mcp_server.py`
(its cases announce as Claude Code and need the file too).

Tests, in `test_hooks.py`, on transcript files the test writes, their
lines shaped as AGENT_CLIENTS_MEASURED.md's section "Both clients: what
tells whose context was replaced" records them: a boundary appended
clears that agent's set at its next announcement and no other agent's;
a recorded boundary is not counted again; a last line without its
newline is not read until it is complete; a subagent's file is found
under `subagents/workflows/<run>/`; a changed `transcript_path` clears
the set and the new file is read from its first line; no transcript
ends the conversation with the fourth line and `client_refused`; each
check, the second with its wait shortened by the test, ends it with the
first line and `check_failed`, and clears no set. Codex: each of the
two compaction hooks with and without `agent_id`, `SessionStart` of
each source, every answer empty.

Done when: CI §8's compaction paragraphs hold against these files.

### Step 6. The evaluation jobs' wire

Needs: step 2, which creates `jobs.py`. It needs nothing of Phase A,
and waits for it only because it adds a function to
`isabelle_driver.py`.

Build (MS §2.4, `fork_job`; MS §2.5's environment; MS §2.6, step 3; CI
§3.3, "The work" and the first half of "The report"; LOGGING.md §4,
`isabelle`, and §5). On the Isabelle side: `fork_job` with its table
and its report under deferred interrupts, the log captured at the fork,
the records `job_forked`, `job_ended`, `report_undelivered` and `bug`;
`TAT.job_cancel`; `TAT.reset` cancelling the futures first and counting
them in its record. On the Python side: the process's id counter and
id-to-job table; the remote procedure `job_finished`, declared with no
timeout, with its three wire shapes — a report carrying a `Bug` ends
the conversation of the job the table holds, whether or not that job is
still on its node, and any other report is handed to the job;
`isabelle_driver.job_cancel`.

Files: `ML/TAT_Framework.ML`, `jobs.py`, `isabelle_driver.py`,
`test/Test_TAT_Framework.thy`, the test plugin.

Tests, through the harness: a callback of the test plugin forks work
that succeeds, fails with messages, raises a `Bug`, and is cancelled; a
test object registered under the id receives the first two reports, the
third ends the conversation, the fourth's future is cancelled; the
records of a task that ends after `TAT.reset` land in the log of the
conversation that forked it. Verified here, not assumed
(EVALUATOR_DESIGN.md §6): a
library theory loaded from source while a job's work runs neither waits
for it nor cancels it.

Done when: these pass, and the logging session has read the code
against LOGGING.md §4.

### Step 7. Messages on the tool result

Needs: step 4.

Build (CI §3.4, its first two paragraphs; CI §4; CI §5, "Every tool
result"; MS §4.6, the tool handler's third point). A message and its
fields; the mailbox; posting; an agent's wake-up; the result composed
of the body, the messages and the trailer the body asked for, a failed
call's included; the mailbox taken after the checkpoint. The records
`job.message_posted` and `job.message_delivered`; `tool.result` and
`tool.given_up` carrying the messages and the trailer.

Files: `jobs.py`, `mcp.py`, `mcp_server.py`.

Tests, in `test_mcp_server.py`: a message posted to an agent rides on
that agent's next result, whatever the tool, after the body and before
the trailer, and on no other agent's; a rendered `TAT_Error` carries
it too; the ending's line carries none; a call given up before the
checkpoint leaves the mailbox as it was.

Done when: these pass.

### Step 8. Construction jobs

Needs: steps 6 and 7.

Build, in `jobs.py` unless a file is named.
- `Construction_Job` (CI §3.2: the table, "The run", "The context"),
  its outcome and the store's image (CI §3.1); questions (CI §3.4:
  `Interactive_Question`, `Answered`, `ask`, the withdrawals, the
  delivered form); what delivery drops of a construction job's
  messages (CI §3.4).
- On `Node` (MS §4.1; CI §3.1): `construction_job_class`, `job()`,
  `carry_job_from(old)`; in the setters, `_on_context_change` through
  `_completed` (MS §4.1, "Status").
- `Unfinished`, `Unfinished_Construction` and `_unfinished()`'s first
  two rows (CI §3.1); `is_finished` and the default mark's four rows
  over them (ARCHITECTURE.md §3.2; PRINT.md §1; RB §5) — `model.py`'s
  `_owes_nothing` and its mark `success` go.
- The edit (MS §4.2, step 3; CI §3.1, §9): the cancel in the completed
  events; at the commit, the old job's image copied where `gen` asked
  for it.
- The store (ARCHITECTURE.md §4.1; COMPILATION.md §4, "Storage"): the
  rows `job` and the automatic-construction setting, a missing row's
  reading, each job step's own transaction (EXCEPTIONS.md §1).
- The ending (CI §9; MS §4.6): `Ending.end` cancels every running
  construction job, in its one synchronous stretch and after the
  ending is marked entered, so that nothing which can raise comes
  before that mark; a start that failed before the forest was built
  has no forest to walk (LD, 2026-10-03). A change in the logging
  session's class, told to it first.
- Exceptions (EXCEPTIONS.md §3; RB §2): `ConstructFailed` becomes
  `ConstructionError` with its three children; `BadAnswer`.
- The loader (PLUGIN_SYSTEM.md §2, §5): the job classes a class
  declares and the members it may not override; `plugin.check_construct`
  is renamed `check_fields` (§5).
- The records `job.construction_started`, `construction_settled`,
  `construction_cancelled`, `question_answered`, `question_withdrawn`,
  `message_dropped`; the run's wrapper sets `log.current_agent` to the
  owner (CI §3.2).
- The bound on concurrent runs, around the wrapper's `await
  self._run()` (CONSTRUCT_DECISIONS.md §15), from the value step 1
  carries; a run waiting for its turn is `RUNNING`.

Files: `jobs.py`, `model.py`, `edit.py`, `store.py`, `plugin.py`,
`exceptions.py`, `mcp_server.py` (`Ending.end`).

Tests. New `test/test_jobs.py`, with no Isabelle: its node classes and
job classes are the test's own, as `test_print.py`'s are, the node
class of kind `lemma` and the construction job titled `proof
construction`, so that the documents' fenced lines apply; its question
takes `verdict`, `accept` or `reject` (CI §5). Cases: a run settling,
failing, raising, and returning after its cancel; a rerun waiting for
the earlier run's task; each cancel reason and its notification; the
question's round trip, a question asked instead, `BadAnswer`, the
withdrawals; what delivery drops; `_on_context_change` on a rerun, and
one that raises a `TAT_Error` under an edit ending the conversation
(CP §2); the
carry on an amend, with a settlement between `gen` and the commit; the
rows across a reload, `RUNNING` read back as `NOT_STARTED`; each step's
own transaction; the ending's cancel making no round trip.
`test/invariants.py`: a settled job's stored image equals its outcome.
`test_exceptions.py`: the construct errors and `BadAnswer`; the three
cases whose sentences RB §2 no longer has; cases for the lines RB §2
has and the module does not. The cases that pin `(success)` (DSL,
"Tests").

Done when: CI §3.2 and the construction half of §3.1 hold as written,
and the cases of §2 whose last step this is pass.

### Step 9. Evaluation jobs

Needs: step 8.

Build.
- `Evaluation_Job` (CI §3.3: the table, the second half of "The
  report", "Running and dropping"), the job holding its `Conversation`
  and entering step 6's table.
- On `Node` (MS §4.1; CI §3.3): `evaluation_job_class`,
  `attach_evaluation_job`, `start_evaluation_job()`,
  `check_outcome()` and the stored check; in the setters, the drop
  onto `Evaluation.dropped`, which this step adds, and the stored
  check's clearing (MS §4.1, "Status"); `cancel(ids)` for the dropped
  at each tree's flush (MS §4.1, "The recursion").
- `Unfinished_Check`, `Unchecked` and the rest of `_unfinished()`'s
  table (CI §3.1).
- The edit (MS §4.2, steps 3 and 4): the drop in the completed events,
  `cancel(ids)` after the block; a construction's `start` dropping the
  node's job (CI §3.2).
- The store: the row `check` (ARCHITECTURE.md §4.1).
- The ending drops every evaluation job (CI §9).
- The failure notification and its merging at delivery (CI §3.4).
- The records `job.evaluation_started`, `evaluation_reported`,
  `evaluation_dropped`, `report_ignored`, `cancel_sent`.

Files: `jobs.py`, `model.py`, `edit.py`, `store.py`,
`mcp_server.py` (`Ending.end`), the test plugin.

Tests. `test_jobs.py`, with no Isabelle: the evaluation jobs `proof
check` and `counterexample search`; each row of CI §3.1's table; each
of the five drops and the stored check's three clearings, and a rerun
that confirms `Ready` clearing nothing; an attach from inside a run
taking effect at the settlement; a `_finished` that leaves `RUNNING`;
the merged failure sentences; a report for a job no longer on its node
is ignored, with `job.report_ignored`. Through the harness: the test
plugin gains a node class, *(author)* of a kind that is not one of
`Theorem`'s, with a construction job, whose run asks one question and
settles by the answer, and an evaluation job, whose work step 6's test
callback forks; an evaluation job started on it settles by the report,
and one dropped by an edit has its future cancelled. The class names
both job classes so that a conversation loading the plugin has all the
tools, as step 17 needs.

Done when: CI §3.1 and §3.3 hold as written.

### Step 10. What the jobs print

Needs: step 9.

Build (CI §6; PRINT.md §1, §2; RB §5): the two tags, the failure
blocks with the colon's rule, the summary under a cut-off nesting node.

Files: `model.py`.

Tests: `test_print.py` against RB §5's blocks, its unpacking adjusted
to the three lines of the tag block, and PRINT.md §2's summary; the
three `test_print` cases §2 gives to this step, their stand-in classes
answering `Theorem`'s marks.

Done when: these render byte for byte.

### Step 11. The construct tools; the stop rule and the interruption judgement

Needs: step 10.

Build.
- `construct`, `cancel_construct`, `check_construct`, `answer` (CI §5;
  TS §5), their four `.jsonc` files; the first two and `answer`
  present only when a construction job class is loaded,
  `check_construct` when a job class of either kind is (CI §3.1); the
  two descriptions completed at start, `check_construct`'s in its
  three forms; `check_construct` read-only (MCP_SPECIFICATION.md §5),
  its state lines the trailer.
- `edit`'s `auto_construct` (TS §1), written on each new node's job
  after `gen` (MS §4.2, step 1).
- The stop rule and the interruption judgement on `/hook` (CI §7; CH
  §1's second and third rows), with the records `agent.stop_judged`
  and `agent.interruption_judged`.

Files: `mcp.py`, `mcp_server.py`, `edit.py`, `plugin.py` (the `edit`
schema with and without `auto_construct`), `tools/*.jsonc`,
`test/baselines.py` (`stated()` reads TS's per-tool `Tool
description:` lines — DSL, "Tests").

Tests. `test_mcp.py`: every fenced line of CI §5 and RB §2, §6 that
these tools render; TS §4's malformed-call block with `auto_construct`
in `it takes …`; the node sets, the skipping and the one refusal;
`check_construct`'s four conditions and both clamps; `answer`'s four
refusals; the two completed descriptions with one and with several
titles. `test_hooks.py`: the stop rule's reason in each row of CI
§7's table against its fenced examples; the interruption denied for a
held agent and for a working call, allowed otherwise.

Done when: every sentence of CI §7 and of CI §5's four tools is
produced verbatim.

### Step 12. The walk starts jobs; `evaluate_to`

Needs: step 11.

Build.
- The walk (CI §3.3, "Where a job starts", "Automatic construction";
  MS §4.1, "The recursion"): `Evaluation.starter`; the evaluation job
  started at a passed node, the construction started automatically at
  a passed node and on a failed report, `blocking`'s
  wait (CI §5, "Every tool result"), `Node.evaluate_to(agent,
  ignore_error, checks)`, an edit's and a move's own evaluation under
  `quick` (MS §4.2, step 4).
- On the result of a call that ran an evaluation (CI §5, "Every tool
  result"): the `Automatically started …` line and the background
  line.
- The tool `evaluate_to` (TS §4, §5; MCP_SPECIFICATION.md §4; RB §3,
  §6; PRINT.md §5): its entry, `tools/evaluate_to.jsonc`, `checks`
  present only when an evaluation job class is loaded and its
  description completed at start, the two opening lines, the order
  constraint's sentence after the stop line and after an edit's `Done`
  line.

Files: `model.py`, `mcp.py`, `tools/evaluate_to.jsonc`.

Tests. `test_forest_walk.py` and `test_jobs.py`: a check starts only
where `_unfinished()` would answer `Unchecked`, and none under `"no"`;
a construction starts automatically at a `ready` node, not at one that
failed and was not invalidated since, again after an invalidation, not
at one that succeeded while its check is passed, running or not yet
run, again when that check failed, and on a failed report, its owner
the caller or the starter; `blocking`
returns after the passed nodes' jobs end, whoever started them, the
failures on the same result. `test_mcp.py`: the lines of RB §6 and
§3, the background line's forms, `checks` absent with no evaluation
job class, a malformed call's lines.

Done when: ARCHITECTURE.md §3.6 and CI §3.3 hold in these tests.

### Step 13. `Theory`'s `description`

Needs: Phase A; Phase B's `Theory.emit_beginning` (B3); step 4.

Build (ST §2, §4): the field, its schema line, the store, what it
prints; its `text ‹…›` block written by `Theory.emit_beginning` before
the header, with ST §2's replacement of the cartouche characters.

Files: `model.py`.

Tests: `test_descriptions.py`; `test_session_theory.py`; `test_print.py`
against ST §4's lines; a compile of a theory with a `description`, one
holding `‹` and `\<close>`, and of one without.

Done when: the case §2 gives to this step passes.

### Step 14. `Theorem`: the statement

Needs: step 3; step 8 (`carry_job_from`); Phase A's
`Node._slots_written_by` and `IsaTerm` in `Isabelle_RPC_Host.unicode`;
Phase B's
`Theory.emit_beginning` writing the header through `Theory.header()`
(B3).

Build. `Theorem` as TH §1 to §4, §6's evaluation, §8's table and §9:
`STATEMENT_DEFS`, `gen` with its checks and its call of
`carry_job_from`, `is_identifier` beside `IsaTerm` in
`Isabelle_RPC_Host.unicode` (DSL, "Outside this repository", item 1),
`TAT.Theorem.evaluate` with its two transitions and the `goal_state`
slot (MS §3) — the class mints the slot in `gen` and `from_store`,
appends it in `_states_inside()` and names it in `_slots_written_by`,
and the callback clears it when a rerun of a `ready` node fails
(CONSTRUCT_DECISIONS.md §15) —, `reserved_names`, `print_fields`, the mark's statement
slot (TH §7, "The mark"). The call of `carry_job_from` carries nothing
until step 15 names the job class. The class is the first of the
plugin `Isabelle_Std` (CONSTRUCT_DECISIONS.md §11, the entries of
2026-10-04), which this step creates: its directory with `etc/settings`
and `ROOT`, its major theory, `ML/TAT_Theorem.ML`, and the Python
subpackage `isabelle_theory_agent.std`, which the theory's registration
names. No conversation loads the class before step 15: the
registration names no package until then, and `test_theorem.py`'s
conversations list the package themselves. The plugin's cases run in a
harness run of their own, launched with `-l Minilang_AoA`. The step
also builds the imports a plugin declares (CONSTRUCT_DECISIONS.md §11):
the declaration in `plugin.py`, kept and returned by `load` as the
compile hooks are; `Theory`'s header, the one function its evaluation
and its emission both write the header through, adding them on a
theory none of whose imports resolves to a theory of the forest;
`Isabelle_Std` declaring `Minilang_AoA.Minilang_AoA`. Measured in this
step: whether that import changes how a statement's terms parse.
Not measured as such (2026-10-10): the statements the std tests send
parse as written under the import; no notation of `Minilang_AoA`'s has
met one yet.

Files: `Isabelle_Std/` (`TAT_Isabelle_Std.thy`; the `etc/settings` and
`ROOT` of the first cut went with R21, the session declared in TAT's ROOT;
`ML/TAT_Theorem.ML`), `isabelle_theory_agent/std/` (`__init__.py`,
`statement.py`, `theorem.py`; the empty `builtins.py` and
`theorem_node.py` go), `ML/TAT_Common_Nodes.ML` (its empty sections for
`Theorem`, `Define` and `Section` go),
`contrib/Isabelle_RPC/Isabelle_RPC_Host/unicode.py`, `test/harness.py`
and `test/conftest.py` (a conversation's packages; the second run).

Tests. New `test/test_theorem.py`: the schema and the descriptions of
TH §2, §3; `gen`'s refusals from TH §4's fenced lines and RB §2; a
valid and an invalid statement evaluated through the harness, the
`goal_state` slot holding a state exactly while the node is `ready`; a
reserved name recorded; the rows of TH §8's table.

Done when: a theory of theorems is built through `edit` and evaluates,
each statement admitted.

### Step 15. `Proof_Job` and `Proof_Check`

Needs: steps 9 to 14; the
`Session`'s folder made before a theory begins (Phase B, B5).

Build (TH §7 whole, §6's last paragraph, §8's examples; CI §10's first
paragraph; CONSTRUCT_DECISIONS.md §15): the two job classes named on
`Theorem`, and the class loaded in every conversation;
`TAT.Theorem.construct` on AoA's `hammer_or_AoA`, extended in Isa-Mini
to return the times; `TAT.Theorem.check` through the function Isa-Mini
exports for the replay of one record; the mark's proof slot.

Files: `isabelle_theory_agent/std/theorem.py`;
`Isabelle_Std/ML/TAT_Theorem.ML`;
`contrib/Isa-Mini/Agent/agent_server.ML` and `proof_store_AoA.ML` (TH
§7 names both); `test/harness.py` (its check of the package list a
conversation is launched with).

Measured in this step (CI §10): that TAT's process serves
`IsaMini.AoA`; how soon the Python half learns of an interrupt of the
forked task; that AoA's `group = NONE` forks end with the job.
Measured 2026-10-09: the first holds — `TAT.Theorem.construct` names
`IsaMini.AoA` in `python_packages`, so the conversation imports it and
the remote procedure is this process's (`test_a_theorem_is_constructed_
checked_invalidated_and_constructed_again` asserts the import). The
other two need a construction that runs long enough to interrupt, which
on the goals the automation closes never happens and on any other goal
reaches the language model; they wait for the AoA round's scripted
driver. Found on the way: `ERROR ""` renders as `Error` through
`Runtime.exn_messages`, so `fork_job` reports it as one empty message
itself (MODULE_STRUCTURE §2.4).

The owner's rule, 2026-10-10, for every step of this plan: no framework
mechanism for what an operation's ML can capture and return itself —
TAT owns all of its ML, and each operation writes what matters into its
return value; capturing Isabelle's warnings for `Theorem` was refused on
it, as `run_commands` had been.

Tests, in `test_theorem.py`: TH §7's sentences and the eleven lines of
its mark; `_check()`'s table; TH §8's three examples; a construction
and a check through the harness that call no language model — under a
scripted driver of AoA's `test.<name>` kind, or on a goal the proof
store or Sledgehammer closes; which of these is settled when the step
starts.

Done when: a `Theorem` is constructed, checked, invalidated and
constructed again in one conversation.

### Step 16. `Theorem`'s emission; the proof-store compile hook

Needs: step 15; Phase B's emission contract, `compile.py` and compile
hooks (B3, B4, B6); step 14's declared import, by which an emitted
theory has the `aoa` method.

Build (TH §5; COMPILATION.md §3; COMPILATION.md §5, "Compile hooks"):
`Theorem.emit`, `sorry` or `by aoa`; the hook the package registers.

Files: `isabelle_theory_agent/std/theorem.py`.

Tests, in `test_theorem.py`: a compile of a forest with a proven, an
unchecked and an unproven theorem writes TH §5's text; the hook removes
what COMPILATION.md §5 says it removes and nothing else.

Done when: `isabelle TAT_compile` writes a theory Isabelle reads.

Status 2026-10-10 (the jobs/construct session): done. `Theorem.emit`
since step 14; the hook `remove_proof_stores_of_no_tree` in
`isabelle_theory_agent/std/theorem.py`, over `compile.paths`, removing
`<T>.proof-store` and `<T>.proof-store.*` entries that are not folders
when their folder (by `compile.identity`, as the compile knows its
session folders: the spelling on disk may differ from the session's)
and `T` are no tree's — the pair review's one defect, 2026-10-13, had it
compare path spellings. Tests in
test_theorem.py: the in-process compile of a proven, an unchecked and an
unproven theorem (`by aoa` / `sorry` / `sorry`) with the hook's keeps
and removals (a link removed, its target and `Gone.proof-stored` kept,
after the review's mutation check); and `isabelle TAT_compile` on a directory made with
`TAT_new -P` (the tool reads the plugin from the database; a harness
case's directory alone carries none) that a conversation of the
plugin's run left — the hook runs in the tool's process, and the tool's
Isabelle reads the ROOT (`sessions "Minilang_AoA"`) and the header (the
declared import) — the step's "done when". Both pass (2026-10-11; 38
Isabelle-backed, 552 in-process). `TAT.Theorem.construct`'s two handler
arms call `MiniLang_Agent_AoA.method_error` (Isa-Mini ca26050, the
review's shared give-up renderer) since the same run. Isa-Mini's two
changes for step 15 are committed by the AoA session (contrib/Isa-Mini
62f6b89).
Open with the owner: the end-to-end case can call a language model only
where `~/.isabelle/Isabelle2025-2/etc/settings` opens AoA's gate
unconditionally (lines 19 and 24 on the owner's machine); the owner
decides whether to make those lines `${VAR-default}`, after which the
harness sets `AOA_ALLOW_NONINTERACTIVE=no` for the child
(test/harness.py, the child's `env` near line 485).

### Step 17. The live run

Needs: steps 1 to 12 and LIP steps 9 to 12; one run per client, the
one of LIP step 13.

The working directory is made with the test plugin loaded (`TAT_new
-P`), whose node class of step 9 gives an agent a construction to
start, a question to answer and a check to wait for before `Theorem`
has any; the launch must let the RPC host import `tat_test_plugin`,
which lies under `test/` — how is checked when the run is prepared.
The agent adds a theory through the tools, evaluates,
constructs, compacts, is stopped and interrupted, and leaves. The
measurements the documents leave to implementation are taken in it:
the project-level files' exact names and an interactive session
reading the two transcript `env` entries from the project settings (CH
§4); which request the library dispatches first after `initialize`,
and Claude Code's `server/discover` probe answered without harm (DSL,
"CLIENT_HOOKS.md", item 6b); `features.multi_agent_v2` naming the
interruption tool and the layer `check_for_update_on_startup` is read
from (CONSTRUCT_DECISIONS.md §10, §12); and, of DSL's "Compaction"
item 2, what AGENT_CLIENTS_MEASURED.md does not yet record. The run's
files stay under `ai-artifacts/probes/`, uncommitted, and no
credential is copied into them.

Done when: the conversation's log shows every rule of CI §7 and §8
firing as specified, on both clients.

Status 2026-10-13 (the jobs/construct session): done for the rules the
runs reach — seen in the log on both clients, Claude Code 2.1.296 (five
runs and an env probe) and Codex 0.156.1 (three runs), with the test
plugin's notes: the stop allowed and blocked (a running check; a pending
question; the second Stop with `stop_hook_active`), `SubagentStop`
blocked and then allowed (the latter on Codex; on Claude Code the
blocked subagent's conversation was ended first, below), the
interruption denied with `holding_work` (`TaskStop`; Codex's
`collaborationinterrupt_agent`) and allowed when nothing was held
(Claude Code only), the compaction detected on both; the three reason
texts byte-for-byte CI §7's; all 423 stop verdicts consistent with the
agents' jobs. Not reached by a run, covered by the in-process suite
where it is: CI §7's rows "a question, and jobs running" and "messages
only", a running construction job holding a stop, the plural state
lines, the 503 while ending, the client refusals, an unannounced call, a
subagent's compaction, the transcript-change events, the
compaction-check failures, a seen set cleared non-empty (REPORT.md §2) —
mapped to the suite in `ai-artifacts/review/steps_16_17/done_when_gap.md`:
ten pinned already, and three tests added to test_hooks.py for the rest
(the 503 for a stop and an interruption while ending; an unannounced
call on Codex; a `SubagentStop` blocked then allowed on Claude Code), so
the gap is closed by the suite, by the owner's word.
Measurements: the project-level file names; an interactive session reads
the project settings' transcript `env` entries (the control without
them is inconclusive); `tools/list` is the first request after
`initialize`, no `server/discover` seen; Codex's `clientInfo`
`codex-mcp-client 0.156.1` and one MCP session per thread;
`multi_agent_v2`'s tool name; `check_for_update_on_startup`'s layer not
determined. The record, the driver, the step files and every run's
directory: `ai-artifacts/probes/live17/` (REPORT.md), uncommitted. For
the owner's decision (REPORT.md §4): twice an announcement came under an
agent id Claude Code writes no transcript for (at stuck moments;
`advisorModel` suspected) and TAT ended the conversation by
CLIENT_HOOKS §2's rule; a model that will not act loops without bound
under `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP=0`; both clients load the user's
own MCP servers (`--strict-mcp-config` exists on Claude Code).

## 4. For the owner

1. **The word to start** was given on 2026-10-05 (「开工」), after Phase
   B's commit; the steps run in the plan's order, 1 to 17, and step 1
   is in (DSL entry 32). The logging session's steps 10 and 11 wait
   for steps 1 and 2. §1's two intervals in which a real client is
   served wrongly remain: between LIP step 10 and step 2, and between
   step 2 and step 5. Two shapes of step 1 are the author's, told to
   the owner here: the bound's text is checked before the lock, so a
   bad value leaves no log; the plugin's declared import is a
   module-level call `TAT_import(<theory name>)` (PLUGIN_SYSTEM §1).

Decided on 2026-10-04 and no longer open (CONSTRUCT_DECISIONS.md §11,
§15): the plugin `Isabelle_Std` with its structure and names; the
import it declares, which `Theory` adds to the header of every theory
that imports no theory of the forest and which `recall` does not show;
the bound's variable and its refusal; a waiting run shown as running;
`check_construct` existing when a job class of either kind is loaded,
which step 11 builds with its second description.
The tool `evaluate_to` (step 12) and `Theory`'s `description` (step 13)
are this plan's, by the owner's word of 2026-10-04. The shared
`IsaTerm` is no longer open: as the compilation session
reports, the owner chose on 2026-10-04 one class for AoA and TAT, AoA's
moved unchanged into `Isabelle_RPC_Host.unicode` (CP §5, point 1; its
step A5); step 14 adds `is_identifier` beside it.

## 5. Corrections to the documents, made when the step lands

The decisions of 2026-10-04 are written into CI §3.1, §5 and §10, TS
§1 and §5, MCP_SPECIFICATION.md §1, TH's opening, §5 and §7,
OPEN_QUESTIONS.md, EVALUATOR_DESIGN.md §5, MS §1, §2.6, §3, §4, §4.5
and §4.6, and ARCHITECTURE.md §2.2; on 2026-10-05, with step 1, the
declared imports in PLUGIN_SYSTEM.md §1 and ST §2 and §4, and the
bound's refusal among the `TAT_StartupError`s of EXCEPTIONS.md §1.

- Step 3: MS §2.4's bullet on `run_commands`, the phrase "no
  `run_commands`" in MS §3's `Theorem` row, and EVALUATOR_DESIGN.md
  §1's and §6's mentions of it describe a function that is gone from
  the framework; MS §2.5's signature gains the two output-buffer
  functions `run_span` calls. MS is told to the
  compilation session first.
- Step 8: CI §3.1 and ARCHITECTURE.md §4.1 call the `job` row "a tag
  and an optional string", while CI §3.1 makes the product a
  MessagePack-representable value and TH §1 a text with two times. The
  row is a tag and an optional value — the product, or the failure's
  message. ARCHITECTURE.md is told to the compilation session first.
- Step 8: MS §4.2 and §4.4 name the field checker `check_construct`;
  it becomes `check_fields`. Told to the compilation session first.
- Steps 14–15 (2026-10-10, from their review): MS §2.4's `fork_job` and
  CI §3.3's "The work" and "The report" gain the product on the report,
  `Construction_Job.forked` and the construction run's fork in the
  table; CI §3.2 the `forked` row and `can_start()` requiring `ready`;
  THEOREM §7, CI §10, MS §4's `Theorem` row and OPEN_QUESTIONS name
  `hammer_or_AoA'`; THEOREM §1, §2 and §6 the undeclared-variable
  refusal and `Ready` with no messages; LOGGING §4's job records
  general over both kinds of job, the product not logged; MS §2.4's
  "one transition" two; the measurements of CI §10 and THEOREM §7
  recorded. Done.
- Step 17 (2026-10-13, from the live run and its review, the owner's
  word 「你可以自决」): CONSTRUCT_DECISIONS.md §1 — the launcher exits
  2, the first request after `initialize`, the clients' `clientInfo`,
  no `server/discover` seen, the measured Claude Code version 2.1.296
  (also CI §8, CH's opening, `mcp_server.measured_version`); §10 —
  "exits 2", the `multi_agent_v2` tool name,
  `check_for_update_on_startup`'s layer not determined; §12 — the
  interactive measurements and the source reading of the two unknown
  agent ids; CH §4 — the `FORCE_SESSION_PERSISTENCE` entry's
  interactive reading not measured (the env probe `claude-code-env` set
  `CLAUDECODE=1`, not `CLAUDE_CODE_CHILD_SESSION=1`); CH §5 — the
  enclosing repository's CLAUDE.md and memory, the user's own MCP
  servers and MCP servers that write files, among the accepted gaps;
  AGENT_CLIENTS_MEASURED — the measured items. CI §1's transcript
  premise and the rule of CH §2 / CI §8 wait for the owner's ruling on
  `ai-artifacts/probes/live17/REPORT.md` §4.1.

## 6. Not in this plan

The AoA round's remainder (CI §10, "Still the round's"): the question
kinds, AoA being told it runs under TAT, a construction that continues
through a context change. The node classes of OPEN_QUESTIONS.md §1.
Nothing is built for an agent that left with jobs running (CI §7's last
paragraph) or for progress notifications (CI §8). Two items
CONSTRUCT_DECISIONS.md §12 lists as pending belong to designs since
replaced: M6, with A3; and the slot-release order, a check the record
asked for when a rerun was "invalidate, then evaluate"
(CONSTRUCT_DECISIONS_LOG.md §12's "Cancellation" entry), which CI
§3.2's "The context" replaced with one write.
