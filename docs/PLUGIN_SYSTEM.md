# The plugin system

Status: design, approved 2026-09-04; §2, §3 and §5 revised 2026-10-12
with the node-class rounds (ai-artifacts/review/NODE_CLASS_RULINGS.md):
the construct checked against its construct schema, the agreement
check at every depth, the grammar without `Any`.

A node class is a plugin: an Isabelle theory carrying its evaluator, and a
Python package carrying everything else (ARCHITECTURE §6). This document is
the Python side of loading one — how a class registers, what the loader
checks, and how the loaded classes together complete the `edit` tool's
schema (TOOL_SCHEMAS.md §1). The ML side of registration is
MODULE_STRUCTURE §2.5; the conversation start that collects the packages,
§2.6.

**What TAT trusts.** A plugin is trusted code: its node classes, its
compile hooks and the theories its package names run with the
framework's own authority, and TAT does not defend itself against them.
What the loader checks (§5) turns a mistake into an early refusal that
names it, where that is cheap; a mistake it does not check for surfaces
where it happens, as the plugin's bug (EXCEPTIONS.md §1) — a class that
leaves an abstract method unimplemented, for one, fails at its first
instantiation. The same trust goes to whoever runs the `isabelle` tools
(MODULE_STRUCTURE §5) and to the Isabelle installation. TAT does not
trust the agent, whose every input is checked (MCP_SPECIFICATION §2,
EXCEPTIONS.md §3), nor the working directory as it finds it, which is
TAT's alone (COMPILATION.md §2): a change made there from outside is
refused, never repaired.

## 1. Loading

The Python side of a plugin is a package, named by the module strings the
plugin's theory registers as `python_packages`. The ML side collects and
deduplicates them at conversation start and hands the list to `launch_TAT`;
`plugin.load` imports each with `importlib.import_module`. Importing is
what registers: a node class is defined at module top level under
`@TAT_node`, and the decorator runs as the class statement executes. The
two framework classes, `Session` and `Theory` (`model.py`), are registered
by `load` itself, first, through the same `TAT_node`. Registration has no
other path. What a class registers into is a process-wide registry, which
holds a class exactly while the module defining it is in `sys.modules` —
the framework's two classes from the first `load`, a plugin's from the
import of its package; what `load` returns is
this conversation's kind table — those two plus the classes of the listed
packages, a class belonging to the package whose module defines it, a
module under the package counting — and the assembled `edit` schema, so a
second conversation in the same process reads the registry rather than
registering again (MODULE_STRUCTURE §4.4).

A package may also register compile hooks: a module-level function under
`@TAT_compile_hook`, of one positional argument, the forest root,
returning nothing, which a compile runs after it has written its files
(COMPILATION.md §5). The decorator registers it as `TAT_node` registers a
class, at import, into a registry of its own, `compile_hooks`, kept in
registration order, which holds a hook exactly while its defining module
is in `sys.modules`; the sweep at the start of `load` clears both
registries of entries whose module is gone, and `load` returns the hooks
the listed packages define beside the kind table.

A plugin's package may also declare imports: theories that the forest's
theories import besides what the agent wrote — `Isabelle_Std`'s declares
`Minilang_AoA.Minilang_AoA`, where the `aoa` method is defined
(node_classes/COMMON.md §3). The declaration is a module-level call
`TAT_import(<theory name>)`, the name in the `imports` field's qualified
shape, registered at import as a compile hook is, into a registry of its
own, swept the same way, and returned by `load` for the listed packages
beside the hooks. How `Theory` adds them to a theory that imports no
theory of the forest is node_classes/SESSION_AND_THEORY.md §2.

A package that fails to import — a syntax error, a registration check
below — fails the conversation start: a plugin's bug is never skipped
quietly. The failed import takes the failing module out of `sys.modules`,
and with it what that module had registered, so the next `load` takes the
fixed module; a module it had imported cleanly before failing stays, with
what that one registered, so a fix inside such a module needs a new host
process — the imported modules are the process's (ARCHITECTURE §9).

## 2. What a class declares

