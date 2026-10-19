# The `Record` node class

Status: proposed 2026-10-13; under review.

A `Record` defines a record type — a type whose values are tuples of
named fields — by its name, its type parameters, its fields and, when
it extends one, its parent record. It opens no proof obligation
(INDEX.md): its evaluation runs the command and nothing more, and the
node is finished when it is `ready`. It is a `Leaf` of the plugin
`Isabelle_Std` deriving from the plugin's `Theory_Member` (COMMON.md
§1) — `class Record(Theory_Member, Leaf)`. Its Python half is
`isabelle_theory_agent/std/record.py`, its ML half
`Isabelle_Std/ML/TAT_Record.ML`. Its agent-facing wording lives here —
the `description` texts of its construct schema (§3), the sentences its
`gen` renders, and the words on its line — pinned by the baseline tests
the way DATATYPE.md's are.

One kind, `record`, which heads the id component: `record_point`.

## 1. Fields

| Field | Type | |
| --- | --- | --- |
| `kind` | `record` | authored |
| `english` | what is defined, `str` | authored |
| `type_parameters` | `list[TypeParameter]` (COMMON.md §4), empty when there are none | authored |
| `type_name` | `str`, the node's name, in the id grammar without hyphens — a letter, then letters, digits, underscores and primes, not ending in an underscore (MCP_SPECIFICATION §2); one outside it is refused with the grammar's own sentence, as a `Datatype`'s is | authored |
| `parent` | `IsaTerm`, the record this one extends, an Isabelle type; optional (§2) | authored |
| `fields` | the fields added, at least one (§2), each its `name` and its `type`, `IsaTerm`s | authored |

What the last evaluation reported travels on the status the evaluation
hook returns, as for every class (COMPILATION.md §4): `CannotEvaluate
(messages)` when the definition failed, `Ready` with no messages when
it went through.

The class has no job and owns no slot: its `_unfinished` is the
framework's default, so the node is finished when its one operation is
`ready`.

## 2. The definition

A record is a name, its type parameters — each a type variable with an
optional sort —, its fields, each a name with an Isabelle type, and,
when it extends one, its parent record, an Isabelle type:

```json
{
  "kind": "record",
  "english": "A point in the plane",
  "type_name": "point",
  "type_parameters": [{"name": "'a"}],
  "fields": [
    {"name": "xcoord", "type": "'a"},
    {"name": "ycoord", "type": "'a"}]
}
```

A record extending it names it as `parent` — `"parent": "'a point"` —,
its `fields` the ones added. `kind`, `english`, `type_name` and
`fields` are required, and in a field `name` and `type`;
`type_parameters` is optional and empty when left out, `parent` and a
parameter's `sort` optional and absent when left out; an empty `sort`
is no sort. An empty `fields` is refused by the framework's check of
the construct, `must not be empty` (MODULE_STRUCTURE §4.4). `gen`
normalises every piece of Isabelle text and `english` once, when the
construct is accepted: newlines become spaces and runs of whitespace
one space; printing, emission and evaluation all use the stored text.

`type_parameters[].name`, `type_parameters[].sort`, `parent`,
`fields[].name` and `fields[].type` are `IsaTerm`s (MODULE_STRUCTURE
§4.3); `type_name` and `english` are `str`.

`TypeParameter` is shared through `TYPE_PARAMETER_DEFS`, the plugin's
(COMMON.md §4); a field is an inline object, used nowhere else.

The class's construct schema:

```jsonc
{
  "type": "object",
  "properties": {
    "kind":            { "type": "string", "enum": ["record"] },
    "english":         { "type": "string", "description": "what is defined, in English, as LaTeX text" },
    "type_name":       { "type": "string" },
    "type_parameters": { "type": "array", "items": { "$ref": "#/$defs/TypeParameter" },
                         "description": "the type's parameters; sorts are usually not specified" },
    "parent":          { "type": "string",
                         "description": "the parent record this one extends. The resulting record includes the parent's fields and the ones added here." },
    "fields":          { "type": "array", "minItems": 1,
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "type": { "type": "string", "description": "An Isabelle type expression" }
        },
        "required": ["name", "type"],
        "additionalProperties": false } }
  },
  "required": ["kind", "english", "type_name", "fields"],
  "additionalProperties": false,
  "$defs": { ...TYPE_PARAMETER_DEFS }   // TypeParameter
}
```

`TYPE_PARAMETER_DEFS`, the definition the schema refers to, with its
check and writer, is COMMON.md §4's.

The class, `kind`, `type_name`, a field's `name` and a type parameter's
`name` carry no description: the class name says what it is, the kind
is Isabelle's own word, and those keys say what they hold (COMMON.md
§5). The schema carries no example: no field's shape hides its meaning.

What the class does not take: mixfix syntax on a field, and
`(overloaded)` — the forest's theories have `typedef_overloaded` set
once, in TAT_Std.thy (COMMON.md §4), so no record carries the option.

## 3. Descriptions

`english`:

```
what is defined, in English, as LaTeX text
```

`type_parameters`:

```
the type's parameters; sorts are usually not specified
```

`parent`:

```
the parent record this one extends. The resulting record includes the parent's fields and the ones added here.
```

`fields[].type`:

```
An Isabelle type expression
```

The description of `TypeParameter.sort` is COMMON.md §4's, pinned there
alone.

## 4. `gen`

