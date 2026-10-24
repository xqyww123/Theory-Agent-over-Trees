# The `LiftingContext` node class

Status: proposed 2026-10-18 and revised the same day after its review
(ai-artifacts/review/lifting_context/LIFTING_CONTEXT_REVIEW.md); the
agent-facing wording below is the owner's (the rulings of 2026-10-18):
the four descriptions of §3, the sentence of §6, and `name` under the
framework's name grammar; the `types[i]` and `repeats` sentences of §4
are COMMON.md §4's under this class's path;
implemented the same day, with `Lifting_Closing` (COMMON.md §6).

A `LiftingContext` opens the Lifting setup of one or more types again,
inside its block alone: `context includes fset.lifting begin … end`.
The Lifting setup of a quotient type or a subtype — made by
`quotient_type` or `setup_lifting` — is what `lift_definition` and the
`transfer` method work through; a `QuotientType`'s or a `Typedef`'s
block closes its type's at its end (QUOTIENT_TYPE.md §6, TYPEDEF.md §6;
COMMON.md §6), and Isabelle's
library closes a type's once its construction is finished, as `Int.thy`
closes `int`'s. Inside the block a `LiftDefinition` on an opened type
defines its function and a `Theorem` about the type is proved by
`transfer`. The ending is `end`, which drops the opening, then
`lifting_update t.lifting` and `lifting_forget t.lifting` for each
opened type, Isabelle's own discipline for such a block (HOL's
`FSet.thy`, `GCD.thy`, `String.thy` and `Int_Pow.thy` end theirs so): a
transfer rule the block declared — a `lift_definition`'s, or a lemma's
under `[transfer_rule]` — outlives `end`, as every fact a `context`
block notes does, and the two commands store it into the type's bundle
and delete it from the context, so that outside the block the type is
opaque again and a later `LiftingContext` opening the type finds the
rule in the bundle. The class opens no proof obligation and has no jobs
(INDEX.md). It is a `StdBlock` of the plugin `Isabelle_Std` — `class
LiftingContext(StdBlock)` — and defines the four hooks
of a block itself, the beginning's two and the ending's two together
(PLUGIN_SYSTEM §5). Its Python half is
`isabelle_theory_agent/std/lifting_context.py`, its ML half
`Isabelle_Std/ML/TAT_Lifting_Context.ML`; the ending's two commands
per type, their transitions and their text, are `Lifting_Closing`'s
(COMMON.md §6), which it shares. Its agent-facing wording lives here —
the `description` texts of its construct schema (§3), the sentences its
`gen` and its evaluation render (§4, §6) — pinned by the baseline
tests the way QUOTIENT_TYPE.md's are.

One kind, `lifting_context`, which heads the id component:
`lifting_context_fset_size`; a child's id carries it,
`lifting_context_fset_size.lift_definition_fcard` (§9).

## 1. Fields

| Field | Type | |
| --- | --- | --- |
| `kind` | `lifting_context` | authored |
| `name` | `str`, the node's name, in the framework's name grammar (MCP_SPECIFICATION §2): a letter, then letters, digits, underscores, primes and interior hyphens, not ending in a hyphen or an underscore; TAT's name for the block, written into no command | authored |
| `types` | `IsaTerm`s, one or more, each the name of a type whose Lifting setup the block opens — an Isabelle identifier, or identifiers joined by dots where the bare name is ambiguous, `fset`, `int`, `FSet.fset` | authored |
| `opened` | the entries of `types` whose setup the block opened — those closed where the block stands (§6) —, in `types`' order: what the ending closes (§5, §6); recorded anew by every evaluation of the beginning that goes through, since it depends on where the block stands; stored, read with `rows.get`, None-valued at birth and until a beginning has gone through | recorded |
| `children` | the nodes inside the block, the framework's row (PLUGIN_SYSTEM §3; ARCHITECTURE §4.1) | — |

The class carries no `english` and writes no `text` line (COMMON.md
§2): the block declares nothing of its own, and each child carries its
own `english`.

Every row is read with `rows.get`, so that a missing one is refused at
start (`TAT_StartupError`). `opened` is no choice the evaluation keeps
to (COMMON.md §5): it is what the beginning found, recorded each time
it goes through, and the ending and the emission follow the last
record.

