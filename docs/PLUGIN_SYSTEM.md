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
`@TAT_node`, and the decorator runs as the class statement executes. There
is no other table of node classes.

A package that fails to import — a syntax error, a registration check
below — fails the conversation start: a plugin's bug is never skipped
quietly.

## 2. What a class declares

A node class derives from `Leaf` or `StdBlock` (MODULE_STRUCTURE §4.1) and
is registered with `@TAT_node`, which takes no arguments. Besides its hooks
it declares, as class attributes:

| attribute | what it is |
| --- | --- |
| `construct_schema` | the complete JSON schema of a construct of this class, hand-written (§3) |
| `argument_schema` | a TypedDict of the same fields, which the framework checks a submitted construct against and which types `gen`'s `raw` (MODULE_STRUCTURE §4.1) |
| `output_omissible`, `input_omissible`, `drop_priority` | the id properties of MCP_SPECIFICATION §2.1 |

The two schemas describe one thing twice, for two readers — the agent and
the type checker — and the loader holds them to each other (§5).

## 3. The construct schema

`construct_schema` is a Python `dict` holding the whole JSON schema of the
class's construct. The loader places it under `#/$defs/<class name>`
unchanged: it adds no key and rewrites none.

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
  "#/$defs/Construct"}, ...}`, or a narrower union such as `Session`'s
  `{"$ref": "#/$defs/Theory"}`. One that does not declare it takes
  contents only through later `edit` calls. The runtime rule that a leaf
  holds no children (`UnexpectedChildren`) stands regardless.
- Shared structures go in the class's own `$defs` and are used through
  `$ref`; a `$ref` may name a key of that `$defs`, `Construct`, or another
  node class. Recursion is ordinary: a definition may refer to itself.
- Every `description` is agent-facing text. For a class TAT ships, it is
  approved wording (RENDER_BASELINES.md); for a class delivered separately,
  it is its author's.

The class is written in Python rather than as a JSON string because the
loader works on the structure — merging `$defs`, checking references — and
serialises once, at start.

## 4. Assembly

After every package is imported, the loader builds the `$defs` of the
`edit` schema once:

- `#/$defs/<class name>`: each class's `construct_schema`, in registration
  order — the order `UnknownKind` lists kinds in (EXCEPTIONS.md §3);
- every class's `$defs`, merged by name (§5);
- `#/$defs/Construct`: `{"anyOf": [{"$ref": "#/$defs/Theory"}, {"$ref":
  "#/$defs/Theorem"}, ...]}` over the class entries, in the same order.

`edit`'s hand-written file (TOOL_SCHEMAS.md §1) carries an empty `$defs`;
the server fills it at start and never afterwards. A class registering
after `load` has returned is refused.

The assembled schema keeps its references. The loader never inlines a
`$ref`; a client that cannot take references is the MCP server's concern,
not this document's.

## 5. What the loader checks

Every failure is a `CannotLoadPlugin` (EXCEPTIONS.md §1: a
`TAT_StartupError`, reported to the client that starts the conversation),
carrying the package, the class, and the reason. At registration, per
class:

- `construct_schema` is a well-formed JSON schema
  (`jsonschema.Draft202012Validator.check_schema`);
- `properties.kind` is present with an `enum` or a `const`;
- no kind it names is registered by another class;
- the class is not omissible on output while compulsory on input
  (MCP_SPECIFICATION §2.1);
- `argument_schema` is within the closed annotation grammar
  (MODULE_STRUCTURE §4.1);
- the two schemas agree: the keys of `properties`, less `kind` and
  `children`, are exactly the TypedDict's keys, and `required`, less
  `kind`, is exactly the TypedDict's required keys.

At assembly, once every class is known:

- every `$ref` in every class's schema has the form `#/$defs/<Name>`, and
  `<Name>` is a key of that class's own `$defs`, `Construct`, or a node
  class name;
- no class's `$defs` uses a reserved name — `Construct` or any node class
  name;
- two classes defining the same `$defs` name define it equally (`dict`
  equality); otherwise the error names both classes and the name;
- the assembled `edit` schema is itself well-formed.

TAT's test suite validates the assembled schema again, with `jsonschema`,
against the classes TAT ships.

## 6. Where

Registration, the kind table and assembly live in `plugin.py`; `edit`'s
schema file is `isabelle_theory_agent/tools/edit.jsonc`. `jsonschema` is a
dependency of the package.
