(*  Title:      Isabelle_Std/ML/TAT_Theorem.ML

The ML half of the plugin's `Theorem` (isabelle_theory_agent/std/theorem.py;
docs/node_classes/THEOREM.md §6): the statement opened and admitted, never a
proof.  The jobs' callbacks are step 15's.
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

(*the half of `sorry` that ends a toplevel goal (Isar_Cmd.global_skip_proof)*)
val admit_transition =
  Toplevel.make "sorry" Position.none |> Toplevel.end_proof Proof.global_skip_proof

(*the statement's names Isabelle would quote in this theory
  (Thy_Header.print_name): the fact's, each variable's, each premise's*)
fun reserved thy ((_, name, for_any, premises, _) : statement) =
  filter (fn n => Thy_Header.print_name thy n <> n) (name :: map #1 for_any @ map #1 premises)

(*the two transitions in turn from the input slot's state: the goal, open and
  no step taken, into `goal_state`; the admitted fact into the resulting slot.
  A failure of either is the statement's: `goal_state` emptied -- a rerun of a
  `ready` node releases nothing, so an earlier run's goal would stand there --
  the resulting slot left to the framework, the messages answered.*)
val _ = Theory.setup (TAT_Framework.register_callback {python_packages = []} (fn env =>
  {name = "TAT.Theorem.evaluate",
    on_interrupt = Remote_Procedure_Calling.Reraise,
    arg_schema = unpackTuple4 (#slot_unpacker env, #slot_unpacker env, #slot_unpacker env,
                               unpack_statement),
    ret_schema = packTuple3 (packBool, packList packString, packList packString),
    function = fn (input, goal, result, statement) =>
      let
        val st = #get input ()
        val errors =
          TAT_Common_Nodes.operation goal (fn () =>
            TAT_Framework.apply_transition (statement_transition statement) st)
        val errors =
          if null errors
          then TAT_Common_Nodes.operation result (fn () =>
                 TAT_Framework.apply_transition admit_transition (#get goal ()))
          else errors
      in
        if null errors
        then (true, [], reserved (Toplevel.theory_of (#get result ())) statement)
        else (#put goal NONE; (false, errors, []))
      end,
    timeout = NONE}))

end

end
