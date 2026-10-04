# Plan: the forest walk (FIRST_END_TO_END_RUN_PLAN.md §7 step 4)

Status: revision 4, 2026-09-23, after three reviews (READY_WITH_FIXES,
NOT_READY on one new defect, READY_WITH_FIXES; their rulings in the
review record) and the owner's decisions on every owner item; checked
against the third ruling by one re-reader before work started;
implemented the same day, §1 items 16 and 17 decided after the
implementation review (§13). The design
is FIRST_END_TO_END_RUN_PLAN.md §6, approved 2026-09-04 and reviewed with
the whole plan (2026-09-06); this file is its implementation plan. §1
records the owner's decisions, which are not up for review; §2 what the
design already has in the code; everything from §3 on is the author's.
The design's content is in the documents under `docs/` (§10); this file
keeps the implementation record (§13).

## 0. Scope

`Forest._evaluate` and what it needs: the import graph; running a tree's
imports before it; the order constraint's stop; the stop that crosses an
import dependency; the invalidation of a tree's importers, on evaluation
and on every edit; the removal of a vanished theory name from the ML
theory table (`TAT.theory_delete`); the `imports` field's grammar, the
header's quoting and the two name grammars that become path elements (§1
items 5, 10 and 13); the reserved theory names (§1 item 12); the loader's
and the launcher's changes (§1 items 1–3); the tests, on the fake state
slot table, on the ML end-to-end driver and on the launcher; the
documents.

Not in scope: the tools (step 5), which call `evaluate_to` and render its
result — how the order constraint's sentence reaches the agent is
TOOL_SCHEMAS.md §4's, designed with the `evaluate_to` tool, on the query
of §3.4; the test harness (TEST_HARNESS_PLAN.md), which this step
unblocks and amends in one place (§1 item 11).

## 1. Decisions taken *(the owner's, 2026-09-22 and 2026-09-23)*

1. The loader never loads a file under the working directory. The
   launcher guarantees it once, at start (§5.1): a launch whose Isabelle
   session layout has a session directory under the working directory is
   refused, with the sentence

   ```
   Isabelle session <name> is declared under the working directory <path>; TAT never loads theories from there
   ```

   Nothing in the ML side compares paths.
