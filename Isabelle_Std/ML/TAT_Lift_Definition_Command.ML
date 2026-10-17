(*  Title:      Isabelle_Std/ML/TAT_Lift_Definition_Command.ML

The `lift_definition` command as the plugin's `LiftDefinition` runs it
(isabelle_theory_agent/std/lift_definition.py; docs/node_classes/LIFT_DEFINITION.md
§6), its two refusals at the open goal rendered: the class's sentence naming the
Lifting setups the refused definition needs, found by the search `needed`, or
Isabelle's own rendering, the command parser's, carried here because
Lifting_Def_Code_Dt keeps it private.  On HOL alone, so that a raw ML process on
HOL evaluates the file and the tests pin the search, the sentence and the refusals
(test/test_lift_definition.py).
*)

signature TAT_LIFT_DEFINITION_COMMAND =
sig
  val needed : Proof.context -> typ * typ -> string list list option
    (*on a refused definition -- the term's type and the type read, in the
      context the command reads the term in --, the smallest sets of Lifting
      setups whose opening makes Lifting accept it: each a sublist of the type
      constructors of the type read whose setup is closed here and reopenable,
      in the order of their first occurrence, the sets in that order compared
      type by type; NONE when no set does*)
  val sentence : Proof.context -> typ -> string list list -> string
    (*the class's sentence on the type read for the sets `needed` answers*)
  val lift_def_cmd_with_err_handling :
    string list * (binding * string option * mixfix) * string -> local_theory -> Proof.state
    (*Lifting_Def_Code_Dt.lift_def_cmd on the options, the function with its
      type and its mixfix annotation, and the term, with no parametricity
      theorem; a QUOT_THM or a CHECK_RTY at the open goal is an error: the
      sentence when `needed` answers, Isabelle's rendering otherwise*)
end

structure TAT_Lift_Definition_Command : TAT_LIFT_DEFINITION_COMMAND =
struct

(* the search *)

(*the type constructors of a type in the order of their first occurrence*)
fun constructors T = rev (Term.fold_subtypes (fn Type (c, _) => insert (op =) c | _ => I) T [])

(*every Lifting setup `lifting_restore` can reopen, under its abstract type's constructor*)
fun reopenable ctxt =
  Symtab.fold (fn (_, {quotient, ...} : Lifting_Info.restore_data) =>
      Symtab.update (Lifting_Util.Tname (snd (Lifting_Util.quot_thm_rty_qty (#quot_thm quotient))), quotient))
    (Lifting_Info.get_restore_data ctxt) Symtab.empty

(*the type constructors on the way from the root to the first place where two
  types differ, both sides included; NONE when the types are equal*)
fun difference (Type (a, Ts), Type (b, Us)) =
      if a = b then Option.map (cons a) (get_first difference (Ts ~~ Us)) else SOME [a, b]
  | difference (T, U) = if T = U then NONE else SOME (map_filter (try dest_Type_name) [T, U])

(*a CHECK_RTY read: each type variable of the term's type with the types its
  occurrences received in the type Lifting forced, each occurrence renamed apart
  and matched; NONE when the match fails on a constructor of the term's type*)
fun occurrences thy (rty_schematic, rty_forced) =
  let
    fun split (Type (a, Ts)) occs = fold_map split Ts occs |>> (fn Us => Type (a, Us))
      | split A occs = let val V = TVar (("'occ", length occs), []) in (V, occs @ [(A, V)]) end
    val (split_rty, occs) = split rty_schematic []
  in
    try (Sign.typ_match thy (split_rty, rty_forced)) Vartab.empty
    |> Option.map (fn env =>
        AList.group (op =) (map (apsnd (Envir.subst_type env)) occs))
  end

fun needed ctxt (rty, qty) =
  let
    val thy = Proof_Context.theory_of ctxt
    val reopenable = reopenable ctxt
    val candidates =
      filter (fn c => Symtab.defined reopenable c andalso is_none (Lifting_Info.lookup_quotients ctxt c))
        (constructors qty)
    val set_ord = list_ord int_ord o apply2 (map (fn c => find_index (fn d => d = c) candidates))
    fun extend s c = filter (member (op =) (c :: s)) candidates
    (*one verdict of Lifting with `opened` opened: NONE when it accepts, else the
      unopened candidates its refusal names (§6)*)
    fun verdict opened =
      let
        val ctxt' =
          fold (Context.proof_map o Lifting_Setup.lifting_restore o the o Symtab.lookup reopenable)
            opened ctxt
        val closed = subtract (op =) opened candidates
        fun of_variable (A, Us) =
          (case (case A of TFree _ => A :: Us | _ => Us) of
            U :: Vs =>
              (case map_filter (fn V => difference (U, V)) Vs of
                [] =>
                  (case A of
                    TVar (_, S) =>
                      if Sign.of_sort thy (U, S) then [] else [inter (op =) (constructors U) closed]
                  | _ => [])
              | paths => map (fn path => inter (op =) path closed) paths)
          | [] => [])
        fun of_check_rty rtys =
          (case occurrences thy rtys of
            NONE => []
          | SOME variables =>
              (case maps of_variable variables of
                [] => closed
              | sets => hd (sort (int_ord o apply2 length) sets)))
      in
        (Lifting_Term.prove_quot_thm ctxt' (rty, qty); NONE)
        handle Lifting_Term.QUOT_THM (Type (r, _), Type (q, _), _) =>
            SOME (if r = q then closed else filter (fn c => c = q) closed)
          | Lifting_Term.QUOT_THM _ => SOME closed
          | Lifting_Term.CHECK_RTY rtys => SOME (of_check_rty rtys)
      end
    fun level [] = NONE
      | level sets =
          let val verdicts = map (fn s => (s, verdict s)) sets in
            (case map_filter (fn (s, NONE) => SOME s | _ => NONE) verdicts of
              [] =>
                level (sort_distinct set_ord (maps (fn (s, named) => map (extend s) (these named)) verdicts))
            | accepted => SOME accepted)
          end
  in level [[]] end


(* the sentence *)

(*the first subtype of T whose constructor is c*)
fun first_occurrence T c =
  the (Term.fold_subtypes
    (fn (U as Type (d, _)) => (fn NONE => if d = c then SOME U else NONE | found => found) | _ => I) T NONE)

fun quoted text = "`" ^ text ^ "`"

(*the command that defines the type, when the type is a node's -- declared in
  a theory Thy_Info does not hold, the heap's theories and every import loaded
  from source being Thy_Info's --: quotient_type, which fills Typedef's table
  too, or else typedef; NONE otherwise*)
fun defining ctxt c =
  if Thy_Info.defined_theory (Name_Space.theory_name {long = true} (Proof_Context.type_space ctxt) c)
  then NONE
  else if is_some (Quotient_Info.lookup_quotients ctxt c) then SOME "quotient_type"
  else if not (null (Typedef.get_info ctxt c)) then SOME "typedef"
  else NONE

fun sentence ctxt qty sets =
  let
    val type_name = quoted o Syntax.string_of_typ ctxt o first_occurrence qty
    val constructor = quoted o Proof_Context.extern_type ctxt
    val lifting =
      (case map (space_implode " and of " o map type_name) sets of
        [one] => one
      | several => space_implode ", or that of " several ^ ",")
    val node =
      (case sets of
        [[c]] =>
          (case defining ctxt c of
            SOME command => "the " ^ command ^ " that defines " ^ constructor c ^ ", or under "
          | NONE => "")
      | _ => "")
    val opening = space_implode ", or one opening " (map (space_implode " and " o map constructor) sets)
  in
    "The lifting of " ^ lifting ^ " is not open here. Place this lift_definition under " ^ node ^
    "a lifting_context opening " ^ opening ^ "."
  end


(* the refusals rendered *)

(*the two renderers of the command's parser, verbatim from lifting_def_code_dt.ML
  (quot_thm_err, check_rty_err): Lifting_Def_Code_Dt does not export them*)
fun quot_thm_err ctxt (rty, qty) pretty_msg =
  let
    val error_msg = cat_lines
       ["Lifting failed for the following types:",
        Pretty.string_of (Pretty.block
         [Pretty.str "Raw type:", Pretty.brk 2, Syntax.pretty_typ ctxt rty]),
        Pretty.string_of (Pretty.block
         [Pretty.str "Abstract type:", Pretty.brk 2, Syntax.pretty_typ ctxt qty]),
        "",
        (Pretty.string_of (Pretty.block
         [Pretty.str "Reason:", Pretty.brk 2, pretty_msg]))]
  in
    error error_msg
  end

fun check_rty_err ctxt (rty_schematic, rty_forced) (raw_var, rhs_raw) =
  let
    val (_, ctxt') = Proof_Context.read_var raw_var ctxt
    val rhs = Syntax.read_term ctxt' rhs_raw
    val error_msg = cat_lines
       ["Lifting failed for the following term:",
        Pretty.string_of (Pretty.block
         [Pretty.str "Term:", Pretty.brk 2, Syntax.pretty_term ctxt rhs]),
        Pretty.string_of (Pretty.block
         [Pretty.str "Type:", Pretty.brk 2, Syntax.pretty_typ ctxt rty_schematic]),
        "",
        (Pretty.string_of (Pretty.block
         [Pretty.str "Reason:",
          Pretty.brk 2,
          Pretty.str "The type of the term cannot be instantiated to",
          Pretty.brk 1,
          Pretty.quote (Syntax.pretty_typ ctxt rty_forced),
          Pretty.str "."]))]
    in
      error error_msg
    end

(*the parser's lift_def_cmd_with_err_handling with the class's sentence first:
  the function with its type and the term read as the command reads them, the
  search in the context the reading gives -- where the command's own
  prove_quot_thm runs --, on the term's type and the type read*)
fun lift_def_cmd_with_err_handling (options, raw_var, rhs_raw) lthy =
  let
    fun rendered isabelle_rendering =
      let
        val ((_, qty, _), lthy1) = Proof_Context.read_var raw_var lthy
        val rhs = Syntax.read_term lthy1 rhs_raw
      in
        (case needed lthy1 (fastype_of rhs, the qty) of
          SOME sets => error (sentence lthy1 (the qty) sets)
        | NONE => isabelle_rendering ())
      end
  in
    (Lifting_Def_Code_Dt.lift_def_cmd (options, raw_var, rhs_raw, []) lthy
      handle Lifting_Term.QUOT_THM (rty, qty, msg) => rendered (fn () => quot_thm_err lthy (rty, qty) msg))
      handle Lifting_Term.CHECK_RTY (rty_schematic, rty_forced) =>
        rendered (fn () => check_rty_err lthy (rty_schematic, rty_forced) (raw_var, rhs_raw))
  end

end
