# The owner's decisions on jobs, the agents, and `Theorem` — current state (2026-10-02)

A record, not a design document: every line is a decision the owner
made in conversation between 2026-09-22 and 2026-10-02, no rationale;
where two entries bear on one point, the later-dated one is its latest
form and the earlier stands superseded (§14 lists what was withdrawn
outright), except the lines marked *(author)*: shapes the
author settled and told the owner — the review's author-decided
findings and details fixed while writing the documents. The
chronological record with every revision is CONSTRUCT_DECISIONS_LOG.md;
§14 lists what was withdrawn. The design documents written from this
record are docs/CONSTRUCT_INTERACTION.md and
docs/node_classes/THEOREM.md; the client facts are
AGENT_CLIENTS_MEASURED.md. Every agent-facing sentence here is approved
verbatim, `X` standing for a full node id.

## 1. Premises

- One `isabelle TAT_mcp` process serves one working directory and one
  agent client process, Claude Code or Codex, chosen at launch by
  `isabelle TAT_mcp -c <client>` (default `claude-code`); the client is started from
  the working directory itself. The agents are that process's main
  conversation and its subagents; their parents are not recorded.
- TAT's lifetime is an external manager's: when the client process
  ends, the manager terminates TAT with SIGTERM, so the ending runs. TAT
  neither detects the client's death nor exits on its own.
- Everything under the working directory is TAT's to write.
- An agent does not leave while a job of its own runs, a construction
  job of its own waits for its answer, or a message waits in its
  mailbox; the client's stop hook holds it (§9), and its parent may not
  interrupt it while it may hold such work: TAT refuses the parent's
  `TaskStop` (Claude Code) and `interrupt_agent` (Codex) through the
  parent's `PreToolUse` (§9). TAT builds no other detection of a
  departure, reads a parent's hook only to refuse an interruption, keeps
  no timeout, records no parent. The client behaviours that bypass both
  hooks (Claude Code: Escape, the stall watchdog, `maxTurns`; Codex:
  session end, SIGINT, Escape) are accepted as they are: the jobs run
  on and settle, messages stay undelivered, a construction job waiting
  for its answer stays until a context change, a delete or an amend, or
  the ending.
- Every piece of work is an agent's; TAT runs unattended, and no design
  point considers a person in the loop (2026-09-09, "TAT 的使用场景假设一切
  工作都是 agent 完成的。所以我们完全不需要考虑人机协作"; 2026-09-23,
  "目标情形是无人值守"; recorded here 2026-09-30, having been left out
  of the premises). The `isabelle` subcommand as the entry point and the
  stop-hook rule follow from it.
