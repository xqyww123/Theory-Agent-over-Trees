(*  Title:      Isabelle_Std/ML/TAT_Datatype.ML

The ML half of the plugin's `Datatype` (isabelle_theory_agent/std/datatype.py;
docs/node_classes/DATATYPE.md §6): the definition as the Python class sends it,
built into the structure the `datatype` and `codatatype` parsers hand
`BNF_FP_Def_Sugar.co_datatype_cmd`, and run as one transition under
`TAT_Common_Nodes.operation`.
*)

structure TAT_Datatype =
struct

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

(*the definition as the Python class sends it: the kind; the type parameters,
  each its name and its sort; the types, each its name, its mixfix annotation
  as `mixfix_text` writes it and its constructors -- each its name, its
  arguments (the type and the selector) and its annotation -- every piece of
  Isabelle text in its ascii*)
type argument = string * string option
type constructor = string * argument list * string option
type definition =
  string * (string * string option) list * (string * string option * constructor list) list

val unpack_definition =
  unpackTuple3 (unpackString,
    unpackList (unpackPair (unpackString, unpackOption unpackString)),
    unpackList (unpackTuple3 (unpackString, unpackOption unpackString,
      unpackList (unpackTuple3 (unpackString,
        unpackList (unpackPair (unpackString, unpackOption unpackString)),
        unpackOption unpackString)))))

fun binding_of NONE = Binding.empty
  | binding_of (SOME name) = Binding.name name

(*one entry of the parsers' structure (bnf_fp_def_sugar.ML, parse_spec), the
  annotations read under the local theory's keywords: the node's type
  parameters, each live and unnamed; the type's name and syntax; the
  constructors, each with no discriminator, its arguments with their
  selectors, and its syntax; no map, rel or pred binding; no selector
  defaults*)
fun spec lthy parameters (name, syntax, constructors) =
  (((((map (fn (v, sort) => (SOME Binding.empty, (v, sort))) parameters, Binding.name name),
      TAT_Mixfix.read lthy syntax),
     map (fn (c, arguments, syn) =>
            (((Binding.empty, Binding.name c), map (fn (T, selector) => (binding_of selector, T)) arguments),
             TAT_Mixfix.read lthy syn))
       constructors),
    (Binding.empty, Binding.empty, Binding.empty)),
   [])

(*the command's own transition: what each parser hands its result to*)
fun transition ((kind, parameters, types) : definition) =
  let
    val (fp, construct) =
      (case kind of
        "datatype" => (BNF_Util.Least_FP, BNF_LFP.construct_lfp)
      | "codatatype" => (BNF_Util.Greatest_FP, BNF_GFP.construct_gfp)
      | _ => raise TAT_Framework.Bug ("TAT_Datatype: the kind " ^ quote kind))
  in
    Toplevel.make kind Position.none
    |> Toplevel.local_theory NONE NONE (fn lthy =>
        BNF_FP_Def_Sugar.co_datatype_cmd fp construct
          (Ctr_Sugar.default_ctr_options_cmd, map (spec lthy parameters) types) lthy)
  end

val _ = Theory.setup (TAT_Framework.register_callback {python_packages = ["isabelle_theory_agent.std"]} (fn env =>
  {name = "TAT.Datatype.evaluate",
    on_interrupt = Remote_Procedure_Calling.Reraise,
    arg_schema = unpackTuple3 (#slot_unpacker env, #slot_unpacker env, unpack_definition),
    ret_schema = packList packString,
    function = fn (input, result, definition) =>
      TAT_Common_Nodes.operation result (fn () =>
        TAT_Framework.apply_transition (transition definition) (#get input ())),
    timeout = NONE}))

end

end
