(*  Title:      Isabelle_Std/ML/TAT_Quotient_Type.ML

The ML half of the plugin's `QuotientType` (isabelle_theory_agent/std/quotient_type.py;
docs/node_classes/QUOTIENT_TYPE.md §6): the quotient type's definition as the Python
class sends it, run as the `quotient_type` command's transition with `(overloaded)`
decided by TAT_Proof_Obligation.decide -- a probe run through the admission, where
the `typedef` happens, then the real run -- or run as recorded; nothing after the
admission.  The callback is built by `TAT_Proof_Obligation.register` (COMMON.md §3);
the admission, the proof construction and the proof check are that structure's; the
block's ending is TAT_Lifting_Closing's.
*)

structure TAT_Quotient_Type =
struct

datatype answer = datatype TAT_Framework.answer

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

(*the message as the Python class sends it, three parts: the authored fields -- the
  type's name, its type parameters, its mixfix annotation as `mixfix_text` writes
  it or none, the Rep and the Abs function names with the defaults filled in --;
  the recorded `overloaded`, none until an evaluation has recorded one (COMMON.md
  §5); the goal's part -- the representation type, `partial` and the relation --
  every piece of Isabelle text in its ascii*)
type authored = string * string list * string option * string * string
type goal = string * bool * string
type message = authored * bool option * goal

val unpack_message =
  unpackTuple3
    (unpackTuple5 (unpackString, unpackList unpackString, unpackOption unpackString, unpackString, unpackString),
     unpackOption unpackBool,
     unpackTuple3 (unpackString, unpackBool, unpackString))

(*the command's own transition, what its parser hands its result to
  (quotient_type.ML), with the option; the annotation read under the local
  theory's keywords; no parametricity theorem*)
fun quotient_type_transition overloaded
      (((name, parameters, syntax, rep, abs), (representation_type, partial, equiv_relation)) : authored * goal) =
  Toplevel.make "quotient_type" Position.none
  |> Toplevel.local_theory_to_proof NONE NONE (fn lthy =>
      Quotient_Type.quotient_type_cmd {overloaded = overloaded}
        ((((((parameters, Binding.name name), TAT_Mixfix.read lthy syntax), representation_type),
           (partial, equiv_relation)), SOME (Binding.name rep, Binding.name abs)), NONE) lthy)

(*`QuotientType`'s open_goal (COMMON.md §3): the transition from the input state to
  the state with the goal open, yielding the option it ran with, decided by
  TAT_Proof_Obligation.decide (QUOTIENT_TYPE.md §6).  The probe reaches the
  admission, since the `typedef` happens there, and `needed_at` is asked of the
  admitted state under the type's name.*)
fun open_goal ((authored as (name, _, _, _, _), overloaded, goal) : message) =
  TAT_Proof_Obligation.decide
    {recorded = overloaded,
     command = fn b => TAT_Framework.apply_transition (quotient_type_transition b (authored, goal)),
     needed = fn st =>
       TAT_Proof_Obligation.admit st
       |> TAT_Framework.map_answer (fn st' => TAT_Overloaded.needed_at st' (Binding.name name))}

val _ = Theory.setup (TAT_Proof_Obligation.register
  {name = "TAT.QuotientType.evaluate",
   message = unpack_message,
   open_goal = open_goal,
   after_admission = K (fn st => Accepted (st, ())),
   records = packPair (packBool, packUnit)})

end

end
