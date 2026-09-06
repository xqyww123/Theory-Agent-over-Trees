# Plan: the first end-to-end run

Status: in discussion. A section marked *(approved)* records the owner's
decision; anything marked *(proposed)* or *(open)* is not settled. Once a
section is settled it moves into the design documents under `docs/`, and
this file keeps only the implementation record.

## 0. Scope

One real tree, evaluated by Isabelle, through the MCP tools. That needs the
`Session` and `Theory` node classes, the forest scheduling that evaluates
imported trees first (ARCHITECTURE §3.5), a `Theorem` that emits only
`sorry`, the `edit` tool, and the persistence everything sits on.
`construct`, AoA, the other node classes, and compilation to `.thy` files
(§1) are outside this plan.

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
  `master_dir`; the Python side writes the files and the forest there.
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
  def to_store(self, rows: Node_Rows) -> None            # write authored and recorded fields
  @classmethod
  def from_store(cls, rows: Node_Rows) -> Self           # rebuild from them; synchronous, no wire
  ```

  `Node_Rows` is a handle the framework makes for one node for one call —
  `store.rows(identity)`, offering `put(field, value)`, `get(field)` and
  `fields()` on that node's rows and refusing `kind` and `children`. A
  class never holds the store or another node's rows. Every stored value
  must be MessagePack-representable. A recorded field must not hold a
  value meaning "work is running": `Theorem` stores a running search as
  `not_started`.
- The framework does the rest. `_store_subtree(node)`: `delete_node`,
  then `kind`, then `children` for a nesting node, then
  `node.to_store(rows)`, then each child. `_load_subtree(identity)`: read
  `kind`, pick the class from the kind table, `cls.from_store(rows)`, set
  the identity, the parent and a fresh state slot, then the children in
  order. Loading the forest is `_load_subtree(0)`. Identities are handed
  out by the framework in `_construct_element`, from `next_identity()`.
- Every **write operation** is one transaction: `edit`, `move`, `delete`,
  and an evaluation hook writing a recorded field. Read operations
  (`recall`, `status`) do not touch the database. The transaction opens
  once the operation has succeeded in memory and closes before the next
  `await`; nothing is awaited inside a transaction. Identities are handed
  out before the transaction exists, so `next_identity()` needs none:
  outside one it is its own write. An operation stores only what it
  changed: `_store_subtree` for every new subtree and for a replaced
  node, the parent's `children` row when that list changed, `delete_node`
  for every node that left, and the one node whose recorded field an
  evaluation hook wrote.
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

## 3. `Theory`'s attribute table *(approved 2026-09-04)*

| Attribute | Type | |
| --- | --- | --- |
| `name` | the theory's short name, `str`: an Isabelle identifier — a letter, then letters, digits, underscores and primes; no dot, no hyphen | authored |
| `imports` | `list[str]`, non-empty; each item as it would be written in the header's `imports` clause: `Main`, `HOL-Library.Multiset`, or a path such as `"lib/Rel"` | authored |

No recorded field. Its construct declares `children`, `items` being
`#/$defs/Construct`, so a theory is created with its first declarations
in one call.

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
forest-wide namespace of theory short names, and the framework's claims
registry — the `taken` mechanism of `_construct_siblings`, extended to
named namespaces, seeded from the pre-edit forest less `config.replacing`
and accumulating the batch's claims, reachable from `NodeConfig` — refuses
a second claim with `DuplicateTheoryShortName`, whose holder is then a
sibling id or a coordinate of the same call (RENDER_BASELINES §2).

## 4. Creating a `Session` *(approved 2026-09-04)*

There is no `new_session` tool. The forest root has the id `Sessions`;
`edit` with `action: "append"` and `target_id: "Sessions"` creates a
`Session`, and `amend` and `delete` address one by id like any node. Every
other action on the root is refused (`ProtectedNode`), and `Sessions` is a
reserved node name. The first layer is ordered like any other.

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
placed after it is a stop, reported by TAT before the tree runs:

```
Since `theory_B` imports `S.C`, you cannot put it before `S.C`. Move it later.
```

(`S.C` as the agent wrote it in `imports`; RENDER_BASELINES §2.) `move` is
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
round trip per tree.

**A stop crossing an import edge.** Before a tree runs, the forest looks
at the `Theory` nodes of its direct imports. If any is not `ready` at its
ending, the tree is not run but walked in the blocked mode already
defined for a failed opening — `Evaluating(blocked_by=X)`, `X` the
stopped node — so every node in it becomes `cannot_evaluate` with the
same `blocked_by`, and the result reports `X`. Trees that do not import
the stopped tree run normally. No new mode is needed.

