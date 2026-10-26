# The `Datatype` node class

Status: proposed 2026-10-06; revised 2026-10-12 after three review
rounds (ai-artifacts/review/NODE_CLASS_RULINGS.md), committed
2026-10-13 (e3eadf3); revised 2026-10-14 with the `Typedef` design
(TYPEDEF.md): a type's syntax, and the shared text's home in COMMON.md
§4; approved 2026-10-14.

A `Datatype` defines an inductive or coinductive type — or several at
once, when they are mutually recursive — each by its name, its type
parameters and its constructors. It opens no proof obligation
(INDEX.md): its evaluation runs the command and nothing more, and the
node is finished when it is `ready`. It is a `Leaf` of the plugin
`Isabelle_Std` and a `Type_Definition` (COMMON.md §1) — `class
Datatype(Leaf, Type_Definition)`: its Python half is `isabelle_theory_agent/std/datatype.py`,
its ML half `Isabelle_Std/ML/TAT_Datatype.ML`. Its agent-facing wording
lives here — the `description` texts of its construct schema (§3), the
sentences its field check renders (§4), and the words on its line —
pinned by the baseline tests the way THEOREM.md's are.

Kinds: `datatype` and `codatatype` — the two commands share one syntax
and one implementation (`bnf_fp_def_sugar.ML`, `parse_co_datatype_cmd`),
differing in the fixpoint taken. The kind heads the id component:
`datatype_tree`, `codatatype_stream`.

## 1. Fields

| Field | Type | |
| --- | --- | --- |
| `kind` | `datatype` or `codatatype` | authored |
| `english` | what is defined, `str` | authored |
| `type_parameters` | `list[TypeParameter]` (§2), the parameters of every type defined, empty when there are none | authored |
| `types` | the types defined, at least one (§2), each its `type_name`, `str`, its optional `syntax`, a `TypeMixfix`, and its `constructors`; the node's name is the types' names joined with `_`, so each is in the id grammar without hyphens — a letter, then letters, digits, underscores and primes, not ending in an underscore (MCP_SPECIFICATION §2) — and one outside it is refused with the grammar's own sentence, as a `Theorem`'s is | authored |

What the last evaluation reported travels on the status the evaluation
hook returns, as for every class (COMPILATION.md §4): `CannotEvaluate
(messages)` when the definition failed, `Ready` with no messages when
it went through.

The class has no job and owns no slot: its `_unfinished` is the
framework's default, so the node is finished when its one operation is
`ready`.

## 2. The definition

A type is a name, an optional syntax — a mixfix annotation on the type
— and its constructors, each a name with its arguments — an Isabelle
type with an optional selector name — and an optional syntax, a mixfix
annotation on the constructor. The type parameters — each a type variable
with an optional sort — are the node's, shared by every type it
defines, since Isabelle requires the types of a mutually recursive
group to have the same parameters (`merge_type_args`,
`bnf_fp_def_sugar.ML`). A node defines one type, or several that are
mutually recursive:

```json
{
  "kind": "datatype",
  "english": "Finite sequences",
  "type_parameters": [{"name": "'a"}],
  "types": [
    {"type_name": "list",
     "constructors": [
       {"name": "Nil"},
       {"name": "Cons", "arguments": [
         {"type": "'a", "selector": "hd"},
         {"type": "'a list", "selector": "tl"}],
        "syntax": {"form": "infixr", "symbol": "#", "priority": 65}}]}
  ]
}
```

`kind`, `english` and `types` are required, and in a type `type_name`
and `constructors`; `type_parameters` and a constructor's `arguments`
are optional and empty when left out, a parameter's `sort`, a type's
`syntax`, an argument's `selector` and a constructor's `syntax`
optional and absent when left out; an empty `sort` is no sort. An empty `types` or
`constructors` is refused by the framework's check of the construct,
`must not be empty` (MODULE_STRUCTURE §4.4). The node's name is the
types' names joined with `_`, in their order — Isabelle's own name for
the group, which qualifies its common theorems, `expr_bexp.induct` —
computed from `types` and never stored; one type gives
`datatype_list`. `gen` normalises every piece of Isabelle text and
`english` once, when the construct is accepted: newlines become spaces
and runs of whitespace one space — in a syntax's `symbol` or `template`
newlines and tabs alone, since runs of spaces there are layout;
printing, emission and evaluation all use the stored text.

