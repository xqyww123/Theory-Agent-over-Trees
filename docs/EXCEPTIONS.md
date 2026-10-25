# Exceptions

Status: design draft.

## 1. Four kinds

`TAT_Error` is what TAT says to the agent: an error the agent can act on,
raised anywhere, handled in exactly one place — the tool boundary — and
rendered into the tool result. The framework loops between the raise and the
boundary catch only to annotate and re-raise (§5).

`TAT_InternalError` is a bug: an invariant TAT itself broke. It does **not**
inherit from `TAT_Error`, and that absent inheritance is the load-bearing
line of the whole design: the tool boundary renders `TAT_Error` and nothing
else, so a bug can never dress up as an agent-facing error and be quietly
retried against. Bugs crash loud: the boundary catches one only to put it
where no agent can answer it — the conversation ends, and the exception
leaves `launch_TAT`, or `compile_TAT` during a compile, into the ML call
that started it, the door a `TAT_StartupError` uses (MODULE_STRUCTURE
§4.6). Two bugs the framework
raises on the client's behaviour: a tool call that no `PreToolUse`
announcement preceded, so TAT cannot tell which agent is calling — a
check every call goes through — and a client reporting an agent gone
with a job running, which no code path learns today
(CONSTRUCT_INTERACTION §7, §8).

An exception escaping an ML callback is a bug of this kind, by rule: a
callback answers every failure of its operation as data — the messages of a
failed header or `end`, a record per command — so whatever it lets through
is either the ML side's `TAT_Framework.Bug`, raised on purpose where TAT
caught itself out, or something the callback did not foresee; neither is
the agent's to act on. Every round trip goes through `isabelle_driver.call`,
which raises `TAT_IsabelleError`, a `TAT_InternalError`, from the RPC
library's `IsabelleError` — an escaped exception, or a failure of the wire
contract such as no callback registered under the name (MODULE_STRUCTURE
§2.5, §4.3); the connection going away answers a round trip with a
connection error instead, which is the conversation's ending and not a bug
(MODULE_STRUCTURE §4.3). A bare interrupt escaping the callback is answered by the RPC library
as `IsabelleInterrupt`, an `IsabelleError`, and is treated the same (one
inside a `Par_Exn` or an `Exn.EXCEPTIONS` is answered as its messages,
MODULE_STRUCTURE §2.5); TAT's callbacks all re-raise it afterwards, so it
then unwinds the ML call and with it the conversation. A node class's
callback follows the same rule, and `TAT_Common_Nodes.operation` is the
helper that keeps it: an exception under the operation becomes its
messages — a proper interrupt the one message `Interrupt` —, and a `Bug`
and every other interrupt propagate as they arrived. A `Bug`
raised in an evaluation job's work is a bug of this kind too: the job's
report carries it to Python, which raises it as a `TAT_InternalError`
(CONSTRUCT_INTERACTION §3.3).

`TAT_StartupError` is the third kind: TAT cannot run in this
environment — the working directory's database was written by another
schema version or is not a database, a node class package cannot be
loaded (PLUGIN_SYSTEM §1, §5), the Isabelle environment variable
`TAT_MAX_CONCURRENT_CONSTRUCTION_JOBS` holds a value that is neither
empty nor a positive integer (MODULE_STRUCTURE §4.6), another
conversation or a compile holds
the working directory (ARCHITECTURE §9), its lock file cannot be opened,
its log directory cannot be made (LOGGING.md §2), a `Session`'s folder
path under it holds something that is not a directory — a compile
refuses it before it removes anything (COMPILATION.md §2, §7), and a
conversation ends on it, or on a folder the system will not make, when
a theory of that `Session` begins (MODULE_STRUCTURE §4.1) — a file
`configure` writes for the agent client cannot be written
(CLIENT_HOOKS.md), the port cannot be bound, the agent client that
connects states, in its MCP
`initialize`, a version lower than the one TAT's client facts were
measured on, or none, or another client's name, or, at an announcement,
the payload names no transcript, the main conversation's transcript is
not found, or an agent's transcript TAT has found can no longer be
read, or a Codex tool call
carries a sandbox policy that is not the profile TAT configured
(CONSTRUCT_INTERACTION §8, CLIENT_HOOKS.md §5). It is raised out of
`launch_TAT`, or out of `compile_TAT` during a compile, at start, at the
first request of
the client's MCP session, at an agent's announcement, or at such a
call — before
the session or the call concerned is served, which is then refused and
enters the conversation's ending, as one raised at start does once the
conversation's log exists (MODULE_STRUCTURE §4.6) — into the ML
call that started the conversation or the compile, and is never rendered
to the agent. It inherits from neither of the other two.

