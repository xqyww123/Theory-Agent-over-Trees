# Open questions

Nothing here is settled. Ordered by what it blocks.

## 1. `Forest` and `Theory` in the recursion

**Blocks:** running anything.

`Node`, `Leaf`, `NonLeaf_Node` and `StdBlock` are written
(`isabelle_theory_agent/model.py`); `Forest._evaluate` is not. Its shape is
fixed (ARCHITECTURE §3.5): the forest ignores the `Session` layer, builds the
import dependency graph over the trees, and schedules evaluation on it, a
`Session` as destination standing for all the trees under it. Still open:
both ends of a `Theory` root's slot chain, settled where `Theory`'s own
evaluation is implemented — its `state`, which nothing writes (trees are
not chained, and `begin_theory` starts from `Toplevel.make_state NONE`
regardless), and the resulting slot its `end` would write, which nothing
reads (the theory value goes to the theory table; the tree has no successor
on the slot chain) — and how a stop in one tree reaches the trees that
import it and no other.

## 2. The remaining node classes

**Blocks:** most of what an agent would actually write.

`Datatype`, `QuotientType`, `Record`, `TypeClass`, `Text`, `Section`, `Context`
and `Locale` are unspecified. `Context` and `Locale` also need their two
omissibility flags (MCP_SPECIFICATION §2.1).

## 3. `construct` on one node or several

After laying out a skeleton the agent will want to construct many proofs at
once. Batching complicates the message model, since each is an independent
asynchronous activity.

## 4. What `Theorem` does when a running search is invalidated

The framework tells a node class that its context is no longer current and later
hands it the new one (ARCHITECTURE §3.6); what `Theorem` does with that is
not decided.

Ignoring the change is free and correct: evaluation runs the stored proof and
never searches (ARCHITECTURE §3.6), so a proof built against the old context is
only a candidate either way, and a stored proof that fails leaves the node
`failed` for another `construct`. Suspending the search and re-running it against the new context
saves a search when the change was harmless, and costs a suspend-and-resume
path through the AoA agent.

## 5. Where the `AoA` proof method lives

If it is defined in a theory, that theory must be in the base heap, and it is a
real import of every tree that uses it.

## 6. The entry point in production

A conversation begins with Isabelle calling into Python (ARCHITECTURE §9),
and something has to make Isabelle do that. TAT is a library and that something is
a client of it (MODULE_STRUCTURE §4); an `isabelle` subcommand through a Scala
component is one form. During development an Isa-REPL app serves.

## 7. Whether to check completeness against Isabelle's own record

`sorry` leaves a `skip_proof` oracle on the theorem, and
`Thm_Deps.has_skip_proof`
(`contrib/Isabelle2025-2/src/Pure/thm_deps.ML:35-36`) finds it. Asking Isabelle
whether any theorem in a forest carries that oracle is an account of
completeness independent of TAT's own, and the two disagreeing would mean TAT
has a bug.

## 8. Two loose ends in `Define`

Small enough to be forgotten, big enough to bite.

- **How `Define`'s evaluator discharges `pat-completeness` and `termination`.**
  ARCHITECTURE §2.2 says `AoA` discharges them, but evaluation never searches
  (ARCHITECTURE §3.6); `Theorem` has a stored proof for this, `Define` has
  nothing yet. And what it emits for `termination` when the proof failed: it is
  a proof obligation, so `sorry` would discharge it, but which failures a node
  class papers over is that class's design and this one is not decided.
- **The table's `function` row covers all three forms**, `definition`
  included, so it shares a name with one of the forms it covers. "The `Define`'s
  `function` command failed" does not say which thing failed.