A node class derives from `Leaf`, `StdBlock` or `Unchained_Node`
(MODULE_STRUCTURE §4.1) and is registered with `@TAT_node`, which takes no
arguments. An `Unchained_Node` chains no children, so a child class that
has a result owns the slot for it, as `Theory` does: it mints the slot in
`gen` and `from_store`, returns it from `resulting_state()`, and appends it
in `_states_inside()`, so it is released when the node leaves.
A class may own a further slot besides, as `Proof_Obligation` does with
`goal_state`: it mints it where the node is built — in `gen` and
`from_store`, or once in a constructor both reach — appends it the same
way, and names it in `_slots_written_by(operation)`, so that the
framework releases it with the result of the operation that writes it
(MODULE_STRUCTURE §4.1, "States").
Besides its hooks a class declares, as class attributes:

| attribute | what it is |
| --- | --- |
| `construct_schema` | the complete JSON schema of a construct of this class, hand-written (§3) |
| `argument_schema` | a TypedDict of the same fields, which types `gen`'s `raw`; a submitted construct is checked against `construct_schema` itself, and the loader holds the two to each other (§5; MODULE_STRUCTURE §4.4) |
| `output_omissible`, `input_omissible`, `drop_priority` | the id properties of MCP_SPECIFICATION §2.1; compulsory in both directions and priority 0 by default, so an omissible class declares them and a leaf declares none |
| `namespace`, optional | the forest-wide namespace the node's name lives in, which the framework checks against the forest and the call (MODULE_STRUCTURE §4.2), and the `BadEdit` to raise when the name is taken — `Theory`'s short names, `DuplicateTheoryShortName` |
| `construction_job_class`, `evaluation_job_class`, optional | the class's job classes, `None` by default: the `Construction_Job` subclass `construct` starts on the node, the `Evaluation_Job` subclass an evaluation starts on it (CONSTRUCT_INTERACTION §3) |

The two schemas describe one thing twice, for two readers — the agent and
the type checker — and the loader holds them to each other (§5). Isabelle
text among a class's fields is typed `IsaTerm` (MODULE_STRUCTURE §4.3),
which `gen` builds with `IsaTerm.from_agent` from the submitted
string.

