# The `Inductive` node class

Status: proposed 2026-10-24, from the design discussion of 2026-10-21 to
2026-10-24 (the owner's rulings in the session `Inductive`,
ai-artifacts/review/inductive/DECISIONS.md); revised the same day after
its review (ai-artifacts/review/inductive/design_review.json) and its
re-review (design_rereview.json); the agent-facing wording below is the
owner's. Implemented on 2026-10-28. Revised 2026-10-28 with the
unused-variable check (COMMON.md §4; ai-artifacts/UNUSED_TERM_VARIABLE_PLAN.md):
§6's parse.

An `Inductive` defines one or more predicates by rules: under the kind
`inductive` as the least predicates that satisfy the rules, under
`coinductive` as the greatest consistent with them. It opens no proof
obligation (INDEX.md): Isabelle proves the rules monotone by itself, and
a monotonicity proof that fails is the definition's failure. It is a
`Leaf` of the plugin `Isabelle_Std`: its Python half is
`isabelle_theory_agent/std/inductive.py`, its ML half
`Isabelle_Std/ML/TAT_Inductive.ML`. Its agent-facing wording lives here
— the `description` texts of its construct schema (§3), the sentences
of its notice (§6) and the words on its line — pinned by the baseline
tests the way DEFINE.md's are.

Kinds: `inductive` and `coinductive`, the two commands sharing one
syntax and one implementation (`Inductive.gen_add_inductive_cmd`),
differing in the fixed point taken. The kind heads the id component:
`inductive_star`, and for several predicates `inductive_even_and_odd`
(§9).

The `for` clause, which fixes the leading arguments that are unchanged
throughout the rules, is not the agent's to write: the evaluation finds
those arguments and records them as `fixed_parameters` (§1, §6).

## 1. Fields

| Field | Type | |
| --- | --- | --- |
| `kind` | `inductive` or `coinductive` | authored |
| `english` | what is defined, `str` | authored |
| `constants` | `list[Variable_With_Syntax]` (COMMON.md §4), non-empty: the predicates defined, each a `name`, `IsaTerm`, in the id grammar without hyphens, an optional `type` and an optional `syntax`, as `Define`'s constants (DEFINE.md §1) | authored |
| `inductive_rules` | `list[Inductive_Rule]` (§2), non-empty: each a `name`, `IsaTerm`; an `english`, `str`; its `for_any`, `list[Variable]` (THEOREM.md §2), empty when left out; its `premises`, `list[IsaTerm]`, empty when left out; its `conclusion`, `IsaTerm` | authored |
| `fixed_parameters` | `list[IsaTerm] \| None`: the names of the arguments the command fixes with `for`, in order, empty when it fixes none; `None` until an evaluation has recorded them — decided by the first evaluation that goes through and run as recorded by every later one (§6, COMMON.md §5); stored, since the command is written from a loaded forest (COMPILATION.md §3), and read back with `rows.get`, so that a missing row is refused at start (`TAT_StartupError`) | recorded |

What the last evaluation reported travels on the status the evaluation
hook returns, as for every class (COMPILATION.md §4): `CannotEvaluate
(messages)` when the definition failed, `Ready` with the notice of §6
or no messages when it went through.

The class has no job and owns no slot: its `_unfinished` is the
framework's default, so the node is finished when its one operation is
`ready`.

## 2. The definition

The reflexive transitive closure of a relation:

```json
{
  "kind": "inductive",
  "english": "The reflexive transitive closure of a relation r",
  "constants": [{"name": "star", "type": "('a ⇒ 'a ⇒ bool) ⇒ 'a ⇒ 'a ⇒ bool"}],
  "inductive_rules": [
    {"name": "refl", "english": "Every element reaches itself", "conclusion": "star r x x"},
    {"name": "step", "english": "A step of r followed by a path is a path",
     "premises": ["r x y", "star r y z"], "conclusion": "star r x z"}
  ]
}
```

A rule is structured as a `LongStatement` is (THEOREM.md §2): its
variables, its premises and its conclusion, never `⟹` or `⋀` written by
the agent; its premises carry no names, since Isabelle's rule syntax
names none. The conclusion applies one of the predicates. `kind`,
`english`, `constants` and `inductive_rules` are required, and in a rule
`name`, `english` and `conclusion`. `gen` normalises every piece of
Isabelle text once, when the construct is accepted, as `Define`'s `gen`
does (DEFINE.md §2), and the node's `english` and every rule's through
`normalised` (COMMON.md §2).

