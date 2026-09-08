# The plugin system

Status: design, approved 2026-09-04.

A node class is a plugin: an Isabelle theory carrying its evaluator, and a
Python package carrying everything else (ARCHITECTURE §6). This document is
the Python side of loading one — how a class registers, what the loader
checks, and how the loaded classes together complete the `edit` tool's
schema (TOOL_SCHEMAS.md §1). The ML side of registration is
MODULE_STRUCTURE §2.5; the conversation start that collects the packages,
§2.6.

## 1. Loading

The Python side of a plugin is a package, named by the module strings the
plugin's theory registers as `python_packages`. The ML side collects and
deduplicates them at conversation start and hands the list to `launch_TAT`;
`plugin.load` imports each with `importlib.import_module`. Importing is
what registers: a node class is defined at module top level under
`@TAT_node`, and the decorator runs as the class statement executes. The
two framework classes, `Session` and `Theory` (`model.py`), are registered
by `load` itself, first, through the same `TAT_node`. There is no other
table of node classes.

A package that fails to import — a syntax error, a registration check
below — fails the conversation start: a plugin's bug is never skipped
quietly.

## 2. What a class declares

A node class derives from `Leaf`, `StdBlock` or `Unchained_Node`
(MODULE_STRUCTURE §4.1) and is registered with `@TAT_node`, which takes no
arguments. Besides its hooks it declares, as class attributes:

| attribute | what it is |
| --- | --- |
| `construct_schema` | the complete JSON schema of a construct of this class, hand-written (§3) |
| `argument_schema` | a TypedDict of the same fields, which the framework checks a submitted construct against and which types `gen`'s `raw` (MODULE_STRUCTURE §4.4) |
| `output_omissible`, `input_omissible`, `drop_priority` | the id properties of MCP_SPECIFICATION §2.1 |
| `namespace`, optional | the forest-wide namespace the node's name lives in, which the framework checks against the forest and the call (MODULE_STRUCTURE §4.2), and the `BadEdit` to raise when the name is taken — `Theory`'s short names, `DuplicateTheoryShortName` |

The two schemas describe one thing twice, for two readers — the agent and
the type checker — and the loader holds them to each other (§5).

## 3. The construct schema

`construct_schema` is a Python `dict` holding the whole JSON schema of the
class's construct. The loader places it under `#/$defs/<class name>`,
hoisting its `$defs` to the top level (§4) and changing nothing else: it
invents no key and rewrites no schema of the class's own.

```python
@TAT_node
class Theorem(Leaf):
    construct_schema = {
        "type": "object",
        "description": "A theorem, stated but not proved.",
        "properties": {
            "kind":      {"type": "string", "enum": ["lemma", "theorem", "corollary"]},
            "statement": {"$ref": "#/$defs/LongStatement"},
            "tags":      {"type": "array", "items": {"type": "string"}, "description": "..."},
        },
        "required": ["kind", "statement"],
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
  calls. A leaf class declares no `children`.
- Shared structures go in the class's own `$defs` and are used through
  `$ref`; a `$ref` may name a key of that `$defs`, `Construct`, or another
  node class. Recursion is ordinary: a definition may refer to itself. The
  argument schema's grammar has no recursion (MODULE_STRUCTURE §4.4), so
  the TypedDict types such a field as `Any`.
- Every `description` is agent-facing text. For a class TAT ships, it is
  approved wording, kept in the class's document under `docs/node_classes/`
  beside its attribute table; for a class delivered separately, it is its
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
the server fills it at start and never afterwards. A class registering
after `load` has returned is refused (a `TAT_InternalError`: the
conversation is running, and a startup error has no reader).

The assembled schema keeps its references. The loader never inlines a
`$ref`; a client that cannot take references is the MCP server's concern
(MODULE_STRUCTURE §4.6), not this document's.

## 5. What the loader checks

Every failure is a `CannotLoadPlugin` (EXCEPTIONS.md §1: a
`TAT_StartupError`, reported to the client that starts the conversation),
carrying the package, the class, and the reason. At registration, per
class:

- `construct_schema` is a well-formed JSON schema
  (`jsonschema.Draft202012Validator.check_schema`), an object with
  `additionalProperties: false` at the top;
- `properties.kind` is present with an `enum` or a `const`, every value a
  string, and `kind` is in `required`;
- no kind it names is registered by another class, and no other class has
  the same Python class name;
- if `children` is declared, the class is not a `Leaf`, and the property
  is `{"type": "array", "items": X, ...}` with `X` a `$ref` of the form
  `#/$defs/<Name>`, or an `anyOf` of such;
- the class is not omissible on output while compulsory on input
  (MCP_SPECIFICATION §2.1);
- the class does not override `is_finished` — `_owes_nothing` is the
  override point (ARCHITECTURE §3.2);
- the class overrides `gen`, `to_store` and `from_store`: the framework's
  defaults only raise, and a class missing one would fail at its first
  edit or at the next start instead of here;
- `argument_schema` is a TypedDict — an empty one for a class with no
  fields — within the closed annotation grammar (MODULE_STRUCTURE §4.4);
- the two schemas agree: the keys of `properties`, less `kind` and
  `children`, are exactly the TypedDict's keys less `kind`, and
  `required`, less `kind` and `children`, is exactly the TypedDict's
  required keys less `kind`.

At assembly, once every class is known:

- every `$ref` in every class's schema has the form `#/$defs/<Name>`, and
  `<Name>` is a key of that class's own `$defs`, `Construct`, or a node
  class name;
- every `$ref` under a `children` property names `Construct` or a node
  class, never a `$defs` entry of the class itself — a target only
  judgeable once every class is registered;
- no class's `$defs` uses a reserved name — `Construct` or any node class
  name;
- two classes defining the same `$defs` name define it equally (`dict`
  equality); otherwise the error names both classes and the name;
- the assembled `edit` schema is itself well-formed.

TAT's test suite validates the assembled schema again, with `jsonschema`,
against the classes TAT ships.

## 6. Where

Registration, the kind table, assembly and the argument schema grammar
live in `plugin.py` (MODULE_STRUCTURE §4.4); `edit`'s schema file is
`isabelle_theory_agent/tools/edit.jsonc`. `jsonschema` and
`jsoncomment` (which reads the `.jsonc` files, as in AoA) are dependencies
of the package.
