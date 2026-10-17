# Compilation

Status: design, tenth revision, revised 2026-10-03 after its sixth
review and the owner's rulings on it (ai-artifacts/COMPILATION_REVIEW.md
§13), and 2026-10-12 with the node-class rounds (§3's text rules and
what `emit` may read, §4's `keywords`, §5's hook;
ai-artifacts/review/NODE_CLASS_RULINGS.md). A sentence ending in *(decided)* carries the owner's ruling, of
2026-09-30, 2026-10-01, 2026-10-02 or 2026-10-03;
every other sentence is the author's; §7 holds the approved wording and
names. The document was approved on 2026-10-02. It is implemented
(ai-artifacts/COMPILATION_IMPLEMENTATION_PLAN.md) but for what the
construction jobs bring (ai-artifacts/CONSTRUCT_IMPLEMENTATION_PLAN.md):
§4's stored check, and the plugin's compile hook (§5).

Compile is turning the forest into `.thy` files and a ROOT on disk; emit
is a node writing its own Isar text (ARCHITECTURE §1). TAT is the compiler
and owns the files. Isabelle never reads them during a conversation —
every change reaches Isabelle by evaluation — and they exist for whoever
builds the Isabelle sessions afterwards; the one reading Isabelle makes
of them under TAT is the compile's own check of what it wrote (§2).
Emission renders evaluation's results; it decides nothing and runs
nothing.

## 1. When: one entry, `isabelle TAT_compile`

The forest is compiled by one explicit command, `isabelle TAT_compile
WORKING_DIRECTORY`, a step of the host's pipeline that runs after the
conversation: not a tool the agent calls, not the conversation's ending,
not any edit *(decided)*. Nothing else writes a `.thy` or the ROOT. It is
a sibling Isabelle tool of `TAT_new` and `TAT_mcp` (§5) *(decided)*.

The command evaluates nothing *(decided)*. It runs on a directory no
conversation holds: the working directory's lock refuses it otherwise,
as it refuses a second conversation (MODULE_STRUCTURE §4.6). It starts
an Isabelle process only to load the plugins,
whose Python packages are named by their theories' registrations
(MODULE_STRUCTURE §2.6), loads the forest from the database, writes
what the stored statuses allow (§4), and exits. Its ML command carries
the framework's `TAT.log_directory` and no class's callback, so nothing
it does can run anything in Isabelle *(decided)*. A large forest is compiled in the
time it takes to write it.

A compile is not a conversation: its call into Python returns, it serves
no agent, and it runs no evaluation. What the two share is what the
working directory's lock claims — the directory, for one conversation or
one compile at a time — and what a conversation's startup builds
before its server: the lock, the log, the ending object, the
`Conversation`, the store, the plugins and the forest (MODULE_STRUCTURE
§4.6; the glossary's amendments, §6).

Three layers, each an entry to the one below (§5): the Python function
`compile(forest, hooks)`; the RPC procedure `compile_TAT`, which the ML
side calls as it calls `launch_TAT`; and the Isabelle tool, which starts
the process, hands the result back through `TAT.finished`, and has
Isabelle read what was written.

## 2. What is written

Under the working directory (FIRST_END_TO_END §1): a ROOT at its top,
holding one entry per `Session`; and one folder per `Session`, named
after it, holding one `<short name>.thy` per tree written. A tree's file
path, `<Session name>/<short name>.thy`, is one method of `Theory` (§7
for its name), which also gives the `master_dir` its header is evaluated
under (model.py, `Theory._eval_beginning_opr`), so that AoA's store, the
compile and the compile hooks name the same file. The forest stores no
path; it moves machines by being compiled on another directory.

**Which trees.** A tree is written when every node in it agrees to emit —
`can_emit()`, §3 — and every forest tree it imports is written
*(decided)*. The first half is ARCHITECTURE §4's rule: a `.thy` with a
hole is not a theory. The second half keeps a missing file out of the
session: `theory T imports U` with no `U.thy` is refused by Isabelle
whatever options the build is given, and the case arises — `U` holds a
nesting node whose beginning failed, so its children never ran while
`U`'s `end` did, and `T` evaluated against `U`'s theory value. A tree
imported by an unwritten one is written all the same *(decided)*.

The decision is a memoised recursion over each tree's resolved imports
(`Forest._resolved_imports`), not a pass in tree order: after a `move`
that reorders trees, an import may stand after its importer
(ARCHITECTURE §3.3), and the recursion reads the import graph as it is.
A tree reached again while its own decision is being made lies on an
import cycle, which no build accepts, and is not written. The reasons
are computed once the set of written trees is fixed.

**The reason a tree is not written** is the first of these that holds.
For 2 and 4, a node whose `can_emit` is false is placed at its first
operation whose stored status is not a `Ready`, or at its last operation
when all are; nodes are scanned in the order the walk runs operations —
a nesting node whose beginning did not pass is met at its beginning,
before its children, and otherwise at its ending, after them.

1. A forest tree it imports, placed before it, is not written: the
   first such, in the order of its `imports` — ARCHITECTURE §3.3's own
   rule, which reports an import's stop before the importer's.
2. A node of it whose `can_emit` is false and which is placed at a
   `CannotEvaluate` operation, or whose operations are all `Ready`: the
   first such.
3. The order constraint (ARCHITECTURE §3.3): the tree imports a forest
   tree placed after it, or itself. The tree named is the first such
   import that is not written, else the first such import; the position
   test is one `Forest` helper that `_order_violation`'s sentence and
   the compile share.
4. A node of it whose `can_emit` is false: the first such, placed at a
   `NotEvaluated` operation.

Only nodes whose `can_emit` is false are ever named, so a class that
widens `can_emit` is never blamed for a status it accepts. A stored
failure comes before the order constraint, so a failure recorded before
a `move` keeps its line and messages; and a chain of lines of kind 1
always moves to a tree placed earlier, so it ends at a line that names a
cause — on an import cycle, at the member that breaks the constraint.

**The `.thy`.** The tree's `Theory` root emits the header, its nodes
their text in tree order, the root the `end` (§3). Every emission
method writes whole lines, each ending in a newline *(decided)*. The
framework writes one empty line between consecutive children of a
nesting node. The whole file is rendered in memory, converted once to
Isabelle's `\<name>` form with `Isabelle_RPC_Host.unicode.ascii_of_unicode`
— an idempotent conversion, so a class may write either spelling — and
only then written (§5). A raw `‹` reaches no file: Isabelle/ML reads it
as a symbol, not as a cartouche delimiter.

A written file may hold `sorry`: a node whose proof is not
constructed, not checked, or failed its check writes `sorry`
(`proof_text()`, node_classes/COMMON.md §3). Building such a file needs Isabelle's `quick_and_dirty` option,
which is the builder's business, not TAT's: compile adds no option and
reports a tree with `sorry` as written *(decided)*.

**The ROOT.** One entry per `Session`, in the forest's order, in
Isabelle's own grammar (`Sessions.Parsers.session_entry`,
`contrib/Isabelle2025-2/src/Pure/Build/sessions.scala`), the clauses in
the order the grammar fixes; the example is the forest of the report
below, where `Sorting`, `Merge` and `Late` are the written trees:

```
session "Sorting" in "Sorting" = "HOL" +
  description ‹Sorting, verified.›
  options ["quick_and_dirty" = "true", "document" = "false"]
  sessions
    "HOL-Library"
  theories
    "Sorting"
    "Merge"
    "Late"
```

- `name`, the `in` path (the folder, which is the name) and
  `parent_session` are transcribed (SESSION_AND_THEORY §1). Every name
  the ROOT carries — session, path, parent, the `sessions` items, the
  `theories` items, every option's name — is written in double quotes: a
  name with a hyphen (`HOL-Library`) is not one token of the ROOT's
  syntax unquoted.
- `description`, when not empty, is one cartouche, through the
  framework's `cartouche` (§3). Left out when empty.
- `options`, when not empty, in the ROOT's own spelling, every value
  quoted (SESSION_AND_THEORY §1). Left out when empty.
