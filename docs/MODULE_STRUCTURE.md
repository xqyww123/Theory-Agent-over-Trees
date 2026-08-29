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
etc/settings                  the Isabelle component: TAT_HOME="$COMPONENT"
isabelle_theory_agent/        the Python package (§4); the pip and conda packages carry the same name
test/                         test_*.py for the Python side, Test_*.thy for the ML side
docs/                         the design
pyproject.toml, VERSION       the Python package; VERSION is the one number pip and conda read
conda/recipe.yaml             the conda package
COPYING, COPYING.LIB, COPYRIGHT   LGPL-2.1-or-later, as in Isa-Mini
```

There is no `ROOT`: none of the theories is in a heap. The session loads
`Theory_Agent_over_Trees.thy` — and every node class theory named to it — from
source on the base heap when it starts (ARCHITECTURE §8), finding it through
`$TAT_HOME`.

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

The state slot table (EVALUATOR_DESIGN §1.1): one per session, locked, and
reached only through four operations.

| operation | used when |
| --- | --- |
| `put` | a node's commands have run and its resulting state is stored |
| `get` | a node is about to run, from the state its input slot names |
| `copy` | one slot's state stands as another's: a class with no closing command, or a failed node passed over (ARCHITECTURE §3.1) |
| `delete` | a node is deleted |

### 2.2 Theory table

The map from qualified theory name (EVALUATOR_DESIGN §7) to `theory` value
(EVALUATOR_DESIGN §3), locked like the state slot table. `put` overwrites and `lookup` reads;
nothing else.

### 2.3 Theory loader

Import resolution in the order of EVALUATOR_DESIGN §2, behind one
`Resources.import_name` call (EVALUATOR_DESIGN §7):

- `resolve` — the theory table, then the base heap, then a load from source;
- `load` — the `Thy_Info.use_theories` wrapper of EVALUATOR_DESIGN §6, under
  one lock, one theory per call, with `parallel_proofs = 1` checked at session
  start, reporting how many theories the load cost;
- `check_new_tree_name` — rejects a tree whose base name — the part after the
  last dot, which is what Isabelle compares (EVALUATOR_DESIGN §7) — the base
  heap already uses; the forest side of that check (MCP_SPECIFICATION §2) is
  Python's.

### 2.4 Running commands

The mechanism of EVALUATOR_DESIGN §1, for any node.

- `begin_theory` — reads the header, resolves each import through §2.3, merges
  the parents' keywords, and runs the `theory … begin` span from
  `Toplevel.make_state NONE`.
- `run_commands` — splits a node's text with `Outer_Syntax.parse_spans` and
  runs each span through `Toplevel.command_errors true`, threading the state.
  Returns one record per command: source, range, errors, output.
- `end_theory` — `Toplevel.end_theory`, yielding the value the theory table
  stores.

**Output.** Every `writeln`, `tracing` and `warning` in the process ends in
`Private_Output.writeln_fn`, `tracing_fn` and `warning_fn`
(`contrib/Isabelle2025-2/src/Pure/General/output.ML:66`, `:70`, `:71`). The session
replaces the three once, with functions that route a message by the id in
`Position.thread_data ()` into a per-command buffer, and fall back to the
original function when there is no id. `run_commands` gives each span a fresh
id and runs it under `Position.setmp_thread_data`. The id travels with
`Future.fork` (`Pure/Concurrent/future.ML:452`), so a message printed on a
forked worker still reaches its command's buffer; a key in `Thread_Data` would
not (EVALUATOR_DESIGN §4).

### 2.5 Node classes

The envelope of ARCHITECTURE §6.2, and the one interface a node class author
sees.

A node class registers a function from the session's environment to a local
callback of `Isabelle_RPC` (`Remote_Procedure_Calling.callback'`):

```sml
type env = {
  get : string -> Toplevel.state,           (*§2.1's get, on this session's table*)
  put : string -> Toplevel.state -> unit,   (*§2.1's put, likewise*)
  ...                                        (*the envelope packer*)
}
val register_callback : (env -> Remote_Procedure_Calling.callback') -> unit
```

The environment is bound to one session's state slot table, so it exists only
once the session has started; the registered function is called then.
Registrations wait in a list until then; there is no table of node classes.

The envelope fixes the input slot, the resulting slot and the outcome that
becomes `evaluation_status`; the class adds what it wants recorded, the
per-command records of §2.4 included if it so chooses. A node that did not
write its resulting slot — one that stopped evaluation, or a nesting node whose
opening failed (ARCHITECTURE §3.3) — has its input slot copied into it here,
so no class can forget it.

### 2.6 Session

The entry point of ARCHITECTURE §9. Starting a session:

1. create the state slot table and the environment of §2.5;
2. call every registered function, collecting the node classes' callbacks;
3. add the framework's own: `delete` on state slots, `check_new_tree_name`,
   the loader's report, and one that forks a thread and returns at once — the
   thread's own outer call into Python is the second chain of work
   (ARCHITECTURE §9);
4. install the output routing of §2.4;
5. `Remote_Procedure_Calling.load ["isabelle_theory_agent"]`, then call the
   procedure `TAT` (§4.5), which does not return for the life of the session.

The callbacks go in the `callback` field of that one command, as AoA's do
(`contrib/Isa-Mini/Agent/agent_server.ML:1740-1772`); none enters
`Isabelle_RPC`'s global callback table.

## 3. `TAT_Common_Nodes`

One section per predefined node class, each a client of §2.5.

