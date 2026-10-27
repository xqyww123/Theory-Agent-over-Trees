# The `LiftDefinition` node class

Status: proposed 2026-10-16, from the design discussion in the session
`lift definition` (the owner's rulings there); reviewed 2026-10-17
(ai-artifacts/review/LIFT_DEFINITION_REVIEW.md); committed and
implemented 2026-10-17; `(code_dt)` judged by §6's heuristic first and
the choice recorded once, 2026-10-18 (017326a); every piece of
agent-facing wording below is the owner's.

A `LiftDefinition` defines a function on a subtype or a quotient type
from a term on its representation type: `lift_definition dl_rev :: "'a
dlist ⇒ 'a dlist" is rev`. Its one command opens one proof obligation
(INDEX.md), that the term respects the representation — for a subtype,
that it keeps the values inside the subtype's defining set; for a
quotient type, that it maps related values to related values — which
it discharges the way `Theorem` does: it is a `Leaf` of the plugin
`Isabelle_Std` deriving from the plugin's `Proof_Obligation` (COMMON.md
§3) — `class LiftDefinition(Proof_Obligation, Leaf)` — whose job
classes `Proof_Job` and `Proof_Check` are `Proof_Obligation`'s. Its
Python half is `isabelle_theory_agent/std/lift_definition.py`, its ML
halves `Isabelle_Std/ML/TAT_Lift_Definition.ML` and
`TAT_Lift_Definition_Command.ML`, which runs the command with its two
refusals at the open goal rendered — the class's sentence, from the
search for the Lifting setups a refused definition needs, or Isabelle's
rendering — and gives the verdict on `(code_dt)` the class asks before
the run (§6). Its agent-facing wording lives here — the `description`
texts of its construct schema (§3), the sentence of §6, the words on its
line, and its owing line (§7) — pinned by the baseline tests the way
TYPEDEF.md's are.

One kind, `lift_definition`, which heads the id component:
`lift_definition_dl_rev`.

## 1. Fields

| Field | Type | |
| --- | --- | --- |
| `kind` | `lift_definition` | authored |
| `english` | what is defined, `str` | authored |
| `name` | `str`, the node's name and the function's, in the id grammar without hyphens — a letter, then letters, digits, underscores and primes, not ending in an underscore (MCP_SPECIFICATION §2); one outside it is refused with the grammar's own sentence, as a `Typedef`'s `type_name` is | authored |
| `type` | `IsaTerm`, the function's type, on the subtype or quotient type | authored |
| `syntax` | `Mixfix` (COMMON.md §4), optional | authored |
| `is` | `IsaTerm`, the term on the representation type the function is defined from | authored |
| `code_dt` | `bool`: whether to declare the function's code generation rule by its representation type, the command's option `(code_dt)`; false when left out | authored |
| `with_code_dt` | `bool`, or none until an evaluation has recorded one: whether the command carries `(code_dt)` — `code_dt` asked for it, the verdict was undecided and the trial passed (§6) —, decided by the first evaluation that goes through and kept to by every later one (§6; COMMON.md §5); none on a fresh node, on the one an amend makes, after evaluations that all failed; stored, since the command is written from a loaded forest (COMPILATION.md §3), and read back with `rows.get`, so that a missing row is refused at start (`TAT_StartupError`) as a missing `is` is — the class is born with the row, None-valued | recorded |

`syntax` left out is stored as a None-valued row and `code_dt` left out
as false, so that every row of the class is read with `rows.get` and
any row missing is refused at start.

What the last evaluation reported travels on the status the evaluation
hook returns, as for every class (COMPILATION.md §4): `CannotEvaluate
(messages)` when the definition failed — the line reads `invalid
definition` —, `Ready` with no messages when it went through — the line
reads `unverified definition` with the proof's word until the proof
stands, `valid definition` then (§7). The two jobs' outcomes and the construction job's
automatic-construction setting are recorded by the framework
(CONSTRUCT_INTERACTION §3.2); `proof`, its product, the proof check's
outcome, the slot `goal_state` and the compulsory construction job are
`Proof_Obligation`'s (COMMON.md §3).

## 2. The definition