- `sessions` lists the session of every theory the session's written
  trees import that is neither the session itself nor its
  `parent_session`, sorted, each once — Isabelle refuses an import from
  a session that is neither an ancestor nor listed here (`Bad import of
  theory …: need to include sessions … in ROOT`, sessions.scala). Which
  session an import belongs to is recorded on the tree when its header
  runs: `Theory`'s recorded field `import_sessions`, the answer
  `TAT.Theory.begin` gives beside its messages, `Resources.theory_qualifier`
  of each import's resolved long name (`Pure/Build/resources.ML`), which
  covers a dotted item, a bare one, and a bare name of a global theory
  such as `HOLCF`. The exclusion of the session and its parent is made at
  compile time, since an amend of `parent_session` invalidates no tree.
  A harmless ancestor may appear, `"HOL"` under a parent `HOL-Library`
  when a tree imports `Main`. Left out when there is none. The ROOT is
  thus a function of the stored forest alone.
- `theories` lists the session's written trees by short name, in the
  session's order; a tree not written is not listed *(decided)*. The
  session builds without it. Left out when no tree of the session is
  written; the entry stays, and so does its folder, which compile makes.

The empty forest compiles to a ROOT with no entry and no folder.

**Names Isabelle refuses, caught at creation.** A ROOT Isabelle refuses
as a whole builds nothing, and the forest's name grammars admit names
Isabelle's reading of a ROOT does not: the names `Path.is_reserved`
refuses as file names — `CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`,
`LPT1`–`LPT9`, in any spelling — and those `Sessions.illegal_theory`
and `Sessions.illegal_session` reserve, `ROOT`, `ROOTS`, `bib`,
`Draft`. All evaluate without complaint, so creation asks Isabelle's own
predicates, not a copy of its lists *(decided)*. The asking is one
Isabelle/Scala function in `lib/tat.jar`, `TAT.reserved_name`, a
`Scala.Fun_String` registered through a `Scala.Functions` service in
`etc/build.props` beside `TAT_Tools`, called from ML as
`Scala.function1` — the launcher's process answers such calls through
its protocol loop (MODULE_STRUCTURE §5). `Theory.gen` asks it through
`TAT.check_new_theory_short_name`, whose answer `reserved` and its
sentence are unchanged (RENDER_BASELINES §2); `Session.gen` asks it
through `TAT.check_session` (below) and answers with a sentence of the
same shape *(decided)*. `Session.gen` also refuses the name `ROOT` in any
spelling, TAT's own rule, since the session's folder would be the ROOT
file's path *(decided)*. And since Isabelle refuses two theory files
whose names differ only in case (`Path.check_case_insensitive`,
sessions.scala), `Theory`'s short-name namespace compares names without
regard to case, the existing `DuplicateTheoryShortName` naming the
holder *(decided)*.

**What else creation checks, and what the final reading catches.** A
`Session` named like a session the Isabelle session layout knows
(`Duplicate session`; the AFP declares about 1100, `Graph_Theory` and
`Matrix` among them), an option Isabelle does not know or a value of
the wrong type, a cycle through `parent_session` or through the derived
`sessions` clause. Two layers:

- `Session.gen` asks Isabelle once, through the callback
  `TAT.check_session(name, parent_session, options)` *(decided)*. It
  answers the first defect as a tagged value in
  `TAT.check_new_theory_short_name`'s shape: `["ok"]`, `["name_reserved"]` — Isabelle's predicates above —
  `["name_known"]` — the session's own name is one the layout knows —
  `["option", i, <Isabelle's message>]` — option `i` refused as Isabelle
  reads a ROOT, by the Scala function `TAT.check_options` (§5) — or
  `["parent_unknown"]`; `gen` renders each (§7 for
  the sentences). A `parent_session` naming a
  `Session` the call keeps or adds before this one is settled on the
  Python side first (SESSION_AND_THEORY §1) and passed as not to be
  asked. Its ML half reuses `Loader.is_known_session`.
- `TAT_compile`, after writing, has Isabelle read what it wrote:
  `Sessions.deps(structure.selection(<the working directory's sessions>))
  .check_errors`, the steps `isabelle build` takes before building,
  which read the ROOT and the theory headers and evaluate nothing
  *(decided)*. On an error the tool prints Isabelle's message after the
  report and exits `2`. This catches what creation cannot see: a cycle a
  later edit made, a session layout that changed between the
  conversation and the compile.

**The directory after a compile.** Every `.thy` under the working
directory, at any depth, and the ROOT at its top are TAT's: compile
removes them all, writes the forest's `.thy` files, runs the compile
hooks (§5), removes the folders left empty, then writes the ROOT
*(decided)*. Compile makes the folder of
every `Session` before it writes, and removes only the empty folders it
did not make, so that every ROOT entry's directory exists *(decided)*.
Nothing the disk step does — the `.thy` files, the ROOT and the folders
— enters a folder whose name begins with a dot or follows a symbolic
link, so a `.git`, a client's dot-folder, and anything a link points at
are out of reach *(decided)*; the lock file and the log under `.tat/`,
which a compile shares with a conversation (§1), it opens as a
conversation does. Every removal, the hooks' included, goes through one
path listing (§5) that keeps this rule, and every file a compile writes
is created afresh at a path the forest gives, under a `Session` folder
that is a directory. A `Session`'s folder that is a symbolic link is
refused before anything is removed, and the compile did not complete
*(decided)*. The same holds for anything else at its path that is not a
directory, a file for instance: the folder is a directory or absent.
And a folder at a path the compile will create — a tree's file, the
ROOT, the ROOT's temporary sibling (§5) — is refused the same way,
before anything is removed *(decided)*: the `.thy` removal takes no
folder, and the file could not be created afresh.
The consequence to know: a
`.thy` anyone else puts under the working directory — the agent's client
runs there (CLIENT_HOOKS.md) — is gone at the next compile. Files of
other kinds a compile never touches; a plugin's compile hook handles
its own, AoA's `<Theory>.proof-store` beside the `.thy` being the first
case (§5): that store appears during the conversation, written by a
`Proof_Obligation`'s construction through AoA (node_classes/COMMON.md §3), and a compile
leaves it where it is.

