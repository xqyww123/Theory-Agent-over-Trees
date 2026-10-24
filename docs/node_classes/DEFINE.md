# The `Define` node class

Status: proposed 2026-10-14, from the design discussion of 2026-10-10 to
2026-10-14 (the owner's rulings in the session `Define`); the
agent-facing wording below is the owner's, the mark's three states, the
owing line, the failure header and the layout of §8 ruled on 2026-10-17;
implemented on 2026-10-17.

A `Define` defines one or more constants by equations, and lets Isabelle
choose how: a plain `definition` when the equations are one non-recursive
equation, `fun` when the equations are a recursive function whose
pattern completeness and termination Isabelle proves by itself, and
`function (sequential, no_partials)` or plain `function` with
`termination` otherwise, where what Isabelle could not prove by itself is
a proof obligation (INDEX.md). It
never proves one in the tree (ARCHITECTURE §2.1): the evaluation admits
each obligation, the construction job, the proof construction, finds the
proofs — one AoA call per obligation, since each is proved at its own
command and replayed at its own `by aoa` —, the evaluation job, the proof
check, replays them in the current context, and the emitted theory
carries each as `by aoa`. It is a `Leaf` of the plugin `Isabelle_Std`
deriving from the plugin's `With_Proof_Obligations` (COMMON.md §3), the
base of the classes whose commands open proof obligations — `class
Define(With_Proof_Obligations, Leaf)` — and not from `Proof_Obligation` under
it, which serves one command opening one goal: `Define`'s commands
open up to two goals, on two commands, and its common forms open none.
Its jobs, `Define_Proof_Job` and `Define_Proof_Check`, derive from
`Proof_Obligation`'s `Proof_Job` and `Proof_Check` and run their work
once per obligation (§7). Its Python half is
`isabelle_theory_agent/std/define.py`, its ML half
`Isabelle_Std/ML/TAT_Define.ML`; the two AoA tasks it runs its
constructions under are registered in the plugin's theory `TAT_Std`,
which every theory of the forest imports (§7). Its agent-facing wording
lives here — the `description` texts of its construct schema (§3), the
sentences its `gen` renders, the words on its line and its owing line
(§7), and what its AoA calls tell the proof agent (§7) — pinned by the
baseline tests the way TYPEDEF.md's are.

One kind, `definition`, whatever the form: the three commands are not
the agent's choice but the evaluation's, recorded as `form` (§1, §6),
and the kind heads the id component: `definition_fib`, and for
several constants `definition_even_and_odd` (§9). `abbreviation` is a
class of its own, `Abbreviation`, not a form of `Define`: an
abbreviation defines no constant and opens no obligation (INDEX.md's row
is updated with this document).

## 1. Fields

| Field | Type | |
| --- | --- | --- |
| `english` | what is defined, `str` | authored |
| `constants` | `list[Variable_With_Syntax]` (§2; COMMON.md §4), non-empty: each a `name`, `IsaTerm`, in the id grammar without hyphens — a letter, then letters, digits, underscores and primes, not ending in an underscore (MCP_SPECIFICATION §2); one outside it is refused with the grammar's own sentence, as a `Typedef`'s `type_name` is —, an optional `type`, `IsaTerm`, and an optional `syntax`, `Mixfix` (COMMON.md §4) | authored |
| `equations` | `list[IsaTerm]`, non-empty: the defining equations, each one Isabelle equation | authored |
| `auto_reduction` | `bool`, required, no default: whether to add the defining equations to the system simplification set | authored |
| `form` | `definition` \| `function (sequential, no_partials)` \| `function`, or none until an evaluation has recorded one: the command the definition is made with — decided by the first evaluation that goes through and run again as recorded by every later one (§6); stored, since the commands are written from a loaded forest (COMPILATION.md §3), and read back with `rows.get`, so that a missing row is refused at start (`TAT_StartupError`) as a missing `equations` is. The file writes `fun` for `function (sequential, no_partials)` when no obligation is open (§5) | recorded |
| `completeness_method` | `str \| None`: under `form = function (sequential, no_partials)` or `function`, the method text that closed the pattern-completeness goal when the evaluation closed it by itself (§6), `None` when the goal stands open and its proof is the construction job's; `None` under `definition` | recorded |
| `termination_method` | `str \| None`: the same for the termination goal | recorded |
| `failed_obligation` | `pattern_completeness` \| `termination` \| `None`: the obligation the last proof construction did not prove, for the construction's sentences (§7); `None` until a run fails, and again when one succeeds; carried by an amend with the outcome (§7); stored | recorded by the construction |

What the last evaluation reported travels on the status the evaluation
hook returns, as for every class (COMPILATION.md §4): `CannotEvaluate
(messages)` when the defining command failed, `Ready` with no messages
when it went through. The two jobs' outcomes and the construction job's
automatic-construction setting are recorded by the framework
(CONSTRUCT_INTERACTION §3.2); `proof`, the construction job's outcome,
and its product — the proofs of the open obligations, one per
obligation (§7) — and the proof check's outcome are the framework's
(CONSTRUCT_INTERACTION §3.1). The two state slots, `completeness_state`
and `termination_state`, are `Define`'s own (§6).

An obligation is **open** when its command opened a goal the evaluation
did not close by itself: under `form = function (sequential,
no_partials)` or `function`, pattern completeness when
`completeness_method` is `None`, termination when `termination_method`
is `None`. The open obligations are what the construction job proves,
what the proof check replays, and what the mark counts (§7); under
`definition`, and before any evaluation, there is none.

## 2. The definition

A definition is its constants, each with a name, an optional type and an
optional syntax, its equations, and whether they reduce automatically:

```json
{
  "kind": "definition",
  "english": "The Fibonacci numbers",
  "constants": [{"name": "fib", "type": "nat ⇒ nat"}],
  "equations": ["fib 0 = 0", "fib (Suc 0) = 1", "fib (Suc (Suc n)) = fib n + fib (Suc n)"],
  "auto_reduction": true
}
```

and a pair of mutually recursive functions:

```json
{
  "kind": "definition",
  "english": "Parity of a natural number, by mutual recursion",
  "constants": [{"name": "even", "type": "nat ⇒ bool"}, {"name": "odd", "type": "nat ⇒ bool"}],
  "equations": ["even 0 = True", "even (Suc n) = odd n", "odd 0 = False", "odd (Suc n) = even n"],
  "auto_reduction": false
}
```

`kind`, `english`, `constants`, `equations` and `auto_reduction` are
required; a constant's `type` and `syntax` are optional and absent when
left out —
a type left out is inferred by Isabelle from the equations. Each
equation is one Isabelle equation, the constant applied to its argument
patterns on the left, as one line of a `fun`'s `where` clause reads
without its quotes and its `|`; the equations of several constants may
be given in any order, since Isabelle sorts them by constant. `gen`
normalises every piece of Isabelle text and `english` once, when the
construct is accepted: newlines become spaces and runs of whitespace one
space — in a syntax's `symbol` or `template` newlines and tabs alone,
since runs of spaces there are layout; printing, emission and
evaluation all use the stored text.

`constants[].type`, a syntax's `symbol` or `template`, and each equation
are `IsaTerm`s (MODULE_STRUCTURE §4.3); `constants[].name` and `english`
are `str`. `Mixfix` is shared through `MIXFIX_DEFS`, the plugin's
(COMMON.md §4): a constant's syntax, infix, binder or template, as a
`Datatype`'s constructor's is.

The class's construct schema:

```jsonc
{
  "type": "object",
  "description": "defines constants by (recursive) equations",
  "properties": {
    "kind":           { "const": "definition" },
    "english":        { "type": "string", "description": "what is defined, in English, as LaTeX text" },
    "constants":      { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/Constant" },
                        "description": "the constants defined; several for mutually recursive functions" },
    "equations":      { "type": "array", "minItems": 1, "items": { "type": "string" },
                        "description": "the defining equations, one Isabelle equation each, the constant applied to patterns on the left. Example: fib (Suc (Suc n)) = fib n + fib (Suc n)" },
    "auto_reduction": { "type": "boolean",
                        "description": "whether to add the defining equations to the system simplification set" }
  },
  "required": ["kind", "english", "constants", "equations", "auto_reduction"],
  "additionalProperties": false,
  "$defs": {
    "Constant": {
      "type": "object",
      "properties": {
        "name":   { "type": "string" },
        "type":   { "type": "string", "description": "the constant's type; left out, Isabelle infers it from the equations" },
        "syntax": { "$ref": "#/$defs/Mixfix" }
      },
      "required": ["name"],
      "additionalProperties": false
    },
    ...MIXFIX_DEFS   // Mixfix
  }
}
```

`Constant` is `Define`'s own definition, used by no other class; what
the node keeps of one is `common.py`'s `Variable_With_Syntax`, with its
wire and its writer `fixes_text`, and `MIXFIX_DEFS`, with its writer, is
COMMON.md §4's.

The class carries a description, its name not saying which commands it
stands for; `constants[].name` carries none (COMMON.md §5). The
schema's examples are Isabelle's own text, never JSON.

What the class does not take: the command — `definition`, `fun` or
`function` — and `termination`, which the evaluation decides and the
class emits (§5, §6); a measure or relation for the termination proof,
which the proof construction finds, TAT keeping proof knowledge out of
the tree (ARCHITECTURE §2.1); `(sequential, no_partials)`, which the
evaluation tries first and drops when the equations refuse it (§6), and
`(domintros)`; `primrec`, `primcorec` and `partial_function`, which are
not in the plugin (INDEX.md §3); names for the equations, which are
Isabelle's `fib.simps` and `fib_def`; `abbreviation`, the class
`Abbreviation`'s.

## 3. Descriptions

The class:

```
defines constants by (recursive) equations
```

`english`:

```
what is defined, in English, as LaTeX text
```

`constants` and `constants[].type`:

```
the constants defined; several for mutually recursive functions
the constant's type; left out, Isabelle infers it from the equations
```

`equations` and `auto_reduction`:

```
the defining equations, one Isabelle equation each, the constant applied to patterns on the left. Example: fib (Suc (Suc n)) = fib n + fib (Suc n)
whether to add the defining equations to the system simplification set
```

The descriptions of `Mixfix` and of its arms' fields are COMMON.md §4's,
pinned there alone.

## 4. `gen`

Where a `Define` stands is COMMON.md §1's; the framework checks it, not
`gen` (PLUGIN_SYSTEM §2).

`Define.gen` checks: each constant's `name` against §1's grammar
(`InvalidName` with `grammar` = `constant name`, the grammar of the
framework's `GRAMMARS` that `LiftDefinition` checks its name against too
(LIFT_DEFINITION.md §4), rendered as RENDER_BASELINES §2's line); no two
constants the same (`InvalidField` with the plugin's one sentence for a
name bound twice, COMMON.md §5); `constants` and `equations` non-empty,
which the schema's `minItems` refuses before `gen` (MODULE_STRUCTURE
§4.4). A sibling already bearing the node's id component is the
framework's `DuplicateName` (MCP_SPECIFICATION §2); any other clash of a
constant's name is Isabelle's at evaluation. Whether the equations
parse, whether their left sides are the constants applied to patterns,
whether the patterns are complete and the recursion terminates, and
whether a syntax is well-formed, are Isabelle's business at evaluation
(MODULE_STRUCTURE §4.1); what Isabelle rejects is an evaluation failure,
not an exception.

`Define`'s `goal_structure()` is `constants` — names, types and
syntaxes — and `equations`, each `IsaTerm` as its `ascii`: both goals
are made of them alone, a syntax included since it decides how an
equation is read, and a proof of either names no other field.
`_carries_job_from(old)` is `With_Proof_Obligations`'s,
`old.goal_structure() == self.goal_structure()` (COMMON.md §3): on an
amend, a changed constant or equation discards the stored proofs; a
changed `english` or `auto_reduction` keeps them. `message()` carries
`goal_structure()` as its goal part and `auto_reduction` beside it (§6).

The `InvalidField` sentence, for a constant listed twice:

```
The field `constants[1].name` repeats `even`.
```

## 5. Emission

The node emits, when its `can_emit` holds — `Define` keeps the
framework's default (COMPILATION.md §3) — the `text` line, then the
commands the recorded `form` names. With `form = definition`:

```
text ‹Definition twice. Twice a natural number.›
definition twice :: "nat ⇒ nat" where
  "twice n = n + n"
declare twice_def [simp]
```

with `form = function (sequential, no_partials)` and no obligation open,
written `fun`:

```
text ‹Definition fib. The Fibonacci numbers.›
fun fib :: "nat ⇒ nat" where
  "fib 0 = 0"
| "fib (Suc 0) = 1"
| "fib (Suc (Suc n)) = fib n + fib (Suc n)"
```

and with `form = function (sequential, no_partials)` and termination
open — pattern completeness closed by the evaluation, termination proven
by the construction —, the equations not simplification rules:

```
text ‹Definition sum_upto. The sum of the naturals from i to N.›
function (sequential, no_partials) sum_upto :: "nat ⇒ nat ⇒ nat" where
  "sum_upto i N = (if N < i then 0 else i + sum_upto (Suc i) N)"
  by pat_completeness auto
termination
  by aoa
declare sum_upto.simps [simp del]
```

- The `text` line's lead: `Definition` and the constants' names joined
  by `and`, `Definition even and odd.`; the line is COMMON.md §2's.
- The command: `definition` and plain `function` as recorded; `function
  (sequential, no_partials)` as recorded while an obligation is open, and
  `fun` when none is — both goals were closed by `fun`'s own methods,
  `pat_completeness auto` and `lexicographic_order`, and `fun` is exactly
  `function (sequential, no_partials)` with those two proofs (`fun.ML`,
  `gen_add_fun`), so it makes the same definition. So the command the
  file carries is the command the evaluation ran, and the file's
  obligations are the ones the evaluation saw (§6). Several constants
  are joined by `and` in the command's head, as Isabelle writes them.
- Each constant, as `fixes_text` writes it (COMMON.md §4): its name;
  `:: "T"` when `type` is given, nothing when
  not; its `syntax`, when given, after the type, in parentheses as
  Isabelle writes it, by the plugin's `mixfix_text` (COMMON.md §4):
  `(infixl "⊕" 65)`.
- `where`, then the equations, each on its own line indented two
  spaces, the second and later led by `| ` — `definition`'s one equation
  without a leader —, each as Isabelle's string token (COMPILATION.md
  §3).
