# Routes for driving Isabelle

Five routes, graded on one question: after Isabelle checks a generated theory,
how do per-command results reach the node that emitted the command?

Either the mapping is **reconstructed** — generate the file, compute line spans,
match ranged results back, handle asynchrony — or it is **given**, with the
evaluator returning one record per command already stamped with its own span.

Citations are to `contrib/Isabelle2025-2/src/` unless prefixed.

| Route | Mapping | Verdict |
| --- | --- | --- |
| LSP via Isabelle-MCP | reconstructed | candidate |
| headless PIDE in Scala | given, one traversal | candidate |
| Isa-REPL | given | rejected — cannot be shipped |
| ML-side push (`Command.print_function`) | — | rejected |
| batch build / exports / `dump` | — | rejected |

## 1. LSP via Isabelle-MCP

Behaviour is documented in [ISABELLE_MCP.md](ISABELLE_MCP.md). Against the
grading question:

- The mapping is reconstructed from a line-span table TAT maintains itself.
- Status and diagnostics arrive ranged and complete, cheaply.
- Full output costs one round trip per command, and each call takes its own
  snapshot (`Tools/VSCode/src/language_server.scala:566-568`), so a report
  assembled over N commands can mix inconsistent document states.
- Neither status channel carries a document version; freshness is a 2.0 s clock.
- Edits are sent whole-document, which re-executes the theory
  ([EXPERIMENTS.md §1](EXPERIMENTS.md)). Fixable at one call site.

## 2. Headless PIDE in Scala

The same engine without the LSP skin. A client holding a `Document.Snapshot`
enumerates every command of a theory in one traversal:

| what | where |
| --- | --- |
| commands with source offsets | `Pure/PIDE/document.scala:359` |
| per-command status | `:1286` |
| per-command message list | `:1290` |
| names a command defines | `:1293` with `Markup.Entity.Def` (`Pure/PIDE/markup.scala:110`) |

Snapshots carry a version id and `is_outdated` (`Pure/PIDE/document.scala:588`,
`:637`), so staleness and cross-command inconsistency are absent rather than
defended against. No Isabelle patch is required; it is an add-on Scala component.

`Headless.use_theories` cannot be used as shipped: its `node_edits` performs
`Text.Edit.replace(0, old, new)` (`Pure/PIDE/headless.scala:492`), which is
remove-all plus insert-all (`Pure/PIDE/text.scala:148-150`). A real edit layer
must be written — an estimated 600-900 lines of Scala plus a Python client,
dominated by that layer and by asynchronous completion semantics rather than by
extracting data. These are internal-ish APIs, so budget a port per Isabelle
release.

Isabelle's span equality is position-independent: the `pos` inside a
`Command_Span` is an offset relative to the span, starting at 0
(`Pure/Isar/outer_syntax.scala:171-179`). Editing line 5 therefore does not
perturb the spans of commands at line 500, and the common-suffix chop in
`Thy_Syntax.chop_common` (`Pure/Thy/thy_syntax.scala:210-219`) keeps their ids.
The incremental capability is in Isabelle; `use_theories` discards it.

## 3. Isa-REPL — rejected

Structurally the best mapping of the five. The server returns one record per
command, in order, each carrying its own span:

```sml
(* contrib/Isa-REPL/library/REPL.ML:202-212 *)
type command_output = {
        command : string,
        output  : message list,
        ...
        errors  : string list,
        range   : Position.T * Position.T
}
```

No span table is needed. It achieves this with the error-recovering
`Toplevel.command_errors false tr s` (`contrib/Isa-REPL/library/REPL.ML:662`), and offers a per-command
collector hook (`contrib/Isa-REPL/library/REPL.ML:191-197`) for extracting generated fact names.

**Rejected**: Isa-REPL is a development tool and cannot be shipped.

What the rejection costs TAT is the whole of the reconstructed-mapping
machinery: the segment table, its invariants, the lexical self-containment
check, the partition cross-check, and the freshness clock. Route 1 needs all of
them and Isa-REPL needs none.

