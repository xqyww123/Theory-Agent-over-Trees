# The `parent_session` check: decisions and record (2026-09-29/30)

A record, not a design document. The design is SESSION_AND_THEORY.md §1
and §3 and MODULE_STRUCTURE.md §2.3, §4.1, §4.2; the decision line is
FIRST_END_TO_END_RUN_PLAN.md §4.

## 1. The owner's decisions

- 2026-09-29. `parent_session` is checked in `Session.gen`, at creation
  and amend, not at evaluation: a `Session` runs no operation and
  `parent_session` has no text Isabelle runs. It must name a `Session` of
  the forest or a session the Isabelle session layout knows; the Isabelle
  half is one ML callback, `TAT.is_known_session`, wrapping
  `Resources.check_session` over the full session structure the launcher
  hands Isabelle. Two sentences approved verbatim (SESSION_AND_THEORY §3):
  `The field \`parent_session\` must name an existing session; \`HOL-Libary\` is not one.`
  and `The field \`parent_session\` must not name the session itself.`
- 2026-09-30, after review 1. The node class contract changes so that
  every construct of an edit call knows the batch before it and what the
  call does: `NodeConfig` gains `batch_before: list[Node]` and
  `role: Insertion | Amendment` and loses `replacing`; `replaces()`
  derives the replacement (an amendment's `old` for the batch's first
  construct). A construct may name as parent a `Session` the call adds
  before it; one the call adds after it is not built yet. The leaving
  node of an amend is known to every construct of its list. Not checked:
  a parent deleted or renamed by a later call; two sessions each the
  other's parent.
- Names: `batch_before`, `role`, `Insertion`, `Amendment`, `replaces()`.
- 2026-09-30, after review 2. `batch_before` is a `tuple[Node, ...]`, not
  a list. The nodes in it keep the `parent` their `gen` was given; the
  framework does not clear it, and the contract says so instead
  (MODULE_STRUCTURE §4.1).

## 2. What landed

- `ML/TAT_Framework.ML`: `Loader.is_known_session`, the callback
  `TAT.is_known_session`.
- `isabelle_driver.is_known_session`.
- `model.py`: `Insertion`, `Amendment`, `Role`, `NodeConfig` as above;
  `Session.gen`'s check, last among its checks.
- `edit.py`: `Edit_Call.role` is the call's; `insert` and `amend` hand
  `_construct_siblings` the batch's role, a nested `children` batch is an
  `Insertion`; `_construct_siblings` builds the sibling table less the
  leaving node and hands each construct the batch before it;
  `_construct_element` builds the `NodeConfig` first and reads
  `replaces()`; `_leaving(role)` in `model.py` is the one reading of the
  leaving node.
- Tests: `test_session_theory.py` (the two sentences pinned from §3, a
  theory's name refused, the parent judged last; the same-call, reversed,
  amend-rename and amend-kept-name cases), `test_edit.py`
  (`test_gen_is_told_the_batch_before_it_and_the_batch_s_role`),
  `test_conversation.py` (`known_session` over the wire; the refusal
  through gen in the end-to-end case).
- Documents: SESSION_AND_THEORY §1, §3 and its status line;
  MODULE_STRUCTURE §2.3, §2.6, §4.1, §4.2, §4.3; FIRST_END_TO_END §2,
  §4; STEP5_HANDOFF's open list.

## 3. Review 1 (2026-09-29, the landed check before the contract change)

Workflow `wf_51e5e8bf-f9c`, six challengers, three defenders per finding,
one judge (Opus 5.5, xhigh); 55 agents. Verdict ACCEPT_WITH_FIXES,
re-review SINGLE_READER. Owner item gen-2 (the amend exception held only
for the batch's first construct, and read `replacing` for a third use):
resolved by the 2026-09-30 decision above, not by the judge's route.
Author items, all applied: elegance-3 (§1's "transcribed and nothing
else" sentence restored), documents-2 (STEP5_HANDOFF's open list),
documents-4 (the status line), tests-model-3 (a theory's name as parent),
gen-3 (the parent judged after the options). Rejected, not to re-raise:
the glossary row naming `check_session`; a reason on the same-call
refusal; recording the fake to pin forest-before-Isabelle order; the
plan's §4 wording.

## 4. Review 2 (2026-09-30, the contract change)

Workflow `wf_486157c5-a64`, the same recipe; 79 agents; material in
`review_parent_session/` (`BRIEF.md`, `diff.patch`, `ruling2.json`,
`material2.json`). Verdict ACCEPT_WITH_FIXES, re-review SINGLE_READER.
Owner items: tests-2 (`batch_before` a tuple) — adopted; contract-2-gate
(clearing batch nodes' `parent` pointers, and the amend's `on_inheriting`
gate receiving a detached replacement) — declined: the pointers stay,
the contract states what they are. Author items, all applied: contract-1
(the contract text: `replaces()` carries fields over, the leaving node is
`Amendment.old` for every construct; `Insertion` covers every `children`
batch; `role` per batch), contract-2 (the "no parent" wording, by the
owner's ruling above), elegance-2 (`Edit_Call.role`, the role handed
down, `_construct_siblings` building the sibling table, `_leaving`),
tests-1 (`CT` on `EVENTS`, `told()` read after the call), contract-5
(FIRST_END_TO_END §2's `from_store` sentence; §2's section list here),
ml-and-documents-4 ("keeps"). Rejected, not to re-raise: every batch of
an amend under `Amendment`; an `old` on `Insertion`; a test of the
`Session` filter at the root; folding the two option-name cases.

## 5. The single reader (2026-09-30)

Workflow `wf_46cf1aea-25b` (Opus 5.5, xhigh; `review_parent_session/reader.json`).
Every author item and both owner rulings verified applied, with a probe
of the contract's wording on six edit paths and eleven mutants, each
caught by the tests. One minor item, applied: this record named the
recording test by its old name. Fit to commit.