**The report and the exit code.** The command prints one line per tree,
in tree order, with the messages of the operation that refused, then the
ROOT's line, then one line per file or folder removed and not written
again; and exits `0` when every tree was written, `1` when the compile
completed and some tree was not, `2` when it did not complete
*(decided)*. Not completing is: refused before writing (the lock held, a
database of another schema version, a plugin that did not load, a
`Session` folder's path holding something other than a directory), the
boot failing to load TAT's theory, the base heap failing to build, a
usage error, a bug midway, the Isabelle process gone, or Isabelle
refusing what was written. `130` is Isabelle's own, for an interrupt
before the Isabelle process started and outside the base heap's build;
an interrupt during that build stops it and the tool exits `2` with
Isabelle's `Failed to build Isabelle/<BASE>`, and one during the check
of an existing heap is ignored (build.scala, `Build.build_logic`). A
pipeline builds on `0` and `1`, and on `2` the directory may be the
previous compile's or a mixture. The lines (§7):

```
Sorting/Sorting.thy written
Sorting/Merge.thy written
Sorting/Sum.thy not written: lemma_sum_comm failed
  Type unification failed: Clash of types "nat" and "bool"
Sorting/Perm.thy not written: lemma_perm_length is not evaluated
Sorting/Uses.thy not written: it imports Sorting.Sum, which is not written
Sorting/Odd.thy not written: section_Old does not emit
Sorting/Early.thy not written: it imports Sorting.Late, which is placed after it
Sorting/Late.thy written
ROOT written
removed Old/Stale.thy
removed Old/
```

`failed` and `is not evaluated` are read off the node's stored statuses
(§4), the messages under `failed` are the status's own (§4), and `does
not emit` is a class's own refusal (§3) on a node whose operations are
`Ready`; the line of kind 3 says `it imports itself` when the tree named
is the line's own. The path is the file's, relative to the working
directory; the node's name is its id (MCP_SPECIFICATION §2.1); the
tree's qualified name is `<session>.<short name>`.

## 3. What a node writes: the contract

Two questions the framework asks a node, on the Python side of the node
class contract (ARCHITECTURE §6, MODULE_STRUCTURE §4.1); both replace
ARCHITECTURE §4's `emit_isar` *(decided)*.

```python
class Node:
    def can_emit(self) -> bool:
        """Whether the node writes its text.  Default: every entry of
        `last_evaluation_statuses()` is a `Ready` (§4); a class narrows it
        with `super().can_emit() and …`, or replaces it."""

    @abstractmethod
    def emit(self, indent: int, out: TextIO) -> int:
        """Write the node at `indent`, whole lines each ending in a newline;
        return the indent in effect after it."""
```

`can_emit` is one overridable method *(decided)*. The framework's default
reads the stored statuses, and a class that replaces it answers for its
own file. It is asked of every node of a tree before any of them writes;
`emit` is called only on the nodes of a tree every node of which said
yes, so a class's `emit` needs no guard. The `indent` passed in is a
proposal; Isabelle's own files write commands at column 0 at every
nesting depth, so today every class returns what it was given, and the
parameter is kept for a layout that may want otherwise *(decided)*.
Every emission method writes whole lines ending in a newline
*(decided)*. A class writes its lines through the framework's
`emit_lines(indent, out, text)` (model.py), which puts every line of
`text` at `indent` and ends each with a newline.

A `Leaf` implements `emit` itself. A `StdBlock`'s `emit` is the
framework's, and the class implements one method per operation of the
block — the words are the walk's, `beginning` and `ending`
(ARCHITECTURE §3.2) *(decided)*. The framework's:

```python
class StdBlock(NonLeaf_Node):
    @final
    def emit(self, indent, out):              # the framework's
        below = self.emit_beginning(indent, out)
        for i, child in enumerate(self.sub_nodes):
            if i: out.write("\n")             # one empty line between siblings
            below = child.emit(below, out)
        return self.emit_ending(indent, out)  # the block's own indent, not the last child's

    @abstractmethod
    def emit_beginning(self, indent: int, out: TextIO) -> int:
        """The beginning command at `indent`; returns the indent the children get."""

    def emit_ending(self, indent: int, out: TextIO) -> int:
        """The ending command at the block's own `indent`; returns the indent
        in effect after the block.  Default: no ending command, the indent
        unchanged."""
        return indent
```

`Theory` overrides both, the header and `end`; `Section` overrides
`emit_beginning` alone, as its evaluation has no ending command. The
loader (PLUGIN_SYSTEM §5) holds the contract in three rules: a `StdBlock`
class does not override `emit` — the children are the framework's to
place, and a class that forgot them would write a file silently missing
half its content; it overrides `_eval_ending_opr` exactly when it
overrides `emit_ending`, since both say whether the class has an ending
command, and one without the other leaves a theory open in the file; and
an override is a coroutine function exactly when the method it overrides
is — the framework's, or one of the plugin's own base classes — which
none of these is: an `async def can_emit` would answer with a coroutine
object, which is true. The methods a class never overrides
carry `typing.final` as well, so the type checker says it before the
loader does *(decided)*.

`Session` and the forest root are on neither path: a `Session` emits no
Isar, its output is the ROOT entry (§2) and the folder, produced by
`compile` from its fields.

**Text in a cartouche.** Isabelle text written into a file inside a
cartouche — a `text` command's, the ROOT's `description` — goes through
the framework's `cartouche` (model.py), which replaces `‹`, `›`,
`\<open>` and `\<close>` in it by `"`, so the cartouche closes where it
should and nothing is refused.

**Text in double quotes.** Isabelle text written into a file inside
double quotes — a term, a type, a sort, a mixfix symbol or template, a
quoted name — is written as Isabelle's outer-syntax string token, by
the rule of `Symbol_Pos.quote_string_qq`, Isabelle symbols left intact,
through one framework function, `string_token` (model.py); the ROOT's
quoted items (§2),
`print_name` (node_classes/SESSION_AND_THEORY.md §2) and every class's
emission go through it.

**What `emit` may read.** A compile runs on a forest loaded from the
database and never evaluated (§1), so `emit` and `can_emit` read only
what is stored, through the public read-only accessors `job()` already
is: authored fields; recorded fields the class stores; its `Theory`'s
stored `keywords`, through `print_name` (node_classes/SESSION_AND_THEORY.md
§2); `last_evaluation_statuses()`, a tuple, the messages of a status
included (§4); and the check's outcome through its accessor (§4), which
`Proof_Obligation`'s choice between `by aoa` and `sorry` reads
(node_classes/COMMON.md §3).
Reading an instant status there — `evaluation_statuses()`, `is_finished()`,
the default `mark` — is a class bug: on a loaded forest every instant
status is `not_evaluated`. The rule is kept by the store-mirror
invariant the test suites already run after every edit and walk
(`assert_store_mirrors`, `test/invariants.py`), moved into the package
— `isabelle_theory_agent/invariants.py` —
as a helper that takes the forest and the kind table and nothing
class-specific, which every class's suite calls on its own forests: it
reloads the forest from the store beside the one in memory and
requires, node by node, the same `last_evaluation_statuses()` in their
stored form — each status's kind and its messages' `unicode`, as
`_store_node` writes them — the same
stored check and the same `can_emit`, and the same result of compile's
first step as text — every file's text keyed by its path, the ROOT's
included, and the report as `report_lines` renders it, which names
nodes by id, its `removed` empty since the disk step alone fills it. A recorded field read by emission but not stored —
`import_sessions`, `keywords` (node_classes/SESSION_AND_THEORY.md §2) —
fails it at once.

## 4. The stored statuses, the messages, the stored check

Every operation of a node has, beside its `evaluation_status`, a second
field, `last_evaluation_status`, which is stored and holds the value
`evaluation_status` was last given *(decided)*. `evaluation_status` keeps its meaning —
`ready` says the operation ran and its resulting slot is current — and is
not stored, a loaded forest being `not_evaluated` throughout
(ARCHITECTURE §4.1).

**The attribute.** The stored values of a node's operations are one list
on `Node`, `_last_evaluation_statuses: list[EvaluationStatus]`, one entry
per own operation in `_own_statuses()`'s order *(decided)*. `Node`'s
constructor makes one `not_evaluated` entry per name in
`_operation_names()` — the operations' names in the same order, what
`on_invalidated` is told and the seen set's keys carry — which each of
the three base classes answers, a `Leaf` one, a `StdBlock` two, an
`Unchained_Node` none; no class sets the list *(decided)*. A class has no operations of its
own beyond these: the loader refuses an override of `_own_statuses`,
and the three implementations carry `typing.final` *(decided)*. A class
reads the list through `last_evaluation_statuses()`, a tuple. Loading
sets every instant status `not_evaluated` as the constructors do and
assigns the stored list to the attribute directly, through no setter
*(decided)*. At rest, whenever an instant status is not `not_evaluated`,
the two are equal; they differ only on a loaded node not yet rerun.

**One form per status, and the messages of a run.** The status values
carry what the run reported *(decided)*. `NotEvaluated` carries nothing,
its one instance `NOT_EVALUATED`; `CannotEvaluate(messages)` the reason the run
failed; `Ready(messages)` what the class's callback chose to report of a
run that went through — a failure it carried on past, or a notice of
its own — and `Ready()` a clean
run; nothing Isabelle prints on its warning channel reaches a status
(MODULE_STRUCTURE §2.4). `Ready` and `CannotEvaluate` are frozen
dataclasses with one field, `messages: tuple[IsaTerm, ...]`
(MODULE_STRUCTURE §4.3), and each has exactly one form: there is no module-level `READY` or
`CANNOT_EVALUATE`, a status's kind is tested with `isinstance`, and
`==` compares the messages too *(decided)*. A module-level `Ready()`
instance may be reused for clean runs, as a value and never by
identity *(decided)*. Its name is §7's. The evaluation hooks return the status the run leaves —
`_eval_opr`, `_eval_beginning_opr` and `_eval_ending_opr` return a
`Ready` or a `CannotEvaluate` *(decided)*. They raise nothing: a
`TAT_Error` escaping one of them is the class's bug, turned into a
`TAT_InternalError` once in `Forest._run`, and anything else that
escapes ends the conversation as it is (EXCEPTIONS §1) *(decided)*. So the messages shown, stored
and reported are those of the run whose status stands: an invalidation
replaces the value and the messages go with it, a rerun brings its own.
Rendering is the framework's: wherever `print_fields` is called
(PRINT.md §2–§3, `Recall` included), the framework writes each own
operation's messages with `print_error`'s block, under the header
`Error:` for a `CannotEvaluate` and `Notice:` for a `Ready` *(decided)*.
The mark is PRINT.md §1's table unchanged, and each block follows its
operation's status, not the line's words (PRINT.md §1). The seen set's keys for an
operation's messages are the framework's, discarded by the setter at
every write (below), so that PRINT.md §4's rule stands: a run's
messages show again after every run, identical or not.

**The setter.** Every status write goes through one setter per
operation (`Leaf._set_status`, `StdBlock._set_beginning`,
`StdBlock._set_ending`), and the setter writes both the instant and
the stored field *(decided)*. It is a plain method, since nothing it
does awaits — the importers are reached through the synchronous
invalidation recursion (MODULE_STRUCTURE §4.1) — so every setter, and
every function one calls, is a plain method *(decided)*. What it does:
it releases the operation's slot
when the status goes from written to unwritten (ARCHITECTURE §3.4),
fires `on_invalidated` when the instant status leaves `ready`
(MODULE_STRUCTURE §4.1), and, when the operation is one the node's jobs
depend on (CONSTRUCT_INTERACTION §3.1), at every write by the walk, a
rerun's rewrite of `ready` included, tells a running construction job
through `_on_context_change` — fired through `_completed` as
`on_invalidated` is, so that whatever it raises is its class's bug
(EXCEPTIONS.md §1) — drops the attached evaluation job, and clears the
node's stored check when the stored status leaves `Ready` (below;
CONSTRUCT_INTERACTION §3.2, §3.3) *(decided)*. It discards
the seen set's keys for the operation's messages, and adds the node to
the set of nodes the walk stores at the tree's end (below)
*(decided)*. It also writes the operation's `evaluation` log record,
given how long the evaluation hook ran, or `None` when none ran
(LOGGING.md §3; MODULE_STRUCTURE §4.1). Given `not_evaluated` for an
operation whose stored status is already `not_evaluated`, the setter
does nothing, so a repeated marking stores and logs nothing again.
`Theory._set_ending`'s rule to
the importers reads the stored field: a stored `Ready` ending replaced
by a value that is not a `Ready` invalidates the importers whole
(ARCHITECTURE §3.4) *(decided)*. An
invalidation, whatever its cause, writes `not_evaluated` through the
setter, so that a compile never trusts a status whose context changed
in the conversation; on a loaded node the setter then finds nothing
written and releases nothing.

