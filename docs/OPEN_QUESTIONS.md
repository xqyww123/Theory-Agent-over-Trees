# Open questions

Nothing here is settled. Ordered by what it blocks.

## 1. The framework's concrete interfaces

**Blocks:** every part of the node class contract.

The base classes and the ML registration API. To be given.

## 2. The remaining node classes

**Blocks:** most of what an agent would actually write.

`Datatype`, `QuotientType`, `Record`, `TypeClass`, `Text`, `Section`, `Context`
and `Locale` are unspecified. `Context` and `Locale` also need their two
omissibility flags (MCP_SPECIFICATION §2.1).

## 3. Tool granularity

One tool per node class, or one `edit` taking a class parameter. Per-class tools
give a typed schema per declaration kind and multiply the tool count — and since
plugins add node classes, they would add tools.

## 4. `construct` on one node or several

After laying out a skeleton the agent will want to construct many proofs at
once. Batching complicates the message model, since each is an independent
asynchronous activity.

## 5. What `Theorem` does when a running search is invalidated

The framework tells a node class that its context is no longer current and later
hands it the new one (ARCHITECTURE §3.6); what `Theorem` does with that is
not decided.

Ignoring the change is free and correct: evaluation replays proofs and never
searches, so a proof built against the old context is only a candidate either
way, and a failed replay starts a new search. Suspending the search and
re-running it against the new context saves a search when the change was
harmless, and costs a suspend-and-resume path through the AoA agent.

## 6. Where the `AoA` proof method lives

If it is defined in a theory, that theory must be in the base heap, and it is a
real import of every tree that uses it.

## 7. The entry point in production

A session begins with Isabelle calling into Python (ARCHITECTURE §9), and
something has to make Isabelle do that. An `isabelle` subcommand through a Scala
component is one form. During development an Isa-REPL app serves.

## 8. Whether to check completeness against Isabelle's own record

`sorry` leaves a `skip_proof` oracle on the theorem, and
`Thm_Deps.has_skip_proof`
(`contrib/Isabelle2025-2/src/Pure/thm_deps.ML:35-36`) finds it. Asking Isabelle
whether any theorem in a forest carries that oracle is an account of
completeness independent of TAT's own, and the two disagreeing would mean TAT
has a bug.

## 9. Two loose ends in `Define`

Small enough to be forgotten, big enough to bite.

- **What the `termination` role emits when its proof failed.** The role's entry
  in ARCHITECTURE §2.2 covers only the successful case. It is a proof
  obligation, so `sorry` would discharge it, but which failures a node class
  papers over is that class's design and this one is not decided.
- **The role named `function` now covers all three forms**, `definition`
  included, so it shares a name with one of the forms it covers. "The `Define`'s
  `function` role failed" does not say which thing failed.
