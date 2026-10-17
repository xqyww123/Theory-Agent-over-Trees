theory TAT_Define_Helper
  imports Minilang_AoA.Minilang_AoA
begin

text \<open>A theory in no heap, for test_define.py's end-to-end case: a theory of the
  forest that imports it runs its \<open>by aoa\<close> under AoA's test driver, the scripted
  agent the case registers in AoA's test table, instead of a language model.\<close>

declare [[AoA_driver = "test.tat_define_termination"]]

end
