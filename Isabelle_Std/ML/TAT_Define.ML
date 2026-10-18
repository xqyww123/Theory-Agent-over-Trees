(*  Title:      Isabelle_Std/ML/TAT_Define.ML

The ML half of the plugin's `Define` (isabelle_theory_agent/std/define.py;
docs/node_classes/DEFINE.md §6): the definition as the Python class sends it, made
by `definition`, or by `function (sequential, no_partials)` or plain `function` and
`termination` with each goal closed as `fun` closes it -- `pat_completeness auto`,
`lexicographic_order` -- or, when the method fails, admitted, the open goal kept in
the node's slot for it; the command and the two methods recorded.  The proof
construction and the proof check are `TAT_Proof_Obligation`'s, one call per open
obligation.
*)

structure TAT_Define =
struct

datatype answer = datatype TAT_Framework.answer

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

(*the definition as the Python class sends it: the constants -- each its name,
  its type or none, its mixfix annotation as `mixfix_text` writes it or none --,
  the equations, `auto_reduction`, every piece of Isabelle text in its ascii, and
  the recorded form -- the command to run again -- or NONE for the command to be
  decided (COMMON.md §5)*)
type definition = (string * string option * string option) list * string list * bool * string option

val unpack_definition =
  unpackTuple4 (unpackList (unpackTuple3 (unpackString, unpackOption unpackString, unpackOption unpackString)),
                unpackList unpackString, unpackBool, unpackOption unpackString)

(*the records (DEFINE.md §1): the form -- the command run --, and the method that
  closed each goal, NONE while the goal stands open*)
val pack_records = packTuple3 (packString, packOption packString, packOption packString)

val completeness_method = "pat_completeness auto"     (*what `fun` runs on each goal (fun.ML, gen_add_fun)*)
val termination_method = "lexicographic_order"

(*the two function commands, as the form names them: the first is `fun`'s
  configuration as Isar spells it (fun.ML, fun_config), the second the default*)
val sequential = "function (sequential, no_partials)"
val plain = "function"

fun config_of command =
  if command = sequential then Function_Fun.fun_config else Function_Common.default_config

