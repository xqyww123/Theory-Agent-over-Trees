# The `Theorem` node class

Status: decided, last on 2026-10-02, after four design reviews
(ai-artifacts/review/CONSTRUCT_RULING*.md); revised 2026-10-12 with the
node-class rounds (ai-artifacts/review/NODE_CLASS_RULINGS.md), what
every class shares moved to COMMON.md; the AoA round is open. The
machinery this class uses — jobs, agents, messages, the tools — is
CONSTRUCT_INTERACTION.md; this file says only what `Theorem` makes of
it.

A `Theorem` states a fact and never proves it in the tree (ARCHITECTURE
§2.1): every evaluation admits it with `sorry`; its construction job,
the proof construction, finds a proof, which its evaluation job, the
proof check, replays in the current context, and which the emitted
theory carries as `by aoa`. It is a `Leaf`, the first node class of the
plugin `Isabelle_Std`, deriving from the plugin's `Proof_Obligation`
(COMMON.md §3), whose job classes `Proof_Job` and
`Proof_Check` are `Proof_Obligation`'s: its Python half is
`isabelle_theory_agent/std/theorem.py`,
its ML half `Isabelle_Std/ML/TAT_Theorem.ML`, loaded by the plugin's
theory `TAT_Isabelle_Std`, which imports AoA's. A working directory has
it when it was made with `-P TAT_Isabelle_Std.TAT_Isabelle_Std` to
`isabelle TAT_new` or `isabelle TAT`. Its agent-facing wording lives here: the
`description` texts of its construct schema (§3), the sentences its
`gen` and its jobs render, and the words on its line — pinned by the
baseline tests the way SESSION_AND_THEORY.md's are.

Kinds: `lemma`, `theorem`, `corollary`, `proposition` — the Isar
commands Isabelle treats alike (`Pure.thy`, `thy_goal_stmt`). The kind
heads the id component: `lemma_P`.

## 1. Fields

| Field | Type | |
| --- | --- | --- |
| `kind` | one of the four | authored |
| `name` | the fact's name, `str`, in the id grammar without hyphens — a letter, then letters, digits, underscores and primes, not ending in an underscore — since it is the node's id component (MCP_SPECIFICATION §2); a name outside it is refused with the grammar's own sentence, as a `Theory`'s is | authored |
| `statement` | `LongStatement` (§2) | authored |

What the last evaluation reported is no field of the class: the
messages travel on the status the evaluation hook returns —
`CannotEvaluate(messages)` when the statement failed, `Ready` with no
messages when it went through — and the framework stores and prints
them (COMPILATION.md §4, PRINT.md §3).

Three things more are recorded on the node by the framework, not by
the class: the two jobs' outcomes and the construction job's
automatic-construction setting (CONSTRUCT_INTERACTION §3.2). `proof`,
its product, the proof check's outcome, the slot `goal_state` and the
compulsory construction job are `Proof_Obligation`'s (COMMON.md §3).

## 2. The statement

`statement` is AoA's `LongStatement`, shared through `STATEMENT_DEFS`
(`Variable` and `LongStatement`, adapted from
`contrib/Isa-Mini/IsaMini/AoA/tools/cc_edit.jsonc` — TAT's copy, with
the descriptions of §3) so that every class
using it merges the same definition (PLUGIN_SYSTEM §5):

```json
{
  "english":    "The length of a reversed list",
  "for_any":    [{"name": "xs", "type": "'a list"}],
  "premises":   [{"name": "ne", "term": "xs ≠ []"}],
  "conclusion": "length (rev xs) = length xs"
}
```

`english` and `conclusion` are required, `for_any` and `premises`
optional. Every variable the premises and the conclusion use is declared
in `for_any`, unless the context the node stands in fixes it — a
`Locale`'s parameters inside its block (LOCALE.md §6): one Isabelle
fixed by itself is refused at evaluation (§6).
`gen` normalises every piece of Isabelle text — the names, the types,
the terms — and `english` once, when the construct is accepted:
newlines become spaces and runs of whitespace one space; printing,
emission and evaluation all use the stored text.

Every piece of Isabelle text is an `IsaTerm` (MODULE_STRUCTURE §4.3):
`for_any[].name`, `for_any[].type`, `premises[].name`,
`premises[].term` and `conclusion` are `IsaTerm`s; `english` and `name`
are `str`.

The class's construct schema:

```jsonc
{
  "type": "object",
  "properties": {
    "kind":      { "type": "string", "enum": ["lemma", "theorem", "corollary", "proposition"] },
    "name":      { "type": "string" },
    "statement": { "$ref": "#/$defs/LongStatement" }
  },
  "required": ["kind", "name", "statement"],
  "additionalProperties": false,
  "$defs": STATEMENT_DEFS
}
```

Neither the class nor `kind` carries a description: the class name says
what it is, and the four kinds need no telling apart.

Whether the proof is constructed automatically is not a field of the
construct: it is `edit`'s `auto_construct` (TOOL_SCHEMAS.md §1), the
framework's setting on the construction job (CONSTRUCT_INTERACTION
§3.2), and the class declares nothing for it.

