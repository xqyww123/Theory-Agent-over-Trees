(*  Title:      Isabelle_Std/ML/TAT_Mixfix.ML

The decoding of the plugin's `Mixfix` and `TypeMixfix` (docs/node_classes/COMMON.md
§4), from the one wire form `common.py`'s `mixfix_wire` writes: the form, the symbol
or template in its ascii, the priority and the argument priorities as authored, a
left-out value absent -- into the constructor of Isabelle's `mixfix` datatype the
form names, Isabelle's defaults filling what was left out.
*)

signature TAT_MIXFIX =
sig
  type syntax = string * string * int option * int list option
  val unpack : syntax MessagePackBinIO.Unpack.unpacker
  val decode : syntax -> mixfix
    (*`infix`, `infixl`, `infixr`: the symbol and the priority; `binder`: the
      priority serving as both of Isabelle's; `mixfix`: the template, the
      argument priorities ([] when left out) and the result priority (1000
      when left out); no position*)
end

structure TAT_Mixfix : TAT_MIXFIX =
struct

type syntax = string * string * int option * int list option

local open MessagePackBinIO.Unpack in

val unpack = unpackTuple4 (unpackString, unpackString, unpackOption unpackInt, unpackOption (unpackList unpackInt))

end

(*the schema requires an infix's and a binder's priority: its absence is a bug*)
fun required (SOME p) = p
  | required NONE = raise TAT_Framework.Bug "TAT_Mixfix: an infix or binder without priority"

fun decode (form, text, priority, argument_priorities) =
  let val source = Input.string text in
    (case form of
      "infix" => Infix (source, required priority, Position.no_range)
    | "infixl" => Infixl (source, required priority, Position.no_range)
    | "infixr" => Infixr (source, required priority, Position.no_range)
    | "binder" => Binder (source, required priority, required priority, Position.no_range)
    | "mixfix" => Mixfix (source, the_default [] argument_priorities, the_default 1000 priority, Position.no_range)
    | _ => raise TAT_Framework.Bug ("TAT_Mixfix: the form " ^ quote form))
  end

end
