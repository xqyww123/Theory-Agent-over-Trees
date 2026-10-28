# The `Section` and `Text` node classes

Status: proposed and implemented 2026-10-24, revised the same day after
its review (ai-artifacts/review/section/SECTION_REVIEW.md); the
agent-facing wording below is the owner's (the rulings of 2026-10-24):
the descriptions of §3, the sentences of §4, `name` under the
framework's name grammar, the caption on the line (PRINT.md §1), and
§6's remedy (2026-10-25); revised 2026-10-25 with the prose translator
(COMPILATION.md §3), and 2026-10-27 with the placement check and the
field check (PLUGIN_SYSTEM §2).

A `Section` is a heading of the theory's document, with the
declarations under it; a `Text` is a passage of prose in it. Both are
document markup: Isabelle's `chapter`, `section`, `subsection`,
`subsubsection`, `paragraph` and `subparagraph` commands, and its `text`
command. Neither opens an Isabelle scope — a heading changes nothing
about how the declarations under it are checked or named (ARCHITECTURE
§2.0) — nor a proof obligation, and neither has jobs (INDEX.md).
Evaluation runs no command for either: a `Section`'s beginning and a
`Text`'s one operation pass the state through (§6), so the two classes
have no ML half. `Section` is a `StdBlock` of the plugin `Isabelle_Std`
with a beginning command and no ending one — `class Section(StdBlock)`,
defining of a block's four hooks the beginning's two, `emit_beginning`
and `_eval_beginning_opr` (PLUGIN_SYSTEM §5; COMPILATION.md §3) —;
`Text` is a `Leaf`, `class Text(Leaf)`. Their Python halves are
`isabelle_theory_agent/std/section.py` and
`isabelle_theory_agent/std/text.py`. Their agent-facing wording lives
here — the `description` texts of their construct schemas (§3), the
sentences their field checks and `Section`'s `cannot_hold` render (§4,
§6) — pinned by
the baseline tests the way LIFTING_CONTEXT.md's are.

`Section`'s kinds are the six heading commands, from the top level down:
`chapter`, `section`, `subsection`, `subsubsection`, `paragraph`,
`subparagraph`; `Text`'s one kind is `text`. The kind heads the id
component: `section_Basics`, `subsection_Lengths`, `text_intro`; a
heading's children carry its component, `section_Basics.lemma_rev_rev`
(§9).

## 1. Fields

`Section`:

| Field | Type | |
| --- | --- | --- |
| `kind` | one of the six heading commands | authored |
| `name` | `str`, the node's name, in the framework's name grammar (MCP_SPECIFICATION §2): a letter, then letters, digits, underscores, primes and interior hyphens, not ending in a hyphen or an underscore; TAT's name for the heading, written into no command | authored |
| `title` | `str`, the heading's text as authored, as `gen` stores it (§2); the document gets its translation (§5) | authored |
| `children` | the declarations under the heading, the framework's row (PLUGIN_SYSTEM §3; ARCHITECTURE §4.1) | — |

`Text`:

| Field | Type | |
| --- | --- | --- |
| `kind` | `text` | authored |
| `name` | `str`, as `Section`'s | authored |
| `text` | `str`, the passage as authored, as `gen` stores it (§2); the document gets its translation (§5) | authored |

Neither class carries an `english`: its own command is already the
document's text (COMMON.md §2). Neither records anything. Every row is
read with `rows.get`, so that a missing one is refused at start
(`TAT_StartupError`).

A `Section` has two operations, the beginning and the ending
(MODULE_STRUCTURE §4.1); the ending is the framework's default, a copy.
A `Text` has one. What an operation's last evaluation reported travels
on its status, as for every class (COMPILATION.md §4): a `Section`'s
beginning is a `CannotEvaluate` with its message where the framework
refuses the heading — its place, by the placement check, the level rule
of a heading above it among the answers (§6), or its `title`, by the
field check (§4) — and a clean `Ready` otherwise; a `Text`'s operation
is a clean `Ready`, or the framework's refusal of its place or of its
`text`. The constructors take the parent, the input slot and the
fields; `StdBlock` builds a `Section` with no children and mints its
slot before the ending (MODULE_STRUCTURE §4.1).

## 2. The heading and the passage

A heading is a name, a title and the declarations placed under it; its
level is judged against every heading above it (§6):

