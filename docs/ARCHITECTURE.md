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
| **segment** | one Isabelle span in an emitted file |
| **state slot** | a name standing for one `Toplevel.state` held on the Isabelle side |
| **state slot table** | the Isabelle-side map from state slot names to their `Toplevel.state` values, one per conversation (EVALUATOR_DESIGN §1.1) |
| **base heap** | the heap TAT's prover runs on, chosen by the client, with nothing of TAT in it (§8) |
| **tree order** | depth-first, a node before its children, children in their own order |
| **evaluate** | running a node's commands in Isabelle and recording what happened (§3) |
| **emit** | a node writing its own Isar text (§4) |
| **compile** | turning the forest into `.thy` files and a ROOT on disk (§4) |
| **conversation** | one run of TAT, from Isabelle's call into Python to its return (§9) |
| **forest directory** | the directory the client names when saving or loading; the ROOT and every `Session`'s directory lie under it (§4) |
| **edit** | any change to the forest — the `edit`, `move` and `delete` tools all make edits; the tool named `edit` (MCP_SPECIFICATION §1) is the narrow sense |
| **Location** | a position in the forest: on the wire, the destination forms of `edit` and `move` (TOOL_SCHEMAS.md); resolved by the framework to a parent and an index within its children, which is what the move hooks receive (MODULE_STRUCTURE §4.1) |

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

Initial node classes: `Session`, `Theory`, `Theorem`, `Define`, `Datatype`, `QuotientType`,
`Record`, `TypeClass`, `Text`, `Section`, `Context`, `Locale`. New node classes must be
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
unspecified (OPEN_QUESTIONS §2).

### 2.1 The trees are pure declarations *(decided)*

No proof structure enters a tree. Every proof is emitted as the `AoA` proof
method, which runs Sledgehammer first and falls back to the AoA proof agent
when it times out; while a node has no proof it emits `sorry` instead (§2.2). A
`Theorem` node carries what is claimed, never how it is established: no proof
attribute, no proof text, no proof subtree.

Throughout this repository, `AoA` in code font is that proof method. AoA in
plain text is the agent system the method falls back to.

### 2.2 Node classes *(decided)*

**`Theorem`**

| Attribute | Type | |
| --- | --- | --- |
| `kind` | `lemma` \| `corollary` \| `theorem` | authored |
| `statement` | AoA's Long statement (`contrib/Isa-Mini/IsaMini/AoA/model.py`, `class LongStatement`) | authored |
| `proof` | `not_started` \| `working` \| `proven` \| `failed` | recorded |

`proof` is the state of the search, not a proof: a tree holds no proof (§2.1).
Adding a `Theorem` may start the search at once, but the default is
`not_started`, so laying out a theory costs nothing. `construct` starts it.

A node whose `proof` is not `proven` emits **`sorry`**, and its evaluator runs
`sorry` in the same case (§3.6). A failing proof would mean the fact is never
added, so every later node using it fails too — a skeleton of twenty lemmas
would check none of them past the first. With `sorry` the fact is admitted, the
whole tree's structure and types are checked, and the agent constructs proofs
afterwards.

This is honest only because `proof` is tracked: such a node evaluates without
error and is still not `finished` (§3.2), so TAT never mistakes an admitted fact
for a proved one.

**`Define`**

| Attribute | Type | |
| --- | --- | --- |
| `auto_reduction` | `bool` | authored |
| `equations` | the defining equations | authored |
| `form` | `definition` \| `fun` \| `function` | recorded |

With `auto_reduction` true the resulting definitional equations carry
`[simp]`; with it false they are removed again with
`note f.simps[simp del]`. A single equation is a
`definition`; several are a `fun`, or a `function` with its proof obligations
discharged by `AoA` when `fun` cannot establish termination on its own. Which of
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

`Datatype`, `QuotientType`, `Record`, `TypeClass`, `Text`, `Section`, `Context`
and `Locale` are unspecified (OPEN_QUESTIONS §2).

## 3. Evaluation *(decided)*

Evaluating a node means handing its data to its node class's evaluator on the
Isabelle side, which runs the node's commands and reports what the class
decides to report. Nothing is checked unless TAT asks for it, because TAT
submits the commands.

