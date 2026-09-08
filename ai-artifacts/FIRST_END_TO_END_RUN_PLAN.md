# Plan: the first end-to-end run

Status: approved through §6 (three review rounds, the last READY_WITH_FIXES
with every fix landed); §7 is the proposed order of work; the items
marked *(open)* are deliberately left open and block nothing in it. Once a
section is settled it moves into the design documents under `docs/`, and
this file keeps only the implementation record.

## 0. Scope

One real tree, evaluated by Isabelle, through the MCP tools. That needs the
`Session` and `Theory` node classes, the forest scheduling that evaluates
imported trees first (ARCHITECTURE §3.5), a `Theorem` that emits only
`sorry`, the `edit`, `move` and `delete` tools, and the persistence
everything sits on. `construct`, AoA, the other node classes, and
compilation to `.thy` files (§1) are outside this plan.

## 1. The working directory *(approved 2026-09-04)*

TAT starts on one directory, the **working directory** (ARCHITECTURE §1),
and its layout is fixed:

```
<working directory>/
  theory_forest.sqlite     the forest (§2); read at start, created empty if absent
  ROOT                     every Session's entry (ARCHITECTURE §4)
  <session name>/          one folder per Session, named after it
    <theory name>.thy      one file per tree, named after the theory's short name
```

- A `Session`'s directory is its name, not an attribute.
- The client hands the directory to `TAT_Framework.start`, which passes it
  to `launch_TAT` as an argument. Both sides read the same string: the ML
  side's `begin_theory` takes `<working directory>/<session name>` as the
  `master_dir`; the Python side keeps it in the `Conversation`
  (MODULE_STRUCTURE §4.1) and writes the files and the forest there.
- TAT owns the files: deleting a tree deletes its `.thy`, deleting a
  `Session` deletes its folder.

*(open, deferred)*: when the `.thy` files and the ROOT are written — the
owner's inclination is when the agent declares its task done — and how the
directory is kept equal to the forest, since a `.thy` left behind under a
`master_dir` is loaded by Isabelle as a second theory (§5). The first run
writes no `.thy` at all, so nothing turns on this yet.

## 2. Persistence *(approved 2026-09-04)*

The forest is stored in one SQLite database, not pickled.

- One table, `fields (node INTEGER, field TEXT, value BLOB, PRIMARY KEY
  (node, field))`: one row per node field, the value in MessagePack. `node`
  is the node's identity number (MCP_SPECIFICATION §2), which survives
  renaming and moving.
- A second table, `meta`, holds the identity counter — so identities stay
  fresh across restarts — and a schema version. A database whose schema
  version is not this TAT's is refused at start (`IncompatibleStore`, a
  `TAT_StartupError`, EXCEPTIONS.md §1).
