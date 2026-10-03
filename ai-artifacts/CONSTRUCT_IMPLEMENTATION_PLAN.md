# Implementation plan: agents, hooks, jobs, the construct tools and `Theorem`

Written 2026-10-03. Nothing of it is implemented. The design is in the
documents under `docs/`; this plan gives only the order of the work,
what each step needs before it starts, the files it touches, what it is
tested with and when it is done. Where a section is cited, the section
is the specification, and the plan repeats none of it. The record of the
decisions is `CONSTRUCT_DECISIONS.md`; what the other sessions' code
offers is in `review/DOC_SYNC_LIST.md`, entries 16, 20 and 22 to 24.

Short names: **CI** = docs/CONSTRUCT_INTERACTION.md, **MS** =
docs/MODULE_STRUCTURE.md, **CH** = docs/CLIENT_HOOKS.md, **RB** =
docs/RENDER_BASELINES.md, **TS** = docs/TOOL_SCHEMAS.md, **TH** =
docs/node_classes/THEOREM.md, **LIP** =
ai-artifacts/LOGGING_IMPLEMENTATION_PLAN.md, **CR** =
ai-artifacts/COMPILATION_REVIEW.md.

Conventions. Every agent-facing sentence is read from the documents by
the baseline tests (`test/baselines.py`), never typed into a test. A
design document changes only through the owner; §4 lists the two
corrections this plan makes to them. A step is done when its tests pass
under `test/harness.py`'s one `isabelle TAT_mcp` per run and `pyright
isabelle_theory_agent` is clean. No `isabelle build`; `lib/tat.jar` is
rebuilt with `isabelle scala_build` after a change to `tat.scala`.
Commits are on `main`, on the owner's word. A sentence marked *(author)*
is a shape this plan chooses where the documents leave one open.

## 1. What each step stands on

| what | whose | state on 2026-10-03 |
| --- | --- | --- |
| the log, the ending object, `isabelle_driver.call`, the tool boundary's records, the Isabelle side's log, `register_callback` taking the callback record (LIP steps 1–6, 8) | the logging session | in, committed (bd48a93, 2e8f6e7, d9472b3), with that session's review fixes uncommitted on top |
| the walk, the setters, the edit's commit block, the store's rows, `owned_slots`, `IsaTerm` in `Isabelle_RPC_Host.unicode` (CR §14 items 1–7) | the compilation session | not started; it waits for the owner's word |
| `compile.py`, `Node.can_emit` / `emit`, the compile hooks' framework side, `isabelle TAT_compile` | the compilation session | not scheduled |
| `hook.py`, `guard.py`, `configure`, the Codex sandbox check (LIP steps 9–11) | the logging session | waits for step 2 here |

What the compilation session's code will hold of this design, as it
told this session on 2026-10-03: `Evaluation` with `starter`, `checks`,
`passed` and `dropped` as fields, `passed` filled by the walk and the
other three unused; the setters without the three lines that concern
jobs. Everything else of the jobs is this plan's, those three lines
included.

The division with the logging session (DOC_SYNC_LIST entry 16, and its
answers of 2026-10-03): this plan builds the client machinery of CI §4,
§7 and §8 — steps 1 to 3 and the two rules of step 8 — and `fork_job`
with its records whole (step 6); the logging session builds `configure`,
the two scripts and the sandbox check on step 2's subclasses, and
reviews step 6 against LOGGING.md §4 (the owner confirmed step 6's
division on 2026-10-03, LOGGING_DECISIONS.md). `ClientRefused` and the
branch of `stopped()` that answers a refusal's own line are built in
step 2, which raises the first refusal; the logging session adds the
sandbox check and its line on the same class (agreed with it on
2026-10-03).

The order. Steps 1 to 4 need only what is in. Steps 5 to 9 need the
compilation session's CR §14. Step 10 needs CR §14 and, for emission
alone, the compile round. Step 11 needs the owner's rulings of §3. Step
12 is one run shared with LIP step 13.

## 2. The steps

### Step 1. `-c`: the client's name from the command line to the server

Needs: nothing more than what is in.

Build. `TAT_mcp [-c CLIENT]` and its refusal (MS §5); the name carried
as one more argument of `TAT.boot` and `TAT.start`, through `start` to
`launch_TAT` (MS §2.6 step 5 and its last paragraph; MS §4.6
`toplevel.py`) — the boot's dispatch on its first argument is the
compile round's, and this step adds none; `toplevel.served()` choosing
the `TAT_Server` subclass by the name and the `start` record carrying it
(CI §8; LOGGING.md §4 `conversation`). The two subclasses, each stating
the `clientInfo.name` it expects and the version its facts were measured
on (MS §4.6; CI §8); *(author)* their class names are
`Claude_Code_Server` and `Codex_Server`. `configure(working_directory)`
is declared on the base and called by `served()` before the port is
bound (MS §4.6, the third layer); its body is LIP step 10's. `TAT_new`
writes no client file: `write_hooks` and the six files' texts leave
`tat.scala` (MS §5; CH, the opening).

Files: `src/scala/tat.scala`, `lib/tat.jar`, `ML/TAT_Boot.ML` (its
header), `ML/TAT_Framework.ML` (`TAT.start`, `start'`, `start`),
`toplevel.py`, `mcp_server.py`, `test/harness.py` (its `launch_TAT`
takes the fourth argument).

