(*  Title:      ML/TAT_Common_Nodes.ML
    Author:     Qiyuan Xu

The predefined node classes (docs/MODULE_STRUCTURE.md §3), each a client of
TAT_Framework's node class interface.
*)

signature TAT_COMMON_NODES =
sig
end

structure TAT_Common_Nodes : TAT_COMMON_NODES =
struct

(*** Theory ***)

(*The two operations of the Python `Theory` (model.py; docs/node_classes/
  SESSION_AND_THEORY.md §2).  Each answers the operation's error messages,
  empty when it passed, so that a failed header or `end` is the node's
  result and not a failed call.  The Python half is registered by the loader
  itself, hence no python_packages (PLUGIN_SYSTEM §1).*)

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

(*Runs an operation whose success is a state, writes that state into the
  target slot, and answers its messages.  Any non-interrupt exception raised
  under `run` -- a failing import load arrives as whatever Thy_Info raised,
  released through Par_Exn (TAT_Framework.Loader.load); a framework Fail too
  -- becomes the operation's messages, read the way Toplevel.command_errors
  reads an exception's; an interrupt is re-raised, as TAT_Framework.run_span
  does.  On failure the slot is left to the framework, which copies the
  input through.  A run answering neither a state nor a message would
  report success while writing nothing, so it is refused as a bug.*)
fun operation slot (run : unit -> Toplevel.state option * string list) =
  (case Exn.capture_body run of
    Exn.Res (SOME st, []) => (#put slot (SOME st); [])
  | Exn.Res (NONE, []) => raise Fail "operation: neither a state nor a message"
  | Exn.Res (_, msgs) => msgs
  | Exn.Exn exn =>
      (case map (#2 o #1) (Runtime.exn_messages exn) of
        [] => Isabelle_Thread.raise_interrupt ()
      | msgs => msgs))

(*the header, from a fresh toplevel state, into the first child's slot*)
val _ = Theory.setup (TAT_Framework.register_callback {python_packages = []} (fn env =>
  Remote_Procedure_Calling.mk_callback {
    name = "TAT.Theory.begin",
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
