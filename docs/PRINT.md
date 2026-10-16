# Rendering

Status: decided (2026-09-21, after two design reviews; the quickview's
focus and depth 2026-09-22; the marks, the fields, the blocks and the
summary 2026-09-30 with CONSTRUCT_INTERACTION.md), except §8.

Every node renders itself through one method, in a **print mode** that
says what the reader is looking at, and at a **depth**, the number of
levels below the rendering's starting node:

```python
class Out_Focus: ...                        # not on the path to a focus: the node itself, no children
class Briefing: ...                         # the briefing: every node, to the bottom
@dataclass(frozen=True)
class Relative_Focus:                       # the quickview: every node of `nodes` is a focus, with what lies
    nodes: frozenset[Node]                  #   `depth` levels under it — its whole subtree at -1; a node
    depth: int                              #   above one is on the path
class Recall: ...                           # the recalled node and what is under it
PrintMode = Out_Focus | Briefing | Relative_Focus | Recall

def print(self, indent: int, out: TextIO, mode: PrintMode, depth: int) -> None         # the framework's: the line, print_fields, the messages, the jobs' blocks, the children, the summary
def print_fields(self, indent: int, out: TextIO, mode: PrintMode, depth: int) -> None  # the class's: its fields; nothing by default
def mark(self, mode: PrintMode, depth: int) -> str                                     # the framework's default (§1); a class may override
def detailed(self, mode: PrintMode, depth: int) -> bool                                # a helper: true for a focus and for Recall below depth 2
```

`indent` is a level, two spaces each; `depth` is 0 at the node a
rendering starts from. Every rendering is one call of
`Forest.render(node, mode, agent)` (MODULE_STRUCTURE §4.1) — `agent` the
agent it is for, whose seen set (§4) `mark` and `print_fields` reach
through the forest — which calls `node.print(0, out, mode, 0)`; the
framework adds one to both for each level it descends, with the
exception §2 names.

## 1. The line and its mark

A node's first line is `- <id> (<mark>)`: the id in its shortest form
(MCP_SPECIFICATION §2.1) and the mark `mark(mode, depth)` returns, the
framework's tags after it inside the parentheses (CONSTRUCT_INTERACTION
§6); no node's line is bare. The lone session's line carries no dash,
and the forest root writes no line of its own: `Sessions:` is a header
(§6).

The framework's default `mark` reads the node's own operations' instant
statuses through `evaluation_statuses()` — none for a `Session`, one for
a leaf, the beginning and the ending for a nesting node (MODULE_STRUCTURE
§4.1) — and `finished` (ARCHITECTURE §3.2). The first row that applies
wins:

| the node | mark |
| --- | --- |
| is `finished` | `complete` |
| has an operation of its own that is an obstacle: `cannot_evaluate` (ARCHITECTURE §3.3) | `failed` |
| its first own operation is `not_evaluated` — never reached, invalidated, or blocked: under a nesting node whose beginning failed, or in a tree one of whose resolved imports has no theory value | `not evaluated` |
| otherwise | `incomplete` |

`incomplete` therefore means: the node's first own operation ran, and
either a later one did not — a nesting node stopped inside, whose ending
could not run after a stop in its tree — or something under it, or
something the node itself still owes, is unfinished; under `Recall` the
summary of §2 says what. A `Session` runs no operation and is `complete`
or `incomplete` by its trees. What blocks a `not evaluated` node is not on
its line: the `failed` marks say where the obstacles are, and the tool
that ran the evaluation names the first stop in its answer
(RENDER_BASELINES §6; MCP_SPECIFICATION §4). An `Error:` block (§3)
accompanies a `failed` line, a `Notice:` block a `complete` or
`incomplete` one — `incomplete` when the class still owes what the
notice is about.

A class overrides `mark` to say more, and reads its instant statuses
through `evaluation_statuses()` as the default does. `Proof_Obligation`
answers two slots, the class's status and its proof's
(node_classes/COMMON.md §3; `Theorem`'s words, node_classes/THEOREM.md
§7). Inside the parentheses, after the mark, the framework adds its
tags: `automatic construction` on a node whose construction job has that
setting on, for every agent, and after it `needs your answer, call
\`check_construct\` to
see it` on a node whose construction job waits for the agent the
rendering is for (CONSTRUCT_INTERACTION §6).
The framework's words are RENDER_BASELINES §5's; a class's words are its
own document's.

## 2. What each mode prints

The framework writes the line at `indent`, calls `print_fields` at
`indent + 1`, writes the messages and the blocks (below), then the
children at `indent + 1` and `depth + 1`. A line
that carries no dash is not a list item and opens no level — the forest
root's header and the lone session's line (§6) — so what a node writes under it,
its fields and its children alike, stays at `indent` while `depth` still
rises. The forest root writes no fields; the empty forest's hint, the
only line it writes under `Sessions:`, sits one level in (§6).

