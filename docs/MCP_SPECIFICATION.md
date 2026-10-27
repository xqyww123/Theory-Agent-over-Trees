# TAT's MCP interface

What TAT exposes to the agent. For the model underneath, see
[ARCHITECTURE.md](ARCHITECTURE.md).

TAT runs as its own Model Context Protocol (MCP) server, named TAT.

## 1. Tools

| Tool | Purpose |
| --- | --- |
| `edit` | Add nodes, or amend one — replace it, its children inherited (§3.1) |
| `delete` | Remove a node or a subtree |
| `move` | Reorder a node within its tree, or move it to another tree or `Session` |
| `recall` | Read the forest: a node by id, or the whole of it |
| `evaluate_to` | Evaluate everything not yet evaluated, up to a node; run the evaluation jobs, or not |
| `construct` | `Start the construction jobs of nodes, such as proof constructions.` — the titles spliced in at start |
| `cancel_construct` | `Cancel the running construction jobs of nodes.` |
| `check_construct` | Wait for the agent's jobs or its messages |
| `answer` | `Answer the question a construction job asked you` |

Of the four construct tools (CONSTRUCT_INTERACTION §5), `construct`,
`cancel_construct` and `answer` exist only when a loaded node class
names a construction job class, and `check_construct` when one names a
job class of either kind. `construct` and
`cancel_construct` take a list of node ids, a non-leaf node standing for
every node under it, and no class arguments; they act on the nodes that
have a construction job, skip those they cannot act on, and are refused
only when the call names no node with one (`` `theory_X.section_Basics`
has nothing to construct. ``). On a `Theorem` `construct` starts the
proof construction, which asks its questions through `answer` and
reports through the messages of §5. Both tools, and `edit`, also set
the nodes' automatic construction (`auto_construct`): while it is on,
an evaluation that reaches the node starts its construction job when
the node needs it.

`move` exists because order carries meaning at theory level: a lemma must follow
everything it uses. Reordering and re-homing declarations is what a tree does
better than text.

TAT has no dependency query and no rename. Isabelle's own errors
report what broke and why, including when a node fails because something it
depends on failed. A rename that does not know every use site is `edit` with
extra steps, and knowing every use site is the dependency analysis TAT does not
do.

### 1.1 `recall`

Reading the forest: a node by id, rendered in depth, or, with no id, the
briefing of the whole forest, every node on one line (PRINT.md §5), and
nothing else; the quickview,
which closes the body of the results of the tools that change the forest, evaluate it,
or start or cancel a construction job, renders the forest around the
nodes the call was about. Its document, the call included, is RECALL.md.

A `recall` of a node that has not been evaluated reports it as such. Reading
never evaluates: TAT submits the commands, so nothing runs unless TAT asks for
it.

What Isabelle or the AFP already provide — theorem search over material TAT
did not write — is not `recall`'s business. That will be a separate `query`
tool, not yet designed; its errors are designed with it.

## 2. Naming nodes

Every node has a **name** and an **id**. The agent addresses nodes by id.

A node's identity is an opaque number that survives renaming and moving; the
id renders its position and id component, not that identity, so a rename
never disturbs results already in flight.

The name is what the agent supplied, as the node class's `gen` set it —
one field of the construct, or a name computed from its fields: a
`Theorem`'s theorem name, a `Section`'s or a `Text`'s `name`, written
into no command (node_classes/SECTION_AND_TEXT.md §2), a `Theory`'s
short name, a `Session`'s Isabelle session name, a `Datatype`'s type
names joined with `_` (node_classes/DATATYPE.md §2). The framework makes
the node's **id component** from it, the kind joined to the name —
`lemma_P`, `theorem_Q`, `corollary_R`, `section_Basics`, `text_intro`,
`datatype_expr_bexp`, `theory_X`, `session_Arith`; a kind keeps to the
name grammar below, which
the loader checks when the class registers (PLUGIN_SYSTEM §5). The tree
root is a `Theory` node, and it owns
the theory header, the `imports` list and the `end`; above the trees, the
forest's first layer is its `Session` nodes (ARCHITECTURE §2), omissible in
both directions (§2.1).