The class's construct schema:

```jsonc
{
  "type": "object",
  "description": "inductive/coinductive predicate definition: defining the predicate as the least one that satisfies the provided inductive rules, or the greatest one consistent with the provided coinductive rules. Example: inductive star :: \"('a ⇒ 'a ⇒ bool) ⇒ 'a ⇒ 'a ⇒ bool\" where refl: \"star r x x\" | step: \"star r x z\" if \"r x y\" \"star r y z\"",
  "properties": {
    "kind":            { "type": "string", "enum": ["inductive", "coinductive"] },
    "english":         { "type": "string", "description": "what is defined, in English" },
    "constants":       { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/Constant" },
                         "description": "the predicates defined; several for mutually inductive predicates" },
    "inductive_rules": { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/InductiveRule" },
                         "description": "the inductive/coinductive rules. An optimization: when an argument of the predicates is unchanged throughout the rules, such as the `r` in `star r x y`, make it the first argument and give it the same variable name in every rule." }
  },
  "required": ["kind", "english", "constants", "inductive_rules"],
  "additionalProperties": false,
  "$defs": {
    "InductiveRule": {
      "type": "object",
      "properties": {
        "name":       { "type": "string", "description": "the rule's name. Example: refl, which a later proof cites as star.refl" },
        "english":    { "type": "string", "description": "the rule in English" },
        "for_any":    { "type": "array", "items": { "$ref": "#/$defs/Variable" },
                        "description": "universally quantified variables to fix" },
        "premises":   { "type": "array", "items": { "type": "string", "description": "Isabelle/HOL term with all literal numbers annotated with types" },
                        "description": "premises to assume" },
        "conclusion": { "type": "string", "description": "an Isabelle/HOL term, which must be an application of one of the predicates. Example: star r x z" }
      },
      "required": ["name", "english", "conclusion"],
      "additionalProperties": false
    },
    ...CONSTANT_DEFS,   // Constant
    ...VARIABLE_DEFS,   // Variable
    ...MIXFIX_DEFS      // Mixfix
  }
}
```

`InductiveRule` is `Inductive`'s own definition; `CONSTANT_DEFS`,
`VARIABLE_DEFS` and `MIXFIX_DEFS` are COMMON.md §4's. A premise's
description is `common.py`'s `TERM_DESCRIPTION`, the one
`LongStatement`'s terms carry. What the node keeps of a rule is
`Inductive_Rule`, its `for_any` read by statement.py's `variables_of`
(COMMON.md §4).

What the class does not take: the `for` clause, which the evaluation
decides (§6); `inductive_set` and `coinductive_set`, a set being the
predicate's `{x. P x}` (INDEX.md §3); `monos`, the monotonicity lemmas a
rule may need beyond Isabelle's own set, whose absence is the
definition's failure; attributes on a rule, such as `[intro]`; and an
abbreviation among the rules, which Isabelle's command accepts as an
`≡` clause and which `Abbreviation` makes instead.

## 3. Descriptions

The class:

```
inductive/coinductive predicate definition: defining the predicate as the least one that satisfies the provided inductive rules, or the greatest one consistent with the provided coinductive rules. Example: inductive star :: "('a ⇒ 'a ⇒ bool) ⇒ 'a ⇒ 'a ⇒ bool" where refl: "star r x x" | step: "star r x z" if "r x y" "star r y z"
```

`english`, `constants` and `inductive_rules`:

```
what is defined, in English
the predicates defined; several for mutually inductive predicates
the inductive/coinductive rules. An optimization: when an argument of the predicates is unchanged throughout the rules, such as the `r` in `star r x y`, make it the first argument and give it the same variable name in every rule.
```

`InductiveRule`'s `name`, `english`, `for_any`, `premises` and
`conclusion`:

```
the rule's name. Example: refl, which a later proof cites as star.refl
the rule in English
universally quantified variables to fix
premises to assume
an Isabelle/HOL term, which must be an application of one of the predicates. Example: star r x z
```

