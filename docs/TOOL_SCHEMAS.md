# Tool argument schemas

Status: design draft. A section marked *(decided)* records the owner's
ruling; *(proposed)* is not settled.

The argument shape of every tool MCP_SPECIFICATION §1 names — `recall`'s
is RECALL.md §3 — and the first line a failed call renders. The JSON
schemas are hand-written, one file per tool under
`isabelle_theory_agent/tools/`, in the style of AoA's
(`contrib/Isa-Mini/IsaMini/AoA/tools/`) though within the closed grammar
of MODULE_STRUCTURE §4.4, which is narrower than AoA's — no `default`, so
an optional argument's description states its default as `Default: …`;
no `anyOf`, no `minimum`; `edit`'s is completed at start from the loaded
node classes (PLUGIN_SYSTEM.md §4), and so are the descriptions of
`construct`, of `check_construct` and of `evaluate_to`'s `checks`, from
the loaded job classes' titles (CONSTRUCT_INTERACTION §5). Ids resolve as
MCP_SPECIFICATION §2.1.

A **construct** is what the agent submits to become a node: a JSON object
whose `kind` names the node class and whose other fields are that class's
own (MCP_SPECIFICATION §3.1). A nesting class's construct carries its
contents in `children`, a list of constructs.

## 1. `edit` *(decided 2026-09-04; `auto_construct` 2026-10-01)*

Tool description: `Edit Isabelle theory constructs`.

