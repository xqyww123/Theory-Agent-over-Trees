# The `QuotientType` node class

Status: proposed 2026-10-17 and revised the same day after its review
(ai-artifacts/review/quotient_type/QUOTIENT_TYPE_REVIEW.md); the
agent-facing wording below is the owner's (his rulings of 2026-10-16
and 2026-10-17) or COMMON.md's shared sentences under this class's
paths. The framework's `job_operation`, which
the class rests on, is committed (16c864e); the class, `Lifting_Closing`
(COMMON.md §6) and the shared checks and writers of COMMON.md §4 it
uses are implemented after `LiftDefinition` (LIFT_DEFINITION.md) and
after the framework step that has `StdBlock` mint its own slot before
the ending (MODULE_STRUCTURE §4.1).

A `QuotientType` defines a quotient type: a new type whose values are
the equivalence classes of an existing type under an equivalence
relation, with a function each way between the two — `quotient_type 'a
fset = "'a list" / "λxs ys. set xs = set ys"`, finite sets as lists up to
order and repetition. Its command opens one proof obligation (INDEX.md),
that the relation is an equivalence — a partial equivalence under
`partial` —, which it discharges the way `Theorem` does. It is a block:
the command is its beginning; the `lift_definition`s and the lemmas
whose proofs transfer the type to its representation type are its
children; its ending closes the type's Lifting setup, `lifting_update
fset.lifting` then `lifting_forget fset.lifting`, Isabelle's own
discipline for a type whose construction is finished (HOL's
`Multiset.thy` and `FSet.thy` end so). It is a `StdBlock` of the plugin
`Isabelle_Std` deriving from the plugin's `Theory_Member`,
`Beginning_Proof_Obligation` and `Lifting_Closing`, the plugin's
`StdBlock` whose ending closes the Lifting setup (COMMON.md §1, §3, §6)
— `class QuotientType(Theory_Member, Beginning_Proof_Obligation,
Lifting_Closing)` — whose job classes `Proof_Job` and `Proof_Check` are
`Proof_Obligation`'s and depend on the beginning alone
(CONSTRUCT_INTERACTION §3.1): a child inserted, amended or deleted
leaves the proof standing. Its Python half is
`isabelle_theory_agent/std/quotient_type.py`, its ML half
`Isabelle_Std/ML/TAT_Quotient_Type.ML`; the ending's two halves are
`Lifting_Closing`'s (COMMON.md §6). Its agent-facing wording lives here
— the `description` texts of its construct schema (§3), the sentences
its `gen` renders, and the words on its line — pinned by the baseline
tests the way TYPEDEF.md's are.

One kind, `quotient_type`, which heads the id component:
`quotient_type_fset`; a child's id carries it, `quotient_type_fset.lift_definition_fmember`
(§9).

## 1. Fields

| Field | Type | |
| --- | --- | --- |
| `kind` | `quotient_type` | authored |
| `english` | what is defined, `str` | authored |
| `type_parameters` | `Type_Parameter`s without a sort (COMMON.md §4), read by `type_variables_of` from type variables written bare and stored as their names; empty when there are none | authored |
| `type_name` | `str`, the node's name, in the id grammar without hyphens — a letter, then letters, digits, underscores and primes, not ending in an underscore (MCP_SPECIFICATION §2); one outside it is refused with the grammar's own sentence, as a `Typedef`'s is | authored |
| `syntax` | `TypeMixfix` (COMMON.md §4), optional | authored |
| `representation_type` | `IsaTerm`, the representation type, `'a list` for `fset` | authored |
| `equiv_relation` | `IsaTerm`, the equivalence relation on the representation type | authored |
| `partial` | `bool`: whether the relation is only a partial equivalence, the command's `partial:`; false when left out | authored |
| `rep_function_name` | `IsaTerm`, optional; `rep_` before `type_name` when left out, and a given name equal to that is stored as left out (§4) | authored |
| `abs_function_name` | `IsaTerm`, optional; `abs_` before `type_name` when left out, and a given name equal to that is stored as left out (§4) | authored |
| `overloaded` | `bool`: whether the command carries `(overloaded)`, decided by the evaluation (§6); false until one has recorded it; stored, since the command is written from a loaded forest (COMPILATION.md §3), and read back with `rows.get`, so that a missing row is refused at start (`TAT_StartupError`) as a missing `equiv_relation` is — the class is born with the row | recorded |
| `children` | the nodes inside the block, the framework's row (PLUGIN_SYSTEM §3; ARCHITECTURE §4.1) | — |

