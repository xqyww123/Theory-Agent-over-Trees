# The `Typedef` node class

Status: proposed 2026-10-13; revised 2026-10-14 after two adversarial
reviews and the owner's rulings (ai-artifacts/review/TYPEDEF_REVIEW.md);
committed 2026-10-14; implemented 2026-10-15; the block shape — the
children, the ending that closes the subtype's Lifting setup, and the
block that refuses children when lifting could not be set up — settled
with the owner on 2026-10-20 (ai-artifacts/review/typedef_block/),
implemented 2026-10-21.

A `Typedef` defines a subtype: a new type whose values stand for the
elements of a non-empty subset of an existing type, with a function each
way between the two. Its command opens one proof obligation (INDEX.md),
that the subset is non-empty, which it discharges the way `Theorem`
does. It is a block: the command, with `setup_lifting` after its proof,
is its beginning; the `lift_definition`s on the subtype and the lemmas
whose proofs transfer it to the existing type are its children; its
ending closes the subtype's Lifting setup, `lifting_update
dlist.lifting` then `lifting_forget dlist.lifting`, Isabelle's own
discipline for a type whose construction is finished (HOL's `Dlist.thy`
and `Float.thy` do so). When lifting could not be set up for the
subtype (§6), the block refuses children, and its ending runs nothing
and writes nothing. It is a `StdBlock` of the plugin
`Isabelle_Std` deriving from the plugin's `Beginning_Proof_Obligation`
and `Lifting_Closing`, the plugin's `StdBlock` whose ending closes the
Lifting setup (COMMON.md §3, §6) — `class
Typedef(Beginning_Proof_Obligation, Lifting_Closing)` — whose job
classes `Proof_Job` and `Proof_Check` are `Proof_Obligation`'s and
depend on the beginning alone (CONSTRUCT_INTERACTION §3.1): a child
inserted, amended or deleted leaves the proof standing. Its Python half
is `isabelle_theory_agent/std/typedef.py`, its ML half
`Isabelle_Std/ML/TAT_Typedef.ML`; the ending's two halves are
`Lifting_Closing`'s (COMMON.md §6). Its agent-facing wording lives here
— the `description` texts of its construct schema (§3), the sentences
its `gen` renders, the notice of §6, the words on its line and its owing
line (§7) — pinned by the baseline tests the way DATATYPE.md's are; the
`children` description and the refusal sentence are `Lifting_Closing`'s
(COMMON.md §6).

One kind, `typedef`, which heads the id component: `typedef_dlist`; a
child's id carries it, `typedef_dlist.lift_definition_dl_rev` (§9).

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
| `lifting` | `bool`, or none until an evaluation has recorded one: whether `setup_lifting` follows the command — lifting set up for the subtype —, decided by the first evaluation that goes through and kept to by every later one (§6; COMMON.md §5); stored, since `setup_lifting` is written from a loaded forest (COMPILATION.md §3), and read back with `rows.get`, so that a missing row is refused at start (`TAT_StartupError`) as a missing `set` is — the class is born with the row, None-valued | recorded |
| `children` | the nodes inside the block, the framework's row (PLUGIN_SYSTEM §3; ARCHITECTURE §4.1) | — |

`syntax`, `rep_function_name` and `abs_function_name` left out are
stored as a None-valued row, so that every row of the class is read with
`rows.get` and any row missing is refused at start.

The node has two operations, the beginning and the ending
(MODULE_STRUCTURE §4.1). What the beginning's last evaluation reported
travels on its status, as for every class (COMPILATION.md §4):
`CannotEvaluate (messages)` when the definition failed, `Ready` when it
went through — with no messages, or with the one notice of §6 when
lifting could not be set up; the ending's likewise, `Ready` with no
messages or `CannotEvaluate (messages)` (§6). The two jobs' outcomes and
the construction job's automatic-construction setting are recorded by
the framework (CONSTRUCT_INTERACTION §3.2); `proof`, its product, the
proof check's outcome, the slot `goal_state` and the compulsory
construction job are `Proof_Obligation`'s (COMMON.md §3), bound to the
beginning (CONSTRUCT_INTERACTION §3.1). Its constructor takes the
parent, the input slot and its fields; `StdBlock` builds it with no
children and mints its slot before the ending (MODULE_STRUCTURE §4.1).

## 2. The definition

A subtype is a name, its type parameters, the subset of the existing
type its values stand for, and the names of the two functions between
the two types — `Rep`, from the subtype to the existing type, and
`Abs`, back — with an optional syntax, a mixfix annotation on the type;
and its children, the `lift_definition`s and lemmas inside the block:

```json
{
  "kind": "typedef",
  "english": "Lists without repetition",
  "type_parameters": [{"name": "'a"}],
  "type_name": "dlist",
  "set": "{xs :: 'a list. distinct xs}",
  "rep_function_name": "list_of_dlist",
  "abs_function_name": "dlist_of_list",
  "children": [
    {"kind": "lift_definition", "english": "Reversal of a list without repetition", "name": "dl_rev",
     "type": "'a dlist ⇒ 'a dlist", "is": "rev"},
    {"kind": "lift_definition", "english": "The length of a list without repetition", "name": "dl_length",
     "type": "'a dlist ⇒ nat", "is": "length"}
  ]
}
```

`kind`, `english`, `type_name` and `set` are required; `type_parameters`
is optional and empty when left out; `syntax`, `rep_function_name` and
`abs_function_name` are optional and absent when left out — a function
name left out is Isabelle's default, `Rep_dlist` or `Abs_dlist`; an
empty `sort` is no sort; `children` is optional, as for every nesting
class (PLUGIN_SYSTEM §3), and contents come later through `edit` as
well — never into a block that refuses children (§6). A sort
constraint may be written on the parameter (`"sort": "zero"`) or inside
`set` (`'a::zero`), as Isabelle
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

