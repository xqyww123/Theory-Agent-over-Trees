# Jobs and the agents

Status: decided, last on 2026-10-02, after four design reviews
(ai-artifacts/review/CONSTRUCT_RULING*.md); §3.1's carry and §3.2's
bound revised 2026-10-12 with the node-class rounds
(ai-artifacts/review/NODE_CLASS_RULINGS.md); the AoA round (§10) is
open. What the classes with a proof obligation make of the machinery is
node_classes/COMMON.md §3, what each class makes of it its own document.

A **job** is work done on a node's behalf that outlives the tool call it
began in. There are two kinds. A **construction job** is started by an
agent and may need that agent while it runs — a `Theorem`'s proof
construction asks a question and waits for the answer (ARCHITECTURE
§3.6). An **evaluation job** is started by an evaluation and reports to
the agent whose call ran it — a `Theorem`'s proof check replays a stored
proof in the current context. This document says how the two kinds live,
whose they are, how their messages reach an agent, how the agent answers,
what the agent sees, and how an agent is kept from leaving work behind.

## 1. Premises

- One serving process — `isabelle TAT`, or `isabelle TAT_mcp` for a
  client started by hand — serves one working directory and **one
  agent client process** — Claude Code or Codex, chosen at launch (§8),
  started from the agent directory, `TAT.agents/` under the working
  directory (ARCHITECTURE §1). The **agents** are that
  process's main conversation and its subagents; their parents are not
  recorded. A further client process on a running conversation — beside
  its client under `isabelle TAT` or `TAT_mcp`, or after it under
  `TAT_mcp` alone — is outside this premise, and TAT does not tell it
  from the first: on Claude Code its new transcript reads as a
  compaction (CLIENT_HOOKS.md §2).
- The conversation's lifetime is ARCHITECTURE §9's: under `isabelle TAT`
  the launcher, as the client's parent, learns of the client's exit and
  ends the conversation, and a conversation that ends first ends the
  client; under `TAT_mcp` alone the conversation ends
  with its process, which whoever started `TAT_mcp` ends when the client
  ends. When the Isabelle process stops first, the ending (§9) runs only
  under an RPC host started elsewhere,
  since the host the Isabelle process started exits with it
  (MODULE_STRUCTURE §4.6). The Python side neither detects the client's
  death nor exits on its own.
- Everything under the working directory is TAT's to write, except what
  the agents write in the agent directory, the one place they can
  (CLIENT_HOOKS.md §5).
- An agent does not leave while a job of its own runs, a construction
  job of its own waits for its answer, or a message waits in its
  mailbox: the client's stop hook holds it, and its parent's attempt to
  interrupt it is refused while it may hold such work or has a call
  still working (§7). TAT builds
  no other detection of an agent's departure, reads a parent's hook only
  to refuse an interruption, records no parent, and keeps no timeout.
  The client behaviours that bypass both hooks — on Claude Code a
  subagent interrupted with Escape, killed by the stall watchdog or
  ended by `maxTurns`; on Codex a session ended with the subagent
  running, SIGINT, Escape — are accepted as they are: the agent's jobs
  run on and settle on the forest, its messages stay undelivered, and a
  construction job waiting for its answer stays until a context change,
  a delete or an amend of its node, or the ending.
- TAT serves a client only from the version its facts were measured on
  (AGENT_CLIENTS_MEASURED.md): it reads the version the client states in
  its MCP `initialize` and refuses the session when it is lower than
  the expected one, or cannot be read (§8).
- Claude Code saves a transcript of the main conversation and of every
  subagent: TAT reads an agent's transcript to learn of its compactions,
  ends the conversation when the main conversation has none, and reads a
  subagent's transcript from the first announcement at which that file
  exists (§8). Claude
  Code's internal agents — queries it runs on a copy of a conversation
  for its own purposes, such as the prompt suggestion after a turn — are
  not agents of the conversation (§8).
- On Codex the model calls TAT's tools from a script it has Codex run,
  and the script decides when the model sees a result. A result the
  script prints only after its thread has compacted, or never, was
  rendered before TAT could know of that compaction: what it left out
  as already shown may be gone from the context it arrives in. This is
  accepted as it is (CLIENT_HOOKS.md §4).
- A conversation is never rewound. Claude Code's rewind — its rewind
  menu restoring the conversation to an earlier prompt, or Esc Esc to
  edit an earlier prompt and send it again — removes context with no
  hook and no compaction boundary, and TAT does not notice it
  (CLIENT_HOOKS.md §4).
- Every piece of work is an agent's: TAT runs unattended, and no design
  point considers a person in the loop. The entry point, an `isabelle`
  subcommand (ARCHITECTURE §9), and the stop-hook rule (§7) follow from
  this.

## 2. Terms

| term | meaning |
| --- | --- |
| **construction job** | a node's own agent-started work; at most one per node, created with the node and kept for its whole life |
| **evaluation job** | work an evaluation starts on a node; at most one on a node at a time, created and dropped by the framework |
| **owner** | the agent a construction job's current run belongs to: the one whose `construct` started it, or, for a run started automatically, the one whose call ran the evaluation that started it |
| **automatic construction** | a construction job's setting, on or off: while it is on, an evaluation that reaches the node starts the job when the node needs it (§3.2, §3.3) |
| **starter** | the agent whose call ran the evaluation that started an evaluation job |
| **an agent's jobs** | the construction jobs it owns and the evaluation jobs it started |
| **title** | a job class's words for its work, singular and plural: `proof construction`, `proof check` |
| **message** | text addressed to one agent: a **notification** (told once) or a **question** (waits for an answer); also, the messages of a status value — Isabelle's output of a run, as `IsaTerm`s, shown under `Error:` or `Notice:` (ARCHITECTURE §1, PRINT.md §3) |
| **mailbox** | an agent's undelivered messages |
| **compulsory** | a construction job the forest is not complete without (ARCHITECTURE §3.2) |
| **the ending** | the conversation's ending (MODULE_STRUCTURE §4.6, §9 here) |
| **the AoA round** | the design round that connects `Proof_Job` to AoA; what it decides is listed in §10 |

## 3. Jobs

### 3.1 On the node

A node class names its job classes in two class attributes, each
`None` by default: `construction_job_class` and `evaluation_job_class`.
The framework builds the construction job (`cls(node)`) when it builds
the node, and `job(self) -> Construction_Job | None` returns it; the
evaluation jobs are built as §3.3 says. `construct`,
`cancel_construct`, `answer` and `edit`'s `auto_construct` exist only
when a loaded class names a construction job class, `checks` (§5) only
when one names an evaluation job class, and `check_construct` when one
names a job class of either kind.

**The outcome.** The construction job's `outcome` is `NOT_STARTED`,
`RUNNING`, `SUCCEEDED(product)` or `FAILED(message)`. `start` sets
`RUNNING`, the run's settlement `SUCCEEDED` or `FAILED`, `cancel`
`NOT_STARTED`. `product` is the class's, a MessagePack-representable
value — for `Theorem` the proof: the method text AoA writes to its proof
store, with the two times of its replay (node_classes/COMMON.md §3);
while the outcome is `SUCCEEDED` it stays on the node,
also while an evaluation job finds it wanting (`bad proof`), and a new
`start` replaces the outcome whole.

**The store's image.** The framework persists the outcome in one
reserved field (one row), `job`, a tag and an optional value — the
product, or the failure's message — at every
change; the value written for
`RUNNING` is `NOT_STARTED`, so that a loaded forest holds no run
(ARCHITECTURE §4.1) and a `start` clears a previous failure. That value —
the outcome with `RUNNING` read as `NOT_STARTED` — is the store's image.
A `cancel` writes nothing: the image it leaves is the one already stored.
On an amend the old node's running job is cancelled, and the
replacement's job may take the old job's image: the carry. The amend's
commit asks the replacement `_carries_job_from(old)`, a hook of the
node, synchronous and free of side effects, false by default, asked
only when the two nodes are of one class that names a construction job
class. On true it copies the old job's image onto
the replacement's job, first in its synchronous block (MODULE_STRUCTURE
§4.2), so a run that settled while the constructs were built is in the
image, and one still running is carried as `NOT_STARTED` and then
cancelled (§9). The stored check is never carried: a carried
`SUCCEEDED` is checked again (§3.3) before the node is finished.
`Isabelle_Std`'s `Proof_Obligation` answers it by default with true when
`goal_structure()` is unchanged; a class deriving from it may override,
saying why in its own document (node_classes/COMMON.md §3).

