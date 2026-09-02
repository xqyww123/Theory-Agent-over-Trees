(*  Title:      ML/TAT_Framework.ML
    Author:     Qiyuan Xu

The framework of TAT's evaluator (docs/MODULE_STRUCTURE.md §2): state slots,
the theory table, the theory loader, running commands, node classes, and the
conversation.  Knows no node class.

Everything a conversation owns -- its state slot table, its theory table, the
callbacks -- is local to one call of `start`, as AoA's state table is local
to one `IsaMini.AoA` call (contrib/Isa-Mini/Agent/agent_server.ML:937).
A node class reaches the conversation only through the `env` handed to its
registered function.
*)

signature TAT_FRAMEWORK =
sig
  (*** State slots (§2.1) ***)
  type slot = {
    get : unit -> Toplevel.state,           (*error when the slot holds nothing*)
    put : Toplevel.state option -> unit     (*NONE deletes*)
  }

  (*** Running commands (§2.4) ***)
  datatype output_message =
    Writeln of string | Tracing of string | Warning of string |
    Information of string | Legacy of string
  type command_record = {
    source : string,                (*the command's text, sliced verbatim*)
    range : Position.range,         (*within the text handed to run_commands*)
    errors : Runtime.error list,
    output : output_message list    (*plain text, markup stripped*)
  }
  val run_commands : Toplevel.state -> string -> command_record list * Toplevel.state option
                                          (*one record per command; stops at a
                                            command that returns no state*)

  (*** Node classes (§2.5) ***)
  type env = {
    slot_unpacker : slot MessagePackBinIO.Unpack.unpacker,
                      (*reads a slot name off the wire, on this conversation's table*)
    begin_theory : {session_name : string, master_dir : Path.T} ->
                   Thy_Header.header -> Toplevel.state,
                      (*§2.4's, imports resolved through this conversation's tables*)
    end_theory : Toplevel.state -> unit
                      (*§2.4's, the result put into this conversation's theory table*)
  }
  val register_callback :
    {python_packages : string list} ->    (*the class's Python half; imported at
                                            conversation start, filling the kind
                                            table (§4.3)*)
    (env -> Remote_Procedure_Calling.callback') -> theory -> theory

  (*** Conversation (§2.6) ***)
  val start' : string -> theory -> unit  (*the Python procedure that is the conversation,
                                           and the theory whose ancestry names the node classes*)
  val start : theory -> unit             (*loads the Python package, then start' "launch_TAT"*)
end

structure TAT_Framework : TAT_FRAMEWORK =
struct

(*** State slots ***)

type slot = {get : unit -> Toplevel.state, put : Toplevel.state option -> unit}

structure Slots = struct

(*A pure table under a Synchronized.var (EVALUATOR_DESIGN §1.1).  Every
  write is one atomic change over the pure table, so a compound operation
  (copy, batch delete) is ordinary pure code inside one change and no
  locked operation can nest another; a read takes an atomic snapshot.*)
type T = Toplevel.state Symtab.table Synchronized.var

fun create () : T = Synchronized.var "TAT.slots" Symtab.empty

fun get (slots : T) name =
  (case Symtab.lookup (Synchronized.value slots) name of
    SOME st => st
  | NONE => error ("State slot " ^ quote name ^ " holds no state"))

fun put' name (SOME st) = Symtab.update (name, st)
  | put' name NONE = Symtab.delete_safe name

fun put (slots : T) name st = Synchronized.change slots (put' name st)

(*afterwards `dst` holds what `src` holds, nothing included -- by construction*)
fun copy (slots : T) (src, dst) =
  Synchronized.change slots (fn tab => put' dst (Symtab.lookup tab src) tab)

fun delete (slots : T) names = Synchronized.change slots (fold Symtab.delete_safe names)

fun exists (slots : T) name = Symtab.defined (Synchronized.value slots) name

fun slot (slots : T) name : slot = {get = fn () => get slots name, put = put slots name}

end

(*** Theory table ***)

structure Theories = struct

(*One per conversation (§2.2), the shape of Slots.  `put` keys by the theory
  value's own long name, so the key cannot disagree with the value; it is
  the string §2.3's resolution produces, because begin_theory qualifies the
  name through the same import_name call.  A second write overwrites: TAT
  re-evaluates on every edit (EVALUATOR_DESIGN §3).*)
type T = theory Symtab.table Synchronized.var

fun create () : T = Synchronized.var "TAT.theories" Symtab.empty

fun lookup (theories : T) name = Symtab.lookup (Synchronized.value theories) name

fun put (theories : T) thy =
  Synchronized.change theories (Symtab.update (Context.theory_long_name thy, thy))

end

(*** Theory loader ***)

structure Loader = struct

(*Thy_Info is process-global and has no internal mutual exclusion, so the
  lock is process-global too (EVALUATOR_DESIGN §6: one lock around every
  call).*)
val lock = Synchronized.var "TAT.thy_load" ()

(*The Thy_Info.use_theories wrapper of EVALUATOR_DESIGN §6, one theory per
  call by signature.

  Thy_Info.use_theories ends with Execution.reset () (thy_info.ML:284), which
  empties the process-global execution table and turns the failures it finds
  there into the exception of the call that produced them.  When a theory fails
  under more than one thread with parallel proofs, the exception escapes earlier
  -- at :275, out of the uncaptured "present ()" in present_theory (:247) -- so
  that reset never runs.  The residue then stays in the table until the next
  call resets, which therefore raises with the previous call's error, after
  committing its own theories.
  Running the reset here makes a failing load leave exactly the state a
  successful load leaves, so every exception describes the call that raised it.
  It also recovers errors that the callee dropped: on a batch where two theories
  fail, the raw call reports one and strands the other.
  Exn.capture_body rather than Exn.result: result re-raises an interrupt on
  the spot, so a cancelled load would skip the reset below and leave exactly
  the residue this wrapper exists to drain.  The drain, run uninterruptibly
  once the call has returned, therefore always completes; a cancellation is
  then re-raised explicitly -- Par_Exn treats an interrupt as a neutral
  element (par_exn.ML) and release_all would swallow it whenever the residue
  holds real errors -- and residue errors are released only when the call
  was not cancelled.*)
fun load qualifier import =
  Synchronized.change lock (fn () =>
    let
      val result =
        Exn.capture_body (fn () => Thy_Info.use_theories (Options.default ()) qualifier [import])
      val residue =
        Thread_Attributes.uninterruptible (fn _ => fn () =>
          map Exn.Exn (maps Task_Queue.group_status (Execution.reset ()))) ()
      val _ =
        (case Exn.get_exn result of
          SOME exn => if Exn.is_interrupt_proper exn then Exn.reraise exn else ()
        | NONE => ())
      val _ = Par_Exn.release_all (result :: residue)
    in () end)

(*What load may be given (EVALUATOR_DESIGN §6): a session-qualified name when
  the session layout knows the file, the file's own path when there is a
  file -- never a bare name.  The path round-trips through use_theories' own
  import_name to the same theory_name, because the qualifier passed along is
  the same.  A qualified import in no known session resolves to a bare
  loaded_theory_node (resources.ML) whose node_name is no file at all --
  nothing anywhere provides it, so refuse by name rather than fabricate one
  by cutting at the wrong dot.  Wording: RENDER_BASELINES.md.*)
fun load_target theory_name node_name =
  (case Resources.find_theory_file theory_name of
    SOME _ => theory_name
  | NONE =>
      if Path.get_ext node_name = "thy"
      then Path.implode (Path.drop_ext node_name)
      else error ("Fail to load `" ^ theory_name ^ "` because it is not found."))

(*Import resolution in the order of EVALUATOR_DESIGN §2, behind one
  Resources.import_name call (§7).*)
fun resolve theories {session_name, master_dir} (import, pos) =
  let
    val {node_name, theory_name, ...} = Resources.import_name session_name master_dir import
  in
    (case Theories.lookup theories theory_name of
      SOME thy => thy
    | NONE =>
        (case Thy_Info.lookup_theory theory_name of
          SOME thy => thy
        | NONE =>
            (load session_name (load_target theory_name node_name, pos);
             Thy_Info.get_theory theory_name)))
  end

(*The base-heap half of the short-name check (§2.3): the long name of the
  theory whose short name `name` takes, or NONE when the name is free.  The
  rejection and its wording are Python's (RENDER_BASELINES.md).*)
fun check_new_theory_short_name name =
  let val short = Long_Name.base_name name
  in List.find (fn n => Long_Name.base_name n = short) (Thy_Info.get_names ()) end

(*EVALUATOR_DESIGN §6: at 3 -- the interactive default -- a theory whose
  structured proof fails commits successfully and the error surfaces later.*)
fun check_parallel_proofs () =
  let val n = ! Multithreading.parallel_proofs
  in if n = 1 then ()
     else error ("TAT requires parallel_proofs = 1, but this process runs at " ^
                 string_of_int n)
  end

end

(*** Running commands ***)

datatype output_message =
  Writeln of string | Tracing of string | Warning of string |
  Information of string | Legacy of string

type command_record = {
  source : string,
  range : Position.range,
  errors : Runtime.error list,
  output : output_message list
}

structure Output_Routing = struct

(*§2.4: agent-facing text leaves the process through the six Private_Output
  channels listed below.  Each is replaced once, with a function that routes
  a message by the id in Position.thread_data () into the buffer registered
  for that id, and falls back to the function it replaced when there is no
  id or no buffer.  The id travels with Future.fork (future.ML:452), so a
  message printed on a forked worker still reaches its command's buffer.*)

val buffers : output_message list Symtab.table Synchronized.var =
  Synchronized.var "TAT.output_buffers" Symtab.empty

fun new_buffer id = Synchronized.change buffers (Symtab.update_new (id, []))

fun take_buffer id =
  Synchronized.change_result buffers (fn tab =>
    (rev (these (Symtab.lookup tab id)), Symtab.delete_safe id tab))

fun route mk fallback outputs =
  (case Position.id_of (Position.thread_data ()) of
    NONE => fallback outputs
  | SOME id =>
      if not (Symtab.defined (Synchronized.value buffers) id) then fallback outputs
      else
        let
          (*total, unlike a YXML parse: a routed output call must never
            raise (stock's own cleaner); computed outside the lock*)
          val text = Protocol_Message.clean_output (implode outputs)
          val routed =
            Synchronized.change_result buffers (fn tab =>
              (case Symtab.lookup tab id of
                NONE => (false, tab)
              | SOME msgs => (true, Symtab.update (id, mk text :: msgs) tab)))
        in if routed then () else fallback outputs end)

(*The channel set is data, so an omission is visible.  The urgent channel
  taught the lesson: the result block of lemma/theorem/definition prints
  through writeln_urgent_fn (proof_display.ML:322-328), a separate ref from
  writeln_fn; urgent output is writeln with an urgent property
  (isabelle_process.ML), hence the shared constructor.
  Deliberately not captured:
  - state_fn: proof states; the Python side reads states off the slots;
  - error_message_fn: errors travel structurally in the command records
    (Toplevel.command_errors), capturing the channel would report each twice;
  - status_fn, report_fn, result_fn, system_message_fn, protocol_message_fn:
    PIDE protocol machinery, not text for an agent.*)
val channels = [
  (Private_Output.writeln_fn, Writeln),
  (Private_Output.writeln_urgent_fn, Writeln),
  (Private_Output.tracing_fn, Tracing),
  (Private_Output.warning_fn, Warning),
  (Private_Output.information_fn, Information),
  (Private_Output.legacy_fn, Legacy)
]

(*Idempotent; the first call captures the process's current functions as the
  fallback.  Called at conversation start (§2.6) and by run_commands itself,
  so capture cannot be forgotten (EVALUATOR_DESIGN §4).*)
val installed = Synchronized.var "TAT.output_routing" false
fun install () =
  Synchronized.change installed (fn true => true | false =>
    (List.app (fn (r, mk) => let val fallback = ! r in r := route mk fallback end) channels;
     true))

end

local

(*offsets count symbols, as Position offsets do*)
fun span_source symbols span =
  let
    val (pos1, pos2) = Command_Span.range span
    val i = the_default 1 (Position.offset_of pos1)
    val j = the_default i (Position.offset_of pos2)
  in implode (take (j - i) (drop (i - 1) symbols)) end

(*§2.4: a fresh id per span.  The id slot of a position is the execution
  registry's key: Execution.fork and Execution.print read it back
  (Position.parse_id) and fail on an unregistered id, so the id is minted
  by the registry's own counter and registered before the command runs,
  exactly as batch loading does (thy_info.ML:359-364); Toplevel.exec_id
  plants it on the transition's position -- the transition runs under its
  own position (toplevel.ML:628), so the ambient wrapper alone would be
  overridden.  After the run, forks that attached to the command are joined
  and their failures land in this command's errors (thy_info.ML:240-242).*)
fun run_span tr st =
  let
    val exec = Document_ID.make ()
    val id = Document_ID.print exec
  in
    \<^try>\<open>
      let
        val _ = Output_Routing.new_buffer id
        val _ = Execution.running Document_ID.none exec [] orelse
                  raise Fail ("Failed to register execution " ^ id)
        val (errors, st') =
          Position.setmp_thread_data (Position.id_only id)
            (fn () => Toplevel.command_errors true (Toplevel.exec_id exec tr) st) ()
        val _ = Execution.join [exec]
        val fork_errors =
          maps Runtime.exn_messages (maps Task_Queue.group_status (Execution.peek exec))
        val output = Output_Routing.take_buffer id
        (*one normalisation contract for both record fields (the output side
          is stripped in Output_Routing.route)*)
        val all_errors =
          map (fn ((i, msg), pos_id) => ((i, Protocol_Message.clean_output msg), pos_id))
            (errors @ fork_errors)
      in
        (*an interrupt is folded to ([], NONE) by command_errors -- Par_Exn.dest
          yields no messages for a proper interrupt; stock re-raises the case
          (command.ML:247-249, toplevel.ML:652-654) and so does TAT: a
          cancellation unwinds the conversation whole.  A failed fork is the
          command's failure -- its committed state carries a broken promise,
          so it is withheld -- keeping "errors nonempty iff no state" exact.*)
        (case (all_errors, st') of
          ([], NONE) => Isabelle_Thread.raise_interrupt ()
        | ([], SOME _) => (([], output), st')
        | (errs, _) => ((errs, output), NONE))
      end
      (*cancel before purge: purge alone drops a still-live group without a
        guard (its own "Attempt to purge valid execution" check is vacuous,
        execution.ML:229-235); after the join above, cancel touches only
        finished groups*)
      finally
        (Execution.cancel exec; Execution.purge [exec];
         ignore (Output_Routing.take_buffer id))\<close>
  end

in

(*§2.4: split with Outer_Syntax.parse_spans, run each span through
  Toplevel.command_errors true, threading the state.  The first argument
  `true` is Isabelle's interactive flag and load-bearing: `sorry` is refused
  without it (EVALUATOR_DESIGN §1).  Tokenisation is one pass over the whole
  text (stock does the same, thy_info.ML:300), but each span is parsed
  against the state it runs in (stock: Command.read_span per element), so a
  command *implementation* an earlier span installed parses in a later one
  -- a new *keyword* does not, its token was lexed before it existed.  The
  init handed to parse_span is pure_syn.ML's own refusal, for a stray
  `theory` command mid-text.*)
fun run_commands st text =
  let
    val _ = Output_Routing.install ()
    val keywords = Thy_Header.get_keywords (Command.read_thy st)
    val symbols = Symbol.explode text
    val spans =
      Outer_Syntax.parse_spans (Token.explode keywords Position.start text)
      |> filter_out Command_Span.is_ignored
    fun run [] st = ([], SOME st)
      | run (span :: rest) st =
          let
            val tr =
              Outer_Syntax.parse_span (Command.read_thy st)
                (fn () => error "Missing theory initialization")
                (Command_Span.content span)
          in
            (*a span that parses to no command produces no record: a
              marked-comment-only span arrives as Malformed_Span yet parses
              to an ignored transition*)
            if Toplevel.is_ignored tr then run rest st
            else
              let
                val ((errors, output), st') = run_span tr st
                val record : command_record =
                  {source = span_source symbols span, range = Command_Span.range span,
                   errors = errors, output = output}
              in
                (case st' of
                  NONE => ([record], NONE)
                | SOME st'' => run rest st'' |>> cons record)
              end
          end
  in run spans st end

end

(*§2.4.  The header's name is qualified through the same one import_name call
  as every import (EVALUATOR_DESIGN §7), as batch loading does
  (thy_info.ML:386): the theory value's long name is then the string
  resolution produces, which is what the theory table keys by.
  The transition is the one the `theory` span parses to -- its parser is
  Thy_Header.args >> (fn _ => Toplevel.init_theory (fn () => error ...))
  (pure_syn.ML), everything but the init discarded -- with our init planted
  where Outer_Syntax.parse_span's second argument would plant it
  (EVALUATOR_DESIGN §1), run from Toplevel.make_state NONE.*)
fun begin_theory theories (context as {session_name, master_dir}) (header : Thy_Header.header) =
  let
    val (name, name_pos) = #name header
    (*node names carry no dot (MCP_SPECIFICATION §2), so a qualified name
      here is a framework bug -- and letting it through would unhook the
      theory-table key from (session, tree)*)
    val _ =
      if Long_Name.is_qualified name
      then raise Fail ("Theory header names a qualified theory: " ^ quote name)
      else ()
    val qualified = #theory_name (Resources.import_name session_name master_dir name)
    val parents = map (Loader.resolve theories context) (#imports header)
    val header' = Thy_Header.make (qualified, name_pos) (#imports header) (#keywords header)
    val tr =
      Toplevel.make Thy_Header.theoryN name_pos
      |> Toplevel.init_theory (fn () => Resources.begin_theory master_dir header' parents)
  in
    (case Toplevel.command_errors true tr (Toplevel.make_state NONE) of
      (_, SOME st) => st
    | ([], NONE) => Isabelle_Thread.raise_interrupt ()   (*as run_span: the folded-interrupt case*)
    | (errors, NONE) => error (cat_lines (map (#2 o #1) errors)))
  end

(*§2.4: the value the theory table stores.  The state must have run the
  node's `end` already; its position lives in the node's text, not here.*)
fun end_theory theories st = Theories.put theories (Toplevel.end_theory Position.none st)

(*** Node classes ***)

type env = {
  slot_unpacker : slot MessagePackBinIO.Unpack.unpacker,
  begin_theory : {session_name : string, master_dir : Path.T} ->
                 Thy_Header.header -> Toplevel.state,
  end_theory : Toplevel.state -> unit
}

(*Registrations ride on the theory (§2.5): a conversation's node classes are
  exactly the classes whose theories the starting theory imports, and
  re-evaluating a registering theory cannot register twice -- the fresh
  theory value carries the registration once.*)
structure Registrations = Theory_Data
(
  type T =
    (serial *
     {python_packages : string list, make : env -> Remote_Procedure_Calling.callback'}) list
  val empty = []
  val merge = Library.merge (eq_fst op =)
)

fun register_callback {python_packages} f =
  Registrations.map (cons (serial (), {python_packages = python_packages, make = f}))

(*** Conversation ***)

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
     ret_schema = packBool, function = Slots.exists slots, timeout = NONE},
  Remote_Procedure_Calling.mk_callback
    {name = "TAT.check_new_theory_short_name", arg_schema = unpackString,
     ret_schema = packOption packString, function = Loader.check_new_theory_short_name,
     timeout = NONE}
]

fun start' procedure thy =
  let
    val _ = Loader.check_parallel_proofs ()
    val slots = Slots.create ()
    val theories = Theories.create ()
    (*This unpacker must not raise: mk_callback advances the input stream only
      after a successful unpack (contrib/Isabelle_RPC/Tools/RPC.ML:446-449), so
      an exception here leaves the connection mid-message and every later
      callback misparses.  It is safe because Slots.slot only builds two
      closures and touches no table -- do not "validate the slot exists" here.*)
    val env : env = {
      slot_unpacker = fn src =>
        let val (name, src') = unpackString src in (Slots.slot slots name, src') end,
      begin_theory = begin_theory theories,
      end_theory = end_theory theories}
    val regs = rev (Registrations.get thy)
    val callbacks = map (fn (_, {make, ...}) => make env) regs @ framework_callbacks slots
    (*the dispatch table would silently keep one of two same-named callbacks*)
    val _ = (case duplicates (op =) (map #name callbacks)
              of [] => ()
               | names => error ("Callback registered twice: " ^ commas_quote names))
    val packages = distinct (op =) (maps (#python_packages o #2) regs)
    val _ = Output_Routing.install ()
    val conversation : (string list, unit) Remote_Procedure_Calling.command =
      {name = procedure, arg_schema = packList packString, ret_schema = unpackUnit,
       callback = callbacks, timeout = NONE}
  in
    Remote_Procedure_Calling.call_command conversation packages
      handle Remote_Procedure_Calling.Remote_Calling_Failure {message, ...} => error message
  end

end

fun start thy =
  (Remote_Procedure_Calling.load ["isabelle_theory_agent"]; start' "launch_TAT" thy)

end
