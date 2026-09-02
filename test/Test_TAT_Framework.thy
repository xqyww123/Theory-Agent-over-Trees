theory Test_TAT_Framework
  imports "../Theory_Agent_over_Trees"
begin

text \<open>The ML half of the framework test.  It registers node-class-style
  callbacks against the state slot table and the theory pipeline, and starts
  a conversation whose Python side is \<open>tat_framework_ml_test.py\<close>; every
  assertion of the driven part lives there.  The two negative tests that
  must not start a conversation (a duplicated callback name, a rejected
  \<open>parallel_proofs\<close>) run below as plain ML.  Evaluate this theory to run the
  test (\<open>test/run_ml_framework_test.py\<close> does).\<close>

ML \<open>
structure TAT_Test_Lib = struct

fun output_message (TAT_Framework.Writeln s) = ("writeln", s)
  | output_message (TAT_Framework.Tracing s) = ("tracing", s)
  | output_message (TAT_Framework.Warning s) = ("warning", s)
  | output_message (TAT_Framework.Information s) = ("information", s)
  | output_message (TAT_Framework.Legacy s) = ("legacy", s)

(*records travel as (source, error messages, (kind, text) output) triples*)
fun serialize records =
  map (fn {source, errors, output, ...} : TAT_Framework.command_record =>
        (source, map (#2 o #1) errors, map output_message output)) records

val pack_records =
  let open MessagePackBinIO.Pack in
    packList (packTuple3 (packString, packList packString,
      packList (packPair (packString, packString))))
  end

end
\<close>

setup \<open>
(*writes a state into the slot; the boolean picks which of two
  distinguishable states, so a copy that fabricates one is caught*)
let open MessagePackBinIO.Pack MessagePackBinIO.Unpack in
  TAT_Framework.register_callback {python_packages = ["tat_framework_ml_test"]} (fn env =>
    Remote_Procedure_Calling.mk_callback {
      name = "TAT_test.make",
      arg_schema = unpackPair (#slot_unpacker env, unpackBool),
      ret_schema = packUnit,
      function = fn (slot, top) =>
        #put slot (SOME (Toplevel.make_state (if top then NONE else SOME \<^theory>))),
      timeout = NONE})
end
\<close>

setup \<open>
(*reads the slot's discriminator; on an empty slot this is the table's error*)
let open MessagePackBinIO.Pack in
  TAT_Framework.register_callback {python_packages = []} (fn env =>
    Remote_Procedure_Calling.mk_callback {
      name = "TAT_test.is_toplevel",
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
    Remote_Procedure_Calling.mk_callback {
      name = "TAT_test.clear",
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
  TAT_Framework.register_callback {python_packages = ["tat_framework_ml_test"]} (fn env =>
    Remote_Procedure_Calling.mk_callback {
      name = "TAT_test.begin",
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
    Remote_Procedure_Calling.mk_callback {
      name = "TAT_test.run",
      arg_schema = unpackPair (#slot_unpacker env,
                     unpackPair (#slot_unpacker env, unpackString)),
      ret_schema = TAT_Test_Lib.pack_records,
      function = fn (src, (dst, text)) =>
        let
          val (records, st') = TAT_Framework.run_commands (#get src ()) text
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
    Remote_Procedure_Calling.mk_callback {
      name = "TAT_test.run_parallel",
      arg_schema = unpackPair (#slot_unpacker env,
                     unpackPair (#slot_unpacker env, unpackPair (unpackString, unpackString))),
      ret_schema = packPair (TAT_Test_Lib.pack_records, TAT_Test_Lib.pack_records),
      function = fn (sa, (sb, (ta, tb))) =>
        let
          val sta = #get sa () and stb = #get sb ()
          val fa = Future.fork (fn () => TAT_Framework.run_commands sta ta)
          val fb = Future.fork (fn () => TAT_Framework.run_commands stb tb)
          val (ra, _) = Future.join fa and (rb, _) = Future.join fb
        in (TAT_Test_Lib.serialize ra, TAT_Test_Lib.serialize rb) end,
      timeout = NONE})
end
\<close>

setup \<open>
(*env's end_theory: the slot's state -- after its `end` has run -- into the
  conversation's theory table*)
let open MessagePackBinIO.Pack in
  TAT_Framework.register_callback {python_packages = []} (fn env =>
    Remote_Procedure_Calling.mk_callback {
      name = "TAT_test.end",
      arg_schema = #slot_unpacker env,
      ret_schema = packUnit,
      function = fn slot => #end_theory env (#get slot ()),
      timeout = NONE})
end
\<close>

ML \<open>
(*a duplicated callback wire name is rejected before anything starts*)
let
  fun reg name =
    TAT_Framework.register_callback {python_packages = []} (fn _ =>
      Remote_Procedure_Calling.mk_callback {
        name = name, arg_schema = MessagePackBinIO.Unpack.unpackUnit,
        ret_schema = MessagePackBinIO.Pack.packUnit, function = I, timeout = NONE})
  val thy' = \<^theory> |> reg "TAT_test.dup" |> reg "TAT_test.dup"
in
  case Exn.capture_body (fn () => TAT_Framework.start' "never_called" thy') of
    Exn.Exn (ERROR msg) =>
      if String.isSubstring "Callback registered twice" msg then ()
      else raise Fail ("wrong rejection: " ^ msg)
  | Exn.Exn e => Exn.reraise e
  | Exn.Res _ => raise Fail "duplicate callback name was not rejected"
end
\<close>

ML \<open>
(*parallel_proofs <> 1 is rejected at conversation start, before anything
  is created (EVALUATOR_DESIGN §6: 3 is the interactive default)*)
let
  val orig = ! Multithreading.parallel_proofs
  val _ = Multithreading.parallel_proofs := 3
  val outcome = Exn.capture_body (fn () => TAT_Framework.start' "never_called" \<^theory>)
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

ML \<open>Remote_Procedure_Calling.load ["tat_framework_ml_test"]\<close>

ML \<open>TAT_Framework.start' "TAT_test.drive" \<^theory>\<close>

end
