# What the classes of `Isabelle_Std` share

Status: proposed 2026-10-10, revised after the first review, committed
2026-10-13 (e3eadf3); revised 2026-10-14 with the `Typedef` design
(TYPEDEF.md; ai-artifacts/review/TYPEDEF_REVIEW.md); revised 2026-10-16
with the `LiftDefinition` design (LIFT_DEFINITION.md): §3's rule for a
goal with no subgoal; revised 2026-10-17 with the `QuotientType` design
(QUOTIENT_TYPE.md; ai-artifacts/review/quotient_type/QUOTIENT_TYPE_REVIEW.md):
§6, and §4's helpers for type parameters without a sort, a pair of
function names and a type's head, implemented 2026-10-18 with that
class, and §4's check of a type parameter declared and not used.

The plugin `Isabelle_Std` (MODULE_STRUCTURE §4.5) carries the node
classes of Isabelle's standard commands (INDEX.md). What they share is
this document's: the base every class derives from (§1), the `english`
field and its `text` line (§2), the base of the classes whose command
opens a proof obligation (§3), the `$defs` several classes merge and
the configuration option `typedef_overloaded`, which `TAT_Std.TAT_Std`
sets for every theory of a forest (§4), the conventions their schemas
and sentences follow (§5), and the ending of a block that closes a
type's Lifting setup (§6). Its Python half is
`isabelle_theory_agent/std/common.py`, its ML halves
`Isabelle_Std/ML/TAT_Proof_Obligation.ML` (§3), `TAT_Mixfix.ML` (§4),
and `TAT_Lifting_Closing.ML` (§6). What a class makes of it is that
class's own document's.

## 1. `Theory_Member`

Every class of the plugin lives inside a theory — under a `Theory`, or
under a nesting node under one; never under a `Session` or the forest
root — and derives from `Theory_Member` before its framework base:
`class Datatype(Theory_Member, Leaf)`. `Theory_Member` gives three
things:

- `require_inside_theory(config, kind)`, a class method the class's
  `gen` calls first, the plugin's convention. It raises
  `NotInsideTheory` for a parent outside a theory.
- `on_moving`, overriding the framework's empty default (MODULE_STRUCTURE
  §4.1): a move whose destination is outside a theory is refused with
  `NotInsideTheory`, carrying the destination's id.
- `theory()`, the `Theory` the node lives in — the root of its tree,
  which the two checks guarantee exists — through which a class writes
  its Isabelle text into the file (`print_name` against the theory's
  `keywords`, SESSION_AND_THEORY §2).

`NotInsideTheory` derives from `BadEdit` and carries the kind and the
parent's id as the agent sees it — `forest().id_of` of the parent:
`config.parent` in `gen`, the destination's in `on_moving`, through one
private helper of `common.py`. It is the plugin's one parent exception:
the framework's `Session` and `Theory` keep theirs,
`BadSessionNodeParent` and `BadTheoryNodeParent`, and every class of
the plugin shares this one (EXCEPTIONS.md §3). Its sentence, pinned
here:

```
A `datatype` cannot be placed under `session_Arith`; it belongs inside a theory.
```

A test of the plugin asserts that every class its package registers
derives from `Theory_Member`, and that a construct of each placed under
a `Session` is refused with `NotInsideTheory`.

## 2. `english` and the `text` line

Every class carries an authored `english`, `str`, required — what it
declares, in a sentence — except `Section` and `Text`, whose own
command is already the document's text; any other class that carries
none says so in its own document, with the reason. `Theorem`'s is
inside its `LongStatement` (THEOREM.md §2); every other class's is a
field of its construct, its description in the class's own document
(`Datatype`'s, DATATYPE.md §3).

`gen` normalises it as it does Isabelle text: newlines become spaces
and runs of whitespace one space. Emission writes it as a `text`
command before the class's own command, through one function of
`common.py`, `text_line(english, lead=None)`: a period added when it
ends without `.`, `!` or `?`, the text through the framework's
`cartouche` (COMPILATION.md §3). A class may put a lead before it:
`Theorem` writes the kind capitalised and the name, `Lemma
rev_length.` (THEOREM.md §5); `Datatype` writes none (DATATYPE.md §5). Evaluation never runs the `text` command. Under
`recall` a class prints `english` at the depths its own table names
(PRINT.md §3).

## 3. `Proof_Obligation`

`Proof_Obligation` serves a class one command of which opens exactly
one goal, which is admitted, the class's `after_admission` step
following the admission in the same operation into the resulting slot
(`Typedef`'s runs `setup_lifting` as its recorded `lifting` says,
TYPEDEF.md §6; `Theorem`'s and `LiftDefinition`'s are the identity).
That operation is the class's `job_operation`, the
operation that writes what the node's jobs read (CONSTRUCT_INTERACTION
§3.1), in two shapes: a `Leaf`'s one operation — `Proof_Obligation`
itself sets `job_operation = None` — and a `StdBlock`'s beginning,
through the subclass `Beginning_Proof_Obligation`, which sets
`"beginning"`, so that the node's jobs depend on the beginning alone. A
class of
either shape whose command opens a proof obligation (INDEX.md) derives
from the class that sets its `job_operation`, before its framework base
— `class Theorem(Theory_Member, Proof_Obligation, Leaf)`, `class
QuotientType(Theory_Member, Beginning_Proof_Obligation,
Lifting_Closing)`, `Lifting_Closing` being the plugin's `StdBlock` (§6)
— and takes its goal's evaluation hook from that class: `_eval_opr` from
`Proof_Obligation`, `_eval_beginning_opr` from
`Beginning_Proof_Obligation`, each `final` and each running
`_eval_goal` (the evaluation, below); the plugin's test over every
registered class pins the rule, as §1's pins `Theory_Member`, and the
loader refuses `Proof_Obligation` bare on a block, `None` being no
operation of a block, as it refuses `Beginning_Proof_Obligation` on a
leaf (PLUGIN_SYSTEM §5). `Proof_Obligation` derives from
`With_Proof_Obligations`, the base of every class whose commands open
proof obligations — `Define`'s open up to two, on two commands
(DEFINE.md) —, which holds what the proofs' standing decides for every
such class: the mark's three words and `mark` (the mark, below),
`proof_text()` (the emission, below), `_carries_job_from` (the amend,
below) and the hook `owes_proof()` — true by default, `Define`'s whether
an obligation is open —; it derives from `Node`, so that its abstract
methods, `goal_structure()` and `message()`, are enforced. `Theorem`,
`Typedef` and `LiftDefinition` derive from `Proof_Obligation`
(THEOREM.md, TYPEDEF.md, LIFT_DEFINITION.md) and `QuotientType` from
`Beginning_Proof_Obligation` (INDEX.md); `Interpretation` and
`Sublocale` are expected to derive from it, each confirming it in its
own document; `Instantiation`, whose goal opens on a `StdBlock`'s
ending, decides in its own document how it discharges its own, and
extends `Proof_Obligation` then, if it uses it, with a subclass whose
goal opens on the ending.

