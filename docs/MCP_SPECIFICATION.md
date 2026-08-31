# TAT's MCP interface

What TAT exposes to the agent. For the model underneath, see
[ARCHITECTURE.md](ARCHITECTURE.md).

TAT runs as its own Model Context Protocol (MCP) server, named TAT.

## 1. Tools

| Tool | Purpose |
| --- | --- |
| `edit` | Add a node, or change an existing node's attributes |
| `delete` | Remove a node or a subtree |
| `move` | Reorder a node within its tree, or move it to another tree or `Session` |
| `recall` | Retrieve — from the forest, or from the Isabelle library |
| `construct` | Start a node's own operation, where its class has one |
| `evaluate_to` | Evaluate everything not yet evaluated, up to a node |
| `status` | Collect pending messages |

`construct` is generic: it dispatches to the node class, and a class without one
reports that it is not supported. On a `Theorem` it starts the proof search.
Whether it takes one node or several is undecided (OPEN_QUESTIONS §4).

`move` exists because order carries meaning at theory level: a lemma must follow
everything it uses. Reordering and re-homing declarations is what a tree does
better than text.

TAT has no dependency query and no rename. Isabelle's own errors
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

A node's identity is an opaque number that survives renaming and moving; the
id renders its position and name, not that identity, so a rename never
disturbs results already in flight.

The name comes from the node class. A `Theorem`'s name is its `kind` joined to
its theorem name — `lemma_P`, `theorem_Q`, `corollary_R`. A `Section`'s and a
`Text`'s are chosen by the agent. The tree root is a `Theory`
node whose name is the theory's, and which owns the theory header, the `imports`
list and the closing `end`.

Above the trees, the forest's first layer is its `Session` nodes
(ARCHITECTURE §2.2): a `Session`'s name is its Isabelle session name, written
`session_<name>` in an id, and omissible in both directions (§2.1).

The id is the dotted sequence of the names of a node's ancestors and its own —
`theory_X.section_Basics.lemma_P`. TAT refuses a name that would give two nodes
the same id.

A theory's name must also be unique against everything already loaded. Isabelle
compares theory identities by **base name** — the part after the last dot
(`contrib/Isabelle2025-2/src/Pure/context.ML:380-383`) — so a tree named `List`
builds without complaint and then kills the first theory that imports it, one
level downstream, with `Duplicate theory name` and no useful location.
Creating a tree — an `edit` adding a `Theory` node — therefore rejects a name
whose base name already appears in the base heap or in the forest.

### 2.1 Which components appear

Each **node class** declares two independent properties: whether its name may be
omitted from an id TAT **prints**, and whether it may be omitted from an id the
agent **supplies**.

`Session`, `Theory` and `Section` are omissible in both directions. A node class that is
omissible on output but compulsory on input would let TAT print an id it then
refuses to accept; TAT rejects that combination when the class is loaded.

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

### 2.2 The id and Isabelle's qualified name

The id is TAT's name for a node: its ancestors' names and its own, joined
(§2). The qualified name is Isabelle's name for what the node declares:
`theory_X.lemma_P` declares `X.P`, and under `locale foo` it declares `foo.P`.
A `Section` is in the id, being an ancestor, and not in the qualified name,
being no scope to Isabelle.

The two correspond, and the omissibility flags (§2.1) are that correspondence:
a nesting class Isabelle sees no scope in, such as `Section`, is droppable from
an id; one that qualifies Isabelle's names is not. Shortest-form printing of an
id is the same computation as Isabelle's shortest-form printing of a qualified
name.

The **id** changes on a rename, on a change of a `Theorem`'s `kind`, and on
any move except between positions under the same parent; a move can also
change the printed short form alone, by creating or removing an ambiguity.
The **qualified name** changes only on a move into or out of a `Locale` or a
`Context`, or into another tree — the moves after which a statement written
against a context's assumptions may no longer hold, and references to the
fact may break.

## 3. Running a change

An edit reaches Isabelle by being evaluated, not by being written to a file.
TAT sends the affected node's data to its evaluator, the evaluator runs the
node's commands and reports what happened, and the `.thy` is written
later from what the nodes emit (ARCHITECTURE §4).

Editing a node invalidates that node, everything after it in its tree, and
every tree that imports that tree (ARCHITECTURE §3.4), then runs `evaluate_to`
on it (§4), so its own result comes back with the call. Everything else
invalidated is reported as not evaluated until the agent asks for it.

## 4. Evaluation

`evaluate_to(destination, ignore_error)` evaluates every node that is not
evaluated, in tree order, up to and including the destination — a nesting
node's whole subtree, so the `Theory` node's id means the whole tree, `end`
included. It returns when it has finished or when it has stopped, naming the
node it stopped at; `ignore_error` carries on past a node that would stop it.
Where evaluation stops, and why the same node stops every later call until it
is edited, is ARCHITECTURE §3.3.

Each node renders its own part of the result: what its class chose to report,
whether it is `finished` (ARCHITECTURE §3.2), and — when it cannot be
evaluated because of another node — which one (ARCHITECTURE §3.3).

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

- **One tool per node class, or one `edit` with a class parameter**
  (OPEN_QUESTIONS §3).
- **The omissibility flags for `Locale` and `Context`**, along with the rest of
  those two node classes (OPEN_QUESTIONS §2).