A lifted function is a name, its type on the subtype or quotient type,
the term on the representation type it is defined from, and, when
wanted, a syntax — a mixfix annotation on the function — and the
declaration of its code generation rule by its representation type:

```json
{
  "kind": "lift_definition",
  "english": "Reversal of a list without repetition",
  "name": "dl_rev",
  "type": "'a dlist ⇒ 'a dlist",
  "is": "rev"
}
```

```json
{
  "kind": "lift_definition",
  "english": "Insertion at the front, unless the element is already there",
  "name": "dl_cons",
  "type": "'a ⇒ 'a dlist ⇒ 'a dlist",
  "syntax": {"form": "infixr", "symbol": "##", "priority": 65},
  "is": "λx xs. if x ∈ set xs then xs else x # xs"
}
```

```json
{
  "kind": "lift_definition",
  "english": "The tail of a list without repetition, if any",
  "name": "dl_tl_opt",
  "type": "'a dlist ⇒ 'a dlist option",
  "is": "λxs. if xs = [] then None else Some (tl xs)",
  "code_dt": true
}
```

`kind`, `english`, `name`, `type` and `is` are required; `syntax` is
optional and absent when left out; `code_dt` is optional and false when
left out. The node's name is `name`.

Where the node stands: `lift_definition` needs the Lifting setup of the
subtype or quotient type open — the setup `setup_lifting` and
`quotient_type` make, which Isabelle's library closes with
`lifting_update` and `lifting_forget` once a type's construction is
finished, and which the `Typedef`'s and the `QuotientType`'s blocks
close at their ends (TYPEDEF.md, QUOTIENT_TYPE.md). So a
`LiftDefinition` on a subtype stands inside the `Typedef`'s block, one
on a quotient type inside the `QuotientType`'s block; where a closed
setup is wanted again a `LiftingContext` opens it (LIFTING_CONTEXT.md)
and the `LiftDefinition` stands inside it. `gen` does not check the
place: a `LiftDefinition`
standing where a setup it needs is closed is refused at evaluation,
with the sentence of §6, as everything Isabelle judges is; a term whose
type Isabelle can take at the closed type itself, `id` at `'a dlist ⇒
'a dlist`, is defined on that type with nothing lifted, and not
refused. `gen` normalises every piece of
Isabelle text and `english` once, when the construct is accepted:
newlines become spaces and runs of whitespace one space — in a syntax's
`symbol` or `template` newlines and tabs alone, since runs of spaces
there are layout; printing, emission and evaluation all use the stored
text.

`type`, `is` and a syntax's `symbol` or `template` are `IsaTerm`s
(MODULE_STRUCTURE §4.3); `name` and `english` are `str`; `code_dt` is
`bool`. `Mixfix` is shared through `MIXFIX_DEFS` (COMMON.md §4).

The class's construct schema:

```jsonc
{
  "type": "object",
  "description": "defines a function on a subtype or a quotient type from a term on its representation type; its proof obligation, which the proof construction proves, is that the term respects the subtype's defining set or the quotient type's equivalence relation. Example: lift_definition dl_rev :: \"'a dlist ⇒ 'a dlist\" is rev, reversal on the subtype 'a dlist of lists without repetition, with the obligation distinct xs ⟹ distinct (rev xs); placed inside the quotient_type or typedef that defines the type, or inside a lifting_context that opens it",
  "properties": {
    "kind":       { "const": "lift_definition" },
    "english":    { "type": "string", "description": "what is defined, in English" },
    "name":       { "type": "string" },
    "type":       { "type": "string", "description": "the type of the function, on the subtype or quotient type. Example: 'a dlist ⇒ 'a dlist" },
    "syntax":     { "$ref": "#/$defs/Mixfix" },
    "is":         { "type": "string", "description": "the term on the representation type the function is defined from. Example: rev" },
    "code_dt":    { "type": "boolean", "description": "whether to declare the function's code generation rule by its representation type" }
  },
  "required": ["kind", "english", "name", "type", "is"],
  "additionalProperties": false,
  "$defs": { ...MIXFIX_DEFS }   // Mixfix
}
```

`MIXFIX_DEFS`, the one definition the schema refers to, with its writer,
is COMMON.md §4's.

