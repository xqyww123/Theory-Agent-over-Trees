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
Dev/TAT_Dev.thy               the development-time client, an Isa-REPL app (ARCHITECTURE §9)
ROOT                          build checks only; nothing ever runs on these heaps
etc/settings                  the Isabelle component: TAT_HOME="$COMPONENT"
isabelle_theory_agent/        the Python package (§4); the pip and conda packages carry the same name
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
carries the predefined node classes; a node class delivered separately
(ARCHITECTURE §6) is another client of the same interface and never depends on
`TAT_Common_Nodes`. The test for where something belongs: if a node class
outside `TAT_Common_Nodes` would need it, it is in `TAT_Framework`.

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
  name and directory, read off its `Session` node
  (node_classes/SESSION_AND_THEORY.md §1): the
  name qualifies every import resolution (EVALUATOR_DESIGN §7), the directory
  is the `master_dir`. It resolves each import through §2.3, merges the
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
  get : unit -> Toplevel.state,           (*§2.1's get; an error when the slot holds nothing*)
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
                                          table (§4.3)*)
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
for it to return if it so chooses.

### 2.6 Conversation

The entry point of ARCHITECTURE §9. Starting a conversation, from the theory
whose ancestry names the node classes (§2.5):

1. create the state slot table and the environment of §2.5;
2. call every function registered in that theory's data, collecting the node
   classes' callbacks and their `python_packages`, deduplicated;
3. add the framework's own: `TAT.state_copy`, `TAT.state_delete` and
   `TAT.state_exists` on state slots (§2.1's `copy`, `delete` and `exists`;
   `get` and `put` ride inside the classes' own callbacks and need no wire
   name), and `TAT.check_new_theory_short_name` (§2.3);
4. install the output routing of §2.4;
5. `Remote_Procedure_Calling.load ["isabelle_theory_agent"]`, then call the
   procedure `launch_TAT` (§4.5) with the collected package list as an
   argument; `launch_TAT` does not return for the life of the conversation.

The callbacks go in the `callback` field of that one command, as AoA's do
(`contrib/Isa-Mini/Agent/agent_server.ML:1740-1772`); none enters
`Isabelle_RPC`'s global callback table. Two callbacks under one name would
silently shadow each other in that command's dispatch table, so starting the
conversation rejects a duplicated name instead.

## 3. `TAT_Common_Nodes`

One section per predefined node class, each a client of §2.5.

| section | what its evaluator runs |
| --- | --- |
| `Theory` | the header through §2.4's `begin_theory`, writing the first child's slot; `end` through `end_theory`, writing the theory table |
| `Theorem` | the statement, then `sorry` or `by` with the stored proof (ARCHITECTURE §3.6) |
| `Define` | the commands of ARCHITECTURE §2.2's table, each reported on its own; records `form` |
| `Section`, `Context`, `Locale`, … | unspecified (OPEN_QUESTIONS §2) |

`Theory` is registered like every other class; the framework does not know it.

`Session` registers nothing: it runs no Isabelle commands — its evaluation is
the forest's scheduling (ARCHITECTURE §3.5) and its emission the ROOT entry
(ARCHITECTURE §4). It lives entirely in `builtins.py` (§4.4).

## 4. Python side

TAT is a library. Whatever starts a conversation — during development an
Isa-REPL app, later some Isabelle component — is a client built on it, and
starting the Isabelle process is the client's business.

```
isabelle_theory_agent/
  model.py             Node, Forest, ids, evaluation and invalidation, compilation, persistence
  isabelle_driver.py   typed calls to the ML side's callbacks
  plugin.py            loading node classes and their table
  builtins.py          the predefined node classes
  theorem_node.py      Theorem: construct, the AoA interface
  mcp.py               the tools, recall, the message queue
  mcp_server.py        the MCP server itself
  toplevel.py          the RPC entry point Isabelle calls into
```

### 4.1 `model.py`

`Node` is the Python half of the node class contract (ARCHITECTURE §6): the
authored and recorded fields, the argument schema — it becomes the tool
schema, and the framework checks submitted descriptions against it
(below) — `gen` (below), `emit_isar`, the name it gives the node and its two omissibility
flags (MCP_SPECIFICATION §2.1), `index_of()` — the node's position in its
parent's `sub_nodes`, computed, never stored — an optional `construct`,
`__getstate__` for persistence (ARCHITECTURE §4.1), and the event hooks
(below).

