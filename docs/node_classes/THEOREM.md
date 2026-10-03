# The `Theorem` node class

Status: decided, last on 2026-10-02, after four design reviews
(ai-artifacts/review/CONSTRUCT_RULING*.md); the AoA round is open. The
machinery this class uses — jobs, agents, messages, the tools — is
CONSTRUCT_INTERACTION.md; this file says only what `Theorem` makes of
it.

A `Theorem` states a fact and never proves it in the tree (ARCHITECTURE
§2.1): every evaluation admits it with `sorry`; its construction job,
the proof construction, finds a proof, which its evaluation job, the
proof check, replays in the current context, and which the emitted
theory carries as `by aoa`. It is a `Leaf`, delivered in
`theorem_node.py` with its two job classes `Proof_Job` and `Proof_Check`
(MODULE_STRUCTURE §4.5). Its agent-facing wording lives here: the
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
| `reserved_names` | `set[str]`: the names of the statement — the fact's, the variables', the premises' — that the last evaluation found reserved by the input theory's keyword table, in their `ascii` spelling, written in double quotes at emission (§5); stored, since emission runs on a loaded forest and reads only stored fields | recorded |

What the last evaluation reported is no field of the class: the
messages travel on the status the evaluation hook returns —
`CannotEvaluate(messages)` when the statement failed, `Ready(messages)`
when it went through and Isabelle still had something to say — and the
framework stores and prints them (COMPILATION.md §4, PRINT.md §3).

Three things more are recorded on the node by the framework, not by
the class: the two jobs' outcomes and the construction job's
automatic-construction setting (CONSTRUCT_INTERACTION §3.2). `proof` is
the construction job's outcome (CONSTRUCT_INTERACTION §3.1):
`NOT_STARTED`, `RUNNING`, `SUCCEEDED(product)` or `FAILED(message)`,
`product` being the proof: the method text AoA writes to its proof
store, such as `(simp add: …)` or `aoa_replay "…"`, with the two times of
its replay — the thread's CPU time and the wall time, in milliseconds,
as AoA records them beside a proof — which the proof check derives its
limits from (§7); it is stored. The proof check's outcome — `RUNNING`, `PASSED`, `FAILED` —
is read through the framework's `check_outcome()`: `RUNNING` while a
running proof check is on the node, the stored check otherwise, which
is cleared when a stored status of the node leaves `ready`, when a proof
construction starts, or when another check takes its place, and by
nothing else (CONSTRUCT_INTERACTION §3.3, ARCHITECTURE §4.1). The mark
(§7), `_check()` (§7), emission (§5) and the failure block (§8) read it
there.

