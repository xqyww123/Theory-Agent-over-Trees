# Plan: the `recall` tool

Status: implemented 2026-09-28 (§7), after review 1, its re-read and a
read of the diff (§8). The design is docs/RECALL.md (decided); this plan
is how it landed: the entry, one ordering change in `Theory`'s
evaluation hooks that a lock-free read requires, the tests, the
documents, the order.

## 0. Scope

The fourth tool of `mcp.py`: `recall` (RECALL.md), advertised beside
`edit`, `move` and `delete`, its schema in `tools/recall.jsonc`, with
its cases in the fake-table suites (`test/test_mcp.py`,
`test/test_print.py`) and through the MCP client on a real conversation
(`test/test_conversation.py`, the harness of TEST_HARNESS_PLAN.md).
With it, §2.1: `Theory`'s two evaluation hooks record a run's messages
and discard their seen-set key together, after the Isabelle call.
Documents brought up to date.

Not in scope: the pending messages that will ride on every tool result
(CONSTRUCT_INTERACTION.md §5, with `construct`); `evaluate_to`; any
other change to the `Recall` rendering (PRINT.md, decided).

## 1. Decisions taken *(the owner's)*

1. `recall` reads one node by id, or, with no id, all the sessions from
   the root; it renders in `Recall` and does nothing else — no
   evaluation, no lock, no quickview (RECALL.md §1, §2; 2026-09-16 and
   2026-09-21).
2. The call: one optional argument, `node_id`, a string, described `The
   id of the node to read. Leave it out to read sessions.`; the tool
   described `Read an Isabelle theory construct with what is under it,
   briefer the deeper; read a construct itself to see it in full.`
   (RECALL.md §3, 2026-09-28).
3. No depth argument: `Recall`'s three levels, briefer the deeper, are
   fixed (2026-09-15; the description tells the agent to read a lower
   node for detail).
4. A failed `recall` renders the cause alone (TOOL_SCHEMAS.md §4,
   2026-08-31).
5. `Theory` discards an operation's seen-set key when its evaluation
   hook records the run's messages, after the operation has run; PRINT.md
   §4's sentence changes accordingly (2026-09-28, review 1's owner item).
6. A read is advertised with MCP's `readOnlyHint`: `Tool` carries a
   required `read_only`, the server lists it for every tool
   (MCP_SPECIFICATION §5, MODULE_STRUCTURE §4.6, RECALL.md §3's closing
   clause; 2026-09-29, review 2's O2).
7. One builder, `_tool`, puts the call check in front of every entry,
   loosening §5's "no new helper" (2026-09-29, review 2's O3).

## 2. The entry

In `mcp.tools`, a fourth tool after `delete`, its schema read from
`tools/recall.jsonc`, built by `_tool` (§2.2) like the other three:

```python
async def run_recall(arguments: dict[str, Any]) -> str:
    node = forest.resolve(arguments["node_id"]) if "node_id" in arguments else forest
    return forest.render(node, RECALL)
```

- The id resolves through `Forest.resolve`, not `_resolve`: a read may
  name the root, and `_resolve` exists to refuse it for the
  forest-changing tools (its docstring says so). `Forest.resolve`
  answers the forest for `Sessions` (MCP_SPECIFICATION §2; RECALL.md
  §3), so `node_id: "Sessions"` reads what an omitted `node_id` reads.
  `NodeNotFound` and `AmbiguousId` propagate as they are — no
  `_operation` context, so no `Cannot` line — and the server boundary
  renders them (MODULE_STRUCTURE §4.6).
- No lock. A rendering runs at one of the walk's awaits — inside a
  hook's Isabelle round trip included. A hook records a run's messages
  and discards their key together, after the call returns (§2.1), so a
  rendering reads the last completed run's messages, shown only while
  that run's status stands; the one await between a run's messages and
  its status, `copy_to` before the status is written, is harmless, since
  `print_fields` gates on the status. `Forest.render` is synchronous, so
  its reentrancy guard cannot fire.
