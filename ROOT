session Theory_Agent_over_Trees = Isabelle_RPC +
  directories "test"
  theories Theory_Agent_over_Trees

session TAT_Std in "Isabelle_Std/TAT_Std" = Minilang_AoA +
  theories TAT_Std

session TAT_Isabelle_Std in Isabelle_Std = Minilang_AoA +
  sessions Theory_Agent_over_Trees TAT_Std
  theories TAT_Isabelle_Std