2. The loader's load-from-source arm loads only a theory whose file the
   Isabelle session layout knows — `Resources.find_theory_file`, which
   resolves the import's qualifier as an Isabelle session name and
   returns the first of that session's directories holding `<short
   name>.thy`; whether that session's ROOT declares the theory does not
   enter. The arm that loaded a `.thy` by its path is removed entirely.
3. The loader's refusal renders the existing sentence of RENDER_BASELINES
   §3, `Fail to load `<qualified name>` because it is not found.`, with
   the name Isabelle resolved the import to. No new agent-facing text at
   the loader.
4. The bare cross-session import (FIRST_END_TO_END_RUN_PLAN.md §5, until
   now *(open)*) needs nothing of its own: a tree in Isabelle session `T`
   writing `imports A` for the forest tree `S.A` asks for `T.A`, which is
   no forest tree, no base-heap theory and no known file, so the header
   fails with the sentence of item 3 — and the name in it, `T.A`, shows
   the agent what its bare name was taken for. No check in `Theory.gen`
   beyond item 5, no Python-side stop.
5. An item of `imports` is a theory name in one of two shapes: `<short
   name>`, or `<Isabelle session name>.<short name>`, each half in the
   grammar of item 13. No quotes, no path, no `.thy` suffix.
   `Theory.gen` refuses anything else with `InvalidField`, rendering

   ```
   The field `imports[1]` must be a theory name without quotes; a path is not allowed.
   ```

   `Theory.header()` quotes every item when it renders the header, so a
   hyphenated name (`HOL-Library.Multiset`, `Launchbury.AList-Utils`) is
   one token to Isabelle's lexer. On this domain `Thy_Header.import_name`
   is the identity; the forest's graph and Isabelle's resolution agree as
   §3.1 says.
6. Under `ignore_error`, the stop that crosses an import dependency
   (§3.3 case 2) is not reported, like every stop inside a tree — the
   blocked tree's nodes are `not_evaluated` and the obstacle's own error
   shows at the obstacle; the order constraint's stop (§3.3 case 1) is
   reported whatever the flag, since the tree it concerns is
   `not_evaluated` throughout and nothing else records why. ARCHITECTURE
   §3.3's "the call then returns continue" gains that one exception.
7. `EvaluationResult` gains no field. The forest answers
   `_order_violation(node)` (§3.4), and the renderer composes the
   sentence from it.
8. The importer rule stays in the `Theory` ending's status setter (§4.1),
   as FIRST_END_TO_END_RUN_PLAN.md §6 places it.
9. The record every edit compares sees an `amend` that replaces a
   `Theory` node. *(As decided on 2026-09-23 this item had three clauses:
   the setter's rule also firing when an ending becomes `not_evaluated`,
   a cross-tree `blocked by` naming the import's deep obstacle, and the
   `Theory` node object as the record's third component. The first two
   the implementation review found insufficient to keep every
   `blocked_by` inside the forest; items 16 and 17 replace them. The
   third the confirming review found replaceable by an author's shape:
   the record holds the resolved imports as the `Theory` nodes
   themselves, so the replaced node shows in its importers' records —
   §4.2, §11.)*
10. A theory short name is a letter followed by letters, digits and
    underscores; an Isabelle session name the same, with interior
    hyphens allowed. Neither takes a prime: both become path elements
    (`<session>/<short name>.thy`, and every import through
    `Path.explode`), and Isabelle refuses `'` in a path element
    (`Pure/General/path.ML`, `illegal_char`). Every other node's name keeps
    the framework's grammar (MCP_SPECIFICATION §2), primes included. The
    two renderings:

    ```
    `Foo-Bar` is not a valid theory name: a theory name starts with a letter and continues with letters, digits and underscores, with no hyphen and no dot.
    `S'` is not a valid session name: a session name starts with a letter and continues with letters, digits, underscores and interior hyphens, and does not end with a hyphen or an underscore.
    ```
11. The test plugin is `Theory_Agent_over_Trees.Test_TAT_Framework`, found
    through `directories "test"` on the repository's own Isabelle session
    (`ROOT`); TEST_HARNESS_PLAN.md §1 item 4 — a session declared under
    `test/`, given with `-d` — is withdrawn: a directory can belong to
    one Isabelle session only (`Sessions.Structure.make`, "Duplicate use
    of directory"), so the two cannot coexist, and the repository's
    session is the simpler home. §10 carries the consequences into that
    plan.
12. A name the Isabelle session layout declares global — Pure's
    bootstrap names, and every theory a ROOT of the layout marks
    `(global)`: `Main`, `Complex_Main`, `HOLCF`, `FOL`, `ZF`, … in the
    distribution, more under the AFP or `-d` — is a reserved theory name
    (§5.2). A tree cannot bear one: `Resources.theory_name` refuses to
    qualify such a name, so a tree so named would be keyed in the ML
    theory table without its Isabelle session. The check is its own,
    answered by Isabelle's own table (`Resources.global_theory`), never
    by a list, and refused with a new `BadEdit`, `ReservedTheoryName`:

    ```
    `FOL` is a reserved theory name; choose another name.
    ```

    A name a loaded theory already bears — `Main` on a HOL heap — is
    still refused as taken, with the real holder, as today.
13. Each half of an `imports` item takes item 10's session grammar —
    a letter, then letters, digits, underscores and interior hyphens —
    so that the AFP's hyphenated theory names (`AList-Utils`, `HOL-CSP`,
    …) can be imported; a tree's own name and a `Session`'s own name keep
    item 10 exactly. The one AFP name outside it, `CoreC++`, stays
    unreachable (§12).
14. ARCHITECTURE §1's glossary gains a row for the **Isabelle session
    layout**: the Isabelle process's map from each known Isabelle
    session to its directories, and the theories a ROOT marks `(global)`
    — what `Resources.init_session` receives from the launcher and what
    `Resources.find_theory_file` and `Resources.global_theory` read.
15. Declined: a variant that would keep a tree's evaluated work while it
    violates the order constraint (the tree stays walked `Invalidating`,
    as §6 says); and a single flush per walk in place of one per tree.
    Adopted in the latter's place: each tree of §3.3's loop walks under
    its own `Evaluation(ev.destination, ev.ignore_error)`, flushed when
    the tree's walk ends — whoever creates an `Evaluation` flushes it,
    with no exception.
16. *(2026-09-23, after the implementation review)* A blocked node — after
    a stop in its tree, under a nesting node whose beginning failed, or in
    a tree one of whose resolved imports has no theory value — is
    `not_evaluated`. No status names the node's obstacle: `cannot_evaluate`
    means an own stop and nothing else, and a blocked node renders
    `(not evaluated)`. The `failed` marks say where the obstacles are, and
    the tool that ran the evaluation names the first stop in its answer
    (RENDER_BASELINES §6, MCP_SPECIFICATION §4). The blocked walk stays a
    mode of its own inside a tree, keeping own stops as they are; §3.3
    case 2's stop is the import's `Theory` node, and its tree is walked
    whole in `Invalidating` mode like case 1's (§3.3, an author's shape
    after the confirming review: such a tree holds nothing to keep).
    PRINT.md §1 loses its `blocked by <id>` row and RENDER_BASELINES §5
    its line.
17. *(2026-09-23)* The `Theory` ending's rule fires on one clause,
    FIRST_END_TO_END_RUN_PLAN.md §6's own: the ending was `ready` and no
    longer is.
18. *(2026-09-23, after the confirming review)* Item 12's reserved names
    are refused as the short name of a qualified import too, whatever the
    session part: `Loader.fetch` never loads `HOL.Main`, `Foo.Main` or
    `FOL.FOL`, which Isabelle would load a second time under that name —
    its comparison being by short name, a later theory importing both
    fails with `Duplicate theory name` far from the cause — and refuses
    them with item 3's sentence, since no theory bears such a name. A
    bare `Main` is untouched.
19. *(2026-10-03, after the compilation design's sixth review,
    ai-artifacts/COMPILATION_REVIEW.md §13)* With `ignore_error` unset
    the walk of a tree ends at its first stop as it ends at its
    destination, the forest going on to its next tree: the stop
    answers `mode` `None`, every enclosing node runs nothing more and
    answers `None`, and `_handle_tree`'s one `_invalidate_from` call
    takes the position after the stop; everything after a stop to the
    tree's end is `not_evaluated`, obstacles included. The `Blocked`
    mode goes, and with it item 16's "the blocked walk stays a mode of
    its own inside a tree, keeping own stops as they are", the
    stopped-child test, `_carry_forward`'s release branch and `move`'s
    second release. The internal `evaluate` flag and `_invalidate_whole`
    of §6 go too: `Node.evaluate_to` always evaluates, and the tests that
    used the flag call the two plain functions of MODULE_STRUCTURE §4.1
    — `Forest._invalidate_from(position, ev)` and a node's
    `_invalidate(ev)` — through a test helper. Item 15's per-tree
    `Evaluation` goes too: the walk runs under one `Evaluation`, which
    `_handle_tree` stores and flushes at each tree's end, `passed`
    accumulating (COMPILATION.md §4). A destination under a nesting node
    whose beginning failed is reported as stopped at that node when
    `ignore_error` is unset, everything after the destination
    invalidated (reader 8, ruled 2026-10-03).

## 2. Already in the code (step 3, 2026-09-08)

Of §6: `Unchained_Node` with its five refusals; `Session._evaluate`
raising `TAT_InternalError`; the `Theory` root's slot chain
(`_state_after_ending`, owned; the input slot nobody writes); `Session`
and `Theory` as framework classes `plugin.load` registers first; the
blocked mode of `Evaluating` and the `Invalidating` mode, which
the node recursion already honours; `Forest.id_of`; RENDER_BASELINES §3's
sentence; EVALUATOR_DESIGN §3's account of `TAT.theory_delete`. What is
missing is exactly `Forest._evaluate` — today `raise NotImplementedError`,
with `test/routing_forest.py` standing in — and everything §3–§6 below
describe.

## 3. The walk: `Forest._evaluate`

### 3.1 Trees, names and the import graph

The forest's **trees** are the `Theory` instances under the `Session`
instances under the root, in tree order; `Forest._trees()` selects them
by class at both levels, so a root whose children are something else —
the single-tree test double of `test_model.py` — holds no tree. A tree's
**qualified name** is `Theory.qualified_name()`, `<Session name>.<short
name>`, the string the ML side keys the theory table by (EVALUATOR_DESIGN
§7): `begin_theory` qualifies the header's name through
`Resources.theory_name`, which joins the qualifier to every name but a
global one, and §1 item 12 keeps a global name off every tree.

A tree's **resolved imports** are the forest trees among its `imports`
items, in the order of the items as the agent wrote them — an item
matching no tree dropped, a tree named twice taken at its first
occurrence: an item of the shape `<session>.<short name>` is taken as
written; an item of the shape `<short name>` is qualified with the
tree's own `Session` name; the result is looked up among the trees'
qualified names, and an item matching no tree is external and never
enters the graph. This agrees with `Resources.theory_name`: on a dotted
item the two are the same rule; on a bare item they differ exactly when
the name is global, and then both answer "no forest tree" — Isabelle
because it leaves the name unqualified, the forest because no tree bears
a global name and every qualified name carries a dot. Since theory short
names are unique in the forest, a bare item from another `Session`
matches nothing (§1 item 4), and a dotted item matches at most one tree.

The graph may contain a cycle, a self-loop included: `Theory.gen` judges
nothing about what an item names, and a `move` into another `Session`
can turn an external dotted item into a self-import with every gate
passed. Every reading below is finite under cycles by definition. The
graph is a function of the forest, recomputed by every walk and every
edit that needs it, never stored; its three readings each build the name
table once for their call:

- `Forest._resolved_imports(tree)`, ordered as above;
- `Forest._importers(tree)` — the trees whose resolved imports contain
  `tree`, the tree itself included when it imports itself;
- `Forest._closure(trees)` — the least set containing `trees` and
  closed under resolved imports, in tree order.

### 3.2 What a walk is given

`Forest._run(ev, mode)` calls `_evaluate` with one of two modes:

- `Seeking(position)` — an edit's unconditional invalidation, or
  `evaluate_to(evaluate=False)` on a node inside a tree. The position's
  parent lies in a tree, or is a `Session` or the root. In a tree: the
  walk is routed to that tree alone (upward from the parent to the child
  of a `Session`), which runs the existing `StdBlock` recursion under the
  same mode. Under a `Session` or the root: nothing is walked, and the
  result is `EvaluationResult(None, INVALIDATING)` — sibling trees are
  independent, and what an edit at the `Session` layer must invalidate is
  §4's business.
- `Evaluating()` with `ev.destination` set — `evaluate_to`. The trees the
  destination stands for are: the tree containing it; every tree under it
  when it is a `Session`; every tree when it is the root. The walk
  handles `_closure` of those trees, in tree order; trees outside it are
  not touched.

### 3.3 Handling each tree

Each tree of the closure is handled in turn, in tree order, by one of
three cases, judged in this order:

1. **The order constraint.** `Forest._order_violation(tree)` answers the
   first item of the tree's `imports`, as the agent wrote it, whose
   resolved tree does not lie strictly earlier in tree order — an import
   placed after the tree, or the tree itself — or `None`; on a node that
   is not a `Theory`, `None`. The constraint is §6's, which no edit
   refuses, since the violating state is reachable by legal edits; case 2
   never names a tree's own `Theory` node, since a self-import is a
   violation. When it answers an item, the tree is not run: it is walked
   whole in `Invalidating` mode (`_invalidate_trees`, §6) —
   `not_evaluated` throughout, nothing about it attempted — and it is a
   stop at the tree's `Theory` node. Nothing is stored:
   the check runs before every run of the tree, so a repairing `move`
   clears it by itself.
2. **A stop crossing an import dependency.** Otherwise, if the first of
   the tree's resolved imports that does not answer `_operations_ready()`
   on its `Theory` node exists — both operations `ready`; the ending
   alone does not do, since after a failed header the ending is `ready`
   and no theory value exists — the tree is not run: it is walked whole
   in `Invalidating` mode like case 1's (`_invalidate_trees`, §6) — it
   holds nothing, a tree whose import has no theory value being
   `not_evaluated` throughout (§4.1's premise) — and it is a stop at that
   import's `Theory` node (§1 item 16); when the import stopped for a
   reason of its own — a failed `end`, a stop inside it — that stop was
   recorded first, the import coming earlier in tree order, and is the
   one §3.4 reports; a failed header is no stop of the import's own, so
   the importer's stop, the import's `Theory` node, is the one reported.
   The check does not consult `ignore_error`: a tree with
   no theory value to import cannot run, as a nesting node whose
   beginning failed cannot be passed.
3. **Running.** Otherwise the tree runs: the recursion in `Evaluating()`
   mode. Its result's `stopped_at`, if any, is a stop; the recursion
   already honours `ignore_error` there.

Since the closure is handled in tree order and case 1 catches every tree
one of whose imports does not lie strictly earlier, a tree reaching case
2 has every resolved import earlier in tree order and already handled in
this walk — run, blocked, or stopped — so its statuses are current.

Each tree's walk is its own `Evaluation`, `Evaluation(ev.destination,
ev.ignore_error)`, flushed when the tree's walk ends: whoever creates an
`Evaluation` flushes it, with no exception — the trees §4.1, §4.2 and §6
walk mid-walk share their caller's. A tree that does not hold
`ev.destination` matches the destination nowhere in the recursion and so
runs whole to its `end`; the tree that holds it stops there. A flush is
one round trip carrying whatever that tree's walk released — the slots
its §4.1 cascade released in other trees included — and none when
nothing was released; a slot released while handling one tree is
therefore gone before a later tree of the same walk could write it
again. `_run`'s final flush of `ev` then finds nothing left.

### 3.4 The result

The walk returns `EvaluationResult(stopped_at, INVALIDATING)`, the two
fields the recursion has: `stopped_at` is the stop of the first tree
in tree order that stopped — case 1 always; case 2 unless `ignore_error`
(§1 item 6); case 3 as its walk reported — or `None`. This is
MCP_SPECIFICATION §4's "naming the first stopped node in tree order". A
violation of the order constraint in a later tree is, like every later
stop, reported once the earlier stop is repaired.

The order constraint's sentence is not carried: it is a function of the
forest, which the tool that renders the result — holding the forest's
lock across the call — obtains through `Forest._order_violation(node)`
on the node the result names: on a `Theory` node whose tree violates the
constraint it answers the offending item, and the renderer composes
RENDER_BASELINES §3's sentence from the node's id and that item (out of
scope, with the `evaluate_to` tool):

```
Since `theory_B` imports `S.C`, you cannot put it before `S.C`. Move it later.
```

A `Theory` node answering an item was reported for that reason and no
other: a tree violating the constraint is never run, so it is never an
own stop, and it lies earlier in tree order than any tree that reaches
case 2 through it, so its own case-1 stop is the one §3.4 reports (§7
asserts it on the two-tree cycle).

`Session._evaluate` stays the framework bug it is; `_run` is never entered
with `Invalidating`.

## 4. Invalidation across trees

### 4.1 An ending leaving `ready` invalidates the importers

Whenever a tree's `Theory` ending was `ready` and no longer is, its
importers become `not_evaluated`, each walked whole in `Invalidating`
mode (§1 item 17). This is a property of the status, enforced in the
setter: `Theory._set_ending` reads the old status, delegates the
assignment — with the release and `on_invalidated` — to
`StdBlock._set_ending`, and only then, on that guard, walks the trees of
`_importers(self)`, the direct importers, in `Invalidating` mode under
the same `Evaluation` (`_invalidate_trees`, §6). Termination follows from
the setter alone: it assigns before it fires, so within one cascade no
ending leaves `ready` twice, cycles included. A tree that imports itself
is its own importer, so the setter fires while that tree's own walk is on
the stack and re-enters it in `Invalidating` mode; the inner call finds
the ending already `not_evaluated` and does nothing.

The transitive importers are reached: each such walk marks that tree's
ending `not_evaluated`, which, when it was `ready`, fires the same rule
for its own importers; and a cascade that meets an ending not `ready`
loses nothing, since no importer of such a tree is itself `ready` — case
2 refuses to run a tree whose import has no theory value, and this rule
takes an importer's `ready` away the moment its import loses it
(`test/invariants.py` states it: a tree one of whose resolved imports
does not answer `_operations_ready()` is `not_evaluated` throughout). So no transitive
importer keeps a current result, which is what ARCHITECTURE §3.4
promises. A blocked importer holds no result and no pointer (§1 item
16), so there is nothing beyond a link not `ready` for a cascade to
clear.

Why the setter covers what it covers: outside the constructor,
`evaluation_status_ending` has exactly one writer, `_set_ending`, so
every in-place change of a `Theory` ending — an edit inside its tree, an
`evaluate_to`, every `Invalidating` walk of §3 and §4 — funnels through
it. What the setter cannot see is a change that moves no ending: the
`amend` that replaces the `Theory` object, and the edits that leave every
ending standing while a name or the graph moves. Those are §4.2's. The
setter needs the forest and the graph, so `_set_ending` becomes `async`
on `StdBlock` — its call sites are all in `async` methods already — while
`_set_status` and `_set_beginning`, which carry no such rule, stay
synchronous.

### 4.2 Every edit compares the trees' records before and after

Every edit takes, per tree identity, the tree's **record** — its
qualified name, and its resolved imports as the `Theory` nodes themselves
(`TreeRecord`) — before it touches the forest and again after its commit.
A tree present in both records whose record changed is walked whole in
`Invalidating` mode (`_invalidate_trees`, §6): its qualified name changed
(its `Session` renamed, itself renamed, moved into another `Session`), or
a tree it imports vanished, appeared, or was replaced by an `amend` — the
change §4.1 cannot see, whatever the amend changed, seen here because a
`Node` compares by identity, so the replacement is another element of
the importer's set. The tree's own node survives the edit, so its ending
becomes `not_evaluated` through `_set_ending`, and §4.1 carries the rest
by the step it states; the amended tree itself is fresh, and the amend's
own walk resets its inherited children. A qualified name present before
and absent after — a deleted, renamed or moved tree, or one under a
renamed `Session` — is removed from the ML theory table in the same
operation, one round trip for all of them (`isabelle_driver.theory_delete`),
so that `Loader.resolve` can never hand an importer the theory value of
a tree that no longer exists.

The record is `Forest._record()`; the comparison and its two consequences
are `Forest._invalidate_changed_trees(ev, before)`. Each of the four
entries of `edit.py` takes the record at its start, before anything is
built, and calls the comparison after its completed events, before the
walks it ends with — the same two lines in `insert`, `amend`, `delete`
and `move`, so no entry has to know which names it disturbed. Nodes, not
names, are what the import set holds: a renamed tree then changes its
importers' records directly, which the post-edit graph — where the old
name resolves to nothing — could not tell §4.1 about; and an `amend`
renaming a tree while adding a fresh tree under the old name changes
them too.

The entries' own walks are unchanged. A reorder within a `Session`, or
of the `Session`s, changes no record, sends nothing to `theory_delete`
and invalidates no tree. An edit inside a tree changes no record and
sends nothing either; its importers are reached through §4.1, since its
own walk moves the tree's ending.

No status names another node (§1 item 16), so an edit leaves no pointer
behind to clear; what §4.1 and §4.2 secure is that no tree keeps a result
built on a theory value that changed, and `test/invariants.py` asserts
after every edit and every walk that a tree one of whose resolved
imports does not answer `_operations_ready()` is `not_evaluated`
throughout.

### 4.3 The ML side

`Theories.delete` — `Synchronized.change theories (fold Symtab.delete_safe
names)`, `delete_safe` because a tree whose header failed never stored a
value; the framework callback `TAT.theory_delete`, argument a list of
qualified names, result unit, `on_interrupt = Reraise`, in
`framework_callbacks`, which therefore takes the theory table beside the
state slot table; and `isabelle_driver.theory_delete(conn, names)`. An
entry whose name has not vanished stays until overwritten by the tree's
next `end` or removed by a later edit; it is never read meanwhile
(EVALUATOR_DESIGN §3).

## 5. The launcher and the loader (§1 items 1–3, 10, 12, 13)

### 5.1 The launcher refuses a session directory under the working directory

`src/scala/tat.scala`, step 3, before `Build.build_logic`: the
`Sessions.Background` the launcher already computes moves first,
`session_background = Sessions.background(…).check_errors`; every
directory of its `sessions_structure.session_directories` — the map from
each known Isabelle session's directories, as `canonical_file`, to the
session's name, the same table `Resources.init_session` ships to the ML
side and `find_theory_file` reads — is tested against the working
directory's `canonical_file` with `File.relative_path`, Isabelle's own
"equal to or under" on path elements; one that answers ends the tool with
§1 item 1's sentence, through `error`, exit code 2 like the launcher's
other refusals. Every refusal thereby precedes anything built or
started, as the launcher's others do: a refused launch costs no heap
build, and §7's launcher case starts no Isabelle process. The reorder is
observationally neutral otherwise: `Build.build_logic`'s own `no_build`
test build loads the same structure first, and `Sessions.background`'s
errors are a subset of its. `Store.session_heaps` and
`Isabelle_Process.start` stay after the build. The layout is fixed for
the life of the Isabelle process, so no file under the working directory
can ever be found from source afterwards, and the ML side needs neither
the working directory nor a comparison.

`lib/tat.jar` is rebuilt as MODULE_STRUCTURE §5 describes.

### 5.2 The loader and the name checks

`fetch` takes the theory name alone, no longer the node's file, and no
qualifier: the surviving conditional — `Resources.find_theory_file`
answers and the name is not a qualified one whose short name is global
(§1 item 18), or the not-found error of §1 item 3 — replaces
`load_target`, whose comment described the by-path arm and goes with it.
`load`'s precondition is the guard that establishes it, not a name shape:
it is handed the one name the Isabelle session layout gives the file —
`<session>.<short name>`, or the short name alone when the layout
declares it global, which `Resources.theory_name` leaves unqualified —
never a path, never a bare non-global name, whose qualifier is no
Isabelle session, and never a qualified name whose short name is global
(§1 item 18). With the
by-path arm gone the qualifier threaded into `fetch` and `load` can
change no result — every name reaching them is a `#theory_name`
`Resources.import_name` produced, on which `theory_name` is the identity
— so both drop it and `load` calls `Thy_Info.use_theories` with `""`,
under which a name survives unchanged by construction; the comment says
so. `resolve` passes `#theory_name` of the node `Resources.import_name`
returns. `fetch_named` keeps `Resources.import_name` as the validation
it has been performing — Isabelle's own refusals of a `.thy` suffix and
of a path-shaped name, each in Isabelle's words — and passes
`#theory_name` to `fetch`; its guard and message are unchanged.

