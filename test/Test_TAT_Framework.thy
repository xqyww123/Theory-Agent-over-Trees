theory Test_TAT_Framework
  imports "../Theory_Agent_over_Trees"
begin

text \<open>The ML half of the framework test.  It registers three
  node-class-style callbacks against the state slot table and starts a
  session whose Python side is \<open>tat_framework_ml_test.py\<close>; every assertion
  lives there.  Evaluate this theory to run the test
  (\<open>test/run_ml_framework_test.py\<close> does).\<close>

setup \<open>
(*writes a state into the slot; the boolean picks which of two
  distinguishable states, so a copy that fabricates one is caught*)
let open MessagePackBinIO.Pack MessagePackBinIO.Unpack in
  TAT_Framework.register_callback (fn env =>
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
  TAT_Framework.register_callback (fn env =>
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
  TAT_Framework.register_callback (fn env =>
    Remote_Procedure_Calling.mk_callback {
      name = "TAT_test.clear",
      arg_schema = #slot_unpacker env,
      ret_schema = packUnit,
      function = fn slot => #put slot NONE,
      timeout = NONE})
end
\<close>

ML \<open>Remote_Procedure_Calling.load ["tat_framework_ml_test"]\<close>

ML \<open>TAT_Framework.start' "TAT_test.drive" \<^theory>\<close>

end