| mode | `print_fields` | children |
| --- | --- | --- |
| `Out_Focus` | called | none |
| `Briefing` | not called | every child, in `Briefing` |
| `Relative_Focus(nodes, depth)`, this node in `nodes` | called | `depth = 0`: every child in `Out_Focus`; otherwise every child in `Relative_Focus(the children, depth − 1)`, `-1` staying `-1` |
| `Relative_Focus(nodes, depth)`, a node of `nodes` under this one | called | every child that is in `nodes` or above one, in the same mode; every other child in `Out_Focus` |
| `Recall` | called | every child in `Recall`, while `depth < 3` |

So under `Relative_Focus` a node is one of three things: a **focus** — a
node of `nodes`, or under one within `depth` levels — which is detailed
and whose children are focuses one level shallower, the layer below the
last being lines only; on the **path**, above a focus, writing what it
writes off the focus; or in `Out_Focus`. `Forest.render` refuses an
empty `nodes`, a node of `nodes` outside the rendered node, and one
under another node of `nodes`.

The descent is the framework's; what a class writes under its line is
the class's, by mode and depth (§3). Four more things the framework
writes under a line: after `print_fields`, the operations' messages
(§3), and then (CONSTRUCT_INTERACTION §6), when the
node is detailed and not itself an obstacle, one **failure block** for
the construction job when its outcome is `FAILED` and one for the check
when `check_outcome()` is `FAILED`, in that order — the job class's `failure_header`, then the
message one level deeper, the header's colon a period when the message
is empty; a `None` header prints nothing; on
every detailed rendering, the seen set aside — and, under `Recall`, below
an `incomplete` nesting node at the last printed depth, the **summary**:
one line per group that has members — the nodes below it that are
`ready`, grouped by the title their `Unfinished` carries, construction
titles first, then evaluation titles, alphabetical within;
then the nodes `failed`, then the nodes `not evaluated`, nesting nodes
counted among them; ids in tree order, relative to the node, up to five,
the count alone past five; no period:

```
- section_Basics (incomplete)
  3 proof constructions incomplete: lemma_A, lemma_C, context_C.lemma_B
  12 proof checks incomplete
  1 node failed: definition_f
  2 nodes not evaluated: lemma_E, lemma_F
```

The summary appears under `Recall` alone, never in a quickview or the
briefing; the blocks appear wherever the node is detailed — a focus, or
`Recall` below depth 2 — and never in the briefing, which writes nothing
under a line but the empty forest's hint (§6) and the empty node's line.

The fourth: a nesting node with no children, in a mode that shows its
children — `Briefing`, `Relative_Focus`, `Recall` while `depth < 3` —
writes where its children would go the **empty node's line**, its id the
one its own line prints:

```
- theory_X (not evaluated)
  Empty so far. Call `edit` with action `append` and target_id `theory_X` to add children.
```

## 3. Fields and messages

A class writes its fields in `print_fields`, one per line, and only under
`Recall`, choosing by the depth what to write — everything at the depths
its own document names, a short form or nothing deeper; under
`Relative_Focus` and `Out_Focus` it writes nothing, the framework
writing the operations' messages (below) and, for a focus, its jobs'
blocks (§2); `Briefing` calls nothing. What `Session` and `Theory` write
is node_classes/SESSION_AND_THEORY.md §4, what `Theorem` writes
node_classes/THEOREM.md §8.

The messages are the framework's to write, wherever it calls
`print_fields`, `Recall` included: for each of the node's own operations,
the messages its status value carries (COMPILATION.md §4) — under the
header `Error:` for a `CannotEvaluate`, and `Notice:` for a `Ready` that
reported something, a run that failed in part and carried on or one that
warned. It writes them with `print_error(indent, out, message, header)`,
the header line at `indent` and every line of the message one level
deeper:

```
Error:
  Type unification failed: Clash of types "nat" and "bool"
  Type error in application: incompatible operand type
```

An operation's messages are its last run's, and that run is current
exactly while the status it left stands: an invalidation replaces the
value and the messages go with it, a rerun brings its own, so an
operation that is `not_evaluated`, or given `ready` without running,
shows none. The messages are written whole under `Recall` below depth 2,
once per run (§4) elsewhere, never in `Briefing`. A class writes no
messages of its own in `print_fields`; what it has to say about a run it
returns on the status (ARCHITECTURE §6.2).

## 4. The seen set

What a class wants shown once, it remembers in the **seen set** of the
agent the rendering is for, `Agent.seen: set[Key]` with `Key = tuple[int,
str | None]`, reached through the forest (MODULE_STRUCTURE §4.1): after
writing the thing it adds a key of its own choosing, and before writing
it checks; `Conversation.forget(key)` removes a key from every agent's
set. The framework keys each own operation's messages (§3)
`(identity, "beginning")` and `(identity, "ending")` on a nesting node
and `(identity, None)` on a leaf — those three keys are the framework's,
a class chooses others — and the status setter discards the key at
every write, so a run's messages show again after every run, identical
or not. Every rendering that writes the thing records it, `Recall` included,
so a quickview after a `recall` does not repeat it; a class checks the
set to keep a quickview from repeating itself, never to abridge a
rendering the agent asked for in depth. A deleted node's keys stay
behind, harmlessly: the number of a deleted node is never handed out
again (`store.next_identity` only grows), and an amend keeps the replaced
node's identity on purpose (MCP_SPECIFICATION §3.1), the key following
it.

