# Module structure

Status: design draft.

## 1. Directories and files

The layout follows the sibling repositories (`contrib/Isa-Mini`,
`contrib/Isabelle_RPC`): an Isabelle component and a Python package in one
repository, one version number for both.

```
Theory_Agent_over_Trees.thy   ML_file "ML/TAT_Framework.ML"; ML_file "ML/TAT_Common_Nodes.ML"
ML/TAT_Framework.ML           structure TAT_Framework (§2)
ML/TAT_Common_Nodes.ML        structure TAT_Common_Nodes (§3)
Dev/TAT_Dev.thy               the development launcher's app: an Isa-REPL app that starts one conversation (ARCHITECTURE §9)
ROOT                          build checks only; nothing ever runs on these heaps
etc/settings                  the Isabelle component: TAT_HOME="$COMPONENT"
isabelle_theory_agent/        the Python package (§4); the pip and conda packages carry the same name
isabelle_theory_agent/tools/  the tools' hand-written JSON schemas (TOOL_SCHEMAS.md)
test/                         test_*.py for the Python side, Test_*.thy for the ML side,
                              and their non-pytest helper modules
docs/                         the design
pyproject.toml, VERSION       the Python package; VERSION is the one number pip and conda read
conda/recipe.yaml             the conda package
COPYING, COPYING.LIB, COPYRIGHT   LGPL-2.1-or-later, as in Isa-Mini
```

The `ROOT` exists because registering the repository as an Isabelle session
root requires one; its Isabelle sessions are compile checks of the sources. A running
conversation never sits on those heaps: it loads `Theory_Agent_over_Trees.thy` —
and every node class theory the starting theory imports — from source on the
base heap when it starts (ARCHITECTURE §8), finding it through `$TAT_HOME`.

One structure per file, and two structures in all. Inside a file the body is
divided by Isabelle's sectioning comments — `(*** section ***)`,
`(** subsection **)`, `(* subsubsection *)` — following
`contrib/Isabelle2025-2/src/Doc/Implementation/ML.thy:60-97`.

`TAT_Framework` knows no node class. `TAT_Common_Nodes` is its first client and
carries the predefined node classes, and the helpers a node class writes its
callbacks with (`operation`, §3); a node class delivered separately
(ARCHITECTURE §6) is another client of the same interface, free to use
`TAT_Common_Nodes` as well *(relaxed 2026-09-09; before, it never depended on
it)*. The test for where something belongs: what the conversation itself
needs — its tables, its loader, its callbacks — is in `TAT_Framework`; what
only a node class needs is in `TAT_Common_Nodes`.

## 2. `TAT_Framework`

### 2.1 State slots

The state slot table (EVALUATOR_DESIGN §1.1): one per conversation, locked,
and reached only through five operations.

| operation | used when |
| --- | --- |
| `put` | a node's commands have run and its resulting state is stored |
| `get` | a node is about to run, from the state its input slot names |
| `copy` | one slot's state stands as another's: a class with no ending command, a failed node passed over (ARCHITECTURE §3.1), a node inserted or deleted (ARCHITECTURE §3.4). Afterwards the target holds what the source holds — nothing, when the source holds nothing |
| `delete` | a node leaves `ready`, or is deleted; takes a list of names, so a batch is one round trip |
| `exists` | the Python side asks whether a slot holds a state |

### 2.2 Theory table

The map from qualified theory name (EVALUATOR_DESIGN §7) to `theory` value
(EVALUATOR_DESIGN §3), locked like the state slot table. `put` overwrites and `lookup` reads;
nothing else. The key of an entry `end_theory` writes is the theory value's
own long name — the same string §2.3's resolution produces.

### 2.3 Theory loader

Import resolution in the order of EVALUATOR_DESIGN §2, behind one
`Resources.import_name` call (EVALUATOR_DESIGN §7):

- `resolve` — the theory table, then the base heap, then a load from source;
- `load` — the `Thy_Info.use_theories` wrapper of EVALUATOR_DESIGN §6, under
  one lock, one theory per call, with `parallel_proofs = 1` checked at
  conversation start;
- `check_new_theory_short_name` — rejects a new theory name whose short name —
  the part after the last dot, which is what Isabelle compares
  (EVALUATOR_DESIGN §7) — the base heap already uses; the forest side of that
  check (MCP_SPECIFICATION §2) is Python's.

### 2.4 Running commands

The mechanism of EVALUATOR_DESIGN §1, for any node.

- `begin_theory` — takes, alongside the header, the tree's Isabelle session
  name — its `Session` node's `name` (node_classes/SESSION_AND_THEORY.md
  §1) — and the `master_dir`, which is that session's folder under the
  working directory (ARCHITECTURE §1): the name qualifies every import
  resolution (EVALUATOR_DESIGN §7). It resolves each import through §2.3, merges the
  parents' keywords, and runs the `theory … begin` span from
  `Toplevel.make_state NONE`.
