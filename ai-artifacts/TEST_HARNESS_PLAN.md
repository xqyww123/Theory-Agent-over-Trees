# Plan: the test harness of plan §7 step 5

Status: settled by two reviews and a re-read, implemented 2026-09-27
(§11). §1 records the owner's decisions. §2's `TAT.reset` and §1 item 6
are in the documents under `docs/` (§7), and FIRST_END_TO_END_RUN_PLAN.md
§7 step 5 gives the harness in outline and points here; §3–§6 remain the
harness's design, and §9–§11 keep the measurements, the known limits and
the record.

## 0. Scope

One pytest suite, `python -m pytest test`, holding every test of TAT: the
ones that need no Isabelle (the fake-table suite, the server and toplevel
tests, the launcher's tests), and the ones that drive a real conversation
— through the MCP tools, directly on the Python objects, or directly on
the ML callbacks, in any mix within one case. The suite replaces
`test/run_ml_framework_test.py` and `test/tat_framework_ml_test.py` (the
Isa-REPL path). The Isabelle-backed case of the tools that have landed —
`edit`, `move`, `delete` — is §6's step-5 case, through the MCP client.

Not in scope: `pytest-xdist` over the Isabelle-backed cases; the
Isabelle-backed cases of the tools not yet written (`recall`,
`evaluate_to`, `status`; FIRST_END_TO_END_RUN_PLAN.md §7's closing list),
which land with those tools and use this harness.

## 1. Decisions taken *(the owner's, 2026-09-21, 2026-09-23 and 2026-09-27)*

1. One Python RPC host, in the test process; one `isabelle TAT` per run,
   handed the host's address in `RPC_Host`; every case that needs Isabelle
   shares that process.
2. Every such case gets a fresh conversation. The ML side stays: a new
   framework callback, `TAT.reset`, empties the conversation's state slot
   table and theory table, and the Python side is rebuilt. The Isabelle
   process is not restarted.
3. The suite holds the unit tests too; a case may call Python directly,
   the ML callbacks directly, or the tools, or none of them.
4. The test plugin is `Theory_Agent_over_Trees.Test_TAT_Framework` —
   `test/Test_TAT_Framework.thy`, found through the repository `ROOT`'s
   `directories "test"` (FOREST_WALK_PLAN.md §1 item 11; a directory can
   belong to one Isabelle session only, so no session of its own under
   `test/` and no `-d`); its `TAT_test.*` callbacks are the probes the
   cases use on the ML side.
5. A case that ends the conversation makes every later Isabelle-backed
   case fail at once, naming it.
6. *(2026-09-23)* What a conversation is bound to on the Isabelle side is
   its state — the state slot table and the theory table — not the
   process: both are empty when the conversation begins and gone when it
   ends, whether because the Isabelle process went or because a fresh
   conversation began on the same process through `TAT.reset`. A theory
   loaded from source stays in `Thy_Info`, the process's cache, so a later
   conversation's import of it is answered by `Thy_Info.lookup_theory`,
   as a base-heap theory is (EVALUATOR_DESIGN §2), with the same theory
   value. ARCHITECTURE §9's paragraph on the launcher stays as it is.
7. *(2026-09-27)* Step 5's test is the approved paragraph's
   (FIRST_END_TO_END_RUN_PLAN.md §7 step 5): the tools are called through
   the `mcp` SDK's Streamable HTTP client and one tree is evaluated in
   Isabelle. The step-5 case of §6 makes one `edit` call. The
   Isabelle-backed cases of the tools not yet written land with those
   tools.
8. *(2026-09-27, after the implementation review)* Stage 2's release
   escalates: a child that outlives its `SIGINT` wait is sent `SIGTERM`,
   then, if its group is still alive after a short bound, `SIGKILL`, and
   is then waited for without a bound, so that the run always ends. The
   record names the case whose request the loop took last, saying whether
   that conversation was being begun, being served or over — in place of
   the re-read's rule naming the case last served.

## 2. `TAT.reset`

**Essence.** The Isabelle side forgets everything evaluated: a fresh
conversation begins on the same Isabelle process.

**ML.** `Slots.clear` and `Theories.clear` (each one `Synchronized.change
… (K Symtab.empty)`); `TAT.reset` joins `framework_callbacks`, which
already closes over both tables (`framework_callbacks slots theories`,
ML/TAT_Framework.ML:523), argument unit, result unit, `on_interrupt =
Reraise`. Two clears, not one record holding both tables that `reset`
replaces wholesale: the record would put an indirection on every slot
operation to guard against a third conversation-owned table, and there
is none.

**Python.** `isabelle_driver.reset(conn)`, one round trip.

**What it does not reset.** `Thy_Info` (§1 item 6): a theory an earlier
case loaded from source stays loaded. A case that tests the
load-from-source arm of EVALUATOR_DESIGN §2 therefore names a theory no
earlier case loads (the old driver's "stale REPL server" check becomes
this rule; the case asserts the theory is not yet in `Thy_Info` before it
begins, so a violation fails loudly).

**What else the conversation has on the ML side.** The framework's own
callbacks and `env` hold nothing of the conversation beyond the two
tables, and the node classes in play — `TAT_Common_Nodes` and the test
plugin — keep nothing in their registration closures. `start'` runs each
registered `make env` once (ML/TAT_Framework.ML:569-570), and under the
harness that one call spans the whole run, so a class that did keep state
there would keep it across every reset (§10).

**Who calls it.** The harness alone: `TAT.reset` is the first act of
every fresh conversation the harness hands out (§3), and no case receives
a conversation once the Isabelle-backed part of the run has ended: every
wait of the harness raises the record first (§4). A
case can end while a task it started is still inside a shielded round
trip; that is harmless, because the ML side's dispatch serves one
callback at a time. It is a framework callback, not a test-plugin one,
because `env` exposes no table wholesale and must not (PLUGIN_SYSTEM).

**Documents.** MODULE_STRUCTURE §2.1 (a sixth operation, `clear`: a fresh
conversation begins on the same Isabelle process), §2.2 (enumerated
rather than closed: `put` overwrites, `lookup` reads, `delete` removes
the names an edit made vanish, `clear` empties the table when a fresh
conversation begins), §2.6 step 3 (`TAT.reset`), §4.3 (`reset`, with the
two sentences of "Who calls it"); ARCHITECTURE §1's `conversation` row,
§9's list of endings and §9's binding sentence, and EVALUATOR_DESIGN
§1.1's lifetime sentence, reworded to §1 item 6 — "Nothing outlives the
conversation" kept; the one clause of ML/TAT_Framework.ML:8-11 likewise
(§7).

## 3. One `launch_TAT` call, several conversations

**Essence.** In production `launch_TAT` builds one conversation and serves
it until its ending. In the harness, the same building code runs once per
case, inside one `launch_TAT` call that never returns.

**The product side.** `toplevel.launch_TAT` splits into

- `toplevel.conversation(python_packages, working_directory, port,
  connection)`: an async context manager doing today's order of business
  — the lock, the store, the `Conversation`, the plugins, the `Forest`,
  the server — and yielding `(forest, loaded, server)`, `loaded` being
  the `Loaded` of `plugin.load` (its `kinds` is the conversation's kind
  table); the `Forest` is built inline, `Forest(Conversation(connection,
  directory), store, loaded.kinds)`, so no local shares the function's
  name;
- `launch_TAT` itself: its unpacking of `arg` as today, then `async with
  conversation(python_packages, working_directory, port, connection) as
  (_, _, server): await connection.writeln(...); await server.serve()`.

Behaviour unchanged; MODULE_STRUCTURE §4.6 describes the order, which the
split keeps, so no document changes.

**The harness side.** The harness is one object, built inside the
session-scoped fixture (§4). When it starts it registers its own bound
method under the wire name, `isabelle_remote_procedure("launch_TAT")
(self.launch_TAT)`. The harness is built after `test/harness.py`'s import
of `isabelle_theory_agent.toplevel` has run the product's registration
(isabelle_theory_agent/__init__.py:9), so the harness's entry replaces
it; the ML side's `Remote_Procedure_Calling.load
["isabelle_theory_agent"]` is `importlib.import_module` on a package
already in `sys.modules` (Isabelle_RPC_Host/rpc.py:545), which re-runs no
decorator, so the harness's entry stands. The procedure:

```
async def launch_TAT(self, arg, connection):
    packages, launcher_directory, port = arg       # the wire delivers a list
    assert packages == ["tat_test_plugin"], packages
    assert (launcher_directory, port) == (str(self.launcher_directory), self.port), (launcher_directory, port)
    self.launched.set_result(None)
    try:
        while True:
            request = await self.requests.get()    # a Request, or None when the suite is over
            if request is None:
                raise Suite_Over("the suite has run its last Isabelle-backed case")
            self.last_taken = request                 # what the record names (§4)
            try:
                await isabelle_driver.reset(connection)          # the first act of every fresh conversation
                async with toplevel.conversation(packages, request.working_directory, port,
                                                 connection) as (forest, loaded, server):
                    self.serving = (request, server)
                    request.handed_over.set_result(
                        Handle(self, request, forest, loaded.kinds, connection, server.url))
                    await server.serve()
            except Next:
                pass
            finally:                                              # no await here
                self.serving = None
            request.ended.set_result(None)                        # reached on the Next path only
    except BaseException as cause:
        self.end_run(cause)                                       # §4: the record of the run's end
        raise
```

One `Request` per conversation: the working directory, the case's node id
(`request.node.nodeid`), and two settlements — the hand-over, which the
fixture's setup awaits, and `ended`, which the fixture's teardown awaits.
Settlements carry only success values: the handle, and `None` on the
`Next` path; `Next` is the harness's own exception (`TAT_Server.end`
accepts any `BaseException`, and `serve` raises whatever first ended the
conversation once the server has stopped accepting and drained — nothing
is in flight at a case's end, so the drain is skipped). Every other way a
conversation or the loop ends — a cancellation (the host cancels the
procedure 3 s after its peer closed, rpc.py:360-374, wherever it is
waiting), an exception out of `toplevel.conversation` (the lock held, the
store, a plugin, the port), a `serve` that raised something other than
`Next`, a `reset` failing on a dead wire, `Suite_Over` — leaves the loop
through its outermost `try`, enters the record of §4 with the raw cause,
and propagates to the host. One cancellation does not: arriving after
`Next` was entered, it is absorbed by `serve` (mcp_server.py:178-183),
`Next` is raised and the loop returns to `get()`; the peer has closed, so
the child's exit enters the record. The `finally` clears what the harness
is serving without awaiting, so a handle has ended exactly when its
`Request` is no longer the one being served.

The assertions on `arg` pin what the launcher sent: the package list
`TAT_Framework.start'` collected and deduplicated from the test plugin's
registrations (§5), the directory `isabelle TAT` was started on, and the
port — the retired driver's first assertion, kept at the seam, for every
conversation of the run.

`Suite_Over` subclasses `Exception`, with a one-line message: the host
writes an `Exception` back to the ML side as its traceback (rpc.py:378-385)
and a `BaseException` not at all (Tools/RPC.ML:24-27); `TAT_Framework.start'`
raises the text as `error message`, `TAT.finished` carries it as code 1,
and the launcher echoes it and exits on it (MODULE_STRUCTURE §2.6).

The port is the launcher's; each conversation rebinds it (`SO_REUSEADDR`
is set).

**The working directory.** Each conversation's is the harness's choice: a
fresh temporary directory by default (the store creates the database; the
Python side reads nothing else from the directory), or a previous
conversation's, for a case that tests "the next conversation on the same
working directory starts from the database, `not_evaluated` throughout"
(ARCHITECTURE §9). The directory `isabelle TAT` is started on is a
separate one, made by `isabelle TAT_new -P
Theory_Agent_over_Trees.Test_TAT_Framework`, whose only job is to carry
the plugin list to the launcher.

**Cost.** Expected well under a second per conversation (a store open, a
server start and stop, one round trip); measured at implementation and
recorded in §9.

## 4. The harness

**One event loop.** Every Isabelle-backed case is `async def`; the
collection hook refuses any other (**Markers**). The cases share one loop
because the session-scoped harness fixture is an `async` fixture, and
anyio keeps its runner — one `asyncio.Runner`, so one loop — alive for
as long as such a fixture is alive (anyio/pytest_plugin.py:41-68,
:113-121); `anyio_backend` is overridden to session scope in
`test/conftest.py` only so that fixture may depend on it, anyio's own
being module-scoped. The harness fixture names `anyio_backend` as a
parameter, which puts it into the fixture closure of every case that uses
the harness, so anyio wraps the case's async fixtures (:128-130) and runs
the case (:172-198); no `anyio` marker is written. The invariant is held
by shape: the harness is one object built inside that fixture, and
everything shared — the host `Server`, its `run_server` task, the child
and its exit task, the request queue, the record below — is an attribute
of it; no asyncio primitive lives at module scope. Measured (2026-09-21,
anyio 4.12.1, pytest 9.0.3): a session-scoped async fixture and two async
cases see one loop; a synchronous case's own `asyncio.run` is a different
loop and disturbs the shared one not at all — but the shared loop does
not run while a synchronous case runs (a 10 ms heartbeat advanced once
during a 50 ms synchronous case); the hook therefore runs the
Isabelle-backed cases last (**Markers**, §10). `pytest-asyncio` 1.3.0 is
installed and coexists: it defaults to strict mode, the component sets
`asyncio_mode` nowhere, and each of its behavioural hooks is gated on the
`asyncio` marker or on `@pytest_asyncio.fixture`
(pytest_asyncio/plugin.py:598-611, :659-661, :722-727).

**The record of the end of the Isabelle-backed part of the run.** The
harness holds one future on the shared loop whose result — never its
exception — is what ended the Isabelle-backed part of the run, and one
non-awaiting method, `end_run(cause)`, that enters it: the first entry
wins, as `TAT_Server.end`'s does (mcp_server.py:185-191). For
`Suite_Over` it records `Suite_Over` itself. For any other cause it
records one harness exception, `Run_Ended`, an `Exception` subclass in
`test/harness.py` with the cause as `__cause__`, carrying the child's
output and naming the case whose request the loop took last, saying
whether that conversation was still being begun (the hand-over not yet
made), being served (`ended` not yet set) or over (between
conversations); it also
ends the conversation being served with that exception (**The
conversation the harness is serving**) and sends `SIGINT` to the child's
process group, a group already gone being no error: the run has failed,
and signalling the process is the only way to stop a running ML callback
(`isabelle_driver.call` shields the round trip, nothing on the wire
carries a cancel from Python to Isabelle, and the callbacks are
registered with `timeout = NONE`). Four callers enter the record:

- the procedure's outermost `try` (§3), which re-raises the raw cause to
  the host;
- a done-callback on the child's exit task, attached at startup and kept
  for the whole run;
- a done-callback on the `run_server` task, attached the same way,
  entering only when the task ended with an exception and was not
  cancelled — so a bind failure is reported as itself, "the host could
  not bind port N", not as a child that could not connect;
- the deadline helper below.

Both watched tasks are plain asyncio tasks held on the harness. The
done-callbacks retrieve the outcome and never raise: an exception raised
in a done-callback reaches anyio's loop exception handler and is
re-raised against whatever step runs next
(anyio/_backends/_asyncio.py:2197-2214). No anyio task group and no other
cancel scope is entered in the session fixture's setup and left in its
teardown (§10).

**One wait helper.** The only way the harness waits for a settlement:
`asyncio.wait({awaited, record}, return_when=FIRST_COMPLETED)`. When the
record holds `Run_Ended`, the helper raises it, before it looks at what
was awaited; otherwise the awaited settlement is done — the record holds
`Suite_Over` only after the last case — and the helper returns its
result, never awaiting the future itself: a `fail_after` around a direct
`await` cancels the future being awaited, after which the loop's
`set_result` raises `InvalidStateError` (measured 2026-09-23; the product
relies on the same distinction, mcp_server.py:281-287). It serves the
setup's hand-over, the teardown's wait on `ended`, `restart()`'s two
waits, and the startup's wait for the harness's `launch_TAT` to be
called. The session teardown's waits for the child — stage 3's release
after `Suite_Over`, stage 2's release — are not settlements: they wait on
the child's exit task alone, `asyncio.wait({exit})` under the deadline,
whatever the record holds, since after `Run_Ended` the helper would raise
at once and the child would be neither waited for nor checked. So no raw
`CancelledError` ever reaches anyio's runner (which a settlement carrying
one would end for the rest of the run,
anyio/_backends/_asyncio.py:2228-2233), and no settlement is cancelled or
completed twice.

