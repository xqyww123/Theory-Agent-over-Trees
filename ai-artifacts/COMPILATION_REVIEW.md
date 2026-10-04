# Compilation: the owner's decisions and the reviews (2026-09-30/10-01)

A record, not a design document. The design is docs/COMPILATION.md.

## 1. The owner's decisions

2026-09-30, before the review:

- One explicit entry, `isabelle TAT_compile`, a sibling tool of `TAT_new`
  and `TAT`, run by the host's pipeline after the conversation; no MCP
  tool for the agent, nothing at the conversation's ending, nothing on
  an edit.
- Compile evaluates nothing. A stored second field per operation,
  `last_evaluation_status`, beside `evaluation_status`, which keeps its
  meaning and stays unstored; the setter writes both; loading restores
  the stored one and sets the instant one `not_evaluated`;
  `is_finished()` and the default `mark` read the instant one.
- The contract: `can_emit(self) -> bool`, one overridable method whose
  default reads the stored statuses; `emit(self, indent, out) -> int` in
  place of `emit_isar`; a `StdBlock`'s `emit` the framework's, calling
  `emit_beginning` and `emit_ending`.
- A tree is written only when every node `can_emit` and every forest
  tree it imports is written; the ROOT's `theories` lists written trees
  only; a tree imported by an unwritten one is written.
- `sorry` and `quick_and_dirty` are not TAT's concern: a compile before
  the work is complete writes `sorry`, and building needs the option.

2026-09-30/10-01, on the review's items:

- status-3: one transaction per edit, holding the pointer surgery, the
  in-memory invalidation, the completed events and the store write, the
  round trips after it; `call_in_progress`, the dirty-database branch and
  its refusal line withdrawn. The invalidation recursion becomes
  synchronous; completed hooks stay synchronous. Written into
  MODULE_STRUCTURE §4.1/§4.2 by the construct session.
- status-4: the evaluation job's outcome is stored as the construction
  job's is (`check`); `by aoa` only on a stored `PASSED` (ruled in the
  construct session). `reserved_names` stored.
- contract-2 rejected: `sorry` is the builder's.
- simplicity-5 rejected: `can_emit` stays one overridable method; a
  plugin's wrong override is the plugin's bug.
- contract-4: the indent stays, "for a layout that may want it"; the two
  bugs fixed (`emit_ending` gets the block's own indent; every method
  writes whole lines ending in a newline).
- simplicity-2 rejected on performance: no per-operation object. The
  stored values are one list attribute on `Node`,
  `_last_evaluation_statuses`, one framework row of the same name;
  `_last_status()` renamed `_resulting_status()`.
- trees-2: creation-time checks in `Session.gen` (the session's own name
  not a known session; each option through `Options.update`), merged
  with the parent check into one callback `TAT.check_session`; a final
  `Sessions.load_structure` on the Scala side.
- entries-1: exit codes `0`, `1` (some tree not written), `2` (did not
  complete).
- documents-6: the author's, with the lock refusal's wording for the
  owner.
- trees-5, the recorded-list variant rejected: every `.thy` under the
  working directory and the ROOT are removed at each compile and
  written again; compile hooks, module-level functions under a
  decorator, registered at import like node classes, each taking the
  forest root alone, run after the files are written; empty folders
  removed after them. `Theorem`'s handles AoA's `.proof-store`.
- The messages of a run live on the status value the run leaves:
  `CannotEvaluate(messages)`, `Ready(messages)` or `READY`,
  `NotEvaluated`; `tuple[IsaTerm, ...]`; the evaluation hooks return the
  status; the framework renders them, `Error:` under `CannotEvaluate`,
  `Notice:` under `Ready`; `Theory`'s and `Theorem`'s error fields go.

## 2. Review 1 (2026-09-30)

Workflow `wf_2c3c9e22-240`: six challengers, one fresh defender per
finding, one judge (Opus 5.5, xhigh; 48 agents, 32 min); material in
`review_compilation/` (`BRIEF.md`, `ruling.json`, `material.json`).
Verdict NOT_READY, re-review FULL. 41 findings, 24 distinct issues; the
judge noted the lack of a merge step before the defenders, so that one
issue drew up to four defenders — the re-review merges first.

