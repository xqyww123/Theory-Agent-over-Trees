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
Out_Focus | Briefing | Relative_Focus(nodes: frozenset[Node], depth: int) | Recall`; the
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
the class is designed. Open with `Theorem` and `Define`: their `mark`
and `print_fields`.

Implemented (2026-09-21, uncommitted): `Node.print` with the four modes
and the lone-session branch, `print_fields` / `mark` defaults,
`_own_statuses` (`_operations_ready` derived, the three copies gone),
`print_error`, `Conversation.seen`, `Forest.render` with the index, the
root's three forms, `Session.print_fields`, `Theory.print_fields` with
the own-stop guard and the seen keys discarded in its hooks; `POST
/on-compaction` in `mcp_server.py` (`_compaction`: the security check
with the manager's settings, `is_post=False`; unknown `client` → 400
before the closure; the closure's exception → `end` + empty 500; every
answer through `_answer`), `mcp.on_compaction`; `_held(directory, port)`
writing pid and port, the refusal reading the first line;
`plugin._check_class` refusing `_operations_ready`, `print`, and
coroutine `print_fields` / `mark`; `tat.scala`: the emptiness refusal, a
file path refused as `TAT` refuses one, `write_hooks` writing the script
and the five files when absent (their texts verbatim from
CLIENT_HOOKS.md), the usage text as proposed to the owner (in the code,
**awaiting approval** — the README's TAT_new paragraph awaits the same
wording); `lib/tat.jar` rebuilt. Tests: `test_print.py` (PRINT.md §6, §7
and RENDER_BASELINES §5 read from the documents; marks; the modes and
depths; the seen set, a rerun re-showing through a monkeypatched driver;
the index), `test_launcher.py` (runs the real `isabelle TAT_new`: the
files equal CLIENT_HOOKS.md's blocks, the refusals, the absent-only
rewrite, the script's three failure paths), the endpoint tests in
`test_mcp_server.py`, the lock's two lines in `test_toplevel.py`, the new
refusals in `test_plugin.py`; 230 pass.

Measured with a real conversation (scratchpad `tatnew/e2e_hooks.py`):
connected 7–8 s after launch; `tat.lock` holds `<pid>\n<port>\n`; the
script answers every client in its shape, discards without an argument,
and prints the refusal line for `emacs` (exit 22, readable through
`--fail-with-body`); Ctrl-C → exit 1 in 1.2–1.5 s. After Ctrl-C
`tat.lock` still holds the dead conversation's pid and port — the Python
host receives the group's SIGINT and dies without `_held`'s `finally` —
which is why the script checks the pid is alive (owner, 2026-09-21) and
treats curl's exit 7 as "not running" too. Observed, not ours: two
`Isabelle_RPC_Host` attached hosts from earlier days (pids 945443,
1999953) still alive on this machine, orphans of other sessions.

Review 3 of the implementation (2026-09-21; `render_review/BRIEF3.md`,
`EXCERPTS3.md`, `diff3.patch`, `ruling3.md`, `result3.json`): **READY
WITH AUTHOR ITEMS**, all applied, no further round: the loader refuses
overriding `_children_to_print` (`NonLeaf_Node`'s own definition
admitted); the script's success path tested against a serving
`TAT_Server` (`test_launcher.py`), the JSON files parsed; `Theory`'s
errors pinned off the focus; SESSION_AND_THEORY §4's field lines pinned;
`/on-compaction` answers an empty 503 while the conversation is ending;
`_held` writes the pid on taking the lock and the port through the
`announce` it yields, called once the server listens; the briefing
closure and the ending hook's discard tested; ARCHITECTURE §9, CLIENT_HOOKS
(curl 7.76; a new section pinning the unknown-client line, which the
tests now read from there), PRINT.md §2 / §4 / §5 wording;
`envelope` driven by the one `CLIENTS` table; `Forest.render` refuses to
nest. Owner's words: the README's `Start the agent's client in
WORKING_DIRECTORY and give it that URL.`; the script prints the approved
line on curl's exit 7 as well. Rejected by the judge, not to re-raise:
deriving `_last_status` from `_own_statuses`; indenting a lone session's
fields; the dead-pid test as flaky. 237 pass.

## The tools (3e), settled and implemented 2026-09-22

Owner's rulings (2026-09-22), the documents authoritative (PRINT.md §2 /
§5, TOOL_SCHEMAS §2 / §4, MCP_SPECIFICATION §3.2, MODULE_STRUCTURE §4.4 /
§4.6, RENDER_BASELINES §1 / §6):

- The quickview's mode is `Relative_Focus(nodes: frozenset[Node],
  depth: int)`: every node of `nodes` is a focus, detailed with
  everything `depth` levels under it, the layer below lines only, `-1`
  the whole subtree; a focus's children get `Relative_Focus(the
  children, depth − 1)`; a node above a focus is on the path; the rest
  `Out_Focus`. The owner's own formulation, replacing the path list;
  the owner declined a `count` of siblings and a bare-node variant, and
  asked not to discuss the singleton set's cost further (measured:
  330 ns and 216 bytes per focus node, beside a 40 ns line write).
- Focus and depth per tool: `edit` the nodes added (`amend`: the
  replacement and those after it), −1; `move` the moved node, −1;
  `delete` the old parent, 0; `evaluate_to` the destination, 0.
  Everything a call added is printed whole, once.
- The success line: `Done: <opr> <target>.`, the target echoed as the
  agent wrote it; `; evaluation stopped at <id>` only when the walk
  stopped at an obstacle. No "evaluated to", no destination id: the
  quickview's marks say it, and TAT has no evaluation caret —
  `evaluate_to` always takes an explicit id (the §3.2 sentence that
  promised the destination's id predates the quickview and is gone).
- ``unknown tool `<name>` `` stays as it is ("不需要过度设计").

Author's calls, told to the owner: a call's own arguments are checked
by `plugin.check_call` — the construct-field checker `_check_fields`,
told which fields are the framework's (`framework`, none for a call) and
that the holder is a tool (`of_tool`, carried by `MissingField`,
`UnexpectedField`, `InvalidField`, which then say tool and argument) —
against TypedDicts in `mcp.py` (`constructs: list[Any]`, the elements
`edit.py`'s), so a malformed call renders TOOL_SCHEMAS §4's lines alone,
before any operation is named; `edit.parent_of` public, used by
`mcp._location`; `detailed` a `Node` method (a focus is the node's own
membership of `nodes`); `Forest.render` computes `_above` by walking up
from each focus and refuses an empty `nodes`, a focus outside the
rendered node, and one under another.

Review 4 (2026-09-22; scratchpad `tools_review/`: `BRIEF4.md`,
`diff4.patch`, `ruling4.md`, the workflow's result in
`tasks/wrx4ud2ot.output`; 69 findings, 46 after dedupe, a defender each,
the judge measuring eleven mutations): **NOT READY**, one blocking item —
`edit` with `"constructs": []` ended the conversation in every
action/evaluate combination, `minItems` being enforced nowhere with the
SDK's validation off. All items landed the same day, owner's rulings on
the three agent-visible ones: the empty batch refused as ``The argument
`constructs` must not be empty.``; the malformed-call sentences in the
tool form (``The `edit` tool needs the argument `evaluate`.``); a `move`
`before`/`after` the moved node itself is its own `MoveBesideItself`
(``` `t_a` is already in that position; a move must name another node. ```,
the author's pick between one sentence and two). Author items, all
applied: `Forest.render` refuses an empty `nodes` and the descent's
guard is an assertion; `assert self.lock.locked()` in `Forest._run`
(the lock removed: 8 tests fail); the quickview rendered inside the
lock; `ACTIONS`/`POSITIONS` read off the schema files and every schema
bound to its TypedDict by one test; `edit.jsonc` pinned to TOOL_SCHEMAS
§1 (the `$defs` comment moved onto its own line there); `edit.delete`
returns the parent it left; one `_location` for both tools and one
`_resolve(root_ok=…)` for `Sessions`; `_operation` yields the phrase;
exhaustive dispatch on action and position; `_check_fields`'s
`framework: Collection[str] = ()`; `validate_call_schema` on the tool
TypedDicts when `tools` builds them; the loader refuses `__eq__` /
`__hash__` (nodes live in sets); tests for `append Sessions`, a
first-layer insertion, a nested batch pinning every per-tool depth,
`match=` on the three render refusals, causes asserted by class and
fields (the `Cannot` lines and TOOL_SCHEMAS §4's block read as
documents), descriptions from `Tool description:` lines
(`baselines.stated`), `test_model.add(kind=…)`; the document repairs of
N1 and M4–M6, M15. Rejected by the judge, not to re-raise: widening the
argument schema grammar with `Literal`; `Relative_Focus.__post_init__`
refusing an empty set (a childless focus builds one legitimately);
`exceptions._OPERATIONS` as a copy of the enum; a `detailed` override
guard; the `table` fixture shared; store-mirror checks in `test_mcp`;
moving the malformed-call lines into RENDER_BASELINES §2. Declined by
the author (the judge recommending the same, the owner having closed the
topic): replacing `_above` with a per-child narrowed mode. Deferred to
step 4 (owner): where the order constraint's sentence (RENDER_BASELINES
§3) goes in a successful call's answer — the judge suggests under the
`Done` line, `_evaluate` handing back the whole `EvaluationResult`.
255 pass, pyright clean on the package. Not yet: the pending-message
queue's seam (with `construct`).

Review 5 (2026-09-22, on the fixes above; `tools_review/BRIEF5.md`,
`diff5_since_review4.patch`, `ruling5.md`, the workflow's result in
`tasks/wj8f5aea5.output`; 40 findings, 26 after dedupe, a fresh defender
each): **READY WITH AUTHOR ITEMS** — ruling 4's blocking item verified
closed; what remained was correctness held in memory rather than in
shape, plus one document clause the author had inverted. Owner's
rulings: O1, checking a call against the schema it advertises and
deleting the tool TypedDicts (the relaxation the judge recommended,
with three amendments: descend into typed `items` or refuse any but
`Construct`'s, check `loaded.edit_schema` itself, and note it reverses
ruling 4's A2/M10/M11), left to the author, who takes it **as its own
change after this round's commit**, so ruling 5's M12 (a `_tool`
helper, `check_call` returning the narrowed TypedDict) is not applied —
O1 replaces it; O2, the `move` phrases without "to" (``Cannot move
theory_Sorting after theory_X.section_Basics``, ``… into
session_Arith``, and the `Done` twin), approved; O3, TOOL_SCHEMAS §4
pointing at RENDER_BASELINES §1 / §6 instead of copying their blocks,
approved; M10's noun `anchor` given a glossary row (ARCHITECTURE §1), the
author's call. Author items, all applied: `of_tool` written on the way
out by `check_call` (`RawASTError._mark_of_tool`, the parameter gone
from the checker and the three constructors; the tool entry marks its
own two raises through `_about_the_call`); three nested-argument cases
and a `move … into Sessions` case tested; MODULE_STRUCTURE §4.6's move
clause restored ("a sibling before which the node stood loses one");
`_location(forest, position, anchor_id, moving)` resolving its own
anchor with `root_ok` from the position; `_done` asserting the lock;
the loader refusing `__eq__` as well as `__hash__`; `MissingField.holder`
and `UnexpectedField.holder_is_top`; the descent test's positive control
restored; EXCEPTIONS §3's `ProtectedNode` row and the tests' rendering
rule reworded; MCP_SPECIFICATION §5's lock sentence; every jsonc block
parsed alike. Struck by the judge, not to re-raise: `parent_of`'s
publication; RENDER_BASELINES §2's elliptical gloss; an `InvalidField`
row gloss; `test_mcp` reading RENDER_BASELINES §2; `Relative_Focus`
holding the non-empty invariant itself; a `docs/DECISIONS.md`.

Review 6 (2026-09-22, confirming, on the fixes above; `BRIEF6.md`,
`diff6_since_review5.patch`, `ruling6.md`, `tasks/w2zr68ajg.output`; 16
findings, 8 after dedupe): **READY WITH AUTHOR ITEMS** — every ruling-5
item verified present, 72 malformed call shapes driven with `of_tool`
marked on all 61 refusals and none of the construct-side errors; five
minor author items, all sentences: `exceptions.py`'s header and field
comment, EXCEPTIONS §3's group row and the tests' rendering rule (the
ML harness added as a home), `edit.parent_of`'s docstring, two test
docstrings, the `[0:1]` slice at §1–§3 — all applied; no owner items.
Struck: PLUGIN_SYSTEM §5's hash clause reasoning (not this round's); a
test binding `_done`'s assertion (its own scenario defeats it); comment
wording and extra `len(lines)` asserts; README's index row. The judge
notes the round fit to commit once the five clauses are written.

## Remaining, in order

**Found 2026-09-22, done 2026-09-23 before the harness:** the plan's
step 4, the forest walk (`Forest._evaluate`, FIRST_END_TO_END_RUN_PLAN §6
— the import graph, the order constraint's stop, stops across import
dependencies, invalidation of importers, `TAT.theory_delete`), had never
been implemented: `Forest._evaluate` raised `NotImplementedError`, and a
smoke run against a real `isabelle TAT` (scratchpad
`tools_review/e2e_tools.py`, output `e2e_tools.out`) showed every tool
call — `evaluate: false` included, since every entry ends with the
invalidation walk — dying there, the server answering `TAT has stopped:
an internal error` as designed; the suite passed because
`test_model.OneTreeForest` supplied its own `_evaluate`. It is now in
(`ai-artifacts/FOREST_WALK_PLAN.md`, the implementation plan and its
record); `test/routing_forest.py` is gone with it. Still open from that
step, for the `evaluate_to` tool: where the order constraint's sentence
goes in a call's answer (TOOL_SCHEMAS §4), composed from
`Forest._order_violation`.

3. f. **O1, implemented and reviewed 2026-09-22; a confirming round,
      then commit — done, `e9cecd9`** (the author's call after ruling 5,
      `tools_review/ruling5.md` §3, the judge recommending it with three
      amendments): a tool call is checked against the schema the tool
      advertises, and the tool TypedDicts are gone. Gone:
      `Edit_Arguments`, `Location_Arguments`, `Move_Arguments`,
      `Delete_Arguments`, `ACTIONS`/`POSITIONS`, `_one_of`, the
      `minItems` refusal in `run_edit`, `_about_the_call` (nothing in
      `mcp.py` raises a shape error now), the TypedDict
      `validate_call_schema`, and `test_mcp.py::
      test_the_advertised_schemas_bind_the_shapes_the_entries_enforce`.
      Come: `plugin.check_call(schema, tool, arguments)` walking the
      keywords `type` (`string`, `boolean`, `integer`, `number`, `array`,
      `object`), `properties`, `required`, `additionalProperties: false`,
      `enum` (on a string, an integer or a number; not a boolean, whose
      values would render as Python's), `minItems`, `items`, nested
      objects, raising the same three exceptions with the same sentences,
      `of_tool` marked on the way out as before; the two checkers share
      one table of the JSON types, `_JSON_TYPES` (Python shape and
      RENDER_BASELINES §2's phrase, a NamedTuple), `_fits` serving both,
      `_JSON_NAMES` mapping the grammar's scalars to JSON type names, and
      one `_check_names` for the two name loops (a typo beats its own
      hole, then a required one missing); `validate_call_schema(schema,
      where)` refuses, where `tools` builds them, a schema that is not
      well formed (`jsonschema`'s `check_schema` first, as `edit_schema`
      and `_check_class` already do), a top that is not an object, and
      one saying anything the check does not enforce or its sentences
      cannot say (an unknown keyword, an unknown or union type, a
      `minItems` other than 1, an `items` neither typed nor the
      `Construct` `$ref`, an object without its three keywords, `$defs`
      below the top) — the binding test's role, held in shape. The three
      amendments applied: (1) `items` typed descends by index, the
      `Construct` `$ref` is opaque, any other refused; (2) `tools` checks
      `loaded.edit_schema` itself for `edit`, the `.jsonc` files for the
      others, one `schemas` table advertised and enforced; (3) the
      documents: MODULE_STRUCTURE §4.4 (the tool schema grammar defined,
      the validator's two directions) / §4.6, EXCEPTIONS §3's `of_tool`
      row, TOOL_SCHEMAS §1 (within §4.4's grammar, narrower than AoA's)
      and §4's intro, RENDER_BASELINES §2's two `InvalidField` sentences
      and its type phrases, `exceptions.py`'s header and `RawASTError`'s
      comment. `_ACTION_POSITION` stays. Ruling 5's M12 is superseded.

      **Owner's ruling (2026-09-22): `integer` is in, phrase `an
      integer`** ("的确我们几乎都会用 integer 类型而非 number 类型", the
      choice of phrase left to the author) — the author's own narrowing
      of the plan (no `integer`, one phrase for a number) lifted on the
      judge's O1 of ruling 7. So RENDER_BASELINES §2 lists six type
      phrases; a tool schema may say `integer`; the construct grammar's
      `int` renders `an integer` and refuses `1.5` again (ruling 7's A2,
      a regression this change had introduced through the shared table:
      `int` welded to `float`); `int | float` in a construct annotation
      is refused at registration ("`float` makes `int` moot", the rule
      `Any` already had — its only rendering would have been "an
      integer or a number"), MODULE_STRUCTURE §4.4's grammar sentence
      saying so.

      Review 7 (2026-09-22; `tools_review/o1/BRIEF7.md`, `diff7.patch`,
      `ruling7.md`, the workflow's result in `tasks/w8xe3fzhi.output`;
      13 findings after dedupe, a fresh defender each, the judge fuzzing
      40 000 schemas and running seven mutants): **READY WITH AUTHOR
      ITEMS**, all applied — A1 the validator made total (the rows of
      its table: a union `type`, a non-list `required`, `enum: 3`, a
      string-typed top — 60 091 crashes in the fuzz before, 0 after);
      A2 above; A3 a `boolean` (and now an `integer`) argument in
      `test_plugin`'s synthetic schema, pinning the phrases the deleted
      binding test had pinned; A4 `_check_names`; M1 the grammar
      paragraph in §4.4; M2 TOOL_SCHEMAS §1's clause; M3 `_KEYWORDS`'s
      comment and `enum` on numbers; M4 `check_call`'s precondition in
      its docstring and §4.4; M5 the synthetic `constructs` given
      `minItems: 1`, so the type-before-`minItems` order is pinned on
      the shape the shipped schema has; M6 `test_mcp` feeds `tools` a
      broken `edit` schema and expects the refusal naming `edit.extra`;
      M7 §4.6 re-wrapped. Struck by the judge, not to re-raise: the
      cross-argument order of two faults (the new order wins, nothing
      pinned the old); EXCEPTIONS §3's `MissingField` row; "retypes
      nothing off the schema"; splitting the validator's sentence in
      four; widening `object`'s shape and `required`'s default as
      mutation padding. 256 pass, pyright clean; the 135-call grid
      (`tools_review/o1/diff_calls.py`, `old.jsonl` / `new2.jsonl`)
      byte-identical through the committed checker and this one; of ten
      mutants (`tools_review/o1/mut8`) eight are caught, the two
      surviving being the struck pair.

      Review 8 (2026-09-22, confirming, on the fixes above;
      `tools_review/o1/BRIEF8.md`, `diff8_since_review7.patch`,
      `ruling8.md`, `tasks/w52sgdiac.output`; 5 findings, a fresh
      defender each): **READY WITH AUTHOR ITEMS** — every ruling-7 item
      verified present (M7's re-wrap had only moved the orphan), the
      `integer` ruling applied consistently, nothing for the owner. The
      four items, all applied: the validator refuses an `enum` that is
      empty or holds a value of another type (the one keyword of the
      grammar whose value `check_schema` cannot see: `[]`, `["a", null]`,
      `[1, true]` rendered "must be one of ." and Python's `None`/`True`
      before), §4.4's paragraph saying so; the synthetic `at.line` given
      an integer `enum` with a row, pinning that an `enum` is read
      whatever the type; a `line: 1.0` row pinning that `integer` is a
      Python `int` (a relaxation to `float.is_integer()` would hand `gen`
      a float under an `int` annotation — the trap A2 repaired), with a
      comment at the table entry; §4.6 re-wrapped without an orphan.
      Struck: `_KEYWORDS` vs `_JSON_TYPES` "no longer tied" (the one live
      case, `null`, is pinned twice); the re-wrap's rationale
      (MODULE_STRUCTURE carries 19 such short lines); the `enum`
      coverage item's severity (no shipped or AoA schema carries a
      non-string enum). 256 pass, pyright clean, the 135-call grid
      byte-identical (`new3.jsonl`). **Fit to commit.**

4. Tests: one Python RPC host (`Isabelle_RPC_Host` launcher, address in
   `RPC_Host`), one `isabelle TAT` per run, the `mcp` SDK's Streamable
   HTTP client; one tree evaluated in Isabelle; `test/run_ml_framework_test.py`
   retires into it. **Done 2026-09-27** (`ai-artifacts/TEST_HARNESS_PLAN.md`,
   the plan and its record; commit `c922897`): the harness `test/harness.py`
   and `test/conftest.py`, a fresh conversation per case through the
   framework callback `TAT.reset`, the test plugin
   `Theory_Agent_over_Trees.Test_TAT_Framework` with its package
   `tat_test_plugin`, the 19 Isabelle-backed cases of
   `test/test_conversation.py` — the step-5 case through the MCP client
   among them — and `test/run_ml_framework_test.py` and
   `test/tat_framework_ml_test.py` retired.
5. Review of the whole step, commit. **Done 2026-09-27**: two plan
   reviews, a re-read and an implementation review (TEST_HARNESS_PLAN.md
   §11); commit `c922897`.

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

## Where things stand after the harness (2026-09-28)

- The harness is `c922897` on `main` (push only on the owner's word,
  to `origin` only). The other session's untracked files
  (`docs/node_classes/THEOREM.md`, `ai-artifacts/CONSTRUCT_DECISIONS.md`,
  `ai-artifacts/AGENT_CLIENTS_MEASURED.md`, `ai-artifacts/probes/`) are
  not this work's.
- The suite: `python -m pytest test` — 306 cases, 39 s, one `isabelle
  TAT` for the 19 Isabelle-backed cases (`test/test_conversation.py`);
  `-m "not isabelle"` never starts Isabelle. The harness's design and
  record: `ai-artifacts/TEST_HARNESS_PLAN.md` (§3, §4 the mechanism; §9
  the measurements; §10 the known limits; §11 the four reviews).
- The reviews' material: this session's scratchpad
  `harness_review2/` — `BRIEF2.md`/`ruling2.json` (the plan's second
  review), `reread.md`, `BRIEF_IMPL.md`/`ruling_impl.json` (the
  implementation review), `diff_step5.patch`, `probe_escalation.py`.
  Review runs take the model id `claude-opus-5-5` and effort `xhigh`
  (Claude Code ≥ 2.1.280); a stopped run resumes with `TaskStop` then
  `Workflow({scriptPath, resumeFromRunId})`.
- Next, in FIRST_END_TO_END_RUN_PLAN.md §7's closing order: `recall`
  (done later this day, the last bullet below), `evaluate_to` as a tool
  (TOOL_SCHEMAS §5; its Isabelle-backed cases through the harness's
  `client()`); compilation (§1's open item: the `.thy` files and the
  ROOT); `construct` (the other session's design work,
  CONSTRUCT_INTERACTION.md, THEOREM.md and CONSTRUCT_DECISIONS.md, into
  which `status` has folded as `check_construct`).
- The owner's decisions still open, none blocking: the three of
  FOREST_WALK_PLAN.md §12 (where the order constraint's sentence goes in
  a tool's answer — with `evaluate_to`; a variant sentence for a
  self-import, or not; `CoreC++` unreachable under the theory-name
  grammar); two memory proposals never ruled on (the review model id and
  version above; the SIGINT-testing rule of this file's measurement
  notes).
- Still unverified (the list above): the start latency on a stock `HOL`
  heap is now measured — 11.6 s to a connected client on 2026-09-21,
  12.6 s to the conversation up on 2026-09-27.
- Later on 2026-09-28: `recall` landed — its document docs/RECALL.md,
  its plan and record ai-artifacts/RECALL_PLAN.md (§7, §8), the tool in
  `mcp.py` with `tools/recall.jsonc`, `Theory`'s hooks recording a run's
  messages and discarding their key together after the call (PRINT.md
  §4), the stopped line reworded to "the sessions could not be saved"
  (RENDER_BASELINES §4); the suite then 312 cases, 20 of them
  Isabelle-backed (RECALL_PLAN §7). After its implementation review
  (2026-09-29, RECALL_PLAN §8): every tool advertised with MCP's
  `readOnlyHint` (`Tool.read_only`), and `mcp._tool` putting the call
  check in front of every entry. Next: `evaluate_to` as a tool.
- 2026-09-29/30: the `parent_session` check (its record and reviews:
  ai-artifacts/PARENT_SESSION_CHECK.md): `Session.gen` refuses a parent
  that is the session itself or names no `Session` the call keeps or
  adds before it and no session the Isabelle session layout knows
  (`TAT.is_known_session`); with it the node class contract's
  `NodeConfig` gained `batch_before` and `role` and lost `replacing`
  (MODULE_STRUCTURE §4.1). The suite then 315 cases, 21 Isabelle-backed.
  `evaluate_to` is the other session's; next here: compilation (§1).
