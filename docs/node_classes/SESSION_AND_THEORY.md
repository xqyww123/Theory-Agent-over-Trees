# The `Session` and `Theory` node classes

Status: design draft; the field descriptions of §1 and §2 await the
owner's approval.

The two node classes that carry the forest's structure: a `Session` groups
trees into one Isabelle session under construction, and a `Theory` is the
root of every tree (ARCHITECTURE §2). They are specified together because
neither means much without the other: the `Session`'s `name` prefixes its
trees' qualified names, and a tree's imports resolve against where the trees
sit in the `Session` layer.

A class's agent-facing wording — the `description` texts of its construct
schema (PLUGIN_SYSTEM §3) — lives here, beside its attribute table.

## 1. `Session`

| Attribute | Type | |
| --- | --- | --- |
| `name` | the Isabelle session name, `str` | authored |
| `parent_session` | the parent Isabelle session of the ROOT entry, `str`; required, no default | authored |
| `options` | `list[Session_Option]`, each `{name: str, value: str}`; empty by default | authored |
| `description` | `str`, empty by default | authored |

Its construct also declares `children`, `items` being `#/$defs/Theory`,
so a session is created with its first theories in one call. Kind:
`session`.

| description of | wording |
| --- | --- |
| the class | `An Isabelle session: a group of theories built together.` |
| `name` | `The Isabelle session name, such as \`Arith\` or \`My-Project\`.` |
| `parent_session` | `The session this one builds on, such as \`HOL\` or \`HOL-Analysis\`.` |
| `options` | `Isabelle session options.` |
| `options[].name` | `An Isabelle session option, such as \`document\`.` |
| `options[].value` | `Its value, such as \`false\`.` |
| `description` | `The session's description.` |
| `children` | `The session's theories, in order.` |

A `Session` owns its ROOT entry: `session <name> in <name> = <parent_session> +
…`, with `options` and `description` transcribed and the `sessions` and
`theories` clauses derived from the trees under it (ARCHITECTURE §4). Its
`name` prefixes its trees' qualified names (EVALUATOR_DESIGN §7). It runs no
Isabelle commands: evaluation is transparent to it (ARCHITECTURE §3.5), and
what it emits is the ROOT entry and the directory, not Isar. `parent_session`
is transcribed and nothing else: the prover sits on the base heap regardless
(ARCHITECTURE §8), and an import the heap lacks is loaded from source.

A `Session` lives directly under the forest root `Sessions` and nowhere
else (`BadSessionNodeParent`). Its trees are not chained: no tree's state
is the next tree's input (ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §6).

## 2. `Theory`

Every tree's root is a `Theory` node; it owns the theory header, the
`imports` list and the `end` (ARCHITECTURE §2). Its evaluator runs
the header through the framework's `begin_theory`, writing the first child's
slot, and `end` through `end_theory`, writing the theory table
(MODULE_STRUCTURE §3).

| Attribute | Type | |
| --- | --- | --- |
| `name` | the theory's short name, `str`: an Isabelle identifier — a letter, then letters, digits, underscores and primes; no dot, no hyphen | authored |
| `imports` | `list[str]`, non-empty; each item as written in the header's `imports` clause: `Main`, `HOL-Library.Multiset`, or a path such as `"lib/Rel"` | authored |

No recorded field. Its construct declares `children`, `items` being
`#/$defs/Construct`. Kind: `theory`.

| description of | wording |
| --- | --- |
| the class | `An Isabelle theory: one file of declarations.` |
| `name` | `The theory's short name, an Isabelle identifier such as \`Sorting\`.` |
| `imports` | `The imported theories, as written in an \`imports\` clause: \`Main\`, \`HOL-Library.Multiset\`, or another theory of this forest.` |
| `children` | `The theory's declarations, in order.` |

The qualified name is `<Session name>.<name>`, computed, never stored.
`Theory.gen` checks: the parent is a `Session` (`BadTheoryNodeParent`); the
identifier grammar of `name` (`InvalidName`); the short name against the
base heap through `check_new_theory_short_name`
(`DuplicateTheoryShortName`); `imports` non-empty with non-empty strings
(`InvalidField`). The short name's uniqueness within the forest and the
batch is the framework's (ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §3).
Whether an import exists is reported by `begin_theory` at evaluation.