```json
{
  "kind": "section",
  "name": "Basics",
  "title": "Basic lemmas about reversal",
  "children": [
    {"kind": "text", "name": "intro", "text": "We start with the two lemmas every later proof uses."},
    {"kind": "lemma", "name": "rev_rev",
     "statement": {"english": "Reversing twice gives the list back",
                   "for_any": [{"name": "xs", "type": "'a list"}], "conclusion": "rev (rev xs) = xs"}},
    {"kind": "subsection", "name": "Lengths", "title": "Length is preserved",
     "children": [
       {"kind": "lemma", "name": "rev_length",
        "statement": {"english": "Reversal keeps the length",
                      "for_any": [{"name": "xs", "type": "'a list"}], "conclusion": "length (rev xs) = length xs"}}
     ]}
  ]
}
```

A passage is a name and its text, which may run to several paragraphs:

```json
{
  "kind": "text",
  "name": "overview",
  "text": "Insertion sort, and its correctness.\n\nSortedness is @{const sorted} of the list library."
}
```

`kind`, `name` and `title`, or `kind`, `name` and `text`, are required;
a `Section`'s `children` is optional, as for every nesting class
(PLUGIN_SYSTEM §3), and contents come later through `edit` as well. The
node's name is `name`: the id is TAT's way of referring to the heading
or the passage, the title and the text are what the document shows.
`gen` stores both as the agent wrote them: `title` with its whitespace
normalised — newlines become spaces, runs of whitespace one space, as an
`english`'s are —, `text` as written, since its blank lines separate
paragraphs and its line breaks are the agent's layout. Both are prose
(PLUGIN_SYSTEM §2): the file gets them through `document_cartouche`
(COMPILATION.md §3), the passage with `lists`, so that a Markdown item
starting a line makes a list, and so the second paragraph of the passage
above is written `Sortedness is ‹sorted› of the list library.` `title`
and `text` are `str`, not `IsaTerm`s: prose, which no Isabelle interface
reads.

The levels are ordered, `chapter` above `section` above `subsection`
above `subsubsection` above `paragraph` above `subparagraph`. A heading
stands only under headings of higher levels, whatever blocks lie
between, and may skip levels: a `subsection` directly under a `chapter`.
A heading under a heading of the same or a lower level is refused at
evaluation by that heading's level rule (§6), where a move is judged
like an insert; `gen` does not judge it. No command ends a heading, and
the file writes the nodes in tree order (§5): so in the document every
node that follows a heading as its sibling — a passage, a declaration, a
heading of a lower level — reads under that heading, up to the next
heading of the same or a higher level; the tree keeps them as siblings,
and `recall` shows the tree.

Headings and passages stand under any block, and any class stands under
a heading: `Section`'s `cannot_hold` answers its level rule alone (§6),
and a heading opens no Isabelle scope.

The classes' construct schemas:

```jsonc
{
  "type": "object",
  "description": "a heading of the theory's document, with the declarations under it",
  "properties": {
    "kind":     { "type": "string", "enum": ["chapter", "section", "subsection", "subsubsection", "paragraph", "subparagraph"] },
    "name":     { "type": "string", "description": "the name used in the node's id" },
    "title":    { "type": "string", "description": "the heading, in English" },
    "children": { "type": "array", "items": { "$ref": "#/$defs/Construct" },
                  "description": "the declarations under the heading" }
  },
  "required": ["kind", "name", "title"],
  "additionalProperties": false
}
```

```jsonc
{
  "type": "object",
  "description": "a passage of prose in the theory's document",
  "properties": {
    "kind": { "const": "text" },
    "name": { "type": "string", "description": "the name used in the node's id" },
    "text": { "type": "string", "description": "the passage, in English" }
  },
  "required": ["kind", "name", "text"],
  "additionalProperties": false
}
```

`#/$defs/Construct` is the framework's (PLUGIN_SYSTEM §4); neither
schema refers to a definition of the plugin's. Each class carries a
description, its name alone not saying what the node puts into the
document; `kind` carries none, the six levels being the agent's own
words; `name` carries one, since it names nothing in Isabelle
(COMMON.md §5).

What the classes do not take: an `english`; a target, `section (in
loc)`, which Isabelle refuses outside a theory context anyway;
`text_raw`, the passage that bypasses the document markup, and `txt`,
the passage inside a proof (INDEX.md §3).

## 3. Descriptions

The `Section` class:

```
a heading of the theory's document, with the declarations under it
```

`name`, of both classes:

```
the name used in the node's id
```

`title`:

```
the heading, in English
```

`children`:

```
the declarations under the heading
```

The `Text` class:

```
a passage of prose in the theory's document
```

`text`:

```
the passage, in English
```

## 4. `gen` and the field check

