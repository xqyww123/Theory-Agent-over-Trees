(*  Title:      Isabelle_Std/ML/TAT_Overloaded.ML

Whether a type needs `(overloaded)` (docs/node_classes/COMMON.md §4): the check
`typedef` makes when the option is not given (typedef.ML, primitive_typedef), which
`Typedef`, `Record` and `QuotientType` decide their recorded `overloaded` with, each
after one run of its command with the option.
*)

signature TAT_OVERLOADED =
sig
  val needed : theory -> string -> bool
    (*whether the type of that full name has open dependencies on overloaded
      definitions in the theory's definition table; the configuration option
      typedef_overloaded is not consulted*)
end

structure TAT_Overloaded : TAT_OVERLOADED =
struct

fun needed thy name = not (null (maps #2 (Defs.get_deps (Theory.defs_of thy) (Defs.Type, name))))

end
