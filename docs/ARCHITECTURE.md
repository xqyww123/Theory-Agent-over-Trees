# TAT Architecture

Status: design draft.

Three section markers:

- ***(decided)*** — settled, though it may name an open detail of its own and
  point to [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) for it.
- ***(open)*** — an active question, listed in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).
- unmarked — provisional.

## 1. Glossary *(decided)*

These terms are fixed. Use them and no synonyms, and write them in English
wherever they appear — in documents, code, comments and discussion in any
language. A concept that needs a name gets one here first.

| Term | Meaning |
| --- | --- |
| **forest** | all working theories, as a set of trees grouped into `Session`s (§2) |
| **tree** | one Isabelle theory; the root's name is the short name of the theory |
| **node** | one semantic unit in a tree |
| **node class** | the kind of a node — `Theorem`, `Define`, … — extensible |
| **plugin** | a node class as delivered: the Isabelle theory carrying its evaluator and the Python package carrying the rest (§6); TAT's own are always loaded, any other is named by `-P` to `isabelle TAT_new` or `isabelle TAT` (§9) |
| **segment** | one Isabelle span in an emitted file |
| **state slot** | a name standing for one `Toplevel.state` held on the Isabelle side |
| **state slot table** | the Isabelle-side map from state slot names to their `Toplevel.state` values, one per conversation (EVALUATOR_DESIGN §1.1) |
| **base heap** | the heap TAT's prover runs on, chosen by the launcher, with nothing of TAT in it (§8, §9) |
| **Isabelle session layout** | the Isabelle process's map from each known Isabelle session to its directories, and the theories a ROOT marks `(global)`: what the launcher hands `Resources.init_session` at start (MODULE_STRUCTURE §5), and what `Resources.find_theory_file` and `Resources.global_theory` read (EVALUATOR_DESIGN §2, §7) |
| **tree order** | depth-first, a node before its children, children in their own order |
| **evaluate** | running a node's commands in Isabelle and recording what happened (§3) |
| **emit** | a node writing its own Isar text (§4) |
| **compile** | turning the forest into `.thy` files and a ROOT on disk, by `isabelle TAT_compile` (§4, §9) |
| **conversation** | one run of TAT, from Isabelle's call into Python — or, within that call, from `TAT.reset` beginning a fresh conversation on the same Isabelle process — until either process stops, the connection between them closes, a bug, a `TAT_DisasterError` or a `TAT_StartupError` refusing the client (§9) ends it from inside, or its host ends it to begin a fresh one; one per working directory (§9); a compile (§4) is not one |
| **launcher** | the Isabelle tools of `tat.scala`: `TAT_new`, which makes a working directory, and `TAT_mcp`, `TAT_compile` and `TAT`, which start the Isabelle process on the chosen base heap through the boot and call `TAT_Framework.start` or its compile counterpart — `TAT` making the working directory first when needed, and starting the agent client once the conversation is served (§9) |
| **boot** | `ML/TAT_Boot.ML`, the one ML file the launcher loads into the Isabelle process before TAT's theory exists; it defines the protocol command `TAT.boot` (MODULE_STRUCTURE §5) |
| **working directory** | the one directory TAT is started on; it holds the forest's database, the lock file that claims it for one conversation or one compile (§4, §9), each conversation's or compile's log (LOGGING.md), the ROOT, one folder per `Session` for its trees' `.thy` files (§4), and the agent directory; with their own tools the agents read and write nothing of it but the agent directory, short of the gaps listed at the end of CLIENT_HOOKS.md §5 |
| **agent directory** | `<working directory>/TAT.agents/`, the directory the agent client is started in: it holds the client's files, which the server's `configure` writes at launch, and whatever the agents write, and apart from it the agents' shell and file tools read and write no file of the user's, short of the gaps listed at the end of CLIENT_HOOKS.md §5; `TAT_new` does not make it |
| **edit** | any change to the forest — the `edit`, `move` and `delete` tools all make edits; the tool named `edit` (MCP_SPECIFICATION §1) is the narrow sense |
| **construct** | what the agent submits to become a node: a JSON object whose `kind` names the node class and whose other fields are the class's own (TOOL_SCHEMAS.md); in the code it is a `RawAST` |
| **Location** | a position in the forest: on the wire, the destination forms of `edit` and `move` (TOOL_SCHEMAS.md); resolved by the framework to a parent and an index within its children, which is what the move hooks receive (MODULE_STRUCTURE §4.1) |
| **anchor** | the node a Location is relative to: `edit`'s `target_id` under `append`, `insert_before` and `insert_after`, `move`'s `location.node_id` (TOOL_SCHEMAS.md) |
| **print mode** | what a rendering is looking at: one of `Out_Focus`, `Briefing`, `Relative_Focus`, `Recall` (PRINT.md) |
| **focus** | under `Relative_Focus`, a node the quickview prints detailed: one a tool call was about, or one within the call's depth under it; the quickview expands the path from the root to them (PRINT.md §2, §5) |
| **mark** | the words in parentheses on a node's line that say its state — the framework's `complete`, `failed`, `not evaluated`, `incomplete`, or a class's own; no line is bare (PRINT.md §1) |
| **quickview** | the rendering that closes the body of the result of `edit`, `move`, `delete`, `evaluate_to`, `construct` and `cancel_construct` (PRINT.md §5) |
| **briefing** | the rendering `recall` gives with no id: every node of the forest, one line each, to the bottom — what an agent reads after its context was replaced (PRINT.md §5, RECALL.md) |
| **seen set** | an agent's record of what a class has shown it once, `Agent.seen`; cleared when that agent's context is replaced (PRINT.md §4) |
| **agent** | one agent of the client process: its main conversation — the client's, not a TAT conversation — or one of its subagents (CONSTRUCT_INTERACTION §4) |
| **job** | work done on a node's behalf that outlives the tool call it began in (CONSTRUCT_INTERACTION §3) |
| **construction job** | a node's own agent-started job — a `Theorem`'s proof construction; at most one per node, created with the node (CONSTRUCT_INTERACTION §3.2) |
| **evaluation job** | a job an evaluation starts on a node — a `Theorem`'s proof check; at most one on a node at a time (CONSTRUCT_INTERACTION §3.3) |
| **owner** | the agent a construction job's current run belongs to: the one whose `construct` started it, or, for a run started automatically, the one whose call ran the evaluation that started it |
| **starter** | the agent whose call ran the evaluation that started an evaluation job |
| **title** | a job class's words for its work, singular and plural: `proof construction`, `proof check` |
| **message** | text addressed to one agent: a notification, told once, or a question, which waits for an answer (CONSTRUCT_INTERACTION §3.4); also, the messages of a status value: Isabelle's output of a run, as `IsaTerm`s, shown under `Error:` or `Notice:` (§3.2, PRINT.md §3) |
| **mailbox** | an agent's undelivered messages, delivered on its next tool result |
| **compulsory** | a construction job the forest is not complete without (§3.2) |