The descriptions of `Constant` and `Mixfix` are COMMON.md §4's, those of
`Variable` and of a premise THEOREM.md §3's, pinned there alone.

## 4. `gen` and the field check

Where an `Inductive` stands is COMMON.md §1's; the framework checks it
before the node's operation runs (PLUGIN_SYSTEM §2).

`Inductive.gen` refuses only what keeps the node from being built: a
constant's name outside the id grammar without hyphens, since the
node's name is computed from the constants' (`InvalidName` with
`grammar` = `constant name`, by `constants_of`, COMMON.md §4).
`constants` and `inductive_rules` non-empty is the schema's `minItems`,
refused before `gen` (MODULE_STRUCTURE §4.4). A sibling already bearing
the node's id component is the framework's `DuplicateName`
(MCP_SPECIFICATION §2).

The field check (PLUGIN_SYSTEM §2), `check_fields`, refuses, before the
node's first own operation, in this order, by the plugin's shared
checks and with their sentences (COMMON.md §5): two constants the same name, by `check_not_bound_twice`
over the stored constants' names; a rule's `name` not an Isabelle
identifier, or two rules the same name, by `check_identifier` with
`in_term` false over the rule names — a fact's name, which may end with
an underscore —; a `for_any` variable's name or a repeat in one rule's
`for_any`, by statement.py's `check_variables` under
`inductive_rules[i]`. A rule's name is a binding the
evaluation passes unparsed, so the check is the class's, never left to
Isabelle. Whether the rules parse and type, whether each conclusion
applies a predicate, and whether the rules are monotone are Isabelle's
business at evaluation (MODULE_STRUCTURE §4.1).

The sentences, all the plugin's shared ones:

```
The field `constants[1].name` repeats `even`.
The field `inductive_rules[1].name` must be an Isabelle identifier: it starts with a letter and continues with letters, digits, underscores and primes ('), and does not end with an underscore.
The field `inductive_rules[1].name` repeats `refl`.
```

and THEOREM.md §4's for a `for_any` variable, under
`inductive_rules[i].for_any[j].name`.

## 5. Emission

The node emits, when its `can_emit` holds — `Inductive` keeps the
framework's default (COMPILATION.md §3) — the `text` line, then the
command:

```
text ‹Inductive ‹star›. The reflexive transitive closure of a relation r.›
inductive star :: "('a ⇒ 'a ⇒ bool) ⇒ 'a ⇒ 'a ⇒ bool" for r where
  refl: "star r x x"
    ―‹Every element reaches itself.›
| step: "star r x z" if "r x y" "star r y z"
    ―‹A step of r followed by a path is a path.›
```

- The `text` line's lead: the kind capitalised and the predicates'
  names, each in a cartouche, joined by `and`, `Inductive ‹star›.`,
  `Coinductive ‹bisim›.`, `Inductive ‹even› and ‹odd›.`; the line is
  COMMON.md §2's.
- The command: the kind, then the constants as `fixes_text` writes them
  (COMMON.md §4); then, when `fixed_parameters` is non-empty, `for` and
  the fixed parameters as `fixes_text` writes them, each with the first
  type a rule's `for_any` gives it, or none; then `where`.
- The rules, each on its own line indented two spaces, the second and
  later led by `| `: the rule's name and `:`, the conclusion; `if` and
  the premises when there are premises; `for`
  and the rule's `for_any` less the fixed parameters as `fixes_text`
  writes them, when any remain — `for x :: "'a" and y :: "'a"`. A
  `Variable` reaches `fixes_text` as a `Variable_With_Syntax` without
  an annotation, built where the class calls it.
- Under each rule, indented four spaces, its `english` as a formal
  comment: `―` before `english_cartouche`'s text (COMMON.md §2), as a
  `Locale`'s axiom carries its statement's. After the rule, so that no
  comment stands between `|` and a rule's name.
- Every piece of Isabelle text — a name, a rule's name, a type, a
  conclusion, a premise — is written through the theory's `print_name`
  (SESSION_AND_THEORY §2), `fixes_text`'s `write` included: bare when
  its `ascii` is an Isabelle identifier that is not a keyword of the
  theory, as Isabelle's string token otherwise, the formal comments
  inside it translated (COMPILATION.md §3).