`type_parameters[].name`, `type_parameters[].sort`,
`types[].constructors[].name`, `types[].constructors[].arguments[].type`,
`types[].constructors[].arguments[].selector` and a syntax's `symbol`
or `template` are `IsaTerm`s (MODULE_STRUCTURE §4.3); `types[].type_name` and
`english` are `str`.

`TypeParameter` is shared through `TYPE_PARAMETER_DEFS`, `TypeMixfix`
through `TYPE_MIXFIX_DEFS` and `Mixfix` through `MIXFIX_DEFS`, all the
plugin's (COMMON.md §4); a type, a constructor and an argument are
inline objects, used nowhere else.

The class's construct schema:

```jsonc
{
  "type": "object",
  "properties": {
    "kind":            { "type": "string", "enum": ["datatype", "codatatype"] },
    "english":         { "type": "string", "description": "what is defined, in English, as LaTeX text" },
    "type_parameters": { "type": "array", "items": { "$ref": "#/$defs/TypeParameter" },
                         "description": "the parameters of the types defined; sorts are usually not specified" },
    "types":           { "type": "array", "minItems": 1,
                         "description": "the types defined by this command: usually one; several only when they are mutually recursive",
      "items": {
        "type": "object",
        "properties": {
          "type_name":    { "type": "string" },
          "syntax":       { "$ref": "#/$defs/TypeMixfix" },
          "constructors": { "type": "array", "minItems": 1,
            "items": {
              "type": "object",
              "properties": {
                "name":      { "type": "string" },
                "arguments": { "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                      "type":     { "type": "string", "description": "An Isabelle type expression" },
                      "selector": { "type": "string", "description": "the name of the function that extracts this argument from the constructor, as hd and tl in Cons (hd: 'a) (tl: \"'a list\"). Leave out if none" }
                    },
                    "required": ["type"],
                    "additionalProperties": false } },
                "syntax":    { "$ref": "#/$defs/Mixfix" }
              },
              "required": ["name"],
              "additionalProperties": false } }
        },
        "required": ["type_name", "constructors"],
        "additionalProperties": false } }
  },
  "required": ["kind", "english", "types"],
  "additionalProperties": false,
  "$defs": { ...TYPE_PARAMETER_DEFS, ...TYPE_MIXFIX_DEFS, ...MIXFIX_DEFS }   // TypeParameter, TypeMixfix, Mixfix
}
```

`TYPE_PARAMETER_DEFS`, `TYPE_MIXFIX_DEFS` and `MIXFIX_DEFS`, the three
definitions the schema refers to, with their checks and writers, are
COMMON.md §4's.

The class, `kind`, `type_name`, a constructor's `name` and a type
parameter's `name` carry no description: the class name says what it
is, the two kinds are Isabelle's own words, and those keys say what
they hold; `selector` carries one, its key alone not saying what it
holds (COMMON.md §5). The schema's examples are
on `selector`, in `TypeMixfix` and in `Mixfix`, where the shape does
not show the meaning; they are Isabelle's own text, never JSON.

What the class does not take: discriminator names and
`discs_sels`, the `for map: rel: pred:` names, selector defaults
(`where`), `dead` and named type parameters, and the plugin options.

## 3. Descriptions

`english`:

```
what is defined, in English, as LaTeX text
```

`types`:

```
the types defined by this command: usually one; several only when they are mutually recursive
```

`type_parameters`:

```
the parameters of the types defined; sorts are usually not specified
```

`types[].constructors[].arguments[].type` and
`types[].constructors[].arguments[].selector`:

```
An Isabelle type expression
the name of the function that extracts this argument from the constructor, as hd and tl in Cons (hd: 'a) (tl: "'a list"). Leave out if none
```

The descriptions of `TypeParameter.sort`, of `TypeMixfix`, of `Mixfix`
and of their arms' fields are COMMON.md §4's, pinned there alone.

## 4. `gen` and the field check

Where a `Datatype` stands is COMMON.md §1's; the framework checks it, not
`gen` (PLUGIN_SYSTEM §2).