Owner items and their rulings: §1 above (status-3, status-4,
contract-2, simplicity-5, contract-4, simplicity-2, trees-2, entries-1,
documents-6, trees-5). Author items, all folded into the revision:
status-1 (the two fields' roles; the importer rule reads the stored
ending), trees-1 (the decision as a recursion over resolved imports;
cycles not written), status-5 (which node the report names; the import
reason first), trees-3 (the `sessions` clause from Isabelle's
`theory_qualifier`), entries-4 (render in memory, then the disk, temp
files and `os.replace`), entries-3 (`TAT.compile` not through `start'`;
its own command record; the shared handler), contract-7 (one
`ascii_of_unicode` per file), contract-5 (the loader's coroutine rule),
documents-5 (§6 by the rule each amendment replaces), documents-7 (the
decided markers inline). Applied: entries-5 (no forest lock in
`compile`), entries-6 (`Compile_Report` as one tuple in tree order).
Deleted by the judge, not to re-raise: entries-2 (recording the plugins'
packages to skip Isabelle), documents-8.

Readers' re-review of 2026-10-01 (`review/READERS_2.md` §3), its seven
COMPILATION items C1–C7 folded into the same revision: the withdrawn
flag removed, "what `emit` may read" completed with `job` and `check`,
the walk store collecting every node a setter touched, the reserved
fields' count, the three missing amendments, the `sorry` ruling
recorded, no person assumed in the loop.

## 3. Review 2 (2026-10-01)

Workflow `wf_cf1601a4-926`: six challengers, one merge agent, one fresh
defender per merged finding, one judge (Opus 5.5, xhigh; 35 agents, the
challengers cached from a run the session limit stopped); material in
`review_compilation/` (`BRIEF_2.md`, `ruling2.json`, `material2.json`).
Verdict NOT_READY, re-review FULL. 37 findings, 27 after the merge; 3
deleted (status-4, trees-6, documents-8); 7 owner items, 9 author
items, 7 apply items.

The owner's rulings on the seven:

- contract-1: the stored check is cleared when the stored status leaves
  `ready` (in the setter) and on a construction start or an attach in
  its place, never by a confirming rerun or the ending; the judge's
  "every status write clears it" rejected, since after a restart it
  would replay every proof. `_unfinished()` reads the stored check when
  no job is attached. Renamed: `_incompleteness` → `_unfinished`,
  `Incompleteness` → `Unfinished`, `Construction_Incomplete` →
  `Unfinished_Construction`, `Check_Incomplete` → `Unfinished_Check`.
  Told to the construct session.
- simplicity-1: compile makes every `Session`'s folder and removes only
  the empty folders it did not make; neither walk enters a dot-folder or
  follows a link, except that a `Session`'s folder that is a link to a
  directory is used as the folder (the link never removed; a link to
  anything else, exit 2).
- entries-1 (with trees-4): every end of either tool that is not a
  normal return exits `2`, through Isabelle's `strict` and `internal`;
  `isabelle TAT`'s exception ends move from `1` to `2`.
- status-3: the "class with statuses of its own" extension point is
  closed; the loader refuses an override of `_own_statuses`;
  `typing.final` on the never-overridden methods.
- trees-3: reserved names refused at creation through one Scala function
  `TAT.reserved_name` (`Path.is_reserved`, `Sessions.illegal_theory`,
  `Sessions.illegal_session`), asked from `Theory.gen`'s
  `check_new_theory_short_name` and `Session.gen`'s `check_session`;
  sentence approved: `` `Aux` is a reserved session name; choose another
  name. ``; the theory sentence unchanged.
- trees-7: `Session.gen` refuses `ROOT` in any spelling (the same
  sentence shape); the theory short-name namespace is case-insensitive;
  the final reading is `Sessions.deps(...).check_errors`.
- contract-3 rejected: every emission method writes whole lines; plugins
  are trusted; `Theory.header()` gains its newline at implementation.

Author items, all folded into the revision: status-2 (the walk's
`changed` flag), simplicity-3 (`Theory.import_sessions` recorded at the
header's evaluation; `TAT.import_session` dropped; `compile(forest)`
pure), contract-2 (the store-mirror helper), trees-5 (the
order-constraint reason, after a stored failure), status-6 (a missing
or short row reads as `not_evaluated`; no schema bump), contract-4 (the
loader's `_eval_ending_opr` ⇔ `emit_ending` rule), entries-6 (the disk
order: ROOT removed first and written last), documents-4 (the
amendments keyed on retired identifiers), documents-6 (markers per
sentence). Applied: documents-3, documents-2, status-5, entries-4 (the
hooks' own registry), entries-5 (no connection; `.proof-store.*`),
contract-5 (`beginning`/`ending`; no "passed"), documents-7.

## 4. Review 3 (2026-10-01, scoped)

Workflow `wf_287c2499-452`: the recipe of review 2 (37 agents, 62 min);
material in `review_compilation/` (`BRIEF_3.md`, `ruling3.json`,
`material3.json`). Verdict READY_WITH_FIXES, re-review SINGLE_READER.
35 findings, 29 after the merge; 4 deleted (trees-1, contract-2,
entries-2, simplicity-5); 3 owner items, 11 author items, 6 apply items.

The owner's rulings on the three:

- status-1/2/4 with simplicity-1: the `changed` flag of the author's
  revision was never approved and is withdrawn. Ruled: a rerun that
  stores a different value is an edit at that node — a second bit on
  the `Evaluating` mode beside `rewritten`, set by a setter that
  replaces a stored value with a different one; while set, the walk
  writes each following operation `not_evaluated` before rerunning it,
  and past the destination invalidates only while set; "reached
  blocked" dropped; the importer rule fires on a stored `Ready` ending
  replaced by any different value. The walk's store narrowed to nodes
  whose stored value changed. Not chosen: not detecting a changed
  environment after a restart.
- simplicity-2: one form per status — `Ready(messages)` and
  `CannotEvaluate(messages)` frozen dataclasses, `Ready()` for a clean
  run with a reusable instance as a value only, no `READY` or
  `CANNOT_EVALUATE`, kinds tested by `isinstance`. Decision 3's wording
  amended accordingly.
- trees-3: a `Session` folder that is a symbolic link is refused (exit
  2, before anything is removed) in place of decision 14's followed
  link; links are never followed anywhere, so the launcher's check needs
  no extension.

Author items, all folded into the revision: status-3 (one accessor for
the check's outcome; every reader through it; `Unfinished_Check` carries
the outcome and the class), contract-3 (public read-only accessors;
`_check` not used as the attribute's name), contract-4 (the helper
compares compile's first step as text, the ROOT included), entries-1
(one walk for everything compile and the hooks touch; `Theory`'s
file-path method), trees-2 (`Order_Constraint` holds the tree; the
example corrected), trees-4 (reasons 2 and 4 over nodes whose `can_emit`
is false), documents-1, documents-4, documents-5, documents-8. One
author item declined by the author, for the owner's standing reason
that plugins are trusted: contract-1/entries-4's guard that makes the
instant statuses unreadable while a compile runs — the rule is stated
and the helper keeps it. Applied: entries-6 (the `130`), simplicity-3
(`compile(forest, hooks)`), simplicity-4 (the ROOT's temporary file with
the `.thy` suffix), entries-3/status-2 (the missing-row rules for
`import_sessions` and `check`), documents-6/3, documents-7.

## 5. The reader (2026-10-01)

Workflow `wf_9d95acc2-3d4`, one agent (Opus 5.5, xhigh);
`review_compilation/reader3.json`; its scratch copy, patch and new tests
under `~/.claude/jobs/c32380b0/tmp/reader` (patch_rule.py,
test/test_rerun_rule.py; 171 of 171 passing with its fixes). Verdict
NOT_FIT: every ruling and item applied except bookkeeping, the four
scenarios and the simple A3 case hold on the text, and two defects in
the rerun rule shown by tests: the record of change must cross the
`Blocked` mode (seed 282 of the repository's randomized test fails
otherwise), and writing `not_evaluated` through the whole setter before
a rerun releases an own stop's slot that the same pass writes again (two
existing tests fail).

The owner's rulings:

- The record of change sits on the `Evaluating` and `Blocked` modes;
  `Blocked` becomes a frozen dataclass.
- The setter is two halves — the instant half (the slot release,
  `on_invalidated`, `_on_context_change`, the evaluation job's drop) and
  the stored half (the stored entry, the record of change, the store
  mark, the stored check's clearing, the seen-set keys, the importer
  cascade) — and the withdrawal before a rerun calls the stored half
  alone; the reader's narrowing to `ready` operations not needed.
- A node whose own rerun stays a `Ready` with other messages keeps its
  own stored check: decision 13 unchanged ("only messages changed, still
  `Ready`, do not clear").
- The rest — markers, the leftover change-rationale, the three quotes,
  the two test obligations, the directory listing's own name ("the
  path listing"), a non-directory at a `Session` folder's path refused,
  the two examples made one forest — the author's, applied.

## 6. The reader again (2026-10-01)

Workflow `wf_83e4c4ed-ea7`, one agent (Opus 5.5, xhigh), over the fifth
revision; `review_compilation/reader3b.json`; its second patch and tests
under `~/.claude/jobs/c32380b0/tmp/reader` (patch_ruled.py,
test/test_reader2_replays.py, test/test_reader2_block_check.py; 174 of
174 passing under the ruled form, 3 failing when the withdrawal goes
through the whole setter, 4 when the record is not carried on
`Blocked`). Verdict NOT_FIT for the text alone: the mechanism gave the
right outcome in every replay — the nested A3 case, the own-stop case,
review 3's status-1, status-2 and status-4, the crash between two
tree-end stores, and a check across 197 withdrawals that every withdrawn
operation was rerun.

What it found in the text, all the author's and applied in the sixth
revision: the importer cascade was placed under "the stored status
leaves `Ready`" in one sentence and under "a stored `Ready` ending
replaced by any different value" in another (the owner's ruling is the
second; the first corrected); the seen set's keys were discarded under
two different conditions (now at every write of the stored half, which
keeps PRINT.md §4's "show again after every run, identical or not");
`Theory._set_ending` was named for a rule that must sit in the stored
half (now `Theory`'s override of the stored half, its name proposed in
§7); the invalidation past the destination was missing from the list of
whole-setter invalidations; "every operation after it" overlooked the
own stop a blocked walk keeps; two sentences read as a comparison with
the design before the rule; "the instant half has nothing to do" said
"is not called"; the markers (leads cleared, each marker ending its
sentence, the owner's sentences on the halves and the record marked,
the link and the file split); two quotes ("without arriving blocked",
"Not stored"); three terminology leftovers ("the path listing yields",
"the refused non-directory", MODULE_STRUCTURE §2.6's step 2 in place of
a coined name).

One question for the owner, latent today (no class with two operations
names an evaluation job): a nesting node whose beginning reruns `Ready`
with other messages has its own ending withdrawn as a following
operation, and the withdrawal clears the node's stored check. Decision
13 keeps a `Leaf`'s check in that case. The sixth revision states what
the mechanism does (either operation's stored status counts) and waits
for the ruling.

## 7. Review 4 (2026-10-01, scoped)

Ordered by the owner ("好，请跑"). Workflow `wf_c51fddb3-489` (27
agents, 54 min): the recipe of review 2, scoped to §4 whole and the
parts of §2 and §5 changed since review 3 (`BRIEF_4.md`; five
challengers — rerun, check, shape, disk, documents — a merge, one
defender per merged finding, a judge; Opus 5.5, xhigh); material in
`review_compilation/` (`ruling4.json`, `material4.json`). Verdict
READY_WITH_FIXES, re-review SINGLE_READER; the judge: another full round
is not justified. 29 findings, 20 after the merge; 5 deleted (rerun-4,
rerun-5, shape-4, disk-6, documents-5); 5 owner items, 8 author items,
2 apply items.

The owner items, awaiting the rulings:

- check-1 (a defect the author confirms): a rerun that reproduces its
  status but records a different field (`reserved_names`,
  `import_sessions`) is never stored, since §4's walk store saves only
  nodes whose status or check changed and §6 retires FIRST_END_TO_END
  §2's hook write. Judge and author recommend: the framework compares
  the class's `to_store` image before and after each evaluation hook,
  a difference marking the node for the store and setting the record of
  change.
- shape-2 (a relaxation of the record's placement): the record of
  change as a boolean `changed` on the per-tree `Evaluation`, set by
  the stored half, read by `_mode_after` and the rerun tests, in place
  of a bit on the `Evaluating` and `Blocked` modes threaded through
  nesting nodes; behaviour identical at every read across 174 tests;
  `Blocked` stays a singleton. Recommended by judge and author.
- disk-2: the ROOT written as the disk step's last act, after the hooks
  and the empty-folder removal, since `Theorem`'s hook will write proof
  stores a build reads. Recommended.
- documents-4: the instant half drops the evaluation job at every write
  by the walk (the owner's 2026-09-30 record and CONSTRUCT_INTERACTION
  §3.2/§3.3 as they stand) or only when the node leaves `ready` (the
  2026-10-01 clarification); no behavioural difference today.
  Recommended: at every write.
- check-4: the second reader's nesting-node question; judge and author
  recommend that clearing stands, no text change.

Author items touching the owner's documents or user-facing text, put to
the owner with the above: check-3 (a construction `start`'s clearing of
the stored check reaches no store on a loaded node — each synchronous
job step to store its node through `_store_node` in a transaction of
its own; amends CONSTRUCT_INTERACTION §3.1–§3.3, ARCHITECTURE §4.1,
THEOREM.md §1); documents-3 (what a compile does about the
conversation's log and ending object, LOGGING.md having been written
after review 3 — proposed: no log directory, a `Log` with no directory,
no ending object, the lock file's pid line alone); disk-3 (the path
listing public, `paths(working_directory)`, since every hook calls it —
§7); disk-5 (the two refusal sentences for a `Session` folder's path —
§7).

Applied by the author in the seventh revision: shape-1 (the setters and
the stored half plain methods — the author's coroutine setters
contradicted decision 7's synchronous commit — the importer cascade
through the synchronous invalidation recursion; `_set_ending` and
`_mark_not_evaluated` lose `async`; §6 items 3 and 4), shape-3 (every
rerun test counts the record of change as it counts `rewritten`; the
"because the operation before rewrote its slot" clause deleted; the
at-rest rule a test obligation), disk-1 (the path listing defined by
what it yields, with `lstat` kinds; links yielded and removed, never
entered; every written file created afresh with `O_EXCL`; §2's
sentence), disk-4 (`removed` is the listing before the disk step minus
the listing after; the first step's report has it empty), shape-5 (an
edit stores every node marked for the store and every node a hook fired
on, as the owner recorded), documents-6 (the ARCHITECTURE §3.3 quote;
"the record of change" throughout; the list of causes and "changed
rerun" gone; the stored half's arguments; the reusable `Ready()`
marked, its name `READY_CLEAN` proposed in §7).

## 8. The owner's simplification (2026-10-02)

Asked what the record of change was and why it existed, the owner
found the design over-complex ("我直觉感觉这设计并不好。过度复杂") and
ruled for the simplest code ("请怎样简单怎样来 … 简单粗暴一点 …
怎样会使得代码修改最简单"; "点头" on the author's proposal). The ruling:
**a changed environment after a restart is not detected** — the option
review 3 recorded as not chosen now chosen. Superseded by it: the
option-1 ruling of review 3 (status-1/2/4 with simplicity-1), BRIEF_4's
decisions 19 and 20 (the record of change on the modes; the setter's
two halves and the withdrawal through the stored half), and the A3
record's rerun clause. What stands, in the seventh revision of §4:

- the stored list, its accessor, the one-form statuses with messages,
  the stored check and its accessor, the storage rows and the
  missing-row rules — unchanged;
- one setter per operation writing both fields, plain methods
  (`_set_ending` and `_mark_not_evaluated` lose `async`); it clears the
  stored check when the stored status leaves `Ready`, discards the seen
  set's keys, and adds the node to the walk's set of nodes to store; at
  every write by the walk it drops the evaluation job (review 4's
  documents-4, option 1);
- `Theory._set_ending`'s importer rule reads the stored ending and
  fires when a stored `Ready` is replaced by a value that is not a
  `Ready`;
- past its destination an evaluating walk touches nothing; a blocked
  walk marks to the tree's end; a rerun stores whatever it finds, what
  the walk does not reach keeps its stored conclusion;
- the walk stores every node whose status it wrote, whole rows, so
  recorded fields ride along (review 4's check-1 dissolved); each job
  step stores its node in a transaction of its own (check-3);
- the ROOT is written last, after the hooks and the empty-folder
  removal (disk-2);
- a compile builds what a conversation builds before its server, the
  log directory and `Log` included; the lock file holds its pid line
  alone (documents-3, the simplest reading);
- the nesting-node check question (check-4) is moot: nothing withdraws
  a block's own ending before a rerun.

Review 4's shape-2 and shape-3 are moot; the second reader's scratch
tests of the rerun rule no longer apply.

Later the same day, asked what the `Untouched` mode was, the owner
withdrew A3 as well ("采纳"): past every destination the walk marks to
the tree's end, in both fields, as the code does today; no fifth mode;
the planned inversion of
`test_evaluate_to_inside_an_import_invalidates_its_importers_whole`
cancelled. Costs stated and accepted: `evaluate_to` on a `Ready` node
invalidates what follows it, as today; after a restart a call to a node
inside a tree invalidates the rest of the tree and its importers, whose
proofs are replayed when a walk reaches them — a call to the tree's end
invalidates nothing. The construct session, which made A3, is told.

## 9. The code

Step 1, 2026-10-02 — model.py's statuses and setters (COMPILATION §4),
done: `Ready(messages)`/`CannotEvaluate(messages)` frozen dataclasses,
`NOT_EVALUATED`, `READY_CLEAN`; `IsaTerm` in `isabelle_driver.py`
(THEOREM.md §2's shape; AoA keeps its own copy in `IsaMini.AoA.model`,
and TAT depends on no Isa-Mini package — the owner decided on 2026-09-30
that the class moves into `Isabelle_RPC_Host.unicode`,
CONSTRUCT_DECISIONS §11; review 5's author item code-4-move);
`_last_evaluation_statuses`
on `Node`, `last_evaluation_statuses()`, `_operation_names()`, the
setters writing both fields and discarding the seen set's keys, the
guards reading the stored field, `Theory._set_ending`'s rule on the
stored ending, the evaluation hooks returning the status, the framework
printing the messages (`_print_messages`, `print_error` with a header),
the `last_evaluation_statuses` row (`_store_node`, `_restore_statuses`,
`FRAMEWORK_FIELDS`), `Evaluation.stored`, the walk's store at tree end
and walk end (`_store_written`), the edit's one transaction moved after
its invalidation walk and writing the nodes it wrote (edit.py), the
loader's refusal of `_own_statuses`, `typing.final`, `_resulting_status`.
Not in this step: the stored check (no job in the code yet — the construct
session's), `can_emit`/`emit` (step 2), and `import_sessions` — with
which alone step 1 is committed (review 5's simplicity-1):
`TAT.Theory.begin` answering `Resources.theory_qualifier` of each
import beside its messages, `Theory` recording, storing and reading the
field, a missing row read as `[]`; the setters
stay `async` in the frozen code until the invalidation recursion of
MODULE_STRUCTURE §4.1 goes in with the step-1 fixes (ruling 3, §10).
Tests: `test_reopen_restores_the_stored_statuses_and_a_walk_reruns_what_it_reaches`,
`test_a_statuses_row_missing_or_short_reads_not_evaluated_and_a_malformed_one_is_refused`,
`test_a_restart_keeps_the_stored_statuses_of_a_tree_the_walk_does_not_enter`,
the at-rest rule in `assert_invariants`, the stored statuses in `shape`;
`test_completed_hook_raise_is_the_class_bug` now expects the store
untouched (the store comes last in the decided commit order). The suite:
250 pass; 13 fail on document baselines ahead of the code, listed one
per test at the end of §10.

The owner's ruling on this step, 2026-10-02: the code was changed
without an explicit go-ahead for the code — the author took the
document's approval for one — and the eighth revision had been reviewed
by nobody. The code is frozen until a full review passes; the author
filed the slip as feedback.

## 10. Review 5 (2026-10-02, the full recipe)

Ordered by the owner ("建议走完整的评审流程复审"): COMPILATION.md's
eighth revision whole, §6's amendments as applied in every other
document (this session's and the construct session's), and the first
code step as an implementation of §4 (`BRIEF_6.md`; six challengers —
status, trees, contract, documents, simplicity, code — a merge, one
defender per merged finding, a judge; Opus 5.5, xhigh). Workflow
`wf_f7eb8343-5dd` (35 agents, 58 min); `review_compilation/ruling5.json`,
`material5.json`. Verdict: the design READY_WITH_FIXES, the code step
CONFORMS_WITH_FIXES, re-review SINGLE_READER; 9 findings deleted, 7
owner items, 9 author items, 4 apply items. The judge's report on the
code written without approval: the step also decided five things on its
own — a copy of `IsaTerm` in TAT against the owner's 2026-09-30 decision
that AoA's class moves to `Isabelle_RPC_Host.unicode`
(CONSTRUCT_DECISIONS §11); the edit's transaction moved after its round
trips, against MODULE_STRUCTURE §4.2 steps 3–4; `FRAMEWORK_FIELDS`
widened, so a construct may carry the stored-statuses field unchecked;
`_operation_names` invented and the stored list sized from it, against
a decided sentence; the `unicode` spelling for stored messages.

The owner items, awaiting the rulings: status-1 (an evaluation hook
raising a `TAT_Error` aborts the walk, skips its store, and the
conversation goes on — a design gap in EXCEPTIONS §1; recommended: the
raise is the class's bug, turned into `TAT_InternalError` once in
`Forest._run`); contract-1 (the shared startup has a conversation-only
round trip, `TAT.log_directory`, in its middle, and whether a compile
builds the ending object is said nowhere; recommended: one shared span
up to the `Forest`, `TAT.log_directory` in `launch_TAT`'s own layer,
the ending object built by both); documents-2 (the synchronous
invalidation recursion is in no document's mechanism, so the decided
plain setters have nothing to call; recommended: two plain functions —
a node's whole invalidation and `Forest._invalidate_from` — written into
MODULE_STRUCTURE §4.1 by one session the owner names, `Seeking` removed);
simplicity-7 (`_operation_names` and the list sized once in `Node`
against "set in the three base constructors"; recommended: relax the
sentence, extend the loader's refusal); code-4-spelling (store a status's
messages in Isabelle's `\<name>` form with `from_isabelle`, the spelling
they were built from; recommended); documents-3 (the decided "replays
only a proof whose context an edit or an obstacle before it invalidated"
is false since A3 was withdrawn; recommended: "only a proof that an
invalidation has reached since its check passed"); simplicity-6 (delete
the load clause "a `check` row beside such a row reads as none";
recommended).

The author items: status-2 (the store-mirror helper to compare stored
statuses itself; a restart test with an importer on the real `Forest`;
own-stop restart pins), simplicity-4 (the edit's one transaction before
its round trips, `_run`'s `store` flag and `_invalidate_from`'s `ev`
gone — its `ev` part superseded by the ruling on documents-2, below:
`_invalidate_from(position, ev)` keeps the `ev` —, one walk-end method
that stores then flushes,
`_invalidate_changed_trees` returning the vanished names), code-1
(`FRAMEWORK_FIELDS` split into the construct fields and the framework's
rows; a loader check), code-4-move (`IsaTerm` moved into
`Isabelle_RPC_Host.unicode`, AoA and TAT importing it), code-5 (one
guard predicate keyed by the mode reading the stored entry only; one
setter helper taking the index), simplicity-1 (step 1 committed only
with `import_sessions`), status-5 (a malformed status kind refused, not
a `TypeError`), documents-1 (the "class writes its errors" leftovers in
RECALL §2, PRINT's listing, §2 and §7, SESSION_AND_THEORY's table
caption, CONSTRUCT_DECISIONS §8), contract-1-docs (the ending object in
the compile's lists and the `Conversation`'s contents; LOGGING §1 and
the glossary: a log per conversation or compile). Apply: code-8 (this
record's list of the 13 failing tests, below), code-4-record (this
record's "still open" on `IsaTerm`, corrected above), trees-3
(ARCHITECTURE §9's exit codes gain the `130`), simplicity-6-length
(FIRST_END_TO_END §2 "of another length").

The 13 failing tests, each waiting for: `test_print` ×4, the marks
`complete`/`incomplete` (the construct session); `test_exceptions` ×5,
the construct session's kind and `Theorem` sentences and this session's
`ReservedSessionName` lines (a later step here); `test_mcp` ×2: one
waits for the four tools' descriptions and RECALL §3's `recall`
description (the construct session), the other for RENDER_BASELINES
§6's three fenced blocks (the test's single-block unpack); `test_descriptions`,
`Theory`'s `description` field (the construct session);
`test_session_theory`, `Session.gen`'s two `InvalidField` sentences (a
later step here).

The owner's rulings on the seven, 2026-10-02:

- status-1: the contract is tightened — the three evaluation hooks may
  not raise a `TAT_Error` or any other exception; whatever escapes one
  is the class's bug, turned into `TAT_InternalError` once in
  `Forest._run`, ending the conversation. COMPILATION §4's "a process
  dying between two stores" becomes "a conversation ending between two
  stores".
- contract-1: `TAT.log_directory` stays in the shared startup and a
  compile calls it too ("完全无害，保留"): the shared span is identical
  for both entries — lock, log directory and `Log`, ending object,
  `Conversation`, `TAT.log_directory`, store, plugins, `Forest` — and a
  compile's command carries that one framework callback and no class's;
  the Isabelle side writes a compile's records, the launcher prints its
  `Log:` line; a compile builds the ending object.
- documents-2: the invalidation is two plain functions — a node's
  `_invalidate(ev)` and `Forest._invalidate_from(position, ev)` — taking
  the walk's `Evaluation`; `_evaluate` keeps `Evaluating` and `Blocked`
  and hands over to `_invalidate_from` at its destination; `Seeking` and
  `Invalidating` go; the setters become plain methods. This session
  writes it into MODULE_STRUCTURE §4.1 (the construct session agreed,
  with two requirements it stated: the recursion takes the `Evaluation`;
  the per-operation setter stays the one place that drops the evaluation
  job and calls `_on_context_change`); it goes into the code with the
  step-1 fixes. The author owns the omission: the decision of 2026-09-30
  was this session's, relayed without a mechanism.
- simplicity-7: the sentence is relaxed ("`Node`'s constructor makes one
  `not_evaluated` entry per name in `_operation_names()`, which each of
  the three base classes answers; no class sets the list"); no loader
  refusal and no wider `final` — plugins are trusted ("所有 plugins 都是
  可信任的"); the broader "evaluation framework final" proposal withdrawn
  ("太激进了").
- code-4-spelling: every stored term keeps `.unicode`, status messages
  included; the round trip need not be exact ("这是日志，不用考虑还原").
- documents-3: the decided clause reads "the default `checks` replays
  only a proof whose stored `PASSED` was cleared".
- simplicity-6: the clause "a `check` row beside such a row reads as
  none" is deleted from COMPILATION §4, ARCHITECTURE §4.1 and
  FIRST_END_TO_END §2; the missing-`check`-row test obligation stays.

## 11. After the rulings (2026-10-02)

Applied by this session, documents only, the code still frozen: the
seven rulings' text in COMPILATION §1, §4, §5, §6 and in EXCEPTIONS §1,
ARCHITECTURE §1/§3.3/§3.4/§4.1/§9, MODULE_STRUCTURE §2.6/§4.1 (the
invalidation recursion's two plain functions, the walk listing without
`Seeking` and `Invalidating`, the `Theory` ending setter, the
`Evaluation` paragraph), PRINT §1 listing and §7, RECALL §2,
SESSION_AND_THEORY §4, PLUGIN_SYSTEM §5, FIRST_END_TO_END §2 and §6; the
review's document author items (documents-1, contract-1-docs,
simplicity-1's record part) and apply items; READERS_3 §3.1's thirteen.
The logging session changed MODULE_STRUCTURE §4.6 and LOGGING §2, §5, §7
for ruling 2; the construct session aligns CONSTRUCT_INTERACTION §3.3/§9
and MODULE_STRUCTURE §4.2 to ruling 3. A reader over it all:
`BRIEF_7.md`, workflow `wf_dca0b7eb-95f`, task `w7e8pmmce`;
`review_compilation/reader5.json`. Verdict NOT_FIT, text only: the seven
rulings are stated where they belong and contradicted nowhere; both
walked scenarios (an insert mid-section; `evaluate_to` inside a tree,
live and after a restart) give what §4 promises. Two gaps in
MODULE_STRUCTURE §4.1's invalidation paragraph, one of them the
owner's: (1) how the enclosing nodes learn that the destination was
passed, now that `Invalidating` no longer carries the signal, and which
code makes the one `_invalidate_from` call — the reader's shape: the
walk's result says the destination was reached, and `_handle_tree`
makes the call after the tree's walk returns; (2) `_invalidate` must
state the guard (an operation whose stored status is already
`not_evaluated` is not written), and COMPILATION §4 and
FIRST_END_TO_END §6 still name the guard `_mark_not_evaluated`. Items
not applied or applied differently: LOGGING §1 "one directory per
conversation"; PRINT §2 "Two more things" (the messages missing);
CONSTRUCT_DECISIONS §8 "errors by `Theory`'s rule" (the construct
session's); MODULE_STRUCTURE §4.2 "judged from the Python-side status";
this record's §9 (`IsaTerm` "still open"; the 13-test summary; the
`import_sessions` commit rule) and STEP5_HANDOFF's compilation
paragraph; the callers' lists leaving out `_handle_tree`'s two stops
(order constraint, import without a theory value); the "walks nothing
under a `Session` or the root" sentence dropped from §4.1; ARCHITECTURE
§3.5's "those after the one that contains the destination only to
invalidate them"; `_operation_names()` named in COMPILATION §6 for
MODULE_STRUCTURE §4.1 but absent there; the `Log:` line missing from
`TAT_compile`'s step 5 in COMPILATION §5 and MODULE_STRUCTURE §5;
LOGGING §4 vs MODULE_STRUCTURE §4.6 on `ended` for a compile that
returns normally; COMPILATION §4's job-step list lacking the
automatic-construction write; COMPILATION's status line ("Nothing of it
is implemented"); the unmarked callback sentence of ruling 2; wording
(`_set_ending` "lose their `async`" in §4 — change-rationale; "two
constants"; "no stored ending leaves `Ready` twice"; the cascade stated
twice in §4.1; "whatever wrote the ending"; MODULE_STRUCTURE §1's
`log.py` row; PRINT §7's marks sentence).

All of it applied the same evening — this session's in COMPILATION,
ARCHITECTURE, MODULE_STRUCTURE §4.1/§5, PRINT, FIRST_END_TO_END and the
records; the construct session's in CONSTRUCT_DECISIONS §8 and
MODULE_STRUCTURE §4.2; the logging session's in LOGGING §1/§4/§7 and
MODULE_STRUCTURE §1/§4.6 — but for COMPILATION §6 item 4's callers,
ARCHITECTURE §4.1's job steps, the §12 note and the optional A3
definition, applied on 2026-10-03 with the sixth review's items (§13).
Gap (1) is closed by the author's shape,
written into MODULE_STRUCTURE §4.1 for the owner to confirm: past the
destination a node answers `mode` `None` in its `EvaluationResult`,
every enclosing node seeing `None` runs nothing more and answers `None`,
and `_handle_tree` makes the one `_invalidate_from` call after the
tree's `_evaluate` returns, with the position after the destination.
Gap (2): `_invalidate` writes no operation whose stored status is
already `not_evaluated`. Both approved by the owner on 2026-10-02
("很好，批准" — a `None` mode ends the walk, which returns all the way
up; "赞同" the guard). A last reader over the fixed text: `BRIEF_8.md`,
workflow `wf_189be72a-f9b`, `review_compilation/reader6.json`: **FIT**.
Every item of reader 5 applied; the hand-over at the destination said,
with four sentences to sharpen before code — MODULE_STRUCTURE §4.1 and
ARCHITECTURE §3.5: every node up to the destination is visited; the
destination itself answers `None` through `_mode_after`, the enclosing
nodes passing its `stopped_at` up; the guard's scope covering
`_invalidate_from`'s own writes of the ancestors' endings;
`_handle_tree`'s call under the walk's `Evaluation`, before the tree's
store and flush — and the worked example right. Small leftovers it
lists, wording and records only, for the author: COMPILATION §6 item
4's callers' list (the two tree-level stops), a trace of
`_mark_not_evaluated` in §6 item 3, the guard's scope phrased on the
stored status of each operation, ARCHITECTURE §4.1's job-step list (the
automatic-construction write), this record's §12 superseded sentence,
§9's stale clause on the setters' `async`, and §10's "drop
`_invalidate_from`'s `ev`" (superseded by ruling 3: the `ev` stays), the
garbled `test_mcp` line in §10, a stray comma in MODULE_STRUCTURE §4.1,
PRINT §2's opening order, MODULE_STRUCTURE §2.6's "A compile runs step
2 alone" (its command carries step 3's `TAT.log_directory`), "A3"
undefined in COMPILATION §6. All of them applied on 2026-10-03 with the
sixth review's items (§13).

## 12. Next

The third reader (`BRIEF_5.md`; workflow `wf_515e6693-1be`;
`review_compilation/reader4.json`) read the seventh revision: NOT_FIT
for the text alone — the design holds, §4 adds no mechanism, and both
scenarios (a restart then `evaluate_to` mid-tree; the own-stop case)
give the right stored statuses. Its items, applied in the eighth
revision: markers (the seen-set discard, the store set, the plain
methods, the whole rows, the job steps' store, the compile's startup,
the ruling's headline sentence, "and check"); the compile's log step —
MODULE_STRUCTURE §4.6's step calls `TAT.log_directory`, which a
compile's command, carrying no callback, cannot answer — so §5 then
said the step does not call it and the Isabelle side writes no record
of a compile (superseded by §10's ruling on contract-1: a compile's
command carries `TAT.log_directory`, the step calls it, and the
Isabelle side writes a compile's records); §6's quotes (the A3 entry of
CONSTRUCT_DECISIONS §8
replaced whole, the CONSTRUCT_DECISIONS_LOG §11 sentence, ARCHITECTURE
§4.1's two phrases in place of THEOREM.md §1's, four quotes marked
*done*) and its missing amendments (CONSTRUCT_INTERACTION's four uses
of the setter's halves, CONSTRUCT_DECISIONS §8's "halves" line, the
`Evaluation` listing's store set, the importer rule's field in
MODULE_STRUCTURE §4.1 and FIRST_END_TO_END §6, ARCHITECTURE §3.5's
"after a stop the recursion goes on"); the edit's store sentence ("every
node whose status its commit wrote", the set the setter collects, in
place of "whose stored value changed", which nothing computes now);
terminology ("invalidate" for "withdraw", "field" for "entry" and
"attribute", "status" for "conclusion", "finds it" for "is the check",
"a blocked walk", the change-rationale sentence of §4 replaced by a
statement of the design); and the clash of the status values'
`messages` with the glossary's **message**, resolved by a second sense
in the glossary (§6 item 5, the author's). Its implementation note, the
`Untouched` mode missing from the code, is moot: A3 was withdrawn the
same day (§8).

The construct session wrote its share of §6 on 2026-10-02, the owner
having approved every request there ("批准编译会话的所有请求"):
CONSTRUCT_INTERACTION §3.1–§3.3, §6, §8; THEOREM §1, §6–§8; the
renaming in ARCHITECTURE §3.2, §3.5, MODULE_STRUCTURE §1, §4.1,
PLUGIN_SYSTEM §1, §5, PRINT §2; A3 withdrawn in ARCHITECTURE §3.5,
MODULE_STRUCTURE §4.1, CONSTRUCT_DECISIONS §8, §14 and the LOG §11;
`Evaluation.stored`, the plain setters and the importer rule's field in
MODULE_STRUCTURE §4.1, §4.2 step 3; the stored check and the job steps'
store in ARCHITECTURE §4.1. Left to this session, after the owner
approves the document: ARCHITECTURE §1 (the glossary, `message`'s
second sense included), §3.2–§3.4, §4, §6.2, §9; MODULE_STRUCTURE §2.3,
§2.6, §3, §4.3, §4.4, §4.6 (the compile's log step), §5; PRINT §3–§4;
RENDER_BASELINES; SESSION_AND_THEORY §1–§4; EXCEPTIONS §1, §3;
EVALUATOR_DESIGN §7; FIRST_END_TO_END §1, §2, §3, §4, §6; LOGGING §2,
§5, §7; `ML/TAT_Boot.ML`'s header. Also from that session, 2026-10-01:
automatic construction is a third reserved field beside `job` and
`check` (COMPILATION §4's storage sentence updated); `Proof_Job._check()`
answers a bool; `proof_times` is a recorded field of `Theorem`.

The owner approved §7 whole and the document on 2026-10-02 ("全部批准").
The amendments of COMPILATION §6 left to this session were applied the
same day by four forks of it, one per document group (ARCHITECTURE;
MODULE_STRUCTURE; PLUGIN_SYSTEM, EXCEPTIONS, PRINT, RENDER_BASELINES,
EVALUATOR_DESIGN, LOGGING; SESSION_AND_THEORY, FIRST_END_TO_END), by
hand, each reviewed here afterwards; the construct session's own agent
edited other passages of the same files at the same time, and that
session runs a readers' re-review over every document afterwards. Then
the code, starting with model.py's statuses and setters (§4),
`compile.py` (§5), `toplevel.py`, `TAT_Framework.ML`,
`TAT_Boot.ML`, `tat.scala`, the Scala function and the rebuilt
`lib/tat.jar`. Standing rules unchanged: no code before the owner
agrees; reviews on Opus 5.5, xhigh, one defender per merged finding, a
merge step before the defenders. The sixth review (§13) comes before
all of this: its five owner items, then its author items, then one
reader.

## 13. The sixth review

The owner asked for a full adversarial round over the design as it
stands after the rulings, before any code ("建议再复审一轮，请发起",
2026-10-02). `BRIEF_9.md`; workflow `wf_ffb84dd7-8da`, 28 agents, 52
minutes: five challengers (the invalidation recursion, the compile's
startup, the status model, the documents against each other,
simplicity), one merge, one fresh defender per merged finding, one
judge; Opus 5.5, xhigh. 22 findings, 21 merged; the defenders upheld 14,
refuted 3, called 4 nitpicks. The judge: **READY_WITH_FIXES**, re-review
**SINGLE_READER**; `review_compilation/ruling6.json`, the defended
material `material6.json`. This session re-checked every deciding
citation against the files (the walk modes and `_handle_tree` in
model.py; `move`'s two invalidations in edit.py; the six test callers
of `evaluate=False`; FOREST_WALK_PLAN item 16; MODULE_STRUCTURE §2.6
beside `TAT_Framework.ML`'s startup; the stored-status round trip) and
found them right, with one qualification under status-4 below.

Five items for the owner, none ruled yet:

- simplicity-1: a walk with `ignore_error` unset ends at its first stop
  as it ends at its destination, and the `Blocked` mode goes. Today a
  blocked walk keeps a later own stop's `cannot_evaluate` up to the
  destination, while `_invalidate_from` resets it past the destination,
  so whether the error survives depends on where the destination was
  put (Theory > [A fails, P, X fails, Y]: a walk to Y keeps X failed, a
  walk to P resets X; reproduced on the frozen code). The keep rule is
  FOREST_WALK_PLAN item 16's (2026-09-23), so the owner decides. Cost: a
  blocked own stop prints `not evaluated` until a walk reaches it
  unblocked. Gone with it: one mode, two guards, `_carry_forward`'s
  release branch and `move`'s second release, two tests. The judge
  recommends adopting.
- simplicity-2: one `Evaluation` per walk instead of one per tree,
  relaxing COMPILATION §4's "on the tree's `Evaluation`" *(decided)*: as
  MODULE_STRUCTURE §4.1 stands, the per-tree object carries `passed` and
  is discarded at the tree's end, so `checks: "blocking"` has nothing to
  wait on. The judge recommends one object, stored and flushed at each
  tree's end.
- simplicity-3: drop the internal `evaluate` flag of `Node.evaluate_to`
  and `Forest._invalidate_whole` with it: six tests call it, no product
  code; the tests would call the two plain functions through a test
  helper. The judge recommends.
- status-1: the setter fires `_on_context_change` through `_completed`,
  as it fires `on_invalidated`, so what the hook raises is the class's
  bug on every path, the edit's commit block included, where a
  `TAT_Error` would otherwise escape with the edit half-committed in
  memory and be rendered as the edit's error. Extends ruling 1 to one
  more hook; EXCEPTIONS §1 gets the rule. The judge recommends.
- status-2: the decided store sentence "every node a hook fired on"
  includes nodes that left the forest; an amend's replaced node shares
  its identity number with the replacement, so storing both leaves it to
  chance whose rows survive. Narrow it to "every node still in the forest
  that a completed hook fired on", delete the rows of a deleted subtree,
  and have `_store_node` refuse a departed node. The judge recommends.

Seven author items: recursion-1 (a `move` invalidates from two
positions, where the node left and where it arrived, as edit.py does
today, while every document gives an edit one position; state the rule
once in MODULE_STRUCTURE §4.1 and §4.2, ARCHITECTURE §3.5,
MCP_SPECIFICATION §3.2, and add a cross-tree move test); startup-2
(MODULE_STRUCTURE §2.6's step 2 both calls the registered functions,
which need step 1's environment, and collects the packages, while a
compile "runs step 2 alone": split the step as `TAT_Framework.ML`
already does, collecting the registrations and packages first and
calling the functions with the environment after); status-3
(CONSTRUCT_INTERACTION §9's example clause of a check dropped mid-walk
describes a case the current rules exclude; the construct session's
document); status-4 (`assert_store_mirrors` compares statuses by `==`,
which compares `.ascii`, while the store keeps `.unicode` and ruling 5
accepts an inexact round trip: compare the stored forms. Qualification:
on ascii as Isabelle prints it the round trip is exact today, `a
\<equiv> b` and `x\<^sub>1 \<Longrightarrow> P` included; the judge's
failing example passes a unicode string as the ascii); documents-1
(reader 6's four §4.1 sentences, its leftovers 0, 1, 2 and 4, still to
apply before code, their wording depending on simplicity-1 and
simplicity-2); documents-2 (`Unchained_Node._invalidate` invalidates
each child whole; FIRST_END_TO_END §6's "marks nothing" is the old
`_mark_not_evaluated`'s meaning); simplicity-4 (the guard sits in the
setter, covering every writer of `not_evaluated`, replacing ruling 5's
code-5 predicate, which was keyed by the removed `Invalidating` mode).
Three to apply as they are: documents-3 (COMPILATION §2 quotes a
FIRST_END_TO_END §1 sentence that no longer exists), documents-6 (a
mid-sentence *(decided)* marker in §4's storage paragraph), documents-7
(define **instant status** in ARCHITECTURE §3.2). Deleted: recursion-3,
startup-1 and simplicity-5 as misreadings; startup-3, documents-4 and
documents-5 as nitpicks.

The owner ruled on 2026-10-03, each item's option one, after an
explanation of each ("好的，赞同"; "赞同选项1"; "好的，赞同你的建议";
"赞同你的建议" twice):

- simplicity-1: a walk with `ignore_error` unset ends at its first stop
  as it ends at its destination — the stop answers `mode` `None`, the
  enclosing nodes answer `None`, and `_handle_tree`'s one
  `_invalidate_from` call takes the position after `stopped_at` when
  the tree's walk stopped, after the destination when it reached it,
  and is not made otherwise; the `Blocked` mode goes, and with it the
  rule keeping a blocked own stop, `_carry_forward`'s release branch,
  `move`'s second release and two tests. A nesting node whose
  beginning failed calls `_invalidate(ev)` on each child and carries
  on as today. FOREST_WALK_PLAN item 16's "the blocked walk stays a
  mode of its own … keeping own stops as they are" is superseded.
- simplicity-2: one `Evaluation` per walk; at each tree's end the walk
  stores `stored`, deletes the released slots and sends `cancel(ids)`
  for `dropped`, each emptied then; `passed` accumulates over the walk,
  which is what `blocking` waits on. COMPILATION §4's "on the tree's
  `Evaluation`" becomes "on the walk's `Evaluation`".
- simplicity-3: `Node.evaluate_to(agent, ignore_error, checks)` always
  evaluates; the internal `evaluate` flag, `Forest._invalidate_whole`,
  the root's refusal and `test_the_root_has_no_position` go; the six
  tests call a test helper that takes the lock, makes an `Evaluation`,
  calls `_invalidate_from(Location(parent, index), ev)` or
  `tree._invalidate(ev)`, then the walk-end store-then-flush.
- status-1: the setter fires `_on_context_change` through `_completed`,
  after the write, as it fires `on_invalidated`; whatever the hook
  raises, a `TAT_Error` included, is its class's bug. EXCEPTIONS §1's
  jobs bullet and CONSTRUCT_INTERACTION §3.2's row say so. One test:
  an `edit` whose invalidation reaches a node whose running job's
  `_on_context_change` raises `InvalidField` ends with
  `TAT_InternalError`, the database still holding the pre-edit forest.
- status-2: "An edit stores every node whose status its commit wrote
  and every node still in the forest that a completed hook fired on,
  and deletes the rows of a deleted subtree, in its one transaction";
  an amend deletes nothing, its identity passing to the replacement;
  `_store_node` refuses, with `TAT_InternalError`, a node whose parent
  chain does not reach the forest; one test with a class whose
  `on_deleted` and `on_inherited` record a field.

The rulings and the author items were written into the documents the
same day: by three forks of this session, by hand, one per document
group (ARCHITECTURE, MCP_SPECIFICATION, EXCEPTIONS, PRINT;
MODULE_STRUCTURE §2.6, §4.1, §4.2; COMPILATION, FIRST_END_TO_END,
FOREST_WALK_PLAN item 19, the records), each checked here afterwards;
and by the construct session in CONSTRUCT_INTERACTION §3.2 and §9,
which confirmed its §3.3, §5 and §9 state neither a per-tree
`Evaluation` nor the `Blocked` mode nor the flag. Two consequences
drawn while applying: with `Blocked` gone, `EvaluationMode` goes
(`_evaluate` takes `Evaluating`; `EvaluationResult.mode: Evaluating |
None`); and `_carry_forward`'s release branch is the one branch behind
both `delete`'s release and `move`'s second release, so ARCHITECTURE
§3.4's deletion-release clause went with the ruling (when the
predecessor has written nothing, nothing is there to release: a node
writes only after its predecessor has). The code items for when the
freeze is lifted are listed in COMPILATION §6 item 9.

Reader 7 over the amended text (`BRIEF_10.md`; workflow
`wf_6ab33539-522`; `review_compilation/reader7.json`): **NOT_FIT** for
the text alone, every item of `ruling6.json` applied (documents-1 in
part), 14 findings, two of them major, all applied the same day by
this session:

- The hand-over rule, copied from the ruling's wording ("after the
  destination when it reached it, and not at all otherwise"), left out
  the destination under a nesting node whose beginning failed, where
  the walk neither stops nor reaches it. MODULE_STRUCTURE §4.1 now has
  `_handle_tree` call `_invalidate_from` with the position after the
  destination whenever the destination lies in the tree and the walk
  did not stop, and not at all for a tree run to its own `end`;
  ARCHITECTURE §3.5's failed-beginning clause says everything after the
  destination is invalidated. This is the owner's ruling of 2026-10-02
  (everything after the destination `not_evaluated`), not a new
  decision.
- "A tree's evaluated nodes are a prefix of it in tree order" is false
  under a failed beginning (its children `not_evaluated`, its ending
  and what follows `ready`); ARCHITECTURE §3.4 and COMPILATION §4 now
  carry that qualification, and §3.4's "a node writes only after its
  predecessor has" rests on §3.1 and §3.5 instead. The sixth review's
  claim that the invariant holds with no exception was wrong on this
  point; consequence 2 of `BRIEF_10.md` holds in every case.
- Minor: the tree's walk, not the call, ends at a strict stop, the
  forest going on to its next tree (ARCHITECTURE §3.3, §3.5;
  MODULE_STRUCTURE §4.1); the visited stretch names the stop; the
  callers' lists name the failed beginning's `_invalidate` on its
  children; LOGGING §4's `walk_started` loses `evaluate`; ARCHITECTURE
  §3.3's "the guards" sentence replaced by the setter's guard in §3.4;
  COMPILATION §6 item 9 records ARCHITECTURE §3.5's replaced passage,
  `_mode_after`'s `Blocked` answer and the places ARCHITECTURE §3.6 and
  LOGGING §4; FIRST_END_TO_END §6, FOREST_WALK_PLAN item 19 and
  STEP5_HANDOFF brought current; "an own stop after it" in ARCHITECTURE
  §3.3 reads "an obstacle after it", and MODULE_STRUCTURE §4.2 step 3's
  copy rule excludes a failed beginning; ARCHITECTURE §6.2 and
  MODULE_STRUCTURE §4.1 say which slot a failed beginning's copy goes
  to. Reader 7 also noted that no document defines **own stop**
  (ARCHITECTURE §1 is the owner's glossary); proposed to the owner.

Reader 8 over the fixes (`BRIEF_11.md`; workflow `wf_128c8d96-efd`;
`review_compilation/reader8.json`): **NOT_FIT**, every finding of
reader 7 applied, the three cases of `BRIEF_11.md` walked through the
text with the documents agreeing on every stored status, one major
finding for the owner and nine minor ones, the minor ones applied the
same day by this session: the obstacle/stop confusion in two
ARCHITECTURE sentences; a failed beginning's copy being its ending's
write, made only when the walk goes on after the block (ARCHITECTURE
§6.2, MODULE_STRUCTURE §4.1); `_mode_after`'s third `None`, the
`EvaluationResult.mode` comment and the hand-over sentence naming the
failed beginning above the destination; `Evaluating`'s comment "run
what is not_evaluated"; COMPILATION §4's restart sentence and its
decided sentence reading "the first stop in each tree"; ARCHITECTURE
§3.5's "in a tree whose walk stops, after the stop"; LOGGING §4's
`stopped` reasons; ARCHITECTURE §3.2's pointer; "own stop" gone from
FIRST_END_TO_END §6 and COMPILATION §6 item 9; MODULE_STRUCTURE §4.1's
"only after everything before it is `ready`" made "only from the input
its predecessor wrote". The major finding, for the owner: what
`evaluate_to` answers when its destination lies under a nesting node
whose beginning failed — the walk neither reaches the destination nor
stops, so the result opens with `Evaluation reached <destination>.`
over a destination shown `not evaluated` (today's code does this);
the options are to report the failed-beginning node as the stop, or a
third opening line. The owner ruled the same day ("赞同 (a)"): the
node is reported as the stop when `ignore_error` is unset; with
`ignore_error` set no stop is reported, as for an import without a
theory value; everything after the destination is invalidated either
way, so `_handle_tree`'s position is the one after the destination
when the stop lies above it. Written into ARCHITECTURE §3.3, §3.5;
MODULE_STRUCTURE §4.1; COMPILATION §4 (the decided sentence) and §6
item 9; MCP_SPECIFICATION §4; FOREST_WALK_PLAN item 19.

Reader 9 over the fixes after reader 8 (`BRIEF_12.md`; workflow
`wf_906cfa96-3ca`; `review_compilation/reader9.json`): **NOT_FIT**,
every finding and leftover of reader 8 applied, the ruling in every
place named, the case walked with `ignore_error` unset and set with
the same stored statuses in every document; seven minor findings and
four leftovers, no design decision, all applied the same day by this
session: MCP_SPECIFICATION §4's statement of the ruling gains the
`ignore_error` condition, and its "why the same node stops every later
call" goes; ARCHITECTURE §3.3's "A stop is a fact about the forest"
paragraph carries the one exception the ruling makes (a failed
beginning is a stop only to a call whose destination lies under it),
and its `ignore_error` paragraph no longer lists a failed beginning
among the stops the flag cannot pass; the "after the stop" summaries
(ARCHITECTURE §3.5 twice, COMPILATION §6 item 4) carry the
failed-beginning exception; a failed beginning's ending is `ready`
once a walk has gone on after the block (ARCHITECTURE §3.2, §3.3);
TOOL_SCHEMAS §4 and RENDER_BASELINES §6's prose describe the reached
line as the destination when no stop is reported — `ignore_error`
leaving the destination `not_evaluated` under a failed beginning or
behind an import without a theory value included — the two lines
themselves unchanged; COMPILATION §6 item 9's and FOREST_WALK_PLAN
item 19's summary of the ruling made per tree; MODULE_STRUCTURE §4.2
step 3's copy rule, §4.1's `None` attribution and visited stretch.
Reader 9 asked the owner to confirm the reading of the reached line;
it follows from the ruling's `ignore_error` half, which the owner
approved, and is reported to the owner with the rest.

Reader 10 over these fixes (`BRIEF_13.md`; workflow `wf_f1f4acac-ab1`;
`review_compilation/reader10.json`): **FIT**, every finding and
leftover of reader 9 applied, the `ignore_error` run and a third
strict call walked with every document agreeing, no finding. One note
for the owner, not a contradiction: a strict `evaluate_to` on the
failed nesting node itself (`section_S`) opens `Evaluation reached
section_S.` — its ending is `ready`, its `failed` mark shows the error
— while `evaluate_to` on a node under it opens `Evaluation stopped at
section_S.`; nothing changes unless the owner wants the two alike.

The design is therefore reviewed: the sixth adversarial round, the
owner's six rulings (the five of ruling6.json and reader 8's), and
four readers over the amended text, the last FIT. Next, once the owner
lifts the freeze: the code — review 5's author items in the shape of
the rulings (§10, §11, §13) and the sixth review's code items
(COMPILATION §6 item 9), on top of the logging session's steps in
`toplevel.py`, `mcp_server.py` and `Conversation`; `pyright` and the
full test suite, `test_conversation.py` against the real Isabelle
included; then a code review against the documents before commit, in
the same shape as the design reviews; the step committed only together
with `import_sessions`.

## 14. The code, after the freeze

The owner lifted the freeze on 2026-10-03 ("建议在 compact 后开工"), the
design having passed reader 10, then held the start the same day until
the logging session's Python-side batch was in and he approves again
("在我批准前你不准开工。要等待另一个 agent 工作完成"); that batch is in
and committed (steps 1–4, `2e8f6e7` and `d9472b3`; its Isabelle-side
batch uncommitted), and as of this writing nothing of items 1–7 is in
the working tree — the code is the frozen step-1 code under those
commits. The work, in order, on `isabelle_theory_agent/model.py`,
`edit.py`, `store.py`, `isabelle_driver.py`, `plugin.py` and `test/` as
they stand (never `toplevel.py`, `mcp_server.py`, `log.py` or
`Conversation`'s constructor, the logging session's):

1. The walk (ruling 3 of §10, rulings simplicity-1/-2/-3 of §13, reader
   8's ruling): `Seeking`, `Invalidating`, `Blocked`, `EvaluationMode`,
   `_mark_not_evaluated`, `_invalidate_whole`, the root's refusal and
   the `evaluate` flag go; `_evaluate(ev, mode: Evaluating)`,
   `EvaluationResult.mode: Evaluating | None`; `_mode_after` answers
   `None` at the destination and at a stop with `ignore_error` unset; a
   nesting node whose beginning failed calls `_invalidate(ev)` on each
   child, answers `None` when the destination lies under it (itself as
   `stopped_at` when `ignore_error` is unset), otherwise copies its
   input to its ending and carries on; one `Evaluation` per walk
   (`checks`, logged by `walk_started`, and `passed`, which the walk
   fills — a leaf when reached, a nesting node at its ending; `starter`
   and `dropped` are the jobs code's, added with `Agent` and the job
   drop that fill them; `stored` and the released slots emptied at each
   tree's end); `_handle_tree`'s one `_invalidate_from` call with the
   position after `stopped_at` — after the destination when the stop is
   a nesting node above it — or after the destination when it lies in
   the tree, before the tree's store and flush; the forest goes on to
   its next tree; the two plain functions `_invalidate(ev)` (Leaf,
   StdBlock, Unchained_Node) and `Forest._invalidate_from(position, ev)`
   with the setter's guard; `Theory._set_ending`'s cascade on the
   stored field; `Forest._run` the evaluating walk's alone, writing
   `walk_started` (a required destination) and `walk_ended` (the walk's
   own deletion count, from `flush`), an edit's `_invalidate_from`
   writing only `operation` records (the logging review's funnels-2);
   `stopped` written once, in `_handle_tree`; every record naming nodes
   by `Forest.full_id`; `Theory._eval_beginning_opr` making
   `<working directory>/<Session name>/` before every run of the
   header, through the compile's folder function (below).
2. The setters (§10 rulings 1, 4–7; §13 status-1, simplicity-4): plain
   methods writing both fields; the guard "stored already
   `not_evaluated` → nothing" at the top of each of the three, before
   `_stored` (funnels-4); release on written→unwritten, the node's
   `owned_slots` released with the operation's resulting state (below);
   the seen-set keys discarded through `Conversation.forget(key)`, added
   in its minimal form (one set) for the jobs code to reimplement over
   the agents; `ev.stored.add`; `on_invalidated` through `_completed`;
   the `evaluation` log record through `log.py`. Left to the jobs code
   (the construct session's, with `_check_outcome`, `Agent` and the
   jobs): the stored check's clearing when the stored status leaves
   `Ready`, `_on_context_change` through `_completed`, the evaluation
   job's drop — three lines in the same setters.
3. The edit's commit (§10 simplicity-4; §13 status-2, recursion-1): one
   transaction at the end of the synchronous block, before the round
   trips (`theory_delete` of the vanished names returned by the plain
   `_invalidate_changed_trees`, `state_delete`, `cancel(ids)`); the
   store set = the nodes whose status the commit wrote + the nodes
   still in the forest a completed hook fired on, the rows of a deleted
   subtree deleted, an amend deleting nothing; `_store_node` refuses a
   node whose parent chain does not reach the forest; `move` keeps its
   two `_invalidate_from` calls; `_carry_forward`'s release branch goes;
   the four "store transaction + `committed` record" blocks become one
   context manager named from "the edit's one store transaction"
   (elegance-8); a deleted or amended-away node's `owned_slots` released
   with its `state`.
4. The store (§10 code-1, status-5): the reserved stored rows (`kind`,
   `children`, `last_evaluation_statuses`; the jobs code adds its own)
   split from the construct's two framework fields (`kind`, `children`)
   that plugin.py checks against; a malformed `last_evaluation_statuses`
   row → `TAT_StartupError`; `Theory.from_store` reads a missing
   `import_sessions` as the empty list; `import_sessions` committed with
   the step; the loader minting a node's `owned_slots` beside its
   `state`, as `edit._construct_element` does.
5. `IsaTerm` (§10 code-4-move): one class in `Isabelle_RPC_Host.unicode`
   (contrib/Isabelle_RPC), TAT and AoA both importing it from there.
   Which class it is awaits the owner, asked on 2026-10-03: TAT's
   (`isabelle_driver.IsaTerm`; THEOREM §2: `str()` refused, equality on
   `ascii`), or AoA's (`contrib/Isa-Mini/IsaMini/AoA/model.py`, the one
   the owner's approval of 2026-09-30 names — DOC_SYNC_LIST "Outside
   this repository": `unicode.py` receives it unchanged), which keeps
   both properties and adds `to_unicode`, `to_ascii`, `__len__`,
   `__lt__` and equality with a `str`. Until then this item waits.
6. `Forest._run` (§10 status-1): whatever escapes `_eval_opr`,
   `_eval_beginning_opr`, `_eval_ending_opr` → `TAT_InternalError`.
7. Tests: the six `evaluate=False` callers through a test helper (lock,
   `Evaluation`, `_invalidate_from` or `tree._invalidate`, store and
   flush); delete `test_own_stop_survives_being_blocked`,
   `test_removing_an_own_stop_behind_a_blocked_predecessor_releases_its_copy`,
   `test_the_root_has_no_position`; `assert_store_mirrors` comparing
   `_status_to_store` forms; `test/invariants.py`'s `CannotEvaluate`
   clause; the new tests of §13 (a cross-tree `move`; a repeated
   `_invalidate_from` storing nothing; an amend and a delete under hooks
   that record a field; a destination under a failed beginning reported
   as stopped at that node; `_on_context_change` raising `InvalidField`
   under an edit is the jobs code's, with the hook); the logging
   session's tests of 2026-10-03 kept passing (the two-importer
   `stopped` records, the per-tree `slots_released` sum, the amend's
   `committed` record, the `store.transaction` assertions on the edit
   path); `pyright isabelle_theory_agent`; the full suite;
   `test/test_conversation.py` against the real Isabelle (the REPL
   server only, never `isabelle build`).
8. A code review against the documents (challengers → merge → one
   fresh defender per merged finding → judge; Opus 5.5, xhigh), then
   the owner's "批准提交" before any commit; `git push origin main` only
   on request.

Two rules of the construct session's AoA path (2026-10-03, the forked
session [7f92f0]; ai-artifacts/review/DOC_SYNC_LIST.md entry 23) are
folded into items 1–4 above, as MODULE_STRUCTURE §4.1 "States" and its
`Theory` bullet state them. `owned_slots`: a class attribute, a tuple of
slot names, empty on `Node`, `('goal_state',)` on `Theorem`; the
framework mints one `Isar_State_Slot` per name wherever it mints the
node's `state` — construction and load — and sets it as the node's
attribute of that name; only the class's evaluation callback writes
them; every setter taking an operation from written to unwritten
releases them with that operation's resulting state, never on a
rewrite; a deleted or amended-away node's go into the released set with
its `state`. The `Session` folder: before every run of `Theory`'s
beginning, the framework makes `<working directory>/<Session name>/`
if absent, through the function the compile uses (COMPILATION §4);
what the beginning does when that function refuses — a symbolic link
or a file at the path — awaits the owner's ruling (the construct
session's proposal: the beginning fails with the refusal's sentence as
its message); until it comes, the refusal is raised as the compile
raises it.

After item 8 the compile round: `compile.py`, `Node.can_emit`, `emit`,
`emit_beginning`, `emit_ending`, the compile hooks' framework side and
the ML/Scala side of `TAT_compile` (COMPILATION §3, §5) — `Theorem`'s
own `can_emit`/`emit` and its package's proof-store hook being the
construct session's. The `evaluate_to` tool (mcp.py, `tools/
evaluate_to.jsonc`, `checks`) and `Theory`'s `description` field are
in the construct session's plan unless the owner assigns them
otherwise.