The node has two operations, the beginning and the ending
(MODULE_STRUCTURE §4.1). What the beginning's last evaluation reported
travels on its status, as for every class (COMPILATION.md §4):
`CannotEvaluate (messages)` when the opening was refused, `Ready` with
no messages when it went through; the ending's likewise (§6). Its
constructor takes the parent, the input slot and its fields; `StdBlock`
builds it with no children and mints its slot before the ending
(MODULE_STRUCTURE §4.1).

## 2. The block

A lifting context is a name, the types it opens, and its children,
the `lift_definition`s and lemmas inside the block:

```json
{
  "kind": "lifting_context",
  "name": "fset_size",
  "types": ["fset"],
  "children": [
    {"kind": "lift_definition", "english": "The number of elements of a finite set", "name": "fcard",
     "type": "'a fset ⇒ nat", "is": "λxs. card (set xs)"},
    {"kind": "lemma", "name": "fcard_fempty",
     "statement": {"english": "The empty finite set has no element", "conclusion": "fcard fempty = 0"}}
  ]
}
```

```json
{
  "kind": "lifting_context",
  "name": "int_swap",
  "types": ["int"],
  "children": [
    {"kind": "lift_definition", "english": "An integer with the two halves of its pair swapped", "name": "int_swap",
     "type": "int ⇒ int", "is": "λ(a, b). (b, a)"}
  ]
}
```

`kind`, `name` and `types` are required; `children` is optional, as
for every nesting class (PLUGIN_SYSTEM §3), and contents come later
through `edit` as well. The node's name is `name`. Each entry of
`types` names a type as the agent sees it named — in the sentence of
LIFT_DEFINITION.md §6 that sends a `lift_definition` here, `` under a
lifting_context opening `fset` ``, the type's constructor as
`Proof_Context.extern_type` prints it, qualified only where the bare
name is ambiguous. `gen` normalises each entry once, when the construct
is accepted: newlines become spaces and runs of whitespace one space;
printing, emission and evaluation all use the stored text.

Each entry of `types` is an `IsaTerm` (MODULE_STRUCTURE §4.3); `name`
is `str`.

Where the block stands is COMMON.md §1's; the framework checks it
(PLUGIN_SYSTEM §2). A type whose setup is open
where the block stands already — the type a `QuotientType` or a
`Typedef` block defines, inside that block — the block leaves as it is,
silently: it neither opens nor closes it (§6). A type with no Lifting
setup to open — a `datatype`, a name no setup bears, a subtype whose
lifting could not be set up (TYPEDEF.md §6), a type whose
`quotient_type` stands later — is refused at evaluation (§6). `gen`
checks neither: each needs the context where the block stands.

What stands inside the block: a node whose class's `placement` names
`LiftingContext` in its `through` (PLUGIN_SYSTEM §2; this plugin's,
COMMON.md §1). The opened types' Lifting setups are open inside
the block and closed at its end (§6), so a `LiftDefinition` on an
opened type stands here, as does a `Theorem` about it proved by
`transfer`; a node that uses the type by name alone needs no open setup
and stands wherever its class's `placement` admits it (COMMON.md §1).

The class's construct schema:

```jsonc
{
  "type": "object",
  "description": "opens the Lifting setup of one or more subtypes (by `typedef`) or quotient types (such as fset) again, so that lift_definition and the `transfer` tactic are available, working through the representation of the types (the lists under fset); in Isabelle code, context includes fset.lifting begin … end",
  "properties": {
    "kind":     { "const": "lifting_context" },
    "name":     { "type": "string", "description": "the block's name, by which it is referred to" },
    "types":    { "type": "array", "minItems": 1, "items": { "type": "string" },
                  "description": "the types whose Lifting setup the block opens again, each by its name" },
    "children": { "type": "array", "items": { "$ref": "#/$defs/Construct" },
                  "description": "the lift_definitions on the opened types, and any other declarations whose proofs need transfer" }
  },
  "required": ["kind", "name", "types"],
  "additionalProperties": false
}
```

`#/$defs/Construct` is the framework's (PLUGIN_SYSTEM §4); the schema
refers to no definition of the plugin's. The class carries a
description, its name alone not saying what opening a setup does for
the agent; `kind` carries none; `name` carries one, the block naming
nothing in Isabelle and its name written into no command (COMMON.md
§5).