- The text in the `unicode` spelling; the file takes the `\<name>` form
  from the compile's conversion (COMPILATION.md §2) and reads as Unicode
  in jEdit all the same.

## 6. Evaluation

The evaluator makes the definition and never runs the `text` command.
It goes through the ML interfaces, never a command string:
`Inductive._eval_opr` sends the class's callback `TAT.Inductive.evaluate`
the input slot, the resulting slot, and its `message()`: `kind`, the
constants as `Variable_With_Syntax`'s wire, the rules — each its name,
its conclusion, its premises and its `for_any` as names with types or
none —, each `IsaTerm` as its `ascii`, and the recorded
`fixed_parameters`, `None` before any evaluation and on the node an
amend makes. A test pins the order. The callback's whole run is one
`operation'` into the resulting slot (MODULE_STRUCTURE §2.5).

**The command's arguments**, for a list of parameters, built from the
message: `cnames_syn`, the constants as `TAT_Mixfix.fixes` reads them;
`pnames_syn`, the parameters, each with the first type a rule's
`for_any` gives it, or none, and `NoSyn`; `specs`, each rule's name, its
conclusion's and premises' text, and its `for_any` less the parameters.

**The parse and the unused-variable check.** On the command's arguments
for the recorded fixed parameters, none under `None`, each rule's
conclusion and premises are parsed, never checked, where the command
parses them (`specification.ML`, `prep_specs`): in the context
`Specification.read_multi_specs (cnames_syn @ pnames_syn) []` leaves,
with the rule's own `for_any` fixed. A parse that fails is the
definition's failure, with Isabelle's messages. A variable of a rule's
`for_any`, as the agent wrote it, that is not a free variable of that
rule's parse refuses the definition before step 1, with COMMON.md §4's
one message, its paths `inductive_rules[i].for_any`.

**Step 1, the rules read.** In the input state's local theory,
`Specification.read_multi_specs (cnames_syn @ pnames_syn) specs`, on the
command's arguments for the recorded fixed parameters, none under
`None` — the command's own reading (`inductive.ML`,
`gen_add_inductive_cmd`) in the default mode, the mode
`gen_add_inductive` checks the rules in before judging them — reads
every rule, each closed over its own variables (`specification.ML`,
`close_form`). A read that fails is the definition's failure, with
Isabelle's messages; it fails exactly where the file's command fails.

**The fixed parameters and the notice**, on that reading. An
*occurrence* is one of the constants together with all the arguments it
is applied to, none included, in a conclusion or a premise. A position's
*common variable* is the variable every occurrence of every predicate
carries at that position, the same by name and by its read `typ`,
compared with `=`; a position has none when some predicate has no
occurrence, some occurrence has fewer arguments, or two occurrences
differ there. The *run* is the longest
run of leading positions whose common variables are all different,
each a rule's variable — one the rule's closing binds, not one its
conclusion's own `⋀` binds (counted on the rule's parse) nor one the
context fixes, such as a `Locale`'s parameter — or a parameter step 1
fixed. With `fixed_parameters` `None`, the run's variables are the
parameters: the criterion Isabelle's own check applies to them
(`inductive.ML`, `dest_predicate`), so Isabelle accepts them on the
reading they were found on. With `fixed_parameters` recorded, the
recorded names are the parameters, and a refusal is the definition's
failure, never a switch (COMMON.md §5).

The notice, at every evaluation that goes through, while some rule's
premise mentions a predicate: each rule's variable not among the run's
that is a later position's common variable, in position order, and
the constants, in their order; names joined by the framework's
`series` with `and`. The definition goes through all the same:

```
An optimization is possible: `r` is unchanged throughout the rules but is not the first argument of `star`; make it the first argument.
```

```
An optimization is possible: `r` and `s` are unchanged throughout the rules but are not the first arguments of `star`; make them the first arguments.
```

```
An optimization is possible: `r` is unchanged throughout the rules but is not the first argument of `even` and `odd`; make it the first argument.
```

**Step 2, the definition.** One transition on the input slot's state,
through `apply_transition` (MODULE_STRUCTURE §2.4), on the command's
arguments for the parameters:

```
Toplevel.local_theory NONE NONE
  (snd o Inductive.add_inductive_cmd true coind cnames_syn pnames_syn specs [])
```

