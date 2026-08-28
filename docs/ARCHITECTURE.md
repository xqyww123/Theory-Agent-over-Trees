# TAT Architecture

Status: design draft.

Section markers, and there are only three:

- ***(decided)*** — settled. A decided section may not rest on an open one.
- ***(open)*** — an active question, named in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).
- unmarked — provisional. Written down to fix the shape, not yet agreed.

## 1. Glossary *(decided)*

These terms are fixed. Use them and no synonyms.

| Term | Meaning |
| --- | --- |
| **forest** | all working theories, as a set of trees |
| **tree** | one Isabelle theory; the root's name is the short name of the theory |
| **node** | one semantic unit in a tree |
| **node class** | the kind of a node — `Theorem`, `Define`, … — extensible |
| **role** | tag distinguishing the several commands one node emits |
| **segment** | one Isabelle span in an emitted file |
| **state slot** | a name standing for one `Toplevel.state` held on the Isabelle side |
| **tree order** | depth-first, a node before its children, children in their own order |
| **compile** | turning trees into `.thy` files on disk |

Two relations are easy to confuse, so neither is called an edge. **Import
dependency** holds between trees, and is what the tree roots declare in their
`imports` clauses. **Nesting** holds between nodes inside one tree.

`node` in this repository always means a node of a TAT tree. Isabelle's own
document model also calls a theory file a node; where that meaning is intended
it is written **PIDE document node** in full.

## 2. The model *(decided)*

A tree is one theory. Import dependency between trees makes the forest a
dependency graph, and compilation order is a topological order over it.

Initial node classes: `Theorem`, `Define`, `Datatype`, `QuotientType`, `Record`,
`TypeClass`, `Text`, `Section`, `Context`, `Locale`. New node classes must be
addable without touching the core.

Each node class corresponds to one or more Isabelle commands.

TAT writes theories it authored. Taking over a `.thy` file it did not write is
out of scope for now and may be supported later. The one place that would lose
information is `Theorem`'s `statement`, which is a structured value rather than
the surface text; section headings, theorem names and constant names are all
recoverable from a file.

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
hammer times out. A `Theorem` node carries what is claimed, never how it is
established: no proof attribute, no proof text, no proof subtree.

Throughout this repository, `AoA` in code font is that proof method. AoA in
plain text is the agent system the method falls back to.

TAT therefore has one execution model and no agent-written proof text.

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

A node whose `proof` is not `proven` emits **`sorry`**. Emitting `by AoA` with
nothing in the cache would fail, and a failing `by` means the fact is never
added, so every later node using it fails too — a skeleton of twenty lemmas
would check none of them past the first. With `sorry` the fact is admitted, the
whole tree's structure and types are checked, and the agent constructs proofs
afterwards.

This is honest only because `proof` is tracked. TAT reports the tree as clean
*and* names the nodes that are not proved; it is not claiming they are.

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

`Define` is the motivating case for **role**: one node, several commands, each
able to fail on its own.

| role | emitted | when |
| --- | --- | --- |
| `function` | the defining command, in whichever `form` | always |
| `pat-completeness` | the completeness proof | `form = function` |
| `termination` | `termination by …` | `form = function` |
| `simp-del` | `note f.simps[simp del]` | `kind = opaque` |

"The definition is wrong" and "the definition is fine but termination failed" are
different reports.

`Datatype`, `QuotientType`, `Record`, `TypeClass`, `Text` and `Section` are
unspecified.

## 3. Evaluation *(decided)*

Evaluating a node means handing its data to its node class's evaluator on the
Isabelle side, which runs the node's commands and reports the result of each
role. Nothing is checked unless TAT asks for it, because TAT submits the
commands.

### 3.1 State slots

Every node owns one **state slot**: a name standing for the `Toplevel.state` the
node starts from. The name belongs to the node for as long as the node exists,
and re-evaluating the node writes that same name again. The Python side never
holds a state, only a name.

