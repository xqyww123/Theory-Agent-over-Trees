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
| **forest** | all working theories, as a set of trees |
| **tree** | one Isabelle theory; the root's name is the short name of the theory |
| **node** | one semantic unit in a tree |
| **node class** | the kind of a node — `Theorem`, `Define`, … — extensible |
| **segment** | one Isabelle span in an emitted file |
| **state slot** | a name standing for one `Toplevel.state` held on the Isabelle side |
| **state slot table** | the Isabelle-side map from state slot names to their `Toplevel.state` values, one per session (EVALUATOR_DESIGN §1.1) |
| **base heap** | the heap TAT's prover runs on: that of the Isabelle session the forest is written against, with nothing of TAT in it (§8) |
| **tree order** | depth-first, a node before its children, children in their own order |
| **evaluate** | running a node's commands in Isabelle and recording what happened (§3) |
| **emit** | a node writing its own Isar text (§4) |
| **compile** | turning trees into `.thy` files on disk |
| **session** | one run of TAT, from Isabelle's call into Python to its return (§9); Isabelle's build unit is always written **Isabelle session** |

Two relations are easy to confuse, so neither is called an edge. **Import
dependency** holds between trees, and is what the tree roots declare in their
`imports` clauses. **Nesting** holds between nodes inside one tree.

`node` in this repository always means a node of a TAT tree. Isabelle's own
document model (PIDE, its interactive document layer) also calls a theory file
a node; where that meaning is intended it is written **PIDE document node** in
full.

## 2. The model *(decided)*

A tree is one theory. Import dependency between trees makes the forest a
dependency graph, and compilation order is a topological order over it.

Initial node classes: `Theorem`, `Define`, `Datatype`, `QuotientType`, `Record`,
`TypeClass`, `Text`, `Section`, `Context`, `Locale`. New node classes must be
addable without touching the core. Every tree's root is a `Theory` node, which
owns the theory header, the `imports` list and the closing `end`.

Each node class corresponds to one or more Isabelle commands.

TAT writes only theories it authored; reading in a foreign `.thy` is out of
scope.

### 2.0 Nesting *(decided)*

A node either contains other nodes or does not.

`Theorem` is a leaf.

`Section` contains the declarations under its heading. It is **presentational
only**: it emits a `section` command and creates no Isabelle scope, so it changes
nothing about how its children are checked or named. It is a nesting node with an
opening command and no closing one.

`Context` and `Locale` also contain nodes, and unlike `Section` they carry
**operational behaviour**: they open an Isabelle context, so their children are
checked inside it and the facts they declare are qualified by it. Both are
unspecified — see OPEN_QUESTIONS.

### 2.1 The trees are pure declarations *(decided)*

No proof structure enters a tree. Every proof is emitted as the `AoA` proof
method, which runs a hammer first and falls back to the AoA proof agent when the
hammer times out; while a node has no proof it emits `sorry` instead (§2.2). A
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
| `kind` | `opaque` \| `auto-simp` | authored |
| `equations` | the defining equations | authored |
| `form` | `definition` \| `fun` \| `function` | recorded |

`auto-simp` adds `[simp]` to the resulting definitional equations; `opaque`
removes them again with `note f.simps[simp del]`. A single equation is a
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
| `simp-del` | `note f.simps[simp del]` | `kind = opaque` |

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

A nesting node's opening command writes its first child's slot. After the last
child, the nesting node's closing command reads the slot it keeps for the
position after all its children and writes its own resulting slot; a class
with no closing command, such as `Section`, copies the one into the other.

A node that fails and is passed over leaves its input state in its resulting
slot unchanged, so whatever follows always has something to run from.

### 3.2 Two fields

`evaluation_status` says whether evaluation can pass through the node.

| value | meaning |
| --- | --- |
| `not_evaluated` | no current result; nothing in the resulting slot to rely on |
| `ready` | the node ran and its resulting slot is current |
| `cannot_evaluate` | evaluation does not pass through the node (§3.3) |

A node whose own commands failed is still `ready` when its class can carry on
regardless. A `Theorem` whose proof failed emits `sorry`, so the fact is declared
and every later node still checks. A nesting node whose opening command failed
is `ready` too: its input state stands as its result, and evaluation resumes
after the block.

