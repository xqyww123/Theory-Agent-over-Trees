# The `LiftDefinition` node class

Status: not yet designed; this file holds what is already decided
about it.

A `LiftDefinition` defines a function on a type made by `typedef` or
`quotient_type` from a function on the representation type —
`lift_definition f :: "τ" is "g"` — and opens a proof obligation, that
`g` respects the representation (INDEX.md). It is a `Leaf` of the
plugin `Isabelle_Std`, expected to derive from `Proof_Obligation`
(COMMON.md §3).

## 1. Decided ahead of the design

`lift_definition` first tries to prove the respectfulness by itself
(`try_prove_reflexivity`, `lifting_def.ML`) and always enters proof
mode: with the goal to prove when it failed, with no subgoal when it
succeeded (`Proof.theorem` over `the_list goal`,
`lifting_def_code_dt.ML`), which a hand-written theory closes with
`.`. How `Proof_Obligation` treats a goal with no subgoal is its open
question (COMMON.md §3), decided with the first of `LiftDefinition`,
`Interpretation` and `Sublocale` designed.