What the class does not take: an `english`; the other elements a
`context` block may open with — `fixes`, `assumes`, a named target —
which are `Context`'s (INDEX.md); any other bundle, `lifting_syntax`
among them, so a transfer rule stated inside the block writes `rel_fun`
rather than `===>`; `lifting_update t.lifting` and `lifting_forget
t.lifting`, which the ending writes (§5).

## 3. Descriptions

The class:

```
opens the Lifting setup of one or more subtypes (by `typedef`) or quotient types (such as fset) again, so that lift_definition and the `transfer` tactic are available, working through the representation of the types (the lists under fset); in Isabelle code, context includes fset.lifting begin … end
```

`name`:

```
the block's name, by which it is referred to
```

`types`:

```
the types whose Lifting setup the block opens again, each by its name
```

`children`:

```
the lift_definitions on the opened types, and any other declarations whose proofs need transfer
```

## 4. `gen`

`LiftingContext.gen` checks each entry of `types`, normalised, by
COMMON.md §4's `dotted_name_of` under the noun `type` and the path
`types[i]` (`InvalidField`), and no two entries the same, the shared
sentence for a repeat (COMMON.md §4). A `name` outside the framework's
name grammar is the framework's `InvalidName`, and a sibling already
bearing the node's id component its `DuplicateName` (MCP_SPECIFICATION
§2); an empty `types` is refused by the framework's check of the
construct, `must not be empty` (MODULE_STRUCTURE §4.4). Whether a type
exists, whether it has a Lifting setup, and whether that setup is
closed here, are judged at evaluation (§6; MODULE_STRUCTURE §4.1); a
refusal there is an evaluation failure, not an exception. The children
are the framework's: built by their own classes' `gen`s and placed
under the node (MODULE_STRUCTURE §4.2).

The class has no jobs, so an amend carries nothing over: the
replacement is a fresh node with the children it inherits
(MODULE_STRUCTURE §4.2).

The `InvalidField` sentences:

```
The field `types[0]` must be a type's name: an Isabelle identifier, or identifiers joined by dots, each of which starts with a letter and continues with letters, digits, underscores and primes ('), and does not end with an underscore.
The field `types[1]` repeats `fset`.
```

Both are COMMON.md §4's — the first `dotted_name_of`'s under the noun
`type`, its grammar text the framework's (COMMON.md §5) —; the path of
both this class's own, `types[i]`.

## 5. Emission

The node emits, when its `can_emit` holds — `LiftingContext` keeps the
framework's default, both stored statuses `Ready` (COMPILATION.md §3),
under which `opened` is recorded — the beginning: the `context` command
on one line, then one empty line when the block has children; the
children in order, one empty line between siblings, at the block's own
indent, the framework's (COMPILATION.md §3); the ending: one empty
line, `end`, then the two commands that close the Lifting setup of each
type the block opened:

```
context includes fset.lifting begin

text ‹The number of elements of a finite set.›
lift_definition fcard :: "'a fset ⇒ nat" is "λxs. card (set xs)" by aoa

text ‹Lemma fcard_fempty. The empty finite set has no element.›
lemma fcard_fempty:
  shows "fcard fempty = 0"
  by aoa

end
lifting_update fset.lifting
lifting_forget fset.lifting
```

and, opening two types, with no child:

```
context includes dlist.lifting and natural.lifting begin

end
lifting_update dlist.lifting
lifting_forget dlist.lifting
lifting_update natural.lifting
lifting_forget natural.lifting
```

- No `text` line: the class has no `english` (§1).
- The command: `context includes`, the bundles `t.lifting` for the
  entries of `types` in their order joined by ` and ` — Isabelle's
  syntax for several (parse_spec.ML, `bundles`) —, then `begin`, on
  one line.
- The bundle's name, `t` followed by `.lifting`, written bare: `t`, an
  identifier or identifiers joined by dots, makes `t.lifting` a long
  identifier, which Isabelle's outer lexer reads as one token even
  where `t` alone is a keyword of the theory (COMMON.md §6).
- The children's text is their own, each class's `emit`, at the block's
  indent: the file reads as the library's do.
- `end` on its own line at the block's indent, then, for each entry of
  `opened` in its order, `lifting_update t.lifting` and `lifting_forget
  t.lifting`, each on its own line at the block's indent, the bundle's
  name bare: the text of `Lifting_Closing`'s ending, written by its
  shared writer (COMMON.md §6). An entry of `types` whose setup was
  open already where the block stands (§6) keeps its bundle in the
  `includes` and gets no pair.