- `check_call` already covers the optional argument: absent passes,
  present must be a string (`null` included, refused as not a string),
  anything else is `UnexpectedField` (`plugin._check_names`).

`tools/recall.jsonc` is RECALL.md §3's block, with the header comment
the other three files carry.

### 2.1 `Theory`'s hooks

`_eval_beginning_opr` and `_eval_ending_opr` become: `errors = await
isabelle_driver.call(...)`, then `seen.discard(key)`, then
`self.<operation>_errors = errors`, then `return not errors`. The
pre-clear `self.<operation>_errors = []` goes: a call that raises is
`TAT_IsabelleError`, an internal error that ends the conversation, so
the pre-clear protected nothing. The comment above the two hooks is
rewritten to match — its "The previous run's messages go before the
call, so a failed call leaves none standing; and the run's key leaves
the seen set, so its messages show again" becomes that the run's
messages replace the previous run's after the call, and the key leaves
the seen set with them, so the messages show again (PRINT.md §4). What
the order buys: an operation's
messages and its key change together, with no await between them, so no
rendering can show a `failed` status with an empty message list and
record the key — which, once `evaluate_to` passes `ignore_error` and an
own stop reruns, a lock-free `recall` landing inside the round trip
would otherwise do, hiding the rerun's messages from the quickview that
follows.

### 2.2 The builder and the hint

