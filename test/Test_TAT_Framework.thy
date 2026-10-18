theory Test_TAT_Framework
  imports Theory_Agent_over_Trees.Theory_Agent_over_Trees
begin

text \<open>The test plugin (ai-artifacts/TEST_HARNESS_PLAN.md §5): the plugin the
  suite's \<open>isabelle TAT_mcp\<close> is started with.  It registers node-class-style
  callbacks against the state slot table and the theory pipeline -- the
  \<open>TAT_test.*\<close> probes the Isabelle-backed cases call -- and contributes no
  node class; its Python package is \<open>tat_test_plugin\<close>, named twice below on
  purpose.  The two checks that must fail before any conversation starts (a
  duplicated callback name, a rejected \<open>parallel_proofs\<close>) run below as plain
  ML while the theory loads, as does the one installation of the output
  routing through which \<open>TAT_Test_Lib.run_span\<close> reads a command's output.\<close>

ML \<open>
(*Avoid run_commands wherever possible: it registers each span in Isabelle's
  execution table, which a library load's Execution.reset wipes
  (docs/EVALUATOR_DESIGN.md §6), and nothing of the product uses it -- every
  operation builds its transition in ML and applies it through
  TAT_Framework.apply_transition (docs/MODULE_STRUCTURE.md §2.4).  It lives
  here, as test code, for the probes test_conversation.py runs Isar text
  with.*)
structure TAT_Test_Lib = struct

structure Output_Routing = struct

(*Agent-facing text leaves the process through the six Private_Output
  channels listed below (docs/MODULE_STRUCTURE.md §2.4).  Each is replaced
  once, with a function that routes a message by the id in
  Position.thread_data () into the buffer registered for that id, and falls
  back to the function it replaced when there is no id or no buffer.  The id
  travels with Future.fork (future.ML:452), so a message printed on a forked
  worker still reaches its command's buffer.*)

(*per id, the (kind, text) messages printed under it, newest first*)
val buffers : (string * string) list Symtab.table Synchronized.var =
  Synchronized.var "TAT_test.output_buffers" Symtab.empty

fun new_buffer id = Synchronized.change buffers (Symtab.update_new (id, []))

fun take_buffer id =
  Synchronized.change_result buffers (fn tab =>
    (rev (these (Symtab.lookup tab id)), Symtab.delete_safe id tab))

fun route kind fallback outputs =
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
              | SOME msgs => (true, Symtab.update (id, (kind, text) :: msgs) tab)))
        in if routed then () else fallback outputs end)

(*The channel set is data, so an omission is visible; each channel carries
  Isabelle's own name for it, the kind of its messages.  The urgent channel
  taught the lesson: the result block of lemma/theorem/definition prints
  through writeln_urgent_fn (proof_display.ML:322-328), a separate ref from
  writeln_fn; urgent output is writeln with an urgent property
  (isabelle_process.ML), hence the shared name.
  Deliberately not captured:
  - state_fn: proof states; the Python side reads states off the slots;
  - error_message_fn: errors travel structurally, in run_span's command
    records; a failed fork also prints its errors here (execution.ML:187),
    so capturing the channel would report them twice;
  - status_fn, report_fn, result_fn, system_message_fn, protocol_message_fn:
    PIDE protocol machinery, not text for an agent.*)
val channels = [
  (Private_Output.writeln_fn, Markup.writelnN),
  (Private_Output.writeln_urgent_fn, Markup.writelnN),
  (Private_Output.tracing_fn, Markup.tracingN),
  (Private_Output.warning_fn, Markup.warningN),
  (Private_Output.information_fn, Markup.informationN),
  (Private_Output.legacy_fn, Markup.legacyN)
]

(*Idempotent; the first call captures the process's current functions as the
  fallback.  Called once when this theory loads, before any conversation.*)
val installed = Synchronized.var "TAT_test.output_routing" false
fun install () =
  Synchronized.change installed (fn true => true | false =>
    (List.app (fn (r, kind) => Unsynchronized.change r (route kind)) channels; true))

end

