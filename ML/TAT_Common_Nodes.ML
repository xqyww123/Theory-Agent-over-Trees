(*  Title:      ML/TAT_Common_Nodes.ML
    Author:     Qiyuan Xu

`operation`, the helper a node class writes its callbacks against, then the
predefined node classes (docs/MODULE_STRUCTURE.md §3), each a client of
TAT_Framework's node class interface.
*)

signature TAT_COMMON_NODES =
sig
  val operation : TAT_Framework.slot -> (unit -> Toplevel.state option * string list)
                  -> string list
    (*runs one operation of a node class and answers its error messages: empty
      when it passed and its state is in the slot (docs/EXCEPTIONS.md §1).  The
      run answers a state and no message, or no state and at least one message;
      anything else is a bug*)
end

structure TAT_Common_Nodes : TAT_COMMON_NODES =
struct

(*** Operations (§2.5) ***)

(*What is never data: a Bug, and an interrupt of either kind -- bare, or
  hidden in the Par_Exn a parallel load releases (Par_Exn keeps a breakdown,
  dropping only a proper interrupt) or in an Exn.EXCEPTIONS.  A wrapper
  holding one of them beside a genuine error propagates whole: the error is
  not reported as data.*)
fun escapes (TAT_Framework.Bug _) = true
  | escapes (Exn.EXCEPTIONS exns) = exists escapes exns
  | escapes exn =
      Exn.is_interrupt exn orelse
      (case Par_Exn.dest exn of
        SOME exns => exists escapes exns
      | NONE => false)

(*The callback's side of docs/EXCEPTIONS.md §1: every failure of the operation
  is data, and what escapes is a bug.  A run's success is a state, written
  into the target slot; its failure is its messages, the slot left to the
  framework, which copies the input through.  An exception raised under
  `run` becomes the operation's messages, read the way Toplevel.command_errors
  reads an exception's (a failing import load arrives as whatever Thy_Info
  raised, released through Par_Exn by TAT_Framework.Loader.load) -- except
  what `escapes` names, re-raised as it arrived.  An exception rendering to
  no message at all would read as success with the slot unwritten; none is
  known, and it is refused as a bug should one appear.*)
fun operation slot (run : unit -> Toplevel.state option * string list) =
  (case Exn.capture_body run of
    Exn.Res (SOME st, []) => (#put slot (SOME st); [])
  | Exn.Res (NONE, msgs as _ :: _) => msgs
  | Exn.Res _ => raise TAT_Framework.Bug "operation: a state and no message, or messages and no state"
  | Exn.Exn exn =>
      if escapes exn then Exn.reraise exn
      else
        (case map (#2 o #1) (Runtime.exn_messages exn) of
          [] => raise TAT_Framework.Bug "operation: an exception with no message"
        | msgs => msgs))

(*** Theory ***)

(*The two operations of the Python `Theory` (model.py; docs/node_classes/
  SESSION_AND_THEORY.md §2).  Each answers the operation's error messages,
  empty when it passed, so that a failed header or `end` is the node's
  result and not a failed call.  The Python half is registered by the loader
  itself, hence no python_packages (PLUGIN_SYSTEM §1).*)

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

(*the header, from a fresh toplevel state, into the first child's slot*)
val _ = Theory.setup (TAT_Framework.register_callback {python_packages = []} (fn env =>
  Remote_Procedure_Calling.mk_callback {
    name = "TAT.Theory.begin",
    on_interrupt = Remote_Procedure_Calling.Reraise,
    arg_schema = unpackPair (#slot_unpacker env,
                   unpackTuple3 (unpackString, unpackString, unpackString)),
    ret_schema = packList packString,
    function = fn (slot, (session_name, master_dir, header)) =>
      operation slot (fn () =>
        (SOME (#begin_theory env {session_name = session_name, master_dir = Path.explode master_dir}
                 (Thy_Header.read Position.start header)),
         [])),
    timeout = NONE}))

(*`end`, from the slot after the children into the resulting slot, and the
  result into the theory table -- before the slot is written, so a table
  write that fails leaves no state the framework does not know of*)
val _ = Theory.setup (TAT_Framework.register_callback {python_packages = []} (fn env =>
  Remote_Procedure_Calling.mk_callback {
    name = "TAT.Theory.end",
    on_interrupt = Remote_Procedure_Calling.Reraise,
    arg_schema = unpackPair (#slot_unpacker env, #slot_unpacker env),
    ret_schema = packList packString,
    function = fn (src, dst) =>
      operation dst (fn () =>
        (case TAT_Framework.run_commands (#get src ()) "end" of
          (_, SOME st) => (#end_theory env st; (SOME st, []))
        | (records, NONE) => (NONE, maps (map (#2 o #1) o #errors) records))),
    timeout = NONE}))

end

(*** Theorem ***)

(*** Define ***)

(*** Section ***)

end
