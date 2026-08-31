# The `Session` and `Theory` node classes

Status: design draft.

The two node classes that carry the forest's structure: a `Session` groups
trees into one Isabelle session under construction, and a `Theory` is the
root of every tree (ARCHITECTURE §2). They are specified together because
neither means much without the other: the `Session`'s `name` prefixes its
trees' qualified names, and a tree's imports resolve against where the trees
sit in the `Session` layer.

## 1. `Session`

| Attribute | Type | |
| --- | --- | --- |
| `name` | the Isabelle session name, `str` | authored |
| `parent` | the parent Isabelle session of the ROOT entry, `str` | authored |
| `directory` | path relative to the forest directory, `PurePosixPath` | authored |
| `options` | `dict[str, str]` | authored |
| `description` | `str`, empty for none | authored |

A `Session` owns its ROOT entry: `session <name> in <directory> = <parent> +
…`, with `options` and `description` transcribed and the `sessions` and
`theories` clauses derived from the trees under it (ARCHITECTURE §4). Its
`name` prefixes its trees' qualified names (EVALUATOR_DESIGN §7). It runs no
Isabelle commands: evaluation is transparent to it (ARCHITECTURE §3.5), and
what it emits is the ROOT entry and the directory, not Isar. `parent` is
transcribed and nothing else: the prover sits on the base heap regardless
(ARCHITECTURE §8), and an import the heap lacks is loaded from source.

## 2. `Theory`

Every tree's root is a `Theory` node; it owns the theory header, the
`imports` list and the closing `end` (ARCHITECTURE §2). Its evaluator runs
the header through the framework's `begin_theory`, writing the first child's
slot, and `end` through `end_theory`, writing the theory table
(MODULE_STRUCTURE §3).

Its attribute table is unspecified.
