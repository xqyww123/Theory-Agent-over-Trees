# TAT's MCP interface

What TAT exposes to the agent. For the model underneath, see
[ARCHITECTURE.md](ARCHITECTURE.md).

TAT runs as its own MCP server, named TAT.

## 1. Tools

| Tool | Purpose |
| --- | --- |
| `edit` | Add a node, or change an existing node's attributes |
| `delete` | Remove a node or a subtree |
| `move` | Reorder a node within its tree, or move it to another tree |
| `recall` | Retrieve — from the forest, or from the Isabelle library |
| `new_theory` | Start a new tree |
| `construct` | Start a node's own operation, where its class has one |
| `evaluate_to` | Evaluate everything not yet evaluated, up to a node |
| `status` | Collect pending messages |

`construct` is generic: it dispatches to the node class, and a class without one
reports that it is not supported. On a `Theorem` it starts the proof search.
Whether it takes one node or several is undecided.

`move` exists because order carries meaning at theory level: a lemma must follow
everything it uses. Reordering and re-homing declarations is what a tree does
better than text.

There is deliberately no dependency query and no rename. Isabelle's own errors
report what broke and why, including when a node fails because something it
depends on failed. A rename that does not know every use site is `edit` with
extra steps, and knowing every use site is the dependency analysis TAT does not
do.

### 1.1 `recall`

One tool, two indexes:

- **the forest** — what has this project already declared? Retrieval by node id
  or by query, plus, with no query, the outline of the forest.
- **the library** — what does Isabelle or the AFP already provide? This is
  theorem search over material TAT did not write.

A detail level selects between a summary rendering and the full one.

A `recall` of a node that has not been evaluated reports it as such. Reading
never evaluates: TAT submits the commands, so nothing runs unless TAT asks for
it.

## 2. Naming nodes

Every node has a **name** and an **id**. The agent addresses nodes by id.

Internally a node is a persistent opaque number that survives renaming and
moving. The id is a rendering of that node's position and name, not its
identity, so results already in flight are never disturbed by a rename.

The name comes from the node class. A `Theorem`'s name is its `kind` joined to
its theorem name — `lemma_P`, `theorem_Q`, `corollary_R`. A `Section`'s and a
`Text`'s are chosen by the agent. The tree root is a `Theory`
node whose name is the theory's, and which owns the theory header, the `imports`
list and the closing `end`.

The id is the dotted sequence of the names of a node's ancestors and its own —
`theory_X.section_Basics.lemma_P`. TAT refuses a name that would give two nodes
the same id.

A theory's name must also be unique against everything already loaded. Isabelle
compares theory identities by **base name** — the part after the last dot
(`contrib/Isabelle2025-2/src/Pure/context.ML:381-384`) — so a tree named `List`
builds without complaint and then kills the first theory that imports it, one
level downstream, with `Duplicate theory name` and no useful location.
`new_theory` therefore rejects a name whose base name already appears in the
base heap or in the forest.

### 2.1 Which components appear

Each **node class** declares two independent properties: whether its name may be
omitted from an id TAT **prints**, and whether it may be omitted from an id the
agent **supplies**.

`Theory` and `Section` are omissible in both directions. A node class that is
omissible on output but compulsory on input would let TAT print an id it then
refuses to accept; the registry rejects that combination.

**Printing.** TAT omits an omissible component when the shorter id still
identifies exactly one node. Ambiguity is judged across the whole forest, so an
id renders identically wherever it appears — there is no notion of a current
tree for it to depend on.

**Reading.** TAT accepts any id obtained from the full one by dropping
input-omissible components. All four of these reach the same node when nothing
else in the forest ends the same way:

```
theory_X.section_Basics.lemma_P
theory_X.lemma_P
section_Basics.lemma_P
lemma_P
```

When more than one node matches, TAT rejects the call and lists the candidates
rather than choosing one.

Resolution and shortest-form printing are the same problem Isabelle solves for
its own name spaces; `Name_Space.extern` computes the shortest unambiguous
external name.

### 2.2 What changes an id

Renaming a node changes its id. So does changing a `Theorem`'s `kind`, since the
`kind` is part of the name.

Moving a node changes its id only when its qualifying ancestors change — moving
between positions under the same parent, or into another `Section`, does not.
Moving into or out of a `Locale` or a `Context`, or into another tree, does.
Those are also the cases where Isabelle's own qualified name for the fact
changes, and where a statement written against a context's assumptions may no
longer hold.

## 3. Running a change

An edit reaches Isabelle by being evaluated, not by being written to a file.
TAT sends the affected node's data to its evaluator, the evaluator runs the
node's commands and reports the result of each role, and the `.thy` is written
later from what the nodes emit (ARCHITECTURE §4).

Editing a node invalidates that node and everything after it, then runs
`evaluate_to` on it (§4), so its own result comes back with the call. Everything
after it is reported as not evaluated until the agent asks for it.

## 4. Evaluation

`evaluate_to(destination, ignore_error)` evaluates every node that is not
evaluated, in tree order, up to and including the destination. It returns when
it has finished or when it has stopped.

Evaluation stops at a node whose class says nothing useful can follow it —
typically a definition that failed, since every later mention of the constant
would then report the constant rather than itself. `ignore_error` carries on past
such a node. It cannot carry on into the children of a nesting node whose opening
command failed: those have no context to run in.

Each node reports two things, and they answer different questions
(ARCHITECTURE §3.2): whether it has a current evaluation, and whether it still
owes anything. A `Theorem` awaiting a proof has a perfectly good evaluation and
still owes a proof. A node left unevaluated because evaluation stopped ahead of
it names the node that stopped it.

## 5. Messages

Evaluation is synchronous, so a result arrives as the return of the call that
caused it. There is no window in which a result can be mistaken for one
belonging to an earlier version of the forest.

`construct` is the exception: it starts a proof search that outlives the call.

MCP has no channel that reliably delivers a server-initiated message to the
model, so TAT attaches such messages to tool results: when a search finishes, the
node's new state rides on the next tool result. `status` returns the pending
messages on demand, for an agent that wants them before its next edit.

## 6. Undecided

- **One tool per node class, or one `edit` with a class parameter.** Per-class
  tools give the agent a typed schema per declaration kind and multiply the tool
  count by the number of node classes; a single `edit` keeps the surface small
  and weakens the schema to a union.
- **The omissibility flags for `Locale` and `Context`**, along with the rest of
  those two node classes.