What stands inside the block: a node whose class's `placement` names
`Typedef` in its `through` (PLUGIN_SYSTEM §2; this plugin's, COMMON.md
§1). The subtype's Lifting setup is open inside the block and closed at
its end (§6), so a `LiftDefinition` on the subtype stands here or inside
a `LiftingContext`, which opens the setup again (LIFTING_CONTEXT.md);
lemmas about the subtype proved by `transfer` likewise, since
`lifting_forget` deletes the subtype's transfer rules. A node that uses
the subtype by name alone — a `Datatype` with an `'a dlist` field, a
`Theorem` proved without `transfer` — needs no open setup, so the block
does not bound it: it stands wherever its class's `placement` admits it
(COMMON.md §1). A block whose `lifting` is recorded false (§6) refuses
children: a node placed inside it is refused with COMMON.md §6's
refusal sentence — at the edit once `lifting` is recorded false, at the
node's first own operation when it was placed before (RENDER_BASELINES
§2, §3).

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
                           "description": "the name of the function that sends a representation in the existing type back to the value of the subtype it represents; Abs_ followed by the type name when left out. Example: dlist_of_list" },
    // COMMON.md §6's description
    "children":          { "type": "array", "items": { "$ref": "#/$defs/Construct" },
                           "description": "lift_definitions and lemmas whose proofs transfer the defined type to its representation type. Outside this block the defined type is opaque — its representation is closed to lift_definition and the transfer tactic — unless a lifting_context opens it again" }
  },
  "required": ["kind", "english", "type_name", "set"],
  "additionalProperties": false,
  "$defs": { ...TYPE_PARAMETER_DEFS, ...TYPE_MIXFIX_DEFS }   // TypeParameter, TypeMixfix
}
```

`TYPE_PARAMETER_DEFS` and `TYPE_MIXFIX_DEFS`, the two definitions the
schema refers to, with their checks and writers, are COMMON.md §4's;
`#/$defs/Construct` is the framework's (PLUGIN_SYSTEM §4).