The construction job is compulsory: the node is finished only when
`proof` is `SUCCEEDED` and the proof check `PASSED` (ARCHITECTURE §3.2,
the framework's `_unfinished`).

## 2. The statement

`statement` is AoA's `LongStatement`, shared through `STATEMENT_DEFS`
(`Variable` and `LongStatement`, adapted from
`contrib/Isa-Mini/IsaMini/AoA/tools/cc_edit.jsonc` — TAT's copy, with
the descriptions of §3) so that every class
using it — a future `Define` — merges the same definition (PLUGIN_SYSTEM
§5):

```json
{
  "english":    "The length of a reversed list",
  "for_any":    [{"name": "xs", "type": "'a list"}],
  "premises":   [{"name": "ne", "term": "xs ≠ []"}],
  "conclusion": "length (rev xs) = length xs"
}
```

`english` and `conclusion` are required, `for_any` and `premises`
optional. `gen` normalises every term (`for_any[].type`,
`premises[].term`, `conclusion`) and `english` once, when the construct
is accepted: newlines become spaces and runs of whitespace one space;
printing, emission and evaluation all use the stored text.

Every piece of Isabelle text is an `IsaTerm` (`Isabelle_RPC_Host.
unicode`, shared with AoA): one value holding the text in both
spellings, `unicode` as the agent writes and reads it and `ascii` in
Isabelle's `\<name>` form, the only form Isabelle/ML reads; built by
`IsaTerm.from_agent` at `gen` and by `IsaTerm.from_isabelle` where
Isabelle's text comes back, `str()` refused, two equal when their
`ascii` is. `for_any[].name`, `for_any[].type`, `premises[].name`,
`premises[].term` and `conclusion` are `IsaTerm`s; `english` and `name`
are `str`. Printing writes `.unicode`, emission and every ML call
`.ascii`; the store holds `.unicode`.

The class's construct schema:

```jsonc
{
  "type": "object",
  "properties": {
    "kind":      { "type": "string", "enum": ["lemma", "theorem", "corollary", "proposition"] },
    "name":      { "type": "string", "description": "The fact's name" },
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

`name`:

```
The fact's name
```

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

`Theorem.gen` checks: the parent is inside a theory — a `Theory`, or a
nesting node under one; never a `Session` or the root
(`BadTheoremNodeParent`, RENDER_BASELINES §2); `name` against §1's
grammar (`InvalidName` with `grammar` = `fact name`, rendered as
RENDER_BASELINES §2's fourth form with that grammar); every `for_any`
variable's `name` and every premise's `name` an Isabelle identifier — on
the `ascii` form, a letter or one of Isabelle's letter symbols, then
letters, digits, underscores, primes, and `\<^sub>` before a letter or
digit, judged in Python beside `IsaTerm` with the symbol table's letter
symbols (`get_LETTER_SYMBOLS()` of `Isabelle_RPC_Host.unicode`), so `ε`
and `x⇩1` pass — a variable's not ending with an
underscore, and no two of either the same (`InvalidField`). Whether the
terms parse is Isabelle's business at evaluation (MODULE_STRUCTURE
§4.1); a term Isabelle rejects is an evaluation failure, not an
exception. On an amend, `gen` compares the new `for_any`, `premises` and
`conclusion` with those of the node it replaces — `config.replaces()`,
the `Amendment`'s `old` for the batch's first construct (MODULE_STRUCTURE
§4.1) — names included and `english` aside, through the one private
helper that also builds the structure
sent to Isabelle (§6), so what is compared is what the check replays;
when equal it asks, through the framework's `carry_job_from(old)`, for
the replaced job's outcome to be carried into
the new node's job, and the commit copies the store's image
(CONSTRUCT_INTERACTION §3.1), the replay times with it.

The `InvalidField` sentences:

```
The field `statement.for_any[0].name` must be an Isabelle identifier.
The field `statement.for_any[0].name` must not end with an underscore.
The field `statement.premises[1].name` binds `ne` a second time.
```

The `InvalidName` rendering:

```
`rev-length` is not a valid fact name: a fact name starts with a letter and continues with letters, digits, underscores and primes ('), and does not end with an underscore.
```

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

- The `text` line: the kind capitalised, the name, a period, then
  `english`, with a period added when it ends without `.`, `!` or `?`.
  `‹`, `›`, `\<open>` and `\<close>` in `english` are replaced by `"` at
  emission, so the cartouche always closes where it should; nothing is
  refused.
- A variable without `type` is fixed bare (`fixes xs`); an empty
  `for_any` or `premises` omits its clause; every term in double quotes.
- A name in `reserved_names` (§1) is written in double quotes — `lemma
  "open":`, `fixes "for"`, `assumes "if":` — the rule of Isabelle's own
  `Token.print_name`; every other name bare.
- `by aoa` when `proof` is `SUCCEEDED` and the proof check's stored
  outcome (§1) is `PASSED`; `sorry` otherwise — an unchecked proof is
  written as `sorry`.
- The whole text in the `\<name>` form (`IsaTerm.ascii`, §2); the file
  reads as Unicode in jEdit all the same.

## 6. Evaluation

The evaluator runs the statement and admits it, never a proof
(ARCHITECTURE §3.6), and never runs the `text` command. It goes through
the ML interfaces. `Theorem._eval_opr` sends the class's callback
`TAT.Theorem.evaluate` the input slot, the resulting slot, and the
statement as structure — `kind`, `name`, the `for_any` variables with
their types, the premises, the conclusion — each `IsaTerm` as its
`ascii` (§2). The ML side builds one transition and applies it to the
input slot's state:

```
Toplevel.local_theory NONE NONE
  (Specification.theorem_cmd … Element.Fixes / Element.Assumes / Element.Shows …
   #> Proof.global_skip_proof true)
|> Toplevel.command_errors true
```

— the shape of `begin_theory`, no `run_span` envelope, no proof step —
and writes the resulting state into the resulting slot: at theory level
the same four steps as a hand-written `theory_init … exit_global`, and
inside a future `Context` or `Locale` the statement is checked in that
context, as ARCHITECTURE §2 promises. An interrupt and a `Bug` are
re-raised; any other error is the statement's: no state is written, the callback
answers the messages, and `_eval_opr` returns `CannotEvaluate` with
them — the node is an obstacle. Otherwise the callback answers what the
run reported beside its success and, for the fact's name, each
variable's and each premise's, whether `Thy_Header.print_name` would
quote it in this theory; `_eval_opr` returns `Ready` with those
messages, the class records the names as `reserved_names` (§1), and
emission quotes them (§5). A reserved name
is not a failure: Isabelle accepts it quoted at every use.

The proof check is started apart from the evaluation, by the framework's
`start_evaluation_job()` (CONSTRUCT_INTERACTION §3.3): with the job
already on the node, `Proof_Check._start` calls the class's second
callback `TAT.Theorem.check` with the input slot, the statement as
above, the stored `product` — the text and its times — and the job's
`id`; the callback forks the
check as a Future task (§7) and returns.

## 7. The jobs and the mark

### `Proof_Job`

`title()` is `proof construction`, `title(plural=True)` `proof
constructions`; `compulsory` is true. Its `_run` drives AoA (deferred:
the drive path, driver and budget, the proof store, the questions it
asks — under two requirements of the owner's: AoA's `request` reports to
the TAT agent driving the job, as a question it answers, and AoA is told
it runs under TAT; CONSTRUCT_INTERACTION §10) and, on success, attaches
`Proof_Check.passed(node)` to the node and returns `SUCCEEDED` with the
proof, text and times, as `product`: a run that reaches its end saw no context change
(the default `_on_context_change` below), so the proof AoA verified
holds in the current context and the node is `proven` from the run's
settlement on.
`_check()` answers whether a proof can be constructed on the node as it
stands; a node it answers false for is skipped by `construct` and by
automatic construction, with no sentence of its own:

| the node | `_check()` |
| --- | --- |
| not `ready` | false |
| `ready`, no proof — `NOT_STARTED` or `FAILED` | true |
| `SUCCEEDED`, the proof check `PASSED` | false: it is proven |
| `SUCCEEDED`, no proof check yet or one `RUNNING` | false: the proof is checked first |
| `SUCCEEDED`, the proof check `FAILED` | true |

`_on_context_change` is the default: the job is cancelled with
`CONTEXT_CHANGED` whenever the walk writes the node's status while it
runs — leaving `ready`, or rewriting it on a rerun. Overriding it to
continue on the new context and repair the stored proof is the AoA
round's.

Its sentences (the rest are the framework's defaults from `title`):

| situation | |
| --- | --- |
| `finished_notification`, success | `` `theory_X.lemma_P` is proven. `` |
| `finished_notification`, failure | `` No proof of `theory_X.lemma_P` was found: `` + the message |
| `failure_header` | `No proof was found:` |

### `Proof_Check`

`Theorem.evaluation_job_class`. `title()` is `proof check`,
`title(plural=True)` `proof checks`. `make` is the default; `_start`
calls `TAT.Theorem.check` (§6) once the framework has put the job on the
node. Its work, the Future task the callback forks: the goal is built
in ML from the statement in the input slot's context —
`Specification.theorem_cmd` on the slot's local theory, the function
the evaluation's transition (§6) calls, and `Proof.goal` of the
`Proof.state` it yields; no Toplevel transition — and the stored
`product`, the text with its times, is replayed on that goal through a
function exported from AoA: the part of
`Proof_Store_AoA.store_hit_replay`
(`contrib/Isa-Mini/Agent/proof_store_AoA.ML`) that takes one record,
derives the replay limits from its times
(`Phi_Proof_Store.replay_limits`) and evaluates its text as a method on
the goal (`Phi_Sledgehammer_Solver.eval_prf_str`). TAT writes no limit
of its own, reads nothing from AoA's proof store and changes nothing in
it. A `product` of the form `aoa_replay "<b64>"` is itself a method
that re-runs the recorded Minilang commands; one Sledgehammer found is
a plain method text such as `metis …`. The check and the construction
are about the same statement. A theorem out is `PASSED` and is
discarded. No theorem — the method failing, subgoals left, a limit
exceeded — is `FAILED` with an empty message: the replay reports a
class of failure and no text, and the agent can only have the proof
constructed again; the callback reports it as one empty error. Nothing
in the work applies a Toplevel transition or forks a proof, so it never
enters Isabelle's execution table (CONSTRUCT_INTERACTION §3.3).
`_finished` is the default. The class method `passed(node)` builds an
instance with `outcome = PASSED` without running, for `Proof_Job`.

Its sentences. The failure block is the header alone, its colon a
period since no message follows (CONSTRUCT_INTERACTION §6); the
notification tells what to do next, and names several nodes in one
sentence or one list (CONSTRUCT_INTERACTION §3.4):

```
The proof no longer holds.
The proof of `theory_X.lemma_P` no longer holds. Call `construct` to prove it again.
The proof of `theory_X.lemma_P`, of `theory_X.lemma_Q` and of `theory_X.lemma_R` no longer holds. Call `construct` to prove them again.
The following proofs no longer hold; call `construct` to prove them again:
  - theory_X.lemma_P
  - theory_X.lemma_Q
  - theory_X.lemma_R
  - theory_Y.lemma_S
```

For the nodes under automatic construction the failure starts the
proof construction at once (CONSTRUCT_INTERACTION §3.3), and the
notification says so in place of the instruction:

```
The proof of `theory_X.lemma_C` no longer holds, so its proof construction was started automatically; call `check_construct` before you exit.
The proof of `theory_X.lemma_C`, of `theory_X.lemma_G` and of `theory_X.lemma_K` no longer holds, so their proof constructions were started automatically; call `check_construct` before you exit.
The following proofs no longer hold, so their proof constructions were started automatically; call `check_construct` before you exit:
  - theory_X.lemma_C
  - theory_X.lemma_G
  - theory_X.lemma_K
  - theory_X.lemma_M
```

### The mark

`Theorem` overrides `mark` with two slots, `(<statement>, <proof>)`; the
framework's `complete` never appears on its line.

The statement slot, from the node's evaluation status: `valid statement`
(`ready`), `invalid statement` (`cannot_evaluate`), `not evaluated`.

The proof slot, from `proof` and the proof check:

| `proof` | proof check | word |
| --- | --- | --- |
| `NOT_STARTED` | | `proof not started` |
| `RUNNING` | | `proving` |
| `FAILED` | | `failed to prove` |
| `SUCCEEDED` | none | `unchecked proof` |
| `SUCCEEDED` | `RUNNING` | `proof checking` |
| `SUCCEEDED` | `PASSED` | `proven` |
| `SUCCEEDED` | `FAILED` | `bad proof` |

Under `invalid statement` the proof slot is left out: `(invalid
statement)`. Under `not evaluated` a stored proof is left out and the
other two words written: `(not evaluated)`, `(not evaluated, proof not
started)`, `(not evaluated, failed to prove)`. A running proof check
exists only under `valid statement` — a stored check survives under
`not evaluated`, where the proof slot is left out — and a running proof
construction only there too, so the line reads one of eleven ways, plus
the tags of CONSTRUCT_INTERACTION §6: `automatic construction` for every
agent, `needs your answer …` for the owner:

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

The jobs' blocks — the framework prints them after `print_fields`, when
detailed, while the outcome is `FAILED` and the node is not an obstacle
(CONSTRUCT_INTERACTION §6) — are the failure blocks alone: the header of
§7 and the message one level deeper. A pending question is never printed
here; the tag on the line sends the agent to `check_construct`, after
the tag `automatic construction` when that setting is on
(CONSTRUCT_INTERACTION §6). The line
with a question waiting; a focus in a quickview after a failed proof
construction; a node under `recall` whose stored proof failed its check:

```
- lemma_rev_length (valid statement, proving, needs your answer, call `check_construct` to see it)
```

```
- lemma_rev_length (valid statement, failed to prove)
  No proof was found:
    Sledgehammer timed out on every prover; the goal needs an induction the search did not attempt.
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