- Under a function command other than `fun`, after the
  equations, the terminal proof of pattern completeness, indented two
  spaces: `by <completeness_method>`
  when the evaluation closed it, `by pat_completeness auto`; otherwise
  `Define`'s `proof_text` for the obligation (§7) — `by aoa` when the
  construction's proof of it stands checked, `sorry` otherwise. Then
  `termination` at the left margin and, indented two spaces, the
  terminal proof of termination the same way: `by lexicographic_order`
  when the evaluation closed it, `by aoa` or `sorry` otherwise.
- `declare twice_def [simp]` after a `definition` when `auto_reduction`
  is true, nothing when false; `declare fib.simps [simp del]`, one
  `<name>.simps` per constant, after a `fun` or after `termination` when
  `auto_reduction` is false, nothing when true: Isabelle makes a
  function's equations simplification rules and a definition's not, and
  the line is written only where the field says otherwise.
- Every piece of Isabelle text — a name, a type, an equation — is
  written through the theory's `print_name` (SESSION_AND_THEORY §2),
  `Token.print_name`'s rule: bare when its `ascii` is an Isabelle
  identifier (`is_identifier`, COMMON.md §5) that is not a keyword of
  the theory, as Isabelle's string token otherwise; an equation is
  always a string token; a symbol and a template as the writer writes
  them; a fact `<name>.simps`, a long identifier, which no keyword is,
  bare.
