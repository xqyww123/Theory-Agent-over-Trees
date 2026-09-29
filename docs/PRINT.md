# Rendering

Status: decided (2026-09-21, after two design reviews; the quickview's
focus and depth 2026-09-22), except §8.

Every node renders itself through one method, in a **print mode** that
says what the reader is looking at, and at a **depth**, the number of
levels below the rendering's starting node:

```python
class Out_Focus: ...                        # not on the path to a focus: the node itself, no children
class Briefing: ...                         # the outline: every node, to the bottom
@dataclass(frozen=True)
class Relative_Focus:                       # the quickview: every node of `nodes` is a focus, with what lies
    nodes: frozenset[Node]                  #   `depth` levels under it — its whole subtree at -1; a node
    depth: int                              #   above one is on the path
class Recall: ...                           # the recalled node and what is under it
PrintMode = Out_Focus | Briefing | Relative_Focus | Recall

def print(self, indent: int, out: TextIO, mode: PrintMode, depth: int) -> None         # the framework's: the line, print_fields, the children
def print_fields(self, indent: int, out: TextIO, mode: PrintMode, depth: int) -> None  # the class's: its fields and its errors; nothing by default
def mark(self, mode: PrintMode, depth: int) -> str | None                              # the framework's default (§1); a class may override
def detailed(self, mode: PrintMode, depth: int) -> bool                                # a helper: true for a focus and for Recall below depth 2
```

`indent` is a level, two spaces each; `depth` is 0 at the node a
rendering starts from. Every rendering is one call of
`Forest.render(node, mode)` (MODULE_STRUCTURE §4.1), which calls
`node.print(0, out, mode, 0)`; the framework adds one to both for each
level it descends, with the exception §2 names.

## 1. The line and its mark

A node's first line is `- <id> (<mark>)`: the id in its shortest form
(MCP_SPECIFICATION §2.1) and the mark `mark(mode, depth)` returns, the
parenthesis left out when it returns none. Two lines carry no dash: the
forest root's and the lone session's (§6).

The framework's default `mark` reads the node's own operations' statuses
through `_own_statuses()` — none for a `Session`, one for a leaf, the
beginning and the ending for a nesting node, a class's own for a class
with statuses of its own (MODULE_STRUCTURE §4.1) — and `finished`
(ARCHITECTURE §3.2). The first row that applies wins:

| the node | mark |
| --- | --- |
| is `finished` | `success` |
| has an operation of its own that is an obstacle: `cannot_evaluate` (ARCHITECTURE §3.3) | `failed` |
| has an operation of its own that is `not_evaluated` — never run, invalidated, or blocked: after a stop in its tree, under a nesting node whose beginning failed, or in a tree one of whose resolved imports has no theory value | `not evaluated` |
| every operation of its own ran | none |

No mark therefore means: the node's own operations ran, and something
under it, or something the node itself still owes, is unfinished. What
blocks a `not evaluated` node is not on its line: the `failed`
marks say where the obstacles are, and the tool that ran the evaluation
names the first stop in its answer (RENDER_BASELINES §6; MCP_SPECIFICATION
§4).

A class overrides `mark` to say more, normally only where the default
says nothing — a `Theorem` whose statement ran and whose proof is not
found is that case, and the word it answers is decided with the class
(§8). The framework's words are RENDER_BASELINES §5's; a class's
words are its own document's.

## 2. What each mode prints

The framework writes the line at `indent`, calls `print_fields` at
`indent + 1`, then the children at `indent + 1` and `depth + 1`. A line
that carries no dash is not a list item and opens no level — the forest
root's line and the lone session's (§6) — so what a node writes under it,
its fields and its children alike, stays at `indent` while `depth` still
rises. The forest root writes no fields; the empty forest's hint, the
only line it writes under `Sessions:`, sits one level in (§6).

| mode | `print_fields` | children |
| --- | --- | --- |
| `Out_Focus` | called | none |
| `Briefing` | called | every child, in `Briefing` |
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
the class's, by mode and depth (§3).

## 3. Fields and errors

A class writes its fields in `print_fields`, one per line, choosing by
the mode and the depth what to write: everything when
`detailed(mode, depth)`, a short form or nothing otherwise, or a rule of
its own — a `Locale` writes its header, `fixes` and `assumes`, only under
`Recall`. What `Session` and `Theory` write is
node_classes/SESSION_AND_THEORY.md §4.

A class also writes its errors there: the messages its last run left,
Isabelle's or its own. The framework supplies `print_error(indent, out,
message)`, which writes the block — an `Error:` line at `indent`, every
line of the message one level deeper:

```
Error:
  Type unification failed: Clash of types "nat" and "bool"
  Type error in application: incompatible operand type