`check_new_theory_short_name` answers one of three, in this order: a
loaded theory bears the short name — its long name, as today (for a
loaded global theory that is the short name itself); no loaded theory
bears it but `Resources.global_theory` knows it — reserved (§1 item 12);
free. The wire shape is the author's. `Theory.gen` raises
`DuplicateTheoryShortName` with the holder, or `ReservedTheoryName`, a
`BadEdit` beside it in EXCEPTIONS.md §3, rendering §1 item 12's sentence.
The refusal happens at creation, where EVALUATOR_DESIGN §7 puts it.

The name grammars are two predicates in `model.py`, used three times:
`_ISABELLE_IDENTIFIER`, narrowed to exclude the prime, for the theory
short name (§1 item 10, `Theory.gen`'s check as today); and the
session-name predicate (§1 item 10) for the session name, a check
`Session.gen` gains, and for each half of an `imports` item (§1 item 13),
the same predicate applied, not a copy. The item check is Isabelle's two steps in
Isabelle's order: a `.thy` suffix refused on the whole item first — as
`Thy_Header.import_name` refuses it before exploding the path
(`Pure/Thy/thy_header.ML`), and since `thy` is itself a legal half — then
the item-half grammar on the one or two halves; §1 item 5's identity
claim is a consequence of that order, and the `model.py` comment cites
the line. `InvalidName` carries one three-valued selector naming the
grammar it renders — the framework's, the theory name's, the session
name's — chosen by the raiser, in place of today's boolean. The session
grammar is strictly narrower than the framework's and `Session.gen`
judges first, so the framework's sentence can no longer fire for a
`Session`: a backstop, as it already is for `Theory`.

Consequences, all wanted: the bare cross-session import fails as §1 item
4 says; a `.thy` left behind under a `Session`'s folder is never loaded,
since no session directory lies under the working directory —
FIRST_END_TO_END_RUN_PLAN.md §1's open item, keeping the directory equal
to the forest, stops being a correctness question; a tree Isabelle could
never open, or a `Session` under which nothing could run, is refused at
creation; and whether an import exists is still `begin_theory`'s report
at evaluation, `Theory.gen` judging only the item's shape (§1 item 5).

## 6. Walking trees whole, and `evaluate_to(evaluate=False)`

One helper walks trees whole in `Invalidating` mode:
`Forest._invalidate_trees(ev, trees)`, each tree's `_evaluate(ev,
INVALIDATING)` in order, under the caller's `Evaluation`, no flush of its
own; it asserts the forest's lock as `_run` does. Its callers are §3.3's
cases 1 and 2, §4.1, §4.2, and the internal form below.

`Node.evaluate_to(evaluate=False)` on a `Theory` runs
`_invalidate_from(Location(session, index))`, which §3.2 walks nothing —
today the call is a no-op on a tree, against ARCHITECTURE §3.5's "a
nesting node at that position is invalidated whole". The internal form
gets the meaning the sentence promises: on a node whose parent is an
`Unchained_Node` — the property that makes "the node whole" equal to
"from this position on", since nothing chains it — it walks the node
whole, `_invalidate_trees(ev, [self])`, under one `Evaluation` the entry
owns and flushes, as `_invalidate_from` does for the other entry. For a
`Theory` that is the tree; for a `Session`, which cannot be walked as
itself (`Session._evaluate` raises), each tree under it, in order; for
the chained fake block the single-tree test double puts under its root,
exactly what `_invalidate_from` did. The root keeps its
`TAT_InternalError`: the internal form's destination is a position, and
the root stands at none. The `Seeking` rule for edits is unchanged,
since the entries never rely on that position to invalidate a tree (§4.2
does). No product code calls the flag today; the fake-table suite does.

## 7. Tests

**The fake-table suite.** A new `test/test_forest_walk.py` on
`test_session_theory.py`'s fakes (`Fake_Theory`, `Failing_Header_Theory`,
`Failing_End_Theory`, the leaf `t` that can fail) over the real `Forest`,
each fake recording the order it ran in. `test_model.Table` gains the fake
`theory_delete`, keeping its calls in a record of its own beside a fake
theory table that the fakes' endings write their qualified name into,
asserting no store transaction is open as the other mutating fakes do;
`Table.calls` stays the state slot table's. `invariants.py` gains: the
two one-way statements the fake theory table implies, over the predicate
the framework owns — every tree answering `_operations_ready()` has its
qualified name in the table, and every name in the table is the
qualified name of a current tree; neither converse holds, the first
because §4.3 keeps an entry after the tree is invalidated, the second
because a failed header leaves the ending `ready` with no value — and
§4.1's premise, that a tree one of whose resolved imports does not answer
`_operations_ready()` is `not_evaluated` throughout. Cases:

- an importer runs its import first, bare within a `Session` and dotted
  from another; a bare cross-session name creates no dependency; an
  external name creates none; the header renders every item quoted;
- a `Session` as destination runs every tree under it to its `end`,
  imports outside the `Session` first; the root, every tree; a tree not
  imported by a target is not touched;
- the order constraint: the importer placed before its import is
  `not_evaluated` throughout, the result names its `Theory` node,
  `_order_violation` answers the item as written, and the sentence
  composed from the two equals RENDER_BASELINES §3's line, asserted
  verbatim with `baselines.fenced_lines`; `_order_violation` answers
  `None` on the leaf a case-3 stop reports and on a non-violating
  `Theory` node; the import itself runs; after the repairing `move`, the
  same call runs it; the first offending item as written is the one
  answered; a two-tree cycle is a case-1 stop of the earlier tree, the
  later tree not run, `not_evaluated` throughout and every node of it
  rendering `(not evaluated)`, while the result names the earlier tree's
  `Theory` node; a self-import is a case-1 stop; every reading terminates;
- the stop crossing an import dependency, under each outcome of the
  import: a failed header (no stop of its own; the importer not run,
  `not_evaluated` throughout, the result naming the import's `Theory`
  node), a failed `end` (the import's own stop, reported once), a leaf's
  own stop inside the import (reported once, the importer and a third
  tree importing it not run); a tree importing two trees whose headers
  both failed reports the item written first; with `ignore_error`: the
  leaf's own stop is carried past, so the import's `end` runs and the
  importer runs after it; a failed header and a failed `end` still block
  the importer, not run, and the result reports nothing — both asserted,
  so a future skip of case 2 fails; the order constraint's stop is
  reported under the flag, and a reorder into a violation leaves the
  ready tree standing until the next walk invalidates it whole; a
  destination inside a blocked tree leaves the tree `not_evaluated`;
- several stops: the first in tree order is reported;
- the flush after each tree: two trees with no dependency between them,
  each with a failing leaf, run once with `ignore_error` so both are
  written whole, then once without — each tree's own stop then releases
  its own slots, and `Table.calls` shows two `delete` calls in tree order
  with disjoint, non-empty name sets, which one final flush would merge;
- §4.1: an edit inside an import, and `evaluate_to` on an inner node of
  it, leave its importers and their importers `not_evaluated` whole, with
  their slots released and `on_invalidated` fired; the next `evaluate_to`
  on the last importer reruns the chain in order; an ending leaving
  `ready` for `not_evaluated` because a leaf stopped — after a run under
  `ignore_error` — invalidates its importers outside the walk, an own
  stop in one of them reset; a `ready` tree moved into the `Session` its external
  dotted import names, so that it imports itself: the record comparison
  walks it, the setter re-enters its own walk, the walk terminates and
  the tree is `not_evaluated` whole;
- §4.2: an amend renaming a tree, an amend renaming a `Session`, a move
  into another `Session`, and a delete each invalidate the changed trees
  and their importers and send exactly the vanished names in one
  `theory_delete`; an amend renaming a tree and adding a fresh tree under
  the old name in the same call leaves every name standing and every
  importer `not_evaluated`, the record holding the nodes; an amend of a
  tree's `Theory` node — changing a forest import, an external import, or
  nothing, and while the tree was blocked or `not_evaluated` — leaves its
  importers and their importers `not_evaluated` whole, sends nothing, and
  the forest still renders; an amend of the obstacle `Theory` node itself
  leaves the chain it blocked `not_evaluated`, and the next call runs it;
  a delete of the tree at the head of a blocked chain leaves the chain
  `not_evaluated` and sends the vanished name;
  an insert whose name an existing import already names invalidates that
  importer; a reorder within a `Session` and a reorder of `Session`s send
  nothing and invalidate no tree; an edit inside a tree sends nothing and
  changes no record, its importers being pinned by the §4.1 bullet; the
  mirror and the invariants hold after each;
- §6: `evaluate_to(evaluate=False)` on a tree releases what it wrote —
  the existing, until now vacuous call at `test_session_theory.py`'s
  owned-slot case gains that assertion — on a `Session`, every tree under
  it;
- names: `test_names` moves `P'_2` to its refused theory names; its four
  malformed session names (`Ch 2`, `x-`, `-x`, `Ch.2`) and a primed one
  assert the session rendering, the comment saying the class's own
  grammar judges a `Session`'s name and the framework's rendering cannot
  fire for one; a primed leaf name stays accepted. `test_the_field_checks`
  covers §1 item 5's sentence at `imports[1]` with `"lib/Rel"` (moved
  there from the header fixture, whose surviving items are `Main` and
  `HOL-Library.Multiset`), `Main.thy`, `A.B.C`, `S'.Foo`, `S.Foo'` and
  `-x` refused — a prime in either half — and `Launchbury.AList-Utils`
  accepted and rendered quoted; an empty
  item keeps "must not be empty"; both header assertions of that file
  take the quoting; a reserved name (`FOL` in the fake heap's global
  table) is refused with §1 item 12's sentence, a loaded global (`Main`)
  as taken with its own name;