- The whole text in the `\<name>` form (`IsaTerm.ascii`); the file reads
  as Unicode in jEdit all the same.

A build of the file replays each `by aoa` from the theory's proof store,
`<short name>.proof-store` beside the file, where the construction's
AoA call recorded that obligation's proof under its own goal (§7); the
`aoa` method is `Minilang_AoA.Minilang_AoA`'s, which `TAT_Std` imports,
the theory the plugin has every theory of the forest import
(PLUGIN_SYSTEM §1; SESSION_AND_THEORY §2).

## 6. Evaluation

The evaluator makes the definition, closing each obligation Isabelle's
`fun` would close by itself and admitting the rest; it never searches
(ARCHITECTURE §3.6) and never runs the `text` command. It goes through
the ML interfaces: `Define`'s `_eval_opr` sends its callback,
`TAT.Define.evaluate`, the input slot, the two goal slots
`completeness_state` and `termination_state`, the resulting slot, and
its `message()`: the constants — each name, its type or none, its syntax
or none —, the equations and `auto_reduction`, each `IsaTerm` as its
`ascii`; a test pins the order. The callback's `on_interrupt` is
`Reraise`, its `timeout` `NONE`. The callback's whole run is one
`operation'` into the resulting slot (MODULE_STRUCTURE §2.5). Every
transition runs through `apply_transition` (MODULE_STRUCTURE §2.4); an
interrupt, and a Bug raised by the step's own code, propagate.

