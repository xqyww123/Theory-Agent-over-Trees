# Open questions

Decisions not yet made. Nothing here may be treated as settled, and no code
should assume an answer. Ordered by how much they block.

## 1. Who writes a `Theorem` node's proof body?

**Blocks:** the node class design for `Theorem`, and whether TAT has to host two
execution models at once.

Three candidates:

1. The proof is one opaque block of text the agent writes; TAT only reports
   whether it checked.
2. A `Theorem` node contains an embedded **AoA proof tree** — interactive,
   stepwise, with live goal states. AoA runs on Isa-REPL, so this means running
   PIDE and Isa-REPL side by side.
3. TAT only emits an automatic tactic (`by aoa` and similar) and reports failure
   otherwise.

Note the interaction with the substrate decision: Isa-REPL is rejected for
shipping (SUBSTRATE_RESEARCH §3), which makes option 2 considerably more
expensive than it first appears.

Recommendation on record: start with option 1 and keep the interface open for
option 2. Not agreed.

## 2. Substrate: LSP via Isabelle-MCP, or headless PIDE in Scala?

**Blocks:** essentially all implementation.

Both are the same engine; see SUBSTRATE_RESEARCH §6 for the comparison table.
Route 1 reuses a mature, well-tested completion model and costs far less to
start. Route 2 removes a class of staleness and snapshot-consistency risk
structurally, and makes the partition cross-check cheap, at the cost of a real
Scala edit layer and a per-release port.

Leaning on record: route 1, given that Isabelle-MCP is robust in practice and
that its Scala component is already a fork we can extend when a specific need
arises. Not formally decided.

## 3. ~~Does the full-text `didChange` defeat PIDE's prefix reuse?~~ RESOLVED

**Answered by experiment: yes, it does.** Moved to
[EXPERIMENTS.md §1](EXPERIMENTS.md); the consequence is recorded in
ARCHITECTURE §9.

What remains open is only what TAT does about it — send ranged edits itself, or
fix the call site in Isabelle-MCP. See §7 below.

## 4. What does the agent see inside the freshness window?

**Blocks:** the tool contract.

Cached decorations are distrusted for `DECORATION_GRACE` (2.0 s) after every
edit-send. Options: block and poll until the verdict is trustworthy (as
`isabelle_evaluate_to` does), or return immediately with an explicit `PENDING`
per node.

Related: whether to close the window properly by adding a version or a
content-hash handshake to the forked Scala server — see ARCHITECTURE §7.2.

## 5. Remaining node class specifications

`Datatype`, `Quotient Type`, `Record`, `TypeClass`, `Text`, `Section` have not
been specified. `Theorem` and `Define` are in ARCHITECTURE §2.

## 6. Forest-to-session mapping

How trees map onto Isabelle sessions, which session TAT launches, and how a tree
that another tree imports is made available. Note Isabelle-MCP's constraint that
the launched session must not precompile the theories being edited.

## 7. Isabelle-MCP refactor scope

TAT needs `IsabelleLSPClient`, the lifespan and the file watcher extractable
without importing Isabelle-MCP's tool surface (ARCHITECTURE §8). How far to go,
and whether those changes land in Isabelle-MCP or in a shim inside TAT.