**A goal with no subgoal.** A command may open its goal with no subgoal
— `lift_definition`'s when Isabelle proves the respectfulness by itself
(LIFT_DEFINITION.md §6), `interpretation`'s, `global_interpretation`'s
and `sublocale`'s of a locale with no assumption —, which Isabelle's own
library closes with `.`. To `Proof_Obligation` it is a goal like any
other, and nothing below branches on it: the admission, the half of
`sorry`, passes on such a state and leaves no `skip_proof` oracle; the
proof construction's call of AoA answers at once with the product `-`
and zero times, no search having run — `async_prove`'s short circuit
for a sequent with no subgoal
(`contrib/auto_sledgehammer/library/sledgehammer_solver.ML`), on which
`hammer_or_AoA'` answers `-` (`contrib/Isa-Mini/Agent/agent_server.ML`)
—; the proof check replays
`-`, the method that does nothing, and passes; and the file's `by aoa`
passes in a build through the same short circuit, no driver run. So the
node is `proven` after one construction that costs no search, and the
file carries `by aoa` as for every other goal.

The tree holds no proof (ARCHITECTURE §2.1): every evaluation admits
the goal; the construction job, the proof construction, finds the
proof, which the evaluation job, the proof check, replays in the
current context, and which the file carries as `by aoa`. What
`Proof_Obligation` holds, and a class leaves to it:

**The product.** `proof` is the construction job's outcome
(CONSTRUCT_INTERACTION §3.1): `NOT_STARTED`, `RUNNING`,
`SUCCEEDED(product)` or `FAILED(message)`, `product` being the proof:
the method text AoA answers, such as `(simp add: …)`, `aoa_replay "…"`
or, on a goal with no subgoal, `-` (above), with the two times of its
replay — the thread's
CPU time and the wall time, in milliseconds, as AoA records them beside
a proof, in the standard-machine form its store holds — which the proof
check derives its limits from; it is stored. The proof check's outcome
— `RUNNING`, `PASSED`, `FAILED` — is read through the framework's
`check_outcome()`: `RUNNING` while a running proof check is on the
node, the stored check otherwise, which is cleared when the stored
status of an operation the node's jobs depend on leaves `ready`, when a
proof construction starts, or when another check takes its place, and
by nothing else
(CONSTRUCT_INTERACTION §3.3, ARCHITECTURE §4.1). The mark, `_check()`,
`proof_text()` and the failure block read it there.

**The slot.** `goal_state`, a state slot beside the node's own
(ARCHITECTURE §3.1, MODULE_STRUCTURE §4.1), holds the `Toplevel.state`
in which the goal stands open and no proof step has been taken. It
holds a state exactly while `job_operation_status()` is `ready`.
`Proof_Obligation` mints it in its constructor, so a loaded node's is
empty, like its `state`; appends it in `_states_inside()`, so that it is
deleted with the node; and names it in `_slots_written_by` for
`job_operation`, so that the framework releases it with that
operation's resulting slot when the operation goes from written to
unwritten (MODULE_STRUCTURE §4.1). Only the evaluation writes it, and
empties it itself when a run fails: the framework releases it only when
the operation goes from written to unwritten, which a failed run, a
leaf's or a beginning's, is not.

**The evaluation.** `Proof_Obligation`'s `_eval_goal`, `final`, run by
the hook of the class that sets `job_operation` — `_eval_opr` on
`Proof_Obligation`, `_eval_beginning_opr` on
`Beginning_Proof_Obligation` —, calls the class's own callback, named
by its class attribute `evaluation_callback` — `TAT.Theorem.evaluate`
for `Theorem` — with `job_operation`'s input slot, `goal_state`, its
resulting slot (`operation_slots`, MODULE_STRUCTURE §4.1) and the
class's message, the result of
its `message()`: a public, synchronous hook returning its fields as
structure, each `IsaTerm` as its `ascii`, with `goal_structure()` as
its goal part (the amend, below). On the ML side the class gives two
steps, each a function of the message:

- `open_goal : Toplevel.state -> (Toplevel.state * 'a) answer`
  (`TAT_Framework.answer`, MODULE_STRUCTURE §2.4), from the input state
  to the state with the goal open together with what the class records,
  or to the refusal with at least one message when the command, or a
  check the class makes on the open goal, refuses the input;
- `after_admission : Toplevel.state -> (Toplevel.state * 'b) answer`,
  from the state with the goal admitted to the state after the class's
  commands that follow the admission, together with what it records, or
  to the refusal with at least one message when one of those commands
  refuses; the identity, `Accepted` with the state it was given and
  `()`, for a class with no command after the admission.

