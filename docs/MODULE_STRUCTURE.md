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
ML/TAT_Boot.ML                the boot: the protocol command `TAT.boot`, loaded before TAT's theory (§5)
src/scala/tat.scala           the launcher: the Isabelle tools `TAT_new`, `TAT_mcp` and `TAT_compile`, and the Scala function `TAT.reserved_name` (§5)
lib/tat.jar                   the launcher compiled by `isabelle scala_build`; committed, as Isabelle_RPC's jar is
etc/build.props               what `isabelle scala_build` builds into lib/tat.jar, and the classes that register the tools and the Scala function
ROOT                          declares the Isabelle session `Theory_Agent_over_Trees`, by which the launcher loads TAT's theory (§5), and `directories "test"`; its heap is a compile check nothing runs on
etc/settings                  the Isabelle component: TAT_HOME="$COMPONENT", lib/tat.jar on the classpath
Isabelle_Std/                 the plugin of Isabelle's standard commands (§4.5): TAT_Isabelle_Std.thy and ML/ with one file per node class; TAT's own ROOT declares its session `TAT_Isabelle_Std in Isabelle_Std`
isabelle_theory_agent/        the Python package (§4); the pip and conda packages carry the same name
isabelle_theory_agent/tools/  the tools' hand-written JSON schemas (TOOL_SCHEMAS.md)
test/                         test_*.py for the Python side, Test_*.thy for the ML side,
                              and their non-pytest helper modules
docs/                         the design
pyproject.toml, VERSION       the Python package; VERSION is the one number pip and conda read
conda/recipe.yaml             the conda package
COPYING, COPYING.LIB, COPYRIGHT   LGPL-2.1-or-later, as in Isa-Mini
```

The `ROOT` declares one Isabelle session, `Theory_Agent_over_Trees`.
Nothing ever runs on its heap: the entry exists so that the launcher can
load `Theory_Agent_over_Trees.Theory_Agent_over_Trees` by that name (§5),
and as a compile check of the sources — the boot excepted, which only a
starting process compiles (§5). A running conversation never sits
on that heap: `Theory_Agent_over_Trees.thy`, and the theory defining each
plugin the working directory records, are loaded from source on the base
heap when the process starts (ARCHITECTURE §8). Its `directories "test"`
puts `test/` among the session's theory search directories, so that a
`.thy` there — `TAT_Lib_Helper`, the test plugin `Test_TAT_Framework` — is
found by its session-qualified name, `Theory_Agent_over_Trees.<name>`,
while declaring no theory there.

One structure per file except the boot, which defines none, and two
structures in TAT's own theory. Inside a file the body is
divided by Isabelle's sectioning comments — `(*** section ***)`,
`(** subsection **)`, `(* subsubsection *)` — following
`contrib/Isabelle2025-2/src/Doc/Implementation/ML.thy:60-97`.

`TAT_Framework` knows no node class. `TAT_Common_Nodes` is its first client and
carries `Theory`'s callbacks and the helper a node class writes its
callbacks with (`operation`, §3); a plugin's node classes — those of
`Isabelle_Std` (§4.5) first — are other clients of the same interface
(ARCHITECTURE §6), free to use `TAT_Common_Nodes` as well. The test for where something belongs: what the conversation itself
needs — its tables, its loader, its callbacks — is in `TAT_Framework`; what
only a node class needs is in `TAT_Common_Nodes`, or in its plugin.

## 2. `TAT_Framework`

### 2.1 State slots

The state slot table (EVALUATOR_DESIGN §1.1): one per conversation, locked,
and reached only through six operations.

| operation | used when |
| --- | --- |
| `put` | a node's commands have run and its resulting state is stored |
| `get` | a node is about to run, from the state its input slot names |
| `copy` | one slot's state stands as another's: a class with no ending command, a failed node passed over (ARCHITECTURE §3.1), a node inserted or deleted (ARCHITECTURE §3.4). Afterwards the target holds what the source holds — nothing, when the source holds nothing |
| `delete` | an operation's status goes from written to unwritten — an invalidation, a stop's copied-through input included — or the node is deleted; takes a list of names, so a batch is one round trip |
| `exists` | the Python side asks whether a slot holds a state |
| `clear` | a fresh conversation begins on the same Isabelle process (ARCHITECTURE §9): the whole table, between two conversations |

### 2.2 Theory table

The map from qualified theory name (EVALUATOR_DESIGN §7) to `theory` value
(EVALUATOR_DESIGN §3), locked like the state slot table. `put` overwrites,
`lookup` reads, `delete` removes the names an edit made vanish
(`TAT.theory_delete`, §2.6; EVALUATOR_DESIGN §3), a name it does not hold
included, and `clear` empties the table when a fresh conversation begins
(§2.1). The key of an entry `end_theory` writes is the theory value's
own long name — the same string §2.3's resolution produces.

### 2.3 Theory loader

Import resolution in the order of EVALUATOR_DESIGN §2, behind one
`Resources.import_name` call (EVALUATOR_DESIGN §7):

- `resolve` — the theory table, then `fetch`, under the name
  `Resources.import_name` produced;
- `fetch` — the base heap, then a load from source of a theory whose file
  the Isabelle session layout knows under the name's session
  (`Resources.find_theory_file`), nothing by path, and nothing under a
  qualified name whose short name the layout declares global
  (EVALUATOR_DESIGN §7); an import found nowhere, or so named, is refused
  under the name Isabelle resolved it to, with RENDER_BASELINES §3's
  sentence. Also how the theories the launcher names are fetched (§5),
  before any conversation exists;
- `load` — the `Thy_Info.use_theories` wrapper of EVALUATOR_DESIGN §6, under
  one lock, one theory per call, with `parallel_proofs` below 3, which the
  boot sets from the option before its first load (§5) and every load and
  the conversation's start assert (`check_parallel_proofs`); handed the
  name `find_theory_file` answered for, under the empty qualifier, which
  leaves such a name unchanged;
- `check_new_theory_short_name` — one of three answers about a new theory's
  short name — the part after the last dot, which is what Isabelle
  compares (EVALUATOR_DESIGN §7) — in this order: taken by a loaded
  theory, with its long name (`Main` on a HOL heap); reserved, no loaded
  theory bearing it but the Isabelle session layout declaring it global
  (`FOL` on a HOL heap), so that Isabelle would leave a tree so named
  unqualified, or Isabelle refusing it as a file or theory name — the
  Scala function `TAT.reserved_name` of `lib/tat.jar` (§5), asked
  through `Scala.function1`, which answers `Path.is_reserved`,
  `Sessions.illegal_theory` and `Sessions.illegal_session`; free. The
  forest side of the check (MCP_SPECIFICATION §2) is Python's, and so is
  every rejection;
- `check_session` — `Session.gen`'s one question
  (node_classes/SESSION_AND_THEORY.md §1), answered with the first defect
  found: the name reserved (`TAT.reserved_name`, above), the name one the
  Isabelle session layout knows (`is_known_session`, below), an option
  Isabelle does not know or whose value is of the wrong type (the Scala
  function `TAT.check_options` of `lib/tat.jar`, §5, which applies the
  options in turn as Isabelle reads a ROOT, so that what passes here the
  compile's final reading accepts), or a `parent_session` the layout
  does not know; the forest half and every rejection are Python's;
- `is_known_session` — whether the Isabelle session layout knows a session
  of the name (`Resources.check_session`); serves `check_session` and
  nothing on the wire.

### 2.4 Running commands

The mechanism of EVALUATOR_DESIGN §1, for any node.

- `begin_theory` — takes, alongside the header, the tree's Isabelle session
  name — its `Session` node's `name` (node_classes/SESSION_AND_THEORY.md
  §1) — and the `master_dir`, which is that session's folder under the
  working directory (ARCHITECTURE §1): the name qualifies every import
  resolution (EVALUATOR_DESIGN §7). The header's text is read with
  `Thy_Header.read` by the caller; `begin_theory` resolves each import
  through §2.3, builds the header's transition in ML (`Toplevel.make` …
  `|> Toplevel.init_theory`, its init `Resources.begin_theory`) and runs
  it from `Toplevel.make_state NONE`.
- `apply_transition` — one transition, built in ML by its operation,
  applied through `Toplevel.command_errors true`; the answer is
  `operation`'s shape (§3): the state, or the errors as messages, markup
  stripped; a folded interrupt is re-raised. `Theory`'s header goes
  through it (`begin_theory`), its `end` is an ML-built `Toplevel.exit`
  transition through it, and `Theorem` builds one transition from its
  statement's structure (THEOREM.md §6). Nothing splits a node's text into
  spans or registers anything in Isabelle's execution table, which a
  library load's `Execution.reset` wipes (EVALUATOR_DESIGN §6). The
  output buffers below, `Output_Routing.new_buffer` and `take_buffer`,
  are exported beside it.
- `end_theory` — `Toplevel.end_theory`, yielding the value the theory table
  stores.
- `fork_job` — the evaluation jobs' one function (CONSTRUCT_INTERACTION
  §3.3): given a job's id and its work, forks the work as a Future task
  on Isabelle's worker pool, keeps the future under the id in the
  framework's table, and when the work ends calls Python's remote
  procedure `job_finished(id, failure)` with interrupts deferred,
  `failure` one value of two shapes: the messages of the exception the
  work raised, `Runtime.exn_messages` as `operation` reports them, none
  on success; or, when the work raised a `Bug` — found as `operation`
  and the callback wrapper of §2.5 find one, by a test the framework
  holds for all three — the `Bug`'s
  message, which the task also logs as the `isabelle` record `bug` and
  which ends the conversation (CONSTRUCT_INTERACTION §3.3); on the wire
  `["ok"]`, `["messages", [...]]` or `["bug", <message>]`. A work TAT
  cancelled — its future cancelled by `TAT.job_cancel` or `TAT.reset` —
  reports nothing: the Python side cancels only a job it has dropped,
  and a reset ends the conversation that would hear. A work interrupted
  by anything else is reported as a `Bug`, since Python still waits for
  its job. The test is the
  framework's `bug_message : exn -> string option`, the first `Bug` found
  bare, in a `Par_Exn` or in an `Exn.EXCEPTIONS`, a `Bug` counting before
  an interrupt in an exception that holds both. The procedure
  answers at once; a task whose report cannot be delivered logs it — the
  `isabelle` record `report_undelivered` (LOGGING.md §4) — and ends. A
  report left unanswered for five minutes is beyond repair, the Python side
  answering no more: the task logs it the same way and ends the process
  as a disaster — the protocol message `TAT.finished` with code 2 and
  the record's message, which the launcher prints (§2.6). A
  task's records go to the Isabelle side's log that was current at its
  fork (LOGGING.md §5). Its
  counterpart is the callback `TAT.job_cancel(ids)` (§2.6),
  which looks the ids up and cancels the futures. A job's work applies no
  Toplevel transition and calls nothing that forks a proof, so nothing of
  it is ever registered in Isabelle's execution table (EVALUATOR_DESIGN
  §6).

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
the rest is PIDE protocol machinery. Each operation runs its transition
under a fresh id in the thread's position — minted by
`Document_ID.make`, registered nowhere: the id slot of a position is the
execution registry's key, but nothing of TAT's calls `Execution.fork` or
`Execution.print` (EVALUATOR_DESIGN §6) — so its messages land in its
own buffer. The id travels with `Future.fork`
(`Pure/Concurrent/future.ML:452`), so a message printed on a forked
worker still reaches its command's buffer; a key in `Thread_Data` would
not (EVALUATOR_DESIGN §4).

### 2.5 Node classes

The envelope of ARCHITECTURE §6.2, and the one interface a node class author
sees.

A node class registers a function from the conversation's environment to a
callback record of `Isabelle_RPC` (`Remote_Procedure_Calling.callback`:
the name, the argument's unpacker, the result's packer, the function, the
interrupt policy and the timeout):

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
  end_theory    : Toplevel.state -> unit,
                    (*§2.4's, the result put into this conversation's theory table*)
  fork_job      : {id : int, work : unit -> unit} -> unit
                    (*§2.4's: the work as a Future task, its end reported to
                      Python by the remote procedure job_finished*)
}
val register_callback :
  {python_packages : string list} ->    (*the class's Python half; imported at
                                          conversation start, filling the kind
                                          table (§4.4)*)
  (env -> ('a, 'b) Remote_Procedure_Calling.callback) -> theory -> theory
```