The class carries a description, its name alone not saying what the
type is made of; `kind` and `type_name` carry none (COMMON.md §5).
The schema's examples are Isabelle's own text, never JSON.

What the class does not take: `(overloaded)` — the forest's theories
have `typedef_overloaded` set once, in TAT_Std.thy (COMMON.md §4), so
no `typedef` carries the option; the name of the
theorem `type_definition_dlist`, which Isabelle fixes; `setup_lifting`'s
optional reflexivity and parametricity theorems; the bundle
`dlist.lifting`, which `setup_lifting` names; `lifting_update
dlist.lifting` and `lifting_forget dlist.lifting`, which the ending
writes (§5).

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

`children`'s description is COMMON.md §6's, pinned there alone; the
descriptions of `TypeParameter.sort`, of `TypeMixfix` and of its arms'
fields are COMMON.md §4's, pinned there alone.

## 4. `gen`

Where a `Typedef` stands is COMMON.md §1's; the framework checks it, not
`gen` (PLUGIN_SYSTEM §2).

`Typedef.gen` checks: `type_name` against §1's grammar (`InvalidName`
with `grammar` = `type name`, RENDER_BASELINES §2's fifth form); the
type parameters by the shared check (COMMON.md §4): each `name` a type
variable, no two the same; each type parameter used in `set`, the
plugin's shared check (COMMON.md §4); `rep_function_name` and
`abs_function_name` through the plugin's shared check of a pair of
function names (COMMON.md §4) — each given name an Isabelle identifier
(COMMON.md §5) not ending with an underscore (COMMON.md §5's clause on
internal names), and the two given names, as given, not the same
(`InvalidField`); a given name equal to the field's default, `Rep_dlist`
or `Abs_dlist` (§2), is a given name like any other, written into the
`morphisms` clause as given (§5). A given name that clashes with the
other field's default — `Abs_dlist` as `rep_function_name` with
`abs_function_name` left out — is Isabelle's refusal when `open_goal`
runs the command (§6). A sibling already bearing the node's id component
is the framework's `DuplicateName` (MCP_SPECIFICATION §2); any other
clash of the type's name is Isabelle's at evaluation. Whether `set`
parses and has a set type, whether every type variable in it is a
parameter, and whether the mixfix annotation is well-formed with one `_`
per parameter, are Isabelle's business at evaluation (MODULE_STRUCTURE
§4.1); what Isabelle rejects is an evaluation failure, not an exception.
The children are the framework's: built by their own classes' `gen`s
and placed under the node (MODULE_STRUCTURE §4.2).

`Typedef`'s `goal_structure()` (COMMON.md §3) is `type_parameters` and
`set`, each `IsaTerm` as its `ascii`: the goal, `∃x. x ∈ S`, is made of
them alone, and a proof of it names neither the type nor the two
functions. On an amend, a changed `set` or type parameter discards the
stored proof; a changed `type_name`, function name, `syntax` or
`english` keeps it, and so do the children, which the amend's
replacement inherits (MODULE_STRUCTURE §4.2) — the replacement, a fresh
node, deciding `lifting` again at its first evaluation (§6).

The `InvalidField` sentences — the type parameters', the unused
parameter's and the function names' — are COMMON.md §4's, pinned there
alone (COMMON.md §5).

## 5. Emission

The node emits, when its `can_emit` holds — `Typedef` keeps the
framework's default, both stored statuses `Ready` (COMPILATION.md §3) —
the beginning: the `text` line, the definition with its proof, when the
recorded `lifting` is true `setup_lifting`, then one empty line when the
block has children; the children in order, one empty line between
siblings, at the block's own indent, the framework's (COMPILATION.md
§3); the ending: one empty line, then the two commands that close the
subtype's Lifting setup — nothing at all when `lifting` is false:

```
text ‹Lists without repetition.›
typedef 'a dlist = "{xs :: 'a list. distinct xs}"
  morphisms list_of_dlist dlist_of_list
  by aoa
setup_lifting type_definition_dlist

text ‹Reversal of a list without repetition.›
lift_definition dl_rev :: "'a dlist ⇒ 'a dlist" is rev by aoa

text ‹The length of a list without repetition.›
lift_definition dl_length :: "'a dlist ⇒ nat" is length by aoa

lifting_update dlist.lifting
lifting_forget dlist.lifting
```

and, with no child and `rep_function_name` alone given, then with a
syntax and no function name given, then one whose lifting could not be
set up (§6):

```
text ‹Polynomials, as their coefficient sequences.›
typedef 'a poly = "{f :: nat ⇒ 'a::zero. ∀⇩∞ n. f n = 0}"
  morphisms coeff Abs_poly
  by aoa
setup_lifting type_definition_poly

lifting_update poly.lifting
lifting_forget poly.lifting
```

```
text ‹A type with an error value added.›
typedef 'a errorable ("_⇩⊥" [21] 21) = "UNIV :: 'a option set"
  by aoa
setup_lifting type_definition_errorable

lifting_update errorable.lifting
lifting_forget errorable.lifting
```

```
text ‹Finite maps from naturals to naturals, as a type of their own.›
typedef fm = "UNIV :: (nat, nat) fmap set"
  by aoa
```

- The `text` line: `english` alone, no lead (COMMON.md §2).
- The head — the type parameters, the name, the syntax — is the
  plugin's `type_head_text` (COMMON.md §4): the parameters before the
  name, none writing the name alone, `typedef dlist =`, one without a
  sort bare, `typedef 'a dlist =`, otherwise parenthesised and
  comma-separated, a sort after `::` as `print_name` writes it (below),
  `typedef ('a :: zero, 'b) t =`, `typedef ('a :: "{zero, linorder}",
  'b) t =` (`type_parameters_text`); the name through the theory's
  `print_name` (below); the `syntax`, when given, after the name and
  before `=`, in parentheses as Isabelle writes it (`mixfix_text`):
  `(infixr "+" 10)`, `("_⇩⊥" [21] 21)`.
- `set` after `=`, through the theory's `print_name` (below).
- The `morphisms` line, indented two spaces, when either function name
  was given, the one left out written as its default; no line when
  neither was: the plugin's shared writer of the clause (COMMON.md §4).
  The head, the set and this clause are assembled by one private helper
  of typedef.py, which §8's line uses too, given the keyword set to
  write against.
- The terminal proof, `by aoa` or `sorry`, indented two spaces, is
  `Proof_Obligation`'s `proof_text()` (COMMON.md §3); the `aoa` method's
  import is the plugin's (PLUGIN_SYSTEM §1; SESSION_AND_THEORY §2).
- `setup_lifting type_definition_dlist` at the block's indent, the
  theorem named after `type_name`, when the recorded `lifting` is true
  (§6), nothing otherwise: it sets the Lifting and Transfer packages up
  for the type, so that `lift_definition` can define its functions and
  `transfer` can prove about it.
- The children's text is their own, each class's `emit`, at the block's
  indent: the block opens no Isabelle scope, and the file reads as the
  library's do.
- `lifting_update dlist.lifting` and `lifting_forget dlist.lifting`,
  each on its own line at the block's indent, the bundle's name —
  `type_name` followed by `.lifting` — written bare, when the recorded
  `lifting` is true; nothing, not even the empty line, when it is false:
  `Lifting_Closing`'s `emit_ending` (COMMON.md §6).
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

The beginning runs the definition, admits its goal, and sets lifting up
as the recorded `lifting` says; the ending closes the subtype's Lifting
setup, or runs nothing when none was set up; neither runs a proof
(ARCHITECTURE §3.6) nor the `text` command. Both go through the ML
interfaces.

