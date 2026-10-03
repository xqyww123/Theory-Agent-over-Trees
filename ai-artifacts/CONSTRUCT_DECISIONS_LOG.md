# The owner's decisions on `construct`, the interaction with the agents, and `Theorem` (2026-09-22 to 2026-09-28)

A record, not a design document: every item below the owner decided in
conversation, one line each, no rationale. The design documents are
written from this file once the open items (§7) are settled. Facts
measured on the way are in AGENT_CLIENTS_MEASURED.md. Agent-facing
sentences appear here only when approved.

Superseded on 2026-09-30 by CONSTRUCT_DECISIONS.md, the consolidated
record, which also carries the corrections of the audit of that day
(ai-artifacts/review/DROPPED_DECISIONS_AUDIT.md). Where this file and
that one differ — the `_on_context_change` default (§2 here), "invalidate,
then evaluate" (§5), the evaluation job's outcome "never stored" (§5),
`by <stored method text>` (§5) — CONSTRUCT_DECISIONS.md is right; this
file is kept as it was written.

## 1. Premises

- One `isabelle TAT` process serves one working directory and **one agent
  client process** (Claude Code or Codex; no other client for now). That
  process's main conversation and all its subagents are the agents; two
  client kinds never share a TAT.
- TAT's lifetime is an external manager's: when the client process ends,
  the manager terminates TAT (SIGTERM, so the ending runs). TAT neither
  detects the client's death nor exits on its own.
- Subagents' parents are not recorded or maintained.

## 2. Objects

- **Construction job.** A node holds at most one; a node class with a
  construction behaviour creates the job in its `__init__` and returns it
  from `job(self) -> Construction_Job | None` (not abstract; default
  `None`).
  The job is a `Construction_Job` subclass instance.
- **Agent.** A framework object per agent: its mailbox, its jobs, its
  block count. Identity: Claude Code — `(session_id, agent_id)` from the
  `PreToolUse` announcement, `agent_id` empty for the main conversation;
  Codex — the thread's id from `_meta` (subagent thread not yet measured).
- **Message.** A notification or a question, addressed to the job's
  owner, holding its text. A question is one `Question(text, schema,
  check)`. A job has at most one pending question; while it waits, no
  other message of that job arrives.
- `Outcome`: `NOT_STARTED`, `RUNNING`, `SUCCEEDED`, `FAILED(message)`
  (§11). Persisted by the framework (like `kind`) at every change, the
  store's image of `RUNNING` being `NOT_STARTED`. `start` sets `RUNNING`,
  the run's settlement `SUCCEEDED` or `FAILED`, `cancel` `NOT_STARTED`.
  `Theorem`'s `proof` is this outcome under `Theorem`'s name, not a
  field of its own (ARCHITECTURE §2.2 changes accordingly).
