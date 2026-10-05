# The `Session` and `Theory` node classes

Status: design, approved 2026-09-06, amended 2026-09-08 (the recorded
fields, the name grammar, §3), 2026-09-16 (§4), 2026-09-22/23 (the name
grammars, the `imports` items, the reserved names, §3), 2026-09-30
(`parent_session`'s check, §3) and 2026-10-02 (the ROOT entry, the checks
through Isabelle, the messages on the status values, `import_sessions`,
`file_path()`, §3, §4; COMPILATION.md); the classes are in `model.py`, their
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

A `Session` owns its ROOT entry, which `compile` writes from its fields
(COMPILATION.md §2): `session "<name>" in "<name>" = "<parent_session>" +`,
then `description` as one cartouche when not empty — `‹`, `›`, `\<open>`
and `\<close>` in it replaced by `"` — `options` when not empty, in the
ROOT's own spelling with every name and value quoted (a value the agent
supplied in quotes is unquoted first), `sessions` listing the session of
every theory the session's written trees import that is neither the
session itself nor its `parent_session` (each tree's `import_sessions`,
§2), and `theories` listing the session's written trees by short name.
Every name in the entry is written in double quotes. Its `name` prefixes
its trees' qualified names (EVALUATOR_DESIGN §7). It runs no Isabelle
commands: evaluation is transparent to it (ARCHITECTURE §3.5); it emits no
Isar, and `compile` makes its folder beside its entry. `parent_session` is
transcribed: the prover sits on the base heap regardless (ARCHITECTURE
§8), and an import the heap lacks is loaded from source when the Isabelle
session layout knows its file.

`Session.gen` checks: the parent is the forest root `Sessions`
(`BadSessionNodeParent`); the name against the session name's grammar — a
letter, then letters, digits, underscores and interior hyphens
(`HOL-Library`), not ending in a hyphen or an underscore, and no prime,
since the name becomes a path element — with its own rendering of
`InvalidName` (RENDER_BASELINES §2), a grammar strictly narrower than the
framework's (MCP_SPECIFICATION §2), whose sentence is a backstop that
cannot fire for a `Session`; the name is not `ROOT` in any spelling, since
the session's folder would be the ROOT file's path (`ReservedSessionName`,
RENDER_BASELINES §2); `parent_session`, and every option's `name` and
`value`, are non-empty (`InvalidField`); no option name appears twice
(`InvalidField`, naming the option); then, in one question to Isabelle
answered with the first defect: the name is not one Isabelle reserves —
`Path.is_reserved`'s and `Sessions.illegal_session`'s, asked through
Isabelle's own predicates (`ReservedSessionName`) — nor one the Isabelle
session layout knows (`InvalidField`, §3), and every option is accepted
as Isabelle reads a ROOT — the Scala function `TAT.check_options`,
MODULE_STRUCTURE §2.3 — (`InvalidField`, §3, carrying Isabelle's
message, its lines joined by single spaces); last, `parent_session` is
not the session's own name, and is the
name of a `Session` the call keeps in the forest or adds before this one —
`NodeConfig`'s `parent`, `role` and `batch_before`, MODULE_STRUCTURE §4.1;
one the call adds after it is not built yet — or of a session the Isabelle
session layout knows (`InvalidField`, §3). The questions to Isabelle go
through one callback, `TAT.check_session`, which answers the first defect
(MODULE_STRUCTURE §2.3). The name's uniqueness is the framework's,
comparing names without regard to case — on a file system that does not
distinguish case two such sessions would share one folder, and Isabelle
refuses a ROOT whose entries do — through a namespace of session names
whose refusal is the id component's, `DuplicateName`, naming the holder.
Nothing checks them again: a parent deleted or
renamed afterwards, or two sessions each the other's parent, surface when
`isabelle TAT_compile` has Isabelle read the ROOT it wrote (COMPILATION.md
§2). Its trees are not chained: no tree's state is the next tree's input
(ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §6).

## 2. `Theory`

Kind: `theory`.

Every tree's root is a `Theory` node; it owns the theory header, the
`imports` list and the `end` (ARCHITECTURE §2). Its evaluator runs
the header through the framework's `begin_theory`, writing the first child's
slot, and `end` through an ML-built `Toplevel.exit` transition into a
resulting slot of its own,
putting the theory value into the theory table through `end_theory`
(MODULE_STRUCTURE §3; the slot, ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md
§6; the order of the two writes, `TAT_Common_Nodes.ML`).

| Field | Type | |
| --- | --- | --- |
| `name` | the theory's short name, `str`: a letter, then letters, digits and underscores; no dot, no hyphen, and no prime, since the name becomes a path element. The framework's name grammar (MCP_SPECIFICATION §2) applies as well, refusing a trailing underscore | authored |
| `imports` | `list[str]`, non-empty; each item a theory name in one of two shapes, `<short name>` or `<session>.<short name>`, each half in the session name's grammar (§1), so that the AFP's hyphenated theory names (`AList-Utils`) can be imported; no quotes, no path, no `.thy`. The header quotes every item | authored |
| `description` | `str`, empty by default; kept as written, no normalisation | authored |
| `import_sessions` | `list[str]`: the session of each import, `Resources.theory_qualifier` of its resolved long name, recorded when the header runs; stored, since the ROOT's `sessions` clause is written from a loaded forest (COMPILATION.md §2) | recorded |