- the existing `test_a_walk_never_reaches_a_session` stays.

The three new sentences of §1 items 10 and 12 are pinned by
`test_exceptions.py` against RENDER_BASELINES §2 as the others are;
`test_plugin.py`'s shipped `theory` example loses its path item.
`test_session_theory.py`'s `Forest_Under_Test` is built on `M.Forest`;
`test/routing_forest.py` is deleted; `test_model.py`'s `OneTreeForest`
needs nothing.

**The ML end-to-end driver** (`test/tat_framework_ml_test.py`, run by
`test/run_ml_framework_test.py`; it retires into the harness later), in
two instalments (§9):

- with step 1, on the test double it uses today: a bare cross-session
  import from a second Isabelle session fails with the sentence naming
  `T.A`; the by-path import (`"lib/TAT_Lib_Rel"`) fails with the
  sentence — `test/lib/TAT_Lib_Rel.thy` retires with the arm; the
  existing `TAT_No_Such_Theory` case asserts the whole sentence naming
  `TAT_TEST.TAT_No_Such_Theory`, its comment corrected from Isabelle's
  wording to TAT's; the load-from-source arm's positive case imports
  `Theory_Agent_over_Trees.TAT_Lib_Helper`, which `find_theory_file`
  resolves once the repository `ROOT` gains `directories "test"` (no
  build target: `directories` only adds theory search directories), with
  the staleness guard the old case had and the holder assertion taking
  that name; the short-name check answers taken for `List` and for
  `Main` (holder `Main`), reserved for `FOL`, free for a fresh name —
  through `Theory.gen` over the live wire, since step 1 lands the check
  whole (§9);
