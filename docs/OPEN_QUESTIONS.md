# Open questions

Nothing here is settled. Ordered by what it blocks.

## 1. The channel between Python and Isabelle

**Blocks:** everything that crosses the boundary, which is most of the design.

The Python side owns the forest and serves the MCP tools; the ML side runs the
evaluator. Both directions are needed: Python drives evaluation, and the
evaluator calls back — a node class asking for another variant, `construct`
relaying between AoA and the tree.

In this repository, `contrib/Isabelle_RPC` is ML to Python over MessagePack with
callbacks, and Isa-REPL's answer to the other direction is a socket server.

## 2. What the agent sees when an upstream node fails

**Blocks:** the tool contract, and the evaluator's loop.

A failing node leaves its fact undeclared, so every later node using it fails
too. TAT owns the evaluator, so it chooses: keep going from the state before the
failure, or stop. And a node that fails because something above it failed should
not read like a node that is itself wrong.

## 3. `construct` on one node or several

After laying out a skeleton the agent will want to construct many proofs at
once. Batching complicates the message model, since each is an independent
asynchronous activity.

## 4. Tool granularity

One tool per node class, or one `edit` taking a class parameter. Per-class tools
give a typed schema per declaration kind and multiply the tool count — and since
plugins add node classes, they would add tools.

## 5. The remaining node classes

`Datatype`, `QuotientType`, `Record`, `TypeClass`, `Text`, `Section`, `Context`
and `Locale` are unspecified. `Context` and `Locale` also need their two
omissibility flags (MCP_SPECIFICATION §2.1).

## 6. Where the `AoA` proof method lives

If it is defined in a theory, that theory must be in the base heap, and it is a
real import of every tree that uses it.

## 7. The framework's concrete interfaces

The base classes and the ML registration API. To be given.