`syntax`, `rep_function_name` and `abs_function_name` left out — a
function name given as its default counting as left out (§4) — are
stored as a None-valued row and `partial` left out as false, so that
every row of the class is read with `rows.get` and any row missing is
refused at start.

The node has two operations, the beginning and the ending (MODULE_STRUCTURE
§4.1). What the beginning's last evaluation reported travels on its
status, as for every class (COMPILATION.md §4): `CannotEvaluate
(messages)` when the definition failed, `Ready` with no messages when it
went through; the ending's likewise, `Ready` with no messages or
`CannotEvaluate (messages)` (§6). The two jobs' outcomes and the
construction job's automatic-construction setting are recorded by the
framework (CONSTRUCT_INTERACTION §3.2); `proof`, its product, the proof
check's outcome, the slot `goal_state` and the compulsory construction
job are `Proof_Obligation`'s (COMMON.md §3), bound to the beginning
(CONSTRUCT_INTERACTION §3.1). Its constructor takes the parent, the
input slot and its fields; `StdBlock` builds it with no children and
mints its slot before the ending (MODULE_STRUCTURE §4.1).

## 2. The definition

A quotient type is a name, its type parameters, the representation
type its values are equivalence classes of, the relation that makes the
equivalence classes, and the names of the two functions between the two
types — `rep`, from the quotient type to a representative in the
representation type, and `abs`, from a value of the representation type
to its equivalence class — with an optional syntax, a mixfix annotation
on the type, and, when the relation is only a partial equivalence,
`partial`; and its children, the `lift_definition`s and lemmas inside
the block:

```json
{
  "kind": "quotient_type",
  "english": "Finite sets, as lists up to order and repetition",
  "type_parameters": ["'a"],
  "type_name": "fset",
  "representation_type": "'a list",
  "equiv_relation": "λxs ys. set xs = set ys",
  "rep_function_name": "list_of_fset",
  "abs_function_name": "fset_of_list",
  "children": [
    {"kind": "lift_definition", "english": "The empty finite set", "name": "fempty",
     "type": "'a fset", "is": "[]"},
    {"kind": "lift_definition", "english": "Membership", "name": "fmember",
     "type": "'a ⇒ 'a fset ⇒ bool", "is": "λx xs. x ∈ set xs"}
  ]
}
```

```json
{
  "kind": "quotient_type",
  "english": "The integers, as pairs of naturals up to a common summand",
  "type_name": "int",
  "representation_type": "nat × nat",
  "equiv_relation": "λ(a, b) (c, d). a + d = c + b"
}
```

```json
{
  "kind": "quotient_type",
  "english": "Rational numbers, as fractions with a non-zero denominator",
  "type_parameters": ["'a"],
  "type_name": "fract",
  "representation_type": "'a :: idom × 'a",
  "equiv_relation": "λ(a, b) (c, d). b ≠ 0 ∧ d ≠ 0 ∧ a * d = c * b",
  "partial": true
}
```

`kind`, `english`, `type_name`, `representation_type` and
`equiv_relation` are required; `type_parameters` is optional and empty
when left out; `syntax`, `rep_function_name` and `abs_function_name` are
optional and absent when left out — a function name left out is
Isabelle's default, `rep_fset` or `abs_fset`, and one given as that
default is stored as left out (§4); `partial` is optional and false
when left out; `children` is optional, as for every nesting class
(PLUGIN_SYSTEM §3), and contents come later through `edit` as well. The
node's name is `type_name`. The type parameters take no sort: the
command's own syntax takes none (`Parse.type_args`), and a sort
constraint is written inside `representation_type`, `'a :: idom × 'a`,
where `typedef` reads it and gives it to the parameter (typedef.ML,
`prepare_typedef`). `gen` normalises every piece of Isabelle text and
`english` once, when the construct is accepted:
newlines become spaces and runs of whitespace one space — in a syntax's
`symbol` or `template` newlines and tabs alone, since runs of spaces
there are layout; printing, emission and evaluation all use the stored
text.

