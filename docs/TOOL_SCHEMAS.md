# Tool argument schemas

Status: design draft. A section marked *(decided)* records the owner's
ruling; *(proposed)* is not settled.

The argument shape of every tool MCP_SPECIFICATION §1 names — `recall`'s
is RECALL.md §3 — and the first line a failed call renders. The JSON
schemas are hand-written, one file per tool under
`isabelle_theory_agent/tools/`, in the style of AoA's
(`contrib/Isa-Mini/IsaMini/AoA/tools/`) though within the closed grammar
of MODULE_STRUCTURE §4.4, which is narrower than AoA's — no `default`, no
`anyOf`, no `minimum`; `edit`'s is completed at start from the loaded
node classes (PLUGIN_SYSTEM.md §4). Ids resolve as MCP_SPECIFICATION
§2.1.

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
      "enum": ["append", "insert_before", "insert_after", "amend"],
      "description": "append: add the constructs at the end of the target's children; insert_before: add them before the target, as its siblings; insert_after: add them after the target, as its siblings; amend: replace the target with the given construct, inheriting the target's children."
    },
    "target_id":  { "type": "string", "description": "The id of the target node; use `Sessions` when you are declaring a new Isabelle session." },
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
  // one entry per node class and `Construct`, their union: PLUGIN_SYSTEM.md §4
  "$defs": { }
}
```

The forest root has the id `Sessions`, and `append` on it creates a
`Session`; every other action on it is refused (`ProtectedNode`). The
first layer is ordered like any other, so `insert_before` a session is an
ordinary insertion. `Sessions` is the root's id, which no node's id
component can be (MCP_SPECIFICATION §2).

Under `amend` the first construct replaces the target, whose children it
inherits and whose identity it takes (MCP_SPECIFICATION §3.1); any further
constructs follow it.

Beyond the schema, TAT checks: `append`'s target can hold children
(`HoldsNoChildren`); no `children` on `amend`'s first construct or on a
leaf construct (`UnexpectedChildren`); and every construct's fields against
its class's argument schema (`UnexpectedField`, `MissingField`,
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

Beyond the schema, TAT checks: `into`'s node can hold children
(`HoldsNoChildren`); the destination is not inside the moved subtree
(`MoveIntoOwnSubtree`), nor `before` or `after` the moved node itself
(`MoveBesideItself`); neither the moved node nor a `before`/`after` node
is `Sessions` (`ProtectedNode`); and the moved node's id component is
free among its new siblings (`DuplicateName`).

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

## 4. What a call renders

A **malformed call** — an argument missing, one the tool does not take,
of the wrong type, outside its allowed set, or an empty `constructs` —
is refused against the schema the tool advertises, before any operation
is named and as a construct's fields are checked (EXCEPTIONS.md §3's
`MissingField`, `UnexpectedField` and `InvalidField`, in their forms for
a tool call; RENDER_BASELINES §2), and renders the cause alone:

```
The `edit` tool needs the argument `evaluate`.
The `edit` tool has no argument `kind`; it takes `action`, `target_id`, `constructs`, `evaluate`.
The argument `constructs` must be a list.
The argument `constructs` must not be empty.
The argument `action` must be one of `append`, `insert_before`, `insert_after`, `amend`.
The argument `location.position` must be one of `before`, `after`, `into`.
```

A **successful** `edit`, `move` or `delete` opens with one line naming
the operation and its target, echoed from the call — the `Done` line,
RENDER_BASELINES §6 — and ends with the quickview (PRINT.md §5): what
the call added, the moved node, or the deleted node's parent, with the
path to them. When the call evaluated and the walk stopped, the line
names the node it stopped at (ARCHITECTURE §3.3), in its shortest form;
whether the call evaluated at all, and how each node fared, the
quickview's marks say.

A **failed** `edit`, `move` or `delete` — the tools that change the forest
(the glossary's broad **edit**, ARCHITECTURE §1) — opens with one line
naming the refused operation and its target, echoed from the call — the
`Cannot` line, RENDER_BASELINES §1; a `move`'s target phrase carries the
position word, `theory_Sorting after theory_X.section_Basics`.
The lines after it are the cause, prefixed by its `raw_ast_path`
(EXCEPTIONS.md §5) where one applies; the path indexes `constructs`. The
`opr` field (EXCEPTIONS.md §4) takes exactly these operation names:
`append`, `insert_before`, `insert_after`, `amend`, `move`, `delete`.

Any other tool's failure — `recall`, `construct`, `evaluate_to`, `status` —
renders the cause alone: the forest's shape is untouched, and a first line
would only repeat the tool the agent just called.

## 5. Undecided

The argument shapes of `construct`, `evaluate_to` and `status`.