The class carries a description, its name alone not saying what it
defines; `kind` and `name` carry none (COMMON.md §5). The schema's
examples are Isabelle's own text, never JSON.

What the class does not take: `parametric`, the command's optional
parametricity theorems of the term.

## 3. Descriptions

The class:

```
defines a function on a subtype or a quotient type from a term on its representation type; its proof obligation, which the proof construction proves, is that the term respects the subtype's defining set or the quotient type's equivalence relation. Example: lift_definition dl_rev :: "'a dlist ⇒ 'a dlist" is rev, reversal on the subtype 'a dlist of lists without repetition, with the obligation distinct xs ⟹ distinct (rev xs); placed inside the quotient_type or typedef that defines the type, or inside a lifting_context that opens it
```

`english`:

```
what is defined, in English
```

`type`, `is` and `code_dt`:

```
the type of the function, on the subtype or quotient type. Example: 'a dlist ⇒ 'a dlist
the term on the representation type the function is defined from. Example: rev
whether to declare the function's code generation rule by its representation type
```

The descriptions of `Mixfix` and of its arms' fields are COMMON.md §4's,
pinned there alone.

## 4. `gen`

Where a `LiftDefinition` stands is COMMON.md §1's; the framework checks it, not
`gen` (PLUGIN_SYSTEM §2).

`LiftDefinition.gen` checks `name` against §1's grammar (`InvalidName`
with `grammar` = `constant name`, rendered with the fact name's text,
RENDER_BASELINES §2's sixth line, a grammar `Define` shares, DEFINE.md
§4). The class has no field check (PLUGIN_SYSTEM §2): nothing else of
its fields is judged before Isabelle reads them. A sibling already bearing the node's id component is the
framework's `DuplicateName` (MCP_SPECIFICATION §2); any other clash of
the function's name is Isabelle's at evaluation. Whether `type` parses
and the Lifting setup of its subtype or quotient type is open here,
whether `is` parses and its type fits, whether it has a free variable,
and whether the mixfix annotation is well-formed, are Isabelle's
business at evaluation (MODULE_STRUCTURE §4.1); what Isabelle rejects is
an evaluation failure, not an exception.

`LiftDefinition`'s `goal_structure()` (COMMON.md §3) is `type` and `is`,
each `IsaTerm` as its `ascii`: the obligation is made of them alone —
the name, the syntax and `code_dt` appear nowhere in it. On an amend, a
changed `type` or `is` discards the stored proof; a changed `name`,
`syntax`, `code_dt` or `english` keeps it.

`gen` renders no sentence of its own: the name's is the framework's
grammar sentence. The
class's own sentence is the evaluation's, for a node standing where a
Lifting setup it needs is closed (§6).

## 5. Emission

The node emits, when its `can_emit` holds — `LiftDefinition` keeps the
framework's default (COMPILATION.md §3) — the `text` line and the
definition with its proof:

```
text ‹Reversal of a list without repetition.›
lift_definition dl_rev :: "'a dlist ⇒ 'a dlist" is rev by aoa
```

and, with a syntax, then with the recorded `with_code_dt` true, then a
definition whose obligation Isabelle proved by itself (§6), the same
terminal proof:

```
text ‹Insertion at the front, unless the element is already there.›
lift_definition dl_cons :: "'a ⇒ 'a dlist ⇒ 'a dlist" (infixr "##" 65) is "λx xs. if x ∈ set xs then xs else x # xs" by aoa
```

```
text ‹The tail of a list without repetition, if any.›
lift_definition (code_dt) dl_tl_opt :: "'a dlist ⇒ 'a dlist option" is "λxs. if xs = [] then None else Some (tl xs)" by aoa
```

```
text ‹The length of a list without repetition.›
lift_definition dl_length :: "'a dlist ⇒ nat" is length by aoa
```

- The `text` line: `english` alone, no lead (COMMON.md §2).
- `(code_dt)` after the command when the recorded `with_code_dt` is
  true (§6), nothing otherwise.
- The function's name after that, then `::` and `type`, each through
  the theory's `print_name` (below).
- The `syntax`, when given, after the type and before `is`, in
  parentheses as Isabelle writes it, by the plugin's `mixfix_text`
  (COMMON.md §4): `(infixr "##" 65)`, `(binder "⨆" 10)`, `("⟨_⟩")`.