Every transition of a step runs through `apply_transition`
(MODULE_STRUCTURE §2.4), which answers `Refused` with Isabelle's
messages when it refuses; an interrupt, and a `Bug` from the step's own code,
propagate — a proper interrupt as far as the operation, which answers it
as the refusal `Interrupt` (MODULE_STRUCTURE §2.5). `TAT_Proof_Obligation` builds the class's evaluation
callback from the callback's name, the message's unpacker, the two
steps and the packer of what they yield, and the class registers
through the builder, `register`. Beside it the structure exports the
admission, `admit : Toplevel.state -> Toplevel.state answer`,
`apply_transition` of the half of `sorry` below, which the callback
applies and a step may try on a state of its own (`LiftDefinition`'s
trial, LIFT_DEFINITION.md §6), and `decide`, a command's option decided under §5's
recorded-choice convention: with a value given — the recorded choice,
or one the class decided beforehand — the command run with it, once, yielding
its state and the value, a refusal the refusal; with none the command
run with the option as a probe, `needed` — a question of the probe's
state, the class's — asked of it, then the command run with the option
so decided, yielding that run's state and the option, the probe's state
a value never written into a slot; a refusal anywhere the answer.
`LiftDefinition` decides its `(code_dt)` through it (LIFT_DEFINITION.md
§6). The body,
`evaluate`, is private to it,
so the steps cannot touch a slot and every class answers one shape. The
callback's arguments are the input slot and the resulting slot of the
operation the goal opens on, with `goal_state` between them, and the
message; its `on_interrupt` is `Reraise`, its `timeout`
`NONE`. It runs `open_goal` under `operation'` (MODULE_STRUCTURE §2.5)
into `goal_state`; then, as one operation into the resulting slot, the
half of `sorry` that ends a toplevel goal — `Toplevel.end_proof
Proof.global_skip_proof` — and `after_admission`; a failure anywhere
empties `goal_state`, and the resulting slot is written only when
everything passed. The answer is `Refused` with the messages or
`Accepted (a, b)`, packed by `TAT_Framework.pack_answer` — on the wire
`[[msgs], nil]` or `[[], [a, b]]`: the messages, and when there are
none the pair of what the two steps yielded. `_eval_goal` returns
`CannotEvaluate(messages)` when there are messages — the operation is
an obstacle — and `Ready(self.record_from_evaluation(what))` otherwise.
`record_from_evaluation(what)`, a member beside `evaluation_callback`
and `message()`, records what the two steps yielded and answers the
tuple of `IsaTerm` messages the `Ready` carries; the default records
nothing and answers `()`; `Typedef`'s sets `lifting` and answers its
notice exactly when it sets it to false (TYPEDEF.md §6). `Theorem`'s
`open_goal` is the `lemma` transition and
the undeclared-variable check, yielding `()`; its `after_admission` the
identity (THEOREM.md §6).

**The jobs.** `Proof_Job` and `Proof_Check` are `Proof_Obligation`'s
`construction_job_class` and `evaluation_job_class`, their callbacks
`TAT.Proof_Obligation.construct` and
`TAT.Proof_Obligation.check`.

`Proof_Job`: `title()` is `proof construction`, `title(plural=True)`
`proof constructions`; `compulsory` is true, so the node is finished
only when `proof` is `SUCCEEDED` and the proof check `PASSED`
(ARCHITECTURE §3.2, the framework's `_unfinished`). Its `_run` calls
`TAT.Proof_Obligation.construct` with `goal_state`, an empty setup — the
call's task, goal hint, tactic whitelist and whether its goal is kept as
it stands, which `Define`'s calls fill
(DEFINE.md §7) — and the id of the run's fork (CONSTRUCT_INTERACTION
§3.2), and waits for the report. The
callback takes the slot's `Proof.state` (`Toplevel.proof_of`), its
context and goal (`Proof.goal`), and forks through the framework's
`fork_job` (MODULE_STRUCTURE §2.4) one call of AoA's `hammer_or_AoA'`
(`contrib/Isa-Mini/Agent/agent_server.ML`) on them — what the `aoa`
method does on a goal: the proof store looked up first, then
Sledgehammer, then the AoA agent, and the proof found written back into
the store — a task of its own, which may land after the report —, all
on AoA's own path with both store switches on; the driver and the
budget are what Isabelle's configuration gives AoA (`AoA_driver`,
Minilang's default budget), TAT setting neither. The report brings the
product: the method text and its two times in the store's
standard-machine form (the product above), which `hammer_or_AoA'`, the
entry beside `hammer_or_AoA`, returns beside the text. A run waiting
for its turn under the framework's bound on runs (CONSTRUCT_INTERACTION
§3.2) is `RUNNING`, and shows as any running one, `proving`. AoA's Python half, the remote
procedure `IsaMini.AoA`, is served by TAT's own process — the plugin's
package imports it —, so a question the search asks reaches the job
through the process's job table (CONSTRUCT_INTERACTION §3.3); the
questions themselves — AoA's `request` as a question to the owner, what
it asks and what the answer does, and AoA being told it runs under TAT
— are the AoA round's remainder (CONSTRUCT_INTERACTION §10). On success
the run attaches `Proof_Check.passed(node)` to the node and returns
`SUCCEEDED` with the product: a run that reaches its end saw no context
change (the default `_on_context_change` below), so the proof AoA
verified holds in the current context and the node is `proven` from
the run's settlement on. `_check()` answers whether a proof can be
constructed on the node as it stands — the framework's `can_start()`
having answered false while `job_operation_status()` is not `ready`
(CONSTRUCT_INTERACTION §3.2); a node
answered false for is skipped by `construct` and by automatic
construction, with no sentence of its own:

| the node | `_check()` |
| --- | --- |
| no proof — `NOT_STARTED` or `FAILED` | true |
| `SUCCEEDED`, the proof check `PASSED` | false: it is proven |
| `SUCCEEDED`, no proof check yet or one `RUNNING` | false: the proof is checked first |
| `SUCCEEDED`, the proof check `FAILED` | true |

`_on_context_change` is the default: the job is cancelled with
`CONTEXT_CHANGED` whenever the walk writes the status of an operation
the node's jobs depend on while it runs — leaving `ready`, or rewriting
it on a rerun; a block's ending, written after a child edit, is no such
operation when the goal opens on the beginning. Overriding it to
continue on the new context and repair the stored proof is the AoA
round's (OPEN_QUESTIONS §2). Its sentences name the node by its id and
so read the same for every class (the rest are the framework's defaults
from `title`):

| situation | |
| --- | --- |
| `finished_notification`, success | `` `theory_X.lemma_P` is proven. `` |
| `finished_notification`, failure | `` No proof of `theory_X.lemma_P` was found: `` + the message; with an assertion, `Failed to prove that <assertion>:` + the message |
| `failure_header` | `No proof was found:`; with an assertion, `Failed to prove that <assertion>:` |

The assertion is the hook `failed_assertion(shown_id)` of
`With_Proof_Obligations` — what the construction was to prove, the node
named by its shown id —, `None` by default, which leaves the two failure
sentences in their first form; a class that defines names its
obligation: `Define` the failed one (DEFINE.md §7), `Typedef` its set
(TYPEDEF.md §7).

`Proof_Check`: `title()` is `proof check`, `title(plural=True)` `proof
checks`. `make` is the default; `_start` calls
`TAT.Proof_Obligation.check` with the one pair of `goal_state` and the
stored `product` — the callback takes a list of goals, each with its
proof, and replays them in order, `Define`'s one per open obligation
(DEFINE.md §7) — and the job's `id`, once the framework has put the job
on the node (CONSTRUCT_INTERACTION §3.3). Its work, the Future task the
callback forks: the goal is `Proof.goal` of the `Proof.state` `goal_state` holds
— the goal the construction worked on; no Toplevel transition — and the
stored `product`, the text with its times, is replayed on it through a
function exported from AoA: the part of
`Proof_Store_AoA.store_hit_replay`
(`contrib/Isa-Mini/Agent/proof_store_AoA.ML`) that takes one record,
derives the replay limits from its times
(`Phi_Proof_Store.replay_limits`) and evaluates its text as a method on
the goal (`Phi_Sledgehammer_Solver.eval_prf_str`). TAT writes no limit
of its own; the check reads nothing from AoA's proof store, which only
the construction's AoA call reads and writes (`Proof_Job` above). A
`product` of the form `aoa_replay "<b64>"` is itself a method that
re-runs the recorded Minilang commands; one Sledgehammer found is a
plain method text such as `metis …`. The check and the construction
work on the same goal, the one `goal_state` holds. A theorem out is
`PASSED` and is discarded. No theorem — the method failing, subgoals
left, a limit exceeded — is `FAILED` with an empty message: the replay
reports a class of failure and no text, and the agent can only have
the proof constructed again; the callback reports it as one empty
error. Nothing in the work applies a Toplevel transition or forks a
proof, so it never enters Isabelle's execution table
(CONSTRUCT_INTERACTION §3.3). `_finished` is the default. The class
method `passed(node)` builds an instance with `outcome = PASSED` without
running, for `Proof_Job`. Its sentences: the failure block is the
header alone, its colon a period since no message follows; the
notification tells what to do next, and names several nodes in one
sentence or one list (CONSTRUCT_INTERACTION §3.4, §6):

```
The proof no longer holds.
The proof of `theory_X.lemma_P` no longer holds. Call `construct` to prove it again.
The proof of `theory_X.lemma_P`, of `theory_X.lemma_Q` and of `theory_X.lemma_R` no longer holds. Call `construct` to prove them again.
The following proofs no longer hold; call `construct` to prove them again:
  - theory_X.lemma_P
  - theory_X.lemma_Q
  - theory_X.lemma_R
  - theory_Y.lemma_S
```

For the nodes under automatic construction the failure starts the
proof construction at once (CONSTRUCT_INTERACTION §3.3), and the
notification says so in place of the instruction:

```
The proof of `theory_X.lemma_C` no longer holds, so its proof construction was started automatically; call `check_construct` before you exit.
The proof of `theory_X.lemma_C`, of `theory_X.lemma_G` and of `theory_X.lemma_K` no longer holds, so their proof constructions were started automatically; call `check_construct` before you exit.
The following proofs no longer hold, so their proof constructions were started automatically; call `check_construct` before you exit:
  - theory_X.lemma_C
  - theory_X.lemma_G
  - theory_X.lemma_K
  - theory_X.lemma_M
```

