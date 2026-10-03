# Open questions

Nothing here is settled. Ordered by what it blocks.

## 1. The remaining node classes

**Blocks:** most of what an agent would actually write.

`Datatype`, `QuotientType`, `Record`, `TypeClass`, `Text`, `Section`, `Context`
and `Locale` are unspecified. `Context` and `Locale` also need their two
omissibility flags (MCP_SPECIFICATION §2.1).

## 2. The AoA round

**Blocks:** a `Theorem` that is ever proven.

What connects `Proof_Job` to AoA is deferred to a design round of its own
(CONSTRUCT_INTERACTION §10): the drive path, driver and budget — a bound
on how many constructions run at once included —, the proof store, the
kinds of question the search asks, cancellation on the AoA side, how AoA
hands over a proof's replay times and exports its replay of one record,
and whether a construction job continues through a context change and repairs its
stored proof — today the default `_on_context_change` cancels it, and the
proof check finds a stale proof wanting. Two requirements bind that
round: AoA's `request` tool, which today lets the AoA agent add subgoals
in AoA's own global environment, reports instead to the TAT agent that
drives the job, as a question that agent answers (CONSTRUCT_INTERACTION
§3.4); and AoA is told that it runs under TAT and given a way to talk to
TAT. What `product` holds is decided: the method text AoA writes to its
proof store (THEOREM.md §1); the proof check replays it under limits
derived from the times recorded with it (THEOREM.md §7).

## 3. Where the `aoa` proof method lives

If it is defined in a theory, that theory must be in the base heap, and it is a
real import of every tree that uses it.

## 4. Whether to check completeness against Isabelle's own record

`sorry` leaves a `skip_proof` oracle on the theorem, and
`Thm_Deps.has_skip_proof`
(`contrib/Isabelle2025-2/src/Pure/thm_deps.ML:35-36`) finds it. In TAT's
own process every `Theorem` carries that oracle, since evaluation always
admits the statement (THEOREM.md §6); the account would have to be taken
of a build of the emitted files, where `by aoa` proves the theorems again
(ARCHITECTURE §2.1). Asking
Isabelle there whether any theorem carries the oracle is an account of
completeness independent of TAT's own, and the two disagreeing would mean
TAT has a bug.

## 5. Two loose ends in `Define`

Small enough to be forgotten, big enough to bite.

- **How `Define`'s evaluator discharges `pat-completeness` and `termination`.**
  ARCHITECTURE §2.2 says `aoa` discharges them, but evaluation never searches
  (ARCHITECTURE §3.6); `Theorem` has a construction job that finds a proof
  and an evaluation job that checks it (CONSTRUCT_INTERACTION §3), `Define`
  has nothing yet. And what it emits for `termination` when the proof
  failed: it is a proof obligation, so `sorry` would discharge it, but which
  failures a node class papers over is that class's design and this one is
  not decided.
- **The table's `function` row covers all three forms**, `definition`
  included, so it shares a name with one of the forms it covers. "The `Define`'s
  `function` command failed" does not say which thing failed.