**The form.** The message carries the recorded `form`: `None` before
any evaluation, and on the node an amend makes — so the command is
decided once per set of equations, at the first evaluation that goes
through, and a
re-evaluation under a changed context never switches it. With `None`
the callback decides: it reads the equations in the input state's
context with the constants fixed at their types and syntax —
`Syntax.read_prop` after `Proof_Context.add_fixes`, a type left out
open — and takes `definition` when there is one constant and one
equation, the equation is an unconditional equality whose left side is
the constant applied to distinct variables or to nothing, and its right
side does not mention the constant; otherwise `function (sequential,
no_partials)`, and when that command refuses the equations — a pattern
that is no constructor, which `sequential` cannot order or complete; a
conditional equation —, `function` on the same equations, whose refusal
is the definition's failure with its messages. A read that fails is the
definition's failure, with Isabelle's messages. With a recorded `form`
the callback runs that command alone; its refusal is the definition's
failure. The two methods below are proof attempts, whose success depends
on the context: they run at every evaluation, whatever the mode.

**`definition`.** One transition, `Toplevel.local_theory NONE NONE` of
`Specification.definition_cmd` on the constant — its binding, its type
or none, its mixfix, `NoSyn` without `syntax`, otherwise the constructor
of Isabelle's `mixfix` datatype the form names, read by the plugin's
`TAT_Mixfix.fixes` (COMMON.md §4) — and the equation; then, when
`auto_reduction` is true, the `declare` transition on `<name>_def` with
`simp`, `Specification.theorems_cmd` as `Pure.thy` builds `declare`.
The transition refused — a right side that does not type, a free
variable — is the definition's failure. Both slots stay empty;
`completeness_method` and `termination_method` are `None`.

