(*  Title:      Isabelle_Std/ML/TAT_Theorem.ML

The ML half of the plugin's `Theorem` (isabelle_theory_agent/std/theorem.py;
docs/node_classes/THEOREM.md §6): the statement opened as the `lemma` command's
goal, with the undeclared-variable and unused-variable checks on it, and nothing
after the admission; the callback is built by `TAT_Proof_Obligation.register`
(COMMON.md §3), whose are also the admission, the proof construction and the
proof check.
*)

structure TAT_Theorem =
struct

datatype answer = datatype TAT_Framework.answer

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

(*the statement as the Python class sends it: the kind, the fact's name, the
  `for_any` variables with their types, the premises, the conclusion -- every
  term and type in its ascii*)
type statement =
  string * string * (string * string option) list * (string * string) list * string

val unpack_statement =
  unpackTuple5 (unpackString, unpackString,
    unpackList (unpackPair (unpackString, unpackOption unpackString)),
    unpackList (unpackPair (unpackString, unpackString)),
    unpackString)

(*the `lemma` command's own transition in its long form (Pure.thy's `theorem`);
  the kind names the transition alone, Isabelle's kind being Thm.theoremK for
  every one of the four commands*)
fun statement_transition ((kind, name, for_any, premises, conclusion) : statement) =
  Toplevel.make kind Position.none
  |> Toplevel.local_theory_to_proof' NONE NONE
      (Specification.theorem_cmd true Thm.theoremK NONE (K I) (Binding.name name, []) []
        [Element.Fixes (map (fn (v, T) => (Binding.name v, T, NoSyn)) for_any),
         Element.Assumes (map (fn (p, t) => ((Binding.name p, []), [(t, [])])) premises)]
        (Element.Shows [(Binding.empty_atts, [(conclusion, [])])]))

(*the free names of the open goal: in the goal and in the premises assumed
  beside it past the input state's context `ctxt0`*)
fun goal_frees ctxt0 st =
  let val {context, goal, ...} = Proof.goal (Toplevel.proof_of st)
      val props = Thm.prop_of goal :: map Thm.prop_of (Assumption.local_prems_of context ctxt0)
   in fold Term.add_free_names props [] end

(*§6's undeclared-variable check: the free names that `for_any` does not
  declare and the input state's context `ctxt0` does not fix (a `Locale`'s
  parameters inside its block, LOCALE.md §6), which Isabelle fixed by itself;
  sorted*)
fun undeclared for_any ctxt0 frees =
  sort_strings (filter_out (Variable.is_fixed ctxt0) (subtract (op =) (map #1 for_any) frees))

(*the unused-variable check (COMMON.md §4): the declared `names` not among the
  free names `frees`, in order*)
fun unused_in frees names = subtract (op =) frees names

(*names joined by `, ` with `last` before the final one, the twin of the
  framework's `exceptions.series` (LOCALE.md §6)*)
fun series _ [one] = one
  | series last names = String.concatWith ", " (take (length names - 1) names) ^ " " ^ last ^ " " ^ List.last names

fun quoted name = "`" ^ name ^ "`"

(*the head of an undeclared-variable sentence, `Theorem`'s and a `Locale`
  axiom's (§6; LOCALE.md §6): the variables, then the axioms they occur in
  when any are named, each list by `series`, the nouns in number*)
fun undeclared_head names axioms =
  "Undeclared variable" ^ (if length names = 1 then " " else "s ") ^ series "and" (map quoted names)
  ^ (if null axioms then ""
     else " in the axiom" ^ (if length axioms = 1 then " " else "s ") ^ series "and" (map quoted axioms))

(*`Theorem`'s one message on undeclared variables; no message when there is none*)
fun undeclared_sentence [] = []
  | undeclared_sentence names =
      [undeclared_head names [] ^
        (if length names = 1 then ": declare it in `for_any`." else ": declare them in `for_any`.")]

(*COMMON.md §4's one message on unused variables: each `for_any` list as its
  path and its unused names, in field order; a list with none left out; no
  message when none has one*)
fun unused_sentence groups =
  (case filter_out (null o #2) groups of
    [] => []
  | groups' =>
      let
        val clauses = groups' |> map_index (fn (i, (path, names)) =>
          (if i = 0 then "The" else "the") ^ " field `" ^ path ^ "` declares " ^ space_implode " " (map quoted names))
        val joined = (case split_last clauses of ([], one) => one | (front, last) => commas front ^ ", and " ^ last)
      in [joined ^ (if length (maps #2 groups') = 1 then ", but it is not used." else ", but they are not used.")] end)

(*`Theorem`'s `open_goal` (COMMON.md §3): the statement's transition from the
  input state to the state with the goal open, refused when a variable is
  undeclared or unused -- the undeclared-variable message first; yields
  nothing*)
fun open_goal (statement as (_, _, for_any, _, _) : statement) st =
  TAT_Framework.apply_transition (statement_transition statement) st
  |> TAT_Framework.bind_answer (fn st' =>
      let
        val ctxt0 = Toplevel.context_of st
        val frees = goal_frees ctxt0 st'
        val messages =
          undeclared_sentence (undeclared for_any ctxt0 frees) @
          unused_sentence [("statement.for_any", unused_in frees (map #1 for_any))]
      in if null messages then Accepted (st', ()) else Refused messages end)

(*`after_admission` the identity, `Accepted` with the state and nothing*)
val _ = Theory.setup (TAT_Proof_Obligation.register
  {name = "TAT.Theorem.evaluate",
   message = unpack_statement,
   open_goal = open_goal,
   after_admission = K (fn st => Accepted (st, ())),
   records = packPair (packUnit, packUnit)})

end

end
