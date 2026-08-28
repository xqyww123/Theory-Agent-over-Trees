# How Isabelle-MCP behaves

Findings that TAT's design depends on. Paths are relative to
`contrib/Isabelle-MCP/` unless prefixed; Isabelle sources are under
`contrib/Isabelle2025-2/src/`.

## 1. What it is

Isabelle-MCP drives a **fork of Isabelle's VSCode language server**, shipped as
its own Isabelle Scala component `isabelle mcp_server` with a prebuilt jar and
`no_build = true` (`contrib/Isabelle-MCP/README.md:33-40`, `contrib/Isabelle-MCP/docs/ARCHITECTURE.md:17`). It is not a
patched Isabelle: nothing is compiled on the user's machine and no session heap
is invalidated. The fork carries PIDE requests the stock server lacks —
`PIDE/theory_status`, `PIDE/cancel_execution`, `PIDE/command_at_position`,
`PIDE/output_at_position`, `PIDE/symbols`, `PIDE/find_theorems_*`.

Anything TAT needs on the Scala side is a change to a fork this project family
owns.

## 2. The run model

The agent owns the files; the server owns the prover.

1. The agent edits a `.thy` on disk.
2. Two detectors pick it up: an inotify watcher on the parent directory, and a
   stat backstop at the start of every tool call.
3. The content is sent as `textDocument/didChange` — **whole document, no
   range** (`src/isabelle_mcp/lsp_client.py:1327`) — and a global edit timestamp
   is stamped.
4. Every tracker's cached status is distrusted for `DECORATION_GRACE`, 2.0 s
   (`src/isabelle_mcp/processing.py:24-40`).
5. `isabelle_evaluate_to(file, L)` takes the single-evaluation mutex, resolves
   the caret onto the last non-blank character of line `L`, and sends one
   `PIDE/caret_update`.
6. PIDE evaluates sequentially per node, from the first changed command **to the
   end of the node**; nodes are scheduled on the import graph; proof bodies are
   forked in parallel.
7. Status streams back as `PIDE/decoration` at ≥0.5 s intervals, per type,
   full-replace within each type.
8. The wait loop blocks on the frontier event and re-stats open documents every
   3 s so mid-evaluation edits are absorbed.
9. The agent polls `isabelle_evaluation_status` until it reports `complete`.

### 2.1 Evaluation is bounded by the target line

Commands after the caret are not executed until the caret reaches them. Measured
twice, at 91 and 95 seconds beyond a reported-complete `evaluate_to`, with a
side effect that status reporting cannot fake — [EXPERIMENTS.md §2](EXPERIMENTS.md).

The mechanism was not established. Reading the perspective submission alone
predicts the opposite, since every `.thy` model is created with
`node_required = is_theory` and `required` suppresses the visible-region cutoff
in `Pure/PIDE/document.ML:864-870`. Behaviour is what was tested.

## 3. The completion predicate

`complete` is the conjunction of two conditions
(`src/isabelle_mcp/evaluation.py:172-181`):

- **`_frontier_reached`** — the destination line lies in no `unprocessed` range,
  and every recursive import is done. Running ranges are ignored here: a fork
  means the evaluation chain has already passed.
- **`_prefix_quiet`** — no `unprocessed` and no `running` range overlaps
  `[0, dest]`, so every forked proof in the prefix has joined.

Neither suffices alone. With the frontier only, a forked proof in the prefix can
still be running and about to fail. With quiet only, a file that never started is
indistinguishable from one that finished.

Correctness rests on one empirical invariant: PIDE delivers "leave
running/unprocessed" and "become bad/error" in the same decoration push.

### 3.1 What a clean verdict does not mean

`sorry` produces `background_bad` and is folded into errors, so it breaks
`clean`. `oops` produces nothing at all — no diagnostic, no decoration, no
warning (`docs/TECH_NOTE.md:143-147`).

## 4. Freshness is a clock

There is no version on either status channel. `publishDiagnostics` carries only
`uri` and `diagnostics` (`Isabelle2025-2/src/Tools/VSCode/src/lsp.scala:507-511`);
`PIDE/decoration` likewise. Freshness is the 2.0 s timer of step 4 above.

An event-based acknowledgement is not available on this protocol: the server
sends nothing when recomputed decorations equal the published ones, so waiting
for a push would latch forever. The clock is forced, and it is the one
load-bearing heuristic in the stack.

It can be tightened for TAT, which writes the files itself and knows the
generation it wrote: carry a document version on the decoration channel and
correlate, or echo a content hash and refuse to attribute until it matches.
Both are changes to the fork of §1. Until one exists, a node's status inside the
window is `PENDING`, never `OK`.

## 5. Diagnostics are not the verdict channel

The verdict is built from `PIDE/decoration` plus `PIDE/theory_status`
(`src/isabelle_mcp/evaluation.py:267-269`). Errors are `text_overview_error`
united with `background_bad`; warnings are `text_overview_warning`; running is
`background_running1`. The diagnostics cache serves `isabelle_hover`.

## 6. Its documents contradict each other

They are stratified in time and were not reconciled, so neither recency nor any
other rule of thumb picks the right one. Both experiments in
[EXPERIMENTS.md](EXPERIMENTS.md) settle a point on which they disagree, and they
do not settle it the same way: on prefix reuse both documents are wrong, and on
whether the caret bounds execution the older `docs/TECH_NOTE.md` is right and the
newer `docs/PIDE_MCP_COMPARISON.md` is wrong.

Treat this appendix, not those documents, as the record of Isabelle-MCP's
behaviour, and measure anything it does not cover.

Known conflicts between them: whether the caret bounds execution; what gates
`complete`; whether `sorry` lands in errors or warnings; whether query tools
error or auto-evaluate during an active evaluation; whether an Isabelle patch is
required.