`TAT_DisasterError` is the fourth: the forest in memory and the forest in
the working directory's database (ARCHITECTURE §4.1) have parted. A write
operation stores what it changed in one transaction at the end of its
synchronous commit block — after the pointer surgery, the in-memory
invalidation and the completed events (MODULE_STRUCTURE §4.2) — an
evaluating walk stores at each tree's end and when it ends, and each
synchronous step of a job that changes the job or the check on its node
— a construction's start, a run's settlement, an evaluation job's
report, an attach — stores the node in a transaction of its own, as does
a construct tool writing a node's automatic-construction setting
(ARCHITECTURE §4.1); so a transaction
that fails, whichever of these it is — a class's
`to_store` raising, a value MessagePack cannot hold, a full disk, another
process holding the write lock — leaves the two apart with no way to
rejoin them. `Forest_Store.transaction` raises it, from the failure, and
nothing answers it to the agent: the conversation ends, and the database holds the last
committed forest, which the next start loads. It inherits from none of the
other three.

The same line sorts what node classes raise:

- a `gen` reading over the wire through the framework's query functions
  gets data or a `TAT_IsabelleError`, never a `TAT_Error` it did not raise
  itself, so a failure on the Isabelle side is never mistaken for a
  class's bug, nor rendered to the agent;
- anything else a `gen` raises that is not a `TAT_Error` is never answered
  to the agent;
- the event hooks split by tense (MODULE_STRUCTURE §4.1): a gate may raise
  `BadEdit` to veto the change while nothing has happened; a completed hook
  fires after the change, so rendering "Cannot …" for what it raises would
  be a lie — anything it raises, `TAT_Error` included, is its class's bug;
- `_carries_job_from`, the question an amend's commit asks the
  replacement (CONSTRUCT_INTERACTION §3.1), is asked through
  `_completed`: anything it raises, `TAT_Error` included, is its class's
  bug;
- a construction job's `_run` has no tool call on the stack: it reports
  through the messages of CONSTRUCT_INTERACTION §3.4 and, while its run is
  still the job's, anything it raises is its class's bug, a cancellation
  it brought on itself included, and so is what its cleanup raises after
  a cancellation (CONSTRUCT_INTERACTION §3.2); so is
  anything its `_on_context_change` raises, `TAT_Error` included, which
  the status setter fires through `_completed` as it fires a completed
  hook; so is
  anything an evaluation job's `make` or `_start` raises, and anything a
  settlement raises — a run's end, a job's report — since a settlement
  answers no agent (CONSTRUCT_INTERACTION §9), but for the
  `TAT_DisasterError` of its own store's transaction (above);
- `can_emit`, `emit`, `emit_beginning`, `emit_ending` and a compile hook
  run under no tool call, on a forest loaded for a compile: anything
  they raise is the class's bug, and the compile ends with exit `2`
  (COMPILATION.md §5).
- `_eval_opr`, `_eval_beginning_opr` and `_eval_ending_opr` raise
  nothing: they answer the operation's status, a failure included
  (COMPILATION.md §4). A `TAT_Error` escaping one of them is the
  class's bug: `Forest._run` raises `TAT_InternalError` from it, so that
  it is never rendered to the agent. Anything else that escapes ends
  the conversation as it is, as at the tool boundary, keeping what it
  is — a bug of the class's; the connection going; the
  `TAT_StartupError` of `Theory`'s beginning for a `Session`'s folder
  that cannot be made (above).

## 2. Classified by the cause, not by the tool

