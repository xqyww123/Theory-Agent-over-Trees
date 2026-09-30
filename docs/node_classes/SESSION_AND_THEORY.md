# The `Session` and `Theory` node classes

Status: design, approved 2026-09-06, amended 2026-09-08 (the recorded
fields, the name grammar, §3), 2026-09-16 (§4), 2026-09-22/23 (the name
grammars, the `imports` items, the reserved names, §3) and 2026-09-30
(`parent_session`'s check, §3); the classes are in `model.py`, their
descriptions pinned by `test/test_descriptions.py` and §3's sentences by
`test/test_session_theory.py`.

The two node classes that carry the forest's structure: a `Session` groups
trees into one Isabelle session under construction, and a `Theory` is the
root of every tree (ARCHITECTURE §2). They are framework classes, defined
in `model.py` (ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §6), and are
specified together because neither means much without the other: the
`Session`'s `name` prefixes its trees' qualified names, and a tree's
imports resolve against where the trees sit in the `Session` layer.

A class's agent-facing wording lives here: in §1 and §2 the `description`
texts of its construct schema (PLUGIN_SYSTEM §3), beside its field
table, one fenced line per description — a field with no line has no
description — and in §3 the `InvalidField` reasons its gen checks supply;
the rendering of each whole exception class its gen raises is
RENDER_BASELINES §2's (EXCEPTIONS.md §3). Baseline tests pin the lines the
way RENDER_BASELINES.md's are pinned.

## 1. `Session`

Kind: `session`.

| Field | Type | |
| --- | --- | --- |
| `name` | the Isabelle session name, `str` | authored |
| `parent_session` | the parent Isabelle session of the ROOT entry, `str`; required, no default | authored |
| `options` | `list[Session_Option]`, each `{name: str, value: str}`; empty by default | authored |
| `description` | `str`, empty by default | authored |

Its construct also declares `children`, `items` being `#/$defs/Theory`,
so a session is created with its first theories in one call.

The construct's own description:

```
Isabelle session
```

`options`:

```
Session options, as in a ROOT entry
```

`children`:

```
The session's theories
```

A `Session` owns its ROOT entry: `session <name> in <name> =
<parent_session> + …`, with `options` and `description` transcribed and
the `sessions` and `theories` clauses derived from the trees under it
(ARCHITECTURE §4). Every option value is written quoted; a value the agent
supplied in quotes is unquoted first. Its `name` prefixes its trees' qualified names
(EVALUATOR_DESIGN §7). It runs no Isabelle commands: evaluation is
transparent to it (ARCHITECTURE §3.5), and what it emits is the ROOT entry
and the directory, not Isar. `parent_session` is transcribed and nothing
else: the prover sits on the base heap regardless (ARCHITECTURE §8), and an
import the heap lacks is loaded from source when the Isabelle session
layout knows its file.

`Session.gen` checks: the parent is the forest root `Sessions`
(`BadSessionNodeParent`); the name against the session name's grammar — a
letter, then letters, digits, underscores and interior hyphens
(`HOL-Library`), not ending in a hyphen or an underscore, and no prime,
since the name becomes a path element — with its own rendering of
`InvalidName` (RENDER_BASELINES §2), a grammar strictly narrower than the
framework's (MCP_SPECIFICATION §2), whose sentence is a backstop that
cannot fire for a `Session`; `parent_session`, and every option's `name`
and `value`, are non-empty (`InvalidField`); no option name appears twice
(`InvalidField`, naming the option); last, `parent_session` is not the
session's own name, and is the name of a `Session` the call keeps in the
forest or adds before this one — `NodeConfig`'s `parent`, `role` and
`batch_before`, MODULE_STRUCTURE §4.1; one the call adds after it is not
built yet — or of a session the Isabelle session layout knows, asked
through `is_known_session` (`InvalidField`, §3). Nothing checks it again:
a parent deleted or renamed afterwards, or two sessions each the other's
parent, surface when the ROOT is built. Its trees are not chained: no
tree's state is the next tree's input
(ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §6).

## 2. `Theory`

Kind: `theory`.

Every tree's root is a `Theory` node; it owns the theory header, the
`imports` list and the `end` (ARCHITECTURE §2). Its evaluator runs
the header through the framework's `begin_theory`, writing the first child's
slot, and `end` through `run_commands` into a resulting slot of its own,
putting the theory value into the theory table through `end_theory`
(MODULE_STRUCTURE §3; the slot, ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md
§6; the order of the two writes, `TAT_Common_Nodes.ML`).

| Field | Type | |
| --- | --- | --- |
| `name` | the theory's short name, `str`: a letter, then letters, digits and underscores; no dot, no hyphen, and no prime, since the name becomes a path element. The framework's name grammar (MCP_SPECIFICATION §2) applies as well, refusing a trailing underscore | authored |
| `imports` | `list[str]`, non-empty; each item a theory name in one of two shapes, `<short name>` or `<session>.<short name>`, each half in the session name's grammar (§1), so that the AFP's hyphenated theory names (`AList-Utils`) can be imported; no quotes, no path, no `.thy`. The header quotes every item | authored |
| `beginning_errors`, `ending_errors` | `list[str]` each: what the last run of the operation reported, empty when it passed; held until the operation runs again and never stored, a loaded forest being `not_evaluated` throughout; shown only while the status that run left stands (PRINT.md §3) | recorded |

Its construct declares `children`, `items` being `#/$defs/Construct`.

`name`:

```
The theory's short name
```

`imports`:

```
Theories to import
```

`children`:

```
The theory's declarations
```

The qualified name is `<Session name>.<name>`, computed, never stored.
`Theory.gen` checks: the parent is a `Session` (`BadTheoryNodeParent`); the
theory name's grammar (`InvalidName`); the short name, through
`check_new_theory_short_name`, against what Isabelle has loaded
(`DuplicateTheoryShortName`, with the holder's long name) and against the
names the Isabelle session layout declares global — `Main`, `FOL`, … —
which no tree can bear (`ReservedTheoryName`, EVALUATOR_DESIGN §7);
`imports` non-empty, each item non-empty and in one of its two shapes
(`InvalidField`, §3). The short name's uniqueness within the forest and the
batch is the framework's (ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §3).
Whether an import exists is reported by `begin_theory` at evaluation.

## 3. The `InvalidField` reasons

The two classes' gen checks render these sentences (RENDER_BASELINES §2's
`InvalidField` shape, with the reason the class's own): the first for an
empty `parent_session`, an empty `imports`, an empty item of `imports`,
and an empty option name or value; the second and third for
`parent_session` naming no existing session, or the session itself (§1);
the fourth for an option set twice; the last for an item of `imports`
that is not a theory name in one of its two shapes:

```
The field `parent_session` must not be empty.
The field `parent_session` must name an existing session; `HOL-Libary` is not one.
The field `parent_session` must not name the session itself.
The field `options[1].name` sets the option `document` a second time.
The field `imports[1]` must be a theory name without quotes; a path is not allowed.
```

## 4. What they print

What each class's `print_fields` writes in each mode (PRINT.md §2, §3);
the line and the children are the framework's, and both classes take the
framework's default `mark`. `Session` runs no operation, so it has no
errors; `Theory` writes its two operations' messages — whole under
`Recall` below depth 2, once per run elsewhere, never in `Briefing` — and
only for an operation that is an obstacle, `cannot_evaluate` (PRINT.md
§3, §4).

| mode | `Session` | `Theory` |
| --- | --- | --- |
| `Out_Focus` | nothing | errors |
| `Briefing` | `parent_session` | `imports` |
| `Relative_Focus`, on the path | nothing | errors |
| `Relative_Focus`, a focus | `parent_session`, `options`, `description` | `imports`, errors |
| `Recall`, depth 0 and 1 | `parent_session`, `options`, `description` | `imports`, errors |
| `Recall`, depth 2 | nothing | `imports`, errors |
| `Recall`, depth 3 | nothing | errors |

The lines:

```
parent_session: HOL
options: quick_and_dirty = true, document = false
description:
  Sorting, verified.
imports: Main HOL-Library.Multiset
```

`options` and `description` are left out when empty; `options` is one
line in the ROOT's own spelling; `description` is a block, one indent
deeper, since it may run to several lines; `imports` is one line, the
items separated by spaces as in the header.
