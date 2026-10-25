# The `Locale` node class

Status: proposed 2026-10-20; revised through 2026-10-23 after four
adversarial reviews (ai-artifacts/review/locale/; runs wf_bc80f426-db4,
wf_9adf83e4-932, wf_68676e20-274 and wf_a0477420-c81) and the owner's
rulings; the agent-facing sentences below are the owner's, but for
the forms §6 derives from them by its stated rules and the descriptions
shared with the other classes. Not implemented. Its
implementation also makes the amendment of `Theorem`'s check of
undeclared variables, with the writer of its sentence's head, which
the axioms' sentences of §6 share, and the ML joiner of a list
(THEOREM.md §2, §6); the `locale name` grammar of the framework
(RENDER_BASELINES §2, EXCEPTIONS.md §3); the arm `NoSyntax` in code,
with which RENDER_BASELINES §2's `must be one of` line ends with
`NoSyntax`; the framework's admission of JSON null as an arm of a union
(§2; PLUGIN_SYSTEM §5, MODULE_STRUCTURE §4.4, RENDER_BASELINES §2);
`statement.py`'s reader (COMMON.md §4); `common.py`'s
`Variable_With_Syntax` with its wire and writer, and
`TAT_Mixfix.fixes` with its converse `TAT_Mixfix.arm_of`, which
`Define`'s constants take (DEFINE.md §1, §2, §5, §8); `common.py`'s
`dotted_name_of`, with LIFTING_CONTEXT.md §4's fence and
test_lifting_context.py; the refusal of a `LiftingContext` on a Lifting
setup whose quotient theorem keeps an exported premise, through
`Exported_Premises.count_of` on the restore data it reads, with its
sentence (§6; LIFTING_CONTEXT.md §6); and the refusal of a
`LiftDefinition` on one, with its sentence (§6; LIFT_DEFINITION.md
§6). It waits for the light locale component (contrib/light_locale):
the header elements `implicit_structure` and `no_implicit_structure`,
with the declaration function that takes either and checks the
structure; the function that lists, for each import, the implicit
structure it would give (`Locale.parent_implicit_structures`); the
function that writes the notice of §6; and the export
`Expression.eliminated_params`. The light locale's discharge of a
Lifting setup's premise in an importing block (§6) comes later and
gates nothing here.

A `Locale` declares a light locale — `light_locale`, the locale
command of the light locale component, the one locale command of a
forest — from the locales it extends, its parameters and the axioms on
them, and holds, inside its block, the declarations belonging to the
local theory. Every theory of a forest has the command through
`TAT_Std`, which imports `Light_Locale.Light_Locale` (PLUGIN_SYSTEM
§1). When the locale or one of its imports has an axiom, the light
locale defines the locale's **predicate**, a constant named after the
locale applied to the parameters the axioms mention, `bounded n`, which
holds exactly when the axioms do.

