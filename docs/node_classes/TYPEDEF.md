# The `Typedef` node class

Status: proposed 2026-10-13; revised 2026-10-14 after two adversarial
reviews and the owner's rulings (ai-artifacts/review/TYPEDEF_REVIEW.md);
committed 2026-10-14. Implemented after NODE_CLASS_IMPLEMENTATION_PLAN.md
§2's step 7.

A `Typedef` defines a subtype: a new type whose values stand for the
elements of a non-empty subset of an existing type, with a function each
way between the two. Its one command opens one proof obligation
(INDEX.md), that the subset is non-empty, which it discharges the way
`Theorem` does: it is a `Leaf` of the plugin `Isabelle_Std` deriving
from the plugin's `Theory_Member` and `Proof_Obligation` (COMMON.md §1,
§3) — `class Typedef(Theory_Member, Proof_Obligation, Leaf)` — whose job
classes `Proof_Job` and `Proof_Check` are `Proof_Obligation`'s. Its
Python half is `isabelle_theory_agent/std/typedef.py`, its ML half
`Isabelle_Std/ML/TAT_Typedef.ML`. Its agent-facing wording lives here —
the `description` texts of its construct schema (§3), the sentences its
`gen` renders, the notice of §6, and the words on its line — pinned by
the baseline tests the way DATATYPE.md's are.

One kind, `typedef`, which heads the id component: `typedef_dlist`.

## 1. Fields

| Field | Type | |
| --- | --- | --- |
| `kind` | `typedef` | authored |
| `english` | what is defined, `str` | authored |
| `type_parameters` | `list[TypeParameter]` (COMMON.md §4), empty when there are none | authored |
| `type_name` | `str`, the node's name, in the id grammar without hyphens — a letter, then letters, digits, underscores and primes, not ending in an underscore (MCP_SPECIFICATION §2); one outside it is refused with the grammar's own sentence, as a `Datatype`'s is | authored |
| `syntax` | `TypeMixfix` (COMMON.md §4), optional | authored |
| `set` | the subset, `IsaTerm` | authored |
| `rep_function_name` | `IsaTerm`, optional; `Rep_` before `type_name` when left out | authored |
| `abs_function_name` | `IsaTerm`, optional; `Abs_` before `type_name` when left out | authored |
| `overloaded` | `bool`: whether the command carries `(overloaded)`, decided by the evaluation (§6); false until one has recorded it; stored, since the command is written from a loaded forest (COMPILATION.md §3), and read back with `rows.get`, so that a missing row is refused at start (`TAT_StartupError`) as a missing `set` is — the class is born with the row | recorded |
| `lifting` | `bool`: whether `setup_lifting` follows the command — Isabelle set lifting up for the subtype —, decided by the evaluation (§6); false until one has recorded it; stored and read back as `overloaded` is | recorded |

What the last evaluation reported travels on the status the evaluation
hook returns, as for every class (COMPILATION.md §4): `CannotEvaluate
(messages)` when the definition failed, `Ready` when it went through —
with no messages, or with the one notice of §6 when lifting could not be
set up. The two jobs' outcomes and the construction job's
automatic-construction setting are recorded by the framework
(CONSTRUCT_INTERACTION §3.2); `proof`, its product, the proof check's
outcome, the slot `goal_state` and the compulsory construction job are
`Proof_Obligation`'s (COMMON.md §3).

## 2. The definition

A subtype is a name, its type parameters, the subset of the existing
type its values stand for, and the names of the two functions between
the two types — `Rep`, from the subtype to the existing type, and
`Abs`, back — with an optional syntax, a mixfix annotation on the type:

```json
{
  "kind": "typedef",
  "english": "Lists without repetition",
  "type_parameters": [{"name": "'a"}],
  "type_name": "dlist",
  "set": "{xs :: 'a list. distinct xs}",
  "rep_function_name": "list_of_dlist",
  "abs_function_name": "dlist_of_list"
}
```