**Construction.** A node enters the forest from a `RawAST` — the JSON
object the agent submitted, `Mapping[str, Any]`. Two of its fields belong
to the framework: `kind` selects the node class (§4.3), and `children` —
which no `gen` ever sees — holds a nesting node's contents. The framework
also checks the description's mechanical shape — required fields present,
types right — against the class's declared argument schema, the same
declaration that builds the tool schema, raising `MissingField` /
`InvalidField` before the class is consulted. Everything semantic lives in
`gen`:

```python
class NodeConfig(NamedTuple):
    state: Isar_State_Slot   # the state before the node. A name: the slot may
                             # hold nothing, and gen neither reads nor writes
                             # through it — only evaluation hooks may assume a
                             # slot holds a state (see Events)
    parent: NonLeaf_Node     # never None: the forest root is not made this way.
                             # During an edit this may be a node not yet in the
                             # forest (a nesting node under construction)
    replacing: Node | None   # on the amend path, the node this description is
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
over the wire through the framework's query callbacks — `Theory.gen`
checks its short name against the base heap and the forest, excluding
`config.replacing` — and those callbacks raise only `TAT_Error` subclasses,
so a transport failure is never blamed on the class. It must not write:
an aborted edit undoes nothing remotely. It raises `TAT_Error`s bare; the
framework prefixes the `raw_ast_path` (EXCEPTIONS.md §5).

An `edit` builds everything before it touches the forest:

1. **Construct, detached.** Every description, in submission order: the
   `children`-legality checks (`UnexpectedChildren`,
   `ChildrenNotInheritable` — decidable from the RawAST and the `kind`
   table alone, so they run before any `gen`), the class lookup, the
   schema check, `gen`, then — for a nesting class — its `children`, built
   by the framework onto the fresh, still-detached node the same way. The
   framework assigns each new node a fresh state slot and reads the name
   off the finished node: a name outside the grammar of
   MCP_SPECIFICATION §2 (`InvalidName`), or one that collides with a
   surviving sibling or with the batch (`DuplicateName`), is refused.
   The amend loop walks the whole submitted list,
   `nodes[0]` built with `replacing` set; so every `raw_ast_path` indexes
   the agent's own list.
2. **Gates.** The hooks that may still veto (Events below), `BadEdit`
   their only voice.
3. **Commit** — pointer surgery only, nothing that can fail. The batch is
   linked in; on amend the replacement takes `old`'s position, state
   slot, identity number and children. The one copy of ARCHITECTURE §3.4
   lands in the first new node's slot — and only when the predecessor
   operation is `ready`, judged from the Python-side status, no round
   trip; every other new slot stays empty, as befits `not_evaluated`
   nodes.
4. **Completed events**, then the caller invalidates — and evaluates when
   the call's `evaluate` says so (MCP_SPECIFICATION §3.2).

A failure anywhere before the commit aborts the call with the forest
untouched: there is no rollback, because nothing happened to roll back.

**Entry points and the lock.** The tool entry takes the forest's lock and
holds it across the whole change; `_insert_children`, `_amend_children`,
`_delete_child`, `_move_child` and the evaluation walk all assume it is
held. One ordering fact: `gen` awaits the ML side's loader lock (§2.3)
while the forest lock is held; nothing on the ML side ever waits for the
forest lock, and that order must stay one-way.

`_move_child` is `move`'s entry: it re-homes a node with its subtree — a
copy on the source side and a copy on the destination side (ARCHITECTURE
§3.4), and **no delete**: the subtree's slots travel with their nodes,
whose names they remain (ARCHITECTURE §3.1).

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
| `on_invalidated()` | completed | the node's status truly left `ready` — not on the walk re-marking a `not_evaluated` node (ARCHITECTURE §3.5; its purpose, §3.6) |
| `on_deleting(reason)` | gate | the node is to leave for good; `reason` is `delete` (whole subtree, children first) or `amend` (the replaced node alone) |
| `on_deleted(reason)` | completed | it left; the Python object is still whole — cancel running work here |
| `on_inserted()` | completed | linked in, children and all |
| `on_removing_child(child, mode)` | gate | `child` is to leave this node's `sub_nodes` |
| `on_added_child(child, mode)` | completed | `child` entered this node's `sub_nodes` |
| `on_inheriting(new_parent)` | gate | on each direct child of a replaced node; never recursive — grandchildren see nothing |
| `on_inherited(old_parent)` | completed | the reparenting happened |
| `on_moving(new_location)` | gate | the node is to move; `new_location` is the resolved Location — the new parent and the index within its `sub_nodes` |
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
a `Theory` root's own `state`, which nothing writes (OPEN_QUESTIONS §1).
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

Every node holds one, `state`, the state before it. The state after it is
computed, as in AoA (`contrib/Isa-Mini/IsaMini/AoA/model.py:4581`):
`resulting_state()` asks the parent, which answers with the next sibling's
`state`, or with the one it keeps for the position after all its children.
So one node's result and the next node's input are one slot, and inserting
or deleting a node moves a value between slots by one copy
(`_insert_children`, `_delete_child`, `_move_child`; ARCHITECTURE §3.4).

**Status.** A status is `NotEvaluated`, `Ready`, or
`CannotEvaluate(blocked_by)` — the Python classes of ARCHITECTURE §3.2's
`not_evaluated`, `ready` and `cannot_evaluate`, §3.3's `blocked_by` riding
inside the third; the reason travels
inside the value, so a `Ready` operation cannot carry a stale one. A `Leaf`
has one, a `StdBlock` two — `evaluation_status_beginning` and
`evaluation_status_ending` — and no node reads another's: the one question
asked of a node from outside is `is_finished()`. Every status write goes
through one setter per operation, which releases what the old status had
written; the two singletons are the same instance across pickling, so `is`
is always right, and a loaded forest's statuses are all `NotEvaluated`.

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
- `Session(NonLeaf_Node)` — groups trees and carries the ROOT entry's fields
  (node_classes/SESSION_AND_THEORY.md §1); not on the evaluation path — the
  forest works on the theories directly (ARCHITECTURE §3.5).
- `Forest(NonLeaf_Node)` — the root above every tree; holds the lock, and
  overrides id resolution and shortest-form printing, the import graph and
  its topological order, invalidation of every tree that imports a changed
  one, and the first step of evaluating imports to their `end`.

An evaluation hook runs the class's own ML callback itself, through `isabelle_driver`
(§4.2), and records what it likes on the node; the framework reads only the
boolean, and on False copies the operation's input into its resulting state
itself (ARCHITECTURE §6.2). `Theory` and `Section` are `StdBlock`s,
`Theorem` and `Define` `Leaf`s.

**The recursion** (ARCHITECTURE §3.5), entered only through
`Node.evaluate_to(ignore_error, evaluate)`, under the forest's lock — taken
once at the tool entry (above) — starting from the forest with the node as
destination. A call's two constants
and the states it releases travel in one `Evaluation`; where the walk is
travels in a `Mode`:

```python
class Evaluation:                    # one evaluate_to call
    destination: Node
    ignore_error: bool
    def release(self, slot)          # deleted together when the call ends