- `is`, then the term through `print_name`. The name, `::`, the type,
  the syntax, `is` and the term are written by one private helper of
  lift_definition.py, which §8's line uses too, given the writer of each
  piece: here the theory's `print_name`.
- The terminal proof, `by aoa` or `sorry`, after the term on the same
  line, is `Proof_Obligation`'s `proof_text()` (COMMON.md §3); the `aoa`
  method's import is the plugin's (PLUGIN_SYSTEM §1; SESSION_AND_THEORY
  §2).
- Every piece of Isabelle text — the name, the type, the term — is
  written through the theory's `print_name` (SESSION_AND_THEORY §2):
  `dl_rev`, `rev` and `length` bare, `"open"`, `"'a dlist ⇒ 'a dlist"`
  and `"λx xs. …"` quoted; a symbol and a template as the writer writes
  them.
- The text in the `unicode` spelling; the file takes the `\<name>` form
  from the compile's conversion (COMPILATION.md §2) and reads as Unicode
  in jEdit all the same.

## 6. Evaluation

The evaluator runs the definition and admits its goal; it never runs a
proof (ARCHITECTURE §3.6) and never the `text` command. It goes through
the ML interfaces. `Proof_Obligation`'s `_eval_opr` (COMMON.md §3)
sends the class's callback — `evaluation_callback`,
`TAT.LiftDefinition.evaluate` — the input slot, `goal_state`, the
resulting slot, and its `message()`: the definition — `name`, the
syntax (absent when left out), `code_dt`, then `goal_structure()` —
`type` and `is` — whole, as its goal part (§4), each `IsaTerm` as its
`ascii` — and the recorded `with_code_dt`, `None` until an evaluation
has recorded one (COMMON.md §5); a test pins the order, as THEOREM.md's
does. The callback is built by `TAT_Proof_Obligation` (COMMON.md §3)
from `LiftDefinition`'s two steps: `open_goal`, the `lift_definition`
command's transition, yielding `with_code_dt`, the option it ran with;
`after_admission`, the identity, yielding nothing.

`LiftDefinition`'s `open_goal` builds the command's transition and runs
it — the shape of `begin_theory`, through `apply_transition` — no proof
step:

```
Toplevel.local_theory_to_proof NONE NONE (fn lthy =>
  Lifting_Def_Code_Dt.lift_def_cmd (options, (name, SOME type, mixfix), is, []) lthy
  handle Lifting_Term.QUOT_THM (rty, qty, msg) => …
       | Lifting_Term.CHECK_RTY (rty_schematic, rty_forced) => …)
```

`name` is the function's name as a binding; `type` and `is` the `ascii`
texts, which the command reads; `mixfix` `NoSyn` without `syntax`,
otherwise the annotation as `mixfix_text` writes it, in `ascii`, read by
Isabelle's `Parse.mixfix` under the local theory's keywords through the
plugin's `TAT_Mixfix` (COMMON.md §4) inside the local theory's function,
as a `Typedef`'s syntax is; `options` `["code_dt"]` or `[]`; the last
argument, the command's parametricity theorems, none (§2). Whether the
command carries the option is decided under the recorded-choice
convention (COMMON.md §5), through `TAT_Proof_Obligation.decide`
(COMMON.md §3). With a recorded `with_code_dt` `open_goal` runs the
command with the option or without it as recorded, alone, and yields
the recorded value; a refusal is `open_goal`'s failure, never a switch.
With none and `code_dt` false it runs the command without the option
and yields false. With none and `code_dt` true it asks the heuristic
first, `TAT_Lift_Definition_Command.code_dt_verdict`, in the context
the command runs in, and runs the trial only where the heuristic is
undecided.

