# TAT's evaluator

Paths are relative to `contrib/Isabelle2025-2/src/` unless prefixed; Isa-REPL
paths are relative to `contrib/Isa-REPL/`.

TAT drives Isabelle itself, command by command. Isa-REPL (`contrib/Isa-REPL`)
has done this for years and is the reference: its shape is evidence, and §4
lists the hazards its review exposed. It serves only as the development-time
client (ARCHITECTURE §9).

## 1. The mechanism

Measured on a stock Isabelle2025-2, using only functions in the public
signatures of unpatched files.

Every `Toplevel.state` lives in a state slot (§1.1), and a node's evaluator is
handed the slot it starts from and the slot it writes (ARCHITECTURE §3.1). No
file is read: each evaluator receives the text of its own node's commands.

For the `Theory` root node's header:

- read it with `Thy_Header.read`
- resolve each import to a `theory` value (§2)
- merge the parents' keyword tables (`Thy_Header.get_keywords`,
  `Keyword.merge_keywords`) before tokenising, or a parent-defined command
  tokenises as garbage
- do not pre-create the theory: start from `Toplevel.make_state NONE` and let
  the `theory … begin` span call an `init` that performs
  `Resources.begin_theory master_dir header parents`

For any node's commands:

- split the text with `Outer_Syntax.parse_spans`
- run each span through `Toplevel.command_errors true`, threading the state
  from the input slot to the resulting slot

For the root node's closing `end`, `Toplevel.end_theory` yields the `theory`
value, which goes into the theory table (§3).

`Toplevel.command_errors` returns `(errors, state option)`; check both, since a
failing command can return no state. The errors are `Runtime.error` values,
`((serial * string) * string option)`, not exceptions. It is the
error-recovering runner — batch loading uses `Toplevel.command_exception`,
which re-raises and therefore stops at the first failure.

Its first argument is Isabelle's interactive flag and must be `true`. `sorry` is
`Method.cheating`, which raises `Cheating requires quick_and_dirty mode!` unless
that flag is set or `quick_and_dirty` is on (`Pure/Isar/method.ML:155-158`).
Stock Isabelle passes `true` (`Pure/PIDE/command.ML:234`), on the path both
interactive and batch runs take.

`Resources.begin_theory` does not touch the filesystem. It stores `master_dir`
as data, which matters only for body commands like `ML_file` that resolve
against it.

### 1.1 The state slot table

The evaluator holds `Toplevel.state` values in one table keyed by a name, and
the Python side holds only names (ARCHITECTURE §3.1). Running a node is
"from the state under this name, run these commands, put the result under that
name". Re-evaluating a node writes the same name again; a name's value is
removed when its node is invalidated or deleted (ARCHITECTURE §3.4).

Each conversation has its own state slot table, created when the conversation
starts and left to the garbage collector when it ends. Nothing outlives the
conversation.

A node class's asynchronous work can reach this table while evaluation runs
(ARCHITECTURE §9), so it is locked. `contrib/Isabelle_RPC/Tools/RPC.ML:429-437` is the pattern in use in
this project family: a hash table plus a `Synchronized.var` held across every
read and write.

## 2. One prover, and what resolution becomes

TAT launches a prover on one base heap. The forest's `Session`s are Isabelle
sessions under construction: every tree is authored, none is in a heap, and a
tree's qualified name is its `Session`'s `name` joined to its own (§7). When
the forest is finished they are ordinary Isabelle sessions someone else builds
(ARCHITECTURE §4).

Import resolution, in order:

```
resolve name =
    our own table            (* trees this conversation evaluated to their end *)
  | Thy_Info.lookup_theory   (* the base heap *)
  | load from source (§6)    (* a library theory the heap lacks *)
```

One producer means one slot per name, so two distinct `theory` values with one
name — which raise `Duplicate theory name` (`Pure/context.ML:383`) or `Cannot
join theories` (`:521`) — cannot be constructed. The invariant holds by shape.

Everything the forest imports from outside itself is expected to be in the base
heap. An import that is not there is loaded from source rather than refused, so
that an agent which discovers a dependency mid-work is not stopped to wait for a
heap rebuild.

## 3. The theory table

A table from qualified theory name (§7) to `theory` value, written by the
`Theory` root node's closing command — its `end` (§1). A second write
overwrites: TAT re-evaluates on every edit.

The table keeps no dependency edges and deletes nothing, because invalidation is
not its job. The Python side marks every tree that imports a changed tree
`not_evaluated` (ARCHITECTURE §3.4) and never requests a theory whose tree is
not evaluated to its end (ARCHITECTURE §3.5), so a stale entry is never read; it is
overwritten when the tree is evaluated again. Like the state slots (§1.1), the
table is locked, since a node class's asynchronous work can reach it while
evaluation runs.

## 4. What to avoid, and why

Each of these is a defect found in Isa-REPL by review, and a hazard of this
design.

**One flag must not gate several effects.** `register_theory'`
(`REPL.ML:521`, `:679-684`) gates the theory-table insertion, the `Thy_Info`
registration and the writing of `.thy` files together. Nobody can have one
without the others.