- `run_commands` — splits a node's text with `Outer_Syntax.parse_spans` and
  runs each span through `Toplevel.command_errors true`, threading the state.
  Returns one record per command: source, range, errors, output.
- `end_theory` — `Toplevel.end_theory`, yielding the value the theory table
  stores.

**Output.** Agent-facing text leaves the process through six `Private_Output`
channels (`contrib/Isabelle2025-2/src/Pure/General/output.ML`):
`writeln_fn`, `writeln_urgent_fn` — a proof's or definition's result block
prints through this one (`Pure/Isar/proof_display.ML:322-328`) —
`tracing_fn`, `warning_fn`, `information_fn` and `legacy_fn`. The
conversation replaces the six once, with functions that route a message by
the id in `Position.thread_data ()` into a per-command buffer, and fall back
to the function they replaced when there is no id, or no buffer under it.
The remaining channels stay untouched: proof states are read off the states
themselves, errors travel structurally out of `Toplevel.command_errors`, and
the rest is PIDE protocol machinery. `run_commands` gives each span a fresh
id — minted by `Document_ID.make` and registered with `Execution.running`
before the span runs, since the id slot of a position is the execution
registry's key and `Execution.fork`/`Execution.print` fail on an
unregistered id — and runs the span under it. The id travels with
`Future.fork` (`Pure/Concurrent/future.ML:452`), so a message printed on a
forked worker still reaches its command's buffer; a key in `Thread_Data`
would not (EVALUATOR_DESIGN §4).

### 2.5 Node classes

The envelope of ARCHITECTURE §6.2, and the one interface a node class author
sees.

A node class registers a function from the conversation's environment to a
local callback of `Isabelle_RPC` (`Remote_Procedure_Calling.callback'`):

```sml
type slot = {
  get : unit -> Toplevel.state,           (*§2.1's get; a Bug when the slot holds nothing*)
  put : Toplevel.state option -> unit     (*§2.1's put; NONE deletes*)
}
type env = {
  slot_unpacker : slot MessagePackBinIO.Unpack.unpacker,
                    (*reads a slot name off the wire, on this conversation's table*)
  begin_theory  : {session_name : string, master_dir : Path.T} ->
                  Thy_Header.header -> Toplevel.state,
                    (*§2.4's, imports resolved through this conversation's tables*)
  end_theory    : Toplevel.state -> unit
                    (*§2.4's, the result put into this conversation's theory table*)
}
val register_callback :
  {python_packages : string list} ->    (*the class's Python half; imported at
                                          conversation start, filling the kind
                                          table (§4.4)*)
  (env -> Remote_Procedure_Calling.callback') -> theory -> theory
```