Isabelle's build unit is always written **Isabelle session** in full; the
`Session` node class (§2.2) is one Isabelle session under construction.

Two relations are easy to confuse, so neither is called an edge. **Import
dependency** holds between trees, and is what the tree roots declare in their
`imports` clauses. **Nesting** holds between nodes: a `Session` contains its
trees' roots, and nodes inside one tree contain one another.

`node` in this repository always means a node of a TAT tree. Isabelle's own
document model (PIDE, its interactive document layer) also calls a theory file
a node; where that meaning is intended it is written **PIDE document node** in
full.

## 2. The model *(decided)*

A tree is one theory. The forest's first layer is its `Session` nodes: every
tree's root sits under exactly one `Session`, an Isabelle session under
construction (§2.2). Import dependency between trees makes the forest a
dependency graph, and compilation order is a topological order over it;
imports cross `Session` boundaries freely. The `Session` layer is ordered
like every other; Isabelle reads no meaning into that order.

The node classes: `Session` and `Theory`, the framework's, and those of
the plugin `Isabelle_Std`, listed in
[node_classes/INDEX.md](node_classes/INDEX.md). New node classes must be
addable without touching the core. Every tree's root is a `Theory` node, which
owns the theory header, the `imports` list and the `end`.

Each node class corresponds to one or more Isabelle commands.

TAT writes only theories it authored; reading in a foreign `.thy` is out of
scope.

### 2.0 Nesting *(decided)*

A node either contains other nodes or does not.

`Session` contains the roots of its trees (§2).

`Theorem` is a leaf.

`Section` contains the declarations under its heading. It is **presentational
only**: it emits a `section` command and creates no Isabelle scope, so it changes
nothing about how its children are checked or named. It is a nesting node with an
beginning command and no ending one.

`Context` and `Locale` also contain nodes, and unlike `Section` they carry
**operational behaviour**: they open an Isabelle context, so their children are
checked inside it and the facts they declare are qualified by it. Both are
unspecified (OPEN_QUESTIONS §1); a `Theorem`'s evaluation is already one
transition on its input slot's state, so it is checked inside whatever
context that state holds (THEOREM.md §6).

### 2.1 The trees are pure declarations *(decided)*

No proof structure enters a tree. Every proof is emitted as the `aoa` proof
method — Sledgehammer first, falling back to the AoA proof agent when it
times out; while a node has no proof, or its stored check is not
`PASSED`, it emits `sorry` instead (§2.2). A build of the emitted file
finds the proof in the theory's proof store, `<short name>.proof-store`
beside the file, where the node's construction recorded it
(node_classes/COMMON.md §3), so `by aoa` there replays and searches nothing. A `Theorem` node carries what is claimed,
never a proof subtree; the proof its construction job found is that job's
product — the method text AoA writes to its proof store, such as `(simp
add: …)` or `aoa_replay "…"` (§3.6, node_classes/COMMON.md §3) — which the framework
stores on the node (CONSTRUCT_INTERACTION §3.1).

Throughout this repository, `aoa` in code font is that proof method. AoA in
plain text is the agent system the method falls back to, and the one a
`Theorem`'s construction job drives to find its proof.

### 2.2 Node classes *(decided)*

`Session` and `Theory` are the framework's. The node classes of
Isabelle's standard commands — `Theorem`, and the others of this
section as they are specified — are one plugin, `Isabelle_Std`
(MODULE_STRUCTURE §4.5), which a working directory takes with `-P` to
`isabelle TAT_new` or `isabelle TAT`.

