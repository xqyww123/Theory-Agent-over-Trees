# The node classes of `Isabelle_Std`

Status: the list, fixed 2026-10-04; every class its row marks unspecified
is design to come.

The plugin `Isabelle_Std` (MODULE_STRUCTURE §4.5) carries the node
classes of Isabelle's standard commands. This document is the list of
them: what each class is, which Isabelle commands it covers, what it
derives from (MODULE_STRUCTURE §4.1), whether its commands open a proof
obligation, and where it is specified. Which of a class's commands are
its kinds — the `kind` enum of its construct (PLUGIN_SYSTEM §3) — is its
own document's. `Session` and `Theory`, the two classes that carry the
forest's structure, are the framework's (SESSION_AND_THEORY.md) and not
the plugin's.

A **proof obligation** is a goal Isabelle must see proved before the
command takes effect: a `lemma`'s statement, a `typedef`'s non-emptiness,
an `instance`'s class axioms. The tree holds no proof (ARCHITECTURE
§2.1): a class whose commands open one discharges it the way `Theorem`
does — a construction job finds the proof, an evaluation job checks it,
emission writes `by aoa` or `sorry` (CONSTRUCT_INTERACTION §3) — through
`Proof_Obligation`, for the classes COMMON.md §3 names; how exactly
each class discharges its own is its own document's. What every class
of the plugin shares besides — its base `Theory_Member`, the `english`
field and its `text` line, the `$defs` merged across classes — is
COMMON.md.

## 1. The classes

| class | commands | base | proof obligation | specified in |
| --- | --- | --- | --- | --- |
| `Section` | `chapter`, `section`, `subsection`, `subsubsection`, `paragraph`, `subparagraph` | `StdBlock`, beginning only | none | not yet; its nesting is ARCHITECTURE §2.0, its id properties MCP_SPECIFICATION §2.1 |
| `Text` | `text` | `Leaf` | none | not yet |
| `Locale` | `locale` | `StdBlock`, beginning and ending | none | not yet; its id properties are open (MCP_SPECIFICATION §6) |
| `Context` | `context` | `StdBlock`, beginning and ending | none | not yet; its id properties are open (MCP_SPECIFICATION §6) |
| `LiftingContext` | `context includes t.lifting … begin … end`, which opens the Lifting setup of one or more types again; its ending emits `lifting_update` and `lifting_forget` for each type it opened | `StdBlock`, beginning and ending | none | LIFTING_CONTEXT.md |
| `TypeClass` | `class` | `StdBlock`, beginning and ending | none | not yet |
| `Instantiation` | `instantiation`, whose ending emits `instance`; whether a lone `instance` is a kind of it is decided with it | `StdBlock`, beginning and ending | the class axioms, on the ending | not yet |
| `Interpretation` | `interpretation`, `global_interpretation` | `Leaf` | the locale's assumptions | not yet |
| `Sublocale` | `sublocale` | `Leaf` | the locale's assumptions | not yet |
| `Datatype` | `datatype`, `codatatype` | `Leaf` | none | DATATYPE.md |
| `Record` | `record` | `Leaf` | none | RECORD.md |
| `Typedef` | `typedef`, which carves a new type out of a non-empty subset of an existing type, `Rep` and `Abs` mapping between the two | `Leaf` | the set is non-empty | TYPEDEF.md |
| `QuotientType` | `quotient_type` | `StdBlock`, beginning and ending | the relation is an equivalence, a partial equivalence under `partial`, on the beginning | QUOTIENT_TYPE.md |
| `LiftDefinition` | `lift_definition` | `Leaf` | the term respects the representation | LIFT_DEFINITION.md |
| `Define` | `definition`, `fun`, `function` with `termination`, the `form` recorded at evaluation | `Leaf` | pattern completeness and termination, under `function` | DEFINE.md |
| `Abbreviation` | `abbreviation` | `Leaf` | none | not yet |
| `TypeSynonym` | `type_synonym` | `Leaf` | none | not yet |
| `Inductive` | `inductive`, `coinductive`, `inductive_set`, `coinductive_set` | `Leaf` | none | not yet |
| `Theorem` | `lemma`, `theorem`, `corollary`, `proposition` | `Leaf` | the statement | THEOREM.md |
| `Lemmas` | `lemmas` | `Leaf` | none | not yet |
| `Notation` | `notation`; `type_notation` and the `no_` forms, decided with it | `Leaf` | none | not yet |

## 2. Decided with a class

Commands no row covers whose fate is settled when the named class is
designed: `text_raw` with `Text`; `termination`, which `Define` emits
(ARCHITECTURE §2.2); `setup_lifting`, which `Typedef` emits
(TYPEDEF.md §5); and `lifting_update` and `lifting_forget`, which
`QuotientType`'s ending emits (QUOTIENT_TYPE.md §5) and
`LiftingContext`'s (LIFTING_CONTEXT.md §5).

## 3. Not in the plugin

Every command inside a proof, since a tree holds no proof (ARCHITECTURE
§2.1), and these commands of Pure and HOL up to `Main`:

- **Declarations without a definition**: `axiomatization`, `typedecl`,
  `consts`. An agent is given no way to add an axiom.
- **`declare`**: it has no name to make an id component from.
- **Covered by a class's own choice**: `primrec`, `primcorec`,
  `partial_function` — `Define` chooses the defining command itself.
- **Derived facts**: `inductive_cases`, `inductive_simps`, `fun_cases` —
  what they derive, a `Theorem` states.
- **For experiment or inside proofs**: `txt`, `experiment`, `notepad`,
  `schematic_goal`.
- **Of narrower use**: `subclass`, `overloading`, `specification`,
  `bundle`, `open_bundle`, `unbundle`, `named_theorems`,
  `adhoc_overloading`, `no_adhoc_overloading`, `alias`, `type_alias`,
  `hide_class`, `hide_type`, `hide_const`, `hide_fact`, `default_sort`,
  `judgment`.
- **Isabelle's own machinery**: `bnf`, `lift_bnf`, `copy_bnf`, `functor`,
  `free_constructors`, `datatype_compat`, `old_rep_datatype`,
  `primcorecursive`, `quotient_definition`, `syntax`, `no_syntax`,
  `translations`, `no_translations`, `syntax_consts`, `syntax_types`,
  `nonterminal`, `realizers`, `realizability`, `extract`, `extract_type`.
- **Code generation**: `export_code`, `code_datatype`, `code_printing`,
  `code_identifier`, `code_reserved`, `code_monad`, `code_reflect`,
  `code_pred`, `quickcheck_generator`.
- **Tool parameters**: `quickcheck_params`, `nitpick_params`,
  `nunchaku_params`, `sledgehammer_params`.
- **ML and files**: `ML`, `ML_file` and its variants, `setup`,
  `local_setup`, `attribute_setup`, `method_setup`, `declaration`,
  `syntax_declaration`, `simproc_setup`, `oracle`, the translation
  commands, `SML_file` and its variants, `SML_import`, `SML_export`,
  `ML_export`, `external_file`, `bibtex_file`, `ROOTS_file`,
  `generate_file`. A tree is declarations, not a program.
- **Diagnostics**: the `print_` commands, `find_theorems`, `find_consts`,
  `thm`, `term`, `typ`, `prop`, `value`, `values`, `nitpick`, `nunchaku`,
  `quickcheck`, `sledgehammer`, `try`, `try0`, `solve_direct`,
  `smt_status`, `unused_thms`. They change no theory; what some of them
  answer may one day be the `query` tool's (MCP_SPECIFICATION §1).