### 3.1 State slots

Every node owns one **state slot**: a name standing for the `Toplevel.state` the
node starts from. The name belongs to the node for as long as the node exists,
and re-evaluating the node writes that same name again. The Python side never
holds a state, only a name.

A node's resulting state is the slot of its next sibling, or, for a last child,
the slot its parent keeps for the position after all its children. The
resulting slot of one node and the input slot of the next are therefore the
same slot, and re-evaluating a node writes into slots that already exist.

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

Every operation a node runs has an `evaluation_status`, which says whether
evaluation passes through it. A leaf has one operation; a nesting node has two,
its beginning and its ending, and so two statuses.

| value | meaning |
| --- | --- |
| `not_evaluated` | no current result; nothing in the resulting slot to rely on |
| `ready` | the operation ran and its resulting slot is current |
| `cannot_evaluate` | evaluation does not pass through (§3.3) |

A node whose own commands failed is still `ready` when its class can carry on
regardless. A `Theorem` whose proof failed emits `sorry`, so the fact is declared
and every later node still checks. A nesting node whose beginning command
failed has that beginning `cannot_evaluate` and its ending `ready` without
running: the framework copies the node's own input state straight into its
resulting slot, and evaluation resumes after the block. (An ending is
`cannot_evaluate` in a different situation: the beginning succeeded and a
child then stopped — §3.5.)

No node class reads another node's statuses: a node renders its own report,
and the one question a class asks of another node is `finished`. The
framework's walk does read them — that is how it knows what to run (§3.5).

`finished` says whether the node still owes anything. It is derived, never
stored, so it cannot drift from what it is derived from.

| node class | `finished` when |
| --- | --- |
| `Theorem` | `proof` is `proven` |
| `Define` | every command it emitted succeeded |
| a nesting class (`Theory`, `Section`, `Locale`, `Context`) | its own commands succeeded and every child is `finished` |
| `Session` | every tree under it is `finished`; it runs no operation and has no `evaluation_status` of its own |
| a class with nothing to discharge | it has been evaluated |

`finished` is true only where `evaluation_status` is `ready`. A forest is
complete when every node is `finished`, and only `finished` answers that
question: a `Theorem` that emitted `sorry` ran a command that succeeded.

### 3.3 Where evaluation stops

A `cannot_evaluate` node is either the obstacle itself or sits after or under
one, and records which: its `blocked_by` is empty in the first case and names
the obstacle in the second.

A node whose failure would make everything after it report **derived errors**
is an obstacle by the judgement of its node class. `Define` is the case: when
the defining command fails the constant does not exist, so every later node that
mentions it fails with a message about the constant instead of about itself. A
nesting node whose ending command failed is one too: a `Theory` whose `end`
failed has no theory value. Such a node **stops** evaluation: everything after
it in the tree is `cannot_evaluate` with that node as `blocked_by`.

A **nesting node whose beginning command failed** leaves its children no context
to run in. Its beginning is `cannot_evaluate` and, like any obstacle, is not
rerun until edited; its ending is `ready` (§3.2); every node under it is
`cannot_evaluate` with that ancestor as `blocked_by`, and none of them runs
while the ancestor stays as it is. This is not a stop: evaluation resumes after
the block.

`evaluate_to` takes an `ignore_error` flag for an agent that wants to see every
error in one pass. With it set the walk carries on past a stop; a failed
beginning is not passed — its children stay blocked (§3.3). The call then
returns "continue", each error showing at its own node.

A stop is a fact about the forest, not about one call. Every `evaluate_to`
returns either "continue" or "stopped at node X" to its caller (§3.5), and an
obstacle returns "stopped" whenever it is passed — including on a later call
that finds it already evaluated and skips it — unless `ignore_error` is set. So
every call stops at the same node until that node is edited. A node blocked by
an obstacle, on the other hand, runs as soon as a call reaches it unblocked. A
node that is both — its own obstacle, and after another — keeps reporting
itself: a blocked status never overwrites an own stop, so it is neither rerun
nor misreported — until a walk rewrites the state under it, by rerunning a
predecessor that had been blocked; then it runs again, on its new input.