- Stored per node: `kind`; on a nesting node, `children` (the ordered
  list of the children's identities); and whatever the node class writes
  (below). The two framework rows are the two names a construct reserves,
  so no class field can collide with them. No `parent` row: parenthood is
  read off `children`. The forest root is identity 0 — `next_identity`
  starts at 1 — and has one row, `children`. Not stored: evaluation
  statuses and state slot names — a loaded forest is `not_evaluated`
  throughout (ARCHITECTURE §4.1).
- **Each node class writes and reads its own fields**:

  ```python
  def to_store(self, rows: Node_Rows) -> None                          # write authored and recorded fields
  @classmethod
  def from_store(cls, config: NodeConfig, rows: Node_Rows) -> Self     # rebuild from them; synchronous, no wire
  ```

  `from_store` takes the `NodeConfig` construction takes — `parent` the
  rebuilt parent, `state` a fresh slot, `replacing` None — so a class's
  `from_store` is its `gen` with `rows` in place of `raw`: the same
  constructor call, a second slot from `Isar_State_Slot.assign` exactly as
  `gen` gets it. `Node_Rows` is a handle the framework makes for one node
  for one call — `store.rows(identity)`, offering `put(field, value)`,
  `get(field)` and `fields()` on that node's rows; `put` refuses `kind`
  and `children`, `get` serves them, `fields()` omits them. A class never
  holds the store or another node's rows. Every stored value must be
  MessagePack-representable. A recorded field must not hold a value
  meaning "work is running": `Theorem` stores a running search as
  `not_started`.
- `kind` is the framework's: `edit._construct_element` sets `node.kind` from
  the construct, `_load_subtree` sets it from the row, and no class keeps
  a copy — `Theorem` declares `kind` in its two schemas for the agent and
  the static checker and reads `node.kind` like everyone else.
- The framework does the rest. `_store_node(node)`: `delete_node`, then
  `kind`, then `children` for a nesting node, then `node.to_store(rows)`;
  `_store_subtree(node)`: `_store_node`, then each child. An evaluation
  hook's write and an amend's replaced node use `_store_node`; a new
  subtree uses `_store_subtree`. `_load_subtree(identity)`: read
  `kind`, pick the class from the kind table, `cls.from_store(config,
  rows)`, set the identity, then the children in order. The root is not a
  `_load_subtree` case: the framework makes the `Forest`, reads row
  `(0, children)` — absent on a fresh database, and the forest is empty —
  and loads each child; `_store_subtree` never runs on the root, and only
  its `children` row is ever written. Identities are handed out by the
  framework in `edit._construct_element`, from `next_identity()`.
- Every **write operation** is one transaction: `edit`, `move`, `delete`,
  and an evaluation hook writing a recorded field that is stored — one
  held only for the life of the conversation, such as `Theory`'s error
  messages (SESSION_AND_THEORY.md §2), needs none. Read operations
  (`recall`, `status`) do not touch the database. The transaction opens
  once the operation has succeeded in memory and closes before the next
  `await`; nothing is awaited inside a transaction. A transaction that
  fails raises `TAT_DisasterError` (EXCEPTIONS.md §1): the operation is
  already committed in memory, so memory and the database have parted,
  and the conversation ends. Identities are handed
  out before the transaction exists, so `next_identity()` needs none:
  outside one it is its own write. An operation stores only what it
  changed: `_store_subtree` for every new subtree, `_store_node` for a
  replaced node, the parent's `children` row when that list changed,
  `delete_node` for every node that left, and `_store_node` for the one
  node whose recorded field an evaluation hook wrote.
- The access layer is TAT's own, `Forest_Store` (one module, standard
  library `sqlite3`, WAL mode): `transaction()` is the only way to open a
  transaction, and `put`/`delete_node` outside one is an error; `get`,
  `fields(node)`, `nodes()` serve loading; `next_identity()` serves
  creation. One connection, used from the event loop only: background
  work writes through the loop, never from another thread.
- Replaces `__getstate__`/`__setstate__` in `model.py`, the class
  identity counter, and the pickle paragraphs of ARCHITECTURE §4.1 and
  MODULE_STRUCTURE §4.1. `test_model.py` and `test_ids.py` pickle nodes
  today; they round-trip through the store instead.

## 3. `Theory`'s attribute table *(approved 2026-09-04; revised 2026-09-08)*

The table of record is SESSION_AND_THEORY.md §2, which since 2026-09-08
also carries the two recorded, never stored fields `beginning_errors` and
`ending_errors`, and notes that the framework's name grammar refuses a
trailing underscore. In brief:

| Attribute | Type | |
| --- | --- | --- |
| `name` | the theory's short name, `str`: an Isabelle identifier — a letter, then letters, digits, underscores and primes; no dot, no hyphen | authored |
| `imports` | `list[str]`, non-empty; each item as it would be written in the header's `imports` clause: `Main`, `HOL-Library.Multiset`, or a path such as `"lib/Rel"` | authored |

Its construct declares `children`, `items` being `#/$defs/Construct`, so
a theory is created with its first declarations in one call.

- The qualified name is `<Session name>.<name>`, computed on demand, never
  stored. The ML side derives the same string through
  `Resources.import_name` and keys the theory table by it
  (`ML/TAT_Framework.ML`, `begin_theory`); a dotted `name` is refused there
  as a framework bug, so `Theory.gen` refuses it first.
- No hyphen, as `Theorem` already rules for its names: the short name is
  written into `theory X imports … begin`, into other trees' `imports`,
  and into qualified fact names such as `X.P`.
- `imports` is non-empty because Isabelle's header grammar requires at
  least one import (`Thy_Header.args`, `Scan.repeat1`); only `Pure` is
  exempt.
- `gen` checks the shape of `imports` and nothing more: resolving an import
  may load a theory from source, which is a write to `Thy_Info`, and `gen`
  must not write (MODULE_STRUCTURE §4.1). Whether an import exists is
  reported by `begin_theory` at evaluation. §5 may add one forest-only
  check.
- Not in the first version: the header's `keywords` and `abbrevs` clauses.