The heuristic's inputs are the type `τ` and the term `t`, read as the
command reads them — `Proof_Context.read_var` on the function and its
type, then `Syntax.read_term` in the context that gives, `ctxt'`
(lifting_def_code_dt.ML:772–774), `TAT_Lift_Definition_Command.read` —;
the raw type `ρ`, the first component of `Lifting_Util.quot_thm_rty_qty
(Lifting_Term.prove_quot_thm ctxt' (fastype_of t, τ))`, the raw type
the plain definition is made over (lifting_def.ML:628–629, 562–567);
and the result type R, `body_type τ`. Its words: an abstract type is a
type constructor with an open Lifting setup in that context
(`Lifting_Info.lookup_quotients` answers), the one kind the option acts
on — a closed setup is a plain constructor to the walk, and one the
definition needs is the search's refusal below; a subtype is an
abstract type whose quotient theorem's relation is `eq_onp P`
(`Lifting_Util.quot_thm_rel`; a `typedef` onto a set other than `UNIV`
with `setup_lifting` — the quotient types `'a fset` and `int` and the
type copies `natural` and `'a wrap`, `typedef`s onto `UNIV`, are none);
the walk is `Lifting_Term.prove_schematic_quot_thm` over
`Lifting_Info.get_quotients` on `(body_type ρ, R)` with actions that
record each step — the function, the table and the pair the option
itself walks (lifting_def_code_dt.ML:225–232, 253–258) —, its steps a
lift (an abstract type none of whose arguments is lifted,
lifting_term.ML:224–229), a composition (an abstract type with a lifted
argument, 231–238) and a constructor step (the same plain constructor
on both sides with a lifted argument, 243–258), the arguments visited
before their parent, so the last step is R's. The verdicts:

- Not needed — the walk takes no step, or exactly one step and that a
  lift of a subtype: with the option Isabelle accepts and declares
  nothing beyond the plain definition but at most an entry in the
  option's own memo of subtype witnesses (`Lifting_Def_Code_Dt`'s
  `Data`), which the option alone reads — `dl_length`; `dl_rev` and
  `dl_cons`; `f :: "'a dlist ⇒ 'a dlist dlist" is "λxs::'a dlist.
  [xs]"`, whose term keeps the inner `dlist`; `int dlist` with `int`'s
  setup closed; the same inside a locale, a class or an interpreted
  locale. `open_goal` runs the command without the option and yields
  false. Sound because a plain definition with a code equation makes
  the option return at once (lifting_def_code_dt.ML:244–250); with none
  (`NONE_EQ`, or `UNKNOWN_EQ` inside a locale, lifting_def.ML:528–546)
  the option's walk takes the heuristic's steps, and a lift of a
  subtype only looks up the subtype's witness in that memo or builds it
  and enters it there (201–216, 146–150; Lifting.thy:271), declaring
  nothing else, since beyond that memo only a constructor step declares
  (259–262, 341–349, 590).
- Without effect — the walk takes a composition step, or exactly one
  step and that a lift of a type that is no subtype: with the option
  Isabelle refuses the admission — `Composition of abstract types has
  not been implemented yet.` for `dl_wrap :: "'a dlist ⇒ 'a dlist
  dlist" is "λxs. [xs]"`, `'a dlist dlist option` with `λxs. Some [xs]`,
  `('a dlist dlist ⇒ 'a dlist) option`, `'a dlist wrap`; `code_dt: "…"
  was not defined as a subtype.` where the walk lifts a type that is no
  subtype, `'a dlist ⇒ 'a fset` with `λxs. xs`, `'a dlist × nat fset
  fset` —, or accepts it and declares nothing: where the plain
  definition already has a code equation, `nat ⇒ nat fset fset` with
  `λn. [[n]]`, or inside a locale whose interpretation's `rewrites`
  turns the abstraction function into a plain constant, or where the
  option's memo already holds the type's witness. `open_goal` runs the
  command without the option and yields false, nothing said. Sound
  because the option, unless it returns at once with the plain
  definition (lifting_def_code_dt.ML:244–250), walks the same steps,
  arguments first, and raises at a composition, `comp_lift_error` (199,
  231), or, at a lift of a type that is no subtype, raises at the
  witness (209) or finds one in the memo and returns the plain
  definition (206, 261–262).
