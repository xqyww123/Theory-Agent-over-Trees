# TAT Architecture

Status: **design draft**. Sections marked *(decided)* record choices already
made; sections marked *(open)* are tracked in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md)
and must not be treated as settled.

## 1. Glossary

These terms are fixed. Use them and no synonyms.

| Term | Meaning |
| --- | --- |
| **forest** | all working theories, as a set of trees |
| **tree** | one Isabelle theory; the root's name is the short name of the theory |
| **node** | one semantic unit in a tree (a theorem, a definition, a section heading) |
| **node class** | the kind of a node — `Theorem`, `Define`, `Datatype`, … — extensible |
| **role** | tag distinguishing the several commands one node emits |
| **segment** | one Isabelle command span in an emitted file (see §4) |
| **compile** | turning trees into `.thy` files on disk |
| **generation** | a monotone counter, bumped on every compile of a file |

## 2. The model *(decided)*

A tree is one theory. The forest's edges are the `imports` relations declared by
the tree roots, so the forest is a dependency graph and compilation order is a
topological order over it.

Initial node classes: `Theorem`, `Define`, `Datatype`, `Quotient Type`, `Record`,
`TypeClass`, `Text`, `Section`. **New node classes must be addable without
touching the core** — this is a primary design requirement, not a nice-to-have.

Each node class corresponds to one or more Isabelle commands.

### 2.1 `Theorem`

| Attribute | Type |
| --- | --- |
| `kind` | `lemma` \| `corollary` \| `theorem` |
| `statement` | AoA's Long statement structure (`IsaMini/AoA/model.py`, `class LongStatement`) |

Who writes the proof body is **(open)** — see OPEN_QUESTIONS §1.

### 2.2 `Define`

| Attribute | Type |
| --- | --- |
| `kind` | `opaque` \| `auto-simp` |
| `equations` | the defining equations |

`auto-simp` adds `[simp]` to the resulting definitional equations. Several
equations compile to `fun`, or to `function … by aoa` plus `termination by aoa`.
`opaque` additionally emits `note xxx.simps[simp del]` to remove the simp rules.

This is the motivating example for the **role** mechanism: one node, several
commands, each of which can fail independently and must be reported separately.

| role | emitted |
| --- | --- |
| `function` | `fun f where …` or `function f where …` |
| `pat-completeness` | the completeness proof (only for the `function` form) |
| `termination` | `termination by …` (only for the `function` form) |
| `simp-del` | `note f.simps[simp del]` (only when `kind = opaque`) |

"The definition is wrong" and "the definition is fine but termination did not go
through" are different reports, and the agent needs to be able to tell them apart.

Remaining node classes: **(open)**, to be specified.

## 3. Compilation *(decided)*

Compilation writes `.thy` files. TAT owns the files: it is the compiler, so it
knows by construction what it wrote and where. After writing, it may notify the
file watchers to trigger re-checking.

The compiler must **not** build the file by string concatenation. It builds an
ordered list of segments, and line numbers are computed once at serialisation
time by counting newlines. Spans are therefore exact by construction and are
never recovered by parsing the output back.

## 4. Segments

A **segment** is exactly one Isabelle command span. This mirrors Isabelle's own
partition of a theory file:

```sml
(* Pure/PIDE/command_span.ML:36 *)
datatype kind = Command_Span of string * Position.T | Ignored_Span | Malformed_Span;
```

The partition is **total**: whitespace and comments are `Ignored_Span`, not gaps.
On the Scala side the same distinction is `is_proper` / `is_ignored`
(`Pure/PIDE/command.scala:497-498`). Because our segment list mirrors that
partition, any position Isabelle reports lands in exactly one segment — lookup is
a total function with no "not found" branch.

Three segment kinds in TAT:

| segment kind | in Isabelle's terms | owner |
| --- | --- | --- |
| command | `Command_Span` | a node, plus a role |
| layout (blank lines, separator comments) | `Ignored_Span` | none |
| structural (`theory X imports … begin`, `end`) | `Command_Span` | the root node |