Defects found while evaluating it, should it ever be reconsidered:

- `init_printers` is never called — the only occurrences are the signature
  (`contrib/Isa-REPL/library/REPL.ML:153`), the definition (`:265`) and a commented-out invocation
  (`:284`) — and `contrib/Isa-REPL/repl_server.sh:92` runs `REPL.disable_output ()`. In a stock
  deployment the `output` field is always empty.
- `Client.eval` discards per-command outputs on any error
  (`contrib/Isa-REPL/IsaREPL/IsaREPL.py:249-254`), which is when they matter.
- A theory closed with `register_thy` cannot be re-evaluated even after rollback
  (`contrib/Isa-REPL/library/REPL.ML:433-435`).
- Intra-theory command parallelism is disabled by design, to keep attribution
  exact.

## 4. ML-side push — rejected

Registering `Command.print_function` (`Pure/PIDE/command.ML:389`) to report
per-command outcomes. Three independent defects, each fatal:

1. **Print functions run only for *visible* commands** (`Pure/PIDE/command.ML:373-381`).
   Under headless PIDE the perspective is empty
   (`Pure/PIDE/headless.scala:482`); under Isabelle-MCP it is ±1 line around the
   caret; in batch loading `Command.eval`/`print` are not on the path.
2. **A `print_fn` sees neither the error messages nor the `failed` flag** — its
   signature passes only `tr` and `st'` (`Pure/PIDE/command.ML:295-297`). `strict = false`
   makes it fire on failure without telling it that it failed.
3. **In PIDE mode ML has no line number.** Document tokens carry only an exec id
   (`Pure/PIDE/document.ML:434`) and `Position.id` has `line = 0`
   (`Pure/General/position.ML:169`), so ML cannot map back to a node.

Document markers cannot carry the node identity either: `apply_markers` is
applied to the *result* of `apply_body`, so a raising command never reaches it
(`Pure/Isar/toplevel.ML:329-335`). Markers cannot report failures.

Usable later as an enrichment — structured payloads straight from ML — on top of
a primary mapping.

## 5. Batch build, exports, `dump` — rejected

Three independent defects, each fatal:

1. **Batch aborts at the first error.** It runs commands through
   `Toplevel.command_exception`, which re-raises (`Pure/Isar/toplevel.ML:733`,
   `:651-656`); the recovering `command_errors` (`:646-649`) is not used. TAT
   routinely has several failing nodes at once.
2. **Invalidation granularity is the session.** `sources_shasum` is compared per
   session (`Pure/Build/build_process.scala:1163-1168`).
3. **The database export has no per-command structure.** `Build.read_theory`
   reconstructs the whole theory as a single synthetic command
   (`Pure/Build/build.scala:799-803`).

Mechanisms examined and their ceilings:

- `Build.add_hook` (`Pure/Build/build.ML:9-11`) hands ML the full per-command
  segment list — span, transition, pre/post `Toplevel.state`. Fires only on
  success (`:89-93`) and only after the whole session.
- `Thy_Info.add_presentation` (`Pure/Thy/thy_info.ML:15`) — same segments, per
  theory, same success-only limit.
- `isabelle dump` is headless PIDE, not batch (`Pure/Tools/dump.scala:225-226`),
  with `parallel_proofs = 0` forced (`:96`); its `messages` aspect drops
  positions.

Still useful for bulk offline passes over a finished forest, where per-command
attribution is not needed.

## 6. Comparing the two candidates

| | LSP | headless Scala |
| --- | --- | --- |
| status freshness | 2.0 s clock | snapshot version id |
| all commands' results | N round trips, N snapshots | one traversal, one snapshot |
| partition cross-check | O(N) round trips | O(1) per compile |
| names a command defines | parse rendered output | `Markup.Entity.Def` |
| ranged edits | a few dozen lines of Python | part of a Scala edit layer |
| effort | reuse Isabelle-MCP | 600-900 lines Scala, plus a port per release |