`kind`, `english`, `type_name` and `set` are required; `type_parameters`
is optional and empty when left out; `syntax`, `rep_function_name` and
`abs_function_name` are optional and absent when left out — a function
name left out is Isabelle's default, `Rep_dlist` or `Abs_dlist`; an
empty `sort` is no sort. A sort constraint may be written on the
parameter (`"sort": "zero"`) or inside `set` (`'a::zero`), as Isabelle
takes either. The node's name is `type_name`. `gen` normalises every
piece of Isabelle text and `english` once, when the construct is
accepted: newlines become spaces and runs of whitespace one space — in
a syntax's `symbol` or `template` newlines and tabs alone, since runs of
spaces there are layout; printing, emission and evaluation all use the
stored text.

`type_parameters[].name`, `type_parameters[].sort`, `set`,
`rep_function_name`, `abs_function_name` and a syntax's `symbol` or
`template` are `IsaTerm`s (MODULE_STRUCTURE §4.3); `type_name` and
`english` are `str`.

`TypeParameter` is shared through `TYPE_PARAMETER_DEFS` and `TypeMixfix`
through `TYPE_MIXFIX_DEFS`, both the plugin's (COMMON.md §4).

The class's construct schema:

```jsonc
{
  "type": "object",
  "description": "defines a subtype: a new type whose values stand for the elements of a non-empty subset of an existing type. Example: typedef 'a dlist = \"{xs :: 'a list. distinct xs}\", the subtype of lists without repetition",
  "properties": {
    "kind":              { "const": "typedef" },
    "english":           { "type": "string", "description": "what is defined, in English, as LaTeX text" },
    "type_parameters":   { "type": "array", "items": { "$ref": "#/$defs/TypeParameter" },
                           "description": "the parameters of the subtype; sorts are usually not specified" },
    "type_name":         { "type": "string" },
    "syntax":            { "$ref": "#/$defs/TypeMixfix" },
    "set":               { "type": "string", "description": "the subset defining the subtype" },
    "rep_function_name": { "type": "string",
                           "description": "the name of the function that sends a value of the subtype to its representation in the existing type; Rep_ followed by the type name when left out. Example: list_of_dlist" },
    "abs_function_name": { "type": "string",
                           "description": "the name of the function that sends a representation in the existing type back to the value of the subtype it represents; Abs_ followed by the type name when left out. Example: dlist_of_list" }
  },
  "required": ["kind", "english", "type_name", "set"],
  "additionalProperties": false,
  "$defs": { ...TYPE_PARAMETER_DEFS, ...TYPE_MIXFIX_DEFS }   // TypeParameter, TypeMixfix
}
```

`TYPE_PARAMETER_DEFS` and `TYPE_MIXFIX_DEFS`, the two definitions the
schema refers to, with their checks and writers, are COMMON.md §4's.

The class carries a description, its name alone not saying what the
type is made of; `kind` and `type_name` carry none (COMMON.md §5).
The schema's examples are Isabelle's own text, never JSON.

What the class does not take: `(overloaded)`, which is recorded (§6),
and the configuration option `typedef_overloaded`; the name of the
theorem `type_definition_dlist`, which Isabelle fixes; `setup_lifting`'s
optional reflexivity and parametricity theorems; `lifting_forget` and
`lifting_update`, which are not in the plugin (INDEX.md §3).

## 3. Descriptions

The class:

```
defines a subtype: a new type whose values stand for the elements of a non-empty subset of an existing type. Example: typedef 'a dlist = "{xs :: 'a list. distinct xs}", the subtype of lists without repetition
```

`english`:

```
what is defined, in English, as LaTeX text
```

`type_parameters`:

```
the parameters of the subtype; sorts are usually not specified
```

`set`, `rep_function_name` and `abs_function_name`:

