# TAT's evaluator

Working plan, not part of the published document set.

TAT drives Isabelle itself, command by command, rather than through a document
model. Isa-REPL (`contrib/Isa-REPL`) is the reference: it has done this for
years, so its shape is evidence and its defects are a map of the hazards. TAT
does not use it — it cannot be shipped, and its own design choices are the
subject of §5.

## 1. The mechanism

Measured on a stock Isabelle2025-2, using only functions in the public
signatures of unpatched files.

Hold an explicit `Toplevel.state`. For each theory:

- read the header with `Thy_Header.read`
- resolve each import to a `theory` value (§2)
- merge the parents' keyword tables (`Thy_Header.get_keywords`,
  `Keyword.merge_keywords`) before tokenising, or a parent-defined command
  tokenises as garbage
- split the whole file text, header included, with `Outer_Syntax.parse_spans`
- run each span through `Toplevel.command_errors true`, threading the state.
  Do not pre-create the theory: start from `Toplevel.make_state NONE` and let
  the first span — the `theory … begin` command — call an `init` that performs
  `Resources.begin_theory master_dir header parents`
- at the end, `Toplevel.end_theory` yields the `theory` value

`Toplevel.command_errors` returns `(errors, state option)`; check both, since a
failing command can return no state. It is the error-recovering runner — batch
loading uses `Toplevel.command_exception`, which re-raises and therefore stops
at the first failure.

Its first argument is Isabelle's interactive flag and must be `true`. `sorry` is
`Method.cheating`, which raises `Cheating requires quick_and_dirty mode!` unless
that flag is set or `quick_and_dirty` is on (`Pure/Isar/method.ML:155-158`).
Stock Isabelle passes `true` (`Pure/PIDE/command.ML:234`), on the path both
interactive and batch runs take. Isa-REPL passes `false`
(`contrib/Isa-REPL/library/REPL.ML:662`); that part of its shape must not be
copied, because TAT emits `sorry` by design (ARCHITECTURE §2.2).

`Resources.begin_theory` does not touch the filesystem. It stores `master_dir`
as data, which matters only for body commands like `ML_file` that resolve
against it.

`Runtime.error` is `((serial * string) * string option)`, not an `exn`.

### 1.1 The state slot table

The evaluator holds `Toplevel.state` values in one table keyed by a name, and
the Python side holds only names (ARCHITECTURE §3.1). Running a node is
"from the state under this name, run these commands, put the result under that
name". Re-evaluating a node writes the same name again, so the table grows only
when nodes are created and shrinks only when they are deleted.

Concurrent chains of work share this table (ARCHITECTURE §9), so it is
guarded. `contrib/Isabelle_RPC/Tools/RPC.ML:429-437` is the pattern in use in
this project family: a hash table plus a `Synchronized.var` held across every
read and write.

## 2. One session, and what resolution becomes

TAT launches a prover on one base session heap. The forest is not a session; it
sits on top of one. Every tree is authored and none is in a heap. When the
forest is finished it becomes an ordinary session someone else builds.

Import resolution has two levels and no third:

```
resolve name =
    our own table          (* trees this session evaluated *)
  | Thy_Info.lookup_theory (* the base heap *)
  | error
```

One producer means one slot per name, so two distinct `theory` values with one
name — which raise `Duplicate theory name` (`Pure/context.ML:383`) or `Cannot
join theories` (`:521`) — cannot be constructed. The invariant holds by shape.

The cost is a build-time requirement: everything the forest imports from outside
itself is expected to be in the base heap.

An import that is not there is loaded from source anyway rather than refused, so
that an agent which discovers a dependency mid-work is not stopped to wait for a
heap rebuild. The loader reports how many theories that cost, since one import
can pull a large closure, and the report is what tells a user to widen the base
session. Such an import is loaded through `Thy_Info.use_theories`, behind the
wrapper of §7.

## 3. The theory table is a graph

Not a `Symtab`. A `String_Graph` keyed by theory name, carrying the theory and
its parent edges, so that re-evaluating a theory can delete everything derived
from it. `Pure/Thy/thy_info.ML:188-194` is the operation, in three lines:

```sml
val succs = String_Graph.all_succs thys [name];
in fold String_Graph.del_node succs thys
```

Re-evaluation replaces and invalidates. It does not reject: TAT recompiles a
tree on every edit, so rejecting a second definition of a name would make the
tool unusable after the first edit of anything.

## 4. What to take from Isa-REPL

- Per-command `Toplevel.command_errors`, which yields per-command `errors` and
  `range` without a span table. This is why the command-to-node mapping is given
  rather than reconstructed.
- The collector hook (`contrib/Isa-REPL/library/REPL.ML:191-197`): arbitrary ML
  run after each command, returning structured data. Extracting the fact names a
  command generated is a collector, not a protocol change.
- Snapshot and rollback of `Toplevel.state` by name, which is a pointer swap.

## 5. What to avoid, and why

Each of these is a defect found in Isa-REPL by review. They are listed because
they are the hazards of this design, not because Isa-REPL is careless.

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
tables (§7), and what makes that safe is §8: our table is consulted first, so a
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

## 6. Open

- **Where the `AoA` proof method lives.** If it is defined in a theory, that
  theory must be in the base heap for §2 to hold.
- **Whether the base heap must be rebuilt when the forest needs a new import**,
  and whether that is acceptable for the intended workflow.

## 7. Loading a library theory that is not in the base heap

Through `Thy_Info.use_theories`, behind one wrapper that is the only entry
point.

```ml
structure Theory_Loader =
struct

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

end;
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

Pass a path or a session-qualified name, not a bare name. Isa-REPL's
process-global `OS.FileSys.chDir` (`contrib/Isa-REPL/library/REPL.ML:376`) is
needed only because it passes bare names.

Two hazards remain, both avoided by not doing something rather than by shape:

- Requesting a theory already loaded from source, whose file has since changed,
  evicts it **and every successor** from `Thy_Info` (`thy_info.ML:371`, `:185-193`).
  Our table is consulted first, so we never re-request. The eviction announces
  itself on the output channel if it ever happens.
- Library theories live in `Thy_Info`'s table and forest theories in ours. Two
  tables are safe only under §8.

The defect is a missing capture at `Pure/Thy/thy_info.ML:247`: `present ()`
should be inside the `Exn.capture_body` that follows it. Worth reporting
upstream; a fix there turns the drain above into a no-op.

## 8. One name-resolution rule

Isabelle compares theory identities by **base name** — the part after the last
dot (`Pure/context.ML:381-384`). Two theories sharing a base name and differing
in identity raise `Duplicate theory name` from the first theory that imports
either, one level downstream of the mistake.

This is not prevented by the direction of dependency. It was measured to arise
from loading one file under two names, from a forest theory taking a base name
the heap already uses, from two concurrent loads, and from staleness eviction.

So: every import, forest or library, resolves through one
`Resources.import_name` call; `#theory_name` is the only key for the table; no
file is ever loaded under two name forms; and a forest theory whose base name is
already taken is rejected when it is created, not when something imports it.
