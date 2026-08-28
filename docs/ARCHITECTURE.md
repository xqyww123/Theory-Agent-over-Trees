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
| **compile** | turning trees into `.thy` files on disk |
| **generation** | a monotone counter, bumped on every compile of a file |

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
nothing about how its children are checked or named.

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

### 2.2 Node classes

**`Theorem`**

| Attribute | Type |
| --- | --- |
| `kind` | `lemma` \| `corollary` \| `theorem` |
| `statement` | AoA's Long statement (`contrib/Isa-Mini/IsaMini/AoA/model.py`, `class LongStatement`) |
| `proof` | `not_started` \| `working` \| `proven` \| `failed` |

`proof` is the state of the search, not a proof: a tree holds no proof (§2.1).
Adding a `Theorem` may start the search at once, but the default is
`not_started`, so laying out a theory costs nothing. `construct` starts it.

A node whose `proof` is `not_started` emits **`sorry`**. Emitting `by AoA` with
nothing in the cache would fail, and a failing `by` means the fact is never
added, so every later node using it fails too — a skeleton of twenty lemmas
would check none of them past the first. With `sorry` the fact is admitted, the
whole tree's structure and types are checked, and the agent constructs proofs
afterwards.

This is honest only because `proof` is tracked. TAT reports the tree as clean
*and* names the nodes that are `not_started`; it is not claiming they are
proved.

**`Define`**

| Attribute | Type |
| --- | --- |
| `kind` | `opaque` \| `auto-simp` |
| `equations` | the defining equations |

`auto-simp` adds `[simp]` to the resulting definitional equations; `opaque`
removes them again with `note f.simps[simp del]`. Several equations compile to
`fun`, or to `function` with its proof obligations discharged by `AoA`.

`Define` is the motivating case for **role**: one node, several commands, each
able to fail on its own.

| role | emitted | when |
| --- | --- | --- |
| `function` | `fun f where …` or `function f where …` | always |
| `pat-completeness` | the completeness proof | `function` form |
| `termination` | `termination by …` | `function` form |
| `simp-del` | `note f.simps[simp del]` | `kind = opaque` |

"The definition is wrong" and "the definition is fine but termination failed" are
different reports.

`Datatype`, `QuotientType`, `Record`, `TypeClass`, `Text` and `Section` are
unspecified.

## 3. Compilation *(decided)*

TAT owns the `.thy` files: it is the compiler, so it knows by construction what
it wrote and where. It also delivers each change to Isabelle itself; the file
watcher plays no part. How, and why it must be that way, is in
[MCP_SPECIFICATION.md §2](MCP_SPECIFICATION.md).

The compiler builds an ordered list of segments and computes line numbers once,
at serialisation, by counting newlines. It never concatenates strings and never
parses its own output back.

## 4. Segments *(decided)*

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
and reports the spans it parsed (§6).

What survives is a check on the published artefact rather than on attribution:
the finished `.thy` is parsed as a whole by whoever builds it, so each node's
text must still be self-delimiting. Cartouches, comments and quotes are balanced
before a node's text is accepted. See
[appendix/SEGMENT_INTEGRITY.md](appendix/SEGMENT_INTEGRITY.md).

## 5. Node classes

A node class is delivered as an Isabelle theory together with a Python package.
The theory is primary: it registers the class's evaluator and constructor on the
ML side, and it names the Python package carrying the class's data definition
and its emitter. Installing a node class means adding a theory to the base
session, so the set of available node classes is fixed when that heap is built.

Four parts:

| part | side | |
| --- | --- | --- |
| data definition and argument schema | Python | becomes the MCP tool schema |
| proposed emission | Python | node data to Isar text |
| evaluator | ML | runs the node; may substitute its own commands |
| constructor | ML | the `construct` operation, for classes that have one |

The evaluator has a default: run the proposed text. Only a class whose commands
depend on the state they meet needs to write one. `Define` is the first — it
emits `fun` and falls back to `function` when termination is not discharged on
its own.

### 5.1 Emission is proposed; execution decides

A node's contribution to the `.thy` file is the transcript of what its evaluator
ran, not the text its emitter proposed. The two differ whenever an evaluator
substitutes commands.

Python writes the file, from the transcripts, in tree order. The evaluator never
writes one. The file and the evaluation therefore cannot disagree.

### 5.2 Two kinds of ML

The framework and the evaluators are needed only by TAT's own process. Generated
theories never name them, so they belong in the base heap and in no tree's
imports.

Anything the generated text does name — the `AoA` proof method, any syntax or
attribute a node emits — must be imported by the trees that use it, and is a
real dependency of the finished forest. A forest that cannot be built without
TAT is not an Isabelle development.

The concrete interfaces are unwritten.

## 6. Command-to-node mapping *(decided)*

The evaluator runs one node's commands at a time and reports what it ran, with
each command's own span and result. The mapping is given, not reconstructed:
there is no line-span table, and no question of whether our partition agrees
with Isabelle's — the spans are the ones Isabelle parsed.

A node emitting text that does not close cannot reach the next node's commands,
because those have not been submitted yet. It fails at its own parse.

## 7. Substrate *(decided)*

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
That includes the theories registering TAT's own node classes (§5.2) and any
proof method the generated text names.

A clean verdict does not mean proved. TAT emits `sorry` deliberately, for nodes
whose proof has not been constructed, and knows which those are (§2.2). It never
emits `oops`, which produces no diagnostic, no decoration and no warning, and so
could not be accounted for.

## 8. Packaging

TAT is a Python process and an Isabelle process. The Python side owns the
forest, serves the MCP tools, and writes the `.thy` files. The Isabelle side
runs the evaluator. The channel between them is unwritten.

Node classes are installed by adding their theories to the base session (§5).

## 9. Directory and module structure

Unwritten.