**`Theorem`** is specified in [node_classes/THEOREM.md](node_classes/THEOREM.md):
four kinds (`lemma`, `theorem`, `corollary`, `proposition`), a `name`, a
`statement` (AoA's `LongStatement`), and, recorded by the framework, `proof`
— the construction job's outcome, `NOT_STARTED`, `RUNNING`,
`SUCCEEDED(product)` or `FAILED(message)` (CONSTRUCT_INTERACTION §3.1) — and
the proof check's outcome, the evaluation job's.

Adding a `Theorem` starts no search: its `proof` is `NOT_STARTED`, so
laying out a theory costs nothing. `construct` starts the construction
job, and so does an evaluation that reaches a node whose automatic
construction is on, when the node needs it (`edit`'s, `construct`'s and
`cancel_construct`'s `auto_construct`, CONSTRUCT_INTERACTION §3.3). A
node emits **`by aoa`** when
`proof` is `SUCCEEDED` and the proof check's stored outcome is `PASSED`,
and **`sorry`** otherwise; its evaluator never runs a proof: it admits the statement with
`global_skip_proof` every time (§3.6, THEOREM.md §6). A failing proof would
mean the fact is never added, so every later node using it fails too — a
skeleton of twenty lemmas would check none of them past the first. With the
fact admitted, the whole tree's structure and types are checked, and the
agent constructs proofs afterwards.

This is honest only because the jobs are tracked: such a node evaluates
without error and is still not `finished` (§3.2), so TAT never mistakes an
admitted fact for a proved one.

**`Define`**

| Field | Type | |
| --- | --- | --- |
| `auto_reduction` | `bool` | authored |
| `equations` | the defining equations | authored |
| `form` | `definition` \| `fun` \| `function` | recorded |

With `auto_reduction` true the resulting definitional equations carry
`[simp]`; with it false they are removed again with
`note f.simps[simp del]`. A single equation is a
`definition`; several are a `fun`, or a `function` with its proof obligations
discharged by `aoa` when `fun` cannot establish termination on its own. Which of
the three was used is decided during evaluation and recorded on the node, so
emission needs no further enquiry.

A `Define` emits several commands, each able to fail on its own, and its
evaluator reports each separately.

| command | emitted | when |
| --- | --- | --- |
| `function` | the defining command, in whichever `form` | always |
| `pat-completeness` | the completeness proof | `form = function` |
| `termination` | `termination by …` | `form = function` |
| `simp-del` | `note f.simps[simp del]` | `auto_reduction` is false |

**`Session`** and **`Theory`**, the two classes that carry the forest's
structure, are specified in
[node_classes/SESSION_AND_THEORY.md](node_classes/SESSION_AND_THEORY.md).

The plugin's other classes, and which of them are specified, are
[node_classes/INDEX.md](node_classes/INDEX.md).

## 3. Evaluation *(decided)*

Evaluating a node means handing its data to its node class's evaluator on the
Isabelle side, which runs the node's commands and reports what the class
decides to report. Nothing is checked unless TAT asks for it, because TAT
submits the commands.

### 3.1 State slots

Every node owns one **state slot**: a name standing for the `Toplevel.state` the
node starts from. The name belongs to the node for as long as the node exists,
and re-evaluating the node writes that same name again. The Python side never
holds a state, only a name. A class may own further slots beside the
node's own: it mints them itself and names the operation that writes
each, and the framework releases them with that operation's result
(MODULE_STRUCTURE §4.1); the plugin's `goal_state`, the state in which
a proof obligation's goal stands open (node_classes/COMMON.md §3), is
the one so far.

A node's resulting state is the slot of its next sibling, or, for a last child,
the slot its parent keeps for the position after all its children. The
resulting slot of one node and the input slot of the next are therefore the
same slot, and re-evaluating a node writes into slots that already exist.
The one exception is a container whose children are not chained — a
`Session`'s trees, the root's `Session`s: there a child that has a result
owns a slot for it, which nothing reads, and the container keeps no slot
of its own (ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §6).

A nesting node's beginning command writes its first child's slot. After the
last child, the nesting node's ending command reads the slot it keeps for the
position after all its children and writes its own resulting slot; a class
with no ending command, such as `Section`, copies the one into the other.

When a node fails and is passed over, the framework copies its input state
into its resulting slot (§6.2), so whatever follows always has something to
run from.

Whether a slot currently holds a state is asked of the table; the Python side
mirrors nothing.

### 3.2 Two fields

Every operation a node runs has an `evaluation_status`, its **instant
status**, which says whether evaluation passes through it. A leaf has one
operation; a nesting node has two,
its beginning and its ending, and so two statuses.

| value | meaning |
| --- | --- |
| `not_evaluated` | no current result; nothing in the resulting slot to rely on |
| `ready` | the operation ran and its resulting slot is current |
| `cannot_evaluate` | the operation ran and failed, and its class judged the failure fatal: the node is an obstacle (§3.3) |

Every operation has a second field beside `evaluation_status`, its
**stored status** `last_evaluation_status`: the value `evaluation_status`
was last given, stored in the database (§4.1) and restored on load,
while `evaluation_status` itself is not stored. A node holds its
operations' stored statuses as one list, one entry per operation in the
order its base class fixes — one for a leaf, two for a nesting node, none
for a container whose children are not chained — and no class adds
operations of its own. The values have one form each: `NOT_EVALUATED`,
`Ready(messages)` and `CannotEvaluate(messages)`, where `messages` are
what the run reported, Isabelle's output as `IsaTerm`s — a
`CannotEvaluate`'s the reason it failed, a `Ready`'s the warnings or the
failure the class carried on past, `Ready()` a clean run; the evaluation
hook returns the status (§6.2), and the framework prints the messages
under `Error:` or `Notice:` (PRINT.md §3). Which field a reader reads:
everything about slots and running — the walk's rerun tests, the
releases, `finished` and the mark — reads `evaluation_status`; every
decision to invalidate or keep a stored status (§3.4), `can_emit`
and the compile report (§4) read the stored status. At rest the two are
equal wherever `evaluation_status` is not `not_evaluated`; they differ
only on a loaded node not yet rerun (COMPILATION.md §4).

A node whose own commands failed is still `ready` when its class can carry on
regardless. A `Theorem`'s evaluation never runs a proof, so a proof that
fails its check leaves the statement `ready` and only the evaluation job
`FAILED`: the fact is declared and every later node still checks. A nesting
node whose beginning command
failed has that beginning `cannot_evaluate` and, when the walk goes on
after the block, its ending `ready` without running: the framework copies
the node's own input state straight into its resulting slot, and
evaluation resumes after the block (§3.3).

No node class reads another node's statuses: a node renders its own report,
and the one question a class asks of another node is `finished`. The
framework's walk does read them — that is how it knows what to run (§3.5).

`finished` says whether the node still owes anything. It is derived, never
stored, so it cannot drift from what it is derived from, and the framework
owns the derivation: a node is `finished` when every operation of its own
and of its subtree is `ready`, and `_unfinished()` answers `None` on it
and on every node of its subtree. `_unfinished()` is the framework's,
derived from the node's construction job and the check's outcome
(CONSTRUCT_INTERACTION §3.1): `None` when the node has no compulsory
construction job, or its construction job `SUCCEEDED` and the check, if
its class names an evaluation job, `PASSED`; otherwise the `Unfinished`
that says what is owed — the construction, the check, or a check not
yet run. A class may override it; `Theorem` does
not, and a class with no construction job owes nothing. `Session` runs no
operation and has no `evaluation_status` of its own.

A forest is complete when every node is `finished`, and only `finished`
answers that question: a `Theorem` that emitted `sorry` ran a command that
succeeded.

### 3.3 Where evaluation stops

A `cannot_evaluate` node is an obstacle. What an obstacle blocks — after it
in its tree, under it, or in a tree that imports its tree — is
`not_evaluated`, like a node that never ran: which obstacle blocks it is
not recorded on the node, and the tool that ran the evaluation names the
first stop in its answer (§3.5, MCP_SPECIFICATION §4).

A node whose failure would make everything after it report **derived errors**
is an obstacle by the judgement of its node class. `Define` is the case: when
the defining command fails the constant does not exist, so every later node that
mentions it fails with a message about the constant instead of about itself. A
nesting node whose ending command failed is one too: a `Theory` whose `end`
failed has no theory value. Such a node **stops** evaluation: everything after
it in the tree is `not_evaluated`.

A **nesting node whose beginning command failed** leaves its children no context
to run in. Its beginning is `cannot_evaluate` and, like any obstacle, is not
rerun until it is edited (§3.5);
its ending is `ready` once a walk has gone on after the block (§3.2);
every node under it is
`not_evaluated`, and none of them runs while the ancestor stays as it is.
This is not a stop: evaluation resumes after the block — unless the
destination lies under it; then the tree's walk ends there, everything
after the destination is invalidated (§3.4), and the call reports the
node as its stop when `ignore_error` is unset (§3.5).

Two stops are the forest's, judged before a tree runs (§3.5). **The order
constraint**: a tree comes after every forest tree it imports — within a
`Session`, later in the list; across `Session`s, in a later `Session` — so
that tree order is a dependency order. A tree importing a forest tree
placed after it, or itself, is not run but invalidated whole,
`not_evaluated` throughout, and is a stop at its
`Theory` node; no edit refuses the state, which legal edits
reach, and the check runs before every run of the tree, so a repairing
`move` clears it by itself. The forest answers which `imports` item
offends and the tree it names (`_order_violation`, MODULE_STRUCTURE §4.1),
and the tool composes RENDER_BASELINES §3's sentence from it. **The stop crossing an import
dependency**: a tree one of whose resolved imports does not have both
operations `ready` — a theory value exists only once the import's `end`
has run; after a failed header the ending is `ready` and no value exists —
is not run but invalidated whole, `not_evaluated`
throughout, and is a stop at that import's `Theory` node; when the import
stopped for a reason of its own, that reason was recorded first, the
import coming earlier in tree order, and is the one the call reports.

`evaluate_to` takes an `ignore_error` flag for an agent that wants to see every
error in one pass. With it set the walk carries on past a stop, but it
does not enter a nesting node whose beginning failed — its children stay
blocked, a destination among them left `not_evaluated` with no stop
reported — nor run a tree importing one without a theory value: that
tree stays blocked, its nodes `not_evaluated`, and the stop is not
reported. The
call then returns "continue", each error showing at its own node, with one
exception: the order constraint's stop is reported whatever the flag says,
since the tree it concerns is `not_evaluated` throughout and nothing else
records why.

A stop is a fact about the forest, not about one call — but for a nesting
node whose beginning failed, which is a stop only to a call whose
destination lies under it. Every `evaluate_to`
returns either "continue" or "stopped at node X" to its caller (§3.5), and a
stop returns "stopped" whenever the walk reaches it — including on a later call
that finds it already evaluated and skips it — unless `ignore_error` is set. So
every call that reaches the node stops there until it is edited, and
every call whose destination lies under a failed beginning stops at that
node; a call to a node after the block goes on past it. A node blocked by
an obstacle, on the other hand, runs as soon as a call reaches it unblocked.
With `ignore_error` unset the walk of the stop's tree ends at the stop
as it ends at its destination, and everything after the stop to the
tree's end is `not_evaluated` (§3.4), an obstacle after it included:
such a node shows `not evaluated` until a walk reaches it unblocked and
runs it on its input.

### 3.4 Invalidation

Invalidating a node marks it and every node after it in its tree
`not_evaluated`, and marks every tree that transitively imports that tree
`not_evaluated` in whole. A tree's states are built on the theory values of the
trees it imports, so a change anywhere in an imported tree invalidates all of an
importing one. This is a property of the tree's `Theory` ending's stored
status: whenever a stored `Ready` ending is replaced by a value that is
not a `Ready`, the tree's direct importers are invalidated whole,
each ending so moved carrying the rule on to its own
importers, so that no transitive importer keeps a current result. Every
status write goes through one setter per operation, which writes
`evaluation_status` and the stored status together (MODULE_STRUCTURE
§4.1). This cascade, an edit's invalidation — from one position, or from
two for a `move` (§3.5) —, the walk's stops at a tree (the order
constraint's, an import without a theory value, §3.3), its marking of
the children under a failed beginning (§3.3) and its marking past its
destination, or past the stop it ends at when `ignore_error` is unset,
are one
synchronous recursion with one implementation — a node's
`_invalidate(ev)` and `Forest._invalidate_from(position, ev)`, plain
functions taking the walk's `Evaluation` (§3.5, MODULE_STRUCTURE §4.1,
§4.2). The setter leaves unwritten an operation whose stored status is
already `not_evaluated` (MODULE_STRUCTURE §4.1); the guard reads the
stored status (§3.2), so it holds on a loaded forest as in a running
conversation.

No tree stays evaluated once a tree it transitively imports has been
edited, renamed, moved, deleted or had its `Theory` node replaced;
renaming a `Session` does that for every tree under it, since their
qualified names carry its `name`; a reorder of trees or of `Session`s
touches no tree. Every edit compares, per tree, its qualified name and its
resolved imports — the `Theory` nodes themselves — before and after
itself, and invalidates whole a tree for which either changed (the
mechanism: MODULE_STRUCTURE §4.2).

Whatever an operation wrote is released when the operation stops being
current — its result, or the input it copied through on failing; the names
stay with the node and re-evaluation writes them again. A walk collects what
it releases and deletes it in one round trip at each tree's end and again
when it ends; there it also stores every node whose status it wrote,
whole, in one transaction (COMPILATION.md §4), and cancels the
evaluation jobs it dropped (CONSTRUCT_INTERACTION §3.3). Deleting a node
releases every state its subtree owns and cancels any work in flight on it.

Inserting or deleting a node changes which slot its predecessor's resulting
state is (§3.1), so the value moves with it when the predecessor has written
one: on insertion the slot formerly at that position is copied into the new
node's; on deletion the deleted node's slot is copied into the one now at its
position. When the predecessor has written nothing, nothing is copied, and
nothing is there to release: a node writes only after its predecessor
has, since it runs, or copies its input through, only from the input its
predecessor wrote (§3.1, §3.5). The predecessor is not touched.

Because invalidation always runs forward, a tree's evaluated nodes are a prefix
of it in tree order, but for the nodes under a nesting node whose
beginning failed, which stay `not_evaluated` while evaluation resumes
after the block (§3.3). TAT keeps no separate record of how far evaluation has
reached: the recursion of §3.5 skips what is evaluated and runs what is not.

### 3.5 Running an evaluation

`evaluate_to(destination, ignore_error, checks)` (MCP_SPECIFICATION §4)
runs every `not_evaluated` node up to and including the destination, in
tree order — a `cannot_evaluate` obstacle is not rerun, and one that is a
stop reports itself again (§3.3) — and invalidates everything after the
destination in its tree, or, in a tree whose walk stops, after the stop
— after the destination still when the stop is a nesting node above it
whose beginning failed (§3.3, §3.4). It is one recursion,
called from the top of the forest under the forest's one lock, so two calls
never interleave:

- The **forest** resolves the destination's id and works on the theories
  directly — evaluation is transparent to the `Session` layer: it builds the
  import dependency graph over the trees, evaluates every tree the
  destination's tree transitively imports to its own `end` — a theory value
  exists only once its theory is closed — in tree order, which the order
  constraint (§3.3) makes a dependency order, then calls the
  destination's tree; a tree that violates the constraint, or whose import
  has no theory value, is a stop instead (§3.3). A `Session` as destination
  stands for all the trees under it, and the root for every tree: the
  forest schedules each of them, to its `end`, through the same graph.
- A **nesting node** runs its beginning command if it is not evaluated. If that
  command succeeded, now or earlier, it calls its children in order up to
  the one that contains the destination, what follows being invalidated
  past the destination (§3.4);
  if it failed, it invalidates each of them whole instead of running them
  (§3.3): when the destination lies under it the walk ends there, the
  node is the stop the call reports when `ignore_error` is unset, and
  everything after the destination is invalidated (§3.4); otherwise its
  input stands as its result and the walk goes on after
  it. A nesting node is reached at its ending
  command: it is the destination only once its children have run, so naming a
  `Theory` means the whole tree, `end` included.
- A **leaf** runs its commands if it is not evaluated or the walk rewrote the
  state before it, and otherwise runs nothing.

The recursion visits every node up to the destination, or up to the
first stop when `ignore_error` is unset, or, whatever the flag, up to a
nesting node above the destination whose beginning failed; there the
tree's walk ends, and everything after that node to the tree's end is
invalidated — after the destination, when the walk ended at such a
nesting node (§3.4).
Nothing is skipped on the way:
a written operation is not rerun — whatever stands after one that ran is
`not_evaluated` already, since every invalidation runs forward to the
tree's end (§3.4) — and a nesting node whose ending is `ready` is still
entered, since an obstacle passed under `ignore_error` may sit inside it.

An edit's invalidation evaluates nothing. It has a position — a parent
and an index among its children — reached before whatever stands there:
inside a tree, the node standing there whole, together with what follows
it in that tree, the index after the last child naming the parent's
ending; at the `Session` layer and the root, nothing — sibling trees are
independent, and the trees an edit there disturbed are reached through
the comparison of §3.4. That is what a deletion needs (§3.4): nothing new
to run, only the successor and what follows in its tree to invalidate.
An edit invalidates from each position whose input it changed: one for
an insertion, an amend or a deletion; two for a `move` — the position
its successor holds where the node left, taken once the node is out (the
parent's ending when the node was last), and the node's new position —
since where it left, the successor now reads the predecessor's result,
so that tree's ending and, through it, that tree's importers are
invalidated too. Where the two overlap, an operation already
`not_evaluated` is not written again (MODULE_STRUCTURE §4.1).

`checks` says whether the walk starts evaluation jobs (CONSTRUCT_INTERACTION
§3.3, §5): on every node it passes — reached in the `Evaluating` mode, up to
and including the destination — whose class names an evaluation job class,
which is `ready`, has no evaluation job, and whose `_unfinished()`
would answer `Unchecked`, it starts one at the node's last operation;
`"no"` starts none,
`"quick"` leaves them running in the background, `"blocking"` keeps the lock
after the walk until every evaluation job running on a passed node has
ended. `edit` and `move` evaluate with `"quick"`.

Every call returns "continue" or "stopped at node X" (§3.3); at a stop,
with `ignore_error` unset, the tree's walk ends and what follows in the
tree is invalidated (§3.4), the answer travels up to the forest, and the
forest goes on to the next tree it schedules.

Editing a node marks it `not_evaluated` and invalidates everything after it
— a `move`, also what followed the node where it left — in the edit's own
commit, a synchronous recursion that runs nothing
(MODULE_STRUCTURE §4.2 step 3), whatever the editing call's `evaluate`
flag; when the flag is true, the evaluation follows the commit
(MCP_SPECIFICATION §3.2). Editing a nesting node's own commands first
invalidates from its first child, since the children are before it in the
walk and would otherwise be kept.

### 3.6 Work that outlives a call

Evaluation is synchronous: a loop that submits one command and waits. It never
searches for a proof, never replays one, and never runs `by aoa`, which
exists only in emitted files (§2.1): `Theorem`'s evaluator runs the statement
alone and admits it (THEOREM.md §6). Work that outlives a call is a **job**
(CONSTRUCT_INTERACTION §3), of two kinds. A **construction job** is the
only thing that starts a search; an agent starts it with `construct`,
or an evaluation does where automatic construction is on, at a node it
passes or on a check that failed (CONSTRUCT_INTERACTION §3.3); a
`Theorem` whose search is running has `proof = RUNNING`. An **evaluation
job** is started by an evaluation when `checks` allows (§3.5); a `Theorem`'s
proof check replays the stored proof in the current context, and its
`FAILED` outcome, not the evaluation's, is what `bad proof` on the node's
line means.

A construction job is told when its context changes under it through the
framework hook `_on_context_change`, called from the status setters on every
write of the node's own evaluation status by the walk while the job runs —
a rerun rewrites `ready` in one step, and that rewrite counts; the setter
fires it as it fires a completed hook, after the write, so anything it
raises is its class's bug (EXCEPTIONS.md §1); the default
cancels the job, and `Theorem` keeps the default. An evaluation job is
dropped on every such write too (CONSTRUCT_INTERACTION §3.3). A job that
continues on a new context is the AoA round's (CONSTRUCT_INTERACTION §10).

## 4. Compilation *(decided)*

TAT is the compiler and owns the `.thy` files. Isabelle never reads them
during a conversation — every change reaches Isabelle by evaluation (§3) —
and they exist for whoever builds the Isabelle sessions afterwards; the one
reading Isabelle makes of them under TAT is the compile's own check of what
it wrote (COMPILATION.md §2).

The forest is compiled by one command, `isabelle TAT_compile
WORKING_DIRECTORY` (§9), a step of the host's pipeline after the
conversation; no tool, no edit and no ending of a conversation writes a
`.thy` or the ROOT. A compile evaluates nothing: it loads the forest from
the database and writes what the stored statuses allow (§3.2,
COMPILATION.md). It writes under the working directory (§1): at its top a
ROOT holding every `Session`'s entry, and under one folder per `Session`,
named after it, its trees' `.thy` files. The forest stores no path, so it
moves machines by being compiled on another directory.

A node writes its own text through `emit(indent, out)`, which writes whole
lines to `out` and returns the indent in effect after it; a nesting node's
`emit` is the framework's, which calls the class's `emit_beginning` and
`emit_ending` around the children (§6, COMPILATION.md §3). The `indent`
passed in is a proposal; a node class that opens or closes an Isabelle
block returns the value it actually leaves behind. Emission reads the
stored statuses and stored fields and runs nothing, so it renders decisions
already made rather than proposing any.

Whether a node emits is `can_emit`, one method whose default answers yes
when every stored status of the node is a `Ready`; a class narrows or
replaces it. `Theorem` keeps the default and emits a `text ‹Lemma <name>.
<english>›` line, the statement, and `by aoa` for a proof that is
`SUCCEEDED` and `PASSED` by its check, `sorry` otherwise (THEOREM.md §5).
A `Theory` with a `description` emits it as a `text ‹…›` block before its
`theory` line (node_classes/SESSION_AND_THEORY.md §2). `Define` will not
emit at all when its defining command failed, since no text would compile.
A tree is written only when every node in it agrees to emit — a `.thy`
with a hole is not a theory — and every forest tree it imports is written;
a tree imported by an unwritten one is written all the same, and the
ROOT's `theories` lists the written trees (COMPILATION.md §2). A written
file may hold `sorry`; building it then needs Isabelle's `quick_and_dirty`
option, which is the builder's business, not TAT's: compile adds no option
and reports a tree with `sorry` as written.

After a compile the directory holds the forest's files and nothing else of
TAT's: compile removes every `.thy` under the working directory and the
ROOT, makes every `Session`'s folder, writes the trees' files, runs the
plugins' compile hooks, removes the folders left empty that it did not
make, and writes the ROOT last. Every removal goes through one path
listing, which enters no folder whose name begins with a dot and follows
no symbolic link; a `Session`'s folder that is not a directory is refused
before anything is removed (COMPILATION.md §2, §5).

### 4.1 Persistence

The `.thy` files are not the forest: what a node records is not in them. The
forest lives in a database in the working directory, one row per node
field, and each node class writes and reads its own fields through
`to_store` and `from_store` (ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §2).
State slot names and `evaluation_status` are not stored: the state slot
table does not outlive the conversation (EVALUATOR_DESIGN §1.1), so a
loaded forest is `not_evaluated` throughout in `evaluation_status` and its
slots are assigned afresh. The stored statuses are (§3.2): one reserved
row per node, `last_evaluation_statuses`, holding the list with each
status's messages, beside `kind`, `children`, `job`, `check` and the
automatic-construction field below. A row that is missing, or whose
length is not the node's number of operations, reads as `not_evaluated`
throughout, so the schema version is unchanged (COMPILATION.md §4). The connection to Isabelle is
not stored either; the loaded forest is given the conversation's current one
(MODULE_STRUCTURE §4.1, `Conversation`).
Work in flight is not stored, only its results: a construction job's
outcome is stored with `RUNNING` read as `NOT_STARTED`, so a loaded forest
holds no run, and an evaluation job's outcome is stored the same way —
`PASSED` or `FAILED(message)`, `RUNNING` as none — kept on the node as
the stored check, cleared when a stored status of the node leaves
`Ready`, when a construction job starts on it or another evaluation job
takes its place, and by nothing else; each synchronous step of a job
that changes the job or the check on its node — a construction's start,
a run's settlement, an evaluation job's report, an attach, a tool
writing the automatic-construction setting — stores the
node in a transaction of its own, and the conversation's ending stores
nothing; a loaded forest re-attaches no job and reads the value through
`check_outcome()` (CONSTRUCT_INTERACTION §3.1, §3.3). Each is a
reserved field of the node's stored image — `job` for the construction
job, `check` for the evaluation job — a tag with an optional value, the
product or the failure's message; a
missing one reads as `NOT_STARTED` and as none, so the store's schema
version is unchanged (COMPILATION.md §4). The construction job's
automatic construction is a third reserved field, a boolean; a missing
one reads as off.

## 5. Segments *(decided)*

A segment is exactly one Isabelle span, mirroring Isabelle's own partition of a
theory file (`contrib/Isabelle2025-2/src/Pure/PIDE/command_span.ML:35`, where the
three kinds of span are `Command_Span`, `Ignored_Span` and `Malformed_Span`).
That partition is total — whitespace and comments are spans, not gaps.

| segment kind | Isabelle's term | owner |
| --- | --- | --- |
| command | `Command_Span` | a node |
| layout (blank lines, separator comments) | `Ignored_Span` | none |
| structural (`theory X imports … begin`, `end`, and the `text ‹…›` block a `Theory`'s `description` puts before the header) | `Command_Span` | the root node |

A node may own several segments. No segment is owned by more than one node
(§7).

The finished `.thy` is parsed as a whole by whoever builds it, so each node's
text must be self-delimiting. No check enforces this: a node's text is
written by its class's own emission, which is trusted to write text that
closes.

## 6. The node class contract *(decided)*

A node class is delivered as an Isabelle theory together with a Python package.
The theory is primary: it registers the class's evaluator on the ML side —
into its own theory data (MODULE_STRUCTURE §2.5) — and the registration names
the Python packages carrying the rest, which the conversation collects and
hands to `plugin.py` to import (MODULE_STRUCTURE §2.6, §4.4). Every node
class is a plugin; TAT's own are always loaded, and any other is recorded
in the working directory (§9) and loaded from source when the process
starts (§8), by the name `SESSION.THEORY` of its theory, so that theory
must live in an Isabelle session some ROOT declares.

| part | side | |
| --- | --- | --- |
| data definition, the construct schema and the argument schema | Python | the construct schema becomes the class's part of `edit`'s schema and is what a submitted construct is checked against; the argument schema, a TypedDict the loader holds to it, types `gen`'s `raw` |
| emission | Python | `can_emit` and `emit` — on a nesting node `emit_beginning` and `emit_ending` — reading the stored statuses, run by a compile (§4) |
| construction job | Python | `construction_job_class`, the class of the job `construct` starts, for classes that have one; `job()` returns the node's (CONSTRUCT_INTERACTION §3.2) |
| evaluation job | Python and ML | `evaluation_job_class`, the class of the job an evaluation starts, for classes that have one; its work runs as a Future task on the ML side (CONSTRUCT_INTERACTION §3.3) |
| evaluator | ML | runs the node's commands, reports what it decided |

A construction job is Python because what it drives is: on a `Theorem` it
runs the AoA proof agent, which is a Python program, and the running search
hangs on the Python node (§3.6).

### 6.1 Two kinds of field

A node's fields are either **authored** — supplied by the agent, part of the
node's identity, untouched by evaluation — or **recorded** — produced by
evaluation. `Define`'s equations are authored; the `form` chosen for them is
recorded. A recorded field is only as current as the evaluation that produced it,
and `can_emit`, reading the stored statuses (§4), is what keeps a stale one
out of a file.

### 6.2 The wire

Each node class registers its own callback, with its own argument and result
schema. Node data has no universal representation; the core never sees it,
which is what lets a node class be added without touching the core.

The framework fixes almost nothing. On the ML side a class's callback reads a
state slot name off the wire into a handle carrying `get` and `put` on the
conversation's state slot table, and beyond that is given only the
conversation's `begin_theory` and `end_theory` (MODULE_STRUCTURE §2.5); what it takes and
what it returns are between it and its own Python half. On the Python
side the class's evaluation hook (MODULE_STRUCTURE §4.1) runs that callback
itself, records on the node whatever
it wants recorded — which commands it ran and how each of them fared included
— and answers the framework with the operation's status: a `Ready`,
carrying the run's messages, or a `CannotEvaluate`, carrying the reason it
failed (§3.2). On a `CannotEvaluate`, the framework copies the operation's
input state into its resulting state, so that `ignore_error` has something
to run from; on a nesting node's beginning it instead copies the node's
input into the node's resulting slot as its ending's write, when the walk
goes on after the block (§3.2, §3.5); no class writes that copy.

A class's callback is a local callback of the conversation's one RPC command
(§9, MODULE_STRUCTURE §2.6), named after the class that owns it. For an
evaluation job the framework's ML half also offers one function that forks
the job's work as a Future task and reports its end through the
remote procedure `job_finished`, and one callback, `cancel(ids)`,
that cancels such tasks (CONSTRUCT_INTERACTION §3.3, MODULE_STRUCTURE
§2.5).

### 6.3 Two kinds of ML

The framework and the evaluators are needed only by TAT's own process. Generated
theories never name them, so they are loaded into that process at start (§8)
and appear in no tree's imports.

Anything the generated text does name — the `aoa` proof method, any syntax or
attribute a node emits — must be imported by the trees that use it, and is a
real dependency of the finished forest.

The concrete interfaces are MODULE_STRUCTURE §2.5 and §4.1.

## 7. Command-to-node mapping *(decided)*

The evaluator runs one node's commands at a time and reports their results to
that node. The mapping is given, not reconstructed: there is no line-span table,
and no question of whether our partition of a file agrees with Isabelle's.

No node's commands reach the next node's: each node's operations are
built and applied on their own (§8), and no command text is parsed at run
time but a `Theory`'s header.

## 8. Substrate *(decided)*

TAT drives Isabelle itself, through its own evaluator written in Isabelle/ML.
The evaluator holds an explicit `Toplevel.state` and runs one command at a time
through `Toplevel.command_errors`, which recovers from a failing command instead
of re-raising. Design in [EVALUATOR_DESIGN.md](EVALUATOR_DESIGN.md). Every
operation builds its transition in ML and applies it through
`Toplevel.command_errors` — `Theory`'s header and `end` (MODULE_STRUCTURE
§2.4), and a `Theorem`'s statement, one transition built from its
structure (THEOREM.md §6). The one text parsed at run time is a
`Theory`'s header, read with `Thy_Header.read` (EVALUATOR_DESIGN §1).

The prover runs on one **base heap** — chosen by the launcher (§9), with
nothing of TAT in it — and the forest sits on top of it, no tree
in any heap
(EVALUATOR_DESIGN §2). A `Session`'s `parent_session` is ROOT metadata, not a
constraint on the heap: a library theory the base heap lacks is loaded from
source when the Isabelle session layout knows its file. TAT's own theories
(§6.3) are never in the base heap: they are loaded from source when the
process starts, and so are `Isabelle_RPC`'s theory, which they import, and
the theories of `Performant_Isabelle_ML` it rests on — found through the
Isabelle session of that name — when the base heap lacks them. A base heap
that holds `Isabelle_RPC` spares that loading at every start.

No node class emits `oops`: it leaves no trace in Isabelle's output and so
could not be accounted for.

## 9. The two processes and the channel *(decided)*

TAT is a Python process and an Isabelle process. The Python side owns the forest,
serves the MCP tools and writes the `.thy` files. The Isabelle side runs the
evaluators.

Isabelle opens the connection. The ML entry, `TAT_Framework.start`, is given
the theories whose ancestries name the node classes, the working directory,
the port to serve on and the agent client's name (MODULE_STRUCTURE §2.6) and
calls the Python procedure `launch_TAT` over `contrib/Isabelle_RPC`; Python
drives Isabelle through that call's callbacks, and the call does not return:
the conversation ends when either process stops, when the connection
between them closes, or when a bug, a `TAT_DisasterError`, or a `TAT_StartupError` refusing the client's version or name, Codex's sandbox or a main conversation with no transcript ends it from
inside (MODULE_STRUCTURE §4.6), the call then returning only by raising —
or when its host ends it, within the same call, to begin a fresh
conversation on the same Isabelle process. AoA's entry has the same shape
(`contrib/Isa-Mini/IsaMini/AoA/toplevel.py:174`). What a conversation is
bound to on the Isabelle side is its state — the state slot table and the
theory table: both are empty when the conversation begins and gone when it
ends, whether because the Isabelle process went or because a fresh
conversation began on the same process through `TAT.reset`
(MODULE_STRUCTURE §2.6). A theory loaded from source stays in `Thy_Info`,
the process's cache, so a later conversation's import of it is answered by
`Thy_Info.lookup_theory`, as a base-heap theory is (EVALUATOR_DESIGN §2),
with the same theory value. The next conversation on the same working
directory starts from the database, `not_evaluated` throughout in
`evaluation_status` (§4.1). One conversation per working directory: a
second conversation, or a compile, on a directory whose lock file another
conversation or compile holds is refused with a `TAT_StartupError`. A
Python process may host conversations one after another, or several at
once on different working directories, each with its own Isabelle, port,
forest and database, lock, `Conversation`, and table of node classes; the
imported modules — the node classes themselves, and any module-level state
a plugin keeps — are the process's, shared by every conversation in it.

What a conversation is given — the list is MODULE_STRUCTURE §4.1's —
is the `Conversation`, held by the forest's root, which a node reaches as
`forest().conversation` (MODULE_STRUCTURE §4.1); a compile builds one too,
with everything a conversation's startup builds before its server (§4,
COMPILATION.md §1).

**One client, its agents.** A conversation serves one Streamable HTTP
endpoint, `http://127.0.0.1:<port>/mcp`, on the loopback interface, to one
agent client process — Claude Code or Codex, chosen at launch — started
from the agent directory (§1); the process's main conversation and its
subagents are TAT's **agents**, each an `Agent` object holding its jobs,
its mailbox and its seen set (CONSTRUCT_INTERACTION §4). TAT tells them
apart because the client announces every tool call through a `PreToolUse`
hook before sending it, and ends the conversation on a call that was not
announced (CONSTRUCT_INTERACTION §8). Starting agents, their prompts, retries and
budgets, and what a subagent may do are the client's business; TAT reaches
into that only to hold an agent that would leave work behind and to refuse a
parent's interruption while any agent other than the caller and the main
conversation would be held so, or has a call still working
(CONSTRUCT_INTERACTION §7). Two
facts about the clients fix this shape. Codex starts a fresh stdio server
process for every subagent, so a stdio TAT would mean one Isabelle process
and one open database per subagent; hence HTTP. Both clients read their MCP
configuration once, when a session starts, so TAT is running before the
client is launched and writes the client's files first (`configure`,
CLIENT_HOOKS.md): the MCP entry with TAT's URL, the hooks, and the
tool-call limit of twelve hours — Claude Code's per-server `timeout`,
Codex's `tool_timeout_sec` — since an `evaluate_to` or a `check_construct`
can run long. The same files put the agents under the client's own
sandbox, in which their shell and file tools read and write the agent
directory and no other file of the user's, the rest of the working
directory included, short of the gaps listed at the end of
CLIENT_HOOKS.md §5: an agent works on the forest through TAT's tools, not
on its files.