The declaration runs only at the top level of a theory: the node
stands in its `Theory`, directly or under a `Section`, and its
`cannot_stand_under` refuses every other place (§6; PLUGIN_SYSTEM §2;
this plugin's table, COMMON.md §1); nothing but a `Locale` is refused
inside it. Inside the block Isabelle is in the
locale's local theory, and a fact a child declares is qualified by the
locale, `idempotent_semigroup.idem_twice`, and is referred to so
outside the block (§6). The class opens no proof obligation and has
no jobs (INDEX.md). It is a `StdBlock` of the plugin `Isabelle_Std` —
`class Locale(StdBlock)` — defining the four hooks of a block itself,
the beginning's two and the ending's two (PLUGIN_SYSTEM §5). Its Python
half is `isabelle_theory_agent/std/locale.py`, its ML half
`Isabelle_Std/ML/TAT_Locale.ML`. Its agent-facing wording lives here —
the `description` texts of its construct schema (§3), the sentences its
`gen` and its evaluation render (§4, §6) — pinned by the baseline
tests the way RECORD.md's are.

One kind, `locale`, which heads the id component:
`locale_idempotent_semigroup`; a child's id carries it,
`locale_idempotent_semigroup.lemma_idem_twice` (§9).

## 1. Fields

| Field | Type | |
| --- | --- | --- |
| `kind` | `locale` | authored |
| `english` | what is defined, `str` | authored |
| `name` | `str`, the locale's name and the node's, in the id grammar without hyphens — a letter, then letters, digits, underscores and primes, not ending in an underscore (MCP_SPECIFICATION §2); one outside it is refused with the grammar's own sentence, as a `Theorem`'s is | authored |
| `imports` | the locales this one extends, each a `Locale_Instance` (§2; COMMON.md §4): the locale's name, an optional qualifier, and one instantiation per parameter of that locale, each a parameter's name and a term; empty when there are none | authored |
| `fixes` | the parameters, each a `Variable_With_Syntax` (COMMON.md §4): a name, an optional type and an annotation — a `Mixfix`, `NoSyntax`, or none when `syntax` is left out; empty when there are none | authored |
| `assumes` | the axioms, each a name and a `Statement` (THEOREM.md §2): its `english`, its `for_any` variables, its `premises` and its `conclusion`; empty when there are none | authored |
| `implicit_structure` | an `IsaTerm`, the structure that notation written without a subscript refers to in the axioms and inside the block, or none for no structure (§2) | authored |
| `annotations` | one optional `Mixfix` per parameter, in `fixes`' order: the annotation each parameter takes from an import (§2), none when it takes none; which the evaluation finds (§6) and the file writes (§5) | recorded |
| `parenthesised_conclusions` | one `bool` per axiom, in `assumes`' order: whether the file writes the axiom's conclusion in parentheses (§5), which the evaluation finds (§6) | recorded |
| `children` | the nodes inside the block, the framework's row (PLUGIN_SYSTEM §3; ARCHITECTURE §4.1) | — |

The recorded fields are recorded anew by every evaluation of the
beginning that goes through, and stored; until a beginning has gone
through they are None-valued, as is `implicit_structure` when it is
none, so that every row of the class is read with `rows.get` and any
row missing is refused at start. The recorded fields are no choice the
evaluation keeps to (COMMON.md §5): each is what the beginning found;
the emission reads them behind `can_emit` (§5), and `recall` reads
`parenthesised_conclusions` behind the beginning's instant status (§8).

The node has two operations, the beginning and the ending
(MODULE_STRUCTURE §4.1). What the beginning's last evaluation reported
travels on its status, as for every class (COMPILATION.md §4):
`CannotEvaluate (messages)` when the declaration was refused, `Ready`
when it went through, with the messages of §6 — the cancellation of
inherited implicit structures, the notice — when there are any and
none otherwise; the ending's likewise (§6). Its constructor
takes the parent, the input slot and its fields; `StdBlock` builds it
with no children and mints its slot before the ending (MODULE_STRUCTURE
§4.1).

## 2. The declaration

A locale is a name, the locales it extends — each with every parameter
instantiated by a term —, its own parameters, the axioms on them, its
implicit structure, and its block:

```json
{
  "kind": "locale",
  "english": "A semigroup whose operation is idempotent",
  "name": "idempotent_semigroup",
  "imports": [
    {"locale": "semigroup", "qualifier": "S",
     "instantiations": [{"name": "f", "term": "f"}]}
  ],
  "fixes": [
    {"name": "f", "type": "'a ⇒ 'a ⇒ 'a", "syntax": {"form": "infixl", "symbol": "⊗", "priority": 70}}
  ],
  "assumes": [
    {"name": "idem",
     "statement": {"english": "Applying the operation to an element and itself gives it back",
                   "for_any": [{"name": "x", "type": "'a"}],
                   "conclusion": "x ⊗ x = x"}}
  ],
  "implicit_structure": null,
  "children": [
    {"kind": "lemma", "name": "idem_twice",
     "statement": {"english": "Applying the operation to an element twice over gives it back",
                   "for_any": [{"name": "x", "type": "'a"}],
                   "conclusion": "x ⊗ (x ⊗ x) = x"}}
  ]
}
```

and, with an implicit structure, on HOL-Algebra's `monoid`, whose one
parameter `G` is a structure:

```json
{
  "kind": "locale",
  "english": "A monoid whose operation is commutative",
  "name": "commutative_monoid",
  "imports": [
    {"locale": "monoid", "qualifier": "M",
     "instantiations": [{"name": "G", "term": "G"}]}
  ],
  "fixes": [{"name": "G", "type": "('a, 'b) monoid_scheme"}],
  "assumes": [
    {"name": "comm",
     "statement": {"english": "Multiplication is commutative",
                   "for_any": [{"name": "x", "type": "'a"}, {"name": "y", "type": "'a"}],
                   "premises": [{"name": "hx", "term": "x ∈ carrier G"}, {"name": "hy", "term": "y ∈ carrier G"}],
                   "conclusion": "x ⊗ y = y ⊗ x"}}
  ],
  "implicit_structure": "G"
}
```

`kind`, `english`, `name` and `implicit_structure` are required;
`imports`, `fixes` and `assumes` are optional and empty when left out;
`children` is optional, as for every nesting class (PLUGIN_SYSTEM §3),
and contents come later through `edit` as well. In a `LocaleInstance`
`locale` and `instantiations` are required, `qualifier` optional and
absent when left out; in an instantiation `name` and `term` are
required; in a parameter `name` is required, `type` and `syntax`
optional, an empty `type` no type; in an axiom `name` and `statement`
are required, and the statement is a `LongStatement` as a `Theorem`'s
is (THEOREM.md §2). `gen` normalises every piece of Isabelle text and
`english` once, when the construct is accepted: newlines become spaces
and runs of whitespace one space — in a syntax's `symbol` or `template`
newlines and tabs alone; printing, emission and evaluation all use the
stored text.

**The parameters.** The parameters of the locale are exactly `fixes`:
each import has every parameter it does not define instantiated by a
term over `fixes`, and none of its parameters becomes a parameter of
this locale under its own name — the evaluation refuses an import that
leaves one uninstantiated (§6). A parameter the imported locale defines
by a `defines` clause is instantiated with `_`; left out, or
instantiated with the right-hand side of its definition, it is the
same declaration to Isabelle, and a term other than that is Isabelle's
to refuse (§6). Isabelle does not carry an imported parameter's mixfix
annotation over when the parameter is instantiated. A parameter whose
`syntax` is left out and which instantiates an imported parameter of
the same name — the instantiation `f = f` — takes that parameter's
annotation when a `Mixfix` can express it, so that the import's
notation reads in the axioms and the block as it does in the import;
when several imports instantiate a parameter of its name so, the
first of them in `imports`' order gives it, and it has none when that
one's annotation is a `(structure)`, `implicit_structure` standing for
it, or a binder whose body priority differs from its own. A parameter whose `syntax`
is `NoSyntax` has no annotation (COMMON.md §4).

**The axioms.** Every variable an axiom's premises and conclusion use
is a parameter or declared in its `for_any`; a `for_any` variable is
never a parameter's name, which `gen` refuses (§4), since the
quantifier would hide the parameter. A premise's `name` is checked by
`gen` and stored; nothing else uses it — the file, the forms Isabelle
reads (§6) and the `recall` line leave it out.

**The implicit structure.** Required, a term or `null`. A term is the
structure that notation written without a subscript refers to, in the
axioms and inside the block — `x ⊗ y` for `x ⊗⇘G⇙ y` —, a term over
`fixes`; the declaration carries it as the light locale's header
element `implicit_structure` (§5), and it is the locale's, in force
wherever the locale is opened; a locale extending it names its own, a
term or `null`. `null` is no structure:
the declaration carries the header element `no_implicit_structure`,
which cancels every structure the locale would inherit — an import's
own implicit structure and an imported parameter's `(structure)`
annotation alike —, so that notation without a subscript does not read in the
axioms or the block, and notation with one reads as everywhere. No
structure is inherited otherwise: the locale's is the one it names.

`imports[].locale`, `imports[].qualifier`,
`imports[].instantiations[].name`, `imports[].instantiations[].term`,
`fixes[].name`, `fixes[].type`, a syntax's `symbol` or `template`,
`assumes[].name`, every piece of Isabelle text of an axiom's statement
(THEOREM.md §2) and `implicit_structure` are `IsaTerm`s
(MODULE_STRUCTURE §4.3); `name`, `english` and an axiom's `english` are
`str`.

`LocaleInstance` is shared through `LOCALE_INSTANCE_DEFS`,
`VariableWithSyntax` through `VARIABLE_WITH_SYNTAX_DEFS`,
`LongStatement` and `Variable` through `STATEMENT_DEFS`, and `Mixfix`,
which `VariableWithSyntax` reaches, through `MIXFIX_DEFS`, all the
plugin's (COMMON.md §4); an axiom is an inline object of this class,
used nowhere else.

The class's construct schema:

```jsonc
{
  "type": "object",
  "description": "A light-weight Isabelle locale: lets you define a local theory (like group theory) under axioms and develop theorems under it.",
  "properties": {
    "kind":               { "const": "locale" },
    "english":            { "type": "string", "description": "what is defined, in English, as LaTeX text" },
    "name":               { "type": "string" },
    "imports":            { "type": "array", "items": { "$ref": "#/$defs/LocaleInstance" },
                            "description": "the local theories this locale extends. Example: group extends monoid; a ring extends an abelian group (its addition) and a monoid (its multiplication)" },
    "fixes":              { "type": "array", "items": { "$ref": "#/$defs/VariableWithSyntax" },
                            "description": "the locale's parameters: fixed variables in the local theory, such as a group's carrier set and its operation" },
    "assumes":            { "type": "array",
                            "items": { "type": "object",
                                       "properties": { "name": { "type": "string" }, "statement": { "$ref": "#/$defs/LongStatement" } },
                                       "required": ["name", "statement"], "additionalProperties": false },
                            "description": "axioms in the local theory, such as the associativity law" },
    "implicit_structure": { "anyOf": [{ "type": "string" }, { "type": "null" }],
                            "description": "the default Isabelle term that allows notation like `A ⊗⇘default⇙ B` to be written `A ⊗ B`, usually the background mathematical structure such as a group or ring. Set it to null for no such default." },
    "children":           { "type": "array", "items": { "$ref": "#/$defs/Construct" },
                            "description": "the declarations belonging to the local theory" }
  },
  "required": ["kind", "english", "name", "implicit_structure"],
  "additionalProperties": false,
  "$defs": { ...LOCALE_INSTANCE_DEFS, ...VARIABLE_WITH_SYNTAX_DEFS, ...STATEMENT_DEFS, ...MIXFIX_DEFS }
}
```

`#/$defs/Construct` is the framework's (PLUGIN_SYSTEM §4).
The arm `{"type": "null"}` in `implicit_structure`'s `anyOf` is the
one place the plugin's schemas admit JSON null; the implementation
admits it in the framework's schema grammar as an arm of a union
alone, and in the argument schema as `str | None` (PLUGIN_SYSTEM §5;
MODULE_STRUCTURE §4.4); a value of another type is refused by the
framework's check of the construct with

```
The field `implicit_structure` must be a string or null.
```

The class carries a description, its name alone not saying what a
light locale is for the agent; `kind`, `name` and an axiom's `name`
carry none: the kind is Isabelle's own word, and the names say what
they hold (COMMON.md §5).

What the class does not take: the stock `locale` command; a
`defines`, `notes` or `constrains` element; `opening`, the bundles a
header opens; `rewrites` on
an import; positional instantiation of an import's parameters, and the
optional qualifier `M?:`; `(structure)` on a parameter, the
`implicit_structure` standing for it; a `for` clause of its own, `fixes`
being written there (§5); `set_implicit_structure` inside the block,
the header element standing for it.

## 3. Descriptions

The class:

```
A light-weight Isabelle locale: lets you define a local theory (like group theory) under axioms and develop theorems under it.
```

`english`:

```
what is defined, in English, as LaTeX text
```

`imports`:

```
the local theories this locale extends. Example: group extends monoid; a ring extends an abelian group (its addition) and a monoid (its multiplication)
```

`fixes`:

```
the locale's parameters: fixed variables in the local theory, such as a group's carrier set and its operation
```

`assumes`:

```
axioms in the local theory, such as the associativity law
```

`implicit_structure`:

```
the default Isabelle term that allows notation like `A ⊗⇘default⇙ B` to be written `A ⊗ B`, usually the background mathematical structure such as a group or ring. Set it to null for no such default.
```

`children`:

```
the declarations belonging to the local theory
```

The descriptions of `LocaleInstance` — its `locale`, `qualifier` and
`instantiations`, and an instantiation's `name` and `term` —, of
`VariableWithSyntax.type` and of `Mixfix` are COMMON.md §4's, and the
descriptions of `LongStatement` are THEOREM.md §3's, pinned there
alone.

## 4. `gen`

`Locale.gen` checks, in this order: `name` against §1's grammar, the
node's name (`InvalidName` with `grammar` = `locale name`, rendered
with the fact name's text, RENDER_BASELINES §2's seventh form; the
implementation adds the grammar to the framework's `GRAMMARS`, to the
Literals of `InvalidName` and `require_id_name`, to EXCEPTIONS.md §3
and to RENDER_BASELINES §2); then
each import by `Locale_Instance`'s reader under `imports[i]` (COMMON.md
§4); then every parameter's `name` an Isabelle identifier not ending
with an underscore (COMMON.md §5), no two the same; then every axiom's
`name` an Isabelle identifier, no two the same, and its statement by
the shared statement reader under `assumes[i].statement` (COMMON.md
§4; THEOREM.md §4); then every axiom's `for_any` names against
`fixes`: one that is a parameter's name is refused; then
`implicit_structure`, a term not blank or `null` (`InvalidField`). A
sibling already bearing the node's id component is the framework's
`DuplicateName` (MCP_SPECIFICATION §2). Whether an imported locale
exists, whether an instantiation names one of its parameters, whether
every parameter of it is instantiated, whether each instantiation's
term is a term over the parameters, whether the terms and types parse,
whether an axiom's variables are declared, and whether the implicit
structure is a term over the parameters, are judged at evaluation (§6;
MODULE_STRUCTURE §4.1); a refusal there is an evaluation failure, not
an exception. Where the node stands is the framework's placement check,
at evaluation (MODULE_STRUCTURE §4.1). The children are the framework's:
built by their own classes' `gen`s and placed under the node
(MODULE_STRUCTURE §4.2).