**Two roles, one field each.** Every decision to invalidate or keep a
stored status reads the stored field; everything about slots and
running reads `evaluation_status`. The first kind: the setter's guard
on a stored `not_evaluated` (above), and `Theory`'s importer
rule (ARCHITECTURE §3.4). The second kind: `_wrote`, the releases in
the setters, the rerun tests and `on_invalidated`. `is_finished()` and the default `mark` read
`evaluation_status` *(decided)*. After a restart every node prints `not
evaluated` until rerun, and the walk reruns what a call reaches,
rebuilding its slots. `can_emit` and the compile report read the stored
field. `_resulting_status()` is the status of the operation that writes
`resulting_state()`.

**Past the destination or a stop, and after a restart.** Past its
destination, or past the first stop in each tree when `ignore_error` is
unset, the
walk writes every operation `not_evaluated` through the setter, both
fields, to the tree's end — `Forest._invalidate_from` with the position
after that node, after the destination when the stop is a nesting node
above it whose beginning failed (MODULE_STRUCTURE §4.1; ARCHITECTURE
§3.3, §3.5) *(decided)*. So a tree's statuses are an evaluated stretch up to the
last destination or stop and `not_evaluated`
after it, the nodes under a nesting node whose beginning failed aside,
in both fields alike; the tree's `end` among them leaves
`Ready`, so the importers are invalidated whole (ARCHITECTURE §3.4). A
changed environment after a restart is not detected *(decided)*. A
rerun stores whatever result it finds, and a tree the walk does not
enter keeps its stored statuses and checks, whether or not a rerun
elsewhere found a different result *(decided)*. So another Isabelle,
another AFP or a changed plugin is found only where the walk runs; the
trees it does not enter keep what the last run found until an edit or
a walk reaches them, and the build of what compile writes finds it.
After a restart a call that evaluates to a tree's end reruns the tree
and invalidates nothing but, with `ignore_error` unset, what follows a
stop; one that evaluates to a node inside it
invalidates the rest of the tree and its importers, whose proofs are
replayed when a walk reaches them.

**The stored check.** The evaluation job's outcome is stored, `PASSED`
or `FAILED(message)`, `RUNNING` as none (ARCHITECTURE §4.1,
CONSTRUCT_INTERACTION §3.3) *(decided)*. It lives on `Node` as one
framework attribute beside `_last_evaluation_statuses` — its name §7 —
restored at load from the `check` row and written by `_store_node`. It
is cleared exactly when the stored status of an operation the node's
jobs depend on (CONSTRUCT_INTERACTION §3.1) leaves `Ready`, and
when a construction job starts on the node — which stores the node,
below — or another evaluation job is attached in its place; a rerun
that confirms a `Ready` over a `Ready` does not clear it, whatever its
messages, nor does the conversation's ending, nor a write of an
operation the jobs do not depend on *(decided)*. The clearing
on a status leaving `Ready` sits in the setter, so no status write can
skip it, a construction start and an attach clearing it themselves
(CONSTRUCT_INTERACTION §3.2, §3.3); on a nesting node the stored status
of each operation its jobs depend on counts — both unless the class
names its beginning. The check's outcome has one accessor on `Node`
(§7 for its name): `RUNNING` while a running evaluation job is on the
node, the stored value otherwise — a settled attached job's outcome
equals the stored one — and every reader goes through it.
`_unfinished()` answers `None` on `PASSED`, an `Unfinished_Check`
carrying the outcome and the class's evaluation job class on `RUNNING`
or `FAILED`, and `Unchecked` on none, so that after a restart a node
with a stored `PASSED` is complete once rerun and the default `checks`
replays only a proof whose stored `PASSED` was cleared, while one with a
stored `FAILED` can be constructed again (CONSTRUCT_INTERACTION §3.1,
§3.3) *(decided)*. The
other readers: `emit`; `Proof_Obligation`'s mark and `Proof_Job._check()`
(node_classes/COMMON.md §3); the failure blocks, printed from a `FAILED` outcome
with the header from a class-level `failure_header`; and the summary
under a cut-off nesting node, grouped by the carried class's title.

**Storage.** One row of the node in `fields`, named
`last_evaluation_statuses`, holding the list with each status's
messages in their `unicode` spelling, as every stored term is held
(MODULE_STRUCTURE §4.3) *(decided)*. It is a reserved framework field beside
`kind`, `children`, `job`, `check` and the construction job's
automatic-construction field (ARCHITECTURE §4.1), written by
`_store_node` and gone with `delete_node`. A row that is missing, or
whose length is not the node's
number of operations, reads as the constructor's list, `not_evaluated`
throughout — the rule
`job` and `check` follow: a missing row that holds a result reads as the
value meaning nothing to trust, while the structural rows `kind` and
`children` stay refused — so the schema version is unchanged; a row that
is not a list of status values is refused at start as a malformed
`children` row is. `Theory.from_store` reads a missing `import_sessions`
row as the empty list and a missing `keywords` row as `None`, and
`Theory.can_emit` refuses while `keywords` is `None`
(node_classes/SESSION_AND_THEORY.md §2): on a database written before
the row, a `Ready` header's tree is not written until a walk reruns
the header and records both.

