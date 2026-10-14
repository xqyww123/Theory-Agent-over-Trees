(*  Title:      Isabelle_Std/ML/TAT_Theorem.ML

The ML half of the plugin's `Theorem` (isabelle_theory_agent/std/theorem.py;
docs/node_classes/THEOREM.md §6): the statement opened as the `lemma` command's
goal, with the undeclared-variable check on it, and nothing after the admission;
the callback is built by `TAT_Proof_Obligation.register` (COMMON.md §3), whose
are also the admission, the proof construction and the proof check.
*)

structure TAT_Theorem =
struct

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

(*§6's check once the goal is open: the statement's free variables -- in the
  goal and in the premises assumed beside it -- that `for_any` does not
  declare, which Isabelle fixed by itself; sorted*)
fun undeclared ((_, _, for_any, _, _) : statement) st =
  let val {context, goal, ...} = Proof.goal (Toplevel.proof_of st)
      val props = Thm.prop_of goal :: map Thm.prop_of (Assumption.all_prems_of context)
      val frees = distinct (op =) (map #1 (fold Term.add_frees props []))
   in sort_strings (subtract (op =) (map #1 for_any) frees) end

fun undeclared_sentence names =
  let val quoted = map (fn n => "`" ^ n ^ "`") names
      val listed =
        (case quoted of
          [one] => one
        | _ => String.concatWith ", " (take (length quoted - 1) quoted) ^ " and " ^ List.last quoted)
   in if length names = 1
      then "Undeclared variable " ^ listed ^ ": declare it in `for_any`."
      else "Undeclared variables " ^ listed ^ ": declare them in `for_any`."
  end

(*`Theorem`'s `open_goal` (COMMON.md §3): the statement's transition from the
  input state to the state with the goal open, refused -- no state, one
  message -- when a variable is undeclared; yields nothing*)
fun open_goal statement st =
  (case TAT_Framework.apply_transition (statement_transition statement) st of
    (SOME st', []) =>
      (case undeclared statement st' of
        [] => (SOME (st', ()), [])
      | names => (NONE, [undeclared_sentence names]))
  | (_, messages) => (NONE, messages))

(*`after_admission` the identity, yielding nothing*)
val _ = Theory.setup (TAT_Proof_Obligation.register
  {name = "TAT.Theorem.evaluate",
   message = unpack_statement,
   open_goal = open_goal,
   after_admission = K (rpair ()),
   records = packPair (packUnit, packUnit)})

end

end