**Launching.** The launcher is four Isabelle tools the component adds
(MODULE_STRUCTURE §5), the same in development and in production:
`isabelle TAT` creates the working directory when needed, starts a
conversation on it and starts the agent client in the agent directory;
`isabelle TAT_new` and `isabelle TAT_mcp` do the first two on their own,
for a client started by hand; `isabelle TAT_compile` compiles the forest
(§4):

```
isabelle TAT [-P PLUGIN]... [-c CLIENT] [-l BASE] [-p PORT] [-d DIR]... [-o OPTION]... WORKING_DIRECTORY [CLIENT_ARGS ...]
isabelle TAT_new [-P PLUGIN]... WORKING_DIRECTORY
isabelle TAT_mcp [-c CLIENT] [-l BASE] [-p PORT] [-d DIR]... [-o OPTION]... WORKING_DIRECTORY
isabelle TAT_compile [-l BASE] [-d DIR]... [-o OPTION]... WORKING_DIRECTORY
```

`TAT_new` creates the directory's database and records in it the plugins
the forest will use, each named by the theory that defines it,
`SESSION.THEORY`; on an existing directory it adds the plugins given and
changes nothing else; it writes no client files. The record is names
only, so a working directory opens on any host on which those plugins'
Isabelle sessions are declared, by a registered component or by a ROOT
under a `-d` given at each launch. `TAT` and `TAT_mcp` choose the agent
client with `-c CLIENT` (`claude-code`, the default, or `codex`) and pass the name
on to the Python side, which writes the client's files into the agent
directory (`configure`; CONSTRUCT_INTERACTION §8, CLIENT_HOOKS.md,
MODULE_STRUCTURE §4.6) and, once a client connects, reads the version
its MCP `initialize` states and refuses the session when it is lower
than the one TAT's client facts were measured on (CONSTRUCT_INTERACTION
§8); `TAT_mcp` starts
the Isabelle process on the base heap `BASE` (§8; the default is
Isabelle's `ISABELLE_LOGIC`; a base heap that is missing or outdated is
built first), loads TAT's theory and the recorded plugins' theories into
it from source, and calls `TAT_Framework.start` with those theories, the
working directory, the port and the client's name; the port is one the
system assigns unless `-p` fixes one, and one that
cannot be bound is a `TAT_StartupError` (MODULE_STRUCTURE §4.6). The call
does not return, so the Isabelle process lives as long as the
conversation; how it ends decides the launcher's exit code (MODULE_STRUCTURE
§5). `TAT_compile` starts the Isabelle process as `TAT_mcp` does, to load the
plugins, and calls the Python procedure `compile_TAT`, which returns; the
tool prints the compile's report and exits `0` when every tree was
written, `1` when the compile completed with some tree unwritten, `2` when
it did not complete, and every end of `TAT_mcp` and `TAT_compile` that is
not a normal return exits `2`, but for Isabelle's own `130`
(MODULE_STRUCTURE §5, COMPILATION.md §2, §5). The conversation's
lifetime: under `isabelle TAT` the client's exit ends the conversation,
and a conversation that ends first ends the client; under `TAT_mcp`
alone the conversation ends with its process, nothing ties that process
to the client's, and whoever started `TAT_mcp` ends it when the client
ends. When the Isabelle process stops first, the conversation ends with
it — its ending running only under an RPC host started elsewhere, the
host Isabelle started exiting with it (MODULE_STRUCTURE §4.6). Either order
of the two processes
works: Isabelle first, which opens an RPC host of its own, or a Python RPC
host first, on an address the environment variable `RPC_Host` hands to the
Isabelle process started next (`contrib/Isabelle_RPC`); the launcher does
nothing for either.