`Section.gen` and `Text.gen` refuse nothing: they store `title` and
`text` as §2 says. The field check (PLUGIN_SYSTEM §2) refuses, before
the node's first own operation, a `title` empty after normalisation and
a `text` with no character but whitespace (`InvalidField`). A `name`
outside the framework's name grammar is the framework's `InvalidName`,
and a sibling already bearing the node's id component its
`DuplicateName` (MCP_SPECIFICATION §2). Whether the heading stands
under headings of higher levels is judged at evaluation too (§6); a
refusal there, as the field check's, is an evaluation failure, not an
exception. The children of a `Section` are the framework's: built by
their own classes' `gen`s and placed under the node (MODULE_STRUCTURE
§4.2).

Neither class has jobs, so an amend carries nothing over: the
replacement is a fresh node, with the children it inherits on a
`Section` (MODULE_STRUCTURE §4.2).

The `InvalidField` sentences:

```
The field `title` must not be empty.
The field `text` must not be empty.
```

## 5. Emission

A `Section` emits, when its `can_emit` holds — the framework's default,
both stored statuses `Ready` (COMPILATION.md §3) — the beginning: the
heading command on one line, then one empty line when the heading has
children; the children in order, one empty line between siblings, at
the heading's own indent, the framework's (COMPILATION.md §3); no
ending. A `Text` emits its one command. The construct of §2, with its
passage, and the passage of §2 on its own:

```
section ‹Basic lemmas about reversal›

text ‹We start with the two lemmas every later proof uses.›

text ‹Lemma ‹rev_rev›. Reversing twice gives the list back.›
lemma rev_rev:
  fixes xs :: "'a list"
  shows "rev (rev xs) = xs"
  by aoa

subsection ‹Length is preserved›

text ‹Lemma ‹rev_length›. Reversal keeps the length.›
lemma rev_length:
  fixes xs :: "'a list"
  shows "length (rev xs) = length xs"
  by aoa
```

```
text ‹Insertion sort, and its correctness.

Sortedness is ‹sorted› of the list library.›
```

- The heading: the kind, a space, the title in a cartouche. The
  passage: `text`, a space, the text in a cartouche, its lines each at
  the node's indent. Both are written through `document_cartouche`
  (COMPILATION.md §3), the passage with `lists`, as a `Theory`'s
  `description` is (SESSION_AND_THEORY.md §2): paired marks stay, a stray
  mark is an ordinary symbol, and a Markdown item that starts a line of
  the passage makes a list, the content then started on a line of its
  own.
- The lemmas' `text` lines are their own (COMMON.md §2); neither class
  writes one of its own (§1).
- A heading with no child writes its line alone; the one empty line
  after it comes with the children.
- The children's text is their own, each class's `emit`, at the
  heading's indent.
- The text in the `unicode` spelling; the file takes the `\<name>` form
  from the compile's conversion (COMPILATION.md §2).

## 6. Evaluation

Neither class runs an Isabelle command: the heading and the passage are
read when the file is built, as an `english` is (COMMON.md §2). The
framework's checks stand before either hook, as for every class
(PLUGIN_SYSTEM §2): the placement check, then the field check (§4).

**The level rule.** `Section`'s `cannot_hold` (PLUGIN_SYSTEM §2)
refuses a heading of the same or a higher level than its own, at any
depth below it, whatever blocks lie between, with the remedy `Use a
lower level, or move it out.` The placement check asks every ancestor
outermost first, so the refusal names the outermost heading the node
cannot stand under: a `section` under a `subsection` under `section_A`
is refused with `section_A` named:

```
A `section` cannot stand under `session_S.theory_X.section_A`. Use a lower level, or move it out.
```

The framework asks it before the heading's beginning at every
evaluation, so a move is judged anew. Refused, the heading is an
obstacle: its children have no context and are `not_evaluated`, and the
ending is `Ready` by the framework's copy of the heading's input to its
result when the walk goes on past it (ARCHITECTURE §3.3).

**`Section`'s beginning.** `_eval_beginning_opr` copies its input slot
into its resulting slot — `operation_slots("beginning")`: the input slot
and the first child's input, or the slot before the ending when there
is no child (MODULE_STRUCTURE §4.1) — through `Isar_State_Slot.copy_to`,
and is a clean `Ready`.

**Inside the heading.** The children run in order from the beginning's
resulting slot, each in the state the one before it left (ARCHITECTURE
§3.5), the state the heading was given: a heading opens no Isabelle
scope. A child inserted, amended or deleted invalidates what follows it
under the heading and the ending, never the beginning
(CONSTRUCT_INTERACTION §3.1); an edit of the heading's own fields
invalidates it whole.

**`Section`'s ending.** The framework's default: the slot after the last
child copied into the heading's resulting slot, a clean `Ready`
(COMPILATION.md §3).

**`Text`.** `_eval_opr` copies the input slot into the resulting slot
and is a clean `Ready`.