**One deadline helper.** Every deadline goes through one context manager
on the harness, wrapping `anyio.move_on_after(D)`: when the scope's own
deadline cancelled the block (`scope.cancelled_caught`), the helper enters
one `TimeoutError` naming what expired into the record through `end_run`
and raises that same instance. It bounds the case body (**Markers**), the
fixture's hand-over wait and its `ended` wait, and the session teardown's
waits; the startup's wait for `launch_TAT` reports an expiry as the
record instead, so that the child's output is shown. An expiry ends the
Isabelle-backed part of the run exactly as the child dying does (§1 item
5): the record names the case, no further conversation is handed out,
the child is signalled. Not a cancel scope spanning a fixture's `yield`:
anyio's runner drives every fixture half and every test body through one
persistent task, and a cancellation crossing that boundary ends the task,
after which every later case and the session fixture's teardown fail with
`ClosedResourceError` (§10).

**The conversation the harness is serving.** The harness records the
conversation it is serving — its `Request` and its server — set at the
hand-over and cleared in the loop's non-awaiting `finally` (§3). One
synchronous operation, `end_conversation(exn)`, ends it through that
server's `end` (first ending wins, mcp_server.py:189-190) and returns its
`Request`; it does nothing, and returns `None`, when no conversation is
being served. Its callers: `end_run`, with `Run_Ended`; and one async
operation, `await_ending()`, with `Next()` — which raises the record when
nothing is being served, and otherwise waits on the returned request's
`ended` through the wait helper under the deadline. `await_ending()` is
the fixture's teardown and the first half of `restart()`.