The class has no jobs, so an amend carries nothing over: the
replacement is a fresh node with the children it inherits
(MODULE_STRUCTURE §4.2).

The `InvalidField` sentences of the class's own:

```
The field `fixes[1].name` must be an Isabelle identifier: it starts with a letter and continues with letters, digits, underscores and primes ('), and does not end with an underscore.
The field `fixes[1].name` repeats `f`.
The field `assumes[1].name` must be an Isabelle identifier: it starts with a letter and continues with letters, digits, underscores and primes ('), and does not end with an underscore.
The field `assumes[1].name` repeats `idem`.
The field `assumes[0].statement.for_any[0].name` declares `n`, which is already declared in `fixes`: a variable declared in `fixes` must not be declared again in `for_any`.
The field `implicit_structure` must be an Isabelle term, or null for no implicit structure at all.
```

`Locale_Instance`'s reader's sentences are COMMON.md §4's, the
`repeats` sentence is COMMON.md §4's under this class's paths, and the
statement reader's sentences are THEOREM.md §4's under the path
`assumes[i].statement`, each pinned in its home alone. The grammar text
after the colon is the framework's, the one `InvalidName` renders for
the grammar `locale name` (RENDER_BASELINES §2), written once and used
by both (COMMON.md §5).

## 5. Emission

