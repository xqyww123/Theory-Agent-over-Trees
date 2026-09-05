# Exceptions

Status: design draft.

## 1. Three kinds

`TAT_Error` is what TAT says to the agent: an error the agent can act on,
raised anywhere, handled in exactly one place — the tool boundary — and
rendered into the tool result. The framework loops between the raise and the
boundary catch only to annotate and re-raise (§5).

`TAT_InternalError` is a bug: an invariant TAT itself broke. It does **not**
inherit from `TAT_Error`, and that absent inheritance is the load-bearing
line of the whole design: the tool boundary catches `TAT_Error` and nothing
else, so a bug can never dress up as an agent-facing error and be quietly
retried against. Bugs escape and crash loud.

`TAT_StartupError` is the third kind, and the smallest: TAT cannot start in
this environment — the working directory's database was written by another
schema version, or is not a database. It is raised before any tool boundary
or agent exists, to the client that starts the conversation, and is never
rendered to the agent. It inherits from neither of the other two.

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
the goal another way. A failed forest-changing operation opens with the
refused operation (§4); the cause — under it, or alone for the other
tools — tells the agent which direction it is.

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
│  ├─ MalformedRawAST         missing_kind — an object with no `kind`, or
│  │                          not an object at all                [framework]
│  ├─ UnknownKind             kind, available_kinds               [framework]
│  ├─ MissingField            kind, field — derived from the class's declared
│  │                          argument schema, before its gen     [framework]
│  ├─ UnexpectedField         holder, holder_is_kind, field, takes — a field
│  │                          the class does not declare; holder is the
│  │                          kind (holder_is_kind), or a nested container's
│  │                          path.  Schema-derived like MissingField, its
│  │                          dual                                [framework]
│  └─ InvalidField            field, reason — schema-derived like
│                             MissingField; also ready-made for `gen`
│                             authors' semantic checks (a term Isabelle
│                             rejects, …), who derive further subclasses
│                             freely.  reason is a predicate completing
│                             "The field `X` …"
├─ BadEdit                    the request is well formed, but the change
│  │                          would break a standing rule; "edit" in the
│  │                          broad sense of the glossary (ARCHITECTURE §1)
│  ├─ DuplicateName           name; taken_by — an existing sibling's id, or
│  │                          the colliding element's coordinate in its own
│  │                          list (`nodes[0]`, `children[2]`; the
│  │                          exception's raw_ast_path names that list):
│  │                          the two ask for opposite remedies   [framework]
│  ├─ InvalidName             name — outside the name grammar of
│  │                          MCP_SPECIFICATION §2; checked where
│  │                          DuplicateName is                    [framework]
│  ├─ DuplicateTheoryShortName  short_name, holder — the base heap or
│  │                          another tree already uses the short name
│  │                          (MCP_SPECIFICATION §2)              [Theory.gen]
│  ├─ UnexpectedChildren      kind, is_leaf — `children` may not appear
│  │                          here: a Leaf can hold none (is_leaf), and an
│  │                          amend's replacement inherits them; never
│  │                          silently dropped. Raised before any gen
│  │                          runs                                [framework]
│  ├─ ChildrenNotInheritable  old_id, new_kind, children_count — the
│  │                          replaced node has children and the
│  │                          replacement class is a Leaf. Raised before
│  │                          any gen runs                        [framework]
│  ├─ Bad<Class>NodeParent    kind, parent_id — the class cannot live under
│  │                          that parent. Not one class: each node class
│  │                          derives its own from BadEdit, named after
│  │                          itself, and raises it in its gen and
│  │                          on_moving — BadTheoremNodeParent,
│  │                          BadTheoryNodeParent, BadSessionNodeParent
│  │                          (Session's gen refuses every parent but the
│  │                          forest root). The framework checks no
│  │                          containment
│  ├─ MoveIntoOwnSubtree      id, destination — the move would make the
│  │                          node its own ancestor               [framework]
│  └─ ProtectedNode           id — the target is protected; the one such
│                             node is the forest root, id `$Root`
│                             (MCP_SPECIFICATION §2)              [framework]
├─ ConstructFailed            `construct` could not start
│  └─ ConstructNotSupported   id — raised by Node.construct's default
│                             implementation; a class with a `construct`
│                             overrides it (MCP_SPECIFICATION §1)

TAT_InternalError             outside TAT_Error; never caught at the boundary

TAT_StartupError              outside both; TAT cannot start here (§1)
└─ IncompatibleStore          the database was written under another
                              schema version                      [Forest_Store]
```

Every `TAT_Error` carries its facts as fields; `__str__` assembles the
agent-facing sentence from them. Logic tests assert on the fields; each
concrete class keeps one **render baseline** — the owner-approved
agent-facing wording, collected in RENDER_BASELINES.md — and no other test
touches the rendered string.

## 4. The `opr` field

The six operations that change the forest — `append`, `insert_before`,
`amend`, `move`, `delete` and `new_session` (TOOL_SCHEMAS.md) — write their
name into `opr` at the tool entry. `__str__` then opens with
`Cannot {opr} {target}`, the target echoed from the call
(TOOL_SCHEMAS.md §5). Any other tool
writes nothing, and the cause renders alone: the forest's shape is
untouched, and an opening line would only repeat what the agent just
called.

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

- a node class's `gen` raises bare — an `InvalidField`, a
  `DuplicateTheoryShortName` — knowing nothing about where its RawAST sat;
- the framework's per-element loop prefixes the element's coordinate and
  re-raises the same object — around everything it does for that element,
  its own checks included: the `kind` lookup, the schema check, the name
  checks;
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

- **Evaluation failure** is a status on the node — `cannot_evaluate`, with
  its `blocked_by` (ARCHITECTURE §3.2, §3.3) — or a recorded
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