**What is unfinished.** The framework's `_unfinished()` (ARCHITECTURE
§3.2; the class's part of `finished`) answers `None` or an `Unfinished`.
It reads the check's outcome through `Node.check_outcome()` (§3.3):
`RUNNING` while a running evaluation job is on the node, the stored
value otherwise.

| the node | answer |
| --- | --- |
| no construction job, or not compulsory | `None` |
| the construction job's outcome not `SUCCEEDED` | `Unfinished_Construction(the construction job)` |
| `SUCCEEDED`, the class names no evaluation job | `None` |
| `SUCCEEDED`, the check's outcome `PASSED` | `None` |
| `SUCCEEDED`, the check's outcome `RUNNING` or `FAILED` | `Unfinished_Check(the outcome, the evaluation job class)` |
| `SUCCEEDED`, no check's outcome | `Unchecked(the evaluation job class)` |

`Unfinished` is an abstract base; `Unfinished_Construction` carries the
job, the other two the evaluation job class, whose title the summary of
§6 groups by. So after a restart a node whose stored check is `PASSED`
is finished once rerun, and one whose stored check is `FAILED` can be
constructed again. A class may override `_unfinished`; `Theorem` does
not.

### 3.2 `Construction_Job`

| member | who | what |
| --- | --- | --- |
| `title(plural=False)` | class method, abstract | the words for the work |
| `compulsory` | class | true when the forest is not complete without the job, as it is by default; read by `_unfinished` alone, never by the stop hook |
| `_run()` | class, hook | the work; returns the outcome; a cancellation propagates out of it: its `try/finally` is its cleanup, which never starts a round trip on the ending's path (MODULE_STRUCTURE §4.3) |
| `_check() -> bool` | class, hook, default true | the class's own condition for a start: whether the job can be started on the node as it stands |
| `auto_construct` | framework, a boolean, false by default | automatic construction, on or off; written by `edit`, `construct` and `cancel_construct` on every node of the call that has a construction job (§5); persisted in a reserved framework field of its own, which the call that writes it stores at once, in a transaction of its own, on every node it wrote — started, cancelled or skipped — and read back at load; no class reads or writes it |
| `can_start() -> bool` | framework | not `RUNNING`, the node `ready` — no class reads a slot the walk has not filled —, and `_check()` |
| `_on_context_change()` | class, hook | called from the status setter on every write of the node's own evaluation status by the walk while the job runs — a rewrite of `ready` on a rerun included — independently of the node's `on_invalidated`, through `_completed` as a completed hook is, after the write; whatever it raises, a `TAT_Error` included, is its class's bug — `TAT_InternalError`, the conversation ends (EXCEPTIONS.md §1); default: cancel with `CONTEXT_CHANGED` |
| `ask(question) -> None` | framework, for `_run` | enqueues an `Interactive_Question` on the job's FIFO queue, posts it to the owner's mailbox when it is the front, and suspends until an answer to it is accepted (§3.4); a cancellation while it waits withdraws that question |
| `repeat_question()` | framework | posts the front question to the owner again when the mailbox no longer holds it — `check_construct`'s delivery of a question again (§5) |
| `start(owner)` | framework, synchronous | called only when `can_start()`: records the owner; drops the node's evaluation job, clearing the stored check; sets `RUNNING`; stores the node in a transaction of its own; spawns the run |
| `forked(name, args)` | framework, for a `_run` whose work is ML's | the class's callback `name` called with `(args, id)`, `id` fresh, under which the callback forks the work through `fork_job` (§3.3); returns the report's errors — none when the work passed — and its product, None when it yielded none; a cancellation meanwhile takes the id out of the table and cancels the work |
| `cancel(reason)` | framework, synchronous | detaches the run, drains its question queue (§3.4), sets `NOT_STARTED`, cancels the task; `reason` is `NODE_DELETED`, `NODE_AMENDED` or `CONTEXT_CHANGED` when the framework cancels, and the owner is then told, even when the owner deleted or amended the node itself; `cancel_construct` passes `None`, and nothing is told |
| wording | class, overridable defaults from `title` | `starting_notice(ids)`, `cancelling_notice(ids)` — `ids` the nodes' ids in their shortest form (§5) —, `answered_notice`, `owned_by_another_refusal`, `finished_notification(outcome)`, `cancelled_notification(reason)` |
| `failure_header(failure)` | class method, abstract | the header of its failure block (§6), printed when the outcome is `FAILED`; `None` prints nothing |

The defaults, for the title `proof construction`: `Started the proof
construction on \`X\`; call \`check_construct\` before you exit.` /
`Cancelled the proof construction on \`X\`.` — each in the three forms
of §5 for one node, two or three, and more — / `Answered the proof
construction on \`X\`; call \`check_construct\` before you exit.` / `The
proof construction on \`X\` belongs to another agent.` /
`… succeeded.` and `… failed:` + the message / `… was cancelled: the
node was deleted.`, `… amended.`, `… its context changed.`. The
notification of a cancelled job names the node the job belongs to, on
an amend the replaced node. A class replaces what it wants said
otherwise (`Proof_Obligation`: node_classes/COMMON.md §3).

**The run.** `start` spawns the framework's wrapper around `_run`
through the ending (§9), never `_run` itself. The wrapper, in order:
sets the log's `agent` to the run's owner (LOGGING.md §3) — a run
started on a failed check is spawned from the report's path and would
inherit none; `call` it inherits, the `construct`'s or none; waits for
every earlier run's task of the job that has not unwound yet
(`asyncio.wait` over them — an `await` of a cancelled task would cancel
this run too); `result = await self._run()`, under the bound on runs
when the conversation has one — the runs of every class's construction
jobs at once, read at the start from the Isabelle environment variable
`TAT_MAX_CONCURRENT_CONSTRUCTION_JOBS`, unset or empty meaning no bound,
a value that is not a positive integer refused as MODULE_STRUCTURE §4.6
says; a compile has none — the place is held from
the start of `_run` until it returns or its cancellation has propagated
out of it, the wait in `ask` and a cancelled run's cleanup included; a
run waiting for its place is `RUNNING`, and a cancellation while it
waits detaches it like any other; then asks one thing: is
the run still the job's? Every legitimate cancellation — `cancel`, by
`cancel_construct`, the framework or the ending — detaches the run
first, so a run that is no longer the job's is one somebody cancelled,
and the wrapper neither settles, reports nor tells anything; what its
cleanup raises is still its class's bug and enters the ending (§9) —
recorded `while_ending` when the ending is already entered (LOGGING.md
§4). A run that is still the job's has ended
on its own: a return settles it, in one synchronous stretch under no
lock — records the outcome and the product, persists them, drains its
question queue (§3.4), applies an attach made from inside `_run`
(§3.3), posts `finished_notification` and wakes the owner — and
anything raised, a `CancelledError` the run brought on itself included,
is a bug that enters the ending (§9). So a run settles exactly once, at
its own end or never. A settlement has no `await` in it, so it is atomic
against every other coroutine; it may land between two awaits of a
locked call, which then sees it as a settlement made just before (§9).

**The context.** The job runs against the node's input context as it was
when the run began. A rerun of the node writes its status again in one
step — `ready` over `ready` when the node was `ready`; it does not pass
through `not_evaluated` — and every write of the status by the walk,
that rewrite included, calls `_on_context_change` and drops the node's
evaluation job; the default hook cancels the job. A class that can
carry on overrides the hook and reads the node's status itself: `ready`
means the node's `state` is the new context.