- The text in the `unicode` spelling; the file takes the `\<name>` form
  from the compile's conversion (COMPILATION.md §2) and reads as Unicode
  in jEdit all the same.

## 6. Evaluation

The beginning opens the setups; the ending drops the opening and
closes the setups; neither runs a proof (ARCHITECTURE §3.6). Both go
through the ML interfaces, each as one operation
(`TAT_Common_Nodes.operation'` for the beginning, which yields
`opened`, `operation` for the ending; MODULE_STRUCTURE §2.5).

**The beginning.** `_eval_beginning_opr` sends the class's callback
`TAT.LiftingContext.open` the beginning's two slots —
`operation_slots("beginning")`: the input slot and the beginning's
resulting slot, the first child's input or the slot before the ending
when there is no child (MODULE_STRUCTURE §4.1) — and `types`, each
entry as its `ascii`. The callback, in the input state's context
(`Toplevel.context_of`), first judges each entry `t` in order: it
reads the pointer of the bundle `t.lifting` — the key under which the
type's setup keeps its restore data, held by the bundle's one attribute
(lifting_setup.ML, `lifting_bundle`) — as the two closing commands read
it, through the one function of `Lifting_Closing`'s ML half that
answers it, or none for a name no bundle bears or a bundle that is no
Lifting bundle (COMMON.md §6), and looks the data up
(`Lifting_Info.lookup_restore_data`): no pointer or no data, and the
entry is refused with the sentence below; found, and the entry is
accepted, and the quotient the data holds names the type — the abstract
type of its quotient theorem (`Lifting_Util.quot_thm_rty_qty`) — whose
constructor `Lifting_Info.lookup_quotients` finds registered in the
context or not: not registered, the entry goes into `opened`;
registered, the setup is open here already, and the entry is left out
of `opened`, silently — the ending's `lifting_forget` would otherwise
close it for what follows the block. Every entry is judged, and the
refusal carries one message per refused entry, its sentence, in the
entries' order:

```
There is no lifting of `nat` to open here.
```

naming the entry as authored, in its `unicode` spelling. With every
entry accepted the callback runs the command's transition —
the shape of `begin_theory`, through `apply_transition` —, what
`context includes t.lifting begin` parses to (Pure.thy):

```
Toplevel.begin_nested_target (Target_Context.context_begin_nested_cmd bundles [])
```