**When the store is written.** An edit stores every node whose status
its commit wrote and every node still in the forest that a completed
hook fired on, and deletes the rows of a deleted subtree, in its one
transaction, the in-memory invalidation included (MODULE_STRUCTURE §4.2
step 3) *(decided)*. An amend deletes nothing: its identity passes to
the replacement, whose `_store_node` rewrites it; `_store_node` refuses,
with `TAT_InternalError`, a node whose parent chain does not reach the
forest *(decided)*. An evaluating walk stores, at each tree's end and
when it ends — where it flushes the slots it released (ARCHITECTURE
§3.4) — every node whose status it wrote, in one transaction with
nothing awaited inside *(decided)*. The setter collects them on the
walk's `Evaluation` — one for the whole walk, which at each tree's end
stores them, deletes the slots it released and cancels the evaluation
jobs it dropped, emptying each, while the nodes it passed accumulate
for `blocking` to wait on (CONSTRUCT_INTERACTION §5) — the importers a
cascade invalidated among them,
and `_store_node` writes the whole node *(decided)*. So a field an
evaluation hook recorded — `keywords`, `import_sessions` — rides
with the status that run left. Each synchronous step of a job that
changes the job or the check on its node — a construction `start`, a
run's settlement, an evaluation job's `finished` report, an attach, a
tool writing the automatic-construction setting —
stores the node through `_store_node` in a transaction of its own
(CONSTRUCT_INTERACTION §3.1, §3.3) *(decided)*. So the check a
construction start clears reaches the database on a loaded node too. A
conversation ending between two stores — the process dying, or a bug
ending it — loses the statuses of the walk since the last store, but
for a node a job step stored meanwhile, and keeps the ones before it,
which the next walk reruns or trusts as after any restart.

**Tests this section relies on**, beside §3's helper: a database
written without the `last_evaluation_statuses`, `check`,
`import_sessions` and `keywords` rows, checking the missing-row rules —
a `Ready` header with an `import_sessions` row and no `keywords` row
among the cases; a restart
followed by a walk, checking that what the walk reached was rerun and
stored, recorded fields included, that the rest of its tree and the
importers were invalidated in both fields, and that a tree it did not
enter kept its stored statuses and checks; and, after every walk the suites run,
the at-rest rule above — wherever an instant status is not
`not_evaluated`, it equals the stored one — in `test/invariants.py`
beside the store-mirror helper.

## 5. The entry points

**`compile.py`**, beside `edit.py`: what `edit.py` is to changing the
forest, this is to writing it.

```python
def compile(forest: Forest, hooks: Sequence[Callable[[Forest], None]]) -> Compile_Report

@dataclass(frozen=True)
class Does_Not_Emit:
    node: Node                    # chosen as §2 says

@dataclass(frozen=True)
class Import_Not_Written:
    tree: Theory                  # the first forest tree it imports, placed before it, that is not written

@dataclass(frozen=True)
class Order_Constraint:
    tree: Theory                  # the forest tree it imports that is placed after it, or itself (§2)

class Entry(NamedTuple):          # one entry under the working directory, as the path listing yields it
    path: Path                    # relative to the working directory
    kind: Literal["file", "folder", "link"]      # as `lstat` reads it

@dataclass(frozen=True)
class Compile_Report:
    trees: tuple[tuple[Theory, Does_Not_Emit | Import_Not_Written | Order_Constraint | None], ...]  # tree order; None: written
    removed: tuple[Entry, ...]    # removed and not written again
```

Synchronous, no round trip, and under no lock: its one caller holds the
working directory's lock on a `Forest` of its own with no server, so
nothing changes the forest meanwhile. Two steps. The first is a
function of the stored forest alone and touches no disk: decide each
tree by §2's rule, render every written tree's text and the ROOT's text
in memory, and run the conversion of §2; it is one function,
`render(forest)`, which the
store-mirror helper of §3 calls too. The second is the disk, in this
order: refuse, as a `TAT_StartupError` (§7 for its sentences), a
`Session` folder's path that `lstat` shows holding anything but a
directory, and a folder at a path it will create — a tree's file, the
ROOT, the ROOT's temporary sibling; remove the ROOT; remove every `.thy` the path listing
yields; make every `Session`'s folder; write each tree's file in place;
run the hooks it is given, those `load` returned; remove the empty
folders compile did not make; write the ROOT last, to a temporary
sibling with the `.thy` suffix, and `os.replace` it into place — a
sibling a killed compile left behind is removed by the next compile's
removal of every `.thy`, and the ROOT takes a temporary file because
Isabelle's `parse_root` accepts a ROOT cut off between two entries. The
ROOT is thus the one mark that a compile finished its disk work, the
hooks' files included: a compile killed or failing after removing the
ROOT leaves none, which Isabelle refuses, and the next compile removes
any partial `.thy`; one refused before that, and a failure in the
first step, leave the directory as the previous compile left it. The path listing is one generator in `compile.py` (§7 for its
name), yielding every entry under the working directory, relative to
it, with its kind as `lstat` reads it — a file, a folder or a symbolic
link: it yields a link without entering it, and neither yields nor
enters a folder whose name begins with a dot. The `.thy` removal
removes every yielded entry whose name ends in `.thy`, a link
included; the empty-folder removal takes the yielded folders, each
after what it holds, and removes each that is empty and is not a
`Session`'s folder — which is all "the folders compile did not make"
means, so no record of them is kept; every hook finds its paths
through the listing and nothing else. Every file a compile writes —
each tree's file, the ROOT's temporary sibling — is created afresh,
with `O_EXCL`, so that nothing still at the path, a link included, is
written through; a refusal there is a bug, exit 2. `removed` is every
path the path listing yields at the start of the disk step and no
longer yields at its end, a folder after what it held: no record is
kept, nothing is asked of the hooks, and a path removed and written
again — a tree's file, the ROOT — is left out. The rendering of the
report into §2's lines is a function beside it, `report_lines`, so the
report holds nodes, not text.

**Compile hooks.** A plugin registers a function, not a class: a
module-level function under the decorator `TAT_compile_hook` (§7 for
the name), of one argument, the forest root, returning nothing
*(decided)*. Like `emit`, it reads stored fields (§3); it also reads
the trees, `forest.trees()`, and the working directory, which
`forest.conversation` gives it. Importing
registers it, as `TAT_node` registers a class (PLUGIN_SYSTEM §1)
*(decided)*. The registry is a process-wide one of its own,
`compile_hooks`, kept in registration order, which holds a hook exactly
while its defining module is in `sys.modules`; the sweep at the start
of `plugin.load` clears both registries of entries whose module is
gone, and `load` returns the hooks the listed packages define beside
its kind table. The loader checks a plain function of one positional
argument, neither a coroutine nor a generator — either would be made and
never run. `compile` calls the hooks it is given after
its files are written, in registration order, removes the empty
folders after them, and writes the ROOT last *(decided)*. A hook
removes only paths the path listing yields, writes only beside a tree's
file, creating each file afresh, and never touches a `.thy` or the
ROOT; it knows a tree's folder by `identity(path)` of `compile.py`, as
the compile knows a `Session`'s, since the folder's spelling on disk may
differ from the session's name; anything it raises is the
plugin's bug, and the compile did not complete. The plugin `Isabelle_Std`
registers one (`common.py`, node_classes/COMMON.md §3) for AoA's
`<Theory>.proof-store`, the proof cache AoA
keeps beside a theory's file: today, to remove each `<T>.proof-store`
and `<T>.proof-store.*` the path listing yields whose `<folder>/<T>.thy` is
no tree's file path — the lock file `with_file_lock` creates and never
removes, a temporary file a killed process left — without which the
folder never empties. The stores themselves are written during the
conversation, by the constructions' AoA calls (node_classes/COMMON.md §3), not by
the hook; a build's `by aoa` replays them.

**`toplevel.py`**: a second procedure beside `launch_TAT`.

```python
@isabelle_remote_procedure("compile_TAT")
async def compile_TAT(arg: tuple[list[str], str], connection: Connection) -> tuple[bool, list[str]]
```

The same first two arguments — the packages, the working directory — and
no port. It builds what `launch_TAT` builds before the server — the
lock, the log directory and its `Log` (LOGGING.md §2, §5), the ending
object, the `Conversation`, the `TAT.log_directory` round trip, the
store, the plugins, the `Forest` — through the same context manager
split so that the server is one layer above the rest, and the lock file
holds its pid line alone *(decided)*. The lock's other line, the port,
is a conversation's; nothing reads it during a compile (MODULE_STRUCTURE
§4.6). A bug escaping a compile enters its ending object, which writes
the `ending` record of the compile's log (LOGGING.md §5). It calls
`compile` with the hooks the `Loaded` yields; and returns whether every
tree was written, and the report's lines. It writes nothing to the
database: its store is opened read-only, a database `TAT_new` made and
no conversation has set up read as the empty forest; and its one call
over the connection is `TAT.log_directory`.