`Record.gen` calls `require_inside_theory` first (COMMON.md §1), then
checks: `type_name` against §1's grammar, the node's name
(`InvalidName` with `grammar` = `type name`, RENDER_BASELINES §2's
fifth form); every type parameter's `name` a type variable and no two
the same, `TypeParameter`'s check (COMMON.md §4); every field's `name`
an Isabelle identifier (COMMON.md §5) not ending with an underscore
(COMMON.md §5's clause on internal names), and no two fields the same
name (`InvalidField`); then every type parameter used, in a field's
`type` or in `parent`, the shared check whose sentence COMMON.md §4
pins. A sibling already bearing the node's id component is the
framework's `DuplicateName` (MCP_SPECIFICATION §2);
any other clash of the name in the theory is Isabelle's at evaluation.
Whether the types parse, whether `parent` is a record type, whether
every type variable of the fields and the parent is a type parameter,
and whether a field's name is the one Isabelle reserves, `more`, are
Isabelle's business at evaluation (MODULE_STRUCTURE §4.1); what
Isabelle rejects is an evaluation failure, not an exception.

The `InvalidField` sentences:

```
The field `type_parameters[0].name` must be a type variable, such as 'a.
The field `type_parameters[1].name` repeats `'a`.
The field `fields[1].name` must be an Isabelle identifier: it starts with a letter and continues with letters, digits, underscores and primes ('), and does not end with an underscore.
The field `fields[1].name` repeats `xcoord`.
```

The grammar text after the colon is the framework's, the one
`InvalidName` renders for the grammars `fact name` and `type name`
(RENDER_BASELINES §2), written once and used by both (COMMON.md §5).

A parent outside a theory is refused with the plugin's
`NotInsideTheory`, whose sentence COMMON.md §1 pins.

## 5. Emission

The node emits, when its `can_emit` holds — `Record` keeps the
framework's default (COMPILATION.md §3) — two commands:

```
text ‹A point in the plane.›
record 'a point =
  xcoord :: "'a"
  ycoord :: "'a"
```

and, extending it:

```
text ‹A point with a colour.›
record 'a cpoint = "'a point" +
  colour :: colour
```

- The `text` line: `english` alone, no lead (COMMON.md §2).
- The type parameters, written before the type's name by the plugin's
  `type_parameters_text` (COMMON.md §4): none writes the name alone,
  `record point =`; one without a sort writes it bare, `record 'a point
  =`; otherwise they are parenthesised and comma-separated, a sort
  after `::` as `print_name` writes it (below): `record ('a :: linorder,
  'b) entry =`.
- `parent`, when given, after `=` as `print_name` writes it (below),
  then `+`: `record 'a cpoint = "'a point" +`.
- Each field on its own line indented two spaces, its type after `::`
  as `print_name` writes it: `xcoord :: "'a"`, `colour :: colour`.
- Every piece of Isabelle text — the type's name, a field's name, a
  sort, a type — is written through the theory's `print_name`
  (SESSION_AND_THEORY §2): bare when its `ascii` is an Isabelle
  identifier (`is_identifier`, COMMON.md §5) that is not a keyword of
  the theory, as Isabelle's string token (COMPILATION.md §3) otherwise
  — `colour` and `linorder` bare, `"'a"`, `"'a point"` and a keyword
  quoted; a type variable as the writer writes it.
- The text in the `unicode` spelling; the file takes the `\<name>` form
  from the compile's conversion (COMPILATION.md §2) and reads as Unicode
  in jEdit all the same.

## 6. Evaluation

The evaluator runs the definition and never the `text` command. It goes
through the ML interfaces. `Record._eval_opr` sends the class's
callback `TAT.Record.evaluate` the input slot, the resulting slot, and
the definition as structure — the type parameters with their sorts,
the type's name, `parent`, and the fields with their types — each
`IsaTerm` as its `ascii`. The ML side runs, under
`TAT_Common_Nodes.operation` (MODULE_STRUCTURE §3), one transition on
the input slot's state — the shape of `begin_theory`, through
`apply_transition` (MODULE_STRUCTURE §2.4):

```
Toplevel.local_theory NONE NONE
  (Record.add_record_cmd {overloaded = false} (parameters, name) parent fields)
```

`Record.add_record_cmd` is the function the command's parser hands its
result to; `parameters` the type parameters as that parser hands them,
each `(name, sort option)`; `name` the type's name as a binding;
`parent` the parent type's text or `NONE`; `fields` each field as
`(binding, type, NoSyn)`; the option off, as in the file (§2).

The result is written into the resulting slot: at theory level the
same steps as a hand-written definition, and inside a `Context` or
`Locale` the definition is made in that context. A proper interrupt is
the definition's error with the one message `Interrupt`; a `Bug` and
every other interrupt are re-raised; any other error is the
definition's: no state is written, the callback answers the messages,
and `_eval_opr` returns `CannotEvaluate` with them — the node is an
obstacle. Otherwise `_eval_opr` returns `Ready` with no messages.

## 7. The mark

`Record` keeps the framework's default (PRINT.md §1): `complete` when
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

The definition is one line: the type with its parameters as emitted
(§5), `=`, the parent and `+` when given, the fields as emitted, joined
by one space — assembled from the stored text in the `unicode`
spelling, every piece as `print_name` writes it against no keyword,
every name bare, without a round trip to Isabelle; `english` follows
at depth 0 alone; no line carries a key.
One private helper writes the type's head, its parent and its fields,
given how names are written; emission and `print_fields` lay its lines
out differently.

```
'a point = xcoord :: "'a" ycoord :: "'a"
A point in the plane
```

```
'a cpoint = "'a point" + colour :: colour
A point with a colour
```

The evaluation's messages are the framework's to print (PRINT.md
§3–§4). A node under `recall` whose definition Isabelle refused — a
field whose type variable is no parameter of the record:

```
- record_pair (failed)
  'a pair = fst :: "'a" snd :: "'b"
  A pair of values
  Error:
    Extra free type variable(s) 'b
    Failed to define record "pair"
```

## 9. Id properties

None declared: a leaf's component is the last of every id, and the
framework's defaults stand (MCP_SPECIFICATION §2.1).