`representation_type`, `equiv_relation`, `rep_function_name`,
`abs_function_name` and a syntax's `symbol` or `template` are
`IsaTerm`s (MODULE_STRUCTURE §4.3); each type parameter is a
`Type_Parameter` without a sort (COMMON.md §4); `type_name` and
`english` are `str`; `partial` is `bool`. `TypeMixfix` is shared
through `TYPE_MIXFIX_DEFS` (COMMON.md §4).

What stands inside the block: any theory member — the framework checks
no containment (PLUGIN_SYSTEM §3), and each class's `gen` judges its own
parent (COMMON.md §1). The type's Lifting setup is open inside the block
and closed at its end (§6), so a `LiftDefinition` on the type stands
here or inside a `LiftingContext`, the class, to be designed, for
`context includes fset.lifting begin … end`, which opens the setup again
(LIFT_DEFINITION.md §2); lemmas about the type proved by `transfer`
likewise, since `lifting_forget` deletes the type's transfer rules. A
member that uses the type by name alone — a `Datatype` with an `'a
fset` field, a `Theorem` proved without `transfer` — stands anywhere
after the block too.

The class's construct schema:

```jsonc
{
  "type": "object",
  "description": "defines a quotient type whose values are the equivalence classes of an existing type under an equivalence relation. Example: quotient_type 'a fset = \"'a list\" / \"λxs ys. set xs = set ys\"",
  "properties": {
    "kind":                { "const": "quotient_type" },
    "english":             { "type": "string", "description": "what is defined, in English, as LaTeX text" },
    "type_parameters":     { "type": "array", "items": { "type": "string" },
                             "description": "the parameters of the quotient type, each a type variable such as 'a; a sort constraint is written inside representation_type, as in \"'a :: idom × 'a\"" },
    "type_name":           { "type": "string" },
    "syntax":              { "$ref": "#/$defs/TypeMixfix" },
    "representation_type": { "type": "string", "description": "e.g., \"'a list\" in the above example" },
    "equiv_relation":      { "type": "string", "description": "e.g., \"λxs ys. set xs = set ys\" in the above example" },
    "partial":             { "type": "boolean", "description": "whether the relation is only a partial equivalence, proved as part_equivp instead of equivp; false when left out" },
    "rep_function_name":   { "type": "string",
                             "description": "the name of the function that sends a value of the quotient type to one of its representatives in the existing type; rep_ followed by the type name when left out. Example: list_of_fset" },
    "abs_function_name":   { "type": "string",
                             "description": "the name of the function that sends a value of the existing type to its equivalence class, a value of the quotient type; abs_ followed by the type name when left out. Example: fset_of_list" },
    "children":            { "type": "array", "items": { "$ref": "#/$defs/Construct" },
                             "description": "lift_definitions and lemmas whose proofs transfer the defined type to its representation type. Outside this block the defined type is opaque — its representation is closed to lift_definition and the transfer method — unless a lifting_context opens it again" }
  },
  "required": ["kind", "english", "type_name", "representation_type", "equiv_relation"],
  "additionalProperties": false,
  "$defs": { ...TYPE_MIXFIX_DEFS }   // TypeMixfix
}
```

`TYPE_MIXFIX_DEFS`, the one definition the schema refers to, with its
writer, is COMMON.md §4's; `#/$defs/Construct` is the framework's
(PLUGIN_SYSTEM §4). The type parameters are a list of strings and not
`TypeParameter`s, which carry a sort the command cannot take.

The class carries a description, its name alone not saying what the type
is made of; `kind` and `type_name` carry none (COMMON.md §5). The
schema's examples are Isabelle's own text, never JSON.

What the class does not take: `parametric`, the command's optional
parametricity theorem of the relation; `(overloaded)`, which is recorded
(§6), and the configuration option `typedef_overloaded`; the names
Isabelle fixes — the theorems `Quotient3_fset` and `fset_equivp`, the
relations `cr_fset` and `pcr_fset`, the bundle `fset.lifting`;
`lifting_update fset.lifting` and `lifting_forget fset.lifting`, which
the ending writes (§5).

## 3. Descriptions

The class:

```
defines a quotient type whose values are the equivalence classes of an existing type under an equivalence relation. Example: quotient_type 'a fset = "'a list" / "λxs ys. set xs = set ys"
```

`english`:

```
what is defined, in English, as LaTeX text
```

`type_parameters`:

```
the parameters of the quotient type, each a type variable such as 'a; a sort constraint is written inside representation_type, as in "'a :: idom × 'a"
```

`representation_type`, `equiv_relation` and `partial`:

```
e.g., "'a list" in the above example
e.g., "λxs ys. set xs = set ys" in the above example
whether the relation is only a partial equivalence, proved as part_equivp instead of equivp; false when left out
```

`rep_function_name` and `abs_function_name`:

```
the name of the function that sends a value of the quotient type to one of its representatives in the existing type; rep_ followed by the type name when left out. Example: list_of_fset
the name of the function that sends a value of the existing type to its equivalence class, a value of the quotient type; abs_ followed by the type name when left out. Example: fset_of_list
```

`children`:

```
lift_definitions and lemmas whose proofs transfer the defined type to its representation type. Outside this block the defined type is opaque — its representation is closed to lift_definition and the transfer method — unless a lifting_context opens it again
```

The descriptions of `TypeMixfix` and of its arms' fields are COMMON.md
§4's, pinned there alone.

## 4. `gen`

`QuotientType.gen` calls `require_inside_theory` first (COMMON.md §1),
then checks: `type_name` against §1's grammar (`InvalidName` with
`grammar` = `type name`, RENDER_BASELINES §2's fifth form); the type
parameters through `type_variables_of` (COMMON.md §4) — each a type
variable on its `ascii`, a prime, then an Isabelle identifier
(COMMON.md §5), and no two the same —; each type parameter used in
`representation_type`, the plugin's one check for a type parameter
declared and not used, shared by every class that declares type
parameters: a lexical scan of the field's `ascii` for type-variable
tokens, refusing the first parameter it does not find on the path
`type_parameters[i]` (`InvalidField`, COMMON.md §4); `rep_function_name`
and
`abs_function_name` through the plugin's shared check of a pair of
function names (COMMON.md §4; `Typedef`'s with `Rep_` and `Abs_`),
with `rep_` and `abs_` as its prefixes — each given name an Isabelle
identifier (COMMON.md §5) not ending with an underscore (COMMON.md §5's
clause on internal names), and the two given names not the same
(`InvalidField`); a given name equal to the field's default, `rep_fset`
or `abs_fset` (§2), is stored as the field left out — so that a field's
default is stored only as the field left out. A given name that clashes
with another — `abs_fset` as `rep_function_name` with
`abs_function_name` left out — is Isabelle's refusal at the admission
(§6). A sibling already bearing the node's id component is the
framework's `DuplicateName` (MCP_SPECIFICATION §2); any other clash of
the type's name is Isabelle's at evaluation. Whether
`representation_type` parses, whether every type variable in it is a
parameter, whether `equiv_relation` parses to a relation on it, whether
it has a free or a schematic variable, and whether the mixfix
annotation is well-formed with one `_` per parameter, are Isabelle's
business at evaluation (MODULE_STRUCTURE §4.1); what Isabelle rejects
is an evaluation failure, not an exception. The children are the
framework's: built by their own classes' `gen`s and placed under the
node (MODULE_STRUCTURE §4.2).

`QuotientType`'s `goal_structure()` (COMMON.md §3) is
`representation_type`, `partial` and `equiv_relation`, each `IsaTerm` as
its `ascii`: the goal, `equivp R` or `part_equivp R` on the
representation type, is made of them alone — a proof of it names neither
the type, nor its parameters, nor the two functions. On an amend, a
changed `representation_type`, `equiv_relation` or `partial` discards
the stored proof; a changed `type_name`, `type_parameters`, `syntax`,
function name or `english` keeps it, and so do the children, which the
amend's replacement inherits (MODULE_STRUCTURE §4.2).

The `InvalidField` sentences:

```
The field `type_parameters[0]` must be a type variable, such as 'a.
The field `type_parameters[1]` binds `'a` a second time.
The field `type_parameters[1]` declares `'b`, which is not used.
```

The first two are this class's, their path its own,
`type_parameters[i]`; their words are COMMON.md §4's type-parameter
sentences, rendered by `type_variables_of` (COMMON.md §4). The third is
COMMON.md §4's sentence for a type parameter declared and not used, the
one sentence of every class that declares type parameters, on the path
`type_parameters[i]` too. The function names' sentences are the shared
check's, pinned in COMMON.md §4.

A parent outside a theory is refused with the plugin's
`NotInsideTheory`, whose sentence COMMON.md §1 pins.

## 5. Emission

The node emits, when its `can_emit` holds — `QuotientType` keeps the
framework's default, both stored statuses `Ready` (COMPILATION.md §3) —
the beginning: the `text` line, the definition with its proof, then one
empty line when the block has children; the children in order, one
empty line between siblings, at the block's own indent, the
framework's (COMPILATION.md §3); the ending: one empty line, then the
two commands that close the type's Lifting setup:

```
text ‹Finite sets, as lists up to order and repetition.›
quotient_type 'a fset = "'a list" / "λxs ys. set xs = set ys"
  morphisms list_of_fset fset_of_list
  by aoa

text ‹The empty finite set.›
lift_definition fempty :: "'a fset" is "[]" by aoa

text ‹Membership.›
lift_definition fmember :: "'a ⇒ 'a fset ⇒ bool" is "λx xs. x ∈ set xs" by aoa

lifting_update fset.lifting
lifting_forget fset.lifting
```

and, with no child, no parameter and no function name given, then with
`partial`, a syntax and `overloaded` recorded true:

```
text ‹The integers, as pairs of naturals up to a common summand.›
quotient_type int = "nat × nat" / "λ(a, b) (c, d). a + d = c + b"
  by aoa

lifting_update int.lifting
lifting_forget int.lifting
```

```
text ‹Rational numbers, as fractions with a non-zero denominator.›
quotient_type (overloaded) 'a fract ("_ ratio" [21] 21) = "'a :: idom × 'a" / partial: "λ(a, b) (c, d). b ≠ 0 ∧ d ≠ 0 ∧ a * d = c * b"
  by aoa

lifting_update fract.lifting
lifting_forget fract.lifting
```

- The `text` line: `english` alone, no lead (COMMON.md §2).
- `(overloaded)` after the command when the recorded `overloaded` is
  true (§6), nothing otherwise.
- The head — the type parameters, the name, the syntax — is the
  plugin's `type_head_text` (COMMON.md §4), which `Typedef` and
  `Datatype` switch to: the parameters before the name, none
  writing the name alone, `quotient_type int =`, one bare,
  `quotient_type 'a fset =`, several parenthesised and comma-separated,
  `quotient_type ('a, 'b) t =` (`type_parameters_text` over parameters
  without a sort); the name through the theory's `print_name` (below);
  the `syntax`, when given, after the name and before `=`, in
  parentheses as Isabelle writes it (`mixfix_text`): `(infixr "+" 10)`,
  `("_ ratio" [21] 21)`.
- `representation_type` after `=`, through the theory's `print_name`
  (below); then `/`; then `partial:` when `partial` is true; then
  `equiv_relation` through `print_name`.
- The `morphisms` line, indented two spaces, when either function name
  was given, the one left out written as its default; no line when
  neither was: the plugin's shared writer of the clause (COMMON.md §4),
  which `Typedef` switches to. The head, the representation type, the
  relation and
  this clause are assembled by one private helper of quotient_type.py,
  which §8's line uses too, given the keyword set to write against.
- The terminal proof, `by aoa` or `sorry`, indented two spaces, is
  `Proof_Obligation`'s `proof_text()` (COMMON.md §3); the `aoa` method's
  import is the plugin's (PLUGIN_SYSTEM §1; SESSION_AND_THEORY §2).
- The children's text is their own, each class's `emit`, at the block's
  indent: the block opens no Isabelle scope, and the file reads as the
  library's do.
- `lifting_update fset.lifting` and `lifting_forget fset.lifting`, each
  on its own line at the block's indent, the bundle's name —
  `type_name` followed by `.lifting` — written bare: `Lifting_Closing`'s
  `emit_ending` (COMMON.md §6).
- Every other piece of Isabelle text — a name, the representation type, the
  relation — is written through the theory's `print_name`
  (SESSION_AND_THEORY §2): bare when its `ascii` is an Isabelle
  identifier (`is_identifier`, COMMON.md §5) that is not a keyword of
  the theory, as Isabelle's string token (COMPILATION.md §3) otherwise —
  `intrel` bare, `"'a list"` and `"λxs ys. set xs = set ys"` quoted; a
  type variable, a symbol and a template as the writers write them.
- The text in the `unicode` spelling; the file takes the `\<name>` form
  from the compile's conversion (COMPILATION.md §2) and reads as Unicode
  in jEdit all the same.

## 6. Evaluation

The beginning runs the definition and admits its goal; the ending
closes the type's Lifting setup; neither runs a proof (ARCHITECTURE
§3.6) nor the `text` command. Both go through the ML interfaces.