On the wire a state slot is its name (§4.1), and `slot_unpacker` is how a
callback's `arg_schema` takes one: it reads the name and yields the slot —
read, write and delete all on the handle, so the callback never touches a
name. A callback's wire name rides inside the `callback'` value itself
(`Remote_Procedure_Calling.mk_callback {name, …}`); the duplicate check of
§2.6 reads it there. `begin_theory` and `end_theory` are in the environment because the
theory table they use is the conversation's: the table has exactly one writer,
and a `theory` value that is not the yield of `Toplevel.end_theory` cannot
enter it (EVALUATOR_DESIGN §4's one-producer rule).

The environment is bound to one conversation's tables, so it exists only
once the conversation has started; the registered function is called then.
Until then the registration rides on the theory (`Theory_Data`, applied with
`setup`), so a conversation's node classes are exactly the classes whose theories
the starting theory imports, and re-evaluating a registering theory cannot
register twice — the fresh theory value carries the registration once. There
is no other table of node classes.

What the callback takes and returns is the class's own affair, agreed with its
Python half (ARCHITECTURE §6.2); the per-command records of §2.4 are there
for it to return if it so chooses. One thing is not its own affair: a
callback answers every failure of its operation as data, and an exception
it lets escape is a bug (EXCEPTIONS.md §1) — `TAT_Framework.Bug`, the
exception TAT raises where it caught itself out, or something the callback
did not foresee. An interrupt is neither a failure of the operation nor a
bug: the RPC library answers it to Python as `IsabelleInterrupt`, which
`isabelle_driver.call` classifies as `TAT_IsabelleError`, a
`TAT_InternalError`, for now (EXCEPTIONS.md §1), and every TAT callback
re-raises it afterwards, so it unwinds the ML call and with it the
conversation.
`TAT_Common_Nodes.operation`
keeps the rule for a callback whose success is a state: the run answers a
state and no message, or no state and at least one message — anything else
is a `Bug` — and `operation` writes the state into the slot, turns any
other exception into the operation's messages the way
`Toplevel.command_errors` reads one, and lets a `Bug` and an interrupt
through as they arrived.

### 2.6 Conversation

The entry point of ARCHITECTURE §9. `start` takes the theory whose ancestry
names the node classes (§2.5), the working directory
(ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §1) and the port to serve on —
`0` for one the system picks — and starts the conversation:

1. create the state slot table and the environment of §2.5;
2. call every function registered in that theory's data, collecting the node
   classes' callbacks and their `python_packages`, deduplicated;
3. add the framework's own: `TAT.state_copy`, `TAT.state_delete` and
   `TAT.state_exists` on state slots (§2.1's `copy`, `delete` and `exists`;
   `get` and `put` ride inside the classes' own callbacks and need no wire
   name), and `TAT.check_new_theory_short_name` (§2.3);
4. install the output routing of §2.4;
5. `Remote_Procedure_Calling.load ["isabelle_theory_agent"]`, then call the
   procedure `launch_TAT` (§4.6) with the collected package list, the
   working directory and the port; `launch_TAT` does not return.

The callbacks go in the `callback` field of that one command, as AoA's
`aoa_cmd` does (`contrib/Isa-Mini/Agent/agent_server.ML`); none enters
`Isabelle_RPC`'s global callback table. Two callbacks under one name would
silently shadow each other in that command's dispatch table, so starting the
conversation rejects a duplicated name instead.

## 3. `TAT_Common_Nodes`

`operation`, the helper a node class writes its callbacks against (§2.5),
then one section per predefined node class, each a client of §2.5.

| section | what it runs |
| --- | --- |
| `operation` | not a class: the helper of §2.5 — a run's state into the slot, its failure as messages, a `Bug` and an interrupt through |
| `Theory` | the header through §2.4's `begin_theory`, writing the first child's slot; `end` through `run_commands`, writing the tree's resulting slot, and the theory value into the theory table through `end_theory` |
| `Theorem` | the statement, then `sorry` or `by` with the stored proof (ARCHITECTURE §3.6) |
| `Define` | the commands of ARCHITECTURE §2.2's table, each reported on its own; records `form` |
| `Section`, `Context`, `Locale`, … | unspecified (OPEN_QUESTIONS §1) |

`Theory`'s evaluator is registered like every other class's. `Session`
registers no evaluator: it runs no Isabelle commands — its evaluation is
the forest's scheduling (ARCHITECTURE §3.5) and its emission the ROOT entry
(ARCHITECTURE §4). The Python halves of both are framework classes in
`model.py` (§4.5).

## 4. Python side

TAT is an Isabelle component (§1) and a pure MCP server (ARCHITECTURE §9).
Launching the Isabelle process is the launcher's business — during
development the Isa-REPL server's, with the app of `Dev/TAT_Dev.thy` making
the call.

```
isabelle_theory_agent/
  exceptions.py        the TAT_Error hierarchy (EXCEPTIONS.md)
  model.py             Node, Forest, Conversation, ids, evaluation and invalidation, persistence; Session and Theory
  edit.py              building nodes from constructs; the entries behind edit, move and delete
  store.py             Forest_Store and Node_Rows: the working directory's database (ARCHITECTURE §4.1)
  isabelle_driver.py   typed calls to the ML side's callbacks
  plugin.py            loading node classes and their table; the argument schema grammar
  builtins.py          the predefined node classes
  theorem_node.py      Theorem: construct, the AoA interface
  mcp.py               the tools, recall, the queue of pending messages
  mcp_server.py        the Streamable HTTP MCP server
  toplevel.py          the RPC entry point Isabelle calls into: the Conversation, the Forest, the server
  tools/edit.jsonc     the edit tool's schema, its $defs filled at start (PLUGIN_SYSTEM §4)
```

A leading underscore marks a framework-internal member: the framework's
own modules use it across files; a node class and a plugin never touch it.

### 4.1 `model.py`

`Node` is the Python half of the node class contract (ARCHITECTURE §6): the
authored and recorded fields, the argument schema — a TypedDict the
framework checks submitted constructs against (§4.2, §4.4), and which types
`gen`'s `raw` for the static checker — `gen` (below), `emit_isar`, the name it gives the node and its two omissibility
flags (MCP_SPECIFICATION §2.1), `index_of()` — the node's position in its
parent's `sub_nodes`, computed, never stored — an optional `construct`,
`to_store` and `from_store` for persistence (ARCHITECTURE §4.1), `_owes_nothing()`
(ARCHITECTURE §3.2), and the event hooks (below).

**Construction.** A node enters the forest from a `RawAST` — the JSON
object the agent submitted, `Mapping[str, Any]` — less `children`, which
no `gen` ever sees (§4.2). Everything semantic lives in `gen`:

```python
class NodeConfig(NamedTuple):
    state: Isar_State_Slot   # the state before the node. A name: the slot may
                             # hold nothing, and gen neither reads nor writes
                             # through it — only evaluation hooks may assume a
                             # slot holds a state (see Events)
    parent: NonLeaf_Node     # never None: the forest root is not made this way.
                             # During an edit this may be a node not yet in the
                             # forest (a nesting node under construction)
    replacing: Node | None   # on the amend path, the node this construct is
                             # replacing; None on every other path. Read it for
                             # exactly two things: leave it out of any uniqueness
                             # check (it is leaving the forest), and carry over
                             # recorded fields the class judges still valid —
                             # Theorem keeps its proof when the statement is
                             # unchanged. Read-only; never mutate it