**The beginning.** `Beginning_Proof_Obligation`'s `_eval_beginning_opr`
(COMMON.md §3) sends the class's callback — `evaluation_callback`,
`TAT.Typedef.evaluate` — the beginning's input slot, `goal_state`, the
beginning's resulting slot — the first child's input, or the slot before
the ending when there is no child (MODULE_STRUCTURE §4.1) — and its
`message()`: the definition — `type_name`, the syntax (absent when left
out), the two function names with the defaults filled in, then
`goal_structure()` — the type parameters with their sorts, and `set` —
whole, as its goal part (§4), each `IsaTerm` as its `ascii` — and the
recorded `lifting`, `None` until an evaluation has recorded one
(COMMON.md §5); a test pins the order, as THEOREM.md's does. The
callback is built by `TAT_Proof_Obligation` (COMMON.md §3) from
`Typedef`'s two steps: `open_goal`, the `typedef` command's transition,
yielding nothing; `after_admission`, the `setup_lifting` transition
under the recorded `lifting`, yielding `lifting`. What the two steps
yield `_eval_beginning_opr` hands the class's `record_from_evaluation`
(COMMON.md §3).

`Typedef`'s `open_goal` builds the `typedef` command's transition and
runs it — the shape of `begin_theory`, through `apply_transition` — no
proof step:

```
Toplevel.local_theory_to_proof NONE NONE (fn lthy =>
  Typedef.typedef_cmd {overloaded = false} (name, parameters, mixfix) set (SOME bindings) lthy)
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

The command runs with the option off: the forest's theories have
`typedef_overloaded` set (COMMON.md §4), and a type with open
dependencies on overloaded definitions, §5's `poly`, is accepted
without it. The transition refused — `apply_transition` answering
`Refused` with Isabelle's messages: a `set` that is no set, `Not a set
type`; a free variable in it, `Illegal variables in representing set`;
a type variable not among the parameters; a name the command declares
already taken, `Duplicate constant declaration` — is the step's
failure with those messages. The goal `∃x. x ∈ S`, open
and no step taken, goes into `goal_state`, where the proof construction
and the proof check find their goal.

`Typedef`'s `after_admission` runs, as the recorded `lifting` says, the
one transition `setup_lifting type_definition_dlist` makes,
`Toplevel.local_theory NONE NONE` of `Lifting_Setup.setup_by_typedef_thm
Lifting_Setup.default_config` on the theorem `type_definition_dlist`,
read by `Proof_Context.get_fact_single` under `type_definition_` before
`type_name` — the lookup by name that the command's own
`Attrib.eval_thms` makes, with no attribute to apply. With no `lifting`
recorded the transition is tried once: Isabelle accepting it, `lifting`
is true and the state is the one after it; Isabelle refusing it —
`apply_transition` answering `Refused` with its messages; an interrupt,
and a Bug of the step's own, propagate instead — `lifting` is false and
the state is the admitted one, the refusal's messages dropped, the
definition standing, Isabelle having accepted the typedef. With
`lifting` recorded true the transition runs, and Isabelle refusing it is
the definition's failure with its messages (COMMON.md §5): the text the
evaluation ran is the text the file carries. With `lifting` recorded
false nothing runs, and the state is the admitted one. A refusal's
causes are Lifting's: a
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
representing set`, like any other failure; inside a `Locale`, its
Lifting setup as LOCALE.md §6 says.

A failure anywhere is `Proof_Obligation`'s (COMMON.md §3): `goal_state`
is emptied and no state is written into the beginning's resulting slot,
the callback answers the messages and nothing to record, and the
beginning's status is `CannotEvaluate` with them: the node is an
obstacle, its children have no context and are `not_evaluated`, the
ending is `Ready` by the framework's copy of the block's input to its
result when the walk goes on past the block (ARCHITECTURE §3.3), and
`lifting` stays what the last successful evaluation recorded, or none,
which `can_emit` keeps out of a file (ARCHITECTURE §6.1). Otherwise the
status is `Ready` with the messages `Typedef`'s `record_from_evaluation`
answers once it has set `lifting`: none when `lifting` is true, the one
notice when it is false —

```
Because of a limitation inside Isabelle, lift_definition cannot be used on this subtype.
```

