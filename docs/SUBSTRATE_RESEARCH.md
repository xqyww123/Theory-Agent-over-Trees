# How TAT drives Isabelle: routes evaluated

Record of the research behind the substrate choice. Five routes were examined
against one question:

> After Isabelle checks a generated theory, how do per-command results reach the
> tree node that emitted the command?

Two answers are structurally different. Either the mapping is **reconstructed**
(generate the file, compute line spans, match ranged results back, and fight
asynchrony), or it is **given** (the evaluator returns one record per command,
already stamped with its own span). Everything below is graded on that axis.

All citations are to `contrib/Isabelle2025-2/src/` unless prefixed otherwise.

## Summary

| Route | Mapping | Verdict |
| --- | --- | --- |
| LSP via Isabelle-MCP | reconstructed | **candidate** |
| headless PIDE in Scala | given, in one traversal | **candidate** |
| Isa-REPL | given | rejected — development-only, not shippable |
| ML-side push (`Command.print_function`) | — | rejected — three independent fatal defects |
| batch `isabelle build` / exports / `dump` | — | rejected — three independent fatal defects |

## 1. LSP via Isabelle-MCP

The baseline, and the route TAT is built on as a plugin. Mapping is
reconstructed: TAT records the line span of every command it emits and attributes
ranged decorations back by line.

What has to be handled, and is:

- Completion is a two-part predicate, not "no errors seen yet" — see
  ARCHITECTURE §7. This is well designed and must be reused, not reinvented.
- Errors are read unclipped over the whole file; only `pending` is clipped to the
  evaluated prefix.
- Running commands are surfaced with onset timestamps, so a stuck proof is
  visible with elapsed seconds.

What remains weak:

- **No version on the status channels.** `publishDiagnostics` carries only `uri`
  and `diagnostics` (`Tools/VSCode/src/lsp.scala:507-511`); `PIDE/decoration`
  likewise has no version. Freshness is a 2.0 s clock
  (`Isabelle-MCP/src/isabelle_mcp/processing.py:24-40`). See ARCHITECTURE §7.1-7.2.
- **Full output costs one round trip per command**, and each call takes its own
  snapshot (`Tools/VSCode/src/language_server.scala:566-568`), so a report
  assembled over N commands can mix mutually inconsistent document states.
- **Edits are sent as full text** (`Isabelle-MCP/src/isabelle_mcp/lsp_client.py:1327`,
  no `range` in `contentChanges`), and this **destroys PIDE's prefix reuse** —
  measured, see EXPERIMENTS §1. Editing the last lemma of a theory re-executes a
  slow command near its top. The same edit sent as a *ranged* `didChange` reuses
  the prefix perfectly, so the fix is local to that one call site.

Note that diagnostics are *not* the verdict channel here: the verdict is built
from `PIDE/decoration` plus `PIDE/theory_status`
(`Isabelle-MCP/src/isabelle_mcp/evaluation.py:267-269`). The diagnostics cache
survives essentially for `isabelle_hover`.

Also note that Isabelle-MCP no longer patches Isabelle. It ships its own Isabelle
Scala component `isabelle mcp_server`, a fork of the `vscode_server` sources with
a prebuilt jar and `no_build = true` (`Isabelle-MCP/README.md:33-40`,
`docs/ARCHITECTURE.md:17`). Anything TAT wants to add on the Scala side is
therefore a local change to a fork this project family already owns — not a
distribution patch, and no session heap is invalidated.

## 2. Headless PIDE in Scala

Same engine as route 1 without the LSP skin. A Scala client holding a
`Document.Snapshot` enumerates every command of a theory in **one traversal**,
with source offset, stable command id, status and the complete message list:

- `Document.Node.command_iterator` (`Pure/PIDE/document.scala:359`)
- `state.command_status(version, command)` (`:1286`)
- `state.command_results(version, command)` (`:1290`)
- `state.command_markup(...)` + `Markup.Entity.Def` (`:1293`,
  `Pure/PIDE/markup.scala:110`) — the names a command *defines*, which is exactly
  what `Define` nodes need and what would otherwise be parsed out of rendered HTML

Snapshots carry a version id and `is_outdated` (`Pure/PIDE/document.scala:588`,
`:637`); `stable_snapshot` asserts version identity
(`Pure/PIDE/headless.scala:18-26`). The staleness and inconsistent-snapshot
problems of route 1 are structurally absent, not merely defended against.

Requires no Isabelle patch; it is an add-on Scala component built with
`isabelle scala_build`, exactly as Isabelle-MCP's own component is.

Cost: `Headless.use_theories` cannot be used as shipped. Its
`node_edits` performs `Text.Edit.replace(0, old.text, text)`
(`Pure/PIDE/headless.scala:492`), and `Text.Edit.replace` is not a diff — it is
remove-everything plus insert-everything (`Pure/PIDE/text.scala:148-150`). A real
edit layer must be written. Estimated 600-900 lines of Scala plus a Python
client; the effort is dominated by the edit layer and by asynchronous completion
semantics, not by extracting the data. Ongoing cost: these are internal-ish APIs
with no stability guarantee, so budget a port per Isabelle release.

Worth recording: Isabelle's span equality is **position-independent** — the `pos`
inside a `Command_Span` is an offset relative to the span itself, starting at 0
(`Pure/Isar/outer_syntax.scala:171-179`). Inserting text at line 5 therefore does
not perturb the spans of commands at line 500, so the common-suffix chop in
`Thy_Syntax.chop_common` (`Pure/Thy/thy_syntax.scala:210-219`) can succeed and
those commands keep their ids. The incremental capability exists in Isabelle; it
is `use_theories` that discards it.