### 3.4 Invalidation

Invalidating a node marks it and every node after it in its tree
`not_evaluated`, and marks every tree that transitively imports that tree
`not_evaluated` in whole. A tree's states are built on the theory values of the
trees it imports, so a change anywhere in an imported tree invalidates all of an
importing one.

Editing a `Session` invalidates every tree under it — their qualified names
carry its `name` — and, through the same rule, every tree that imports them.

Whatever an operation wrote is released when the operation stops being
current — its result, or the input it copied through on failing; the names
stay with the node and re-evaluation writes them again. A call collects what
it releases and deletes it all in one round trip at its end. Deleting a node
releases every state its subtree owns and cancels any work in flight on it.

Inserting or deleting a node changes which slot its predecessor's resulting
state is (§3.1), so the value moves with it when the predecessor has written
one: on insertion the slot formerly at that position is copied into the new
node's; on deletion the deleted node's slot is copied into the one now at its
position. When the predecessor has written nothing, nothing is copied — and
on deletion the slot at that position is released if the deleted node had
written it, since its writer is gone. The predecessor is not touched.

Because invalidation always runs forward, a tree's evaluated nodes are a prefix
of it in tree order. TAT keeps no separate record of how far evaluation has
reached: the recursion of §3.5 skips what is evaluated and runs what is not.

### 3.5 Running an evaluation

`evaluate_to(destination, ignore_error, evaluate)` — the internal form; the
tool omits `evaluate` (MCP_SPECIFICATION §4) — runs every `not_evaluated`
node up to and including the destination, in tree order — a
`cannot_evaluate` obstacle is not rerun; it reports its stop again (§3.3) —
and invalidates everything after the destination in its tree (§3.4). It is
one recursion, called from the top of the forest under the forest's one
lock, so two calls never interleave:

- The **forest** resolves the destination's id and works on the theories
  directly — evaluation is transparent to the `Session` layer: it builds the
  import dependency graph over the trees, evaluates every tree the
  destination's tree transitively imports to its own `end` — a theory value
  exists only once its theory is closed — in dependency order, then calls the
  destination's tree. A `Session` as destination stands for all the trees
  under it: the forest schedules each of them, to its `end`, through the same
  graph.
- A **nesting node** runs its beginning command if it is not evaluated. If that
  command succeeded, now or earlier, it calls its children in order, and
  those after the one that contains the destination only to invalidate them;
  if it failed, it still enters them, but to mark each one `cannot_evaluate`
  (§3.3) rather than to run it. A nesting node is reached at its ending
  command: it is the destination only once its children have run, so naming a
  `Theory` means the whole tree, `end` included.
- A **leaf** runs its commands if it is not evaluated, and otherwise runs
  nothing.

The recursion visits every node of the tree. Past the destination it evaluates
nothing and marks each node `not_evaluated` (§3.4). That is what makes an edit
reach everything after the edited node; on a call from the agent it changes
nothing, since those nodes are `not_evaluated` already. Nothing is skipped on
the way: a `ready` operation is not rerun, but a nesting node whose ending
is `ready` is still entered, since an obstacle passed under `ignore_error`
may sit inside it.

Without `evaluate` the same walk touches nothing before the destination, not
even a node that is not `ready`, and invalidates from the destination on. Its
destination is then a position — a parent and an index among its children —
reached before whatever stands there, so a nesting node at that position is
invalidated whole, opening first; the index after the last child names the
parent's ending. That is what a deletion needs (§3.4): nothing new to run,
only the successor and what follows to invalidate.

Every call returns "continue" or "stopped at node X" (§3.3); after a stop the
recursion goes on, marking what follows `cannot_evaluate` with X as
`blocked_by`, and the answer travels up to the forest.

Editing a node marks it `not_evaluated` and invalidates everything after it
through this walk — run without `evaluate` when the editing call's
`evaluate` flag is false, and as part of the full evaluation when it is true
(MCP_SPECIFICATION §3.2). Editing a nesting node's own commands first
invalidates from its first child, since the children are before it in the
walk and would otherwise be kept.

### 3.6 Work that outlives a call