— a constant of typedef.py, which the framework prints as a `Notice:`
block (PRINT.md §3); the mark (§7) is unchanged, the node owing nothing.
With `lifting` recorded false `Typedef`'s answer to `Lifting_Closing`'s
hook `is_lifting_setup_made()` is false — true while `lifting` is none
or true —, on which the block refuses children and its ending runs
nothing (COMMON.md §6). A child the block holds already is refused at
its first own operation, its status a `CannotEvaluate` carrying the
framework's refusal with COMMON.md §6's refusal sentence after it
(PLUGIN_SYSTEM §2; RENDER_BASELINES §3); a node placed inside the block
later is refused at the edit, as `ChildRefused` (RENDER_BASELINES §2).
The proof check and the proof construction, with their callbacks
`TAT.Proof_Obligation.check` and
`TAT.Proof_Obligation.construct`, are `Proof_Obligation`'s (COMMON.md
§3): the goal they work on has one subgoal, always.

**Inside the block.** The children run in order from the beginning's
resulting slot, each in the state the one before it left (ARCHITECTURE
§3.5), with the subtype's Lifting setup open: a `LiftDefinition` on the
subtype defines its function and declares its transfer rule, a `Theorem`
may be proved by `transfer`. A child's failure is the child's; it stops
the walk inside the block as a failure stops it anywhere (ARCHITECTURE
§3.3), and the ending runs when the walk reaches it. A child inserted,
amended or deleted invalidates what follows it in the block and the
ending, never the beginning, so the goal, `goal_state`, the proof and
the recorded `lifting` stand (CONSTRUCT_INTERACTION §3.1); an edit of
the node's own fields invalidates the block whole.

**The ending.** `Lifting_Closing`'s `_eval_ending_opr` (COMMON.md §6)
runs, from the slot after the last child into the block's resulting
slot, the two transitions `lifting_update dlist.lifting` and
`lifting_forget dlist.lifting` make while `is_lifting_setup_made()`
answers true, and nothing while it answers false; what they do to the
setup and to the children's transfer rules (§2), and the ending's
status and its refusal, are COMMON.md §6's.

## 7. The jobs and the mark

The proof construction, `Proof_Job`, the proof check, `Proof_Check`,
their callbacks, their sentences, and the two-slot mark `(<status>,
<proof>)` are `Proof_Obligation`'s (COMMON.md §3). `Typedef` names what
the construction was to prove through the hook `failed_assertion`
(COMMON.md §3), so that the failure header and the failure notification
both read, with AoA's message after it:

```
Failed to prove that `typedef_dlist`'s definitional set is non-empty:
```

and, when the agent refuted it, its refutation sentence,
`refutation_sentence` (COMMON.md §3), with the agent's own words after it:

```
`typedef_dlist`'s definitional set may be empty:
```

`Typedef`'s own words are
the three words of a class that defines: `valid_word`, `valid
definition`, alone when the proof stands; `unverified_word`, `unverified
definition`, with the proof's word while the node owes it; and
`invalid_word`, `invalid definition`, under `cannot_evaluate`. Its line
reads one of eleven ways, plus the tags of CONSTRUCT_INTERACTION §6:

```
(valid definition)
(unverified definition, proof not started)  (unverified definition, proving)         (unverified definition, failed to prove)
(unverified definition, unchecked proof)    (unverified definition, proof checking)  (unverified definition, bad proof)
(invalid definition)
(not evaluated)                             (not evaluated, proof not started)       (not evaluated, failed to prove)
```

While the line reads `unverified definition`, the node's owing line
(PRINT.md §2) says what it owes:

```
The definition is unverified until the set is proven non-empty.
```

The ending's status is not on the line: a refused ending shows as its
`Error:` block under a line whose first slot is `valid definition` or
`unverified definition` (PRINT.md §1), and the jobs run as before, the
beginning being the one operation they depend on (CONSTRUCT_INTERACTION
§3.1). In an ancestor's Recall summary (PRINT.md §2) the node is counted
by its own operations, not by its line: among the failed nodes while its
ending is refused; with its beginning `ready` and its ending not yet
run, under the title its `Unfinished` carries while its proof is
unfinished, and in no group once it is proven.