Tests. `test_launcher.py`: `-c x` is refused with MS §5's sentence and
exit 2; `TAT_new` leaves none of the six files, and the cases on
`HOOK_FILES` and on `.tat/on-compaction.sh` go. `test_toplevel.py`: the
`start` record carries the name; each name selects its subclass.

Done when: `isabelle TAT_mcp -c codex` serves through the Codex subclass
and the suite passes with the default.

### Step 2. `POST /hook`, the announcement, the agents

Needs: step 1.

Build.
- The path (MS §4.6, "The server has one path beside `/mcp`"): `POST
  /hook` in place of `/on-compaction`; `CLIENTS`, `envelope`,
  `unknown_client`, the server's `on_compaction` parameter and
  `mcp.on_compaction` go. The records `hook.request` and `hook.answer`
  (LOGGING.md §4).
- `Agent` (CI §4; MS §4 lists it in `jobs.py`): in this step its
  creation at the first call or hook, its seen set and its working-call
  count; the mailbox, the jobs and the wake-up are step 5's. The
  `Conversation` holds the agents and offers `forget(key)` (MS §4.1;
  PRINT.md §4). The records `agent.created` and `agent.seen`.
- `event_of_hook` (CI §8; CH §1's table), in this step the
  announcement: the call recorded, Claude Code answered the grant,
  Codex an empty answer. Every other hook is answered empty until
  step 3 (compaction) and step 8 (stop, interruption).
- `agent_of_call` (CI §8, "`agent_of_call` never guesses"; CH §2, §3)
  and the unannounced call (EXCEPTIONS.md §1; the record
  `tool.unannounced`).
- The handler (MS §4.6; DOC_SYNC_LIST entry 22): `log.current_call`
  from the call's `_meta`, the subclass naming its client's key, set
  first; `log.current_agent` from `agent_of_call`, before `tool.call`
  is written; neither reset when the body ends; the working-call count
  in a `try/finally` around the body (CI §4). The rule rests on each
  request running in a task of its own, which holds in the SDK in use
  (mcp 1.26.0, `Server.run`: `tg.start_soon(self._handle_message, …)`).
  `/hook` sets `current_agent` to the hook's agent.
- The `clientInfo` check at the first request of an MCP session that
  reaches a handler of TAT's, `tools/list` or `tools/call` (CI §8; MS
  §4.6); `ClientRefused` (EXCEPTIONS.md §3) with RB §4's sixth line and
  the launcher's sentence of MS §4.6; `stopped()` answering a
  refusal's own line, tested before the connection's going; the
  records `client_connected` and `client_refused`, the second written
  where the refusal is raised.
- Rendering for an agent (MS §4.1; CI §6): `Forest.render(node, mode,
  agent)`, the messages' seen-set test reading that agent's set, the
  setter's discard through `Conversation.forget`; *(author)*
  `Tool.run` takes the calling `Agent` beside the arguments — the
  boundary keeps its check that a body returns a text, and `tool.call`
  records the client's arguments alone.
- `recall` with no id renders `Briefing`, and its two descriptions
  become RECALL.md §3's (RECALL.md §2, §3).

