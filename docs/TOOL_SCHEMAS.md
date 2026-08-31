# Tool argument schemas

Status: design draft.

The concrete argument shapes of the tools MCP_SPECIFICATION §1 names, and the
first line a failed call renders. Ids resolve as MCP_SPECIFICATION §2.1; a
node description is MCP_SPECIFICATION §3.1's.

## 1. `edit`

Three actions, told apart by which key is present — exactly one of `append`,
`insert_before`, `amend` per call, always together with `nodes`, a non-empty
list of node descriptions.

| call | meaning |
| --- | --- |
| `{"append": <parent id>, "nodes": […]}` | add the nodes at the end of the parent's children |
| `{"insert_before": <id>, "nodes": […]}` | add the nodes before the addressed node, as its siblings |
| `{"amend": <id>, "nodes": […]}` | `nodes[0]` replaces the addressed node, its children inherited (MCP_SPECIFICATION §3.1); `nodes[1:]` follow the replacement |

## 2. `move`

`node` names the node to move; exactly one of three destination keys says
where, in the same language as `edit`'s actions:

| call | meaning |
| --- | --- |
| `{"node": <id>, "before": <id>}` | before the addressed node, as its sibling |
| `{"node": <id>, "after": <id>}` | after the addressed node, as its sibling |
| `{"node": <id>, "to": <parent id>}` | at the end of the parent's children |

## 3. `delete`

```
{"node": <id>}
```

Removes the node and its subtree.

## 4. What a failure renders

A failed `edit`, `move` or `delete` — the three tools that change the forest
(the glossary's broad **edit**, ARCHITECTURE §1) — opens with one line naming
the refused operation and its target, echoed from the call:

```
Cannot append theory_X.section_Basics
Cannot insert_before theory_X.lemma_P
Cannot amend theory_X.lemma_P
Cannot move theory_Sorting to after theory_X.section_Basics
Cannot move theory_Sorting to session_Arith
Cannot delete theory_X.section_Basics
```

The lines after it are the cause, prefixed by its `raw_ast_path`
(EXCEPTIONS.md §5) where one applies. The `opr` field (EXCEPTIONS.md §4)
takes exactly these operation names: `append`, `insert_before`, `amend`,
`move`, `delete`.

A failed read-only tool — `recall`, `construct`, `evaluate_to`, `status` —
renders the cause alone: it changed nothing, and the first line would only
repeat the tool the agent just called.

## 5. Undecided

- The argument shapes of `recall`, `construct`, `evaluate_to` and `status`.
- How `append` names the forest root: adding a `Session` targets it, and it
  has no id (MCP_SPECIFICATION §2).