**`TAT_Framework.ML`**: `TAT.compile` does not go through `start'`, whose
command packs a port and builds the state slot table, the theory table,
the environment and every class's callbacks, none of which a compile
uses; its command record carries the framework's `TAT.log_directory`
and no class's callback, so "compile evaluates nothing" holds by
construction — a class's callback is answered as unknown.
Step 2 of MODULE_STRUCTURE §2.6, which collects the packages, is one
function both entries call. A second protocol command, `TAT.compile`, shares
`TAT.start`'s handler as one ML function — the forked plain thread,
`Future.interruptible_task`, `Exn.capture_body`, the messages, the
`TAT.finished` answer (MODULE_STRUCTURE §2.6) — each command supplying
its mapping from a normal result to a code: `TAT.start` `0`,
`TAT.compile` `0` with the report's lines when every tree was written
and `1` with them when one was not; every exception, in either command,
`2` with its messages *(decided)*. The boot answers every failure before
the hand-off with `2` likewise. The boot's first argument becomes the
protocol command to run, `TAT.start` or `TAT.compile`, the rest passed
through as before.

**`src/scala/tat.scala`**: a third tool beside `TAT_new` and `TAT_mcp`.

```
isabelle TAT_compile [-l BASE] [-d DIR]... [-o OPTION]... WORKING_DIRECTORY
```

Steps 1 to 3 of `TAT_mcp` (MODULE_STRUCTURE §5) shared, with one change to
both tools: every end that is not a normal return exits `2` — the base
heap's build through `Build.build_logic(…, strict = true)`, which raises
instead of exiting, `Getopts` in its `internal` mode, the process
terminating without `TAT.finished`; `Command_Line.tool` turns the error
into `2` — so that a `1` from `TAT_compile` can come only from
`compile_TAT`'s report *(decided)*. The one exception is §2's `130`.
Step 4 sends `TAT.boot` with `TAT.compile` and no port; step 5 waits for
`TAT.finished` — meanwhile printing the log's path once
`TAT.log_directory` names it, and each `warning` record (LOGGING.md §7)
— prints its lines — with `progress.echo` on `0` and `1`,
as errors otherwise — then, on `0` or `1`, has Isabelle read what was
written (§2) and exits `2` with Isabelle's message if it is refused,
else with the code. The functions `TAT.reserved_name` and
`TAT.check_options` (§2) live in the same jar. The directory's lock, the plugins' loading and the base heap
are the conversation's own mechanisms, so nothing is added for them.

## 6. Amendments to the other documents, by the rule each replaces

Applied on 2026-10-02, after the owner's approval — the construct
session's documents by that session, the rest by this one — except
`ML/TAT_Boot.ML`'s header and plugin.py's refusal message, which are the
code's; a line marked *done* was written by the session that owns the
document before the approval. Each item names the identifiers
it retires — single backticked tokens, which whoever applies it finds
with `/usr/bin/grep -rnI <token> docs ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md`
(the default `grep` honours `.gitignore`) — and lists each prose
passage it replaces by section, quoted as it stands.

