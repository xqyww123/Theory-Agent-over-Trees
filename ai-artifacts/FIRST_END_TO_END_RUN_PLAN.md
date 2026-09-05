# Plan: the first end-to-end run

Status: in discussion. A section marked *(approved)* records the owner's
decision; anything marked *(proposed)* or *(open)* is not settled. Once a
section is settled it moves into the design documents under `docs/`, and
this file keeps only the implementation record.

## 0. Scope

One real tree, evaluated by Isabelle, through the MCP tools. That needs the
`Session` and `Theory` node classes, the forest scheduling that evaluates
imported trees first (ARCHITECTURE §3.5), a `Theorem` that emits only
`sorry`, the `edit` tool, and the persistence and file layout everything
sits on. `construct`, AoA, and the other node classes are outside this
plan.

## 1. The working directory *(approved 2026-09-04)*

TAT starts on one directory, the **working directory**, and its layout is
fixed:

```
<working directory>/
  theory_forest.sqlite     the forest (§2); read at start, created empty if absent
  ROOT                     every Session's entry (ARCHITECTURE §4)
  <session name>/          one folder per Session, named after it
    <theory name>.thy      one file per tree, named after the theory's short name
```

- A `Session`'s directory is its name, not an attribute.
- The client hands the directory to `TAT_Framework.start`, which passes it
  to `launch_TAT` as an argument. Both sides read the same string: the ML
  side's `begin_theory` takes `<working directory>/<session name>` as the
  `master_dir`; the Python side writes the files and the forest there.
- TAT owns the files: deleting a tree deletes its `.thy`, deleting a
  `Session` deletes its folder.

## 2. Persistence *(approved 2026-09-04)*

The forest is stored in one SQLite database, not pickled.

- One table, `fields (node INTEGER, field TEXT, value BLOB, PRIMARY KEY
  (node, field))`: one row per node field, the value in MessagePack. `node`
  is the node's identity number (MCP_SPECIFICATION §2), which survives
  renaming and moving.
- A second table, `meta`, holds the identity counter — so identities stay
  fresh across restarts — and a schema version. A database whose schema
  version is not this TAT's is refused at start (`IncompatibleStore`, a
  `TAT_StartupError`, EXCEPTIONS.md §1).