- Undecided — every other case, and whenever the reading of `τ` or
  `t`, `prove_quot_thm` or the walk raises: a constructor step with no
  composition among the steps, where the option has work to do and only
  the trial tells whether Isabelle accepts it — `dl_tl_opt`, `'a dlist
  × nat`, `'a dlist list`, `('a dlist × 'a fset) option`. `open_goal`
  runs the command with the option as a probe, then the trial, the
  admission tried on the probe's state — `TAT_Proof_Obligation.admit`,
  the one the callback applies (COMMON.md §3) —, then the command with
  the option when the trial passed, yielding true, and without it when
  the trial was refused, yielding false, nothing said; the probe's state
  is dropped. The option acts at the admission, where Isabelle declares
  the rule and refuses what it cannot declare, with its own message: `f
  :: "'a dlist ⇒ ('a dlist × 'a fset) option" is "λxs. Some (xs, xs)"`
  is refused with `code_dt: "X.fset" was not defined as a subtype.` and
  passes without the option.
  Where the command is refused at its open goal, as when the reading or
  `prove_quot_thm` raises, it is refused the same with the option as
  without it — the option reaches only `add_lift_def_code_dt`, inside
  `after_qed` (lifting_def_code_dt.ML:769–802) —, so the probe's
  refusal, rendered as below, is `open_goal`'s failure and no trial is
  run.

The option acts only where Isabelle has no code generation rule for the
function already, and is nothing otherwise.

Two refusals the command raises at the open goal as exceptions of its own,
`Lifting_Term.QUOT_THM` and `CHECK_RTY`, which `lift_def_cmd` lets
through, the step catches around the call inside the local theory's
function, where the command's parser catches them
(`lift_def_cmd_with_err_handling`; past `apply_transition` an exception
is only its text), and renders as the parser does, by the parser's two
renderers, `quot_thm_err` and `check_rty_err`, which
`Lifting_Def_Code_Dt` does not export and
TAT_Lift_Definition_Command.ML carries verbatim — a term whose type is
no representation of the subtype at a
position where the subtype stands, `dl_suc :: "'a dlist ⇒ nat" is Suc`,
and a term whose type cannot be instantiated to the representation type
the declared type asks for, `dl_bad :: "'a dlist ⇒ nat" is id`:

```
Lifting failed for the following types:
Raw type:  nat
Abstract type:  'a dlist

Reason:  The type nat is not a raw type for the quotient type "X.dlist"; the correct raw type must be an instance of ?'a list
```

```
Lifting failed for the following term:
Term:  id
Type:  ?'b ⇒ ?'b

Reason:  The type of the term cannot be instantiated to "'a list ⇒ nat".
```

— except when a Lifting setup the definition needs is closed where the
node stands (§2); then the step's failure is the class's sentence in
place of Isabelle's, a string of TAT_Lift_Definition_Command.ML pinned
by an Isabelle-backed test.

Which setups the definition needs is computed on the refusal. The
candidates are the type constructors of `type` whose Lifting setup is
closed here — `Lifting_Info.lookup_quotients` finds no quotient for the
constructor — and reopenable — an entry of
`Lifting_Info.get_restore_data` holds a quotient theorem whose abstract
type (`Lifting_Util.quot_thm_rty_qty`) has that constructor. Opening a
set of candidates applies `Lifting_Setup.lifting_restore` to each one's
stored quotient, what `context includes t.lifting` does to the table
Lifting reads. Whether Lifting accepts a set is one call of
`Lifting_Term.prove_quot_thm` on the type of `is` and on `type`, read as
`lift_def_cmd` reads them — `Proof_Context.read_var` on the function
and its type, then `Syntax.read_term` in the context that gives
(lifting_def_code_dt.ML:772-774) — in that context with the set opened:
the one computation of the command that raises the two exceptions. The
search is breadth-first from the empty set: level k + 1 holds each
refused set of level k extended by each candidate its refusal names;
the answer is every accepted set of the first level that has one — the
smallest sets whose opening makes Lifting accept the definition,
several when they tie — or none, when a level is empty, and then
Isabelle's rendering above is the failure. What a refusal names: a
`QUOT_THM` raised where the term's type has a type constructor other
than `type`'s constructor T names T when T is an unopened candidate and
nothing otherwise; any other `QUOT_THM` names every unopened candidate;
a `CHECK_RTY (σ', ρ)` is read by matching σ', each occurrence of a type
variable renamed apart, against ρ with `Sign.typ_match`, which gives the
representation type each occurrence received (a type variable fixed in
the context also receives itself): a variable whose occurrences
received different types names the unopened candidates among the type
constructors on the way from the root to the first place where two of
them differ, both sides included; one whose type lies outside its sort
(`Sign.of_sort`) names the unopened candidates in that type; a match
failing on a constructor of the term's type names nothing; of several
variables, the smallest set. Every accepted superset of a refused set
opens a setup the refusal names, so the search reaches every smallest
accepted set and calls `prove_quot_thm` no more often than trying the
candidates' subsets by size would.

