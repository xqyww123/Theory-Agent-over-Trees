# Reading the forest: `recall`

Status: decided (§1 and §2: MCP_SPECIFICATION §1.1, PRINT.md §5; §3, the
call: 2026-09-28, its read-only hint 2026-09-29; the rendering with no id
and both descriptions: 2026-09-30).

`recall` reads the forest: one node with what is under it, or the whole
forest. It renders and does nothing else — it evaluates nothing, changes
nothing, and its result carries no quickview. What Isabelle or the AFP
already provide — theorem search over material TAT did not write — is
not its business; that is the future `query` tool (MCP_SPECIFICATION
§1.1).

## 1. What it reads

- A node, by any id MCP_SPECIFICATION §2.1 accepts; with no id, the
  briefing of the whole forest: every node, one line each, to the bottom
  (§2).
- The forest as it stands at that instant. `recall` takes no lock: it
  reads the forest in memory (MCP_SPECIFICATION §5), so it answers while
  an `evaluate_to` runs — whose walk changes the statuses one node at a
  time — and several `recall`s answer at once (ARCHITECTURE §9).
- Reading never evaluates. A node that has not been evaluated shows
  `not evaluated` (PRINT.md §1) until a tool that evaluates runs.

## 2. What it renders

With an id, `Forest.render` of the node in `Recall` (PRINT.md §5): the
node at depth 0 and everything under it to depth 3. Each level is the
framework's line — the id in its shortest form and the mark, PRINT.md §1
— the class's `print_fields` for that depth, the framework's message
blocks (PRINT.md §3, §4) and its failure blocks where the node is
detailed (PRINT.md §2), and, under an
`incomplete` nesting node at depth 3, the framework's summary of what is
unfinished below it (PRINT.md §2); below depth 3 nothing, not even lines.
What each class writes at each depth is its own table: `Session` and
`Theory` in node_classes/SESSION_AND_THEORY.md §4, `Theorem` in
node_classes/THEOREM.md §8.

With no id, `Forest.render` of the forest root in `Briefing` (PRINT.md
§5), the **briefing** (ARCHITECTURE §1; the agent-facing text of §3
calls it an outline): every node of the forest, one line each — the id
in its shortest form and the mark, and the tags of
CONSTRUCT_INTERACTION §6 — `automatic construction` for every agent,
`needs your answer …` for the owner — to the bottom; no fields, no
messages, no summary. It is what an agent reads after its context was replaced
(CONSTRUCT_INTERACTION §8). `Sessions`, the root's id, given as the id
renders the root in `Recall` like any other node.

An evaluation's messages follow the framework's rule (PRINT.md §3, §4),
`Error:` and `Notice:` blocks alike: an operation's messages are written whole at depths 0 and 1, whatever the seen set
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

A `recall` of `Sessions`, the root, in `Recall` — two sessions, `A` finished and `B`
holding a theory not yet evaluated, which imports `A`'s tree; the
theories' nodes are at depth 3, where a `Theorem` writes nothing under
its line, and a `Session` at depth 1 writes no `description`:

```
Sessions:
- session_A (complete)
  parent_session: HOL
  - theory_Base (complete)
    imports: Main
    - lemma_A (valid statement, proven)
- session_B (incomplete)
  parent_session: HOL
  - theory_X (not evaluated)
    imports: Main A.Base
    - lemma_P (not evaluated, proof not started)
```

## 3. The call

Tool description: `Read an Isabelle theory construct with what is under it, briefer the deeper, or an outline of everything.`

```jsonc
{
  "type": "object",
  "properties": {
    "node_id": { "type": "string", "description": "The id of the node to read. Leave it out to read the outline of everything." }
  },
  "required": [],
  "additionalProperties": false
}
```

`node_id` is optional: a call without it renders the briefing (§2). The
call takes no depth: `Recall` fixes it, and the briefing has none.

A successful call answers the rendering alone — no `Done` line, no
quickview; the caller's undelivered messages follow the rendering as on every
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
resolves the id through `Forest.resolve`, renders the forest root in
`Briefing` when there is none, holds no lock, and is advertised read-only
(MCP_SPECIFICATION §5).
