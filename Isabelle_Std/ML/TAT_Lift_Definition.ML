(*  Title:      Isabelle_Std/ML/TAT_Lift_Definition.ML

The ML half of the plugin's `LiftDefinition` (isabelle_theory_agent/std/lift_definition.py;
docs/node_classes/LIFT_DEFINITION.md §6): the lifted function's definition as the
Python class sends it, run as the `lift_definition` command's transition through
TAT_Lift_Definition_Command, with the option `(code_dt)` decided by
TAT_Proof_Obligation.decide under the recorded-choice convention (COMMON.md §5): as
recorded; with nothing recorded, without it when `code_dt` is false, otherwise as
TAT_Lift_Definition_Command's verdict says, the trial -- the admission tried on the
probe's state -- only where it is undecided.  Nothing after the admission.  The
callback is built by `TAT_Proof_Obligation.register` (COMMON.md §3); the admission,
the proof construction and the proof check are that structure's.
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

(*the message: the definition and the recorded with_code_dt, NONE until an
  evaluation has recorded one (COMMON.md §5)*)
val unpack_message = unpackPair (unpack_definition, unpackOption unpackBool)

(*the command's own transition, what its parser hands its result to
  (lifting_def_code_dt.ML), with the option `(code_dt)` when with_code_dt; the
  annotation read under the local theory's keywords; the two refusals at the open
  goal rendered by TAT_Lift_Definition_Command*)
fun transition with_code_dt (name, syntax, typ, is) =
  Toplevel.make "lift_definition" Position.none
  |> Toplevel.local_theory_to_proof NONE NONE (fn lthy =>
      TAT_Lift_Definition_Command.lift_def_cmd_with_err_handling
        (if with_code_dt then ["code_dt"] else [], (Binding.name name, SOME typ, TAT_Mixfix.read lthy syntax), is)
        lthy)

(*`LiftDefinition`'s open_goal (COMMON.md §3): the transition from the input state
  to the state with the goal open, yielding with_code_dt, the option it ran with,
  decided by TAT_Proof_Obligation.decide (§6).  With nothing recorded, `decide` is
  given false, or none where `code_dt` is true and the verdict -- the type read under
  NoSyn, as under any mixfix annotation -- is undecided; `needed` is the admission
  tried on the probe's state, nothing said of its refusal.*)
fun open_goal ((name, syntax, code_dt, typ, is) : definition, with_code_dt) st =
  let
    val definition = (name, syntax, typ, is)
    fun undecided () =
      TAT_Lift_Definition_Command.code_dt_verdict (Toplevel.context_of st) ((Binding.name name, SOME typ, NoSyn), is)
      = TAT_Lift_Definition_Command.Undecided
  in
    TAT_Proof_Obligation.decide
      {recorded =
         (case with_code_dt of
           NONE => if code_dt andalso undecided () then NONE else SOME false
         | some => some),
       command = fn b => TAT_Framework.apply_transition (transition b definition),
       needed = fn st' =>
         Accepted (case TAT_Proof_Obligation.admit st' of Accepted _ => true | Refused _ => false)}
      st
  end

val _ = Theory.setup (TAT_Proof_Obligation.register
  {name = "TAT.LiftDefinition.evaluate",
   message = unpack_message,
   open_goal = open_goal,
   after_admission = K (fn st => Accepted (st, ())),
   records = packPair (packBool, packUnit)})

end

end