`Datatype.gen` refuses only a `type_name` outside §1's grammar, since
each is part of the node's name (`InvalidName` with `grammar` = `type
name`, RENDER_BASELINES §2's fifth form), and reads the rest normalised
(§2). The field check (PLUGIN_SYSTEM §2) refuses, before the node's
first own operation, in this order: two types the same name; then the
type parameters by the shared check (COMMON.md §4): each `name` a type
variable, no two the same; then each type's constructors in turn: the
constructor's `name` an Isabelle identifier (COMMON.md §5) not ending
with an underscore (COMMON.md §5's clause on internal names), no
earlier constructor of its type the same name — Isabelle qualifies a
constructor by its type, so two types of a group may share one —, then
each of its `selector`s likewise, no earlier selector of that
constructor the same (`InvalidField`); then each type parameter used
in some constructor's argument type, the plugin's shared check
(COMMON.md §4). A sibling already bearing the node's id
component is the framework's `DuplicateName` (MCP_SPECIFICATION §2); any
other clash of the types' names in the theory — a `codatatype` sibling
of the same name among them — is Isabelle's at evaluation. Whether the
types parse, whether each argument's type is a bounded natural functor,
whether every type is non-empty, and whether a mixfix annotation is
well-formed, a type's with one `_` per parameter, are Isabelle's
business at evaluation (MODULE_STRUCTURE §4.1); what Isabelle rejects is
an evaluation failure, not an exception.

The `InvalidField` sentences:

```
The field `types[1].type_name` repeats `expr`.
The field `types[0].constructors[1].name` must be an Isabelle identifier: it starts with a letter and continues with letters, digits, underscores and primes ('), and does not end with an underscore.
The field `types[0].constructors[2].name` repeats `Nil`.
The field `types[0].constructors[1].arguments[0].selector` must be an Isabelle identifier: it starts with a letter and continues with letters, digits, underscores and primes ('), and does not end with an underscore.
The field `types[0].constructors[1].arguments[1].selector` repeats `hd`.
```

The type parameters' sentences are COMMON.md §4's, written once in
`common.py`. The grammar text after the colon is the framework's, the
one `InvalidName` renders for the grammars `fact name` and `type name`
(RENDER_BASELINES §2), written once and used by both (COMMON.md §5).

## 5. Emission

The node emits, when its `can_emit` holds — `Datatype` keeps the
framework's default (COMPILATION.md §3) — two commands:

```
text ‹Finite sequences.›
datatype 'a list =
    Nil
  | Cons (hd: "'a") (tl: "'a list") (infixr "#" 65)
```

and, with several types:

```
text ‹Arithmetic and boolean expressions.›
datatype expr =
    Num nat
  | Plus expr expr
  | If bexp expr expr
and bexp =
    Less expr expr
  | Not bexp
```

- The `text` line: `english` alone, no lead (COMMON.md §2).
- Every type's head — the node's type parameters, the type's name, its
  syntax — is the plugin's `type_head_text` (COMMON.md §4): the
  parameters before the name, none writing the name alone, `datatype
  tree =`, one without a sort bare, `datatype 'a tree =`, otherwise
  parenthesised and comma-separated, a sort after `::` as `print_name`
  writes it (below), `datatype ('a :: linorder, 'b) map =`
  (`type_parameters_text`); the name through the theory's `print_name`
  (below); the type's `syntax`, when given, after its name and before
  `=`, in parentheses as Isabelle writes it (`mixfix_text`): `datatype
  ('a, 'b) either (infixr "⊕" 60) =`.
- The first constructor on its own line indented four spaces, every
  further one on its own line indented two and led by `| `; each
  argument's type as `print_name` writes it (below), `nat` bare and
  `"'a list"` quoted, an argument with a selector as `(hd: "'a")`.
- A constructor's `syntax` after its arguments, in parentheses as
  Isabelle writes it by the plugin's `mixfix_text` (COMMON.md §4), the
  symbol or template as a string token:
  `(infixr "#" 65)`, `(binder "∀" 10)`, `("⟨_, _⟩")`; a general
  mixfix's argument priorities in brackets and its result priority after
  them, each when given: `("_ ! _" [100, 101] 100)`.
- Every further type as a block of the same shape, `and` at the left
  margin in place of the command.
- Every piece of Isabelle text — a name, a sort, an argument's type —
  is written through the theory's `print_name` (SESSION_AND_THEORY §2):
  bare when its `ascii` is an Isabelle identifier (`is_identifier`,
  COMMON.md §5) that is not a keyword of the theory, as Isabelle's
  string token (COMPILATION.md §3) otherwise — `nat` and `linorder`
  bare, `"'a list"` and a keyword quoted; a type variable, a symbol and
  a template as the writers write them.
- The text in the `unicode` spelling; the file takes the `\<name>` form
  from the compile's conversion (COMPILATION.md §2) and reads as Unicode
  in jEdit all the same.

## 6. Evaluation

The evaluator runs the definition and never the `text` command. It goes
through the ML interfaces. `Datatype._eval_opr` sends the class's
callback `TAT.Datatype.evaluate` the input slot, the resulting slot, and
the definition as structure — `kind`, the type parameters with their
sorts, the types each with its name, its syntax and its constructors
with their arguments, selectors and syntax — each `IsaTerm` as its
`ascii`. The ML
side runs, under `TAT_Common_Nodes.operation` (MODULE_STRUCTURE §2.5),
one transition on the input slot's state:

```
Toplevel.local_theory NONE NONE
  (BNF_FP_Def_Sugar.co_datatype_cmd fp construct
    (Ctr_Sugar.default_ctr_options_cmd, specs))
```

— the shape of `begin_theory`, through `apply_transition`. `fp` and
`construct` are `Least_FP` and `BNF_LFP.construct_lfp` for `datatype`,
`Greatest_FP` and `BNF_GFP.construct_gfp` for `codatatype`: the
function each command's parser hands its result to. `specs` is that
parser's structure, one entry per type, built from the fields inside
the local theory's function: the node's type parameters, each `(SOME
Binding.empty, (name, sort))`, in every entry; the type's name as a
binding; the type's syntax, read as a constructor's is; each
constructor `((Binding.empty, name), arguments)` with its mixfix —
`NoSyn` without `syntax`; otherwise the annotation as `mixfix_text`
writes it, in `ascii`, read by Isabelle's `Parse.mixfix` under the
local theory's keywords through the plugin's `TAT_Mixfix` (COMMON.md
§4), so the command receives what the file carries —; each argument
`(selector or Binding.empty, type)`; no `map`, `rel` or `pred`
binding; no selector defaults. The
result is written into the resulting
slot: at theory level the same steps as a hand-written definition, and
inside a `Context` or `Locale` the definition is made in that context.
A proper interrupt is the definition's error with the one message
`Interrupt`; a `Bug` and every other interrupt are re-raised; any other
error is the definition's: no state is written, the callback answers the messages,
and `_eval_opr` returns `CannotEvaluate` with them — the node is an
obstacle. Otherwise `_eval_opr` returns `Ready` with no messages.

## 7. The mark

`Datatype` keeps the framework's default (PRINT.md §1): `complete` when
the definition went through, `failed` when it is an obstacle, `not
evaluated` otherwise; it owes nothing after its evaluation, so
`incomplete` never appears on its line.

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

The definition is one line per type: the type with its parameters and
its syntax as emitted (§5), `=`, the constructors as emitted, joined by
` | `, every further type's line led by `and ` — assembled from the
stored text, every piece through `print_name` against no keyword
(SESSION_AND_THEORY §2): every name, an identifier, bare, a sort and
an argument's type quoted unless an identifier, whatever keywords the
theory recorded, without a round trip to Isabelle; `english` follows
at depth 0 alone; no line carries a key. One private helper writes a
type's head and constructors, given the keyword set — the theory's for
emission, none here; emission and `print_fields` lay its lines out
differently.

```
'a list = Nil | Cons (hd: "'a") (tl: "'a list") (infixr "#" 65)
Finite sequences
```

```
expr = Num nat | Plus expr expr | If bexp expr expr
and bexp = Less expr expr | Not bexp
Arithmetic and boolean expressions
```

The evaluation's messages are the framework's to print (PRINT.md
§3–§4). A node under `recall` whose definition Isabelle refused — a
`datatype` with no finite value, which only a `codatatype` can define:

```
- datatype_stream (failed)
  'a stream = SCons "'a" "'a stream"
  An infinite sequence
  Error:
    Cannot define empty datatype "stream"
```

## 9. Id properties

None declared: a leaf's component is the last of every id, and the
framework's defaults stand (MCP_SPECIFICATION §2.1).