```
the subset defining the subtype
the name of the function that sends a value of the subtype to its representation in the existing type; Rep_ followed by the type name when left out. Example: list_of_dlist
the name of the function that sends a representation in the existing type back to the value of the subtype it represents; Abs_ followed by the type name when left out. Example: dlist_of_list
```

The descriptions of `TypeParameter.sort`, of `TypeMixfix` and of its
arms' fields are COMMON.md §4's, pinned there alone.

## 4. `gen`

`Typedef.gen` calls `require_inside_theory` first (COMMON.md §1), then
checks: `type_name` against §1's grammar (`InvalidName` with `grammar` =
`type name`, RENDER_BASELINES §2's fifth form); the type parameters by
the shared check (COMMON.md §4): each `name` a type variable, no two the
same; each `rep_function_name` and `abs_function_name` given an Isabelle
identifier (COMMON.md §5) not ending with an underscore (COMMON.md §5's
clause on internal names) and not beginning with `Rep_` or `Abs_`, the
beginnings of the names a field left out takes (§2), and the two not
the same (`InvalidField`) — so that no given name is a default's. A
sibling already bearing the
node's id component is the framework's `DuplicateName`
(MCP_SPECIFICATION §2); any other clash of the type's name is Isabelle's
at evaluation. Whether `set` parses and has a set type, whether every type
variable in it is a parameter, and whether the mixfix annotation is
well-formed with one `_` per parameter, are Isabelle's business at
evaluation (MODULE_STRUCTURE §4.1); what Isabelle rejects is an
evaluation failure, not an exception.

`Typedef`'s `goal_structure()` (COMMON.md §3) is `type_parameters` and
`set`, each `IsaTerm` as its `ascii`: the goal, `∃x. x ∈ S`, is made of
them alone, and a proof of it names neither the type nor the two
functions. On an amend, a changed `set` or type parameter discards the
stored proof; a changed `type_name`, function name, `syntax` or
`english` keeps it.

The `InvalidField` sentences:

```
The field `rep_function_name` must be an Isabelle identifier: it starts with a letter and continues with letters, digits, underscores and primes ('), and does not end with an underscore.
The field `rep_function_name` must not begin with `Rep_` or `Abs_`.
The field `abs_function_name` binds `list_of_dlist` a second time.
```

The third names the later of two given names that are the same. The
type parameters' sentences are COMMON.md §4's, written once in
`common.py`. The grammar text after the colon is the framework's, the
one `InvalidName` renders for the grammars `fact name` and `type name`
(RENDER_BASELINES §2), written once and used by both (COMMON.md §5).

A parent outside a theory is refused with the plugin's
`NotInsideTheory`, whose sentence COMMON.md §1 pins.

## 5. Emission

The node emits, when its `can_emit` holds — `Typedef` keeps the
framework's default (COMPILATION.md §3) — the `text` line, the
definition with its proof and, when the recorded `lifting` is true,
`setup_lifting`:

```
text ‹Lists without repetition.›
typedef 'a dlist = "{xs :: 'a list. distinct xs}"
  morphisms list_of_dlist dlist_of_list
  by aoa
setup_lifting type_definition_dlist
```

and, with `overloaded` recorded true and `rep_function_name` alone
given, then with a syntax and no function name given:

```
text ‹Polynomials, as their coefficient sequences.›
typedef (overloaded) 'a poly = "{f :: nat ⇒ 'a::zero. ∀⇩∞ n. f n = 0}"
  morphisms coeff Abs_poly
  by aoa
setup_lifting type_definition_poly
```

```
text ‹A type with an error value added.›
typedef 'a errorable ("_⇩⊥" [21] 21) = "UNIV :: 'a option set"
  by aoa
setup_lifting type_definition_errorable
```

- The `text` line: `english` alone, no lead (COMMON.md §2).
- `(overloaded)` after the command when the recorded `overloaded` is
  true (§6), nothing otherwise.