The framework makes the wire callback itself
(`Remote_Procedure_Calling.mk_callback`), once it has put one wrapper
around the record's `function`: the wrapper times the function, records
whether it returned, raised or was interrupted as the `isabelle` log event
`callback`, writes the event `bug` when a `TAT_Framework.Bug` left it —
found by the test `operation` and `fork_job` use — and releases the result
unchanged (LOGGING.md §4, §5). The framework's own callbacks (§2.6) are
made the same way, so no callback of a conversation goes unrecorded. On
the wire a state slot is its name (§4.1), and `slot_unpacker` is how a
callback's `arg_schema` takes one: it reads the name and yields the slot —
read, write and delete all on the handle, so the callback never touches a
name. The duplicate check of §2.6 reads the record's `name`.
`begin_theory` and `end_theory` are in the environment because the
theory table they use is the conversation's: the table has exactly one writer,
and a `theory` value that is not the yield of `Toplevel.end_theory` cannot
enter it (EVALUATOR_DESIGN §4's one-producer rule).

The environment is bound to one conversation's tables, so it exists only
once the conversation has started; the registered function is called then.
Until then the registration rides on the theory (`Theory_Data`, applied with
`setup`), so a conversation's node classes are exactly the classes registered
in the ancestries of the theories `start` is given (§2.6), and re-evaluating
a registering theory cannot register twice — the fresh theory value carries
the registration once. There is no other table of node classes.

What the callback takes and returns is the class's own affair, agreed with its
Python half (ARCHITECTURE §6.2). One thing is not its own affair: a
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

The entry point of ARCHITECTURE §9. `start` takes the theories whose
ancestries name the node classes (§2.5) — TAT's own and the one defining
each plugin — the working directory
(ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §1), the port to serve on and
the agent client's name, and starts the conversation:

1. create the state slot table and the environment of §2.5;
2. collect the registrations in those theories' data — a registration
   carries a serial, so one reached through several ancestries counts
   once — and their `python_packages`, deduplicated;
3. call each registration's function with the environment, collecting
   the node classes' callbacks, and add the framework's own:
   `TAT.state_copy`, `TAT.state_delete` and
   `TAT.state_exists` on state slots (§2.1's `copy`, `delete` and `exists`;
   `get` and `put` ride inside the classes' own callbacks and need no wire
   name), `TAT.theory_delete` on the theory table (§2.2's `delete`),
   `TAT.check_new_theory_short_name` (§2.3), whose three answers travel as
   `["taken", <long name>]`, `["reserved"]` and `["free"]`,
   `TAT.check_session` (§2.3), whose answers travel as `["ok"]`,
   `["name_reserved"]`, `["name_known"]`, `["option", <index>,
   <Isabelle's message>]` and `["parent_unknown"]`, `TAT.job_cancel`, which
   cancels the futures of the evaluation jobs whose ids it is given
   (§2.4's `fork_job`), `TAT.log_directory`, which names the directory
   the Isabelle side appends its records to (LOGGING.md §5) and passes
   the name on to the launcher, as the protocol message
   `TAT.log_directory`, sent as `TAT.finished` is (LOGGING.md §7), and
   `TAT.reset`, which cancels every job's future, empties both tables
   (§2.1's and §2.2's `clear`) and begins a fresh Isabelle-side log
   (LOGGING.md §5);
4. install the output routing of §2.4;
5. `Remote_Procedure_Calling.load ["isabelle_theory_agent"]`, then call the
   procedure `launch_TAT` (§4.6) with the collected package list, the
   working directory, the port, the client's name and the text of the
   Isabelle environment variable `TAT_MAX_CONCURRENT_CONSTRUCTION_JOBS`,
   empty when it is unset; `launch_TAT` does
   not return.

The callbacks go in the `callback` field of that one command, as AoA's
`aoa_cmd` does (`contrib/Isa-Mini/Agent/agent_server.ML`); none enters
`Isabelle_RPC`'s global callback table. Two callbacks under one name would
silently shadow each other in that command's dispatch table, so starting the
conversation rejects a duplicated name instead.

A compile (COMPILATION.md) runs step 2 — one function both entries
call — and, of step 3, makes `TAT.log_directory` alone; then
`Remote_Procedure_Calling.load` and the procedure
`compile_TAT` (§4.6) with the collected package list and the working
directory, which returns whether every tree was written and the report's
lines. Its command carries the framework's `TAT.log_directory` and no
class's callback, so nothing a compile does can run anything in
Isabelle.

`start` is reached through the protocol command `TAT.start`, and the
compile through `TAT.compile`, both of which `TAT_Framework.ML` defines
as it is loaded (`Protocol_Command.define`, a Pure API) and the boot runs
once TAT's theory is loaded, the one its first argument names (§5).
`TAT.start`'s arguments are the working directory, the port, the
client's name, then the plugins' theory names; `TAT.compile`'s the
working directory, then the plugins' theory names. The two share one
handler, one ML function: it forks a plain Isabelle thread — no Future
worker, and inside no theory — whose whole body is captured with
`Exn.capture_body` and runs under `Future.interruptible_task`: it fetches
TAT's own theory and each plugin's through `Loader.fetch` (§2.3) — a
load asserting `parallel_proofs` below 3, as `start` does — and calls
`start` or the compile; then, on every path, it answers the launcher
with the protocol message `TAT.finished`, carrying a code and messages
in the shape `build_session_finished` uses, each command supplying its
mapping from a normal result to a code: `TAT.start` `0` when the
conversation ended by `start` returning; `TAT.compile` `0` with the
report's lines when every tree was written and `1` with them when one
was not; either, `2` with the exception's messages when an exception
ended it — a plugin that does not load or is not found, a bug, a
`TAT_DisasterError`, a `TAT_StartupError`, the Python side going away
before the procedure answered, an interrupt at the terminal, whose
message is `Interrupt`; `CRASHED` stands for the messages when they
could not be rendered. The launcher reads the code and never parses
text.

## 3. `TAT_Common_Nodes`

`operation`, the helper a node class writes its callbacks against (§2.5),
then `Theory`'s section, a client of §2.5. The rows after `Theory` are
the plugin `Isabelle_Std`'s, one structure per class in a file of its
own under `Isabelle_Std/ML/` (§4.5) — `Theorem`'s is `TAT_Theorem`.

| section | what it runs |
| --- | --- |
| `operation` | not a class: the helper of §2.5 — a run's state into the slot, its failure as messages, a `Bug` and an interrupt through |
| `Theory` | the header through §2.4's `begin_theory`, writing the first child's slot and answering, beside its messages, the session of each import — `Resources.theory_qualifier` of the resolved name — which the class records as `import_sessions` (COMPILATION.md §2); `end` through an ML-built `Toplevel.exit` transition, writing the tree's resulting slot, and the theory value into the theory table through `end_theory` |
| `Theorem` | `TAT.Theorem.evaluate`: the statement opened and admitted, two direct-ML transitions on the input slot's state, the first's result into the node's `goal_state` slot, the second's into the resulting slot (THEOREM.md §6); `TAT.Theorem.construct`: the proof construction — AoA's `hammer_or_AoA` on the `goal_state` slot's goal, forked through §2.4's `fork_job`, the product reported; `TAT.Theorem.check`: the proof check — the stored product replayed on that goal through the function AoA exports, no Toplevel transition — forked the same way (THEOREM.md §7) |
| `Define` | the commands of ARCHITECTURE §2.2's table, each reported on its own; records `form` |
| `Section`, `Context`, `Locale`, … | unspecified (OPEN_QUESTIONS §1) |

`Theory`'s evaluator is registered like every other class's. `Session`
registers no evaluator: it runs no Isabelle commands — its evaluation is
the forest's scheduling (ARCHITECTURE §3.5) — and it emits nothing:
`compile` writes its ROOT entry from its fields (COMPILATION.md §2). The
Python halves of both are framework classes in `model.py` (§4.1).

## 4. Python side

TAT is an Isabelle component (§1) and an MCP server for one agent client
process (ARCHITECTURE §9). Launching the Isabelle process is the launcher's
business, `isabelle TAT_mcp` and `isabelle TAT_compile` (§5).

```
isabelle_theory_agent/
  exceptions.py        the TAT_Error hierarchy (EXCEPTIONS.md)
  model.py             Node, Forest, Conversation, ids, evaluation and invalidation, persistence; Session and Theory
  jobs.py              Construction_Job, Evaluation_Job, Unfinished, Interactive_Question and Answered, Agent, messages and mailboxes (CONSTRUCT_INTERACTION §3, §4)
  edit.py              building nodes from constructs; the entries behind edit, move and delete
  compile.py           compile, Compile_Report, report_lines and the path listing `paths`: the forest written as `.thy` files and a ROOT (COMPILATION.md §5)
  invariants.py        the store-mirror helper a node class's test suite calls on its forests (COMPILATION.md §3)
  store.py             Forest_Store and Node_Rows: the working directory's database (ARCHITECTURE §4.1)
  log.py               Log: a conversation's or a compile's log (LOGGING.md)
  hook.py              the conversation's hooks' script, copied into the working directory's .tat/ by configure (CLIENT_HOOKS.md §1)
  guard.py             the guard script that keeps Claude Code's agents in the agent directory, copied likewise (CLIENT_HOOKS.md §5)
  isabelle_driver.py   typed calls to the ML side's callbacks; IsaTerm in, IsaTerm out for Isabelle text
  plugin.py            loading node classes and their table; the argument schema grammar
  std/                 the Python half of the plugin Isabelle_Std (§4.5), one module per node class: theorem.py, Theorem with Proof_Job and Proof_Check (THEOREM.md); statement.py, the statement's schema definitions
  mcp.py               the tools, recall
  mcp_server.py        the Streamable HTTP MCP server and its tool boundary, which delivers an agent's mailbox; TAT_Server and its two client subclasses (CONSTRUCT_INTERACTION §8)
  toplevel.py          the two RPC entry points Isabelle calls into, launch_TAT and compile_TAT: the ending object, the Conversation, the Forest, the server
  tools/*.jsonc        the tools' schemas; edit's $defs filled at start (PLUGIN_SYSTEM §4)
```

A leading underscore marks a framework-internal member: the framework's
own modules use it across files; a node class and a plugin never touch it.

### 4.1 `model.py`

`Node` is the Python half of the node class contract (ARCHITECTURE §6): the
authored and recorded fields, the argument schema — a TypedDict the
framework checks submitted constructs against (§4.2, §4.4), and which types
`gen`'s `raw` for the static checker — `gen` (below), `can_emit` and `emit` (COMPILATION.md §3), the name it gives the node and its two omissibility
flags (MCP_SPECIFICATION §2.1), `index_of()` — the node's position in its
parent's `sub_nodes`, computed, never stored — the class attributes
`construction_job_class` and `evaluation_job_class`, `None` by default,
with `job()` returning the node's construction job (CONSTRUCT_INTERACTION
§3.1), `to_store` and `from_store` for persistence (ARCHITECTURE §4.1),
`_unfinished()` (ARCHITECTURE §3.2), `_own_statuses()` — the statuses of the node's own
operations, in the order it runs them: `[self._status]` for a `Leaf`, the
beginning's and the ending's for a `StdBlock`, none for an
`Unchained_Node`; the three implementations are `final`, and the loader
refuses an override (PLUGIN_SYSTEM §5) — from which the framework
derives `_operations_ready()`, `print_fields` and `mark` (PRINT.md), the
stored list `last_evaluation_statuses()` in the same order, made by
`Node`'s constructor from `_operation_names()`, the operations' names in
that order, which the three base classes answer likewise
(COMPILATION.md §4); and the event hooks (below).

Four aliases name what an id is made of: `Id = str`, the dotted string the
agent sees; `Id_Component = str`, one `<kind>_<name>`; `Id_Components =
list[Id_Component]`, what `id_components(id)` splits an `Id` into; and
`Identity = int`, the stored, opaque number (ARCHITECTURE §4.1).

Every rendering (PRINT.md) is one call of `Forest.render(node: Node,
mode: PrintMode, agent: Agent) -> str`: it builds an index from id
component to the nodes bearing it, holds `agent` — the agent the
rendering is for, whose seen set `mark` and `print_fields` reach through
the forest (CONSTRUCT_INTERACTION §6) — for the call's duration as it holds
the index, calls `node.print(0, out, mode, 0)` into a buffer, discards both
in a `finally`, and returns the text; `id_of` uses the index while one
stands and computes as before otherwise, so `resolve`'s guesses work
outside a rendering. The index goes with the rendering because a move can
change a printed short form (MCP_SPECIFICATION §2.2), and it is sound
because rendering is synchronous throughout — `print`, `print_fields`,
`mark`, `is_finished`, `id_of` — so a rendering sees one forest and needs
no lock. For `Relative_Focus(nodes, depth)` the same
call collects the ancestors of every node of `nodes` — walking up, never
down — into `_above`, which the descent consults for what is on the
path, and refuses an empty `nodes`, a node of `nodes` outside `node`, or
one under another (`TAT_InternalError`); `detailed` is a method of
`Node`, since a focus is the node's own membership of `nodes`. The framework's `print` also holds the lone
session's form (PRINT.md §6): descending from the forest into its only
child, at `depth >= 1`, it writes the child's line without the dash and
the child's body at the same indent. The seen set (PRINT.md §4) is each
agent's, `Agent.seen: set[Key]` with `Key = tuple[int, str | None]`;
`Conversation.forget(key)` removes a key from every agent's set, which is
how the status setter discards an operation's message keys at every
write (COMPILATION.md §4), and a compaction clears the compacted agent's
set alone (CONSTRUCT_INTERACTION §6).

**Construction.** A node enters the forest from a `RawAST` — the JSON
object the agent submitted, `Mapping[str, Any]` — less `children`, which
no `gen` ever sees (§4.2). Everything semantic lives in `gen`:

```python
@dataclass(frozen=True)
class Insertion:             # the batch joins `parent`'s children and none of them
    pass                     # leaves: append / insert_before / insert_after, and
                             # every construct's `children`, an amend's included

@dataclass(frozen=True)
class Amendment:             # amend: `old`, one of `parent`'s children, leaves the
    old: Node                # forest with the call — every construct of the batch
                             # leaves it out of whatever it looks up among the
                             # forest's nodes, uniqueness and existence alike;
                             # never mutate it. The batch's first construct takes
                             # its place, the rest follow it

Role = Insertion | Amendment

class NodeConfig(NamedTuple):
    state: Isar_State_Slot   # the state before the node. A name: the slot may
                             # hold nothing, and gen neither reads nor writes
                             # through it — only evaluation hooks may assume a
                             # slot holds a state (see Events)
    parent: NonLeaf_Node     # never None: the forest root is not made this way.
                             # Its sub_nodes are the children before the call;
                             # during an edit the parent may itself be a node not
                             # yet in the forest (a nesting node under construction)
    batch_before: tuple[Node, ...]
                             # the batch's constructs built before this one, in
                             # submission order — the ones after it are not built
                             # yet. Built, not placed: fields, kind and identity
                             # set, `parent` the one their gen was given, but not
                             # among its children and not in the forest; read
                             # their fields, never resolve, print or walk up from
                             # them
    role: Role               # what the call does to `parent`'s children

    def replaces(self) -> Node | None
                             # the node this construct takes the place of: an
                             # amendment's `old` for the batch's first construct,
                             # else None. Read it to carry over recorded fields the
                             # class judges still valid — Theorem asks for the old
                             # job's outcome to be carried, as the store's image,
                             # when for_any, premises and conclusion are unchanged
                             # (CONSTRUCT_INTERACTION §3.1, THEOREM.md §4)

@classmethod
async def gen(cls, config: NodeConfig, raw: RawAST) -> Self
```

`gen` checks and constructs; the framework owns placement. Where a node
may live is the node's own judgement: its `gen` refuses a parent its class
cannot live under — `Bad<Class>NodeParent`, EXCEPTIONS.md §3 — and on a
move its `on_moving` does; the framework checks no containment. A `gen`
that amends may ask the framework to carry the replaced node's job
outcome to the new node, `carry_job_from(old)`, which the commit honours
(CONSTRUCT_INTERACTION §3.1). It may read
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
- **A completed hook is for effect.** It fires inside the commit's one
  synchronous block, after the pointer surgery and the in-memory
  invalidation and before the store write (§4.2), so what it changes on
  a node is stored with the edit; it is synchronous — the loader refuses
  an `async` override. Raising anything, `BadEdit` included, is the
  class's bug (EXCEPTIONS.md §1). The framework itself cancels a deleted
  or amended node's construction job and drops its evaluation job in the
  completed events, never at the gates; no class writes that
  (CONSTRUCT_INTERACTION §9).

| hook | tense | fires |
| --- | --- | --- |
| `on_invalidated(operation)` | completed | an operation's status truly left `ready` — not on the walk re-marking a `not_evaluated` node (ARCHITECTURE §3.5). `operation` says which: a `StdBlock` passes `beginning` or `ending`, a `Leaf` passes `None`. For a class that keeps something derived from its evaluation and must discard it then; a running construction job is told of a changed context by `_on_context_change` (CONSTRUCT_INTERACTION §3.2), not here. No shipped class overrides it |
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
the node's own `on_inserted` or `on_moved`. `on_invalidated` fires in the
status setter, so before all of these: in an edit, during the commit's
in-memory invalidation (§4.2 step 3); in an evaluation, during its walk.
A running construction job has a hook of its own,
`_on_context_change`, called by the status setters on every
write of the node's own evaluation status by the walk while the job runs
— a rerun's rewrite of `ready` included — independently of
`on_invalidated`, and called as a completed hook is: after the write,
through `_completed`, so whatever it raises, a `TAT_Error` included, is
its class's bug (EXCEPTIONS.md §1). Its default cancels the job
(CONSTRUCT_INTERACTION §3.2).

No hook fires on an aborted call. In any hook, as in `gen`, a state slot
may hold nothing; the only code that may assume its slot holds a state is
an evaluation hook — `_eval_opr`, `_eval_beginning_opr`,
`_eval_ending_opr` — because the recursion runs a node only from the
input its predecessor wrote (ARCHITECTURE §3.4, §3.5). The one exception is
a `Theory` root's own `state`, which nothing ever writes
(ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §6).
Everything that needs the prover — fetching facts, checking terms,
recording results — therefore belongs in the evaluation hooks, not in
`gen` and not in events.

**States.** `Isar_State_Slot` is a name in the ML side's state slot table
(§2.1) together with the `Conversation`, which holds the connection and
the log its round trips are recorded in; on the wire it is the name
(`to_msgpack`, `from_msgpack`). It offers `copy_to`, `delete` and
`is_initialized` — §2.1's `copy`, `delete` and `exists`, seen from Python —
each a round trip; nothing about the table is mirrored on
the Python side. Persistence keeps neither the name nor the connection: a
loaded forest is reassigned its slots.

Every node holds one, `state`, the state before it. A class may own
further slots — `Theorem`'s `goal_state` (THEOREM.md §6) — and does so
itself: it mints each where the node is built, in `gen` and
`from_store`; appends it in `_states_inside()`, so that it is deleted
with the node; and names it in `_slots_written_by(operation)`, empty by
default, which answers the further slots an operation writes besides
its resulting state — `operation` as `on_invalidated` is told it. The
framework releases them with the operation's resulting state, in the
setter that takes the operation from written to unwritten; only the
class's evaluation callback writes them. The
state after a node,
`resulting_state()`, is computed, as in AoA
(`contrib/Isa-Mini/IsaMini/AoA/model.py`'s `Node.resulting_state`): under a chaining parent it
asks the parent, which answers with the next sibling's `state`, or with the
one it keeps for the position after all its children — so one node's result
and the next node's input are one slot, and inserting or deleting a node
moves a value between slots by one copy (`edit.insert`, `edit.delete`,
`edit.move`; ARCHITECTURE §3.4); under an `Unchained_Node`, which chains
nothing, a node that has a result owns the slot for it, as `Theory` does
with `_state_after_ending` (ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §6).

**Status.** A status value is `NOT_EVALUATED`, the one `NotEvaluated`,
a `Ready(messages)` or a `CannotEvaluate(messages)` — the Python classes
of ARCHITECTURE §3.2's `not_evaluated`, `ready` and `cannot_evaluate`;
the last two are frozen dataclasses with one field, `messages:
tuple[IsaTerm, ...]`, the output of the run that left the status, so a
kind is tested with `isinstance` and `==` compares the messages too;
`Ready()` is a clean run, and `READY_CLEAN` a module-level instance of
it, a value and never a kind (COMPILATION.md §4). A `Leaf`
has one, a `StdBlock` two — `evaluation_status_beginning` and
`evaluation_status_ending` — and no node reads another's: the one question
asked of a node from outside is `is_finished()`, which the framework
answers — every operation of the node and of its subtree `Ready`, and
`_unfinished()` `None` on it and on every node of its subtree
(ARCHITECTURE §3.2, CONSTRUCT_INTERACTION §3.1); a class may override
`_unfinished()` and never `is_finished()`, and the loader refuses one
that does (PLUGIN_SYSTEM §5). Every status write goes through one setter per
operation, which releases the operation's resulting state, and the
further slots the class says the operation writes (above), when the
status goes from written to
unwritten — never on a rewrite; a loaded forest's
instant statuses are all `NOT_EVALUATED`, its stored ones what the last
run left. Each setter writes the instant status
and its stored status, and is a plain method (COMPILATION.md §4); it also
clears the node's stored check when the stored status leaves `Ready`,
discards the seen set's keys for the operation's messages, adds the
node to the walk's `stored` (below), and writes the `evaluation` log
event `operation` (LOGGING.md §4) — for which it takes one argument
besides the status: how long the evaluation hook ran, or `None` when no
hook ran, so that every write says whether a run produced it. Given
`not_evaluated` for an operation whose stored status is already
`not_evaluated`, the setter does nothing, so a repeated marking stores
and logs nothing again. At every write by the walk, a
rerun's rewrite of `ready` included, it calls a running construction
job's `_on_context_change`, through `_completed` as it fires
`on_invalidated`, and drops the node's evaluation job
(CONSTRUCT_INTERACTION §3.2, §3.3). Beside the instant statuses a node
holds `_last_evaluation_statuses`, one list in `_own_statuses()`'s
order, read through `last_evaluation_statuses()` and stored as the
reserved row `last_evaluation_statuses`, and the stored check,
`_check_outcome`, read through `check_outcome()` (ARCHITECTURE §4.1);
`_resulting_status()` is the status of the operation that writes
`resulting_state()`. The guards that decide to invalidate or keep a
stored status read the stored field; everything about slots and
running reads the instant one (COMPILATION.md §4).
`Theory`'s ending setter also carries ARCHITECTURE §3.4's rule: when the
stored ending, a `Ready`, is replaced by a value that is not a `Ready`,
each direct importer is invalidated whole, `_invalidate(ev)`, under
the same `Evaluation` (the invalidation functions, below).

**Hierarchy**, following AoA's (`class Leaf` :5333, `class NonLeaf_Node`
:5449, `class StdBlock` :5836):

- `Leaf(Node)` — a class overrides `_eval_opr() -> Ready |
  CannotEvaluate`: run the node from `state` into `resulting_state()`,
  returning the status the run leaves, its messages on it; and `emit`
  (COMPILATION.md §3).
- `NonLeaf_Node(Node)` — `sub_nodes`, `_resulting_state_of_child`, and the
  children loop of the recursion.
- `StdBlock(NonLeaf_Node)` — keeps `_state_before_ending`, the slot after all
  its children; a class overrides `_eval_beginning_opr() -> Ready |
  CannotEvaluate` (from `state` into the first child's `state`) and, if
  it has an ending command, `_eval_ending_opr() -> Ready |
  CannotEvaluate` (from `_state_before_ending` into `resulting_state()`);
  the default ending copies. Its `emit` is the framework's, `final`; a
  class overrides `emit_beginning` and, exactly when `_eval_ending_opr`,
  `emit_ending` (COMPILATION.md §3).
- `Unchained_Node(NonLeaf_Node)` — a container whose children are not
  chained: no child's result is the next child's input, it mints no slot
  and runs no operation of its own; a child that has a result owns the
  slot for it (ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §6).
- `Session(Unchained_Node)` — groups trees and carries the ROOT entry's
  fields (node_classes/SESSION_AND_THEORY.md §1); not on the evaluation
  path — the forest works on the theories directly (ARCHITECTURE §3.5),
  and a walk reaching a `Session` is a framework bug; emits nothing,
  `compile` writing its entry (COMPILATION.md §2).
- `Theory(StdBlock)` — the root of a tree (node_classes/SESSION_AND_THEORY.md
  §2); owns its resulting slot, `_state_after_ending`, which nothing
  reads; `file_path()`, `<Session name>/<short name>.thy`, which the
  header's `master_dir`, the compile and the compile hooks share; and
  `import_sessions`, recorded when the header runs (COMPILATION.md §2).
  Before its header runs it makes its `Session`'s folder when that is
  absent, with the function the compile uses (COMPILATION.md §2, §5), so
  that AoA's proof store beside the file has a directory to be written
  in (THEOREM.md §7). A folder that cannot be made — its path holds
  something that is not a directory, or the system refuses — ends the
  conversation with a `TAT_StartupError` (EXCEPTIONS.md §1): the
  working directory's structure is TAT's alone, and nothing an agent
  can do repairs it.
- `Forest(Unchained_Node)` — the root above every `Session`. Holds the
  lock, the store (ARCHITECTURE §4.1) and the `Conversation`; resolves ids
  and prints their shortest form; and, in the walk, keeps the import graph
  (recomputed whenever needed, never stored), routes a walk to the tree it
  concerns, invalidates every tree that imports a changed one, and runs a
  tree's imports to their `end`; `_order_violation(node)` answers the
  `imports` item that violates the order constraint (ARCHITECTURE §3.3),
  and None off a violating `Theory`, so the tool may ask it of any node a
  result names.

`Conversation` is what one conversation, or one compile, is given and
the forest does not store — this list and no other: the connection to the
Isabelle side, the working directory (ARCHITECTURE §4), the log
(LOGGING.md §2), the ending object (§4.6), the bound on the
construction jobs running at once, None for none (node_classes/THEOREM.md
§7; a compile has none), and the agents of the client process by the
identity the client gives them (CONSTRUCT_INTERACTION §4), which the
server creates and whose seen sets `forget` reaches (§4.1). A node
reaches it through `forest().conversation` (PLUGIN_SYSTEM §2).

An evaluation hook runs the class's own ML callback (§2.5) itself, through
`isabelle_driver.call` (§4.3) — once per hook: `_eval_opr` once,
`_eval_beginning_opr` and `_eval_ending_opr` once each — so that one
operation is one round trip and the ML side completes the whole operation
inside that one call; it records what it likes
on the node, and the framework reads only the status it returns,
copying the operation's input into its resulting state itself on a
`CannotEvaluate` — for a beginning, the node's input into the node's
resulting slot, as the ending's write and only when the walk goes on
after the block (below; ARCHITECTURE §6.2). The jobs are exempt from the cadence: a construction job's `_run`
and an evaluation job's `_start` design their own use of the wire, still
through `call` (CONSTRUCT_INTERACTION §3.2, §3.3). `gen` and the event
hooks never call a class's own callback;
`gen` reads only through the framework's query functions (§4.3).
`Theory` and `Section` are `StdBlock`s, `Theorem` and `Define` `Leaf`s.

**The recursion** (ARCHITECTURE §3.5), entered through
`Node.evaluate_to(agent, ignore_error, checks)` — `agent` is the
caller, the starter of the jobs the walk starts; `checks` says whether
the walk starts evaluation jobs on the nodes it passes, and `"blocking"`
keeps the lock after the walk until every evaluation job running on a
passed node has ended (CONSTRUCT_INTERACTION §3.3, §5) — and, for an
edit's unconditional invalidation, `Forest._invalidate_from(position,
ev)`, a plain function run inside the edit's commit block (§4.2 step
3), which runs nothing and awaits nothing — both under the forest's lock
(above), starting from the forest. Two shapes of destination: an
evaluating walk has a destination node; an edit's invalidation starts at
a `Location`. A walk's constants, what it releases, drops and stores,
and the nodes it passed travel in one `Evaluation`; where the walk is
travels in an `Evaluating`:

```python
class Evaluation:                    # one walk: made by the walk's entry for `Forest._run`, and
    destination: Node | None         # by an edit for its commit; its released slots, `dropped` and
                                     # `stored` emptied at each tree's end, `passed` kept
                                     # — `destination`: the node an evaluating walk runs up to and
                                     # including; none for an edit's invalidation
    ignore_error: bool
    starter: Agent | None            # the caller, starter of the jobs the walk starts; None starts none
    checks: str                      # "no" | "quick" | "blocking" (CONSTRUCT_INTERACTION §5)
    passed: list[Node]               # the nodes reached in Evaluating, for `blocking` to wait on
    stopped_at: Node | None          # where the walk stopped, written by `_run` when it ends
    started: list[Construction_Job]  # the constructions the walk started automatically, for the
                                     # result's `Automatically started …` line (CONSTRUCT_INTERACTION §5)
    was_not_ready: set[Node]         # a stored status of these was not `ready` before the walk wrote it:
                                     # the invalidation since a failure that automatic construction asks for
    dropped: list[int]               # the evaluation jobs dropped, their ids sent as cancel(ids) at flush
    stored: set[Node]                # the nodes whose status the walk wrote — a setter adds each —
                                     # stored whole at each tree's end and when the walk ends
    def release(self, slot)          # deleted together when the Evaluation is flushed

class Evaluating                            # before the destination: run what is not_evaluated

@dataclass(frozen=True)
class EvaluationResult:
    stopped_at: Node | None          # the node evaluation stopped at, if it stopped
    mode: Evaluating | None          # the mode the node after this one runs under; None past
                                     # the destination, past a stop when `ignore_error` is
                                     # unset, or at a failed beginning the destination lies
                                     # under: nothing more runs

async def _evaluate(self, ev: Evaluation, mode: Evaluating) -> EvaluationResult
def _invalidate(self, ev: Evaluation) -> None            # Leaf, StdBlock, Unchained_Node: the node whole,
                                                         # NotEvaluated through its setters; plain, awaits nothing
def _invalidate_from(self, position: Location, ev: Evaluation) -> None   # Forest: from the position
                                                         # to the tree's end and up the ancestors
```

`Leaf`, `StdBlock` and `Forest` each write `_evaluate`; `StdBlock`'s runs
the beginning, the children, then the ending, and nothing is skipped up
to the destination: a written operation is not rerun — what stands after
one that ran is `not_evaluated` already, every invalidation running
forward to the tree's end (ARCHITECTURE §3.4) — but every node up
to the destination, or up to the first stop when `ignore_error` is
unset, or, whatever the flag, up to a nesting node above the
destination whose beginning failed, is visited. `Forest`'s handles each tree of the
closure of the trees the destination stands for, in tree order, by the
first of three cases that applies — the order constraint's stop, the
stop crossing an import dependency, the run (ARCHITECTURE §3.3) — all
under the walk's one `Evaluation`, which `_handle_tree` stores and
flushes at each tree's end — the nodes in `stored` written, the released
slots deleted, `cancel(ids)` sent for `dropped`, each then emptied,
`passed` kept — so a walk over several trees deletes what it released at
each tree's end and `blocking` waits on every tree's passed nodes; a tree
reaching the second case has every resolved import earlier in tree order
and already handled, so its statuses are current. The mode changes in
`_mode_after`, which answers `None` at the destination and at a stop
when `ignore_error` is unset, and otherwise `Evaluating`, and at a
nesting node whose beginning failed, which answers `None` when the
destination lies under it (below).
An evaluating walk's destination is a node, reached at its ending;
there, as at a stop when `ignore_error` is unset, `_evaluate` returns,
and `_handle_tree` hands what follows to `_invalidate_from` (below).

Invalidation is the two plain functions, which run nothing and await
nothing, so the edit's commit block can hold them (§4.2 step 3), and
whose setters release, drop and store onto the `ev` they are given.
`_invalidate(ev)` on a `Leaf` writes its operation `not_evaluated`; on a
`StdBlock` its beginning, each child through the child's own
`_invalidate`, then its ending; on an `Unchained_Node`, which has no
operation, each child through the child's own `_invalidate`. The
setter's guard (above) makes a repeated invalidation store nothing
again. `Forest._invalidate_from(position, ev)` writes
`not_evaluated` from `position` to the end of its tree: the siblings
from that index, each whole, then the parent's ending, then the parent's
later siblings, and so on up to the tree's `end`; a position at the
index after the last child is the parent's ending; a position whose
parent is a `Session` or the root marks nothing, sibling trees being
independent. `Theory`'s ending setter, finding a stored `Ready` ending
replaced by a value that is not a `Ready`, calls `_invalidate(ev)` on
each direct importer (ARCHITECTURE §3.4), so the cascade runs,
synchronously, inside whatever wrote the ending; the assignment comes
first, so within one cascade no stored ending leaves `Ready` twice, and
a cycle of imports ends at a tree whose ending is already
`not_evaluated`. Their callers, all under the forest's lock: the edit's
commit (`_invalidate_from` at each position whose input the edit
changed — one for an insert, an amend or a delete, two for a `move`
(§4.2); `_invalidate` on each tree whose record changed,
`_invalidate_changed_trees`); `Theory`'s ending setter, on each direct
importer; and the evaluating walk — `_handle_tree` calls `_invalidate`
on a tree it stops at, one breaking the order constraint or one whose
import has no theory value (ARCHITECTURE §3.3); a nesting node whose
beginning failed calls `_invalidate` on each child; and `_handle_tree`
calls `_invalidate_from` once, under the walk's `Evaluation`, after the
tree's `_evaluate` returns and before the tree's store and flush: with
the position after `stopped_at` when the tree's `_evaluate` stopped
there — after the destination instead when the stop is a nesting node
above it whose beginning failed; otherwise, when the destination lies
in the tree, with the position after the destination, whether the walk
reached it or a nesting node above it whose beginning failed answered
`None` under `ignore_error`; and not at all for a tree run to its own
`end`. The
walk's result tells it: the destination, or the stop when
`ignore_error` is unset, answers `mode` `None` (`_mode_after`, or the
nesting node itself, below), and
every enclosing node up to the tree's `Theory`, seeing `None` from a
child, runs nothing more and answers `None` itself, with the child's
`stopped_at`; the forest then goes on to the next tree it schedules. A nesting node
whose beginning failed invalidates each child whole, `_invalidate(ev)`,
answers `None` when the destination lies under it — with itself as
`stopped_at` when `ignore_error` is unset — and otherwise copies
its input to its ending and carries on. A resulting state
is released only when the status of the operation that writes it goes from
written to unwritten; a rewrite releases nothing. A nesting node is reached
at its ending.

### 4.2 `edit.py`

Changing the forest: how a submitted construct becomes a node, and the
four entries behind the `edit`, `move` and `delete` tools — `insert`,
`amend`, `delete`, `move`. Each returns what the tool's quickview focuses
on (PRINT.md §5): `insert` and `amend` the batch, its last element the
natural destination (MCP_SPECIFICATION §3.2); `delete` the parent it
left; `move` nothing, the caller holding the moved node.

Two fields of a construct belong to the framework: `kind` selects the
node class (§4.4), and `children` — which no `gen` ever sees — holds a
nesting node's contents. The framework checks the construct's mechanical
shape — no field the class does not declare, required fields present,
types right — against the class's declared argument schema
(`check_fields`, §4.4), raising `UnexpectedField` / `MissingField` /
`InvalidField` before the class is consulted. The JSON tool schemas are
hand-written, as AoA's (`contrib/Isa-Mini/IsaMini/AoA/tools/`).

An `edit` takes the trees' record first — per tree, its qualified name
and its resolved imports, the `Theory` nodes themselves
(`Forest._record`) — and builds everything before it touches the forest:

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
   leaving) or an earlier construct of the call already bears there,
   compared without regard to case, since Isabelle refuses two theory
   files whose names differ only in case (`DuplicateTheoryShortName`,
   naming the holder), finding the forest's by walking it.
   Each construct is built with the batch's earlier constructs and its
   batch's role in its `NodeConfig` (§4.1): an amend's batch under
   `Amendment(old)`, its first element the replacement; a construct's
   `children` are a batch of their own, inserted. The amend loop walks
   the whole submitted list, so every `raw_ast_path` indexes the agent's
   own list. On every node built that has a construction job the
   framework then writes the call's `auto_construct` on the job
   (CONSTRUCT_INTERACTION §3.2); the value does not travel in
   `NodeConfig`, and no class sees it, as none sees `evaluate`.
2. **Gates.** The hooks that may still veto (§4.1's events), `BadEdit`
   their only voice.
3. **Commit** — first the one copy of ARCHITECTURE §3.4, a round trip
   (`copy_to`) made before the synchronous block (`move` makes two,
   below): the predecessor's resulting state is copied into the first
   new node's slot, and only when the predecessor operation has written
   it: `ready`, or a stop whose copy-through counts — not a failed
   beginning, which writes nothing: the block's result, when the walk
   goes on, is its ending's write (§4.1) — judged from
   the instant status (`evaluation_status`); every other new slot stays empty, as befits
   `not_evaluated` nodes. Then one synchronous block, nothing awaited
   inside it, so a call holding no lock never sees a part-changed forest
   (MCP_SPECIFICATION §5): the pointer surgery, which cannot fail — the
   batch is linked in; on amend the replacement takes `old`'s position,
   state slot, identity number and children; then the in-memory
   invalidation, `Forest._invalidate_from(position, ev)` (§4.1; `move`
   calls it at two positions, below), a plain
   function on the edit's `Evaluation` — the statuses written
   `not_evaluated` through the setters, which release the slots, drop
   the evaluation jobs and mark the nodes for the store onto it, and fire
   `on_invalidated`; the cascade to the importers through `Theory`'s
   ending setter, and through the comparison of the record with the
   trees as they now are (`Forest._invalidate_changed_trees`, plain: a
   tree present in both whose record changed is invalidated whole,
   `_invalidate(ev)`; the names that vanished are returned for step 4's
   `theory_delete`); then the other completed
   events, in which the framework cancels a deleted or amended node's
   construction job and drops its evaluation job (CONSTRUCT_INTERACTION
   §9); then one store transaction writing every node changed — the new
   rows, the `children` row, every node whose status the commit wrote and
   every node still in the forest that a completed hook fired on — and
   deleting the rows of a deleted subtree (ARCHITECTURE §4.1); an amend
   deletes nothing, its identity passing to the replacement, whose rows
   replace `old`'s; `_store_node` refuses, with `TAT_InternalError`, a
   node whose parent chain does not reach the forest. A transaction that fails
   raises `TAT_DisasterError` (EXCEPTIONS.md §1): memory and the database
   have parted, and the conversation ends.
4. **The round trips**, after the block: every qualified name that
   vanished is removed from the ML theory table (ARCHITECTURE §3.4;
   §4.3's `theory_delete`), the released slots are deleted
   (`state_delete`), and the tasks of the evaluation jobs dropped in the
   block are cancelled (`cancel(ids)`, CONSTRUCT_INTERACTION §3.3); then
   the caller evaluates when the call's
   `evaluate` says so (MCP_SPECIFICATION §3.2), with `checks` `"quick"`.

A failure anywhere before the commit aborts the call with the forest
untouched: there is no rollback, because nothing happened to roll back.

**Entry points and the lock.** The tool entries that hold the forest's
lock — `edit`, `move`, `delete`, `evaluate_to` — hold it across the whole
call; `recall`, the future `query`, and the four construct tools —
`construct`, `cancel_construct`, `check_construct`, `answer`, each
synchronous from its checks to its change — take none (MCP_SPECIFICATION
§5, CONSTRUCT_INTERACTION §9). A call is cancelled only by the
conversation's ending (ARCHITECTURE §9). `evaluate_to`'s tool entry
takes it and drives the walk through `Forest._run`, holding it through
`blocking`'s wait and the quickview — `Node.evaluate_to` takes it itself
for a caller outside the tools; an edit's tool entry takes it
and calls `insert`, `amend`, `delete` or `move`, which assume it held, as
does the walk each ends with. One ordering fact: `gen` awaits the ML
side's loader lock (§2.3) while the forest lock is held; nothing on the
ML side ever waits for the forest lock, and that order must stay one-way —
it holds by construction, since a job's report is settled in one
synchronous step under no lock (CONSTRUCT_INTERACTION §3.3) and no lock
holder awaits a job's task.

`move` re-homes a node with its subtree — a copy on the source side and a
copy on the destination side (ARCHITECTURE §3.4), both round trips made
before the commit's synchronous block (step 3). Its invalidation runs
from two positions, each whose input the move changed: the source
successor's, taken after the pointer surgery — the parent's ending when
the moved node was last — where the successor now reads the
predecessor's result, so that tree's ending and through it that tree's
importers are invalidated too; and the moved node's new position, which
takes its whole subtree. The setter's guard makes the overlap of the two
harmless. The subtree's slots
travel with their nodes, whose names they remain (ARCHITECTURE §3.1); no
slot is deleted. One value may be released: the moved node's old input,
when nothing wrote a value at the destination — its writer is still
current, so no release would otherwise clear it.

### 4.3 `isabelle_driver.py`

`call`, the one door to the wire for a conversation — it takes the
`Conversation`, for its connection and for the log, in which it records
every round trip (LOGGING.md §5); the shield and the classification
below are one private function of a connection, which `call` is together
with the `round_trip` record — and one function per callback the
framework's ML side offers (§2.6): each knows the callback's name and the
MessagePack shape of its arguments and result, and nothing else does; the
framework's modules, and a `gen` reading over the wire, call these
functions. `theory_delete` removes vanished qualified names from the
theory table in one round trip; `check_new_theory_short_name` answers one
of `Taken(holder)`, `Reserved()` and `Free()` (§2.3), the wire's tagged
list read here and nowhere else; `check_session` answers the first
defect `Session.gen` must report, or none (§2.3), the wire's tagged list
read here likewise; `reset` cancels every job's future, empties
the state slot table and the theory table and begins a fresh Isabelle-side
log (§2.6, LOGGING.md §5) — a fresh conversation begins on the same
Isabelle process (ARCHITECTURE §9) — through the private function on a
bare connection, since it runs before any `Conversation` exists and the
Python side records it nowhere; it is the first act of every conversation
the test harness hands out, and called by nothing else: no case receives
a conversation once the Isabelle-backed part of the run has ended, and a
case that ends while a task it started is still inside a shielded round
trip is harmless, because the ML side's dispatch serves one callback at a
time. A node class's own callback (§2.5) is not here: the class calls
it itself, through `call`, from its evaluation hooks (§4.1), the shape
being between the class and its own ML half (ARCHITECTURE §6.2). `call`
raises `TAT_IsabelleError` from an exception the callback let escape, or
from a failure of the wire contract such as no callback registered under
the name — a bug either way (EXCEPTIONS.md §1). The connection going away
answers every round trip in flight with a connection error instead, not
an `IsabelleError`; that is the conversation's ending (§4.6), not a bug.
A round trip begun after the connection has gone is never answered, so a
tool body's cancellation path never starts one: the ending cancels every
body and every construction job (§4.6) and must be able to wait for them,
which is why a construction job's `_run` keeps its `try/finally` free of
round trips (CONSTRUCT_INTERACTION §3.2). `call` shields the round
trip: a callback is a two-phase exchange on the RPC connection that must
not be interrupted, so a cancellation of the caller unwinds it at once
while the round trip in flight completes on its own and its result is
dropped. Isabelle text crosses here as `IsaTerm`
(`Isabelle_RPC_Host.unicode`): a function takes it and sends `.ascii`,
and wraps the text Isabelle returns with `IsaTerm.from_isabelle`, so no
caller converts (THEOREM.md §2).

### 4.4 `plugin.py`

Imports every package in the list `launch_TAT` or `compile_TAT` received
(§2.6) — the `python_packages` the node class theories registered.
`@TAT_node` fills a process-wide registry as classes register, and
`@TAT_compile_hook` a registry of its own, `compile_hooks`, in
registration order, as module-level functions of one argument, the
forest root, register (COMPILATION.md §5); the sweep at the start of
`load` clears both registries of entries whose module is gone, and
`load` returns, in `Loaded`, this conversation's kind table — the
framework's two classes and the listed packages' — the assembled `edit`
schema from it (PLUGIN_SYSTEM §1), and the compile hooks the listed
packages define. The loader checks a hook is a plain function of one
positional argument, neither a coroutine nor a generator. The table is what `edit`
dispatches on. What the loader
checks at registration and at assembly, and how it completes the `edit`
schema, is PLUGIN_SYSTEM.md. `check_call(schema, tool, arguments)` checks
a tool call's own arguments against the schema the tool advertises — the
one object the agent is told and held to — the way `check_fields`
checks a construct's fields against its class's declaration: an argument
the schema does not name, a required one missing, a type, an `enum`, an
empty `constructs` (`minItems`), an object's fields by their names and a
typed `items`' elements by their index, the innermost at fault reported;
the constructs themselves it leaves to `edit.py`. The refusal is marked
as the call's on its way out (`RawASTError.of_tool`), which the three
shape errors render as tool and argument (RENDER_BASELINES §2). The two
checkers render in one vocabulary, the JSON types' phrases, held once.
`validate_call_schema(schema, where)` refuses, as the tools are built
(§4.6), a schema saying anything the check does not enforce or its
sentences cannot say, and one saying too little for the check to read —
an object without its `properties`, an array without its `items` — so
that the two cannot drift apart. A tool's schema comes from a closed
grammar of its own: a well-formed JSON schema that is an object carrying
`properties`, `additionalProperties: false` and a `required` within
them; a `string`, an `integer` or a `number`, each optionally with an
`enum` of one or more values of its type; a `boolean`; an `array` with
`items`, either a schema of this
grammar or the `Construct` `$ref` the check leaves to `edit.py`, and
optionally `minItems: 1`, the only count its sentence can say;
`description` anywhere, `$defs` at the top alone; and one property
declared as a bare `object`, `answer`'s `answer`, which the check reads
as "an object" until the pending question's own schema — itself within
this grammar — takes its place at call time (CONSTRUCT_INTERACTION §5).

The argument schema grammar lives here too. A declaration's annotations
come from a closed grammar — `str`, `bool`, `int`, `float`, `Any`,
`list[X]`, a TypedDict, and unions of those holding at most one
TypedDict and no arm another makes moot (`Any`, `int` beside `float`),
each field optionally wrapped in `NotRequired[X]` or
`Required[X]`, which the loader reads off the annotation itself — so every
check renders within RENDER_BASELINES §2's
vocabulary; `@TAT_node` refuses anything else when the class is
registered, as it refuses a TypedDict that nests itself and an annotation
Python cannot resolve. `check_fields` checks a submitted construct
against the declaration; `edit.py` runs it before the class's `gen`
(§4.2).

### 4.5 The plugin `Isabelle_Std`

The node classes of Isabelle's standard commands (ARCHITECTURE §2.2)
are one plugin, `Isabelle_Std`; `Session` and `Theory`, which carry the
forest's structure, are the framework's and live in `model.py`
(ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §6). The plugin's theories
and ML live under `Isabelle_Std/`. TAT's own `ROOT` declares the session
`TAT_Isabelle_Std in Isabelle_Std`, whose parent is `Minilang_AoA` and
which imports the session `Theory_Agent_over_Trees`. The parent being
`Minilang_AoA`, TAT's whole session structure requires `Minilang_AoA` to
resolve — so TAT requires Isa-Mini present, which is no loss, since the
`aoa` proof method the plugin needs lives there and TAT without it does
nothing (EVALUATOR_DESIGN §5). Its theory `TAT_Isabelle_Std` imports
`Theory_Agent_over_Trees.Theory_Agent_over_Trees` and
`Minilang_AoA.Minilang_AoA` and loads one ML file per node class from
`Isabelle_Std/ML/`; the Python half is the subpackage
`isabelle_theory_agent.std`, which the theory's registrations name
(§2.5), one module per class. A working directory takes the plugin with
`isabelle TAT_new -P TAT_Isabelle_Std.TAT_Isabelle_Std` (§5) and is
launched on the base heap `Minilang_AoA` (`-l`), so that AoA's theory is
not loaded from source at every launch; `TAT_Isabelle_Std` being on the
session search path, no `-d` is needed. The plugin declares the import
`Minilang_AoA.Minilang_AoA`, where the `aoa` method is defined, for the
forest's theories (PLUGIN_SYSTEM §1, node_classes/THEOREM.md §5).

`Theorem` is its first class, and
brings two job classes (THEOREM.md §7): `Proof_Job`, its
construction job, whose `_run` drives the AoA search and returns the
proof as the job's product, which
the framework stores on the node; and `Proof_Check`, its evaluation job,
whose `_start` forks the replay of that proof on the ML side (§2.4's
`fork_job`). The framework, not the class, posts the jobs' notifications
to the owner's or starter's mailbox (CONSTRUCT_INTERACTION §3.4) and
cancels or drops the jobs when the node is deleted or amended (§4.2).

### 4.6 `mcp.py`, `mcp_server.py`, `toplevel.py`

`mcp.py` implements the tools of MCP_SPECIFICATION §1. A tool's body
returns its text, alone or with the trailer it asks for (`With_Trailer`),
and the tool boundary in `mcp_server.py` (below) makes the result: the
body's text, then the caller's undelivered messages — `jobs.deliver`
takes the mailbox — then the trailer, made once the messages are taken
(CONSTRUCT_INTERACTION §5); the future `query` tool
(MCP_SPECIFICATION §1.1) lands here too. `tools(forest, loaded)` builds all
nine tools — `edit`, `move`, `delete` (TOOL_SCHEMAS.md), `recall`
(RECALL.md §3), `evaluate_to`, and `construct`, `cancel_construct`,
`check_construct` and `answer` (CONSTRUCT_INTERACTION §5), the last four
only when a loaded class names the job class each needs
(CONSTRUCT_INTERACTION §3.1) — through one
builder, `_tool(name, description, schema, run, read_only)`, which
validates the schema as the tool is built (`plugin.validate_call_schema`)
and checks every call against it before the entry runs
(`plugin.check_call`, §4.4), enums and `minItems` included — so no entry
can skip the check, and none retypes anything off the schema; `edit`'s
dispatches on an `action` the check let through; `answer`'s entry checks
the call once more, against the schema with the pending question's in
the bare `answer` property's place (CONSTRUCT_INTERACTION §5);
`read_only` is MCP's `readOnlyHint`, true for `recall` and
`check_construct`, which change no node and no job; the schemas
come from `tools/*.jsonc`, `edit`'s the assembled one of
`Loaded.edit_schema`, and the descriptions of `construct`, of `check_construct` and of
`evaluate_to`'s `checks` are completed at start from the loaded job
classes' titles. A forest-changing
tool's entry then holds the forest's lock across the change, the
evaluation the call asks for and the quickview, naming the refused
operation on a `TAT_Error` raised by the change (EXCEPTIONS.md §4)
through one context manager, which also yields the phrase the `Done`
line carries; the walk raises none
(ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §6). The change is `edit.py`'s
entry with its Location (ARCHITECTURE §1) resolved here, once for both
tools: `edit`'s `append`, `insert_before` and `insert_after` are `move`'s
`into`, `before` and `after`, the end of the anchor's children or the
anchor's index, one past it for `after`; for a move the index is counted
after the node's removal, so a sibling before which the node stood
loses one. Refused before the model: a leaf as an `into` anchor
(`HoldsNoChildren`), `Sessions` anywhere but as one (`ProtectedNode`,
raised by the one id resolution every forest-changing entry goes
through, which `_location` does for its anchor), and a `before`/`after`
relative to the moved node itself (`MoveBesideItself`).
`evaluate` runs the walk through `Forest._run` under the lock already
held (§4.1). The result is the `Done` line over `Forest.render(forest,
Relative_Focus(…))` with PRINT.md §5's nodes and depth. `recall`'s entry
resolves its id through `Forest.resolve`, `Sessions` included, and
answers `Forest.render(node, Recall)` alone; with no id it answers
`Forest.render(forest, Briefing)` alone, the briefing (RECALL.md §2).
`mcp_server.py` builds the server: one Streamable HTTP server on
`127.0.0.1:<port>`, one endpoint `/mcp`, a low-level `mcp.server.Server`
from the Python `mcp` SDK, listing each tool with its description, its
schema and its `readOnlyHint` (MCP_SPECIFICATION §5) — TAT's own
transport code, with no dependency on Isa-Mini; two lessons from AoA's
(`contrib/Isa-Mini/IsaMini/AoA/mcp_http_server.py`): the session manager's
lifetime stays inside one asyncio task, and — unlike that file, which
sleeps — the port is bound before anything is announced, never waited
for. The server is given the
SDK's transport security settings — the allowed host is `127.0.0.1` with
the bound port, the spelling the printed URL uses too — so a request whose `Host` or `Origin`
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
  since the SDK's responder has by then answered the client itself; only
  past the checkpoint does it take the caller's messages from its mailbox
  and attach them (CONSTRUCT_INTERACTION §3.4), so a call nobody receives
  leaves them for the next.

**The conversation's ending** is the server's one state besides serving.
It is one object, the ending object, which `toplevel.conversation()`
enters as a context right after the `Log` (below) and hands to the
`Conversation` and to the server: it holds the `Log`, the ending's
future, the `Forest` once that is built, the tasks it will cancel and
wait for, `end(exn)` and `spawn(coroutine)`; the server registers its
tool bodies through `spawn`, and a construction job's run is spawned
through it (CONSTRUCT_INTERACTION §9). The ending is entered when a
handler catches anything that is not a `TAT_Error` — a bug, a
`TAT_DisasterError`, or the connection error a dead wire answers a round
trip with (§4.3) — when a job's settlement, a `make` or `_start`, or the
`/hook` path's judgement raises anything at all, when a construction run's
`_run` raises while its run is still its job's, when a tool call arrives
that no `PreToolUse` announced (CONSTRUCT_INTERACTION §8), when the
subclass refuses a session or an agent with a `TAT_StartupError` — the
client's version or name, Codex's sandbox, an agent with no transcript
(below) — when `launch_TAT` finds the connection gone, the connection
going ending its RPC call, at the server's exit, for whatever escapes the
third layer, so that the server stops only after the ending's calls are
answered, or at the context's exit, for whatever else escapes the start
or a compile once the log exists, a `TAT_StartupError` included;
whichever door is reached first enters it, and `end` writes the `ending`
record there (LOGGING.md §4). The external manager's SIGTERM
ends the launcher and the Isabelle process with it (ARCHITECTURE §9):
under an RPC host started elsewhere it arrives through the connection's
door; the host the Isabelle process started exits with that process, and
no ending runs — the client is gone, the kernel releases the lock, the
database holds its last commit, and only the log's last records are lost.
In it `end`, in one synchronous stretch, cancels every running
construction job — the jobs found by walking the forest, no registry;
none when the `Forest` is not yet built — through its own `cancel(None)`,
drops every evaluation job without a round trip, and cancels every
working call's body and every other spawned task; each handler answers
its own call — the one that ended the conversation included — with the
line of RENDER_BASELINES §4 for what ended it, taking no lock and
touching no forest. The line is chosen by the exception's class: a
`TAT_DisasterError` and the connection gone have their own lines; a
refusal raised while serving — the `TAT_StartupError` subclass of
EXCEPTIONS.md §3, whose constructor requires its line — carries its line
itself; everything else is the internal error's line, which no refusal
can reach. The ending's
cancellation reaches a working call's handler as its own wait failing,
which the handler answers rather than passes on — a handler that passes it
on answers nobody; a call whose client has already given up stays on the
handler's checkpoint path and is answered by nobody; a tool call whose
body completed — before the ending reached it, or after ignoring its
cancellation — is answered what it did. A tool call that arrives while
the conversation is ending is answered the same message, until the server
stops accepting, which it does once the ending is entered; one arriving
after that is refused at the transport. The server then waits for every
request still in flight — the standalone stream a client holds open for
as long as it likes excepted — and for every task it cancelled, the
bodies and the construction runs, to unwind (§4.3). A round
trip a cancelled body was in finishes on its own, or fails with the
connection; either way nothing reads its result (§4.3). The forest in
memory goes with the conversation, and the database holds its last commit
(ARCHITECTURE §4.1). Then the server stops, the ending object's context
exits — writing the `ended` record once everything has unwound, so that
no caller orders it — and `launch_TAT` leaves.

`mcp_server.py` is also where
the assembled `edit` schema reaches the client (PLUGIN_SYSTEM §4): TAT
serves it as assembled, `$ref`s intact. Node classes may recurse
(PLUGIN_SYSTEM §3), so the schema has no finite inlining; serving a client
that drops references means choosing a different shape for it — a
decision to take when such a client appears, on AoA's precedent
(`contrib/Isa-Mini/IsaMini/AoA/mcp_http_server.py` serves several variants
of one `edit` schema).

The server has one path beside `/mcp`: `POST /hook`, to which the
conversation's hooks post their payloads (CLIENT_HOOKS.md §1). `TAT_Server` has
one subclass per client, `claude-code` and `codex` (CONSTRUCT_INTERACTION
§8), which implements `configure` (the client's files), `agent_of_call`
(the calling `Agent` of a tool call, from the `PreToolUse` announcement
that preceded it; the handler raises that agent's working-call count
in a `try/finally` around the body as soon as it is named, before any
lock is awaited, and lowers it when the body ends, CONSTRUCT_INTERACTION
§4), `event_of_hook` (the client's JSON into a `stop` or `compaction`
event on an `Agent`, an `interrupt` event on the set of agents the call
may stop, or nothing) and the answer's
envelope — the hook output JSON
each client documents: the announcement's `permissionDecision: allow`
on Claude Code and an empty answer on Codex, a stop's `decision: block`
with the reason, an interruption's `permissionDecision: deny` with the
reason when refused and an empty answer otherwise (`TaskStop` needs no
grant; Codex rejects a bare `allow`), a compaction's empty answer. The
hooks that keep the agents in the agent directory do not come here: a
script `configure` writes answers them without TAT (CLIENT_HOOKS.md §5).
At the
first request of an MCP session that reaches TAT, the subclass checks
the session's `clientInfo` — the `name` against the one the subclass
expects of the client `-c` chose, `claude-code` or `codex-mcp-client`,
the `version` against the one its facts were measured on — and refuses
a session that fails with a `ClientRefused` (EXCEPTIONS.md §3), which
ends the conversation (CONSTRUCT_INTERACTION §8); the launcher prints
`TAT cannot serve this client: it is <name> <version>; TAT requires
<client> <version> or newer.` The
Codex subclass also declares, in the `initialize` result, the capability
under which Codex sends the sandbox policy in force with every tool
call, and refuses a session whose policy is not TAT's profile
(CLIENT_HOOKS.md §5, CONSTRUCT_INTERACTION §8). The path reads
the payload, then, in one synchronous step under no lock, tests for the
ending and judges the event: a stop or an interruption by
CONSTRUCT_INTERACTION §7's rule, the interruption reading the agents'
working-call counts in that same step, a compaction by clearing that agent's seen
set (PRINT.md §4) and nothing more — the agent reads the briefing itself,
`recall` with no id (PRINT.md §5). On Claude Code the announcement of a call is
also where a compaction is detected. The subclass keeps, for each
transcript file it reads, how far it has read it and the
`compact_boundary` lines recorded from it; for each agent, the
`transcript_path` of its last announcement and the agent's own file
under it — the file that path and the payload's `agent_id` name; and
for each session, the `PostCompact` hooks and the boundaries not yet
matched, the second check's account (CLIENT_HOOKS.md §2). At an
announcement it reads the lines the agent's file has gained, and a
boundary not yet recorded, a `transcript_path` other than the one kept,
or the part of the file TAT had read no longer there, is the agent's
compaction event; while a `PostCompact` waits for its boundary, a task
of the ending's reads every transcript of its session. An agent whose
transcript is not found at an announcement ends the conversation with a
`TAT_StartupError` (CLIENT_HOOKS.md §2, CONSTRUCT_INTERACTION §8).
While the conversation is ending the path answers
status 503 with an empty body, touching no forest. The request is counted
among those in flight, so the conversation's ending waits for it. The
judgement runs under the tool body's rule: anything it
raises enters the conversation's ending, a `TAT_Error` included, since
this path answers no agent and has nothing to render for one; the branch
then answers status 500 with an empty body, so the hook script exits with
a code that is not a block and nothing half-rendered reaches the agent.
The path checks the request the way `/mcp` does — `Host` TAT's own,
`Origin`, when present, TAT's own — with a `TransportSecurityMiddleware`
built on the same settings object the session manager is given. Like
`recall`, it takes no lock and reads the forest as it stands
(MCP_SPECIFICATION §5).

`toplevel.py` holds the two procedures Isabelle calls: `launch_TAT`
(`@isabelle_remote_procedure("launch_TAT")`) with the package list, the
working directory, the port, the client's name and the text of
`TAT_MAX_CONCURRENT_CONSTRUCTION_JOBS` (§2.6), which does not
return — an empty text is no bound on the construction jobs running at
once, and any other that is not a positive integer is a
`TAT_StartupError`, `TAT requires TAT_MAX_CONCURRENT_CONSTRUCTION_JOBS
to be a positive integer, but it is <value>` (node_classes/THEOREM.md
§7); and `compile_TAT` with the package list and the working
directory, which returns whether every tree was written and the
report's lines (COMPILATION.md §5). The start is three layers of context
managers, the two procedures sharing the first two:

1. **`toplevel.conversation()`**, entered by both:
   - the working directory's lock, `tat.lock` (below), a working
     directory whose lock file TAT cannot open refused with a
     `TAT_StartupError`, `TAT cannot use <working directory> as its
     working directory: <strerror>`, and one another conversation or a
     compile holds with `<working directory> is held by another TAT
     conversation or compile (its Python process is pid <n>)`;
   - the log directory and its `Log` (LOGGING.md §2, §5), a directory
     that cannot be made being a `TAT_StartupError`, `TAT cannot write
     its log under <working directory>: <strerror>`;
   - the ending object (above), given the `Log`, entered as a context:
     whatever escapes from here on enters the ending at the context's
     exit before it leaves the procedure, and the exit writes `ended`
     once the ending was entered;
   - the `Conversation` (§4.1), from the connection, the working
     directory, the `Log` and the ending object;
   - the log directory's absolute path told to the Isabelle side
     (`TAT.log_directory`, §2.6), through `isabelle_driver.call` — the
     one framework callback a compile's command carries (COMPILATION.md
     §5).
2. **Entered by both:** the `Forest_Store` on `<working
   directory>/TAT.sqlite`, given the `Log` — a compile's read-only, a
   database without the store's tables read as the empty forest
   (COMPILATION.md §5); the plugins (§4.4); the `Forest`, handed to the
   ending object. Here `compile_TAT` calls `compile` with the hooks the
   `Loaded` yields and returns.
3. **`launch_TAT` alone:** the `TAT_Server` subclass the client's name
   selects makes the agent directory, `TAT.agents/`, when it is absent,
   and writes the client's files into it and the two scripts into `.tat/`
   (`configure`, CLIENT_HOOKS.md: the MCP entry, the settings, the hooks;
   the Codex subclass also looks up the real path of `/etc/resolv.conf`
   for its profile), a file it cannot write being a `TAT_StartupError`,
   `TAT cannot write <path>: <strerror>`; the server, a port that cannot
   be bound being a `TAT_StartupError` too, `TAT cannot serve on
   127.0.0.1:<port>: <strerror>`; the port line of `tat.lock`; the line `TAT is serving on
   http://127.0.0.1:<port>/mcp` printed to the Isabelle side, which
   nothing depends on and the launcher does not echo (§5); then serving
   until the conversation's ending (above), after which the layers exit in
   reverse and the lock is released.

Every file `configure` writes is written from a Python value through its
format's one encoder — JSON through `json.dumps`, TOML strings through
one function of TAT's that escapes `"`, `\` and every control character,
DEL included — and every hook command is built by one function of the
`TAT_Server` base class, which quotes each path with `shlex.quote`; no
value reaches a file by string concatenation.

**`tat.lock`** is a non-blocking exclusive `flock` on a descriptor the
procedure keeps open for its whole life, so that the kernel releases it
when the process dies and the `finally` of the first layer releases it
otherwise; `flock`, not a POSIX record lock, because only `flock`
conflicts between two open descriptors in one process, which refuses a
second conversation in this host as well as in another. The holder writes
its pid into the file when it takes the lock and, a conversation only, its
port once the server is listening, one line each, and clears the file on
release; each reader takes the line it needs and no more — the refusal
above the first, the hook script of CLIENT_HOOKS.md §1 the second and the
first, to see the holder is alive — so the refusal's parenthesis is
missing, or still names a holder that died, only between taking the lock
and writing it, and between clearing it on release and closing the
descriptor.

## 5. The launcher

`src/scala/tat.scala` defines the Isabelle tools `TAT_new`, `TAT_mcp` and
`TAT_compile` (ARCHITECTURE §9) and the Scala functions
`TAT.reserved_name` and `TAT.check_options` (§2.3), registered through
`etc/build.props` the way `contrib/Isabelle_RPC` registers its Scala
functions — the tools through `Isabelle_Scala_Tools`, the functions
through a `Scala.Functions` service; `lib/tat.jar` is
committed, and `etc/build.props` sets `no_build`, so no `isabelle`
invocation on a user's machine rebuilds it; after a change the jar is
rebuilt by removing that line, running `isabelle scala_build`, and
restoring it. The
tools run in the JVM that `isabelle` starts, like every Isabelle/Scala
tool. Every end of `TAT_mcp` and `TAT_compile` that is not a normal return
exits `2`: `Getopts` in its `internal` mode and `Build.build_logic`
with `strict = true` raise instead of exiting, the process terminating
without `TAT.finished` is an error, and `Command_Line.tool` turns each
into `2`; the one exception is an interrupt before the Isabelle process
starts and outside the base heap's build, Isabelle's own `130`.

`TAT_new [-P PLUGIN]... WORKING_DIRECTORY` takes a directory
that does not exist, is empty, or already holds a `TAT.sqlite`; any other
is refused with `<path> is not empty and is not a TAT working directory`,
a path that is a file with `<path> is not a directory`, and one whose
absolute path contains `[` or `]` with `<path> contains [ or ], which
TAT cannot use in a working directory path` — both clients read those
characters as pattern syntax in the entries that hide the directory from
the agents (CLIENT_HOOKS.md §5); `*` and `?`, which they read so too,
Isabelle's own path syntax refuses before the tool runs — each exiting
`2`. It creates the directory if it does
not exist, creates `TAT.sqlite` in it if absent, and adds one row per `-P`
to the table `plugins`, each the session-qualified name of the theory
defining the plugin; the table is always created, empty when no `-P` is
given, and a name already in it is not added twice. It writes no client
files: those are the server's `configure` at every launch (§4.6,
CLIENT_HOOKS.md), whose hook script reads the port of the running
conversation from `tat.lock`, so no file carries a port. On a directory
that already holds a `TAT.sqlite` it adds the given plugins and changes
nothing else; nothing removes a row, since the stored nodes name the
kinds a plugin owns. It records nothing else — no paths, so the directory
opens on another host. `Forest_Store` (§4.1) creates its own tables in
the same file and never reads `plugins`; the launcher never reads the
store's, and reads a file without `plugins` as no plugins.

`TAT_mcp [-c CLIENT] [-l BASE] [-p PORT] [-d DIR]... [-o OPTION]...
WORKING_DIRECTORY`, `CLIENT` one of `claude-code` (the default) and
`codex`, any other refused with `TAT knows no client <name>`, exiting
`2`, in order:

1. resolves `WORKING_DIRECTORY` to an absolute path — the path is handed
   on to the Python side, which under the `RPC_Host` order is a process
   started elsewhere (ARCHITECTURE §9) — and refuses one that is not a
   directory, with `<path> is not a directory`, or holds no `TAT.sqlite`,
   with `<path> holds no TAT.sqlite; run isabelle TAT_new first`, or
   contains `[` or `]`, with `TAT_new`'s sentence for it; each
   refusal exits `2`, as an Isabelle tool's own errors do; then reads
   `plugins`;
2. builds the Isabelle options: the defaults, the `-o` arguments in order,
   and last the two TAT sets itself, which therefore win —
   `isabelle_rpc_dialogue=absent` and `editor_tracing_messages=0`, since
   no dialogue can be answered in a headless process, and the second is
   Isabelle's own tracing limiter, which asks one; refuses
   `parallel_proofs` at 3 or above, with
   `TAT requires parallel_proofs below 3, but the options give <n>`,
   exiting `2` — the boot restores the option's value, and every load
   asserts it below 3 (§2.3);
3. the `Sessions.Background` for `BASE` over the `-d` directories, checked
   for errors — the Isabelle session layout (ARCHITECTURE §1) — and,
   before anything is built or started, the refusal of a launch whose
   layout has a session directory equal to or under the working
   directory, both as canonical paths and compared on path elements
   (`File.relative_path`), with `Isabelle session <name> is declared under
   the working directory <path>; TAT never loads theories from there`,
   exiting `2`: no theory is ever loaded from under the working directory
   (EVALUATOR_DESIGN §2), and the layout is fixed for the life of the
   process; then, under a `Console_Progress` and its interrupt handler,
   `Build.build_logic` on `BASE` — default `ISABELLE_LOGIC` — with the
   `-d` directories, `build_heap` and `strict = true`, which builds and
   stores a missing or outdated base heap first and raises when a
   session fails to build, the tool exiting `2` with Isabelle's `Failed
   to build Isabelle/<BASE>`; then `Store.session_heaps` on the background; then
   `Isabelle_Process.start`
   on those heaps with an `isabelle.Session` that echoes nothing the
   process prints — whatever ends the conversation arrives in
   `TAT.finished` — with `ML/TAT_Boot.ML` as `use_prelude` and Isabelle's own
   `Command_Line.ML_tool(List("Isabelle_Process.init_build ()"))` as
   `eval_main`; then waits for the process to be ready, reporting a failed
   start with the process's own syslog and exiting `2`;
4. sends `TAT.boot` with `TAT.start`, the working directory, the port,
   default 8191, the client's name, and the plugins' theory names;
5. waits for `TAT.finished` (§2.6) or for the Isabelle process to
   terminate, whichever comes first — meanwhile printing where the
   conversation's log is, once the protocol message `TAT.log_directory`
   names it, and each `warning` record written to it
   (LOGGING.md §7) — prints the messages `TAT.finished`
   carried, stops the process, and exits with its code: `0` when the
   conversation ended by `start` returning; `2` when an exception ended
   it — a bug, a `TAT_DisasterError`, a `TAT_StartupError`, a plugin that
   did not load, the Python side going away before `launch_TAT`
   answered, an interrupt at the terminal, whose message is `Interrupt`
   when the answer outruns the process's termination; `2` when the
   process terminated without `TAT.finished`, with
   `Isabelle process terminated:` and Isabelle's own wording of the
   return code; and `2` when `TAT.finished` arrived but could not be
   decoded, the launcher's own error, with
   `TAT.finished could not be decoded:` and the failure. The launcher prints and exits
   itself rather than letting the failure out of the tool. Once the
   Isabelle process is started, an interrupt at the terminal terminates
   it, and the conversation ends as above; before that, the interrupt is
   Isabelle's: outside `Build.build_logic` it ends the tool with `130`
   and nothing printed; inside it stops a build under way, the tool
   exiting `2` with `Failed to build Isabelle/<BASE>`, and a check that
   finds the heap in place ignores it. Earlier still, `Getopts` in its
   `internal` mode raises on an unknown option, a wrong number of
   arguments or a rejected option argument, and the tool exits `2`.

`TAT_compile [-l BASE] [-d DIR]... [-o OPTION]... WORKING_DIRECTORY`
(COMPILATION.md) shares steps 1 to 3; its step 4 sends `TAT.boot` with
`TAT.compile`, the working directory and the plugins' theory names, no
port and no client; its step 5 waits for `TAT.finished` or the
process's termination — meanwhile printing the log's path once
`TAT.log_directory` names it, and each `warning` record (LOGGING.md §7)
— prints the lines it carried — with
`progress.echo` on `0` and `1`, as errors otherwise — then, on `0` or
`1`, has Isabelle read what was written,
`Sessions.deps(structure.selection(<the working directory's sessions>)).check_errors`,
the steps `isabelle build` takes before building, and exits `2` with
Isabelle's message when they refuse it, else with the code: `0` when
every tree was written, `1` when the compile completed and some tree
was not, `2` when it did not complete (COMPILATION.md §2).

`ML/TAT_Boot.ML` is the boot: the one ML file the launcher loads before
TAT's theory exists. A `--use` file is compiled by Poly/ML's own compiler,
outside any theory, against the name space the base heap leaves behind, so
the boot is Standard ML over Isabelle's structures — no antiquotations —
and what it defines is visible to theory ML and theory ML's to it. It
defines no structure and one protocol command, `TAT.boot`. Its handler forks a plain Isabelle thread whose whole body is
captured with `Exn.capture_body`: it restores `parallel_proofs` from the
option — the `isabelle.Session`'s handshake, `Prover.options`, runs
`Isabelle_Process.init_options_interactive ()`, which sets
`Multithreading.parallel_proofs` to 3 for any positive option value; the
boot sets it back to `Options.default_int "parallel_proofs"`
(EVALUATOR_DESIGN §6) — loads `Theory_Agent_over_Trees.Theory_Agent_over_Trees`
with `Thy_Info.use_theories`, and then runs the protocol command its
first argument names, `TAT.start` or `TAT.compile` (§2.6), through
`Protocol_Command.run` with the rest; a failure before that hand-off is
answered with `TAT.finished` carrying `2` and the failure's messages. The Isabelle session layout lists every known
Isabelle session's directories, so a theory is found by its session name
wherever a registered component or a ROOT under a `-d` directory declares
that session; a heap-resident theory costs nothing to load. The handler
forks because the protocol loop reads one message at a time and a loaded
theory's `Scala.function` calls are answered through that loop.