### 3.3 `Evaluation_Job`

The framework settles no evaluation job: it has the class build one,
attaches it, starts it, reads its outcome and drops it. The class builds
the instance, does the work, and writes the outcome.

| member | who | what |
| --- | --- | --- |
| `__init__(node, starter)` | base | sets `node`, `starter` (`None` when never started), `id` (the framework's counter, unique across the process, for matching the ML report) and `outcome = RUNNING` |
| `outcome` | the class writes, the framework reads | `RUNNING`, `PASSED`, `FAILED(message)`. A settled outcome is also kept on the node, as the **stored check**: a framework attribute beside the node's stored statuses, persisted in the reserved field `check` and restored at load (ARCHITECTURE §4.1, COMPILATION.md §4). It is written when the `finished` report's body, or an attach applied at a run's settlement, settles the job, and each such step stores the node in a transaction of its own. It is cleared exactly when a stored status of the node leaves `Ready` — in the status setter —, when a construction job starts on the node, and when another evaluation job is attached in its place; a rerun that confirms `Ready` over `Ready` does not clear it, whatever its messages, nor does a drop by itself, nor the conversation's ending. `Node.check_outcome()` is its one accessor: `RUNNING` while a running evaluation job is on the node, the stored check otherwise; every reader goes through it — `_unfinished()` (§3.1), emission, a class's mark and `_check()`, the failure blocks and the summary of §6. A loaded forest re-attaches no job |
| `title(plural=False)` | class method, abstract | the words for the work |
| `make(node, starter) -> Self` | class method, synchronous, default `cls(node, starter)` | builds the instance and begins nothing; a class whose constructor takes more overrides it; what a class needs from Isabelle to set its job up it fetches in `_start` |
| `_start()` | hook, async, abstract | begins the work through the class's own ML callback, passing `self.id`, and returns at once; called by the framework once the job is on its node |
| `_finished(errors)` | hook, default given | called by the framework on the ML report, synchronously, under no lock; default: `PASSED` on no errors, else `FAILED` with the errors joined by newlines |
| `failure_header(failure)` | class method, abstract | the header of its failure block (§6), printed from a `FAILED` check's outcome whether or not a job is on the node; `None` prints nothing |
| `failure_notification(ids, automatic)` | class, abstract | the sentence its failure sends (§3.4) for the nodes these ids name, in their shortest form — one, two or three, or more, in the forms of §5 — `automatic` saying that the failure started their construction |

**Where a job starts.** A node the walk **passes** is one it reaches in
the `Evaluating` mode (MODULE_STRUCTURE §4.1) — rerun, or `ready` and
left as it stands; no node past the destination is passed. An
evaluation starts a job on every node it passes, at the node's last
operation, when the node is `ready`, its class names an evaluation job,
no evaluation job is on it, `_unfinished()` would answer `Unchecked`,
and the evaluation's `checks` argument says so (§5); no other node gets
one. The framework's `Node.start_evaluation_job()` does it, in this
order: `job = cls.make(node, caller)`, `cls` the node class's
`evaluation_job_class`; `attach_evaluation_job(job)`; `await
job._start()`. Nothing runs between the test and the attach, so no
`construct` can slip in and start a construction beside the check; and
the job is on its node, with its id, before any work begins, so a report
can never arrive for a job the framework does not hold. `make` and
`_start` run after the node's evaluation is committed, like a completed
hook, and follow its rule (EXCEPTIONS.md §1): anything either raises, a
`TAT_Error` included, is its class's bug — `start_evaluation_job()`
turns a `TAT_Error` into a `TAT_InternalError` as `_completed` does —
and the conversation ends, the ending dropping the job.
`Node.attach_evaluation_job(job)` puts a job on the node, dropping the
one there; a class may attach a job it built and settled itself —
`Proof_Obligation`'s proof
construction does from its `_run` (node_classes/COMMON.md §3): from inside a run,
`attach_evaluation_job` accepts a settled job only, and the attach takes
effect at the run's settlement, with the outcome, and is discarded with
a cancelled run.

**Automatic construction.** On a node it passes, after the test above,
an evaluation also starts the node's construction job — `start(caller)`,
the caller its owner — when the node is `ready`, the job's
`auto_construct` is on, `can_start()` holds, and the node holds no
result worth keeping: the job is `NOT_STARTED`; or its last run ended
`FAILED` and the node was invalidated since — its stored status was not
`ready` before this evaluation wrote it; or it ended `SUCCEEDED` and the
check on the node is `FAILED`. A `SUCCEEDED` job whose check is
`PASSED`, `RUNNING` or not yet run is left alone: the result stands, or
is checked first by the test above. When a check's report is `FAILED`
and `auto_construct` is on, the report's body starts the construction at
once, the job's starter its owner. Nothing else starts a construction
automatically, and automatic construction starts no evaluation of its
own.

**The work.** The class's ML callback forks the work as a Future task —
`Future.fork`, on Isabelle's worker pool — and returns; when the task
ends it calls the framework's remote procedure `job_finished(id, failure)`,
`failure` the work's errors, none on success, or the message of a `Bug`
the work raised (MODULE_STRUCTURE §2.4). A construction job whose work
is ML's forks it the same way, through `Construction_Job.forked` (§3.2),
and its report carries the product the work yields (node_classes/COMMON.md §3).
The framework's ML half offers the fork and the report as one function:
it forks the work, keeps the future under the job's id in a table of its
own, and runs the report after the work with interrupts deferred, so
that a work which ended is always reported. The callback
`cancel(ids)` looks the ids up in that table and cancels the futures;
it goes through the existing callback table, the remote procedure
through Isabelle_RPC's registry, declared with a timeout of five minutes —
it answers at once, so a report unanswered that long means the Python
side answers no more, and the task ends the process as a disaster
(MODULE_STRUCTURE §2.4) — on the wire
`TAT.job_cancel` and `job_finished`, the function `fork_job` of the
class's ML environment (MODULE_STRUCTURE §2.4–§2.6). The callback reads
what the work needs of the node's slots before the fork — `Theorem` its
`goal_state` —; the work bounds its own time, and the framework sets no
limit. The work applies no Toplevel
transition and registers nothing in Isabelle's execution table — a
construction's, AoA's search and its store's write-back, forks Future
tasks under the job's group alone, every call inside it synchronous
(node_classes/COMMON.md §3) — so a library load's `Execution.reset`
(EVALUATOR_DESIGN §6), which empties that table and collects its
groups' errors, never meets it; no lock orders the jobs against a load. `Proof_Check`'s work replays the stored product on the goal
`goal_state` holds, through the function AoA exports (node_classes/COMMON.md §3).

**The report.** `finished` answers at once. Its body is synchronous and
takes no lock; the table from a job's id to the job is the process's —
the report arrives on a pooled connection of the RPC host's, which
belongs to no conversation — and the job holds the `Conversation` it
was made in, through which the report reaches the conversation and its
log. A job is in the table from its start (`start_evaluation_job`
registers it just before the work begins) until its report or a drop —
a construction run's fork from `forked`'s call until its report or the
run's end —:
every drop discards it (§4.2), so a report whose job the table no longer
holds — dropped, or its conversation already ended — is **nobody's**,
and is ignored whole, a `Bug` included: nothing is stored, nothing is
told, the conversation does not end.
For a job the table still holds — one still on its node — a report that
carries a `Bug` raises `TAT_InternalError` with the `Bug`'s message and
so enters the ending (§9): `_finished` never sees it, nothing is stored
and nothing is told to the starter. Otherwise the body calls
the job's `_finished(errors)`, then reads `outcome` — on `FAILED` it
posts `failure_notification` to the starter and, under automatic
construction, starts the node's construction job (above); a success is
silent — marks the job ended and wakes the starter. A report whose job is off
its node is a dropped job's and is ignored. Anything the body raises,
and an `outcome` that `_finished` leaves `RUNNING`, is a bug that enters
the ending (§9); `finished` answers all the same. No Isabelle thread
ever waits for the forest lock (MODULE_STRUCTURE §4). Like a run's
settlement, a report may land between two awaits of a locked call (§9).

**Running and dropping.** An evaluation job is **running** when its
`outcome` is `RUNNING` and it is on its node; the stop hook, the state
lines, the background line and `blocking` all read this one definition.
A node's evaluation job is **dropped** — one synchronous step: taken off
the node, marked ended, its starter woken — when the walk writes the
node's status (an invalidation, or a rerun, which rewrites `ready` in one
step), on a delete or an amend, when a construction job
starts on the node, and when another job is attached in its place;
nothing else drops it. The status setter does both: the drop at every write by the walk, the
clearing when the stored status leaves `Ready` (COMPILATION.md §4). Cancelling the task is a separate,
best-effort step: a walk collects the ids it dropped and sends one
`cancel(ids)` at its `flush`; an edit collects the ids its commit block
dropped — in its invalidation and its completed events — and sends one
`cancel(ids)` after the block, with its other round trips
(MODULE_STRUCTURE §4.2 step 4); any other drop sends it at once,
from synchronous code through a task spawned on the ending object
(MODULE_STRUCTURE §4.6); the ending drops every job and sends none (§9). A dropped job's later
report is ignored, as above.