`Theory.gen` checks: the parent is a `Session` (`BadTheoryNodeParent`); the
identifier grammar of `name` (`InvalidName`, rendering the agent's own
spelling); the short name against the base heap through
`check_new_theory_short_name`; `imports` non-empty with non-empty strings
(`InvalidField`). The short name's uniqueness **within the forest and the
batch** is the framework's: `Theory` declares that its name lives in the
forest-wide namespace of theory short names, and the framework — after
the `taken` check of `edit._construct_siblings` — walks the pre-edit forest,
less the node the amend replaces, which is leaving, for a node bearing the
name in that namespace, and keeps the names the call's constructs have
taken so far; either way it refuses the construct with
`DuplicateTheoryShortName`, whose holder is then a node's id or the full
path of a construct of the same call (RENDER_BASELINES §2). Nothing is
kept across calls.

## 4. Creating a `Session` *(approved 2026-09-04)*

There is no `new_session` tool. The forest root has the id `Sessions`;
`edit` with `action: "append"` and `target_id: "Sessions"` creates a
`Session`, and `amend` and `delete` address one by id like any node. Every
other action on the root is refused (`ProtectedNode`); `Sessions` is the
root's id, which no node's id component `<kind>_<name>` can be
(MCP_SPECIFICATION §2). The first layer is ordered like any other.

`Session` is an ordinary node class. Its construct carries `name`;
`parent_session` (the parent Isabelle session of the ROOT entry; required,
no default); `options`, a list of `{name, value}` pairs — a map with free
keys is refused by strict tool schemas on every major provider — defaulting
to empty; `description`, defaulting to empty; and `children`, `items`
being `#/$defs/Theory`. Its attribute table and the wording of every field
description are in `SESSION_AND_THEORY.md` §1, which is where a node
class's agent-facing descriptions live (PLUGIN_SYSTEM.md §3).

Rendering — `print`, `quickview`, the root's two renderings and the
empty-forest hint — is PRINT.md.

*(open)*: whether `parent_session` is checked against Isabelle's known
sessions (needs a new ML callback) or only transcribed into the ROOT entry.

## 5. How an import names a forest tree *(open)*

Facts, from the Isabelle source (`Resources.import_name`) and an
in-process probe (`scratchpad/probe_imports`, 2026-09-04):

- A bare import name is qualified with the importing theory's own session
  name; a dotted name is taken as written. The ML side then consults the
  conversation's theory table first, under exactly that string.
- So `imports S.A` works from any session once tree `A` of session `S` is
  evaluated to its end, the importing tree's own session included
  (verified). A bare `imports A` works only from session `S` (verified).