**`function (sequential, no_partials)` and `function`.** The transition
`Toplevel.local_theory_to_proof NONE NONE` of `Function.function_cmd` on
the constants and the equations — with `Function_Fun.fun_config`, the
configuration `fun` runs under, which the options `(sequential,
no_partials)` spell, or with `Function_Common.default_config` for plain
`function` —, its state put into `completeness_state`: the goal of
pattern completeness and compatibility open and no step taken; under
`sequential` Isabelle
has ordered the equations and completed the missing cases first, so that
`pat_completeness auto` closes the goal, under plain `function` the
equations stand as written and the goal is theirs to prove. The
transition refused — a constant mentioned that is not defined, a type
error — is the definition's failure, the node an obstacle (ARCHITECTURE
§3.3): no constant exists, so every later node naming it would fail
about it.
Then, on the open goal, the method `fun` runs, `pat_completeness auto`
(`fun.ML`, `gen_add_fun`: `Pat_Completeness.pat_completeness_tac` then
`auto_tac`), as a terminal proof. Closing the goal records
`completeness_method = "pat_completeness auto"` and empties the slot;
the method failing leaves the goal in the slot, `completeness_method`
`None`, and the goal is admitted — the half
of `sorry` that ends a toplevel goal, `Toplevel.end_proof
Proof.global_skip_proof`, as `Proof_Obligation` admits its goal
(COMMON.md §3). Either way the function is now defined, with its
recursion relation and `<name>_dom`. Then `termination`,
`Function.termination_cmd NONE`, into `termination_state`: the goal
`All <name>_dom`, that is `∀x. accp <name>_rel x`, open and no step
taken; on it the termination prover `fun` runs, `lexicographic_order`
(`Function_Common.termination_prover_tac`), as a terminal proof. Closing
the goal records `termination_method = "lexicographic_order"` and
empties the slot; the method failing leaves the goal in the slot,
`termination_method` `None`, and admits it. Last, when `auto_reduction`
is false, the `declare` transition on every `<name>.simps` with `simp
del`.

The slots are read only under `form = function (sequential,
no_partials)` and `function`, where an open obligation is one whose
method is `None` (§1).

**What the slots hold.** `completeness_state` and `termination_state`
are state slots beside the node's own (ARCHITECTURE §3.1,
MODULE_STRUCTURE §4.1), minted in its constructor as `Proof_Obligation`
mints `goal_state`
(COMMON.md §3), appended in `_states_inside()` and named in
`_slots_written_by`, so that they are deleted with the node and released
with its resulting state when the status goes to `not_evaluated`. Each
holds a `Toplevel.state` in which its goal stands open and no proof step
has been taken, exactly while the node's instant status is `ready` and
the obligation is open; the evaluation alone writes them, and empties
both when a rerun of a `ready` node fails, a rewrite that releases
nothing. The termination goal is the one the emitted `termination`
command opens: the function data the `relation` method reads are in its
context, as in a hand-written theory.

**The answer.** A failure anywhere empties both slots and writes no
state into the resulting slot; the callback answers the messages and
nothing to record, and `_eval_opr` returns `CannotEvaluate` with them:
the node is an obstacle, and its `form` and the two methods stay what
the last successful evaluation recorded, which `can_emit` keeps out of a
file (ARCHITECTURE §6.1). Otherwise the callback answers no messages
and the three records, `_eval_opr` stores them and returns `Ready` with
no messages: an open obligation is no notice; the mark and the owing
line under it say what the node owes (§7). At theory level these are the steps the hand-written
text takes; inside a `Context` or `Locale` the definition is made in
that context, as ARCHITECTURE §2 promises.

## 7. The jobs and the mark

**One proof per obligation.** An obligation is proved at its own
command and replayed, in a build, by its own `by aoa`, which looks the
proof up in AoA's proof store by a hash of its own goal; so the proofs
of the two obligations are two records in the store, and the
construction makes one AoA call per open obligation, pattern
completeness first.