A compaction event — TAT learning that an agent's context was replaced:
on Codex the `PreCompact` and `PostCompact` hooks, which name the agent,
and a `SessionStart` of the main conversation; on Claude Code, where no hook
names the agent, a compaction boundary in the agent's own transcript,
a new transcript path, or the part of the transcript TAT had read no
longer there, found at the agent's next announcement
(CLIENT_HOOKS.md, MODULE_STRUCTURE §4.6) — clears that agent's set
whole, and that agent's alone: nothing it was shown can be assumed. On
Claude Code a `/clear` or a `/resume` counts as a compaction of every agent running
across it, a background subagent whose context it leaves in place
included. The agent then reads the briefing itself, `recall` with no id
(§5). Rendering is synchronous, so the set needs no lock.

## 5. The three renderings

- The **quickview** closes the body of the results of `edit`, `move`,
  `delete`, `evaluate_to`, `construct` and `cancel_construct`, before
  the messages and the trailer (CONSTRUCT_INTERACTION §5): `Forest.render` of
  the forest root in `Relative_Focus(nodes, depth)`, the nodes the call
  was about and how deep under them it looks. No other tool result
  carries one: `check_construct` and `answer` end with their own lines
  (CONSTRUCT_INTERACTION §5).

  | tool | `nodes` | `depth` |
  | --- | --- | --- |
  | `edit` | the nodes the call added — on `amend`, the replacement and those after it | `-1` |
  | `move` | the moved node | `-1` |
  | `delete` | the deleted node's parent | `0` |
  | `evaluate_to` | the destination | `0` |
  | `construct`, `cancel_construct` | the nodes the call names | `0` |

  What a call added is printed whole, once; the rest of the forest is
  the path and the lines beside it.
- The **briefing** is `recall` with no id (RECALL.md): `Forest.render`
  of the forest root in `Briefing`, for the calling agent — every node
  of the forest, one line each, to the bottom; what an agent reads
  after its context was replaced (CONSTRUCT_INTERACTION §8).
- `recall` with no id is the briefing above. `recall` with an id is
  `Forest.render` of the recalled node in `Recall` (MCP_SPECIFICATION
  §1.1): the node and its children with everything their classes write when detailed, the
  grandchildren with their short form, the level below them with what
  their classes write at depth 3 and, under an `incomplete` nesting node
  there, the summary of §2, and nothing deeper.

## 6. The forest root

Two or more sessions — here in a quickview whose focus is `theory_X`:

```
Sessions:
- session_A (complete)
- session_B (incomplete)
  - theory_X (not evaluated)
    Empty so far. Call `edit` with action `append` and target_id `theory_X` to add children.
```

Exactly one: neither `Sessions:` nor the list. The framework's `print`,
descending from the forest root into its only child at `depth >= 1`,
writes the session's line without the dash and keeps what the session
writes under it at the same indent; a `recall` that starts at the
session itself, at depth 0, keeps the dash. The same quickview:

```
session_A (incomplete)
- theory_Base (complete)
- theory_X (not evaluated)
  Empty so far. Call `edit` with action `append` and target_id `theory_X` to add children.
```

None, in every mode:

```
Sessions:
  There are no Isabelle sessions yet. Call `edit` with action `append` and target_id `Sessions` to declare one.
```

`Sessions:` is a header, not a node's line, and carries no mark.

## 7. An example

The quickview after an `evaluate_to` on `theory_X` — the focus, at depth
0 — in a forest of one session and three theories; `definition_f` failed
with a two-line message, `lemma_P` after it is blocked, `lemma_A` before
it ran and still owes its proof, and `theory_Y`, which imports
`theory_X`, was invalidated by the edit that put `definition_f` there;
the result's first line, above this quickview, is `Evaluation stopped at
definition_f.` (TOOL_SCHEMAS.md §4):

```
session_A (incomplete)
- theory_Base (complete)
- theory_X (incomplete)
  - lemma_A (valid statement, proof not started)
  - definition_f (failed)
    Error:
      Type unification failed: Clash of types "nat" and "bool"
      Type error in application: incompatible operand type
  - lemma_P (not evaluated, proof not started)
- theory_Y (not evaluated)
```

The lines with a dash, the default marks and the message block are the
framework's (§3), `Theorem`'s marks the class's. `theory_Base` and `theory_Y` are
in `Out_Focus`; `theory_X` is the focus, and writes no field, since
fields are `Recall`'s alone (§3) — its beginning ran and the stop inside
it kept its ending from running, so it is `incomplete`; the call's depth
is 0, so its children are in `Out_Focus`. `lemma_A` ran and still owes its
proof: `Proof_Obligation`'s two-slot mark (node_classes/COMMON.md §3).
`definition_f` is a `Define`, a class not yet designed (§8); the block is
the framework's `Error:` for its `CannotEvaluate`, and stands here to fix
the block's place.

## 8. Undecided

`Define`'s `mark` and `print_fields` — decided with the class. `Theorem`'s
are node_classes/THEOREM.md §7 and §8.
