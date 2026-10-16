(*  Title:      Isabelle_Std/ML/TAT_Proof_Obligation.ML

The ML half of the plugin's `Proof_Obligation` (isabelle_theory_agent/std/common.py;
docs/node_classes/COMMON.md §3): the goal a class's command opens, admitted and never
proved in the tree, with the class's commands after the admission; the proof
construction, AoA's standard entry on that goal; the proof check, the proof replayed
on it.
*)

signature TAT_PROOF_OBLIGATION =
sig
  val register :
    {name : string,
     message : 'm MessagePackBinIO.Unpack.unpacker,
     open_goal : 'm -> Toplevel.state -> (Toplevel.state * 'a) TAT_Framework.answer,
     after_admission : 'm -> Toplevel.state -> Toplevel.state * 'b,
     records : ('a * 'b) MessagePackBinIO.Pack.packer} -> theory -> theory
    (*registers a class's evaluation callback (COMMON.md §3), built from the
      callback's name, the message's unpacker, the class's two steps -- each a
      function of the message -- and the packer of what they yield.  The
      arguments are the input slot, `goal_state`, the resulting slot and the
      message.  `open_goal`, from the input state to the state with the goal
      open and what the class records -- refused with messages when the
      command, or a check the class makes on the open goal, refuses the input
      -- runs under `operation'` into `goal_state`; then, as one operation
      into the resulting slot, the half of `sorry` that ends a toplevel goal
      and `after_admission`, total from the admitted state.  The answer is
      `Refused` with the messages, or `Accepted` with the pair of what the
      two steps yielded, packed by TAT_Framework.pack_answer: on the wire
      [[msgs], nil] or [[], [a, b]].  When either operation answers
      `Refused`, `goal_state` is emptied -- a rerun of a `ready` node
      releases nothing, so an earlier run's goal would stand there -- and
      the resulting slot is written only when both answer `Accepted`; a
      proper interrupt is a refusal, its one message `Interrupt`; a Bug and
      every other interrupt are re-raised*)
end

structure TAT_Proof_Obligation : TAT_PROOF_OBLIGATION =
struct

datatype answer = datatype TAT_Framework.answer

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

(*the half of `sorry` that ends a toplevel goal (Isar_Cmd.global_skip_proof)*)
val admit_transition =
  Toplevel.make "sorry" Position.none |> Toplevel.end_proof Proof.global_skip_proof

(*the body of a class's evaluation callback: `register`'s contract; each
  step is applied to the message inside its operation, so that whatever the
  step does on the message is the operation's too*)
fun evaluate (input, goal, result) open_goal after_admission message =
  let
    val answer =
      (case TAT_Common_Nodes.operation' goal (fn () => open_goal message (#get input ())) of
        Accepted a =>
          TAT_Common_Nodes.operation' result (fn () =>
            TAT_Framework.apply_transition admit_transition (#get goal ())
            |> TAT_Framework.map_answer (after_admission message))
          |> TAT_Framework.map_answer (pair a)
      | Refused messages => Refused messages)
    val _ = (case answer of Refused _ => #put goal NONE | Accepted _ => ())
  in answer end

fun register {name, message, open_goal, after_admission, records} =
  TAT_Framework.register_callback {python_packages = ["isabelle_theory_agent.std"]} (fn env =>
    {name = name,
     on_interrupt = Remote_Procedure_Calling.Reraise,
     arg_schema = unpackTuple4 (#slot_unpacker env, #slot_unpacker env, #slot_unpacker env, message),
     ret_schema = TAT_Framework.pack_answer records,
     function = fn (input, goal, result, m) =>
       evaluate (input, goal, result) open_goal after_admission m,
     timeout = NONE})

(*the product on the wire (COMMON.md §3): the method text and the two times of
  its replay in milliseconds, thread CPU then wall, as the store orders them*)
val pack_product = packTuple3 (packString, packInt, packInt)
val unpack_product = unpackTuple3 (unpackString, unpackInt, unpackInt)

(*the goal `goal_state` holds: the Proof.state's context and goal*)
fun goal_of get =
  let val {context, goal, ...} = Proof.goal (Toplevel.proof_of (get ()))
   in (context, goal) end

(*the proof construction (COMMON.md §3): one call of AoA's standard entry on the
  goal, the proof store read and written on AoA's own path, forked as the job's
  work; its product the proof.  The agent's give-up is the failure's message, as
  the `aoa` method renders it.  AoA's Python half is served by this process: the
  plugin's package imports it.*)
val _ = Theory.setup (TAT_Framework.register_callback {python_packages = []} (fn env =>
  {name = "TAT.Proof_Obligation.construct",
    on_interrupt = Remote_Procedure_Calling.Reraise,
    arg_schema = unpackPair (#slot_unpacker env, unpackInt),
    ret_schema = packUnit,
    function = fn (goal, id) =>
      let val (ctxt, sequent) = goal_of (#get goal) in
        #fork_job env {id = id, work = fn () =>
          let
            (*the two give-ups the `aoa` method renders, rendered as it renders
              them — the agent's, and the engine's own failure; any other
              Auto_Fail is re-raised.  Sync raises them at the call, the join
              joins a value*)
            val (times, text) =
              let val (fut, _) =
                    MiniLang_Agent_AoA.hammer_or_AoA'
                      {fact_override = Sledgehammer_Fact.no_fact_override, proof_id = NONE,
                       hammer_timeout = NONE, async_mode = Phi_Sledgehammer_Solver.Sync,
                       read_store = SOME true, write_store = SOME true,
                       task = MiniLang_Agent_AoA.usual, user_operations = []} ctxt sequent
              in Future.join fut end
              handle exn as MiniLang_Agent_AoA.Agent_Give_Up _ => MiniLang_Agent_AoA.method_error exn
                   | exn as Phi_Sledgehammer_Solver.Auto_Fail _ => MiniLang_Agent_AoA.method_error exn
            val (cpu, wall) = Phi_Proof_Store.ms_of_times times
          in SOME (pack_product (text, cpu, wall)) end}
      end,
    timeout = NONE}))

(*the proof check (COMMON.md §3): the stored product replayed on the same goal
  through the function AoA exports, forked as the job's work; no theorem is one
  empty error -- the replay says only that it failed; an interrupt is re-raised
  for fork_job to read -- a proper one TAT did not send the check's failure
  `Interrupt` (MODULE_STRUCTURE §2.4); anything else the replay raises is a
  bug, AoA's own classification of it, and ends the conversation*)
val _ = Theory.setup (TAT_Framework.register_callback {python_packages = []} (fn env =>
  {name = "TAT.Proof_Obligation.check",
    on_interrupt = Remote_Procedure_Calling.Reraise,
    arg_schema = unpackTuple3 (#slot_unpacker env, unpack_product, unpackInt),
    ret_schema = packUnit,
    function = fn (goal, (text, cpu, wall), id) =>
      let val (ctxt, sequent) = goal_of (#get goal) in
        #fork_job env {id = id, work = fn () =>
          let
            val replayed =
              (case Exn.capture_body (fn () =>
                      Proof_Store_AoA.replay_record (ctxt, sequent)
                        (Phi_Proof_Store.times_of_ms (cpu, wall), text)) of
                Exn.Res replayed => replayed
              | Exn.Exn exn =>
                  if TAT_Framework.interrupted exn then Exn.reraise exn
                  else raise TAT_Framework.Bug ("the proof check's replay raised: " ^ Runtime.exn_message exn))
          in (case replayed of SOME _ => NONE | NONE => error "") end}
      end,
    timeout = NONE}))

end

end
