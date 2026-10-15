# The `Typedef` design: edits it asks of the other documents

Status: proposed 2026-10-13 with docs/node_classes/TYPEDEF.md, revised
after two reviews (2026-10-14). §4's edits of MODULE_STRUCTURE,
PLUGIN_SYSTEM, SESSION_AND_THEORY, ARCHITECTURE and RENDER_BASELINES
were applied on 2026-10-14 by this session, on the owner's word, the
compilation session that owned them having ended. §1–§3 were applied
the same day by the design session [4aa7ce] to INDEX.md, COMMON.md,
DATATYPE.md and THEOREM.md (DOC_SYNC_LIST entry 66), which also wrote
the implementation step §4 asks for as step 7 of
NODE_CLASS_IMPLEMENTATION_PLAN.md §2 (the builder named `register`;
`print_name(text, spelling)`; `TAT_Mixfix.ML` and
`type_parameters_text` land with Datatype, step 8) and owns
COMPILATION.md from that day — its §3 sentences on `print_name` and
`keywords` hold under the generalisation, so no edit there. Committed
2026-10-14 (01e915f). The review of plan steps 7 and 8
(ai-artifacts/review/STEPS_7_8_REVIEW.md, 2026-10-14) and the owner's
answers to it (ai-artifacts/review/DOC_SYNC_LIST.md, entry 70) then
settled: the writers take no `spelling` — every writer writes
`unicode`, and the compile's conversion of the file gives it its
`\<name>` form (every ML call still sends `ascii`); a mixfix annotation
is read by Isabelle's own `Parse.mixfix` from the text `mixfix_text`
writes, inside the local theory's function, which is all
`TAT_Mixfix.ML` keeps; `recall` is written against no keyword. Where
this list says otherwise (§2's writers and decoding, §3's `print_name`
and decoding, §4's `print_name` bullet and decoding), those decisions
supersede it; TYPEDEF.md follows them.

## 1. node_classes/INDEX.md

- The `Typedef` row's last column: `TYPEDEF.md`.
- §2 "Decided with a class": drop `setup_lifting`, `lifting_forget`
  and `lifting_update` from the sentence; add `setup_lifting`, which
  `Typedef` emits (TYPEDEF.md §5), beside `termination`, which `Define`
  emits.
- §3 "Not in the plugin", the group "Of narrower use": add
  `lifting_forget` and `lifting_update` — they delete a type's lifting
  setup and transfer rules to hide a library type's construction, which
  an agent's theory has no use for, and after them a later theory's
  `lift_definition` on the type needs `including t.lifting`.

## 2. node_classes/COMMON.md

§3 `Proof_Obligation`:

- :12-13, "its ML half `Isabelle_Std/ML/TAT_Proof_Obligation.ML`" → its
  ML halves `Isabelle_Std/ML/TAT_Proof_Obligation.ML` (§3),
  `TAT_Mixfix.ML` and `TAT_Overloaded.ML` (§4).
- The shape sentence, "a `Leaf` whose one command opens exactly one
  goal, admitted as the operation's last transition" → the goal is
  admitted, and the class's `after_admission` step follows the admission
  in the same operation into the resulting slot (`Typedef`'s tries
  `setup_lifting` and keeps the admitted state when Isabelle refuses it,
  TYPEDEF.md §6; `Theorem`'s is the identity).
- The contract, :138-146 and the sentences after them, as TYPEDEF.md §6
  states it. The class gives two steps: `open_goal : Toplevel.state ->
  (Toplevel.state * 'a) option * string list` — a state with the
  class's record and no message, or no state and at least one message,
  `operation`'s rule — and `after_admission : Toplevel.state ->
  Toplevel.state * 'b`, total. Every transition of a step runs through
  `apply_transition` (MODULE_STRUCTURE §2.4); an interrupt, and a Bug
  from the step's own code, propagate. `TAT_Proof_Obligation` builds
  each class's evaluation callback from its name, its message unpacker,
  its two steps as functions of the message, and the packer of its two
  records: the arguments are the input slot, `goal_state`, the resulting
  slot and the message; `on_interrupt` is `Reraise`, `timeout` `NONE`;
  the run is `open_goal` under the generalised `operation` into
  `goal_state`, then `sorry`'s half, `Toplevel.end_proof
  Proof.global_skip_proof`, and `after_admission` as one operation into
  the resulting slot; a failure anywhere empties `goal_state`; the
  answer is `(messages, (a, b) option)`, on the wire `[[msgs], nil]` or
  `[[], [a, b]]`. A class registers through the builder (its name is the
  author's, not `evaluation_callback`, the Python attribute);
  `evaluate` is private. So the steps cannot touch a slot and every
  class answers one shape.
- The Python half: `_eval_opr` reads the messages and the pair; messages
  give `CannotEvaluate(messages)`; otherwise it returns
  `Ready(self.record_from_evaluation(what))`. A member beside
  `evaluation_callback` and `message()`: `record_from_evaluation(what)`
  records what the two steps yielded and answers the tuple of `IsaTerm`
  messages the `Ready` carries; the default records nothing and answers
  `()`; `Typedef`'s sets `overloaded` and `lifting` and answers its
  notice exactly when it sets `lifting` to false (TYPEDEF.md §6). "Ready
  with no messages otherwise" → `Ready` with what the member answers.
- :342-345, "What stays the class's: its command's transition and what
  the agent authors; …" → its two steps, `open_goal` and
  `after_admission`; `record_from_evaluation` and the recorded fields it
  sets; what the agent authors; `evaluation_callback`, the name of its
  callback; `message()`; `goal_structure()`; `valid_word` and
  `invalid_word`; and its own `print_fields`.
- `Theorem` on the contract: `open_goal` the `lemma` transition and the
  undeclared-variable check, yielding `()`; `after_admission` the
  identity; its callback built by the base. THEOREM.md §6 :191-199 and
  :214-218 follow (told to [4aa7ce] with the rest; the code is
  [9ffa3c]'s).
- "`Typedef`, `QuotientType`, … are expected to [derive from it], each
  confirming it in its own document" → `Typedef` confirmed (TYPEDEF.md).
- The mark's words: `valid definition` and `invalid definition` are now
  `Typedef`'s (the sentence already names them for "a class that
  defines").
- The `goal_structure()` clause "the names the command binds in the
  context count" → what decides the goal: its term, the assumptions of
  the context, and the names that bind a fact a stored proof may cite —
  THEOREM.md §4's criterion. `Typedef`'s is `type_parameters` and `set`
  (TYPEDEF.md §4).

§4 Shared `$defs`:

- The table: `MIXFIX_DEFS` keeps `Mixfix` alone; a new
  `TYPE_MIXFIX_DEFS` holds `TypeMixfix`, used by `Typedef` and by
  `Datatype`'s `types[].syntax` (§3 below). A class's `$defs` spreads
  only the definitions its schema reaches.
- The sentence "`TypeSynonym`'s and `QuotientType`'s parameters … and a
  type's own syntax, which takes no binder, are decided with those
  classes" → the type's syntax is `TypeMixfix` (TYPEDEF.md §3's
  descriptions); the parameters' sentence stays.
- `TypeMixfix`'s schema, after `Mixfix`'s: the same two arms as
  `Mixfix`'s infix and general arms, no binder arm — a type's mixfix
  refuses a binder (`Bad mixfix declaration`, mixfix.ML
  `syn_ext_types`) — with these descriptions, pinned here alone (the
  owner's texts of 2026-10-13): the union `Isabelle's mixfix annotation
  for a type`; the infix arm `an infix type constructor. Example:
  (infixr "+" 10)`; the general arm `a template with one _ per type
  parameter. Example: ("_⇩⊥" [21] 21)`; the general arm's
  `argument_priorities` and `priority` as `Mixfix`'s. Whether the
  template has one `_` per parameter is Isabelle's business at
  evaluation. `mixfix_text` writes both unions.
- No new writer for a piece of Isabelle text. The theory's `print_name`
  (SESSION_AND_THEORY §2) takes any piece — a name, a term, a type, a
  sort — and writes it bare when its `ascii` is an Isabelle identifier
  (`Isabelle_RPC_Host.unicode.is_identifier`, the grammar §5 already
  uses) that is not in the theory's `keywords`, as Isabelle's string
  token (COMPILATION §3) otherwise: `Token.print_name`'s rule for an
  identifier, which was its rule for a name already (the owner's ruling
  of 2026-10-14). `UNIV`,
  `zero`, `α`, `x⇩1` bare; `{xs. distinct xs}`, `'a ⇒ 'b`, `0.5` and
  the keyword `open` quoted. The test is made on `ascii`, the piece
  written in the spelling asked for; `keywords` still `None` means no
  keyword is known, so `recall` may use it before a header has run (§4
  below). `type_parameters_text(theory, parameters, spelling)` writes a
  sort through it; `mixfix_text` is untouched, a mixfix template being a
  string token by Isabelle's grammar.
- :386-388, "the two `InvalidField` sentences DATATYPE.md §4 pins" → the
  two sentences, in a fenced block here (DATATYPE.md §4's two lines),
  pinned by test_common.py; :389 the signature with the theory; :393 the
  example `('a :: linorder, 'b)`; :440-442, "The writers take the
  spelling alone and never `print_name`: a type variable is written
  bare, a sort, a symbol and a template in double quotes" →
  `type_parameters_text` writes a type variable bare and a sort through
  the theory's `print_name`; `mixfix_text` takes the spelling alone and
  writes its symbol or template as a string token.
- :364-368, "Each class's document lists every description its schema
  carries, the shared ones included (§5); a test of the plugin pins the
  schema text below against `common.py`'s constants" → the shared
  descriptions are pinned here alone (§5 below); a class document lists
  its own.
- "Its ML decoding stays in `TAT_Datatype.ML` until a second class takes
  it" → the decoding of both unions is `Isabelle_Std/ML/TAT_Mixfix.ML`,
  structure `TAT_Mixfix`, one file of its own, loaded by
  `TAT_Isabelle_Std.thy` before the class files.
- Beside it, a second shared ML file: `Isabelle_Std/ML/TAT_Overloaded.ML`,
  structure `TAT_Overloaded`, `needed : theory -> string -> bool` —
  whether the type of that full name has open dependencies on overloaded
  definitions in the theory's definition table, `not (null (maps #2
  (Defs.get_deps (Theory.defs_of thy) (Defs.Type, name))))`, the check
  `typedef` makes when `(overloaded)` is not given (typedef.ML:152-155);
  it does not consult the configuration option `typedef_overloaded`.
  `Typedef` (TYPEDEF.md §6), `Record` (RECORD.md §6, on the extension
  type from `Record.get_extension`) and `QuotientType` decide their
  recorded `overloaded` with it, each after one run of its command with
  the option (the owner's ruling of 2026-10-14, shared with the Record
  design session [355583], which cites the helper by this name). A test
  pins both answers: `{x :: 'a::zero. x = 0}` true, `{n :: nat. n > 0}`
  false.

§5 Conventions:

- "`kind` and the class carry none [description]" → whether a field or
  the class carries a description is decided one by one; `kind` never
  does; `Typedef`'s class does (TYPEDEF.md §3).
- The convention that a class document copies the shared descriptions
  it uses → every shared sentence — a `$defs` description, a shared
  refusal sentence — has one home in COMMON.md and one test pin; a class
  document lists its own alone and names that home for the rest (the
  owner's ruling of 2026-10-13; TYPEDEF.md §3, §4 follow it). The home
  of the shared `$defs`' descriptions and refusals is §4;
  `NotInsideTheory`'s sentence stays in §1, where it is pinned and
  tested (the author's call, 2026-10-14).

## 3. node_classes/DATATYPE.md (the owner's word of 2026-10-13: the type classes take a type's syntax)

- §1/§2: `types[].syntax`, a `TypeMixfix`, optional, written after the
  type's name and before `=` (`datatype (dead 'e, 'a) sum_bot (infixr
  "+⇩⊥" 10) = …`, the parser's slot `parse_type_args_named_constrained
  -- Parse.binding -- Parse.opt_mixfix`); the "What the class does not
  take" clause on a type's mixfix dropped.
- §5: the type's syntax emitted after the name; §6: the `NoSyn` in the
  spec's type slot replaced by the decoded syntax, and the decoding of
  every syntax by `TAT_Mixfix`, not `TAT_Datatype.ML`; §8: printed with
  the type; §2's `$defs` spreads `TYPE_MIXFIX_DEFS` as well.
- §3: the copies of shared descriptions (`TypeParameter.sort`,
  `Mixfix` and its arms) leave for COMMON §4, under the convention
  above; §4's type-parameter refusal sentences likewise.
- §5: "a sort in double quotes after `::`" and "the argument's type in
  double quotes" → through the theory's `print_name` (COMMON §4; the
  owner's ruling of 2026-10-14: every emitted term, type and sort
  follows `Token.print_name`'s rule for an identifier); the mixfix
  pieces stay string
  tokens. §8: the argument types under `recall` through `print_name`
  likewise, with `unicode` as the spelling.
- Later, the same for `QuotientType` (the slot after the name) and
  `TypeSynonym` (the slot after the right-hand type, `Parse.opt_mixfix'`);
  `record` has none, so `Record` keeps `Notation`'s `type_notation`.

node_classes/THEOREM.md (told to [4aa7ce] with the above; its code is
[9ffa3c]'s):

- §5, "every term in double quotes" → through the theory's `print_name`:
  `fixes xs :: "'a"` quoted (a type variable is no identifier), a
  conclusion `True` bare, `"P x"` quoted.
- §6 :191-199, "The callback is one call of `TAT_Proof_Obligation.evaluate`
  with `Theorem`'s own function …" → the callback is built by
  `TAT_Proof_Obligation` from `Theorem`'s two steps: `open_goal`, the
  `lemma` transition and, on the open goal, the undeclared-variable
  check, yielding nothing; `after_admission`, the identity. :214-218,
  "A failure is `TAT_Proof_Obligation.evaluate`'s … `Theorem`'s function
  refuses" → the base's; `Theorem`'s `open_goal` refuses.

## 4. Framework documents

- MODULE_STRUCTURE §2.4 :144-151, `apply_transition`'s bullet: "a proof
  obligation's evaluation runs the class's own transition and then
  `sorry`'s half through it" → every transition of a class's two steps
  and `sorry`'s half — `Typedef`'s `typedef` with the option and its
  `setup_lifting` among them (TYPEDEF.md §6).
- MODULE_STRUCTURE §2.5 :289-296 and §3's `operation` row:
  `TAT_Common_Nodes.operation` is generalised to carry a value beside
  the state — `slot -> (unit -> (Toplevel.state * 'a) option * string
  list) -> string list * 'a option`, the same Bug, exception and
  interrupt rules — and today's `operation` is its `unit` case, so
  `Theory`'s two operations and `Datatype`'s are untouched.
- MODULE_STRUCTURE §3 :386-389, "after the plugin's shared half,
  `TAT_Proof_Obligation`" → after the plugin's shared structures,
  `TAT_Proof_Obligation`, `TAT_Mixfix` and `TAT_Overloaded`. The
  `Proof_Obligation` row: the contract of §2 above (the builder, the two
  steps, the one operation for `sorry`'s half and `after_admission`, the
  answer). The `Theorem` row: `TAT.Theorem.evaluate`, built by the base
  from the `lemma` transition with the undeclared-variable check and the
  identity. A `Typedef` row: `TAT.Typedef.evaluate`, built by the base
  from `open_goal` — the `typedef` transition with the option, then
  `TAT_Overloaded.needed` on the open goal's theory, yielding
  `overloaded` — and `after_admission` — the `setup_lifting` transition,
  kept when Isabelle accepts it, yielding `lifting` (TYPEDEF.md §6).
  §1 and §4.5: `Isabelle_Std/ML/TAT_Mixfix.ML` and `TAT_Overloaded.ML`;
  §4's `std/` line :427 gains typedef.py, `Typedef` (TYPEDEF.md).
- SESSION_AND_THEORY §2 :209-214, `print_name`: takes any piece of
  Isabelle text, not a name alone — bare when its `ascii` is an
  identifier (`is_identifier`) not in `keywords`, a string token
  otherwise; serves `recall` as well as emission, `keywords` `None`
  meaning no keyword is known, so "emission's alone" and the assertion
  in model.py go. PLUGIN_SYSTEM §2 :115 and :307 and COMPILATION §3
  :400, which let a class read the keywords through `print_name` alone,
  stand, now covering every piece (COMPILATION's sentence is the
  compilation session's to edit).
- ARCHITECTURE §1 :56, the gloss of a status value's messages,
  "Isabelle's output of a run" → Isabelle's output of a run, or a
  class's notice about it (TYPEDEF.md §6).
- NODE_CLASS_IMPLEMENTATION_PLAN.md §2: a new step before `Typedef`'s
  own, after step 2 (be6380c stays its record) — the generalised
  `operation`, the base's builder of a class's evaluation callback with
  the two steps and the answer, `record_from_evaluation`, `Theorem`'s
  move to the builder (TAT_Theorem.ML, theorem.py, test_theorem.py's
  pins), `print_name` generalised and `type_parameters_text` writing a
  sort through it, `TAT_Overloaded.ML` with its test. The Isabelle-backed
  cases of test_theorem.py (the std harness, four cases) and
  test_fork_job.py exercise the callback's wire answer end to end, so the
  answer's new shape shows up there first (the jobs session [9ffa3c],
  2026-10-14). Step 7: the Mixfix
  decoding to `TAT_Mixfix.ML`, and one function of common.py beside
  `mixfix_text` that writes a syntax into a message (the form, the
  symbol or template as `ascii`, the priorities as authored, a left-out
  value absent), read by `TAT_Mixfix`'s one unpacker, which fills
  Isabelle's defaults.
- PLUGIN_SYSTEM §5, one more check on a class (the owner's ruling of
  2026-10-14): every key of the class's `$defs` is reached by a `$ref`
  of the class's schema, directly or through other `$defs` entries;
  one that is not is a `CannotLoadPlugin` naming the class and the key.
  The agreement check already follows every `$ref` into `$defs`; it
  records the keys it reaches and compares them with the key set. The
  compilation session is told before the edit; the loader step of
  NODE_CLASS_IMPLEMENTATION_PLAN.md §2 (step 5) gains the check and a
  test with an unreached entry.
- MCP_SPECIFICATION §2: the computed-name examples gain nothing — a
  `Typedef`'s name is its `type_name`, one field.
- RENDER_BASELINES §2: the type name's grammar is checked by
  `Typedef.gen` too (the sentence names `Datatype.gen`).
- OPEN_QUESTIONS §1: unchanged; INDEX.md's last column carries it.

## 5. Facts the design rests on (verified 2026-10-13/14, Isabelle2025-2, AFP 2026-05-13)

- `typedef`'s grammar: `Parse_Spec.overloaded -- Parse.type_args_constrained
  -- Parse.binding -- Parse.opt_mixfix -- (= |-- Parse.term) --
  Scan.option (morphisms |-- binding -- binding)` (typedef.ML:331-339);
  the goal `∃x. x ∈ S` (`mk_inhabited`, :103-104), always one subgoal;
  the set bound to `?<type name>` (`goal_pat`, :210-211).
- `overloaded` is read once in typedef.ML, :155: `if null newT_deps
  orelse overloaded orelse Config.get lthy typedef_overloaded then ()
  else error …` ("Type definition with open dependencies, use typedef
  (overloaded) …"); the dependencies are registered either way
  (:146-150). Probed on the HOL heap (`isabelle ML_process`,
  2026-10-13): `typedef 'a zeroes = "{x :: 'a::zero. x = 0}"` is
  refused without the flag and accepted with it; `{xs :: 'a list.
  distinct xs}` and `{n :: nat. n > 0}` are accepted without;
  `"distinct"` is refused either way, `Not a set type: "'b list ⇒
  bool"` then `The error(s) above occurred in typedef "dlist"`.
- The one-run form rests on this: the check reads `Defs.get_deps` on the
  theory right after the registration at :146-150, inside the command
  that opens the goal (`prepare_typedef`, :229; the axiom is conditional
  on inhabitance, so it is added before the proof), and nothing is added
  to the type's entry before the goal state; so the helper read on the
  open goal's theory returns the `newT_deps` the check computed, and the
  state with the option is the state without it.
- `Typedef.make_morphisms name (SOME (Rep_dlist, Abs_dlist))` and
  `make_morphisms name NONE` give the same bindings — `dlist.Rep_dlist`,
  `dlist.Abs_dlist`, `dlist.type_definition_dlist` (probed).
- Of HOL's and the AFP's 135 `morphisms` clauses, 57 names are the
  default written out and 23 begin with `Rep_`/`Abs_` without being it
  (`Rep_Nat` for `nat`, all of that kind); refusing a given name that
  begins so (TYPEDEF.md §4) loses no usage.
- `setup_lifting type_definition_<t>` after a fresh typedef is refused
  for four causes, none of which touches the definition's validity;
  (A) and (B) probed (Isabelle2025-2 HOL heap; Isabelle2024 HOL-Library
  heap for `fmap`), (C) and (D) read from lifting_setup.ML: (C) a
  theory-level name `setup_lifting` declares is already taken —
  `cr_<t>` (:46) and `cr_<t>_def` (:51), `pcr_<t>` (:85),
  `Quotient_<t>` (:725); (D) `define_pcr_cr_eq`'s own error
  (:114-125, :163). (A) the representing type mentions a
  type constructor with a dead parameter and a hand-written `quot_map`
  of fewer premises than parameters — `('a, 'b) fmap` of
  HOL-Library.Finite_Map; by the sources also CryptHOL's `resumption`
  and `bset` — and `Lifting_Term.prove_param_quot_thm` lets a raw `THM`
  through (`exception THM 1 raised (line 2132 of "thm.ML"):
  dest_state`); (B) the Rep function's name is one of the fact names
  `setup_lifting` notes under the type's name — `domain`,
  `rep_transfer`, `left_unique`, `right_unique`, `left_total`,
  `right_total`, `bi_unique`, `bi_total`, `domain_par`,
  `domain_par_left_total`, `domain_eq`, `id_abs_transfer`, `pcr_cr_eq`
  — `Duplicate fact declaration "Main.t2.domain" vs. "Main.t2.domain"`.
  Ordinary sets, `UNIV` copies, type parameters, sorted parameters,
  function-space representations pass; a representing type without a
  relator (`'a itself`) passes with the warning `Generation of a
  parametrized correspondence relation failed`. `(overloaded)` and
  sorts play no part. `setup_lifting` must start from a fresh local
  theory, as a transition of its own: run on the typedef's own local
  theory it fails at `fold_Domainp_pcrel` for every parametrised type.
- Isa-Mini's `quote_space kws s` (translator/library/aux.ML:185) quotes
  `s` when it holds a character outside letters, digits, `_`, `'`, `.`,
  or is a command or keyword of the theory; AoA's printed terms and
  types go through it (`print_term`, `pretty_tm`).
- In a local theory the type and the two constants are global
  (`Local_Theory.background_theory_result`, :131-134, :145-150); free
  variables in the set are refused (:123-126); extra type variables
  too (:118-121); NEWS: "without introducing dependencies on parameters
  or assumptions".
- A type's mixfix takes `Infix`, `Infixl`, `Infixr`, `Mixfix`; a
  `Binder` is "Bad mixfix declaration" (mixfix.ML:195-211); the `_`
  count must equal the arity (:213-217).
- Usage, HOL 122 / AFP ~404 typedefs: `(overloaded)` 11% / 30%;
  explicit `morphisms` 35% / 29%, of which "custom Rep, default Abs"
  13 / 31; a type mixfix 8% / 3%; inside a locale or context 1 / ~19;
  `setup_lifting type_definition_<t>` in the same file 52% / 62%;
  `lifting_forget` in 21 of HOL's 33 theories with `setup_lifting`, 45
  of the AFP's 220; non-emptiness proofs 75–80% terminal one-liners,
  `..` on `UNIV` copies the commonest.
- Transfer rules live in `Item_Net`s (transfer.ML:80-86), so their
  number does not slow lookup linearly; HOL's sources declare ~530
  `[transfer_rule]`s.
- `Lifting_Setup.setup_by_typedef_thm : config -> thm -> local_theory ->
  binding * local_theory` and `Lifting_Setup.default_config = {notes =
  true}`, both exported (lifting_setup.ML:12, :17, :38); the command
  reads its theorem through `Attrib.eval_thms` (:742), whose lookup is
  `Proof_Context.get_fact` (attrib.ML:220-224), the same `retrieve` as
  `get_fact_single` (proof_context.ML:1088-1089), and its typedef branch
  passes `default_config` (:780).
- `Parse.embedded`, which term, type and sort read, is `cartouche ||
  string || short_ident || long_ident || sym_ident || term_var ||
  type_ident || type_var || number` (parse.ML:266-272); a bare `0.5`
  lexes as a `Float` token (token.ML:723), which none of them accepts,
  so `0.5` must be quoted. HOL's class `"open"` (Topological_Spaces.thy:16)
  is a Pure keyword (Pure.thy:10), so a sort `open` must be quoted.
  `Isabelle_RPC_Host.unicode.is_identifier` is Isabelle's identifier
  grammar over the `ascii` spelling (letter symbols and `\<^sub>`
  included), used by theorem.py:194 already.
- `apply_transition` (TAT_Framework.ML:533-537) re-raises the interrupt
  `Toplevel.command_errors` folds into `([], NONE)`; a step that ran
  `command_errors` itself would record a cancellation as a result.