A node's resulting state is the slot of its next sibling, or, for a last child,
the slot its parent keeps for the position after all its children. The output of
one node and the input of the next are therefore the same slot, and
re-evaluating a node writes into slots that already exist.

A node that fails and is passed over leaves its input state in its resulting
slot unchanged, so whatever follows always has something to run from.

### 3.2 Two fields

`evaluation_status` says whether evaluation can pass through the node.

| value | meaning |
| --- | --- |
| `not_evaluated` | no current result; nothing in the resulting slot to rely on |
| `ready` | the node ran and its resulting slot is current |
| `cannot_evaluate` | the node ran and evaluation stops here |

A node whose own commands failed is still `ready` when its class can carry on
regardless. A `Theorem` whose proof failed emits `sorry`, so the fact is declared
and every later node still checks.

`finished` says whether the node still owes anything. It is derived, never
stored, so it cannot drift from what it is derived from.

| node class | `finished` when |
| --- | --- |
| `Theorem` | `proof` is `proven` |
| `Define` | every role succeeded |
| a nesting class (`Section`, `Locale`, `Context`) | its own commands succeeded and every child is `finished` |
| a class with nothing to discharge | it has been evaluated |

`finished` is true only where `evaluation_status` is `ready`. A forest is
complete when every node is `finished`, and only `finished` answers that
question: a `Theorem` that emitted `sorry` ran a command that succeeded.

### 3.3 Where evaluation stops

`cannot_evaluate` has two sources, and they do not behave alike.

A **nesting node whose opening command failed** leaves its children no context to
run in. That is a fact about the state rather than a policy — there is nothing to
run them from.

A node whose failure would make everything after it report **derived errors**
stops evaluation by the judgement of its node class. `Define` is the case: when
the defining command fails the constant does not exist, so every later node that
mentions it fails with a message about the constant instead of about itself.

`evaluate_to` takes an `ignore_error` flag for an agent that wants to see every
error in one pass. It passes the second kind and never the first: a nesting node
whose opening failed has its whole subtree skipped, and evaluation resumes after
the block.

A node left unevaluated because evaluation stopped before reaching it records
which node stopped it, so it can say why rather than only that it did not run.

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

Because invalidation always runs forward, a tree's evaluated nodes are always a
prefix of it in tree order. TAT keeps no separate record of how far evaluation
has reached: the first node that is not evaluated is that point.

### 3.5 Running an evaluation

`evaluate_to(destination, ignore_error)` evaluates every `not_evaluated` node up
to and including the destination, in tree order, beginning at the first one.
Every tree the destination's tree imports must be evaluated to its own `end`
first, since a theory value exists only once its theory is closed.

Editing a node invalidates from that node and then evaluates it, so the result of
what was just written comes back with the call.

### 3.6 Work that outlives a call

Evaluation is synchronous: a loop that submits one command and waits. The one
asynchronous activity is `construct`, which starts a proof search; a `Theorem`
whose search is running has `proof = working`.

A node class that starts such work decides for itself what happens when its
context is invalidated under it. This adds no framework machinery: invalidation
and evaluation are already the two methods a node class overrides, so the class
is told at invalidation that its context is no longer current, and is given the
new one at evaluation. What `Theorem` does with that is open.

## 4. Compilation *(decided)*

TAT owns the `.thy` files: it is the compiler, so it knows by construction what
it wrote and where. It also delivers each change to Isabelle itself; the file
watcher plays no part.

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

## 5. Segments *(decided)*

A segment is exactly one Isabelle span, mirroring Isabelle's own partition of a
theory file (`contrib/Isabelle2025-2/src/Pure/PIDE/command_span.ML:36`, where the
three kinds of span are `Command_Span`, `Ignored_Span` and `Malformed_Span`).
That partition is total — whitespace and comments are spans, not gaps.

