theory TAT_Std
  imports Minilang_AoA.Minilang_AoA
begin

text \<open>The theory every theory of a forest imports (docs/PLUGIN_SYSTEM.md §1): the
  \<open>aoa\<close> method, through Minilang_AoA, and the two AoA tasks a \<open>Define\<close>'s proof
  constructions run under (docs/node_classes/DEFINE.md §7), registered here once, so
  that AoA resolves them in the theory of every goal of the forest.  It sets the
  configuration option \<open>typedef_overloaded\<close> once, for every type definition of a
  forest (docs/node_classes/COMMON.md §4).  Nothing of the framework: a finished forest
  builds on this session alone.\<close>

declare [[typedef_overloaded]]

setup \<open>
  MiniLang_Agent_Plugin.register_task {python_packages = ["isabelle_theory_agent.std.define"]}
    {name = "TAT.pattern_completeness"}
  #> MiniLang_Agent_Plugin.register_task {python_packages = ["isabelle_theory_agent.std.define"]}
    {name = "TAT.termination"}
\<close>

end