### 3.4 Messages and questions

A message has a recipient, a text, whether it interrupts the recipient's
`check_construct`, optionally what it is about — its **subject**: an
evaluation job, or a construction job's run, asked at delivery whether
the message still stands — and the question it carries.
Anything may post one. A message is delivered at the tool boundary,
after the body of the recipient's next tool result, whatever the tool
(§5): the handler takes the mailbox only after its cancellation
checkpoint (MODULE_STRUCTURE §4.6), so a call the agent client gave up
before then leaves the mailbox as it was, for the next call; a
cancellation arriving in the moment between the taking and the
client's reading of the result loses the messages, which TAT cannot
see, MCP carrying no receipt. At delivery a message whose evaluation job is no longer on its node, or
whose run was cancelled, or whose question is no longer its
job's front question, is dropped; a cancelled or dropped job so
leaves no question or notification of its own behind, and a settled
run's own notifications stand. The two
notifications the framework posts about a construction job come from no
run and are always delivered.

The framework's notifications: a construction job finished
(`finished_notification`) or was cancelled by the framework
(`cancelled_notification`), both interrupting; an evaluation job failed
(`failure_notification`), not interrupting. A failure notification
carries the facts its merge needs — the class that words it, the node it
is for, whether the failure started that node's construction — fixed at
posting, so the merge needs no live job; its subject is the job while
the failure did not start the construction, and none — it then always
stands — when it did, the construction's `start` having dropped the job.
At delivery the failures of one class are merged into one
sentence for the nodes whose construction the failure started and one
for the others. A job
class posting a notification of its own sets the flag itself. Questions
always interrupt.

A question is an `Interactive_Question`, subclassed by the job class:

```python
class Interactive_Question(ABC):
    text: str             # what the owner reads
    schema: JSON_Schema   # an object schema for `answer`, within the tool schemas' grammar
                          # (MODULE_STRUCTURE §4.4); validated in `ask`; substituted for the
                          # tool's `answer` property at answer time

    @abstractmethod
    def receive(self, answer: JSON) -> Answered | Interactive_Question:
        """Judge a shape-valid answer.
        Return `Answered(response)` to accept: keep what the job needs on `self`; `response`
        is the `answer` tool's text, None for the framework's default.
        Return a question to ask instead: it replaces this one as the pending question and is
        delivered in the same tool result.
        Raise `BadAnswer(message)` to refuse: this question stays pending."""

@dataclass(frozen=True)
class Answered:
    response: str | None = None
```

A job holds a **FIFO queue** of questions: a run may ask several at once
— from branches it forks — and each waits for its own answer. Only the
**front** is posted to the owner and answerable; the one the owner sees
and `answer` answers is the front, and the agent answers them one at a
time. `ask(question)` validates the schema — a failure is a bug in
`_run` — enqueues the question, posts it only when it is the front, and
suspends the run until some `receive` accepts an answer to it; the job
then reads its data off the question whose `receive` accepted — a
replacement being the class's own, built in its `receive`, which keeps
the front's place and its waiting `ask`. A question asked instead is
posted the same way. `receive` runs in the `answer` tool's body, under
no lock, synchronously, so answers do not interleave. A question leaves
the queue when an answer to it is accepted — the next question, if any,
is then posted —, when its `ask` is cancelled, when the job is
cancelled, and when the run settles; **withdrawing** it removes it from
the queue and cancels the `ask` waiting on it, so a stray asking branch
ends with it, and a cancel or a settlement **drains** the whole queue.
No withdrawal touches a mailbox: at delivery a question that is no
longer the job's front is dropped, by the same filter as above. So a job
that is not `RUNNING` has no pending question, whatever its `_run` did.
A job may post other messages while a question of its waits; a class
that posts one contradicting its pending question is a bug, not
something the framework guards against.

Delivered, a question reads:

```
The proof construction on `lemma_P` asks:
<the question's text>
Answer with the `answer` tool, node_id `lemma_P`; the answer must follow the JSON schema:
{
  …the schema, complete…
}
```

## 4. The agents

An `Agent` is one agent of the client process, created when its first
call or hook reaches TAT and never discarded. It holds its jobs of both
kinds, its mailbox, its seen set (§6), and the wake-up its waiting
`check_construct` sleeps on: a change to its mailbox or its jobs wakes
it. The framework tells agents apart only as objects; how a client names
them is the server subclass's (§8). It also counts its **working
calls** — TAT tool calls of its whose bodies are still running (§9):
the count rises as soon as `agent_of_call` names it, before any lock is
awaited, and falls when the body ends, whatever the client did
meanwhile; a call is not counted from its announcement, since an
announced call the client never sends would hold the agent for ever.
The interruption judgement reads the count (§7); the stop rule does
not, since an agent whose client gave up on a call may reach its own
stop hook while the body still runs, and no `check_construct` could
clear such a block.

Who may do what: `answer` is the owner's alone
(`ConstructOwnedByAnother`), and `cancel_construct` cancels the caller's
own runs and skips the others (§5); a question's text and the `needs
your answer …` tag on the node's line (§6) are shown to the owner only; a job's failure block (§6) is
shown to everyone.

## 5. The tools

| tool | arguments | description |
| --- | --- | --- |
| `construct` | `node_ids`, `auto_construct` | completed at start: `Start the construction jobs of nodes, such as {construction titles}.` — the titles plural, distinct, alphabetical, joined with commas and `and`; with `Theorem` alone `Start the construction jobs of nodes, such as proof constructions.` |
| `cancel_construct` | `node_ids`, `auto_construct` | `Cancel the running construction jobs of nodes.` |
| `check_construct` | `wait_seconds` | completed at start: `Wait until any {construction titles} or all {evaluation titles} have finished, or a message arrives. Returns at once when nothing is running. To ensure all jobs have finished, call it repeatedly.` — each slot's titles distinct, alphabetical, the first slot's singular, the second's plural, joined with commas and `or` before the last; with no evaluation job class loaded, the `or all …` part absent and the verb singular: `Wait until any {construction titles} has finished, or a message arrives. Returns at once when nothing is running. To ensure all jobs have finished, call it repeatedly.`; with no construction job class loaded `Wait until all {evaluation titles} have finished, or a message arrives. Returns at once when nothing is running. To ensure all jobs have finished, call it repeatedly.`; with `Theorem` alone `Wait until any proof construction or all proof checks have finished, or a message arrives. Returns at once when nothing is running. To ensure all jobs have finished, call it repeatedly.` |
| `answer` | `node_id`, `answer` | `Answer the question a construction job asked you` |

Argument descriptions: `node_ids`, a list of ids, required: `The ids of
the nodes whose construction jobs to start; a non-leaf node stands for
every node under it.` / `… to cancel; …`. `auto_construct`, a boolean,
optional — the value the nodes' automatic construction takes, off when
left out, on these two tools and on `edit` alike; a tool description
says nothing of the arguments, and the one sentence that tells what
automatic construction is stands on `construct`'s:

```
If true, automatically start the construction of each node whenever an evaluation reaches it and it is not constructed yet; false turns this automatic construction off. Default: false.
True keeps their automatic construction on; false turns it off. Default: false.
True turns the new nodes' automatic construction on; false leaves it off. Default: false.
```

— `construct`'s, `cancel_construct`'s and `edit`'s, in that order.
`wait_seconds`, an integer, required: `The time
to wait at most, in seconds; the call returns earlier when a message
arrives or every job has finished` (neither clamp of `check_construct`
below is in the schema or its descriptions); `The id of the node whose
construction job asked the question`; `The answer, in the shape the
question asked for`. `answer` is declared a bare object and checked
twice, both times with the checker every tool call goes through
(`plugin.check_call`): by the builder against the bare-object schema,
then, inside the entry once the job and its pending question are found,
against the question's own schema substituted for it — a schema that
carries no `$defs`, which `ask` refuses — so a wrong shape renders as `The argument \`answer.verdict\` must be one of
\`accept\`, \`reject\`.`; then `receive` judges it. Messages travel
only on tool results.