**The construction.** `Define_Proof_Job` derives from
`Proof_Obligation`'s `Proof_Job` (COMMON.md §3): its title, its
sentences and its `_check()` are `Proof_Job`'s — the sentences naming
the failed obligation through `Proof_Job`'s hook (below) —, and
`_check()` answers false besides when no obligation is open — the common `Define` has
nothing to prove, and `construct` and automatic construction skip it
with no sentence of their own (CONSTRUCT_INTERACTION §3.2). `compulsory`
is `Proof_Job`'s, true; `Define`'s `_unfinished` answers `None` when the
last evaluation recorded no open obligation, and the framework's table
otherwise (CONSTRUCT_INTERACTION §3.1). Its `_run` calls
`TAT.Proof_Obligation.construct` once per open obligation, in command
order, with the obligation's slot, the call's setup (below) and the id
of the run's fork; each call is what `Proof_Job`'s one call is — AoA's
`hammer_or_AoA'` on the slot's goal, the proof store read and written on
AoA's own path, the driver and the budget Isabelle's configuration —
under the setup's task, with its declarations added to the goal's proof
context before the call. A call that fails ends the run: the outcome is
the call's failure, its message and kind (COMMON.md §3), the node recording which obligation failed,
`failed_obligation` (§1), for the job's sentences (below), and the
proofs of the obligations before it are not kept, which costs nothing
on the next run, since AoA's store serves them back without a search.
All calls passing, the run clears `failed_obligation`, attaches
`Define_Proof_Check.passed(node)` and returns `SUCCEEDED` with the
product: one proof per open obligation, under the obligation's name,
each the method text with its two times in the store's standard-machine
form, the proof `Proof_Job` returns for its one goal (COMMON.md §3).

The setup is `TAT.Proof_Obligation.construct`'s argument beside the slot
and the fork id — the call's task with its payload, its goal hint, its
tactic whitelist, and whether its goal is kept as it stands —, empty for
`Theorem` and `Typedef`, whose call stays `task = usual` with no
declaration (COMMON.md §3); the body makes the declarations on the goal's
proof context through the three ML entries AoA exports for it,
`Agent_Hint.add_goal_hint` (GOAL_HINTS.md §1), `MiniLang_Agent_AoA.add_tactics`
(TACTIC_DESIGN.md §5.1) and `Auto_Intro.add_hook` (AUTO_INTRO_DECISION.md
§2), for this call alone, so that none reaches the theory, its file, or
any other call. The setup's four parts, a call carrying up to four:

- *The task*, what the proof agent is told it is doing
  (contrib/Isa-Mini/IsaMini/AoA/docs/USER_OPERATIONS.md §4.2): one of
  two, `TAT.pattern_completeness` and `TAT.termination`, each a Python
  class of `define.py` registered with `@aoa_task`, both deriving from
  one base, a subclass of `StdTask` that overrides `task_initial` alone:
  for the major it returns the task's text given below, ending in a
  blank line; for a worker, `""`; the system prompt gets no text from
  the task. The payload is the constants' names
  and the equations in the `unicode` spelling. Both are registered on
  the ML side in `TAT_Std` — `register_task {python_packages =
  ["isabelle_theory_agent.std.define"]} {name = …}` —, the theory every
  theory of the forest imports, since AoA resolves a task's name in the
  goal's theory and refuses a second registration of a name
  (`agent_plugin.ML`): the registration cannot be overwritten by a later
  theory, and a library registering the same name fails loudly at
  load, which the `TAT.` prefix makes unlikely.
- *The goal hint* (GOAL_HINTS.md), for the termination call only, its
  one pattern `whole_prop "Wellfounded.accp _ _"`, the shape of the goal
  `All <name>_dom` — that is `∀x. accp <name>_rel x` —, whose `∀` the
  hint's walk opens; declared in the call's context alone, it can fire
  on no other goal. The pattern completeness call declares no hint: its
  goals share no shape. The text is below.
- *The tactic whitelist* (TACTIC_DESIGN.md): `relation` and
  `size_change` for the termination call, `pat_completeness` for the
  pattern completeness call, each with its interpretation below, all
  shown in the prompt. The `Tactic` operation exists in the call because
  the whitelist is non-empty, and in no other call of the conversation.
- *The goal kept as it stands* (AUTO_INTRO_DECISION.md), for both calls.
  Before the agent sees a goal that opens with a binder or a premise, AoA
  inserts an `Intro` step of its own, and on these two goals that step
  breaks the method each is for: `relation` and `size_change` resolve the
  goal against the termination rule, whose conclusion is `All <name>_dom`,
  and `pat_completeness` reads the cases from the goal's own premises.
  The call declares an auto-Intro hook that answers `No_Intro` on exactly
  one goal — the completeness goal in the pattern completeness call, the
  termination goal in the termination call —, compared with `aconv`, so
  that every other goal keeps its automatic Intro: the compatibility
  goals, which stand beside the completeness goal in the same call, and
  the goals a method derives, such as the recursive-call subgoal of
  `relation`. Nothing is shown for it: the agent sees the goal with its
  binders in place. A call that keeps its goal also runs without AoA's
  split segment, the preprocessing that rewrites every goal of a call
  whose largest goal is large (AUTO_INTRO_DECISION.md §8): the setup puts
  AoA's configuration option `AoA_auto_split` to false on the call's
  context, so that the goal the hook keeps is the goal the agent sees.