@classmethod
async def gen(cls, config: NodeConfig, raw: RawAST) -> Self
```

`gen` checks and constructs; the framework owns placement. Where a node
may live is the node's own judgement: its `gen` refuses a parent its class
cannot live under — `Bad<Class>NodeParent`, EXCEPTIONS.md §3 — and on a
move its `on_moving` does; the framework checks no containment. It may read
over the wire through the framework's query functions (§4.3) — `Theory.gen`
checks its short name against the base heap — and those functions answer
data or raise `TAT_IsabelleError`, a bug (EXCEPTIONS.md §1), so a failure
on the Isabelle side is never blamed on the class. It must not write:
an aborted edit undoes nothing remotely. It raises `TAT_Error`s bare; the
framework prefixes the `raw_ast_path` (EXCEPTIONS.md §5).

**Events.** Ten hooks, empty by default, driven by the framework — a class
only ever speaks for its own node. The tense is the contract:

- **A progressive hook is a gate.** It fires before the commit, while
  nothing has changed, and must be free of side effects. Raising `BadEdit`
  vetoes the whole call; raising anything else is the class's bug.
  Insertion's gate is `gen` itself, so there is no `on_inserting`.
- **A completed hook is for effect.** It fires after the commit; this is
  where irreversible work belongs — `Theorem`'s `on_deleted` cancels its
  running search. Raising anything, `BadEdit` included, is the class's bug
  (EXCEPTIONS.md §1).

| hook | tense | fires |
| --- | --- | --- |
| `on_invalidated(operation)` | completed | an operation's status truly left `ready` — not on the walk re-marking a `not_evaluated` node (ARCHITECTURE §3.5; its purpose, §3.6). `operation` says which: a `StdBlock` passes `beginning` or `ending`, a `Leaf` passes `None`, a class with its own statuses passes its own value |
| `on_deleting(reason)` | gate | the node is to leave for good; `reason` is `delete` (whole subtree, children first) or `amend` (the replaced node alone) |
| `on_deleted(reason)` | completed | it left; the Python object is still whole — cancel running work here |
| `on_inserted()` | completed | linked in, children and all |
| `on_removing_child(child, mode)` | gate | `child` is to leave this node's `sub_nodes` |
| `on_added_child(child, mode)` | completed | `child` entered this node's `sub_nodes` |
| `on_inheriting(new_parent)` | gate | on each direct child of a replaced node; never recursive — grandchildren see nothing |
| `on_inherited(old_parent)` | completed | the reparenting happened |
| `on_moving(new_location)` | gate | the node is to move; `new_location` is the resolved Location — the new parent and the index within its `sub_nodes`, counted after the node's removal, so within one parent it is the index the node will have |
| `on_moved(old_location)` | completed | it moved; `old_location` is the resolved Location it left |

The pairs that carry a place follow one rule: the gate is handed where the
node is going, the completed hook where it came from. `mode`
says why a membership changed: `insert_or_delete`, `move`, `inheritance` —
children passing to a replacement — or `amend`, the replacement exchange
itself.

Completed order after one commit: what left fires `on_deleted`, children
before parents; inherited children fire `on_inherited`; then, in tree
order over what entered or moved, the parent's `on_added_child` and then
the node's own `on_inserted` or `on_moved`. `on_invalidated` fires during
the walk that follows.

No hook fires on an aborted call. In any hook, as in `gen`, a state slot
may hold nothing; the only code that may assume its slot holds a state is
an evaluation hook — `_eval_opr`, `_eval_beginning_opr`,
`_eval_ending_opr` — because the recursion runs a node only after
everything before it is `ready` (ARCHITECTURE §3.5). The one exception is
a `Theory` root's own `state`, which nothing ever writes
(ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §6).
Everything that needs the prover — fetching facts, checking terms,
recording results — therefore belongs in the evaluation hooks, not in
`gen` and not in events.

**States.** `Isar_State_Slot` is a name in the ML side's state slot table
(§2.1) together with the connection; on the wire it is the name
(`to_msgpack`, `from_msgpack`). It offers `copy_to`, `delete` and
`is_initialized` — §2.1's `copy`, `delete` and `exists`, seen from Python —
each a round trip; nothing about the table is mirrored on
the Python side. Persistence keeps neither the name nor the connection: a
loaded forest is reassigned its slots.

Every node holds one, `state`, the state before it. The state after it,
`resulting_state()`, is computed, as in AoA
(`contrib/Isa-Mini/IsaMini/AoA/model.py`'s `Node.resulting_state`): under a chaining parent it
asks the parent, which answers with the next sibling's `state`, or with the
one it keeps for the position after all its children — so one node's result
and the next node's input are one slot, and inserting or deleting a node
moves a value between slots by one copy (`edit.insert`, `edit.delete`,
`edit.move`; ARCHITECTURE §3.4); under an `Unchained_Node`, which chains
nothing, a node that has a result owns the slot for it, as `Theory` does
with `_state_after_ending` (ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §6).

**Status.** A status is `NotEvaluated`, `Ready`, or
`CannotEvaluate(blocked_by)` — the Python classes of ARCHITECTURE §3.2's
`not_evaluated`, `ready` and `cannot_evaluate`, §3.3's `blocked_by` riding
inside the third; the reason travels
inside the value, so a `Ready` operation cannot carry a stale one. A `Leaf`
has one, a `StdBlock` two — `evaluation_status_beginning` and
`evaluation_status_ending` — and no node reads another's: the one question
asked of a node from outside is `is_finished()`, which the framework
answers — every operation of the node and of its subtree `Ready`, and
`_owes_nothing()` true on it and on every node of its subtree
(ARCHITECTURE §3.2); a class overrides
`_owes_nothing()` and never `is_finished()`, and the loader refuses one that
does (PLUGIN_SYSTEM §5). Every status write goes through one setter per
operation, which releases the operation's resulting state when the status
goes from written to unwritten — never on a rewrite; a loaded forest's
statuses are all `NotEvaluated`.

**Hierarchy**, following AoA's (`class Leaf` :5333, `class NonLeaf_Node`
:5449, `class StdBlock` :5836):

- `Leaf(Node)` — a class overrides `_eval_opr() -> bool`: run the node from
  `state` into `resulting_state()`, return whether evaluation passes through
  it.
- `NonLeaf_Node(Node)` — `sub_nodes`, `_resulting_state_of_child`, and the
  children loop of the recursion.
- `StdBlock(NonLeaf_Node)` — keeps `_state_before_ending`, the slot after all
  its children; a class overrides `_eval_beginning_opr() -> bool` (from
  `state` into the first child's `state`) and, if it has an ending command,
  `_eval_ending_opr() -> bool` (from `_state_before_ending` into
  `resulting_state()`); the default ending copies.
- `Unchained_Node(NonLeaf_Node)` — a container whose children are not
  chained: no child's result is the next child's input, it mints no slot
  and runs no operation of its own; a child that has a result owns the
  slot for it (ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §6).
- `Session(Unchained_Node)` — groups trees and carries the ROOT entry's
  fields (node_classes/SESSION_AND_THEORY.md §1); not on the evaluation
  path — the forest works on the theories directly (ARCHITECTURE §3.5),
  and a walk reaching a `Session` is a framework bug.
- `Theory(StdBlock)` — the root of a tree (node_classes/SESSION_AND_THEORY.md
  §2); owns its resulting slot, `_state_after_ending`, which nothing reads.
- `Forest(Unchained_Node)` — the root above every `Session`. Holds the
  lock, the store (ARCHITECTURE §4.1) and the `Conversation`; resolves ids
  and prints their shortest form; and, in the walk, keeps the import graph
  (recomputed whenever needed, never stored), routes a walk to the tree it
  concerns, invalidates every tree that imports a changed one, and runs a
  tree's imports to their `end`.

`Conversation` is what one conversation is given and the forest does not
store: the connection to the Isabelle side, and the working directory
(ARCHITECTURE §4). A node reaches it through `forest().conversation`
(PLUGIN_SYSTEM §2).

An evaluation hook runs the class's own ML callback (§2.5) itself, through
`isabelle_driver.call` (§4.3) — once per hook: `_eval_opr` once,
`_eval_beginning_opr` and `_eval_ending_opr` once each — so that one
operation is one round trip and the ML side completes the whole operation
inside that one call; it records what it likes
on the node, and the framework reads only the boolean, copying the
operation's input into its resulting state itself on False (ARCHITECTURE
§6.2). `construct` is exempt from the cadence: a class that has one designs
its own use of the wire, still through `call`. `gen` and the event hooks
never call a class's own callback;
`gen` reads only through the framework's query functions (§4.3).
`Theory` and `Section` are `StdBlock`s, `Theorem` and `Define` `Leaf`s.

**The recursion** (ARCHITECTURE §3.5), entered through
`Node.evaluate_to(ignore_error, evaluate)` and, for an edit's unconditional
invalidation, `Forest._invalidate_from(position)`, under the forest's lock
(above), starting from the forest. A walk's two constants
and the states it releases travel in one `Evaluation`; where the walk is
travels in a `Mode`:

```python
class Evaluation:                    # one walk
    destination: Node | None         # the node an evaluating walk runs up to and including;
                                     # none for an invalidate-only walk
    ignore_error: bool
    def release(self, slot)          # deleted together when the walk ends