Every concrete class names **what is wrong**, never **which tool was
running**. The agent knows which tool it called; the failing operation is
carried once, by the `opr` field (§4), not baked into class names. The
precedent to avoid is AoA, which classifies per operation and so holds
three classes for one cause — `NodeNotFound`, `CannotDelete_NodeNotFound`
and `CannotEdit_NodeNotFound` (`contrib/Isa-Mini/IsaMini/AoA/model.py`).

The groups under `TAT_Error` are the agent's remediation directions:
fix the id you gave (`ResolutionError`), fix the construct — or the
call — you submitted (`RawASTError`), rethink the change (`BadEdit`), the
construct tool refused — nothing to construct, not running, another's,
no question waiting (`ConstructionError`), or the question refused the
answer (`BadAnswer`). A failed forest-changing operation opens with the
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
├─ RawASTError                a submitted RawAST, or a tool call's own
│  │                          arguments, is malformed.  The group carries
│  │                          of_tool, written after the raise only when
│  │                          `check_call` read a tool's schema
│  │                          (§4's shape): the holder is a tool,
│  │                          the fields its arguments, and the three shape
│  │                          errors' sentences say so (TOOL_SCHEMAS §4)
│  ├─ MalformedRawAST         missing_kind — an object with no `kind`, or
│  │                          not an object at all                [framework]
│  ├─ UnknownKind             kind, available_kinds               [framework]
│  ├─ MissingField            holder, field — derived from the class's
│  │                          construct schema or the tool's schema, before
│  │                          a gen                               [framework]
│  ├─ UnexpectedField         holder, holder_is_top, field, takes — a field
│  │                          the class does not declare; holder is the
│  │                          kind or the tool (holder_is_top), or a nested
│  │                          container's path.  Schema-derived like
│  │                          MissingField, its dual              [framework]
│  └─ InvalidField            field, reason — schema-derived like
│                             MissingField; also ready-made for `gen`
│                             authors' semantic checks (a term Isabelle
│                             rejects, …), who derive further subclasses
│                             freely.  reason is a predicate completing
│                             "The field `X` …"
├─ BadEdit                    the request is well formed, but the change
│  │                          would break a standing rule; "edit" in the
│  │                          broad sense of the glossary (ARCHITECTURE §1)
│  ├─ DuplicateName           id_component — the `<kind>_<name>` two
│  │                          siblings would share (MCP_SPECIFICATION §2);
│  │                          taken_by — an existing sibling's id, or
│  │                          the colliding element's coordinate in its own
│  │                          list (`constructs[0]`, `children[2]`; the
│  │                          exception's raw_ast_path names that list):
│  │                          the two ask for opposite remedies   [framework]
│  ├─ InvalidName             name, grammar — outside the grammar named:
│  │                          the framework's name grammar of
│  │                          MCP_SPECIFICATION §2, checked where
│  │                          DuplicateName is [framework]; the theory
│  │                          name's [Theory.gen]; the session name's
│  │                          [Session.gen]; the fact, type, constant
│  │                          and locale names' — a plugin node's own
│  │                          name, the id grammar without hyphens
│  │                          (node_classes/COMMON.md §5) [the class's
│  │                          gen]; the seven grammars are
│  │                          RENDER_BASELINES §2's
│  ├─ DuplicateTheoryShortName  short_name, holder — the base heap, another
│  │                          tree, or a construct of the same call
│  │                          (its full path in the call) already uses
│  │                          the short name (MCP_SPECIFICATION §2)
│  │                                                  [Theory.gen, framework]
│  ├─ ReservedTheoryName      name — the Isabelle session layout declares
│  │                          the name global, or Isabelle reserves it as
│  │                          a file or theory name, so no tree can bear
│  │                          it (EVALUATOR_DESIGN §7; COMPILATION.md §2)
│  │                                                            [Theory.gen]
│  ├─ ReservedSessionName     name — Isabelle reserves the name as a file
│  │                          or session name, or it is `ROOT`, so no
│  │                          session can bear it (COMPILATION.md §2)
│  │                                                           [Session.gen]
│  ├─ UnexpectedChildren      kind, is_leaf — `children` may not appear
│  │                          here: a Leaf can hold none (is_leaf), and an
│  │                          amend's replacement inherits them; never
│  │                          silently dropped, `GivenLater` where the
│  │                          class declares `children` aside
│  │                          (MCP_SPECIFICATION §3.1). Raised before any
│  │                          gen runs                            [framework]
│  ├─ ChildrenNotInheritable  old_id, new_kind, children_count — the
│  │                          replaced node has children and the
│  │                          replacement class is a Leaf. Raised before
│  │                          any gen runs                        [framework]
│  ├─ BadNodeParent           kind, parent_id, remedy — the forest's
│  │  │                       shape, at the edit (MODULE_STRUCTURE §4.2):
│  │  │                       a node of any class but Session and Theory
│  │  │                       placed under the forest root or a Session,
│  │  │                       where no evaluation reaches it, at an
│  │  │                       insert, an amend and a move; parent_id a
│  │  │                       full id, remedy the sentence after the head
│  │  │                       (RENDER_BASELINES §2)               [framework]
│  │  ├─ BadSessionNodeParent  kind, parent_id — the remedy fixed; raised
│  │  │                       in Session's gen and on_moving for every
│  │  │                       parent but the forest root          [Session]
│  │  └─ BadTheoryNodeParent   kind, parent_id — the remedy fixed; raised
│  │                          in Theory's gen and on_moving for every
│  │                          parent but a Session                 [Theory]
│  ├─ MoveIntoOwnSubtree      id, destination — the move would make the
│  │                          node its own ancestor               [framework]
│  ├─ MoveBesideItself        id — the move is `before` or `after` the
│  │                          moved node itself                   [framework]
│  ├─ HoldsNoChildren         id, kind — the target of an `append` or a
│  │                          `move … into` is a leaf              [framework]
│  └─ ProtectedNode           id — the target is protected: the forest
│                             root `Sessions`, which takes `edit`'s `append`
│                             and a `move … into`, and nothing else
│                             (MCP_SPECIFICATION §2, TOOL_SCHEMAS §1, §2)
│                                                                  [framework]
├─ ConstructionError          abstract: a construct tool refused
│  │                          (CONSTRUCT_INTERACTION §5)
│  ├─ ConstructNotSupported   id, or none for several ids — `construct` or
│  │                          `cancel_construct` naming no node with a
│  │                          construction job                     [framework]
│  ├─ ConstructOwnedByAnother id — `answer` on a question of another
│  │                          agent's run                          [framework]
│  └─ NoQuestionPending       id — `answer` on a node where no question of
│  │                          the caller's waits: no construction job, a
│  │                          job not running, a run that asked nothing
│                                                                  [framework]
└─ BadAnswer                  message — the question's `receive` refused a
                              shape-valid answer; the question stays
                              pending (CONSTRUCT_INTERACTION §3.4)
                                                       [Interactive_Question]

TAT_InternalError             outside TAT_Error; never answered to the agent
└─ TAT_IsabelleError          an ML callback failed: it let an exception
                              escape, was interrupted, or no callback bears
                              the name; __cause__ is the RPC library's
                              IsabelleError
                                                          [isabelle_driver]

TAT_StartupError              outside both; TAT cannot run here (§1)
├─ IncompatibleStore          the database was written under another
│                             schema version                      [Forest_Store]
├─ ClientRefused              line — a refusal raised while serving: the
│                             client's version or name, Codex's sandbox,
│                             the main conversation's transcript not found
│                             (CONSTRUCT_INTERACTION §8); `line` is the
│                             ending's line for it (RENDER_BASELINES §4),
│                             which the constructor requires, so no
│                             refusal is answered as an internal error
│                                                              [TAT_Server]
├─ CannotUseWorkingDirectory  a `Session`'s folder cannot be made when a
│                             theory of it begins; the conversation ends
│                             (§1; MODULE_STRUCTURE §4.1)           [Theory]
└─ CannotLoadPlugin           package, node_class, reason — a package would
                              not import, or a node class failed a check
                              of PLUGIN_SYSTEM §5; node_class is None when
                              no class is named                   [plugin]

TAT_DisasterError             outside all three; memory and the database
                              have parted, the conversation ends (§1);
                              `__cause__` is what failed          [Forest_Store]
```

Every `TAT_Error` carries its facts as fields; `__str__` assembles the
agent-facing sentence from them. Logic tests assert on the fields; each
concrete class keeps one **render baseline** — the owner-approved
agent-facing wording, collected in RENDER_BASELINES.md. A reason a node
class's `gen` supplies to a framework exception — `InvalidField`'s
`<reason>`, whose shape alone is RENDER_BASELINES §2's — is approved in
that class's document under docs/node_classes/ and pinned by that class's
test, as `Session`'s and `Theory`'s reasons are in SESSION_AND_THEORY
§3 and test_session_theory.py; a plugin's own exception class keeps its
render baseline in the plugin's document, pinned by the plugin's tests.
Every other
test that meets a rendering
asserts the exception's class and fields, or reads the line from the
documents (TOOL_SCHEMAS §4's malformed-call block, RENDER_BASELINES §6's
success lines and RECALL.md §3's refusal block by test_mcp.py,
RENDER_BASELINES §5's node lines and RECALL.md §2's example by
test_print.py, RENDER_BASELINES §3's evaluation text by
test_conversation.py and test_forest_walk.py);
the lines the framework writes itself — the `Cannot <opr> <target>`
opening (RENDER_BASELINES §1), the `Done` line (§6) and a node's line
with its mark (§5) — a test may also spell out with its own ids. No test
outside the homes above spells out a cause sentence.

## 4. The `opr` field

The operations that change the forest — `append`, `insert_before`,
`insert_after`, `amend`, `move` and `delete` (TOOL_SCHEMAS.md) — write
their name into `opr` at the tool entry. `__str__` then opens with
`Cannot {opr} {target}`, the target echoed from the call
(TOOL_SCHEMAS.md §4). Any other tool — `recall`, `evaluate_to`,
`construct`, `cancel_construct`, `check_construct`, `answer` — writes
nothing, and the cause renders alone: it asked for nothing to be
made or unmade, and an opening line would only repeat what the agent
just called. A call refused on its own shape, before the operation is
known, renders alone the same way (TOOL_SCHEMAS.md §4).

`opr` is a field written once by the layer that knows it — like §5's, and
deliberately not a wrapper exception: an `except DuplicateName` means the
same thing at every depth, and no class exists whose fields could go
unfilled.

## 5. The `raw_ast_path` field

An error raised while building a batch must say which element: which index
of the submitted `constructs` list, nested under which `children`. AoA threads a
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
  full path, rendered as `constructs[2].children[0]`.

A coordinate always indexes the **submitted list** — never a position in
the forest; that is a Location (ARCHITECTURE §1), a different thing under a
different name. The amend loop walks the whole submitted list, `constructs[0]`
dispatched as the replacement, so its indexes are the agent's own.

Two rules keep this sound:

- **Everything on the unwind path re-raises the same object** — no
  wrapping, no substitution — whether the frame is the framework's or a
  nesting class's. The annotation accumulates on one exception, and an
  outer `except UnknownKind` still catches.
- **Nothing before the commit has side effects** (MODULE_STRUCTURE §4.2),
  so an aborted call needs no undoing: there is no rollback code for an
  exception to interrupt.

A class author cannot get the path wrong, because a class author never
writes it.

## 6. What is deliberately not an exception

- **Evaluation failure** is a status on the node — `cannot_evaluate`
  (ARCHITECTURE §3.2, §3.3) — or a job's outcome: the construction job's
  `FAILED`, the evaluation job's `FAILED` (CONSTRUCT_INTERACTION
  §3.1, §3.3), shown as the node's failure block and told once as a
  notification. A failing proof is a normal day at work, not an
  exception.
- **The jobs' results** arrive as messages from the recipient's mailbox,
  riding on its next tool result (CONSTRUCT_INTERACTION §3.4).

This is why the hierarchy is small where AoA's is large: AoA's edit admits
partial success, so it needs `EditOutcome.failure` and the whole
`CannotEdit` family to carry failure as data. TAT's edit applies whole or
not at all (MODULE_STRUCTURE §4.2), so there is no partially-applied
outcome to describe.