— the call the command's parser makes (`inductive.ML`,
`gen_ind_decl`), so the evaluation runs what the file runs. `coind` is
true under `coinductive`; the monotonicity lemmas are none. The
transition refused — a conclusion that applies no predicate, rules that
are not monotone — is the definition's failure, with Isabelle's
messages. Isabelle's progress lines, `Proofs for inductive
predicate(s) …`, are `writeln`s, which `apply_transition` does not
collect. The monotonicity proof (`Goal.prove_future`) runs inside the
transition, since no goal of a node's commands forks
(EVALUATOR_DESIGN §6), so its failure is the definition's.

**The answer.** A failure writes no state into the resulting slot; the
callback answers the messages, and `_eval_opr` returns `CannotEvaluate`
with them: the node is an obstacle, and its `fixed_parameters` stay what
the last evaluation that went through recorded. Otherwise the callback
answers no messages, the parameters it ran and the notice's variables;
`_eval_opr` stores the parameters and returns `Ready` with the notice,
or with no messages. At theory level these are the steps the
hand-written text takes; inside a `Context` or `Locale` the definition
is made in that context.

## 7. The mark

`Inductive` keeps the framework's default (PRINT.md §1): `complete` when
the definition went through, `failed` when it is an obstacle, `not
evaluated` otherwise; it owes nothing after its evaluation, so
`incomplete` never appears on its line.

## 8. What it prints

`print_fields` (PRINT.md §3) writes the definition, and only under
`Recall`; it writes no keyed line, and answers so (PRINT.md §2);
wherever it is called the framework writes the evaluation's messages
after it:

| mode | `print_fields` writes |
| --- | --- |
| `Out_Focus` | nothing |
| `Briefing` | not called |
| `Relative_Focus`, a focus | nothing |
| `Recall`, depth 0 | the constants, the rules each with its `english`, `english` |
| `Recall`, depth 1 and 2 | the constants, the rules |
| `Recall`, depth 3 | nothing |

The constants are one line, as `fixes_text` writes them with the stored
text bare, then ` for ` and the recorded fixed parameters, names alone
— a parameter's type stands first in each predicate's —, when there are
any; each rule one line: its name, `: `, the conclusion,
` if ` and the premises joined by ` and ` when there are premises,
` for ` and its `for_any` less the fixed parameters as `fixes_text`
writes them, bare, when any remain — no quotes. The constants and the
rules stand one level deeper than `english`, a rule's `english` one
level deeper than its rule; all in the `unicode` spelling, assembled
from the stored text without a round trip to Isabelle.

```
- inductive_star (complete)
    star :: ('a ⇒ 'a ⇒ bool) ⇒ 'a ⇒ 'a ⇒ bool for r
    refl: star r x x
      Every element reaches itself
    step: star r x z if r x y and star r y z
      A step of r followed by a path is a path
  The reflexive transitive closure of a relation r
```

A node that draws §6's notice, at depth 1, and one whose rules Isabelle
refused:

```
- inductive_star (complete)
    star :: 'a ⇒ 'a ⇒ ('a ⇒ 'a ⇒ bool) ⇒ bool
    refl: star x x r
    step: star x z r if r x y and star y z r
  Notice:
    An optimization is possible: `r` is unchanged throughout the rules but is not the first argument of `star`; make it the first argument.
```

```
- inductive_star (failed)
    star :: ('a ⇒ 'a ⇒ bool) ⇒ 'a ⇒ 'a ⇒ bool
    refl: star r x x
      Every element reaches itself
    step: r x z if r x y and star r y z
      A step of r followed by a path is a path
  The reflexive transitive closure of a relation r
  Error:
    Ill-formed introduction rule "step"
    ⟦r x y; star r y z⟧ ⟹ r x z
    Conclusion of introduction rule must be an inductive predicate
```

(Isabelle's own message, measured in Isabelle2025-2.)

## 9. Id properties

None declared: a leaf's component is the last of every id, and the
framework's defaults stand (MCP_SPECIFICATION §2.1). The component is
the kind and the predicates' names joined by `_and_`,
`inductive_even_and_odd`; a lone predicate named `even_and_odd` bears
the same component as the pair and is refused beside it as a
`DuplicateName`.