The node emits, when its `can_emit` holds — `Locale` keeps the
framework's default, both stored statuses `Ready` (COMPILATION.md §3),
under which the recorded fields are recorded — the beginning: the
`text` line, the declaration and `begin`; then one empty line when the
block has children; the children in order, one empty line between
siblings, at the block's own indent, the framework's (COMPILATION.md
§3); the ending: one empty line and `end`:

```
text ‹A semigroup whose operation is idempotent.›
light_locale idempotent_semigroup =
  S: semigroup where f = f
  for f :: "'a ⇒ 'a ⇒ 'a" (infixl "⊗" 70) +
  no_implicit_structure
  assumes idem: "⋀(x::'a). x ⊗ x = x"
    ―‹Applying the operation to an element and itself gives it back.›
begin

text ‹Lemma idem_twice. Applying the operation to an element twice over gives it back.›
lemma idem_twice:
  fixes x :: "'a"
  shows "x ⊗ (x ⊗ x) = x"
  by aoa

end
```

and, with an implicit structure and no child:

```
text ‹A monoid whose operation is commutative.›
light_locale commutative_monoid =
  M: monoid where G = G
  for G :: "('a, 'b) monoid_scheme" +
  implicit_structure G
  assumes comm: "⋀(x::'a) (y::'a). ⟦x ∈ carrier G; y ∈ carrier G⟧ ⟹ x ⊗ y = y ⊗ x"
    ―‹Multiplication is commutative.›
begin

end
```

and, extending nothing:

```
text ‹A positive bound.›
light_locale bounded =
  fixes n :: nat
  no_implicit_structure
  assumes pos: "0 < n"
    ―‹The bound is positive.›
begin

end
```

- The `text` line: `english` alone, no lead (COMMON.md §2).
- The head, `light_locale`, the name and `=`, the header element
  being always there.
- Below the head every line is indented two spaces; when the locale
  has an import, a ` +` ends every import line but the last and the
  line before the first element — the `for` line, or the last import
  line when there is no parameter.
- Each import on its own line, as `locale_instance_text` writes it
  (COMMON.md §4): `S: semigroup where f = f`, `padic_integers where Zp
  = _ and p = p`.
- The parameters, when the locale has an import, in the `for` clause
  on one line after the imports: `for` and `fixes_text` over the
  parameters (COMMON.md §4), each whose `syntax` is left out passed
  with its recorded `annotations` entry in place of none — `for f :: "'a
  ⇒ 'a ⇒ 'a" (infixl "⊗" 70)`; when it has none, as a `fixes` element
  in the same shape. The `for` clause is read before the imports'
  declarations are active: a type that a locale's block declares is
  written in a parameter's type by its full name, the declaring
  locale's before it, as outside any block (`T0.t`); the short name,
  and `Q.t` under a qualifier `Q`, serve in the axioms and in the block
  alone.
- The implicit structure on its own line: `implicit_structure G`,
  `implicit_structure "padic_int p"`, or `no_implicit_structure` for
  `null`.
- Each axiom on its own line, `assumes`, its name, a colon and its
  proposition as a string token, which one private writer of
  locale.py writes from the statement, given whether the conclusion
  stands in parentheses: one `⋀` binding the `for_any` variables in
  their order, a typed one in parentheses with its type after `::`,
  `⋀(x::'a) y (z::'b).`, none when `for_any` is empty; then the
  premises in their order, their names
  left out, inside `⟦` and `⟧` separated by `; ` and followed by ` ⟹ `,
  none when there is no premise; then the conclusion, in parentheses
  when the recorded `parenthesised_conclusions` says so (§6). Under the
  line, indented two spaces more, the axiom's `english` as a formal
  comment, `―` before `english_cartouche`'s text (COMMON.md §2).
