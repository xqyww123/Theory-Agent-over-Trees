# Tool argument schemas

Status: design draft. A section marked *(decided)* records the owner's
ruling; *(proposed)* is not settled.

The argument shape of every tool MCP_SPECIFICATION §1 names, and the first
line a failed call renders. The JSON schemas are hand-written, one file per
tool under `isabelle_theory_agent/tools/`, in the style of AoA's
(`contrib/Isa-Mini/IsaMini/AoA/tools/`); `edit`'s is completed at start
from the loaded node classes (PLUGIN_SYSTEM.md §4). Ids resolve as
MCP_SPECIFICATION §2.1.

A **construct** is what the agent submits to become a node: a JSON object
whose `kind` names the node class and whose other fields are that class's
own (MCP_SPECIFICATION §3.1). A nesting class's construct carries its
contents in `children`, a list of constructs.

## 1. `edit` *(decided 2026-09-04)*

Tool description: `Edit Isabelle theory constructs`.

```jsonc
{
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "enum": ["append", "insert_before", "amend"],
      "description": "append: add the constructs at the end of the target's children; insert_before: add them before the target, as its siblings; amend: replace the target with the given construct, inheriting the target's children."
    },
    "target_id":  { "type": "string", "description": "The id of the target node." },
    "constructs": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/$defs/Construct" },
      "description": "The constructs to add, in order."
    },
    "evaluate":   { "type": "boolean", "description": "Whether to evaluate the new nodes right away." }
  },
  "required": ["action", "target_id", "constructs", "evaluate"],
  "additionalProperties": false,
  "$defs": { }      // one entry per node class and `Construct`, their union: PLUGIN_SYSTEM.md §4
}
```

The forest root has the id `Sessions`, and `append` on it creates a
`Session`; every other action on it is refused (`ProtectedNode`). The
first layer is ordered like any other, so `insert_before` a session is an
ordinary insertion. `Sessions` is a reserved name: no node may bear it.

Under `amend` the first construct replaces the target, whose children it
inherits and whose identity it takes (MCP_SPECIFICATION §3.1); any further
constructs follow it.

Beyond the schema, TAT checks: no `children` on `amend`'s first construct
or on a leaf construct (`UnexpectedChildren`); and every construct's fields
against its class's argument schema (`UnexpectedField`, `MissingField`,
`InvalidField`), which the schema already enforces for a client that
validates it.

## 2. `move` *(decided 2026-09-04)*

Tool description: `Move an Isabelle theory construct`. The destination is
a **Location** (ARCHITECTURE §1) on the wire.

```jsonc
{
  "type": "object",
  "properties": {
    "source_id": { "type": "string", "description": "The id of the node to move, with its subtree." },
    "location": {
      "type": "object",
      "description": "Where it goes.",
      "properties": {
        "position": { "type": "string", "enum": ["before", "after", "into"],
                      "description": "before or after the node, as its sibling; into: at the end of the node's children." },
        "node_id":  { "type": "string", "description": "The node the position is relative to." }
      },
      "required": ["position", "node_id"],
      "additionalProperties": false
    },
    "evaluate": { "type": "boolean", "description": "Whether to evaluate the moved node right away." }
  },
  "required": ["source_id", "location", "evaluate"],
  "additionalProperties": false
}
```

## 3. `delete` *(decided 2026-09-04)*

Tool description: `Delete an Isabelle theory construct`.

```jsonc
{
  "type": "object",
  "properties": {
    "node_id": { "type": "string", "description": "The id of the node to delete, with its subtree." }
  },
  "required": ["node_id"],
  "additionalProperties": false
}
```

No `evaluate`: there is nothing new to see (MCP_SPECIFICATION §3.2).

## 4. What a failure renders

A failed `edit`, `move` or `delete` — the tools that change the forest
(the glossary's broad **edit**, ARCHITECTURE §1) — opens with one line
naming the refused operation and its target, echoed from the call:

```
Cannot append theory_X.section_Basics
Cannot insert_before theory_X.lemma_P
Cannot amend theory_X.lemma_P
Cannot move theory_Sorting to after theory_X.section_Basics
Cannot move theory_Sorting to session_Arith
Cannot delete theory_X.section_Basics
```

The lines after it are the cause, prefixed by its `raw_ast_path`
(EXCEPTIONS.md §5) where one applies; the path indexes `constructs`. The
`opr` field (EXCEPTIONS.md §4) takes exactly these operation names:
`append`, `insert_before`, `amend`, `move`, `delete`.

Any other tool's failure — `recall`, `construct`, `evaluate_to`, `status` —
renders the cause alone: the forest's shape is untouched, and a first line
would only repeat the tool the agent just called.

## 5. Undecided

The argument shapes of `recall`, `construct`, `evaluate_to` and `status`.