`evaluate_to` (TOOL_SCHEMAS.md) takes `node_id`, required — `The id of
the node to evaluate up to, with its subtree; a theory's id means the
whole theory.`; `ignore_error`, optional — `Whether to carry on past a
node that fails, so the nodes after it are evaluated too. Default:
false.`; and `checks`, optional, an enum of `"no"`, `"quick"` and
`"blocking"`, `"quick"` when left out. The tool schemas' grammar has no
`default`; a description states it as `Default: …`. `checks`'
description is completed at start from the loaded classes'
evaluation-job titles, distinct and alphabetical, joined with commas and
`and` — the property absent when no class names one:

```
Whether to run the {titles} of the nodes: "no" runs none; "blocking" runs them and waits for them to finish before the call returns; "quick" runs them in the background, and you may wait for them with `check_construct` or go on (a failure will be reported to you, a success is silent). Default: "quick".
```

`edit`'s and `move`'s own evaluation (`evaluate: true`) runs with
`quick`. A successful `evaluate_to`'s body is its opening line —
`Evaluation reached theory_X.` or `Evaluation stopped at definition_f.`
(TOOL_SCHEMAS.md §4), followed, when the stop is the order constraint's,
by that constraint's sentence on the next line (RENDER_BASELINES §3, §6)
— and the quickview.

**Every tool result** is the body's text, then the caller's undelivered
messages, then the trailer the body asked for — a failed call's rendered
`TAT_Error` included; only the ending's fixed line carries no messages.
A call that ran an evaluation names, after the messages and before the
trailer, the constructions its evaluation started automatically (§3.3),
in the forms of `construct`'s line below opened with `Automatically
started` — `Automatically started the proof construction on
\`lemma_A\`; call \`check_construct\` before you exit.` — and
nothing when there is none; a construction started on a failed check is
told by that failure's notification (§3.4, §6).
A *plain* result is one with no trailer. Body, messages and trailer are
separated by one blank line, and the messages from each other by one. A call that ran an
evaluation asks for the background line: the caller's running
evaluation jobs, all of them, counted by title, titles distinct and
alphabetical — `3 proof checks are running in the background.` / `1
proof check is running in the background.` / `1 counterexample search
and 3 proof checks are running in the background.` — nothing when the
count is zero; the first time for an agent, keyed `(0, "background")` in
its seen set, `3 proof checks are running in the background; call
\`check_construct\` to wait for them.`. `check_construct` asks for its
state lines. Under `blocking` the call keeps the forest lock after its
walk and waits until every evaluation job that was running on a node
the walk passed has ended — settled or dropped, whoever started it —
then writes the quickview and the trailer; the failures ride on the
same result as messages. No context changes during the wait, since only
a holder of the lock changes one; a node whose context the walk itself
changed had its job dropped and, when the walk reran it, a new one
started, so every job waited for belongs to a current context.

- `construct`: the nodes of the call are the nodes its ids name and,
  for a non-leaf node, every node under it — `Sessions`, the root,
  standing for every tree —, those without a construction job left out;
  no class arguments. On each, `auto_construct` is written
  as the call gives it; each whose job `can_start()` is started, the
  caller its owner; a node that cannot be started now — not `ready`,
  already constructed, running — is skipped, not refused, and its mark
  says how it stands. Result: the `Started …` line below, naming every
  node the call started, over the quickview, its focuses at depth 0 the
  nodes the call named, an id under another named id left out. Refused only when no node of the call has a
  construction job (`ConstructNotSupported`).
- `cancel_construct`: the same nodes; `auto_construct` written on each;
  every run of the caller's among them cancelled (`cancel(None)`); a run
  that is another agent's is skipped and goes on. Result: the
  `Cancelled …` line, naming every node whose run the call cancelled,
  over the quickview.

  The two lines take the forms of `check_construct`'s state lines: one
  node; two or three, `on` repeated and `and` before the last; more, a
  header and one id per line, each in its shortest form; and a fixed
  sentence for none. Each
  is one line or list per job class, worded by that class, so two
  classes of one title give two; the classes in the order their first
  nodes come in tree order. The `Automatically started` line (§3.3) is
  one per class the same way.

  ```
  Started the proof construction on `lemma_P`; call `check_construct` before you exit.
  Started the proof construction on `lemma_P`, on `lemma_Q` and on `lemma_R`; call `check_construct` before you exit.
  Started the following proof constructions; call `check_construct` before you exit:
    - lemma_P
    - lemma_Q
    - lemma_R
    - lemma_S
  No construction job was started.
  Cancelled the proof construction on `lemma_P`.
  Cancelled the proof construction on `lemma_P`, on `lemma_Q` and on `lemma_R`.
  Cancelled the following proof constructions:
    - lemma_P
    - lemma_Q
    - lemma_R
    - lemma_S
  No construction job was running.
  ```
- `check_construct`: returns on a condition, judged when the call starts
  and again whenever the caller's mailbox or jobs change:
  1. the mailbox holds an interrupting message;
  2. a construction job of the caller's waits for an answer — the
     question is delivered again: put back into the mailbox when it is
     no longer there, one entry per job at most;
  3. since the call started, a job of the caller's has ended — settled,
     cancelled or dropped — and none of its title is left running;
  4. the deadline: `wait_seconds` clamped, silently, to at least 3
     seconds and to a minute under the client's twelve-hour limit (§8).

  Neither kind running or waiting at the start: at once, with the single
  line `No job is running.` as its body, a plain result, any messages
  after it. Otherwise the body is empty and the state lines are the
  trailer, after the messages; they describe what stands at the return: the caller's jobs
  grouped by title and situation — a construction job waiting for its
  answer or still running, an evaluation job still running — each node
  once, one sentence or list per group, groups in the order construction
  titles then evaluation titles, alphabetical within, a construction
  title's waiting group before its running group; up to three nodes
  as one sentence with `on` repeated and `and` before the last,
  `The proof construction on \`lemma_P\` and on
  \`lemma_Q\` is waiting for your answer.` / `… is still
  running.`, `The proof check on \`…\` is still running.`; more than
  three as a header with the plural title and one id per line, each in
  its shortest form:

  ```
  The following proof constructions are still running:
    - lemma_Q
    - lemma_R
    - lemma_S
    - lemma_T
  ```

  and for the waiting group `The following proof constructions are
  waiting for your answer:` over the same kind of list;

  and, for a title the caller had a job of during the call and now has
  none of, `All proof constructions have finished.` / `All proof checks
  have finished.` — one line per such title, construction titles first,
  then evaluation titles, alphabetical within. A return at the deadline
  has the same shape as any other. No quickview.
