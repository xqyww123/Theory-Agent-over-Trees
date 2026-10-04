# TAT's evaluator

Paths are relative to `contrib/Isabelle2025-2/src/` unless prefixed; Isa-REPL
paths are relative to `contrib/Isa-REPL/library/`, except `IsaREPL.py`
(`contrib/Isa-REPL/IsaREPL/`) and `repl_server.sh` (`contrib/Isa-REPL/`).

TAT drives Isabelle itself, command by command. Isa-REPL (`contrib/Isa-REPL`)
has done this for years and is the reference: its shape is evidence, and §4
lists the hazards its review exposed.

## 1. The mechanism

Measured on a stock Isabelle2025-2, using only functions in the public
signatures of unpatched files.

Every `Toplevel.state` lives in a state slot (§1.1), and a node's evaluator is
handed the slot it starts from and the slot it writes (ARCHITECTURE §3.1). No
file is read, and every operation builds its transition in ML and applies
it through `Toplevel.command_errors true`, threading the state from the
input slot to the resulting slot.

For the `Theory` root node's header:

- read its text with `Thy_Header.read` — the one text parsed at run time
- resolve each import to a `theory` value (§2)
- do not pre-create the theory: build the transition the `theory` span
  would parse to, `Toplevel.make Thy_Header.theoryN pos |>
  Toplevel.init_theory`, its `unit -> theory` performing
  `Resources.begin_theory master_dir header parents`, and run it from
  `Toplevel.make_state NONE`

For the root node's `end`: an ML-built `Toplevel.exit` transition, then
`Toplevel.end_theory`, which yields the `theory` value that goes into the
theory table (§3). A `Theorem` builds one transition from its statement's
structure (THEOREM.md §6). The span path — split a node's text with
`Outer_Syntax.parse_spans` and run each span — is the retiring
`run_commands`, not to be used (MODULE_STRUCTURE §2.4, §6 below).

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

Each conversation has its own state slot table, empty when the conversation
begins and gone when it ends — with the Isabelle process, or emptied by
`TAT.reset` when a fresh conversation begins on the same process
(ARCHITECTURE §9). Nothing outlives the conversation.

A node class's asynchronous work can reach this table while evaluation runs
(ARCHITECTURE §9), so it is locked: a pure table under one
`Synchronized.var`, every compound operation one atomic change over it
(`contrib/Isabelle_RPC/Tools/RPC.ML`'s global callback registry is the
mutable-hash-table variant of the same shape).

## 2. One prover, and what resolution becomes

The prover runs on one base heap (ARCHITECTURE §8). The forest's `Session`s are Isabelle
sessions under construction: every tree is authored, none is in a heap, and a
tree's qualified name is its `Session`'s `name` joined to its own (§7). When
the forest is finished they are ordinary Isabelle sessions someone else builds
(ARCHITECTURE §4).

Import resolution, in order:

```
resolve name =
    our own table            (* trees this conversation evaluated to their end *)
  | Thy_Info.lookup_theory   (* the base heap *)
  | load from source (§6)    (* a theory whose file the Isabelle session layout knows *)
```

One producer means one slot per name, so two distinct `theory` values with one
name — which raise `Duplicate theory name` (`Pure/context.ML:383`) or `Cannot
join theories` (`:521`) — cannot be constructed. The invariant holds by shape.

Everything the forest imports from outside itself is expected to be in the base
heap. An import that is not there is loaded from source rather than refused, so
that an agent which discovers a dependency mid-work is not stopped to wait for a
heap rebuild — from the file the Isabelle session layout knows under the
name's session (`Resources.find_theory_file`), never by path, never under
a qualified name whose short name the layout declares global (§7), and
never from under the working directory, which the launcher keeps out of
the layout (MODULE_STRUCTURE §5). An import found nowhere — no forest tree, no
base-heap theory, no known file — fails the header with RENDER_BASELINES
§3's sentence, under the name Isabelle resolved it to.

## 3. The theory table

A table from qualified theory name (§7) to `theory` value, written by the
`Theory` root node's ending command — its `end` (§1). A second write
overwrites: TAT re-evaluates on every edit.