**The amend.** `goal_structure()`, abstract on `Proof_Obligation` —
which derives from `Node`, so that the abstraction is enforced and a
class that leaves it out fails at its first instantiation — is the
class's: the fields that decide the goal — its term, the assumptions
of the context it stands in, and the names that bind a fact a stored
proof may cite (THEOREM.md §4's criterion) — `english` aside, as the
structure sent to Isabelle —
`message()` carries it as its goal part, so what an amend compares is
what Isabelle receives —, a value compared with `==`, read from the
node's own authored fields alone. It holds every field that determines the
goal and no other: one more costs a proof construction whenever that
field changes; one less carries a proof onto a goal it was not found
for, which the proof check refuses unless its replay happens to pass —
and then a build's `by aoa` misses AoA's proof store, which keys a
proof by a hash of its goal. The framework's question
`_carries_job_from(old)` — asked by an amend's commit of a replacement
of the replaced node's own class, before anything moves, and answered
true to have the old job's image copied, the replay times with it
(CONSTRUCT_INTERACTION §3.1; MODULE_STRUCTURE §4.1, §4.2) —
`With_Proof_Obligations` answers with `old.goal_structure() ==
self.goal_structure()`; a class may override the answer, saying in its
own document why its goal is not decided by those fields alone. No
class's `gen` reads the replaced node for it. `Theorem`'s is its
statement, names included (THEOREM.md §4); `Typedef`'s is
`type_parameters` and `set` (TYPEDEF.md §4); `LiftDefinition`'s is
`type` and `is` (LIFT_DEFINITION.md §4).

**The mark.** `With_Proof_Obligations` overrides `mark` with two slots,
`(<status>, <proof>)`; the framework's `complete` never appears on the line. The
first slot is the class's word for `job_operation_status()`
(CONSTRUCT_INTERACTION §3.1), its
class attributes `valid_word` and `invalid_word` — `valid statement`
and `invalid statement` for `Theorem`, `valid definition` and `invalid
definition` for a class that defines (below) — and
`not evaluated`. The second, from `proof` and the proof
check:

| `proof` | proof check | word |
| --- | --- | --- |
| `NOT_STARTED` | | `proof not started` |
| `RUNNING` | | `proving` |
| `FAILED` | | `failed to prove` |
| `SUCCEEDED` | none | `unchecked proof` |
| `SUCCEEDED` | `RUNNING` | `proof checking` |
| `SUCCEEDED` | `PASSED` | `proven` |
| `SUCCEEDED` | `FAILED` | `bad proof` |

Under the invalid word the proof slot is left out. Under `not
evaluated` a stored proof is left out and the other two words written.
A running proof check exists only under `ready` — a stored check
survives under `not evaluated`, where the proof slot is left out — and a
running proof construction only there too, so `Theorem`'s line reads
one of eleven ways, plus the tags of CONSTRUCT_INTERACTION §6
(THEOREM.md §7).

A class that defines — `Typedef`, `LiftDefinition`, `QuotientType`,
`Define` — sets a third word, `unverified_word`, `unverified
definition`: its definition is valid only once its obligation is
discharged, so under `ready` the first slot is `valid_word` alone, the
proof slot left out, when the node owes no proof — its `owes_proof()`
false, `Define`'s with no open obligation (DEFINE.md §7), or `proof`
`SUCCEEDED` and the proof check `PASSED` — and `unverified_word` with
the proof slot's word while it does; `proven` never stands on such a
line, `valid definition` saying it. Such a line reads one of eleven
ways too, listed in the class's document. While it reads
`unverified_word`, the class's `owing_line()` — the framework's hook,
`None` on `Node` and so on `Theorem`; printed under the line after the
fields and the messages, before the jobs' blocks, wherever the node is
detailed (PRINT.md §2) — names what the node owes, in the sentence the
class's document gives: `Define`'s `The definition is unverified until
termination is proven.` (DEFINE.md §7).

**The emission.** `proof_text()` is the terminal proof the class writes
after its command: `by aoa` when `proof` is `SUCCEEDED` and the proof
check's stored outcome is `PASSED`, `sorry` otherwise — an unchecked
proof is written as `sorry`. A build of the file finds the proof in the
theory's proof store, `<short name>.proof-store` beside the file, where
the construction's AoA call recorded it — or, on a goal with no
subgoal, for which nothing is recorded, passes through `async_prove`'s
short circuit (above) — and replays it without
searching; the `aoa` method is `Minilang_AoA.Minilang_AoA`'s, which
`TAT_Std.TAT_Std` imports, the theory the plugin has every theory of the
forest import — it also registers the AoA tasks `Define`'s
constructions run under (PLUGIN_SYSTEM §1; SESSION_AND_THEORY §2;
DEFINE.md §7). The plugin's compile hook for AoA's proof stores,
`remove_proof_stores_of_no_tree` (COMPILATION.md §5), is `common.py`'s.

**The blocks.** The jobs' blocks — the framework prints them after
`print_fields`, when detailed, while the outcome is `FAILED`, unless an
operation the node's jobs depend on is an obstacle
(CONSTRUCT_INTERACTION §6) — are the failure blocks alone: the header
above and the message one level deeper (for example THEOREM.md §8).

What stays the class's: its two steps, `open_goal` and
`after_admission`; `record_from_evaluation` and the recorded fields it
sets; what the agent authors; `evaluation_callback`, the name of its
callback; `message()`; `goal_structure()`; `valid_word` and
`invalid_word`, and for a class that defines `unverified_word` and
`owing_line()`; its own `print_fields`; and, on a block, its other
operation, unless a base of the plugin gives it — `QuotientType`'s
ending is `Lifting_Closing`'s (§6). `Proof_Obligation`
stores no row of its own: `proof` and the check are the framework's
(CONSTRUCT_INTERACTION §3.1, ARCHITECTURE §4.1).

## 4. Shared `$defs`

A structure several classes use is defined once and merged by name
(PLUGIN_SYSTEM §4–§5): `STATEMENT_DEFS` in `std/statement.py`, with
its check and its writer, which are `Theorem`'s (THEOREM.md); the
other three here, in `common.py`. A class's `$defs` spreads only the
definitions its schema reaches (PLUGIN_SYSTEM §5).

| definition | holds | used by |
| --- | --- | --- |
| `STATEMENT_DEFS` | `Variable`, `LongStatement` (THEOREM.md §2) | `Theorem` |
| `TYPE_PARAMETER_DEFS` | `TypeParameter` | `Datatype`, `Record`, `Typedef` |
| `TYPE_MIXFIX_DEFS` | `TypeMixfix` | `Typedef`, `QuotientType`, and `Datatype` for a type's syntax |
| `MIXFIX_DEFS` | `Mixfix` | `Datatype` for a constructor's syntax, `LiftDefinition` for the function's, and `Notation` for a constant's |

`QuotientType`'s parameters take no sort (`Parse.type_args`): type
variables written bare, read by `type_variables_of`, which runs the
check below under the path `type_parameters[i]` (QUOTIENT_TYPE.md §4);
`TypeSynonym`'s, which `type_synonym` reads the same way, take the same
shape. The descriptions
the definitions below carry and the shared refusal sentences have
their one home here (§5): a test of the plugin pins the schema text
below against `common.py`'s constants, and the sentences against its
check.

`TYPE_PARAMETER_DEFS` — a type parameter, a type variable with an
optional sort:

```jsonc
{
  "TypeParameter": {
    "type": "object",
    "properties": {
      "name": { "type": "string" },
      "sort": { "type": "string", "description": "an Isabelle sort, such as linorder" }
    },
    "required": ["name"],
    "additionalProperties": false
  }
}
```

`common.py` holds its `gen`-time check — on the `ascii` form, a prime,
then an Isabelle identifier (§5), and no two the same — whose two
`InvalidField` sentences, pinned here, every class taking the
definition renders:

```
The field `type_parameters[0].name` must be a type variable, such as 'a.
The field `type_parameters[1].name` repeats `'a`.
```

and its writer, `type_parameters_text(parameters, keywords)`, which
every class taking the definition uses, for the file against the
theory's `keywords` and under `recall` against none: no parameter
writes nothing; one without a sort writes it bare, `'a`; otherwise
they are parenthesised and comma-separated, a sort after `::` through
`print_name` (SESSION_AND_THEORY §2) — bare when its `ascii` is an
Isabelle identifier not in the keyword set given, a string token
otherwise: `('a :: linorder, 'b)`, `('a :: "{zero, linorder}")`. An
empty `sort` is no sort.

`MIXFIX_DEFS` — Isabelle's mixfix annotation (`Parse.mixfix`) less the
`structure` form and a binder's own body priority:

```jsonc
{
  "Mixfix": {
    "description": "Isabelle's mixfix annotation",
    "anyOf": [
      { "type": "object", "description": "an infix operator, as in (infixr \"#\" 65)",
        "properties": {
          "form":     { "type": "string", "enum": ["infix", "infixl", "infixr"] },
          "symbol":   { "type": "string" },
          "priority": { "type": "integer" } },
        "required": ["form", "symbol", "priority"], "additionalProperties": false },
      { "type": "object", "description": "a binder, as in (binder \"∀\" 10)",
        "properties": {
          "form":     { "type": "string", "enum": ["binder"] },
          "symbol":   { "type": "string" },
          "priority": { "type": "integer" } },
        "required": ["form", "symbol", "priority"], "additionalProperties": false },
      { "type": "object", "description": "a template with one _ per argument, as in (\"⟨_, _⟩\") or (\"_ ! _\" [100, 101] 100)",
        "properties": {
          "form":                { "type": "string", "enum": ["mixfix"] },
          "template":            { "type": "string" },
          "argument_priorities": { "type": "array", "items": { "type": "integer" }, "description": "one per _; 0 when left out" },
          "priority":            { "type": "integer", "description": "the result's; 1000 when left out" } },
        "required": ["form", "template"], "additionalProperties": false }
    ]
  }
}
```

`TYPE_MIXFIX_DEFS` — a type's mixfix annotation: `Mixfix`'s infix and
general arms and no binder, which a type's mixfix refuses (`Bad mixfix
declaration`, mixfix.ML `syn_ext_types`):

```jsonc
{
  "TypeMixfix": {
    "description": "Isabelle's mixfix annotation for a type",
    "anyOf": [
      { "type": "object", "description": "an infix type constructor. Example: (infixr \"+\" 10)",
        "properties": {
          "form":     { "type": "string", "enum": ["infix", "infixl", "infixr"] },
          "symbol":   { "type": "string" },
          "priority": { "type": "integer" } },
        "required": ["form", "symbol", "priority"], "additionalProperties": false },
      { "type": "object", "description": "a template with one _ per type parameter. Example: (\"_⇩⊥\" [21] 21)",
        "properties": {
          "form":                { "type": "string", "enum": ["mixfix"] },
          "template":            { "type": "string" },
          "argument_priorities": { "type": "array", "items": { "type": "integer" }, "description": "one per _; 0 when left out" },
          "priority":            { "type": "integer", "description": "the result's; 1000 when left out" } },
        "required": ["form", "template"], "additionalProperties": false }
    ]
  }
}
```

`Mixfix` and `TypeMixfix` are unions told apart by `form`, which
`check_call` judges against the construct schema (MODULE_STRUCTURE
§4.4). `symbol` and `template` are `IsaTerm`s, normalised at `gen` for
newlines and tabs alone, since runs of spaces in a template are layout;
no `gen` refuses one. Whether a priority lies within 0 and 1000,
whether there are more argument priorities than the template has
arguments, and whether a type's template has one `_` per parameter, is
Isabelle's business at evaluation; fewer priorities are padded with 0.
Their writer, `mixfix_text(syntax)`, writes either annotation as
Isabelle does, the symbol or template as a string token
(COMPILATION.md §3): `(infixr "#" 65)`, `(binder "∀" 10)`, `("⟨_,
_⟩")`, a template's argument priorities in brackets and its result
priority after them, each when given, `("_ ! _" [100, 101] 100)`. The
ML receives that text, in `ascii` (`mixfix_wire`), and reads it with
Isabelle's own parser of the annotation, `Parse.mixfix`, under the
local theory's keywords — `Isabelle_Std/ML/TAT_Mixfix.ML`, structure
`TAT_Mixfix`, `read`, loaded by `TAT_Isabelle_Std.thy` before the
class files — so the command receives what the file carries; a text it
does not read whole is the operation's messages. `mixfix_text` takes
no keyword set: a symbol and a template are string tokens by
Isabelle's grammar; `type_parameters_text` writes a type variable bare
and a sort through `print_name`.

No type definition of a forest carries `(overloaded)`:
`TAT_Std.TAT_Std`, which every theory of a forest imports
(PLUGIN_SYSTEM.md §1), sets the configuration option
`typedef_overloaded`, which a theory inherits from its imports. Under
it Isabelle waives the one check that demands `(overloaded)`
(typedef.ML, `primitive_typedef`: a type with open dependencies on
overloaded definitions), for `typedef`, `quotient_type`, `record`,
`datatype` and `codatatype` alike; the dependencies are registered all
the same.
`Typedef`, `QuotientType` and `Record` run their commands with
`{overloaded = false}`; a type with open dependencies on overloaded
definitions is defined and emitted as any other, which the
Isabelle-backed tests of `Typedef` (`'a poly` on `zero`) and
`QuotientType` (`'a fract` on `idom`) pin.

Four helpers of `common.py` with no definition of their own
(QUOTIENT_TYPE.md §4–§5). The
type-parameter check above takes the field's path: `type_parameters_of`
runs it under `type_parameters[i].name`, and `type_variables_of(raw)`,
over type variables written bare, under `type_parameters[i]`, answering
`Type_Parameter`s without a sort and reading a stored image back. The
check, the defaults and the `morphisms` writer of a pair of function
names — `function_names_of`, `function_names` and `morphisms_clause` —,
the last two parameterised by the class's two default prefixes (`Rep_`
and `Abs_`, `rep_` and `abs_`): each given name an Isabelle identifier
(§5) not ending with an underscore, the two given names, as given,
different — a name equal to its default is a given name like any other
— its two `InvalidField` sentences, pinned here, the second naming the
later of two given names that are the same:

```
The field `rep_function_name` must be an Isabelle identifier: it starts with a letter and continues with letters, digits, underscores and primes ('), and does not end with an underscore.
The field `abs_function_name` repeats `list_of_fset`.
```

— the names with the defaults filled in, for the class's `message()`;
and the `morphisms` clause, each name through `print_name` against the
keywords, none when neither name was given. And
`type_head_text(parameters, name, syntax, keywords)`, a type's head as
the commands write it: `type_parameters_text` over the parameters, the
name through `print_name` against the keywords, and `mixfix_text`'s
annotation in parentheses when a syntax is given — `'a fset`, `('a, 'b)
t (infixr "+" 10)`. And the check that every declared type parameter is
used, for every class that declares type parameters (`Datatype`,
`Record`, `Typedef`, `QuotientType`): a lexical scan of the class's
Isabelle text in `ascii` — a datatype's constructor argument types, a
record's field types, a typedef's set, a quotient type's
`representation_type` — for type-variable tokens, the first parameter
not found refused on its path with the one `InvalidField` sentence,
pinned here:

```
The field `type_parameters[1]` declares `'b`, which is not used.
```

## 5. Conventions

- Whether a field carries a description is decided field by field, by
  whether its key and its place already say what it holds, and whether
  the class carries one by whether its name says what it defines:
  `kind` never does; `Datatype`'s class carries none and `Typedef`'s
  one (TYPEDEF.md §3); `Theorem`'s `name` and a constructor's `name`
  carry none, `premises[].name` keeps `binding name for the premise`
  (THEOREM.md §3), `selector` says what it extracts (DATATYPE.md §3).
  An example in a description is Isabelle's own text, never JSON, and
  stands only where the shape does not show the meaning.
- Every piece of Isabelle text is an `IsaTerm` (MODULE_STRUCTURE §4.3).
  The node's own name, and each authored field a class computes it from
  — `Datatype`'s `type_name`s — is `str` in the id grammar without
  hyphens — a letter, then letters, digits, underscores and primes, not
  ending in an underscore (MCP_SPECIFICATION §2), except
  `LiftingContext`'s `name`, written into no command, which is in the
  framework's name grammar and judged by the framework
  (LIFTING_CONTEXT.md §4); a type parameter's name is a type variable,
  shown in its refusal by Isabelle's own example, `such as 'a`, since
  it has no grammar text of its own; a `LiftingContext`'s `types` entry
  is an Isabelle identifier or identifiers joined by dots, each part
  judged as one (LIFTING_CONTEXT.md §4); every other name is an
  Isabelle identifier: on the `ascii` form of its
  normalised text, a letter or
  one of Isabelle's letter symbols, then letters, digits, underscores,
  primes, and `\<^sub>` before one of those — `Symbol_Pos.scan_ident`'s
  grammar over Isabelle's own letter list (`Symbol.is_letter_symbol`'s),
  judged in Python beside `IsaTerm` (`is_identifier` of
  `Isabelle_RPC_Host.unicode`), so `ε` and `x⇩1` pass and `h\<nat>`
  does not. A name Isabelle reads in a term — a variable's, a
  constructor's, a selector's — does not end with an underscore, since
  Isabelle marks internal names that way (`Name.is_internal`) and
  refuses one in a term (`Name.reject_internal`); a fact's name may.
