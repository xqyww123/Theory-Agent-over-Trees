(*  Title:      Isabelle_Std/ML/TAT_Lifting_Closing.ML

The ML half of the plugin's `Lifting_Closing` (isabelle_theory_agent/std/common.py;
docs/node_classes/COMMON.md §6): the ending of a block that closes the Lifting setup
its beginning made -- the two transitions `lifting_update t.lifting` and
`lifting_forget t.lifting` make, run as one operation from the slot after the last
child into the block's resulting slot.  `bundle_name`, `pointer` and `close` are
`LiftingContext`'s too (TAT_Lifting_Context.ML; LIFTING_CONTEXT.md §6).
*)

structure TAT_Lifting_Closing =
struct

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

fun bundle_name t = t ^ ".lifting"

(*the pointer the bundle's one attribute holds -- the key of the setup's restore
  data (lifting_setup.ML, `lifting_bundle`) --, read as the two commands read it:
  lifting_setup.ML's `pointer_of_bundle_name`, which Isabelle does not export, with
  its two errors*)
fun the_pointer ctxt bundle_name =
  let
    val bundle = Bundle.get ctxt (Bundle.check ctxt (bundle_name, Position.none))
    fun err () = error "The provided bundle is not a lifting bundle"
  in
    (case bundle of
      [(_, [arg_src])] => (Token.read ctxt Parse.string arg_src handle ERROR _ => err ())
    | _ => err ())
  end

(*the pointer, or NONE for a name no bundle bears or a bundle that is no Lifting bundle*)
fun pointer ctxt = try (the_pointer ctxt)

(*the two commands' own transitions on the pointer (lifting_setup.ML)*)
fun update pointer =
  Toplevel.make "lifting_update" Position.none
  |> Toplevel.local_theory NONE NONE (Lifting_Setup.update_transfer_rules pointer)

fun forget pointer =
  Toplevel.make "lifting_forget" Position.none
  |> Toplevel.local_theory NONE NONE (Lifting_Setup.lifting_forget pointer)

(*the ending's two transitions on the pointer, `lifting_update` then `lifting_forget`*)
fun close_setup pointer st =
  TAT_Framework.apply_transition (update pointer) st
  |> TAT_Framework.bind_answer (TAT_Framework.apply_transition (forget pointer))

(*the type `t`'s setup closed in the state: its pointer read in the state's context,
  then the two transitions*)
fun close t st = close_setup (the_pointer (Toplevel.context_of st) (bundle_name t)) st

val _ = Theory.setup (TAT_Framework.register_callback {python_packages = ["isabelle_theory_agent.std"]} (fn env =>
  {name = "TAT.Lifting_Closing.close",
    on_interrupt = Remote_Procedure_Calling.Reraise,
    arg_schema = unpackTuple3 (#slot_unpacker env, #slot_unpacker env, unpackString),
    ret_schema = packList packString,
    function = fn (input, result, name) => TAT_Common_Nodes.operation result (fn () => close name (#get input ())),
    timeout = NONE}))

end

end