- `begin` on its own line at the block's indent; the children's text is
  their own, each class's `emit`, at the block's indent: the file
  reads as the library's do; `end` on its own line at the block's
  indent.
- Every piece of Isabelle text — the locale's name, an import as
  `locale_instance_text` writes it, a parameter's name and type, the
  implicit structure, an axiom's name — is written through the
  theory's `print_name` (SESSION_AND_THEORY §2): bare when its `ascii`
  is an Isabelle identifier (`is_identifier`, COMMON.md §5) that is not
  a keyword of the theory, as Isabelle's string token (COMPILATION.md
  §3) otherwise — `f` and `G` bare, `"'a ⇒ 'a ⇒ 'a"` and a keyword
  quoted, `assumes "open": …`; the exceptions: an axiom's proposition
  is always a string token, an import's dotted locale name and the
  instantiation `_` are written bare (COMMON.md §4), and a syntax's
  symbol is written by `mixfix_text`.
- The text in the `unicode` spelling; the file takes the `\<name>` form
  from the compile's conversion (COMPILATION.md §2) and reads as Unicode
  in jEdit all the same.

## 6. Evaluation

Before the beginning runs, the placement check asks the node's
`cannot_stand_under` (PLUGIN_SYSTEM §2): it refuses every ancestor in
its tree but the theory and a `Section` (COMMON.md §1) — a
`Lifting_Block` (COMMON.md §6) with `Move it out.` (COMMON.md §1)
followed by the sentence below; any other ancestor with `Move it out.`
alone. The
sentence, a constant of locale.py pinned by the class's test:

```
Reopen a `lifting_context` within the locale if you need it.
```

The beginning declares the locale and opens its block; the ending
closes the block; neither runs a proof (ARCHITECTURE §3.6). Both go
through the ML interfaces, each as one operation
(`TAT_Common_Nodes.operation'` for the beginning, which yields the
recorded fields and the notice, `operation` for the ending;
MODULE_STRUCTURE §2.5).

**The beginning.** `_eval_beginning_opr` sends the class's callback
`TAT.Locale.open` the beginning's two slots —
`operation_slots("beginning")`: the input slot and the beginning's
resulting slot, the first child's input or the slot before the ending
when there is no child (MODULE_STRUCTURE §4.1) — and the declaration
as structure: the name; the imports, each `Locale_Instance`'s wire
(COMMON.md §4); the parameters, each `Variable_With_Syntax`'s wire and
whether its `syntax` was left out; the axioms, each its name and two
texts of its proposition written by §5's writer and sent in `ascii`,
as `mixfix_wire` sends `mixfix_text`'s, the premises bare in both —
the **declared form**, the conclusion in parentheses, and the
conclusion bare —; and the implicit structure, a term or none — each
`IsaTerm` as its `ascii`. The ML writes no text of the declaration's
terms. A test pins the order of what is sent and of the answer, as
THEOREM.md's does.