**Startup, lazily.** The session-scoped fixture starts nothing until the
first Isabelle-backed case asks for it; `python -m pytest test -m "not
isabelle"` never starts Isabelle. When asked, it enters three stages on
one `contextlib.AsyncExitStack`, registering each stage's release as the
stage succeeds, so a startup that fails runs only the releases of the
stages it entered and its own error, with the child's output, stays the
reported error:

1. a free port for the host; `Isabelle_RPC_Host.Server(addr, logger)` with
   the suite's own logger (not `mk_logger_`, which reconfigures the root
   logger and would break pytest's log capture), `run_server()` as a task
   on the shared loop with its done-callback; the harness registers its
   `launch_TAT` (§3). Release: the `Server`'s own context manager, which
   stops it; nothing awaits or inspects the task afterwards (a stopped
   server ends it cancelled).
2. a temporary directory, `isabelle TAT_new -P
   Theory_Agent_over_Trees.Test_TAT_Framework` on it; `isabelle TAT -p
   <free port> <directory>` with `RPC_Host` in its environment, in its
   own session (`start_new_session=True`, `SIGINT` at default), stdout and
   stderr to one log; the child's exit as a task with its done-callback.
   The base heap is the launcher's default, the product path (measured
   2026-09-21: 11.6 s to a connected client on `HOL` against 8.4 s on
   `Isabelle_RPC`). No `PYTHONPATH`: with `RPC_Host` set the ML side only
   connects and launches no interpreter, and every import happens in the
   pytest process, where `test/` is on `sys.path` by pytest's
   conftest-directory insertion (as `test_mcp_server.py`'s `from
   baselines import DOCS` already relies on). Release: if the child is
   still alive, `SIGINT` to what remains of its process group (a group
   already gone is no error) and wait for its exit under the deadline; a
   child that outlives the wait is sent `SIGTERM` — the JVM's shutdown
   hook then runs Isabelle's own termination of the ML process's group —
   and, if its group is still alive after a short bound, `SIGKILL`, then
   waited for without a bound, so that the run always ends, the expiry
   being the report; assert that no process is left in the group.
3. wait, through the wait helper under the deadline, for the harness's
   `launch_TAT` to be called — the child's exit and a `run_server` failure
   reach the record and so end this wait as themselves. The deadline is
   generous, since the first run on a machine may build the base heap.
   Release: the run's end through the product's ending chain, below.

**Teardown.** The releases in reverse order. Stage 3's: it raises the
record when it holds `Run_Ended`; otherwise `None` on the request queue,
so `launch_TAT` raises `Suite_Over` (§3), which the record then holds; it
waits on the child's exit task under the deadline, raises the record if
it holds `Run_Ended` by then, and asserts exit code 1 and that the
child's log contains the line `"*** " +
traceback.format_exception_only(over)[-1].rstrip("\n")`, `over` the
recorded `Suite_Over` — the exception line of the traceback the host
wrote back. Stage 2's release then signals a child still alive — the
fallback for a `Suite_Over` ending that did not finish within the
deadline, and the normal course after `Run_Ended`, whose `end_run`
already sent `SIGINT` — waits for it, escalating as above, and asserts
that no process is left in the group. Stage 1's, the `Server`'s own
context manager, stops the host.

**The case-scoped fixture `conversation`.** For each Isabelle-backed case:
check the record and fail at once with `Run_Ended` if it holds one; put a
`Request` with a fresh temporary directory and the case's node id on the
queue; await its hand-over through the wait helper under the deadline;
yield the handle. At teardown: `await_ending()` — when nothing is being
served, the conversation already ended by another path, whose `end_run`
ran in the step that cleared it, and the recorded `Run_Ended` is raised —
so the teardown of a case whose conversation ended for any reason but
`Next` fails with `Run_Ended`. What the case gets:

| attribute | what it is |
| --- | --- |
| `forest` | the `Forest`, for cases on the Python objects |
| `kinds` | the conversation's kind table (PLUGIN_SYSTEM §1), what `edit.insert` and `edit.amend` take |
| `connection` | the RPC `Connection`, which the model objects take (`Isar_State_Slot.assign`); a case reaches the ML callbacks through `isabelle_driver.call` |
| `url` | the MCP endpoint |
| `client()` | an async context manager yielding an initialised `mcp.ClientSession` on `url` — `test_mcp_server.py`'s `client(url)` helper, moved where both can import it |
| `working_directory` | the conversation's |
| `restart()` | checks that this handle is the one being served; `await_ending()` — `ended` is set only after the directory's `flock` is released; requests the next conversation on the same working directory and returns its handle |

A handle has ended exactly when its `Request` is no longer the one being
served; no flag is kept. Every attribute of an ended handle, `restart`
included, raises on access: the recorded `Run_Ended` itself after the end
of the Isabelle-backed part of the run, else a sentence naming the handle
`restart()` returned. `server` belongs to the harness and is not on the
handle.

**Markers.** `pytest_configure` registers `isabelle`; a `tryfirst`
`pytest_collection_modifyitems` marks every item whose `fixturenames`
closure contains the session-scoped harness fixture — not only
`conversation`, so a case taking the harness fixture alone (the
measurement of a fresh conversation's cost, §8 step 4) is covered —
refuses, naming the item, an `isabelle`-marked item whose closure lacks
the harness and an `isabelle` item whose original `obj` is not a
coroutine function,
replaces each `isabelle` item's `obj` by a `functools.wraps`'d `async`
wrapper that runs the original under the deadline helper (`D`
overridable by an argument on the marker; the wrapper reaches the harness
through the item's `funcargs`, which pytest fills for the whole fixture
closure before the call, _pytest/fixtures.py:707), and stable-sorts
`items` so that the `isabelle` ones come last. So an Isabelle-backed case
cannot exist without a deadline, and no development dependency is needed.
The hook runs before the builtin mark plugin's `deselect_by_mark`
(_pytest/mark/__init__.py:282-284; conftest plugins register later), so
`-m "not isabelle"` sees the derived marker. `test/test_launcher.py`
keeps its own `skipif` and is deliberately unmarked: it needs the binary,
not the shared Isabelle process.

**The ending guard.** `test/conftest.py`'s autouse
`no_uvicorn_error_is_logged` reads the teardown phase as well as the call
phase: under the harness a conversation's ending happens in the
`conversation` fixture's teardown, and an autouse fixture's tail sees the
records a later-set-up fixture's teardown logged (measured 2026-09-23,
pytest 9.0.3, `caplog.get_records("teardown")`).

## 5. The test plugin

- `test/Test_TAT_Framework.thy` imports `Theory_Agent_over_Trees.
  Theory_Agent_over_Trees` by name, as a plugin does, and is found the way
  a plugin is: `Loader.fetch_named` on the name the launcher was given,
  through the repository `ROOT`'s `directories "test"` (§1 item 4). It
  keeps its `TAT_test.*` registrations, with `TAT_test.clear` renamed
  `TAT_test.delete` (the framework's word for removing a slot is `delete`,
  `Slots.delete` and `TAT.state_delete`; `clear` empties a table, §2;
  `reset` is the conversation-level operation), keeps the two load-time
  checks (a duplicated callback name, `parallel_proofs` at 3), and drops
  the last two lines — `Remote_Procedure_Calling.load` and the `start'`
  call — since the launcher starts the conversation. A load-time check
  that fails aborts the boot with its message, which the session-scoped
  fixture reports. Its registrations keep no state in their closures
  (§2).
- Its `python_packages` name `tat_test_plugin`, a package under `test/`
  with no node class (importable in the test process because pytest puts
  `test/` on `sys.path`); the registrations still name it twice, and the
  deduplication of MODULE_STRUCTURE §2.6 is pinned by §3's assertion on
  the launcher's argument.
- `test/TAT_Lib_Helper.thy` stays as the load-from-source material,
  imported as `Theory_Agent_over_Trees.TAT_Lib_Helper`, which
  `Resources.find_theory_file` resolves through the same `directories
  "test"`.

## 6. The cases

- `test/test_conversation.py` (new, replaces `tat_framework_ml_test.py`):
  the old driver's blocks, one case per topic instead of one drive —
  state slots through the probes; the theory pipeline (begin, run,
  records, output routing, the five output kinds; `sorry` under `declare
  [[quick_and_dirty = true]]` and under `declare [[quick_and_dirty =
  false]]`, each run declaring its own value since `isabelle TAT` leaves
  the option off, the second pinning the interactive flag of
  `Toplevel.command_errors` — ported with the moved comment rewritten and
  the first run's record count 2 → 3, the `declare` being a command of
  its own; empty text; a failing command; a failed fork
  and a succeeding one, the second being the control; `end` and the
  theory table — a second tree's import resolving to the first through
  the conversation's table, the overwrite, and, once that import has
  resolved, a bare name from another Isabelle session refused); output
  isolation under `run_parallel`; the loader's arms (the base heap; load
  from source by session-qualified name, on `TAT_Lib_Helper`; a bare
  import with no file, a qualified import in no Isabelle session, a path,
  a global theory written session-qualified — each refused; a rejected
  header); spans parsing against the state they run in;
  `TAT_Common_Nodes.operation`'s outcomes; `check_new_theory_short_name`'s
  three answers; an exception escaping a callback; the Theory node class
  end to end against real Isabelle, on the handle's `forest` and `kinds`
  (its imports are by name, so nothing depends on the working directory)
  and patching `isabelle_driver.theory_delete` through pytest's
  `monkeypatch` (`forest.id_of`, the short-name check in `gen` over the
  wire, an empty theory to its end and its three slots, a second tree
  importing the first, a failing header as the node's own stop, a tree
  deleted — its slots released, its importer `not_evaluated` whole, one
  `theory_delete` round trip — and a `Session` deleted whole). Every
  `TAT_test.*` probe goes through `isabelle_driver.call`; a negative
  assertion catches `TAT_IsabelleError`, whose message embeds the ML text,
  or, where the old driver asserted on the raw library exception, its
  `__cause__`. The refusal sentence is read from RENDER_BASELINES §3
  through `test/baselines.py`, with an unpacking that fails if §3 gains or
  loses a fenced line; the `TAT_Nowhere.Nope` case asserts that line
  verbatim, and every other name's sentence is derived from it by
  substituting the name, the failing-header check of the Theory node
  class block included.