`bundles` the entries' bundles in order, each `((true, Position.none),
(t ^ ".lifting", Position.none))`, the polarity `true` being
`includes` without `no`; no context element. The transition includes
each bundle into the block's context — its one attribute,
`lifting_restore_internal` on the pointer, registers the quotient again and
adds the stored transfer rules (lifting_setup.ML) — and opens the
nested target; the state it leaves, a local theory inside the target,
goes into the beginning's resulting slot. What Isabelle refuses there is
the beginning's failure with its messages — a bundle whose quotient
Isabelle's sanity check rejects, or one for a type registered with
another quotient (`lifting_restore`), in practice never. At theory
level these are the steps the hand-written
text takes; inside a `Locale` the same (LOCALE.md §6); inside a
`Context` that class's to settle when it is designed (INDEX.md).

A refusal anywhere is the beginning's `CannotEvaluate` with its
messages: no state is written into the beginning's resulting slot, the
node is an obstacle, its children have no context and are
`not_evaluated`, the ending is `Ready` by the framework's copy of the
block's input to its result when the walk goes on past the block
(ARCHITECTURE §3.3), and `opened` stays what the last beginning that
went through recorded, or none. Otherwise the callback answers, beside
no message, the entries it put into `opened`, which the class records,
and the status is `Ready` with no messages.

**Inside the block.** The children run in order from the beginning's
resulting slot, each in the state the one before it left (ARCHITECTURE
§3.5), with the opened types' Lifting setups open: a `LiftDefinition`
on an opened type defines its function and declares its transfer rule,
a `Theorem` may be proved by `transfer`. A child's failure is the
child's; it stops the walk inside the block as a failure stops it
anywhere (ARCHITECTURE §3.3), and the ending runs when the walk reaches
it. A child inserted, amended or deleted invalidates what follows it in
the block and the ending, never the beginning (CONSTRUCT_INTERACTION
§3.1); an edit of the node's own fields invalidates the block whole.

**The ending.** `_eval_ending_opr` sends the callback
`TAT.LiftingContext.close` the ending's two slots —
`operation_slots("ending")`: the slot after the last child and the
block's resulting slot — and `opened`, each entry as its `ascii`. The
callback runs, as
one operation into the resulting slot, first the `end` transition,
`Toplevel.end_nested_target`, what `end` parses to after a `context`
block (Pure.thy): it closes the nested target and drops the opening —
the included bundles' declarations are the block's context's alone
(bundle.ML, `includes` through `Attrib.local_notes`) — while the facts
the children noted, their attributes applied, outlive it, as every fact
a `context` block notes does; the state is back at the level the block
began at. Then, for each entry of `opened` in order, the pointer of the
bundle `t.lifting` read again in that state, as the beginning read it,
and on it the two transitions of `Lifting_Closing`'s ending (COMMON.md
§6): `lifting_update t.lifting`, which stores into the type's bundle
every transfer rule of the context whose relation mentions the type's —
the rules the block declared, which `end` left standing —, and
`lifting_forget t.lifting`, which deletes them from the context; the
type's Quotient registration, which it deletes too, `end` has dropped
already. The callback answers the operation's messages: none, and the
ending is `Ready`; some, and it is `CannotEvaluate` with them, the
framework copying the ending's input through — in practice a proper
interrupt's `Interrupt` (MODULE_STRUCTURE §2.5), the bundles being the
ones the beginning read.

## 7. The mark

The class has no jobs and no proof obligation; its mark is the
framework's default (PRINT.md §1), read from its two operations:
`complete`, `failed` when either is an obstacle, `not evaluated` when
its beginning is `not_evaluated`, `incomplete` while something inside
it is unfinished. It answers no owing line. An `Error:` block stands
under a `failed` line (PRINT.md §1). In an ancestor's Recall summary
(PRINT.md §2) the node is counted by its own operations: among the
failed nodes while its beginning or its ending is refused, among the
nodes not evaluated while its beginning is not evaluated.

## 8. What it prints

`print_fields` (PRINT.md §3) writes the beginning command, and only
under `Recall`; wherever it is called the framework writes the two
operations' messages after it, then the children (PRINT.md §2):

| mode | `print_fields` writes |
| --- | --- |
| `Out_Focus` | nothing |
| `Briefing` | not called |
| `Relative_Focus`, a focus | nothing |
| `Recall`, depth 0 to 2 | the beginning command |
| `Recall`, depth 3 | nothing |

The beginning command is one line, the text §5 emits — `context
includes`, the bundles joined by ` and `, `begin` — assembled from the
stored text by the one private helper of lifting_context.py that §5's
line uses too; no line carries a key. The children are the framework's
to print, one level deeper, in the mode PRINT.md §2's table gives them;
a block with none shows the empty node's line.

```
context includes fset.lifting begin
```

The evaluation's messages are the framework's to print (PRINT.md
§3–§4): an `Error:` block while an operation is an obstacle. A node
under `recall` whose beginning was refused, `fset` having no Lifting
setup where the block stands:

```
- lifting_context_fset_size (failed)
  context includes fset.lifting begin
  Error:
    There is no lifting of `fset` to open here.
  - lift_definition_fcard (not evaluated, proof not started)
    fcard :: "'a fset ⇒ nat" is "λxs. card (set xs)"
  - lemma_fcard_fempty (not evaluated, proof not started)
    fcard fempty = 0
    The empty finite set has no element
```

A node under `recall` whose beginning went through and whose ending was
refused:

```
- lifting_context_fset_size (failed)
  context includes fset.lifting begin
  Error:
    Interrupt
  - lift_definition_fcard (valid definition)
    fcard :: "'a fset ⇒ nat" is "λxs. card (set xs)"
  - lemma_fcard_fempty (valid statement, proven)
    fcard fempty = 0
    The empty finite set has no element
```

## 9. Id properties

Omissible in both directions, as `Section` and `QuotientType` are,
with drop priority 1: its component goes after `Section`'s and with
`Session`'s, the outermost of the two first, before `Theory`'s
(MCP_SPECIFICATION §2.1) — the block is a scope to TAT and none that
qualifies a name to Isabelle, a child's qualified name not carrying it,
`X.fcard`. A child's id prints as short as the forest allows,
`lift_definition_fcard`, and is accepted with or without the component;
the node's own component, `lifting_context_fset_size`, ends its own id
and is never dropped from it.