- TAT serves only a client whose version is at least the one its facts
  were measured on (§12). Decided 2026-09-30 (review 4's Q3, "点头"),
  replacing "at start it reads the client's version" (`claude
  --version`, which reads the program on TAT's path, not the one that
  connects — the Claude Agent SDK's bundled 2.1.173 beside a 2.1.285 on
  the path, measured): the version is read from the MCP `initialize`
  each session opens with — `clientInfo.version`, a field the MCP
  specification's lifecycle requires — at the first request that
  reaches TAT; the leading dotted numbers are compared; lower, unreadable,
  or a `clientInfo.name` that is another client's than `-c` chose,
  refuses the session with the existing `TAT_StartupError` naming both
  versions, and the launcher exits 2. The first request of a session
  to reach TAT after `initialize` is `tools/list` on both clients. In
  `clientInfo.name` Claude Code names itself `claude-code`, Codex
  `codex-mcp-client`; Codex opens one MCP session per thread, each
  checked at its first request (measured 2026-10-13, Claude Code
  2.1.296, Codex 0.156.1). Claude Code 2.1.296 connects and lists TAT's
  tools without harm, and its MCP log names no `server/discover`.
  *(author)* The expected versions are the latest measured, Claude Code
  2.1.296 (raised from 2.1.286 on 2026-10-13, the live run having used
  it) and Codex 0.156.1, raised with every round of measurement.

## 2. Jobs on a node

- Two kinds: a construction job, agent-started; an evaluation job,
  started by an evaluation. A node class names its classes in the class
  attributes `construction_job_class` and `evaluation_job_class`, both
  `None` by default; the framework builds the construction job
  (`cls(node)`) with the node, and `job(self) -> Construction_Job |
  None` returns it. At most one of each kind on a node.
- The construction job's `outcome`: `NOT_STARTED`, `RUNNING`,
  `SUCCEEDED(product)`, `FAILED(message)`. `start` sets `RUNNING`, the
  run's settlement `SUCCEEDED` or `FAILED`, `cancel` `NOT_STARTED`.
  `product` is the class's, a string — for `Theorem` the proof: the
  method text AoA writes to its proof store, such as `(simp add: …)` or
  `aoa_replay "…"` (decided 2026-08-29; restored 2026-09-30 after the
  author had reduced it on 2026-09-28 to "an opaque string whose content
  the AoA round decides" without approval); it stays on the node while
  the outcome is `SUCCEEDED`, also while an evaluation job finds it
  wanting.
  `Theorem`'s `proof` is this outcome under `Theorem`'s name, not a
  field of its own. The evaluation job's attribute is also named
  `outcome`; the construction job's is never written by it.
- Persistence: one reserved framework field (one row), `job`, a tag and an optional string,
  written at every change; the store's image of `RUNNING` is
  `NOT_STARTED`, so a loaded forest holds no run and a `start` clears a
  previous failure; `cancel` writes nothing. On an amend the old node's
  running job is cancelled (`NODE_AMENDED`); `Theorem.gen` carries the
  old job's outcome into the new node's job when `for_any`, `premises`
  and `conclusion` are unchanged (§11) — `gen` records the intent, the
  commit copies the store's image.
- `_incompleteness() -> Incompleteness | None` replaces
  `_is_self_complete`; `None` is self-complete. `Incompleteness` is an
  abstract base with three subclasses: `Construction_Incomplete(job)`
  (outcome not `SUCCEEDED`), `Check_Incomplete(job)` (the evaluation
  job `RUNNING` or `FAILED`), `Unchecked(job_class)` (`SUCCEEDED`, the
  class names an evaluation job, none on the node). Default: no
  construction job or not compulsory → `None`; outcome not `SUCCEEDED` →
  `Construction_Incomplete`; `SUCCEEDED` and no evaluation job class →
  `None`; job `PASSED` → `None`; job `RUNNING`/`FAILED` →
  `Check_Incomplete`; no job → `Unchecked`. Unchecked is incomplete.
  Overridable; `Theorem` does not. No `sentence()`.
- `compulsory` feeds only the forest's completeness, never the stop
  hook.
- Id properties: compulsory by default (`output_omissible = False`,
  `input_omissible = False`, `drop_priority = 0`); an omissible class
  declares otherwise; a leaf declares none.

## 3. `Construction_Job`

| member | who | what |
| --- | --- | --- |
| `title(plural=False)` | class method, abstract | `proof construction` / `proof constructions` |
| `compulsory` | class | true when the forest is not complete without it |
| `_run()` | class, hook | the work; returns the outcome; a cancellation propagates out of it: its `try/finally` is its cleanup, which never starts a round trip on the ending's path |
| `_check()` | class, hook, default empty | the class's own start conditions, raised as its own `ConstructionError` subclass |
| `_on_context_change()` | class, hook | called from `_set_status` on every write of the node's own evaluation status by the walk while the job runs — a rerun's rewrite of `ready` included — independently of `on_invalidated`; default: cancel with `CONTEXT_CHANGED`, unconditionally (decided 2026-09-30; the earlier "unless the new status is `ready`" never fired for the default, a job starting on a `ready` node only) |
| `ask(question) -> None` | framework, for `_run` | posts an `Interactive_Question` to the owner and suspends until an answer is accepted; *(author)* a cancellation while it waits withdraws the question |
| `start(owner)` | framework, synchronous | refuses while `RUNNING` (`ConstructAlreadyRunning`); `_check()`; records the owner; drops the node's evaluation job; sets `RUNNING`; persists the store's image; spawns the run |
| `cancel(reason)` | framework, synchronous | detaches the run, withdraws its pending question, sets `NOT_STARTED`, cancels the task; `reason` ∈ `NODE_DELETED`, `NODE_AMENDED`, `CONTEXT_CHANGED` when the framework cancels, and the owner is told, even when the owner deleted or amended the node itself; `cancel_construct` passes `None`, nothing is told |
| wording, defaults from `title` | class, overridable | `starting_notice`, `cancelling_notice`, `answered_notice`, `running_refusal`, `not_running_refusal`, `owned_by_another_refusal`, `no_question_refusal`, `finished_notification(outcome)`, `cancelled_notification(reason)`, `failure_header(failure)` (abstract; `None` prints nothing) |

- The defaults: `Started the proof construction on \`X\`; call
  \`check_construct\` before you exit.` / `Cancelled the proof
  construction on \`X\`.` / `Answered the proof construction on \`X\`;
  call \`check_construct\` before you exit.` / `The proof construction
  on \`X\` is already running.` / `… is not running.` / `… is another
  agent's.` / `… has no question waiting for an answer.` / `…
  succeeded.` and `… failed:` + message / `… was cancelled: the node was
  deleted.` / `… amended.` / `… its context changed.`. The cancellation
  notice names the node the job belongs to, on an amend the replaced
  node.
- The run *(author)*: `start` spawns the framework's wrapper through
  the ending (§10). The wrapper waits for every earlier run's task of
  the job to unwind (`asyncio.wait` over the unfinished ones; never an
  `await` of a cancelled task), then `result = await self._run()`,
  then tests one thing, whether the run is still the job's: every
  legitimate cancellation (`cancel`, by `cancel_construct`, the
  framework or the ending) detaches the run first, so a detached run
  gets nothing; a run still the job's settles on a return, in one
  synchronous stretch under no lock — records outcome and product,
  persists, withdraws its pending question, applies an attach made from
  inside `_run` (§4), posts `finished_notification`, wakes the owner —
  and anything it raises, a `CancelledError` it brought on itself
  included, is a bug that enters the ending. A settlement may land
  between two awaits of a locked call, which then sees it as made just
  before. A question stops pending on an accepted answer, on its `ask`'s
  cancellation, on the job's cancellation and at the settlement;
  withdrawing clears it and cancels the waiting `ask`; delivery drops a
  question no longer pending.
- A rerun does not pass through `not_evaluated` (decided 2026-09-30,
  "赞同保持一步"): the walk writes the status again in one step —
  `ready` over `ready` — and the status setter treats every write by
  the walk, a rewrite included, as a context change for the jobs: it
  calls `_on_context_change` and drops the evaluation job, while
  `on_invalidated`, the release rule and `Theory`'s importer rule read
  only true changes; no pre-traversal. This corrects the author's
  "invalidate, then evaluate" of 2026-09-28, which the code never did
  and which would have released the fresh state at the flush.
- No `_cancel()` (P1), no `fail()`, no replay flag, no mark-words method.

## 4. `Evaluation_Job`

- `__init__(node, starter | None)` sets `node`, `starter`, `id` (the
  framework's counter, unique across the process) and `outcome =
  RUNNING`. `outcome` ∈ `RUNNING`, `PASSED`, `FAILED(message)`, written
  by the class alone. Stored (decided 2026-09-30 in the compilation
  session, "赞同" at 11:11 and 11:15 UTC; correcting "never stored"): as
  the construction job's store image is, `PASSED` or `FAILED(message)`
  in a transaction of its own at each synchronous step that changes the
  job on the node — the `finished` report's body, an attach applied at a
  run's settlement, every drop (a walk's or an edit's drop rides in
  their store of the node) — `RUNNING` as none, never by the
  conversation's ending, which drops every job and writes nothing;
  loading restores it as a value emission reads, re-attaching no job, so
  marks, `_incompleteness`, `is_finished` and the stop hook are
  unchanged. *(author)* A reserved framework field (one row) of `job`'s
  shape (§2), named `check`, a missing row read as none.
- Class method `make(node, starter) -> Self`, synchronous, with the
  default `cls(node, starter)`, overridable: builds the instance and
  begins nothing; what a class needs from Isabelle it fetches in
  `_start`. Abstract class method `title(plural)`. Abstract hook
  `_start()`, async: begins the work through the class's own ML
  callback, passing `self.id`, and returns at once; the framework calls
  it once the job is on its node. Hook `_finished(errors)`, called by
  the framework on the ML report, synchronously, under no lock; default
  `PASSED` on no errors else `FAILED(errors joined by newlines)`.
  Abstract `failure_header(failure)` and `failure_notification(message)`.
- Framework: `Node.start_evaluation_job()` = `job = cls.make(node,
  caller)`; `attach_evaluation_job(job)`; `await job._start()`, nothing
  between the test and the attach — *(author)* `make` and `_start`
  follow the completed hook's rule: anything they raise, a `TAT_Error`
  included, is the class's bug (`TAT_InternalError`), the conversation
  ends, the ending drops the job. `Node.attach_evaluation_job(job)`
  attaches, dropping the one there — a class may attach a job it built
  and settled itself; *(author)* from inside a construction run it
  accepts a settled job only, and the attach takes effect at the run's
  settlement. The walk starts a job at every node it passes (rerun or
  left `ready`), at the node's last operation, when the node is
  `ready`, has no evaluation job, `_incompleteness()` would answer
  `Unchecked`, and `checks` allows. *(author)* "Passes" means reached
  in the `Evaluating` walk mode: up to and including the destination,
  never past it.
- The report: the remote procedure `finished(id, errors)` answers at
  once; its synchronous body, when the job with this id is still on its
  node, calls `_finished(errors)`, posts `failure_notification` to the
  starter on `FAILED`, marks the job ended and wakes the starter; a
  report whose job is off its node is a dropped job's and is ignored.
  The procedure is declared with no timeout. *(author)* Anything the
  body raises, and an `outcome` that `_finished` leaves `RUNNING`, is a
  bug that enters the ending (§10).
- Running: an evaluation job is running when its `outcome` is `RUNNING`
  and it is on its node; the stop hook, the state lines, the background
  line and `blocking` read this one definition. *(author)* Dropping is
  one synchronous operation, `drop(job)`: takes the job off the node,
  marks it ended, wakes the starter. Cancelling the task is a
  separate best-effort step, the callback `cancel(ids)` with the ids a
  walk dropped, sent at the walk's `flush`, at once outside a walk, not
  at all by the ending. A node's job is dropped when the node leaves
  `ready`, on a rerun, delete, amend, a construction `start`, and by an
  attach.
- `blocking`: the evaluating call keeps the forest lock and, after the
  walk, waits until every evaluation job that was running on a node the
  walk passed has ended — settled or dropped, whoever started it — then
  writes the quickview and the trailer. No context changes during the
  wait: only a lock holder changes one, and a rerun in the walk drops
  and restarts the job of a node whose context changed.
- ML side (approved 2026-09-28: "fork 后把 future 按编号存进框架自己的表；
  取消就是 Python 调一个框架的 callback `cancel(编号)`，查表、
  `Future.cancel`" — "很好的设计，赞同"): the framework's ML half offers
  the fork and the report as one function — the work forked as a
  Future task on Isabelle's worker pool, the future kept under the
  job's id in the framework's own table, the report `finished(id,
  errors)` after the work with interrupts deferred — and one callback
  `cancel(ids)`, which looks the ids up and cancels the futures;
  callbacks through the existing table, remote procedures through
  Isabelle_RPC's registry, no new registry. The work bounds its own
  time; the framework sets no limit. *(author)* The work reads the
  input slot's state once, at the fork.
  **Correction, 2026-09-30.** Between 2026-09-29 and 09-30 the author
  replaced this approved shape, without the owner's approval, by "a
  plain Isabelle thread, on no Future worker, registering no execution,
  the work under `Future.interruptible_task`" — on the strength of
  review 2's finding A7 and review 3's F4, shown to the owner only as
  author items — and wrote it into CONSTRUCT_INTERACTION §3.3,
  THEOREM.md §6/§7 and MODULE_STRUCTURE §2.4/§2.6
  (ai-artifacts/review/JOB_THREAD_ARCHAEOLOGY.md). The owner corrected
  it on 2026-09-30. The finding rested on a wrong model of the replay
  (Isar commands, `Goal.prove_future`): the proof check's work is a goal
  built in ML and `eval_prf_str`, AoA's own replay path, which applies
  no Toplevel transition and forks no proof, so nothing of a job's
  enters Isabelle's execution table on any thread (§11, EVALUATOR_DESIGN
  §6). Decided 2026-09-30: no lock orders the jobs against a library
  load; jobs, evaluation and loads run beside each other.
- After a construction job succeeds the framework does nothing:
  `Proof_Job._run` ends by `attach_evaluation_job(Proof_Check.passed(
  node))`, `passed` a `Proof_Check` class method building an instance
  with `outcome = PASSED` — with the default `_on_context_change`, a run
  that reaches its end saw no context change. `proven` means "a
  `PASSED` evaluation job is on the node".

## 5. Messages and questions

- A message: recipient, text, whether it interrupts `check_construct`,
  optionally what it comes from (an evaluation job or a construction
  run) and a question. Anything may post. Delivered at the tool
  boundary on the recipient's next tool result, nowhere else; at
  delivery a message whose evaluation job is off its node, whose run is
  no longer its job's, or whose question is no longer its job's pending
  question is dropped; the framework's notifications come from no run.
- The framework's notifications: `finished_notification` and
  `cancelled_notification` interrupt; an evaluation job's
  `failure_notification` does not; a job class sets the flag on its own
  notifications; questions always interrupt; success of an evaluation
  job is silent.
- `Interactive_Question` (replaces `Question(text, schema, check)`):
  `text`; `schema`, an object schema within the tool-schema grammar,
  validated in `ask` (a failure is a bug in `_run`), substituted for
  the tool's `answer` property and checked by `check_call` before the
  question sees the value; abstract `receive(answer) -> Answered |
  Interactive_Question`: `Answered(response: str | None = None)` accepts
  (the job's data stays on the question; `response` is the tool's text,
  `None` the default `answered_notice`); a returned question replaces
  the pending one and is delivered in the same result; `BadAnswer(
  message)` refuses, the question stays. A job holds a FIFO queue of
  questions (2026-10-09, superseding "one pending question per job"):
  a run may ask several at once from branches it forks, only the front
  is posted and answerable, and the agent answers them one at a time;
  other messages of the job may arrive meanwhile. `ask` enqueues,
  posts the front to the owner's mailbox and suspends until an `Answered`
  *(author: a schema failing validation is a bug in `_run`;
  `check_construct` puts a delivered question back)*. `receive` is
  synchronous, in the tool body, under no lock.
- Delivery format: `The proof construction on \`<full id>\` asks:` +
  text + `Answer with the \`answer\` tool, node_id \`<full id>\`; the
  answer must follow the JSON schema:` + the complete schema,
  multi-line. No `Question:` header; never printed under the node.

## 6. Agents

- `Agent`: one per agent of the client process, created at its first
  call or hook, never discarded; holds its jobs of both kinds (owned
  construction jobs, started evaluation jobs), its mailbox, its seen set,
  its wake-up (a change to its mailbox or jobs). Identity: Claude Code —
  the `PreToolUse` announcement's `agent_id`, empty for the main
  conversation; Codex — the call's `_meta.threadId` (*(author)*
  corrected 2026-09-30 from `_meta.thread_id`, a key that does not
  exist; the same value as `_meta["x-codex-turn-metadata"].thread_id`).
- `answer` and `cancel_construct` are the owner's alone; a question's
  text and the tag are shown to the owner only; failure blocks to all.
- `Agent` counts its working calls (decided 2026-09-30, review 4's Q2:
  "要"): the count rises in the handler's `try/finally` as soon as
  `agent_of_call` names the agent, before any lock is awaited, and
  falls when the body ends; not counted from the announcement. Read by
  the interruption judgement only, never by the stop rule.
- Seen set per agent: `Agent.seen: set[Key]`, `Key = tuple[int, str |
  None]`; `Conversation.forget(key)` removes a key from every agent's
  set (the evaluation hooks' discard when they record a run's messages,
  after the operation ran, PRINT.md §4); a compaction clears the
  compacted agent's set alone.
  `Forest.render(node, mode, agent)`; `mark` and `print_fields` reach
  the agent through the forest.

## 7. Tools

- Tools: `construct {node_id}` — `Start a node's own construction job,
  such as the proof of a theorem`; `cancel_construct {node_id}` —
  `Cancel a node's running construction job`; `check_construct
  {wait_seconds: integer, required}` — description completed at start
  (below); `answer {node_id, answer}` — `Answer the question a
  construction job asked you`, `answer` a bare object replaced at run
  time by the question's schema. Field descriptions: `The id of the
  node whose construction job to start` / `… to cancel`; `The time to
  wait at most, in seconds; the call returns earlier when a message
  arrives or every job has finished`; `The id of the node whose
  construction job asked the question`; `The answer, in the shape the
  question asked for`. `construct` takes one node, no class-specific
  arguments. `status` is removed. The four tools exist only when a
  loaded class names a construction job class.
- `check_construct`'s description: `Wait until any {construction titles,
  singular} or all {evaluation titles, plural} have finished, or a
  message arrives. Returns at once when nothing is running. To ensure
  all jobs have finished, call it repeatedly.` — each slot's titles
  distinct, alphabetical, joined with commas and `or` before the last;
  the `or all …` part absent without evaluation job classes. With
  `Theorem` alone: `Wait until any proof construction or all proof
  checks have finished, or a message arrives. Returns at once when
  nothing is running. To ensure all jobs have finished, call it
  repeatedly.`
- `evaluate_to`: `node_id`, required, `The id of the node to evaluate
  up to, with its subtree; a theory's id means the whole theory.`;
  `ignore_error`, optional, `Whether to carry on past a node that
  fails, so the nodes after it are evaluated too. Default: false.`;
  `checks`, optional, enum `"no"`, `"quick"`, `"blocking"`, default
  `"quick"`, absent without evaluation job classes, description `Whether
  to run the {titles} of the nodes: "no" runs none; "blocking" runs them
  and waits for them to finish before the call returns; "quick" runs
  them in the background, and you may wait for them with
  \`check_construct\` or go on (a failure will be reported to you, a
  success is silent). Default: "quick".` with `{titles}` the plural
  titles, distinct, alphabetical, joined with commas and `and`,
  completed at start where `edit`'s schema is. The grammar has no
  `default`; descriptions state `Default: …`. `edit`'s and `move`'s own
  evaluation runs with `quick`. The tool description (the owner's
  wording, 2026-09-30): `Evaluate Isabelle theory constructs up to a
  node. Already evaluated constructs are skipped.`
- `evaluate_to`'s result opens with `Evaluation reached theory_X.` /
  `Evaluation stopped at definition_f.`, the node in its shortest form
  (decided 2026-09-30; the owner rejected "up to" and "successfully");
  the order constraint's sentence (RENDER_BASELINES §3) follows on the
  line after a stop it explains, in `evaluate_to`'s result and after an
  edit's `Done` line alike; then the quickview (READERS_FOLLOWUP row 10;
  recorded here 2026-10-02).
- Every tool result: the body's text, then the caller's undelivered
  messages, then the trailer. A call that ran an evaluation ends with
  the background line, the caller's running evaluation jobs counted by
  title: `3 proof checks are running in the background.` / `1 proof
  check is running in the background.` / `3 proof checks and 1
  counterexample search are running in the background.` (the approved
  example; the titles' order follows the description's rule,
  alphabetical, *(author)*); nothing at zero; first time per agent
  *(author: key `(0, "background")`)*: `3 proof checks are running in
  the background; call \`check_construct\` to wait for them.`.
- `construct`: result `starting_notice` over the quickview (the node,
  depth 0); refusals `ConstructNotSupported` (`\`X\` has nothing to
  construct.`), `ConstructAlreadyRunning`, the class's own.
  `cancel_construct`: `cancelling_notice` over the quickview;
  `ConstructNotRunning`, `ConstructOwnedByAnother`.
- `check_construct` returns on: an interrupting message; a construction
  job waiting for an answer (the question delivered again); since the
  call started a job of the caller's ended *(author: settled, cancelled
  or dropped)* and none of its title is left running; the deadline
  (`wait_seconds`
  clamped silently to at least 3 s and to a minute under the client's
  twelve-hour limit; neither in the schema). Nothing running or waiting
  at the start: at once, the single line `No job is running.`, a plain
  result. State lines, by title and situation, construction titles then
  evaluation titles, alphabetical within, each node once, up to three
  as one sentence with `on` repeated and `and` before the last: `The
  proof construction on \`X\` is waiting for your answer.` / `The proof
  construction on \`X\` and on \`Y\` is still running.` / `The proof
  check on \`X\` is still running.`; more than three: `The following
  proof constructions are
  still running:` + one full id per line (`  - theory_X.lemma_Q`), and
  for the waiting group `The following proof constructions are waiting
  for your answer:` over the same kind of list (decided 2026-09-30,
  READERS_FOLLOWUP row 12a; recorded here 2026-10-02); a
  title the caller had a job of and now none: `All proof constructions
  have finished.` / `All proof checks have finished.`. No quickview; a
  deadline return has the same shape.
- `answer`: refusals `ConstructNotRunning`, `ConstructOwnedByAnother`,
  `NoQuestionPending`, the checker's shape sentence (`The argument
  \`answer.verdict\` must be one of …`), `BadAnswer`; accepted → the
  question's `response` or `answered_notice`; asked instead → the new
  question as a message; no quickview.
- Failures of `construct` and `cancel_construct` open with `Cannot
  <tool> <node id>`; `check_construct`'s and `answer`'s render the cause
  alone, `answer`'s four refusal sentences naming the node themselves.
  Exceptions: `ConstructionError` (abstract `TAT_Error`, replaces
  `ConstructFailed`) with `ConstructNotSupported`,
  `ConstructAlreadyRunning`, `ConstructNotRunning`,
  `ConstructOwnedByAnother`, `NoQuestionPending`; `BadAnswer` under
  `TAT_Error`. Any `TAT_Error` renders, `isError`; anything else ends the
  conversation.

## 8. Rendering

- The framework's mark: `finished` → `complete`; an own obstacle →
  `failed`; the node's first own operation `not_evaluated` (never
  reached, invalidated, blocked) → `not evaluated`; otherwise
  `incomplete` — its first operation ran, and a later one did not or
  something under it is unfinished. A nesting node whose beginning ran
  and whose ending did not is therefore `incomplete`, not `not
  evaluated`. No line is bare. `Session`: `complete` or `incomplete` by
  its trees.