- The step-5 case (§1 item 7), in the file above: through the handle's
  `client()`, one `edit` call appending a `session` construct holding one
  `theory`, with `evaluate: true`; the `Done` line and the theory's
  `success` mark asserted; then the restore case: after `restart()` the
  new handle's forest, rebuilt from the store, holds the tree,
  `not_evaluated` throughout, and evaluates it again. Evaluating a lemma
  end to end waits for `Theorem`.
- The reset case, in the file above, asks the same questions before the
  restart and after it. In the first conversation, which evaluated a
  tree: each slot name the case keeps answers `state_exists` true, and an
  importer of the tree's theory, begun through the `TAT_test.begin` probe
  into a fresh slot under the tree's Isabelle session name, succeeds —
  through the probe, because the restored forest would evaluate the
  import first. After `restart()`: the same names answer false, and the
  same probe call fails with RENDER_BASELINES §3's sentence. The names are
  the first conversation's: a fresh conversation's own slots are fresh
  names whether or not `TAT.reset` ran, since `Isar_State_Slot._counter`
  never restarts.
- `test_isabelle_driver.py`'s guard `test_call_is_the_one_door_to_the_wire`
  widens its scan to `test/`, allowing `isabelle_driver.py` and its own
  file: the cases reach the wire through the shielded door only, and the
  suite polices that as it does for the product. The widening lands in
  the edit that deletes the retired driver (§8 step 5), which calls
  `connection.callback` directly.
