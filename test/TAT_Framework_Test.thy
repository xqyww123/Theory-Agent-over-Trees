theory TAT_Framework_Test
  imports "../Theory_Agent_over_Trees"
begin

text \<open>The ML half of the framework test.  It registers two node-class-style
  callbacks against the state slot table and starts a session whose Python
  side is \<open>tat_framework_ml_test.py\<close>; every assertion lives there.
  Evaluate this theory to run the test (test/test_ml_framework.py does).\<close>

ML \<open>
local open MessagePackBinIO.Pack in

(*writes a fresh toplevel state into the slot*)
val _ = TAT_Framework.register_callback (fn env =>
  Remote_Procedure_Calling.mk_callback {
    name = "TAT_test.make",
    arg_schema = #slot_unpacker env,
    ret_schema = packUnit,
    function = fn slot => #put slot (SOME (Toplevel.make_state NONE)),
    timeout = NONE})

(*reads the slot; on an empty slot this is the table's error*)
val _ = TAT_Framework.register_callback (fn env =>
  Remote_Procedure_Calling.mk_callback {
    name = "TAT_test.is_toplevel",
    arg_schema = #slot_unpacker env,
    ret_schema = packBool,
    function = fn slot => Toplevel.is_toplevel (#get slot ()),
    timeout = NONE})

end
\<close>

ML \<open>Remote_Procedure_Calling.load ["tat_framework_ml_test"]\<close>

ML \<open>TAT_Framework.start' "TAT_test.drive"\<close>

end