## 3. Descriptions

`LongStatement`, in the order `english`, `for_any`, `for_any[].type`,
`premises`, `premises[].name`, `premises[].term` and `conclusion`:

```
the statement in English, as LaTeX text
universally quantified variables to fix
An Isabelle type expression. Leave empty ("") if unsure
named premises to assume
binding name for the premise
Isabelle/HOL term with all literal numbers annotated with types
```

(`for_any[].type` is `Variable.type`; the last line is both
`premises[].term` and `conclusion`.) An empty `type` is no type.

## 4. `gen`

Where a `Theorem` stands is COMMON.md §1's; the framework checks it, not
`gen` (PLUGIN_SYSTEM §2).

`Theorem.gen` checks: `name` against §1's grammar (`InvalidName` with
`grammar` = `fact name`, rendered as RENDER_BASELINES §2's fourth form
with that grammar); every `for_any` variable's `name` and every
premise's `name` an Isabelle identifier (COMMON.md §5), a variable's not
ending with an underscore (COMMON.md §5's clause on internal names), and
no two of either the same (`InvalidField`). Whether the terms parse is
Isabelle's business at evaluation (MODULE_STRUCTURE §4.1); a term
Isabelle rejects is an evaluation failure, not an exception. `Theorem`'s
`goal_structure()` (COMMON.md §3) is the `for_any`, `premises` and
`conclusion`, names included — each binds a fact a stored proof may cite
—, each `IsaTerm` as its `ascii`; `message()` carries it as its goal
part (§6; COMMON.md §3). `english`, `kind` and `name` are not in it,
since Isabelle opens the same goal for the four kinds and for any name:
on an amend a rename, a change of kind or a reworded `english` keeps the
proof, and a change to any other part of the statement does not. `gen`
has no part in it.

The `InvalidField` sentences:

```
The field `statement.for_any[0].name` must be an Isabelle identifier: it starts with a letter and continues with letters, digits, underscores and primes ('), and does not end with an underscore.
The field `statement.premises[1].name` repeats `ne`.
```

The grammar text after the colon is the framework's, the one
`InvalidName` renders for the grammar `fact name` (RENDER_BASELINES
§2), written once and used by both.

## 5. Emission

The node emits, when its `can_emit` holds — `Theorem` keeps the
framework's default (COMPILATION.md §3) — two commands:

```
text ‹Lemma rev_length. The length of a reversed list.›
lemma rev_length:
  fixes xs :: "'a list"
  assumes ne: "xs ≠ []"
  shows "length (rev xs) = length xs"
  by aoa
```

- The `text` line's lead: the kind capitalised and the name, `Lemma
  rev_length.`; the line is COMMON.md §2's.
- A variable without `type` is fixed bare (`fixes xs`); an empty
  `for_any` or `premises` omits its clause.
- Every piece of Isabelle text — a name, a variable's type, a term —
  is written through the theory's `print_name` (SESSION_AND_THEORY §2):
  bare when its `ascii` is an Isabelle identifier (`is_identifier`,
  COMMON.md §5) that is not a keyword of the theory, as Isabelle's
  string token (COMPILATION.md §3) otherwise — `lemma "open":`, `fixes
  "for"`, `assumes "if":`; `fixes xs :: "'a"` quoted, a conclusion
  `True` bare, `"P x"` quoted.
- The terminal proof, `by aoa` or `sorry`, is `Proof_Obligation`'s
  `proof_text()` (COMMON.md §3); the `aoa` method's import is the
  plugin's (PLUGIN_SYSTEM §1; SESSION_AND_THEORY §2).
- The text in the `unicode` spelling; the file takes the `\<name>` form
  from the compile's conversion (COMPILATION.md §2) and reads as Unicode
  in jEdit all the same.

## 6. Evaluation

The evaluator runs the statement and admits it, never a proof
(ARCHITECTURE §3.6), and never runs the `text` command. It goes through
the ML interfaces. `Proof_Obligation`'s `_eval_opr` (COMMON.md §3)
sends the class's callback — `evaluation_callback`,
`TAT.Theorem.evaluate` — the input slot, `goal_state`, the resulting
slot, and its `message()`: `kind`, `name` and `goal_structure()` — the
`for_any` variables with their types, the premises, the conclusion —
each `IsaTerm` as its `ascii` (§2). The callback is built by
`TAT_Proof_Obligation` (COMMON.md §3) from `Theorem`'s two steps:
`open_goal`, the `lemma` command's transition and, on the open goal,
the check below, yielding nothing; `after_admission`, the identity.
Between the two the callback applies the half of `sorry` that ends a
toplevel goal (`Isar_Cmd.global_skip_proof`):

```
Toplevel.local_theory_to_proof NONE NONE
  (Specification.theorem_cmd … Element.Fixes / Element.Assumes / Element.Shows …)

Toplevel.end_proof Proof.global_skip_proof
```

— the shape of `begin_theory`, through `apply_transition`, no proof step.
The first's result, the goal open and no step taken, goes into
`goal_state`, where the proof construction and the proof check find
their goal; the second's into the resulting slot (COMMON.md §3): at
theory level the same four steps as a hand-written `theory_init …
exit_global`, and inside a future `Context` or `Locale` the statement
is checked in that context, as ARCHITECTURE §2 promises. A failure is
`Proof_Obligation`'s (COMMON.md §3). On the open goal, `Theorem`'s
`open_goal` refuses the statement whose
free variables — in the goal, or in the premises assumed beside it —
`for_any` does not declare and the input state's context does not fix
— a `Locale`'s parameters inside its block (LOCALE.md §6) —, which
Isabelle fixed by itself (§2): the
same failure, one message naming them in alphabetical order,

```
Undeclared variable `x`: declare it in `for_any`.
Undeclared variables `x` and `y`: declare them in `for_any`.
```

Its head, `Undeclared variable(s) …`, is written by one writer of
TAT_Theorem.ML, which the axioms' sentences of LOCALE.md §6 share with
the axioms named after the variables; the lists are joined by its
`series`, the twin of the framework's `exceptions.series`.

Otherwise `_eval_opr` returns `Ready` with no messages: `Theorem`'s
`record_from_evaluation` is `Proof_Obligation`'s default, which records
nothing (COMMON.md §3). The proof check
and the proof construction, with their callbacks
`TAT.Proof_Obligation.check` and `TAT.Proof_Obligation.construct`, are
`Proof_Obligation`'s (COMMON.md §3).

## 7. The jobs and the mark

The proof construction, `Proof_Job`, the proof check, `Proof_Check`,
their callbacks `TAT.Proof_Obligation.construct` and
`TAT.Proof_Obligation.check`, their sentences, and the two-slot mark
`(<status>, <proof>)` are `Proof_Obligation`'s (COMMON.md §3);
`Theorem` names no assertion, and its refutation sentence
(`refutation_sentence`, COMMON.md §3) is `` `lemma_rev_length` may not
hold ``. `Theorem`'s own words are `valid_word` and `invalid_word`:
`valid statement` (`ready`) and `invalid statement`
(`cannot_evaluate`). Its line reads
one of eleven ways, plus the tags of CONSTRUCT_INTERACTION §6:
`automatic construction` for every agent, `needs your answer …` for the
owner:

```
(valid statement, proof not started)  (valid statement, proving)         (valid statement, failed to prove)
(valid statement, unchecked proof)    (valid statement, proof checking)  (valid statement, proven)
(valid statement, bad proof)
(invalid statement)
(not evaluated)                       (not evaluated, proof not started) (not evaluated, failed to prove)
```

## 8. What it prints

`print_fields` (PRINT.md §3) writes the statement, and only under
`Recall`; wherever it is called the framework writes the evaluation's
messages after it (a leaf is never on a focus's path):

| mode | `print_fields` writes |
| --- | --- |
| `Out_Focus` | nothing |
| `Briefing` | not called |
| `Relative_Focus`, a focus | nothing |
| `Recall`, depth 0 and 1 | the proposition, `english` |
| `Recall`, depth 2 | the proposition |
| `Recall`, depth 3 | nothing |

The proposition is the whole statement in Isabelle's meta form — one `⋀`
per `for_any` variable, `::T` when typed, one `⟹` per premise, names
dropped, a premise or conclusion that itself contains `⋀` or `⟹` in
either spelling wrapped in parentheses so the line still reads as one
rule — assembled from the stored text, without a round trip to
Isabelle; `english` follows it; neither line carries a key; each is one
line (§2).

```
⋀xs::'a list. xs ≠ [] ⟹ length (rev xs) = length xs
The length of a reversed list
```

The evaluation's messages are the framework's to print (PRINT.md
§3–§4): after the statement, as an `Error:` block while the node is an
obstacle and as a `Notice:` block when a `Ready` carries messages;
whole under `Recall` at depth 0 and 1, elsewhere once per run, through
the seen set, whose keys the framework keeps and discards at every
status write.

The jobs' blocks are `Proof_Obligation`'s (COMMON.md §3). A pending
question is never printed here; the tag on the line sends the agent to `check_construct`, after
the tag `automatic construction` when that setting is on
(CONSTRUCT_INTERACTION §6). The line
with a question waiting; a focus in a quickview after a failed proof
construction, and after the agent refuted the statement; a node under `recall`
whose stored proof failed its check:

```
- lemma_rev_length (valid statement, proving, needs your answer, call `check_construct` to see it)
```

```
- lemma_rev_length (valid statement, failed to prove)
  No proof was found:
    Sledgehammer timed out on every prover; the goal needs an induction the search did not attempt.
```

```
- lemma_rev_length (valid statement, failed to prove)
  `lemma_rev_length` may not hold:
    For xs = [a, b], rev xs = [b, a] differs from xs while the premise xs ≠ [] holds: the statement fails as stated.
```

```
- lemma_rev_length (valid statement, bad proof)
  ⋀xs::'a list. xs ≠ [] ⟹ length (rev xs) = length xs
  The length of a reversed list
  The proof no longer holds.
```

## 9. Id properties

None declared: a leaf's component is the last of every id, and the
framework's defaults stand (MCP_SPECIFICATION §2.1).