- Kept as they are: every present file; `test_mcp_server.py`'s ending
  cases stay the only tests of the ending (a case that ends its
  conversation would end the Isabelle-backed part of the run).
- Retired: `test/run_ml_framework_test.py`, `test/tat_framework_ml_test.py`.

## 7. Files

| file | change |
| --- | --- |
| `ML/TAT_Framework.ML` | `Slots.clear`, `Theories.clear`, `TAT.reset`; the header's clause (§2) |
| `isabelle_theory_agent/isabelle_driver.py` | `reset` |
| `isabelle_theory_agent/toplevel.py` | `conversation(python_packages, working_directory, port, connection)` split out of `launch_TAT`, yielding the `Loaded` too |
| `test/conftest.py` | `anyio_backend`, `pytest_configure`, the collection hook (the marker, the coroutine check, the deadline wrapper, the order), the session-scoped and the case-scoped fixtures, the ending guard's teardown phase |
| `test/harness.py` | the harness object: the record and `end_run`, the wait helper, the deadline helper, `end_conversation`, `launch_TAT`, `Request`, `Handle`, `Next`, `Suite_Over`, `Run_Ended`; the `client(url)` helper moved from `test_mcp_server.py` |
| `test/Test_TAT_Framework.thy`, `test/tat_test_plugin/` | the test plugin (§5) |
| `test/test_conversation.py` | the cases (§6) |
| `test/test_isabelle_driver.py` | the guard's scan widened (§6) |
| `test/run_ml_framework_test.py`, `test/tat_framework_ml_test.py` | deleted, by moving (§8) |
| `docs/MODULE_STRUCTURE.md` | §1 (:39-40 names the theories themselves, `TAT_Lib_Helper` and the test plugin, not the test file), §2.1, §2.2, §2.6, §4.3 (§2) |
| `docs/ARCHITECTURE.md` | §1's `conversation` row (both ends: a conversation begins with Isabelle's call into Python, or, within that call, when `TAT.reset` begins a fresh conversation on the same Isabelle process; it can also end when its host ends it to begin a fresh one), §9's list of endings (:593-596), §9's binding sentence (:598-601) — each transcribed from §1 item 6 |
| `docs/EVALUATOR_DESIGN.md` | §1.1's lifetime sentence (§1 item 6) |
| `docs/EXCEPTIONS.md` | §3's list of homes (:222): `test_conversation.py` in place of `tat_framework_ml_test.py` |
| `ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md` | §7 step 5's test paragraph: the host in the test process, one `isabelle TAT` per run, a fresh conversation per case through `TAT.reset`, the tools called through the `mcp` SDK's Streamable HTTP client kept; the standing rule (:371) names the Isabelle-backed cases of `python -m pytest test`, keeping the record that steps 1–4 ran the script |
| `ai-artifacts/STEP5_HANDOFF.md` | the harness done, the retired files |

