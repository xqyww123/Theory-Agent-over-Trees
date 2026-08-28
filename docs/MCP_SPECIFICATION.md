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
| `evaluate_to` | Set the caret and wait for checking to reach it |
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

A `recall` of a node past the caret reports it as unevaluated. Reading does not
advance evaluation: TAT submits commands, so nothing is checked unless TAT asks
for it.

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
TAT sends the affected node's data to the evaluator, the evaluator runs its
commands and reports the transcript and results, and TAT writes the `.thy` from
the transcripts (ARCHITECTURE §5.1).

Results therefore arrive as the return of the call that caused them. There is no
window in which a result from an earlier version of the file can be mistaken for
a current one.

## 4. The caret

One caret. It points at exactly one node.

- Editing a node makes that node the caret.
- Isabelle evaluates up to the caret and no further, because TAT submits no
  commands past it.
- `evaluate_to(node_id)` moves the caret. It blocks for up to 30 seconds; if
  evaluation has not reached the target by then it returns and evaluation
  continues in the background.

A node counts as **evaluated** when its evaluator has reported on every command
it ran. Nodes after the caret report as unevaluated, which is what they are.

## 5. Messages

MCP has no channel that reliably delivers a server-initiated message to the
model, so TAT attaches its messages to tool results.

- When a node finishes evaluating, its new state is attached to the next tool
  result.
- A node that has been evaluating for 30 seconds with no change produces a
  message saying so, repeated every 30 seconds. A proof that will never
  terminate looks exactly like one that is merely slow, and only elapsed time
  distinguishes them.
- `status` returns the pending messages on demand, for an agent that wants them
  before its next edit.

## 6. Undecided

- **One tool per node class, or one `edit` with a class parameter.** Per-class
  tools give the agent a typed schema per declaration kind and multiply the tool
  count by the number of node classes; a single `edit` keeps the surface small
  and weakens the schema to a union.
- **The omissibility flags for `Locale` and `Context`**, along with the rest of
  those two node classes.

Resolution and shortest-form printing are the same problem Isabelle solves for
its own name spaces; `Name_Space.extern` computes the shortest unambiguous
external name.
- **Imported trees.** Evaluation is bounded by the caret for a tree that nothing
  imports. Whether a tree that other open trees import is pushed further along
  by their requirements has not been measured.
