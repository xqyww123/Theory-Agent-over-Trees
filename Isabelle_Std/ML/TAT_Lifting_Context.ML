(*  Title:      Isabelle_Std/ML/TAT_Lifting_Context.ML

The ML half of the plugin's `LiftingContext` (isabelle_theory_agent/std/lifting_context.py;
docs/node_classes/LIFTING_CONTEXT.md §6): the beginning, `context includes t.lifting
... begin`, every name judged first -- no Lifting bundle, or none with restore data,
the class's sentence; a setup open here already left out of `opened`, silently --
and the names it opened answered beside the messages; the ending, `end`, then
TAT_Lifting_Closing's `close` for each name of `opened`, its pointer read after `end`.
*)

structure TAT_Lifting_Context =
struct

datatype answer = datatype TAT_Framework.answer

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

datatype judgment = No_Lifting of string | Opens | Open_Already

(*§6: a name's bundle's pointer and its restore data, else the sentence; the
  quotient's type registered in the context -- its setup open here already -- or not*)
fun judge ctxt name =
  (case Option.mapPartial (Lifting_Info.lookup_restore_data ctxt)
      (TAT_Lifting_Closing.pointer ctxt (TAT_Lifting_Closing.bundle_name name)) of
    NONE => No_Lifting ("There is no lifting of `" ^ name ^ "` to open here.")
  | SOME {quotient, ...} =>
      let val (_, qty) = Lifting_Util.quot_thm_rty_qty (#quot_thm quotient)
      in if is_some (Lifting_Info.lookup_quotients ctxt (dest_Type_name qty)) then Open_Already else Opens end)

(*the command's own transition, what `context includes ... begin` parses to
  (Pure.thy): the bundles in the names' order, no context element*)
fun begin_transition names =
  Toplevel.make "context" Position.none
  |> Toplevel.begin_nested_target
      (Target_Context.context_begin_nested_cmd
        (map (fn name => ((true, Position.none), (TAT_Lifting_Closing.bundle_name name, Position.none))) names) [])

(*the beginning: every name judged, the refused ones' sentences together; else the
  transition, yielding the names it opened*)
fun open_block names st =
  let
    val ctxt = Toplevel.context_of st
    val judged = map (fn name => (name, judge ctxt name)) names
    val refused = map_filter (fn (_, No_Lifting sentence) => SOME sentence | _ => NONE) judged
  in
    if null refused then
      TAT_Framework.apply_transition (begin_transition names) st
      |> TAT_Framework.map_answer (rpair (map_filter (fn (name, Opens) => SOME name | _ => NONE) judged))
    else Refused refused
  end

(*the ending: `end`, what it parses to after a `context` block (Pure.thy), then each
  opened name's setup closed in the state after `end`*)
val end_transition = Toplevel.make "end" Position.none |> Toplevel.end_nested_target

fun close_block opened st =
  fold (TAT_Framework.bind_answer o TAT_Lifting_Closing.close) opened
    (TAT_Framework.apply_transition end_transition st)

val _ = Theory.setup (TAT_Framework.register_callback {python_packages = ["isabelle_theory_agent.std"]} (fn env =>
  {name = "TAT.LiftingContext.open",
    on_interrupt = Remote_Procedure_Calling.Reraise,
    arg_schema = unpackTuple3 (#slot_unpacker env, #slot_unpacker env, unpackList unpackString),
    ret_schema = TAT_Framework.pack_answer (packList packString),
    function = fn (input, result, names) =>
      TAT_Common_Nodes.operation' result (fn () => open_block names (#get input ())),
    timeout = NONE}))

val _ = Theory.setup (TAT_Framework.register_callback {python_packages = ["isabelle_theory_agent.std"]} (fn env =>
  {name = "TAT.LiftingContext.close",
    on_interrupt = Remote_Procedure_Calling.Reraise,
    arg_schema = unpackTuple3 (#slot_unpacker env, #slot_unpacker env, unpackList unpackString),
    ret_schema = packList packString,
    function = fn (input, result, opened) =>
      TAT_Common_Nodes.operation result (fn () => close_block opened (#get input ())),
    timeout = NONE}))

end

end