### 4.1 The two invariants

1. **One node may own several segments.** Normal; that is what `role` is for.
2. **No segment may be owned by more than one node.** This is the foundation of
   the whole mapping and must be defended actively.

Invariant 2 is broken by exactly one failure mode: **a node's emitted text is not
self-delimiting and swallows its successors.** An unclosed cartouche `‹`, an
unclosed `(*`, or a truncated command makes Isabelle parse one span covering
several of our segments (or a `Malformed_Span`). Attribution downstream then
misaligns *silently*. With LLM-generated statement text this is not a theoretical
risk.

Three layers of defence, cheapest first:

1. **Lexical self-containment check before emitting.** Balance cartouches,
   comments and quotes over each node's text. On failure, report it as a
   node-level error and never write the poisoned file. This also produces a far
   better message than Isabelle's downstream parse error.
2. **Partition cross-check.** Compare our segment boundaries against Isabelle's
   actual command ranges. On disagreement, mark the file's attribution
   *untrusted* rather than reporting misaligned results.
3. **`Malformed_Span`** is Isabelle telling us defence 1 leaked. Free backstop.

The cost of defence 2 depends on the substrate: one round trip per command over
LSP (`PIDE/output_at_position` returns the command's true range), versus a single
in-process traversal under headless PIDE. See SUBSTRATE_RESEARCH §6.

## 5. Node class interface

The extension seam. Modelled on AoA's `Node` (`IsaMini/AoA/model.py:4124`), which
separates assembling operations from rendering them.

```python
class NodeClass(ABC):
    name: ClassVar[str]
    ArgSchema: ClassVar[type[TypedDict]]               # -> MCP tool schema

    def compile(self, node) -> list[EmittedCommand]: ...
    def absorb(self, node, results: Mapping[str, CommandResult]) -> NodeReport: ...
    def quickview(self, node, report) -> str: ...
    def print(self, node, report) -> str: ...
```

`compile` is the **only** emission point, so span bookkeeping cannot be bypassed:
a new node class inherits correct attribution for free. `absorb` is where a node
class interprets raw per-command results into its own semantics.

`ArgSchema` -> MCP tool schema generation should reuse AoA's existing machinery
rather than being rewritten.

## 6. Command-to-node mapping

The mapping is **asserted at generation time, not recovered by analysis**: each
`compile()` returns its own commands, so `node -> text` is known; `text -> lines`
is newline counting. What must then be defended is that our asserted partition
agrees with Isabelle's actual parse (§4.1).

Results arrive in three kinds with very different costs, and must be harvested
accordingly:

| result | source | cost | granularity |
| --- | --- | --- | --- |
| processing status | `PIDE/decoration` (pushed) | cheap, complete | ranged |
| errors / warnings | `PIDE/decoration` (pushed) | cheap, complete | ranged |
| full output (proof state, generated equations) | `PIDE/output_at_position` (pulled) | one round trip **per command** | single command |

So: status and diagnostics are attributed in bulk by range; full output is pulled
lazily, only for nodes that need detail. This mirrors AoA's
`does_quickview_need_detail()`.

Line-number types must reuse Isabelle-MCP's existing `MCPLine` / `LSPLine`
(`evaluation.py`) rather than introducing a third 1-based/0-based convention.

## 7. Evaluation completion

TAT must **not** invent its own notion of "the file checked out fine". It reuses
Isabelle-MCP's completion predicate, which is the conjunction of two orthogonal
conditions (`Isabelle-MCP/src/isabelle_mcp/evaluation.py:172-181`):

- `_frontier_reached` — the destination line lies in no `unprocessed` range
  (running ranges are deliberately ignored: a fork means the evaluation chain has
  already passed), **and** every recursive import is done.
- `_prefix_quiet` — no `unprocessed` and no `running` range overlaps `[0, dest]`,
  i.e. every forked proof in the prefix has joined.

Neither suffices alone. Frontier-only reports success while a forked proof in the
prefix is still running and about to fail — a real bug, fixed in Isabelle-MCP
0.1.4 (`CHANGELOG.md:74-92`). Quiet-only cannot distinguish "finished" from
"never started".

### 7.1 Facts about the verdict that TAT must encode

- **Evaluation does not stop at the target line.** Both servers submit
  `required = true`, and with it execution runs from the first changed command to
  the end of the node (`Pure/PIDE/document.ML:864-870`). `evaluate_to` draws a
  waiting-and-reporting boundary, not an execution boundary.
- **`sorry` breaks `clean`** (it produces `background_bad`, folded into errors),
  but **`oops` produces nothing at all** — no diagnostic, no decoration, no
  warning (`Isabelle-MCP/docs/TECH_NOTE.md:143-147`). TAT is immune by
  construction only as long as it never emits `oops`; free-text proof bodies must
  be screened at the same gate as §4.1's defence 1.
- **Freshness is a 2.0 s clock, not an event.** Every edit-send stamps a global
  timestamp and cached decorations are distrusted for `DECORATION_GRACE`
  (`Isabelle-MCP/src/isabelle_mcp/processing.py:24-40`). An event-based
  acknowledgement is not available on this protocol: the server sends nothing
  when recomputed decorations equal the published ones, so waiting for a push
  would latch forever. This is a forced design choice, and it is the one
  load-bearing heuristic in the stack.

### 7.2 Where TAT is better placed than Isabelle-MCP

Isabelle-MCP's docs name the disk-to-model race as intrinsic to a file-watching
architecture (`docs/PIDE_MCP_COMPARISON.md:162`). TAT does not have to inherit
it: TAT writes the files itself, so it knows the generation it just wrote. Two
ways to convert the 2.0 s heuristic into a guarantee, both local changes because
the Scala language server is already a fork owned by this project family
(`Isabelle-MCP/src/isabelle_mcp/scala/Isabelle2025-2/`):

1. carry a document version on the decoration channel, and correlate;
2. echo a content hash of the server's current model, and refuse to attribute
   until it matches.

Neither exists today. Until one does, results must be marked `PENDING` rather
than `OK` inside the window — a `NodeStatus` with no defaultable success value.

## 8. Edit cost: ranged edits are mandatory

Measured, not inferred — see [EXPERIMENTS.md §1](EXPERIMENTS.md).

Isabelle-MCP sends every file sync as a `didChange` carrying the **whole**
document with no range (`Isabelle-MCP/src/isabelle_mcp/lsp_client.py:1327`). This
**destroys PIDE's reuse of the unchanged prefix**: editing only the last lemma of
a theory re-executes a slow command near its top, reproducibly, confirmed by
timing, by the `running:` status, and by a side-effect probe.

PIDE itself is not at fault. The identical edit delivered as a **ranged**
`didChange` reuses the prefix perfectly, with the error diagnostic landing on the
edited line in both cases. One call site is causally responsible.

Therefore, for TAT:

- **An edit must be delivered as a minimal range**, not as a full document.
  Since TAT compiles the file itself it holds both the old and the new segment
  lists, so a common-prefix/suffix trim is cheap and exact — it does not need a
  general text diff.
- Without this, the edit loop costs one whole theory per node edit, which
  defeats the point of a node-granular agent.
- The same trap exists on the headless route: `Headless.use_theories` also
  performs a whole-file `Text.Edit.replace` (`Pure/PIDE/headless.scala:492`).
  The difference is the size of the fix — a few dozen lines of range computation
  in Python here, against a full document-bookkeeping layer in Scala there.

## 9. Packaging *(decided)*

TAT is a plugin of Isabelle-MCP exposing its own MCP server. It reuses
Isabelle-MCP's `IsabelleLSPClient` (session lifecycle, evaluation status,
decorations, `output_at_position`) as a library.

This requires a small refactor of Isabelle-MCP first: `server.py` currently holds
a module-level `FastMCP` instance with flat `@mcp.tool()` registrations, a
module-level client singleton, and a lifespan bound to that server. Client,
lifespan and file watcher need to be extractable without importing the tool
surface.