1. **Emission's gate is `can_emit`, reading the stored statuses.**
   Retires nothing by token; prose: ARCHITECTURE §4 "emits whenever the
   node is `ready`", §6.1 "emission's gate on `evaluation_status`";
   THEOREM.md §5 "emits, when it is `ready`" (the node emits when
   `can_emit` holds; `Theorem` keeps the default); THEOREM.md §5's `by
   aoa` bullet *done*.
2. **`emit_isar` is replaced** by `emit`, `emit_beginning`, `emit_ending`.
   Retires `emit_isar`: ARCHITECTURE §4 and §6's contract table;
   MODULE_STRUCTURE §4.1's contract listing; PLUGIN_SYSTEM §5: a
   `StdBlock` class does not override `emit`, overrides
   `_eval_ending_opr` exactly when `emit_ending`, the coroutine rule for
   every override, `_own_statuses` not overridden (strike "—
   `_own_statuses` is (MODULE_STRUCTURE §4.1)" and change plugin.py's
   refusal message with it), `typing.final` on the never-overridden
   methods; what `can_emit`, `emit` and a hook may read; EXCEPTIONS §1:
   `can_emit`, `emit` and a compile hook join what node classes raise, a
   bug ending the compile with `2`; the three evaluation hooks raise
   nothing, a `TAT_Error` escaping one being the class's bug, a
   `TAT_InternalError` raised in `Forest._run`, and anything else
   ending the conversation as it is.
3. **The second status field, one form per status, the messages on the
   status values, the stored check, the walk past the destination.** Retires `READY`,
   `CANNOT_EVALUATE`, `errors`, `beginning_errors`, `ending_errors`,
   `_last_status`, `_incompleteness`, `Incompleteness`,
   `Construction_Incomplete`, `Check_Incomplete` (renamed `_unfinished`,
   `Unfinished`, `Unfinished_Construction`, `Unfinished_Check`); prose:
   "a class with statuses of its own" (MODULE_STRUCTURE §4.1 l.364;
   PRINT.md §1) and "a class with its own statuses" (MODULE_STRUCTURE
   §4.1 l.485), the prose of A3 — the withdrawn rule of 2026-10-01 that
   a rerun storing a different value is an edit at that node, with a
   fifth walk mode (ai-artifacts/CONSTRUCT_DECISIONS.md §14) — in
   ARCHITECTURE §3.5 and MODULE_STRUCTURE
   §4.1 — "reran the destination", "without a rerun", the `Untouched`
   mode in the `EvaluationMode` listing and its comment, "past a
   destination that was rerun or reached blocked" in the `Invalidating`
   comment, the `_mode_after` sentence — A3 being withdrawn: past every
   destination the walk marks to the tree's end, in both fields
   (ARCHITECTURE §3.5's "after a stop the recursion goes on, marking
   what follows `not_evaluated`" stays as it is), `Conversation.forget` as called by a
   hook (MODULE_STRUCTURE §4.1; CONSTRUCT_INTERACTION §6), "derived from
   the node's two jobs" (ARCHITECTURE §3.2) *done*, "written at each
   synchronous step that changes the job on its node" and "keeps the
   value for emission to read" (ARCHITECTURE §4.1: the job steps store
   the node), "one **failure block** per job of the node whose outcome
   is `FAILED`" and "the job their `Incompleteness` carries" (PRINT.md
   §2) *done*, the `-> bool` of the evaluation hooks (ARCHITECTURE §6.2;
   MODULE_STRUCTURE §4.1), "The ending setter alone is `async`"
   (MODULE_STRUCTURE §4.1) and "so the ending's setter becomes `async`;
   every caller already is" (FIRST_END_TO_END §6): `_set_ending` loses
   its `async`, and `_mark_not_evaluated` gives way to `_invalidate`
   (item 4); the setter's halves in
   CONSTRUCT_INTERACTION — "called from the status setter's instant
   half on every write" (§3.2, the `_on_context_change` row: "called
   from the status setter on every write"), "in the status setter's
   stored half" (§3.3, the `outcome` row: "in the status setter"), "The
   drop is the status setter's instant half's, the stored check's
   clearing its stored half's (COMPILATION.md §4); in a running
   conversation the two happen at the same moment." (§3.3: "The status
   setter does both: the drop at every write by the walk, the clearing
   when the stored status leaves `Ready` (COMPILATION.md §4)."), "in
   the status setter's stored half at every write" (§6: "in the status
   setter at every write"); "when the ending leaves `ready`"
   (MODULE_STRUCTURE §4.1) and "Whenever a tree's `Theory` ending goes
   from `ready` to anything else" (FIRST_END_TO_END §6: the stored
   ending, from a `Ready` to anything that is not a `Ready`); "never
   stored" on the check *done*. Places:
   ARCHITECTURE §3.2 (the fields,
   the one-form values with messages, who reads which, the operations
   fixed by the base classes), §3.3 (the guards read the stored field),
   §3.4 (the setter writes both fields; the importer rule reads the
   stored ending; where a walk stores), §3.5 (past every destination
   the walk marks to the tree's end, in both fields; A3 withdrawn),
   §4.1 (`last_evaluation_statuses` stored; the
   missing-row rule; the stored check's clearing, its attribute and its
   accessor; the job steps store the node; "a loaded forest is
   `not_evaluated` throughout" kept for the instant field), §6.2;
   MODULE_STRUCTURE §4.1 (the status paragraph, the setter writing both
   fields, the attribute and its accessor, `_operation_names()`,
   `_resulting_status`, the `Evaluation` listing gaining the set of
   nodes the walk stores, the `on_invalidated` row; the walk listing:
   item 4's two plain functions in place of the `Seeking` and
   `Invalidating` modes), §4.2 step 3 ("every node whose status changed
   and every node a hook fired on": every node whose status the commit
   wrote); FIRST_END_TO_END §2 (the
   reserved row, the missing-row rule, the evaluation-hook write
   replaced by the walk's store of every node whose status it wrote;
   "Not stored: evaluation statuses" narrowed to the instant ones), §3
   (the two error fields), §6; PRINT.md §1, §2, §3 and §7 and its code
   listing (the framework writes the messages, `Error:` and `Notice:`;
   `print_fields` writes the fields alone), §4 (the keys are the
   framework's, discarded by the setter); RECALL.md §2 (the messages at
   each depth, by PRINT §3–§4's rule); RENDER_BASELINES (the two
   headers);
   SESSION_AND_THEORY §2 and §4 (`Theory`'s two error fields gone;
   `import_sessions` recorded and stored; the file-path method; `errors`
   in §4's table the framework's); THEOREM.md §1, §6, §7 (the check's
   accessor and its readers), §8; CONSTRUCT_INTERACTION §3.1
   (`_unfinished` through the accessor; `Unfinished_Check` carries the
   outcome and the class; `start` stores the node), §3.2 and §3.3
   (`failure_header` a class method; the `outcome` row and the `start`
   row: each job step stores its node through `_store_node`; the drop
   paragraph: the clearing follows the stored status), §6; the A3 entry
   of ai-artifacts/CONSTRUCT_DECISIONS.md §8 ("a rerun that stores a
   different value is an edit at that node …"), replaced whole by the
   ruling of 2026-10-02 — A3 withdrawn: past every destination the walk
   marks to the tree's end, in both fields; a rerun stores whatever it
   finds — its text of 2026-10-01 moving to the record's withdrawn
   section, as does the A3 entry of
   ai-artifacts/CONSTRUCT_DECISIONS_LOG.md §11 with its fifth mode and
   its inversion of
   `test_evaluate_to_inside_an_import_invalidates_its_importers_whole`,
   which stays as it is; "the status setter's instant and stored
   halves" (CONSTRUCT_DECISIONS.md §8), which reads "one status setter
   per operation writing both fields".
4. **The walk's store and the edit's transaction.** MODULE_STRUCTURE
   §4.2 step 4 *done*, §4.1's completed-hook rule *done*; the synchronous
   invalidation recursion, two plain functions taking the walk's
   `Evaluation` — a node's `_invalidate(ev)`, marking it whole
   `not_evaluated` through its setters, an `Unchained_Node`'s
   invalidating each child whole, and
   `Forest._invalidate_from(position, ev)`, marking from a position to
   the tree's end and up the ancestors — whose callers are the edit's
   commit (`_invalidate_from` at the edit's position, a `move` at two:
   the source successor's and the moved node's new one; `_invalidate`
   on each tree whose record changed), the importer cascade in
   `Theory`'s ending setter, and the evaluating walk — `_handle_tree`'s
   `_invalidate` on a tree it stops at (the order constraint, an import
   without a theory value), a failed beginning's `_invalidate` on each
   child, and `_handle_tree`'s one `_invalidate_from` call after the
   tree's `_evaluate` returns, with the position after the stop — after
   the destination when the stop is a nesting node above it whose
   beginning failed — or after the destination when it lies in the
   tree; `Seeking`,
   `Invalidating`, `Blocked` and
   `_mark_not_evaluated` go, `EvaluationMode` with them, `_evaluate`
   taking `Evaluating`; the three setters plain
   methods (MODULE_STRUCTURE §4.1's walk and status listing, written by
   this session; ARCHITECTURE §3.4 in the same words; CONSTRUCT_INTERACTION
   §3.3, §9 and MODULE_STRUCTURE §4.2 aligned by the construct session;
   FIRST_END_TO_END §6).
5. **Compile is the command, and the glossary.** Retires the callback
   `TAT.is_known_session` (`Loader.is_known_session` stays, off the
   wire); prose: ARCHITECTURE §1 "`isabelle TAT`, the
   command that starts" and "claims it for one conversation";
   ARCHITECTURE §4 "Isabelle never reads them" (replaced by this
   document's opening: never during a conversation; the compile's own
   reading); MODULE_STRUCTURE §2.6 "`1` with the exception's messages
   when an exception ended it" and §5 "`1` when an exception ended it",
   "`1` when the process terminated without `TAT.finished`", the
   Getopts sentence "exits `1`", and "the build's own code" (step 3, the
   interrupt sentence); CONSTRUCT_INTERACTION §8 "which the launcher
   prints before exiting 1 (§9)". Places: ARCHITECTURE §1 — `launcher`,
   the Isabelle tools of `tat.scala`, `TAT_new`, `TAT_mcp` and
   `TAT_compile`, the latter two starting the Isabelle process through
   the boot; `working directory`, the lock claims it for one
   conversation or one compile; `conversation`, a compile is not one;
   `message`, which gains a second sense: the messages of a status
   value, Isabelle's output of a run as `IsaTerm`s, shown under
   `Error:` or `Notice:` (§4 here; PRINT.md §3); §4
   (when the forest is compiled, §1 here; the rule for which trees; the
   directory after a compile: the folders made, the path listing, the
   refused non-directory); §9 (launching: the third tool); MODULE_STRUCTURE §1
   (`compile.py` among the modules of §4; `TAT_compile`; the Scala
   function), §2.3 (`check_session`), §2.6 (`TAT.compile`,
   `TAT.check_session` in place of `TAT.is_known_session`; the exception
   code `2`), §4.1 (`Conversation`: what a conversation or a compile is
   given), §4.3 (the driver: `check_session`), §4.4 (`Loaded` gains the
   compile hooks; PLUGIN_SYSTEM §1 and §5 the decorator, its registry,
   its check, and what a hook may touch), §4.6 (`compile_TAT`, the
   context manager split, the ending object built by both entries, the
   `Conversation` holding it (§4.1 too); the lock refusal's wording, §7),
   §5 (the tool;
   the boot's first argument; `strict`, `internal`, every non-normal end
   `2`, the `130`; the `Scala.Functions` service; the final
   `Sessions.deps` reading); `ML/TAT_Boot.ML`'s header and the comment
   above `TAT.start`; EXCEPTIONS §1 and PLUGIN_SYSTEM §5: a startup error
   leaves through `launch_TAT` or `compile_TAT`, a `Session` folder's
   path refused joins the causes, and "another conversation holds the
   working directory" (EXCEPTIONS §1) reads "another conversation or a
   compile"; PLUGIN_SYSTEM §5: the path listing is the one framework
   function a hook calls to find paths, and every file it writes is
   created afresh; MODULE_STRUCTURE §4.6 and LOGGING.md §1, §2, §5, §7
   and ARCHITECTURE §1's `working directory` (a compile makes its log
   directory and `Log` and calls `TAT.log_directory` as a conversation
   does, so both sides write its records and the launcher prints its
   `Log:` line — one log per conversation or compile; the lock file's
   second line is a conversation's, a compile writing its pid line
   alone);
   FIRST_END_TO_END §1 (the open item closed; the ownership bullet).
6. **The ROOT entry and the names.** Retires nothing by token; prose:
   SESSION_AND_THEORY §1 "`parent_session` is transcribed and nothing
   else" (the `sessions` clause); "declares global" as the whole of
   `ReservedTheoryName` (SESSION_AND_THEORY §2, EXCEPTIONS §3,
   EVALUATOR_DESIGN §7, RENDER_BASELINES §2: a name the layout declares
   global, or one Isabelle reserves); the theory namespace comparing
   exactly (MODULE_STRUCTURE §4.2). Places: SESSION_AND_THEORY §1 (the
   entry as §2 writes it; `Theory`'s `emit_beginning` and `emit_ending`;
   the checks: the reserved names through Isabelle's predicates, `ROOT`,
   the known session, the options), §2 (`import_sessions`; the file-path
   method; the case-insensitive namespace; the reserved-name check), §3
   (§7's two `InvalidField` reasons); RENDER_BASELINES §2 (the widened
   caption; the session's counterpart class with the two approved lines,
   its name §7); MODULE_STRUCTURE §2.3 (`check_session`,
   `check_new_theory_short_name` asking the Scala function), §3 (a
   `Session` emits nothing; `compile` writes its entry; `TAT.Theory.begin`
   answers the import sessions), §4.2 (the namespace); EXCEPTIONS §3;
   FIRST_END_TO_END §4.
7. **`sorry` is the builder's.** ARCHITECTURE §4, one sentence.
8. **Records.** ai-artifacts/STEP5_HANDOFF.md;
   ai-artifacts/COMPILATION_REVIEW.md; ai-artifacts/CONSTRUCT_DECISIONS.md
   (item 3's two entries), through the construct session.
9. **The sixth review's rulings** (ai-artifacts/COMPILATION_REVIEW.md
   §13), applied on 2026-10-03. Retires `Blocked`, `EvaluationMode`,
   `_invalidate_whole`, the internal `evaluate` flag of
   `Node.evaluate_to`; prose: "a blocked walk never overwrites an own
   stop" and the guards that keep one (ARCHITECTURE §3.3; MODULE_STRUCTURE
   §4.1; §4 here), "one per tree of the forest's evaluating walk" and
   "each tree under an `Evaluation` of its own" (MODULE_STRUCTURE §4.1;
   FIRST_END_TO_END §6; "the tree's `Evaluation`" in §4 here), "Three
   shapes of destination" and the whole-node shape (MODULE_STRUCTURE
   §4.1; ARCHITECTURE §3.5's "Without `evaluate`"; MCP_SPECIFICATION §4's
   "one more, internal flag"), "every node a hook fired on" (§4 here;
   MODULE_STRUCTURE §4.2 step 3; FIRST_END_TO_END §2's "`delete_node`
   for every node that left" and "An amend's replaced node uses
   `_store_node`"), "A compile runs step 2 alone" (MODULE_STRUCTURE
   §2.6); ARCHITECTURE §3.5's "after a stop the recursion goes on,
   marking what follows `not_evaluated`", which item 3 kept. The
   rulings: with `ignore_error` unset the walk of a tree ends at its
   first stop as at its destination, the forest going on to its next
   tree, the stop answering `mode` `None`
   and `_handle_tree`'s one `_invalidate_from` call taking the position
   after it, everything after a stop `not_evaluated` to the tree's end,
   obstacles included; one `Evaluation` per walk, stored and flushed at
   each tree's end, `passed` accumulating; `Node.evaluate_to(agent,
   ignore_error, checks)` always evaluates; the setter fires
   `_on_context_change` through `_completed`; the edit's store set and
   `_store_node`'s refusal (§4 here). The author's: a `move` invalidates
   from two positions, the source successor's and the moved node's new
   one, where it left that tree's ending and its importers included;
   MODULE_STRUCTURE §2.6's step 2 collects the registrations and the
   packages, step 3 calls the functions with the environment and adds
   the framework's callbacks, a compile running step 2 and, of step 3,
   making `TAT.log_directory` alone; the setter's guard on a stored
   `not_evaluated` (§4 here); §3's helper comparing the stored forms;
   `Unchained_Node._invalidate` invalidating each child whole; the
   definition of **instant status** (ARCHITECTURE §3.2). Places:
   ARCHITECTURE §3.2–§3.6, §4.1; MODULE_STRUCTURE §2.6, §4.1, §4.2;
   MCP_SPECIFICATION §3.2, §4; EXCEPTIONS §1; LOGGING §4 (the
   `walk_started` event without `evaluate`); CONSTRUCT_INTERACTION §3.2,
   §9 (the construct session's); FIRST_END_TO_END §2, §6; §3 and §4
   here. The code, once the owner lifts the freeze: `Blocked`,
   `EvaluationMode`, `_mode_after`'s `Blocked` answer (it answers `None`
   at a stop), the stopped-child
   test, `_carry_forward`'s release branch, `move`'s second release, the
   `evaluate` flag, `_invalidate_whole` and the root's refusal go, with
   the tests `test_own_stop_survives_being_blocked`,
   `test_removing_an_own_stop_behind_a_blocked_predecessor_releases_its_copy`
   and `test_the_root_has_no_position`; `test/invariants.py`'s clause on
   a `CannotEvaluate` operation may then require an obstacle's input
   slot to be held;
   `_handle_tree` runs every tree under the walk's one `Evaluation`;
   the setters gain the guard and the `_completed` call; `_store_node`
   gains the refusal; the six tests that used the flag call a test
   helper; and the tests §13 names: a cross-tree `move`, a repeated
   `_invalidate_from` storing nothing, an `_on_context_change` raising
   `InvalidField` under an edit, an amend and a delete under hooks that
   record a field. The ruling of 2026-10-03 on reader 8's finding: a
   destination under a nesting node whose beginning failed is reported
   as stopped at that node when `ignore_error` is unset, and everything
   after the destination is invalidated either way (ARCHITECTURE §3.3,
   §3.5; MODULE_STRUCTURE §4.1; MCP_SPECIFICATION §4; §4 here).

## 7. Wording and names

Items 1 to 5 approved on 2026-10-02 *(decided)*.

1. The report's lines are §2's, read by the pipeline or on a terminal;
   the order-constraint line's variant is `it imports itself`.
2. The lock refusal when a compile holds the directory: `<working
   directory> is held by another TAT conversation or compile (its Python
   process is pid <n>)`, in place of `another TAT conversation holds
   <working directory> (its Python process is pid <n>)`. Not `TAT is
   running`: during a compile the hook script says `TAT is not running in
   this directory`.
3. `Session.gen`'s new sentences — the reserved-name ones, and two in
   `InvalidField`'s shape (SESSION_AND_THEORY §3):

   ```
   `Aux` is a reserved session name; choose another name.
   `ROOT` is a reserved session name; choose another name.
   The field `name` must not be the name of an existing Isabelle session; `Graph_Theory` is one.
   The field `options[1]` is not accepted by Isabelle: Unknown option "documnet".
   ```

4. Names: the decorator `TAT_compile_hook`; the exception class behind
   the session's reserved-name sentence, `ReservedSessionName`; the
   stored check's attribute `_check_outcome` and accessor
   `check_outcome()` (`_check` is `Construction_Job`'s hook); the
   accessor `last_evaluation_statuses()`; `Theory`'s file-path method
   `file_path()`; the path listing in `compile.py`,
   `paths(working_directory)` — public, since every hook calls it to
   find its paths and a plugin touches no underscored name
   (PLUGIN_SYSTEM §2); the module-level clean `Ready()` instance (§4),
   `READY_CLEAN`, a value and never a kind.
5. The refusal of a `Session` folder's path (§2, §5), printed to the
   pipeline's log as an error:

   ```
   TAT cannot compile into <working directory>: <Session name>/ is a symbolic link; a session's folder must be a directory or absent
   TAT cannot compile into <working directory>: <Session name>/ is not a directory; a session's folder must be a directory or absent
   TAT cannot compile into <working directory>: <path>/ is a folder; compile writes a file there
   ```

   The third, approved on 2026-10-04, for a folder at a path the
   compile will create (§2), `<path>` relative to the working directory.

6. The same folder refused in a conversation, when a theory of the
   `Session` begins and the folder cannot be made (MODULE_STRUCTURE
   §4.1; EXCEPTIONS §1): the conversation ends and the launcher prints
   one of these, approved on 2026-10-04 *(decided)*:

   ```
   TAT cannot use <working directory> as its working directory: <Session name>/ is a symbolic link; a session's folder must be a directory or absent
   TAT cannot use <working directory> as its working directory: <Session name>/ is not a directory; a session's folder must be a directory or absent
   TAT cannot use <working directory> as its working directory: <Session name>/ cannot be made: <the system's message>
   ```
