(*  Title:      Isabelle_Std/ML/TAT_Overloaded.ML

Whether a type needs `(overloaded)` (docs/node_classes/COMMON.md §4): the check
`typedef` makes when the option is not given (typedef.ML, primitive_typedef), and
the type's full name as `Typedecl` declared it, read off a toplevel state.  `Typedef`
and `QuotientType` decide their recorded `overloaded` with it through
TAT_Proof_Obligation.decide, `Record` after one run of its command with the option.
On HOL alone, so that a raw ML process on HOL evaluates the file and test/test_common.py
pins `needed` and `needed_at`.
*)

signature TAT_OVERLOADED =
sig
  val needed : theory -> string -> bool
    (*whether the type of that full name has open dependencies on overloaded
      definitions in the theory's definition table; the configuration option
      typedef_overloaded is not consulted*)
  val needed_at : Toplevel.state -> binding -> bool
    (*`needed` on the state's theory under the type's full name: the theory's
      naming at theory level, the local theory's inside a `Context` or `Locale`,
      which carries its qualifier*)
end

structure TAT_Overloaded : TAT_OVERLOADED =
struct

fun needed thy name = not (null (maps #2 (Defs.get_deps (Theory.defs_of thy) (Defs.Type, name))))

fun needed_at st b =
  let val gthy = Toplevel.generic_theory_of st
  in needed (Context.theory_of gthy) (Context.cases Sign.full_name Local_Theory.full_name gthy b) end

end
