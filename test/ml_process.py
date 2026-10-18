"""Isabelle probes on a raw ML process (not a pytest module): `isabelle
ML_process -l <logic>` through a harness's `run_tool`, for what the std
harness cannot host — it loads the plugin's theory whole and offers no
probe.  The program begins with a theory `Probe` on the base theory (a
theory of the heap), `state_after thy text`, which runs Isar text on a
theory and answers the toplevel state after it, `after thy text`, which
answers that state's theory, and `in_theory thy files`, which evaluates
ML files inside the theory's context — the environment an `ML_file` of
a theory has, the heap's structures visible, as the plugin's theory
loads its files; a case appends its own ML.  A file evaluated inside the
context sees neither the program's bindings nor the raw toplevel's:
`AFTER` is the same two functions for such a file, on the context's
theory.  The logic and the base theory default to `HOL` and `Main`."""

from pathlib import Path

from isabelle_theory_agent.model import string_token

ROOT = Path(__file__).resolve().parent.parent

AFTER = """
  fun state_after thy text =
    fold (Toplevel.command_exception true)
      (Outer_Syntax.parse_text thy (K thy) Position.start text) (Toplevel.make_state (SOME thy));
  fun after thy text = Toplevel.theory_of (state_after thy text);
"""


def probe(base: str) -> str:
    return f"""
  val thy0 = Theory.begin_theory ("Probe", Position.none) [Thy_Info.get_theory {string_token(base)}];
  fun in_theory thy files =
    ML_Context.exec (fn () => List.app (ML_Context.eval_file ML_Compiler.flags o Path.explode) files)
      (Context.Theory thy);
""" + AFTER


def ml_string(text: str) -> str:
    """`text` as an ML string literal: Isabelle's string token is one."""
    return string_token(text)


async def ml_process(harness, ml: str, logic: str = "HOL", base: str = "Main"):
    """The probe on `base` and `ml` run on a raw ML process of `logic`; the
    completed process."""
    return await harness.run_tool(["isabelle", "ML_process", "-l", logic, "-e", probe(base) + ml])