**The beginning.** `Beginning_Proof_Obligation`'s `_eval_beginning_opr`
(COMMON.md §3) sends the class's callback — `evaluation_callback`,
`TAT.QuotientType.evaluate` — the beginning's input slot, `goal_state`,
the beginning's resulting slot — the first child's input, or the slot
before the ending when there is no child (MODULE_STRUCTURE §4.1) — and
its `message()`: `type_name`, the type parameters, the syntax (absent
when left out), the two function names with the defaults filled in,
then `goal_structure()` — `representation_type`, `partial` and
`equiv_relation` — whole, as its goal part (§4), each `IsaTerm` as its
`ascii`; a test pins the order, as THEOREM.md's does. The callback is
built by `TAT_Proof_Obligation` (COMMON.md §3) from `QuotientType`'s two
steps: `open_goal`, the `quotient_type` command's transition, yielding
nothing; `after_admission`, the identity on the state, yielding
`overloaded`.

`QuotientType`'s `open_goal` builds the command's transition and runs it
— the shape of `begin_theory`, through `apply_transition` — no proof
step:

```
Toplevel.local_theory_to_proof NONE NONE (fn lthy =>
  Quotient_Type.quotient_type_cmd {overloaded = true}
    ((((((parameters, name), mixfix), representation_type), (partial, equiv_relation)), SOME (rep, abs)), NONE) lthy)
```