## 8. Order of work

1. `TAT.reset` and `isabelle_driver.reset`; restart nothing — the ML side
   is exercised by the suite once it exists.
2. `toplevel.conversation`; `test_toplevel.py` unchanged and passing.
3. The test plugin (§5); `isabelle TAT` by hand on a `TAT_new -P
   Theory_Agent_over_Trees.Test_TAT_Framework` directory, with
   `ISABELLE_RPC_PYTHON` naming the virtualenv's interpreter and
   `PYTHONPATH=test` — that run has `RPC_Host` unset, so Isabelle spawns
   the host itself and that host must import `tat_test_plugin`. The
   checkpoint: the plugin theory found and loaded, the conversation up,
   and `TAT_Lib_Helper` loaded from source through the `edit` tool (a
   theory importing `Theory_Agent_over_Trees.TAT_Lib_Helper`).
4. The harness (§4) with one trivial case; the cost of a fresh
   conversation measured.
5. The cases (§6), ported by moving: each block cut out of
   `test/tat_framework_ml_test.py` in the same edit that adds the case
   carrying it, so the file shrinks as `test_conversation.py` fills. The
   last edit deletes the retired files, updates every remaining mention
   of them (§7) and widens the door guard (§6); its check is
   `/usr/bin/grep -rnI -e tat_framework_ml_test -e run_ml_framework_test`
   over the component finding only the implementation records
   (FOREST_WALK_PLAN.md, FIRST_END_TO_END_RUN_PLAN.md's step records,
   STEP5_HANDOFF.md, this plan) — `/usr/bin/grep`, because the default
   grep honours `.gitignore`.
6. Documents (§7); review of the whole; commit on the owner's word.

## 9. Measurements

- `isabelle TAT` to a connected client, 2026-09-21: 8.4 s on
  `Isabelle_RPC`, 11.6 s on `HOL`; `SIGINT` to exit, 1.5 s, no leftover.
- One event loop across the run: §4.
- The ending guard sees the teardown phase: §4.
- A `fail_after` around a direct `await` cancels the awaited future;
  around `asyncio.wait` it does not: §4.