```

`Theory`'s rule: its two operations' messages — whole under `Recall`
below depth 2, once per run (§4) elsewhere, never in `Briefing` — and
only for an operation that is an obstacle, `cannot_evaluate` (§1's second
row), the one status a failed run of it leaves
standing. An operation's recorded messages are its last run's, and that
run is current exactly while the status it left stands, so an operation
that is `not_evaluated`, or given `ready` without running, shows
none: a `Theory`'s `Error:` block accompanies a `failed` line and no
other.

## 4. The seen set

What a class wants shown once, it remembers in the conversation's **seen
set**, `Conversation.seen`: after writing the thing it adds a key of its
own choosing, and before writing it checks. `Theory` keys its messages
`(identity, "beginning")` and `(identity, "ending")`, and discards the key
when the evaluation hook records the run's messages, after the operation
has run, so a run's messages show again after every run, identical or
not. Every rendering that writes the thing records it, `Recall` included,
so a quickview after a `recall` does not repeat it; a class checks the
set to keep a quickview from repeating itself, never to abridge a
rendering the agent asked for in depth. A deleted node's keys stay
behind, harmlessly: the number of a deleted node is never handed out
again (`store.next_identity` only grows), and an amend keeps the replaced
node's identity on purpose (MCP_SPECIFICATION §3.1), the key following
it.

`POST /on-compaction` clears the set whole (MODULE_STRUCTURE §4.6,
CLIENT_HOOKS.md): the agent's context was replaced, and nothing it was
shown can be assumed. Rendering is synchronous, so the set needs no lock.

## 5. The three renderings

- The **quickview** ends the results of `edit`, `move`, `delete` and
  `evaluate_to`: `Forest.render` of the forest root in
  `Relative_Focus(nodes, depth)`, the nodes the call was about and how
  deep under them it looks. No other tool result carries one.

  | tool | `nodes` | `depth` |
  | --- | --- | --- |
  | `edit` | the nodes the call added — on `amend`, the replacement and those after it | `-1` |
  | `move` | the moved node | `-1` |
  | `delete` | the deleted node's parent | `0` |
  | `evaluate_to` | the destination | `0` |

  What a call added is printed whole, once; the rest of the forest is
  the path and the lines beside it.
- The **briefing** answers `POST /on-compaction`: `Forest.render` of the
  forest root in `Briefing`.
- `recall` is `Forest.render` of the recalled node in `Recall`, or, with
  no id, of the forest root (MCP_SPECIFICATION §1.1): the node and its
  children with everything their
  classes write when detailed, the grandchildren with their short form,
  the level below them with what their classes write at depth 3, and
  nothing deeper.

## 6. The forest root

Two or more sessions — here in a quickview whose focus is `theory_X`:

```
Sessions:
- session_A (success)
- session_B
  - theory_X (not evaluated)
    imports: Main
```

Exactly one: neither `Sessions:` nor the list. The framework's `print`,
descending from the forest root into its only child at `depth >= 1`,
writes the session's line without the dash and keeps what the session
writes under it at the same indent; a `recall` that starts at the
session itself, at depth 0, keeps the dash. The same quickview:

```
session_A
- theory_Base (success)
- theory_X (not evaluated)
  imports: Main
```

None, in every mode:

```
Sessions:
  There are no Isabelle sessions yet. Call `edit` with `{"action": "append", "target_id": "Sessions", "constructs": [{"kind": "session", ...}], "evaluate": false}` to declare one.
```

`Sessions:` carries no mark.

## 7. An example

The quickview after an `evaluate_to` on `theory_X` — the focus, at depth
0 — in a forest of one session and three theories; `definition_f` failed
with a two-line message, `lemma_P` after it is blocked, `lemma_A` before
it ran and still owes its proof, and `theory_Y`, which imports
`theory_X`, was invalidated by the edit that put `definition_f` there:

```
session_A
- theory_Base (success)
- theory_X (not evaluated)
  imports: Main
  - lemma_A
  - definition_f (failed)
    Error:
      Type unification failed: Clash of types "nat" and "bool"
      Type error in application: incompatible operand type
  - lemma_P (not evaluated)
- theory_Y (not evaluated)
```

The lines with a dash, and the marks on them, are the framework's;
`imports: Main` and the error block are what the classes write.
`theory_Base` and `theory_Y` are in `Out_Focus`; `theory_X` is the focus
and writes `imports`; the call's depth is 0, so its children are in
`Out_Focus`. `lemma_A` ran and
still owes its proof, so the default `mark` leaves its line bare, and
`Theorem`'s own `mark` is undecided (§8). `definition_f` is a `Define`, a
class not yet designed (§8); the block is what its `print_fields` would
write through `print_error`, and stands here to fix the block's place.

## 8. Undecided

`Theorem`'s and `Define`'s `mark` and `print_fields` — decided with each
class.