- `answer`: refused when no question of a run of the caller's waits on
  the node — no construction job (`Sessions`, the root, among them), a
  job not running, a run that has
  asked nothing — with `` `theory_X.definition_f` has no question
  waiting for an answer. `` (`NoQuestionPending`, the framework's
  sentence), when the question is another agent's run's
  (`ConstructOwnedByAnother`, the class's `owned_by_another_refusal`),
  when the answer fails the shape check (the checker's
  sentence), or `receive` refuses it (`BadAnswer`, the question's
  sentence). Accepted, the result is the question's `response`, by
  default the job's `answered_notice`. When `receive` asks instead, the
  result is empty and the new question rides on it as a message. No
  quickview.

A failed `construct`, `cancel_construct`, `check_construct` or `answer`
renders the cause alone: an id no node bears or several do, or, for the
first two, `ConstructNotSupported` — `` `theory_X.section_Basics` has
nothing to construct. `` for a call that named one node, `None of these
nodes has anything to construct.` for one that named several. A call
that fails starts and cancels nothing.
`construct`, `cancel_construct`, `answer` and `check_construct` take no
lock (§9).

Exceptions: `ConstructionError` (abstract, `TAT_Error`) with the
framework's `ConstructNotSupported`, `ConstructOwnedByAnother`,
`NoQuestionPending`; `BadAnswer` is a
`TAT_Error` of its own. No class names the tool that failed
(EXCEPTIONS.md §2).

## 6. What the agent sees

- **The mark.** The framework's four rows (PRINT.md §1): `complete`,
  `failed`, `not evaluated`, `incomplete`; no line is bare. `not
  evaluated` says the node's first own operation did not run — never
  reached, invalidated or blocked; a node whose first operation ran and
  whose later one did not, a nesting node stopped inside, is
  `incomplete`, and the summary below tells what stopped it.
  `Proof_Obligation` overrides `mark` with its two slots
  (node_classes/COMMON.md §3).
- **The tags.** After its mark, inside the same parentheses, a node's
  line carries what the framework adds. A node whose construction job
  has automatic construction on carries `automatic construction`, in
  every rendering, for every agent and whatever its state: `- lemma_P
  (not evaluated, proof not started, automatic construction)`, `-
  lemma_Q (valid statement, proven, automatic construction)`. A node
  whose construction job waits for its owner's answer carries, after
  that, `needs your answer, call \`check_construct\` to see it` — in
  every rendering, the briefing included, to the owner only, until the
  answer is accepted.
- **The failure blocks.** When a node is detailed (PRINT.md §2) and is
  not itself an obstacle, the framework prints after the class's
  `print_fields`, for the construction job when its outcome is `FAILED`
  and for the check when `check_outcome()` is `FAILED`, in that order, the job class's
  `failure_header(failure)` — `failure` the `FAILED` outcome — and
  the message on the lines below, one level (two spaces) deeper; a `None` header
  prints nothing. A header ends in a colon; when the message is empty
  the colon is written as a period and nothing follows — `The proof no
  longer holds.` — and the same holds for a notification that carries a
  message under it. The blocks are printed on every detailed rendering;
  the seen set does not apply. A question's text is never printed under
  the node.
- **The summary under a cut-off nesting node.** Under `Recall`, an
  `incomplete` nesting node at the last printed depth (3) writes one
  line per group: the nodes below it that are `ready` grouped by the
  title their `Unfinished` carries — the construction job's, or the
  evaluation job class's; one group per title, construction titles
  first, then evaluation titles, alphabetical within —, then the nodes `failed`, then the
  nodes `not evaluated`, nesting nodes counted among them; ids in tree
  order, up to five, relative to the node; more than five the count
  alone; a group with no members writes no line; no period; not in a
  quickview or the briefing:

  ```
  - section_Basics (incomplete)
    3 proof constructions incomplete: lemma_A, lemma_C, context_C.lemma_B
    12 proof checks incomplete
    1 node failed: definition_f
    2 nodes not evaluated: lemma_E, lemma_F
  ```

- **Notifications** on tool results: `\`lemma_P\` is proven.`,
  `No proof of \`lemma_P\` was found:` + the message on the
  lines below, indented, `The proof construction on \`lemma_P\`
  was cancelled: the node was deleted.` / `… amended.` / `… its context
  changed.`, and `Proof_Obligation`'s failed proof check, which gives no reason
  and tells what to do next (node_classes/COMMON.md §3): `The proof of
  \`lemma_P\` no longer holds. Call \`construct\` to prove it
  again.` — for a node under automatic construction `The proof of
  \`lemma_P\` no longer holds, so its proof construction was
  started automatically; call \`check_construct\` before you exit.`;
  several nodes are named in one sentence or one list (§3.4).
- **The seen set** (PRINT.md §4) is the agent's: `Agent.seen: set[Key]`,
  `Key = tuple[int, str | None]`. `Conversation.forget(key)` removes a
  key from every agent's set — the framework's discard of an operation's
  message keys, in the status setter at every write
  (COMPILATION.md §4, PRINT.md §4) — and a
  compaction clears the compacted agent's set alone. Rendering reads the agent it is for: `Forest.render(node, mode,
  agent)`, the forest holding it for the call's duration as it holds its
  index; `Node.mark` and `print_fields` reach it through the forest.
- **The briefing** (PRINT.md §5) is what `recall` without an id
  renders; it calls no `print_fields` and prints no block. An agent
  reads it after its compaction (§8): it sees the marks and the tags,
  and calls `check_construct`.

## 7. Leaving

An agent may not leave work behind, or messages unread. The client runs
a hook when an agent is about to stop — `SubagentStop` for a subagent,
`Stop` for the main conversation, on both clients — and TAT answers it
by what `check_construct` would return if the agent called it now with
no time to wait: when that call would return the single line `No job is
running.` and deliver no message, the stop is allowed; otherwise it is
blocked. TAT makes that judgement on the hook path as `check_construct`
makes it at its start: in one synchronous step under no lock, after the
payload is read; while the conversation is ending the path answers 503
and judges nothing (MODULE_STRUCTURE §4.6). The reason carries no
message and no question — messages travel on tool results alone (§3.4),
and the hook's text passes through the client's hands, which may escape
or cut it (AGENT_CLIENTS_MEASURED.md) — but tells the agent what holds
it and what to call: the opening line
`The \`TAT\` server blocked your exit:`, the state lines (§5) — the
groups with members, no `All … have finished.` line — and one
instruction composed from what stands:

| what stands | the instruction |
| --- | --- |
| a question, and jobs running | `Call \`check_construct\` to see the question{s} and to wait for the running {titles}; answer {it|them} before you exit.` |
| a question only | `Call \`check_construct\` to see the question{s}; answer {it|them} before you exit.` |
| jobs running only | `Call \`check_construct\` to wait for the running {titles} before you exit.` |
| messages only | `Call \`check_construct\` to read your messages before you exit.` |

`{titles}` in their own numbers, construction titles first, then
evaluation titles alphabetically, same titles merged. Messages waiting
beside a question or a running job need no mention: the call the
instruction asks for delivers them.

```
The `TAT` server blocked your exit:
The proof construction on `lemma_P` is waiting for your answer.
The proof check on `lemma_A` and on `lemma_B` is still running.
Call `check_construct` to see the question and to wait for the running proof checks; answer it before you exit.
```

```
The `TAT` server blocked your exit:
Call `check_construct` to read your messages before you exit.
```

What reaches an agent's mailbox comes from its own jobs, or from the
framework about them, so an agent with no job left is held until one
call. TAT sets no limit on how often it blocks,
and switches off Claude Code's own (§8). The ending cancels every
construction job and drops every evaluation job (§9).