- The type parameters, written before the name by the plugin's
  `type_parameters_text` (COMMON.md §4): none writes the name alone,
  `typedef dlist =`; one without a sort writes it bare, `typedef 'a
  dlist =`; otherwise they are parenthesised and comma-separated, a sort
  after `::` as `print_name` writes it (below): `typedef ('a :: zero, 'b)
  t =`, `typedef ('a :: "{zero, linorder}", 'b) t =`.
- The `syntax`, when given, after the name and before `=`, in
  parentheses as Isabelle writes it, by the plugin's `mixfix_text`
  (COMMON.md §4): `(infixr "+" 10)`, `("_⇩⊥" [21] 21)`.
- `set` after `=`, through the theory's `print_name` (below).
- The `morphisms` line, indented two spaces, when either function name
  was given, the one left out written as its default; no line when
  neither was. The head with its parameters and syntax, the set and
  this clause are written by one private helper of typedef.py, which
  §8's line uses too, given the keyword set to write against.
- The terminal proof, `by aoa` or `sorry`, indented two spaces, is
  `Proof_Obligation`'s `proof_text()` (COMMON.md §3); the `aoa` method's
  import is the plugin's (PLUGIN_SYSTEM §1; SESSION_AND_THEORY §2).
- `setup_lifting type_definition_dlist` at the left margin, the theorem
  named after `type_name`, when the recorded `lifting` is true (§6),
  nothing otherwise: it sets the Lifting and Transfer packages up for
  the type, so that `lift_definition` can define its functions and
  `transfer` can prove about it.
- Every piece of Isabelle text — a name, the set, a sort — is written
  through the theory's `print_name` (SESSION_AND_THEORY §2): bare when
  its `ascii` is an Isabelle identifier (`is_identifier`, COMMON.md §5)
  that is not a keyword of the theory, as Isabelle's string token
  (COMPILATION.md §3) otherwise — `UNIV` and `zero` bare, `"{xs :: 'a
  list. distinct xs}"`, `"open"` and `"0.5"` quoted; a type variable, a
  symbol and a template as the writers write them.
- The text in the `unicode` spelling; the file takes the `\<name>` form
  from the compile's conversion (COMPILATION.md §2) and reads as Unicode
  in jEdit all the same.

## 6. Evaluation

The evaluator runs the definition, admits its goal, and sets lifting
up; it never runs a proof (ARCHITECTURE §3.6) and never the `text`
command. It goes through the ML interfaces. `Proof_Obligation`'s
`_eval_opr` (COMMON.md §3) sends the class's callback —
`evaluation_callback`, `TAT.Typedef.evaluate` — the input slot,
`goal_state`, the resulting slot, and its `message()`: `type_name`, the
syntax (absent when left out), the two function names with the defaults
filled in, then `goal_structure()` — the type parameters with their
sorts, and `set` — whole, as its goal part (§4), each `IsaTerm` as its
`ascii`; a test pins the order, as THEOREM.md's does. The callback is
built by `TAT_Proof_Obligation` (COMMON.md §3) from `Typedef`'s two
steps: `open_goal`, the `typedef` command's transition and, on the open
goal, `TAT_Overloaded.needed` (COMMON.md §4), yielding `overloaded`;
`after_admission`, the `setup_lifting` transition, yielding `lifting`.
What the two steps yield `_eval_opr` hands the class's
`record_from_evaluation` (COMMON.md §3).

`Typedef`'s `open_goal` builds the `typedef` command's transition and
runs it — the shape of `begin_theory`, through `apply_transition` — no
proof step:

```
Toplevel.local_theory_to_proof NONE NONE (fn lthy =>
  Typedef.typedef_cmd {overloaded = true} (name, parameters, mixfix) set (SOME bindings) lthy)
```