**Per-connection state must not live in `Thread_Data`.** `Future.fork`
propagates `Position.thread_data` and the generic context, nothing else
(`Pure/Concurrent/future.ML:452`). Isa-REPL keeps its session id and its theory
table in `Thread_Data` (`REPL.ML:243`, `:315`), so any message produced on a
forked worker cannot find its session and is dropped (`REPL.ML:271-275`). Route
by `Position.id` as PIDE does, or pass the identity explicitly.

**Do not let one name have two producers.** Isa-REPL evaluates some theories
itself into its own table and loads others through `Thy_Info.use_theories` into
`Thy_Info`'s graph, with nothing keeping a name out of both. TAT also has two
tables (§6), and what makes that safe is §7: our table is consulted first, so a
name that we produced is never requested from the other one.

**Do not `chDir`.** `REPL.ML:353-395` changes the working directory of the whole
process under a lock that covers only other loaders. It has forced defensive
absolutisation of client paths at `Server.ML:256-267` and `:384-388`, and one
site was missed (`Server.ML:640,643`).

**Do not discard per-command output on failure.** `IsaREPL.py:249-254` drops the
per-command results whenever the error slot is set, which is when they matter.

**Output capture must actually be switched on.** Isa-REPL's `init_printers`
(`REPL.ML:265`) has no callers, and `repl_server.sh:92` runs
`REPL.disable_output ()`, so its `output` field is always empty.

**The evaluator must not own the files.** Isa-REPL deletes and rewrites the
`.thy` (`REPL.ML:472-485`, `:521-528`). TAT is the compiler; two writers is one
too many.

## 5. Open

Where the `AoA` proof method lives — OPEN_QUESTIONS §5. §2 holds only if its
theory is in the base heap.

## 6. Loading a library theory that is not in the base heap

Through `Thy_Info.use_theories`, behind one wrapper that is the only entry
point (MODULE_STRUCTURE §2.3).

```ml
(*Thy_Info.use_theories ends with Execution.reset () (thy_info.ML:284), which
  empties the process-global execution table and turns the failures it finds
  there into the exception of the call that produced them.  When a theory fails
  under more than one thread with parallel proofs, the exception escapes earlier
  -- at :275, out of the uncaptured "present ()" in present_theory (:247) -- so
  that reset never runs.  The residue then stays in the table until the next
  call resets, which therefore raises with the previous call's error, after
  committing its own theories.
  Running the reset here makes a failing load leave exactly the state a
  successful load leaves, so every exception describes the call that raised it.
  It also recovers errors that the callee dropped: on a batch where two theories
  fail, the raw call reports one and strands the other.*)
fun load options qualifier imports =
  let
    val result = Exn.result (Thy_Info.use_theories options qualifier) imports;
    val residue = map Exn.Exn (maps Task_Queue.group_status (Execution.reset ()));
  in hd (Par_Exn.release_all (result :: residue)) end;
```

Three conditions, all required together:

- **`parallel_proofs` pinned to 1**, and checked at startup. At 3 — which
  `init_options_interactive` sets (`Pure/System/isabelle_process.ML:212`) — a
  theory whose structured proof fails commits successfully and the error
  surfaces later, breaking the correspondence between committing and succeeding.
- **One theory per call.** In a mixed batch the successful siblings of a failing
  theory are not committed, because the escape also skips the commit.
- **One lock around every call.** `Thy_Info` has no internal mutual exclusion;
  two concurrent calls over overlapping sets each produce their own `theory`
  value for a shared name.

Pass a path or a session-qualified name, not a bare name.

Two hazards remain, both avoided by not doing something rather than by shape:

- Requesting a theory already loaded from source, whose file has since changed,
  evicts it **and every successor** from `Thy_Info` (`thy_info.ML:371`, `:185-193`).
  Our table is consulted first, so we never re-request. The eviction announces
  itself on the output channel if it ever happens.
- Library theories live in `Thy_Info`'s table and forest theories in ours. Two
  tables are safe only under §7.

The defect is a missing capture at `Pure/Thy/thy_info.ML:247`: `present ()`
should be inside the `Exn.capture_body` that follows it. A fix there would
turn the drain above into a no-op.

## 7. One name-resolution rule

Isabelle compares theory identities by **short name** — the part after the last
dot (`Pure/context.ML:380-383`). Two theories sharing a short name and differing
in identity raise `Duplicate theory name` from the first theory that imports
either, one level downstream of the mistake.

Importing in one direction only does not prevent it. It was measured to arise
from loading one file under two names, from a forest theory taking a short name
the heap already uses, from two concurrent loads, and from staleness eviction.

So: every import, forest or library, resolves through one
`Resources.import_name` call, with the importing tree's `Session` `name` as
the qualifier; the qualified name it returns (`#theory_name`,
such as `HOL-Library.Multiset`) is the only key for the theory table (§3); no
file is ever loaded under two name forms; and a forest theory whose short name
is already taken is rejected when it is created, not when something imports
it.
