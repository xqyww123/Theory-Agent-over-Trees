# Exceptions

Status: design draft.

## 1. Two worlds

`TAT_Error` is what TAT says to the agent: an error the agent can act on,
raised anywhere, handled in exactly one place — the tool boundary — and
rendered into the tool result. The framework loops between the raise and the
boundary catch only to annotate and re-raise (§5).

`TAT_InternalError` is a bug: an invariant TAT itself broke. It does **not**
inherit from `TAT_Error`, and that absent inheritance is the load-bearing
line of the whole design: the tool boundary catches `TAT_Error` and nothing
else, so a bug can never dress up as an agent-facing error and be quietly
retried against. Bugs escape and crash loud.

The same line sorts what node classes raise:

- the framework's query callbacks raise only `TAT_Error` subclasses across
  the `gen` boundary, so a transport failure is never mistaken for a class's
  bug;
- anything else a `gen` raises that is not a `TAT_Error` is not caught at
  the tool boundary;
- the event hooks split by tense (MODULE_STRUCTURE §4.1): a gate may raise
  `BadEdit` to veto the change while nothing has happened; a completed hook
  fires after the change, so rendering "Cannot …" for what it raises would
  be a lie — anything it raises, `TAT_Error` included, is its class's bug;
- `construct`'s background work has no tool call on the stack: it reports
  through the messages of MCP_SPECIFICATION §5 and never raises into the
  framework.

## 2. Classified by the cause, not by the tool

Every concrete class names **what is wrong**, never **which tool was
running**. The agent knows which tool it called; the failing operation is
carried once, by the `opr` field (§4), not baked into class names. The
precedent to avoid is AoA, which classifies per operation and so holds
three classes for one cause — `NodeNotFound`, `CannotDelete_NodeNotFound`
and `CannotEdit_NodeNotFound` (`contrib/Isa-Mini/IsaMini/AoA/model.py`).

The groups under `TAT_Error` are the agent's four remediation directions:
fix the id you gave (`ResolutionError`), fix the node description you
submitted (`RawASTError`), rethink the change (`BadEdit`), or — for
`ConstructFailed` — the node's class does not offer the operation, so reach
the goal another way. A rendered error opens with the refused operation
(§4); the cause under it tells the agent which direction it is.

## 3. The hierarchy

A bracketed tag marks who raises the class; an untagged class is for node
class authors.

```
TAT_Error                     two framework-written fields: raw_ast_path (§5), opr (§4)
├─ ResolutionError            an id failed to designate exactly one node
│  ├─ NodeNotFound            id, near_matches — the closest existing ids,
│  │                          a guess list                        [framework]
│  └─ AmbiguousId             id, candidates — every node the id matches,
│                             each in its shortest unambiguous form
│                             (MCP_SPECIFICATION §2.1)            [framework]
├─ RawASTError                a submitted RawAST is malformed
│  ├─ MalformedRawAST         not an object, or no `kind`         [framework]
│  ├─ UnknownKind             kind, available_kinds               [framework]
│  ├─ MissingField            field — derived from the class's declared
│  │                          argument schema, before its gen     [framework]
│  └─ InvalidField            field, reason — schema-derived like
│                             MissingField; also ready-made for `gen`
│                             authors' semantic checks (a term Isabelle
│                             rejects, …), who derive further subclasses
│                             freely
├─ BadEdit                    the request is well formed, but the change
│  │                          would break a standing rule; "edit" in the
│  │                          broad sense of the glossary (ARCHITECTURE §1)
│  ├─ DuplicateName           name; taken_by — an existing sibling's id, or
│  │                          the raw_ast_path of the colliding element of
│  │                          the same call: the two ask for opposite
│  │                          remedies. The same check refuses a name that
│  │                          is not a single id component        [framework]
│  ├─ DuplicateTheoryBaseName base_name, holder — the base heap or another
│  │                          tree already uses the base name
│  │                          (MCP_SPECIFICATION §2)              [Theory.gen]
│  ├─ UnexpectedChildren      children_count, children_ids — `children`
│  │                          may not appear here: on an amend's
│  │                          replacement they are inherited (the ids say
│  │                          what will be), and a Leaf can hold none;
│  │                          never silently dropped. Raised before any
│  │                          gen runs                            [framework]
│  ├─ ChildrenNotInheritable  old_id, new_kind — the replaced node has
│  │                          children and the replacement class is a
│  │                          Leaf. Raised before any gen runs    [framework]
│  ├─ WrongParent             kind, parent_id — the class cannot live under
│  │                          that parent; ready-made for `gen` and
│  │                          `on_moving`
│  ├─ MoveIntoOwnSubtree      id, destination — the move would make the
│  │                          node its own ancestor               [framework]
│  └─ ProtectedNode           id — the target is the forest root, which no
│                             edit, move or delete may touch      [framework]
├─ ConstructFailed            `construct` could not start
│  └─ ConstructNotSupported   kind — the class has no `construct`
│                             (MCP_SPECIFICATION §1)              [framework]

TAT_InternalError             outside TAT_Error; never caught at the boundary
```