(*Isar text read under the context's keywords: `by`'s one or two method texts
  (`by pat_completeness auto` is an initial and a terminal method) and
  `declare`'s attributes*)
val read_methods = TAT_Mixfix.read_text (Method.parse -- Scan.option Method.parse) "method"
val read_attribs = TAT_Mixfix.read_text Parse.attribs "attributes"

(*the constants as the commands take them, the annotation read under the local
  theory's keywords (COMMON.md §4)*)
fun fixes lthy constants =
  map (fn (name, typ, syntax) => (Binding.name name, typ, TAT_Mixfix.read lthy syntax)) constants

(*** the form (DEFINE.md §6) ***)

(*the equations read with the constants fixed at their types and syntax:
  `definition` for one constant and one equation that is an unconditional
  equality whose left side is the constant applied to distinct variables or to
  nothing and whose right side does not mention it; `function` otherwise -- a
  conditional or quantified equation, or no equation at all, is left to it.  A
  read that fails raises, the definition's failure*)
fun is_definition ctxt ((constants, equations, _, _) : definition) =
  (case (constants, equations) of
    ([(name, typ, syntax)], [equation]) =>
      let
        val (_, ctxt') =
          Proof_Context.add_fixes
            [(Binding.name name, Option.map (Syntax.read_typ ctxt) typ, TAT_Mixfix.read ctxt syntax)] ctxt
        val prop = Syntax.read_prop ctxt' equation
        fun is_the_constant (Free (x, _)) = x = name
          | is_the_constant _ = false
        val sides =
          (case try Logic.dest_equals prop of
            SOME sides => SOME sides
          | NONE => try (HOLogic.dest_eq o HOLogic.dest_Trueprop) prop)
      in
        (case sides of
          NONE => false
        | SOME (lhs, rhs) =>
            let val (head, args) = strip_comb lhs in
              is_the_constant head andalso forall is_Free args andalso not (has_duplicates (op aconv) args)
              andalso not (exists_subterm is_the_constant rhs)
            end)
      end
  | _ => false)

(*** the transitions ***)

fun definition_transition ((constants, equations, _, _) : definition) =
  Toplevel.make "definition" Position.none
  |> Toplevel.local_theory NONE NONE (fn lthy =>
      Specification.definition_cmd (SOME (the_single (fixes lthy constants))) [] []
        (Binding.empty_atts, the_single equations) false lthy |> #2)

(*`function (sequential, no_partials)` under `fun`'s configuration (fun.ML,
  fun_config), or plain `function` under the default one*)
fun function_transition command ((constants, equations, _, _) : definition) =
  Toplevel.make "function" Position.none
  |> Toplevel.local_theory_to_proof NONE NONE (fn lthy =>
      Function.function_cmd (fixes lthy constants) (map (fn eq => ((Binding.empty_atts, eq), [], [])) equations)
        (config_of command) false lthy)

val termination_transition =
  Toplevel.make "termination" Position.none
  |> Toplevel.local_theory_to_proof NONE NONE (Function.termination_cmd NONE)

(*`by <methods>` as the terminal proof of the toplevel goal `st` holds*)
fun by_transition methods st =
  Toplevel.make "by" Position.none
  |> Toplevel.end_proof (K (Proof.global_terminal_proof (read_methods (Toplevel.context_of st) methods)))

(*`declare <facts> <attributes>` (Pure.thy's command, Specification.theorems_cmd)*)
fun declare_transition facts attributes =
  Toplevel.make "declare" Position.none
  |> Toplevel.local_theory NONE NONE (fn lthy =>
      Specification.theorems_cmd ""
        [(Binding.empty_atts, map (fn fact => (Facts.named fact, read_attribs lthy attributes)) facts)] [] false lthy
      |> #2)

(*** the evaluation (DEFINE.md §6) ***)

(*a goal opened into `slot`, closed by `method` as a terminal proof -- the slot
  emptied, the method recorded -- or, the method failing, admitted, the open goal
  left in the slot and nothing recorded*)
fun close slot method st =
  let val _ = #put slot (SOME st) in
    (case TAT_Framework.apply_transition (by_transition method st) st of
      Accepted st' => (#put slot NONE; Accepted (st', SOME method))
    | Refused _ => TAT_Proof_Obligation.admit st |> TAT_Framework.map_answer (rpair NONE))
  end

(*from the input state to the state after the definition's commands, with the
  records; both slots emptied first, the evaluation alone writing them.  The
  command is the recorded one when the message carries it; with none, decided
  here (DEFINE.md §6): `definition` by the equations' shape, else `function
  (sequential, no_partials)`, and plain `function` on the same equations when
  that command refuses them -- the fallback of the command alone, not of the
  steps after it*)
fun run (definition as (constants, _, auto_reduction, mode) : definition) {completeness, termination} st =
  let
    val _ = (#put completeness NONE; #put termination NONE)
    val names = map #1 constants
    val apply = TAT_Framework.apply_transition
    fun declare facts attributes st = if null facts then Accepted st else apply (declare_transition facts attributes) st
    fun by_definition st =
      apply (definition_transition definition) st
      |> TAT_Framework.bind_answer (declare (if auto_reduction then [the_single names ^ "_def"] else []) "[simp]")
      |> TAT_Framework.map_answer (rpair ("definition", NONE, NONE))
    fun opened command st = apply (function_transition command definition) st
    fun finished command st_open =
      close completeness completeness_method st_open
      |> TAT_Framework.bind_answer (fn (st', cm) =>
          apply termination_transition st'
          |> TAT_Framework.bind_answer (close termination termination_method)
          |> TAT_Framework.bind_answer (fn (st'', tm) =>
              declare (if auto_reduction then [] else map (fn n => n ^ ".simps") names) "[simp del]" st''
              |> TAT_Framework.map_answer (rpair (command, cm, tm))))
    fun by_function command st = opened command st |> TAT_Framework.bind_answer (finished command)
  in
    (case mode of
      SOME "definition" => by_definition st
    | SOME command => by_function command st
    | NONE =>
        if is_definition (Toplevel.context_of st) definition then by_definition st
        else
          (case opened sequential st of
            Accepted st_open => finished sequential st_open
          | Refused _ => by_function plain st))
  end

(*the callback: the input slot, the two goal slots, the resulting slot and the
  definition; one operation into the resulting slot, a failure anywhere its
  messages, both goal slots emptied*)
val _ = Theory.setup (TAT_Framework.register_callback {python_packages = ["isabelle_theory_agent.std"]} (fn env =>
  {name = "TAT.Define.evaluate",
   on_interrupt = Remote_Procedure_Calling.Reraise,
   arg_schema =
     unpackTuple5 (#slot_unpacker env, #slot_unpacker env, #slot_unpacker env, #slot_unpacker env, unpack_definition),
   ret_schema = TAT_Framework.pack_answer pack_records,
   function = fn (input, completeness, termination, result, definition) =>
     let
       val answer =
         TAT_Common_Nodes.operation' result (fn () =>
           run definition {completeness = completeness, termination = termination} (#get input ()))
       val _ = (case answer of Refused _ => (#put completeness NONE; #put termination NONE) | Accepted _ => ())
     in answer end,
   timeout = NONE}))

end

end