`name` is `type_name` as a binding; `parameters` the type parameters as
Isabelle's parser hands them, each a string; `mixfix` `NoSyn` without
`syntax`, otherwise the annotation as `mixfix_text` writes it, in
`ascii`, read by Isabelle's `Parse.mixfix` under the local theory's
keywords through the plugin's `TAT_Mixfix` (COMMON.md §4) inside the
local theory's function, as a `Typedef`'s syntax is; `representation_type`
and `equiv_relation` the `ascii` texts, which the command reads;
`partial` the flag; `rep` and `abs` the two function names with the
defaults filled in (§2), as bindings under `SOME`: without a
`morphisms` clause the command's syntax hands `NONE`, which
`add_quotient_type` names `rep_fset` and `abs_fset`, the same two, so
the definition is the emitted text's either way; the last argument,
the command's parametricity theorem, none (§2). The command reads
`equiv_relation` as a relation on the representation type
(quotient_type.ML, `parse_spec`): a representation type or a relation
that does not parse, or a relation of another type, is the step's
failure with Isabelle's message. It then checks the specification
(`sanity_check`): the relation has no schematic variable and no free
variable, and neither the representation type nor the relation has a
type variable outside the parameters — each refusal the step's failure
with Isabelle's message, the type's name in quotes before it; for a
free `P`, `"fset": illegal variable(s) in the relation: "P"`. A
representation type with no map function warns and goes on. The goal,
`equivp R` — `part_equivp R` under `partial` — open and no step taken,
goes into `goal_state`, where the proof construction and the proof check
find their goal.

