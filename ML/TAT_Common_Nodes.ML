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
  val identifier_words : Keyword.keywords -> string list
    (*the words of a keyword table that are identifiers, from both lexicons,
      in the `\<name>` spelling (SESSION_AND_THEORY §2)*)
end

structure TAT_Common_Nodes : TAT_COMMON_NODES =
struct

(*** Operations (§2.5) ***)

(*What is never data: a Bug and an interrupt of either kind, each found
  however wrapped (TAT_Framework.bug_message, TAT_Framework.interrupted).  A
  wrapper holding one of them beside a genuine error propagates whole: the
  error is not reported as data.*)
fun escapes exn = is_some (TAT_Framework.bug_message exn) orelse TAT_Framework.interrupted exn

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
  result and not a failed call; the beginning answers beside them, when it
  passed, the session of each import and the theory's keywords, which the
  Python class stores on the node.  The Python half is registered by the
  loader itself, hence no python_packages (PLUGIN_SYSTEM §1).*)

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

(*the session of each import, in the header's order: the qualifier of the
  name the import resolves to, which the Python class records for the ROOT's
  `sessions` clause (docs/COMPILATION.md §2)*)
fun import_sessions {session_name, master_dir} (header : Thy_Header.header) =
  map (fn (import, _) =>
        Resources.theory_qualifier
          (#theory_name (Resources.import_name session_name master_dir import)))
      (#imports header)

fun identifier_words table =
  filter Symbol_Pos.is_identifier
    (Scan.dest_lexicon (Keyword.minor_keywords table) @ Scan.dest_lexicon (Keyword.major_keywords table))

(*the theory's keyword table: what the Python class's `print_name` quotes,
  the rule of Token.print_name*)
fun keywords st = identifier_words (Thy_Header.get_keywords (Toplevel.theory_of st))

(*the header, from a fresh toplevel state, into the first child's slot;
  answers the header's error messages and, when it passed, the session of
  each import and the keywords*)
val _ = Theory.setup (TAT_Framework.register_callback {python_packages = []} (fn env =>
  {name = "TAT.Theory.begin",
    on_interrupt = Remote_Procedure_Calling.Reraise,
    arg_schema = unpackPair (#slot_unpacker env,
                   unpackTuple3 (unpackString, unpackString, unpackString)),
    ret_schema = packTuple3 (packList packString, packList packString, packList packString),
    function = fn (slot, (session_name, master_dir, header)) =>
      let
        val context = {session_name = session_name, master_dir = Path.explode master_dir}
        val errors =
          operation slot (fn () =>
            (SOME (#begin_theory env context (Thy_Header.read Position.start header)), []))
      in
        (*a header that passed is read a second time: it parsed, and every
          import resolved*)
        if null errors
        then (errors, import_sessions context (Thy_Header.read Position.start header), keywords (#get slot ()))
        else (errors, [], [])
      end,
    timeout = NONE}))

(*`end`, from the slot after the children into the resulting slot, and the
  result into the theory table -- before the slot is written, so a table
  write that fails leaves no state the framework does not know of.  The
  transition is Toplevel.exit, the one the `end` span parses to at theory
  level (EVALUATOR_DESIGN §1); on a state still inside a context or a proof
  it fails, and the failure is the node's messages.*)
val _ = Theory.setup (TAT_Framework.register_callback {python_packages = []} (fn env =>
  {name = "TAT.Theory.end",
    on_interrupt = Remote_Procedure_Calling.Reraise,
    arg_schema = unpackPair (#slot_unpacker env, #slot_unpacker env),
    ret_schema = packList packString,
    function = fn (src, dst) =>
      operation dst (fn () =>
        let
          val (st, messages) =
            TAT_Framework.apply_transition
              (Toplevel.make "end" Position.none |> Toplevel.exit) (#get src ())
        in (Option.app (#end_theory env) st; (st, messages)) end),
    timeout = NONE}))

end

end