**Concurrency.** The calls that hold the forest's lock — `edit`, `move`,
`delete` and `evaluate_to` — hold it across the whole call
(MODULE_STRUCTURE §4.2), so they serialise: a parent and its subagents run
at once, and one client may send several calls at once, but while one
`evaluate_to` runs the other edits wait, as in AoA. `recall`, the future
`query`, and the four construct tools — `construct`, `cancel_construct`,
`check_construct`, `answer` — take no lock: the readers read the forest in
memory as it stands and answer meanwhile (MCP_SPECIFICATION §5), and each
construct tool is synchronous from its checks to its change
(CONSTRUCT_INTERACTION §9), so several calls are working at once. A tool
call is cancelled only by the conversation's ending (MODULE_STRUCTURE
§4.6): a client that gives up on a call loses its answer, and the call
finishes and releases what it holds; the ending cancels every working call
and answers it (MODULE_STRUCTURE §4.6). Evaluation is a synchronous loop
(§3.6), driven through that one call's callbacks; the framework's other
concurrent activity is the jobs (§3.6, CONSTRUCT_INTERACTION §3): a
construction job's run is a task spawned through the conversation's ending
object, an evaluation job's work a Future task on the ML side that reports back, and a
job's settlement — a run's end, a report — and a job's drop are each one
synchronous step under no lock, atomic against every call on the one
event loop. Under `checks: "blocking"` an `evaluate_to` keeps the lock
after its walk until every evaluation job running on a node it passed
has ended. The ending cancels every construction job and drops every
evaluation job. `Proof_Obligation`'s construction job drives AoA through its ML
callback on the state its evaluation recorded (node_classes/COMMON.md §3).

What the framework contributes to such work is thread safety where it can
reach shared state: the state slot table and the theory table are locked,
and the tools a proof search reaches — AoA's proof store and
`auto_sledgehammer`'s cache — are thread-safe; a proof check's work reads
its input slot's state once, at its fork. Evaluating several trees at once
is not designed for; it would be a change on the ML side — the loader's
conditions (EVALUATOR_DESIGN §6) and the one-operation-per-round-trip
cadence (MODULE_STRUCTURE §4.1) — not to this shape.

## 10. Directory and module structure

In [MODULE_STRUCTURE.md](MODULE_STRUCTURE.md).