The table keeps no import dependencies: invalidation is the Python side's,
which marks every tree that imports a changed tree `not_evaluated`
(ARCHITECTURE §3.4) and never requests a theory whose tree is not evaluated
to its end (ARCHITECTURE §3.5), so an entry that is merely out of date is
never read and is overwritten when the tree is evaluated again. An entry
whose qualified name has vanished — its tree deleted, renamed, or moved
into another `Session`, or its `Session` renamed — is deleted in the same
operation, through
`TAT.theory_delete` (`Theories.delete`), so that `resolve` (§2) can never
hand an importer the theory of a tree that no longer exists
(ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §6). Like the state slots
(§1.1), the table is locked, since a node class's asynchronous work can
reach it while evaluation runs.

## 4. What to avoid, and why

Each of these is a defect found in Isa-REPL by review, and a hazard of this
design.

**One flag must not gate several effects.** `register_theory'`
(`REPL.ML:521`, `:679-686`) gates the theory-table insertion, the `Thy_Info`
registration and the writing of `.thy` files together. Nobody can have one
without the others.

**Per-connection state must not live in `Thread_Data`.** `Future.fork`
propagates `Position.thread_data` and the generic context, nothing else
(`Pure/Concurrent/future.ML:452`). Isa-REPL keeps its session id and its theory
table in `Thread_Data` (`REPL.ML:243`, `:315`), so any message produced on a
forked worker cannot find its session and falls through to the global output
function instead of reaching its client (`REPL.ML:268-273`). Route
by `Position.id` as PIDE does, or pass the identity explicitly.

**Do not let one name have two producers.** Isa-REPL evaluates some theories
itself into its own table and loads others through `Thy_Info.use_theories` into
`Thy_Info`'s graph, with nothing keeping a name out of both. TAT also has two
tables (§6), and what makes that safe is §2's resolution order: our table is
consulted first, so a name that we produced is never requested from the
other one.

**Do not `chDir`.** `REPL.ML:353-395` changes the working directory of the whole
process under a lock that covers only other loaders. It has forced defensive
absolutisation of client paths at `Server.ML:256-268` and `:384-389`, and one
site was missed (`Server.ML:640,643`).

**Do not discard per-command output on failure.** `IsaREPL.py:249-254` drops the
per-command results whenever the error slot is set, which is when they matter.

**Output capture must actually be switched on.** Isa-REPL's `init_printers`
(`REPL.ML:265`) has no callers, and the `isabelle REPL` tool's `Isa_REPL.startup`
handler runs `REPL.disable_output ()`, so its `output` field is always empty.

**The evaluator must not own the files.** Isa-REPL deletes and rewrites the
`.thy` (`REPL.ML:472-485`, `:521-528`). TAT is the compiler; two writers is one
too many.

## 5. The `aoa` proof method

The `aoa` proof method is defined in `Minilang_AoA.Minilang_AoA`. §2
holds only if that theory is in the base heap, so a working directory
that uses the plugin `Isabelle_Std` is launched on the base heap
`Minilang_AoA` (node_classes/THEOREM.md).

## 6. Loading a library theory that is not in the base heap

Through `Thy_Info.use_theories`, behind one wrapper that is the only entry
point (MODULE_STRUCTURE §2.3); the boot's load of TAT's own theory, before
the wrapper exists, is the one call outside it (MODULE_STRUCTURE §5).

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
  fail, the raw call reports one and strands the other.
  Exn.capture_body rather than Exn.result: result re-raises an interrupt on
  the spot, so a cancelled load would skip the reset below and leave exactly
  the residue this wrapper exists to drain.  The drain, run uninterruptibly
  once the call has returned, therefore always completes; a cancellation is
  then re-raised explicitly -- Par_Exn treats an interrupt as a neutral
  element (par_exn.ML) and release_all would swallow it whenever the residue
  holds real errors -- and residue errors are released only when the call
  was not cancelled.*)
fun load import =
  Synchronized.change lock (fn () =>
    let
      val _ = check_parallel_proofs ()
      val result =
        Exn.capture_body (fn () => Thy_Info.use_theories (Options.default ()) "" [import])
      val residue =
        Thread_Attributes.uninterruptible (fn _ => fn () =>
          map Exn.Exn (maps Task_Queue.group_status (Execution.reset ()))) ()
      val _ =
        (case Exn.get_exn result of
          SOME exn => if Exn.is_interrupt_proper exn then Exn.reraise exn else ()
        | NONE => ())
      val _ = Par_Exn.release_all (result :: residue)
    in () end)
