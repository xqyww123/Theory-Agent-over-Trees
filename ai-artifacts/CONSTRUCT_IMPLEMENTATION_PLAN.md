# Implementation plan: agents, hooks, jobs, the construct tools and `Theorem`

Written 2026-10-03, revised on 2026-10-04 after four readers' checks
(review/IMPLEMENTATION_PLAN_REVIEW_2.md). Nothing of it is implemented.
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
ai-artifacts/LOGGING_DECISIONS.md, **CR** =
ai-artifacts/COMPILATION_REVIEW.md, **DSL** =
ai-artifacts/review/DOC_SYNC_LIST.md.

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

| what | whose | state on 2026-10-03 |
| --- | --- | --- |
| the log, the ending object, `isabelle_driver.call`, the tool boundary's records, the Isabelle side's log, `register_callback` taking the callback record (LIP steps 1–6, 8) | the logging session | in, committed (bd48a93, 2e8f6e7, d9472b3, df271ca) |
| the walk, the setters, the edit's commit block, the store's rows, `owned_slots`, the `Session`'s folder made before a theory begins, `IsaTerm` in `Isabelle_RPC_Host.unicode` (CR §14 items 1–7) | the compilation session | not started: the owner holds its start until he approves again (CR §14's opening) |
| `compile.py`, `Node.can_emit` and `emit`, the compile hooks' framework side, `isabelle TAT_compile` (COMPILATION.md §3, §5) | the compilation session | after CR §14's item 8 (CR §14's last paragraph) |
| `hook.py`, `guard.py` (LIP step 9); `configure` (LIP step 10); the Codex sandbox check (LIP step 11); the launcher refusing a path with `[` or `]` (LIP step 12) | the logging session | steps 9 and 12 in the tree, uncommitted — step 12 in `tat.scala`, `lib/tat.jar` and `test_launcher.py`, which steps 1 and 4 here edit after it; step 10 waits for step 1 here, step 11 for step 2 |

**Steps 1 to 3 before CR §14, steps 4 to 17 after.** Steps 1 to 3
share no file with CR §14 and need nothing of it. Every other step
edits a file CR §14 rewrites — `model.py`, `edit.py`, `store.py`,
`plugin.py`, `isabelle_driver.py` — or `mcp.py`, which its change to
`Evaluation` reaches, or needs what it builds, and starts only when CR
§14 is in the tree: the two sessions never edit one file at the same
time. The owner's word of 2026-10-03 (DSL entry 15) and the recorded
division (DSL entry 16; LD, K1) put all of this plan after the
compilation code; taking steps 1 to 3 out of that rule, because LIP
steps 10 and 11 wait for them, is the owner's to allow (§4, point 1).

**What the compilation session's code leaves to this plan** (CR §14,
items 1, 2, 4 and 7): `Evaluation`'s `starter` and `dropped`; in the
setters, the stored check's clearing, `_on_context_change` and the
evaluation job's drop; the jobs' reserved rows; `Conversation.forget`
over the agents' sets, which that code writes over the one set the
conversation holds today; the test of an `_on_context_change` that
raises under an edit.

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
and 18 fail, each because a document is ahead of the code.