- A fresh conversation through `restart()` — the ending, `TAT.reset`, the
  next conversation built and handed over — 2026-09-27: 0.22 s. The two
  first cases, `isabelle TAT`'s start included: 12.9 s.
- A deadline expiring during an ML callback, 2026-09-27 (a probe, not a
  case; repeated after the implementation review's changes): the case
  fails with `TimeoutError` naming what expired, its teardown and the
  next case's setup with `Run_Ended` saying "during" that case and
  showing the child's output (`*** Interrupt`), the child is signalled
  and gone, nothing left in its group; 17 s in all.
- Stage 2's escalation, 2026-09-27, against a stand-in child ignoring
  `SIGINT` and `SIGTERM` (`DEADLINE` 3 s, `TERMINATION` 2 s): the child
  killed, the exit task done, the group gone, the expiry reported after
  5.0 s.
- The whole suite, `python -m pytest test`, 2026-09-27: 306 cases in
  39 s — 281 needing no Isabelle, the launcher's 6, and 19 Isabelle-backed
  cases on one `isabelle TAT`, whose start is the larger part of their
  18 s.

## 10. Known limits

- Under `--ff` or `--nf`, which reorder the items after the conftest
  hook, a synchronous case can run while the harness is alive; the shared
  loop is idle meanwhile (§4).
- `Thy_Info`, and anything a node class keeps in its own registration
  closure, accumulate across cases (§2).
- A deadline's expiry, like the child's death, ends the Isabelle-backed
  part of the run: a running ML callback can be stopped only by a signal
  to the process (§4).
- A cancel scope, a task group's included (a failing child cancels it),
  spanning the fixture/body boundary kills anyio's shared runner for the
  rest of the run; the deadline is installed inside the case's own
  coroutine, and the harness's background work is plain asyncio tasks,
  for that reason (§4).
- A case that ends its conversation ends the Isabelle-backed part of the
  run; the ending is tested only in `test_mcp_server.py`.
- The Isabelle-backed cases cannot run under `pytest-xdist`.
- The suite never exercises Isabelle's launch of an ephemeral host, nor
  an import into it: with `RPC_Host` set the ML side only connects. The
  retired driver exercised both on every run, under an interpreter and a
  path it supplied itself (`ISABELLE_RPC_PYTHON`, `PYTHONPATH`), never
  under the interpreter the RPC layer picks; that automated coverage is
  given up. §8 step 3 repeats that run once, by hand; `isabelle TAT` at a
  terminal exercises it under the interpreter the RPC layer picks.

## 11. Record

- **First review, 2026-09-21** (the forked session's scratchpad
  `harness_review/ruling.json`): READY_WITH_FIXES. Its blocking item —
  `Forest._evaluate` unimplemented, so no case could build or evaluate a
  tree on the conversation's forest — was settled by landing the forest
  walk first (FOREST_WALK_PLAN.md, commit `84a6868`). Its owner item —
  ARCHITECTURE §9's binding of a conversation to its process against
  `TAT.reset` — is §1 item 6 (approved 2026-09-23). Its author items are
  in the sections above, three of them in the form the second review
  ruled (below): the two settlements of every conversation and the single
  `reset` call site (§3); the loop's end through the product's ending
  chain, the `run_server` task watched, the deadline as a collection-hook
  wrapper and its expiry as a fatal path, the derived `isabelle` marker,
  the ending guard's teardown phase, no `Connection.callback` on the
  handle, `restart()` returning a new handle and awaiting `ended` first,
  the one-loop mechanism and the settled confirmations (§4);
  `TAT_test.delete`, the closures' statelessness and the assertion pinning
  the package list (§5); the three added clauses, porting by moving, the
  reset case's slot names and the widened guard (§6); `PYTHONPATH` moved
  from §4 to §8 step 3, which also exercises the load-from-source arm
  (§8); §2.2 enumerated (§2). Rejected there, not to be re-raised: a
  forest-class parameter on `toplevel.conversation`; a heap probe or a
  pre-flight build before `isabelle TAT` (the launcher may build the base
  heap, STEP5_HANDOFF.md); a second `isabelle TAT` child for the boot
  path; copying a `TAT_new` template into every case; renaming
  `conversation` or `launch_TAT`; a polling-latency figure in place of §9's
  measurement.
- **The forest walk's landing, 2026-09-23** (FOREST_WALK_PLAN.md §10):
  §1 item 4 replaced (`Theory_Agent_over_Trees.Test_TAT_Framework`, no
  `test/ROOT`, no `-d`), `test/routing_forest.py` and
  `test/lib/TAT_Lib_Rel.thy` gone, `TAT_Lib_Helper` imported by its
  session-qualified name, and the ML driver's two instalments of that step
  — the loader's arms and the Theory node class end to end — added to §6.
- **Second review, 2026-09-23** (this session's scratchpad
  `harness_review2/ruling2.json`, 37 findings): READY_WITH_FIXES. Its
  owner item — the tools' Isabelle-backed case had no home, their step
  having committed — is §1 item 7 (approved 2026-09-27). Its author items
  are in the sections above: the record of the end of the Isabelle-backed
  part of the run, its four callers, the one wait helper and the one
  deadline helper, the conversation the harness is serving and
  `end_conversation`, `TAT.reset` as the first act of every fresh
  conversation inside the request's `try` — the applied form of the first
  review's "a deadline that fires leaves the ML side running" — the
  handle without a flag, `Suite_Over` an `Exception` and the echoed line
  derived from it, the staged startup on an `AsyncExitStack`, the
  `run_server` task's done-callback in place of the teardown inspection
  (amending the first review's inspection clause), the coroutine check in
  place of the `anyio` marker and the `anyio_backend` closure check
  (amending the anyio clause of the first review's marker item), the
  Isabelle-backed cases run last, the procedure registered as the
  harness's bound method, `toplevel.conversation` taking the parts and
  yielding the `Loaded`, the handle's `kinds`, the launcher's argument
  unpacked before it is asserted, the glossary's `conversation` row and
  §9's list of endings among ARCHITECTURE's places (§2, §7), and the
  terminology fixes (§3, §4); the step-5 tree without a
  lemma, the reset case's positive controls, the cross-session refusal
  under the theory-table clause, `sorry` declaring `quick_and_dirty`
  itself, the refusal sentence read from the document, the Theory node
  class block on the handle's forest with `monkeypatch`, the guard widened
  in the deleting edit (§6); the further homes of the retired driver's
  name and the grep check (§7, §8); §10's last bullet as the first review
  ruled, and the `--ff`/`--nf` and task-group bullets (§10). Rejected
  there, not to be re-raised: that the process-group check cannot see the
  ML process (the `bash_process` parent stays in the group); that §1 item
  6's `Thy_Info` sentence has no home (§7 sends it to ARCHITECTURE §9).
- **The re-read, 2026-09-27** (`harness_review2/reread.md`):
  PASS_WITH_EDITS, eight edits, all in: the session teardown's waits for
  the child taken off the wait helper and put on the child's exit task
  alone; the fixture's teardown when `end_conversation` returns `None`; the
  dead `ended_by_next` line; the deadline helper's signature; three
  wordings; the two narrow windows stated (§2, §3); the `sorry` porting
  note and the record's omissions.
- **Implementation, 2026-09-27**, in §8's order. Step 1: `Slots.clear`,
  `Theories.clear`, `TAT.reset` (`arg_schema = unpackUnit`, Python sends
  `None`), `isabelle_driver.reset`, the ML header's clause. Step 2:
  `toplevel.conversation`, the `Forest` built inline; `test_toplevel.py`
  unchanged. Step 3: the test plugin as §5 (`TAT_test.delete`, the package
  `tat_test_plugin`, the last two lines dropped); the by-hand run passed
  its checkpoint — the plugin found by name, the ephemeral host importing
  `tat_test_plugin` under `PYTHONPATH=test`, `TAT_Lib_Helper` loaded from
  source through `edit`. Step 4: `test/harness.py` and `test/conftest.py`
  as §3 and §4, with two details the plan left open: `Run_Ended` renders
  the child's output when it is printed, not when it is entered (the
  launcher writes nothing until it ends); all three stage releases are
  `async`, so that `AsyncExitStack.callback` — a `.callback(` the widened
  door guard would flag — is not needed. The first two cases and the
  fatal-path probe: §9. Step 5: the driver's blocks ported into
  `test/test_conversation.py`, 19 cases; the cross-session refusal under
  the theory-table case; `sorry` declaring its own value; the refusal
  sentence from RENDER_BASELINES §3; the retired files deleted in the edit
  that widened the door guard (the guard now scans `test/` too, allowing
  the door and itself) and corrected the remaining mentions (EXCEPTIONS.md
  §3, MODULE_STRUCTURE §1, FIRST_END_TO_END §7's rule and step-5
  paragraph, two test docstrings); the grep check finds only the
  implementation records. Step 6: the documents of §7, except
  `ai-artifacts/STEP5_HANDOFF.md`, which carries another session's
  uncommitted text and is left to the owner. The whole suite: §9.
- **Implementation review, 2026-09-27** (`harness_review2/ruling_impl.json`,
  28 findings): READY_WITH_FIXES. Its owner item — a child outliving stage
  2's `SIGINT` wait left the run hanging on the thread in `Popen.wait` —
  and its offered relaxation of the record's naming are §1 item 8. Its
  author items, all made: the record's timing text from the request the
  loop took last (`last_taken`; `handed_over` and `ended` tell the three
  cases); the deadline helper on `anyio.move_on_after`, entering and
  raising one `TimeoutError`, and the startup's expiry reported as the
  record; `signal_child` returning when there is no child; one
  `raise_if_ended()` raising the recorded `Run_Ended` with a fresh
  traceback, used at every site (the wait helper, `converse`,
  `release_run` before and after its wait, `await_ending`, the startup's
  expiry, the handle's guard — which raises the record itself, and a
  sentence naming the successor otherwise; `why_ended` gone);
  `release_run` raising the record first and deriving the echoed line from
  the recorded `Suite_Over` (the `suite_over` attribute gone); stage 1
  released by the `Server`'s own context manager, stages 1 and 2 started by
  harness methods (`start_host`, `start_child`, `await_launch`), so
  `conftest.py` reads as three starts each followed by its release;
  `TAT_new` without `capture_output`; `_child_done` silent on a
  cancellation; `await_ending()` as the one ending wait (the fixture's
  teardown, and the first half of `restart()`; `Next`'s docstring names
  it); the door guard comparing the ordered list, one line per file;
  `text_of` moved to `harness.py` beside `client` and `free_port`
  (`test_launcher.py` imports `free_port` from there); a hand-written
  `isabelle` marker on a case outside the harness refused at collection;
  the marker's description; the first case's docstring saying what it
  pins (the hand-over); the reset case's docstring without the false
  reason (the case begins and ends its first theory through the probes,
  not through a forest tree); `TAT_Lib_Helper.thy` naming no test;
  `toplevel.conversation`'s docstring and MODULE_STRUCTURE §4.6 stating the
  order the code runs (the plugins before the `Conversation`, since the
  `Forest` is built inline); MODULE_STRUCTURE §4.3 carrying the two
  sentences of §2; this plan's status line, §4 and §11. Rejected there,
  not to be re-raised: the handle's `__dict__` spelling and its
  `**fields: Any` surface; the fake-backed builders imported into the
  Isabelle-backed module; the wait helper taking the deadline itself; and,
  rebuked, that `Probes` caching the raw connection escapes the handle's
  guard (the connection is the run's, not a conversation's). The suite
  and the two probes after the changes: §9.