- `Theorem` overrides `mark` with two slots. Statement: `valid
  statement` / `invalid statement` / `not evaluated`. Proof: `proof not
  started` (`NOT_STARTED`), `proving` (`RUNNING`), `failed to prove`
  (`FAILED`), `unchecked proof` (`SUCCEEDED`, no evaluation job), `proof
  checking` (job `RUNNING`), `proven` (job `PASSED`), `bad proof` (job
  `FAILED`). `(invalid statement)` alone; under `not evaluated` a stored
  proof is unmarked; eleven combinations; the tag `needs your answer,
  call \`check_construct\` to see it` as a third item, owner only, every
  rendering, until answered.
- Fields only under `Recall`, every class: Session depth 0
  `parent_session`, `options`, `description`, depth 1 `parent_session`,
  `options`; Theory `imports` at depth 0–2, `description` at depth 0;
  Theorem at depth 0–1 two lines — the proposition in Isabelle's meta
  form first, `english` second, no leading keys — at depth 2 the
  proposition alone, nothing at depth 3, in `Out_Focus` or as a focus.
  The framework writes an evaluation's messages after the fields, in
  every mode where `print_fields` is called (PRINT §3; the compilation
  session's ruling, confirmed 2026-10-01); a focus writes the
  framework's messages and its jobs' blocks only.
  `Briefing` never calls `print_fields`.
- Failure blocks: after `print_fields`, when detailed, per job with
  outcome `FAILED`, never under an obstacle: `failure_header` then the
  message one level deeper; every detailed rendering, no seen set.
- The summary under an `incomplete` nesting node at `Recall`'s last
  printed depth (3): one line per group — `ready` nodes by the title of
  their `Incompleteness`'s job (`Unchecked` by its class's), then
  `failed`, then `not evaluated`; ids in tree order relative to the
  node, up to five, else the count; no period; not in a quickview or
  the briefing: `3 proof constructions incomplete: lemma_A, lemma_C,
  context_C.lemma_B` / `12 proof checks incomplete` / `1 node failed:
  definition_f` / `2 nodes not evaluated: lemma_E, lemma_F`. *(author)*
  A group with no members writes no line.
- Notifications: `\`X\` is proven.`, `No proof of \`X\` was found:` +
  message, `The proof construction on \`X\` was cancelled: the node was
  deleted.` / `… amended.` / `… its context changed.`, `The proof of
  \`X\` no longer holds:` + errors.
- Past its destination a walk marks every operation `not_evaluated`,
  to the tree's end, however it reached the destination — evaluating or
  blocked — as the code does today; there is no fifth walk mode, and
  `test_evaluate_to_inside_an_import_invalidates_its_importers_whole`
  stays as it is (the owner, in the compilation session on 2026-10-02,
  withdrawing A3; all of that session's requests approved here the same
  day, 「批准编译会话的所有请求」). Accepted with it: `evaluate_to` on a
  `Ready` node invalidates what follows it; after a restart a call to a
  node inside a tree invalidates the rest of the tree and its
  importers. A changed environment after a restart is not detected.
- The compilation session's rulings confirmed here on 2026-10-01 and
  written into this session's documents the same day: the stored check
  cleared only when a stored status leaves `Ready`, when a construction
  job starts or another evaluation job is attached; one accessor,
  `Node.check_outcome()`; `_unfinished()` / `Unfinished` /
  `Unfinished_Construction` / `Unfinished_Check` for
  `_incompleteness()` / `Incompleteness` / `Construction_Incomplete` /
  `Check_Incomplete`; the messages on the status values (`Ready`,
  `CannotEvaluate`), `Theorem` keeping no `errors` field;
  `failure_header` a class method; one status setter per operation
  writing both fields, a plain method; each synchronous step of a job
  that changes the job or the check on its node stores the node in a
  transaction of its own; an edit stores every node whose status its
  commit wrote, a walk every node whose status it wrote, at each tree's
  end and when it ends; `Theory`'s importer rule fires when a stored
  `Ready` ending is replaced by a value that is not a `Ready`; exit
  code 2 for a non-normal end.

## 9. Leaving

- `SubagentStop` and `Stop` are blocked exactly when a `check_construct`
  returning at once would not answer `No job is running.` with no
  message: the agent has a job running, a construction job waiting for
  its answer, or a message in its mailbox that delivery would not drop.
  The reason carries no message and no question: the opening line `The
  \`TAT\` server blocked your exit:`, the state lines with members, and
  one instruction: `Call \`check_construct\` to see the question{s} and
  to wait for the running {titles}; answer {it|them} before you exit.` /
  `Call \`check_construct\` to see the question{s}; answer {it|them}
  before you exit.` / `Call \`check_construct\` to wait for the running
  {titles} before you exit.` / `Call \`check_construct\` to read your
  messages before you exit.` (messages only; beside a question or a
  running job they go unmentioned); titles in their numbers,
  construction first then evaluation alphabetical, merged. No limit on
  blocks; Claude Code's ceiling off (§10). The ending cancels every
  construction job and drops every evaluation job.