- with step 2, the driver's forest on `M.Forest`: after the existing
  `edit.delete(ta)`, `tb` is `not_evaluated` whole and the following
  `evaluate_to` fails its header with the sentence naming
  `TAT_E2E.TAT_E2E_A` — the one place §4.2's record, the real
  `theory_delete` round trip and `Loader.resolve`'s refusal meet; the
  existing `TAT_E2E_C` case asserts the whole not-found sentence naming
  `TAT_E2E.TAT_E2E_Nowhere`; the instalment ends by deleting the `Session`
  whole, one `theory_delete` carrying a name the table holds and one it
  never held.

**The launcher.** One case beside the `TAT_new` cases, a plain
`subprocess.run`: a working directory holding a `ROOT` declaring `session
Foo in "Foo" = HOL +` (the folder need not exist: `Foo` is never selected,
and `canonical_file` resolves a path that does not); `isabelle TAT -d
<working directory> <working directory>` exits 2 with §1 item 1's
sentence naming `Foo`, verbatim, and starts no Isabelle process.

## 8. Files

| file | change |
| --- | --- |
| `isabelle_theory_agent/model.py` | the two name predicates and `Session.gen`'s check; `Theory.gen`'s item check and the three-way short-name answer, `Theory.header()` quoting, `Theory.qualified_name`; `StdBlock._set_ending` async, `Theory._set_ending` with §4.1; `Forest._trees`, `_resolved_imports`, `_importers`, `_closure`, `_order_violation`, `_handle_tree`, `TreeRecord`, `_record`, `_invalidate_changed_trees`, `_invalidate_trees`, `_evaluate` (§3), the docstrings of `Evaluation`, `Forest._run` and `_invalidate_from`; `Node.evaluate_to` (§6) |
| `isabelle_theory_agent/exceptions.py` | `ReservedTheoryName`; `InvalidName`'s three-valued selector and session-name rendering |
| `isabelle_theory_agent/edit.py` | the record and the comparison in the four entries (§4.2) |
| `isabelle_theory_agent/isabelle_driver.py` | `theory_delete`; `check_new_theory_short_name`'s three answers |
| `ML/TAT_Framework.ML` | `Theories.delete`; `TAT.theory_delete`; `framework_callbacks` over both tables; `fetch`, `load`, `resolve`, `fetch_named` (§5.2); `check_new_theory_short_name` and its `ret_schema` (§5.2) |
| `src/scala/tat.scala`, `lib/tat.jar` | the refusal of §5.1 and the reordered step 3 |
| `ROOT` | `directories "test"` (its purpose recorded in MODULE_STRUCTURE §1, §10) |
| `test/test_forest_walk.py` | new (§7) |
| `test/test_model.py`, `test/invariants.py`, `test/test_session_theory.py`, `test/test_exceptions.py`, `test/test_plugin.py` | the fake `theory_delete` and the fake theory table; the statements and the invariant; `Forest_Under_Test` on `M.Forest`; the quoted headers, the moved path item, the name cases; the three sentences; the shipped example |
| `test/routing_forest.py`, `test/lib/TAT_Lib_Rel.thy` | deleted |
| `test/tat_framework_ml_test.py` | the probes of §7 |
| `test/test_launcher.py` | the launcher case |
| the documents of §10 | |