| section | what its evaluator runs |
| --- | --- |
| `Theory` | the header through §2.4's `begin_theory`, writing the first child's slot; `end` through `end_theory`, writing the theory table |
| `Theorem` | the statement, then `sorry` or `by` with the stored proof (ARCHITECTURE §3.6) |
| `Define` | the commands of ARCHITECTURE §2.2's table, each reported on its own; records `form` |
| `Section`, `Context`, `Locale`, … | unspecified (OPEN_QUESTIONS §2) |

`Theory` is registered like every other class; the framework does not know it.

## 4. Python side

TAT is a library. Whatever starts a session — during development an Isa-REPL
app, later some Isabelle component — is a client built on it, and starting the
Isabelle process is the client's business.

```
isabelle_theory_agent/
  model.py             Node, Forest, ids, evaluation and invalidation, compilation, persistence
  isar_helper.py       segment integrity (appendix/SEGMENT_INTEGRITY.md)
  isabelle_driver.py   typed calls to the ML side's callbacks
  plugin.py            loading node classes and their table
  builtins.py          the predefined node classes
  theorem_node.py      Theorem: construct, the AoA interface, the second chain of work
  mcp.py               the tools, recall, the message queue
  mcp_server.py        the MCP server itself
  toplevel.py          the RPC entry point Isabelle calls into
```

### 4.1 `model.py`

`Node` is the Python half of the node class contract (ARCHITECTURE §6): the
authored and recorded fields, the argument schema that becomes the tool
schema, `emit_isar`, the name it gives the node and its two omissibility flags
(MCP_SPECIFICATION §2.1), an optional `construct`, `__getstate__` for
persistence (ARCHITECTURE §4.1), and `invalidate`, the hook a class overrides
to learn that its context is no longer current (ARCHITECTURE §3.6).

The class hierarchy follows AoA's (`contrib/Isa-Mini/IsaMini/AoA/model.py`,
`class Leaf` :5333, `class NonLeaf_Node` :5449, `class StdBlock` :5836). A
class declares what to run and never runs it:

- `Leaf(Node)` overrides `the_operation()`;
- `NonLeaf_Node(Node)` holds `sub_nodes`;
- `StdBlock(NonLeaf_Node)` overrides `beginning_opr()` and `ending_opr()`;
  `ending_opr()` returning `None` means the class has no closing command and
  its resulting slot is a copy of the slot after its children.

An operation is what the class's evaluator on the ML side is sent (§2.5). The
one place that sends it is `Node._evaluate` below, which runs the beginning
operation, recurses into the children, and then the ending operation.
`Theory` and `Section` are `StdBlock`s — `Section` with no ending operation —
and `Theorem` and `Define` are `Leaf`s.

`Forest` is a `Node` too, the root above every tree, and overrides much: id
resolution and shortest-form printing, the import graph and its topological
order, invalidation of every tree that imports a changed one, and
`evaluate_to`'s first step of evaluating imports to their `end`.

Evaluation and invalidation are one recursion (ARCHITECTURE §3.5), written
once in `Node`:

```python
@dataclass
class EvaluationResult:
    stopped_at: Node | None          # where a class's judgement stopped evaluation
    has_passed_destination: bool

def _evaluate(self, destination: Node, ignore_error: bool,
              has_passed_destination: bool, blocked_by: Node | None) -> EvaluationResult
```

It visits every node of the tree in tree order, and what it does to each is
fixed by the two flags:

| `has_passed_destination` | `blocked_by` | on the node |
| --- | --- | --- |
| false | none | evaluate it, unless it is evaluated already |
| false | an ancestor | mark it `cannot_evaluate`, with that ancestor as the reason |
| true | any | mark it `not_evaluated` |

A nesting node whose opening command failed enters its children with itself
as `blocked_by`. `stopped_at` ends evaluation but not the recursion, which
goes on to invalidate what follows the destination; with `ignore_error` a
class's stop ends nothing. A destination that is already evaluated ends the
call before it starts. The `evaluate_to` tool calls `_evaluate` on the
destination; `edit` marks the edited node `not_evaluated` first and then does
the same.

### 4.2 `isabelle_driver.py`

One function per callback the ML side offers (MODULE_STRUCTURE §2.5, §2.6):
each knows the callback's name and the MessagePack shape of its arguments and
result, and nothing else does. `model.py` and the node classes call these
functions and never the wire.

### 4.3 `plugin.py`

Loads the Python package a node class theory names (ARCHITECTURE §6) and
keeps the table from class name to Python class. The table is what builds the
tool schemas and what `edit` dispatches on; it also rejects a class that is
omissible on output but compulsory on input (MCP_SPECIFICATION §2.1).

### 4.4 `builtins.py` and `theorem_node.py`

The predefined node classes of ARCHITECTURE §2.2. `Theorem` has its own file
because `construct` is where everything asynchronous lives: it asks the ML side
to fork a thread that calls into AoA, so that the search runs on a connection
of its own while evaluation keeps the session's (ARCHITECTURE §9); it stores
the method text AoA found on the node; it queues the message that rides on the
next tool result (MCP_SPECIFICATION §5); and deleting the node cancels it.

### 4.5 `mcp.py`, `mcp_server.py`, `toplevel.py`

`mcp.py` implements the eight tools of MCP_SPECIFICATION §1, `recall`'s two
indexes — the forest, and the library through `contrib/Semantic_Embedding`'s
retrieval — and the queue of pending messages. `mcp_server.py` builds the
server from them. `toplevel.py` is the procedure Isabelle calls
(`@isabelle_remote_procedure("TAT")`), which does not return for the life of
the session and hands the loaded forest its connection.