```

`lock` is the one loader lock (below), and `check_parallel_proofs` asserts
the first condition below (`ML/TAT_Framework.ML`).

Four conditions, all required together:

- **`parallel_proofs` below 3**, refused by the launcher when the options
  give more, set from the option by the boot before its first load, and
  asserted by every load and at the conversation's start (MODULE_STRUCTURE
  §5, §2.3). Measured on Isabelle2025-2 with `Thy_Info.use_theories` on a theory
  whose proof fails, terminal or structured: at 0, 1 and 2 the call raises
  and the theory is not committed; at 3 — the value
  `init_options_interactive` sets (`Pure/System/isabelle_process.ML:212`) —
  the call raises too, but the theory is committed with its false theorem
  in it, and so is a theory importing it, so the correspondence between
  committing and succeeding breaks. At 1 and 2 a failing load also leaves
  one residual failure in the execution table, which makes the next call
  raise with the previous theory's error while committing its own; the
  drain in `load` above removes it. The setting governs the theories this
  loader loads, whose bodies run on Future workers; the conversation's own
  thread is no worker (MODULE_STRUCTURE §2.6), so `Future.proofs_enabled`
  is false there and no goal of a node's commands forks whatever the option
  says. A job's work does run on a worker (CONSTRUCT_INTERACTION §3.3),
  and forks none either: it applies no Toplevel transition and calls no
  `Goal.prove_future` or `Goal.prove_sorry`.
- **One theory per call.** In a mixed batch the successful siblings of a failing
  theory are not committed, because the escape also skips the commit.
- **One lock around every call.** `Thy_Info` has no internal mutual exclusion;
  two concurrent calls over overlapping sets each produce their own `theory`
  value for a shared name.
- **No command may be running anywhere in the process while a load runs.**
  The call ends in `Execution.reset ()`, a wholesale wipe of the
  process-global execution table each running span is registered in
  (MODULE_STRUCTURE §2.4): a concurrent span would lose its entry, stranding
  its forks and making a later `Execution.fork` under its id fail. Nothing
  of TAT's collides with it: the conversation runs on a thread inside no
  theory, started only after the boot has finished loading TAT's theory
  and `TAT.start` has loaded the plugins' (MODULE_STRUCTURE §2.6, §5), so
  those loads never overlap it; its dispatch is one synchronous loop;
  `begin_theory` resolves every import before it runs anything; and TAT
  registers nothing in the table itself — `run_commands`, which did, is
  not to be used (MODULE_STRUCTURE §2.4). The jobs, which do run beside a
  load (CONSTRUCT_INTERACTION §3.3), never reach the table either: a job's
  work applies no Toplevel transition and calls nothing that forks a
  proof — `Goal.prove_future`, `Goal.prove_sorry` — and the tactics a
  replay runs prove through `Goal.prove`, which never forks;
  `Proof_Check`'s work is a goal built in ML and `eval_prf_str`
  (THEOREM.md §7). So no lock orders the jobs against a load.

`load` is handed the one name the Isabelle session layout gives the
file: `<session>.<short name>`, or the short name alone when the layout
declares it global — never a path, never a bare non-global name, and
never a qualified name whose short name is global (§7) — under the empty
qualifier, so that `use_theories`'s own resolution leaves it unchanged and
the theory loads under exactly that name.

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

Isabelle compares theory identities by **short name** — the part after the
last dot; Isabelle's own sources call it the base name (`theory_base_name`,
`Pure/context.ML:380-383`). Two theories sharing a short name and differing
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
it. So is a name the Isabelle session layout declares global (`Main`,
`FOL`, …): `Resources.theory_name` leaves such a name unqualified, and a
tree so named would be keyed without its `Session` (`ReservedTheoryName`,
answered by `Resources.global_theory`); and so is a name Isabelle
reserves as a file or theory name — `Path.is_reserved`,
`Sessions.illegal_theory`, asked through the Scala function
`TAT.reserved_name` (COMPILATION.md §2) — which the same
`ReservedTheoryName` refuses. The same names are refused as
the short name of a qualified import: Isabelle answers `imports HOL.Main`
by loading `Main.thy` a second time as a theory named `HOL.Main`, and a
later theory importing both fails with `Duplicate theory name`; `fetch`
refuses the name instead, with RENDER_BASELINES §3's sentence, so the
error stands at the import that wrote it.