Mode = Evaluating | Seeking | Invalidating
class Evaluating: blocked_by: Node | None   # before the destination: run what is not Ready,
                  rewritten: bool           # or, blocked, mark CannotEvaluate(blocked_by);
                                            # rewritten: the state here was written this walk,
                                            # so even a Ready node or an own stop runs again
class Seeking: destination: Location        # before the position without evaluating: touch nothing
class Invalidating                          # past the destination: mark NotEvaluated

@dataclass(frozen=True)
class EvaluationResult:
    stopped_at: Node | None          # the obstacle that ended evaluation
    mode: Mode                       # the mode the node after this one runs under

async def _evaluate(self, ev: Evaluation, mode: Mode) -> EvaluationResult
```

`Leaf` and `StdBlock` each write it; `StdBlock`'s runs the beginning, the
children, then the ending, and nothing is skipped: a `Ready` operation is
not rerun, but every node is visited. The mode changes in one place: the
destination turns it into `Invalidating`, and a stop turns `Evaluating` into
`Evaluating(stop)` unless `ignore_error`. An evaluating walk's destination
is a node, reached at its ending; an invalidate-only walk's is a Location,
reached before the child standing there — so a nesting node at that
position is invalidated whole, opening first — or, at the index after the
last child, before the parent's ending. A nesting node whose beginning
failed enters its children with itself as `blocked_by`; a nesting node
whose child stopped cannot run its ending and is `CannotEvaluate` with the
same obstacle. A blocked status never overwrites an own stop: an obstacle
keeps reporting itself, and is not rerun until edited — or until the state
under it is rewritten by this walk (ARCHITECTURE §3.3). A resulting state
is released only when the status of the operation that writes it goes from
written to unwritten; a rewrite releases nothing. A nesting node is reached
at its ending.

### 4.2 `edit.py`

Changing the forest: how a submitted construct becomes a node, and the
four entries behind the `edit`, `move` and `delete` tools — `insert`,
`amend`, `delete`, `move`.

Two fields of a construct belong to the framework: `kind` selects the
node class (§4.4), and `children` — which no `gen` ever sees — holds a
nesting node's contents. The framework checks the construct's mechanical
shape — no field the class does not declare, required fields present,
types right — against the class's declared argument schema
(`check_construct`, §4.4), raising `UnexpectedField` / `MissingField` /
`InvalidField` before the class is consulted. The JSON tool schemas are
hand-written, as AoA's (`contrib/Isa-Mini/IsaMini/AoA/tools/`).

An `edit` builds everything before it touches the forest:

1. **Construct, detached.** Every construct, in submission order: the
   `children`-legality checks (`UnexpectedChildren`,
   `ChildrenNotInheritable` — decidable from the RawAST and the `kind`
   table alone, so they run before any `gen`), the class lookup, the
   schema check, `gen`, then — for a nesting class — its `children`, built
   by the framework onto the fresh, still-detached node the same way. The
   framework assigns each new node a fresh state slot and reads the name
   off the finished node: a name outside the grammar of
   MCP_SPECIFICATION §2 (`InvalidName`), or an id component
   `<kind>_<name>` that collides with a surviving sibling's or with the
   batch's (`DuplicateName`), is refused; a
   class may also declare that its names live in a forest-wide namespace
   — `Theory`'s short names — and the framework then refuses a name a
   node of the forest (less the node the amend replaces, which is
   leaving) or an earlier construct of the call already bears there
   (`DuplicateTheoryShortName`), finding the forest's by walking it.
   The amend loop walks the whole submitted list,
   `constructs[0]` built with `replacing` set; so every `raw_ast_path` indexes
   the agent's own list.
2. **Gates.** The hooks that may still veto (§4.1's events), `BadEdit`
   their only voice.
3. **Commit** — pointer surgery, which cannot fail, then one store
   transaction writing what changed (ARCHITECTURE §4.1), with nothing
   awaited between them, so a call holding no lock never sees a
   part-changed forest (MCP_SPECIFICATION §5). The batch is
   linked in; on amend the replacement takes `old`'s position, state
   slot, identity number and children. The one copy of ARCHITECTURE §3.4
   lands in the first new node's slot — and only when the predecessor
   operation has written it: `ready`, or an own stop, whose copy-through
   counts — judged from the Python-side status, no round trip; every
   other new slot stays empty, as befits `not_evaluated` nodes. A
   transaction that fails raises `TAT_DisasterError` (EXCEPTIONS.md §1):
   memory and the database have parted, and the conversation ends.
4. **Completed events**, then the entry invalidates unconditionally; the
   caller evaluates when the call's `evaluate` says so
   (MCP_SPECIFICATION §3.2).

A failure anywhere before the commit aborts the call with the forest
untouched: there is no rollback, because nothing happened to roll back.

**Entry points and the lock.** The tool entries that hold the forest's
lock — `edit`, `move`, `delete`, `evaluate_to` — hold it across the whole
call; `recall`, `status` and the future `query` take none
(MCP_SPECIFICATION §5). A call is cancelled only by the conversation's
ending (ARCHITECTURE §9). `evaluate_to`'s entry is
`Node.evaluate_to`, which takes it itself; an edit's tool entry takes it
and calls `insert`, `amend`, `delete` or `move`, which assume it held, as
does the walk each ends with. One ordering fact: `gen` awaits the ML
side's loader lock (§2.3) while the forest lock is held; nothing on the
ML side ever waits for the forest lock, and that order must stay one-way.

`move` re-homes a node with its subtree — a copy on the source side and a
copy on the destination side (ARCHITECTURE §3.4). The subtree's slots
travel with their nodes, whose names they remain (ARCHITECTURE §3.1); no
slot is deleted. Two values may be released: the moved node's old input,
when nothing wrote a value at the destination — its writer is still
current, so no release would otherwise clear it — and the source
successor's slot, when the predecessor there wrote nothing but the moved
node had, which is `delete`'s rule too.

### 4.3 `isabelle_driver.py`

`call`, the one door to the wire, and one function per callback the
framework's ML side offers (§2.6): each knows the callback's name and the
MessagePack shape of its arguments and result, and nothing else does; the
framework's modules, and a `gen` reading over the wire, call these
functions. A node class's own callback (§2.5) is not here: the class calls
it itself, through `call`, from its evaluation hooks (§4.1), the shape
being between the class and its own ML half (ARCHITECTURE §6.2). `call`
raises `TAT_IsabelleError` from an exception the callback let escape, or
from a failure of the wire contract such as no callback registered under
the name — a bug either way (EXCEPTIONS.md §1). The connection going away
answers a round trip with a connection error instead, not an
`IsabelleError`; that is the conversation's ending (§4.6), not a bug.
`call` shields the round trip: a callback is a two-phase exchange on the
RPC connection that must not be interrupted, so a cancellation of the
caller unwinds it at once while the round trip in flight completes on its
own and its result is dropped.

### 4.4 `plugin.py`

Imports every package in the list `launch_TAT` received (§2.6) — the
`python_packages` the node class theories registered. `@TAT_node` fills a
process-wide registry as classes register; `load` returns this
conversation's kind table — the framework's two classes and the listed
packages' — and the assembled `edit` schema from it (PLUGIN_SYSTEM §1).
The table is what `edit` dispatches on. What the loader
checks at registration and at assembly, and how it completes the `edit`
schema, is PLUGIN_SYSTEM.md.

The argument schema grammar lives here too. A declaration's annotations
come from a closed grammar — `str`, `bool`, `int`, `float`, `Any`,
`list[X]`, a TypedDict, and unions of those holding at most one
TypedDict, each field optionally wrapped in `NotRequired[X]` or
`Required[X]`, which the loader reads off the annotation itself — so every
check renders within RENDER_BASELINES §2's
vocabulary; `@TAT_node` refuses anything else when the class is
registered, as it refuses a TypedDict that nests itself and an annotation
Python cannot resolve. `check_construct` checks a submitted construct
against the declaration; `edit.py` runs it before the class's `gen`
(§4.2).

### 4.5 `builtins.py` and `theorem_node.py`

The predefined node classes of ARCHITECTURE §2.2, except `Session` and
`Theory`, which carry the forest's structure and live in `model.py`
(ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §6). `Theorem` has its own file
because `construct` is where everything asynchronous lives: it starts the AoA
search and hangs the running search on the node (ARCHITECTURE §3.6, §9) — how
it drives AoA is designed here, on AoA's own precedent; it stores the method
text AoA found on the node; it queues the message that rides on the next tool
result (MCP_SPECIFICATION §5); and deleting the node cancels it.

### 4.6 `mcp.py`, `mcp_server.py`, `toplevel.py`

`mcp.py` implements the tools of MCP_SPECIFICATION §1 and the queue of
pending messages; the future `query` tool (MCP_SPECIFICATION §1.1) will land
here too. `mcp_server.py` builds the server: one Streamable HTTP server on
`127.0.0.1:<port>`, one endpoint `/mcp`, a low-level `mcp.server.Server`
from the Python `mcp` SDK — TAT's own transport code, with no dependency on
Isa-Mini; two lessons from AoA's
(`contrib/Isa-Mini/IsaMini/AoA/mcp_http_server.py`): the session manager's
lifetime stays inside one asyncio task, and — unlike that file, which
sleeps — the port is waited on deterministically. The server is given the
SDK's transport security settings — the allowed host is `127.0.0.1` with
the bound port, or `127.0.0.1:*` when the port is system-chosen, the
spelling the printed URL uses too — so a request whose `Host` or `Origin`
header is not TAT's own is refused before dispatch; without them the SDK
checks nothing.

The tool handler TAT registers is the tool boundary of EXCEPTIONS.md §1.
Three things about it hold the design's invariants against the SDK's
defaults.

- It is registered with the SDK's input validation off
  (`validate_input=False`): the framework checks a submitted construct
  against the class's declared argument schema itself and answers
  `UnknownKind`, `MissingField`, `UnexpectedField` and `InvalidField`
  (EXCEPTIONS.md §3); the SDK's jsonschema message never reaches the agent.
- It renders a `TAT_Error` into the result and renders nothing else. Any
  other exception starts the conversation's ending (below): the handler
  records it and hands it to `launch_TAT`, which raises it out of the RPC
  call as an ordinary `Exception`, the only kind the RPC host reports to
  the ML side. The hand-off is out of band because the SDK turns any
  ordinary exception a handler lets escape, and any value it returns, into
  a result the agent would retry against.
- It runs the call's body as a task outside the request's cancel scope and
  waits for that task shielded, so neither a client's
  `notifications/cancelled` — its per-tool timeout expiring — nor the SDK's
  unwind reaches a body mid-edit: the client loses its answer, and the body
  finishes and releases what it holds. After the body the handler takes a
  checkpoint, letting a pending cancellation through instead of answering,
  since the SDK's responder has by then answered the client itself.

**The conversation's ending** is the server's one state besides serving.
The server enters it when a handler catches anything that is not a
`TAT_Error` — a bug, a `TAT_DisasterError`, or the connection error a dead
wire answers a round trip with (§4.3) — or when `launch_TAT` finds the
connection gone, the connection going ending its RPC call; whichever door
is reached first enters it. In it the server
cancels every working call's body, and each handler answers its own call —
the one that ended the conversation included — with the message of
RENDER_BASELINES §4, taking no lock and touching no forest. The ending's
cancellation reaches a working call's handler as its own wait failing,
which the handler answers rather than passes on — a handler that passes it
on answers nobody; a call whose client has already given up stays on the
handler's checkpoint path and is answered by nobody. A call that arrives
while the conversation is ending is answered the same message. A round
trip a cancelled body was in finishes on its own, or fails with the
connection; either way nothing reads its result (§4.3). The forest in
memory goes with the conversation, and the database holds its last commit
(ARCHITECTURE §4.1). Then the server stops and `launch_TAT` leaves.

```
TAT has stopped: an internal error; this call did not complete.
TAT has stopped: the forest could not be saved; this call did not complete.
TAT has stopped: Isabelle is gone; this call did not complete.
```

`mcp_server.py` is also where
the assembled `edit` schema reaches the client (PLUGIN_SYSTEM §4): TAT
serves it as assembled, `$ref`s intact. Node classes may recurse
(PLUGIN_SYSTEM §3), so the schema has no finite inlining; serving a client
that drops references means choosing a different shape for it — a
decision to take when such a client appears, on AoA's precedent
(`contrib/Isa-Mini/IsaMini/AoA/mcp_http_server.py` serves several variants
of one `edit` schema). `toplevel.py` is the procedure Isabelle calls
(`@isabelle_remote_procedure("launch_TAT")`) with the package list, the
working directory and the port (§2.6); it does not return. In order: it
takes the working directory's lock, `tat.lock` — a non-blocking exclusive
`flock` on a descriptor it keeps open for the life of the conversation, so
the kernel releases it when the process dies and it is released in the
call's `finally` when the conversation ends any other way; `flock`, not a
POSIX record lock, because only `flock` conflicts between two open
descriptors in one process, and that is what refuses a second conversation
in this host as well as in another; a directory another conversation holds
is refused with a `TAT_StartupError` — builds the
`Conversation` (§4.1) from its connection and the working directory; opens
the `Forest_Store` on `<working directory>/theory_forest.sqlite`; loads the
plugins (§4.4); builds the `Forest`; starts the server, a port that cannot
be bound being a `TAT_StartupError` too, and prints its URL to the Isabelle
side; then serves until the conversation's ending (above), after which the
lock is released.