## 7. The mark

Both classes take the framework's default mark (PRINT.md §1). A `Text`
reads `not evaluated` until its operation ran, `failed` when the
placement check or the field check refuses it, and `complete` otherwise.
A `Section` reads `not evaluated`, `incomplete` while something under it
is unfinished, `failed` when its beginning is refused — by the placement
check, the level rule among its answers, or by the field check — and
`complete` otherwise. Neither answers an owing
line. In an ancestor's Recall summary (PRINT.md §2) a heading is counted
by its own operations, among the failed nodes while its beginning is
refused.

## 8. What it prints

A `Section` writes its title on its line and no field under it; a
`Text` writes its text under its line, under `Recall` alone (PRINT.md
§2, §3):

| mode | `Section`: `caption` | `Text`: `print_fields` writes |
| --- | --- | --- |
| `Out_Focus` | nothing | nothing |
| `Briefing` | nothing | not called |
| `Relative_Focus`, on the path | nothing | — |
| `Relative_Focus`, a focus | the title | nothing |
| `Recall`, depth 0 and 1 | the title | the text |
| `Recall`, depth 2 and 3 | nothing | nothing |

The title is the **caption** of PRINT.md §1, written by the framework
on the node's line after its id and a colon, before the mark; `Section`
answers it where the node is detailed (PRINT.md's `detailed`: a focus,
or `Recall` at depth 0 and 1), `None` elsewhere, so the briefing and
the lines beside a focus show the id alone. Its `print_fields` writes
nothing and answers false; its children header is `declarations`
(PRINT.md §2), the word `Theory` answers, since the children of both
are the declarations under them: the children stand one level deeper
under `declarations:` when a message block stands above them — the
beginning's refusal —, directly under the line otherwise. A `Text`'s
`print_fields` writes the text, every line at the fields' indent, as
stored but for its trailing line breaks, which it drops; no key; and
answers false.

A `recall` of the heading of §2 — its passage, its lemma and its
subsection at depth 1, the subsection's lemma at depth 2:

```
- section_Basics: Basic lemmas about reversal (incomplete)
  - text_intro (complete)
    We start with the two lemmas every later proof uses.
  - lemma_rev_rev (valid statement, proven)
    ⋀xs::'a list. rev (rev xs) = xs
    Reversing twice gives the list back
  - subsection_Lengths: Length is preserved (incomplete)
    - lemma_rev_length (valid statement, proof not started)
      ⋀xs::'a list. length (rev xs) = length xs
```

A `recall` of its theory — the heading at depth 1, the subsection at
depth 2, where neither its title nor the passage's text is written:

```
- theory_X (incomplete)
  imports: Main
  declarations:
    - section_Basics: Basic lemmas about reversal (incomplete)
      - text_intro (complete)
      - lemma_rev_rev (valid statement, proven)
        ⋀xs::'a list. rev (rev xs) = xs
      - subsection_Lengths (incomplete)
        - lemma_rev_length (valid statement, proof not started)
```

The quickview after an `edit` that appended a heading with a passage
and a subsection to `theory_X` — the new nodes are focuses to the
bottom, the heading before them and the other theory are lines beside
them:

```
session_A (incomplete)
- theory_X (incomplete)
  - section_Basics (incomplete)
  - section_Sorting: Insertion sort (not evaluated)
    - text_overview (not evaluated)
    - subsection_Correctness: Sortedness and permutation (not evaluated)
      - lemma_isort_sorted (not evaluated, proof not started)
- theory_Y (complete)
```

A `recall` of a heading whose beginning was refused, a `section` placed
under a `subsection_Lengths` that stands directly under `theory_X`: the
`Error:` block is a keyed line, so its children stand under
`declarations:`:

```
- section_Details: The details (failed)
  Error:
    A `section` cannot stand under `session_A.theory_X.subsection_Lengths`. Use a lower level, or move it out.
  declarations:
    - lemma_rev_length (not evaluated, proof not started)
      ⋀xs::'a list. length (rev xs) = length xs
      Reversal keeps the length
```

## 9. Id properties

`Section` is omissible in both directions, with drop priority 0: the
first component to go, before `Session`'s and the blocks' at 1 and
`Theory`'s at 2 (MCP_SPECIFICATION §2.1) — the heading is a scope to
TAT and none to Isabelle, a child's qualified name not carrying it,
`X.rev_rev`. A child's id prints as short as the forest allows,
`lemma_rev_rev`, and is accepted with or without the component; the
heading's own component, `section_Basics`, ends its own id and is never
dropped from it.

`Text` declares none: a leaf's component is the last of every id, and
the framework's defaults stand (MCP_SPECIFICATION §2.1).