The sentence names each type of a set — its first occurrence in `type`
as read, as `Syntax.string_of_typ` prints it in the local theory — and
its constructor by `Proof_Context.extern_type`. With one set of one type,
it names the node that defines the type when the type is the forest's —
declared in a theory `Thy_Info` does not hold (`Thy_Info.defined_theory`
false of the theory `Name_Space.theory_name {long = true}` gives on the
type space), since library theories live in `Thy_Info`'s table and the
forest's in the framework's (EVALUATOR_DESIGN §6), by `quotient_type`
(`Quotient_Info.lookup_quotients`) or else by `typedef`
(`Typedef.get_info`, which a `quotient_type` fills too) — and a
`LiftingContext`; for a type that is not the forest's, a
`LiftingContext` alone; with one set of
several types, a `LiftingContext` opening them all; with several sets,
a `LiftingContext` for each:

```
The lifting of `'a dlist` is not open here. Place this lift_definition under the typedef that defines `dlist`, or under a lifting_context opening `dlist`.
The lifting of `'a fset` is not open here. Place this lift_definition under the quotient_type that defines `fset`, or under a lifting_context opening `fset`.
The lifting of `int` is not open here. Place this lift_definition under a lifting_context opening `int`.
The lifting of `'a dlist` and of `natural` is not open here. Place this lift_definition under a lifting_context opening `dlist` and `natural`.
The lifting of `'a wrap`, or that of `'a dlist`, is not open here. Place this lift_definition under a lifting_context opening `wrap`, or one opening `dlist`.
```

A set's types, and the sets, are named in the order of the types' first
occurrence in `type`, sets compared type by type; the types of a set are
joined by `and of`, the sets by `, or that of`; the constructors after
`opening` by `and`, the alternatives by `, or one opening`.

Any other refusal of the transition — a type or a term that does not
parse — is `apply_transition` answering `Refused` with Isabelle's
messages, the step's failure with them.

The goal the command opens is the respectfulness statement in the
readable form the command prints, its bound variables named after their
types — for `dl_rev`, `⋀list. distinct list ⟹ distinct (rev list)`; for
`dl_cons`, `⋀a list. distinct list ⟹ distinct (if a ∈ set list then
list else a # list)` — which goes into `goal_state`, open and no step
taken, where the proof construction and the proof check find it. The
command first tries to prove the statement by itself, and when it
succeeds — a type copy, a function from the subtype to a type without
it, such as `dl_length :: "'a dlist ⇒ nat" is length` — the goal opens with
no subgoal: to `Proof_Obligation` a goal like any other (COMMON.md §3),
whose construction costs no search and whose file text is `by aoa`.

The admission — the half of `sorry` that ends a toplevel goal, applied
by `Proof_Obligation`'s callback between the two steps — runs the
command's own ending: the constant is defined, the facts `dl_rev_def`,
`dl_rev.rsp`, `dl_rev.transfer`, `dl_rev.abs_eq` and `dl_rev.rep_eq`
are noted, and with the option the code generation rule is declared.
What Isabelle refuses there is the admission's refusal —
`apply_transition` answering `Refused` with its messages: a free
variable in the term, `dl_f :: "'a dlist ⇒ 'a dlist" is "λxs. g xs"`,

```
Extra variables on rhs: "g"
The error(s) above occurred in definition:
"dl_f ≡ map_fun list_of_dlist dlist_of_list g"
```

a name already a constant's, `Duplicate constant declaration
"X.dl_rev" vs. "X.dl_rev"`. `after_admission`, the
identity, follows. At theory level
these are the steps the hand-written text takes; inside a `Context` or
`Locale` the definition is made in that context, like a `definition`.

A failure anywhere is `Proof_Obligation`'s (COMMON.md §3): `goal_state`
is emptied and no state is written into the resulting slot, the
callback answers the messages and nothing to record, and `_eval_opr`
returns `CannotEvaluate` with them: the node is an obstacle, and
`with_code_dt` stays what the last evaluation that went through
recorded — none, if none has —, which `can_emit` keeps out of a file
(ARCHITECTURE §6.1). Otherwise `_eval_opr` returns `Ready` with no
messages: `LiftDefinition`'s `record_from_evaluation` sets
`with_code_dt` to what `open_goal` yielded — the option the command ran
with, as decided or as recorded (COMMON.md §5) — and answers no message
(COMMON.md §3). The proof check and the proof construction,
with their callbacks `TAT.Proof_Obligation.check` and
`TAT.Proof_Obligation.construct`, are `Proof_Obligation`'s (COMMON.md
§3): the goal they work on has one subgoal or none.

## 7. The jobs and the mark

The proof construction, `Proof_Job`, the proof check, `Proof_Check`,
their callbacks, their sentences, and the two-slot mark `(<status>,
<proof>)` are `Proof_Obligation`'s (COMMON.md §3). `LiftDefinition`'s
own are the three words of a class that defines: `valid_word`, `valid
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
(PRINT.md §2) says what it waits for:

```
The definition is unverified until the term is proven to respect the representation.
```

`LiftDefinition` names what the construction was to prove through the
hook `failed_assertion` (COMMON.md §3), so that the failure header and
the failure notification both read, with AoA's message after it:

```
Failed to prove that `lift_definition_dl_rev`'s defining term respects the representation:
```

and, when the agent refuted it, its refutation sentence,
`refutation_sentence` (COMMON.md §3), with the agent's own words after it:

```
`lift_definition_dl_rev`'s defining term may not respect the representation:
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
| `Recall`, depth 0 | the definition with `(code_dt)` before it when the authored `code_dt` is true, `english` |
| `Recall`, depth 1 and 2 | the definition |
| `Recall`, depth 3 | nothing |

The definition is one line: the name, `::`, the type, the syntax as
emitted (§5) when given, `is` and the term — assembled from the stored
text, every piece through `print_name` against no keyword
(SESSION_AND_THEORY §2): the name, an identifier, bare, the type and
the term quoted unless an identifier, whatever keywords the theory
recorded, without a round trip to Isabelle; `english` follows at depth
0 alone; no line carries a key. The line is §5's private helper's,
given the module-level `print_name`. At depth 0 the line begins with `(code_dt)` when
the authored `code_dt` is true, what the agent wrote; the recorded
`with_code_dt` is not printed.

```
dl_cons :: "'a ⇒ 'a dlist ⇒ 'a dlist" (infixr "##" 65) is "λx xs. if x ∈ set xs then xs else x # xs"
Insertion at the front, unless the element is already there
```

```
(code_dt) dl_tl_opt :: "'a dlist ⇒ 'a dlist option" is "λxs. if xs = [] then None else Some (tl xs)"
The tail of a list without repetition, if any
```

The evaluation's messages are the framework's to print (PRINT.md
§3–§4): an `Error:` block while the node is an obstacle; after it, while
the node is unverified, its owing line (§7). A node under `recall` whose
definition Isabelle refused — standing where the
subtype's Lifting setup is closed (§2, §6):

```
- lift_definition_dl_rev (invalid definition)
  dl_rev :: "'a dlist ⇒ 'a dlist" is rev
  Reversal of a list without repetition
  Error:
    The lifting of `'a dlist` is not open here. Place this lift_definition under the typedef that defines `dlist`, or under a lifting_context opening `dlist`.
```

The jobs' blocks are `Proof_Obligation`'s (COMMON.md §3); a node under
`recall` whose stored proof failed its check:

```
- lift_definition_dl_rev (unverified definition, bad proof)
  dl_rev :: "'a dlist ⇒ 'a dlist" is rev
  Reversal of a list without repetition
  The definition is unverified until the term is proven to respect the representation.
  The proof no longer holds.
```

## 9. Id properties

None declared: a leaf's component is the last of every id, and the
framework's defaults stand (MCP_SPECIFICATION §2.1).