`finished` says whether the node still owes anything. It is derived, never
stored, so it cannot drift from what it is derived from.

| node class | `finished` when |
| --- | --- |
| `Theorem` | `proof` is `proven` |
| `Define` | every command it emitted succeeded |
| a nesting class (`Section`, `Locale`, `Context`) | its own commands succeeded and every child is `finished` |
| a class with nothing to discharge | it has been evaluated |

`finished` is true only where `evaluation_status` is `ready`. A forest is
complete when every node is `finished`, and only `finished` answers that
question: a `Theorem` that emitted `sorry` ran a command that succeeded.

### 3.3 Where evaluation stops

`cannot_evaluate` has two sources.

A node whose failure would make everything after it report **derived errors**
stops evaluation by the judgement of its node class. `Define` is the case: when
the defining command fails the constant does not exist, so every later node that
mentions it fails with a message about the constant instead of about itself.

A **nesting node whose opening command failed** leaves its children no context
to run in. The nesting node itself is `ready` (§3.2); every node under it is
`cannot_evaluate`, recording that ancestor as the reason, and none of them
runs while the ancestor stays as it is. That is a fact about the state rather
than a policy — there is nothing to run them from.

`evaluate_to` takes an `ignore_error` flag for an agent that wants to see every
error in one pass. It passes the first kind and never the second, which is not
a stop at all: evaluation resumes after the block whether the flag is set or
not.

A stop is a fact about the forest, not about one call. Every `evaluate_to`
returns either "continue" or "stopped at node X" to its caller (§3.5), and a
node of the first kind returns "stopped" whenever it is passed — including on
a later call that finds it already evaluated and skips it — unless
`ignore_error` is set. So every call stops at the same node until that node is
edited.

A node left `not_evaluated` because evaluation stopped before reaching it
records which node stopped it, so it can say why rather than only that it did
not run.

### 3.4 Invalidation

Invalidation happens entirely on the Python side and sends nothing to Isabelle.

Invalidating a node marks it and every node after it in its tree
`not_evaluated`, and marks every tree that transitively imports that tree
`not_evaluated` in whole. A tree's states are built on the theory values of the
trees it imports, so a change anywhere in an imported tree invalidates all of an
importing one.

State slots are not released. The name belongs to the node and re-evaluation
overwrites it, so nothing accumulates. Deleting a node releases its slot and
cancels any work in flight on it.

Because invalidation always runs forward, a tree's evaluated nodes are a prefix
of it in tree order. TAT keeps no separate record of how far evaluation has
reached: the recursion of §3.5 skips what is evaluated and runs what is not.

### 3.5 Running an evaluation

`evaluate_to(destination, ignore_error)` evaluates every `not_evaluated` node up
to and including the destination, in tree order. It is one method, defined on
every node and called recursively from the top:

- The **forest** resolves the destination's id, evaluates every tree the
  destination's tree transitively imports to its own `end` — a theory value
  exists only once its theory is closed — in dependency order, then calls the
  destination's tree.
- A **nesting node** runs its opening command if it is not evaluated. If that
  command succeeded, now or earlier, it calls its children in order, and
  those after the one that contains the destination only to invalidate them;
  if it failed, it still enters them, but to mark each one `cannot_evaluate`
  (§3.3) rather than to run it. A `Theory` runs its `end` only when the
  destination is the `Theory` node itself, or when the forest is evaluating
  the tree as an import.
- A **leaf** runs its commands if it is not evaluated, and otherwise runs
  nothing.

The recursion visits every node of the tree. Past the destination it evaluates
nothing and marks each node `not_evaluated` (§3.4). That is what makes an edit
reach everything after the edited node; on a call from the agent it changes
nothing, since those nodes are `not_evaluated` already. A destination that is
already evaluated ends the call at once: everything before it is evaluated
too, and nothing after it is touched.

Every call returns "continue" or "stopped at node X" (§3.3); a nesting node
that receives "stopped" from a child evaluates no further child, and the
answer travels up to the forest.

