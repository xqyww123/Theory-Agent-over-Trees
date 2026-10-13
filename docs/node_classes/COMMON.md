# What the classes of `Isabelle_Std` share

Status: proposed 2026-10-10, revised after the first review; under
review.

The plugin `Isabelle_Std` (MODULE_STRUCTURE §4.5) carries the node
classes of Isabelle's standard commands (INDEX.md). What they share is
this document's: the base every class derives from (§1), the `english`
field and its `text` line (§2), the base of the classes whose command
opens a proof obligation (§3), the `$defs` several classes merge (§4),
and the conventions their schemas and sentences follow (§5). Its
Python half is `isabelle_theory_agent/std/common.py`, its ML half
`Isabelle_Std/ML/TAT_Proof_Obligation.ML`. What a class makes of it is that
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
  its names into the file (`print_name`, SESSION_AND_THEORY §2).

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

`Proof_Obligation` serves one shape: a `Leaf` whose one command opens
exactly one goal, admitted as the operation's last transition. A class
of that shape whose command opens a proof obligation (INDEX.md) derives
from it before its framework base — `class Theorem(Theory_Member,
Proof_Obligation, Leaf)` — and `Proof_Obligation` derives from `Node`,
so that its abstract method is enforced. `Theorem` derives from it; `Typedef`,
`QuotientType`, `LiftDefinition`, `Interpretation` and `Sublocale` are
expected to, each confirming it in its own document; `Instantiation`,
whose goal opens on a `StdBlock`'s ending, decides in its own document
how it discharges its own, and extends `Proof_Obligation` then if it
uses it. Open, `Proof_Obligation`'s own, decided with the first of
`LiftDefinition`, `Interpretation` and `Sublocale` designed, on a
measurement of `Proof.global_skip_proof` on such a state, and answered
by a rule of `Proof_Obligation`, not a field of a class: a goal that
opens with no subgoal — `lift_definition`'s when Isabelle proves
respectfulness by itself (LIFT_DEFINITION.md), and `interpretation`'s,
`global_interpretation`'s and `sublocale`'s of a locale with no
assumption, which Isabelle's own library closes with `.`. What admitting
it does, whether a proof construction runs on it and, if none, what
`_unfinished`, `_check()` and the proof slot answer, and what
`proof_text()` writes, are the open parts (OPEN_QUESTIONS §1). Until
then `Proof_Obligation` serves a goal with at least one subgoal.

The tree holds no proof (ARCHITECTURE §2.1): every evaluation admits
the goal; the construction job, the proof construction, finds the
proof, which the evaluation job, the proof check, replays in the
current context, and which the file carries as `by aoa`. What
`Proof_Obligation` holds, and a class leaves to it:

**The product.** `proof` is the construction job's outcome
(CONSTRUCT_INTERACTION §3.1): `NOT_STARTED`, `RUNNING`,
`SUCCEEDED(product)` or `FAILED(message)`, `product` being the proof:
the method text AoA writes to its proof store, such as `(simp add: …)`
or `aoa_replay "…"`, with the two times of its replay — the thread's
CPU time and the wall time, in milliseconds, as AoA records them beside
a proof, in the standard-machine form its store holds — which the proof
check derives its limits from; it is stored. The proof check's outcome
— `RUNNING`, `PASSED`, `FAILED` — is read through the framework's
`check_outcome()`: `RUNNING` while a running proof check is on the
node, the stored check otherwise, which is cleared when a stored status
of the node leaves `ready`, when a proof construction starts, or when
another check takes its place, and by nothing else
(CONSTRUCT_INTERACTION §3.3, ARCHITECTURE §4.1). The mark, `_check()`,
`proof_text()` and the failure block read it there.

**The slot.** `goal_state`, a state slot beside the node's own
(ARCHITECTURE §3.1, MODULE_STRUCTURE §4.1), holds the `Toplevel.state`
in which the goal stands open and no proof step has been taken. It
holds a state exactly while the node's instant status is `ready`.
`Proof_Obligation` mints it in its `__init__`, from the parent's
`forest().conversation`, so that no class's `gen` or `from_store` mints
it and a loaded node's is empty, like its `state`; appends it in
`_states_inside()`, so that it is deleted with the node; and names it
in `_slots_written_by`, so that the framework releases it with the
node's resulting state when the status goes to `not_evaluated`. Only
the evaluation writes it, and empties it when a rerun of a `ready` node
fails, a rewrite that releases nothing.