## 3. Isa-REPL — rejected

Structurally the best mapping of all five: the server returns one record per
command, in order, each carrying its own span in the submitted string.

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

Per-command `errors` and `range` mean no span table at all. It achieves this by
using the error-recovering variant `Toplevel.command_errors false tr s`
(`REPL.ML:662`) where batch uses the re-raising `command_exception`. It also has
a per-command collector plugin hook (`REPL.ML:191-197`) — the sanctioned place to
extract generated fact names.

**Rejected**: Isa-REPL is a development tool, not something TAT can ship.

Recorded for completeness, since it also affects any future reconsideration —
defects found while evaluating it:

- `init_printers` is **never called**: the only three occurrences repo-wide are
  the signature (`REPL.ML:153`), the definition (`:265`), and a commented-out
  invocation (`:284`); and `repl_server.sh:92` runs `REPL.disable_output ()`. In
  a stock deployment the `output` field is therefore always empty.
- `Client.eval` discards per-command outputs on any error
  (`IsaREPL.py:249-254`), i.e. exactly when they matter; the docstring
  contradicts the code.
- A theory closed with `register_thy` cannot be re-evaluated even after rollback
  (`REPL.ML:433-435`), because `evaluated_theories` is not part of the rollback
  state.
- The design deliberately disables intra-theory command parallelism to keep
  attribution exact (`doc/Readme.md`, "Concurrency").

## 4. ML-side push — rejected

Registering `Command.print_function` (`Pure/PIDE/command.ML:389`, type at `:295`)
to report per-command outcomes over Isabelle_RPC. Three independent fatal
defects:

1. **Print functions only run for *visible* commands** (`command.ML:373-381`).
   Under headless PIDE the perspective is `Text.Perspective.empty`
   (`Pure/PIDE/headless.scala:482`) so they never run; under Isabelle-MCP the
   perspective is ±1 line around the caret
   (`Isabelle-MCP/src/isabelle_mcp/lsp_client.py:361`); in batch theory loading
   `Command.eval`/`print` are not on the path at all.
2. **A `print_fn` cannot see error messages, or even the `failed` flag.** Its
   signature passes only `tr` and `st'` (`command.ML:295-297`); `strict = false`
   merely makes it fire on failure without telling it that it failed (`:327`).
3. **In PIDE mode ML has no line number.** Document tokens carry only an exec id
   (`Pure/PIDE/document.ML:434`) and `Position.id` has `line = 0`
   (`Pure/General/position.ML:169`), so `Position.line_of` is `NONE`. ML cannot
   map back to a node on its own.

Document markers were examined as the node-identity carrier and are **fatal on
failure**: in `apply_capture`, `apply_markers` is applied to the *result* of
`apply_body`, so a raising command never reaches it
(`Pure/Isar/toplevel.ML:329-335`). Markers cannot report failures.

Also: `exec_id` deduplicates repeats of one *evaluation*, not of one logical
command — re-evaluation mints a fresh eval and a fresh id
(`Pure/PIDE/document.ML:703-720`); and prints are forked concurrently by default
(`command.ML:386-387`), so callbacks arrive out of document order.

Retained as a possible **enrichment** (structured payloads straight from ML) once
a primary mapping exists — never as the primary mapping.

## 5. Batch build / exports / dump — rejected

Three independent fatal defects:

1. **Batch aborts at the first error.** It runs commands through
   `Toplevel.command_exception`, which re-raises
   (`Pure/Isar/toplevel.ML:733`, `:651-656`); the error-recovering
   `command_errors` (`:646-649`) is not used. Results after the first failing
   node are unobtainable. TAT routinely has several failing nodes at once, so
   this alone disqualifies the family.
2. **Invalidation granularity is the session.** `sources_shasum` is compared per
   session (`Pure/Build/build_process.scala:1163-1168`); editing one node
   re-checks every theory in the session.
3. **The database export has no per-command structure.** `Build.read_theory`
   reconstructs the whole theory as a single synthetic command
   (`Pure/Build/build.scala:799-803`), so command identity is gone and only text
   ranges survive — i.e. the same span-table substrate as route 1, minus
   interactivity and minus error recovery.

Mechanisms examined and their ceilings:

- `Build.add_hook` (`Pure/Build/build.ML:9-11`) hands ML the **full per-command
  segment list** (span, transition, pre/post `Toplevel.state`), which combined
  with `Export.export` would give per-node structured artefacts with no Scala
  code. But it fires **only on success** (`:89-93`) and **only after the whole
  session**.
- `Thy_Info.add_presentation` (`Pure/Thy/thy_info.ML:15`) — same segments, per
  theory, same success-only limitation.
- `isabelle dump` is not batch at all: it is headless PIDE
  (`Pure/Tools/dump.scala:225-226`, `:317-321`) with `parallel_proofs = 0`
  forced (`:96`). Its `messages` aspect drops positions.

Still useful for **bulk offline passes** over a finished forest — "does the whole
forest still compile", corpus extraction — where per-command attribution is not
needed.

## 6. What the choice turns on

Route 1 and route 2 are the same engine. The difference is the interface:

| | route 1 (LSP) | route 2 (headless Scala) |
| --- | --- | --- |
| status freshness | 2.0 s clock | snapshot version id |
| all commands' results | N round trips, N snapshots | one traversal, one snapshot |
| partition cross-check (ARCH §4.1 defence 2) | O(N) round trips | O(1) per compile |
| names a command defines | parse rendered output | `Markup.Entity.Def` |
| effort | reuse Isabelle-MCP | 600-900 lines Scala + per-release port |