- A bare `imports A` from another session `T` looks for `T.A`: with no
  file `T/A.thy` it fails with Isabelle's `No such file: ".../T/A.thy"
  … for theory "T.A"`; with such a file present (a stale one, under §1)
  it silently loads a second theory `T.A`, and a later theory importing
  both fails with `Duplicate theory name` far from the cause (verified).
- Whatever the rule, the forest's import graph (§6) must recognise both
  the bare and the qualified spelling of a forest tree, or the importing
  tree runs before its import is in the table.

What TAT does about the bare cross-session import is not decided.

## 6. `Forest._evaluate` *(approved 2026-09-04)*

What §6 settles: the import graph; the order and mode in which trees run;
how a stop crosses an import edge; what invalidation means at the
`Session` layer, including after an edit that changes or removes a
qualified name (R4 of the plan review); the theory table's removal; the
two ends of a `Theory` root's slot chain; and `Session`'s framework
methods.

**The order constraint** *(approved 2026-09-04)*. A tree comes after every
forest tree it imports: within a `Session`, later in the list; across
`Session`s, in a later `Session`. Tree order is therefore a dependency
order, and no sorting is ever needed. A tree that imports a forest tree
placed after it is an evaluation stop of that tree, not a `TAT_Error`: the
violating state is reachable with every edit accepted (the import is
external until the imported tree is appended after it). The check runs
before every run of the tree and is never stored, so a repairing `move`
clears it by itself; the tree is walked in the `Invalidating` mode — it is
`not_evaluated`, nothing about it was attempted, and no new status value
is needed — and the evaluation result carries, beside "stopped at
`theory_B`", the sentence

```
Since `theory_B` imports `S.C`, you cannot put it before `S.C`. Move it later.
```

(`S.C` as the agent wrote it in `imports`; RENDER_BASELINES §3.) `move` is
how the agent repairs the order.

**The import graph.** A tree's resolved imports are computed from its
`imports` strings by the rule of §5 — a bare name qualified with the
tree's own `Session` name, a dotted name as written — and matched against
the qualified names of the forest's trees; a name matching no tree is
external and Isabelle's business. The graph is recomputed from the forest
whenever it is needed; it is never stored. It is not a chain: a later tree
need not depend on an earlier one, so every rule below follows the graph,
never the position.

**Running.** `evaluate_to(destination)` names a node; its tree is `T`.
The forest runs `T`'s transitive imports, in tree order, each to its own
`end` — a walk whose destination is that tree's `Theory` node — then runs
`T` to the destination. Trees `T` does not import are not touched. A
`Session` as destination stands for all trees under it; the root, for all
trees. Each tree's walk is one `Evaluation`, flushed when it ends: one
round trip per tree. The call's `ignore_error` applies to every tree it
runs. When several trees stop, the call reports the first in tree order
(MCP_SPECIFICATION §4); each stopped tree's own report is in its nodes.
`Forest._evaluate` carries the reported stop for both forest-level stops
— the order constraint's and the import edge's — since the recursion
returns no `stopped_at` from a blocked or invalidating walk.

The forest reads a tree's `imports` and a `Session`'s `name` directly:
`Session` and `Theory` are the two classes that carry the forest's
structure (ARCHITECTURE §2.2), framework classes defined in `model.py`,
not plugins in `builtins.py`. `plugin.load` registers them itself, first,
through the same `TAT_node` every plugin class goes through, so the
checks of PLUGIN_SYSTEM §5 apply to them and they head the registration
order. Their ML evaluators stay in `TAT_Common_Nodes.ML`.

**A stop crossing an import edge.** Before a tree runs, the forest looks
at the `Theory` nodes of its direct imports. If any does not have both its
operations `ready` — the ending alone does not do: after a failed header
the ending is `ready` and no theory value exists (the `Theory` root's slot
chain, below) — the tree is not run but walked in the blocked mode already
defined for a failed opening — `Evaluating(blocked_by=X)`, `X` the
stopped node — so every node in it becomes `cannot_evaluate` with the
same `blocked_by`, and the result reports `X`. Trees that do not import
the stopped tree run normally. No new mode is needed.

**Invalidation at the `Session` layer.** The routing lives in
`Forest._evaluate` alone. A `Seeking` position is resolved upward to the
tree containing it, and that tree alone is walked; a position whose
parent is a `Session` or the root walks nothing — sibling trees are
independent unless the graph says otherwise. `Session._evaluate` raises
`TAT_InternalError`: evaluation is transparent to the `Session` layer, and
a walk that reaches one is a framework bug. Three rules complete it:

- Whenever a tree's `Theory` ending goes from `ready` to anything else,
  its transitive importers become `not_evaluated` (each walked in the
  `Invalidating` mode). This is a property of the status, enforced in the
  ending's status setter on the guard `on_invalidated` already uses — old
  `ready`, new not `ready`; not the release guard, which stays silent when
  `ready` becomes an own stop, exactly the case a tree without a theory
  value is — so it covers `evaluate_to` on an inner node as well as every
  edit. The setter needs the forest and the graph, so the status setters
  become `async`; every caller already is. The recursion ends because a
  status leaves `ready` at most once per walk, so each tree is
  invalidated at most once.
- Every edit snapshots, per tree identity, the pair (qualified name,
  resolved import set) before and after itself; a tree whose pair changed —
  its `Session` renamed, itself renamed, moved into another `Session`, or
  a name it imports vanished or appeared — is invalidated whole, with its
  transitive importers. The snapshot is the framework's, once, in the edit
  entry; no edit path has to remember which names it disturbed. This is
  the mechanism behind ARCHITECTURE §3.4's "editing a `Session`
  invalidates every tree under it".
- A qualified name that vanished is removed from the ML theory table in
  the same operation (a new callback, `TAT.theory_delete`, and
  `Theories.delete`), so `Loader.resolve` can never hand an importer a
  theory value of a tree that no longer exists. EVALUATOR_DESIGN §3
  changes accordingly.

**The `Theory` root's slot chain** *(revised 2026-09-08)*. `Theory.state`,
its input slot, is written by nobody: `begin_theory` starts from
`Toplevel.make_state NONE`, and `Theory`'s beginning ignores the slot. Its
resulting slot is its own — `_state_after_ending`, which `resulting_state()`
returns and `_states_inside` includes, so a leaving tree releases it — since
under an unchained container no successor's input is there to be it. Its
ending runs `end` into that slot and puts the theory value into the theory
table through `end_theory`. Nothing reads the slot. The release invariant
therefore reads, for a tree: the resulting slot holds a value exactly when
the ending's write is still current and its source held something — held
after a successful `end`, and after a failed `end`, whose copy-through
copies the open theory's state; empty after a failed header, whose
copy-through copies an input nobody wrote, so that the ending is `ready`
(ARCHITECTURE §3.2) with an empty slot and no theory value in the table.
This is why the import-edge rule above asks for
both of the `Theory`'s operations `ready`, never the ending alone.

**`Unchained_Node`, `Session` and `Forest`.** A `Session`'s trees, and the
root's `Session`s, are not chained: no child's resulting state is the next
child's input. One class between `NonLeaf_Node` and both of them,
`Unchained_Node`, carries every consequence once, and mints no slot:
`_resulting_state_of_child` is refused — a child that has a result owns the
slot for it (above); `_predecessor_wrote` is False, `_source_before` is None
and `_carry_forward` does nothing;
`_last_status` is `NOT_EVALUATED` — the container runs no operation, so it
has written nothing, and the inherited edit paths that ask (an amend, a
delete or a move of a `Session`) correctly release nothing;
`_mark_not_evaluated` marks nothing; `_resulting_state_of_all_children` is
refused — the container keeps no slot after its children. `Session` adds
its fields and the `TAT_InternalError` above; `Forest` adds the graph, the
scheduling above, and id resolution. `Session` has a state slot like every
node, unused.

## 7. Implementation order *(proposed)*

Each step lands with its tests, passes review, and is committed before the
next begins. The ML end-to-end test (`test/run_ml_framework_test.py`) runs
at every step that touches the ML side.

1. **Persistence in the model** (§2): `Node_Rows` (in `store.py`),
   `to_store`/`from_store` on the hierarchy, `node.kind`,
   `_store_node`/`_store_subtree`/`_load_subtree` on `Forest`, identities
   from `next_identity()`, root 0; the edit entries store what they
   changed, each in one transaction after its commit step;
   `__getstate__`/`__setstate__` and the class counter go. Tests: round
   trips through a real `Forest_Store`, and the edit suite's fake classes
   gain `to_store`/`from_store`.
2. **The loader** (PLUGIN_SYSTEM.md): `construct_schema`, kinds from the
   schema, a bare `@TAT_node`, the checks of §5 with `CannotLoadPlugin`,
   `$defs` hoisting, `#/$defs/Construct`; `is_finished` final with
   `_owes_nothing`; the namespace check of §3 (the class's `namespace`);
   `load` registering `Session` and `Theory` first;
   `jsonschema` as a dependency; `edit.jsonc`. (`UnexpectedField.takes`
   without `kind` at the top level is done.) Tests: the assembled schema
   validates, and constructs of every shipped kind validate against it.
3. **`Session` and `Theory`** (§3, §4, SESSION_AND_THEORY.md):
   `Unchained_Node`, `Session` and `Theory` in `model.py`; the ML
   evaluator of `Theory` in `TAT_Common_Nodes.ML`; the description
   baseline test over SESSION_AND_THEORY.md. Tests: the ML end-to-end
   test drives an empty theory, and a second one importing it, to `end`.
   *(2026-09-08: `Theorem`, first planned for this step, follows as its
   own step once these two are in — its construct schema, ARCHITECTURE
   §2.2's `kind` and `statement` as AoA's `LongStatement` with no proof
   text, and its descriptions are proposed for approval then, in a
   `docs/node_classes/THEOREM.md`.)*
4. **The forest walk** (§6): the import graph, the order constraint's stop,
   transitive imports before `T`, stops across import edges, invalidation of
   importers, the pre/post graph comparison, `TAT.theory_delete`.
   Tests: the fake-table suite gains multi-tree forests, and pins the
   order constraint's sentence from RENDER_BASELINES §3 the way the
   exception renderings are pinned.
5. **The tools and the entry point**: `mcp.py` with `edit`, `move`,
   `delete` (TOOL_SCHEMAS.md — `insert_after` is `edit.insert` at
   `index + 1`; `HoldsNoChildren` and `ProtectedNode` are refused here,
   before the model is called) and the `quickview` appended to every
   result (PRINT.md, its default rendering only); `mcp_server.py`;
   `toplevel.py`'s `launch_TAT` taking the working directory,
   `TAT_Framework.start` passing it; `Dev/TAT_Dev.thy` starting a
   conversation. Test: an in-process client calls the tools and evaluates
   one tree in Isabelle.

Out of this plan, in the order they are likely needed afterwards: `recall`,
`evaluate_to` and `status` as tools (TOOL_SCHEMAS.md §5); the renderings
(PRINT.md); the import question (§5); compilation (§1); `construct`.