| case | waits for |
| --- | --- |
| `test_launcher`: `test_a_fresh_directory_gets_the_database_the_script_and_the_hook_files`, `test_the_script_fails_readably_without_a_running_conversation`, `test_the_script_reaches_a_serving_conversation` | step 4, which removes them with the files they test |
| `test_mcp_server`: `test_on_compaction_answers_the_briefing_in_the_clients_shape` | step 4, which removes it with the path |
| `test_mcp`: `test_the_four_tools_their_descriptions_and_schemas_as_the_documents_state_them` | step 4 (`recall`'s description); it grows with steps 11 and 12 |
| `test_print`: `test_the_root_forms_of_print_md_section_6` | step 4 (no field under a focus) and step 8 (`complete`) |
| `test_print`: `test_the_recall_of_recall_md_section_2`, `test_the_quickview_of_print_md_section_7` | step 4 (the fields by mode), step 8 (the marks) and step 10 (the tags) |
| `test_print`: `test_the_lines_of_render_baselines_section_5` | step 8 (the marks) and step 10 (the tags; the unpacking of RB §5) |
| `test_exceptions`: `test_construct_not_supported`, `test_unknown_kind`, `test_invalid_field`, `test_unexpected_field` | step 8 (the last three pin sentences RB §2 no longer has) |
| `test_exceptions`: `test_every_baseline_is_covered` | step 8 (the construct errors; RB §2's lines the module has no case for), step 11 (`auto_construct` in `it takes …`), step 14 (the fact name's line) and the compilation session's `ReservedSessionName` lines |
| `test_mcp`: `test_a_malformed_call_is_refused_on_its_own_shape_with_no_opening_line` | step 11 (`auto_construct` in `it takes …`) |
| `test_mcp`: `test_the_success_lines_of_render_baselines_section_6` | step 11 and step 12 (RB §6's three blocks) |
| `test_descriptions`: `test_descriptions_are_the_documents_fenced_lines` | step 13 |
| `test_session_theory`: `test_the_field_checks` | the compilation session (CR §10, "The 13 failing tests") |

## 3. The steps

### Steps 1 to 3: before CR §14

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
third layer); its body is LIP step 10's.

Files: `src/scala/tat.scala`, `lib/tat.jar`, `ML/TAT_Boot.ML` (its
header), `ML/TAT_Framework.ML` (`TAT.start`, `start'`, `start`),
`toplevel.py`, `mcp_server.py`, `test/harness.py` (its `launch_TAT`
takes the fourth argument), `test/Test_TAT_Framework.thy` (its two
calls of `start'`).

Tests. `test_launcher.py`: `-c x` is refused with MS §5's sentence and
exit 2. `test_toplevel.py`: the `start` record carries the name; each
name selects its subclass.

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
  through it. The record `client_connected`.
- The harness's client. `test/harness.py`'s `client()` states a
  `clientInfo` — `claude-code`, the measured version — and announces
  each call to `/hook` before sending it with the matching `_meta`;
  the tests that call tools through it are unchanged.

Files: `mcp_server.py`, new `jobs.py`, `exceptions.py`, `toplevel.py`,
`test/harness.py`, `test/test_mcp_server.py` (its cases build the
server and call tools without the harness's client).

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

Needs: what is in; the owner's answer to §4, point 2.

Build (EVALUATOR_DESIGN.md §1; MS §2.4; MS §3, the `Theory` row): the
ML-built `Toplevel.exit` transition; `run_commands`, `run_span` and
`command_record` leave `TAT_Framework`. The step is written for the
answer §4's point 2 proposes: the three move into the test plugin's
`TAT_Test_Lib`, whose callbacks `TAT_test.run` and
`TAT_test.run_parallel` are how `test_conversation.py` runs Isar text
in seventeen places, and the framework's signature gains the two
functions of its output buffers that `run_span` calls,
`Output_Routing.new_buffer` and `take_buffer`.

Files: `ML/TAT_Framework.ML`, `ML/TAT_Common_Nodes.ML`,
`test/Test_TAT_Framework.thy`.

Tests: `test_session_theory.py` and `test_conversation.py`, unchanged,
with no new failure.

Done when: nothing under `ML/` or `isabelle_theory_agent/` names
`run_commands`; §5's corrections to MS and EVALUATOR_DESIGN.md are
made.

### Steps 4 to 17: after CR §14

### Step 4. Rendering for an agent

Needs: CR §14; step 2.

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

Needs: step 2, which creates `jobs.py`. It needs nothing of CR §14, and
waits for it only because it adds a function to `isabelle_driver.py`.

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
  self._run()` (CONSTRUCT_DECISIONS.md §15): built when the owner has
  named its variable (§4, point 4).

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
(CR §14, item 7); the
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
  TS §5), their four `.jsonc` files, present only when a construction
  job class is loaded, the two descriptions completed at start,
  `check_construct` read-only (MCP_SPECIFICATION.md §5), its state
  lines the trailer.
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
failed and was not invalidated since, again after an invalidation, and
on a failed report, its owner the caller or the starter; `blocking`
returns after the passed nodes' jobs end, whoever started them, the
failures on the same result. `test_mcp.py`: the lines of RB §6 and
§3, the background line's forms, `checks` absent with no evaluation
job class, a malformed call's lines.

Done when: ARCHITECTURE.md §3.6 and CI §3.3 hold in these tests.

### Step 13. `Theory`'s `description`

Needs: CR §14; step 4.

Build (ST §2, §4): the field, its schema line, the store, what it
prints.

Files: `model.py`.

Tests: `test_descriptions.py`; `test_session_theory.py`; `test_print.py`
against ST §4's lines.

Done when: the case §2 gives to this step passes.

### Step 14. `Theorem`: the statement

Needs: step 3; step 8 (`carry_job_from`); the compilation session's
`owned_slots` and `IsaTerm` in `Isabelle_RPC_Host.unicode`; the
owner's answer to §4, point 5.

Build. `Theorem` as TH §1 to §4, §6's evaluation, §8's table and §9:
`STATEMENT_DEFS`, `gen` with its checks and its call of
`carry_job_from`, `is_identifier` beside `IsaTerm` in
`Isabelle_RPC_Host.unicode` (DSL, "Outside this repository", item 1),
`TAT.Theorem.evaluate` with its two transitions and the `goal_state`
slot (MS §3), `reserved_names`, `print_fields`, the mark's statement
slot (TH §7, "The mark"). The call of `carry_job_from` carries nothing
until step 15 names the job class. *(author)* The class's Python half
is loaded as a plugin's is, by the package its ML registration names
(MS §2.5), `isabelle_theory_agent.theorem_node`. Whether a conversation
loads the class before step 15 is §4, point 3; the step is written for
the answer proposed there: the registration names no package until
step 15, and `test_theorem.py`'s conversations list the package
themselves.

Files: `theorem_node.py`, `ML/TAT_Common_Nodes.ML` or the theory §4's
point 5 names, `contrib/Isabelle_RPC/Isabelle_RPC_Host/unicode.py`,
`test/harness.py` (a conversation's packages).

Tests. New `test/test_theorem.py`: the schema and the descriptions of
TH §2, §3; `gen`'s refusals from TH §4's fenced lines and RB §2; a
valid and an invalid statement evaluated through the harness, the
`goal_state` slot holding a state exactly while the node is `ready`; a
reserved name recorded; the rows of TH §8's table.

Done when: a theory of theorems is built through `edit` and evaluates,
each statement admitted.

### Step 15. `Proof_Job` and `Proof_Check`

Needs: steps 9 to 14; the owner's rulings of §4, points 4 and 5; the
`Session`'s folder made before a theory begins (the compilation
session's).

Build (TH §7 whole, §6's last paragraph, §8's examples; CI §10's first
paragraph; CONSTRUCT_DECISIONS.md §15): the two job classes named on
`Theorem`, and the class loaded in every conversation;
`TAT.Theorem.construct` on AoA's `hammer_or_AoA`, extended in Isa-Mini
to return the times; `TAT.Theorem.check` through the function Isa-Mini
exports for the replay of one record; the mark's proof slot.

Files: `theorem_node.py`; the theory that holds `Theorem`'s ML;
`contrib/Isa-Mini/Agent/agent_server.ML` and `proof_store_AoA.ML` (TH
§7 names both); `test/harness.py` (its check of the package list a
conversation is launched with).

Measured in this step (CI §10): that TAT's process serves
`IsaMini.AoA`; how soon the Python half learns of an interrupt of the
forked task; that AoA's `group = NONE` forks end with the job.

Tests, in `test_theorem.py`: TH §7's sentences and the eleven lines of
its mark; `_check()`'s table; TH §8's three examples; a construction
and a check through the harness that call no language model — under a
scripted driver of AoA's `test.<name>` kind, or on a goal the proof
store or Sledgehammer closes; which of these is settled when the step
starts.

Done when: a `Theorem` is constructed, checked, invalidated and
constructed again in one conversation.

### Step 16. `Theorem`'s emission; the proof-store compile hook

Needs: step 15; `compile.py` with `Node.can_emit` and `emit`; where
the `aoa` method lives, so that an emitted theory imports it
(OPEN_QUESTIONS.md §3; §4, point 5).

Build (TH §5; COMPILATION.md §3; COMPILATION.md §5, "Compile hooks"):
`Theorem.emit`, `sorry` or `by aoa`; the hook the package registers.

Files: `theorem_node.py`.

Tests, in `test_theorem.py`: a compile of a forest with a proven, an
unchecked and an unproven theorem writes TH §5's text; the hook removes
what COMPILATION.md §5 says it removes and nothing else.

Done when: `isabelle TAT_compile` writes a theory Isabelle reads.

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

## 4. For the owner

1. **The order between the sessions.** The owner's word of 2026-10-03
   put this session's implementation after the compilation system and
   the logging system (DSL entry 15). CR §14 has not started, and steps
   4 to 17 wait for it. Steps 1 to 3 share no file with it and could
   run before it, which lets the logging session finish its steps 10
   and 11; the price is §1's two intervals in which a real client is
   served wrongly — TAT calls refused under `-p` between LIP step 10
   and step 2, compactions clearing no seen set between step 2 and
   step 5. The alternative is to hold steps 1 to 3, and with them LIP
   steps 10 and 11, until CR §14 is in.
2. **The text runner after `end` leaves it.** Decided on 2026-09-30
   (DSL, "MODULE_STRUCTURE.md", item 1; MS §2.4): once `Theory`'s
   `end` is built in ML, `run_commands` and `run_span` go, and "those
   two tests" are rewritten against `end_theory`. The two are not
   tests but the test plugin's callbacks `TAT_test.run` and
   `TAT_test.run_parallel`, through which `test_conversation.py` runs
   Isar text in seventeen places — definitions, lemmas with their
   proofs, ML that prints — for its cases on the theory table, import
   resolution and output isolation. Proposed: the runner moves into the
   test plugin as test code, the framework exporting the two
   output-buffer functions it calls, and no product code runs text.
   The alternative is to rewrite the seventeen probes, each on
   transitions built in ML.
3. **`Theorem` before its jobs exist.** The owner ruled that `Theorem`
   names no job class until its jobs are built, its proofs written
   `sorry`. TH §7's mark reads its proof slot from the construction
   job, and CI §3.1's table makes a node without one finished: in that
   state a theorem's line has no specified proof slot, and a theory of
   `sorry` theorems reads `complete`. Proposed: no conversation loads
   `Theorem` until step 15, so the state never reaches an agent, and
   step 14 can be committed on its own. The alternative is a ruling on
   the line and on the theory's mark for that state.
4. **Three rulings the AoA drive path still needs**
   (CONSTRUCT_DECISIONS.md §15, "Pending the owner"): the environment
   variable's name and the sentence for a value that is not a positive
   integer, which the bound of step 8 waits for; how a run waiting for
   its turn shows; what `Theory`'s beginning does when its `Session`'s
   folder cannot be made — the compilation session's code raises the
   compile's refusal until the ruling gives the beginning its own
   failure (CR §14's closing paragraphs).
5. **Where `Theorem`'s ML lives.** MS §3 puts its three callbacks in
   `TAT_Common_Nodes`. `TAT.Theorem.construct` calls AoA's
   `hammer_or_AoA`, so the theory that holds it imports AoA's, while
   TAT's theory imports `Isabelle_RPC` alone and its session's parent
   is `Isabelle_RPC`. On the answer depend the file step 14 writes
   `TAT.Theorem.evaluate` into, the base heap a launch needs and how
   long the harness takes to start. Where the `aoa` method lives, and
   so what an emitted theory imports for `by aoa`, is the neighbouring
   question (OPEN_QUESTIONS.md §3), which step 16 waits for.
6. **A class with an evaluation job and no construction job.** CI §3.1
   then offers `checks` without the four construct tools, yet `checks`'
   description, the background line's first sentence and every
   instruction of the stop rule tell the agent to call
   `check_construct`. `Theorem` and the test plugin's class name both
   kinds, so no step meets the case; the design needs a ruling before
   a class of that shape exists.
7. **Two pieces no plan was assigned,** taken here unless the owner
   says otherwise: the tool `evaluate_to` (step 12) and `Theory`'s
   `description` (step 13). The compilation session has no objection
   (CR §14's last paragraph).
8. **Which `IsaTerm` is shared.** The record of 2026-09-30 (DSL,
   "Outside this repository") has `Isabelle_RPC_Host/unicode.py`
   receive AoA's class unchanged and AoA import it from there; TAT's
   own class differs from it (TH §2). CR §14 item 5 states both and
   waits for the owner's choice, which the compilation session has
   asked for; step 14 waits with it.

## 5. Corrections to the documents, made when the step lands

- Step 3: MS §2.4's bullet on `run_commands`, the phrase "no
  `run_commands`" in MS §3's `Theorem` row, and EVALUATOR_DESIGN.md
  §1's and §6's mentions of it describe a function that is gone from
  the framework; MS §2.5's signature gains the two output-buffer
  functions if §4's point 2 is answered as proposed. MS is told to the
  compilation session first.
- Step 8: CI §3.1 and ARCHITECTURE.md §4.1 call the `job` row "a tag
  and an optional string", while CI §3.1 makes the product a
  MessagePack-representable value and TH §1 a text with two times. The
  row is a tag and an optional value — the product, or the failure's
  message. ARCHITECTURE.md is told to the compilation session first.
- Step 8: MS §4.2 and §4.4 name the field checker `check_construct`;
  it becomes `check_fields`. Told to the compilation session first.

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