type command_record = {
  source : string,                (*the command's text, sliced verbatim*)
  range : Position.range,         (*within the text handed to run_commands*)
  errors : string list,           (*TAT_Framework.messages_of_errors of the
                                    command's errors and its forks'*)
  output : (string * string) list (*kind and text, markup stripped*)
}

(*offsets count symbols, as Position offsets do*)
fun span_source symbols span =
  let
    val (pos1, pos2) = Command_Span.range span
    val i = the_default 1 (Position.offset_of pos1)
    val j = the_default i (Position.offset_of pos2)
  in implode (take (j - i) (drop (i - 1) symbols)) end

(*A fresh id per span.  The id slot of a position is the execution
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
                  raise TAT_Framework.Bug ("Failed to register execution " ^ id)
        val (errors, st') =
          Position.setmp_thread_data (Position.id_only id)
            (fn () => Toplevel.command_errors true (Toplevel.exec_id exec tr) st) ()
        val _ = Execution.join [exec]
        val fork_errors =
          maps Runtime.exn_messages (maps Task_Queue.group_status (Execution.peek exec))
        val output = Output_Routing.take_buffer id
        val all_errors = TAT_Framework.messages_of_errors (errors @ fork_errors)
      in
        (*a proper interrupt is folded to ([], NONE) by command_errors --
          Par_Exn.dest yields it no messages; stock re-raises the case
          (command.ML:247-249, toplevel.ML:655) and so does this harness.
          A failed fork is the command's failure -- its committed state
          carries a broken promise, so it is withheld -- keeping "errors
          nonempty iff no state" exact.*)
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

(*Split with Outer_Syntax.parse_spans, run each span through
  Toplevel.command_errors true, threading the state.  Tokenisation is one
  pass over the whole text (stock does the same, thy_info.ML:300), but each
  span is parsed against the state it runs in (stock: Command.read_span per
  element), so a command *implementation* an earlier span installed parses
  in a later one -- a new *keyword* does not, its token was lexed before it
  existed.  The init handed to parse_span is pure_syn.ML's own refusal, for
  a stray `theory` command mid-text.  One record per command; stops at a
  command that returns no state.*)
fun run_commands st text =
  let
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

(*records travel as (source, error messages, (kind, text) output) triples*)
fun serialize records =
  map (fn {source, errors, output, ...} : command_record =>
        (source, errors, output)) records

val pack_records =
  let open MessagePackBinIO.Pack in
    packList (packTuple3 (packString, packList packString,
      packList (packPair (packString, packString))))
  end

end
\<close>

ML \<open>
val _ = TAT_Test_Lib.Output_Routing.install ()
\<close>

setup \<open>
(*writes a state into the slot; the boolean picks which of two
  distinguishable states, so a copy that fabricates one is caught*)
let open MessagePackBinIO.Pack MessagePackBinIO.Unpack in
  TAT_Framework.register_callback {python_packages = ["tat_test_plugin"]} (fn env =>
    {name = "TAT_test.make",
      on_interrupt = Remote_Procedure_Calling.Reraise,
      arg_schema = unpackPair (#slot_unpacker env, unpackBool),
      ret_schema = packUnit,
      function = fn (slot, top) =>
        #put slot (SOME (Toplevel.make_state (if top then NONE else SOME \<^theory>))),
      timeout = NONE})
end
\<close>

setup \<open>
(*reads the slot's discriminator; on an empty slot the table raises a Bug,
  which escapes the callback unconverted (docs/EXCEPTIONS.md §1)*)
let open MessagePackBinIO.Pack in
  TAT_Framework.register_callback {python_packages = []} (fn env =>
    {name = "TAT_test.is_toplevel",
      on_interrupt = Remote_Procedure_Calling.Reraise,
      arg_schema = #slot_unpacker env,
      ret_schema = packBool,
      function = fn slot => Toplevel.is_toplevel (#get slot ()),
      timeout = NONE})
end
\<close>

setup \<open>
(*deletes through the slot handle: the `put NONE` route*)
let open MessagePackBinIO.Pack in
  TAT_Framework.register_callback {python_packages = []} (fn env =>
    {name = "TAT_test.delete",
      on_interrupt = Remote_Procedure_Calling.Reraise,
      arg_schema = #slot_unpacker env,
      ret_schema = packUnit,
      function = fn slot => #put slot NONE,
      timeout = NONE})
end
\<close>

setup \<open>
(*env's begin_theory: header text in, the post-`theory … begin` state into
  the slot.  The package list is deliberately repeated: deduplication is the
  framework's (§2.6).*)
let open MessagePackBinIO.Pack MessagePackBinIO.Unpack in
  TAT_Framework.register_callback {python_packages = ["tat_test_plugin"]} (fn env =>
    {name = "TAT_test.begin",
      on_interrupt = Remote_Procedure_Calling.Reraise,
      arg_schema = unpackPair (#slot_unpacker env,
                     unpackTuple3 (unpackString, unpackString, unpackString)),
      ret_schema = packUnit,
      function = fn (slot, (session_name, master_dir, src)) =>
        #put slot (SOME (#begin_theory env
          {session_name = session_name, master_dir = Path.explode master_dir}
          (Thy_Header.read Position.start src))),
      timeout = NONE})
end
\<close>

setup \<open>
(*run_commands from one slot into another.  A run that ends with no state
  leaves the target slot deleted -- `put NONE`.*)
let open MessagePackBinIO.Pack MessagePackBinIO.Unpack in
  TAT_Framework.register_callback {python_packages = []} (fn env =>
    {name = "TAT_test.run",
      on_interrupt = Remote_Procedure_Calling.Reraise,
      arg_schema = unpackPair (#slot_unpacker env,
                     unpackPair (#slot_unpacker env, unpackString)),
      ret_schema = TAT_Test_Lib.pack_records,
      function = fn (src, (dst, text)) =>
        let
          val (records, st') = TAT_Test_Lib.run_commands (#get src ()) text
          val _ = #put dst st'
        in TAT_Test_Lib.serialize records end,
      timeout = NONE})
end
\<close>

setup \<open>
(*two run_commands under Future.fork: output must land in each run's own
  records with no crossover.  Interleaving is best-effort -- with one free
  worker the runs serialise and the assertion still holds -- but when they
  do overlap, only routing by id keeps the buffers apart.*)
let open MessagePackBinIO.Pack MessagePackBinIO.Unpack in
  TAT_Framework.register_callback {python_packages = []} (fn env =>
    {name = "TAT_test.run_parallel",
      on_interrupt = Remote_Procedure_Calling.Reraise,
      arg_schema = unpackPair (#slot_unpacker env,
                     unpackPair (#slot_unpacker env, unpackPair (unpackString, unpackString))),
      ret_schema = packPair (TAT_Test_Lib.pack_records, TAT_Test_Lib.pack_records),
      function = fn (sa, (sb, (ta, tb))) =>
        let
          val sta = #get sa () and stb = #get sb ()
          val fa = Future.fork (fn () => TAT_Test_Lib.run_commands sta ta)
          val fb = Future.fork (fn () => TAT_Test_Lib.run_commands stb tb)
          val (ra, _) = Future.join fa and (rb, _) = Future.join fb
        in (TAT_Test_Lib.serialize ra, TAT_Test_Lib.serialize rb) end,
      timeout = NONE})
end
\<close>

setup \<open>
(*TAT_Common_Nodes.operation under each answer of its run and each kind of
  exception (docs/EXCEPTIONS.md §1): accepted, its state written and no
  message; a user-level error, as messages -- one carrying a position, its
  markup stripped; refused, its messages; a Bug, a refusal with no message,
  and an exception rendering to no message, all three escaping the callback;
  a proper interrupt, the refusal `Interrupt`, and a breakdown, escaping --
  each raised under the run itself and, through TAT_Framework.apply_transition
  on a `keep` transition, inside a transition -- its answer read as a total
  after_admission reads it, a refusal carrying on from the state given
  (COMMON.md §3), so that only an interrupt passing through apply_transition
  reaches the operation; a breakdown inside a Par_Exn, escaping whole.  The
  probe is Swallow: every case's conversation is served
  inside the run's one ML call, the one the harness's launch_TAT answers,
  which an interrupt re-raised under Reraise would unwind; Swallow's
  conditions (RPC.ML) hold here -- the interrupts are raised exceptions, no
  interrupt_thread, no Timeout.apply, the command's timeout NONE, and
  isabelle_driver.call raising IsabelleInterrupt as TAT_IsabelleError, an
  ordinary exception.*)
let open MessagePackBinIO.Pack MessagePackBinIO.Unpack
  fun transition raise_it =
    let val st = Toplevel.make_state NONE in
      (case TAT_Framework.apply_transition
          (Toplevel.make "tat_test" Position.none |> Toplevel.keep (fn _ => raise_it ())) st of
        TAT_Framework.Refused _ => TAT_Framework.Accepted st
      | accepted => accepted)
    end
in
  TAT_Framework.register_callback {python_packages = []} (fn env =>
    {name = "TAT_test.operation",
      on_interrupt = Remote_Procedure_Calling.Swallow,
      arg_schema = unpackPair (#slot_unpacker env, unpackString),
      ret_schema = packList packString,
      function = fn (slot, outcome) =>
        TAT_Common_Nodes.operation slot (fn () =>
          (case outcome of
            "ok" => TAT_Framework.Accepted (Toplevel.make_state NONE)
          | "error" => error "tat-user-error"
          | "position" => error ("tat-pos" ^ Position.here (Position.line 1))
          | "refused" => TAT_Framework.Refused ["tat-refused-1", "tat-refused-2"]
          | "bug" => raise TAT_Framework.Bug "tat-bug"
          | "nothing" => TAT_Framework.Refused []
          | "silent" => raise Exn.EXCEPTIONS []
          | "interrupt" => Isabelle_Thread.raise_interrupt ()
          | "breakdown" => raise Exn.Interrupt_Breakdown
          | "breakdown_wrapped" => raise (Par_Exn.make [Exn.Interrupt_Breakdown])
          | "transition_interrupt" => transition (fn () => Isabelle_Thread.raise_interrupt ())
          | "transition_breakdown" => transition (fn () => raise Exn.Interrupt_Breakdown)
          | _ => raise Fail ("unknown outcome " ^ outcome))),
      timeout = NONE})
end
\<close>

setup \<open>
(*env's end_theory: the slot's state -- after its `end` has run -- into the
  conversation's theory table*)
let open MessagePackBinIO.Pack in
  TAT_Framework.register_callback {python_packages = []} (fn env =>
    {name = "TAT_test.end",
      on_interrupt = Remote_Procedure_Calling.Reraise,
      arg_schema = #slot_unpacker env,
      ret_schema = packUnit,
      function = fn slot => #end_theory env (#get slot ()),
      timeout = NONE})
end
\<close>

setup \<open>
(*env's fork_job under each end of a job's work (docs/CONSTRUCT_INTERACTION.md
  §3.3): it passes, fails with a message carrying markup, which the report
  strips, raises a Bug, meets a proper interrupt or a breakdown, or waits for
  the file the case names to appear -- for as long as the case likes, or
  until it is cancelled*)
let open MessagePackBinIO.Pack MessagePackBinIO.Unpack in
  TAT_Framework.register_callback {python_packages = []} (fn env =>
    {name = "TAT_test.fork_job",
      on_interrupt = Remote_Procedure_Calling.Reraise,
      arg_schema = unpackPair (unpackInt, unpackPair (unpackString, unpackString)),
      ret_schema = packUnit,
      function = fn (id, (outcome, path)) =>
        #fork_job env {id = id, work = fn () =>
          if outcome = "produce" then SOME (packString "made")
          else
            ((case outcome of
              "pass" => ()
            | "fail" => error (Markup.markup Markup.keyword1 "tat-job-error")
            | "empty" => error ""
            | "bug" => raise TAT_Framework.Bug "tat-job-bug"
            | "interrupt" => Isabelle_Thread.raise_interrupt ()
            | "breakdown" => raise Exn.Interrupt_Breakdown
            | "wait" =>
                let val file = Path.explode path in
                  while not (File.exists file) do OS.Process.sleep (Time.fromMilliseconds 50)
                end
            | _ => raise Fail ("unknown outcome " ^ outcome)); NONE)},
      timeout = NONE})
end
\<close>

setup \<open>
(*the command spans a build cuts a text into under the keyword table of the
  theory in the slot, each as its source: what a file's header must stay one
  of (SESSION_AND_THEORY §2)*)
let open MessagePackBinIO.Pack MessagePackBinIO.Unpack in
  TAT_Framework.register_callback {python_packages = []} (fn env =>
    {name = "TAT_test.spans",
      on_interrupt = Remote_Procedure_Calling.Reraise,
      arg_schema = unpackPair (#slot_unpacker env, unpackString),
      ret_schema = packList packString,
      function = fn (slot, text) =>
        let val keywords = Thy_Header.get_keywords (Toplevel.theory_of (#get slot ()))
        in Outer_Syntax.parse_spans (Token.explode keywords Position.none text)
           |> map (fn span => implode (map Token.unparse (Command_Span.content span)))
        end,
      timeout = NONE})
end
\<close>

ML \<open>
(*a duplicated callback wire name is rejected before anything starts*)
let
  fun reg name =
    TAT_Framework.register_callback {python_packages = []} (fn _ =>
      {name = name,
        on_interrupt = Remote_Procedure_Calling.Reraise,
        arg_schema = MessagePackBinIO.Unpack.unpackUnit,
        ret_schema = MessagePackBinIO.Pack.packUnit, function = I, timeout = NONE})
  val thy' = \<^theory> |> reg "TAT_test.dup" |> reg "TAT_test.dup"
in
  case Exn.capture_body (fn () => TAT_Framework.start' "never_called" [thy'] "" 0 "") of
    Exn.Exn (ERROR msg) =>
      if String.isSubstring "Callback registered twice" msg then ()
      else raise Fail ("wrong rejection: " ^ msg)
  | Exn.Exn e => Exn.reraise e
  | Exn.Res _ => raise Fail "duplicate callback name was not rejected"
end
\<close>

ML \<open>
(*parallel_proofs at 3 -- the interactive default -- is rejected at
  conversation start, before anything is created (EVALUATOR_DESIGN §6)*)
let
  val orig = ! Multithreading.parallel_proofs
  val _ = Multithreading.parallel_proofs := 3
  val outcome = Exn.capture_body (fn () => TAT_Framework.start' "never_called" [\<^theory>] "" 0 "")
  val _ = Multithreading.parallel_proofs := orig
in
  case outcome of
    Exn.Exn (ERROR msg) =>
      if String.isSubstring "parallel_proofs" msg then ()
      else raise Fail ("wrong rejection: " ^ msg)
  | Exn.Exn e => Exn.reraise e
  | Exn.Res _ => raise Fail "parallel_proofs = 3 was not rejected"
end
\<close>

end
