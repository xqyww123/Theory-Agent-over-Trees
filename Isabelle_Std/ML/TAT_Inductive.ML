(*  Title:      Isabelle_Std/ML/TAT_Inductive.ML

The ML half of the plugin's `Inductive` (isabelle_theory_agent/std/inductive.py;
docs/node_classes/INDUCTIVE.md §6): the rules parsed as the `inductive` command
parses them, the definition refused when a `for_any` variable is unused; the rules
read as the command reads them, the fixed parameters found on that reading -- or
the recorded ones taken -- with the notice's variables; and the definition made by
the command's own call, `Inductive.add_inductive_cmd`.
*)

structure TAT_Inductive =
struct

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

(*a rule as the Python class sends it: its name, its conclusion, its premises,
  its `for_any` variables each with its type or none -- every piece of Isabelle
  text in its ascii*)
type rule = string * string * string list * (string * string option) list

(*the definition: the kind, the constants as `Variable_With_Syntax`'s wire, the
  rules, and the recorded fixed parameters, or NONE for them to be decided
  (COMMON.md §5)*)
type definition =
  string * (string * string option * string option) list * rule list * string list option

val unpack_definition =
  unpackTuple4 (unpackString,
    unpackList (unpackTuple3 (unpackString, unpackOption unpackString, unpackOption unpackString)),
    unpackList (unpackTuple4 (unpackString, unpackString, unpackList unpackString,
      unpackList (unpackPair (unpackString, unpackOption unpackString)))),
    unpackOption (unpackList unpackString))

