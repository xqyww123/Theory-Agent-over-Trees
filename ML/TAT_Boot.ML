(*  Title:      ML/TAT_Boot.ML
    Author:     Qiyuan Xu

The boot (docs/MODULE_STRUCTURE.md §5): the one file the launcher loads
before TAT's theory exists, as the Isabelle process's prelude.  Compiled by
Poly/ML's own compiler, outside any theory: Standard ML over Isabelle's
structures, no antiquotations.  Defines the protocol command TAT.boot, whose
arguments are those of TAT.start (TAT_Framework.ML): the working directory,
the port, then the plugins' theory names.
*)

val _ =
  Protocol_Command.define_bytes "TAT.boot" (fn args =>
    let
      (*the launcher's answer on a failure before the hand-off; TAT.start
        answers every later path, rendering the exception the same way
        (TAT_Framework.ML)*)
      fun messages exn =
        if Exn.is_interrupt exn then ["Interrupt"]
        else
          (case Exn.capture Runtime.exn_message_list exn of
            Exn.Res msgs => msgs
          | Exn.Exn _ (*sic!*) => ["CRASHED"])
      fun finished exn =
        Output.protocol_message [Markup.function "TAT.finished"]
          [let open XML.Encode in pair int (list string) (1, messages exn) end]
      fun boot () =
       ((*the isabelle.Session's handshake, Prover.options, set it to 3 for any
          positive option value (Pure/System/isabelle_process.ML,
          init_options_interactive); the loader needs it below 3
          (EVALUATOR_DESIGN §6)*)
        Multithreading.parallel_proofs := Options.default_int "parallel_proofs";
        Thy_Info.use_theories (Options.default ()) ""
          [("Theory_Agent_over_Trees.Theory_Agent_over_Trees", Position.none)];
        Protocol_Command.run "TAT.start" args)
    in
      (*forked: the protocol loop reads one message at a time, and a loading
        theory's Scala.function calls are answered through it*)
      ignore (Isabelle_Thread.fork (Isabelle_Thread.params "TAT.boot") (fn () =>
        (case Exn.capture_body (Future.interruptible_task boot) of
          Exn.Res () => ()
        | Exn.Exn exn => finished exn)))
    end);
