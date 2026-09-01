# Tool argument schemas

Status: design draft.

The concrete argument shapes of the tools MCP_SPECIFICATION §1 names, and the
first line a failed call renders. Ids resolve as MCP_SPECIFICATION §2.1; a
node description is MCP_SPECIFICATION §3.1's.

## 1. `edit`

Three actions, told apart by which key is present — exactly one of `append`,
`insert_before`, `amend` per call, always together with `nodes`, a non-empty
list of node descriptions, and the mandatory boolean `evaluate`
(MCP_SPECIFICATION §3.2): whether to evaluate the change right away.

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

Every call also carries the mandatory boolean `evaluate`
(MCP_SPECIFICATION §3.2).

## 3. `delete`

```
{"node": <id>}
```

Removes the node and its subtree. No `evaluate` flag: there is nothing new
to see (MCP_SPECIFICATION §3.2).

## 4. `new_session`

```
{"session": <node description>}
```

Creates one `Session` at the forest's first layer — the one place the
editing tools do not serve: the forest root's id `$Root` is protected
(MCP_SPECIFICATION §2), and the first layer carries no order. The
tool itself fixes the description's `kind` to `session`, and it carries the
mandatory boolean `evaluate` (MCP_SPECIFICATION §3.2); `children` may
carry the `Session`'s first trees, built as any nested description is
(MODULE_STRUCTURE §4.1). Everything else about a `Session` goes through the
generic tools: it has an id, so `amend` and `delete` address it, and
`move … to` re-homes trees between `Session`s. A `Session` itself never
moves — there is nowhere else for it to live, and the first layer carries
no order (ARCHITECTURE §2).

## 5. What a failure renders

A failed `edit`, `move`, `delete` or `new_session` — the tools that change
the forest (the glossary's broad **edit**, ARCHITECTURE §1) — opens with one
line naming the refused operation and its target, echoed from the call:

```
Cannot append theory_X.section_Basics
Cannot insert_before theory_X.lemma_P
Cannot amend theory_X.lemma_P
Cannot move theory_Sorting to after theory_X.section_Basics
Cannot move theory_Sorting to session_Arith
Cannot delete theory_X.section_Basics
Cannot new_session session_Arith
```

The lines after it are the cause, prefixed by its `raw_ast_path`
(EXCEPTIONS.md §5) where one applies. The `opr` field (EXCEPTIONS.md §4)
takes exactly these operation names: `append`, `insert_before`, `amend`,
`move`, `delete`, `new_session`.

Any other tool's failure — `recall`, `construct`, `evaluate_to`, `status` —
renders the cause alone: the forest's shape is untouched, and a first line
would only repeat the tool the agent just called.

## 6. Undecided

The argument shapes of `recall`, `construct`, `evaluate_to` and `status`.