| segment kind | Isabelle's term | owner |
| --- | --- | --- |
| command | `Command_Span` | a node, plus a role |
| layout (blank lines, separator comments) | `Ignored_Span` | none |
| structural (`theory X imports … begin`, `end`) | `Command_Span` | the root node |

A node may own several segments; that is what `role` is for. No segment is owned
by more than one node, because the evaluator runs one node's commands at a time
(§7).

What survives is a check on the published artefact rather than on attribution:
the finished `.thy` is parsed as a whole by whoever builds it, so each node's
text must still be self-delimiting. Cartouches, comments and quotes are balanced
before a node's text is accepted. See
[appendix/SEGMENT_INTEGRITY.md](appendix/SEGMENT_INTEGRITY.md).

## 6. The node class contract *(decided)*

A node class is delivered as an Isabelle theory together with a Python package.
The theory is primary: it registers the class's evaluator on the ML side, and it
names the Python package carrying the rest. Installing a node class means adding
a theory to the base session, so the set of available node classes is fixed when
that heap is built.

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
schema. There is no universal representation of node data: one would be either
untyped or a union that the core has to know about, and a union defeats adding a
node class without touching the core.

The framework fixes the envelope and leaves the contents free.

- Fixed: the input state slot, the destination state slot, the outcome that
  becomes `evaluation_status`, and the per-role results.
- Free: how the class packs its own data, and whatever else it wants recorded.

The framework supplies the unpacker that turns a state slot name into a
`Toplevel.state`, and the packer for the envelope, so no class writes either
twice.

Callbacks are registered in one process-global table keyed by name, with
`Strhashtab.update` (`contrib/Isabelle_RPC/Tools/RPC.ML:429-435`), which
overwrites without complaint. Every callback name is therefore prefixed with the
name of the node class that owns it.

### 6.3 Two kinds of ML

The framework and the evaluators are needed only by TAT's own process. Generated
theories never name them, so they belong in the base heap and in no tree's
imports.

Anything the generated text does name — the `AoA` proof method, any syntax or
attribute a node emits — must be imported by the trees that use it, and is a
real dependency of the finished forest. A forest that cannot be built without
TAT is not an Isabelle development.

The concrete interfaces are unwritten.

## 7. Command-to-node mapping *(decided)*

The evaluator runs one node's commands at a time and reports the result of each,
by role. The mapping is given, not reconstructed: there is no line-span table,
and no question of whether our partition of a file agrees with Isabelle's.

A node emitting text that does not close cannot reach the next node's commands,
because those have not been submitted yet. It fails at its own parse.

## 8. Substrate *(decided)*

TAT drives Isabelle itself, through its own evaluator written in Isabelle/ML.
The evaluator holds an explicit `Toplevel.state` and runs one command at a time
through `Toplevel.command_errors`, which recovers from a failing command instead
of re-raising. Design in [EVALUATOR_DESIGN.md](../EVALUATOR_DESIGN.md); the
routes examined and rejected are in
[appendix/SUBSTRATE_RESEARCH.md](appendix/SUBSTRATE_RESEARCH.md).

The forest is not a session. TAT launches a prover on one base session heap and
the forest sits on top of it: every tree is authored, none is in a heap. When
the forest is finished it is an ordinary session that anyone can build.

Everything the forest imports from outside itself must be in that base heap.
That includes the theories registering TAT's own node classes (§6.3) and any
proof method the generated text names.

A clean verdict does not mean proved. TAT emits `sorry` deliberately, for nodes
whose proof has not been constructed, and knows which those are (§3.2). It never
emits `oops`, which produces no diagnostic, no decoration and no warning, and so
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

Concurrent chains share the state slot table, so that table is locked.

Node classes are installed by adding their theories to the base session (§6).

The entry point that starts a session in production is undecided. During
development an Isa-REPL app starts it, registered from a theory that the
production build does not import, so Isa-REPL is a development dependency and
never a shipped one.

## 10. Directory and module structure

Unwritten.