- A refused name's sentence carries the framework's grammar text
  (`GRAMMARS`, RENDER_BASELINES §2): `InvalidName` renders it after the
  noun of its grammar, `InvalidField` after `must be`, the noun of what
  the field must be and a colon (THEOREM.md §4, DATATYPE.md §4).
- A class's own sentences — its descriptions, its `gen`'s refusals,
  the words of its mark — are in its own document, pinned by the
  baseline tests. Every shared sentence — a shared `$defs`
  description, a shared refusal sentence — has one home, §4, and one
  test pin there; a class document lists its own sentences alone and
  names that home for the rest. `NotInsideTheory`'s sentence is §1's.
  A framework exception's whole rendering is RENDER_BASELINES §2's own.
- A choice the evaluation makes between commands, or between a
  command's options — `Define`'s `definition`, `function (sequential,
  no_partials)` or `function` (DEFINE.md §6), `Typedef`'s
  `setup_lifting` (TYPEDEF.md §6), `LiftDefinition`'s `(code_dt)`
  (LIFT_DEFINITION.md §6) — is decided once per set of the
  authored fields it depends on, and recorded: the class's message
  carries the recorded choice, `None` until an evaluation has recorded
  one — on a fresh node, on the one an amend makes, after evaluations
  that all failed —; under `None` the
  evaluation decides — a first form tried and a second on its refusal,
  a command tried once and kept exactly when accepted, or a heuristic
  on the authored fields that decides where it can and, where it
  cannot, a probe run whose result decides — and records the choice;
  under a
  recorded choice it runs that alone, and a refusal is the operation's
  failure, never a switch. So the text the evaluation ran is the text
  the file carries, a re-evaluation under a changed context never
  changes it, and a decision that costs failed trials or a probe costs
  them once. A proof attempt whose success depends on the context —
  `Define`'s `pat_completeness auto` and `lexicographic_order` — is no
  such choice: it runs at every evaluation.