Files: `mcp_server.py`, `mcp.py`, new `jobs.py`, `model.py`
(`Conversation`, `Forest.render`, `_print_messages`, the one discard
line — announced to the compilation session, which keeps
`conversation.forget(key)` as the setter's call either way),
`exceptions.py`, `tools/recall.jsonc`, `toplevel.py`.

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
client's name are each refused with the sixth line, an equal and a
higher one served. `test_print.py` and `test_mcp.py`: a message shown
to one agent is shown again to another, `forget` removes a key from
both, `recall` without an id is the briefing with RECALL.md §3's lines;
every `f.render(node, mode)` gains its agent. `test_mcp_server.py`: the
`/on-compaction` cases go.

Done when: the suite passes, and the logging session can write LIP
steps 9 to 11 on the subclasses.

### Step 3. Compaction events

Needs: step 2.

Build (CI §8, "A compaction event" to the two checks; CH §1–§3; MS
§4.6; PRINT.md §4). Codex: `PreCompact`, `PostCompact` and
`SessionStart` as events on the agent the payload names. Claude Code:
at each announcement the agent's transcript — the file, the lines
gained, the `compact_boundary` lines recorded by `uuid`, the changed
`transcript_path` — and the refusal of an agent with no transcript,
with RB §4's fourth line; `PostCompact` counted; the two checks, each a
`TAT_InternalError` with its message, the second's ten seconds waited
in a task spawned on the ending object. The records
`agent.transcript_read`, `agent.compaction`, `agent.check_failed`.

Files: `mcp_server.py`.

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

### Step 4. `Theory`'s `end` built in ML; `run_commands` removed

Needs: nothing more than what is in.

Build (EVALUATOR_DESIGN.md §1; MS §2.4, §3's `Theory` row): the
ML-built `Toplevel.exit` transition; `run_commands` and `run_span`
leave `TAT_Framework`.

Files: `ML/TAT_Framework.ML`, `ML/TAT_Common_Nodes.ML`,
`test/Test_TAT_Framework.thy` — its two tests on `run_commands`, the
run from one slot into another and the two runs under `Future.fork`
whose output must not mix, are rewritten on transitions built in ML.

Tests: those two; `test_session_theory.py` and `test_conversation.py`
unchanged and passing.

Done when: nothing in the repository names `run_commands`.

### Step 5. Jobs on the node

Needs: CR §14 in the tree; step 2.

Build, in `jobs.py` unless a file is named.
- `Construction_Job` (CI §3.2: the table, "The run", "The context") and
  its outcome with the store's image (CI §3.1).
- `Evaluation_Job` (CI §3.3: the table, "The report", "Running and
  dropping"), the process's id counter and id-to-job table, the Python
  remote procedure `job_finished` with its three wire shapes and its
  raise on a `Bug` (MS §2.4), declared with no timeout (CI §3.3, "The
  work").
- `Unfinished` and its three subclasses, `_unfinished()`,
  `Node.check_outcome()` and the stored check (CI §3.1, §3.3; MS §4.1,
  "Status"); `is_finished` and the default mark's four rows over them
  (ARCHITECTURE.md §3.2; PRINT.md §1; RB §5) — `model.py`'s
  `_owes_nothing` and its mark `success` go.
- On `Node` (MS §4.1; CI §3.1, §3.3): the two class attributes,
  `job()`, `attach_evaluation_job`, `start_evaluation_job()`,
  `carry_job_from(old)`.
- The setters' three lines (MS §4.1, "Status"): the stored check
  cleared, `_on_context_change` through `_completed`, the evaluation
  job dropped onto the walk's `dropped`.
- The edit (MS §4.2 steps 3 and 4; CI §3.1, §9): the cancel and the
  drop in the completed events, the carry at the commit, `cancel(ids)`
  after the block; `isabelle_driver.job_cancel` (MS §4.3).
- Messages (CI §3.4): the mailbox, posting, the delivery filter, the
  merging of failures, `Interactive_Question`, `Answered`, `ask`,
  withdrawal; `Agent`'s jobs and wake-up (CI §4).
- The store (ARCHITECTURE.md §4.1; COMPILATION.md §4, "Storage"): the
  rows `job`, `check` and the automatic-construction setting, a missing
  row's reading, each job step's own transaction (EXCEPTIONS.md §1,
  `TAT_DisasterError`).
- The ending (CI §9; MS §4.6): `Ending.end` cancels every running
  construction job and drops every evaluation job, in its one
  synchronous stretch and after the ending is marked entered, so that
  nothing which can raise comes before that mark; a start that failed
  before the forest was built has no forest to walk. A change in the
  logging session's class, told to it first.
- Exceptions (EXCEPTIONS.md §3; RB §2): `ConstructFailed` becomes
  `ConstructionError` with its three children; `BadAnswer`.
- The loader (PLUGIN_SYSTEM.md §2, §5): the job classes a class
  declares and the members it may not override; `plugin.check_construct`
  is renamed `check_fields` (DOC_SYNC_LIST, "Found by the readers", item
  1; §4 below).
- The `job` records (LOGGING.md §4), the run's wrapper setting
  `log.current_agent` to the owner (CI §3.2).

Files: `jobs.py`, `model.py`, `edit.py`, `store.py`, `plugin.py`,
`exceptions.py`, `isabelle_driver.py`, `mcp_server.py` (`Ending.end`).

Tests. New `test/test_jobs.py`, on three job classes of the test
plugin, titled as the documents' examples are so that the baselines
apply: a compulsory construction job `proof construction` whose
question takes `verdict`, `accept` or `reject` (CI §5); the evaluation
jobs `proof check` and `counterexample search`. An evaluation job's
report is the procedure called by the test; the ML side is step 6's.
Cases: each row of CI §3.1's table; a run settling, failing, raising,
and returning after its cancel; a rerun waiting for the earlier run's
task; each cancel reason and its notification; the question's round
trip, a question asked instead, `BadAnswer`, the withdrawals; the
delivery filter's three cases; `_on_context_change` on a rerun; each of
the five drops and the stored check's three clearings, and a rerun that
confirms `Ready` clearing nothing; the carry on an amend, with a
settlement between `gen` and the commit; the rows across a reload; a
report for a dropped id, one carrying a `Bug`, a `_finished` that
leaves `RUNNING`; the ending's cancel and drop making no round trip.
`test/invariants.py`: a settled job's stored image equals its outcome.
`test_exceptions.py` and the tests that pin `(success)`
(DOC_SYNC_LIST, "Tests").

Done when: CI §3.1 to §3.4 hold as written, and the four `test_print`
cases and the `test_exceptions` cases that the end of CR §10 lists as
waiting for this session pass.

### Step 6. The Isabelle side of the evaluation jobs

Needs: step 5.

Build (MS §2.4 `fork_job`, §2.5's environment, §2.6 step 3; CI §3.3,
"The work"; LOGGING.md §4 `isabelle`, §5): `fork_job` with its table
and its report under deferred interrupts; the log captured at the fork,
the records `job_forked`, `job_ended`, `report_undelivered` and `bug`;
`TAT.job_cancel`; `TAT.reset` cancelling the futures first and counting
them in its record.

Files: `ML/TAT_Framework.ML`, `test/Test_TAT_Framework.thy`, the test
plugin.

Tests, through the harness: the test plugin's callback forks work that
succeeds, fails with messages, raises a `Bug`, and is cancelled, and
the test evaluation job settles, fails, ends the conversation, and is
dropped accordingly; a report after `TAT.reset` lands in the log of the
conversation that forked it and is ignored. Verified here, not assumed
(EVALUATOR_DESIGN.md §6): a library theory loaded from source while a
job runs neither waits for the job nor cancels it.

Done when: these pass, and the logging session has read the code
against LOGGING.md §4.

### Step 7. The walk starts jobs; `evaluate_to`

Needs: steps 5 and 6.

Build.
- The walk (CI §3.3, "Where a job starts", "Automatic construction";
  MS §4.1, "The recursion"): the evaluation job started at a passed
  node, the construction started automatically at a passed node and on
  a failed report, `cancel(ids)` at each tree's flush, `blocking`'s
  wait (CI §5, "Every tool result"), `Node.evaluate_to(agent,
  ignore_error, checks)`, an edit's and a move's own evaluation under
  `quick` (MS §4.2 step 4).
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
returns after the passed nodes' jobs end, whoever started them.
`test_mcp.py`: the lines of RB §6 and §3, `checks` absent with no
evaluation job class, a malformed call's lines.

Done when: ARCHITECTURE.md §3.6 and CI §3.3 hold in these tests.

### Step 8. The construct tools, the tool result, the two rules

Needs: step 7.

Build.
- `construct`, `cancel_construct`, `check_construct`, `answer` (CI §5;
  TS §5), their four `.jsonc` files, present only when a construction
  job class is loaded, the two descriptions completed at start,
  `check_construct` read-only (MCP_SPECIFICATION.md §5).
- `edit`'s `auto_construct` (TS §1), written on each new node's job
  after `gen` (MS §4.2 step 1).
- The result (CI §5, "Every tool result"; CI §3.4; MS §4.6, the tool
  handler's third point): the body, the messages taken after the
  checkpoint, the `Automatically started …` line, the trailer — the
  background line, `check_construct`'s state lines; the records
  `tool.result` and `tool.given_up` carrying the messages and the
  trailer, `job.message_delivered` and `job.message_dropped`.
- The stop rule and the interruption rule on `/hook` (CI §7; CH §1's
  second and third rows), with the records `agent.stop_judged` and
  `agent.interruption_judged`.

Files: `mcp.py`, `mcp_server.py`, `edit.py`, `tools/*.jsonc`,
`test/baselines.py` (`stated()` reads TS's per-tool `Tool
description:` lines — DOC_SYNC_LIST, "Tests").

Tests. `test_mcp.py`: every fenced line of CI §5 and RB §2, §6 that
these tools render; the node sets, the skipping and the one refusal;
`check_construct`'s four conditions and both clamps; `answer`'s four
refusals; a call given up before the checkpoint leaves the mailbox as
it was. `test_hooks.py`: the stop rule's reason in each row of CI §7's
table against its fenced examples; the interruption denied for a held
agent and for a working call, allowed otherwise.
`test_descriptions.py`: the descriptions with one and with several
titles.

Done when: every sentence of CI §5 and §7 is produced verbatim.

### Step 9. What the jobs print

Needs: step 5; lands with step 8.

Build (CI §6; PRINT.md §1, §2; RB §5): the two tags, the failure
blocks with the colon's rule, the summary under a cut-off nesting node,
the notifications' forms.

Files: `model.py`.

Tests: `test_print.py` against RB §5's blocks, its unpacking adjusted
to the three lines of the tag block, and PRINT.md §2's summary.

Done when: these render byte for byte.

### Step 10. `Theorem`: the statement; `Theory`'s `description`

Needs: CR §14 (`owned_slots`, `IsaTerm` moved); step 4. Emission is
written against COMPILATION.md §3 and runs once the compile round is
in.

Build. `Theorem` as TH §1 to §4, §6's evaluation, §8 and §9:
`STATEMENT_DEFS`, `gen` with its checks and the carry, `is_identifier`
beside `IsaTerm` in `Isabelle_RPC_Host.unicode` (DOC_SYNC_LIST,
"Outside this repository", item 1), `TAT.Theorem.evaluate` with its two
transitions and the `goal_state` slot (MS §3), `reserved_names`,
`print_fields`, the mark's statement slot (TH §7, "The mark"), `emit`
(TH §5). The class names no job class in this step (§3, point 2).
`Theory`'s `description` (SESSION_AND_THEORY.md §2, §4): the field, its
schema line, the store, what it prints.

Files: `theorem_node.py`, `ML/TAT_Common_Nodes.ML`, `model.py`
(`Theory`), `contrib/Isabelle_RPC/Isabelle_RPC_Host/unicode.py`.

Tests. New `test/test_theorem.py`: the schema and the descriptions of
TH §2, §3; `gen`'s refusals from TH §4's fenced lines and RB §2; a
valid and an invalid statement evaluated through the harness, the
`goal_state` slot holding a state exactly while the node is `ready`; a
reserved name recorded; what TH §8's table prints.
`test_descriptions.py`: `Theory`'s `description`.

Done when: a theory of definitions and theorems is built through the
tools, evaluates and prints as the documents say.

### Step 11. `Proof_Job` and `Proof_Check`

Needs: steps 5 to 10; the owner's rulings of §3, points 3 and 4; for
the compile hook, the compile round.

Build (TH §7 whole, §6's last paragraph, §5's `by aoa`; CI §10's first
paragraph; CONSTRUCT_DECISIONS.md §15): the two job classes named on
`Theorem`; `TAT.Theorem.construct` on AoA's `hammer_or_AoA`, extended
in Isa-Mini to return the times; `TAT.Theorem.check` through the
function Isa-Mini exports for the replay of one record; the bound on
concurrent runs; the mark's proof slot; the proof-store compile hook
(COMPILATION.md §5, "Compile hooks").

Measured in this step (CI §10): that TAT's process serves
`IsaMini.AoA`; how soon the Python half learns of an interrupt of the
forked task; that AoA's `group = NONE` forks end with the job.

Tests, in `test_theorem.py`: TH §7's sentences and the eleven lines of
its mark; `_check()`'s table; a construction and a check through the
harness that call no language model — under a scripted driver of AoA's
`test.<name>` kind, or on a goal the proof store or Sledgehammer
closes; which of these is settled when the step starts.

Done when: a `Theorem` is constructed, checked, invalidated and
constructed again in one conversation.

### Step 12. The live run

Needs: steps 1 to 9 and LIP steps 9 to 12; one run per client, the one
of LIP step 13.

The agent adds a theory through the tools, evaluates, compacts, is
stopped and interrupted, and leaves. The measurements the documents
leave to implementation are taken in it: the project-level files' exact
names and an interactive session reading the two transcript `env`
entries from the project settings (CH §4); which request the library
dispatches first after `initialize`, and Claude Code's `server/discover`
probe answered without harm (DOC_SYNC_LIST, "CLIENT_HOOKS.md", item
6b); `features.multi_agent_v2` naming the interruption tool and the
layer `check_for_update_on_startup` is read from
(CONSTRUCT_DECISIONS.md §10, §12); and, of DOC_SYNC_LIST's
"Compaction" item 2, what AGENT_CLIENTS_MEASURED.md does not yet
record. The run's files stay under `ai-artifacts/probes/`, uncommitted,
and no credential is copied into them.

Done when: the conversation's log shows every rule of CI §7 and §8
firing as specified, on both clients.

## 3. For the owner

1. **When the compilation session starts CR §14.** Steps 5 to 11 wait
   for it; that session waits for the owner's word.
2. **`Theorem` between step 10 and step 11.** The owner ruled that
   `Theorem` names no job class until its jobs are built. TH §7's mark
   reads its proof slot from the construction job, and CI §3.1's table
   makes a node without one finished, so in that interval a theorem's
   line has no specified proof slot and a theory of `sorry` theorems
   reads `complete`. Proposed: nothing is committed between the two
   steps, so the interval exists only in the working tree; inside it
   the line shows the statement slot alone. The alternative is a ruling
   on what the line shows.
3. **Three rulings the AoA drive path still needs**
   (CONSTRUCT_DECISIONS.md §15, "Pending the owner"): the environment
   variable's name and the sentence for a
   value that is not a positive integer; how a run waiting for its turn
   shows; what `Theory`'s beginning does when its `Session`'s folder
   cannot be made.
4. **Where `Theorem`'s ML lives.** `TAT.Theorem.construct` calls
   AoA's `hammer_or_AoA`, so the theory that defines it imports AoA's;
   today TAT's theory imports `Isabelle_RPC` alone
   (OPEN_QUESTIONS.md §3 is the same question for the `aoa` method).
   Step 11 needs the answer; step 10 does not.
5. **Two pieces no plan was assigned,** taken here unless the owner
   says otherwise: the tool `evaluate_to` (step 7) and `Theory`'s
   `description` (step 10). The compilation session has no objection.
6. **AoA's own `IsaTerm`.** The compilation session moves TAT's class
   into `Isabelle_RPC_Host.unicode`; replacing the wider class in
   Isa-Mini with it is a change there, which that session puts to the
   owner.

## 4. Corrections to the documents, made when the step lands

- Step 5: CI §3.1 and ARCHITECTURE.md §4.1 call the `job` row "a tag
  and an optional string", while CI §3.1 makes the product a
  MessagePack-representable value and TH §1 a text with two times. The
  row is a tag and an optional value — the product, or the failure's
  message. ARCHITECTURE.md is told to the compilation session first.
- Step 5: MS §4.2 and §4.4 name the field checker `check_construct`;
  it becomes `check_fields`. Told to the compilation session first.

## 5. Not in this plan

The AoA round's remainder (CI §10, "Still the round's"): the question
kinds, AoA being told it runs under TAT, a construction that continues
through a context change. The node classes of OPEN_QUESTIONS.md §1.
Nothing is built for an agent that left with jobs running (CI §7's last
paragraph), for progress notifications (CI §8), or for the two items
CONSTRUCT_DECISIONS.md §12 lists as pending that belong to withdrawn
designs — M6 and the slot-release order.