Mode = Evaluating | Seeking | Invalidating
class Evaluating: blocked_by: Node | None   # before the destination: run what is not Ready,
                                            # or, blocked, mark CannotEvaluate(blocked_by)
class Seeking                               # before the destination without evaluating: touch nothing
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
`Evaluating(stop)` unless `ignore_error`. A nesting node whose beginning
failed enters its children with itself as `blocked_by`; a nesting node
whose child stopped cannot run its ending and is `CannotEvaluate` with the
same obstacle. A nesting node is reached at its ending.


### 4.2 `isabelle_driver.py`

One function per callback the ML side offers (MODULE_STRUCTURE §2.5, §2.6):
each knows the callback's name and the MessagePack shape of its arguments and
result, and nothing else does. `model.py` and the node classes call these
functions and never the wire.

### 4.3 `plugin.py`

Imports every package in the list `launch_TAT` received (§2.6) — the
`python_packages` the node class theories registered — and keeps the table
from `kind` to Python class, which importing a package fills through the
`@TAT_node` decorator; one class registers every kind it answers to —
`Theorem` registers `lemma`, `theorem` and `corollary`. The table is what
builds the tool schemas and what `edit` dispatches on; loading also rejects
a class that is omissible on output but compulsory on input
(MCP_SPECIFICATION §2.1).

### 4.4 `builtins.py` and `theorem_node.py`

The predefined node classes of ARCHITECTURE §2.2. `Theorem` has its own file
because `construct` is where everything asynchronous lives: it starts the AoA
search and hangs the running search on the node (ARCHITECTURE §3.6, §9) — how
it drives AoA is designed here, on AoA's own precedent; it stores the method
text AoA found on the node; it queues the message that rides on the next tool
result (MCP_SPECIFICATION §5); and deleting the node cancels it.

### 4.5 `mcp.py`, `mcp_server.py`, `toplevel.py`

`mcp.py` implements the eight tools of MCP_SPECIFICATION §1 and the queue of
pending messages; the future `query` tool (MCP_SPECIFICATION §1.1) will land
here too. `mcp_server.py` builds the
server from them. `toplevel.py` is the procedure Isabelle calls
(`@isabelle_remote_procedure("launch_TAT")`), which does not return for the life of
the conversation and hands the loaded forest its connection.
