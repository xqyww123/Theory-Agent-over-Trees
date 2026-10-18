(*  Title:      Isabelle_Std/ML/TAT_Lifting_Closing.ML

The ML half of the plugin's `Lifting_Closing` (isabelle_theory_agent/std/common.py;
docs/node_classes/COMMON.md §6): the ending of a block that closes the Lifting setup
its beginning made -- the two transitions `lifting_update t.lifting` and
`lifting_forget t.lifting` make, run as one operation from the slot after the last
child into the block's resulting slot.
*)

structure TAT_Lifting_Closing =
struct

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

(*the pointer the bundle's attribute holds, of the binding `lifting_bundle` gives
  the bundle (lifting_setup.ML): the same at theory level and inside a `Context`
  or `Locale`, the target morphism leaving the full name unchanged*)
fun pointer lthy name =
  Lifting_Setup.pointer_of_bundle_binding lthy (Binding.qualify_name true (Binding.name name) "lifting")

(*the two commands' own transitions (lifting_setup.ML)*)
fun update name =
  Toplevel.make "lifting_update" Position.none
  |> Toplevel.local_theory NONE NONE (fn lthy => Lifting_Setup.update_transfer_rules (pointer lthy name) lthy)

fun forget name =
  Toplevel.make "lifting_forget" Position.none
  |> Toplevel.local_theory NONE NONE (fn lthy => Lifting_Setup.lifting_forget (pointer lthy name) lthy)

val _ = Theory.setup (TAT_Framework.register_callback {python_packages = ["isabelle_theory_agent.std"]} (fn env =>
  {name = "TAT.Lifting_Closing.close",
    on_interrupt = Remote_Procedure_Calling.Reraise,
    arg_schema = unpackTuple3 (#slot_unpacker env, #slot_unpacker env, unpackString),
    ret_schema = packList packString,
    function = fn (input, result, name) =>
      TAT_Common_Nodes.operation result (fn () =>
        TAT_Framework.apply_transition (update name) (#get input ())
        |> TAT_Framework.bind_answer (TAT_Framework.apply_transition (forget name))),
    timeout = NONE}))

end

end
