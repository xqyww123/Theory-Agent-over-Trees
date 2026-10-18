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
theory.  The logic and the base theory default to `HOL` and `Main`.
`read_back(harness, file, tmp_path)` reads an emitted file back whole
under what it imports."""

from pathlib import Path

from isabelle_theory_agent.model import string_token

ROOT = Path(__file__).resolve().parent.parent
TAT_STD = ROOT / "Isabelle_Std" / "TAT_Std" / "TAT_Std.thy"

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


def body_of(theory: str) -> str:
    """A theory's text between its `begin` line and its `end` line."""
    return theory[theory.index("begin\n") + len("begin\n"):theory.rindex("end\n")]


async def read_back(harness, file: str, tmp_path) -> None:
    """An emitted file read back whole by Isabelle under what it imports:
    TAT_Std.thy's body, then the file's, run as one text on a raw process
    of the base heap `Minilang_AoA` begun on `Minilang_AoA.Minilang_AoA`;
    asserted to go through."""
    body = tmp_path / "read_back.thy"
    body.write_text(body_of(TAT_STD.read_text()) + body_of(file))
    r = await ml_process(harness, f'val _ = after thy0 (File.read (Path.explode {ml_string(str(body))}));\n'
                                  'writeln "read back";', logic="Minilang_AoA", base="Minilang_AoA.Minilang_AoA")
    assert r.returncode == 0 and "read back" in r.stdout.splitlines(), (r.stdout, r.stderr)