- `compulsory`: a job attribute. `Node._owes_nothing` is renamed
  `_is_self_complete`; its default: no job, or the job not compulsory, or
  its outcome `SUCCEEDED`. `Theorem` no longer overrides it (ARCHITECTURE
  §3.2's table gets one generic row). Compulsory feeds only the forest's
  completeness, never the stop hook.

`Construction_Job` (the names the owner fixed; the rest told, §5):

| member | who | what |
| --- | --- | --- |
| `title()` | class, public, abstract | `Theorem`: `proof construction` |
| `_run()` | class, hook | the work; returns the outcome |
| `_cancel()` | class, hook | stops the work; also the destructor at TAT's ending |
| `_on_context_change()` | class, hook | called on **every** change of the node's own evaluation status while the job runs; default: cancel with `CONTEXT_CHANGED` unless the new status is `ready` |
| `ask(question)` | framework | delivers the question, suspends until an accepted answer, returns it |
| `start(owner)` | framework | refuses if `RUNNING`; runs the class's check; sets `RUNNING`; launches `_run` as a background task |
| `cancel(reason)` | framework | cancels the task, `_cancel()`, sets `NOT_STARTED`; a reason means the framework cancelled and notifies the owner |
| eight wording methods | class, public, overridable defaults | `starting_notice`, `cancelling_notice`, `running_refusal`, `not_running_refusal`, `owned_by_another_refusal`, `no_question_refusal`, `finished_notification(outcome)`, `cancelled_notification(reason)` |

- `Cancel_Reason`: `NODE_DELETED`, `NODE_AMENDED`, `CONTEXT_CHANGED`.
- On amend the old node's running job is cancelled (`NODE_AMENDED`); the
  class's `gen` may carry the old job's outcome (and its own result) into
  the new job — `Theorem` does when the statement is unchanged; what is
  carried is the store's image (`RUNNING` as `NOT_STARTED`).
- The framework refuses `start` only while running; every other
  precondition is the class's, raised as its own `ConstructionError`
  subclass.
- The whole `Outcome` is persisted (`Failed.message` included), as one
  framework column: a tag and an optional string; `RUNNING` is written
  as `NOT_STARTED` (ARCHITECTURE §4.1: work in flight is not stored), so
  a `start` clears the previous failure.
- Exceptions: `ConstructionError` (abstract, replaces `ConstructFailed`;
  job classes derive their refusals from it) with six framework children:
  `ConstructNotSupported`, `ConstructAlreadyRunning`,
  `ConstructNotRunning`, `ConstructOwnedByAnother`, `NoQuestionPending`,
  `BadAnswer`. Which tool failed is the `opr` field's `Cannot <tool>
  <id>` line, never a class.
- The context-change hook fires from `_set_status`, independent of the
  node's `on_invalidated`.
- The class's synchronous start check is `_check()` (default empty),
  called by the framework's `start` before the task is launched.
- The mark's words are the job's: a job method returns the word for its
  four outcomes (`RUNNING` / `SUCCEEDED` / `NOT_STARTED` / `FAILED`;
  `Theorem`: `proving`, `proven`, `no proof`, `bad proof`), and
  `Node.mark`'s default writes it where the framework's rows are silent.
  `Theorem` overrides neither `mark` nor `_is_self_complete`.

## 3. Tools (all approved)

| tool | schema | description |
| --- | --- | --- |
| `construct` | `{node_id}` | `Start a node's own construction job, such as the proof of a theorem` |
| `cancel_construct` | `{node_id}` | `Cancel a node's running construction job` |
| `check_construct` (renamed from `wait_construct` 2026-09-28) | `{wait_seconds: integer}`, required; `The time to wait at most, in seconds; the call returns earlier when a message arrives or every job has finished` | `Wait until every construction job you started has finished, or one of them has a message for you` |
| `answer` | `{node_id, answer}`; `answer` a bare object, replaced at run time by the question's schema and checked with the existing checker | `Answer the question a construction job asked you` |

Field descriptions: `The id of the node whose construction job to start`
/ `… to cancel`; `The id of the node whose construction job asked the
question`; `The answer, in the shape the question asked for`.

- `status` is removed. Messages travel only on tool results and
  `wait_construct`.
- `construct` acts on one node; no class-specific arguments.
- `check_construct` returns when every job of the caller's has finished,
  or any message for the caller arrives (questions always interrupt;
  notifications carry an interrupt flag the job class sets), or
  `wait_seconds` elapse; it returns every accumulated undelivered
  message; with a pending question it returns at once, re-delivering the
  question; with no job it is refused. TAT clamps the wait to its own
  ceiling (set with the client's timeout in `configure`) and, silently,
  waits at least 3 seconds even for `0` — neither appears in the schema
  or descriptions. A timeout return has the same shape as an interrupted
  one (`… is still running.`).
- No `Question:` header; the question's text is never printed under the
  node — the tag sends the agent to `check_construct`. Under the node,
  when detailed and the outcome is `FAILED`, only the job's failure block
  is printed, for everyone, after `print_fields` (§11): the job's
  `failure_header(failure) -> str | None` (abstract; `None` prints
  nothing) then the message one level deeper. `Proof_Job`
  (`Theorem`'s job class): `No proof was found:` when the search gave up,
  `The proof no longer holds:` when a stored proof failed to replay —
  which it is, `Proof_Job` records in a field of its own. Replay failure
  is recorded through `job.fail(message)` (framework method, callable
  only while the job is not running) from `Theorem._eval_opr`; the ML
  side falls back to `sorry` in the same round trip.
- `answer` and `cancel_construct` are the owner's alone.
- Failures of `construct`, `cancel_construct`, `answer` open with
  `Cannot <tool> <node id>` (the `opr` mechanism); `wait_construct`
  renders the cause alone.
- Tool errors: `TAT_Error` → rendered, `isError`; anything else → the
  conversation's ending. A bug in `_run` → the ending too.

## 4. Wording (approved unless marked)

Framework:

- `wait_construct` last line, per title, singular `on` repeated:
  `Your proof construction on \`X\` and on \`Y\` has finished.` /
  `… is still running.` / `… is waiting for your answer.`; empty set:
  `Every construction job of yours has finished.`; no job:
  `You have no construction job running.`
- Question delivery: `The proof construction on \`<full id>\` asks:` +
  the job's text + `Answer with the \`answer\` tool, node_id \`<full id>\`;
  the answer must follow the JSON schema:` + the schema, complete,
  multi-line. No `Question:` header. Printed under the node's line when
  detailed (open: modes, §6), to the owner only.
- Tag `needs your answer, call \`check_construct\` to see it`, appended
  to the mark with a comma, on the node's line in every rendering, **to
  the owner only**, until answered. `starting_notice` ends `call
  \`check_construct\` before you exit.`; the hook reason says `call
  \`check_construct\` and answer their questions before you exit.`
- Hook block reason (G22): `Your proof construction on \`X\` and on \`Y\`
  have not finished; call \`wait_construct\` and answer their questions
  before you exit.` (singular `has`). Parent fallback (G23): `The
  subagent left its proof construction on \`X\` and on \`Y\` unfinished;
  they were cancelled.`
- `\`<id>\` has nothing to construct.` (no job).
- Answer shape errors: the existing checker's sentences with the root
  `answer` (`The argument \`answer.verdict\` must be one of …`).

Defaults from `title` (approved, except the last sentence):
`Started the proof construction on \`X\`; call \`wait_construct\` before
you exit.` / `… is already running.` / `Cancelled the proof construction
on \`X\`.` / `… is not running.` / `… is another agent's.` / `… has no
question waiting for an answer.` / `… succeeded.` and `… failed:` +
message / `… was cancelled: the node was deleted.` / `… amended.` /
`… its context changed.`

`Theorem` (approved): kinds `lemma`, `theorem`, `corollary`,
`proposition`; marks `proving`, `proven`, `no proof`, `bad proof`; schema
`{kind, name, statement}`, `statement` = the shared `LongStatement`
(`STATEMENT_DEFS`: `Variable`, `LongStatement` copied from AoA), no
description on the class or on `kind`; descriptions: `name` `The fact's
name`; `english` `the statement in English, as LaTeX text`; `for_any`
`universally quantified variables to fix`; `Variable.type` `An Isabelle
type expression. Leave empty ("") if unsure`; `premises` `named premises
to assume`; `premises[].name` `binding name for the premise`;
`premises[].term` and `conclusion` `Isabelle/HOL term with all literal
numbers annotated with types`. `Theorem`'s own sentences (approved):
`\`X\` must be evaluated before its proof can be constructed.`, `\`X\` is
already proven.`, `\`X\` is proven.`, `No proof of \`X\` was found:`.

## 5. Emission and evaluation of `Theorem` (approved)

- `.thy`: `text ‹Lemma <name>. <english>›` (kind capitalised; a period
  added when `english` ends without `.`/`!`/`?`; `‹`, `›` and their ASCII
  forms in `english` replaced by `"` at emission, nothing refused), then
  the statement, then `by aoa` when `proof` is `proven`, else `sorry`.
- Evaluation does not run the `text` command; it runs the statement with
  `by <stored method text>` when proven, else `sorry`.

## 6. Agents, hooks, the server

- The client is chosen per launch: `isabelle TAT -c <client>`, default
  `claude-code`. `TAT_new` writes no client files; the server writes them
  at launch (`configure(self, working_directory)`), Scala's `write_hooks`
  goes.
- `TAT_Server` has one subclass per client; the subclass implements
  `configure`, `agent_of_call(context: RequestContext) -> Agent`,
  `event_of_hook(request: Request) -> Hook | None`, the envelope and the
  stop policy. The hook endpoint is generic; `/on-compaction` folds into
  it.
- Claude Code: a `PreToolUse` hook (matcher `mcp__tat__.*`) announces
  every call (`tool_use_id`, `session_id`, `agent_id`, `agent_type`);
  `agent_of_call` matches `_meta["claudecode/toolUseId"]`. Codex: the
  thread id in `_meta` (pending measurement for subagent threads).
- `SubagentStop`: block while the agent has running jobs (reason G22).
  The main conversation's `Stop`: the same rule (§7.B). `SessionEnd`:
  cancel every job. An agent TAT knows to have left with a job running:
  §12's internal error (the ninth-stop release and G23 of 2026-09-27 are
  withdrawn).
- Codex hooks need `--dangerously-bypass-hook-trust` (config equivalent:
  pending) and `default_tools_approval_mode = "approve"` on the server
  entry.
- `configure` sets `CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS=0` (no automatic
  backgrounding of `wait_construct`); the stall timeout value is open.
- `Briefing` never calls `print_fields` (framework rule); SESSION_AND_THEORY
  §4 loses its `Briefing` row.
- `TAT_AGENT` / `X-TAT-Agent` are dropped (single process).

## 7. Open — awaiting the owner

A. Wording: all approved (the `… its context changed.` sentence too).
Pending in THEOREM.md: the underscore sentence of §4 (§10); §6, to be
rewritten after the review's A4 (D); in §8, the proposition on one line
with whitespace runs collapsed, and `english` as written with every line
at the field indent; §9 id properties; `Proof_Job`'s two failure headers
(§3).
B. Rules (decided 2026-09-28: E18 is sent even when the owner
deleted/amended the node itself; E17 interrupts `check_construct`;
`Theorem` prints its statement only under `Recall`, assembled from the
agent's text (§11 has the detail); the main
conversation's `Stop` is blocked under the same rule and fuse as
`SubagentStop`; no fuse of TAT's own — Codex is blocked as long as jobs
run or questions wait, and Claude Code's own eighth-block ceiling is
merely observed; the client files in the working directory are TAT's to
write whole — everything under the working directory is TAT's):
`Theorem`'s `gen` checks, evaluation callback, id properties (the
draft's). Decided 2026-09-28: TAT's tool calls get a twelve-hour limit
(`configure`: Claude Code per-server `timeout` 43200000 ms, Codex
`tool_timeout_sec` 43200); `check_construct` clamps `wait_seconds` to a
minute less; the subagent stall watchdog is left alone (measured: a tool
call's wait does not count toward it).
C. Measured 2026-09-28 (AGENT_CLIENTS_MEASURED.md): Codex subagent
`_meta.thread_id`; Codex hook-trust config equivalent (none); Unicode
terms (rejected unconverted). To measure, from the review: M1 the
`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` variable under TAT's launch; M2 which
hook fires when a foreground subagent is interrupted, stopped,
stall-killed or ends by `maxTurns`, and whether a background subagent's
end has an event; M4 the hook command's current directory; M5 whether
`SessionStart` reaches TAT under `--dangerously-bypass-hook-trust`; M3
only if P2 is declined; M6 at implementation.
D. The review (2026-09-28, `review/CONSTRUCT_RULING.md`): verdict
NOT_READY; every owner question of it is answered in §11 and §12
(2026-09-29): A3 yes; A4 and Q2 lapsed; A5 → `You have no job
running.` as a plain result; A6/P2 adopted; A8/P3 declined; A9 →
internal error; A10 → `Interactive_Question`; P1 adopted; P4 reduced;
P5's last two parts adopted; P6 adopted.
E. Decided 2026-09-29, **the evaluation job's shape and start path**
(supersedes §12's "ML side" bullet; the `create` remote procedure goes):
`Evaluation_Job.__init__(node, starter | None)` sets `node`, `starter`,
`id` (the framework's counter) and `outcome = RUNNING`; `outcome`
(`RUNNING`, `PASSED`, `FAILED(message)`) is written by the class alone,
the framework only reads it; abstract class methods `title(plural)` and
`start(node, starter) -> Self` (construct, begin the work through the
class's own ML callback — `Proof_Check`: `TAT.Theorem.check`, which
forks and returns — and return the instance); `_finished(errors)`, a
hook the framework calls under the lock on the ML report `finished(id,
errors)`, default `PASSED` on no errors else `FAILED(errors joined by
newlines)`, after which the framework posts `failure_notification` to
the starter on `FAILED` and wakes the starter; abstract `failure_header`,
`failure_notification`. Framework: `Node.start_evaluation_job()` =
`attach(await cls.start(node, caller))`, called from the walk where
`_incompleteness()` would answer `Unchecked`, at the node's last
operation when `ready` and `checks` allows; `Node.attach_evaluation_job
(job)` attaches, dropping the old one; dropping interrupts through
`cancel(id)`. No `_settle`, no `record_evaluation_job`, no
`_start_evaluation_job` on `Node`. **After a construction job succeeds
the framework does nothing**: `Proof_Job._run` ends by
`attach_evaluation_job(Proof_Check.passed(node))` — a `Proof_Check`
class method building an instance with `outcome = PASSED` — since with
the default `_on_context_change` a run that reaches its end saw no
context change; the AoA round's continuing job replays instead
(`start_evaluation_job()`) and repairs by the result. `proven` means
"a `PASSED` evaluation job is on the node" everywhere.
F. Decided 2026-09-29, **titles at class level and `check_construct`'s
description**: `title(plural)` is a class method on both job kinds
(§12's "instance method" withdrawn); a node class names its
construction job class in the class attribute `construction_job_class`
(default `None`), parallel to `evaluation_job_class`, and the framework
builds the instance (`cls(node)`) when the node is built — `job()`
returns it, the class no longer builds it in `__init__`. The four
construct tools are built only when a loaded class names a construction
job class, as `checks` exists only when one names an evaluation job
class. `check_construct`'s return condition "none of its kind left" is
per title. Its description is completed at start: `Wait until any of
your {construction titles} or all of your {evaluation titles} have
finished, or a message arrives for you` — each slot's titles distinct,
alphabetical, joined with commas and `or` before the last; the
`or all of your …` part absent when no evaluation job class is loaded.
Final wording (approved 2026-09-29, `your` dropped throughout): `Wait
until any {construction titles, singular} or all {evaluation titles,
plural} have finished, or a message arrives. Returns at once when
nothing is running. To ensure all jobs have finished, call it
repeatedly.` — with `Theorem` alone `Wait until any proof construction
or all proof checks have finished, or a message arrives. Returns at once
when nothing is running. To ensure all jobs have finished, call it
repeatedly.` The state lines drop `Your`/`of yours` likewise (approved):
`The proof construction on \`X\` is waiting for your answer.` / `The
proof construction on \`X\` and on \`Y\` is still running.` / `The proof
check on \`X\` is still running.` / `The following proof constructions
are still running:` + ids / `All proof constructions have finished.` /
`All proof checks have finished.` (per title; replaces `Every
construction job of yours has finished.`). Decided 2026-09-29: the
nothing-running line is `No job is running.` (replaces `You have no job
running.`); `Theorem` emits `sorry` while its proof check is `FAILED`,
`by aoa` in every other `SUCCEEDED` case.

## 8. Deferred to the AoA round

The drive path (`by aoa` through `run_commands` vs `raw_AoA`), driver and
budget, the proof store, the question kinds, cancellation on the AoA
side, `Theorem` overriding `_on_context_change` to continue and repair.

## 10. Decided 2026-09-28, late

- `TAT.Theorem.evaluate` goes through the ML interfaces, not
  `run_commands`: `Named_Target.theory_init` on the input slot's theory,
  `Specification.theorem_cmd` (statement failure = its exception),
  `Proof.global_skip_proof true` or `Proof.global_terminal_proof`
  (proof failure = its exception, then `sorry` in the same call),
  `Local_Theory.exit_global`, the state written back to the slot; the
  execution envelope of `run_span` (exec id, output routing, fork join)
  factored out and reused. Python sends the structure (kind, name,
  fixes, assumes, shows, proof method or none), converted to `\<name>`
  form; the Isar text is rendered only for emission. **`run_commands` is
  to be avoided**: it stays for `Theory`'s header and `end` only.
- How the resulting `Toplevel.state` is rebuilt — `Toplevel.make_state
  (SOME thy')` or a transition — pending measurement (an Opus probe).
- `for_any` names must not end with an underscore; sentence (approved
  2026-09-29): `The field \`statement.for_any[0].name\` must not end
  with an underscore.`
- Measured 2026-09-28 (`ai-artifacts/probes/toplevel_state_rebuild/`):
  after a direct-ML `lemma` (theory_init → theorem_cmd →
  global_terminal_proof / global_skip_proof → exit_global) every way of
  rebuilding the `Toplevel.state` lets the next `lemma` (using `p1`),
  `end` and `Toplevel.end_theory` succeed; differences: (A)
  `make_state (SOME thy')` loses `previous_theory_of` (NONE) and the
  presentation context (level 0), so a following `print_theorems` lists
  the whole theory instead of the new facts; (B2) two transitions —
  `Toplevel.local_theory_to_proof'` then `Toplevel.end_proof` through
  `Toplevel.command_errors true` — reproduces the real span's state
  exactly (previous theory a proper extension, presentation context at
  level 1); (B1) one `Toplevel.theory` transition keeps a previous
  theory but no local presentation context. `Toplevel.empty` needs no
  name or position. Statement and proof failures come from
  `theorem_cmd` and `global_terminal_proof` respectively, same texts as
  the real spans minus the position suffix. **Choice: B2.**

## 11. Decided 2026-09-28, after the review

- **Printing a `Theorem`.** Its statement is printed only under `Recall`:
  at depth 0 and 1 two lines, the proposition in Isabelle's meta form
  first, `english` second, no leading keys; at depth 2 the proposition
  alone; nothing at depth 3, in `Out_Focus`, or as a focus of
  `Relative_Focus` — there only its errors and its job's block. Errors
  follow `Theory`'s rule and come after the statement.
- **The job's failure block** is printed by the framework after
  `print_fields`, not before; when detailed; while the outcome is
  `FAILED`; never under a node that is itself an obstacle (§12).
- **`Theory`'s `imports`** likewise only under `Recall`: the
  `Relative_Focus` focus row of SESSION_AND_THEORY §4 becomes errors
  only. Whether `Session`'s three fields follow: open (§7.D).
- **`Outcome` is four-valued**: `NOT_STARTED`, `RUNNING`, `SUCCEEDED`,
  `FAILED(message)`. `start` sets `RUNNING`; the run's settlement sets
  `SUCCEEDED` or `FAILED`; `cancel` sets `NOT_STARTED`. The store's image
  of `RUNNING` is `NOT_STARTED` (ARCHITECTURE §4.1: work in flight is not
  stored), written at every change of the outcome, so a `start` clears a
  previous failure; `Theorem.gen`'s carry on amend is the store's image.
  "Cancel returns to the outcome before the run" is withdrawn. For the
  AoA round: during a run the previous outcome is no longer on the node;
  a repair of a broken proof would need `start` to hand it to `_run`.
- (Withdrawn 2026-10-02: past every destination the walk marks to the
  tree's end; no fifth mode; the test stays. CONSTRUCT_DECISIONS §8,
  §14.) **Invalidation past the destination** (the review's A3; ARCHITECTURE
  §3.5 changes): when the walk reaches the destination without having
  rerun it and without arriving blocked, the nodes past it are left as
  they are; otherwise they are marked `not_evaluated` as before. An
  edit's invalidation is unchanged. Implemented as a fifth walk mode
  meaning "past the destination, touch nothing" (named by the author);
  `test_evaluate_to_inside_an_import_invalidates_its_importers_whole` is
  inverted.

## 12. Decided 2026-09-28, the proof-check round

- **Evaluation never replays a proof.** `TAT.Theorem.evaluate` runs
  `theory_init |> theorem_cmd … |> global_skip_proof true |> exit_global`
  as direct ML under `Exn.capture` (interrupts re-raised), then
  `Toplevel.make_state (SOME thy')` into the slot; any failure is the
  statement's: obstacle, `errors`, no state. §10's "Choice: B2" and the
  `run_span` envelope are withdrawn; `run_span` is untouched;
  `run_commands` stays `Theory`'s alone. `job.fail` and the replay flag
  are gone.
- **`Evaluation_Job`**: a framework ABC for background work an
  evaluation spawns. A node class names its subclass in a class
  attribute (default `None`); `Theorem` names `Proof_Check`. At most one
  per node. `title(cls, plural: bool = False)`: `proof check` /
  `proof checks`. Its `outcome`: `RUNNING`, `PASSED`, `FAILED(message)`,
  never stored. The construction job's `outcome` is not written by it;
  both attributes are named `outcome`.
- **ML side**: the class's evaluation callback forks the work on a thread
  of its own and returns; the framework's ML half offers `start` (calls
  Python's `create` remote procedure, forks, calls `finished(id, errors)`
  on completion) and one callback `cancel(id)`. No time limit in the
  framework: the implementer bounds its work. No new registry:
  callbacks through the existing table, remote procedures through
  Isabelle_RPC's. A `finished` whose id matches no attached job is
  discarded.
- **The `evaluate_to` schema** (approved): `node_id`, required, `The id
  of the node to evaluate up to, with its subtree; a theory's id means
  the whole theory.`; `ignore_error`, optional, `Whether to carry on past
  a node that fails, so the nodes after it are evaluated too. Default:
  false.`; `checks` (renamed from `check_proofs`; approved), optional,
  enum `"no"`, `"quick"`, `"blocking"`, default `"quick"`. The grammar
  has no `default`, so a description states it as `Default: …`. `checks`
  is completed at start, where `edit`'s schema is: its description is
  the template
  `Whether to run the {titles} of the nodes: "no" runs none; "blocking"
  runs them and waits for them to finish before the call returns;
  "quick" runs them in the background, and you may wait for them with
  \`check_construct\` or go on (a failure will be reported to you, a
  success is silent). Default: "quick".` with `{titles}` the
  `title(plural=True)` of every `Evaluation_Job` class the loaded node
  classes name, distinct titles only, in alphabetical order (the author's
  choice: independent of plugin order), joined naturally (`proof checks`;
  `proof checks and counterexample searches`; commas and `and` beyond
  two); when no class names one, the property is absent. The background
  line groups its counts by title the same way. A check starts on every
  node the walk passes that has a stored proof and no evaluation job.
  `blocking`: the call waits for the checks it started, holding the lock.
  `quick`: returns at once; checks run without the lock and settle under
  it. `edit`'s and `move`'s own evaluation (`evaluate: true`) uses
  `quick`, without a parameter, and their results carry the background
  line like any call that ran an evaluation (approved).
- **Cancellation**: leaving `ready` drops the node's evaluation job; a
  rerun is "invalidate, then evaluate" — the walk marks the node
  `not_evaluated` before rerunning it — so one rule cancels both job
  kinds; delete and amend likewise; no pre-traversal. (To check in the
  code: the order of the slot release and the rewrite.) Messages are
  filtered at delivery: one whose job is no longer on its node is
  dropped; cancellation scans nothing.
- **Messages are generic**: recipient, text, interrupts, optional
  question, optional job; anything may post. An evaluation job's failure
  is a non-interrupting message to the agent whose call started it,
  `The proof of \`theory_X.lemma_P\` no longer holds:` + the errors
  indented; success is silent.
- **`check_construct`** returns on a condition, judged when the call
  starts and again whenever the caller's mailbox or jobs change (a job's
  settlement triggers the agent's wake-up; no pseudo-message): an
  interrupting message; a pending question; a job of the caller's has
  just settled and none of its kind is left running; the deadline.
  Neither kind running at the start: at once. The state lines say what
  stands at the return, `Every proof check of yours has finished.` among
  them beside `Every construction job of yours has finished.`. Description: `Wait until every construction
  job and proof check of yours has finished, or a message arrives for
  you`. The sentence for nothing running of either kind: proposed `You
  have no job running.` The stop hook blocks while the caller has
  evaluation jobs.
- **The background line**, after a call that ran an evaluation and in
  `check_construct`'s result, nowhere else; the caller's running
  evaluation jobs, grouped by class: `3 proof checks are running in the
  background.` / `1 proof check is running in the background.` /
  `3 proof checks and 1 counterexample search are running in the
  background.`; the first time per agent (seen set): `3 proof checks are
  running in the background; call \`check_construct\` to wait for them.`
- **`_is_self_complete` becomes `_incompleteness() -> Incompleteness |
  None`** (approved). `Incompleteness` is the framework's abstract base
  with `sentence()`; three subclasses: `Construction_Incomplete(job)` (the
  construction job's outcome `NOT_STARTED`, `RUNNING` or `FAILED`),
  `Check_Incomplete(job)` (the evaluation job's outcome `RUNNING` or
  `FAILED`), `Unchecked(job_class)` (`SUCCEEDED`, the class names an
  `Evaluation_Job`, none on the node). Sentences from `title()` and the
  outcome: `the proof construction has not started` / `is running` /
  `failed`; `the proof check is running` / `failed` / `has not run`.
  Default: no job or not compulsory → `None`; outcome not `SUCCEEDED` →
  `Construction_Incomplete`; `SUCCEEDED` and no `Evaluation_Job` named →
  `None`; named and `PASSED` → `None`; `RUNNING`/`FAILED` →
  `Check_Incomplete`; absent → `Unchecked`. Overridable; `Theorem` does
  not. Where the sentences are shown: open.
- **`Proof_Job._check`**: not `ready` → `\`X\` must be evaluated before
  its proof can be constructed.`; `SUCCEEDED` with check `PASSED` →
  `\`X\` is already proven.`; `SUCCEEDED` with no check or `RUNNING` →
  `\`X\` already has a proof; check it before constructing another.`;
  check `FAILED` → allowed.
- **Failure blocks per job**: `No proof was found:` (construction
  `FAILED`), `The proof no longer holds:` (evaluation `FAILED`); a node
  that is an obstacle prints no job block.
- **Marks, two slots**: statement `valid statement` / `invalid statement`
  / `not evaluated`; proof `proof not started` / `proving` / `failed to
  prove` / `unchecked proof` / `proof checking` / `proven` / `bad proof`;
  `(invalid statement)` alone; under `not evaluated` a stored proof is
  unmarked; the tag is a third item; `Theorem` overrides `mark`; no
  `success` for `Theorem`. Eleven combinations plus the tag. §4's four
  words are superseded.
- **P4 reduced**: `SUCCEEDED` carries the class's product, an opaque
  string; what `Proof_Job` stores is the AoA round's. The product stays
  on the node when its check fails.
- **An agent that left.** The premise stands: an agent does not leave
  with a job running, because the stop hook holds it; TAT builds no
  other detection, keeps no timeout, and does not use the parent's
  hooks. Where TAT knows the premise was broken — Claude Code's
  ninth-stop release while P2 is declined; nothing once P2 is adopted —
  it raises `TAT_InternalError` and the conversation ends (message,
  internal: `Agent <id> left with jobs running: the proof construction
  on \`X\`, 3 proof checks.`). Accepted imperfection: the client
  behaviours that bypass the hook (measured 2026-09-28, both clients:
  Claude Code's Escape, `TaskStop`, stall watchdog, `maxTurns`; Codex's
  `interrupt_agent`, session end, SIGINT, Escape) are invisible to TAT
  and not designed for — the departed agent's jobs run on and settle on
  the forest, its messages stay undelivered, a search stuck on a
  question stays until delete, amend or `SessionEnd`. P3 is declined;
  `answer` and `cancel_construct` stay the owner's. The ninth-stop
  cancellation and G23 are withdrawn.
- **The framework's mark** (PRINT.md §1 rewritten; approved): `finished`
  → `complete` (replaces `success`); an own obstacle → `failed`; an own
  `not_evaluated` → `not evaluated`; own operations ran but not
  `finished` → `incomplete`. No line is ever bare. `Theorem` keeps its
  two-slot mark. `Session`: `complete` or `incomplete` by its trees.
- **The summary under a cut-off nesting node** (the outlet of
  `Incompleteness`; approved): in `Recall`, under an `incomplete` nesting
  node at the last printed depth (3), one line per group, tree order: the
  nodes below it grouped by the title of the job their `Incompleteness`
  carries (`Unchecked` by its class's), plus one group each for nodes
  `failed` and `not evaluated`; up to 5 ids written out (relative to the
  node), more than 5 the count alone; no trailing period:
  `3 proof constructions incomplete: lemma_A, lemma_C, context_C.lemma_B`,
  `12 proof checks incomplete`, `1 node failed: definition_f`, `2 nodes
  not evaluated: lemma_E, lemma_F`. Not in quickviews or the briefing.
  `Incompleteness` needs no `sentence()`: the summary uses titles.
- **`check_construct`'s state lines and the stop hook's reason** (one
  renderer; approved): the caller's jobs grouped by title and situation
  — a construction job `waiting for your answer` or `still running`, an
  evaluation job `still running` — each node once; up to 3 nodes as one
  sentence with `on` repeated (`Your proof construction on \`X\` and on
  \`Y\` is waiting for your answer.`), more than 3 as a header with the
  plural title and one full id per line (`The following proof
  constructions are still running:` / `  - theory_X.lemma_Q`). The hook's
  reason is these lines plus one instruction composed from what stands:
  `Call \`check_construct\` to see the question{s}[ and to wait for the
  running {titles}]; answer {it|them} before you exit.` or, without a
  question, `Call \`check_construct\` to wait for the running {titles}
  before you exit.`; `{titles}` in their own numbers, construction
  titles first, evaluation titles alphabetical, same titles merged. G22
  is superseded. The background count line stays only on the results of
  calls that ran an evaluation.
- **`title(plural: bool = False)` on both job kinds** (approved):
  `Construction_Job`'s an instance method, `Evaluation_Job`'s a class
  method.
- **`Theorem`'s `Evaluation_Job` subclass is `Proof_Check`** (approved),
  titles `proof check` / `proof checks`.
- **`You have no job running.`** (approved): `check_construct`'s whole
  state section when the caller has, at the call's start, no
  construction job running or waiting for an answer and no evaluation
  job running; a plain result, not an error; undelivered messages follow
  it. Replaces `You have no construction job running.`; the review's Q3
  is answered: no exception class.
- **Fields only under `Recall`, for every class** (approved; PRINT.md §3
  states it once): Session — depth 0 `parent_session`, `options`,
  `description`; depth 1 `parent_session`, `options`; nothing deeper or
  in any other mode. Theory — `imports` at depth 0, 1 and 2, errors in
  every mode. Theorem as §11. A focus writes only errors and its jobs'
  blocks.
- **`Theory` gets a `description` field** (approved): `str`, empty by
  default, authored; schema description `A summary of the theory, as
  LaTeX text`; emitted, when non-empty, as a `text ‹…›` block before the
  `theory` line (Isabelle accepts `text` before the header,
  thy_header.ML:180–193), `‹`/`›` and their ASCII forms replaced by `"`,
  the content as written, no period added; never run by the evaluator;
  printed at `Recall` depth 0 only; an amend that changes it re-evaluates
  the theory like any amend.
- **`Theorem`'s text is normalised in `gen`** (approved; closes THEOREM
  §8's two *(proposed)* details): every term (`for_any[].type`,
  `premises[].term`, `conclusion`) and `english` have newlines replaced
  by spaces and runs of whitespace collapsed to one space, once, when
  the construct is accepted; printing, emission and evaluation all use
  the stored text, so the proposition and the English are one line each
  everywhere. `Session`'s and `Theory`'s `description` stay as written.
- **An unannounced call** (approved 2026-09-29; the review's A9/D27):
  `agent_of_call` never guesses. On both clients every `tools/call` must
  have been announced by its own `PreToolUse` (measured: Codex's precedes
  the call by 5–8 ms, its `tool_use_id` = `_meta.callId`; Claude Code's
  `_meta["claudecode/toolUseId"]`); the identity is the announcement's
  `agent_id` on Claude Code and `_meta.thread_id` on Codex. A call without
  an announcement means the client's hooks do not reach TAT: the
  framework raises `TAT_InternalError` with the message `This call was
  not announced by the client's hooks, so TAT cannot tell which agent is
  calling.` (logged, never shown), the conversation ends, and every tool
  is refused with the ending's `an internal error` line. No per-process
  `SessionStart` fact (Codex's `SessionStart` comes after the MCP
  handshake anyway). The "an unannounced call is the main conversation"
  sentence of CONSTRUCT_INTERACTION §8 is deleted.
- **P2 adopted** (approved 2026-09-29; M1 measured: the variable works):
  `configure` writes `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP: "0"` into
  `.claude/settings.json`'s `env`; TAT keeps no block count, has no
  ninth-stop rule and one stop policy for both clients; the
  internal-error rule for a known departure has no trigger and stays an
  invariant. Also measured: the ceiling only counts blocks with no tool
  call between them. `configure` also writes `check_for_update_on_startup
  = false` for Codex (approved; the TUI's "Update now" dialog swallowed a
  keystroke in a probe), into the project's `.codex/config.toml` if the
  key applies at that layer — to verify at implementation. TAT's hook
  scripts exit 2 only on `Stop`/`SubagentStop` (Codex: exit 2 on
  `UserPromptSubmit` silently swallows the prompt). Consequences of M4
  (author's): the hook commands
  `configure` writes use absolute paths and TAT never reads a payload's
  `cwd` as the working directory; the client must be launched from the
  working directory itself (from elsewhere the project settings are not
  loaded and no hook runs), a premise for §1.
- **`Interactive_Question` and the `answer` tool's result** (approved
  2026-09-29; the review's A10/D28). `Question(text, schema, check)` is
  replaced by the ABC `Interactive_Question` with `text`, `schema`
  (validated against the tool-schema grammar in `ask`; substituted for
  the tool's `answer` property and checked by `check_call` before the
  question sees the value) and the abstract `receive(answer) ->
  Answered | Interactive_Question`: return `Answered(response: str | None
  = None)` to accept — the job's data stays on the question object,
  `response` is the tool's text, `None` the framework default `Answered
  the proof construction on \`X\`; call \`check_construct\` before you
  exit.` (a wording method from `title`); return another question to
  ask instead — it replaces the pending one and is delivered in the same
  tool result in the delivery format; raise `BadAnswer(message)` to
  refuse — the question stays pending. `Construction_Job.ask(question)
  -> None` suspends until some `receive` returns `Answered`. `receive` is
  synchronous, in the tool body, under no lock. `answer` carries no
  quickview. **`answer`'s failures render the cause alone**: the tool
  writes no `opr` (EXCEPTIONS §4's rule: it does not change the forest's
  shape), so `Cannot answer …` never appears; the four refusals' sentences
  name the node themselves. `BadAnswer` derives from `TAT_Error`
  directly; `ConstructionError` keeps five framework children.
- **P1 adopted** (approved 2026-09-29): `_cancel()` is dropped; a
  cancellation is the task's cancellation, and `_run`'s own `try/finally`
  is the cleanup; the ending's destructor is the same cancellation; the
  cleanup never starts a round trip on the ending's path. How AoA stops
  its search on the ML side is the AoA round's.
- **P5's last two parts** (approved 2026-09-29): the tool boundary
  appends the caller's messages after the body's text and then the
  trailer the body asked for — `check_construct`'s state lines, an
  evaluating call's background line — so the state lines come after the
  messages; the per-node `Your proof construction on \`X\` and on \`Y\`
  has finished.` line is dropped (the jobs' own `finished_notification`s
  say it); the `Every … of yours has finished.` state lines stay.
- **P6 adopted** (approved 2026-09-29): the seen set is per agent,
  `Agent.seen: set[Key]` with `Key = tuple[int, str | None]` as today;
  `Conversation.forget(key)` removes a key from every agent's set (the
  evaluation hooks' discard); compaction clears the compacted agent's set
  alone. Rendering reads the agent A11 passes.
- **Author's shapes settled while writing the documents** (2026-09-29;
  told, not owner decisions): the wrapper persists the outcome's image
  under the lock, releases it, awaits the previous run's task, then
  calls `_run`; `cancel` writes nothing (its image is already stored);
  `gen` records the carry and the commit copies the image; `start` drops
  the node's evaluation job; dropping an evaluation job interrupts its
  thread through `cancel(id)`, except on the ending; under `blocking`
  the evaluating call performs its own jobs' settlements while holding
  the lock; messages carry an evaluation job or a construction run and
  are dropped at delivery when that is gone, the framework's own
  notifications carrying none; a question is posted to the mailbox by
  `ask`, and `check_construct` puts it back when it was delivered; the
  background line's first-time key is `(0, "background")`; `SessionEnd`
  cancels every construction job telling no one and drops every
  evaluation job; an `Agent` is created at its first call or hook and
  never discarded; the summary's groups are job titles, then `failed`,
  then `not evaluated`, `ready` nodes only in the title groups; a
  `FAILED` evaluation job's message is the errors joined by newlines;
  the names `evaluation_job_class`, `answered_notice`, `starter`. The
  job's "mark words" method is gone: `Theorem`'s `mark` composes its own
  words. Open, for the owner: after a construction job settles
  `SUCCEEDED`, start the node's evaluation job at once (proposed, so
  that `proven` means checked); `check_construct`'s description
  completed from the titles like `checks`'; emission `sorry` while the
  proof check is `FAILED`; the compaction hook's agent field (measured
  at implementation).
- **Id properties of a leaf** (approved; closes THEOREM §9): a leaf's
  component is always the last of any id, so its properties are never
  consulted; the framework's defaults (`output_omissible = False`,
  `input_omissible = False`, `drop_priority = 0`, model.py:283–285) stand
  and a leaf class declares none. MCP_SPECIFICATION §2.1's "each class
  declares three" becomes "compulsory by default; an omissible class
  declares otherwise".
