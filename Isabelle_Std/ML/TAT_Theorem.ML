(*  Title:      Isabelle_Std/ML/TAT_Theorem.ML

The ML half of the plugin's `Theorem` (isabelle_theory_agent/std/theorem.py;
docs/node_classes/THEOREM.md §6, §7): the statement opened and admitted, never
proved in the tree; the proof construction, AoA's standard entry on the goal
so opened; the proof check, the proof replayed on that goal.
*)

structure TAT_Theorem =
struct

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

(*the statement as the Python class sends it: the kind, the fact's name, the
  `for_any` variables with their types, the premises, the conclusion -- every
  term and type in its ascii*)
type statement =
  string * string * (string * string option) list * (string * string) list * string

val unpack_statement =
  unpackTuple5 (unpackString, unpackString,
    unpackList (unpackPair (unpackString, unpackOption unpackString)),
    unpackList (unpackPair (unpackString, unpackString)),
    unpackString)

(*the `lemma` command's own transition in its long form (Pure.thy's `theorem`);
  the kind names the transition alone, Isabelle's kind being Thm.theoremK for
  every one of the four commands*)
fun statement_transition ((kind, name, for_any, premises, conclusion) : statement) =
  Toplevel.make kind Position.none
  |> Toplevel.local_theory_to_proof' NONE NONE
      (Specification.theorem_cmd true Thm.theoremK NONE (K I) (Binding.name name, []) []
        [Element.Fixes (map (fn (v, T) => (Binding.name v, T, NoSyn)) for_any),
         Element.Assumes (map (fn (p, t) => ((Binding.name p, []), [(t, [])])) premises)]
        (Element.Shows [(Binding.empty_atts, [(conclusion, [])])]))

(*the half of `sorry` that ends a toplevel goal (Isar_Cmd.global_skip_proof)*)
val admit_transition =
  Toplevel.make "sorry" Position.none |> Toplevel.end_proof Proof.global_skip_proof

(*the statement's names Isabelle would quote in this theory
  (Thy_Header.print_name): the fact's, each variable's, each premise's*)
fun reserved thy ((_, name, for_any, premises, _) : statement) =
  filter (fn n => Thy_Header.print_name thy n <> n) (name :: map #1 for_any @ map #1 premises)

(*the two transitions in turn from the input slot's state: the goal, open and
  no step taken, into `goal_state`; the admitted fact into the resulting slot.
  A failure of either is the statement's: `goal_state` emptied -- a rerun of a
  `ready` node releases nothing, so an earlier run's goal would stand there --
  the resulting slot left to the framework, the messages answered.*)
val _ = Theory.setup (TAT_Framework.register_callback {python_packages = []} (fn env =>
  {name = "TAT.Theorem.evaluate",
    on_interrupt = Remote_Procedure_Calling.Reraise,
    arg_schema = unpackTuple4 (#slot_unpacker env, #slot_unpacker env, #slot_unpacker env,
                               unpack_statement),
    ret_schema = packTuple3 (packBool, packList packString, packList packString),
    function = fn (input, goal, result, statement) =>
      let
        val st = #get input ()
        val errors =
          TAT_Common_Nodes.operation goal (fn () =>
            TAT_Framework.apply_transition (statement_transition statement) st)
        val errors =
          if null errors
          then TAT_Common_Nodes.operation result (fn () =>
                 TAT_Framework.apply_transition admit_transition (#get goal ()))
          else errors
      in
        if null errors
        then (true, [], reserved (Toplevel.theory_of (#get result ())) statement)
        else (#put goal NONE; (false, errors, []))
      end,
    timeout = NONE}))

(*the product on the wire (THEOREM.md §1): the method text and the two times of
  its replay in milliseconds, thread CPU then wall, as the store orders them*)
val pack_product = packTuple3 (packString, packInt, packInt)
val unpack_product = unpackTuple3 (unpackString, unpackInt, unpackInt)

(*the goal `goal_state` holds (§7): the Proof.state's context and goal*)
fun goal_of get =
  let val {context, goal, ...} = Proof.goal (Toplevel.proof_of (get ()))
   in (context, goal) end

(*the proof construction (§7): one call of AoA's standard entry on the goal, the
  proof store read and written on AoA's own path, forked as the job's work; its
  product the proof.  The agent's give-up is the failure's message, as the `aoa`
  method renders it.  AoA's Python half is served by this process: its package
  is named here, so that the conversation imports it.*)
val _ = Theory.setup (TAT_Framework.register_callback {python_packages = ["IsaMini.AoA"]} (fn env =>
  {name = "TAT.Theorem.construct",
    on_interrupt = Remote_Procedure_Calling.Reraise,
    arg_schema = unpackPair (#slot_unpacker env, unpackInt),
    ret_schema = packUnit,
    function = fn (goal, id) =>
      let val (ctxt, sequent) = goal_of (#get goal) in
        #fork_job env {id = id, work = fn () =>
          let
            val (fut, _) =
              MiniLang_Agent_AoA.hammer_or_AoA'
                {fact_override = Sledgehammer_Fact.no_fact_override, proof_id = NONE,
                 hammer_timeout = NONE, async_mode = Phi_Sledgehammer_Solver.Sync,
                 read_store = SOME true, write_store = SOME true,
                 task = MiniLang_Agent_AoA.usual, user_operations = []} ctxt sequent
              handle MiniLang_Agent_AoA.Agent_Give_Up (reason, detail, _) =>
                error (MiniLang_Agent_AoA.banner_of reason ^ "\n" ^ detail)
            val (times, text) = Future.join fut
            val (cpu, wall) = Phi_Proof_Store.ms_of_times times
          in SOME (pack_product (text, cpu, wall)) end}
      end,
    timeout = NONE}))

(*the proof check (§7): the stored product replayed on the same goal through
  the function AoA exports, forked as the job's work; no theorem is one empty
  error -- the replay says only that it failed*)
val _ = Theory.setup (TAT_Framework.register_callback {python_packages = []} (fn env =>
  {name = "TAT.Theorem.check",
    on_interrupt = Remote_Procedure_Calling.Reraise,
    arg_schema = unpackTuple3 (#slot_unpacker env, unpack_product, unpackInt),
    ret_schema = packUnit,
    function = fn (goal, (text, cpu, wall), id) =>
      let val (ctxt, sequent) = goal_of (#get goal) in
        #fork_job env {id = id, work = fn () =>
          (case Proof_Store_AoA.replay_record (ctxt, sequent)
                  (Phi_Proof_Store.times_of_ms (cpu, wall), text) of
            SOME _ => NONE
          | NONE => error "")}
      end,
    timeout = NONE}))

end

end