Editing a node marks it `not_evaluated` and runs `evaluate_to` on it, so the
result of what was just written comes back with the call and everything after
it is invalidated on the way.

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
(OPEN_QUESTIONS §5).

## 4. Compilation *(decided)*

TAT is the compiler and owns the `.thy` files. Isabelle never reads them; every change reaches Isabelle by
evaluation (§3), and the files exist for whoever builds the forest afterwards.

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
forest itself is saved with
`pickle`, and each node class decides through `__getstate__` what of its node
is saved. State slot names are not: the state slot table does not outlive the
session (EVALUATOR_DESIGN §1.1), so a loaded forest is `not_evaluated`
throughout and its slots are assigned afresh. The connection to Isabelle is
not saved either; the session hands the loaded forest its current one. Work in
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
text must be self-delimiting. Cartouches, comments and quotes are balanced
before a node's text is accepted. See
[appendix/SEGMENT_INTEGRITY.md](appendix/SEGMENT_INTEGRITY.md).

## 6. The node class contract *(decided)*

A node class is delivered as an Isabelle theory together with a Python package.
The theory is primary: it registers the class's evaluator on the ML side, and it
names the Python package carrying the rest. Installing a node class means
naming its theory to the session, which loads it from source at start (§8).

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

The framework fixes the envelope and leaves the contents free.

- Fixed: the input state slot, the resulting state slot, and the outcome that
  becomes `evaluation_status`.
- Free: how the class packs its own data, and whatever it wants recorded —
  which commands it ran and how each of them fared included.

The framework supplies the unpacker that turns a state slot name into a
`Toplevel.state`, and the packer for the envelope, so no class writes either
twice.

A class's callback is a local callback of the session's one RPC command (§9,
MODULE_STRUCTURE §2.5), named after the class that owns it.

### 6.3 Two kinds of ML

The framework and the evaluators are needed only by TAT's own process. Generated
theories never name them, so they are loaded into that process at start (§8)
and appear in no tree's imports.

Anything the generated text does name — the `AoA` proof method, any syntax or
attribute a node emits — must be imported by the trees that use it, and is a
real dependency of the finished forest.

The concrete interfaces are unwritten (OPEN_QUESTIONS §1).

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

TAT launches the prover on one **base heap** — that of the Isabelle session the forest
is written against, with nothing of TAT in it — and the forest sits on top of
it, no tree in any heap (EVALUATOR_DESIGN §2). A library theory the base heap
lacks is loaded from source, at a cost the loader reports. TAT's own theories
(§6.3) are never in the base heap: the session loads them from source when it
starts, which is quick because they are small. The same goes for
`Isabelle_RPC`'s theory, which they import, when the base heap lacks it.

No node class emits `oops`: it leaves no trace in Isabelle's output and so
could not be accounted for.

## 9. The two processes and the channel *(decided)*

TAT is a Python process and an Isabelle process. The Python side owns the forest,
serves the MCP tools and writes the `.thy` files. The Isabelle side runs the
evaluators.

Isabelle opens the connection. An ML entry calls a Python procedure over
`contrib/Isabelle_RPC` and does not return for the life of the session; Python
drives Isabelle through that call's callbacks. AoA is built the same way
(`contrib/Isa-Mini/IsaMini/AoA/toplevel.py:164`).

Callbacks travel on the connection their outer call arrived on, and the protocol
carries no request identifiers, so one connection carries one chain of work. Two
chains that run at the same time therefore need one outer call each;
`Isabelle_RPC`'s connection pool
(`contrib/Isabelle_RPC/Tools/RPC.ML:864-895`) gives every call its own
connection. A callback exists for Python to ask Isabelle to open another, which
is what running a `construct` alongside evaluation needs.

Concurrent chains share the state slot table, so that table is locked. The
other state they share is inside tools that a proof search reaches — AoA's proof
store and `auto_sledgehammer`'s cache — and those are thread-safe.

The entry point that starts a session in production is undecided
(OPEN_QUESTIONS §7). During
development an Isa-REPL app starts it, registered from a theory that the
production build does not import, so Isa-REPL is a development dependency and
never a shipped one.

## 10. Directory and module structure

In [MODULE_STRUCTURE.md](MODULE_STRUCTURE.md).