**Being stopped by a parent.** A parent stops a subagent with a tool —
`TaskStop` on Claude Code, `interrupt_agent` on Codex — and the
subagent then never sees the result of the call it had in flight
(AGENT_CLIENTS_MEASURED.md). TAT answers the parent's `PreToolUse` on
that tool with one judgement on both clients, made with the stop rule:
the call is denied when any agent other than the caller and the main
conversation would be held, or has a call still working (§4) — a
stopped agent's working call runs to its end (MODULE_STRUCTURE §4.6)
and can start proof
checks in its name whose failures nobody would be told of; otherwise it
is allowed. TAT reads neither
`TaskStop`'s `task_id` nor `interrupt_agent`'s path. This is sound
because a stop can end only its target and the target's foreground
descendants, never the caller, which is running while it calls, nor the
main conversation, which is no task on Claude Code and which Codex
refuses as a target; judging every other agent therefore misses none
and needs no record of parents. No judgement of the target alone could
be sound: on Claude Code the target may be named by its launch name or
through `shell_id`, which TAT cannot resolve, and a target stopped by
its exact id takes its foreground children with it, which TAT cannot
see (AGENT_CLIENTS_MEASURED.md). The price, on Claude Code: while any
other subagent holds work, `TaskStop` is refused on an idle subagent
and on a background shell as well, with the same reason. The denial's
reason, on both clients, reaches the parent as the call's error result
and reads:

```
This agent cannot be interrupted: it may still have work in `TAT`.
Send it a message asking it to finish its work in `TAT` and exit, then wait for it.
```

A message to a busy subagent arrives when its current call returns
(Claude Code) or at its next step, within about half a minute (Codex);
the subagent then finishes and stops through the stop hook, work and
messages settled. Whether the parent follows the advice is the
model's; the denial holds either way.

No code path of TAT's learns that an agent left with a job running;
should a client ever report it, the reaction is `TAT_InternalError`
(`Agent <id> left with jobs running: the proof construction on \`X\`, 3
proof checks.`, logged as the `agent` record `left_with_jobs`,
LOGGING.md §4) and the ending.

## 8. The server and the client

`isabelle TAT -c <client>` and `isabelle TAT_mcp -c <client>` (default
`claude-code`) choose the client for the launch; the first also starts
it (MODULE_STRUCTURE §5). `TAT_Server` has one subclass per client, which implements
`configure`, `launch_arguments` (CLIENT_HOOKS.md §3), `agent_of_call`,
`event_of_hook` and the result envelope.
The client's version is read where the client states it: every MCP
session opens with an `initialize` request whose `clientInfo` carries
the client's `name` and `version` (the MCP specification's lifecycle;
the library keeps them as the session's `client_params`, and serves no
request before them). At the first request of a session that reaches
TAT, the subclass compares the leading dotted numbers of that `version`
with the version its facts were measured on — Claude Code 2.1.296,
Codex 0.156.1, raised with every round of measurement — and the `name`
with the client `-c` chose; a version that is lower, or cannot be read,
or a name that is another client's, refuses the session: no tool is
served, and TAT ends the conversation with a `TAT_StartupError` naming
both versions, which the launcher prints before exiting 2 (MODULE_STRUCTURE
§5). Nothing is read from the client's program itself: `isabelle TAT`
only finds it on the path and starts it, under `TAT_mcp` alone the
program that connects is started by hand and need not be the one on
TAT's path, and in both cases what is checked is what the connecting
client states in `initialize`. On Codex the subclass also checks
the sandbox the client runs its agents in: every tool call carries the
policy in force, and a call whose policy is not the profile TAT
configured refuses the session the same way, with
`TAT refuses this Codex session: its sandbox is not the one TAT configured. Start Codex in <working directory>/TAT.agents without a sandbox option.`
(CLIENT_HOOKS.md §5); every tool call is answered the ending's line for
it meanwhile (RENDER_BASELINES §4). `configure(working_directory)`
writes that client's files whole into the agent directory, and the
scripts the hooks run into `.tat/` — CLIENT_HOOKS.md §2 and §3 list the
files, §5 what in them keeps the agents inside the agent directory. Of
the hooks, the conversation's are the stop hooks (§7); on Codex
`SessionStart`, `PreCompact` and `PostCompact` (CLIENT_HOOKS.md §3); the
parent's `PreToolUse` on `TaskStop` (Claude Code) or
`collaborationinterrupt_agent` (Codex), which reaches `/hook` as an
`interrupt` event and is answered with `permissionDecision` `deny` and
the reason, or an empty answer; and the announcement below. The server is registered with
the client under the name `TAT`, so the agent sees its tools as
`mcp__TAT__…` and TAT names itself `TAT` in every sentence. At each hook
request on the endpoint `/hook` `event_of_hook(request)` translates the
client's JSON into a `stop` or `compaction` event on an `Agent`, or an
`interrupt` event on the set of agents the call may stop — the subclass
looks them up and never creates one; an empty set is allowed — or
consumes it; at each tool call `agent_of_call(context)` names the
calling `Agent`.