The texts the proof agent reads. The task's part of the initial
message, written for the major agent only — a worker's is the
framework's —, for a termination call on `sum_upto`, §5's example, whose
recursion `lexicographic_order` cannot see decreasing:

```
Your proof goal (given in `proof.yaml`) is to show the function `sum_upto` terminates
  sum_upto i N = (if N < i then 0 else i + sum_upto (Suc i) N)
Typically you should first try applying the `Tactic` operation with `relation` or `size_change`.
```

and for a pattern completeness call, the first and the last line:

```
Your proof goal (given in `proof.yaml`) is to show the equations of the function `sum_upto` cover every argument and agree where they overlap
Typically you should first try applying the `Tactic` operation with `pat_completeness`.
```

Several constants read `the functions `even` and `odd` terminate`.

The goal hint of the termination call:

```
The goal asserts the termination of `sum_upto`. You may try `Tactic` with `relation` or `size_change`.
```

The interpretations:

```
relation            `relation R` proves termination with a well-founded relation `R` that the recursive calls decrease. Typically `relation "measure f"` where `f :: arguments ⇒ nat` maps the tuple of the arguments to a number that every recursive call makes smaller, e.g. `measure (λ(xs, ys). length xs + length ys)` for `merge xs ys`. When one measure function is not enough, `relation "measures [f1, f2]"` compares by `f1` first and by `f2` on a tie, e.g. `measures [λ(m, n). m, λ(m, n). n]` for the Ackermann function `ack m n`. After applying the tactic, it leaves you to prove, for each recursive call, that the call's argument is below the left-hand side's argument in `R`, and that `R` is well-founded.
size_change         `size_change` proves termination by analyzing how the sizes of the arguments change in each recursive call. It either closes the goal or fails, leaving nothing to prove; on a large function it can take a while.
pat_completeness    `pat_completeness` proves the goal that the equations cover every argument, the one of the form `⋀P x. (x = … ⟹ P) ⟹ … ⟹ P`, by case analysis on the constructors of the argument types, following the patterns. It either closes that goal or fails; it fails when some constructor case is matched by no equation, or a pattern is not a constructor.
```

**The check.** `Define_Proof_Check` derives from `Proof_Check`: its
title, its sentences and `passed` are `Proof_Check`'s; its `_start`
calls `TAT.Proof_Obligation.check` once, with every open obligation's
slot and the proof the product holds for it — none when the product
lacks one — and the job's id; the callback replays them in order, each
what `Proof_Check`'s one goal gets: the proof replayed on the slot's
goal under limits derived from its times, no Toplevel transition
(COMMON.md §3). The outcome is `PASSED` when every replay yields its
theorem, `FAILED` with an empty message at the first that does not, a
missing proof among them; the failure block and the notification are
`Proof_Check`'s.

**Its sentences.** `Define` names what was not proved through the hook
`failed_assertion(shown_id)` (COMMON.md §3), so that the construction's
failure header and its failure notification both read `Failed to prove
that <assertion>:` with AoA's message after it; the assertion is
`failed_obligation`'s, the node by its id: `` function
`definition_sum_upto` terminates `` or `` `definition_sum_upto`'s
definitional equations cover every argument ``. When the agent refuted
the obligation both read its refutation sentence,
`refutation_sentence(shown_id)`, with the agent's own words after it: ``
Function `definition_sum_upto` may not terminate: `` or ``
`definition_sum_upto`'s definitional equations may not cover every
argument: ``. An amend whose commit carries the outcome carries
`failed_obligation` with it: `gen` reads the replaced node for it under
the commit's own question, `_carries_job_from` (COMMON.md §3). A
`FAILED` outcome on a node that records no `failed_obligation` — stored
before the carry — reads `Proof_Job`'s sentences. The
success notification and the titles are `Proof_Job`'s. The failure
block stands only while the failure is still owed: `failure_header` is
`None`, and nothing is printed, once an evaluation has recorded a `form`
under which the obligation the block names is closed — or, for a carried
failure naming none, under which no obligation is open —; the line's
mark still reads `failed to prove` while an obligation is open, and the
block returns with the next failed run.

**The mark.** `Define`'s `mark` is `With_Proof_Obligations`'s two slots,
`(<status>, <proof>)`, under the rule for a class that defines
(COMMON.md §3), its `owes_proof()` answering whether an obligation is
open: `valid definition` alone when the node owes no proof — no open
obligation, or `proof` `SUCCEEDED` and the proof check `PASSED` —;
`unverified definition` with the proof slot's word while it does;
`invalid definition` under `cannot_evaluate`. Its line reads one of
eleven ways, plus the tags of CONSTRUCT_INTERACTION §6:

```
(valid definition)
(unverified definition, proof not started)  (unverified definition, proving)         (unverified definition, failed to prove)
(unverified definition, unchecked proof)    (unverified definition, proof checking)  (unverified definition, bad proof)
(invalid definition)
(not evaluated)                             (not evaluated, proof not started)       (not evaluated, failed to prove)
```

