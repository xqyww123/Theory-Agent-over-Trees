(*  Title:      ML/TAT_Framework.ML
    Author:     Qiyuan Xu

The framework of TAT's evaluator (docs/MODULE_STRUCTURE.md §2): state slots,
the theory table, the theory loader, running commands, node classes, and the
session.  Knows no node class.

Everything a session owns -- its state slot table, its theory table, the
callbacks -- is local to one call of `start`, as AoA's state table is local
to one `IsaMini.AoA` call (contrib/Isa-Mini/Agent/agent_server.ML:937).
A node class reaches the session only through the `env` handed to its
registered function.
*)

signature TAT_FRAMEWORK =
sig
  (*** State slots (§2.1) ***)
  type slot = {
    get : unit -> Toplevel.state,           (*error when the slot holds nothing*)
    put : Toplevel.state option -> unit     (*NONE deletes*)
  }

  (*** Node classes (§2.5) ***)
  type env = {
    slot_unpacker : slot MessagePackBinIO.Unpack.unpacker   (*reads a slot name off the wire*)
  }
  val register_callback : (env -> Remote_Procedure_Calling.callback') -> unit

  (*** Session (§2.6) ***)
  val start' : string -> unit    (*the Python procedure that is the session*)
  val start : unit -> unit       (*start' "launch_TAT"*)
end

structure TAT_Framework : TAT_FRAMEWORK =
struct

(*** State slots ***)

type slot = {get : unit -> Toplevel.state, put : Toplevel.state option -> unit}

structure Slots = struct

(*A hash table under one lock, held across every read and write
  (contrib/Isabelle_RPC/Tools/RPC.ML:429-437).*)
type T = {table : Toplevel.state Strhashtab.table, lock : unit Synchronized.var}

fun create () : T = {table = Strhashtab.empty 64, lock = Synchronized.var "TAT.slots" ()}

fun sync ({lock, ...} : T) f = Synchronized.change_result lock (fn () => (f (), ()))

fun get (slots : T) name = sync slots (fn () =>
  case Strhashtab.lookup (#table slots) name
    of SOME st => st
     | NONE => error ("State slot " ^ quote name ^ " holds no state"))

fun put (slots : T) name (SOME st) = sync slots (fn () => Strhashtab.update (#table slots) (name, st))
  | put (slots : T) name NONE = sync slots (fn () => Strhashtab.delete_safe (#table slots) name)

(*afterwards `dst` holds what `src` holds, nothing included*)
fun copy (slots : T) (src, dst) = sync slots (fn () =>
  case Strhashtab.lookup (#table slots) src
    of SOME st => Strhashtab.update (#table slots) (dst, st)
     | NONE => Strhashtab.delete_safe (#table slots) dst)

fun delete (slots : T) names = sync slots (fn () =>
  List.app (Strhashtab.delete_safe (#table slots)) names)

fun exists (slots : T) name = sync slots (fn () => Strhashtab.defined (#table slots) name)

fun slot (slots : T) name : slot = {get = fn () => get slots name, put = put slots name}

end

(*** Theory table ***)

(*** Theory loader ***)

(*** Running commands ***)

(*** Node classes ***)

type env = {slot_unpacker : slot MessagePackBinIO.Unpack.unpacker}

(*Registrations wait here until a session starts (§2.5): the environment
  exists only then.  In registration order.*)
val registrations = Synchronized.var "TAT.registrations" ([] : (env -> Remote_Procedure_Calling.callback') list)

fun register_callback f = Synchronized.change registrations (fn fs => fs @ [f])

(*** Session ***)

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

fun framework_callbacks (slots : Slots.T) = [
  Remote_Procedure_Calling.mk_callback
    {name = "TAT.copy_state", arg_schema = unpackPair (unpackString, unpackString),
     ret_schema = packUnit, function = Slots.copy slots, timeout = NONE},
  Remote_Procedure_Calling.mk_callback
    {name = "TAT.delete_states", arg_schema = unpackList unpackString,
     ret_schema = packUnit, function = Slots.delete slots, timeout = NONE},
  Remote_Procedure_Calling.mk_callback
    {name = "TAT.state_exists", arg_schema = unpackString,
     ret_schema = packBool, function = Slots.exists slots, timeout = NONE}
]

fun start' procedure =
  let
    val slots = Slots.create ()
    val env : env = {slot_unpacker = fn src =>
      let val (name, src') = unpackString src in (Slots.slot slots name, src') end}
    val callbacks =
      map (fn f => f env) (Synchronized.value registrations) @ framework_callbacks slots
    (*the dispatch table would silently keep one of two same-named callbacks*)
    val _ = (case duplicates (op =) (map #name callbacks)
              of [] => ()
               | names => error ("Callback registered twice: " ^ commas_quote names))
    val session : (unit, unit) Remote_Procedure_Calling.command =
      {name = procedure, arg_schema = packUnit, ret_schema = unpackUnit,
       callback = callbacks, timeout = NONE}
    val _ = Remote_Procedure_Calling.load ["isabelle_theory_agent"]
  in Remote_Procedure_Calling.call_command session () end

end

fun start () = start' "launch_TAT"

end
