(*  Title:      Isabelle_Std/ML/TAT_Typedef.ML

The ML half of the plugin's `Typedef` (isabelle_theory_agent/std/typedef.py;
docs/node_classes/TYPEDEF.md §6): the subtype's definition as the Python class
sends it, run as the `typedef` command's transition with `(overloaded)`, the
option's need read off the open goal; after the admission, `setup_lifting` on the
type's theorem as the recorded `lifting` says -- tried once with none, run with
true, left out with false.  The callback is built by
`TAT_Proof_Obligation.register` (COMMON.md §3); the admission, the proof
construction and the proof check are that structure's too.
*)

structure TAT_Typedef =
struct

datatype answer = datatype TAT_Framework.answer

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

(*the definition as the Python class sends it: the type's name; its mixfix
  annotation as `mixfix_text` writes it, none for none; the Rep and the Abs
  function names, a name left out as its default; then the goal's part -- the
  type parameters, each its name and its sort, and the set -- every piece of
  Isabelle text in its ascii*)
type definition =
  string * string option * string * string * (string * string option) list * string

val unpack_definition =
  unpackTuple6 (unpackString, unpackOption unpackString, unpackString, unpackString,
    unpackList (unpackPair (unpackString, unpackOption unpackString)), unpackString)

(*the message: the definition and the recorded `lifting`, none until an
  evaluation has recorded one (COMMON.md §5)*)
val unpack_message = unpackPair (unpack_definition, unpackOption unpackBool)

(*the command's own transition, what its parser hands its result to (typedef.ML),
  with the option: the one check it switches off is asked by TAT_Overloaded.needed
  instead; the annotation read under the local theory's keywords*)
fun typedef_transition ((name, syntax, rep, abs, parameters, set) : definition) =
  Toplevel.make "typedef" Position.none
  |> Toplevel.local_theory_to_proof NONE NONE (fn lthy =>
      Typedef.typedef_cmd {overloaded = true} (Binding.name name, parameters, TAT_Mixfix.read lthy syntax) set
        (SOME (Typedef.make_morphisms (Binding.name name) (SOME (Binding.name rep, Binding.name abs)))) lthy)

(*`Typedef`'s open_goal (COMMON.md §3): the transition from the input state to
  the state with the goal open, yielding whether the type needs the option --
  TAT_Overloaded.needed under the type's full name as Typedecl declared it
  (TYPEDEF.md §6); the dependencies are registered as the goal opens
  (typedef.ML, prepare_typedef)*)
fun open_goal (definition as (name, _, _, _, _, _)) st =
  TAT_Framework.apply_transition (typedef_transition definition) st
  |> TAT_Framework.map_answer (fn st' =>
      let
        val ctxt = Proof.context_of (Toplevel.proof_of st')
        val full_name = Local_Theory.full_name ctxt (Binding.name name)
      in (st', TAT_Overloaded.needed (Proof_Context.theory_of ctxt) full_name) end)

(*the one transition `setup_lifting type_definition_<name>` makes: the theorem
  read by its name and no attribute, the lookup the command's own
  Attrib.eval_thms makes (lifting_setup.ML, setup_lifting_cmd)*)
fun lifting_transition name =
  Toplevel.make "setup_lifting" Position.none
  |> Toplevel.local_theory NONE NONE (fn lthy =>
      Lifting_Setup.setup_by_typedef_thm Lifting_Setup.default_config
        (Proof_Context.get_fact_single lthy (Facts.named ("type_definition_" ^ name))) lthy
      |> snd)

(*`Typedef`'s after_admission (COMMON.md §3) under the recorded `lifting`
  (TYPEDEF.md §6): with none, `setup_lifting` tried once -- the state after it
  and true when Isabelle accepts it, the admitted state and false when it
  refuses, its messages dropped; with true, run, a refusal the definition's
  failure; with false, not run, the admitted state and false*)
fun after_admission (((name, _, _, _, _, _), recorded) : definition * bool option) admitted =
  if recorded = SOME false then Accepted (admitted, false)
  else
    (case TAT_Framework.apply_transition (lifting_transition name) admitted of
      Accepted st => Accepted (st, true)
    | Refused messages => if is_some recorded then Refused messages else Accepted (admitted, false))

val _ = Theory.setup (TAT_Proof_Obligation.register
  {name = "TAT.Typedef.evaluate",
   message = unpack_message,
   open_goal = open_goal o fst,
   after_admission = after_admission,
   records = packPair (packBool, packBool)})

end

end
