# Hand-off within plan §7 step 5 (updated 2026-09-21)

Where things stand: the ML and Scala halves of step 5 are committed
(`fd4a42e`, `0508b71`), and so is the Python half but for the tools
(2026-09-21, after review rounds 11–13): `plugin.py`'s registry split, the
shield in `isabelle_driver.call`, `mcp_server.py`, `toplevel.launch_TAT`,
the dependencies. `mcp.py` holds the seam only (`tools` returns `[]`): the
tools wait on their own design, which the owner deferred to when they are
written; the rendering their results end with is PRINT.md (decided
2026-09-21). The design is MODULE_STRUCTURE §2.6, §5 and §4.3–§4.6,
ARCHITECTURE §9, EVALUATOR_DESIGN §6, PLUGIN_SYSTEM §1, plan §7 step 5.

## Owner's standing permissions for this work

- `isabelle TAT` may be run at will (it may build a base heap).
- `isabelle scala_build` may be run at will, for this component (the
  rebuild procedure is in `etc/build.props`' comment and MODULE_STRUCTURE
  §5).
- `isabelle build` stays forbidden except `repl_server.sh`.
- Test framework: the author's call (plan §7 step 5 names the shape).
- TAT is registered as an Isabelle component on this host.

## Done (do not redo)

1. ML: `ML/TAT_Boot.ML` (`TAT.boot`); `TAT.start` in `TAT_Framework.ML`;
   `start` taking theories, working directory, port; `Loader.fetch` /
   `fetch_named`; `check_parallel_proofs` below 3 in every load; both
   emitters render `Interrupt` and fall back to `CRASHED`.
2. Scala: `src/scala/tat.scala` (`TAT_new`, `TAT`), `etc/build.props`
   (`no_build`), `lib/tat.jar`, `etc/settings`.
