# Reading the forest: `recall`

Status: decided (§1 and §2: MCP_SPECIFICATION §1.1, PRINT.md §5; §3, the
call: 2026-09-28, its read-only hint 2026-09-29).

`recall` reads the forest: one node with what is under it, or the whole
forest. It renders and does nothing else — it evaluates nothing, changes
nothing, and its result carries no quickview. What Isabelle or the AFP
already provide — theorem search over material TAT did not write — is
not its business; that is the future `query` tool (MCP_SPECIFICATION
§1.1).

## 1. What it reads

- A node, by any id MCP_SPECIFICATION §2.1 accepts; with no id, the
  whole forest, from its root.
- The forest as it stands at that instant. `recall` takes no lock: it
  reads the forest in memory (MCP_SPECIFICATION §5), so it answers while
  an `evaluate_to` runs — whose walk changes the statuses one node at a
  time — and several `recall`s answer at once (ARCHITECTURE §9).
- Reading never evaluates. A node that has not been evaluated shows
  `not evaluated` (PRINT.md §1) until a tool that evaluates runs.

## 2. What it renders

`Forest.render` of the node in `Recall` (PRINT.md §5): the node at
depth 0 and everything under it to depth 3. Each level is the
framework's line — the id in its shortest form and the mark, PRINT.md §1
— and the class's `print_fields` for that depth: at depths 0 and 1 the
node is detailed and the class writes everything it has; at depth 2 its
short form; at depth 3 what it writes at that depth; below depth 3
nothing, not even lines. What `Session` and `Theory` write at each depth
is node_classes/SESSION_AND_THEORY.md §4; what `Theorem` writes is
node_classes/THEOREM.md §8.

Errors follow `Theory`'s rule (PRINT.md §3, §4): an obstacle operation's
messages are written whole at depths 0 and 1, whatever the seen set
holds, and once per run at depths 2 and 3. Every rendering records what
it writes into the seen set, a `recall` included, so the quickview after
a `recall` does not repeat a message the `recall` showed.

The forest root and the lone session render as PRINT.md §6: a `recall`
of the whole forest with two or more sessions opens with `Sessions:`, no
dash and no mark, and lists the sessions under it; with exactly one
session, it opens with that session's line, without the dash, and what
the session writes stays at the same indent; with none, it is
`Sessions:` and the hint. A `recall` that starts at a session keeps the
dash.

A `recall` of the whole forest — two sessions, `A` finished and `B`
holding a theory not yet evaluated, which imports `A`'s tree; the
theories' nodes are at depth 3, where a `Theorem` writes nothing under
its line:

```
Sessions:
- session_A (success)
  parent_session: HOL
  - theory_Base (success)
    imports: Main
    - lemma_A (success)
- session_B
  parent_session: HOL
  description:
    Sorting, verified.
  - theory_X (not evaluated)
    imports: Main A.Base
    - lemma_P (not evaluated)
```

## 3. The call

Tool description: `Read an Isabelle theory construct with what is under it, briefer the deeper; read a construct itself to see it in full.`

```jsonc
{
  "type": "object",
  "properties": {
    "node_id": { "type": "string", "description": "The id of the node to read. Leave it out to read sessions." }
  },
  "required": [],
  "additionalProperties": false
}
```

`node_id` is the one optional argument of TAT's tools: a call without
it reads from the forest root. The call takes no depth: `Recall` fixes
it (§2).

A successful call answers the rendering alone — no `Done` line, no
quickview; the caller's pending messages ride on its end as on every
tool result (CONSTRUCT_INTERACTION.md §5). A failed call renders the
cause alone (TOOL_SCHEMAS.md §4): an id no node bears or several do
(`NodeNotFound`, `AmbiguousId`, RENDER_BASELINES §2), or a malformed
call, in the forms every tool shares:

```
`lemma_fo` is not found. Did you mean `lemma_foo` or `lemma_fold`?
The id `lemma_P` matches more than one node: `theory_X.lemma_P`, `theory_Y.lemma_P`. Choose the one you meant.
The `recall` tool has no argument `id`; it takes `node_id`.
```

The tool lives in `mcp.py` beside `edit`, `move` and `delete`
(MODULE_STRUCTURE §4.6), its schema in `tools/recall.jsonc`; it
resolves the id through `Forest.resolve`, renders the forest root when
there is none, holds no lock, and is advertised read-only
(MCP_SPECIFICATION §5).
