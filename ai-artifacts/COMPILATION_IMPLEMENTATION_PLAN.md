# Implementation plan: the walk and the stored statuses, then compilation

Written 2026-10-04 by the compilation session, on the tree at `ba5f999`.
Phase A (§3) is implemented and reviewed (§7); Phase B (§4) is not
begun. The design is in the documents under
`docs/`; where a section is cited, the section is the specification.
This plan gives the order of the work, what each step needs, the code
shapes the author has already worked out, the tests each step changes
and adds, and when it is done. The record of the reviews and rulings is
`COMPILATION_REVIEW.md` (**CR**), whose §14 is the work order this plan
details: steps A1 to A8 here are CR §14's items 1 to 8, under the same
numbers.

Short names: **MS** = docs/MODULE_STRUCTURE.md, **AR** =
docs/ARCHITECTURE.md, **CO** = docs/COMPILATION.md, **ST** =
docs/node_classes/SESSION_AND_THEORY.md, **CIP** =
ai-artifacts/CONSTRUCT_IMPLEMENTATION_PLAN.md (the jobs session's),
**LIP** = ai-artifacts/LOGGING_IMPLEMENTATION_PLAN.md, **LCR** =
ai-artifacts/review/LOGGING_CODE_RULING.md.

Conventions. No `isabelle build`; the Isabelle side is exercised
through the test harness, which starts a real `isabelle TAT_mcp`;
`lib/tat.jar` is rebuilt with `isabelle scala_build` (remove
`no_build` from `etc/build.props`, build, restore it) and only while no
`isabelle TAT_mcp` runs. Repository files are edited by hand, never by
script. A step is done when the tests it names pass, the suite has no
failure beyond §1's list, and `pyright isabelle_theory_agent` is clean.
Commits are on `main`, on the owner's word ("批准提交"); a push only on
request, to `origin`. Agent-facing sentences are read from the
documents by the baseline tests, never typed into a test.

## 1. The state on 2026-10-04

- Before Phase A, `main` at `ba5f999`: the frozen step-1 code of CR §9
  (the status values, the stored statuses, the three setters, the walk
  with `Blocked`, `Seeking` and `Invalidating`) in HEAD, swept into the
  logging session's commits; the logging session's Python side (LIP
  steps 1 to 4), Isabelle side and launcher (5, 6, 8) and scripts (9,
  12) in. Without Isabelle 319 cases passed and 18 failed.
- With Phase A in the tree: without Isabelle 333 cases pass and the
  same 18 fail; the 23 Isabelle-backed cases, deselected by `-m "not
  isabelle"`, pass through the harness. `pyright isabelle_theory_agent`
  reports nothing. The 18 are CIP §2's table; two of them wait for this
  plan: `test_session_theory::test_the_field_checks` (B2) and, in part,
  `test_exceptions::test_every_baseline_is_covered` (B2's
  `ReservedSessionName` lines).
- The documents already describe the target: AR §3.2–§3.6, MS §4.1
  ("Status", "States", "The recursion") and §4.2, CO whole, LOGGING §4.

## 2. What each phase needs from outside

**Phase A** (steps A1 to A8: `model.py`, `edit.py`, `store.py`,
`plugin.py`, `mcp.py`, `test/`; A5 also `isabelle_driver.py`, `log.py`
and two other repositories) needs no other session's code and no
decision still open.

Phase A touches no ML and no Scala, and none of `toplevel.py`,
`mcp_server.py`, `jobs.py`, `exceptions.py`, `test/harness.py`,
`test_mcp_server.py`, `test_toplevel.py`, `test_launcher.py`, so CIP's
steps 1 to 3 and the logging session's remaining steps (LIP 10, 11)
share no file with it. CIP step 3 runs `test_session_theory.py` and
`test_conversation.py` unchanged while Phase A edits both: whoever runs
them sees the other's work in progress, and says so before reading a
failure as its own.

**Phase B** (steps B1 to B8: compilation) needs no other session's
code either. It needs one thing, which §5 point 3's order gives it:
while it runs, no other session edits `isabelle_theory_agent/`, `ML/`,
`src/scala/`, `lib/tat.jar` or `test/` — the jobs session's steps 1 to
3 are in before B1 and its steps 4 to 17 start after B8 — the logging
session's `mcp_server.py` and `test_mcp_server.py` (LIP 10, 11) aside,
which Phase B does not touch.

**What waits for this plan.** CIP steps 4 to 17 wait for Phase A; CIP
step 14 for A2's `_slots_written_by` and A5; CIP step 15 for B5's folder;
CIP step 16 for B3, B4 and B6. The logging session's four tests (LCR
funnels-2 (iii), funnels-4, funnels-7 (d), tests-2's second half) wait
for A1, A2 and A3.

**What Phase A leaves to the jobs session** (CIP §1 and its steps 8, 9,
12 and 13): `Evaluation.starter` and `Evaluation.dropped`; in the three
setters, the stored check's clearing, `_on_context_change` through
`_completed` and the evaluation job's drop; `cancel(ids)` at each
flush; `Node.evaluate_to`'s `agent` and `checks` parameters, and an
edit's and a move's own evaluation under `"quick"` (until then
`mcp.py`'s walk carries `"no"`); `check_outcome()`, `_unfinished()`;
the rows `job`, `check` and the automatic-construction setting;
`Conversation.forget` over the agents' sets; the test of an
`_on_context_change` that raises under an edit. And of Phase B: the
`text ‹…›` block `Theory.emit_beginning` writes for a `description`
(ST §2), which lands with the field in CIP step 13.

## 3. Phase A: the walk, the setters, the edit's commit, the store

Order: A1, A2 and A3 together — the walk cannot be rewritten without
the setters' guard, and `edit.py` imports `Seeking` — with A6, which is
three lines of A1's `Forest._run`; then A4, A5, A7. The suite is run
after A1+A2+A3 with A7's helpers and changed expectations, and again
after each later step.

### A1. The walk

Specification: AR §3.3–§3.5; MS §4.1 "The recursion"; CO §4 "Past the
destination or a stop"; LOGGING §4 `evaluation`; CR §13 (rulings
simplicity-1, -2, -3; reader 8's ruling).

Goes from `model.py`: `Blocked`, `BLOCKED`, `Seeking`, `Invalidating`,
`INVALIDATING`, `EvaluationMode`, `Node._mark_not_evaluated` (all four
definitions), `Forest._invalidate_whole`, `Forest._invalidate_trees`,
`evaluate_to`'s `evaluate` parameter and the root's refusal,
`Forest._run`'s `mode` and `store` parameters, the per-tree `own`
`Evaluation` in `_handle_tree`.

The shapes:

```python
class Evaluation:                       # one walk, or one edit's commit
    def __init__(self, destination: Node | None, ignore_error: bool, checks: str = "no"):
        self.destination, self.ignore_error, self.checks = destination, ignore_error, checks
        self.passed: list[Node] = []    # reached in Evaluating: a leaf when reached, a nesting node at its ending
        self.stored: set[Node] = set()
        self._released: set[str] = set()
        self.releases = 0               # slots deleted over every flush (as today)
    def release(self, slot) -> None     # as today
    async def flush(self, conversation) -> None   # as today

@dataclass(frozen=True)
class Evaluating:
    rewritten: bool = False

@dataclass(frozen=True)
class EvaluationResult:
    stopped_at: Node | None
    mode: Evaluating | None             # None: nothing more runs in this tree
```

On `Node`:

```python
def _is_under(self, ancestor: Node) -> bool      # strictly: `ancestor` is one of this node's ancestors
def _mode_after(self, ev, stop: Node | None, ran: bool) -> Evaluating | None:
    return None if self is ev.destination or stop is not None else Evaluating(rewritten=ran)
def _reached(self, ev, ran: bool) -> EvaluationResult:      # the tail of every node the walk reaches
    ev.passed.append(self)
    stop = self if not isinstance(self._resulting_status(), Ready) and not ev.ignore_error else None
    return EvaluationResult(stop, self._mode_after(ev, stop, ran))
@abstractmethod
async def _evaluate(self, ev: Evaluation, mode: Evaluating) -> EvaluationResult
@abstractmethod
def _invalidate(self, ev: Evaluation) -> None
async def evaluate_to(self, ignore_error: bool) -> EvaluationResult:
    forest = self.forest()
    async with forest.lock:
        return await forest._run(self, ignore_error)
```

A stop is recorded only when `ignore_error` is unset, so inside
`_evaluate` `stopped_at is not None` implies `mode is None`.

`Leaf`:

```python
async def _evaluate(self, ev, mode):
    ran = mode.rewritten or not _wrote(self._status)
    if ran:
        status, duration = await _timed(self._eval_opr())
        if isinstance(status, CannotEvaluate):
            await self.state.copy_to(self.resulting_state())
        self._set_status(ev, status, duration)
    return self._reached(ev, ran)

def _invalidate(self, ev):
    self._set_status(ev, NOT_EVALUATED, None)
```

`NonLeaf_Node._evaluate_children(ev, mode: Evaluating)`: each child in
order under the mode the previous one answered; the first child
answering `mode` `None` ends the loop and its result is returned as it
is; otherwise `EvaluationResult(None, <the last mode>)`.

`StdBlock`:

```python
async def _evaluate(self, ev, mode):
    began = mode.rewritten or self.evaluation_status_beginning is NOT_EVALUATED
    if began:
        status, duration = await _timed(self._eval_beginning_opr())
        self._set_beginning(ev, status, duration)
    if isinstance(self.evaluation_status_beginning, CannotEvaluate):    # the children have no context
        for child in self.sub_nodes:
            child._invalidate(ev)
        if ev.destination is not None and ev.destination._is_under(self):
            return EvaluationResult(None if ev.ignore_error else self, None)
        copied = mode.rewritten or not isinstance(self.evaluation_status_ending, Ready)
        if copied:
            await self.state.copy_to(self.resulting_state())
            self._set_ending(ev, READY_CLEAN, None)
        return self._reached(ev, copied)
    r = await self._evaluate_children(ev, Evaluating(rewritten=began))
    if r.mode is None:                  # the destination or a stop lies under: nothing more runs
        return r
    ended = r.mode.rewritten or not _wrote(self.evaluation_status_ending)
    if ended:
        status, duration = await _timed(self._eval_ending_opr())
        if isinstance(status, CannotEvaluate):
            await self._state_before_ending.copy_to(self.resulting_state())
        self._set_ending(ev, status, duration)
    return self._reached(ev, ended)

def _invalidate(self, ev):              # beginning, each child whole, ending
    self._set_beginning(ev, NOT_EVALUATED, None)
    for child in self.sub_nodes:
        child._invalidate(ev)
    self._set_ending(ev, NOT_EVALUATED, None)
```

`Unchained_Node._invalidate(ev)`: each child's `_invalidate(ev)`.
`Session._evaluate` keeps its `TAT_InternalError`.

`Theory._set_ending` (plain): reads the stored ending before `super()`;
after it, when the stored ending was a `Ready` and the new value is not,
`importer._invalidate(ev)` for each of `forest._importers(self)`.

`Forest`:

```python
def _invalidate_from(self, position: Location, ev: Evaluation) -> None:
    parent, index = position.parent, position.index
    while isinstance(parent, StdBlock):         # a Session or the root: nothing, sibling trees are independent
        for child in parent.sub_nodes[index:]:
            child._invalidate(ev)
        parent._set_ending(ev, NOT_EVALUATED, None)
        index, parent = parent.index_of() + 1, parent.parent

async def _evaluate_tree(self, ev, tree) -> Node | None:
    """The run of one tree and its one `_invalidate_from` (MS §4.1)."""
    destination = ev.destination
    assert destination is not None              # an evaluating walk has one (`_run`)
    stop = (await tree._evaluate(ev, Evaluating())).stopped_at
    after = destination if stop is None or destination._is_under(stop) else stop
    if self._tree_of(after) is tree:
        assert after.parent is not None         # a node of a tree
        self._invalidate_from(Location(after.parent, after.index_of() + 1), ev)
    return stop

async def _handle_tree(self, ev, tree) -> Node | None:
    # order constraint: tree._invalidate(ev); stop, reason = tree, "order_constraint"
    # an import without both operations ready: tree._invalidate(ev);
    #     stop, reason = (None if ev.ignore_error else missing), "import_without_theory"
    # else: stop, reason = await self._evaluate_tree(ev, tree), "command_failed"
    # then, as today: the one `stopped` record (full ids; `tree` for import_without_theory)
    # then the tree's end: self._store_written(ev); await ev.flush(self.conversation)

async def _evaluate(self, ev, mode):            # the trees of the closure, in tree order
    ...                                         # first stop wins; returns EvaluationResult(stopped_at, None)

async def _run(self, destination: Node, ignore_error: bool, checks: str = "no") -> EvaluationResult:
    """The evaluating walk, under the lock; it makes the walk's `Evaluation` (MS §4.1)."""
    # ev = Evaluation(destination, ignore_error, checks)
    # walk_started(destination=full_id, ignore_error, checks)
    # try: r = await self._evaluate(ev, Evaluating())
    # except TAT_Error as e: raise TAT_InternalError("an evaluation hook raised a TAT_Error") from e   (A6)
    # self._store_written(ev); await ev.flush(self.conversation)      # the walk's end
    # walk_ended(outcome, slots_released=ev.releases, duration)
```

`after` in `_evaluate_tree`: the tree itself as `after` gives a position
whose parent is a `Session`, which marks nothing; a destination in
another tree, a `Session` or the root gives `_tree_of(after) is not
tree`, so nothing is marked — a tree run to its own `end`.

`_wrote`'s and `_predecessor_wrote`'s docstrings say "obstacle", not
"own stop"; `_predecessor_wrote`'s last sentence becomes: a failed
beginning writes nothing — at position 0 only `ready` counts.

Other callers: `mcp.py`'s `_evaluate` calls
`forest._run(destination, False)` and drops its imports of `Evaluating`
and `Evaluation`.

### A2. The setters

Specification: MS §4.1 "Status" and "States"; CO §4 "The setter";
LCR funnels-4.

```python
# Node
def _unchanged(self, index: int, new) -> bool:          # the guard: a repeated marking writes nothing
    return new is NOT_EVALUATED and self._last_evaluation_statuses[index] is NOT_EVALUATED
def _slots_written_by(self, operation) -> Sequence[Isar_State_Slot]:   # a class's override: the further
    return ()                                           # slots of its own that the operation writes
def _release(self, ev, index: int, slot) -> None:       # written -> unwritten: the operation's result,
    ev.release(slot)                                    # and what the class says the operation wrote
    for further in self._slots_written_by(self._operation_names()[index]):
        ev.release(further)
```

`Leaf._set_status(ev, new, duration)`, `StdBlock._set_beginning` and
`StdBlock._set_ending` are plain methods of one shape: `if
self._unchanged(i, new): return`; `old` = the instant status; the
release when written goes to unwritten — `_wrote(old) and not
_wrote(new)` for a leaf and an ending, `isinstance(old, Ready) and not
isinstance(new, Ready)` for a beginning, whose failed run wrote nothing
— through `self._release(ev, i, <the operation's resulting slot>)`; the
instant status assigned; then the one helper every setter ends on,
`self._written(ev, i, old, duration)`: it writes the stored entry from
the instant status, discards the seen set's key through
`forest.conversation.forget((self.identity, operation))`, adds the node
to `ev.stored`, writes the `operation` record, and last, both fields
written, calls `_completed(self.on_invalidated,
self._operation_names()[i])` when the instant status left `Ready` — a
completed hook fires after the write (MS §4.1, "Events"), and the jobs
session's `_on_context_change` goes beside it, in `_written`.

`Conversation.forget(self, key) -> None`: `self.seen.discard(key)`, a
method on the frozen dataclass; its constructor is not touched.

A slot a class owns besides `state` is the class's to mint and to
list (the owner's ruling of 2026-10-04, §7): it mints the slot where
the node is built, in `gen` and `from_store`, and appends it in its
`_states_inside`, so that a deleted subtree's and an amended-away
node's are released with the rest (A3); the framework's part is
`_slots_written_by` alone.

### A3. The edit's commit

Specification: MS §4.2 steps 3 and 4 and the `move` paragraph; MS §4.1
"Events"; CO §4 "When the store is written"; LCR elegance-8.

Every entry has this order, with nothing awaited between the pointer
surgery and the store:

1. the round trips before the block: `insert`'s one copy, `delete`'s
   `_carry_forward`, `move`'s two;
2. the pointer surgery;
3. `forest._invalidate_from(position, ev)` — `insert` and `delete`:
   `Location(parent, index)`; `amend`: `Location(replacement, 0)` when
   the replacement inherited children, the children coming before its
   own ending in the walk (AR §3.5), else `Location(parent, index)`;
   `move`: at the source successor's position as it is after the
   surgery (the parent's ending when the node was last), then at the
   new position;
4. `invalidated, vanished = forest._invalidate_changed_trees(ev, before)`,
   now plain: each changed tree `_invalidate(ev)`; returns the changed
   trees and the sorted vanished qualified names;
5. the completed hooks, in MS §4.1's order, each fired through a local
   helper that calls `_completed(hook, *args)` and remembers
   `hook.__self__` — every hook an entry fires is a bound method of a
   node;
6. `_store_transaction(...)`, below;
7. the round trips after the block: `theory_delete(vanished)` when there
   are any, then `ev.flush(conversation)`.

`_store_transaction(forest, ev, operation, location, *, changed,
deleted=(), created=(), removed=(), moved=(), invalidated=())`, in
`edit.py`: one call of `forest._store_written(ev, [*created, *changed],
deleted)`, then the `committed` record (today's `_committed`, folded
in; `removed`'s ids taken before the nodes detach, every id
`Forest.full_id`'s). It is a function, not a context manager: what each
entry stores is data — the new nodes, the nodes a completed hook fired
on, the parents whose `children` row changed, the deleted subtree — so
the block has no body.

`created` per entry: every node of each new subtree, in tree order —
the new rows, stored whether or not a hook fired on them. `changed`:
the remembered hook receivers; plus `delete`'s parent and `move`'s old
parent, on which no completed hook fires. `deleted`: `delete`'s subtree
in tree order; nothing for an amend.

On `Forest`:

```python
def _in_forest(self, node) -> bool                       # its parent chain reaches this root
def _store_node(self, node) -> None:
    # the root: its `children` row alone; a node not `_in_forest`: TAT_InternalError;
    # otherwise as today (delete_node, kind, children, last_evaluation_statuses, to_store)
def _store_written(self, ev, changed=(), deleted=()) -> None:
    # nodes = ev.stored, then those of `changed` that are `_in_forest`, each once;
    # a node of ev.stored not `_in_forest`: TAT_InternalError, before any transaction opens;
    # nothing to write and nothing to delete: no transaction;
    # else one transaction: delete_node for each of `deleted`, then _store_node for each node;
    # ev.stored.clear()
```

The refusal is raised before the transaction opens, so it reaches the
conversation as the `TAT_InternalError` MS §4.2 names; raised inside
one — `_store_node` called on its own — it is the cause of the
`TAT_DisasterError` every failed transaction raises.

`_store_written_rows`, `_store_subtree` and the entries' own
`with forest.store.transaction():` blocks go; `_store_children` stays
for `_store_node` and for `test_model.add`.

`NonLeaf_Node._carry_forward(index, node)` loses `ev` and its release
branch (`Unchained_Node`'s and `OneTreeForest`'s overrides follow);
`move` keeps `else: ev.release(node.state)`.

### A4. The store and the loader

- `store.py` holds both constants: `CONSTRUCT_FRAMEWORK_FIELDS`, the
  two framework fields of a construct (`kind`, `children`), and
  `FRAMEWORK_FIELDS`, the reserved rows, built from it plus
  `last_evaluation_statuses`. `plugin.py`'s `_check_class` (twice) and
  `check_construct` use the first in place of `FRAMEWORK_FIELDS`; and
  `_check_class` refuses a class whose construct declares a field named
  after another reserved row — such a class would otherwise load and
  then fail at its first store (CR §10, code-1's loader check;
  PLUGIN_SYSTEM §5's bullet). Tests: `test_plugin.py`, the refusal with
  its reason; `test_edit.py`, a construct carrying
  `last_evaluation_statuses` refused with `UnexpectedField`;
  `test_store.py`, `Node_Rows` refusing every reserved row.
- The malformed-row refusal and the missing-row rule are in.
  `import_sessions` moved to B1: it needs the ML answer of
  `TAT.Theory.begin`.

### A5. `IsaTerm` in `Isabelle_RPC_Host.unicode`

Decided by the owner on 2026-10-04 ("移动到 Isabelle_RPC 以作为一个统一
的基础设施"): one class for AoA and TAT, in
`contrib/Isabelle_RPC/Isabelle_RPC_Host/unicode.py` (an editable
install, so both see it at once) and exported from
`Isabelle_RPC_Host/__init__.py`. The class is AoA's, moved unchanged —
the approval of 2026-09-30 (DOC_SYNC_LIST, "Outside this repository");
it refuses `str()` and compares by `ascii` as TAT's does, and adds
`to_unicode`, `to_ascii`, `__len__`, `__lt__` and equality with a
`str`. `contrib/Isa-Mini/IsaMini/AoA/model.py` imports it and drops its
definition, its type aliases staying where they are;
`isabelle_driver.py` loses its copy; `model.py`, `log.py` (one import
line; the logging session agreed) and the tests import it from
`Isabelle_RPC_Host.unicode`. Tests: TAT's suite; AoA's module imports
(`python -c "import IsaMini.AoA.model"`), since AoA's own suite calls
a language model. The two other repositories are committed on the
owner's word like this one.

### A6. `Forest._run`

In A1's listing: a `TAT_Error` escaping `_evaluate` can only come from
an evaluation hook — completed hooks raise `TAT_InternalError` through
`_completed`, the wire `TAT_IsabelleError` or a connection error, the
store `TAT_DisasterError` — and is raised as `TAT_InternalError` from
it, so that no hook's `TAT_Error` is ever rendered to the agent. Other
exceptions pass as they are, and the tool boundary ends the
conversation on each, as it does on anything that is not a
`TAT_Error`: a class's bug of another kind; and what is no bug — a
connection error, the conversation's ending (EXCEPTIONS §1), and the
`TAT_StartupError` of `Theory`'s beginning for a folder that cannot be
made (B5).

EXCEPTIONS §1's last bullet and CO §4 (twice) say so since 2026-10-04,
when the owner approved it (§5, point 4).

### A7. Tests

Helpers.

- `test_model.py`: `invalidate(node)` (and its coroutine
  `_invalidate(node)` for async cases) — the lock, an
  `Evaluation(None, False)`, `node._invalidate(ev)` when the node's
  parent is an `Unchained_Node` or absent, else
  `forest._invalidate_from(Location(node.parent, node.index_of()), ev)`,
  then `forest._store_written(ev)` and `ev.flush`; it returns nothing.
  The six `evaluate=False` callers use it: `test_model.py:326`,
  `test_session_theory.py:265`, `test_forest_walk.py:622`,
  `test_edit.py:745` and `:969`; `:893` is the deleted case below. The
  two that assert on the call's result (`test_model.py:327`,
  `test_forest_walk.py:623`) lose that assertion.
- `OneTreeForest._evaluate`: the destination's tree — every child when
  the destination is the root, ending at the first stop — through
  `self._evaluate_tree(ev, tree)`; returns `EvaluationResult(stop,
  None)`. Its `_carry_forward` alias follows A3. Being an
  `Unchained_Node`, the double's root marks nothing at its own level,
  as the real root: an edit among its top-level blocks invalidates no
  later block, though the double chains them. No case evaluates two
  top-level blocks; the docstring says so.
- `test_print.py`'s `rerun`: `x._set_ending(...)` without `await`.
- `test/invariants.py`: the `CannotEvaluate` clause requires the
  obstacle's input slot held and equal to what it copied, for a node
  under a chaining parent (`invariants._chained`) that is not the first
  child of a parent with no beginning; the comments say "obstacle". A new
  clause, AR §3.4's last paragraph: in the walk's order within a tree,
  no operation is written after an unwritten one, except that under a
  nesting node whose beginning is `cannot_evaluate` the children are
  unwritten while its ending and what follows may be written.
  `assert_store_mirrors` compares each node's stored statuses in their
  stored form (`M._status_to_store`) itself, whatever `shape` holds.

Deleted: `test_own_stop_survives_being_blocked`,
`test_removing_an_own_stop_behind_a_blocked_predecessor_releases_its_copy`,
`test_the_root_has_no_position`.

Changed expectations.

- `EvaluationResult(None, INVALIDATING)` becomes
  `EvaluationResult(None, None)` wherever it stands (`test_model.py`,
  `test_forest_walk.py`, `test_session_theory.py`,
  `test_conversation.py`); the imports of `INVALIDATING` go.
- `test_model.py::test_c_failed_opening`: `t2.evaluate_to(False)` and
  the later `t1.evaluate_to(False)` answer `stopped_at is sec`; after
  the second, `T3`, `T4` and the section's ending are `not_evaluated`.
  Added to it: `t1.evaluate_to(True)` answers
  `EvaluationResult(None, None)` with `T1` `not_evaluated`.
- `test_model.py::test_insert_into_evaluated_tree`: `f._run(M.Evaluation(nodes[-1], False))`.
- `test_edit.py::test_failed_opening_after_failed_ending_keeps_its_result`:
  after the strict walk `st(b) == (NOT_EVALUATED, NOT_EVALUATED)`.
- `test_edit.py::test_own_stop_reruns_when_its_input_is_rewritten`:
  after the strict walk `st(x) is NOT_EVALUATED`; renamed to say what
  it now shows — an obstacle after a strict stop runs again when a walk
  reaches it.
- `test_edit.py::test_each_edit_is_one_transaction_touching_what_it_changed`:
  the touched sets are the hook receivers and the parents — a move
  within one parent the parent and the moved node, across parents both
  parents and the moved node, the amend the replacement, its parent and
  every inherited child; the insert's and the delete's stay.
- `test_edit.py::test_amending_a_childless_block_counts_each_deleted_slot_once`
  (the logging session's, told first): an edit writes no `walk_ended`;
  the case asserts the one `state_delete`'s three distinct names and
  that the amend wrote no `walk_started`.
- `test_forest_walk.py::test_blocked_by_a_failed_header` (the logging
  session's, told first): `walk_started`'s data gains `"checks": "no"`.
- `test_session_theory.py::test_a_walk_never_reaches_a_session`: the
  call passes `M.Evaluating()`.
- Comments and names that say "own stop" say "obstacle" or "stop" as
  AR §3.3 defines them; the two deleted identifiers aside.

New cases.

1. `test_forest_walk.py`: a `move` across trees — `A > [x, y]`, `B`
   importing `A`, `C > [z]`, all evaluated; `x` moved to `C`'s front:
   `y` and `A`'s ending `not_evaluated`, `B` whole through the importer
   rule, `x`, `z` and `C`'s ending `not_evaluated`; one transaction;
   the store mirrors.
2. `test_forest_walk.py`: a nesting node under a real `Theory` (the
   kind table gains `tm.Block`): `T > [S (beginning fails) > [a, b], d]`,
   `W` importing `T`. `W.evaluate_to(True)` leaves `S` `(cannot_evaluate,
   ready)`, `d` and `T` `ready`, `W` evaluated; then
   `a.evaluate_to(False)` answers `stopped_at is S`, writes one
   `stopped` record naming `S` with `command_failed`, leaves `b`, `S`'s
   ending, `d` and `T`'s ending `not_evaluated` and `W` whole; then
   `T.evaluate_to(False)` answers no stop, writes `S`'s ending by the
   copy and runs `d` and `T`'s `end` again; `a.evaluate_to(True)`
   answers no stop and leaves the statuses the strict call left.
3. `test_edit.py`: a second invalidation from the same position stores
   and logs nothing — no transaction, no `operation` record, no
   `state_delete`.
4. `test_edit.py`: hooks that record a field. Classes whose
   `on_inherited`, `on_added_child`, `on_moved` and `on_deleted` set a
   stored field: after an amend the inherited children's and the
   parent's fields are in the store and the amended-away node's are
   not; after a delete no row of the subtree remains and nothing is
   refused; after a move the moved node's field is stored.
5. `test_edit.py`: a node outside the forest among the nodes to store
   is refused with `TAT_InternalError` and no transaction opens;
   `_store_node` called on it inside a transaction raises
   `TAT_DisasterError` with that cause.
6. `test_model.py`: a slot of the class's own. A leaf class minting
   one, its hook writing it: fresh on construction and on load, never
   equal to another slot's name; released with the result when the
   status goes to `not_evaluated`, not on a rerun; among the deleted
   names of a delete and of an amend. And a nesting class whose
   beginning writes one: a walk to a node inside the block invalidates
   the ending alone and releases nothing of it, the ending run again
   reads what the beginning wrote, and invalidating the block whole
   releases it.
7. `test_model.py`: an evaluation hook raising a `TAT_Error` ends the
   walk with `TAT_InternalError`, the cause chained.
8. `test_print.py` or `test_model.py`: `Conversation.forget` removes
   the key a status write names.
9. `test_model.py`: how `slots_released` is counted — one slot released
   twice on one `Evaluation` and flushed is one name in the one
   `state_delete` and `releases == 1`; and on a walk, a nesting node
   with a slot of its own invalidated whole: `walk_ended`'s
   `slots_released` equals the number of names of the tree's
   `state_delete`.

Then `pyright isabelle_theory_agent`, the suite without Isabelle, and
the 23 Isabelle-backed cases through the harness.

### A8. Review and commit

The documents' status lines are corrected (CO's opening; CR §14; the
compilation bullet of STEP5_HANDOFF.md). An adversarial code review
against the documents — challengers, merge, one fresh defender per
merged finding, a judge; Opus 5.5, xhigh, in English; the findings
reported in Chinese in three classes. Then the owner's "批准提交". The
logging session and the jobs session are told when A1–A3 are in the
tree and again when the commit is made.

## 4. Phase B: compilation

Specification: CO §1–§3, §5, §7; ST §1–§3; MS §2.3, §2.6, §3 (the
`Theory` row), §4.4, §4.6, §5; PLUGIN_SYSTEM §1, §5; EXCEPTIONS §1, §3;
RENDER_BASELINES §2.

**Where it stands (2026-10-04, Phase A committed as `dfefca1`).** The
jobs session's steps 1 to 3 did not start — the owner has not yet let
them — so the order changed: Phase B takes the ML and Scala files
first, and that session's steps 1 and 3 build on what B1, B2 and B7
leave; it has released ML/TAT_Framework.ML, ML/TAT_Common_Nodes.ML,
ML/TAT_Boot.ML, src/scala/tat.scala, lib/tat.jar, etc/build.props,
exceptions.py, isabelle_driver.py, toplevel.py, test/harness.py and
test/Test_TAT_Framework.thy to this session, which tells it when they
are free again. The logging session's steps 10 and 11 wait for the end
of Phase B.

In the tree, uncommitted, with their tests (fast suite 353 passed, the
same 18 known failures; pyright clean):

- B3 whole: `Node.can_emit`, `Node.emit`, `StdBlock.emit` (`final`)
  with `emit_beginning`/`emit_ending`, `Theory`'s two through
  `header()`, `Unchained_Node.emit` refusing; the loader's rules
  (`_check_coroutines` compares every override with the method it
  overrides); every test node class has its `emit`.
- B4 whole: `compile.py` — `render(forest) -> Rendering` (the first
  step), `compile(forest, hooks)`, `paths`, `Entry`, `Compile_Report`
  (its `removed` holds `Entry`s, so that a folder's line ends in `/`),
  `report_lines`; `Forest._misplaced_imports`, the position test the
  walk and the compile share; `test/test_compile.py`, CO §2's report
  and ROOT read from the document.
- B6 whole: `TAT_compile_hook`, `compile_hooks`, `Loaded.compile_hooks`.
- B5 but for its harness cases: `isabelle_theory_agent/invariants.py`
  (`assert_store_mirrors(forest, kinds)`, called by
  `test/invariants.py` after every edit and walk of the suites);
  `session_folder_refusal` and `make_session_folder` in `model.py`,
  which `compile.py` and `Theory._eval_beginning_opr` share;
  `model.CannotUseWorkingDirectory`; `mcp_server.stopped`'s seventh
  reason (both sessions told).
- B1 whole: `Theory.import_sessions` (stored; a missing row reads
  empty) and `Theory.file_path()`; in `ML/TAT_Common_Nodes.ML`,
  `TAT.Theory.begin` answers the pair of the header's messages and the
  session of each import (`import_sessions`, computed in the class's
  own ML: the framework's `begin_theory` keeps its type, as MS §2.5
  lists it), which `_eval_beginning_opr` records when the header
  passed. Through the harness: `Main` records `["HOL"]`, a tree of the
  forest its `Session`, kept across a restart.
- B5's harness case: the folder made at a theory's first run, and a
  file at its path raising `CannotUseWorkingDirectory` before anything
  runs (`test_conversation.py`). That the exception ends a conversation
  is the tool boundary's rule for anything that is no `TAT_Error`,
  which `test_mcp_server.py` covers; no case drives it through the
  harness, where it would end the run the cases share.
- Of B2: the namespace compared without regard to case
  (`edit._take_name`).

- B2 whole, as the shapes below: the jar rebuilt with
  `TAT.reserved_name` (`etc/build.props` names `TAT_Functions` under
  `services`, `no_build` restored); `test_the_field_checks` passes with
  ST §3's seven lines, so the known failures are 17. The options were
  first checked in ML (`Options.update`), whose message is `Unknown
  system option "documnet"` where the documents' example shows
  Isabelle/Scala's `Unknown option "documnet"`; §8's F2 moved the check
  to the Scala side, whose message it is.
- `test/stand_ins.py`: `conversation()` no longer takes the repository
  as its working directory — a `Theory`'s beginning makes a folder
  there — but `<the case's temporary directory>/work` (the logging
  session's file; told).

- B7 whole. Python: `toplevel.compile_TAT` on `conversation()`; the
  lock's refusal in CO §7's wording. ML: `collect` (MS §2.6's step 2),
  `compile`, and one handler, `define_entry`, behind `TAT.start` and
  `TAT.compile` — each command reads its arguments into the plugins'
  theory names and a function of the loaded theories answering the code
  and the lines, every exception `2`; `TAT.boot` runs the command its
  first argument names and answers a failure before the hand-off with
  `2`. Scala: `TAT.launch`, steps 1 to 5 up to what `TAT.finished`
  carried, which `TAT_mcp` and the new `TAT_compile` share; `Getopts`
  in its `internal` mode, `Build.build_logic` strict, the process's
  termination `2`; `TAT_compile`'s final reading through
  `Sessions.load_structure(select_dirs = <the working directory>)`,
  the empty selection — which selects exactly the sessions of a
  selected directory — and `Sessions.deps(...).check_errors`; the jar
  rebuilt. `test/Test_TAT_Framework.thy` needed no change: `start'`
  keeps its type. Two things for the owner: the usage text and the
  one-line description of `isabelle TAT_compile` are the author's
  drafts; and the lines `TAT.finished` carried on `2` are printed
  through the progress as errors, as CO §5 says, which Isabelle's
  `Console_Progress` writes to the standard output — an error the tool
  itself raises (a usage error, Isabelle refusing what was written)
  goes to the standard error.
- Tests of B7: `test_toplevel.py` — a compile on a directory a
  conversation left (the report, the files, the one round trip, the
  database untouched, no `ending`), a forest written whole, what
  escapes a compile entering its ending, a compile refused by the lock;
  `test_launcher.py` — the refusals before the process exiting `2` in
  both tools, and three Isabelle-backed cases on directories the run's
  conversations left, the tool's process calling `compile_TAT` on the
  run's RPC host: exit `0` with the `Log:` line and the files, then
  `2` under a layout declaring the session again; exit `1`; exit `2`
  while a conversation holds the directory. `harness.release_run`
  expects `2`.

- B8: the status lines (CO's opening, STEP5_HANDOFF's compilation
  bullet); the code review and its fixes, §8.

The Isabelle-backed cases: 27 pass. Without Isabelle: 368 pass, 17
known failures (`ai-artifacts/review_phase_b/known_failures.txt`).
`pyright isabelle_theory_agent` is clean.

Ruled on 2026-10-05: the lines `TAT.finished` carries on `2` stay on
the standard output, as Isabelle's `Console_Progress` prints an error;
the delta after Phase A's review needs no further review; the version
floor of `isabelle-rpc` in Isa-Mini is the release agent's. Still to
do: the usage text of `isabelle TAT_compile`; his "批准提交".

The shapes B2 was written to:

- Scala: `object Reserved_Name extends Scala.Fun_String("TAT.reserved_name")`
  answering the words, separated by a space, of the predicates that
  hold of the name — `file` (`Path.is_reserved`), `theory`
  (`Sessions.illegal_theory`), `session` (`Sessions.illegal_session`);
  `class TAT_Functions extends Scala.Functions(TAT.Reserved_Name)`,
  named under `services` in `etc/build.props`.
- ML `Loader`: `reserved_as name` reads that answer through
  `Scala.function1`; `check_new_theory_short_name` answers `Reserved`
  also on `file` or `theory`; `check_session {name, parent, options}`
  answers the first of: the name reserved (`file` or `session`), the
  name known (`is_known_session`), option `i` refused (the Scala
  function `TAT.check_options`, applying each in turn as Isabelle reads
  a ROOT, Isabelle's message kept), the parent unknown — `parent` an option, `NONE` when
  the Python side settled it. The wire callback `TAT.check_session`
  replaces `TAT.is_known_session`; its answer is a tagged list of
  strings in `check_new_theory_short_name`'s shape, the option's index
  as digits.
- Python: `isabelle_driver.check_session` decoding the answer into
  one of five dataclasses; `Session.gen` in this order — the
  grammar, `ROOT` in any spelling (`ReservedSessionName`, no round
  trip), the non-empty and no-option-twice checks, then the one round
  trip (the parent passed as not to be asked when a `Session` of the
  call bears it or it is the session's own name), then "must not name
  the session itself" — which differs from ST §1's in one place, a
  name Isabelle reserves being judged in the round trip, after the
  checks that cost none, where ST §1 lists it beside `ROOT` (§8, F11,
  the owner's); `exceptions.ReservedSessionName` beside
  `ReservedTheoryName`. The fakes of `test_session_theory.py` and the
  probes of `test_conversation.py` follow.

### B1. `import_sessions` and `file_path()`

Needs: the two ML files free.
Build. ML: `begin_theory` answers, beside the state, the session of
each import — `Resources.theory_qualifier` of the resolved long name —
and `TAT.Theory.begin` returns the messages and that list (MS §3). Python:
`Theory.import_sessions`, recorded by `_eval_beginning_opr` when the
header passes, stored, a missing row read as the empty list (CO §4,
"Storage"); `Theory.file_path()`, which `_eval_beginning_opr`'s
`master_dir` uses (CO §2; ST §2).
Files: `ML/TAT_Framework.ML`, `ML/TAT_Common_Nodes.ML`, `model.py`,
the fakes of `test_session_theory.py`.
Tests: `test_conversation.py` — a theory importing `Main`, `HOL.List`
and `HOL-Library.Phantom_Type` (a small theory of another session, in
`HOL-Library.Multiset`'s place: it loads in a moment) records `["HOL",
"HOL", "HOL-Library"]` as Isabelle answers them, and one importing
`Main` and that theory keeps `["HOL", "HOL-Library"]` across a restart;
`test_model.py` — a database without the row.

### B2. The names Isabelle refuses, caught at creation

Needs: the ML and Scala files free; a jar rebuild.
Build (CO §2, "Names Isabelle refuses" and "What else creation
checks"; ST §1–§3; MS §2.3, §2.6 step 3, §5): the Scala function
`TAT.reserved_name`, a `Scala.Functions` service in `etc/build.props`;
`Loader.check_new_theory_short_name` asking it; `Loader.check_session`
and the wire callback `TAT.check_session` in place of
`TAT.is_known_session`; `isabelle_driver.check_session`; `Session.gen`
— `ROOT` in any spelling, `ReservedSessionName`, the name the layout
knows, the options, the parent last; the theory namespace compared
without regard to case.
Files: `src/scala/tat.scala`, `lib/tat.jar`, `etc/build.props`,
`ML/TAT_Framework.ML`, `model.py`, `edit.py` (`_take_name`),
`isabelle_driver.py`, `exceptions.py`, the tests' fakes.
Tests: `test_session_theory::test_the_field_checks` passes with ST §3's
seven lines; `test_exceptions` gains `ReservedSessionName`'s two lines;
`test_conversation.py` asks the real Isabelle a reserved name, an
unknown option and a name the layout knows.

### B3. The emission contract

Build (CO §3; PLUGIN_SYSTEM §5): `Node.can_emit`, `Node.emit`;
`StdBlock.emit` with `emit_beginning` and `emit_ending`; `Theory`'s
two, the header and `end` — `emit_beginning` writes the header by
calling `Theory.header()`, the one function `_eval_beginning_opr`
sends, so that the run and the emitted file cannot differ (the jobs
session's step 14 adds a plugin's declared imports in that function);
the `text ‹…›` block for a `description`
comes with the field, in CIP step 13; the loader's three rules and
`typing.final` on the methods no class overrides. Every test node class
gains its `emit`.
Files: `model.py`, `plugin.py`, the tests' classes.
Tests: `test_plugin.py` — each rule refused with its reason;
`test_session_theory.py` — a tree's text.

### B4. `compile.py`

Build (CO §2, §5, §7): `paths(working_directory)`; the function that
makes a `Session`'s folder, with §7's two refusals; `compile(forest,
hooks) -> Compile_Report`, its first step one function of the stored
forest — which trees, the four reasons, each file's text converted
once with `ascii_of_unicode`, the ROOT's text — and its disk step in
CO §5's order; `report_lines`. `Forest._order_violation`'s position
test becomes the one helper the compile shares.
Files: new `compile.py`, `model.py`.
Tests: new `test/test_compile.py`, no Isabelle, on fake classes: CO
§2's example report line by line from the document; each reason; an
import cycle; a tree imported by an unwritten one; the ROOT's clauses
and quoting; the directory rules — a dot folder and a symbolic link
untouched, a `.thy` elsewhere removed, the two refusals leaving the
directory as it was; `removed`; a file created with `O_EXCL`.

### B5. The store-mirror helper in the package; the folder at a theory's beginning

Build (CO §3, last paragraph; MS §4.1's `Theory` bullet): the helper
that reloads the forest and compares the stored statuses, `can_emit`
and the first step's text and report — *(author)* in a module
`isabelle_theory_agent/invariants.py`, called by
`test/invariants.py`; the jobs session adds the stored check's
comparison when `check_outcome()` exists. `Theory._eval_beginning_opr`
makes its `Session`'s folder through B4's function before the header
runs; a folder that cannot be made raises `TAT_StartupError` with §5
point 2's sentence, ending the conversation. B4's function answers the
reason alone, and each caller — the compile, the theory's beginning —
puts its own opening before it.
Files: new `invariants.py`, `model.py`, `test/invariants.py`.
Tests: a class whose `emit` reads an instant status is caught by the
helper; a theory's first evaluation makes the folder; a file and a
symbolic link at the folder's path each end the conversation with
their sentence, the forest and the database as they were
(`test_conversation.py`, through the harness, and
`test_session_theory.py` without Isabelle, which also drives a folder
the system will not make).

### B6. Compile hooks

Build (CO §5, "Compile hooks"; PLUGIN_SYSTEM §1, §5):
`TAT_compile_hook`, the registry `compile_hooks`, the sweep in `load`,
`Loaded` carrying the hooks, the loader's check of a hook.
Files: `plugin.py`.
Tests: `test_plugin.py` — registration by import, the order, the
sweep, a coroutine refused; `test_compile.py` — a hook runs after the
files and before the empty folders' removal and the ROOT.

### B7. The three entries

Needs: the ML and Scala files free; a jar rebuild.
Build (CO §5; MS §2.6, §4.6, §5): `toplevel.compile_TAT`, on
`conversation()`; the lock's refusal in CO §7's wording;
`TAT.compile`, sharing `TAT.start`'s handler as one ML function, its
command carrying `TAT.log_directory` alone, step 2's collection one
function both call; the boot running the command its first argument
names; `isabelle TAT_compile`; every end that is not a normal return
exiting `2` in `TAT_mcp` and `TAT_compile` (`Getopts` internal,
`Build.build_logic` strict); the final reading through
`Sessions.deps(...).check_errors`.
Files: `toplevel.py`, `ML/TAT_Framework.ML`, `ML/TAT_Boot.ML`,
`src/scala/tat.scala`, `lib/tat.jar`, `test/Test_TAT_Framework.thy`,
`test/harness.py` (the boot's first argument).
Tests: `test_toplevel.py` — `compile_TAT` on a stored forest returns
the report and writes the files, a second holder refused with CO §7's
sentence; `test_launcher.py` — `isabelle TAT_compile` on a directory a
conversation left: exit `0`, `1` and `2`, the `Log:` line, a ROOT
Isabelle refuses reported with exit `2`.

### B8. Review and commit

As A8. The documents' status lines; CR gains the record.

## 5. For the owner

1. **Which `IsaTerm` is shared** (A5): decided on 2026-10-04, one
   class in Isabelle_RPC for AoA and TAT; A5 reads it as AoA's class
   moved unchanged, the approval of 2026-09-30.
2. **A `Session` folder that cannot be made when a theory begins**
   (B5): decided on 2026-10-04 — the conversation ends. The working
   directory is TAT's alone, a structure changed from outside is reason
   enough to refuse service, and an agent shown the failure could not
   repair it ("这种情况足以拒绝为用户服务"). The beginning raises
   `TAT_StartupError`, which is no `TAT_Error`: it passes `Forest._run`
   as it is, the tool boundary enters the ending with it, and the
   launcher prints its sentence and exits `2`. The three sentences,
   approved the same day, are CO §7's item 6.
3. **The order between Phase B and CIP steps 4 to 17**: left to this
   session by the owner on 2026-10-04 ("这个与设计无关。你可以自主决定").
   Decided: Phase A, then Phase B, then CIP steps 4 to 17; CIP steps 1
   to 3 run beside Phase A, which shares no file with them, and are in
   before B1. The compilation system is then whole before the jobs code
   reshapes `model.py`, and Phase B's few edits there are not rebased
   over ten steps of another session's.
4. **What `Forest._run` converts** (A6): decided on 2026-10-04 ("同意
   Forest._run 只转换 TAT_Error"), in place of the ruling of 2026-10-02
   that had everything escaping an evaluation hook raised as
   `TAT_InternalError`. `_run` converts a `TAT_Error` alone, the one
   kind that would otherwise be shown to the agent as its own mistake;
   anything else ends the conversation as what it is, so that the
   ending can tell which reason ended it. Written into EXCEPTIONS §1
   and CO §4.
6. **What an agent's call in flight is answered when the folder ends
   the conversation** (B5). The server answers every call it cancels
   with one line of RENDER_BASELINES §4, chosen by what ended the
   conversation (`mcp_server.stopped`); a `TAT_StartupError` raised in
   a call falls to "an internal error" today, which this is not.
   Approved by the owner on 2026-10-04 ("好的批准"): the answer's new
   form, for every reason, and a seventh reason —

   ```
   TAT has stopped: <reason>; this is a critical error, and this call did not complete. Stop now and call TAT no more. If another agent started you, tell it to stop as well; otherwise tell the user that TAT has stopped.
   ```

   with `<reason>` one of `an internal error`, `the sessions could not
   be saved`, `Isabelle is gone`, `Claude Code saves no transcript`,
   `Codex's sandbox is not the one TAT configured`, `a client TAT does
   not serve connected`, and the new `it cannot use its working
   directory` — chosen for a subclass of `TAT_StartupError` the
   folder's refusal raises, *(author)* `CannotUseWorkingDirectory`.
   RENDER_BASELINES §4 holds the seven lines; `test_mcp_server.py`
   unpacks exactly the lines of that section and `stopped` is in
   `mcp_server.py`, both the logging session's, so the document, the
   function and the unpack change in one step, agreed with that
   session; B5 adds the seventh reason's branch, the logging and jobs
   sessions told first (the jobs session adds `ClientRefused`'s branch
   there in its step 2). The owner also ruled the same day that the
   connection to Isabelle going is a critical crash, its `ending`
   record written at level `error` (LOGGING §4; the logging session
   confirms it with him and writes it).
5. **`Evaluating.rewritten`.** Under the sixth review's rulings every
   invalidation runs forward to the tree's end, so no written operation
   stands after an unwritten one, a failed beginning's children aside
   (the invariant A7 adds). `rewritten` then never makes a written
   operation run again: it is set only after an operation that was
   unwritten, and what follows such an operation is unwritten too. A
   reader of this plan tried ten routes to a counterexample — edits,
   either flag, a restart, the importer rule — and found each closed.
   The plan keeps `rewritten` as MS §4.1 lists it; removing it is a
   simplification to decide after A7's invariant has run over the
   suite.

## 6. How this plan was checked

Two readers on 2026-10-04, one against the design documents and one
against the code and the tests, each tracing the code shapes of §3 by
hand: the walk's four cases at a failed beginning, the position handed
to `_invalidate_from`, the edit's order and store set, and every
evaluating, invalidating or editing case of `test_model.py`,
`test_edit.py`, `test_forest_walk.py` and `test_session_theory.py`,
`test_random_interleavings_keep_the_invariants` under A7's two new
invariant clauses included. Their findings are in the text above: the
setter firing its hook after both fields are written; the refusal of a
node outside the forest raised before the transaction; the new nodes
stored whether or not a hook fired; the amend's position; the two
narrowing assertions for the type checker; the helper returning
nothing; the loader's refusal of a reserved row's name; `Theory`'s
`description` block left to CIP step 13; Phase B's rule on shared
files. One point is the owner's to confirm, §5 point 4.

## 7. The code review of Phase A

On 2026-10-04, by the owner's recipe: four challengers (the walk; the
setters, the store and the edit's commit; the tests; elegance, reuse
and the move of `IsaTerm`), a merge into 28 findings, one fresh
defender per finding, a judge; each claim about a test checked with a
wrong implementation swapped in in memory. Verdict READY_WITH_FIXES;
the result is `ai-artifacts/review_phase_a/review_result.json`.

- Confirmed and fixed, 23. In the code: one helper every setter ends on
  (`Node._written`, review 5's code-5); `Forest._run` making the walk's
  `Evaluation` (MS §4.1); one tail for a node the walk reaches
  (`Node._reached`); `Forest._in_forest` and `edit.move` on
  `Node._is_under`; both constants of the framework's fields in
  `store.py`; the beginning's rerun test asking the status itself;
  six docstrings and comments that had become false. In the documents:
  PLUGIN_SYSTEM §5's bullet for the loader's refusal (review 5's
  code-1). Tests added: after a restart, an import losing its theory
  value invalidates the stored importer, by a walk and by an edit; a
  beginning that fails after a restart invalidates what its children
  stored; an amend of a `Theory` with evaluated children; the store at
  each tree's end; a loaded node releases nothing and fires no
  `on_invalidated`; `on_invalidated` before the other completed hooks,
  and after both fields are written; a construct carrying
  `last_evaluation_statuses` refused; `Evaluation.passed`.
- Rejected, 4 (F4, F18, F22 and one of F28's three points).
- For the owner, 1 (F1): on a nesting class, which setter releases a
  slot the class owns — under `owned_slots`, a class attribute the
  framework minted, released in every setter and deleted, a walk or an
  edit inside a block released a slot its still-`ready` beginning had
  written. Ruled on 2026-10-04: the owner asked whether the framework
  must do this at all ("我们不能让 adhoc deriving node 自己去做吗？必须
  做进框架里吗？") and approved the answer ("赞同甲") — a class mints a
  slot of its own in `gen` and `from_store` and appends it in
  `_states_inside()`, as `Theory` does with its resulting slot; the
  framework keeps the one thing a class cannot do, the release on
  invalidation, through `Node._slots_written_by(operation)`, in which
  the class names the further slots that operation writes.
  `owned_slots` and the framework's minting are gone; MS §4.1 "States"
  and "Status", AR §3.1, PLUGIN_SYSTEM §2 and THEOREM.md §1 say so. F12
  is the nesting class's case of A7's sixth test.

## 8. The code review of Phase B

On 2026-10-04, by the owner's recipe: five challengers (emission and
compile's first step; the disk step, the folder, the hooks and the
Python entry; the creation checks and the Isabelle side; the tests;
elegance, reuse and false sentences), a merge of their 61 findings into
52, one fresh defender per finding, a judge. Verdict READY_WITH_FIXES,
no blocker; the result is
`ai-artifacts/review_phase_b/review_result.json`.

- Confirmed and fixed, 40.
  - Behaviour, 6. An option's value is read in one place,
    `model._option_value` — what the agent supplied less the quotes it
    may have come in — for creation's check and for the ROOT alike: the
    check had been sent the value with its quotes, which Isabelle
    refuses for a `bool`, `int` or `real` option (F1). A removed path
    that is not valid UTF-8 is spelled in the report with the escape
    the log writes, so that the answer can travel (F5). The folders a
    compile keeps are known by what the file system says they are, not
    by their names' spelling (F8). An interrupt during `TAT_compile`'s
    final reading exits `2` (F10). The Isabelle-backed cases'
    `isabelle TAT_compile` runs in a process group of its own, ended as
    the child's is at a case's deadline (`Harness.run_tool`), and
    `leave` ends its conversation on every path (F14, F33).
  - Shape, 7. `compile._placed`, the one rule placing a refusing node
    at an operation (F16); `Session.folder()`, from which a tree's file
    path, the folder made, the folders kept and the ROOT's `in` path
    follow (F17); the parent as an option on the wire (F37); the hook
    registry a dict (F38); `call_python`, the load-call-error phrase
    both ML entries end on, and `working_directory_argument` for the
    two tools' one argument (F39); `model._indented`, the one
    split-and-indent (F40); `baselines.fenced_blocks` reading a fence
    indented inside a list item, so that CO §7's sentences are read
    from the document by all four tests (F41).
  - Tests, 19 (F18–F32, F34–F36, F42): each gap closed with a case, and
    each new case checked against the wrong implementation it is there
    for — 29 mutations swapped in in memory, every one caught
    (`ai-artifacts/review_phase_b/mutations.py`, `run_mutations.sh`).
  - Text, 8 (F44–F51): the order of `tat.scala`'s sections, six
    comments and docstrings, MS §2.3's "an option Isabelle does not
    know".
- Rejected, 2 (F43, F52).
- For the owner, 10 — the specification silent or at odds with itself,
  or the fix a change to a decided design or to wording someone reads:
  - F2: an option value Isabelle/ML accepts and Isabelle/Scala refuses
    when it reads the ROOT (`timeout = 10min`): creation checks with
    `Options.update` in ML, as CO §2 decides, and CO §2 also says
    creation catches a value of the wrong type.
  - F3: CO §2's decided sentence that nothing a compile does enters a
    dot-folder or follows a link is false of the lock and the log, which
    a compile shares with a conversation.
  - F4: a folder at a tree's file path makes every compile fail midway;
    CO §5 calls the refusal there a bug.
  - F6: a generator function passes the hook's check and never runs.
  - F7: a compile on a database `TAT_new` made writes the schema into
    it, against "it writes nothing to the database".
  - F9: two `Session`s whose names differ only in case.
  - F11: where `Session.gen` judges a name Isabelle reserves — ST §1
    lists it beside `ROOT`, the code asks in the one round trip, after
    the checks that cost none.
  - F12: Isabelle's message for a value of the wrong type holds a line
    break, inside the agent's one-line sentence.
  - F13: the coroutine rule compares an override with the method it
    overrides, a plugin's own included; PLUGIN_SYSTEM §5 says "the
    framework's method".
  - F15: a class that leaves `emit` or `emit_beginning` abstract
    registers, and fails at its first instantiation with a bare
    `TypeError`.

  Ruled on 2026-10-04, and done the same day but for F2: F3, CO §2's
  sentence narrowed to the disk step, no refusal of a link at the lock;
  F4, a folder at a path the compile will create refused before anything
  is removed, with CO §7 item 5's third sentence; F6, a generator
  refused at registration ("可以批准，但其实无所谓"); F7, a compile's
  store read-only, a database without the store's tables the empty
  forest ("赞同，但其实无所谓"); F9, session names compared without
  regard to case through a namespace whose refusal is the id component's
  `DuplicateName`, no new sentence ("直接说命名冲突就行"); F11, ST §1
  and MS §2.3 reworded to the code's order; F12, the lines of Isabelle's
  message joined by single spaces; F13, PLUGIN_SYSTEM §5 and CO §3
  widened to "the method it overrides"; F15, no check — plugins are
  trusted ("我们始终可以相信 plugins 的"), which PLUGIN_SYSTEM's opening
  now states, with what TAT does not trust. F2, approved on 2026-10-05
  once the owner had asked whether the Scala call would run at every
  evaluation (it runs once per `Session` created, never at an
  evaluation): the options are checked by a second Scala function in
  `lib/tat.jar`, `TAT.check_options`, a `Scala.Fun_Strings` taking the
  names and values in turn and applying each as `Options.init() +
  spec`, answering nothing or the first refused option's index and
  Isabelle/Scala's message — the message the documents' example shows —
  in place of ML's `Options.update`; `Options.init()` is read once per
  process.