3. Python:
   - `plugin.py`: one process-wide `registry: dict[type[Node], list[str]]`
     (class → its kinds, registration order); `load` registers the
     framework's classes once, imports, and returns `Loaded(kinds,
     edit_schema)` — the table selected from the registry: the framework's
     classes and those whose `__module__` is a listed package or a module
     under it; `assemble`/`edit_schema` take the class list. The seal is
     gone: a table is a snapshot, so a later registration cannot reach it.
   - `isabelle_driver.call`: `asyncio.shield` around the round trip.
   - `mcp_server.py`: `Tool(name, description, input_schema, run)`;
     `TAT_Server(port, tools)` binds in the constructor
     (`TAT_StartupError`), `async with` listens/stops, `serve()` returns
     what ended the conversation (a `CancelledError` when the RPC host
     cancelled `launch_TAT`), `end(exn)` enters the ending. The handler:
     body as its own task, `asyncio.wait` inside `anyio.CancelScope
     (shield=True)`, then `anyio.lowlevel.checkpoint()`; `TAT_Error` →
     `isError` text; else `end` + the RENDER_BASELINES §4 line
     (`stopped`). The ASGI app counts non-GET requests in flight so the
     manager is torn down only after every handler has answered. uvicorn
     is driven through `startup`/`main_loop`/`shutdown`, not `serve()`
     (which captures SIGINT/SIGTERM); `interface="asgi3"` is required for
     a bound method.
   - `toplevel.launch_TAT((packages, wd, port), connection)`: `tat.lock`
     flock → `Forest_Store` → `Conversation` → `plugin.load` → `Forest` →
     `TAT_Server` → `writeln` the served line → `raise await
     server.serve()`.
   - `pyproject.toml`: `mcp>=1.26`, `uvicorn>=0.41`, `anyio>=4.5`.
   - Tests: `test_mcp_server.py` (SDK client end to end: results, the
     ending's three doors, the host's cancellation, a client's
     cancellation, Host header 421, 404, port in use), `test_toplevel.py`
     (lock, served line, cancellation, release); 197 pass.

Measured: the first real run of the Python side under `isabelle TAT`
(scratchpad `launcher_run/e2e.py`, log `e2e.log`): an `mcp` client
connected 21 s after launch (`Isabelle_RPC` heap), listed `[]`, got
``unknown tool `nothing` `` on a bogus name; Ctrl-C → `*** Interrupt`,
exit 1, 1.5 s, no orphan. Earlier measurements as before (the three
pre-flight refusals, Ctrl-C in every phase, `TAT_new`'s table).

## Awaiting the owner

Wording (owner's rulings of 2026-09-14):

- `another TAT conversation holds <working directory> (its Python process
  is pid <pid>)` (`TAT_StartupError`, `toplevel._held`; reaches the
  launcher's terminal): approved; the holder writes its pid into
  `tat.lock`, the parenthesis is dropped when the file is still empty.
- `TAT cannot serve on 127.0.0.1:<port>: <strerror>` (`TAT_StartupError`,
  `mcp_server._bind`): approved.
- ``unknown tool `<name>` `` (agent-visible, `isError`, `_call_tool`):
  approved for now; to be discussed again with the tools themselves.
- PLUGIN_SYSTEM §1's added clause on which classes a package contributes:
  the author's call (kept).

Review 11 (2026-09-15; ruling in the scratchpad `entry_review/ruling11.json`,
brief `BRIEF11.md`, diff `diff11.patch`): not accepted; two blocking, the
rest major/minor. Owner's rulings on its owner items:

- GRACE = 5 seconds: the ending's drain (`anyio.move_on_after`) and
  uvicorn's `timeout_graceful_shutdown`; worst case the sum (10 s); §4.6
  now says the ending waits a bounded time and stops regardless.
- PLUGIN_SYSTEM §4's seal passage replaced (done); MODULE_STRUCTURE §4.3
  qualified — only a round trip in flight gets the connection error; a
  tool body's cancellation path never starts one (done).
- "every call" answered the stopped line means every **tool call**
  (RENDER_BASELINES §4, MODULE_STRUCTURE §4.6 changed); `tools/list` and
  `ping` answer normally while the ending lasts.
- §4.6: the promise holds until the server stops accepting (done).
- The `main_loop` relaxation is not taken; decision 6 stands.
- A working directory TAT cannot write:
  `TAT cannot use <working directory> as its working directory: <strerror>`
  (`TAT_StartupError`, around `os.open` of `tat.lock`).

The code fixes, applied with the owner's go-ahead (2026-09-15), to be
re-reviewed (round 12):

- `_call_tool` decides the answer (`_answer`) before its checkpoint; the
  decision is total (`except Exception` enters the ending; a body that
  let a cancellation escape enters it with a `TAT_InternalError`); the
  ending's reason is read from one place, `self._ending`, an
  `asyncio.Future`.
- `serve` raises what ended the conversation (`NoReturn`); after
  `main_loop` it stops accepting (`_stop_accepting`: uvicorn's own three
  steps) and drains `while self._requests: await self._idle.wait()` under
  `anyio.move_on_after(GRACE)`; `timeout_graceful_shutdown=GRACE` on the
  uvicorn config; `ws="none"`.
- The port is bound in `__aenter__` (closed if `startup` fails);
  `launch_TAT` is `await server.serve()`.
- `isabelle_driver.call` retrieves an abandoned round trip's outcome
  (`_dropped`) so asyncio reports nothing.
- `plugin.load` drops from the registry the classes whose module a failed
  import removed from `sys.modules`, so a fixed package loads on retry.
- `_held`: `os.open` failure → the approved `TAT cannot use … as its
  working directory: …`; the pid is cleared on release.
- Tests: events instead of sleeps, one 30 s deadline per test, the
  client's cancellation through a real `notifications/cancelled`, the
  RENDER_BASELINES §4 lines read from the document, no `uvicorn.error`
  record at ERROR on any ending (autouse), the stalled peer (GRACE
  monkeypatched to 1), the empty tool list, `validate_input=False`, the
  boundary's own failures, the registry retry; 205 pass; three
  consecutive runs of the server and toplevel files clean, zero ASGI
  tracebacks with the logging plugin off.
- Docs: MODULE_STRUCTURE §4.6 (order of business, the lock texts, the pid,
  the bounded ending, the standalone stream), §4.3, PLUGIN_SYSTEM §4,
  RENDER_BASELINES §4 ("tool call").

Review 12 (2026-09-15; ruling `entry_review/ruling12.json`, brief
`BRIEF12.md`, diff `diff12.patch`; the run was split by session limits —
challengers and 21 defenders from `wf_bf3942d8-06c`, the rest from the
continuation `wf_dd341108-6d2`, inputs under `entry_review/cont12/`): not
accepted, "the gap is much smaller than round 11's and most of what is
left is prose". Accepted: the `caplog` guard reads the teardown phase
(inert; `get_records("call")`); the stalled-peer ending logs an ASGI
traceback (drop the connections the drain gave up on, inside
`manager.run()`, then drain again); the `late` assertion still races the
tick (test-only: hold the window via a wrapped `main_loop`, warm the
client's schema cache with an early `list_tools`); own the session
manager in `__aenter__`/`__aexit__` (`AsyncExitStack`) so the endpoint
listens only while it runs; `remove_reader` on `__aenter__`'s failure
path; `tool.run` called inside the body task (`_run`); PLUGIN_SYSTEM §1's
"filled once per process" replaced by the `sys.modules` invariant; two
owner items — the GRACE bound is on the transport, not on a body that
ignores its cancellation (decision 1's "worst case is their sum" is
false; §4.6 and the module comment to restate), and what a call whose
body completed despite the ending is answered (code: what it did; docs:
the stopped line). Rejected: the abandoned-trip test being vacuous.

Owner's rulings after round 12 (2026-09-15): **GRACE removed** — a peer
that stalls mid-request is a trusted local client's bug, not TAT's
concern; the ending waits for the requests in flight with no cap, and
uvicorn's `timeout_graceful_shutdown` stays at its default (decision 1 of
2026-09-15 withdrawn; the round-12 owner item on the bound is moot). A
tool call whose body completed despite the ending — before it, or after
ignoring its cancellation — is answered what it did (code wins; the clause
is in MODULE_STRUCTURE §4.6 and RENDER_BASELINES §4). The round-12 author
items applied: the `caplog` guard reads the call phase and lives in
`test/conftest.py` (every test file); the session manager runs from
`__aenter__` to `__aexit__` (`AsyncExitStack`), `serve` no longer enters
it; `remove_reader` on `__aenter__`'s failure path; `tool.run` called
inside the body task (`_run`); the `late` assertion holds the accepting
window through a wrapped `main_loop` (`hold_accepting`) and warms the
SDK client's schema cache; plugin import failures become
`CannotLoadPlugin(package, None, "<ExcType>: <msg>")` (reason text is
Python's — to mention to the owner); docs: §4.6 (the completed body, the
ending's waits, the lock file predicate, the second pid window), EXCEPTIONS
§1's list, PLUGIN_SYSTEM §1's `sys.modules` invariant; tests for the
head-end window, the released port after a failed or cancelled startup,
the `Origin` refusal, `tools/list` during the ending, a plain-`def` tool,
a missing package. 208 pass; mutation checks on the guard and on
`remove_reader` done; e2e clean. Re-review: round 13.

Review 13 (2026-09-15; ruling `entry_review/ruling13.json`, brief
`BRIEF13.md`, diff `diff13.patch`): **accepted**, conditional on five
author items, all applied: `_stop_listening` split out of
`_stop_accepting` and called first in `__aexit__` (the writeln-failure
path no longer accepts while the manager unwinds); the `__aexit__`
comment names the body wait; the attached-client test (the deployed
shape, in a task of its own — the mutant with `__aexit__`'s two awaits
reversed hangs to the 30 s deadline); the tail's two assertions (`serve`
waits for `stubborn`'s call; a connection after it is refused — both
statements now have a red mutant); the tick test asserts it reached
`create_server`'s window and runs the cancelled `__aenter__` in its own
task (the judge's missed item: the test's task otherwise kept
`cancelling() == 1`). Docs (no design change, the author's call):
`CannotLoadPlugin`'s docstring and EXCEPTIONS' tree entry widened to the
import failure; EXCEPTIONS §1 points at PLUGIN_SYSTEM §1 and §5; §4.6's
pid sentence admits a crashed holder's pid in the first window;
PLUGIN_SYSTEM §1's recovery promise narrowed to the failing module (a
clean submodule of a failed package stays cached; a fix there needs a new
host process — the judge's recommended resolution over a code handler,
which would have to know which conversations still hold a package).
Rejected by the judge: startup texts under RENDER_BASELINES (that
document is agent-facing; `TAT_StartupError` never reaches the agent);
hairsplitting: "stops accepting once entered" read as simultaneity;
settled: helper copies between test files. Optional for the owner: §4.6's
`toplevel.py` paragraph as a list; a home for the four startup strings if
they are to be drift-guarded. 209 pass.

Observed, not ours: the `mcp` SDK handles a new session's first request
inside its session-creation lock (streamable_http_manager.py,
`_handle_stateful_request`), so a peer that sends a session-less POST's
headers and stalls blocks every new session until it goes; existing
sessions are unaffected.

Deferred by the owner (2026-09-14) to the design of `edit`/`move`/`delete`
themselves, not to be raised before then: the success result's body (the
text a successful call returns, before the `quickview`).

## Rendering settled (2026-09-15, in the forked session)

The owner decided the rendering; PRINT.md is now the design, with
RENDER_BASELINES §5 (the lines), CLIENT_HOOKS.md (new: the hook files per
agent client and `POST /on-compaction`), MODULE_STRUCTURE §4.1 (the
contract gains `print`, `quickview`, `errors`), §4.6 (the endpoint), §5
(`TAT_new`: the emptiness rule, `-p`, the hook files), ARCHITECTURE §1
(the working directory row), MCP_SPECIFICATION §1.1 (`recall` renders
through `print`; no detail levels). The rulings of that day are
superseded by the paragraph below wherever the two differ; the documents
are authoritative.

The rendering went through two design reviews (scratchpad
`render_review/`: `BRIEF1.md`, `EXCERPTS.md`, `ruling1.md`,
`result1.json`; `BRIEF2.md`, `EXCERPTS2.md`, `ruling2.md`,
`result2.json`); the owner ruled on every item, the round-2 judge said
no third round is needed once its items land, and they have landed
(2026-09-21). The design is PRINT.md, SESSION_AND_THEORY.md §4,
CLIENT_HOOKS.md, MODULE_STRUCTURE §4.1 / §4.6 / §5, PLUGIN_SYSTEM §5,
RENDER_BASELINES §5, MCP_SPECIFICATION §1.1 / §5, ARCHITECTURE §1's rows.
In one breath: `print(indent, out, mode, depth)` with `PrintMode =
Out_Focus | Briefing | Relative_Focus(path: list[Node]) | Recall`; the
class hooks `print_fields(indent, out, mode, depth)` and an overridable
`mark(mode, depth)` whose default is the four-word table; no `errors()`
— a class prints its errors in `print_fields` through `print_error`,
shows a thing once through `Conversation.seen` (keys the class's;
`Theory` discards its key in the evaluation hook, prints only for an
operation that is an own stop, whole under `Recall` below depth 2, once
per run elsewhere, never in `Briefing`); `Forest.render(node, mode)` is
every rendering's entry (id index built and dropped there); the quickview
ends `edit`, `move`, `delete`, `evaluate_to` only; `Out_Focus` prints the
node itself and no children, for every class; the lone session's dashless
line is the framework's `print`'s (root's only child, `depth >= 1`);
`_own_statuses()` in the contract, `_operations_ready` derived; the
endpoint's closure `on_compaction` built in `mcp.py` (clear the seen set,
render the root in `Briefing`; anything raised enters the ending, 500
empty body), the transport-security check with the manager's settings
(`is_post=False`), unknown `client` refused before the seen set is
touched; `tat.lock` two lines, pid then port, each reader one line; the
hooks are one script `.tat/on-compaction.sh <client>` (guard on the port
line, approved line `TAT is not running in this directory.`, `curl -sS
--fail-with-body`) and five files calling it; `TAT_new` without `-p`; the
evaluation walk's alias `EvaluationMode` (done in `model.py`); the
aliases `Id`, `Id_Component`, `Id_Components`, `Identity`; `edit`'s
`target_id` description (TOOL_SCHEMAS §1, `tools/edit.jsonc`).

Rejected by the owner, not to re-raise: recording the port in
`TAT.sqlite`; `TAT` writing the hook files; a `bullet` parameter on
`print`; a fallback when hooks are absent; any cap or ordering of the
briefing; a `Session` listing its theories in `Out_Focus`; a `not
finished` mark; showing errors whole at every `Recall` depth (rejected
twice: keep "below depth 2"); settling `Theorem`'s `not proven` before
the class is designed. Open with the tools: each tool's focus. Open with
`Theorem` and `Define`: their `mark` and `print_fields`.

Work this adds to the Python half, before or with 3e: `Node.print` with
the four modes and the lone-session branch, `print_fields` / `mark`
defaults, `_own_statuses`, `print_error`, `Conversation.seen`,
`Forest.render` with the index, the root's three forms; `POST
/on-compaction` in `mcp_server.py` (`_asgi` routes by path already) with
the closure and the security check; the quickview on the four tools'
results; `_held` writing pid and port and reading the first line. In the
launcher: the emptiness refusal (text approved), the script and the five
files (contents in CLIENT_HOOKS.md); `TAT_new`'s usage text changes and
is user-facing — propose the new wording to the owner before writing it.
Measurements listed at the end of CLIENT_HOOKS.md; the baseline test
should pin PRINT.md §6's two root forms and §7's example.

## Remaining, in order

3. e. `mcp.py`: `edit`, `move`, `delete` (TOOL_SCHEMAS.md; `insert_after`
      is `edit.insert` at index + 1; `HoldsNoChildren`/`ProtectedNode`
      refused before the model), the `quickview` on every result, the
      pending-message queue's seam. Build `Tool`s from the schema files
      under `tools/` (`edit.jsonc`'s `$defs` from `Loaded.edit_schema`).
4. Tests: one Python RPC host (`Isabelle_RPC_Host` launcher, address in
   `RPC_Host`), one `isabelle TAT` per run, the `mcp` SDK's Streamable
   HTTP client; one tree evaluated in Isabelle; retire
   `test/run_ml_framework_test.py` (and `Test_TAT_Framework.thy` with it),
   `test/routing_forest.py`.
5. Review of the whole step, commit.

## Still unverified from the first-run list

Exit code 0 (unreachable today: `launch_TAT` ends only by raising — a
normal ending is undesigned); `editor_tracing_messages=0` load-bearing
(needs a plugin theory emitting over 1000 tracing lines); `Scala.function`
calls during the boot's own load (only indirect evidence); `init_build`'s
print modes against RENDER_BASELINES (needs the tests); start latency on a
stock HOL heap (only `Isabelle_RPC` measured; 21 s to a connected client
against 8 s to the old `NotImplementedError` — the difference is not
broken down).

## To propose to the owner when reached

- `docs/node_classes/THEOREM.md`: untracked draft, before the `Theorem`
  class.
- Isabelle_RPC's `Invalid response, protocol error` when the host dies
  mid-conversation: the library's text; the owner defers it.
- Isabelle_RPC has no public "connection closed" hook: `launch_TAT` learns
  of a dead wire from the host's cancellation (after its 3 s grace) or
  from a round trip failing; a hook in the library would be earlier.

## Measurement notes

- Never test Ctrl-C from a bash background job (`cmd &` in a script):
  the child inherits SIGINT ignored and every result is void. Use
  `subprocess.Popen(..., start_new_session=True,
  preexec_fn=lambda: signal.signal(SIGINT, SIG_DFL))` and `os.killpg`
  (`launcher_run/sigint/probe.py`, `probe_conv.py`, `launcher_run/e2e.py`).
- A blocking stand-in for the Python side lives in
  `launcher_run/stub/isabelle_theory_agent/`; put it first on
  `PYTHONPATH` to keep a conversation running without the real package.
- The review recipe (challengers → fresh defenders → judge, Opus, English)
  and its briefs/rulings are under the scratchpad `entry_review/`
  (BRIEF9.md, ruling10.md).
