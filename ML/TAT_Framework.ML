(*  Title:      ML/TAT_Framework.ML
    Author:     Qiyuan Xu

The framework of TAT's evaluator (docs/MODULE_STRUCTURE.md §2): state slots,
the theory table, the theory loader, running commands, node classes, and the
conversation.  Knows no node class.

A conversation's state slot table and theory table are created by one call
of `start`, as AoA's state table is by one `IsaMini.AoA` call
(contrib/Isa-Mini/Agent/agent_server.ML:937), and emptied by `TAT.reset`
when a fresh conversation begins on the same process (docs/ARCHITECTURE.md
§9); the callbacks are that call's too.  A node class reaches the
conversation only through the `env` handed to its registered function.
*)

signature TAT_FRAMEWORK =
sig
  (*** Bugs (docs/EXCEPTIONS.md §1) ***)
  exception Bug of string             (*an invariant TAT broke -- the framework's or
                                        a node class's; a callback never turns it
                                        into data*)
  val bug_message : exn -> string option
                                      (*the first Bug in an exception: bare, in a
                                        Par_Exn or in an Exn.EXCEPTIONS; found before
                                        any interrupt the exception holds beside it*)
  val interrupted : exn -> bool       (*an interrupt of either kind: bare, in a Par_Exn
                                        or in an Exn.EXCEPTIONS*)

  (*** State slots (§2.1) ***)
  type slot = {
    get : unit -> Toplevel.state,           (*a Bug when the slot holds nothing: a
                                              node runs only after its input is
                                              written (ARCHITECTURE §3.5)*)
    put : Toplevel.state option -> unit     (*NONE deletes*)
  }

  (*** Running commands (§2.4) ***)
  datatype output_message =
    Writeln of string | Tracing of string | Warning of string |
    Information of string | Legacy of string
  structure Output_Routing : sig
    val new_buffer : string -> unit     (*a buffer for what is printed under this id
                                          in Position.thread_data*)
    val take_buffer : string -> output_message list
                                        (*its messages, oldest first, plain text; the
                                          buffer gone*)
  end
  val apply_transition : Toplevel.transition -> Toplevel.state -> Toplevel.state option * string list
                                          (*one transition through Toplevel.command_errors
                                            true: the state, or its errors as messages --
                                            `operation`'s shape (TAT_Common_Nodes.ML)*)

  (*** Node classes (§2.5) ***)
  type env = {
    slot_unpacker : slot MessagePackBinIO.Unpack.unpacker,
                      (*reads a slot name off the wire, on this conversation's table*)
    begin_theory : {session_name : string, master_dir : Path.T} ->
                   Thy_Header.header -> Toplevel.state,
                      (*§2.4's, imports resolved through this conversation's tables*)
    end_theory : Toplevel.state -> unit,
                      (*§2.4's, the result put into this conversation's theory table*)
    fork_job : {id : int, work : unit -> unit} -> unit
                      (*§2.4's: the work as a Future task, its end reported to
                        Python by the remote procedure job_finished*)
  }
  val register_callback :
    {python_packages : string list} ->    (*the class's Python half; imported at
                                            conversation start, filling the kind
                                            table (§4.4)*)
    (env -> ('a, 'b) Remote_Procedure_Calling.callback) -> theory -> theory
                                          (*the record; the framework makes the wire
                                            callback, logging every run (§2.5)*)

  (*** Conversation (§2.6) ***)
  val start' : string -> theory list -> string -> int -> string -> unit
                      (*the Python procedure that is the conversation, called once
                        its package is loaded; the theories whose ancestries name
                        the node classes; the working directory; the port to serve
                        on; the agent client's name*)
  val start : theory list -> string -> int -> string -> unit
                      (*start' "launch_TAT"*)
  val compile : theory list -> string -> bool * string list
                      (*the same theories and working directory, through the Python
                        procedure compile_TAT (docs/COMPILATION.md §5): whether every
                        tree was written, and the report's lines*)
end

structure TAT_Framework : TAT_FRAMEWORK =
struct

(*** Bugs ***)

(*A callback answers every failure of its operation as data, so an exception
  escaping one is a bug by definition (docs/EXCEPTIONS.md §1); this is the
  one TAT raises on purpose -- the framework or a node class -- which a
  callback's exception handling lets through.*)
exception Bug of string

(*A Bug may arrive wrapped: inside the Par_Exn a parallel load releases, or
  inside an Exn.EXCEPTIONS.  One test for `operation`, the callback wrapper
  and fork_job; a Bug beside an interrupt is still a Bug.*)
fun bug_message (Bug message) = SOME message
  | bug_message (Exn.EXCEPTIONS exns) = get_first bug_message exns
  | bug_message exn =
      (case Par_Exn.dest exn of
        SOME exns => get_first bug_message exns
      | NONE => NONE)

(*An interrupt of either kind -- bare, or hidden in the Par_Exn a parallel
  load releases (Par_Exn keeps a breakdown, dropping only a proper interrupt)
  or in an Exn.EXCEPTIONS.  One test for `operation` and fork_job.*)
fun interrupted (Exn.EXCEPTIONS exns) = exists interrupted exns
  | interrupted exn =
      Exn.is_interrupt exn orelse
      (case Par_Exn.dest exn of
        SOME exns => exists interrupted exns
      | NONE => false)

(*** The log (docs/LOGGING.md §5) ***)

structure Log = struct

(*JSON, enough for one record's line: Isabelle/ML has no JSON of its own*)
datatype json =
  String of string | Int of int | Real of real | Bool of bool |
  Array of json list | Object of (string * json) list

local
  fun escape c =
    (case c of
      #"\"" => "\\\"" | #"\\" => "\\\\" | #"\n" => "\\n" | #"\r" => "\\r" | #"\t" => "\\t"
    | _ =>
        if Char.ord c < 32
        then "\\u" ^ StringCvt.padLeft #"0" 4 (Int.fmt StringCvt.HEX (Char.ord c))
        else str c)
in
  fun string_of (String s) = enclose "\"" "\"" (String.translate escape s)
    | string_of (Int i) = signed_string_of_int i
    | string_of (Real r) = Real.fmt (StringCvt.FIX (SOME 6)) r
    | string_of (Bool b) = if b then "true" else "false"
    | string_of (Array xs) = enclose "[" "]" (commas (map string_of xs))
    | string_of (Object fields) =
        enclose "{" "}" (commas (map (fn (k, v) => string_of (String k) ^ ":" ^ string_of v) fields))
end

fun seconds time = Real (Time.toReal time)

(*a record's `ts`: UTC, to the microsecond*)
fun timestamp () =
  let
    val now = Time.now ()
    val micro = Time.toMicroseconds now mod 1000000
  in
    Date.fmt "%Y-%m-%dT%H:%M:%S" (Date.fromTimeUniv now) ^ "." ^
    StringCvt.padLeft #"0" 6 (LargeInt.toString micro) ^ "Z"
  end

(*One conversation's log: the records made before the Python side has named
  the directory, held latest first; then the file isabelle.jsonl there.  A
  write never raises and reports nothing: what stops it stops the Python
  side too, which reports.*)
datatype state = Held of string list | Writing of Path.T
type T = state Synchronized.var

fun create () : T = Synchronized.var "TAT.log" (Held [])

(*The process's current log, an empty one from this file's load, so the
  theories a start loads before the conversation begins are recorded;
  TAT.reset installs a fresh one; a job keeps the one it found at its fork.*)
val current : T Synchronized.var = Synchronized.var "TAT.log.current" (create ())
fun get_current () = Synchronized.value current
fun renew () = Synchronized.change current (K (create ()))

val never_raising = Event_Log.never_raising (K ())

fun record (log : T) {event, level, data} =
  never_raising (fn () =>
    let
      val line =
        string_of (Object [("ts", String (timestamp ())), ("category", String "isabelle"),
          ("event", String event), ("level", String level), ("data", Object data)]) ^ "\n"
    in
      Synchronized.change log
        (fn Held lines => Held (line :: lines)
          | writing as Writing path => (File.append path line; writing))
    end)

(*the Python side names the directory once it exists (LOGGING.md §5): the
  records held so far go there first*)
fun tell (log : T) directory =
  never_raising (fn () =>
    let val path = Path.append directory (Path.basic "isabelle.jsonl") in
      Synchronized.change log
        (fn Held lines => (if null lines then () else File.append_list path (rev lines); Writing path)
          | Writing _ => Writing path)
    end)

end

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
  | NONE => raise Bug ("State slot " ^ quote name ^ " holds no state"))

fun put' name (SOME st) = Symtab.update (name, st)
  | put' name NONE = Symtab.delete_safe name

fun put (slots : T) name st = Synchronized.change slots (put' name st)

(*afterwards `dst` holds what `src` holds, nothing included -- by construction*)
fun copy (slots : T) (src, dst) =
  Synchronized.change slots (fn tab => put' dst (Symtab.lookup tab src) tab)

fun delete (slots : T) names = Synchronized.change slots (fold Symtab.delete_safe names)

fun exists (slots : T) name = Symtab.defined (Synchronized.value slots) name

(*a fresh conversation on the same process (docs/ARCHITECTURE.md §9): how
  many it cleared, for the `reset` record*)
fun clear (slots : T) = Synchronized.change_result slots (fn tab => (Symtab.size tab, Symtab.empty))

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

(*delete_safe: a tree whose header failed never stored a value*)
fun delete (theories : T) names = Synchronized.change theories (fold Symtab.delete_safe names)

fun clear (theories : T) =
  Synchronized.change_result theories (fn tab => (Symtab.size tab, Symtab.empty))

end

(*** Theory loader ***)

structure Loader = struct

(*Thy_Info is process-global and has no internal mutual exclusion, so the
  lock is process-global too (EVALUATOR_DESIGN §6: one lock around every
  call).*)
val lock = Synchronized.var "TAT.thy_load" ()

(*EVALUATOR_DESIGN §6, measured: at 3 -- the interactive default -- a theory
  whose proof fails commits, and the error surfaces later; below 3 a failing
  load raises and commits nothing.  Checked by every load and at conversation
  start.*)
fun check_parallel_proofs () =
  let val n = ! Multithreading.parallel_proofs
  in if n < 3 then ()
     else error ("TAT requires parallel_proofs below 3, but this process runs at " ^
                 string_of_int n)
  end

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
  was not cancelled.

  The import is the one name the Isabelle session layout gives the file
  (EVALUATOR_DESIGN §6): <session>.<short name>, or the short name alone when
  the layout declares it global -- never a path, never a bare non-global
  name, never a qualified name whose short name is global.  Under the empty
  qualifier use_theories' own import_name leaves such a name unchanged, so
  the theory loads under exactly this name.*)
fun load import =
  Synchronized.change lock (fn () =>
    let
      val _ = check_parallel_proofs ()
      val loaded_before = Thy_Info.get_names ()
      val start = Time.now ()
      val result =
        Exn.capture_body (fn () => Thy_Info.use_theories (Options.default ()) "" [import])
      val residue =
        Thread_Attributes.uninterruptible (fn _ => fn () =>
          map Exn.Exn (maps Task_Queue.group_status (Execution.reset ()))) ()
      val _ =
        (case Exn.get_exn result of
          SOME exn => if Exn.is_interrupt_proper exn then Exn.reraise exn else ()
        | NONE => ())
      val _ = Par_Exn.release_all (result :: residue)
      (*the record `theory_loaded` (LOGGING.md §4), one per theory the load
        added, each with the load's whole duration*)
      val duration = Log.seconds (Time.now () - start)
      val log = Log.get_current ()
      val _ =
        List.app (fn name =>
            Log.record log {event = "theory_loaded", level = "info",
              data = [("name", Log.String name), ("duration", duration)]})
          (subtract (op =) loaded_before (Thy_Info.get_names ()))
    in () end)

(*The last two steps of EVALUATOR_DESIGN §2's order: the base heap, then a
  load from source -- of a theory whose file the Isabelle session layout
  knows, nothing by path (§2.3), and never under a qualified name whose
  short name the layout declares global (`HOL.Main`): Isabelle would load
  the file a second time as a theory of that name, and a later theory
  importing both dies of the duplicate short name (EVALUATOR_DESIGN §7).
  Also how a theory named to the launcher (§5) is fetched, before any
  conversation -- so no theory table here.  Wording: RENDER_BASELINES.md.*)
fun fetch pos theory_name =
  let
    val global_short_name =
      Long_Name.is_qualified theory_name andalso
      is_some (Resources.global_theory (Long_Name.base_name theory_name))
  in
    (case Thy_Info.lookup_theory theory_name of
      SOME thy => thy
    | NONE =>
        if is_some (Resources.find_theory_file theory_name) andalso not global_short_name
        then (load (theory_name, pos); Thy_Info.get_theory theory_name)
        else error ("Fail to load `" ^ theory_name ^ "` because it is not found."))
  end

(*Import resolution in the order of EVALUATOR_DESIGN §2, behind one
  Resources.import_name call (§7).*)
fun resolve theories {session_name, master_dir} (import, pos) =
  let val {theory_name, ...} = Resources.import_name session_name master_dir import in
    (case Theories.lookup theories theory_name of
      SOME thy => thy
    | NONE => fetch pos theory_name)
  end

(*a theory the launcher names (§5), by its SESSION.THEORY name: the guard
  refuses any unqualified name, even a global one fetch alone would load,
  with the launcher's own sentence.  import_name supplies Isabelle's own
  refusals of a `.thy` suffix and of a path-shaped name.*)
fun fetch_named name =
  if Long_Name.is_qualified name
  then fetch Position.none (#theory_name (Resources.import_name "" Path.current name))
  else error ("The plugin theory must be fully qualified (SESSION.THEORY), but provided " ^
              quote name)

(*Isabelle's own predicates on a name, asked instead of copying its lists
  (docs/COMPILATION.md §2): the Scala function TAT.reserved_name of
  lib/tat.jar answers the words of those that hold -- `file`
  (Path.is_reserved), `theory` (Sessions.illegal_theory), `session`
  (Sessions.illegal_session).  The launcher's process answers the call
  through its protocol loop (§5).*)
fun reserved kinds name =
  exists (member (op =) kinds) (space_explode " " (Scala.function1 "TAT.reserved_name" name))

(*The Isabelle half of the short-name check (§2.3), one of three answers in
  this order: a loaded theory bears the short name -- its long name, which
  for a global theory is the short name itself; none does but the Isabelle
  session layout declares the name global -- reserved, since theory_name
  would leave a tree so named unqualified -- or Isabelle refuses it as a
  file or theory name; free.  The rejection and its wording are Python's
  (RENDER_BASELINES.md).*)
datatype short_name_answer = Taken of string | Reserved | Free

fun check_new_theory_short_name name =
  let val short = Long_Name.base_name name in
    (case List.find (fn n => Long_Name.base_name n = short) (Thy_Info.get_names ()) of
      SOME long => Taken long
    | NONE =>
        if is_some (Resources.global_theory short) orelse reserved ["file", "theory"] short
        then Reserved else Free)
  end

(*Whether the Isabelle session layout knows a session of the name (§2.3).
  Resources.check_session fails on an unknown one; the context serves its
  report only.*)
fun is_known_session name =
  can (Resources.check_session \<^context>) (name, Position.none)

(*`Session.gen`'s one question (§2.3), answered with the first defect: the
  name reserved as a file or session name; the name one the Isabelle session
  layout knows; an option Isabelle does not know, or whose value is of the
  wrong type -- its place among the options and Isabelle's message; a parent
  the layout does not know -- `parent` is NONE when the forest settled it.
  The options are applied as Isabelle reads a ROOT, by the Scala function
  TAT.check_options of lib/tat.jar (§5), so that what passes here the final
  reading accepts.  The forest half and every rejection are Python's
  (SESSION_AND_THEORY.md §1).*)
datatype session_answer =
  Session_Ok | Name_Reserved | Name_Known | Option_Refused of int * string | Parent_Unknown

fun check_session (name, parent, options) =
  let
    fun refused () =
      (case Scala.function "TAT.check_options" (maps (fn (option, value) => [option, value]) options) of
        [] => NONE
      | [i, msg] => SOME (Value.parse_int i, msg)
      | answer => raise Fail ("TAT.check_options answered " ^ commas_quote answer))
  in
    if reserved ["file", "session"] name then Name_Reserved
    else if is_known_session name then Name_Known
    else
      (case refused () of
        SOME answer => Option_Refused answer
      | NONE =>
          (case parent of
            SOME session => if is_known_session session then Session_Ok else Parent_Unknown
          | NONE => Session_Ok))
  end

end

(*** Running commands ***)

datatype output_message =
  Writeln of string | Tracing of string | Warning of string |
  Information of string | Legacy of string

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
  fallback.  Called at conversation start (§2.6), before any operation runs
  (EVALUATOR_DESIGN §4).*)
val installed = Synchronized.var "TAT.output_routing" false
fun install () =
  Synchronized.change installed (fn true => true | false =>
    (List.app (fn (r, mk) => let val fallback = ! r in r := route mk fallback end) channels;
     true))

end

(*§2.4: one transition, built in ML by its operation, applied through
  Toplevel.command_errors true.  The first argument `true` is Isabelle's
  interactive flag and load-bearing: `sorry` is refused without it
  (EVALUATOR_DESIGN §1).  The errors are the messages, markup stripped, as
  the output side is in Output_Routing.route.  An interrupt is folded to
  ([], NONE) by command_errors -- Par_Exn.dest yields no messages for a
  proper interrupt; stock re-raises the case (command.ML:247-249,
  toplevel.ML:652-654) and so does TAT: a cancellation unwinds the
  conversation whole.*)
fun apply_transition tr st =
  (case Toplevel.command_errors true tr st of
    (_, SOME st') => (SOME st', [])
  | ([], NONE) => Isabelle_Thread.raise_interrupt ()
  | (errors, NONE) => (NONE, map (Protocol_Message.clean_output o #2 o #1) errors))

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
    (*theory names carry no dot (MCP_SPECIFICATION §2), so a qualified name
      here is a framework bug -- and letting it through would unhook the
      theory-table key from (session, tree)*)
    val _ =
      if Long_Name.is_qualified name
      then raise Bug ("Theory header names a qualified theory: " ^ quote name)
      else ()
    val qualified = #theory_name (Resources.import_name session_name master_dir name)
    val parents = map (Loader.resolve theories context) (#imports header)
    val header' = Thy_Header.make (qualified, name_pos) (#imports header) (#keywords header)
    val tr =
      Toplevel.make Thy_Header.theoryN name_pos
      |> Toplevel.init_theory (fn () => Resources.begin_theory master_dir header' parents)
  in
    (case apply_transition tr (Toplevel.make_state NONE) of
      (SOME st, _) => st
    | (NONE, messages) => error (cat_lines messages))
  end

(*§2.4: the value the theory table stores.  The state must have run the
  node's `end` already; its position lives in the node's text, not here.*)
fun end_theory theories st = Theories.put theories (Toplevel.end_theory Position.none st)

(*What ends the launcher (§2.6, §5): the protocol message TAT.finished, a
  code and messages in build_session_finished's shape; it takes the first.*)
fun tell_finished (answer : int * string list) =
  answer
  |> let open XML.Encode in pair int (list string) end
  |> single
  |> Output.protocol_message [Markup.function "TAT.finished"]

(*** Evaluation jobs (§2.4; docs/CONSTRUCT_INTERACTION.md §3.3) ***)

structure Jobs = struct

(*What a job's work came to, as Python's job_finished is told it: on the wire
  ["ok"], ["messages", [...]] or ["bug", <message>].  A work TAT cancelled
  reports nothing: the Python side cancels only a job it has dropped, and
  TAT.reset ends the conversation that would hear.*)
datatype failure = Passed | Messages of string list | Bug_Raised of string

local open MessagePackBinIO.Pack in

fun pack_failure Passed = packList packString ["ok"]
  | pack_failure (Messages messages) = packPair (packString, packList packString) ("messages", messages)
  | pack_failure (Bug_Raised message) = packPair (packString, packString) ("bug", message)

(*the remote procedure, through Isabelle_RPC's registry; it answers at once,
  so one left unanswered this long means the Python side answers no more*)
val report_timeout = Time.fromSeconds 300
val finished : (int * failure, unit) Remote_Procedure_Calling.command =
  {name = "job_finished", arg_schema = packPair (packInt, pack_failure),
   ret_schema = MessagePackBinIO.Unpack.unpackUnit, callback = [], timeout = SOME report_timeout}

end

(*the wire's value, for the log*)
fun json_of_failure Passed = Log.Array [Log.String "ok"]
  | json_of_failure (Messages messages) =
      Log.Array [Log.String "messages", Log.Array (map Log.String messages)]
  | json_of_failure (Bug_Raised message) = Log.Array [Log.String "bug", Log.String message]

(*the exception a work raised, read as `operation` reads one (TAT_Common_Nodes.ML):
  a Bug before anything else, an interrupt as no failure at all, and an
  exception rendering to no message -- which would read as success -- a bug*)
fun failure_of exn =
  (case bug_message exn of
    SOME message => SOME (Bug_Raised message)
  | NONE =>
      if interrupted exn then NONE
      else
        (case map (#2 o #1) (Runtime.exn_messages exn) of
          [] => SOME (Bug_Raised "fork_job: an exception with no message")
        | messages => SOME (Messages messages)))

(*A job from its fork to its end.  A task cancelled before it began never
  runs -- Future skips its body -- so its end is the canceller's to record:
  the phase says who writes job_ended, exactly once per job_forked, and
  whether an interrupt of the work was TAT's own cancel.  The log is the one
  current at the fork (LOGGING.md §5).*)
datatype phase = Pending | Running | Cancelled | Ended
type job = {future : unit future, phase : phase Synchronized.var, log : Log.T}
type T = job Inttab.table Synchronized.var

fun create () : T = Synchronized.var "TAT.jobs" Inttab.empty

fun ended (log : Log.T) id failure duration =
  Log.record log {event = "job_ended", level = "info",
    data = [("id", Log.Int id)] @
      (case failure of SOME failure => [("failure", json_of_failure failure)] | NONE => []) @
      [("duration", Log.seconds duration), ("cancelled", Log.Bool (is_none failure))]}

(*the report, made with interrupts deferred by its caller: one that cannot be
  delivered is recorded, and the task ends; one the Python side left
  unanswered is beyond repair, and ends the process as a disaster -- the
  launcher prints the record's message and exits 2*)
fun report (log : Log.T) id failure =
  (case Exn.capture_body (fn () => Remote_Procedure_Calling.call_command finished (id, failure)) of
    Exn.Res () => ()
  | Exn.Exn exn =>
      if Exn.is_interrupt exn then Exn.reraise exn
      else
        let
          val unanswered = (case exn of Remote_Procedure_Calling.Read_Timeout => true | _ => false)
          val reason =
            (case exn of
              Remote_Procedure_Calling.Remote_Calling_Failure {message, ...} => message
            | _ =>
                if unanswered
                then "it did not answer within " ^
                  string_of_int (Time.toSeconds report_timeout) ^ " seconds"
                else Runtime.exn_message exn)
          val message =
            "The result of evaluation job " ^ string_of_int id ^
            " could not be reported to the Python side: " ^ reason
          val _ =
            Log.record log {event = "report_undelivered", level = "warning",
              data = [("id", Log.Int id), ("failure", json_of_failure failure),
                      ("message", Log.String message)]}
        in if unanswered then tell_finished (2, [message]) else () end)

(*§2.4's fork_job: the work as a Future task of a group of its own, the
  future kept under the id; only the work itself can be interrupted -- what
  follows it, the report included, runs with interrupts deferred, so a work
  that ended is always reported.  The table changes with the fork in one
  uninterruptible step: no task runs that the table does not hold.*)
fun fork (jobs : T) {id, work} =
  let
    val log = Log.get_current ()
    val phase = Synchronized.var "TAT.job" Pending
    fun task () =
      Thread_Attributes.uninterruptible_body (fn run =>
        if Synchronized.change_result phase (fn Pending => (true, Running) | p => (false, p)) then
          let
            val start = Time.now ()
            val result = Exn.capture_body (fn () => run work ())
            val cancelled = Synchronized.change_result phase (fn p => (p = Cancelled, Ended))
            val _ = Synchronized.change jobs (Inttab.delete_safe id)
            (*an interrupt nobody of TAT sent leaves a job Python still waits for: a bug*)
            val failure =
              (case result of
                Exn.Res () => SOME Passed
              | Exn.Exn exn =>
                  (case failure_of exn of
                    NONE =>
                      if cancelled then NONE
                      else SOME (Bug_Raised "fork_job: the work was interrupted, and TAT had not cancelled it")
                  | failure => failure))
            val _ = ended log id failure (Time.now () - start)
            val _ =
              (case failure of
                SOME (Bug_Raised message) =>
                  Log.record log {event = "bug", level = "error",
                    data = [("message", Log.String message), ("job", Log.Int id)]}
              | _ => ())
          in Option.app (report log id) failure end
        else ())
  in
    Thread_Attributes.uninterruptible_body (fn _ =>
      Synchronized.change jobs (fn tab =>
        if Inttab.defined tab id
        then raise Bug ("Evaluation job " ^ string_of_int id ^ " forked twice")
        else
          let
            val _ = Log.record log {event = "job_forked", level = "info", data = [("id", Log.Int id)]}
            val params =
              {name = "TAT.job", group = SOME (Future.new_group NONE), deps = [], pri = 0,
               interrupts = true}
            val future = singleton (Future.forks params) task
          in Inttab.update (id, {future = future, phase = phase, log = log}) tab end))
  end

(*a job taken off the table: one still Pending ends here; a Running one is
  marked, and ends when the interrupt reaches its work*)
fun cancel (id, {future, phase, log} : job) =
  (if Synchronized.change_result phase
        (fn Pending => (true, Ended) | Running => (false, Cancelled) | p => (false, p))
   then ended log id NONE Time.zeroTime else ();
   Future.cancel future)

(*TAT.job_cancel: the ids looked up, their futures cancelled; an id that is
  not there -- its job ended -- is not an error*)
fun cancel_ids (jobs : T) ids =
  Thread_Attributes.uninterruptible_body (fn _ =>
    Synchronized.change_result jobs (fn tab =>
      (map_filter (fn id => Option.map (pair id) (Inttab.lookup tab id)) ids,
       fold Inttab.delete_safe ids tab))
    |> List.app cancel)

(*TAT.reset: every job's future cancelled; how many, for the `reset` record*)
fun cancel_all (jobs : T) =
  Thread_Attributes.uninterruptible_body (fn _ =>
    let val taken = Synchronized.change_result jobs (fn tab => (Inttab.dest tab, Inttab.empty))
    in List.app cancel taken; length taken end)

end

(*** Node classes ***)

type env = {
  slot_unpacker : slot MessagePackBinIO.Unpack.unpacker,
  begin_theory : {session_name : string, master_dir : Path.T} ->
                 Thy_Header.header -> Toplevel.state,
  end_theory : Toplevel.state -> unit,
  fork_job : {id : int, work : unit -> unit} -> unit
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

(*The framework makes every wire callback itself (§2.5), around the record's
  function: the log event `callback` -- how long the function ran, whether
  it returned, raised or was interrupted -- and `bug` when a Bug left it;
  the result released as it arrived.  The log is the one current when the
  callback began, so TAT.reset's own record lands in the conversation it
  ends.*)
fun make_callback ({name, on_interrupt, arg_schema, ret_schema, function, timeout}
                   : ('a, 'b) Remote_Procedure_Calling.callback) =
  Remote_Procedure_Calling.mk_callback
    {name = name, on_interrupt = on_interrupt, arg_schema = arg_schema, ret_schema = ret_schema,
     timeout = timeout,
     function = fn arg =>
       let
         val log = Log.get_current ()
         val start = Time.now ()
         val result = Exn.capture_body (fn () => function arg)
         val outcome =
           (case result of
             Exn.Res _ => "returned"
           | Exn.Exn exn => if Exn.is_interrupt exn then "interrupted" else "raised")
         val _ =
           Log.record log {event = "callback", level = "info",
             data = [("name", Log.String name), ("duration", Log.seconds (Time.now () - start)),
                     ("outcome", Log.String outcome)]}
         val _ =
           (case Option.mapPartial bug_message (Exn.get_exn result) of
             SOME message =>
               Log.record log {event = "bug", level = "error",
                 data = [("message", Log.String message), ("callback", Log.String name)]}
           | NONE => ())
       in Exn.release result end}

fun register_callback {python_packages} f =
  Registrations.map (cons (serial (), {python_packages = python_packages, make = make_callback o f}))

(*** Conversation ***)

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

(*the three answers on the wire, a tagged list: ["taken", <long name>],
  ["reserved"], ["free"]*)
fun pack_short_name_answer (Loader.Taken long) = packList packString ["taken", long]
  | pack_short_name_answer Loader.Reserved = packList packString ["reserved"]
  | pack_short_name_answer Loader.Free = packList packString ["free"]

(*the session check's answers in the same shape: ["ok"], ["name_reserved"],
  ["name_known"], ["option", <its index, in digits>, <Isabelle's message>],
  ["parent_unknown"]*)
fun pack_session_answer answer =
  packList packString
    (case answer of
      Loader.Session_Ok => ["ok"]
    | Loader.Name_Reserved => ["name_reserved"]
    | Loader.Name_Known => ["name_known"]
    | Loader.Option_Refused (i, msg) => ["option", string_of_int i, msg]
    | Loader.Parent_Unknown => ["parent_unknown"])

(*The Python side names the log directory, absolute (LOGGING.md §5, §7):
  the records held so far go there, and the launcher is told, as
  TAT.finished tells it.  The one framework callback a compile's command
  carries too (COMPILATION.md §5).*)
val log_directory =
  make_callback
    {name = "TAT.log_directory",
     on_interrupt = Remote_Procedure_Calling.Reraise,
     arg_schema = unpackString,
     ret_schema = packUnit,
     function = fn directory =>
       (Log.tell (Log.get_current ()) (Path.explode directory);
        Output.protocol_message [Markup.function "TAT.log_directory"] [XML.Encode.string directory]),
     timeout = NONE}

fun framework_callbacks (slots : Slots.T) (theories : Theories.T) (jobs : Jobs.T) = [
  make_callback
    {name = "TAT.state_copy",
     on_interrupt = Remote_Procedure_Calling.Reraise,
     arg_schema = unpackPair (unpackString, unpackString),
     ret_schema = packUnit, function = Slots.copy slots, timeout = NONE},
  make_callback
    {name = "TAT.state_delete",
     on_interrupt = Remote_Procedure_Calling.Reraise,
     arg_schema = unpackList unpackString,
     ret_schema = packUnit, function = Slots.delete slots, timeout = NONE},
  make_callback
    {name = "TAT.state_exists",
     on_interrupt = Remote_Procedure_Calling.Reraise,
     arg_schema = unpackString,
     ret_schema = packBool, function = Slots.exists slots, timeout = NONE},
  make_callback
    {name = "TAT.theory_delete",
     on_interrupt = Remote_Procedure_Calling.Reraise,
     arg_schema = unpackList unpackString,
     ret_schema = packUnit, function = Theories.delete theories, timeout = NONE},
  make_callback
    {name = "TAT.check_new_theory_short_name",
     on_interrupt = Remote_Procedure_Calling.Reraise,
     arg_schema = unpackString,
     ret_schema = pack_short_name_answer, function = Loader.check_new_theory_short_name,
     timeout = NONE},
  make_callback
    {name = "TAT.check_session",
     on_interrupt = Remote_Procedure_Calling.Reraise,
     arg_schema = unpackTuple3 (unpackString, unpackOption unpackString,
                                unpackList (unpackPair (unpackString, unpackString))),
     ret_schema = pack_session_answer, function = Loader.check_session, timeout = NONE},
  log_directory,
  (*the futures of the evaluation jobs whose ids it is given, cancelled (§2.4)*)
  make_callback
    {name = "TAT.job_cancel",
     on_interrupt = Remote_Procedure_Calling.Reraise,
     arg_schema = unpackList unpackInt,
     ret_schema = packUnit, function = Jobs.cancel_ids jobs, timeout = NONE},
  (*a fresh conversation begins on the same process: every job's future
    cancelled first, both tables emptied, recorded into this conversation's
    log, which a fresh one then replaces (LOGGING.md §5); a cancelled job's
    task ends later, into the log it found at its fork*)
  make_callback
    {name = "TAT.reset",
     on_interrupt = Remote_Procedure_Calling.Reraise,
     arg_schema = unpackUnit,
     ret_schema = packUnit,
     function = fn () =>
       let
         val futures_cancelled = Jobs.cancel_all jobs
         val slots_cleared = Slots.clear slots
         val theories_cleared = Theories.clear theories
         val _ =
           Log.record (Log.get_current ()) {event = "reset", level = "info",
             data = [("futures_cancelled", Log.Int futures_cancelled),
                     ("slots_cleared", Log.Int slots_cleared),
                     ("theories_cleared", Log.Int theories_cleared)]}
       in Log.renew () end,
     timeout = NONE}
]

(*Step 2 (§2.6), which a conversation and a compile share: the theories'
  registrations -- one reached through several ancestries counts once -- and
  their Python packages*)
fun collect theories =
  let val regs = distinct (eq_fst op =) (maps (rev o Registrations.get) theories)
  in (regs, distinct (op =) (maps (#python_packages o #2) regs)) end

(*What both entries end on (§2.6): the Python package loaded, its procedure
  called, a failure of the call an ERROR*)
fun call_python command arg =
  (Remote_Procedure_Calling.load ["isabelle_theory_agent"];
   Remote_Procedure_Calling.call_command command arg
     handle Remote_Procedure_Calling.Remote_Calling_Failure {message, ...} => error message)

fun start' procedure theories working_directory port client =
  let
    val _ = Loader.check_parallel_proofs ()
    (*the bound on the construction jobs running at once, as text: empty when
      unset, which the Python side takes as no bound (§4.6)*)
    val max_concurrent_construction_jobs = getenv "TAT_MAX_CONCURRENT_CONSTRUCTION_JOBS"
    val slots = Slots.create ()
    val theory_table = Theories.create ()
    val jobs = Jobs.create ()
    (*This unpacker must not raise: mk_callback advances the input stream only
      after a successful unpack (contrib/Isabelle_RPC/Tools/RPC.ML), so an
      exception here leaves the message pending on the connection and every later
      callback misparses.  It is safe because Slots.slot only builds two
      closures and touches no table -- do not "validate the slot exists" here.*)
    val env : env = {
      slot_unpacker = fn src =>
        let val (name, src') = unpackString src in (Slots.slot slots name, src') end,
      begin_theory = begin_theory theory_table,
      end_theory = end_theory theory_table,
      fork_job = Jobs.fork jobs}
    val (regs, packages) = collect theories
    val callbacks =
      map (fn (_, {make, ...}) => make env) regs @ framework_callbacks slots theory_table jobs
    (*the dispatch table would silently keep one of two same-named callbacks*)
    val _ = (case duplicates (op =) (map #name callbacks)
              of [] => ()
               | names => error ("Callback registered twice: " ^ commas_quote names))
    val _ = Output_Routing.install ()
    val conversation
          : (string list * string * int * string * string, unit) Remote_Procedure_Calling.command =
      {name = procedure,
       arg_schema = packTuple5 (packList packString, packString, packInt, packString, packString),
       ret_schema = unpackUnit, callback = callbacks, timeout = NONE}
  in
    call_python conversation
      (packages, working_directory, port, client, max_concurrent_construction_jobs)
  end

(*The compile's command carries the framework's TAT.log_directory and no
  class's callback: nothing a compile does can run anything in Isabelle
  (docs/COMPILATION.md §5).*)
fun compile theories working_directory =
  let
    val (_, packages) = collect theories
    val command : (string list * string, bool * string list) Remote_Procedure_Calling.command =
      {name = "compile_TAT", arg_schema = packPair (packList packString, packString),
       ret_schema = unpackPair (unpackBool, unpackList unpackString),
       callback = [log_directory], timeout = NONE}
  in call_python command (packages, working_directory) end

end

val start = start' "launch_TAT"

(*The handler of the two protocol commands the boot runs once this theory is
  loaded (§2.6, §5).  `entry` reads the command's arguments into the
  plugins' theory names and what to run on the loaded theories, which
  answers the code and the lines of a normal result.  Forked off the
  protocol loop -- which reads one message at a time, and answers the
  Scala.function calls of a loading theory -- as a plain Isabelle thread,
  inside no theory, interruptible as build_session's is
  (Pure/Build/build.ML); every path ends in TAT.finished, in
  build_session_finished's shape: the entry's answer, or 2 with the
  exception's messages -- "Interrupt" for an interrupt, "CRASHED" when the
  messages could not be rendered.*)
fun define_entry name (entry : string list -> string list * (theory list -> int * string list)) =
  Protocol_Command.define name (fn args =>
    let
      (*by name: \<^theory> here is this theory before TAT_Common_Nodes registers
        its node classes; Thy_Info holds the finished value*)
      val own_theory_name = Context.theory_long_name \<^theory>
      fun body () =
        let val (plugins, run) = entry args
        in run (map Loader.fetch_named (own_theory_name :: plugins)) end
      (*a terminal interrupt arrives as Interrupt_Breakdown, which
        exn_message_list does not name; the sic arm is build_session's*)
      fun messages exn =
        if Exn.is_interrupt exn then ["Interrupt"]
        else
          (case Exn.capture Runtime.exn_message_list exn of
            Exn.Res msgs => msgs
          | Exn.Exn _ (*sic!*) => ["CRASHED"])
      fun finished result =
        tell_finished (case result of Exn.Res answer => answer | Exn.Exn exn => (2, messages exn))
    in
      ignore (Isabelle_Thread.fork (Isabelle_Thread.params name) (fn () =>
        finished (Exn.capture_body (Future.interruptible_task body))))
    end)

(*TAT.start: the working directory, the port, the client's name, then the
  plugins' theory names; 0 when the conversation ended by start returning*)
val _ =
  define_entry "TAT.start"
    (fn working_directory :: port :: client :: plugins =>
          (plugins, fn theories =>
            (start theories working_directory (Value.parse_int port) client; (0, [])))
      | _ => raise Match)

(*TAT.compile: the working directory, then the plugins' theory names; the
  report's lines, with 0 when every tree was written and 1 when one was not*)
val _ =
  define_entry "TAT.compile"
    (fn working_directory :: plugins =>
          (plugins, fn theories =>
            let val (written, lines) = compile theories working_directory
            in (if written then 0 else 1, lines) end)
      | _ => raise Match)

end