`_tool(name, description, schema, run, read_only)` in `mcp.py`:
`validate_call_schema(schema, name)`, then `Tool(name, description,
schema, checked, read_only)` where `checked` runs `check_call(schema,
name, arguments)` before `run` — so no entry can skip the check or name
another tool's schema; the `schemas` table, its loop and the four
`check_call` lines go. `mcp_server.Tool` gains a required `read_only:
bool`, and `_list_tools` passes `annotations=ToolAnnotations(readOnlyHint=
tool.read_only)` for every tool (`false` is MCP's default); `recall` is
the one `True`. Tests: `[t.read_only for t in tools.values()] == [False,
False, False, True]` in test_mcp.py; the hint crossing the wire in
test_mcp_server.py.

## 3. Tests

### 3.1 `test/test_mcp.py`, on the fake forest

- The advertised list becomes `["edit", "move", "delete", "recall"]`.
  `RECALL = DOCS / "RECALL.md"`; `schema, [not_found, ambiguous,
  unexpected] = fenced_blocks(RECALL, "3.")` — the unpacking fixes the
  refusal block at three lines — and the descriptions test reads
  `recall`'s description with `stated(RECALL, "Tool description")` and
  its schema from `schema`, as the other three are read from
  TOOL_SCHEMAS.md.
- Success, by literal lines, the convention of the file's other success
  tests. Inside the test, with `build()`'s own idiom, one more level:
  `inner = add(sec, Block(sec, slot(), "Inner", slot()))` and a `t_x`
  under it. Then the no-id call answers `['block_Theory (not
  evaluated)', '- block_Section (not evaluated)', '  - t_a (not
  evaluated)', '  - t_b (not evaluated)', '  - block_Inner (not
  evaluated)', '- t_c (not evaluated)']` — `t_x` absent, which is
  `Recall`'s depth cut and so pins the mode; the dashless first line
  pins PRINT.md §6. `node_id="Sessions"` answers the same lines. A
  `recall` of `block_Section` answers `['- block_Section (not
  evaluated)', '  - t_a (not evaluated)', '  - t_b (not evaluated)', '  -
  block_Inner (not evaluated)', '    - t_x (not evaluated)']`, which
  pins the node and the dash.
- No lock: with `forest.lock` held by the test, the no-id call answers
  the same lines, under `asyncio.wait_for` so that a regression fails
  instead of hanging.
- Refusals, by class and fields, each rendering one line with no
  opening line: an id nothing bears (`NodeNotFound`); an ambiguous one
  (`AmbiguousId`, the forest given a second block with an `a` of its
  own); `node_id` not a string (`InvalidField`, `of_tool`); an argument
  the tool does not take (`UnexpectedField`), rendering `[unexpected]`.
  And `{not_found, ambiguous} <= set(fenced_lines(DOCS / "RENDER_BASELINES.md", "2."))`
  (the file's inline idiom; `fenced_lines` imported), so RECALL.md §3's
  copies of those two lines cannot drift from their home, where
  test_exceptions.py ties them to the classes. The descriptions test
  compares the four tools' descriptions against TOOL_SCHEMAS.md's three
  `stated` lines followed by RECALL.md's one.
- The forest is untouched by every call above (`names(...)`, as the
  other refusal tests assert).

### 3.2 `test/test_print.py`, the rendering rules `recall` leans on

- The depth-1 rule — whole whatever the seen set holds — pinned where
  the depth-2 rule is: in `test_recall_at_depth_two_shows_a_theory_s_errors_once_per_run`,
  after the second render, `render(f, a, RECALL)[-2:] == ["    Error:",
  "      header broke"]`; the test renamed to cover depths one and two.
- RECALL.md §2's promise that a `recall` records what it writes whole:
  a sibling of `test_a_theory_prints_its_error_once_per_run_in_a_quickview_and_whole_in_recall`
  — `f, a, x = failing_theory()`, then
  `render(f, x, RECALL)[-2:] == ["  Error:", "    header broke"]`, then
  `render(f, f, focus(x))[-1] == "  imports: Main"`.
- RECALL.md §2's example, `test_the_recall_of_recall_md_section_2`,
  shaped like `test_the_quickview_of_print_md_section_7`:
  `session(f, "A")` with a `Base` theory `READY`/`READY` holding a
  `READY` `Lemma` `A` that owes nothing (the file's `_owes_nothing`
  override idiom); `session(f, "B", description="Sorting, verified.")`
  with `theory(b, "X", imports=("Main", "A.Base"))` holding `Lemma` `P`;
  `[example] = fenced_blocks(DOCS / "RECALL.md", "2.")`; `render(f, f,
  RECALL) == example`.
- §2.1, beside the rerun tests: `isabelle_driver.call` patched with a
  coroutine that renders `Recall` of the theory before returning the new
  messages; the rendering taken inside the call shows the previous run's
  messages, and the quickview after the rerun shows the new ones.

### 3.3 `test/test_conversation.py`, through the MCP client

One case on a fresh conversation, one `edit` with `evaluate: true`
building a session `TAT_RECALL` (`parent_session` `HOL`) holding `A`
(imports `Main`) and `B` (imports `TAT_Nowhere.Nope`, so its header
fails with RENDER_BASELINES §3's sentence); the `edit`'s quickview shows
`B`'s error once.

- `session.call_tool("recall")`, no arguments at all — the shape only
  the wire sends, and `recall` is the first tool whose arguments are all
  optional: exactly these six lines —
  `session_TAT_RECALL`,
  `parent_session: HOL`,
  `- theory_A (success)`,
  `  imports: Main`,
  `- theory_B (failed)`,
  `  imports: TAT_Nowhere.Nope`.
  No `Error:` block: the lone session is at
  depth 1 and the theories at depth 2 (PRINT.md §2: "depth still
  rises"), where an error is written once per run, and the `edit`'s
  quickview has shown it — so the case pins, through the wire, that one
  conversation's seen set spans tools.
- `recall` of `theory_B`: `- theory_B (failed)`, `  imports:
  TAT_Nowhere.Nope`, then the `Error:` block, whole at depth 0 though
  the key is recorded, its message line derived from RENDER_BASELINES §3
  with the file's `not_found` helper.

The lines the framework writes itself are asserted literally; the
loader's sentence is derived, never spelled out (EXCEPTIONS.md §3). That
a `NodeNotFound` crosses the wire as the whole `isError` text is
test_mcp_server.py's already.

## 4. Documents

- PRINT.md §4: "discards the key in the evaluation hook before the
  operation runs" becomes "discards the key when the evaluation hook
  records the run's messages, after the operation has run" (§1 item 5).
  The same rule in node_classes/THEOREM.md §8 ("discarded before the
  operation runs") is the other session's draft, told to the owner
  rather than edited here.
- MODULE_STRUCTURE.md §4.6's `tools` paragraph rewritten, not added to:
  `tools` builds `edit`, `move` and `delete` (TOOL_SCHEMAS.md) and
  `recall` (RECALL.md §3); the schema and `check_call` sentence stays,
  true of all four; the lock, the `Done` phrase, "the one id resolution
  every entry goes through" and "the result is the `Done` line over …"
  are said of the forest-changing tools; one sentence for `recall`: it
  resolves through `Forest.resolve`, `Sessions` included, and answers
  `Forest.render(node, Recall)` alone (the lock is "Entry points and
  the lock"'s to state, and it does).
- `mcp.tools`' docstring: the three forest-changing tools as now, and
  `recall`, rendering the node in `Recall` under no lock.
- EXCEPTIONS.md §3's list of the documents tests read lines from:
  RECALL.md §3's refusal block (test_mcp.py) and §2's example
  (test_print.py).
- The docstrings of test_mcp.py (the three forest-changing tools and
  `recall`) and test_print.py (RECALL.md §2 among the examples pinned).
- FIRST_END_TO_END_RUN_PLAN.md §7's closing sentence: `recall` done,
  pointing here; STEP5_HANDOFF.md's "Where things stand": the next item.

## 5. Author's calls, stated so they are visible

- `node_id: "Sessions"` reads the sessions like an omitted `node_id`,
  through `Forest.resolve` as it stands; the entry keeps the plain `if
  "node_id" in arguments` rather than `arguments.get("node_id",
  "Sessions")`, which would copy the root's id into a third place and
  hide RECALL.md §3's rule that a missing id reads the root.
- `recall` is advertised last, after `delete`.
- RECALL.md keeps its `Tool description:` on one line, which is how
  `baselines.stated` reads approved descriptions.
- One helper, `_tool` (§2.2, review 2's O3); the entry itself is two
  lines on functions that exist; the tests use test_mcp.py's
  `build`/`add`/`refused`/`names` and test_print.py's
  `failing_theory`/`session`/`theory`/`leaf`/`render`/`focus`.

## 6. Order of work

1. `tools/recall.jsonc`, the entry, test_mcp.py's cases and
   test_print.py's; `python -m pytest test -m "not isabelle"`.
2. §2.1: the hooks, their test, PRINT.md §4.
3. The Isabelle-backed case; `python -m pytest test`.
4. The documents of §4.
5. One fresh Opus 5.5 reader over the diff; the record (§7).

## 7. Record

- **What landed** (2026-09-28, in §6's order): `tools/recall.jsonc`;
  `run_recall` in `mcp.tools`, the tool advertised fourth; the cases of
  §3.1 (two tests, the descriptions test now over four tools) and §3.2
  (the depth-1 assertion, the recording test, RECALL.md §2's example,
  the inside-the-rerun test); `Theory`'s two hooks reordered as §2.1
  says, the pre-clear gone, the comment rewritten; PRINT.md §4's
  sentence; the wire case of §3.3, its theories named `TAT_RECALL_A` and
  `TAT_RECALL_B` (short names must be unique against the base heap);
  the documents of §4. The same commit carries, uncommitted since
  `c922897`: docs/RECALL.md itself and its pointers (README.md,
  MCP_SPECIFICATION §1.1, TOOL_SCHEMAS' intro and §5); the stopped line
  "the sessions could not be saved" (RENDER_BASELINES §4,
  MODULE_STRUCTURE §4.6, `mcp_server.py`); FIRST_END_TO_END_RUN_PLAN.md
  §7's two done markers; in STEP5_HANDOFF.md, items 4 and 5 and the
  forest-walk paragraph marked done, the section "Where things stand
  after the harness", and item 3.f's record of the other session's O1
  of 2026-09-22 (reviews 7 and 8, the `integer` ruling; its code is
  `e9cecd9`), carried whole on the owner's word (review 2's O4).
- **Outcomes.** `python -m pytest test -m "not isabelle"`: 292 passed
  after step 2 (291 after step 1). `python -m pytest test`: 312 passed
  in 39 s, the wire case passing on its first run with the literal lines
  of §3.3. The diff's reader ran five mutants against the new tests —
  the beginning hook's key discarded before the call, a whole rendering
  not recording, whole at depth 0 only, resolution through `_resolve`,
  the lock taken — each caught by exactly one of them; the ending
  hook's order, which they left unpinned, is pinned since review 2 (§8).
- **After review 2** (2026-09-29): the ending rerun test renders inside
  the round trip (A1); `_tool` and `read_only` (§2.2, the owner's O2 and
  O3); RECALL.md §2's account of the root's three forms corrected to
  PRINT.md §6's (O1); the records of A2 and A3.
- **Told to the owner, not done here:** node_classes/THEOREM.md §8's
  "discarded before the operation runs" is the other session's draft and
  follows PRINT.md §4's new sentence; TOOL_SCHEMAS §5 still lists
  `status`, which is the construct work's to remove.

## 8. Reviews

- **Review 1** (2026-09-28; six challengers, three fresh defenders per
  finding, one judge, Opus 5.5 at xhigh, in English; the brief
  `BRIEF1.md`, the ruling `ruling1.json` and the material
  `material1.json` in the session's scratchpad `recall_review/`):
  READY_WITH_FIXES, one fresh reader over the revised plan. Twenty-five
  findings, merged into twenty items: nine author items, all applied
  above — the no-id wire case
  had the theories at depth 1 (they are at depth 2, so no error block);
  its second `edit` could not fail; the success test's expected value
  was the entry's own expression; `Sessions` and RECALL.md §3's refusal
  block were unpinned; RECALL.md §2's example was read by no test; §4
  named no sentence `recall` makes false; §2's "never inside one" was
  false — one owner item, approved (§1 item 5, §2.1), and ten rejected
  (clearing the seen set over the wire, a second wire `recall` for the
  depth-1 rule, a `get("node_id", "Sessions")` entry, dropping RECALL.md
  §3's copied lines, a new stub class, contrived no-lock scenarios, a
  restatement called a defect, and three mistaken claims).
- **The re-read** (one fresh reader, Opus 5.5, `REREAD_BRIEF.md`,
  `reread1.json`): PASS_WITH_EDITS — every author item and O1 verified
  applied, every literal line of §3 rebuilt with the test files' own
  helpers and found right; four edits, all applied: two literals wrapped
  across source lines, the hook comment's rewrite named in full, the
  example's test named.
- **The read of the diff** (one fresh reader, Opus 5.5,
  `diffread1.json`): PASS_WITH_EDITS — the entry, the hooks, the tests
  case by case and the documents verified, five mutants each caught by
  one new test; two re-wrapped paragraphs (PRINT.md §4, TOOL_SCHEMAS'
  intro), applied, and the notes §7 records.
- **Review 2, the implementation** (2026-09-28/29; the same recipe over
  the landed diff; `BRIEF_IMPL.md`, `ruling_impl.json`,
  `material_impl.json`): ACCEPT_WITH_FIXES, one fresh reader over the
  fixed diff. Twelve findings: three author items — the ending hook's
  order pinned by no test (three mutants passed the suite; three lines
  in the ending rerun test catch all three), two records set right —
  four owner items, all approved 2026-09-29 — RECALL.md §2's root forms
  (a transcription error, corrected), the read-only hint (§1 item 6),
  the builder (§1 item 7), the commit's scope (§7) — and five rejected
  (the plan's `copy_to` sentence, SESSION_AND_THEORY's "held until the
  operation runs again", `Sessions` in the `ProtectedNode` row, the
  `status` sentences that are the construct work's, and a `_call` helper
  for the hooks, which would not make the mistake impossible).