Evaluation is synchronous: a loop that submits one command and waits. It never
searches for a proof, and never runs `by AoA`, which exists only in emitted
files (§2.1). `Theorem`'s evaluator runs the statement alone, then either `sorry`
or `by` applied to the proof `construct` stored on the node — the method text
AoA writes to its proof store, such as `(simp add: …)` or `aoa_replay "…"` —
which the node passes along with the statement. The one asynchronous activity,
and the only thing that starts a search, is `construct`; a `Theorem` whose
search is running has `proof = working`.

A node class that starts such work decides for itself what happens when its
context is invalidated under it. This adds no framework machinery: invalidation
and evaluation are already the two moments the framework calls into a node
class, so the class is told at invalidation that its context is no longer
current, and is given the new one at evaluation. What `Theorem` does with that is open
(OPEN_QUESTIONS §4).

## 4. Compilation *(decided)*

TAT is the compiler and owns the `.thy` files. Isabelle never reads them;
every change reaches Isabelle by evaluation (§3), and the files exist for
whoever builds the forest afterwards.

Compilation writes under one directory, the **forest directory**, which the
client names when saving or loading: at its top a ROOT holding every
`Session`'s entry, and under each `Session`'s `directory` its trees' `.thy`
files. The forest stores no absolute path — `directory` is relative to the
forest directory — so a forest moves machines by being handed another one.

A node writes its own text through `emit_isar(indent, out)`, which writes to
`out` and returns the indent in effect after it. The `indent` passed in is a
proposal; a node class that opens or closes an Isabelle block returns the value
it actually leaves behind. Emission runs after evaluation, so it renders
decisions already made rather than proposing any.

Each node class decides when it will emit. `Theorem` emits whenever the node is
`ready`, using `sorry` for a proof it does not have. `Define` will not emit at
all when its defining command failed, since no text would compile. A tree is
written only when every node in it agrees to emit: a `.thy` with a hole is not a
theory.

### 4.1 Persistence

The `.thy` files are not the forest: what a node records is not in them. The
forest itself is saved with `pickle`, and each node class decides through
`__getstate__` what of its node is saved. State slot names are not: the state slot table does not outlive the
conversation (EVALUATOR_DESIGN §1.1), so a loaded forest is `not_evaluated`
throughout and its slots are assigned afresh. The connection to Isabelle is
not saved either; the conversation hands the loaded forest its current one. Work in
flight is not saved, only its results.

## 5. Segments *(decided)*

A segment is exactly one Isabelle span, mirroring Isabelle's own partition of a
theory file (`contrib/Isabelle2025-2/src/Pure/PIDE/command_span.ML:35`, where the
three kinds of span are `Command_Span`, `Ignored_Span` and `Malformed_Span`).
That partition is total — whitespace and comments are spans, not gaps.

| segment kind | Isabelle's term | owner |
| --- | --- | --- |
| command | `Command_Span` | a node |
| layout (blank lines, separator comments) | `Ignored_Span` | none |
| structural (`theory X imports … begin`, `end`) | `Command_Span` | the root node |

A node may own several segments. No segment is owned by more than one node
(§7).

The finished `.thy` is parsed as a whole by whoever builds it, so each node's
text must be self-delimiting. No separate check enforces this: text that does
not close — an unclosed cartouche, comment or quote — fails at its own node's
evaluation (§7), and a node whose commands failed does not emit (§4), so such
text never reaches a file.

## 6. The node class contract *(decided)*

A node class is delivered as an Isabelle theory together with a Python package.
The theory is primary: it registers the class's evaluator on the ML side —
into its own theory data (MODULE_STRUCTURE §2.5) — and the registration names
the Python packages carrying the rest, which the conversation collects and
hands to `plugin.py` to import (MODULE_STRUCTURE §2.6, §4.3). Installing a
node class means having the theory the conversation starts from import it;
the conversation loads it from source at start (§8).

| part | side | |
| --- | --- | --- |
| data definition and argument schema | Python | becomes the MCP tool schema |
| emission | Python | `emit_isar`, run after evaluation |
| constructor | Python | the `construct` operation, for classes that have one |
| evaluator | ML | runs the node's commands, reports what it decided |