(*** the command's arguments (§6) ***)

type args =
  (binding * string option * mixfix) list * (binding * string option * mixfix) list *
  Specification.multi_specs_cmd

(*the first type a rule's `for_any` gives a parameter, or none*)
fun first_type (rules : rule list) p =
  get_first (fn (_, _, _, for_any) => get_first (fn (v, T) => if v = p then T else NONE) for_any) rules

(*`cnames_syn`, `pnames_syn` and `specs` for the parameters `params`: each rule's
  `for_any` less the parameters*)
fun args ctxt ((_, constants, rules, _) : definition) params : args =
  (TAT_Mixfix.fixes ctxt constants,
   map (fn p => (Binding.name p, first_type rules p, NoSyn)) params,
   map (fn (name, concl, prems, for_any) =>
     (((Binding.name name, []), concl), prems,
      map (fn (v, T) => (Binding.name v, T, NoSyn)) (filter_out (member (op =) params o #1) for_any)))
     rules)

(*** the parse and the unused-variable check (§6; COMMON.md §4) ***)

(*each rule parsed, never checked, where the command parses it (specification.ML,
  prep_specs): in the context read_multi_specs leaves for the constants and the
  parameters, the rule's own `for_any` fixed; its conclusion and its premises*)
fun parsed ctxt ((cnames_syn, pnames_syn, specs) : args) =
  let val vars_ctxt = #2 (Specification.read_multi_specs (cnames_syn @ pnames_syn) [] ctxt) in
    specs |> map (fn ((_, concl), prems, for_any) =>
      let val rule_ctxt = #2 (vars_ctxt |> fold_map Proof_Context.read_var for_any |-> Proof_Context.add_fixes)
      in (Syntax.parse_prop rule_ctxt concl, map (Syntax.parse_prop rule_ctxt) prems) end)
  end

(*COMMON.md §4's message on the `for_any` variables, as the rules write them, that
  are not free in their rule's parse*)
fun unused_message (rules : rule list) parses =
  TAT_Theorem.unused_sentence (map_index (fn (i, ((_, _, _, for_any), (concl, prems))) =>
    ("inductive_rules[" ^ string_of_int i ^ "].for_any",
     TAT_Theorem.unused_in (fold Term.add_free_names (concl :: prems) []) (map #1 for_any)))
    (rules ~~ parses))

(*** the detection (§6) ***)

(*the occurrences in `t` as check_prem' finds them (inductive.ML): a subterm
  headed by one of the predicates (`cs`) taken whole, any other walked through
  its Abs body and both sides of $*)
fun occurrences cs t =
  if member (op =) cs (head_of t) then [t]
  else
    (case t of
      Abs (_, _, b) => occurrences cs b
    | t $ u => occurrences cs t @ occurrences cs u
    | _ => [])

(*step 1 -- the rules read in the default mode, each closed over its own
  variables (specification.ML, close_form) -- then on that reading the run of
  leading common variables and the notice's variables.  Each rule is taken
  apart as check_rule takes it, its binders substituted as Frees of their own
  names, a binder repeating a name free in the rule or an earlier binder's
  renamed apart (Term.variant_bounds): a `\<And>` written inside a conclusion stays
  apart from the rule's variable of the same name, as check_rule keeps it.  A
  rule's variable is one of the Frees of the binders the closing added -- the
  leading ones, those the conclusion's text binds itself following, counted
  on its parse in `parses` --, never one the context fixes.  A position's
  common variable is the Free every occurrence of every predicate
  carries there, equal by name and typ; none at any position when some
  predicate has no occurrence.  The run: the leading positions whose common
  variables are all different, each a rule's variable or a parameter step 1
  fixed.  The notice, while some premise has an occurrence: each rule's
  variable not in the run that is a later position's common variable, in
  position order.  A read that fails raises, the definition's failure*)
fun detect ctxt ((cnames_syn, pnames_syn, specs) : args) parses =
  let
    val ((vars, intrs), _) = Specification.read_multi_specs (cnames_syn @ pnames_syn) specs ctxt
    val (cs, ps) = chop (length cnames_syn) (map (Free o apfst Binding.name_of o fst) vars)
    fun taken_apart ((_, rule), (concl_parse, _)) =
      let
        val params = Term.variant_bounds rule (Logic.strip_params rule)
        val own = length (Logic.strip_params (Type.strip_constraints concl_parse))
        val frees = rev (map Free params)
        val concl = subst_bounds (frees, Logic.strip_assums_concl rule)
        val prems = map (curry subst_bounds frees) (Logic.strip_assums_hyp rule)
      in (map Free (take (length params - own) params), occurrences cs concl, maps (occurrences cs) prems) end
    val rules = map taken_apart (intrs ~~ parses)   (*each its variables, its conclusion's occurrences, its premises'*)
    val occs = maps (fn (_, concl_occs, prem_occs) => concl_occs @ prem_occs) rules
    fun common i =
      (case map (fn t => try (nth (snd (strip_comb t))) i) occs of
        (x as SOME (Free _)) :: xs => if forall (fn y => y = x) xs then x else NONE
      | _ => NONE)
    val commons =
      if forall (fn c => exists (fn t => head_of t = c) occs) cs
      then map common (0 upto fold (Integer.max o length o snd o strip_comb) occs 0 - 1)
      else []
    fun rule_variable x = forall (fn (frees, _, _) => member (op =) frees x) rules
    fun leading run (SOME x :: rest) =
          if (rule_variable x orelse member (op =) ps x) andalso not (member (op =) run x)
          then leading (run @ [x]) rest else run
      | leading run _ = run
    val run = leading [] commons
    val notice =
      if forall (fn (_, _, prem_occs) => null prem_occs) rules then []
      else
        map_filter I (drop (length run) commons)
        |> filter (fn x => rule_variable x andalso not (member (op =) run x))
        |> distinct (op =)
  in (map (fst o dest_Free) run, map (fst o dest_Free) notice) end

(*** the evaluation (§6) ***)

(*step 2: the call the command's parser makes (inductive.ML, gen_ind_decl), the
  monotonicity lemmas none*)
fun definition_transition coind ((cnames_syn, pnames_syn, specs) : args) =
  Toplevel.make "inductive" Position.none
  |> Toplevel.local_theory NONE NONE (snd o Inductive.add_inductive_cmd true coind cnames_syn pnames_syn specs [])

(*from the input state to the state after the definition, with the parameters
  run and the notice's variables: the rules parsed under the recorded parameters,
  none under NONE, refused when a `for_any` variable is unused; step 1 and the
  detection, which counts on that parse; the parameters the recorded ones, or
  the run under NONE, never a switch; step 2 on the arguments for them*)
fun run (definition as (kind, _, rules, recorded) : definition) st =
  let
    val ctxt = Toplevel.context_of st
    val recorded_args = args ctxt definition (these recorded)
    val parses = parsed ctxt recorded_args
  in
    (case unused_message rules parses of
      [] =>
        let
          val (found, notice) = detect ctxt recorded_args parses
          val params = the_default found recorded
        in
          TAT_Framework.apply_transition (definition_transition (kind = "coinductive") (args ctxt definition params)) st
          |> TAT_Framework.map_answer (rpair (params, notice))
        end
    | messages => TAT_Framework.Refused messages)
  end

(*the callback: the input slot, the resulting slot and the definition; one
  operation into the resulting slot*)
val _ = Theory.setup (TAT_Framework.register_callback {python_packages = ["isabelle_theory_agent.std"]} (fn env =>
  {name = "TAT.Inductive.evaluate",
   on_interrupt = Remote_Procedure_Calling.Reraise,
   arg_schema = unpackTuple3 (#slot_unpacker env, #slot_unpacker env, unpack_definition),
   ret_schema = TAT_Framework.pack_answer (packPair (packList packString, packList packString)),
                                              (*the parameters run and the notice's variables*)
   function = fn (input, result, definition) =>
     TAT_Common_Nodes.operation' result (fn () => run definition (#get input ())),
   timeout = NONE}))

end

end
