# Open questions

Nothing here is settled. Ordered by what it blocks.

## 1. The remaining node classes

**Blocks:** most of what an agent would actually write.

`Datatype`, `QuotientType`, `Record`, `TypeClass`, `Text`, `Section`, `Context`
and `Locale` are unspecified. `Context` and `Locale` also need their two
omissibility flags (MCP_SPECIFICATION §2.1).

## 2. `construct` on one node or several

After laying out a skeleton the agent will want to construct many proofs at
once. Batching complicates the message model, since each is an independent
asynchronous activity.

## 3. What `Theorem` does when a running search is invalidated

The framework tells a node class that its context is no longer current and later
hands it the new one (ARCHITECTURE §3.6); what `Theorem` does with that is
not decided.

Ignoring the change is free and correct: evaluation runs the stored proof and
never searches (ARCHITECTURE §3.6), so a proof built against the old context is
only a candidate either way, and a stored proof that fails leaves the node
`failed` for another `construct`. Suspending the search and re-running it against the new context
saves a search when the change was harmless, and costs a suspend-and-resume
path through the AoA agent.

## 4. Where the `AoA` proof method lives

If it is defined in a theory, that theory must be in the base heap, and it is a
real import of every tree that uses it.

## 5. The entry point in production

TAT is an Isabelle component (MODULE_STRUCTURE §1) and a pure MCP server
(ARCHITECTURE §9); open is the production launcher: what starts the Isabelle
process and calls `TAT_Framework.start` with a working directory and a port,
and in which order — Isabelle first, or a long-lived Python RPC host that
Isabelle processes join, each starting a conversation of its own. An
`isabelle` subcommand through a Scala component is one form. During
development the Isa-REPL app of `Dev/TAT_Dev.thy` serves.

## 6. Whether to check completeness against Isabelle's own record

`sorry` leaves a `skip_proof` oracle on the theorem, and
`Thm_Deps.has_skip_proof`
(`contrib/Isabelle2025-2/src/Pure/thm_deps.ML:35-36`) finds it. Asking Isabelle
whether any theorem in a forest carries that oracle is an account of
completeness independent of TAT's own, and the two disagreeing would mean TAT
has a bug.

## 7. Two loose ends in `Define`

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