**Invalidation at the `Session` layer.** Positions under a `Session` or
the root are not walked: sibling trees are independent unless the graph
says otherwise. Instead:

- An edit inside tree `T` runs `T`'s own walk from the edited position
  (the `Seeking` walk of ARCHITECTURE §3.5), then invalidates every
  transitive importer of `T` whole (a walk in the `Invalidating` mode).
- Every edit also compares the import graph before and after itself,
  keyed by tree identity: a tree whose resolved import set changed —
  because a qualified name it named vanished or appeared, through a
  rename, a delete, a move into another `Session`, or a `Session`'s
  rename — is invalidated whole, with its transitive importers. The
  comparison is the framework's, once, in the edit entry; no edit path
  has to remember which names it disturbed.
- A qualified name that vanished is removed from the ML theory table in
  the same operation (a new callback, `TAT.theory_delete`, and
  `Theories.delete`), so `Loader.resolve` can never hand an importer a
  theory value of a tree that no longer exists. EVALUATOR_DESIGN §3
  changes accordingly.

**The `Theory` root's slot chain.** `Theory.state`, its input slot, is
never written: `begin_theory` starts from `Toplevel.make_state NONE`, and
`Theory`'s beginning ignores the slot. Its ending runs `end`, writes the
resulting state into its resulting slot like any `StdBlock` — so the
release invariants hold unchanged — and puts the theory value into the
theory table through `end_theory`. Nothing reads that resulting slot.

**`Session`.** A `NonLeaf_Node` off the evaluation path. Its trees are not
chained: `_predecessor_wrote` is false, `_carry_forward` does nothing, and
`_resulting_state_of_child(tree)` is a slot of the tree's own, never the
next tree's input. Those three overrides move from `Forest` to `Session`;
`Forest` keeps only the graph, the scheduling above, and id resolution.
`Session` has a state slot like every node, unused.

## 7. Implementation order *(proposed)*

Each step lands with its tests, passes review, and is committed before the
next begins. The ML end-to-end test (`test/run_ml_framework_test.py`) runs
at every step that touches the ML side.

1. **Persistence in the model** (§2): `Node_Rows`, `to_store`/`from_store`
   on the hierarchy, `_store_subtree`/`_load_subtree` on `Forest`,
   identities from `next_identity()`, root 0; the edit entries store what
   they changed; `__getstate__`/`__setstate__` and the class counter go.
   Tests: round trips through a real `Forest_Store`, and the edit suite's
   fake classes gain `to_store`/`from_store`.
2. **The loader** (PLUGIN_SYSTEM.md): `construct_schema`, kinds from the
   schema, a bare `@TAT_node`, the checks of §5 with `CannotLoadPlugin`,
   `$defs` hoisting, `#/$defs/Construct`; `is_finished` final with
   `_owes_nothing`; the claims registry of §3 (namespaces on `NodeConfig`);
   `jsonschema` as a dependency; `edit.jsonc`. Tests: the assembled
   schema validates, and constructs of every shipped kind validate against
   it.
3. **`Session`, `Theory`, and `Theorem` emitting `sorry`** (§3, §4,
   SESSION_AND_THEORY.md): Python halves in `builtins.py` and
   `theorem_node.py`; the ML evaluators of `Theory` and `Theorem` in
   `TAT_Common_Nodes.ML`; `Session`'s three overrides. Tests: the ML
   end-to-end test drives a theory with two lemmas to `end`.
4. **The forest walk** (§6): the import graph, the order constraint's stop,
   transitive imports before `T`, stops across import edges, invalidation of
   importers, the pre/post graph comparison, `TAT.theory_delete`.
   Tests: the fake-table suite gains multi-tree forests.
5. **The tools and the entry point**: `mcp.py` with `edit`, `move`,
   `delete` (TOOL_SCHEMAS.md) and the `quickview` appended to every result
   (PRINT.md, its default rendering only); `mcp_server.py`; `toplevel.py`'s
   `launch_TAT` taking the working directory, `TAT_Framework.start` passing
   it; `Dev/TAT_Dev.thy` starting a conversation. Test: an in-process
   client calls the tools and evaluates one tree in Isabelle.

Out of this plan, in the order they are likely needed afterwards: `recall`,
`evaluate_to` and `status` as tools (TOOL_SCHEMAS.md §5); the renderings
(PRINT.md); the import question (§5); compilation (§1); `construct`.