**The evaluation.** `Proof_Obligation`'s `_eval_opr` calls the class's
own callback, named by its class attribute `evaluation_callback` —
`TAT.Theorem.evaluate` for `Theorem` — with the input slot,
`goal_state`, the resulting slot and the class's message, the result of
its `message()`: a public, synchronous hook returning its fields as
structure, each `IsaTerm` as its `ascii`, with `goal_structure()` as
its goal part (the amend, below). On the ML side the callback's body is
one call of `TAT_Proof_Obligation.evaluate`, an ML function, not
a callback: it takes the three slots and the class's own function from
the input state to the state with the goal open, whose result is
`Toplevel.state option * string list` — `NONE` with messages when the
command, or a check the class makes on the open goal, refuses the
input. It runs the function under `TAT_Common_Nodes.operation`
(MODULE_STRUCTURE §3), writes the state it yields into `goal_state`,
applies the half of `sorry` that ends a toplevel goal —
`Toplevel.end_proof Proof.global_skip_proof`, through
`apply_transition` — into the resulting slot, and answers the messages,
empty when it passed (`operation`'s rule). On any failure no state
is written into either slot and `goal_state` is emptied; an interrupt
and a `Bug` are re-raised. `_eval_opr` returns `CannotEvaluate
(messages)` on a failure — the node is an obstacle — and `Ready` with
no messages otherwise.

**The jobs.** `Proof_Job` and `Proof_Check` are `Proof_Obligation`'s
`construction_job_class` and `evaluation_job_class`, their callbacks
`TAT.Proof_Obligation.construct` and
`TAT.Proof_Obligation.check`.

`Proof_Job`: `title()` is `proof construction`, `title(plural=True)`
`proof constructions`; `compulsory` is true, so the node is finished
only when `proof` is `SUCCEEDED` and the proof check `PASSED`
(ARCHITECTURE §3.2, the framework's `_unfinished`). Its `_run` calls
`TAT.Proof_Obligation.construct` with `goal_state` and the id of the
run's fork (CONSTRUCT_INTERACTION §3.2), and waits for the report. The
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
having answered false off `ready` (CONSTRUCT_INTERACTION §3.2); a node
answered false for is skipped by `construct` and by automatic
construction, with no sentence of its own:

| the node | `_check()` |
| --- | --- |
| no proof — `NOT_STARTED` or `FAILED` | true |
| `SUCCEEDED`, the proof check `PASSED` | false: it is proven |
| `SUCCEEDED`, no proof check yet or one `RUNNING` | false: the proof is checked first |
| `SUCCEEDED`, the proof check `FAILED` | true |

`_on_context_change` is the default: the job is cancelled with
`CONTEXT_CHANGED` whenever the walk writes the node's status while it
runs — leaving `ready`, or rewriting it on a rerun. Overriding it to
continue on the new context and repair the stored proof is the AoA
round's (OPEN_QUESTIONS §2). Its sentences name the node by its id and
so read the same for every class (the rest are the framework's defaults
from `title`):

| situation | |
| --- | --- |
| `finished_notification`, success | `` `theory_X.lemma_P` is proven. `` |
| `finished_notification`, failure | `` No proof of `theory_X.lemma_P` was found: `` + the message |
| `failure_header` | `No proof was found:` |

`Proof_Check`: `title()` is `proof check`, `title(plural=True)` `proof
checks`. `make` is the default; `_start` calls
`TAT.Proof_Obligation.check` with `goal_state`, the stored `product`
and the job's `id`, once the framework has put the job on the node
(CONSTRUCT_INTERACTION §3.3). Its work, the Future task the callback
forks: the goal is `Proof.goal` of the `Proof.state` `goal_state` holds
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
class's: the fields that determine the goal — `Proof.goal`'s record,
the context it stands in included, so the names the command binds
there count — `english` aside, as the structure sent to Isabelle —
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
`Proof_Obligation` answers with `old.goal_structure() ==
self.goal_structure()`; a class may override the answer, saying in its
own document why its goal is not decided by those fields alone. No
class's `gen` reads the replaced node for it.

**The mark.** `Proof_Obligation` overrides `mark` with two slots, `(<status>,
<proof>)`; the framework's `complete` never appears on the line. The
first slot is the class's two words for its evaluation status, its
class attributes `valid_word` and `invalid_word` — `valid statement`
and `invalid statement` for `Theorem`, `valid definition` and `invalid
definition` for a class that defines — and `not evaluated`. The second, from `proof` and the proof
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
A running proof check exists only under the valid word — a stored check
survives under `not evaluated`, where the proof slot is left out — and a
running proof construction only there too, so the line reads one of
eleven ways, plus the tags of CONSTRUCT_INTERACTION §6; `Theorem`'s
eleven are THEOREM.md §7.

**The emission.** `proof_text()` is the terminal proof the class writes
after its command: `by aoa` when `proof` is `SUCCEEDED` and the proof
check's stored outcome is `PASSED`, `sorry` otherwise — an unchecked
proof is written as `sorry`. A build of the file finds the proof in the
theory's proof store, `<short name>.proof-store` beside the file, where
the construction's AoA call recorded it, and replays it without
searching; the `aoa` method is `Minilang_AoA.Minilang_AoA`'s, which the
plugin has every theory import (PLUGIN_SYSTEM §1; SESSION_AND_THEORY
§2). The plugin's compile hook for AoA's proof stores,
`remove_proof_stores_of_no_tree` (COMPILATION.md §5), is `common.py`'s.

**The blocks.** The jobs' blocks — the framework prints them after
`print_fields`, when detailed, while the outcome is `FAILED` and the
node is not an obstacle (CONSTRUCT_INTERACTION §6) — are the failure
blocks alone: the header above and the message one level deeper (for
example THEOREM.md §8).

What stays the class's: its command's transition and what the agent
authors; `evaluation_callback`, the name of its callback; `message()`;
`goal_structure()`; `valid_word` and `invalid_word`; and its own
`print_fields`. `Proof_Obligation`
stores no row of its own: `proof` and the check are the framework's
(CONSTRUCT_INTERACTION §3.1, ARCHITECTURE §4.1).

## 4. Shared `$defs`

A structure several classes use is defined once and merged by name
(PLUGIN_SYSTEM §4–§5): `STATEMENT_DEFS` in `std/statement.py`, with
its check and its writer, which are `Theorem`'s (THEOREM.md); the
other two here, in `common.py`.

| definition | holds | used by |
| --- | --- | --- |
| `STATEMENT_DEFS` | `Variable`, `LongStatement` (THEOREM.md §2) | `Theorem` |
| `TYPE_PARAMETER_DEFS` | `TypeParameter` | `Datatype`, `Record`, `Typedef` |
| `MIXFIX_DEFS` | `Mixfix` | `Datatype`, and `Notation` for a constant's syntax |

`TypeSynonym`'s and `QuotientType`'s parameters, which take no sort
(`Parse.type_args`), and a type's own syntax, which takes no binder, are
decided with those classes. Each class's document lists every
description its schema carries, the shared ones included (§5); a test
of the plugin pins the schema text below against `common.py`'s
constants.

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
then an Isabelle identifier (§5), and no two the same, the two
`InvalidField` sentences DATATYPE.md §4 pins — and its writer,
`type_parameters_text(parameters, spelling)`, which every class taking
the definition uses, for the file in `ascii` and under `recall` in
`unicode`: no parameter writes nothing; one without a sort writes it
bare, `'a`; otherwise they are parenthesised and comma-separated, a
sort in double quotes after `::`: `('a :: "linorder", 'b)`. An empty
`sort` is no sort.

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

`Mixfix` is a union told apart by `form`, which `check_call` judges
against the construct schema (MODULE_STRUCTURE §4.4). `symbol` and
`template` are `IsaTerm`s, normalised at `gen` for newlines and tabs
alone, since runs of spaces in a template are layout; no `gen` refuses
one. Whether a priority lies within 0 and 1000, and whether there are
more argument priorities than the template has arguments, is
Isabelle's business at evaluation; fewer are padded with 0. Its writer,
`mixfix_text(syntax, spelling)`, writes the annotation as Isabelle
does, the symbol or template in double quotes: `(infixr "#" 65)`,
`(binder "∀" 10)`, `("⟨_, _⟩")`, a general mixfix's argument priorities
in brackets and its result priority after them, each when given, `("_
! _" [100, 101] 100)`. Its ML decoding stays in `TAT_Datatype.ML` until
a second class takes it. The writers take the spelling alone and never
`print_name`: a type variable is written bare, a sort, a symbol and a
template in double quotes.

## 5. Conventions

- Whether a field carries a description is decided field by field, by
  whether its key and its place already say what it holds: `kind` and
  the class carry none; `Theorem`'s `name` and a constructor's `name`
  carry none, `premises[].name` keeps `binding name for the premise`
  (THEOREM.md §3), `selector` says what it extracts (DATATYPE.md §3).
  An example in a description is Isabelle's own text, never JSON, and
  stands only where the shape does not show the meaning.
- Every piece of Isabelle text is an `IsaTerm` (MODULE_STRUCTURE §4.3).
  The node's own name, and each authored field a class computes it from
  — `Datatype`'s `type_name`s — is `str` in the id grammar without
  hyphens — a letter, then letters, digits, underscores and primes, not
  ending in an underscore (MCP_SPECIFICATION §2); a type parameter's
  name is a type variable, shown in its refusal by Isabelle's own
  example, `such as 'a`, since it has no grammar text of its own; every
  other name is an Isabelle identifier: on the `ascii` form, a letter or
  one of Isabelle's letter symbols, then letters, digits, underscores,
  primes, and `\<^sub>` before a letter or digit, judged in Python
  beside `IsaTerm` with the symbol table's letter symbols
  (`get_LETTER_SYMBOLS()` of `Isabelle_RPC_Host.unicode`), so `ε` and
  `x⇩1` pass. A name Isabelle reads in a term — a variable's, a
  constructor's, a selector's — does not end with an underscore, since
  Isabelle marks internal names that way (`Name.is_internal`) and
  refuses one in a term (`Name.reject_internal`); a fact's name may.
- A refused name's sentence carries the framework's grammar text
  (`GRAMMARS`, RENDER_BASELINES §2): `InvalidName` renders it after the
  noun of its grammar, `InvalidField` after `must be`, the noun of what
  the field must be and a colon (THEOREM.md §4, DATATYPE.md §4).
- A class's sentences — its descriptions, the descriptions of the
  shared `$defs` it merges included, its `gen`'s refusals, the words of
  its mark — are in its own document, pinned by the baseline tests; a
  framework exception's whole rendering is RENDER_BASELINES §2's own.
