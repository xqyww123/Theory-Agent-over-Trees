theory TAT_Lib_Rel
  imports Main
begin

text \<open>Imported by a slash-relative path (\<open>lib/TAT_Lib_Rel\<close>) in the framework
  test: the path resolves against the tree's master_dir, never the process
  working directory.\<close>

definition tat_lib_rel_z :: nat where "tat_lib_rel_z = 2"

end
