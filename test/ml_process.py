"""Isabelle probes on a raw ML process (not a pytest module): `isabelle
ML_process -l HOL` through a harness's `run_tool`, for what the std harness
cannot host — it loads the plugin's theory whole and offers no probe.  The
program begins with a theory `Probe` on the heap's `Main`, `after thy
text`, which runs Isar text on a theory and answers the theory after it,
and `in_theory thy files`, which evaluates ML files inside the theory's
context — the environment an `ML_file` of a theory has, HOL's structures
visible, as the plugin's theory loads its files; a case appends its own
ML.  A file evaluated inside the context sees neither the program's
bindings nor the raw toplevel's: `AFTER` is the same `after` for such a
file, on the context's theory."""

from pathlib import Path

from isabelle_theory_agent.model import string_token

ROOT = Path(__file__).resolve().parent.parent

AFTER = """
  fun after thy text =
    Toplevel.theory_of (fold (Toplevel.command_exception true)
      (Outer_Syntax.parse_text thy (K thy) Position.start text) (Toplevel.make_state (SOME thy)));
"""

PROBE = """
  val thy0 = Theory.begin_theory ("Probe", Position.none) [Thy_Info.get_theory "Main"];
  fun in_theory thy files =
    ML_Context.exec (fn () => List.app (ML_Context.eval_file ML_Compiler.flags o Path.explode) files)
      (Context.Theory thy);
""" + AFTER


def ml_string(text: str) -> str:
    """`text` as an ML string literal: Isabelle's string token is one."""
    return string_token(text)


async def ml_process(harness, ml: str):
    """The probe and `ml` run on a raw ML process; the completed process."""
    return await harness.run_tool(["isabelle", "ML_process", "-l", "HOL", "-e", PROBE + ml])