A class sets `name` in its `gen` to the name the agent supplied, or to
one computed from its fields (a `Datatype`'s, DATATYPE.md §2); the
framework makes the id component `<kind>_<name>` from it (MCP_SPECIFICATION
§2). Besides its own node, a class may read `forest().conversation` — what
MODULE_STRUCTURE §4.1 lists; of its log a class writes `note` records
alone, the named events being the framework's (LOGGING.md §3, §5) —,
`forest().id_of` for a node's id as the agent sees it, and its
`Theory`'s `print_name` over the stored `keywords`
(node_classes/SESSION_AND_THEORY.md §2), and
nothing with a leading underscore, except the hooks it is
meant to override: `_unfinished` and `_carries_job_from` on the node, `_states_inside` and
`_slots_written_by` for a slot the class owns, and on its job classes
`_run`, `_check`, `_on_context_change`, `_start` and `_finished`
(CONSTRUCT_INTERACTION §3.2, §3.3), as the evaluation hooks `_eval_opr`,
`_eval_beginning_opr` and `_eval_ending_opr` already are.

## 3. The construct schema

`construct_schema` is a Python `dict` holding the whole JSON schema of the
class's construct. The loader places it under `#/$defs/<class name>`,
hoisting its `$defs` to the top level (§4) and changing nothing else: it
invents no key and rewrites no schema of the class's own.

```python
@TAT_node
class Theorem(Theory_Member, Proof_Obligation, Leaf):
    construct_schema = {
        "type": "object",
        "properties": {
            "kind":      {"type": "string", "enum": ["lemma", "theorem", "corollary", "proposition"]},
            "name":      {"type": "string"},
            "statement": {"$ref": "#/$defs/LongStatement"},
        },
        "required": ["kind", "name", "statement"],
        "additionalProperties": False,
        "$defs": STATEMENT_DEFS,
    }
```

- `properties.kind` names, as an `enum` or a `const`, every kind the class
  answers to. It is the only source of that list: the kind table is built
  from it.
- A nesting class that lets the agent submit contents in one call
  declares `children` itself — `{"type": "array", "items": {"$ref":
  "#/$defs/Construct"}, ...}`, or with a narrower `items`, such as
  `Session`'s `{"type": "array", "items": {"$ref": "#/$defs/Theory"}}`.
  One that does not declare it takes contents only through later `edit`
  calls — a `children` in its construct is refused — and a narrower
  `items` describes where the classes' `gen`s let a node stand, the
  framework checking no containment (MODULE_STRUCTURE §4.2). A leaf
  class declares no `children`.
- Shared structures go in the class's own `$defs`, each key a Python
  identifier, and are used through `$ref`; a `$ref` under the top-level
  `children` names `Construct` or a node class (the bullet above), every other
  `$ref` a key of that `$defs`. Recursion is ordinary: a definition may
  refer to itself, provided every cycle of `$ref`s passes through an
  object — no `$defs` entry is a bare `$ref` — whose TypedDict nests
  itself and is defined at module level (MODULE_STRUCTURE §4.4).
- Every `description` is agent-facing text. For a class TAT ships, it is
  approved wording, kept in the class's document under `docs/node_classes/`
  beside its field table; for a class delivered separately, it is its
  author's.

The class is written in Python rather than as a JSON string because the
loader works on the structure — merging `$defs`, checking references — and
serialises once, at start.

## 4. Assembly

After every package is imported, the loader builds the `$defs` of the
`edit` schema once:

- `#/$defs/<class name>`: each class's `construct_schema`, in registration
  order — the order `UnknownKind` lists kinds in (EXCEPTIONS.md §3) — less
  its `$defs`, which the next item hoists; every `$ref` resolves at the
  document root, so the nested copy would be dead weight sent on every
  call;
- every class's `$defs`, merged by name at the top level (§5);
- `#/$defs/Construct`: `{"anyOf": [{"$ref": "#/$defs/Theory"}, {"$ref":
  "#/$defs/Theorem"}, ...]}` over the class entries, in the same order.

`edit`'s hand-written file (TOOL_SCHEMAS.md §1) carries an empty `$defs`;
`load` fills a copy of it for the conversation it is starting.

The assembled schema keeps its references. The loader never inlines a
`$ref`; a client that cannot take references is the MCP server's concern
(MODULE_STRUCTURE §4.6), not this document's.

## 5. What the loader checks

Every failure is a `CannotLoadPlugin` (EXCEPTIONS.md §1: a
`TAT_StartupError`, raised out of `launch_TAT`, or out of `compile_TAT`
during a compile, into the ML call that started the conversation or the
compile), carrying the package, the class, and the reason. At
registration, per class:

- `construct_schema` is a well-formed JSON schema
  (`jsonschema.Draft202012Validator.check_schema`), an object with
  `additionalProperties: false` at the top;
- `properties.kind` is present with an `enum` or a `const`, not both,
  and nothing else but `type` — `"string"` when present — and
  `description`, every value a string
  within the name grammar of MCP_SPECIFICATION §2 — it heads every id
  component `<kind>_<name>` — and `kind` is in `required`;
- no kind it names is registered by another class, and no other class has
  the same Python class name;
- no field of `construct_schema` bears the name of a row the framework
  stores, `kind` and `children` aside — `last_evaluation_statuses`
  (COMPILATION.md §4), `job`, `check` and `auto_construct` (ARCHITECTURE
  §4.1): such a class would load and then fail at its first store;
- if `children` is declared, the class is not a `Leaf`, `children` is
  not in `required` — no construct must carry it, and an amend's may not
  — and the property is `{"type": "array", "items": X}` and nothing else
  but a `description`, with `X` a `$ref` of the form `#/$defs/<Name>`,
  or an `anyOf` of such;
- the class is not omissible on output while compulsory on input
  (MCP_SPECIFICATION §2.1);
- a `construction_job_class`, when the class declares one, is a
  `Construction_Job` subclass that implements `title`, `failure_header`
  and `_run`, and overrides none of the framework's members —
  `can_start`, `start`, `cancel`, `ask`, `receive_answer`, `repeat_question`,
  `question_message` (CONSTRUCT_INTERACTION §3.2); an
  `evaluation_job_class` an `Evaluation_Job` subclass that implements
  `title`, `_start`, `failure_header` and `failure_notification`, and
  overrides neither `_report` nor `dropped_for` (§3.3);
- the class does not override `is_finished` — `_unfinished` is the
  override point (ARCHITECTURE §3.2) — nor `_operations_ready` nor
  `_own_statuses` (MODULE_STRUCTURE §4.1), nor `print` nor
  `_children_to_print` — `print_fields` and `mark` are (PRINT.md); the
  methods a class never overrides carry `typing.final` as well, so the
  type checker says it before the loader does;
- a `StdBlock` class does not override `emit` — the children are the
  framework's to place (COMPILATION.md §3) — and it overrides
  `_eval_ending_opr` exactly when it overrides `emit_ending`, since both
  say whether the class has an ending command;
- an override is a coroutine function exactly when the method it
  overrides is — the framework's, or one of the plugin's own base
  classes: `print_fields` and `mark` are plain, as rendering is
  synchronous (PRINT.md), and so are `can_emit`, `emit`, `emit_beginning`
  and `emit_ending`; the evaluation hooks are coroutines;
- the class defines neither `__eq__` nor `__hash__`: a node is equal to,
  and hashed as, itself alone, since nodes live in sets (PRINT.md §2);
- the class overrides `gen`, `to_store` and `from_store`: the framework's
  defaults only raise, and a class missing one would fail at its first
  edit or at the next start instead of here;
- `argument_schema` is a TypedDict — an empty one for a class with no
  fields — within the closed annotation grammar (MODULE_STRUCTURE §4.4),
  a field optionally wrapped in `NotRequired[X]` or `Required[X]`, which
  the loader reads off the annotation itself;
- every `$defs` key is a Python identifier, and no `$defs` entry is a
  bare `$ref`; every `$ref` outside the top-level `children` has the
  form `#/$defs/<Name>` and names a key of the class's own `$defs` —
  judgeable now, since a class carries what it refers to;
- every `$defs` entry is reached by a `$ref` of the class's schema
  outside the top-level `children`, directly or through other entries:
  the agreement check (below) keeps the keys it follows and compares
  them with the `$defs` keys, and an entry it never reached is refused,
  the class and the key named;
- the two schemas agree, at every depth, a `$ref` followed into
  `$defs`: an object carries `additionalProperties: false`, its
  `properties` are exactly the TypedDict's keys and its `required`
  exactly the TypedDict's required keys — at the top, `kind` and
  `children` set aside on the schema's side and `kind` on the
  TypedDict's, for `properties` and `required` alike; below the top,
  nothing set aside; a `string` is a `str`, or with an `enum` a
  `Literal` of those values; a `boolean`, an `integer` and a `number`
  are `bool`, `int` and `float`; an `array` is a list of what its
  `items` is, with `minItems: 1` a non-empty list; an `anyOf`, no arm
  of which is itself an `anyOf`, is a union whose arms pair with its
  own one for one — by JSON type, and TypedDicts told apart by a
  `Literal` by the values of the choosing field; a `$ref` met again
  with the annotation it was met with agrees without being followed
  again, which is how a definition that refers to itself meets a
  TypedDict that nests itself; and no schema carries a keyword besides
  these, `description`, and `$defs` at the top alone. Values, fields
  and arms are compared as
  sets, never by position, since an annotation does not reliably keep
  its order (MODULE_STRUCTURE §4.4). So what a construct schema says of
  the class's own fields — which the check enforces — is what `gen`'s
  `raw` holds. Which classes a
  `children` property's `items` admit describes where the classes'
  `gen`s let a node stand — `Bad<Class>NodeParent`, `NotInsideTheory` —
  the framework checking no containment (MODULE_STRUCTURE §4.2).

At assembly, once every class is known:

- every `$ref` under the top-level `children` names `Construct` or a
  node class, never a `$defs` entry of the class itself — a target only
  judgeable once every class is registered;
- no class's `$defs` uses a reserved name — `Construct` or any node class
  name;
- two classes defining the same `$defs` name define it equally (`dict`
  equality); otherwise the error names both classes and the name;
- the assembled `edit` schema is itself well-formed.

TAT's test suite validates the assembled schema again, with `jsonschema`,
against the classes TAT ships.

A compile hook (§1) is checked at registration too: a plain function of
one positional argument, neither a coroutine nor a generator. A compile runs on a forest
loaded from the database and never evaluated, every instant status
`not_evaluated`, so `can_emit`, `emit` and a hook read only what is
stored — authored fields, the recorded fields the class stores, its
`Theory`'s stored `keywords` through `print_name`,
`last_evaluation_statuses()`, `check_outcome()` and `job()`
(COMPILATION.md §3).
A hook finds its paths through `paths(working_directory)` of
`compile.py`, the one framework function it calls for them; it removes
only paths that listing yields, writes only beside a tree's file,
creating each file afresh, and never touches a `.thy` or the ROOT
(COMPILATION.md §5).

## 6. Where

Registration, the kind table, assembly and the argument schema grammar
live in `plugin.py` (MODULE_STRUCTURE §4.4); `edit`'s schema file is
`isabelle_theory_agent/tools/edit.jsonc`. `jsonschema` and
`jsoncomment` (which reads the `.jsonc` files, as in AoA) are dependencies
of the package.