Every class carries its facts as fields; `__str__` assembles the
agent-facing sentence from them. Logic tests assert on the fields; each
concrete class keeps one **render baseline** — the reviewed, owner-approved
agent-facing wording — and no other test touches the rendered string.

## 4. The `opr` field

The six operations that change the forest — `append`, `insert_before`,
`amend`, `move`, `delete` and `new_session` (TOOL_SCHEMAS.md) — write their
name into `opr` at the tool entry. `__str__` then opens with
`Cannot {opr} {target}`, the target echoed from the call
(TOOL_SCHEMAS.md §5). A read-only tool
writes nothing, and the cause renders alone: the tool changed nothing, and
an opening line would only repeat what the agent just called.

`opr` is a field written once by the layer that knows it — like §5's, and
deliberately not a wrapper exception: an `except DuplicateName` means the
same thing at every depth, and no class exists whose fields could go
unfilled.

## 5. The `raw_ast_path` field

An error raised while building a batch must say which element: which index
of the submitted `nodes` list, nested under which `children`. AoA threads a
`path` string down through every parser signature; TAT's `gen(cls, config,
raw)` deliberately has no such parameter. The path is instead written
**upward** by the framework:

- a node class's `gen` raises bare — `MissingField("statement")` — knowing
  nothing about where its RawAST sat;
- the framework's per-element loop prefixes the element's coordinate and
  re-raises the same object — around everything it does for that element,
  its own checks included: the `kind` lookup, the schema check, the name
  checks, the gates;
- nesting prefixes `children` steps, so the unwinding loops spell out the
  full path, rendered as `nodes[2].children[0]`.

A coordinate always indexes the **submitted list** — never a position in
the forest; that is a Location (ARCHITECTURE §1), a different thing under a
different name. The amend loop walks the whole submitted list, `nodes[0]`
dispatched as the replacement, so its indexes are the agent's own.

Two rules keep this sound:

- **Everything on the unwind path re-raises the same object** — no
  wrapping, no substitution — whether the frame is the framework's or a
  nesting class's. The annotation accumulates on one exception, and an
  outer `except UnknownKind` still catches.
- **Nothing before the commit has side effects** (MODULE_STRUCTURE §4.1),
  so an aborted call needs no undoing: there is no rollback code for an
  exception to interrupt.

A class author cannot get the path wrong, because a class author never
writes it.

## 6. What is deliberately not an exception

- **Evaluation failure** is a status on the node —
  `cannot_evaluate(blocked_by)` (ARCHITECTURE §3.2, §3.3) — or a recorded
  outcome of its class, such as `Theorem`'s `proof = failed`
  (ARCHITECTURE §2.2), reported in the tool result. A failing proof is a
  normal day at work, not an exception.
- **`construct` results** arrive as messages riding on tool results
  (MCP_SPECIFICATION §5).

This is why the hierarchy is small where AoA's is large: AoA's edit admits
partial success, so it needs `EditOutcome.failure` and the whole
`CannotEdit` family to carry failure as data. TAT's edit applies whole or
not at all (MODULE_STRUCTURE §4.1), so there is no partially-applied
outcome to describe.