`name` is `type_name` as a binding; `parameters` the type parameters as
Isabelle's parser hands them, each `(name, sort option)`; `mixfix`
`NoSyn` without `syntax`, otherwise the annotation as `mixfix_text`
writes it, in `ascii`, read by Isabelle's `Parse.mixfix` under the
local theory's keywords through the plugin's `TAT_Mixfix` (COMMON.md
§4) inside the local theory's function, as a `Datatype`'s syntax is;
`set` the `ascii` text, which
Isabelle reads; `bindings` `Typedef.make_morphisms` of the two function
names with the defaults filled in (§2), the bindings the command's own
syntax makes whether or not a `morphisms` clause is written.

The transition runs with `{overloaded = true}`, once. The option
switches off one check — that the type has no open dependency on an
overloaded definition (`typedef.ML`, `primitive_typedef`, the option's
one use) — and nothing else: the dependencies are registered before the
check whether or not it is set, so the state is the one the emitted
text (§5) reaches with or without `(overloaded)`. With the goal open,
the plugin's `TAT_Overloaded.needed` (COMMON.md §4) asks the state's
theory the question the check asks — whether the type's entry in the
definition table has open dependencies, `Defs.get_deps` — and
`overloaded` is its answer: true exactly when Isabelle would have
refused the command without the option. The configuration option
`typedef_overloaded` is not consulted: where a theory sets it, the
file carries an `(overloaded)` Isabelle does not need. The same helper
decides `Record`'s and `QuotientType`'s option, on the type each
defines through `Typedef.add_typedef`. The transition refused —
`apply_transition` answering `Refused` with Isabelle's messages: a `set`
that is no set, `Not a set type`; a free variable in it, `Illegal
variables in representing set`; a type variable not among the
parameters — is the step's failure with those messages, which never
demand `(overloaded)`. The goal `∃x. x ∈ S`, open and no step taken,
goes into `goal_state`, where the proof construction and the proof
check find their goal.

