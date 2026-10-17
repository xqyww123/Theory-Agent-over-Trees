(*  Title:      Isabelle_Std/ML/TAT_Lift_Definition.ML

The ML half of the plugin's `LiftDefinition` (isabelle_theory_agent/std/lift_definition.py;
docs/node_classes/LIFT_DEFINITION.md §6): the lifted function's definition as the
Python class sends it, run as the `lift_definition` command's transition through
TAT_Lift_Definition_Command, with the option `(code_dt)` when the class asks for it
and the admission, tried on the state the command reaches, accepts it; nothing after
the admission.  The callback is built by `TAT_Proof_Obligation.register` (COMMON.md
§3); the admission, the proof construction and the proof check are that structure's.
*)

structure TAT_Lift_Definition =
struct

datatype answer = datatype TAT_Framework.answer

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

(*the definition as the Python class sends it: the function's name; its mixfix
  annotation as `mixfix_text` writes it, none for none; `code_dt`; then the goal's
  part -- the type and the term -- every piece of Isabelle text in its ascii*)
type definition = string * string option * bool * string * string

val unpack_definition =
  unpackTuple5 (unpackString, unpackOption unpackString, unpackBool, unpackString, unpackString)

(*the command's own transition, what its parser hands its result to
  (lifting_def_code_dt.ML), under the options given; the annotation read under the
  local theory's keywords; the two refusals at the open goal rendered by
  TAT_Lift_Definition_Command*)
fun transition options (name, syntax, typ, is) =
  Toplevel.make "lift_definition" Position.none
  |> Toplevel.local_theory_to_proof NONE NONE (fn lthy =>
      TAT_Lift_Definition_Command.lift_def_cmd_with_err_handling
        (options, (Binding.name name, SOME typ, TAT_Mixfix.read lthy syntax), is) lthy)

(*`LiftDefinition`'s open_goal (COMMON.md §3): the transition from the input state
  to the state with the goal open, yielding with_code_dt.  With `code_dt` false, the
  command without the option, false.  With it true, the command with the option and,
  on the state it reaches, the admission as a trial, its state dropped: accepted,
  that state and true; refused, the command without the option and false, nothing
  said (§6).  A run with the option refused is the refusal, the option acting at
  the admission alone.*)
fun open_goal ((name, syntax, code_dt, typ, is) : definition) st =
  let
    val definition = (name, syntax, typ, is)
    fun without_option () =
      TAT_Framework.apply_transition (transition [] definition) st |> TAT_Framework.map_answer (rpair false)
  in
    if not code_dt then without_option ()
    else
      (case TAT_Framework.apply_transition (transition ["code_dt"] definition) st of
        Accepted st' =>
          (case TAT_Proof_Obligation.admit st' of
            Accepted _ => Accepted (st', true)
          | Refused _ => without_option ())
      | Refused messages => Refused messages)
  end

val _ = Theory.setup (TAT_Proof_Obligation.register
  {name = "TAT.LiftDefinition.evaluate",
   message = unpack_definition,
   open_goal = open_goal,
   after_admission = K (rpair ()),
   records = packPair (packBool, packUnit)})

end

end
