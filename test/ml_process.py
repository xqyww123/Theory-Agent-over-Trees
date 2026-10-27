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
theory.  `BUILD_READER` is `read_as_built thy text`, the build reader
(COMPILATION.md §3), and `verdict f`, `"ok"` or `"refused: "` and the
first line of the message `f ()` raised, for the program and for such a
file alike.  The
logic and the base theory default to `HOL` and `Main`.
`read_back(harness, file, tmp_path)` reads an emitted file back whole
under what it imports, as a build reads it."""

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

# A theory text read as a build reads it (thy_info.ML `eval_thy`), from no
# theory, its header beginning `thy`: every span through `Command.read_span`,
# whose token check refuses a malformed symbol; the comment check an
# interactive session adds (command.ML `check_span_comments`); one
# `present_thy`, which evaluates every formal comment's body; its YXML
# read back as it was written, as the document export reads it (`exported`).
BUILD_READER = """
  fun verdict f =
    (case Exn.result f () of
      Exn.Res _ => "ok"
    | Exn.Exn exn => "refused: " ^ hd (split_lines (Runtime.exn_message exn)));
  fun exported body =
    let val y = YXML.string_of_body body
    in if YXML.string_of_body (YXML.parse_body y) = y then () else error "Malformed YXML" end;
  fun read_as_built thy text =
    let
      val keywords = Thy_Header.get_keywords thy;
      fun read span (st, segments) =
        let
          val tr = Command.read_span keywords st Path.current (K thy) span;
          val st' = Toplevel.command_exception false tr st;
          val _ = Command_Span.content span |> List.app (fn tok =>
            Document_Output.check_comments (Toplevel.presentation_context st')
              (Input.source_explode (Token.input_of tok)));
        in (st', {span = span, command = tr, prev_state = st, state = st'} :: segments) end;
      val (_, segments) =
        fold read (Outer_Syntax.parse_spans (Token.explode keywords Position.start text))
          (Toplevel.make_state NONE, []);
    in exported (Document_Output.present_thy (Options.default ()) keywords (Context.theory_base_name thy) (rev segments)) end;
"""


def probe(base: str) -> str:
    return f"""
  val thy0 = Theory.begin_theory ("Probe", Position.none) [Thy_Info.get_theory {string_token(base)}];
  fun in_theory thy files =
    ML_Context.exec (fn () => List.app (ML_Context.eval_file ML_Compiler.flags o Path.explode) files)
      (Context.Theory thy);
""" + AFTER + BUILD_READER


def ml_string(text: str) -> str:
    """`text` as an ML string literal: Isabelle's string token, with the
    ASCII control characters it leaves raw, which Isabelle/ML refuses
    raw, escaped."""
    return string_token(text).translate(_ML_ESCAPES)


_ML_ESCAPES = str.maketrans({"\t": "\\t", "\n": "\\n", "\v": "\\v", "\f": "\\f", "\x7f": "\\127"})


async def ml_process(harness, ml: str, logic: str = "HOL", base: str = "Main", options: tuple[str, ...] = ()):
    """The probe on `base` and `ml` run on a raw ML process of `logic`, under
    the system `options` given (`NAME=VAL` or `NAME`); the completed
    process."""
    return await harness.run_tool(["isabelle", "ML_process", "-l", logic, *(a for o in options for a in ("-o", o)),
                                   "-e", probe(base) + ml])


def body_of(theory: str) -> str:
    """A theory's text between its `begin` line and its `end` line."""
    return theory[theory.index("begin\n") + len("begin\n"):theory.rindex("end\n")]


async def read_back(harness, file: str, tmp_path) -> None:
    """An emitted file read back by Isabelle under what it imports, as a
    build reads it: TAT_Std.thy's body run on a raw process of the base
    heap `Minilang_AoA` begun on `Minilang_AoA.Minilang_AoA`, then the
    file whole — the text before its header, its header, its body —
    through `read_as_built` on that theory, under `quick_and_dirty`, which
    a build of a file holding `sorry` needs (COMPILATION.md §2); asserted
    to go through."""
    std, emitted = tmp_path / "read_back_std.thy", tmp_path / "read_back.thy"
    std.write_text(body_of(TAT_STD.read_text()))
    emitted.write_text(file)

    def read(path): return f"File.read (Path.explode {ml_string(str(path))})"
    r = await ml_process(harness, f"val _ = read_as_built (after thy0 ({read(std)})) ({read(emitted)});\n"
                                  'writeln "read back";', logic="Minilang_AoA", base="Minilang_AoA.Minilang_AoA",
                         options=("quick_and_dirty",))
    assert r.returncode == 0 and "read back" in r.stdout.splitlines(), (r.stdout, r.stderr)