```jsonc
{
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "enum": ["append", "insert_before", "insert_after", "amend"],
      "description": "append: add the constructs at the end of the target's children (the way to give children marked `GivenLater`); insert_before: add them before the target, as its siblings; insert_after: add them after the target, as its siblings; amend: replace the target with the given construct, inheriting the target's children."
    },
    "target_id":  { "type": "string", "description": "The id of the target node; use `Sessions` when you are declaring a new Isabelle session." },
    "constructs": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/$defs/Construct" },
      "description": "The constructs to add, in order."
    },
    "evaluate":   { "type": "boolean", "description": "Whether to evaluate the new nodes right away." },
    "auto_construct": { "type": "boolean", "description": "True turns the new nodes' automatic construction on; false leaves it off. Default: false." }
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

`auto_construct` is there only when a loaded class names a construction
job class, like `construct` (§5). It is the value the automatic
construction (CONSTRUCT_INTERACTION §3.2) of every node the call adds
takes, where the node has a construction job — an amend's replacement
included, which does not inherit the replaced node's.

Beyond the schema, TAT checks: `append`'s target can hold children
(`HoldsNoChildren`); the forest's shape — a session under `Sessions`, a
theory under a session, every other construct inside a theory
(`BadNodeParent`, EXCEPTIONS.md §3); no `children` on `amend`'s first construct or on a
leaf construct (`UnexpectedChildren`), `GivenLater` where the class
declares `children` aside, on `amend`'s first construct too
(MCP_SPECIFICATION §3.1); and every construct's fields against
its class's construct schema (`UnexpectedField`, `MissingField`,
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
(`HoldsNoChildren`); the forest's shape — a session under `Sessions`, a
theory under a session, every other node inside a theory
(`BadNodeParent`, EXCEPTIONS.md §3); the destination is not inside the moved subtree
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
of the wrong type, outside its allowed set, an empty `constructs`, or
nested deeper than 100 levels —
is refused before any operation is named — one nested deeper than 100
levels before any other check, the rest against the schema the tool
advertises, as a construct's fields are checked (EXCEPTIONS.md §3's
`MissingField`, `UnexpectedField` and `InvalidField`, in their forms for
a tool call; RENDER_BASELINES §2) — and renders the cause alone:

```
The `edit` tool needs the argument `evaluate`.
The `edit` tool has no argument `kind`; it takes `action`, `target_id`, `constructs`, `evaluate`, `auto_construct`.
The argument `constructs` must be a list.
The argument `constructs` must not be empty.
The argument `constructs` must not be nested deeper than 100 levels.
The argument `action` must be one of `append`, `insert_before`, `insert_after`, `amend`.
The argument `location.position` must be one of `before`, `after`, `into`.
```

A **successful** `edit`, `move` or `delete` opens with one line naming
the operation and its target, echoed from the call — the `Done` line,
RENDER_BASELINES §6 — and its body closes with the quickview (PRINT.md §5): what
the call added, the moved node, or the deleted node's parent, with the
path to them. When the call evaluated and the walk stopped, the line
names the node it stopped at (ARCHITECTURE §3.3), in its shortest form;
whether the call evaluated at all, and how each node fared, the
quickview's marks say.

A **successful** `evaluate_to` opens with one line: the stop the call
reports — `Evaluation stopped at definition_f.`, the node in its
shortest form — or, when it reports none, its destination —
`Evaluation reached theory_X.`, also when `ignore_error` left the
destination `not_evaluated` under a failed beginning or behind an
import without a theory value (RENDER_BASELINES §6; ARCHITECTURE §3.3);
when the stop is the order
constraint's, RENDER_BASELINES §3's sentence follows on the next line,
as it does after an edit's `Done` line; then the quickview, the
destination at depth 0 (PRINT.md §5).

A **failed** `edit`, `move` or `delete` — the tools that change the forest
(the glossary's broad **edit**, ARCHITECTURE §1) — opens with one line
naming the refused operation and its target, echoed from the call — the
`Cannot` line, RENDER_BASELINES §1; a `move`'s target phrase carries the
position word, `theory_Sorting after theory_X.section_Basics`.
The lines after it are the cause, prefixed by its `raw_ast_path`
(EXCEPTIONS.md §5) where one applies; the path indexes `constructs`.
The `opr` field (EXCEPTIONS.md §4) takes exactly these operation
names: `append`, `insert_before`, `insert_after`, `amend`, `move`,
`delete`.

Any other tool's failure — `recall`, `evaluate_to`, `construct`,
`cancel_construct`, `check_construct`, `answer` — renders the cause
alone: it asked for nothing to be made or
unmade, and a first line would only repeat the tool the agent just
called.

## 5. `evaluate_to` and the construct tools *(decided 2026-09-30 and 2026-10-01, CONSTRUCT_INTERACTION §5)*

`evaluate_to`. Tool description: `Evaluate Isabelle theory constructs up
to a node. Already evaluated constructs are skipped.`

```jsonc
{
  "type": "object",
  "properties": {
    "node_id":      { "type": "string", "description": "The id of the node to evaluate up to, with its subtree; a theory's id means the whole theory." },
    "ignore_error": { "type": "boolean", "description": "Whether to carry on past a node that fails, so the nodes after it are evaluated too. Default: false." },
    "checks":       { "type": "string", "enum": ["no", "quick", "blocking"],
                      "description": "Whether to run the {titles} of the nodes: \"no\" runs none; \"blocking\" runs them and waits for them to finish before the call returns; \"quick\" runs them in the background, and you may wait for them with `check_construct` or go on (a failure will be reported to you, a success is silent). Default: \"quick\"." }
  },
  "required": ["node_id"],
  "additionalProperties": false
}
```

`checks` is absent when no loaded class names an evaluation job class;
its description is completed at start: `{titles}` are the loaded classes' evaluation-job titles in the plural,
distinct and alphabetical, joined with commas and `and`.

`construct`. Tool description, completed at start: `Start the
construction jobs of nodes, such as {construction titles, plural}.` —
with `Theorem` alone loaded, `Start the construction jobs of nodes, such
as proof constructions.`

```jsonc
{
  "type": "object",
  "properties": {
    "node_ids": { "type": "array", "minItems": 1, "items": { "type": "string" },
                  "description": "The ids of the nodes whose construction jobs to start; a non-leaf node stands for every node under it." },
    "auto_construct": { "type": "boolean", "description": "If true, automatically start the construction of each node whenever an evaluation reaches it and it is not constructed yet; false turns this automatic construction off. Default: false." }
  },
  "required": ["node_ids"],
  "additionalProperties": false
}
```

`cancel_construct`. Tool description: `Cancel the running construction
jobs of nodes.`

```jsonc
{
  "type": "object",
  "properties": {
    "node_ids": { "type": "array", "minItems": 1, "items": { "type": "string" },
                  "description": "The ids of the nodes whose construction jobs to cancel; a non-leaf node stands for every node under it." },
    "auto_construct": { "type": "boolean", "description": "True keeps their automatic construction on; false turns it off. Default: false." }
  },
  "required": ["node_ids"],
  "additionalProperties": false
}
```

A tool description says nothing of the arguments; each argument is
described in the schema. On all three tools that carry it — `edit`,
`construct`, `cancel_construct` — `auto_construct` is the value the
nodes' automatic construction takes, and leaving it out means off.

`check_construct`. Tool description, completed at start: `Wait until any
{construction titles, singular} or all {evaluation titles, plural} have
finished, or a message arrives. Returns at once when nothing is running.
To ensure all jobs have finished, call it repeatedly.` — with no
evaluation job class loaded, the `or all …` part absent and the verb
singular: `Wait until any {construction titles, singular} has finished,
or a message arrives. Returns at once when nothing is running. To ensure
all jobs have finished, call it repeatedly.` With no
construction job class loaded: `Wait until all {evaluation titles,
plural} have finished, or a message arrives. Returns at once when
nothing is running. To ensure all jobs have finished, call it
repeatedly.`

```jsonc
{
  "type": "object",
  "properties": {
    "wait_seconds": { "type": "integer", "description": "The time to wait at most, in seconds; the call returns earlier when a message arrives or every job has finished" }
  },
  "required": ["wait_seconds"],
  "additionalProperties": false
}
```

`answer`. Tool description: `Answer the question a construction job
asked you`.

```jsonc
{
  "type": "object",
  "properties": {
    "node_id": { "type": "string", "description": "The id of the node whose construction job asked the question" },
    "answer":  { "type": "object", "description": "The answer, in the shape the question asked for" }
  },
  "required": ["node_id", "answer"],
  "additionalProperties": false
}
```

`answer` is declared a bare object, the one such property the grammar of
MODULE_STRUCTURE §4.4 admits; at call time the pending question's own
schema takes its place, and the call is checked against that.
`construct`, `cancel_construct` and `answer` exist only when a loaded
class names a construction job class, `check_construct` when one names
a job class of either kind. What each returns, and on what a failed one renders, is
CONSTRUCT_INTERACTION §5.