The admission — the half of `sorry` that ends a toplevel goal, applied
by `Proof_Obligation`'s callback between the two steps — runs the
command's own ending (quotient_type.ML, `add_quotient_type`): the
`typedef` of the representation type's equivalence classes under the
relation, run with `{overloaded = true}` as a `Typedef`'s is (TYPEDEF.md
§6); the two
functions `rep_fset` and `abs_fset`, or the names given, defined on it;
the theorems `fset_equivp` and `Quotient3_fset` noted; and the Lifting
setup of the type (quotient_type.ML, `setup_lifting_package`, through
`Lifting_Setup.setup_by_quotient`) — `cr_fset`, `pcr_fset`,
`Quotient_fset`, the transfer rules `fset.rel_eq_transfer`,
`fset.right_unique`, `fset.right_total` and the rest
`setup_by_quotient` notes, and the bundle `fset.lifting`, which the
ending closes. What Isabelle refuses there is the admission's refusal
— `apply_transition` answering `Refused` with
its messages, the step's failure and the node's: a name the command
declares already taken, `Duplicate constant declaration
"theory_X.rep_fset" vs. "theory_X.rep_fset"`; a Lifting setup the
package cannot make, which a `Typedef` turns into its notice and a
`QuotientType` does not, the setup being the command's own work and not
a step after it. `after_admission` then reads, on the admitted state,
whether the type needs `(overloaded)`: the plugin's
`TAT_Overloaded.needed` (COMMON.md §4) asked of the state's theory on
the type's full name — the name `Typedecl` declared, read off the
admitted state's generic theory (`Toplevel.generic_theory_of`) by
`Context.cases Sign.full_name Local_Theory.full_name` on `type_name`'s
binding: the theory's naming at theory level, where the admission
leaves no local theory, and the local theory's inside a `Context` or
`Locale`, which carries its qualifier —, true exactly when Isabelle
would have refused the typedef inside the command without the option;
the state is the admitted one,
untouched. The option is read after the admission because the typedef
happens there, not where the goal opens. The configuration option
`typedef_overloaded` is not consulted: where a theory sets it, the file
carries an `(overloaded)` Isabelle does not need. At theory level these
are the steps the hand-written text takes; inside a `Context` or
`Locale` the definition is made in that context — the type and the two
functions global all the same.

A failure anywhere is `Proof_Obligation`'s (COMMON.md §3): `goal_state`
is emptied and no state is written into the beginning's resulting slot,
the callback answers the messages and nothing to record, and the
beginning's status is `CannotEvaluate` with them: the node is an
obstacle, its children have no context and are `not_evaluated`, the
ending is `Ready` by the framework's copy of the block's input to its
result when the walk goes on past the block (ARCHITECTURE §3.3), and
`overloaded` stays what the last successful evaluation recorded, which
`can_emit` keeps out of a file (ARCHITECTURE §6.1). Otherwise the status
is `Ready` with no messages: `QuotientType`'s `record_from_evaluation`
sets `overloaded` to what `after_admission` yielded and answers no
message (COMMON.md §3). The proof check and the proof construction, with
their callbacks `TAT.Proof_Obligation.check` and
`TAT.Proof_Obligation.construct`, are `Proof_Obligation`'s (COMMON.md
§3): the goal they work on has one subgoal, always.

**Inside the block.** The children run in order from the beginning's
resulting slot, each in the state the one before it left
(ARCHITECTURE §3.5), with the type's Lifting setup open: a
`LiftDefinition` on the type defines its function and declares its
transfer rule, a `Theorem` may be proved by `transfer`. A child's
failure is the child's; it stops the walk inside the block as a failure
stops it anywhere (ARCHITECTURE §3.3), and the ending runs when the walk
reaches it. A child inserted, amended or deleted invalidates what
follows it in the block and the ending, never the beginning, so the
goal, `goal_state` and the proof stand (CONSTRUCT_INTERACTION §3.1); an
edit of the node's own fields invalidates the block whole.

**The ending.** `Lifting_Closing`'s `_eval_ending_opr` (COMMON.md §6)
runs, from the slot after the last child into the block's resulting
slot, the two transitions `lifting_update fset.lifting` and
`lifting_forget fset.lifting` make; what they do to the setup and to
the children's transfer rules (§2), and the ending's status and its
refusal, are COMMON.md §6's.

## 7. The jobs and the mark

The proof construction, `Proof_Job`, the proof check, `Proof_Check`,
their callbacks, their sentences, and the two-slot mark `(<status>,
<proof>)` are `Proof_Obligation`'s (COMMON.md §3), reading the
beginning's status, the one the jobs depend on (`job_operation_status()`,
CONSTRUCT_INTERACTION §3.1). `QuotientType`'s own are `valid_word` and
`invalid_word`: `valid definition` (`ready`) and `invalid definition`
(`cannot_evaluate`). Its line reads one of eleven ways, plus the tags of
CONSTRUCT_INTERACTION §6:

```
(valid definition, proof not started)  (valid definition, proving)         (valid definition, failed to prove)
(valid definition, unchecked proof)    (valid definition, proof checking)  (valid definition, proven)
(valid definition, bad proof)
(invalid definition)
(not evaluated)                        (not evaluated, proof not started)  (not evaluated, failed to prove)
```

The ending's status is not on the line: a refused ending shows as its
`Error:` block under a line that reads the valid word (PRINT.md §1),
and the jobs run as before, the beginning being the one operation they
depend on (CONSTRUCT_INTERACTION §3.1). In an ancestor's Recall summary
(PRINT.md §2) the node is counted by its own operations, not by its
line: among the failed nodes while its ending is refused; with its
beginning `ready` and its ending not yet run, under the title its
`Unfinished` carries while its proof is unfinished, and in no group
once it is proven.

## 8. What it prints

`print_fields` (PRINT.md §3) writes the definition, and only under
`Recall`; wherever it is called the framework writes the two operations'
messages after it, then the failure blocks, then the children (PRINT.md
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
syntax as emitted (§5), `=`, the representation type, `/`, `partial:`
when `partial`, the relation, and `morphisms` with the two names when
either was given — assembled from the stored text, every piece through
`print_name` against no keyword (SESSION_AND_THEORY §2): every name, an
identifier, bare, the representation type and the relation quoted
unless an identifier, whatever keywords the theory recorded, without a
round trip
to Isabelle; `english` follows at depth 0 alone; no line carries a key.
The line is the private helper's that writes the emitted text (§5),
given no keyword set. `(overloaded)` is not printed: it is not authored.
The children are the framework's to print, one level deeper, in the mode
PRINT.md §2's table gives them; a block with none shows the empty node's
line.

```
'a fset = "'a list" / "λxs ys. set xs = set ys" morphisms list_of_fset fset_of_list
Finite sets, as lists up to order and repetition
```

The evaluation's messages are the framework's to print (PRINT.md
§3–§4): an `Error:` block while an operation is an obstacle. A node
under `recall` whose definition Isabelle refused — a relation with a
free variable:

```
- quotient_type_fset (invalid definition)
  'a fset = "'a list" / "λxs ys. set xs = set ys ∧ P xs" morphisms list_of_fset fset_of_list
  Finite sets, as lists up to order and repetition
  Error:
    "fset": illegal variable(s) in the relation: "P"
  - lift_definition_fempty (not evaluated, proof not started)
    fempty :: "'a fset" is "[]"
  - lift_definition_fmember (not evaluated, proof not started)
    fmember :: "'a ⇒ 'a fset ⇒ bool" is "λx xs. x ∈ set xs"
```

A node under `recall` whose definition went through, its proof found,
and whose ending was refused:

```
- quotient_type_fset (valid definition, proven)
  'a fset = "'a list" / "λxs ys. set xs = set ys" morphisms list_of_fset fset_of_list
  Finite sets, as lists up to order and repetition
  Error:
    Interrupt
  - lift_definition_fempty (valid definition, proven)
    fempty :: "'a fset" is "[]"
  - lift_definition_fmember (valid definition, proven)
    fmember :: "'a ⇒ 'a fset ⇒ bool" is "λx xs. x ∈ set xs"
```

The jobs' blocks are `Proof_Obligation`'s (COMMON.md §3); a node under
`recall` whose stored proof failed its check:

```
- quotient_type_fset (valid definition, bad proof)
  'a fset = "'a list" / "λxs ys. set xs = set ys" morphisms list_of_fset fset_of_list
  Finite sets, as lists up to order and repetition
  The proof no longer holds.
  - lift_definition_fempty (valid definition, proven)
    fempty :: "'a fset" is "[]"
  - lift_definition_fmember (valid definition, proven)
    fmember :: "'a ⇒ 'a fset ⇒ bool" is "λx xs. x ∈ set xs"
```

## 9. Id properties

Omissible in both directions, as `Section` is, with drop priority 1:
its component goes after `Section`'s and with `Session`'s, the
outermost of the two first, before `Theory`'s (MCP_SPECIFICATION
§2.1) — the block is a scope to TAT and none to Isabelle, a child's
qualified name not carrying it, `X.fempty`. A child's id prints as
short as the forest allows,
`lift_definition_fempty`, and is accepted with or without the
component; the node's own component, `quotient_type_fset`, ends its
own id and is never dropped from it.