`construct` is Python because what it drives is: on a `Theorem` it runs the AoA
proof agent, which is a Python program, and the running search hangs on the
Python node (§3.6).

### 6.1 Two kinds of field

A node's fields are either **authored** — supplied by the agent, part of the
node's identity, untouched by evaluation — or **recorded** — produced by
evaluation. `Define`'s equations are authored; the `form` chosen for them is
recorded. A recorded field is only as current as the evaluation that produced it,
and emission's gate on `evaluation_status` is what keeps a stale one out of a
file.

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
— and answers the framework with one boolean: whether evaluation passes
through the node (§3.2). On no, the framework copies the operation's input
state into its resulting state, so that `ignore_error` has something to run
from; no class writes that copy.

A class's callback is a local callback of the conversation's one RPC command
(§9, MODULE_STRUCTURE §2.6), named after the class that owns it.

### 6.3 Two kinds of ML

The framework and the evaluators are needed only by TAT's own process. Generated
theories never name them, so they are loaded into that process at start (§8)
and appear in no tree's imports.

Anything the generated text does name — the `AoA` proof method, any syntax or
attribute a node emits — must be imported by the trees that use it, and is a
real dependency of the finished forest.

The concrete interfaces are MODULE_STRUCTURE §2.5 and §4.1.

## 7. Command-to-node mapping *(decided)*

The evaluator runs one node's commands at a time and reports their results to
that node. The mapping is given, not reconstructed: there is no line-span table,
and no question of whether our partition of a file agrees with Isabelle's.

A node emitting text that does not close cannot reach the next node's commands,
because those have not been submitted yet. It fails at its own parse.

## 8. Substrate *(decided)*

TAT drives Isabelle itself, through its own evaluator written in Isabelle/ML.
The evaluator holds an explicit `Toplevel.state` and runs one command at a time
through `Toplevel.command_errors`, which recovers from a failing command instead
of re-raising. Design in [EVALUATOR_DESIGN.md](EVALUATOR_DESIGN.md).

The prover runs on one **base heap** — launched and chosen by the client
(§9), with nothing of TAT in it — and the forest sits on top of it, no tree
in any heap
(EVALUATOR_DESIGN §2). A `Session`'s `parent` is ROOT metadata, not a
constraint on the heap: a library theory the base heap lacks is loaded from
source. TAT's own theories
(§6.3) are never in the base heap: the conversation loads them from source
when it starts, which is quick because they are small. The same goes for
`Isabelle_RPC`'s theory, which they import, when the base heap lacks it.

No node class emits `oops`: it leaves no trace in Isabelle's output and so
could not be accounted for.

## 9. The two processes and the channel *(decided)*

TAT is a Python process and an Isabelle process. The Python side owns the forest,
serves the MCP tools and writes the `.thy` files. The Isabelle side runs the
evaluators.

Isabelle opens the connection. An ML entry calls a Python procedure over
`contrib/Isabelle_RPC` and does not return for the life of the conversation;
Python drives Isabelle through that call's callbacks. AoA is built the same way
(`contrib/Isa-Mini/IsaMini/AoA/toplevel.py:164`).

The framework starts, schedules and tracks no concurrent activity: evaluation
is a synchronous loop (§3.6), driven through that one call's callbacks. The one
asynchronous activity, `construct` (§3.6), is a node class's own affair: the
class arranges it and the running work hangs on its node. How `Theorem`'s
`construct` drives AoA is designed with its Python half (MODULE_STRUCTURE
§4.4), on AoA's own precedent.

What the framework contributes to such work is thread safety where it can
reach shared state: the state slot table and the theory table are locked, and
the tools a proof search reaches — AoA's proof store and `auto_sledgehammer`'s
cache — are thread-safe.

TAT is a library; whatever starts a conversation is a client of it, and the
production client is undecided (OPEN_QUESTIONS §6). During development an
Isa-REPL app is the client, registered from a theory nothing shipped imports
(`Dev/TAT_Dev.thy`), so Isa-REPL is a development dependency and never a
shipped one.

## 10. Directory and module structure

In [MODULE_STRUCTURE.md](MODULE_STRUCTURE.md).