`Typedef`'s `after_admission` runs the one transition `setup_lifting
type_definition_dlist` makes, `Toplevel.local_theory NONE NONE` of
`Lifting_Setup.setup_by_typedef_thm Lifting_Setup.default_config` on
the theorem `type_definition_dlist`, read by
`Proof_Context.get_fact_single` under `type_definition_` before
`type_name` — the lookup by name that the command's own
`Attrib.eval_thms` makes, with no attribute to apply. Isabelle
accepting it, `lifting` is true and the state is the one after it.
Isabelle refusing it — `apply_transition` answering `Refused` with its
messages; an interrupt, and a Bug of the step's own, propagate instead
— `lifting` is false and the state is the admitted one, the refusal's
messages dropped. A refusal never makes the definition invalid,
Isabelle having accepted the typedef; its causes are Lifting's: a
representing type over a type constructor whose `quot_map` rule is
short of a premise, such as `fmap`, where
`Lifting_Term.prove_param_quot_thm` lets a bare `THM` through
(`lifting_term.ML`); a name `setup_lifting` declares already taken —
one of the thirteen facts it notes under the type's name, `domain`,
`rep_transfer`, `bi_total` and ten more, by the Rep function's name, or
`cr_dlist`, `pcr_dlist`, their `_def` facts or `Quotient_dlist` by an
earlier member of the theory; and a failure of its own
`define_pcr_cr_eq` (`lifting_setup.ML`). Nothing here depends on this
list being complete. At theory level these are the steps the
hand-written text takes; inside a
`Context` or `Locale` the definition is made in that context — the type
and the two functions global all the same, and a `set` naming the
context's parameters refused by Isabelle, `Illegal variables in
representing set`, like any other failure.

A failure anywhere is `Proof_Obligation`'s (COMMON.md §3): `goal_state` is
emptied and no state is written into the resulting slot, the callback
answers the messages and nothing to record, and `_eval_opr` returns
`CannotEvaluate` with them: the node is an obstacle, and its
`overloaded` and `lifting` stay what the last successful evaluation
recorded, which `can_emit` keeps out of a file (ARCHITECTURE §6.1).
Otherwise `_eval_opr` returns `Ready` with the messages `Typedef`'s
`record_from_evaluation` answers once it has set `overloaded` and
`lifting`: none when `lifting` is true, the one notice when it is false
—

```
Because of a limitation inside Isabelle, lift_definition cannot be used on this subtype.
```

— a constant of typedef.py, which the framework prints as a `Notice:`
block (PRINT.md §3); the mark (§7) is unchanged, the node owing
nothing. The proof check and the
proof construction, with their callbacks `TAT.Proof_Obligation.check`
and `TAT.Proof_Obligation.construct`, are `Proof_Obligation`'s
(COMMON.md §3): the goal they work on has one subgoal, always.

## 7. The jobs and the mark

The proof construction, `Proof_Job`, the proof check, `Proof_Check`,
their callbacks, their sentences, and the two-slot mark `(<status>,
<proof>)` are `Proof_Obligation`'s (COMMON.md §3). `Typedef`'s own are
`valid_word` and `invalid_word`: `valid definition` (`ready`) and
`invalid definition` (`cannot_evaluate`). Its line reads one of eleven
ways, plus the tags of CONSTRUCT_INTERACTION §6:

```
(valid definition, proof not started)  (valid definition, proving)         (valid definition, failed to prove)
(valid definition, unchecked proof)    (valid definition, proof checking)  (valid definition, proven)
(valid definition, bad proof)
(invalid definition)
(not evaluated)                        (not evaluated, proof not started)  (not evaluated, failed to prove)
```

## 8. What it prints

`print_fields` (PRINT.md §3) writes the definition, and only under
`Recall`; wherever it is called the framework writes the evaluation's
messages after it:

| mode | `print_fields` writes |
| --- | --- |
| `Out_Focus` | nothing |
| `Briefing` | not called |
| `Relative_Focus`, a focus | nothing |
| `Recall`, depth 0 | the definition, `english` |
| `Recall`, depth 1 and 2 | the definition |
| `Recall`, depth 3 | nothing |

The definition is one line: the type with its parameters and its
syntax as emitted (§5), `=`, the set, and `morphisms` with the two
names when either was given — assembled from the stored text, every
piece through `print_name` against no keyword (SESSION_AND_THEORY §2):
every name, an identifier, bare, a sort and the set quoted unless an
identifier, whatever keywords the theory recorded, without a round trip
to Isabelle; `english` follows at depth 0 alone; no line carries a key.
The line is the private helper's that writes the emitted text (§5),
given no keyword set. Neither `(overloaded)` nor `setup_lifting` is
printed: neither is authored.

```
'a dlist = "{xs :: 'a list. distinct xs}" morphisms list_of_dlist dlist_of_list
Lists without repetition
```

The evaluation's messages are the framework's to print (PRINT.md
§3–§4): an `Error:` block while the node is an obstacle, a `Notice:`
block when its `Ready` carries the notice of §6. A node under `recall`
whose definition Isabelle refused — a `set` that is a predicate, not a
set:

```
- typedef_dlist (invalid definition)
  'a dlist = distinct morphisms list_of_dlist dlist_of_list
  Lists without repetition
  Error:
    Not a set type: "'b list ⇒ bool"
    The error(s) above occurred in typedef "dlist"
```

A node under `recall` whose definition went through but for which
Isabelle could not set lifting up (§6):

```
- typedef_fm (valid definition, proven)
  fm = "UNIV :: (nat, nat) fmap set"
  Finite maps from naturals to naturals, as a type of their own
  Notice:
    Because of a limitation inside Isabelle, lift_definition cannot be used on this subtype.
```

The jobs' blocks are `Proof_Obligation`'s (COMMON.md §3); a node under
`recall` whose stored proof failed its check:

```
- typedef_dlist (valid definition, bad proof)
  'a dlist = "{xs :: 'a list. distinct xs}" morphisms list_of_dlist dlist_of_list
  Lists without repetition
  The proof no longer holds.
```

## 9. Id properties

None declared: a leaf's component is the last of every id, and the
framework's defaults stand (MCP_SPECIFICATION §2.1).