The callback runs one operation. It first judges the imports, in the
input state's context (`Toplevel.context_of`): every import's locale
name, in order, through `Locale.check`, which raises Isabelle's own
`Undefined locale: "semigrp"` for a name no locale bears — that is the
run's one message, and no import's parameters are judged —; then each
import's parameters, `Locale.params_of`, less those the instantiations
name and less those the locale defines by a `defines` clause
(`Expression.eliminated_params`, the light locale's export). The
parameters left are those the import would keep under its own name,
and the run is refused with one message per import that leaves any,
in the imports' order, its parameters in their order:

```
The import `semigroup` leaves its parameter `f` uninstantiated: instantiate it in `imports[1].instantiations`.
The import `monoid` leaves its parameters `f` and `z` uninstantiated: instantiate them in `imports[1].instantiations`.
```

naming the import as authored — its qualifier and a colon when it has
one, then the locale's name, `M: monoid`, by one ML helper, which the
message below on an undeclared variable that is an import's parameter
uses too —, the parameters as
the import declares them and the field's path. Every import is judged
for its parameters, and any refusal means the declaration does not
run. In every sentence of TAT's own in this section a list of names — parameters,
axioms, variables — is joined by `, ` with ` and ` before the last;
the constants the qualified-constant sentence offers, alphabetically
as written, by `, ` with ` or ` before the last — written by one ML
joiner taking its last word, the twin of the framework's
`exceptions.series`. In the same pass, for each parameter whose
`syntax` is left out, the first import in `imports`' order whose
instantiations name a parameter of its name with a term whose
`ascii` is that name gives its annotation through `TAT_Mixfix.arm_of`
(COMMON.md §4). Its result, the arm in `ascii`, which Python reads
with `IsaTerm.from_isabelle`, is recorded as `annotations`; the
transition takes the `mixfix` the arm stands for, `NoSyn` when there
is none. test_common pins, for every form of `MIXFIX_DEFS`, that
`TAT_Mixfix.read` of `mixfix_wire` of the arm is `Mixfix.equal` to it.

With every import accepted the callback runs, in the same operation,
the declaration's transition into the resulting slot — the shape of
`begin_theory`, through `apply_transition` (MODULE_STRUCTURE §2.4) —,
what `light_locale … begin` parses to (Light_Locale.thy):

```
Toplevel.begin_main_target true
  (Expression.add_light_locale_cmd name Binding.empty [] expression structure elements #> snd)
```

`name` the locale's name as a binding; the bundles `[]`; `expression`
the imports, each `((locale, Position.none), ((qualifier, true),
(Expression.Named instantiations, [])))` — the qualifier `("", false)`
when none, the instantiations each `(parameter, term)`, no `rewrites`
— with the parameters as the `for` clause, read by `TAT_Mixfix.fixes`
(COMMON.md §4), each `(binding, type option, mixfix)`, an annotation
found above in place of `NoSyn`; also when there is no import, where
the file writes a `fixes` element (§5): the locale is the same either
way. `structure` the light locale's three-valued argument
(`Syntax_Trans.Inherit | Cancel | Declare`): `Declare` with the term's
`ascii`, or `Cancel` for none; never `Inherit`, `implicit_structure`
being required. Its own checks of the structure run inside the
transition, and their sentences are the light locale's
(Light_Locale.thy). `elements` one `Element.Assumes [((binding, []),
[(proposition, [])])]` per axiom, in `assumes`' order, the proposition
the declared form, none when there is no axiom — the elements the
file's lines parse to.

Then, in the state the declaration leaves, four steps: two readings of
the axioms, the notice, and the cancelled implicit structures. Each axiom's texts are read through
`Syntax.read_prop` in the locale's context (`Locale.init`) over the
theory the declaration leaves, with the constants the declaration
defined — the heads of `Locale.intros_of`'s rules: the predicate, and
`L_axioms` when there is one — hidden (`Sign.hide_const true`): the
context Isabelle read the axioms in, and the build reads the file in.
The names are classified in the state the declaration leaves.

First, the axioms' undeclared variables: the free variables of each
axiom's declared form that the locale's parameters do not fix
(`Variable.add_free_names`, which skips the fixed). The names the light
locale no longer binds because an import's definition was unfolded
(`Locale.eliminated_names_of`, which gives the definition) are judged
once, over every axiom, first, one message per name, alphabetically:

```
The variable `Zp` stood for the local definition `Zp ≡ padic_int p`. Since TAT doesn't allow a locale to define its parameters, `Zp` cannot be used any more. If you meant the definition, write `padic_int p`; if you meant merely a variable, use another name.
```

Then, over the names left, one message per name that is the name of
an import's parameter, alphabetically, naming the axioms it occurs in,
in `assumes`' order, every such import in `imports`' order — named as
above — and the term each instantiates it with:

```
Undeclared variable `f` in the axiom `assoc`. If you meant the parameter `f` of the import `semigroup`, write `g`; otherwise, declare it in `fixes` or `for_any`.
Undeclared variable `f` in the axiom `assoc`. If you meant the parameter `f` of the import `A: semigroup`, write `g`; of the import `B: semigroup`, write `h`; otherwise, declare it in `fixes` or `for_any`.
```

Then, over the names still left, one message per name that the local theory bears as the short
name of constants under an import's qualifier: the constants the
imports bring into the block, those whose full name starts with
`local.`, with this name as their short name, each as
`Name_Space.extern` writes it, `Q.dbl`, `Q.R.dbl`, `R.dbl`; with one
such constant, the import named is its written form less its short
name (`Long_Name.qualifier`), `Q`, `Q.R`, `R` — the last the qualifier
of an import of an import; the names alphabetically, each naming the
axioms it occurs in, in `assumes`' order:

```
Undeclared variable `dbl` in the axiom `a1`. If you meant the constant of the import `Q`, write `Q.dbl`; if you meant a variable, declare it in `for_any`.
Undeclared variable `dbl` in the axiom `a1`. If you meant a constant of an import, write `A.dbl` or `B.dbl`; if you meant a variable, declare it in `for_any`.
```

Last, one message for every name still left, over all the axioms: the
names alphabetically in one list, then the axioms they occur in, in
`assumes`' order, in another; `variable` or `variables` by the number
of names, `the axiom` or `the axioms` by the number of axioms, and the rest of
the message likewise — `it` for one name, `each one` for several; `the
axiom is` or `the axioms are` for one name, `an axiom` for several:

```
Undeclared variable `m` in the axiom `pos`. If it is a parameter of the locale, declare it in `fixes`; if the axiom is to hold for every value of it, declare it in `for_any`.
Undeclared variable `m` in the axioms `pos` and `comm`. If it is a parameter of the locale, declare it in `fixes`; if the axioms are to hold for every value of it, declare it in `for_any`.
Undeclared variables `m`, `x` and `y` in the axioms `pos` and `comm`. Declare each one that is a parameter of the locale in `fixes`, and each one an axiom is to hold for every value of in `for_any`.
```

Each message's head, `Undeclared variable(s) … in the axiom(s) …`, is
written by the one writer `Theorem`'s sentence's head shares (THEOREM.md
§6).

Isabelle itself closes an undeclared variable of an axiom universally,
which would leave a locale that reports `Ready` and means something
else; any of these messages refuses the run.

Second, each axiom's conclusion: the text with the conclusion bare,
read, is compared with the declared form read the same way; when the
reading goes through and gives the same term (`aconv`), the file
writes the conclusion bare, otherwise in parentheses — recorded as
`parenthesised_conclusions`.

Third, the notice: the light locale's function that writes its
warnings, `Expression.unfolded_definitions_message`, over the context
the `light_locale … begin` transition leaves — `Toplevel.context_of` of
the state after it, the context the command prints in, which the
printing depends on — and the locale's full name, so that the notice
and the warning are the same text, gives the lines it prints when the
declaration unfolds a
definition of an imported locale — a parameter that locale defines by
a `defines` clause, replaced by its definition and no longer bound, as
`Zp` under `padic_integers` — and, for each such name that `fixes`
declares again, the sentence that it is a fresh variable here; the
lines joined (`cat_lines`), with Isabelle's markup stripped
(`Protocol_Message.clean_output`, as `messages_of_errors` strips an
error's, MODULE_STRUCTURE §2.4), are one message, none when there is no
line:

```
The following definitions from `padic_integers` are unfolded.
  Zp ≡ padic_int p
The names `Zp` are not bound and shouldn't be used any more. Write their unfolded terms instead.
```

With `Zp` declared again in `fixes`, the notice is instead:

```
The following definitions from `padic_integers` are unfolded.
  Zp ≡ padic_int p
The parameter `Zp` from locale `padic_integers` is not bound any more and treated as a fresh variable here.
```

Fourth, the cancelled implicit structures: when `implicit_structure`
is `null`, `Locale.parent_implicit_structures` — one entry per header
edge, in `imports`' order, duplicates included, each its locale's name
and the implicit structure it would give, as a term of this locale, or
none — gives the structures `null` cancels, each term printed on one
line, `Pretty.unformatted_string_of` of `Syntax.pretty_term` in the
locale's context with markup stripped (`Protocol_Message.clean_output`),
read by Python with `IsaTerm.from_isabelle`. When there is any, one
message, the first of the beginning's `Ready`, the notice after it:
`` `null` cancels the implicit structure``, `s` when more than one,
and each term — as `print_name` writes it against no keyword, `G`
bare, `"padic_int p"` quoted — with `inherited from locale` and its
import's authored `imports[i].locale`, without the qualifier, joined
by `, ` and the last by ` and `, then a period:

```
`null` cancels the implicit structure "padic_int p" inherited from locale padic_integers.
`null` cancels the implicit structures G inherited from locale group and R inherited from locale ring.
`null` cancels the implicit structures A inherited from locale l1, B inherited from locale l2 and C inherited from locale l3.
```

With nothing refused the callback answers the operation's messages,
none, the recorded fields, in §1's order, the cancelled structures and
the notice; the class records the fields, and the status is `Ready`
with the cancellation's message and the notice as its messages, which
the framework prints under one `Notice:` (PRINT.md §3). What Isabelle
refuses — an import that names no locale, an instantiation naming no
parameter of it (`"g" not a parameter of instantiated expression`), an
instantiation's term naming a variable `fixes` does not declare
(`Illegal free variables in expression: "h"`), `_` written for a
parameter the import does not define (`Illegal dummy pattern(s) in
term`), a defined parameter instantiated with a term other than its
definition (``The 1st parameter `Zp` of locale `padic_integers` is
defined as `padic_int p` and cannot be instantiated. You must write
`_`.``), a type or a term that does not parse (`Undefined type name:
"t"`), an implicit structure the light locale's check refuses —, the
uninstantiated parameters, the undeclared variables, and a proper
interrupt (`Interrupt`, MODULE_STRUCTURE §2.5) are the beginning's
failure with their messages: a `Bug` and every other interrupt are
re-raised; otherwise no state is written, the recorded fields stay what
the last beginning that went through recorded, the callback answers the
messages, and `_eval_beginning_opr` returns `CannotEvaluate` with them —
the node is an obstacle, its children have no context and are
`not_evaluated`, and the ending is `Ready` by the framework's copy of
the block's input to its result when the walk goes on past the block
(ARCHITECTURE §3.3).

**Inside the block.** The children run in order from the beginning's
resulting slot, each in the state the one before it left (ARCHITECTURE
§3.5), inside the locale's local theory, where the parameters are
fixed and the axioms assumed. A `Theorem` there uses the parameters
without declaring them in `for_any`: its check of undeclared variables
leaves out the variables its input state's context fixes, the locale's
parameters (THEOREM.md §6), and the refusal it renders is its own.
Every name a child declares — a fact, a constant, a type, a bundle —
bears its short name inside the block alone and the locale's qualifier
outside it, `idempotent_semigroup.idem_twice`, `L.fs`, `L.fs.lifting`;
a fact carries the locale's predicate as its premise when the locale
has one, as the light locale stores every fact of a block, its count
in the theorem's `exported_premises` tag. A `LiftingContext` in the
block runs its beginning and ending as at theory level, naming a type
the block declares by its short name. A Lifting setup a child makes —
a `QuotientType`'s, a `Typedef`'s with `lifting` — is, when the locale
has a predicate, stored with the predicate as the premise of its
quotient theorem; three cases follow. Inside the declaring block the
setup is the block's own, without the premise, and works as at theory
level. In the block of a `Locale` that imports this one, where it is
known that the predicate holds, the light locale's packages discharge
the premise as they read the setup (the light locale's repair of its
packages, not landed; until then such a block refuses as below).
Elsewhere — at theory level, or in the block of a `Locale` that does
not import this one — no such fact is known: the theorem keeps its
count, and a `LiftingContext` opening the type refuses with its
sentence of LIFTING_CONTEXT.md §6, ``There is no lifting of `LQ.qt` to
open here.``, and a `LiftDefinition` on it with its own, which
LIFT_DEFINITION.md §6 takes at implementation:

```
You can only use the lifting of `LQ.qt` in the `LQ` locale, a locale extending it, or a theory where such a locale is installed by an interpretation.
```

A child's failure is the child's; it stops the walk inside the
block as a failure stops it anywhere (ARCHITECTURE §3.3), and the
ending runs when the walk reaches it. A child inserted, amended or
deleted invalidates what follows it in the block and the ending, never
the beginning (CONSTRUCT_INTERACTION §3.1); an edit of the node's own
fields invalidates the block whole.

**The ending.** `_eval_ending_opr` sends the callback
`TAT.Locale.close` the ending's two slots — `operation_slots("ending")`:
the slot after the last child and the block's resulting slot. The
callback runs, as one operation into the resulting slot, the `end`
transition, `Toplevel.end_main_target`, what `end` parses to after a
`light_locale` block (Pure.thy): it closes the locale's target, and the
state is back at the theory's top level. The callback answers the
operation's messages: none, and the ending is `Ready`; some, and it is
`CannotEvaluate` with them, the framework copying the ending's input
through — in practice a proper interrupt's `Interrupt`.

## 7. The mark

The class has no jobs and no proof obligation; its mark is the
framework's default (PRINT.md §1), read from its two operations:
`complete`, `failed` when either is an obstacle, `not evaluated` when
its beginning is `not_evaluated`, `incomplete` while something inside
it is unfinished. It answers no owing line. An `Error:` block stands
under a `failed` line, a `Notice:` block beside a line whose beginning
reported the cancellation or the notice of §6 (PRINT.md §1, §3). In an ancestor's Recall
summary (PRINT.md §2) the node is counted by its own operations: among
the failed nodes while its beginning or its ending is refused, among
the nodes not evaluated while its beginning is not evaluated.

## 8. What it prints

`print_fields` (PRINT.md §3) writes the declaration, and only under
`Recall`; wherever it is called the framework writes the two
operations' messages after it, then the children (PRINT.md §2):

| mode | `print_fields` writes |
| --- | --- |
| `Out_Focus` | nothing |
| `Briefing` | not called |
| `Relative_Focus`, a focus | nothing |
| `Recall`, depth 0 | `english`, the declaration with each axiom's `english` |
| `Recall`, depth 1 and 2 | the declaration |
| `Recall`, depth 3 | nothing |

The declaration mirrors the construct, one keyed line per field, the
field's name as the key. `imports:`, `fixes:` and `assumes:` each
head one line per element, one level deeper and without a dash — an
import as `locale_instance_text` writes it (COMMON.md §4); a parameter
as `fixes_text` writes it over that one parameter, with its own
`syntax`, what the agent wrote; an axiom as its name, a colon and its
proposition as a string token —, and a field with no element writes no
line; `implicit_structure: ` and the term, or `null`, is always
written. At depth 0 the locale's `english` stands first, under the
node's line, and each axiom's `english` follows its line one level
deeper still, as the file places its formal comment. Every piece is
assembled from the stored text in the `unicode` spelling, as
`print_name` writes it against no keyword, every name bare, `G` bare
and `"padic_int p"` quoted, without a round trip to Isabelle; the
recorded `annotations` is not printed. An axiom's proposition is the
file's (§5): both write it through one writer, §5 with the recorded
`parenthesised_conclusions` entry, this section with the entry while
the beginning's instant status is `Ready` and `false` otherwise, so
that a node whose beginning was refused prints its axioms too.

`children_header()` answers `locale context`, and `print_fields`
answers that it wrote keyed lines wherever it wrote the declaration —
under `Recall` to depth 2 — and false elsewhere (PRINT.md §2), so that
there the children, or the empty node's line, stand under `locale
context:` one level deeper; where the declaration is not written — a
focus, the path — the children header stands only when the framework
wrote a message block, and the children follow the line directly
otherwise, as they always do in the briefing. A node under `recall`,
with one child:

```
- locale_commutative_monoid (incomplete)
  A monoid whose operation is commutative
  imports:
    M: monoid where G = G
  fixes:
    G :: "('a, 'b) monoid_scheme"
  implicit_structure: G
  assumes:
    comm: "⋀(x::'a) (y::'a). ⟦x ∈ carrier G; y ∈ carrier G⟧ ⟹ x ⊗ y = y ⊗ x"
      Multiplication is commutative
  locale context:
    - locale_commutative_monoid.lemma_comm_inv (valid statement, proving)
      ⋀x::'a. x ∈ carrier G ⟹ inv x ⊗ x = x ⊗ inv x
      The inverse of an element commutes with it
```

A child's id carries the locale's component always (§9). At depth 1
and 2 the same without the two kinds of `english`. The
evaluation's messages are the framework's to print (PRINT.md §3–§4). A
node under `recall` whose beginning Isabelle refused — an import
naming no locale:

```
- locale_idempotent_semigroup (failed)
  A semigroup whose operation is idempotent
  imports:
    S: semigrp where f = f
  fixes:
    f :: "'a ⇒ 'a ⇒ 'a" (infixl "⊗" 70)
  implicit_structure: null
  assumes:
    idem: "⋀(x::'a). x ⊗ x = x"
      Applying the operation to an element and itself gives it back
  Error:
    Undefined locale: "semigrp"
  locale context:
    - locale_idempotent_semigroup.lemma_idem_twice (not evaluated, proof not started)
      ⋀x::'a. x ⊗ (x ⊗ x) = x
      Applying the operation to an element twice over gives it back
```

A node under `recall` whose `null` cancelled an inherited structure
and whose beginning unfolded a definition of an imported locale, with
no child — the two messages of §6 under one `Notice:`:

```
- locale_LF (complete)
  The p-adic integers for a prime p
  imports:
    padic_integers where Zp = _ and p = p
  fixes:
    p :: int
  implicit_structure: null
  Notice:
    `null` cancels the implicit structure "padic_int p" inherited from locale padic_integers.
    The following definitions from `padic_integers` are unfolded.
      Zp ≡ padic_int p
    The names `Zp` are not bound and shouldn't be used any more. Write their unfolded terms instead.
  locale context:
    Empty so far. Call `edit` with action `append` and target_id `locale_LF` to add children.
```

In a quickview the node as a focus writes no field: its line, the
message blocks once per run (PRINT.md §4), and the children — the
same `LF` just added by an `edit` with `evaluate` true, and
`commutative_monoid` added with its child, whose beginning reported
nothing:

```
  - locale_LF (complete)
    Notice:
      `null` cancels the implicit structure "padic_int p" inherited from locale padic_integers.
      The following definitions from `padic_integers` are unfolded.
        Zp ≡ padic_int p
      The names `Zp` are not bound and shouldn't be used any more. Write their unfolded terms instead.
    locale context:
      Empty so far. Call `edit` with action `append` and target_id `locale_LF` to add children.
```

```
  - locale_commutative_monoid (incomplete)
    - locale_commutative_monoid.lemma_comm_inv (valid statement, proving)
```

## 9. Id properties

None declared: the framework's defaults stand, the component
compulsory in both directions with drop priority 0 (MCP_SPECIFICATION
§2.1) — the block is a scope to Isabelle, which qualifies a child's
name by it, `idempotent_semigroup.idem_twice`, and the id follows,
`locale_idempotent_semigroup.lemma_idem_twice`, printed and accepted
with the component always.