## 6. `Lifting_Closing`

`Lifting_Closing` is the plugin's `StdBlock` whose ending closes the
Lifting setup its beginning made: the base of a block whose beginning,
whenever it is `Ready`, has defined a type and made its Lifting setup,
the bundle `t.lifting` with it — `QuotientType` (QUOTIENT_TYPE.md).
`Typedef` takes it when it takes the block shape; what the ending does
for a `Typedef` whose `setup_lifting` Isabelle refused, `lifting` false
and no bundle made (TYPEDEF.md §6), is decided with that conversion.
`t` is the node's `name`, the type's name. The ending is the two
commands `lifting_update t.lifting` and `lifting_forget t.lifting`,
Isabelle's own discipline for a type whose construction is finished
(HOL's `Multiset.thy` and `FSet.thy` end so): `lifting_update` stores
into the type's lifting bundle every transfer rule of the context whose
relation mentions the type's, the setup's own and those `lift_definition`
declared inside the block, so that `context includes t.lifting`, which
`LiftingContext` is for (LIFTING_CONTEXT.md), restores them all; `lifting_forget` deletes
those rules from the context and the type's Quotient registration,
after which a `lift_definition` on the type is refused
(LIFT_DEFINITION.md §6) and `transfer` leaves the type alone. A class
takes it as its framework base, after the class that sets its
`job_operation`: `class QuotientType(Theory_Member,
Beginning_Proof_Obligation, Lifting_Closing)`; listed before that
class, it puts `StdBlock`'s abstract `_eval_beginning_opr` first, and
the class cannot be instantiated.

It defines the ending's two hooks together, as PLUGIN_SYSTEM §5
requires: `_eval_ending_opr` and `emit_ending`; a class on it writes
neither. The two commands' transitions and their two lines are one
function each of its two halves, which `LiftingContext`'s ending — `end`,
then the two commands for each type it opened — runs and writes too
(LIFTING_CONTEXT.md §5, §6).

**The evaluation.** `_eval_ending_opr` calls the callback
`TAT.Lifting_Closing.close` with the ending's two slots —
`operation_slots("ending")`, the slot after the last child and the
block's resulting slot (MODULE_STRUCTURE §4.1) — and the type's name.
The callback runs, as one operation into the resulting slot
(`TAT_Common_Nodes.operation`, MODULE_STRUCTURE §2.5), the two
transitions the commands make, each `Toplevel.local_theory NONE NONE`:
`Lifting_Setup.update_transfer_rules` then `Lifting_Setup.lifting_forget`
on the bundle's pointer — the key of the setup's restore data, which
the bundle's one attribute holds (lifting_setup.ML, `lifting_bundle`)
— read as the two commands read it (`pointer_of_bundle_name`, which
Isabelle does not export): the bundle `t.lifting` by its name in the
context, its attribute's argument read back; one function of
TAT_Lifting_Closing.ML answers the pointer, or none for a name no
bundle bears or a bundle that is no Lifting bundle, and
`LiftingContext`'s beginning asks it too (LIFTING_CONTEXT.md §6). It
answers the operation's messages: none, and the ending is `Ready`;
some, and it is `CannotEvaluate` with them, the framework copying the
ending's input through — in practice a proper interrupt's `Interrupt`
(MODULE_STRUCTURE §2.5), the bundle being the one the block's beginning
made. Inside a `Context` or `Locale` the two commands name the bundle as
the hand-written text does, `t.lifting`.

**The emission.** `emit_ending` writes one empty line, then
`lifting_update t.lifting` and `lifting_forget t.lifting`, each on its
own line at the block's indent, the bundle's name bare: `t`, in the id
grammar, is an identifier, so `t.lifting` is a long identifier, which
Isabelle's outer lexer reads as one token even where `t` alone is a
keyword of the theory (token.ML, `scan_token`, the longest match) —
after `quotient_type "term"`, `lifting_update term.lifting`; it returns
the block's indent.

Its Python half is `common.py`'s, its ML half
`Isabelle_Std/ML/TAT_Lifting_Closing.ML`, loaded by
`TAT_Isabelle_Std.thy` before the class files; the callback takes the
ending's two slots and `t` and answers the operation's messages, a list
of strings, as `TAT.Theory.end` answers its own (MODULE_STRUCTURE §3).
