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
  val register_callback : (env -> Remote_Procedure_Calling.callback') -> theory -> theory

  (*** Session (§2.6) ***)
  val start' : string -> theory -> unit  (*the Python procedure that is the session,
                                           and the theory whose ancestry names the node classes*)
  val start : theory -> unit             (*loads the Python package, then start' "launch_TAT"*)
end

structure TAT_Framework : TAT_FRAMEWORK =
struct

(*** State slots ***)

type slot = {get : unit -> Toplevel.state, put : Toplevel.state option -> unit}

structure Slots = struct

(*A hash table under one lock, held across every read and write
  (contrib/Isabelle_RPC/Tools/RPC.ML:429-437).  The primed layer works on the
  bare table and holds no lock; the public layer takes the lock and calls
  only into the primed layer, so no locked operation can nest another --
  Synchronized's mutex is not reentrant.*)
type T = {table : Toplevel.state Strhashtab.table, lock : unit Synchronized.var}

fun create () : T = {table = Strhashtab.empty 64, lock = Synchronized.var "TAT.slots" ()}

local

fun get' table name =
  (case Strhashtab.lookup table name
     of SOME st => st
      | NONE => error ("State slot " ^ quote name ^ " holds no state"))

fun put' table name (SOME st) = Strhashtab.update table (name, st)
  | put' table name NONE = Strhashtab.delete_safe table name

(*afterwards `dst` holds what `src` holds, nothing included -- by construction*)
fun copy' table (src, dst) = put' table dst (Strhashtab.lookup table src)

fun delete' table = List.app (fn name => put' table name NONE)

fun exists' table name = Strhashtab.defined table name

fun sync ({lock, ...} : T) f = Synchronized.change_result lock (fn () => (f (), ()))

in

fun get (slots : T) name = sync slots (fn () => get' (#table slots) name)
fun put (slots : T) name st = sync slots (fn () => put' (#table slots) name st)
fun copy (slots : T) arg = sync slots (fn () => copy' (#table slots) arg)
fun delete (slots : T) names = sync slots (fn () => delete' (#table slots) names)
fun exists (slots : T) name = sync slots (fn () => exists' (#table slots) name)

end

fun slot (slots : T) name : slot = {get = fn () => get slots name, put = put slots name}

end

(*** Theory table ***)

(*** Theory loader ***)

(*** Running commands ***)

(*** Node classes ***)

type env = {slot_unpacker : slot MessagePackBinIO.Unpack.unpacker}

(*Registrations ride on the theory (§2.5): a session's node classes are
  exactly the classes whose theories the starting theory imports, and
  re-evaluating a registering theory cannot register twice -- the fresh
  theory value carries the registration once.*)
structure Registrations = Theory_Data
(
  type T = (serial * (env -> Remote_Procedure_Calling.callback')) list
  val empty = []
  val merge = Library.merge (eq_fst op =)
)

fun register_callback f = Registrations.map (cons (serial (), f))

(*** Session ***)

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

fun framework_callbacks (slots : Slots.T) = [
  Remote_Procedure_Calling.mk_callback
    {name = "TAT.state_copy", arg_schema = unpackPair (unpackString, unpackString),
     ret_schema = packUnit, function = Slots.copy slots, timeout = NONE},
  Remote_Procedure_Calling.mk_callback
    {name = "TAT.state_delete", arg_schema = unpackList unpackString,
     ret_schema = packUnit, function = Slots.delete slots, timeout = NONE},
  Remote_Procedure_Calling.mk_callback
    {name = "TAT.state_exists", arg_schema = unpackString,
     ret_schema = packBool, function = Slots.exists slots, timeout = NONE}
]

fun start' procedure thy =
  let
    val slots = Slots.create ()
    (*This unpacker must not raise: mk_callback advances the input stream only
      after a successful unpack (contrib/Isabelle_RPC/Tools/RPC.ML:446-449), so
      an exception here leaves the connection mid-message and every later
      callback misparses.  It is safe because Slots.slot only builds two
      closures and touches no table -- do not "validate the slot exists" here.*)
    val env : env = {slot_unpacker = fn src =>
      let val (name, src') = unpackString src in (Slots.slot slots name, src') end}
    val callbacks =
      map (fn (_, f) => f env) (rev (Registrations.get thy)) @ framework_callbacks slots
    (*the dispatch table would silently keep one of two same-named callbacks*)
    val _ = (case duplicates (op =) (map #name callbacks)
              of [] => ()
               | names => error ("Callback registered twice: " ^ commas_quote names))
    val session : (unit, unit) Remote_Procedure_Calling.command =
      {name = procedure, arg_schema = packUnit, ret_schema = unpackUnit,
       callback = callbacks, timeout = NONE}
  in
    Remote_Procedure_Calling.call_command session ()
      handle Remote_Procedure_Calling.Remote_Calling_Failure {message, ...} => error message
  end

end

fun start thy =
  (Remote_Procedure_Calling.load ["isabelle_theory_agent"]; start' "launch_TAT" thy)

end
