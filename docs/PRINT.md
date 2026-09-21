# Rendering

Status: decided (2026-09-21), except §8.

Every node renders itself through one method, in a **print mode** that
says what the reader is looking at, and at a **depth**, the number of
levels below the rendering's starting node:

```python
class Out_Focus: ...                        # not on the path to the focus: the node itself, no children
class Briefing: ...                         # the outline: every node, to the bottom
@dataclass(frozen=True)
class Relative_Focus: path: list[Node]      # the nodes from the next child down to the focus; [] when this node is the focus
class Recall: ...                           # the recalled node and what is under it
PrintMode = Out_Focus | Briefing | Relative_Focus | Recall

def print(self, indent: int, out: TextIO, mode: PrintMode, depth: int) -> None         # the framework's: the line, print_fields, the children
def print_fields(self, indent: int, out: TextIO, mode: PrintMode, depth: int) -> None  # the class's: its fields and its errors; nothing by default
def mark(self, mode: PrintMode, depth: int) -> str | None                              # the framework's default (§1); a class may override
def detailed(mode: PrintMode, depth: int) -> bool                                      # a helper: true for Relative_Focus([]) and for Recall below depth 2
```

`indent` is a level, two spaces each; `depth` is 0 at the node a
rendering starts from. The framework adds one to both for each level it
descends.

## 1. The line and its mark

A node's first line is `- <id> (<mark>)`: the id in its shortest form
(MCP_SPECIFICATION §2.1) and the mark `mark(mode, depth)` returns, the
parenthesis left out when it returns none. The one exception is the lone
session's line (§6).

The framework's default `mark` reads the node's own operations' statuses
through `_own_statuses()` — none for a `Session`, one for a leaf, the
beginning and the ending for a nesting node, a class's own for a class
with statuses of its own (MODULE_STRUCTURE §4.1) — and `finished`
(ARCHITECTURE §3.2). The first row that applies wins:

| the node | mark |
| --- | --- |
| is `finished` | `success` |
| has an operation of its own that is an obstacle: `cannot_evaluate` with no `blocked_by` (ARCHITECTURE §3.3) | `failed` |
| has an operation of its own that is blocked: `cannot_evaluate` naming a `blocked_by` | `blocked by <id>` |
| has an operation of its own that is `not_evaluated` | `not evaluated` |
| every operation of its own ran | none |

No mark therefore means: the node's own operations ran, and something
under it, or something the node itself still owes, is unfinished.
`blocked by` names the obstacle by its id in the shortest form; the
obstacle is always in the forest, since every delete, amend and move
invalidates from its position first (ARCHITECTURE §3.4).

A class overrides `mark` to say more, normally only where the default says
nothing: a `Theorem` whose statement ran and whose proof is not found
answers `not proven`. The framework's four words are RENDER_BASELINES
§5's; a class's words are its own document's.

## 2. What each mode prints

The framework writes the line at `indent`, calls `print_fields` at
`indent + 1`, then the children at `indent + 1` and `depth + 1`:

| mode | `print_fields` | children |
| --- | --- | --- |
| `Out_Focus` | called | none |
| `Briefing` | called | every child, in `Briefing` |
| `Relative_Focus([c, …])` | called | `c` in `Relative_Focus([…])`, every other child in `Out_Focus` |
| `Relative_Focus([])` | called | every child in `Out_Focus` |
| `Recall` | called | every child in `Recall`, while `depth < 3` |

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

`Theory`'s rule: its two operations' messages, in every mode but
`Briefing`, once per run (§4), and not for an operation that is
`not_evaluated`.

## 4. The seen set

What a class wants shown once, it remembers in the conversation's **seen
set**, `Conversation.seen`: after writing the thing it adds a key of its
own choosing, and before writing it checks. `Theory` keys its messages
`(identity, "beginning")` and `(identity, "ending")`, and discards the key
in the evaluation hook before the operation runs, so a run's messages
show again after every run, identical or not.

`POST /on-compaction` clears the set whole (MODULE_STRUCTURE §4.6,
CLIENT_HOOKS.md): the agent's context was replaced, and nothing it was
shown can be assumed. Rendering is synchronous, so the set needs no lock.

## 5. The three renderings

- The **quickview** ends the results of `edit`, `move`, `delete` and
  `evaluate_to`: the forest root in `Relative_Focus` with the path to the
  call's focus, the node the call was about (§8), at depth 0. No other
  tool result carries one.
- The **briefing** answers `POST /on-compaction`: the forest root in
  `Briefing` at depth 0.
- `recall` renders the recalled node in `Recall` at depth 0, with no id
  the forest root: the node with everything its class writes when
  detailed, its children likewise, the grandchildren in the short form,
  the level below them as lines.

## 6. The forest root

Two or more sessions:

```
Sessions:
- session_A (success)
  <what the session prints under its line>
- session_B
  ...
```

Exactly one: neither `Sessions:` nor the list — the session's own line
without the dash, and what it prints under its line at the same indent.
The session decides this itself, being the root's only child; in every
other respect, its depth included — the root at 0, a session at 1 in both
forms — it prints as it would in the list:

```
session_A (success)
<what the session prints under its line>
```

None, in every mode:

```
Sessions:
  There are no Isabelle sessions yet. Call `edit` with `{"action": "append", "target_id": "Sessions", "constructs": [{"kind": "session", ...}], "evaluate": false}` to declare one.
```

`Sessions:` carries no mark.

## 7. An example

The quickview after an `edit` on `theory_X` — the focus — in a forest of
one session and three theories; `definition_f` failed with a two-line
message, `lemma_P` after it is blocked, `lemma_A` before it ran and still
owes its proof, and `theory_Y`, which imports `theory_X`, was invalidated
by the edit:

```
session_A
- theory_Base (success)
- theory_X (blocked by definition_f)
  imports: Main
  - lemma_A
  - definition_f (failed)
    Error:
      Type unification failed: Clash of types "nat" and "bool"
      Type error in application: incompatible operand type
  - lemma_P (blocked by definition_f)
- theory_Y (not evaluated)
```

`theory_Base` and `theory_Y` are in `Out_Focus`; `theory_X` is the focus
and writes `imports`; its children are in `Out_Focus`, and `definition_f`
writes its error there because its class does so in every mode but
`Briefing`.

## 8. Undecided

Each tool's focus — decided with the tools (TOOL_SCHEMAS.md). `Theorem`'s
`mark` and `print_fields` — decided with the class.