- Stored per node: `kind`, `parent` (the parent's identity), every authored
  field, every recorded field; on a nesting node, `children` (the ordered
  list of the children's identities). Not stored: evaluation statuses and
  state slot names — a loaded forest is `not_evaluated` throughout
  (ARCHITECTURE §4.1). Every stored value must be MessagePack-representable;
  that is a requirement on node classes.
- Every **write operation** is one transaction: `edit`, `move`, `delete`,
  and an evaluation hook writing a recorded field. Read operations
  (`recall`, `status`) do not touch the database. The transaction
  opens once the operation has succeeded in memory and closes before the
  next `await`; nothing is awaited inside a transaction. Identities are
  handed out before the transaction exists, so `next_identity()` needs none:
  outside one it is its own write.
- The access layer is TAT's own, `Forest_Store` (one module, standard
  library `sqlite3`, WAL mode): `transaction()` is the only way to open a
  transaction, and `put`/`delete_node` outside one is an error; `get`,
  `fields(node)`, `nodes()` serve loading; `next_identity()` serves
  creation. One connection, used from the event loop only: background
  work writes through the loop, never from another thread.
- Replaces `__getstate__`/`__setstate__` in `model.py`, and the pickle
  paragraph of ARCHITECTURE §4.1 and MODULE_STRUCTURE §4.1. A condition on
  that rewrite: a node's whole field set is written by exactly one
  routine, which calls `delete_node` and then `put` inside the operation's
  one transaction — an `amend` keeps the identity but may change the field
  set, and the store cannot tell a stale row from a current one; every
  other `put` writes one recorded field of a node whose field set is
  unchanged.

## 3. `Theory`'s attribute table *(approved 2026-09-04)*

| Attribute | Type | |
| --- | --- | --- |
| `name` | the theory's short name, `str`: an Isabelle identifier — a letter, then letters, digits, underscores and primes; no dot, no hyphen | authored |
| `imports` | `list[str]`, non-empty; each item as it would be written in the header's `imports` clause: `Main`, `HOL-Library.Multiset`, or a path such as `"lib/Rel"` | authored |

No recorded field.

- The qualified name is `<Session name>.<name>`, computed on demand, never
  stored. The ML side derives the same string through
  `Resources.import_name` and keys the theory table by it
  (`ML/TAT_Framework.ML`, `begin_theory`); a dotted `name` is refused there
  as a framework bug, so `Theory.gen` refuses it first.
- No hyphen, as `Theorem` already rules for its names: the short name is
  written into `theory X imports … begin`, into other trees' `imports`,
  and into qualified fact names such as `X.P`.
- `imports` is non-empty because Isabelle's header grammar requires at
  least one import (`Thy_Header.args`, `Scan.repeat1`); only `Pure` is
  exempt.
- `gen` checks the shape of `imports` and nothing more: resolving an import
  may load a theory from source, which is a write to `Thy_Info`, and `gen`
  must not write (MODULE_STRUCTURE §4.1). Whether an import exists is
  reported by `begin_theory` at evaluation. §5 may add one forest-only
  check.
- Not in the first version: the header's `keywords` and `abbrevs` clauses.

`Theory.gen` checks: the parent is a `Session` (`BadTheoryNodeParent`); the
identifier grammar of `name` (`InvalidName`, rendering the agent's own
spelling); the short name against every other `Theory` in the forest,
excluding `config.replacing`, and then against the base heap through
`check_new_theory_short_name` (`DuplicateTheoryShortName`); `imports`
non-empty with non-empty strings (`InvalidField`).

## 4. Creating a `Session` *(approved 2026-09-04)*

There is no `new_session` tool. The forest root has the id `Sessions`;
`edit` with `action: "append"` and `target_id: "Sessions"` creates a
`Session`, and `amend` and `delete` address one by id like any node. Every
other action on the root is refused (`ProtectedNode`), and `Sessions` is a
reserved node name. The first layer is ordered like any other.

`Session` is an ordinary node class: its `construct_schema` (PLUGIN_SYSTEM.md
§3) carries `name`, `parent`, `options` (defaults to empty), `description`
(defaults to empty; the field's schema description reads `The session's
description.`), and `children` typed `{"$ref": "#/$defs/Theory"}`, so a
session may be created with its first theories in one call. It has no
`directory` field (§1).

The root renders as

```
Sessions:
- session_A
  <fields, rendered by Session.print>
- session_B
  ...
```

and, when the forest is empty,

```
Sessions:
  There are no Isabelle sessions yet. Call `edit` with `{"action": "append", "target_id": "Sessions", "constructs": [{"kind": "session", ...}]}` to declare one.
```

Rendering is every node's own: `print(self, indent: int, out: TextIO) -> int`
(the full rendering: the node's fields and status, then its children) and
`quickview(self, indent: int, out: TextIO) -> int` (one line, children
compressed), each returning the indent for what follows, as `emit_isar`
does (ARCHITECTURE §4). `recall`'s two detail levels call one or the other,
and every tool result ends with the forest's `quickview`, as AoA's do.

*(open)*: whether `parent` is checked against Isabelle's known sessions
(needs a new ML callback) or only transcribed into the ROOT entry.

## 5. How an import names a forest tree *(open)*

Facts, from the Isabelle source (`Resources.import_name`) and an
in-process probe (`scratchpad/probe_imports`, 2026-09-04):

- A bare import name is qualified with the importing theory's own session
  name; a dotted name is taken as written. The ML side then consults the
  conversation's theory table first, under exactly that string.
- So `imports S.A` works from any session once tree `A` of session `S` is
  evaluated to its end, the importing tree's own session included
  (verified). A bare `imports A` works only from session `S` (verified).
- A bare `imports A` from another session `T` looks for `T.A`: with no
  file `T/A.thy` it fails with Isabelle's `No such file: ".../T/A.thy"
  … for theory "T.A"`; with such a file present (a stale one, under §1)
  it silently loads a second theory `T.A`, and a later theory importing
  both fails with `Duplicate theory name` far from the cause (verified).
- Whatever the rule, the forest's import graph (§6) must recognise both
  the bare and the qualified spelling of a forest tree, or the importing
  tree runs before its import is in the table.

What TAT does about the bare cross-session import is not decided.

## 6. `Forest._evaluate` *(to be proposed)*

The two loose ends of OPEN_QUESTIONS §1 — a `Theory` root's own `state`,
which nothing writes, and the resulting slot its `end` would write, which
nothing reads — are settled here.

## 7. Implementation order *(to be written once §5 and §6 are settled)*