Its construct declares `children`, `items` being `#/$defs/Construct`. What
the header's and the `end`'s runs reported is no field: it lives on the
status values the evaluation hooks return, which the framework stores and
prints (COMPILATION.md §4; PRINT.md §3).

`name`:

```
The theory's short name
```

`imports`:

```
Theories to import
```

`description`:

```
A summary of the theory, as LaTeX text
```

`children`:

```
The theory's declarations
```

A non-empty `description` is emitted as a `text ‹…›` block before the
`theory` line, the content as written and no period added; `‹`, `›`,
`\<open>` and `\<close>` in it are replaced by `"`, so the cartouche closes
where it should and nothing is refused (ARCHITECTURE §4, §5). It is never
run: evaluation runs the header and the `end` alone. An amend that
changes it re-evaluates the tree like any other amend. `Theory` writes its
text through `emit_beginning` — that block, then the header, each line
ending in a newline — and `emit_ending`, the `end` (COMPILATION.md §3).

The header `Theory` runs and the header it emits are one text, built by
one function: the `theory` line, the agent's `imports`, and — on a theory
none of whose imports resolves to a theory of the forest — the imports
the loaded plugins declare (PLUGIN_SYSTEM §1), which every other theory
receives through the forest theories it imports. The agent writes none
of them, and `recall` shows the agent's items alone (§4); their sessions
are recorded in `import_sessions` with the agent's, so the ROOT's
`sessions` clause names them (COMPILATION.md §2).

The qualified name is `<Session name>.<name>`, computed, never stored; the
tree's file path, `<Session name>/<name>.thy` relative to the working
directory, is `file_path()`, which gives both the `master_dir` the header
is evaluated under and the file `compile` writes (COMPILATION.md §2).
`Theory.gen` checks: the parent is a `Session` (`BadTheoryNodeParent`); the
theory name's grammar (`InvalidName`); the short name, through
`check_new_theory_short_name`, against what Isabelle has loaded
(`DuplicateTheoryShortName`, with the holder's long name) and against the
names no tree can bear — those the Isabelle session layout declares
global, `Main`, `FOL`, …, and those Isabelle reserves, `Path.is_reserved`'s
and `Sessions.illegal_theory`'s, asked through Isabelle's own predicates
(`ReservedTheoryName`, EVALUATOR_DESIGN §7; COMPILATION.md §2); `imports`
non-empty, each item non-empty and in one of its two shapes
(`InvalidField`, §3). The short name's uniqueness within the forest and the
batch is the framework's, comparing names without regard to case, since
Isabelle refuses two theory files whose names differ only in case
(ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §3; `DuplicateTheoryShortName`
names the holder). Whether an import exists is reported by `begin_theory`
at evaluation, which also records `import_sessions`.

## 3. The `InvalidField` reasons

The two classes' gen checks render these sentences (RENDER_BASELINES §2's
`InvalidField` shape, with the reason the class's own): the first for an
empty `parent_session`, an empty `imports`, an empty item of `imports`,
and an empty option name or value; the second and third for
`parent_session` naming no existing session, or the session itself (§1);
the fourth for an option set twice; the fifth for an item of `imports`
that is not a theory name in one of its two shapes; the sixth for a
session name the Isabelle session layout already knows; the last for an
option Isabelle refuses, with Isabelle's message, its lines joined by
single spaces:

```
The field `parent_session` must not be empty.
The field `parent_session` must name an existing session; `HOL-Libary` is not one.
The field `parent_session` must not name the session itself.
The field `options[1].name` sets the option `document` a second time.
The field `imports[1]` must be a theory name without quotes; a path is not allowed.
The field `name` must not be the name of an existing Isabelle session; `Graph_Theory` is one.
The field `options[1]` is not accepted by Isabelle: Unknown option "documnet".
```

## 4. What they print

What is written under each class's line in each mode — the class's
`print_fields`, and the framework's messages (PRINT.md §2, §3);
the line and the children are the framework's, and both classes take the
framework's default `mark`. Fields are written under `Recall` alone;
`Briefing` calls `print_fields` on no class. `Session` runs no operation,
so it has no messages; `Theory`'s two operations' messages are the
framework's to write, from the status values, wherever `print_fields` is
called — under `Error:` for a `CannotEvaluate` and `Notice:` for a
`Ready`, whole under `Recall` below depth 2, once per run elsewhere
(PRINT.md §3, §4); `Theory`'s `print_fields` writes its fields alone.

| mode | `Session` | `Theory` |
| --- | --- | --- |
| `Out_Focus` | nothing | messages |
| `Relative_Focus`, on the path | nothing | messages |
| `Relative_Focus`, a focus | nothing | messages |
| `Recall`, depth 0 | `parent_session`, `options`, `description` | `description`, `imports`, messages |
| `Recall`, depth 1 | `parent_session`, `options` | `imports`, messages |
| `Recall`, depth 2 | nothing | `imports`, messages |
| `Recall`, depth 3 | nothing | messages |

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
deeper, since it may run to several lines, the same form for both
classes; `imports` is one line, the items the agent wrote, separated by
spaces, without the imports the plugins declare (§2).