## 8. What it prints

`print_fields` (PRINT.md §3) writes the definition, and only under
`Recall`; wherever it is called the framework writes the two operations'
messages after it, then the owing line while the definition is
unverified (§7), then the failure blocks, then the children (PRINT.md
§2):

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
given no keyword set. `setup_lifting` is not printed: it is not
authored. The children are the framework's to print, one level deeper,
in the mode PRINT.md §2's table gives them; a block with none shows the
empty node's line — none under a block that refuses children (PRINT.md
§2).

```
'a dlist = "{xs :: 'a list. distinct xs}" morphisms list_of_dlist dlist_of_list
Lists without repetition
```

The evaluation's messages are the framework's to print (PRINT.md
§3–§4): an `Error:` block while an operation is an obstacle, a `Notice:`
block when the beginning's `Ready` carries the notice of §6; after them,
while the node is unverified, its owing line (§7). A node under `recall`
whose definition Isabelle refused — a predicate where a set is
expected:

```
- typedef_dlist (invalid definition)
  'a dlist = "distinct :: 'a list ⇒ bool" morphisms list_of_dlist dlist_of_list
  Lists without repetition
  Error:
    Not a set type: "'a list ⇒ bool"
    The error(s) above occurred in typedef "dlist"
  - lift_definition_dl_rev (not evaluated, proof not started)
    dl_rev :: "'a dlist ⇒ 'a dlist" is rev
  - lift_definition_dl_length (not evaluated, proof not started)
    dl_length :: "'a dlist ⇒ nat" is length
```

A node under `recall` whose definition went through, its proof found
and checked, but for which lifting could not be set up (§6) — it
refuses children, so no empty node's line stands under it:

```
- typedef_fm (valid definition)
  fm = "UNIV :: (nat, nat) fmap set"
  Finite maps from naturals to naturals, as a type of their own
  Notice:
    Because of a limitation inside Isabelle, lift_definition cannot be used on this subtype.
```

The same block when a `lift_definition` was submitted with it, refused
at its first own operation (§6; RENDER_BASELINES §3):

```
- typedef_fm (valid definition)
  fm = "UNIV :: (nat, nat) fmap set"
  Finite maps from naturals to naturals, as a type of their own
  Notice:
    Because of a limitation inside Isabelle, lift_definition cannot be used on this subtype.
  - lift_definition_fm_empty (invalid definition)
    fm_empty :: fm is fmempty
    Error:
      A node of kind `lift_definition` cannot stand inside `session_S.theory_T.typedef_fm`, a node of kind `typedef`. For technical reasons, this subtype does not support lifting; you cannot use the transfer tactic or lift_definitions on this type.
```

The jobs' blocks are `Proof_Obligation`'s (COMMON.md §3); a node under
`recall` whose stored proof failed its check:

```
- typedef_dlist (unverified definition, bad proof)
  'a dlist = "{xs :: 'a list. distinct xs}" morphisms list_of_dlist dlist_of_list
  Lists without repetition
  The definition is unverified until the set is proven non-empty.
  The proof no longer holds.
  - lift_definition_dl_rev (valid definition)
    dl_rev :: "'a dlist ⇒ 'a dlist" is rev
  - lift_definition_dl_length (valid definition)
    dl_length :: "'a dlist ⇒ nat" is length
```

## 9. Id properties

Omissible in both directions, as `QuotientType` is, with drop priority
1: its component goes after `Section`'s and with `Session`'s, the
outermost of the two first, before `Theory`'s (MCP_SPECIFICATION §2.1)
— the block is a scope to TAT and none to Isabelle, a child's qualified
name not carrying it, `X.dl_rev`. A child's id prints as short as the
forest allows, `lift_definition_dl_rev`, and is accepted with or without
the component; the node's own component, `typedef_dlist`, ends its own
id and is never dropped from it.