The id is the dotted sequence of the id components of a node's ancestors
and its own — `theory_X.section_Basics.lemma_P`. A name is therefore a
letter followed by letters, digits, underscores, primes (`'`) and interior
hyphens — a hyphen or underscore may not end a name, and a hyphen may not
begin one — and the framework refuses one outside this grammar
(`InvalidName`, rendering the agent's own spelling). Hyphens exist for
`Session` names like `HOL-Library`; a class whose names must be Isabelle
identifiers, such as `Theory` and `Theorem`, rejects them in its `gen`
first, with its own rendering of `InvalidName`. A `Theory`'s and a
`Session`'s names become path elements — `<session>/<short name>.thy` —
and so take no prime either: each class judges its own grammar first
(node_classes/SESSION_AND_THEORY.md), with its own rendering
(RENDER_BASELINES §2). TAT refuses a name that would give two nodes the
same id.

The forest root has the id **`Sessions`**, which no node's id component can
be, an id component always carrying an underscore. `edit`'s `append` on it
creates a `Session`; every other action on it is refused (`ProtectedNode`).

A theory's name must also be unique against everything already loaded. Isabelle
compares theory identities by **short name** — the part after the last dot
(`contrib/Isabelle2025-2/src/Pure/context.ML:380-383`) — so a tree named `List`
builds without complaint and then kills the first theory that imports it, one
level downstream, with `Duplicate theory name` and no useful location.
`Theory.gen` therefore rejects a name whose short name already appears in
the base heap, and the framework one already borne in the forest or in the
same call, through the class's `namespace` (`DuplicateTheoryShortName`) —
excluding, on an amend, the node being replaced (MODULE_STRUCTURE §4.2).

### 2.1 Which components appear

Each **node class** declares three id properties: whether its id component
may be omitted from an id TAT **prints**, whether it may be omitted from an
id the agent **supplies**, and its **drop priority** — which output-omissible
component goes first when several could go.

`Session`, `Theory` and `Section` are omissible in both directions; their drop
priorities order them `Section` first, then `Session`, then `Theory` last. The
framework's defaults make a class compulsory in both directions with drop
priority 0; an omissible class declares otherwise, and a leaf, whose
component ends every id, declares nothing. A
node class that is omissible on output but compulsory on input would let TAT
print an id it then refuses to accept; TAT rejects that combination when the
class is loaded.

**Printing.** Starting from the full id, TAT repeatedly deletes one
component: among the output-omissible components whose deletion leaves the id
identifying exactly one node, the one with the lowest drop priority — the
outermost of them when several tie — until none can go. Ambiguity is judged
across the whole forest, so an id renders identically wherever it appears —
there is no notion of a current tree for it to depend on. So
`session_Arith.theory_X.section_B.lemma_P` shortens through
`session_Arith.theory_X.lemma_P` and `theory_X.lemma_P` to `lemma_P`,
stopping at the first form something else in the forest collides with.

**Reading.** TAT accepts any id obtained from the full one by dropping
input-omissible components — never the node's own, the component every
form ends with. All four of these reach the same node when nothing
else in the forest ends the same way:

```
theory_X.section_Basics.lemma_P
theory_X.lemma_P
section_Basics.lemma_P
lemma_P
```

When more than one node matches, TAT rejects the call and lists the candidates
rather than choosing one — unless the id equals one candidate's full id,
component for component with nothing dropped: the exact match wins. Siblings'
id components are unique, so at most one node matches exactly; a full id therefore
always designates its node, and every id TAT prints resolves back to the node
it was printed for.

Resolution and shortest-form printing are the same problem Isabelle solves for
its own name spaces; `Name_Space.extern` computes the shortest unambiguous
external name.

### 2.2 The id and Isabelle's qualified name

The id is TAT's name for a node: its ancestors' id components and its own,
joined (§2). The qualified name is Isabelle's name for what the node declares:
`theory_X.lemma_P` declares `X.P`, and `theory_X.locale_foo.lemma_P` declares
`X.foo.P`.
A `Section` is in the id, being an ancestor, and not in the qualified name,
being no scope to Isabelle.

The two correspond, and the flags of §2.1 echo the correspondence: a nesting
class Isabelle sees no scope in, such as `Section`, drops first. The class
declarations of §2.1 are the authority, though — `Session` and `Theory` are
droppable even while they qualify Isabelle's names, the id being TAT's name
and not Isabelle's. Shortest-form printing of an id is the same computation
as Isabelle's shortest-form printing of a qualified name.

The **id** changes on an amend that changes the node's kind or its name —
a `Theorem`'s `kind`, a `Datatype`'s type names — and on
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

### 3.1 What `edit` takes

Its argument shape is TOOL_SCHEMAS.md §1: one of four actions, and a list
of constructs. A construct (ARCHITECTURE §1) is a JSON object whose `kind`
field selects the node class — a class answers to the kinds its schema
names, so `Theorem` answers to `lemma`, `theorem`, `corollary` and
`proposition` — and
whose other fields are that class's own: the framework enforces their
mechanical shape from the class's declared schema, and the class is the
authority on their meaning: its `gen` at the edit, for what keeps the
node from being built, and its field check at evaluation, for the rest
(PLUGIN_SYSTEM §2). A nesting class
takes its contents in a `children` field, a list of constructs again; the
field's name is the same for every class. In place of the list, the
value `GivenLater` says the contents come in later calls: where the
class declares `children`, a construct carrying it is taken as one
without `children`, an amend's replacement included; anywhere else it
is refused as any `children` is. It is what a client shown the schema
without recursion (PLUGIN_SYSTEM §4) writes.

**Adding** — `append`, `insert_before` and `insert_after` (TOOL_SCHEMAS.md
§1) — links the constructs, in order, at the destination.

**Amending** replaces the addressed node with the first construct. The
node's children are inherited, never resupplied: a replacement carrying
`children` is rejected, as is a leaf replacement when the node has
children (EXCEPTIONS.md). The node's identity (§2) passes to the
replacement — a rename is an amend, and results in flight still find the
node — and a construction job running on it is cancelled, its owner
told the node was amended (CONSTRUCT_INTERACTION §3.2). Which of the
node's recorded fields survive is its class's judgement, made in `gen`
through `config.replaces()` (MODULE_STRUCTURE §4.1). The construction
job's outcome survives when the class answers the commit's
`_carries_job_from(old)` with true (CONSTRUCT_INTERACTION §3.1):
`Theorem` does when `for_any`, `premises` and `conclusion` are
unchanged (node_classes/THEOREM.md §4), so a rename, a change of `kind`
or a reworded `english` costs no search. Constructs after the first are added after the replacement,
so one call turns a lemma into a definition and two lemmas.

An `edit` is atomic: nothing touches the forest until every construct
has been built and checked (MODULE_STRUCTURE §4.2), so it applies whole
or leaves the forest exactly as it was, and the error names the element
and field at fault (EXCEPTIONS.md).

### 3.2 What follows

Editing a node invalidates that node, everything after it in its tree —
for a move, also what followed it where it left — and every tree that
imports either tree (ARCHITECTURE §3.4) — unconditionally.
Whether the call also evaluates is the agent's choice: `edit` and `move`
each take a mandatory boolean `evaluate` (TOOL_SCHEMAS.md); `edit`'s
optional `auto_construct` turns the new nodes' automatic construction
on, with or without `evaluate` (CONSTRUCT_INTERACTION §3.3).
With `evaluate` true, the call runs `evaluate_to` on the change's natural
destination — the last node the call submitted, in tree order; for a
`move`, the moved node — with `ignore_error` unset and `checks`
`"quick"`, so the result comes back with the call and the evaluation jobs
it started run on in the background, counted in the result's last line
(CONSTRUCT_INTERACTION §5); a nesting node is reached at its ending
command (ARCHITECTURE §3.5), so a submitted subtree is evaluated whole.
With `evaluate`
false, nothing is evaluated — only the edit's own invalidation runs,
inside its commit (MODULE_STRUCTURE §4.2) — and the
quickview shows the new nodes `not evaluated`, for a later
`evaluate_to`. `delete` takes no such flag: there is nothing new to see,
and only the invalidation runs (ARCHITECTURE §3.5). Replacing a nesting node invalidates from its first
child, since the children come before its own commands in the walk
(ARCHITECTURE §3.5). Whatever is invalidated and not evaluated is
reported as such until the agent asks for it. What a successful call
returns — the `Done` line and the quickview — is TOOL_SCHEMAS.md §4.

## 4. Evaluation

`evaluate_to(node_id, ignore_error, checks)` — the tool, TOOL_SCHEMAS.md
§5; the recursion behind it is MODULE_STRUCTURE §4.1's — evaluates every
node that is not evaluated, in
tree order, up to and including the destination — a nesting node's whole
subtree, so the `Theory` node's id means the whole tree, `end` included.
It returns when every tree it ran has finished or stopped, naming the
first stopped node in tree order, which for a blocked tree may lie in a
tree it imports, and for a destination under a nesting node whose
beginning failed is that node. `ignore_error` carries on past a stop
inside a tree; it enters neither a nesting node whose beginning failed
nor a tree whose import has no theory value, and with it set neither of
those two is reported — only the order constraint's stop is
(ARCHITECTURE §3.3).
Its result opens with `Evaluation reached theory_X.` or `Evaluation
stopped at definition_f.` (TOOL_SCHEMAS.md §4, RENDER_BASELINES §6), the
order constraint's sentence under a stop of that kind, then the
quickview. Where evaluation stops, which stops the flag can pass, and
which later calls the same node stops, is ARCHITECTURE §3.3.
`checks` says what becomes of the evaluation jobs the walk would start on
the nodes it passes — a `Theorem`'s proof check, when it holds a proof
and no stored check (CONSTRUCT_INTERACTION §3.3): `"no"`
starts none; `"quick"`, the default, starts them and leaves them running
in the background, the result's last line counting them; `"blocking"`
starts them and returns only when every evaluation job running on a node
the walk passed has ended, their failures riding on the same result as
messages (§5).

Each node renders its own part of the result: what its class chose to report,
and whether it is `finished` (ARCHITECTURE §3.2).

## 5. Messages

Evaluation is synchronous, so a result arrives as the return of the call that
caused it. The result of a call that holds the forest's lock — `edit`,
`move`, `delete`, `evaluate_to` — describes the forest as of the moment the
call released it; another agent's call may have changed it since
(ARCHITECTURE §9). A read — `recall`, the future `query` — is advertised
with MCP's `readOnlyHint`, takes no lock and reads the forest in memory,
never the database, as it stands at that instant: whole (MODULE_STRUCTURE
§4.2), and with evaluation possibly under way, since an evaluating call
changes statuses one node at a time, and a job's settlement lands between
two of its awaits (CONSTRUCT_INTERACTION §9). The four construct tools
take no lock either, each synchronous from its checks to its change;
`check_construct` changes no node and no job and is advertised
read-only like `recall` — delivering the caller's messages, which every
tool result does, is no change. The seen
set (PRINT.md §4) is each agent's, written by every rendering and cleared
by that agent's compaction, taking no lock of its own, rendering being
synchronous.

Two kinds of work outlive a call (CONSTRUCT_INTERACTION §3): a
construction job — a `Theorem`'s proof construction, started with
`construct` or automatically by an evaluation, owned by the agent whose
call started it, which may ask that agent a question — and an evaluation job — a `Theorem`'s proof check, started by
an evaluation under `checks`, reporting to the agent whose call ran it.

MCP has no channel that reliably delivers a server-initiated message to the
model, so TAT attaches such messages to tool results: each agent has a
mailbox, and every tool result of that agent's — whatever the tool —
carries, after its body and before its trailer, the messages waiting
there, filtered at delivery so that a cancelled
or dropped job leaves nothing of its own behind (CONSTRUCT_INTERACTION
§3.4); the node's state is the record, the message a notification.
`check_construct` waits for a message or a job's end, so an agent that
wants them before its next edit calls it; a blocked stop's reason
(CONSTRUCT_INTERACTION §7) carries no message, only what to call.

## 6. Undecided

- **The omissibility flags for `Context`**, along with the rest of that
  node class (OPEN_QUESTIONS §1).