A **compaction event** is TAT learning that an agent's context was
replaced; it clears that agent's seen set (§6), and nothing more: TAT
pushes no briefing, the agent reads one itself with `recall` and no id
(PRINT.md §5, RECALL.md), told to by a skill of its own after a
compaction. Every compaction is detected, but for one exception below,
on both clients and for subagents as much as for the main conversation
(AGENT_CLIENTS_MEASURED.md):
- On Codex, `PreCompact` and `PostCompact` fire for every thread that
  compacts, and their `agent_id` names the subagent (a payload without
  one is the main conversation's); each of the two is the compaction
  event, so that a TAT call ending while the summary is written is
  rendered against an empty set, and what it recorded is forgotten once
  the compaction is done (CLIENT_HOOKS.md §3). Nothing a compaction
  hook answers reaches the model there, so the hooks are answered with
  nothing. A `SessionStart` — `resume`, `clear`, `fork`, `compact`; its
  hook leaves out `startup`, a new thread's start — fires for the main
  conversation only and is its compaction event too. A thread that is no spawned subagent — a `/review` thread —
  carries no `agent_id` either, so its compaction clears the main
  conversation's set, and its own set, should it call TAT, is not
  cleared; this is accepted.
- On Claude Code, `PreCompact`, `SessionStart` (`compact`) and
  `PostCompact` fire for a subagent's compaction as for the main
  conversation's, but none of their payloads names the agent; TAT registers `PostCompact` alone, and reads nothing from it but its `transcript_path`, the session it belongs to (the second check below). A compaction is detected at the agent's next
  announcement, from the agent's own transcript, which Claude Code has
  written before that announcement: a compaction boundary there that
  TAT has not recorded is the agent's compaction event. So is an
  announcement whose `transcript_path` differs from the one at the
  agent's previous announcement: `/clear` and `/resume` replace the
  main conversation's context, and count as a compaction of every
  subagent running across them as well (CLIENT_HOOKS.md §2). So is a
  transcript whose part TAT had read is no longer there, which TAT
  reads again from its first line (CLIENT_HOOKS.md §2). A main
  conversation whose transcript TAT does not find at an announcement
  cannot be served; a subagent whose transcript TAT has not yet found
  is served, and its transcript is read from the first announcement at
  which it exists — a compaction the subagent's transcript records
  before that first reading is not detected (CLIENT_HOOKS.md §2). When
  the main conversation's transcript is not found, the payload names
  none, or a transcript TAT has found can no longer be read, TAT ends
  the conversation with a `ClientRefused`, a `TAT_StartupError`
  (EXCEPTIONS.md §3), `TAT cannot serve this client: Claude Code saves
  no transcript of the conversation. Start it without
  --no-session-persistence.`, which the launcher prints before exiting
  2 (MODULE_STRUCTURE §5); every tool call is answered the ending's
  line for it meanwhile (RENDER_BASELINES §4).

  Two checks guard the premise that the transcript shows every
  compaction before the agent's next call (CLIENT_HOOKS.md §2). Each
  fails the conversation as an unannounced call does — `TAT_InternalError`
  carrying the check's message, which the launcher prints, the log's
  `check_failed` recording it (LOGGING.md §4), every tool answered the
  ending's `an internal error` line: a compaction boundary found for an
  agent whose own timestamp precedes that agent's previous served
  announcement, `TAT found a compaction of agent <id> recorded after a
  result it had already rendered for that agent; its reading of Claude
  Code's transcripts cannot be trusted.`; and a `PostCompact` hook for
  a session TAT reads that no compaction boundary in that session's
  transcripts matches — each hook matched with one boundary, timestamped
  within 10 seconds before the hook or appearing within 10 seconds after
  it — `TAT received a PostCompact hook but found no compaction boundary
  in its session's transcripts within 10 seconds; its reading of Claude
  Code's transcripts cannot be trusted.`; a `PostCompact` for a session TAT
  does not read yet starts no check. Neither check clears a seen set.

`SessionEnd` is not handled: what follows the client's exit is
ARCHITECTURE §9's, and the event also fires while agents still work.

`agent_of_call` never guesses. On both clients a `PreToolUse` hook
(matcher `mcp__TAT__.*`) announces every call before the client sends
it, and the call must have been announced: on Claude Code the
announcement's `tool_use_id` is the call's `_meta["claudecode/toolUseId"]`
and its `agent_id` (empty for the main conversation) the identity; on
Codex the announcement's `tool_use_id` is the call's `_meta.callId` and
the identity is the call's `_meta.threadId`, the thread's own. A Claude
Code announcement whose payload carries an `agent_id` and no
`agent_type` is an internal agent's: Claude Code runs it on a copy of a
conversation for a purpose of its own — the prompt suggestion after a
turn, the progress summary of a background subagent — saves no
transcript for it, and refuses its tool call itself after the hooks,
whatever they answer. TAT answers it the grant below and does nothing
else: it creates no agent, reads no transcript, and records the call
for nobody, so a call under its `tool_use_id`, should one arrive, is
unannounced. On Claude Code the announcement's answer also grants the
call:
`{"hookSpecificOutput": {"hookEventName": "PreToolUse",
"permissionDecision": "allow"}}`, without which Claude Code refuses
TAT's tools under `-p` and prompts for a background subagent's call. A
call without an announcement means the client's hooks do not reach
TAT: the framework raises `TAT_InternalError` (`This call was not
announced by the client's hooks, so TAT cannot tell which agent is
calling.`, logged as the `tool` record `unannounced`, LOGGING.md §4,
never shown) and the conversation ends, every tool
answering the ending's `an internal error` line (RENDER_BASELINES §4).
The hook script never exits 2: every decision — the announcement's
grant, an interruption's refusal, a stop's block — travels in the JSON
TAT answers, an allowed interruption and an
unblocked stop are empty answers, and every failure of the script's
own — no TAT to reach, the script failing for a reason of its own — is
exit 1, which neither client reads as a block (CLIENT_HOOKS.md). TAT
never reads a hook payload's `cwd` as the working directory.

- Claude Code: `settings.json`'s `env` sets
  `CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS=0` (a `check_construct` is never
  moved to the background), `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP=0` (no
  ceiling on consecutive blocks), `CLAUDE_CODE_SKIP_PROMPT_HISTORY=0` and
  `CLAUDE_CODE_FORCE_SESSION_PERSISTENCE=1` (transcripts on,
  CLIENT_HOOKS.md §2), and `CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION=false`
  (no prompt-suggestion internal agent, CLIENT_HOOKS.md §2). The server
  entry's `timeout` is the
  most a tool call may take, and Claude Code waits at least that long
  for its next byte; the subagent stall watchdog is not configured. The
  project settings load only when the client starts in the agent
  directory.
- Codex: the server entry carries `default_tools_approval_mode =
  "approve"` and `tool_timeout_sec`; `configure` sets Codex's
  `check_for_update_on_startup` to false. Codex runs project hooks only
  when the project is trusted and only under
  `--dangerously-bypass-hook-trust`, which has no configuration
  equivalent: both are given at launch.

`configure` gives TAT's tool calls a limit of twelve hours (Claude
Code's per-server `timeout`, 43200000 ms; Codex's `tool_timeout_sec`,
43200); `check_construct` clamps `wait_seconds` to a minute less. TAT
sends no progress notifications.

## 9. The ending and concurrency

The ending is one object, built in `toplevel.conversation()` before the
`Conversation` and handed to it and to the server: it holds the ending's
future, the tasks it will cancel and wait for, `end(exn)` and
`spawn(coroutine)`. The server registers its tool bodies through
`spawn`; a construction job's run is spawned through it; `end`, in one
synchronous stretch, cancels every running construction job through the
job's own `cancel(None)` — the run detached, its question withdrawn,
`NOT_STARTED`, the task cancelled, nothing told — drops every evaluation
job, and cancels every other spawned task, all without a round trip;
the server's exit waits for the tasks to unwind before the store closes.

A job's settlement — a construction run's end (§3.2), an evaluation
job's report (§3.3) — and a job's drop are each one synchronous step
under no lock.
The server is one event loop, so a stretch with no `await` in it is
atomic against every other coroutine, a locked call included; a
settlement may land between two awaits of a locked call, which then
treats it as made just before it, as lockless readers may see it anyway
(MCP_SPECIFICATION §5). A settlement answers no agent, so anything it raises, a
`TAT_Error` included, is a bug and enters the ending, as anything the
`/hook` path's judgement raises does (MODULE_STRUCTURE §4.6); so is an
evaluation job that `_finished` leaves `RUNNING`, since no second
report comes. No holder of the lock ever awaits a job's task;
`blocking` awaits the jobs' ends only, which settlements and drops set.
`construct`, `cancel_construct`, `answer` and `check_construct` take no
lock: each is synchronous from its checks to its change and renders its
quickview the way `recall` does. The framework cancels a deleted or
amended node's construction job and drops its evaluation job in the
completed events — inside the edit's one
synchronous commit block, before its store write (MODULE_STRUCTURE
§4.2) — never at the gates.

## 10. The AoA round

Decided on 2026-10-03 and stated in node_classes/COMMON.md §3 and THEOREM.md §6: the drive path —
`Proof_Job._run` through `Proof_Obligation`'s callback `TAT.Proof_Obligation.construct` (node_classes/COMMON.md §3) on
the `goal_state` slot the evaluation fills, one call of AoA's
`hammer_or_AoA'` — the entry beside `hammer_or_AoA` with the replay
times beside the text — forked through `fork_job`, the proof store read and
written on AoA's own path, the product returned with its times —, the
driver and the budget from Isabelle's configuration, the bound on
concurrent runs from the Isabelle environment variable
`TAT_MAX_CONCURRENT_CONSTRUCTION_JOBS` (§3.2), the function AoA
exports for the replay of one record, and emission keeping `by aoa`.

Still the round's: the question kinds — AoA's `request` tool, which
today lets the AoA agent add subgoals in AoA's own global environment,
reports instead to the TAT agent that drives the job, as a question that
agent answers (§3.4): its text and schema, what the answer means, what
AoA does while it waits and after; AoA being told that it runs under TAT
and given a way to talk to TAT — the task kind the `IsaMini.AoA` call
carries, and the words; a job that continues through a context change
and repairs a stored proof — for which `start` would have to hand `_run`
the outcome it clears, since the node no longer holds it while the run
goes, and whose `_run` would end with a replay instead of
`Proof_Check.passed` —, until which a context change cancels the run and
the construction is started again. To measure, not to design:
cancellation on the AoA side — how soon the Python half learns of the
interrupt of the forked task, and that AoA's own `group = NONE` forks
end with the job —, which waits for the round's scripted driver; that
TAT's process serves `IsaMini.AoA` is measured: the plugin's package
imports it (node_classes/COMMON.md §3).
The two requirements of the owner's bind the remainder: AoA's `request`
reports to the TAT agent as a question, and AoA is told it runs under
TAT. What `product` holds is decided, the method text AoA writes to its
proof store with its times, and so is the proof check: a replay of that
text under limits derived from the times recorded with it, with no
reason shown when it fails (node_classes/COMMON.md §3).