- An interruption is refused with the same judgement as a stop, one
  rule on both clients (decided 2026-09-30, after review 4: "全都统一成
  codex 那种全局策略"): the parent's `TaskStop` (Claude Code) or
  `interrupt_agent` (Codex) is denied when any agent other than the
  caller and the main conversation would be held by the stop rule or
  has a TAT call still working (§6; decided 2026-09-30, review 4's Q2);
  TAT reads neither `task_id` nor the path. Sound because a stop ends only
  its target and the target's foreground descendants, never the caller
  or the main conversation; a judgement of the target alone was unsound
  on Claude Code twice over (a target named by its launch name or
  `shell_id`; a target's foreground children, measured
  `review4_refusal_facts` N1/C1 and N2/N3). Price on Claude Code: an
  idle subagent or a background shell cannot be stopped while another
  subagent holds work, and the reason then names a shell an agent —
  accepted. The owner's Codex rule of 2026-09-30 08:30 was "有全局 jobs
  时发送这个拒绝"; leaving out the caller and the main conversation is
  the author's restatement of 08:31, approved by the owner on
  2026-09-30 ("可以"). The reason, both clients, two lines: `This agent cannot
  be interrupted: it may still have work in \`TAT\`.` / `Send it a
  message asking it to finish its work in \`TAT\` and exit, then wait
  for it.` — no state lines. Otherwise the interruption is allowed.
- Should a client ever report an agent gone with a job running,
  `TAT_InternalError` (`Agent <id> left with jobs running: the proof
  construction on \`X\`, 3 proof checks.`, logged) and the ending; no
  code path learns it today.

## 10. The server and the clients

- `TAT_Server` has one subclass per client: `configure(working_
  directory)` writes the client's files whole (MCP entry, hooks with
  absolute paths, settings); `agent_of_call(context)`;
  `event_of_hook(request) -> Hook | None` on the one endpoint `/hook`
  (`stop`, `interrupt`, `compaction`); the envelope. `TAT_new` writes no
  client files. The server is registered with the client under the name `TAT`
  (tools `mcp__TAT__…`); the agent-facing name is `TAT`, never `tat`.
- The Isabelle tool that starts a conversation is `isabelle TAT_mcp`
  (the owner, 2026-10-02: 「建议把 isabelle TAT 重命名为 isabelle
  TAT_mcp」), in place of `isabelle TAT`. Only the tool's name changes:
  `TAT_new`, `TAT_compile`, the server's name `TAT`, the protocol
  commands `TAT.boot`, `TAT.start`, `TAT.finished`, the procedure
  `launch_TAT`, `TAT.sqlite`, `tat.lock` and `TAT.agents/` stand.
  Applied the same day: `src/scala/tat.scala` (the tool, its usage text,
  `TAT_new`'s usage text; the value `tat_mcp_tool` *(author)*),
  `lib/tat.jar` rebuilt, README.md, the tests (`harness.py`'s command
  and its log file `isabelle_TAT_mcp.log` *(author)*, `test_launcher.py`'s
  helper `tat_mcp` *(author)*), and docs/ (ARCHITECTURE, MODULE_STRUCTURE,
  CLIENT_HOOKS, CONSTRUCT_INTERACTION, COMPILATION). Left as written:
  COMPILATION.md's quotation of ARCHITECTURE §1's replaced sentence (the
  compilation session's), and the plans and review records under
  `ai-artifacts/`, which say what was true when they were written.
- `configure` also writes the parent's `PreToolUse` hook that refuses
  an interruption (§9): Claude Code matcher `TaskStop`, Codex matcher
  `collaborationinterrupt_agent`; the hook posts to `/hook` as an
  `interrupt` event and answers `permissionDecision: deny` with the
  reason, or an empty answer (the wire form corrected by the author
  after review 4, below). *(author)* On Codex the tool name exists only
  under multi-agent V2 with the default tool namespace, so `configure`
  writes `features.multi_agent_v2 = true` (source read; measured
  2026-10-13 on 0.156.1: under it the tool is
  `collaborationinterrupt_agent`, its `tool_input` `{"target":
  "/root/<name>"}`, the hook matched and the denial reached the
  parent — with `gpt-5.6-sol`, which the model catalog gives V2 by
  itself, so the run does not show that the flag is what gives V2).
- `agent_of_call` never guesses: every `tools/call` must have been
  announced by a `PreToolUse` hook (matcher `mcp__TAT__.*`); Claude Code
  matches `_meta["claudecode/toolUseId"]`, Codex `_meta.callId`; an
  unannounced call → `TAT_InternalError` (`This call was not announced
  by the client's hooks, so TAT cannot tell which agent is calling.`,
  logged) and the ending, every tool then answering `an internal error`.
  TAT never reads a payload's `cwd` as the working directory. *(author)*
  The hook script never exits 2: every decision travels in the JSON TAT
  answers, and a script that reaches no TAT exits 1, which no client
  reads as a block. *(author, after review 4, 2026-09-30)* The script
  guarantees it rather than a curl version: `curl -sS -f … || { [ $?
  -eq 7 ] && not_running; exit 1; }`, so an old curl or a curl failure
  of its own is exit 1 too (the earlier `exit $rc` after
  `--fail-with-body` exited 22 on 503/500 and 2 on a curl older than
  7.76, measured). An allowed interruption is an empty answer on both
  clients, not `permissionDecision: allow`, which Codex 0.156.1 answers
  "unsupported" and marks failed; `TaskStop` needs no grant (measured).
  The `interrupt` event is on the set of agents the call may stop, an
  empty set allowed. *(author)* The
  announcement's answer on Claude Code carries `{"hookSpecificOutput":
  {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}`
  (§12).
- Every compaction, a subagent's as much as the main conversation's, is
  detected through the client's hooks and clears the compacted agent's
  seen set; no fallback (the owner, 2026-09-15: 「agent compaction 后所有
  "看过"的不能再信，必须被清空」, 「否决。我们可以假设这些配置始终是好的」;
  2026-09-30: 「强烈反对。这是严重的问题」 to accepting a subagent's
  compaction going unnoticed). The author's narrowing of 2026-09-29 —
  "`SessionStart` of every source is the main conversation's compaction
  event", which left a subagent's compaction undetected — was never put
  to the owner and is withdrawn (ai-artifacts/review/COMPACTION_ARCHAEOLOGY.md).
  *(author, from the probes of 2026-09-30)* The channels: on Codex,
  `PostCompact`, registered in `hooks.json`, whose `agent_id` names the
  subagent (none: the main conversation), and `SessionStart`, which
  fires for the main conversation only; on Claude Code, where no
  compaction hook names the agent, the count of `compact_boundary`
  lines in the announcing agent's transcript, read at each
  announcement, a rise being that agent's compaction event, and
  `SessionStart` with `startup`, `resume` or `clear` for the main
  conversation; `SessionStart` with `compact` answered with nothing on
  both. (Superseded on 2026-10-01 by the entries below: on Codex
  `PreCompact` is registered beside `PostCompact`, and a `SessionStart`
  of every source, `compact` included, is the main conversation's
  compaction event, answered with nothing; on Claude Code TAT registers
  no `SessionStart` and reads boundaries and the `transcript_path` at
  each announcement — CLIENT_HOOKS §1–§3.) Nothing a compaction hook answers reaches the model on Codex,
  and on Claude Code TAT cannot tell whom it would reach, so no
  compaction hook carries `additionalContext` and TAT pushes no
  briefing: the agent reads it itself (decided 2026-09-30, "把 briefing
  这些文本放在 recall 里"): `recall` with no id renders the forest root in
  `Briefing` — changing the 2026-09-28 rule, under which no id rendered
  the root in `Recall`; an id, `Sessions` included, still renders in
  `Recall` — and a skill of the agent's, outside TAT, tells it to call
  `recall` with no id after a compaction. `node_id`'s description
  (approved 2026-09-30): `The id of the node to read. Leave it out to
  read the outline of everything.` The tool description (approved
  2026-09-30, the owner's wording polished): `Read an Isabelle theory
  construct with what is under it, briefer the deeper, or an outline of
  everything.`
  The `Briefing` rendering stays an internal interface, `Forest.render`
  in `Briefing`. TAT handles no `SessionEnd`.
- Which agent a compaction names on Claude Code (2026-10-01; the
  channel is open). A brainstorm recommended "a compaction event clears
  every agent's seen set" (ai-artifacts/review/COMPACTION_IDENTITY_RULING.md);
  the owner rejected it (「强烈反对！这是最糟糕的方案！」): clearing the set
  of an agent that did not compact is not acceptable, and a compaction
  clears the compacted agent's set alone, as the entry above says. TAT
  stays an MCP server (「TAT 必须作为一个 MCP」): no architecture in which
  TAT drives the client itself, as AoA's driver does with one
  `ClaudeSDKClient` per subagent and in-process hooks on each. The
  refuted candidates are repaired, not dropped (「有漏的情形能修的你要修
  一下」): the eleven repair results are in
  ai-artifacts/review/COMPACTION_IDENTITY_REPAIR_RESULTS.md and the
  judge's ruling over them in
  ai-artifacts/review/COMPACTION_IDENTITY_REPAIR.md. The ruling's
  recommendation (reading the announcing agent's own transcript at each
  announcement, amended; changes on Codex) and its eight questions await
  the owner; until then the entry above stands unchanged.
- `/clear` is a compaction event of every agent running across it (the
  owner, 2026-10-01: 「可以把 `clear` 视同为某种 compaction，是可以接受的」,
  confirmed the same day). On Claude Code, an agent whose announcement
  carries a `transcript_path` different from the one at its previous
  announcement has its seen set cleared: the main conversation, whose
  context `/clear` emptied, and equally a background subagent that keeps
  running, whose context survives. The accepted cost: such a subagent is
  shown its once-only text one more time, once per `/clear`. *(author)*
  It follows that TAT holds one transcript file per agent, the one under
  the session directory of its latest announcement, and reads no file of
  an earlier session directory. On Codex `/clear` starts a new thread
  with a new rollout path (read in the source); what happens there to
  subagent threads running across it is not measured.
- The channel on Claude Code is accepted (the owner, 2026-10-01:
  「现在也就只能先忍受这个脏方案了」, the missing agent name in the
  compaction hooks being a defect of Claude Code's): at each
  announcement TAT reads the announcing agent's own transcript for
  compaction boundaries it has not recorded. The standard for the whole
  matter is best effort (「总体思路就是，尽力就好，期望未来它们能改进」).
  Reliance on the transcript's internal format: accepted, with a version
  rule looser than admitting only the exact versions measured
  (「接受，但可以稍微宽松一点」): the rule stays as it is — a client below
  the measured version is refused, there is no upper bound and no exact
  set, and a newer version is served, the checks below being its guard
  (confirmed 2026-10-01, 「没错」). A rewind that removes context without
  a summary (the rewind menu's "Restore conversation", or Esc Esc to
  edit an earlier prompt and send it again; no hook fires for it): not
  considered, a premise — TAT assumes it does not happen (the owner,
  2026-10-01: 「我们不考虑回退，假设回退不存在」, after the offline survey
  `ai-artifacts/probes/rewind_fork_survey/REPORT.md` showed that
  recognising it from the transcript both clears needlessly and can
  miss). TAT reads nothing of the transcript for it. Checks that report
  a broken premise (a compaction boundary later than a rendering it
  should have preceded; a `PostCompact` with no boundary following):
  agreed (「赞同」). Deferred by the owner (2026-10-01, 「现在先不讨论。
  我正在 a forked agent 中单独设计 agent 系统，之后会通知你」): whom
  such a check reports to and what TAT does then, and whether TAT gets a
  log, there being none today; nothing of either is written until the
  owner brings that design back. The `env` TAT writes into
  `.claude/settings.json` gains `CLAUDE_CODE_SKIP_PROMPT_HISTORY=0` (the
  owner's amendment) and `CLAUDE_CODE_FORCE_SESSION_PERSISTENCE=1`
  (2026-10-01, 「赞同写」), the second turning transcripts back on for an
  interactive Claude Code started from inside another one. An agent for
  which TAT holds no transcript and finds none at its announcement —
  Claude Code started with `--no-session-persistence`, or through the
  SDK with `persistSession: false`, neither of which a variable undoes —
  ends the whole conversation (2026-10-01, 「建议此时直接结束整个会话」;
  the author had recommended refusing the one call). *(author, 「怎么
  方便写代码怎么来就好」)* It is a `TAT_StartupError`, through the door
  the version refusal uses: the conversation enters its ending, the
  launcher prints the message and exits 2. The launcher's line (approved
  2026-10-01): `TAT cannot serve this client: Claude Code saves no
  transcript of the conversation. Start it without
  --no-session-persistence.` The line the agents' calls are answered
  during that ending, a fourth beside RENDER_BASELINES §4's three
  (approved 2026-10-01): `TAT has stopped: Claude Code saves no
  transcript; this call did not complete.` (On 2026-10-04 the owner
  gave every line of RENDER_BASELINES §4 a new frame around its
  reason, as the compilation session reports; the reason's words,
  `Claude Code saves no transcript`, stand, and the line is read from
  that section.) *(author)* What the Claude
  Code subclass keeps per agent: the `transcript_path` of its last
  announcement, how far it has read the agent's transcript, and the
  boundaries recorded from it — recorded boundaries rather than a count,
  since a `/clear` starts a new file. A subagent's file is looked for at
  any depth under `subagents/`, a workflow agent's lying one directory
  deeper. A transcript not found ends the conversation at whatever
  announcement it happens, with no exception (the owner, 2026-10-01:
  「直接写"找不到 transcript 就结束整个会话"就行…这个延迟不要紧的」;
  narrowed on 2026-10-13 to the main conversation's transcript — Claude
  Code's internal agents, below); the
  author had proposed to exempt the announcement right after a `/clear`,
  where a running subagent's new file appeared 91 ms after its
  announcement in one of the two runs measured and 67 ms before it in
  the other). TAT registers no `SessionStart` on Claude Code any
  more: the path rule covers `/clear` and `/resume`, and at `startup`
  the set is empty. Written into CLIENT_HOOKS §1, §2, §4,
  CONSTRUCT_INTERACTION §1, §8, MODULE_STRUCTURE §4.6, PRINT §4,
  EXCEPTIONS §1, RENDER_BASELINES §4 on 2026-10-01; the checks, their
  reaction and the log are not written, and Codex is unchanged.
- Codex, the compaction hooks (2026-10-01). A TAT call made from a
  script the model has Codex run can end while its thread's summary is
  being written, between `PreCompact` and `PostCompact`, its result
  delivered into the new context (measured, main conversation and
  subagent, one run each; AGENT_CLIENTS_MEASURED.md). Decided:
  `PreCompact` is registered on Codex beside `PostCompact`, and both
  clear the named thread's seen set (the owner, asking 「那么我们可以挂
  PreCompact 钩子吗？」, then accepting its costs: a failed compaction
  clears that thread's set for nothing, 「接受」; one more hook in the
  configuration, 「接受」). A script that keeps a TAT result and prints
  it only after a compaction, or never, is accepted as a client
  behaviour and documented (「接受并文档好了」). Written 2026-10-01 into
  CLIENT_HOOKS §1, §3, §4, CONSTRUCT_INTERACTION §1, §8, PRINT §4.
  The thread a compaction hook names stays the one its `agent_id` names,
  the main conversation when there is none (2026-10-01, 「建议继续使用
  agent_id，没有它就当作主会话」; naming by the payload's
  `transcript_path` was proposed and not taken). TAT therefore reads no
  `transcript_path` on Codex, and a Codex that keeps no rollout
  (`--ephemeral`) is served like any other. What follows from the rule,
  read in the source and not measured: a thread that is no spawned
  subagent (`/review`, guardian, memory) carries no `agent_id`, so its
  compaction clears the main conversation's set, and its own, should it
  call TAT, is not cleared. `direct_only_tool_namespaces` is not
  pursued, the held-back result being accepted.
- Claude Code: `.claude/settings.json`'s `env`
  `CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS=0` and
  `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP=0` and
  `CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION=false` (2026-10-13, the owner:
  the prompt suggestion is the most frequent internal agent, and its
  `SubagentStop` follows every turn); per-server `timeout` 43200000 ms;
  the stall watchdog left alone; `--strict-mcp-config --mcp-config
  <agent directory>/.mcp.json` at launch (2026-10-13, the owner,
  「赞同，请加」: the live run showed the client starting the user's own
  MCP servers, isabelle-mcp among them, in the agent's session; the
  strict flag alone ignores the project's `.mcp.json` too, measured — the
  agent then had no TAT tool). Codex: `default_tools_approval_mode =
  "approve"`, `tool_timeout_sec` 43200, `check_for_update_on_startup =
  false` (the layer it is read from is not determined; the 2026-10-13
  run showed no update banner, and its one TUI warning, whose text was
  not captured, may concern this key); trust and
  `--dangerously-bypass-hook-trust` have no configuration equivalent
  and are given at launch. `check_construct` clamps to a minute under
  twelve hours. *(author)* TAT sends no progress notifications (the
  review's A13). Which field of a compaction hook names the agent:
  measured 2026-09-30 — Codex's `PostCompact` `agent_id`; on Claude
  Code none.
- *(author)* The ending is one object built in `toplevel.conversation()` before
  the `Conversation`, handed to it and to the server: the future, the
  tasks, `end(exn)`, `spawn(coroutine)`; tool bodies and construction
  runs are spawned through it; `end`, in one synchronous stretch,
  cancels every running construction job through its own `cancel(None)`,
  drops every evaluation job and cancels every other task, without a
  round trip; `serve` waits for the tasks. A settlement — a construction
  run's end, an evaluation job's report — is one synchronous step under
  no lock (§3, §4); anything it raises, a `TAT_Error` included, is a
  bug that enters the ending, like the `/hook` path's judgement's; no lock
  holder awaits a job's task, and `blocking` awaits the jobs' ends
  only; `construct`, `cancel_construct`, `answer`, `check_construct`
  take no lock; a deleted or amended node's construction job is
  cancelled and its evaluation job dropped in the completed events, inside the edit's one synchronous commit block,
  before its store write. Decided 2026-09-30 in the compilation session
  (「所以实际上最后的方案是把事务扩大了，对吗？」 「好的，赞同」, 11:05 UTC;
  recorded here 2026-09-30 by the audit): an edit is one enlarged
  transaction, preceded by the Isabelle round trip that copies the
  predecessor's state (two for `move`; DROPPED_DECISIONS_AUDIT.md §2.A.1,
  restored 2026-10-02 from READERS_2's A1) — pointer surgery, the in-memory invalidation as a
  synchronous recursion, the completed events (synchronous; the loader
  refuses an async override), then the store write of every node
  changed, status-changed or hook-fired — with the round trips
  (`theory_delete`, `state_delete`, and *(author, 2026-10-02, READERS_2's
  A19)* the `cancel(ids)` of the evaluation jobs dropped in the block)
  after it; `call_in_progress`, the
  dirty-database branch and the `TAT_compile` refusal line go. A job's
  settlement, an await-free stretch, lands before or after such a
  block, never inside it.
- From the review of steps 1 and 2 (2026-10-05, ai-artifacts/review/
  STEPS_1_2_REVIEW.md §4), the owner ruled: `hook.answer`'s `judged` is
  absent for a request answered 503 or 500, which was not judged
  (「按你的建议来」; LOGGING.md §4 and `log.py` are the logging session's
  to change); the `<client>` of the refusal sentence `TAT cannot serve
  this client: it is <name> <version>; TAT requires <client> <version> or
  newer.` is the name `-c` takes, `claude-code` or `codex` (「赞同」); a
  second announcement of a `tool_use_id` whose first call has not arrived
  is a bug on the `/hook` path, which ends the conversation (「建议当作
  bug」, then 「好的，赞同」 on the guard with its sentence `TAT received a
  second announcement of the call <id> before that call arrived; the
  client's hooks cannot be trusted.`; the ids are unique on both clients
  by their measured behaviour, so a repeat means the premise about the
  client's hooks is broken, and TAT stops rather than guesses). *(author)*
  On Codex the agent is
  named by the call's `_meta.threadId`, as CONSTRUCT_INTERACTION §8 states,
  created at the call (`agent.created` with `first="call"`), `main` when
  `threadId` equals `sessionId`; the announcement records the `callId`
  alone.

- Claude Code's internal agents (2026-10-13, the owner, after the live
  run's two ended conversations and the verification
  `ai-artifacts/review/steps_16_17/option_b_code.md`, `option_b_empirical.md`).
  A `PreToolUse` on a TAT tool whose payload carries `agent_id` and no
  `agent_type` is an internal agent's announcement: answered the grant,
  recorded as `hook.answer` judged `internal_announcement`, no agent
  created, no transcript read, nothing recorded for `agent_of_call`;
  decided in the Claude Code subclass, Codex unchanged. The refusal for
  a transcript not found stays for the main conversation; a subagent
  whose file has not yet been found at an announcement is served, and
  its file is read from the first announcement at which it exists (a
  subagent of type `fork` gets its file seconds after its first call) —
  a compaction before that first reading unseen, accepted. Internal
  agents' `SubagentStop`s are judged as the stop of an agent TAT has
  not met: allowed, no agent created. Accepted: when the main
  conversation runs as a
  custom agent, an internal agent's payload carries that agent's type,
  and TAT takes it for a subagent's. Written into CONSTRUCT_INTERACTION
  §1, §8, CLIENT_HOOKS §1, §2, MODULE_STRUCTURE §4.6, EXCEPTIONS §1,
  LOGGING §4.

## 11. `Theorem`

- Kinds `lemma`, `theorem`, `corollary`, `proposition`; schema `{kind,
  name, statement}`, `statement` the shared `LongStatement`
  (`STATEMENT_DEFS`: `Variable`, `LongStatement` copied from AoA), no
  description on the class or `kind`;
  descriptions: `name` `The fact's name`; `english` `the statement in
  English, as LaTeX text`; `for_any` `universally quantified variables
  to fix`; `Variable.type` `An Isabelle type expression. Leave empty
  ("") if unsure`; `premises` `named premises to assume`;
  `premises[].name` `binding name for the premise`; `premises[].term`
  and `conclusion` `Isabelle/HOL term with all literal numbers annotated
  with types`.
- Isabelle text is typed `IsaTerm` — AoA's value holding one text in
  both spellings, `unicode` for the agent and `ascii` (the `\<name>`
  form) for Isabelle, built only by `from_agent` or `from_isabelle`,
  `str()` refused, equal by `ascii` — moved from AoA's `model.py` to
  `Isabelle_RPC_Host.unicode`, AoA importing it from there. `for_any[]
  .name`, `for_any[].type`, `premises[].name`, `premises[].term` and
  `conclusion` are `IsaTerm`s built by `gen` with `from_agent`; the
  fact `name`, `english` and `Theory.description` are `str`.
  `isabelle_driver` takes and returns `IsaTerm` for Isabelle text
  (`.ascii` out, `from_isabelle` in); printing uses `.unicode`, emission
  `.ascii`; the store holds `.unicode`. The identifier check is a
  function beside `IsaTerm`, on `.ascii`, with `get_LETTER_SYMBOLS()`.
- `gen`: parent inside a theory (`BadTheoremNodeParent`); `name` in the
  id grammar without hyphens — ASCII, since it is the node's id
  component (`InvalidName`, grammar `fact name`, rendered `` `rev-length`
  is not a valid fact name: a fact name starts with a letter and
  continues with letters, digits, underscores and primes ('). ``);
  variable and premise names Isabelle identifiers in the `\<name>` form
  — a letter or letter symbol, then letters, digits, `_`, `'`, and
  `\<^sub>` before a letter or digit — so `ε` and `x⇩1` pass; unique; a
  variable's not ending in `_` (`InvalidField`, since 2026-10-11 one
  sentence for both, carrying the fact name's grammar text, written
  once in the framework: `The field \`statement.for_any[0].name\` must
  be an Isabelle identifier: it starts with a letter and continues with
  letters, digits, underscores and primes ('), and does not end with an
  underscore.` / `The field \`statement.premises[1].name\` binds \`ne\`
  a second time.`); terms and `english` normalised once when the construct is
  accepted (newlines to spaces, whitespace runs to one space; printing,
  emission and evaluation use the stored text; `Session`'s and
  `Theory`'s `description` stay as written). The carry on amend when
  `for_any`, `premises` and `conclusion` are equal, names included,
  `english` aside *(author: one private helper builds both the
  comparison and the structure sent to ML; an empty and a missing
  `type` are one form)*.
- Emission: `text ‹Lemma <name>. <english>›` (kind capitalised; a
  period added when `english` ends without `.`/`!`/`?`; `‹`, `›` and
  their ASCII forms replaced by `"`, nothing refused), the statement,
  then `by aoa` when `SUCCEEDED` and the stored proof check is `PASSED`
  (decided 2026-09-30, the compilation review judge's stricter variant,
  replacing "not `FAILED`"; an unchecked proof is `sorry`),
  else `sorry`; the whole text in `\<name>` form (`IsaTerm.ascii`); the
  Isar text is rendered only for emission. A name the theory's keyword
  table reserves — `open`, `if`, `for`, `value` … — is written in
  double quotes, the rule of `Token.print_name`; the evaluation judges
  each name with `Thy_Header.print_name` and the class records which
  names to quote in the stored field `reserved_names`, since emission
  runs on a loaded forest (ruled in the compilation session, status-4,
  ai-artifacts/COMPILATION_REVIEW.md; recorded here 2026-10-02).
- Evaluation: `TAT.Theorem.evaluate` runs one transition built in ML,
  `Toplevel.local_theory NONE NONE (theorem_cmd … #>
  Proof.global_skip_proof true)`, through `Toplevel.command_errors true`
  on the input slot's state — the shape of `begin_theory` — and writes
  the resulting state into the slot, so a `Theorem` under a future
  `Context` or `Locale` is checked inside it; any failure is the
  statement's (obstacle, `errors`, no state); never the `text` command,
  never a proof; the structure is sent in `\<name>` form. `run_commands`
  is not to be used at all (decided 2026-09-30): it registers each span
  in Isabelle's execution table, which a library load's
  `Execution.reset` wipes; `Theory`'s header already builds its
  transition in ML, and its `end` moves to an ML-built `Toplevel.exit`
  transition through `Toplevel.command_errors true`, after which
  `run_span` and `run_commands` are commented out — with the
  implementation, not before (decided 2026-09-30); until then the code
  still runs `end` through `run_commands`, under a DO NOT USE comment. `TAT.Theorem.check` forks the proof check as a
  Future task and returns (decided 2026-09-30, correcting the author's
  "plain Isabelle thread"); its work: the goal built in ML from the
  statement (`Specification.theorem_cmd` on the input slot's local
  theory, `Proof.goal`), the stored `product` replayed on it through
  `Phi_Sledgehammer_Solver.eval_prf_str` — AoA's own store-hit replay
  path, the text read as a method and evaluated on the goal under the
  recorded replay limits — a theorem `PASSED`, `Auto_Fail` `FAILED`
  with its message; no Toplevel transition, never the statement
  transition of the evaluation (decided 2026-09-30).
- `Proof_Job`: `proof construction(s)`; compulsory; `_check`: not
  `ready` → `\`X\` must be evaluated before its proof can be
  constructed.`; `SUCCEEDED` + check `PASSED` → `\`X\` is already
  proven.`; `SUCCEEDED` + no check or `RUNNING` → `\`X\` already has a
  proof; check it before constructing another.`; check `FAILED` →
  allowed; `_on_context_change` default; `finished_notification`
  `\`X\` is proven.` / `No proof of \`X\` was found:` + message;
  `failure_header` `No proof was found:`; `_run` ends with
  `Proof_Check.passed`.
- `Proof_Check`: `proof check(s)`; `make` default; `_start` calls
  `TAT.Theorem.check` with the input slot, the statement, `product` and
  `self.id`; replays `product` on the goal built in ML (above), with
  its recorded times, through the function exported from AoA (the
  entry on the time limit, below); bounds its own time; `_finished` default; `failure_header`
  `The proof no longer holds:`; `failure_notification` `The proof of
  \`X\` no longer holds:` + errors; class method `passed(node)`.
- *(author)* In the proposition line a premise or the conclusion that
  contains `⋀` or `⟹`, in either spelling, is parenthesized.
- `Theory` gets `description` (`str`, empty by default; `A summary of
  the theory, as LaTeX text`; emitted, when non-empty, as a `text ‹…›`
  block before the `theory` line, `‹`, `›` and their ASCII forms
  replaced by `"`, the content as written, no period added; never run;
  printed at `Recall` depth 0; an amend re-evaluates).

- `Theorem`'s construct carries an optional boolean `construct`,
  description `Whether to start the proof construction right away, once
  the node is evaluated. Default: false.` (approved 2026-09-30): the
  option of 2026-08-27 ("在用户添加 Theorem 节点时可以指定是否立刻开始 AoA
  证明，但默认是 not_started"), restored after the author removed it
  during the document sync of 2026-09-30. With `true` the construction
  starts once the edit's evaluation has made the node `ready`, as the
  `construct` tool would, the editing agent its owner; `construct: true`
  under `evaluate: false` is a `BadEdit` at the gate, `` `construct`
  needs `evaluate` ``; a node not `ready` afterwards starts nothing.
  When the node comes out `ready` with a proof already on it (an amend
  that carried one), the proof check comes first, and the construction
  is started as soon as that check has failed (the owner, 2026-10-01:
  「赞同证明检查在先，`construct: true`时，在证明检查失败后立刻进行构造」);
  a check that passes leaves nothing to start, which is no error: the
  edit succeeds and nothing is reported (2026-10-01, 「已有证明，且证明
  检查通过，此时显然是不需要报错，应该视作成功的」). A node that does
  not come out `ready` starts nothing and the edit's result says nothing
  more about it (「我认为不需要？evaluation 失败后无法启动构造是显然的」).
  The wish does not lapse there: the construction is to start by itself
  once the node can be constructed, and "whether to construct
  automatically" is to be a member of the construction job, for every
  node class that has one (the owner's direction, 2026-10-01: 「我认为
  应该自动启动构造。我认为这应该是绑定在所有具有 Construction Job 的
  nodes 上的一个属性（应该是直接绑在 construction job 上的）」), with the
  `construct` tool turned into, or merged with, the setter of that
  member (「把 construct tool 改成一种类似于 toggle_construct 的工具…
  或者至少是功能可以合并」). The direction is agreed (「大方向上赞同」),
  with `construct` and `cancel_construct` kept as two tools. The owner's
  proposals for their shape (2026-10-01, under discussion): `construct`
  gains an argument saying whether the nodes are constructed
  automatically from now on or only this once; both tools take a list of
  node ids, and a node that is not a leaf stands for every descendant of
  it that has a construction job — which replaces "`construct` takes one
  node" of §7. Decided: the argument is the value the nodes' setting
  takes — a `construct` without it, or with it false, turns an existing
  automatic construction off as well as starting the nodes this once
  (「我认为应该要关掉」; the author had proposed to leave the setting
  alone). `cancel_construct` interrupts the running construction jobs
  and gains an argument of its own saying whether automatic construction
  is turned off too, under the same name, `auto_construct` (the owner's
  proposal, 2026-10-01: 「给 cancel_construct 也加一个参数来指定是否要
  取消这个"自动 construct"，就叫"auto_construct"」). Left out or false,
  `cancel_construct` turns automatic construction off as well; true
  keeps it on (2026-10-01, 「赞同你的建议」, and the owner's own wording
  「True to keep their automatic construction on; otherwise, disable it.
  Default: disable.」). So each call of either tool sets the nodes'
  setting, and leaving the argument out means off. The descriptions of
  `auto_construct` (approved 2026-10-01): on `construct`, `True turns
  their automatic construction on; false turns it off. Default: false.`;
  on `cancel_construct`, `True keeps their automatic construction on;
  false turns it off. Default: false.` `Theorem`'s field `construct` is
  renamed `auto_construct` (approved 2026-10-01, 「好」), the initial
  value of the node's setting; its description is to be rewritten. A
  node of a `construct` call that cannot be started now is skipped, not
  refused (2026-10-01, 「赞同你的建议」): what can start is started; the
  setting is written on every node of the call that has a construction
  job, started or not; the result's first line says how many were
  started and each node's mark says the rest. The one failure left is a
  call that names no node with a construction job at all:
  `` `theory_X.section_Basics` has nothing to construct. `` when it
  named one node, `None of these nodes has anything to construct.` when
  it named several (approved 2026-10-02). A failed `construct` or
  `cancel_construct` renders the cause alone, without the `Cannot
  construct <id>` line (approved 2026-10-02, 「批准」), and starts or
  cancels nothing. The sentences
  refusing a single start — not evaluated, already proven, has a proof
  to check, already running — go. A call naming a node with children
  sets the nodes under it at that moment and nothing more: a node added
  under it later takes its setting from the edit that adds it (2026-10-01,
  「不算，应该遵循当时的 edit 命令的 auto_construct 参数取值」). That
  value is an argument of `edit` itself, `auto_construct`, beside
  `evaluate`, applying to every node the call adds that has a
  construction job (2026-10-01, 「赞同第二种写法」) — so `Theorem`'s
  construct carries no such field any more, the rename approved earlier
  the same day being overtaken, and no node class declares anything for
  it. The rule that refused the field under `evaluate: false`, with its
  sentence `` `construct` needs `evaluate` ``, goes (「接受」): the
  setting needs no start on the spot. The description of `edit`'s
  argument (approved 2026-10-01): `True turns the new nodes' automatic
  construction on; false leaves it off. Default: false.` — an amend's
  new node takes the edit's value, not the replaced node's. *(author)*
  The value does not travel in `NodeConfig`: the framework writes it on
  the new node's construction job after `gen` returns, as it handles
  `evaluate` itself, and reads it back from its own reserved field at
  load; no class sees it. When automatic construction acts (2026-10-01,
  「就是在 evaluation 到每个 node 的时候需要的话去激活 construct」): an
  evaluation that reaches a node whose setting is on starts its
  construction job if the node needs it — it is `ready`, the job is not
  running, and it has no proof. A node whose construction ran to its end
  and failed does not need it again while its context is unchanged, and
  does once the context has changed (「这显然是不算，除非 context 发生了
  改变」). A node with a proof is checked first, and a failed check starts
  the construction, as decided above. Automatic construction never
  starts an evaluation of its own. A run started this way is owned by
  the agent whose call ran the evaluation — it answers the run's
  questions, is told of its end, and does not leave while it runs — and
  one started on a failed check by the agent whose evaluation started
  that check (2026-10-01, 「赞同你的建议」; the agent that turned the
  setting on may be long gone). The tool descriptions (the owner's
  wording, 2026-10-01): `construct`, `Start the construction jobs of
  nodes, such as {titles}.`, the loaded construction job classes'
  titles spliced in; `cancel_construct`, `Cancel the running
  construction jobs of nodes.` A tool description says nothing of the
  arguments: `node_ids` and `auto_construct` are described in the
  schema, each on its own argument (「node_ids，auto_construct 这些放到
  Schema 的 argument description 中，你别在 tool description 中写」).
  `construct`'s `node_ids` (approved 2026-10-01, the owner's "non-leaf"
  for the author's "with children"): `The ids of the nodes whose
  construction jobs to start; a non-leaf node stands for every node
  under it.`; `cancel_construct`'s is the same sentence with `cancel`
  for `start`. `{titles}` renders, with `Theorem` alone loaded, `Start
  the construction jobs of nodes, such as proof constructions.`
  (「很好」). `construct`'s `auto_construct` (approved 2026-10-01, the
  owner's sentence with the author's `start`, `not constructed yet` and
  `automatic construction`), the one place that says what automatic
  construction is: `If true, automatically start the construction of
  each node whenever an evaluation reaches it and it is not constructed
  yet; false turns this automatic construction off. Default: false.` —
  it replaces the shorter sentence approved for `construct` earlier the
  same day; `edit`'s and `cancel_construct`'s stand. A node whose
  setting is on shows it on its line, whatever its state, as a tag the
  framework adds after the class's own words, `automatic construction`
  (2026-10-01, 「赞同第一种」): `- lemma_P (not evaluated, proof not
  started, automatic construction)`, `- lemma_Q (valid statement,
  proven, automatic construction)`. A `construct` that starts several
  nodes names every node it started, and a `cancel_construct` every node
  it cancelled (2026-10-01, 「必须把所有启动的 nodes 全都列出」
  「cancel_construct 也是」; the author had proposed a count), and so
  does a call whose evaluation started constructions automatically
  (「evaluation 过程中所有启动的 constructions 的 nodes 也必须全部列出」).
  The lines (approved 2026-10-01), in the form `check_construct`'s state
  lines already have — one node, the existing sentence; two or three,
  one sentence with `on` repeated and `and` before the last; more, a
  header and one id per line:
  ``Started the proof construction on `theory_X.lemma_P`; call
  `check_construct` before you exit.`` /
  ``Started the proof construction on `theory_X.lemma_P`, on
  `theory_X.lemma_Q` and on `theory_X.lemma_R`; call `check_construct`
  before you exit.`` /
  ``Started the following proof constructions; call `check_construct`
  before you exit:`` + `  - theory_X.lemma_P` … /
  `No construction job was started.`;
  ``Cancelled the proof construction on `theory_X.lemma_P`.`` /
  ``Cancelled the proof construction on `theory_X.lemma_P`, on
  `theory_X.lemma_Q` and on `theory_X.lemma_R`.`` /
  `Cancelled the following proof constructions:` + the ids /
  `No construction job was running.`
  `construct`'s and `cancel_construct`'s line stands above the
  quickview, the named nodes its focuses. A call that ran an evaluation
  (`edit`, `evaluate_to`) puts the same `Started …` line at the end of
  its result, beside the background line, and nothing when none was
  started. A construction started on a failed check, after the call
  that started the check has returned, is told with the agent's next
  result, whatever the tool: the check's `failure_notification`, one
  message per node since each carries its own errors (not merged:
  2026-10-01, 「赞同你的观点，不合并」), and after the
  messages one `Started …` line naming every construction started
  automatically for that agent since its previous result (confirmed
  2026-10-01, 「确认没错」) — so several of them read as one line or one
  list, not as the same sentence repeated. The whole result of an
  `evaluate_to` that started constructions (approved 2026-10-01): the
  opening line, the quickview with `proving` and the `automatic
  construction` tag on the lines, then the `Started …` line or list,
  then the background line. A header that ends in a colon and has an
  empty message under it is written with a period instead and nothing
  below (approved 2026-10-01) — the two failure notifications and the
  two failure blocks' headers: ``The proof of `X` no longer holds.``,
  `The proof no longer holds.`, ``No proof of `X` was found.``, `No
  proof was found.` A failed proof check gives no reason at all
  (2026-10-01, 「建议什么都不显示，因为实际没有有意义的信息。the agent
  能做的也仅仅是重新调用 AoA 去重新证明」): the replay function reports
  a class of failure and no text, and the agent can only have the proof
  constructed again. Its notification says so and tells what to do next
  (the owner's draft 「The proof of `theory_X.lemma_C` no longer holds.
  Run `construct` to re-prove it」, `Call` for `Run` as elsewhere). With
  no errors of their own, the notifications of several nodes are merged
  in the form the `Started …` line has (2026-10-01, 「赞同」, reversing
  "not merged" of the same day, whose reason was the errors):
  ``The proof of `theory_X.lemma_C` no longer holds. Call `construct`
  to prove it again.`` /
  ``The proof of `theory_X.lemma_C`, of `theory_X.lemma_G` and of
  `theory_X.lemma_K` no longer holds. Call `construct` to prove them
  again.`` /
  ``The following proofs no longer hold; call `construct` to prove them
  again:`` + `  - theory_X.lemma_C` …
  Under automatic construction the construction starts at once, as
  decided (「开着自动时是立刻」), so those nodes' notification is the
  first half alone — ``The proof of `theory_X.lemma_C` no longer
  holds.``, and the list forms without the instruction — and the
  `Started …` line follows it. The failure block under the node is the
  header alone, `The proof no longer holds.` (This answers the readers'
  O3.)
- The proof check's time limit (2026-10-01; answers the readers' O2).
  TAT keeps storing the proof itself (「我们当然还是要保存证明的，但是用
  AoA 的重放机制」): the method text — `aoa_replay "<b64>"` when AoA's
  agent found it, a plain method text such as `metis …` when Sledgehammer
  did — and beside it the two times recorded with it, the thread's CPU
  time and the wall time of its replay, the pair AoA's own store rows
  hold. The check replays that pair through a function exported from
  AoA — the part of `Proof_Store_AoA.store_hit_replay` that takes one
  record, derives the limits with `Phi_Proof_Store.replay_limits` and
  runs `eval_prf_str` — and reads nothing from AoA's store and changes
  nothing in it (「确认」). TAT writes no limit formula and no handling
  of the replay's failure classes. How AoA hands the times over with the
  proof is the AoA round's. *Superseded in part (2026-10-03, §15):* the
  construction reads and writes AoA's store through AoA's own path; the
  check still reads nothing from it; the times come back with the text
  from `hammer_or_AoA`.
- THEOREM §7's clause "the same goal is what `Proof_Job` hands to
  `run_AoA`" is deleted (2026-10-01, 「赞同删掉」; answers the readers'
  O9): how TAT drives AoA stays whole with the AoA round. What stays
  said: the check and the construction are about the same statement.
- `Sessions:` is a header, not a node's line, and carries no mark
  (confirmed 2026-10-01, 「确认」; answers the readers' O10): PRINT §6
  stands; §1's "no line is bare" is said of nodes' lines, and the
  sentence that the briefing writes nothing under a line excepts the
  empty forest's hint. No rendering changes.
- Emitted text that closes (2026-10-01; answers the readers' O6): no
  check and no special rule. What a node writes into a `.thy` is
  generated by TAT's own code, and that code is trusted to write text
  that closes (「代码生成是我们自己控制的，我们总得相信我们自己的代码
  是对的」; the author had proposed escaping every term at emission as a
  guarantee by construction). ARCHITECTURE §5 and §7 lose the claim
  that unclosed text "fails at its own node's evaluation": a class's
  emission is responsible for its own text.
- Automatic starts say that they are automatic, and why (approved
  2026-10-02, after 「难道不应该强调是由于 xxx 而自动启动的吗？」). A
  construction started on a failed check is told by the failure
  notification itself, one sentence: ``The proof of `theory_X.lemma_C`
  no longer holds, so its proof construction was started automatically;
  call `check_construct` before you exit.`` / ``The proof of `C`, of `G`
  and of `K` no longer holds, so their proof constructions were started
  automatically; call `check_construct` before you exit.`` / ``The
  following proofs no longer hold, so their proof constructions were
  started automatically; call `check_construct` before you exit:`` +
  the ids. One started by an evaluation that reached the node ends that
  call's own result with ``Automatically started the proof construction
  on `theory_X.lemma_A`; call `check_construct` before you exit.`` (the
  same forms for several). This replaces, from 2026-10-01: the
  notification "…no longer holds." followed by a separate `Started …`
  line, and the rule that every result ends with a `Started …` line for
  what was started since the previous one — so a `construct` result
  carries one `Started …` line, its own. Nodes not under automatic
  construction keep "… no longer holds. Call `construct` to prove it
  again." NOT YET in the documents (CONSTRUCT_INTERACTION §3.4, §5, §6;
  THEOREM §7; RENDER_BASELINES §6).
- `answer`'s refusals (approved 2026-10-02). A node with no question
  waiting — no construction job, a job not running, a run that has asked
  nothing — is answered one sentence, whatever the job's state: ``
  `theory_X.definition_f` has no question waiting for an answer. ``
  (the owner: 「直接说"theory_X.definition_f 上没有关联的问题"」, 「也不
  需要给 construction job 的状态了」). A question that belongs to
  another agent's run: ``The proof construction on `theory_X.lemma_P`
  belongs to another agent.`` (the owner's wording, replacing "… is
  another agent's."). `ConstructNotRunning` and `not_running_refusal`
  go; `NoQuestionPending` covers the first sentence, which is the
  framework's and no longer composed from a title. NOT YET in the
  documents (CONSTRUCT_INTERACTION §3.2, §5; RENDER_BASELINES §2;
  EXCEPTIONS §3; THEOREM §7).
- The fact-name sentence (approved 2026-10-02) says the whole grammar:
  ``rev-length` is not a valid fact name: a fact name starts with a
  letter and continues with letters, digits, underscores and primes
  ('), and does not end with an underscore.`` — written into
  RENDER_BASELINES §2 and THEOREM §4 the same day.
- "Message" keeps both senses (2026-10-02, 「两个意思都保留」): text
  addressed to one agent — a notification or a question — and the
  messages of a status value, Isabelle's output of a run, as the
  glossary (ARCHITECTURE §1) has them; CONSTRUCT_INTERACTION §2 gains
  the second.
- The table from an evaluation job's id to the job is the process's,
  not a conversation's, and each job holds the `Conversation` it was
  made in; the `job_finished` report, arriving on a pooled RPC
  connection that belongs to no conversation, finds the job by its id
  and the conversation through the job (approved 2026-10-02, 「批准此
  建议」; found by the logging session's reviews,
  ai-artifacts/review/LOGGING_AGENT_DIRECTORY_RULING.md §1, C6; the
  sentence "reached from the connection the report arrives on" of
  CONSTRUCT_INTERACTION §3.3 was the author's error). Written into
  CONSTRUCT_INTERACTION §3.3 the same day.
- The caller's messages are taken from its mailbox only after the
  handler's cancellation checkpoint, when the result is about to be
  sent; a result nobody receives — the agent client gave the call up
  before the checkpoint — leaves the mailbox as it was, for the agent's
  next call (approved 2026-10-02, 「赞同」; the companion change of
  CONSTRUCT_RULING_3, found again by the logging session's reviews).
  Accepted with it: a cancellation arriving between taking the messages
  and the client's reading of the result still loses them — a window of
  milliseconds that TAT cannot see, since MCP carries no receipt; the
  stopped subagent's messages are nobody's, and `check_construct`'s
  clamp keeps its return a minute before the client's twelve-hour limit.
  Written into CONSTRUCT_INTERACTION §3.4 and MODULE_STRUCTURE §4.6 the
  same day.
- The framework's wrapper around `_run`, the only thing `start` spawns,
  sets the log's `agent` context variable to the run's owner as its
  first step, so a run started on a failed check — spawned from the
  report's path, which inherits no agent — logs under its owner like one
  started by `construct`; `call` stays inherited (approved 2026-10-02,
  「采纳」; the logging session's D20, written in LOGGING.md §3 already).
  Written into CONSTRUCT_INTERACTION §3.2 "The run" the same day.
- The order of implementation (2026-10-02, 「赞同后者」): the framework
  first — jobs, agents, hooks, compaction, the tools, rendering, `Theorem`
  without its jobs — and the AoA round after, adding `Proof_Job._run`,
  `Proof_Check` and what they need. The plan: CONSTRUCT_IMPLEMENTATION_PLAN.md,
  written the same day, citing the documents and repeating none of them.
  Until the AoA round `Theorem` names no job class: the construct tools
  do not exist for it and its proofs are written `sorry` (2026-10-02,
  「建议构造工具对它不存在，它的证明一律写成 sorry」).
  The plan was withdrawn on 2026-10-03 after its check
  (ai-artifacts/review/IMPLEMENTATION_PLAN_REVIEW.md): the compilation
  system and the logging system are implemented first, this session's
  part after, from a plan rewritten then (「先把这个实现计划标记为废弃，
  我会先实现 compilation 和 logging system 之后你再实现」). The order
  decided the day before — the framework before the AoA round — stands
  within that part.
- A compaction check that fails ends the conversation, as an
  unannounced call does: `TAT_InternalError` carrying the check's
  message, which the launcher prints; the agents read the ending's
  existing `an internal error` line, and the log's `agent` event
  `check_failed` (level `error`) records it (the owner, in the logging
  session, 2026-10-03: 「建议继续结束 conversation」; LOGGING.md §4). The
  checks and their messages (approved 2026-10-03, 「批准」): a boundary
  whose own timestamp precedes the agent's previous served announcement,
  `TAT found a compaction of agent <id> recorded after a result it had
  already rendered for that agent; its reading of Claude Code's
  transcripts cannot be trusted.`; a `PostCompact` received while no new
  boundary appears in any transcript within 10 seconds, `TAT received a
  PostCompact hook but found no compaction boundary in any transcript
  within 10 seconds; its reading of Claude Code's transcripts cannot be
  trusted.` — for which `PostCompact` is registered on Claude Code
  again, answered with nothing and read for the count alone. Neither
  check clears a seen set. Written into CONSTRUCT_INTERACTION §8 and
  CLIENT_HOOKS §1–§2 the same day.
- `on_invalidated` stays (2026-10-02, 「on_invalidated 留着」): a node
  event, fired by the status setter when an operation's status leaves
  `ready`, for a class that keeps something derived from its evaluation
  and must discard it then; telling a running construction job of a
  changed context is `_on_context_change`'s, not its. No shipped class
  overrides it. MODULE_STRUCTURE §4.1's event table is to say what it
  is for.
- `run_commands` after `Theory`'s `end` leaves it (2026-10-04, 「赞同。
  但需要明确注释"尽量别用 run_commands"」): `run_commands`, `run_span` and
  `command_record` leave `TAT_Framework` and move into the test
  plugin's `TAT_Test_Lib` as test code, under a comment saying to avoid
  `run_commands` wherever possible; the framework's signature gains the
  two output-buffer functions `run_span` calls. No product code runs
  Isar text. This replaces the entry of 2026-09-30 in that one part:
  the "two tests" it meant to rewrite are the test plugin's callbacks
  `TAT_test.run` and `TAT_test.run_parallel`, through which
  `test_conversation.py` runs Isar text in seventeen places.
- `Theorem` before its jobs exist (2026-10-04, 「赞同」): no conversation
  loads `Theorem` until `Proof_Job` and `Proof_Check` are built; until
  then its ML registration names no Python package, and only its own
  tests' conversations list the package. So a `Theorem` without a job
  class — a line with no proof slot, a theory of `sorry` theorems
  reading `complete` — never reaches an agent. This replaces the entry
  of 2026-10-02 that `Theorem` is loaded with no job class and its
  proofs written `sorry`.
- `Theorem` is a plugin of its own (2026-10-04, 「Theorem 会是一个单独的
  pluin，放在这个 plugin 的单独的 major thy file」): its ML — the
  callbacks `TAT.Theorem.evaluate`, `construct` and `check` — lives in
  the plugin's own major theory, which imports AoA's; it leaves
  `TAT_Common_Nodes`, and TAT's own theory keeps importing
  `Isabelle_RPC` alone.
- The plugin is `Isabelle_Std` (2026-10-04, 「建议把此 plugin 扩展为
  Isabelle std 然后未来会加上 section, text, locale, datatype, typedef
  等等 Isabelle 标准命令」, then 「批准以上设计。批准名字」): one plugin for
  the node classes of Isabelle's standard commands, `Theorem` its
  first. Its directory `Isabelle_Std/` in TAT's repository is an
  Isabelle component of its own, with its own `ROOT` — session
  `TAT_Isabelle_Std = Minilang_AoA + sessions Theory_Agent_over_Trees`
  — which TAT's top-level `ROOT` does not name, since Isabelle refuses
  the whole session structure over a `ROOT` whose parent session is
  unknown, and TAT must work where Isa-Mini is absent. Its major theory
  `TAT_Isabelle_Std` imports
  `Theory_Agent_over_Trees.Theory_Agent_over_Trees` and
  `Minilang_AoA.Minilang_AoA` and loads one ML file per node class from
  `Isabelle_Std/ML/` (`TAT_Theorem.ML`, `structure TAT_Theorem`). Its
  Python half is the subpackage `isabelle_theory_agent.std`, one module
  per class (`theorem.py`; `statement.py` for `STATEMENT_DEFS`), which
  replaces `builtins.py` and `theorem_node.py`. `TAT_Common_Nodes`
  keeps `operation` and `Theory`. A working directory takes the plugin
  by `isabelle TAT_new -P TAT_Isabelle_Std.TAT_Isabelle_Std`, written
  explicitly (「TAT_new 显式写 -P」), and is launched on the base heap
  `Minilang_AoA`; the plugin's tests run in a harness run of their own
  on that heap.
- The import `by aoa` needs is the plugin's to write, not the agent's
  (2026-10-04, 「aoa 的 import 由 Isabelle_Std 写不好吗？」, then
  「思路是赞同的。但反对对每个 theory 都加，应该分析 theories' dependent
  graph 只对头部的几个加，剩下的就自然会被加上」, 「赞同 Theory 两处都
  加上」, 「赞同对所有 theory 生效，不看里面有没有 Theorem」): a plugin
  declares theories that the conversation's theories import besides
  what the agent wrote — `Isabelle_Std` declares
  `Minilang_AoA.Minilang_AoA`, where the `aoa` method is defined. The
  framework's `Theory` adds them to its header both when it runs the
  header in the conversation and when it emits the `.thy`, after the
  agent's own imports, and only on a theory none of whose imports
  resolves to a theory of the forest: every other theory receives them
  through the forest theories it imports. Whether the theory holds a
  `Theorem` plays no part. *(author)* The declaration is made at
  import in the plugin's Python package, registered as a compile hook
  is; evaluation and emission write the header through one function,
  so the two cannot differ. `recall`'s `imports` line shows what the
  agent wrote and not the added import (「赞同不显示」). MODULE_STRUCTURE §1, §3, §4,
  §4.5, PLUGIN_SYSTEM §1–§2, SESSION_AND_THEORY §2, THEOREM.md's
  opening and §7, ARCHITECTURE §2.2 and OPEN_QUESTIONS §1, §3 are
  brought in line once that is settled.
- The tool `evaluate_to` and `Theory`'s `description` field are the
  jobs session's to build (2026-10-04, 「好」).
- `check_construct` exists when a loaded class names a job class of
  either kind (2026-10-04, 「赞同补上」); `construct`,
  `cancel_construct`, `answer` and `edit`'s `auto_construct` still
  exist only with a construction job class, `checks` only with an
  evaluation job class. Before, a conversation whose classes named
  evaluation jobs alone had no `check_construct`, while `checks`'
  description, the background line and the stop rule's instructions
  all send the agent to it. With no construction job class loaded its
  description is `Wait until all {evaluation titles} have finished, or
  a message arrives. Returns at once when nothing is running. To ensure
  all jobs have finished, call it repeatedly.` — the titles as in the
  full form.
- MCP's `readOnlyHint`: delivering the caller's messages is no change
  (the owner, 2026-10-01: 「它只是发送了 construct 的消息而已」), so a tool
  is read-only when it changes no node and no job — `recall` and, from
  now on, `check_construct` (「赞同，check_construct 应该是只读」). The
  sentence "`check_construct` is not read-only, since it delivers
  messages" of MCP_SPECIFICATION goes. (This answers the readers' O8.)
  *(author)* On `cancel_construct` a run owned by another agent is
  skipped like any node that cannot be acted on, and goes on running;
  the setting is written all the same. Open: the tools' own descriptions and
  `node_ids`'; the result's first line; who owns a run started automatically; what happens after a run
  fails; how the agent is told of a construction started after its edit
  has returned; whether a construction started within the edit prints
  the starting notice.

## 12. Measured

AGENT_CLIENTS_MEASURED.md and `ai-artifacts/probes/`: Codex subagent
`_meta.threadId`; no hook-trust config equivalent; Unicode rejected by
Isabelle/ML; the stall watchdog ignores tool-call time; the state
rebuild (`make_state` suffices); departure hooks on both clients (none
for the subagent); M1 (the cap variable works; the ceiling counts only
blocks with no tool call between); M4 (hook cwd = session cwd; project
settings load only from the working directory); M5 (Codex's
`SessionStart` after the MCP handshake; every `tools/call` preceded by
its `PreToolUse`). Review 2 (`ai-artifacts/probes/review2_*`): Claude
Code grants TAT's tools no permission unless the `PreToolUse` answer
carries `permissionDecision: allow` (refused under `-p`, a prompt for a
background subagent; the answer works with no rule, trust or launch
flag); Claude Code's `/clear` and `/resume` fire `SessionEnd` then
`SessionStart` while a background subagent keeps calling TAT; Codex's
root `SessionEnd` comes at the idle unload, about 60 s after `/new`
(source read); an ML report can overtake the callback's reply (asyncio
model). 2026-09-30 (`ai-artifacts/probes/stop_hook_reason_codex/`): on
Codex a blocked stop's reason reaches the model for `Stop` and
`SubagentStop`, both forms, as a user-role `<hook_prompt>` message in
the blocked agent's own conversation, verbatim but for trimming, the
XML escaping of `&`, `<`, `>`, and a cut to about 10 KB with the full
text saved to a file; repeated blocks all delivered. 2026-09-30
(`probes/late_result_after_followup_codex/`,
`probes/interrupt_denial_claude_code/`,
`probes/interrupt_denial_codex/`, `probes/codex_path_mapping_*`): a
Codex subagent interrupted and resumed never sees the result of the
call it had in flight; a `PreToolUse` hook denies `TaskStop` (Claude
Code 2.1.285; its `task_id` is the subagent's `agent_id` only when the
parent passes that — it may pass the launch name in any capitalisation
or the id in the old `shell_id` field, and Claude Code resolves all
three after the hook; a stopped subagent's foreground children stop
with it, background ones survive) and `interrupt_agent` (Codex,
target named by path, no payload carries path and thread id together)
with the reason reaching the parent as the call's error result; a
message to a busy subagent arrives after its current call (Claude Code)
or at its next code-mode yield, within 31 s (Codex); every
deterministic path-to-thread mapping needs Codex's rollout file
(`ai-artifacts/review/CODEX_PATH_MAPPING_RULING.md`).
Pending at implementation: M6 (the suite with the inverted test),
`check_for_update_on_startup`'s layer, the slot-release order. Measured
2026-10-13 in interactive sessions (`ai-artifacts/probes/live17/`,
Claude Code 2.1.296, Codex 0.156.1): the project-level files of
CLIENT_HOOKS §2 and §3 are read; `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP=0`
from the project settings honoured 164 consecutive text-only `Stop`
blocks; `CLAUDE_CODE_SKIP_PROMPT_HISTORY=0` and
`CLAUDE_CODE_FORCE_SESSION_PERSISTENCE=1` there turn the transcript
back on under an inherited `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1` and
`CLAUDE_CODE_CHILD_SESSION=1`; the first request after `initialize` is
`tools/list`; Codex opens one MCP session per thread; after every
main-conversation turn Claude Code fires a `SubagentStop` for an
internal agent whose `agent_transcript_path` names no file; and twice a
`PreToolUse` on a TAT tool came under an `agent_id` with no
`agent_type` and no transcript — read in the 2.1.296 bundle
(`ai-artifacts/review/steps_16_17/orphan_agent_static.md`), these are
Claude Code's internal agents, whose calls its own permission function
refuses after the hooks (`ai-artifacts/probes/live17/REPORT.md` §4.1;
AGENT_CLIENTS_MEASURED.md); each time TAT ended the conversation by
§10's rule of 2026-10-01, narrowed by the owner on 2026-10-13 (§10,
Claude Code's internal agents). Measured
2026-09-30 (probes `codex_subagent_compaction`,
`claude_code_subagent_compaction`, both REPORT.md): Codex runs
`PreCompact`/`PostCompact` for every thread, `agent_id` naming a
subagent, `SessionStart(compact)` for the main conversation only, its
`additionalContext` reaching the model, a compaction hook's answer never;
`_meta.windowId` counts compactions; Claude Code runs `PreCompact`,
`SessionStart(compact)` and `PostCompact` for a subagent's compaction
without naming it, the `additionalContext` reaching exactly the
compacted agent, the `compact_boundary` on disk before the agent's next
`PreToolUse` (39 of 39); `SessionStart` sources `resume`, `clear`,
`startup` (and on Codex `fork`) all reach the model.

## 13. Deferred to the AoA round

Decided on 2026-10-03 and moved to §15: the drive path, driver and
budget, the bound on how many constructions run at once (2026-10-01),
the proof store, how AoA hands over a proof's replay times, and the
function it exports for the replay of one record (the time limit itself
was decided in §11). Still deferred: the question kinds; a job that
continues through a context change and repairs a stored proof (`start`
handing `_run` the outcome it clears; `_run` ending with a replay
instead of `passed`); to measure, not to design, cancellation on the
AoA side. Two requirements of the owner's bind the round (2026-09-22,
"关键的，AoA 中的 request_lemma … 这个 request report 要上报给 TAT 的 the
running agent"; "我们需要某种机制告诉 AoA 它正运行在 TAT 下并以能跟 TAT
通讯"; restored 2026-09-30 after the author had dropped them from this
list on 2026-09-27): AoA's `request` tool reports to the TAT agent
driving the job, as a question that agent answers, instead of adding
subgoals in AoA's own global environment; and AoA is told it runs under
TAT and given a way to talk to TAT. What `product` holds is decided
(§2).

## 14. Withdrawn

The `status` tool; `wait_construct`; the `Question:` header; printing
the question under the node; the parent fallback (G23) and the
ninth-stop cancellation; the hook reason G22 (`Your proof construction
on \`X\` and on \`Y\` have not finished; …`); TAT's block count and stop
policy per client; a TAT-side fuse or timeout; departure detection; P3
(any agent may cancel); `_cancel()`; `job.fail()`; the replay flag;
"cancel returns to the outcome before the run"; the job's mark-words
method and the marks `proving`/`proven`/`no proof`/`bad proof` as a
set of four; `_owes_nothing` and `_is_self_complete`; the job built in
the class's `__init__`; `ask` returning the answer; `Question(text,
schema, check)`; `check_construct` refused when there is no job; `Every
construction job of yours has finished.`, `Every proof check of yours
has finished.` and the per-node `… has finished.` line; `You have no
construction job running.` and `You have no job running.`; `Cannot
answer …`; `success` as a mark and the bare mark; `Theorem` printing
its statement outside `Recall`; evaluation running `by <stored method
text>`; `Proof_Job` owning `The proof no longer holds:`; the `create`
remote procedure; `_settle`, `record_evaluation_job`,
`_start_evaluation_job`; §10's "Choice: B2" and the `run_span`
envelope; the 30-second progress notification (the review's A13);
`check_proofs` as the parameter's name; the two earlier
`check_construct` descriptions; the per-process `SessionStart` fact;
"an unannounced call is the main conversation"; `/on-compaction` as an
endpoint of its own; `Construction_Job.title` as an instance method;
`Incompleteness.sentence()`; the framework starting a check after a
construction succeeds; `TAT_AGENT` / `X-TAT-Agent`; Scala's
`write_hooks`. After review 2: settlement under the forest lock;
`Evaluation_Job.start(node, starter) -> Self` as the abstract class
method, and `_finished` under the lock; `blocking` waiting for the
call's own jobs and handling their reports; the `session_end` event;
the keyword guard with `` `open` is a keyword of this theory and cannot
name a premise. ``; `Toplevel.make_state` for `Theorem`'s state; the
summary under every nesting node (P2) and its `not evaluated`
exception; the stop hook's reason as a delivery of messages and
questions, with `The \`TAT\` server blocked your exit to deliver the
messages you have not seen yet:` and the `Answer the question{s} …`
instructions; the server name `tat`; an identifier check through an ML
callback. After review 3: an async `make`; "a `_start` that raises
reports the error as the evaluation's"; the ending cancelling the runs'
tasks rather than the jobs; the wrapper sorting `_run`'s end by
exception type; "the input theory" for the proof check; the rule "only
the latest call's result takes messages" (review 3's F3, superseded by
refusing interruptions); an unconditional refusal of every
interruption; refusing on Codex by the caller's children (unsound: a
sibling may interrupt a sibling); mapping a Codex path to its thread
id through the rollout's first line or the UUIDv7 timestamp
(researched and verified, not adopted); the `updatedInput` rewrite of
the target; state lines in the refusal's reason; the stop hook's
opening line changed to `You cannot exit yet:`. After review 4
(2026-09-30): judging the interruption's target alone on Claude Code
(`task_id` = `agent_id`), unsound twice over — a target named by its
launch name or `shell_id`, and a target's foreground descendants; the
hybrid rule "the target when its id is known, every agent otherwise";
forbidding nested subagents through
`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`; reading `agent-<id>.meta.json`
for a target's descendants. Corrected by the owner
on 2026-09-30 (§4): the plain Isabelle thread for evaluation jobs and
`Future.interruptible_task` around their work, both the author's
without approval; the statement transition inside the proof check's
work; "how the replay is done is the AoA round's" (it is `eval_prf_str`,
§11); `run_commands` as `Theory`'s `end` path (§11). Found by the audit
of 2026-09-30 (ai-artifacts/review/DROPPED_DECISIONS_AUDIT.md) and
corrected the same day: the `product` as "an opaque string whose content
the AoA round decides" (§2); the `aoa` proof method as "replays the
proof the construction job found" (ARCHITECTURE §2.1, changed during the
document sync without being on its list); the AoA `request` routing
dropped from §13; the two-step rerun (§3); `evaluate_to`'s opening line
left unwritten (§7); the Codex refusal rule's exclusion written as the
owner's (§9); the outcome "never stored" (§4). Withdrawn on 2026-10-02
by the owner's rulings in the compilation session: A3 in both its forms
— "when the walk reaches the destination without rerunning it and
without arriving blocked, the nodes past it are left as they are", with
its fifth walk mode "past the destination, touch nothing" and the
inverted test, and the form of 2026-10-01, "a rerun that stores a
different value is an edit at that node"; the status setter's instant
and stored halves and the walk's record of change. Withdrawn on
2026-10-01: `Theorem`'s `construct` field and its rule under `evaluate:
false`; the refusals of a single `construct` (`ConstructAlreadyRunning`
and `Proof_Job`'s three sentences); "`construct` takes one node".
Withdrawn on 2026-10-03 (§15): the proof check's goal built from the
statement by a second `theorem_cmd`; `Theorem`'s evaluation as one
transition; the compile hook writing the proof stores from the forest's
proofs; "TAT changes nothing in AoA's proof store" as said of the
construction.

## 15. The AoA round: the drive path (2026-10-03)

Decided in the forked session on 2026-10-03; THEOREM.md §1, §5–§7,
CONSTRUCT_INTERACTION §10, OPEN_QUESTIONS §2, ARCHITECTURE §2.1, §3.1,
§9, MODULE_STRUCTURE §4.1, §4.3 and COMPILATION.md state it.

- The drive path (「我认为应该第一条，但不是从陈述建出目标。Theorem node 的
  evaluation 需要记录 the state after opening the proof goal 且尚未开始证明的
  Toplevel.state，并调用框架接口赋予一个 slot … 然后 the Construction job
  把这个 slot 发给 a callback 然后 the callback 取得 Proof state 然后调用
  AoA 的（标准）启动接口」): `Theorem`'s evaluation applies two
  transitions instead of one — the `lemma` command's own
  (`Toplevel.local_theory_to_proof` of `Specification.theorem_cmd`),
  whose result, the goal open and no step taken, goes into a slot the
  class owns; then the admit (`Toplevel.end_proof
  Proof.global_skip_proof`, the toplevel half of `Isar_Cmd.skip_proof`),
  into the resulting slot. The construction job hands that slot to the
  class's third callback, `TAT.Theorem.construct`, which takes the
  `Proof.state` and its goal and runs AoA's standard entry on it; the
  proof check replays the stored product on the same goal instead of
  rebuilding it from the statement — the two now work on one goal by
  construction. The author's shapes, told to the owner: the slot is
  `goal_state`; a further slot is the class's own to mint and to
  delete, as `Theory` does for the slot it owns — the class mints it
  where the node is built, in `gen` and `from_store`, and appends it in
  `_states_inside()` — and the framework does the one thing a class
  cannot, the release on invalidation: `Node._slots_written_by(operation)`,
  empty by default, names the further slots an operation writes, and
  each setter taking the operation from written to unwritten releases
  them with its resulting state, never on a rewrite (the owner's ruling
  of 2026-10-04 in the compilation session, as that session reports,
  「赞同甲」, on his question whether the framework must do this at all;
  it replaces the class attribute `owned_slots`, which the framework
  minted). A rerun that takes a `ready` leaf to `cannot_evaluate` is a
  rewrite and releases nothing, so `TAT.Theorem.evaluate` clears
  `goal_state` itself when it fails; the invariant that `goal_state` holds a state exactly
  while the node's instant status is `ready`, which keeps a loaded
  forest — `not_evaluated` throughout — from starting a construction on
  an empty slot.
- The standard entry is `hammer_or_AoA` with Sledgehammer first
  (「保留」), as the `aoa` method itself: the proof store looked up,
  then Sledgehammer, then the agent, the proof written back. The owner
  allowed the change to Isa-Mini this needs (「允许」): `hammer_or_AoA`
  returns the replay times beside the text, in the store's
  standard-machine form, and the per-record replay inside
  `Proof_Store_AoA.store_hit_replay` is exported for the check.
- The proof store is written, and read, through AoA's own path
  (「我认为还是需要写 proof store 文件的。这样就可以继续写 `by aoa` 了」), so
  emission keeps `by aoa` (ARCHITECTURE §2.1 stands). Verified in the
  code the same day: the store file is `<master directory of the
  theory>/<short name>.proof-store` (`Phi_Proof_Store.store_path`,
  contrib/auto_sledgehammer/library/cache_file.ML), which for TAT's
  in-process theory is the emitted file's own folder, the header's
  `master_dir` and `file_path()` being one; the key is the hash of the
  subgoals, the theory's short name and the context's assumptions
  (`Hasher.all_goals`, `hash_in_context'`), the same at construction
  and at a build of the file; the store appends only into an existing,
  writable directory and otherwise warns once per location ("cached
  proofs will be read but not recorded") and skips; the write-back is a
  dependent fork of the proof's future with `interrupts = true`. Hence
  the framework makes the `Session`'s folder before the tree's theory
  begins, with the compile's function; a compile removes only `.thy`
  files and the ROOT and leaves the store; the store file travels with
  the theory files, as AoA's convention is. The owner knows the working
  directory now gains `.proof-store` files during a conversation, not
  only at a compile (「确认，誊进文档」). The check keeps reading nothing
  from the store; §11's clause is superseded in that part only.
- The driver and the per-run budget are Isabelle's configuration
  (`AoA_driver`; Minilang's default budget), TAT adding no setting
  (「沿用 Isabelle 的配置」).
- The number of constructions running at once: unbounded by default; the
  user may bound it through an Isabelle environment variable (「建议默认
  无限制，但允许用户限制，通过 isabelle 环境变量」). The author's shape: the
  bound is the framework's, around the run wrapper's `await
  self._run()`, so a waiting run is `RUNNING` and a cancellation while it
  waits detaches it like any other. Decided on 2026-10-04: the
  variable is `TAT_MAX_CONCURRENT_CONSTRUCTION_JOBS` (the owner's
  name); unset or empty means no bound; a value that is not a positive
  integer refuses the start, with `TAT requires
  TAT_MAX_CONCURRENT_CONSTRUCTION_JOBS to be a positive integer, but it
  is <value>` (「批准」); a run waiting for its turn shows as a running
  one, `proving`, with no word of its own (「赞同和运行中的一样显示
  proving，不加新词」). *(author)* The refusal is a `TAT_StartupError`
  raised where the conversation starts, which the launcher prints
  before exiting 2: the Isabelle side reads the variable and hands its
  text to `launch_TAT` with the client's name.
- When the `Session`'s folder cannot be made before the theory begins —
  a symbolic link or a file at its path, the cases the compile refuses
  — the conversation ends: the beginning raises `TAT_StartupError`.
  Decided by the owner on 2026-10-04 in the compilation session, as
  that session reports: the working directory is TAT's alone to
  manage, a structure changed from outside is reason enough to refuse
  service, and an agent shown the failure could not repair it. The
  proposal that the beginning fail with the refusal's sentence is
  withdrawn. Written by that session into MODULE_STRUCTURE §4.1's
  `Theory` bullet and EXCEPTIONS §1; the launcher's sentences are its
  to propose, the code its step B5.
- Verified the same day, so that the drive path rests on measured
  facts: AoA is entered from ML, `hammer_or_AoA` → `raw_AoA` → the
  remote procedure `IsaMini.AoA` (contrib/Isa-Mini/IsaMini/AoA/toplevel.py:191),
  whose Python side runs the LLM client and serves it the Minilang tools
  over an HTTP MCP server; `run_AoA` returns the text with its times,
  `hammer_or_AoA` the text alone; AoA's `request` tool today is a hint
  to the planning agent and, for a worker, a general lemma proved by a
  headless prover in AoA's global environment; an Isabelle interrupt of
  the forked task reaches Python as a callback failure that
  `interrupts_are_cancellations` turns into a cancellation, after which
  the driver closes its client. To verify at implementation: that TAT's
  process serves `IsaMini.AoA`; how soon the Python half learns of an
  interrupt; that AoA's `group = NONE` forks end with the job.
- What stays the round's is §13's remainder: the question kinds, AoA
  told it runs under TAT, a job continuing through a context change
  (until then the context change cancels and the construction is
  started again).
- The bound's home (2026-10-05, from the review of steps 1 and 2): the
  value lives on `Conversation` as `max_concurrent_construction_jobs`,
  None for no bound, and MODULE_STRUCTURE §4.1's list of what a
  `Conversation` holds names it (「赞同你的建议」). The declared imports'
  sessions are recorded in `import_sessions` with the agent's, by
  construction, so the ROOT's `sessions` clause names `Minilang_AoA`;
  SESSION_AND_THEORY §2 says so (「赞同你的建议」).
- Landed on 2026-10-09 (step 15), the shapes told to the owner: the
  entry with the times is a sibling `hammer_or_AoA'`, `hammer_or_AoA`
  its projection, so that AoA's own callers are untouched; TAT's call
  passes `task = usual, user_operations = []`, the AoA session's
  user-operations API, uncommitted in Isa-Mini beside the two changes
  §15 allows, which that session commits together with its work; the
  measurement that TAT's process serves `IsaMini.AoA` holds — the
  plugin's package imports it —, the two about interrupts wait for the
  round's scripted driver. Ruled on 2026-10-10, from the review of steps
  14 and 15: the report carries the product as `["ok", <product>]`, one
  `fork_job` for both kinds of job (「赞同维持甲」); `can_start()` requires
  the node `ready` (「赞同」); a replay that raises anything but its
  ordinary failure is a bug that ends the conversation (「应该当作 Bug，
  问题应该及早发现」); `Theorem`'s evaluation refuses a variable `for_any`
  does not declare, checks no types, and `Ready` carries no messages —
  no warning is captured, since an operation's ML returns what matters
  itself (「我们掌控了整个 ML … 这一切都是各个 operation 的 ML 的自由」); the
  plugin's package imports `IsaMini.AoA` rather than `python_packages`
  naming it (「为什么你不去 import the plugin package and then let the
  plugin package import the AoA package」); the product is not logged.