## 9. Order of work

A rule for the cuts: a step may add a callback with no caller, but a
step that changes an existing answer lands with the code that reads it.

1. ML (§4.3), the launcher (§5.1) and the jar, `ROOT`'s `directories
   "test"`, the loader (§5.2's `fetch`, `load`, `resolve`, `fetch_named`)
   and the driver's `theory_delete`; the short-name check whole across
   its layers — ML `check_new_theory_short_name` and its `ret_schema`,
   `isabelle_driver.check_new_theory_short_name`, `Theory.gen`'s reading
   of the three answers, `ReservedTheoryName` with §1 item 12's sentence,
   its RENDER_BASELINES §2 line and `test_exceptions.py` case, and
   `test_session_theory.py`'s fake of the wire; the ML driver's first
   instalment on its present double; the launcher case. The REPL
   restarted; the driver, the launcher case and the Python-only suite
   green.
2. `model.py` §3, §4.1, §5.2's name grammars and `InvalidName`, and §6,
   then `edit.py` §4.2; `routing_forest.py` deleted; the fence lines of
   SESSION_AND_THEORY §3 and RENDER_BASELINES §2 that the two name
   sentences and the `InvalidField` reason need, and EXCEPTIONS.md §3's
   rows, since the suite pins them; every existing test green on the real
   `Forest`; the driver on `M.Forest` with its second instalment.
3. `test_forest_walk.py`, the fake table's statements and the invariants
   (§7), written case by case against the code of step 2.
4. The documents (§10).
5. Review of the whole; commit on the owner's word.

## 10. Documents

Transcription of §6 and of §1's decisions — no new design; "import
edge" in the sections touched becomes "import dependency" (ARCHITECTURE
§1), EVALUATOR_DESIGN §3's "dependency edges" included; the one name
"Isabelle session layout" throughout:

- `docs/ARCHITECTURE.md` §1 (the glossary row of §1 item 14), §3.3 (the
  two forest-level stops: the order constraint's, walked `Invalidating`
  and reported whatever `ignore_error` says, its sentence composed from
  `_order_violation`; the stop crossing an import dependency, the tree
  blocked and `not_evaluated` throughout, the stop the import's `Theory`
  node, not reported under `ignore_error`; "the call then returns
  continue" gains the first as its exception; the `cannot_evaluate` node
  an obstacle and what it blocks `not_evaluated`, in §3.2's table and
  §3.3's opening), §3.4 (the
  first paragraph: the outcome §4.1 delivers — no transitive importer
  keeps a current result — on the ending leaving `ready`; the second
  paragraph replaced by the invariant, stated
  in qualified names and resolved import sets, not the plan's "record":
  no tree stays evaluated once a tree it transitively imports has been
  edited, renamed, moved, deleted or had its `Theory` node replaced,
  renaming a `Session` doing that for every tree under it, a reorder of
  trees or of `Session`s touching no tree; the third paragraph: a walk
  deletes what it has released at each tree's end and again when it
  ends), §3.5 (a tree's transitive imports run before it, in tree order,
  under the order constraint; the "Without `evaluate`" paragraph split
  into the two walks it now covers — `evaluate_to(evaluate=False)` names
  a node and invalidates it whole, opening first, for a `Theory` the
  tree and for a `Session` every tree under it; an edit's invalidation
  has a position, inside a tree the node standing there whole together
  with what follows it in that tree, the index after the last child
  naming the parent's ending, and at the `Session` layer and the root
  nothing, sibling trees being independent and the trees concerned
  reached through the comparison of §3.4 — with the closing sentence
  about a deletion scoped the same way), §8 (an import the base heap
  lacks is loaded from source when the Isabelle session layout knows
  its file).
- `docs/MODULE_STRUCTURE.md` §1 (the `ROOT` entry also declares
  `directories "test"`, which puts `test/` among the session's theory
  search directories so a `.thy` there is found by its session-qualified
  name, while declaring no theory there, so "nothing ever runs on its
  heap" stands), §2.2 (`delete`), §2.3 (`load`, `fetch`, `resolve`:
  theories the Isabelle session layout knows, nothing by path, no
  qualifier; `check_new_theory_short_name`'s three answers, the reserved
  names intensionally), §2.6 (`TAT.theory_delete` in step 3), §4.1 (the
  ending setter's rule and its guard, termination from the
  setter; the entry points and the three destination shapes — an
  evaluating walk has a destination node, an edit's invalidation seeks a
  Location, a whole-node invalidation has neither and starts in
  `Invalidating`; the `Evaluation` sentence and its code-block comments:
  one `Evaluation` per tree walk of §3.3 and one for every other walk,
  each flushed by whoever created it, so a walk over several trees
  deletes what it released at each tree's end; `_order_violation`; the
  `Forest` bullet as it stands, now true), §4.2 (the record at the entry's start, before anything is
  built; the comparison between step 4's completed events and the
  invalidation the entry ends with), §4.3 (`theory_delete`, the
  three-way answer), §5 (step 3 reordered: the background and the
  refusal, then the build, the heaps, the process; the refusal's
  sentence; the canonical comparison; "exiting with the build's own code
  when it fails" narrowed to a session that fails to build, every other
  error exiting 2; the boot's "the process's session environment"
  renamed to the Isabelle session layout).
- `docs/EVALUATOR_DESIGN.md` §2 (the third arm stated once, as §1 item
  2 words it; the other documents point here), §6 (`load`'s precondition
  as §5.2 states it: the name `find_theory_file` answered for,
  session-qualified or global, never a path or a bare non-global name;
  the path form gone), §7 (the reserved names refused at creation).
- `docs/EXCEPTIONS.md` §3 (`ReservedTheoryName` beside
  `DuplicateTheoryShortName`; the `InvalidName` row rewritten for its
  selector and its three raisers, the grammars left to RENDER_BASELINES
  §2; the reason count of the two classes written without a numeral;
  the home list naming both homes of RENDER_BASELINES §3 once
  `test_forest_walk.py` reads its Python-side line).
- `docs/RENDER_BASELINES.md` §2 (the theory-name sentence without primes;
  the session-name sentence; the reserved-name sentence), §3 (the
  not-found sentence's cases: no forest tree, no base-heap theory, no
  file the Isabelle session layout knows; the wording unchanged; the
  order constraint's sentence composed from the forest's answer; the
  attribution to `Loader.fetch`).
- `docs/PRINT.md` §1 (the `blocked by <id>` row gone; a `not evaluated`
  node's obstacle found through the `failed` marks and the tool's
  answer), §3, §7 (the example's lines); `docs/RENDER_BASELINES.md` §5
  (the `blocked by` line gone).
- `docs/MCP_SPECIFICATION.md` §2 (theory and session names take no
  prime), §4 (the `ignore_error` clause bounded to the stops inside a
  tree, which stops the flag can pass left to ARCHITECTURE §3.3; "every
  tree it ran" widened to a node named from a tree the call did not
  run).
- `docs/node_classes/SESSION_AND_THEORY.md` §1 (the session name's
  grammar and its check, strictly narrower than the framework's, whose
  sentence is a backstop that cannot fire for a `Session`; the
  loaded-from-source clause, as ARCHITECTURE §8), §2 (the `name` row
  without primes; the `imports` row: the two shapes, each half in the
  session grammar, no `.thy`, quoted in the header; `Theory.gen`'s check
  list with the reserved names), §3 (the new `InvalidField` reason,
  pinned like the others).
- `docs/TOOL_SCHEMAS.md` §4: nothing now; the sentence's rendering waits
  for the `evaluate_to` tool.
- `ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md` §1 (the open item's
  correctness half closed), §3 (the `imports` row: the two shapes, no
  path, no `.thy`; the name row without primes; the prose check list
  struck in favour of the pointer to SESSION_AND_THEORY §2 it already
  names, and "§5 may add one forest-only check" struck as answered by
  §1 item 4), §5 (settled: §1 item 4), §6 (implemented; the record, its
  resolved imports the `Theory` nodes themselves, and the ending's rule
  on its one clause; "import edge" corrected), §7 step 4 (the record).
- `ai-artifacts/STEP5_HANDOFF.md`: step 4 done before the tools; its
  completed to-do struck.
- `ai-artifacts/TEST_HARNESS_PLAN.md`: §1 item 4 withdrawn (§1 item 11
  here), and with it every `test/ROOT`, every `TAT_Test.` qualifier and
  every `-d test` — §3's working-directory paragraph, §4 steps 2 and 3,
  §5, §7's file row, §8 step 3; the plugin is
  `Theory_Agent_over_Trees.Test_TAT_Framework` throughout;
  `routing_forest.py` gone and the harness's tree cases unblocked;
  `test/TAT_Lib_Helper.thy` stays as the load-from-source material,
  imported by its session-qualified name, `test/lib/TAT_Lib_Rel.thy` and
  the `master_dir` sentence go.

## 11. Shapes the author decides, stated so they are visible

- Only the ending setter becomes `async` (§4.1); §6's sentence says "the
  status setters", but the other two carry no rule.
- The importers are reached by direct importers plus recursion through
  the same rule (§4.1).
- The closure is handled by one three-case procedure per tree (§3.3)
  rather than "imports, then `T`"; the outcomes are §6's, and the
  procedure is the same for one tree and for many.
- `_resolved_imports` answers in the order of the `imports` items as
  written, so case 2 picks the first not-ready import the way case 1
  picks the first offending item (§3.1, §3.3).
- Both forest-level stops leave the tree walked whole in `Invalidating`
  mode (§3.3); the blocked mode is the recursion's, inside a tree.
- The record holds the imported `Theory` nodes themselves (§4.2): the
  design's pair, an `amend` seen through its importers' records.
- Each tree of §3.3's loop walks under its own `Evaluation`, flushed
  when it ends: the owner's §1 item 15, not a shape of the author's.
- `_order_violation` is total on nodes and answers `None` off a
  violating `Theory`, so the renderer asks it of any `stopped_at`.
- The wire shape of `check_new_theory_short_name`'s three answers;
  `InvalidName`'s three-valued selector; `fetch` and `load` without a
  qualifier.

## 12. Deferred

- The rendering of the order constraint's sentence from
  `_order_violation`: TOOL_SCHEMAS.md §4, with the `evaluate_to` tool.
- RENDER_BASELINES §3's sentence reads oddly for a self-import, where the
  tree and the item coincide; the owner approved a variant on 2026-10-05
  (RENDER_BASELINES §3's second line), rendered with the first by the
  `evaluate_to` tool.
- The AFP Isabelle session `CoreC++`, and its theory of the same name,
  cannot be imported: `+` is outside §1 item 13's grammar.

## 13. Implementation record (2026-09-23)

- **What landed.** §9's steps 1–4 as written, on `main`, uncommitted
  until the owner's word: the ML side, the launcher and `lib/tat.jar`,
  `ROOT`'s `directories "test"`, the loader and the three-way short-name
  check (step 1); the walk, the `Theory` ending's rule, the record every
  edit compares, the name grammars, `Theory.header()` quoting, the
  whole-node invalidation, `test/routing_forest.py` and
  `test/lib/TAT_Lib_Rel.thy` deleted (step 2); `test/test_forest_walk.py`
  and the invariants (step 3); the documents of §10 (step 4).
- **Outcomes.** `python -m pytest test --ignore=test/test_launcher.py`:
  281 passed. `python -m pytest test/test_launcher.py`: 6 passed, the
  launcher case included. `python test/run_ml_framework_test.py`, on a
  fresh REPL server (base session `Minilang_AoA`): passed after step 1,
  after step 2, after each review's changes, and after §1 item 18's
  `fetch` change, its `HOL.Main` probe included. `lib/tat.jar` rebuilt
  by `isabelle scala_build`, `etc/build.props` restored.
- **The review** (§9 step 5; six challengers, three fresh defenders per
  finding, one judge, Opus 5.5 at xhigh, in English; the brief
  `BRIEF_IMPL.md`, the diff and the ruling `ruling_impl.json` beside the
  earlier reviews' files in the review session's scratchpad): NOT_READY
  on one blocking defect, an owner item — a cross-tree `blocked_by`
  copied from an import's beginning could outlive its node when the
  import's ending was already `not_evaluated` (a destination inside a
  blocked tree, in a cycle), so that a later `amend` or `delete` left a
  pointer to a node outside the forest and the next rendering raised
  `TAT_InternalError` — and some twenty author items, all applied: the
  `TreeRecord` named tuple, `_THEORY_NAME`, `fetch_named`'s comment, the
  `Evaluation` and `Invalidating` docstrings, three documents' account of
  the record's third component, the tests that mutation testing showed
  missing (the ending leaving `ready` for a stop, a reorder into a
  violation on a ready tree, the cascade beyond an edit's direct
  importers, the record's identities, `refused` asserting the reason,
  the not-touched case on an evaluated tree), and the hand-off's
  bookkeeping.
- **The confirming review** (same recipe, Opus 5.5; brief
  `BRIEF_IMPL2.md`, ruling `ruling_impl2.json`): READY_WITH_FIXES —
  items 16 and 17 verified correct case by case, every first-round item
  verified applied; five stale sentences of the withdrawn status model
  (ARCHITECTURE §3.2, MODULE_STRUCTURE §4.1, PRINT §1 and §3, plan §7),
  "obstacle" used for two concepts, the blocked mode as a singleton
  `Blocked` in place of a flag, `_is_own_stop` gone, the invariant in
  item 16's own words, one fixture and one case for the order
  constraint's first item, the vestigial blocked-chain case deleted,
  three docstrings trimmed — all applied. Of its proposals the author
  took two as internal shapes, told to the owner: case 2's tree walked
  `Invalidating` like case 1's, and the record holding the imported
  nodes themselves (§1 items 9 and 16, §3.3, §4.2, §11). The third the
  owner settled as item 18, measured first on Isabelle itself, batch and
  PIDE alike: `imports "HOL.Main"` loads clean and the next theory
  importing `Main` beside it dies of `Duplicate theory name`; `fetch`
  now refuses such a name, with a probe in the ML driver.
- **The re-read** (one fresh reader, Opus 5.5, over the whole diff after
  the fixes above): every ruled shape verified in the code; nine stale
  sentences found — TOOL_SCHEMAS §4's "stopped at an obstacle", the ML
  `load` comment, RENDER_BASELINES §3's and EVALUATOR_DESIGN §2's account
  of `fetch` without item 18, and five of this plan's — all corrected.
- **The owner's decisions on the review.** Items 16 and 17: a blocked
  node is `not_evaluated` and no status names its obstacle, so the class
  of defect is gone by construction rather than by either repair the
  judge weighed (`_obstacle_of` reading the ending alone, or the
  importers' closure walked); the ending's rule back to its one clause.
  `ai-artifacts/STEP5_HANDOFF.md` stays out of this commit, with this
  step's own edits to it, since it carries the other session's
  uncommitted text.
- **Still open.** TOOL_SCHEMAS §4's rendering of the order constraint's
  sentence, with the `evaluate_to` tool; `TEST_HARNESS_PLAN.md`'s
  revision (its first-review rulings and §10's amendments), then its
  review and the harness itself.