**The owing line.** While the line reads `unverified definition`, the
node's owing line (PRINT.md §2) names what it owes, the open
obligations in command order: `The definition is unverified until
pattern completeness is proven.`, `The definition is unverified until
termination is proven.`, `The definition is unverified until pattern
completeness and termination are proven.`; under the other words there
is none.

**The emission.** `proof_text()` is the terminal proof the node writes
for an open obligation (§5): `by aoa` when `proof` is `SUCCEEDED` and
the proof check's stored outcome is `PASSED`, `sorry` otherwise —
`With_Proof_Obligations`'s rule, asked for each open obligation; the
check being one outcome for the node, both obligations are written `by
aoa` or neither.

## 8. What it prints

`print_fields` (PRINT.md §3) writes the definition, and only under
`Recall`; wherever it is called the framework writes the evaluation's
messages after it:

| mode | `print_fields` writes |
| --- | --- |
| `Out_Focus` | nothing |
| `Briefing` | not called |
| `Relative_Focus`, a focus | nothing |
| `Recall`, depth 0 | the constants, the equations, `english` |
| `Recall`, depth 1 and 2 | the constants, the equations |
| `Recall`, depth 3 | nothing |

The constants are one line: each name, `:: T` when typed, its syntax
when given, joined by `and`; the equations one per line, in the stored
text; both one level deeper than everything else under the node's line;
`english` follows at that level — all assembled from the stored text in
the `unicode` spelling, names bare, without a round trip to Isabelle; no
line carries a key.

```
  sum_upto :: nat ⇒ nat ⇒ nat
  sum_upto i N = (if N < i then 0 else i + sum_upto (Suc i) N)
The sum of the naturals from i to N
```

After the fields the framework writes the evaluation's messages
(PRINT.md §3–§4) and, while the node is unverified, its owing line (§7),
wherever the node is detailed. A focus in a quickview writes no field,
so there the owing line stands under the mark alone:

```
- definition_sum_upto (unverified definition, proof not started)
  The definition is unverified until termination is proven.
```

A node under `recall` that owes nothing — a `fun` —, and one whose
definition Isabelle refused, its right side naming a constant that does
not exist, with the framework's `Error:` block:

```
- definition_fib (valid definition)
    fib :: nat ⇒ nat
    fib 0 = 0
    fib (Suc 0) = 1
    fib (Suc (Suc n)) = fib n + fib (Suc n)
  The Fibonacci numbers
```

```
- definition_sum_upto (invalid definition)
    sum_upto :: nat ⇒ nat ⇒ nat
    sum_upto i N = (if N < i then 0 else i + suma (Suc i) N)
  The sum of the naturals from i to N
  Error:
    Extra variables on rhs: "suma"
    The error(s) above occurred in definition:
    "sum_upto i N ≡ if N < i then 0 else i + suma (Suc i) N"
```

The jobs' blocks have `Proof_Obligation`'s shape (COMMON.md §3), the
construction's header `Define_Proof_Job`'s (§7); a node under `recall`
whose termination proof the construction did not find, one whose
termination the agent refuted, and one whose stored proofs failed their
check:

```
- definition_sum_upto (unverified definition, failed to prove)
    sum_upto :: nat ⇒ nat ⇒ nat
    sum_upto i N = (if N < i then 0 else i + sum_upto (Suc i) N)
  The sum of the naturals from i to N
  The definition is unverified until termination is proven.
  Failed to prove that function `definition_sum_upto` terminates:
    Sledgehammer timed out on every prover; the relation the search tried does not decrease on the recursive call.
```

```
- definition_sum_upto (unverified definition, failed to prove)
    sum_upto :: nat ⇒ nat ⇒ nat
    sum_upto i N = (if N < i then 0 else i + sum_upto (Suc i) N)
  The sum of the naturals from i to N
  The definition is unverified until termination is proven.
  Function `definition_sum_upto` may not terminate:
    The first argument grows on every recursive call, and no bound on it follows from the equations.
```

```
- definition_sum_upto (unverified definition, bad proof)
    sum_upto :: nat ⇒ nat ⇒ nat
    sum_upto i N = (if N < i then 0 else i + sum_upto (Suc i) N)
  The sum of the naturals from i to N
  The definition is unverified until termination is proven.
  The proof no longer holds.
```

## 9. Id properties

None declared: a leaf's component is the last of every id, and the
framework's defaults stand (MCP_SPECIFICATION §2.1). The component is
`definition` and the constants' names joined by `_and_`,
`definition_even_and_odd`; a lone constant named `even_and_odd` bears
the same component as the pair and is refused beside it as a
`DuplicateName`.
