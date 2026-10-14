"""What the classes of `Isabelle_Std` share (node_classes/COMMON.md):
`NotInsideTheory`'s sentence, and `Theory_Member` over every class the
package registers (§1); the `text` line (§2); `Proof_Obligation`'s
abstraction, and its reading of the class's own words, callback, message
and records, through a stand-in (§3); `TAT_Overloaded`, Isabelle-backed
(§4).  The rest of what `Proof_Obligation` does on a node is pinned
through `Theorem`, test_theorem.py.
Run: python -m pytest test/test_common.py
"""

from pathlib import Path

import jsoncomment
import pytest

import test_session_theory as ts
from baselines import DOCS, fenced_blocks, fenced_lines
from isabelle_theory_agent import edit, isabelle_driver, model as M, plugin
from isabelle_theory_agent.exceptions import BadEdit, InvalidField
from isabelle_theory_agent.std import common, datatype, theorem
from isabelle_theory_agent.std.common import (
    Mixfix, NotInsideTheory, Proof_Obligation, Theory_Member, Type_Parameter, text_line)
from Isabelle_RPC_Host.unicode import IsaTerm
from test_datatype import LIST, definition
from test_model import locked, run
from test_session_theory import Forest_Under_Test, session, theory
from test_theorem import lemma

table = ts.table                    # the fake state slot table and the fake wire, per test
COMMON = DOCS / "node_classes" / "COMMON.md"

# One construct per kind the package registers, valid under a theory; held
# to the registered kinds, so a new class adds its example here.
EXAMPLES = {**{kind: lemma("p", kind=kind) for kind in theorem.KINDS},
            **{kind: definition(LIST, kind=kind) for kind in datatype.KINDS}}


def test_not_inside_theory_is_section_1_s_sentence():
    [line] = fenced_lines(COMMON, "1.")
    e = NotInsideTheory("datatype", "session_Arith")
    assert str(e) == line and (e.kind, e.parent_id) == ("datatype", "session_Arith")
    assert issubclass(NotInsideTheory, BadEdit)


def test_every_registered_class_is_a_theory_member_refused_outside_a_theory():
    """§1: every class the package registers derives from `Theory_Member`;
    a construct of each placed under a `Session` or the root is refused by
    its `gen` with `NotInsideTheory`, a move there by `on_moving`, the
    parent's id as the agent sees it; under a nesting node under the
    theory it is accepted, by `gen` and by a move, and directly under
    another theory by a move; `theory()` is, each time, the theory it
    lives in."""
    loaded = plugin.load(["isabelle_theory_agent.std"])
    registered = {kind: cls for kind, cls in loaded.kinds.items() if cls not in M.FRAMEWORK_NODE_CLASSES}
    assert set(registered) == set(EXAMPLES)
    kinds = {**ts.KINDS, **registered}
    f = Forest_Under_Test(kinds=kinds)
    (s,) = run(locked(f, edit.insert(f, 0, [session("Arith", theory("X") | {"children": [
        {"kind": "block", "name": "B", "children": [{"kind": "block", "name": "C"}]}]}, theory("Y"))], kinds)))
    x, y = s.sub_nodes
    (b,) = x.sub_nodes
    (c,) = b.sub_nodes
    outside = ((s, "session_Arith"), (f, "Sessions"))
    for kind, construct in EXAMPLES.items():
        cls = registered[kind]
        assert issubclass(cls, Theory_Member)
        for parent, parent_id in outside:
            with pytest.raises(NotInsideTheory) as e:
                run(locked(f, edit.insert(parent, 0, [construct], kinds)))
            assert (e.value.kind, e.value.parent_id, e.value.raw_ast_path) == (kind, parent_id, "constructs[0]")
        (node,) = run(locked(f, edit.insert(c, 0, [construct], kinds)))
        assert isinstance(node, cls) and node.theory() is x
        run(locked(f, edit.move(node, b, 0)))
        assert node.parent is b and node.theory() is x
        run(locked(f, edit.move(node, y, 0)))
        assert node.parent is y and node.theory() is y
        for parent, parent_id in outside:
            with pytest.raises(NotInsideTheory) as e:
                run(locked(f, edit.move(node, parent, 0)))
            assert (e.value.kind, e.value.parent_id) == (kind, parent_id)
        assert node.parent is y
        run(locked(f, edit.delete(node)))
    assert f.sub_nodes == [s] and s.sub_nodes == [x, y] and x.sub_nodes == [b] and b.sub_nodes == [c]
    assert y.sub_nodes == []


def test_the_text_line_is_section_2_s():
    """§2: a period added when `english` ends without `.`, `!` or `?`; the
    class's lead before it; the text through the framework's `cartouche`."""
    assert text_line("The length of a reversed list") == "text ‹The length of a reversed list.›"
    assert [text_line(e) for e in ("Bang!", "Why?", "Done.")] == ["text ‹Bang!›", "text ‹Why?›", "text ‹Done.›"]
    assert text_line("Bang", "Lemma q.") == "text ‹Lemma q. Bang.›"
    assert text_line("‹Quoted› \\<open>here\\<close>") == 'text ‹"Quoted" "here".›'


def test_proof_obligation_enforces_its_abstract_methods():
    """§3: `Proof_Obligation` derives from `Node`, so a class that leaves
    `goal_structure()` or `message()` out fails at its first instantiation;
    `Theorem` has both."""
    class Without_Goal_Structure(Theory_Member, Proof_Obligation, M.Leaf):
        def message(self): return ()
        def emit(self, indent, out): return indent

    class Without_Message(Theory_Member, Proof_Obligation, M.Leaf):
        def goal_structure(self): return ()
        def emit(self, indent, out): return indent

    for cls, missing in ((Without_Goal_Structure, "goal_structure"), (Without_Message, "message")):
        with pytest.raises(TypeError, match=missing):
            cls(None, None)
    assert issubclass(theorem.Theorem, Proof_Obligation) and theorem.Theorem.__abstractmethods__ == frozenset()


class Stand_In(theorem.Theorem):
    """A second `Proof_Obligation` class, with its own words, callback,
    message and records (§3); the rest `Theorem`'s."""
    evaluation_callback = "TAT.Stand_In.evaluate"
    valid_word, invalid_word = "valid definition", "invalid definition"
    recorded = None                     # what `record_from_evaluation` was given, once called

    def message(self):
        return ("stand_in", self.name)

    def record_from_evaluation(self, what):
        self.recorded = what
        return (IsaTerm.from_agent(f"recorded {what[0]} and {what[1]}"),)


def test_proof_obligation_reads_the_class_s_own_words_callback_message_and_records(monkeypatch):
    """§3: `_eval_opr` calls the class's own `evaluation_callback` with the
    three slots and its `message()`, and reads its answer, the messages and
    what the two steps yielded: the messages make the node an obstacle,
    the class's `record_from_evaluation` not called; none is `Ready`
    carrying what `record_from_evaluation` answers, given the pair; the
    default, `Theorem`'s, records nothing and answers `()`.  The mark's
    first slot is the class's `valid_word` or `invalid_word`."""
    kinds = {**ts.KINDS, "lemma": Stand_In}
    f = Forest_Under_Test(kinds=kinds)
    (s,) = run(locked(f, edit.insert(f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        lemma("p"), lemma("q")]})], kinds)))
    (x,) = s.sub_nodes
    p, q = x.sub_nodes
    calls = []

    async def call(conversation, name, args):
        calls.append((name, args))
        return [["no"], None] if args[3] == q.message() else [[], ["opened", "admitted"]]
    monkeypatch.setattr(isabelle_driver, "call", call)
    run(x.evaluate_to(None, False))
    assert [name for name, _ in calls] == ["TAT.Stand_In.evaluate"] * 2
    assert [args[:3] for _, args in calls] == [
        (n.state.to_msgpack(), n.goal_state.to_msgpack(), n.resulting_state().to_msgpack()) for n in (p, q)]
    assert [args[3] for _, args in calls] == [p.message(), q.message()] == [("stand_in", "p"), ("stand_in", "q")]
    (status,) = p.evaluation_statuses()
    assert isinstance(status, M.Ready) and [m.unicode for m in status.messages] == ["recorded opened and admitted"]
    assert p.recorded == ["opened", "admitted"]
    assert p.mark(M.BRIEFING, 0) == "valid definition, proof not started"
    (status,) = q.evaluation_statuses()
    assert isinstance(status, M.CannotEvaluate) and [m.unicode for m in status.messages] == ["no"]
    assert q.recorded is None
    assert q.mark(M.BRIEFING, 0) == "invalid definition"
    assert "record_from_evaluation" not in vars(theorem.Theorem)
    assert Proof_Obligation.record_from_evaluation(p, [None, None]) == ()


# --- the shared `$defs` (§4): the schema text, the type parameters' check and writer, the mixfix writers

def test_the_shared_defs_are_section_4_s_schema_text():
    """§4: the three definitions, descriptions included, are the section's
    jsonc blocks, pinned here alone; `Datatype`'s `$defs` are the three."""
    blocks = [jsoncomment.JsonComment().loads("\n".join(b)) for b in fenced_blocks(COMMON, "4.") if b[0] == "{"]
    assert blocks == [common.TYPE_PARAMETER_DEFS, common.MIXFIX_DEFS, common.TYPE_MIXFIX_DEFS]
    assert datatype.Datatype.construct_schema["$defs"] == {**common.TYPE_PARAMETER_DEFS, **common.TYPE_MIXFIX_DEFS,
                                                           **common.MIXFIX_DEFS}


def test_the_type_parameters_check_renders_section_4_s_two_sentences():
    """§4: a name that is not a prime and an Isabelle identifier on its
    `ascii`, and a name bound twice, each the section's sentence; the
    pieces normalised, an empty `sort` no sort."""
    [variable, binds] = [b for b in fenced_blocks(COMMON, "4.") if b[0].startswith("The field")][0]
    with pytest.raises(InvalidField) as e:
        common.type_parameters_of([{"name": "a"}])
    assert str(e.value) == variable and e.value.field == "type_parameters[0].name"
    with pytest.raises(InvalidField) as e:
        common.type_parameters_of([{"name": "'a"}, {"name": "'a", "sort": "linorder"}])
    assert str(e.value) == binds and e.value.field == "type_parameters[1].name"
    for bad in ("", "'", "'1", "''a", "'a b", "a'", "'a-b"):
        with pytest.raises(InvalidField) as e:
            common.type_parameters_of([{"name": "'b"}, {"name": bad}])
        assert e.value.field == "type_parameters[1].name" and e.value.reason.startswith("must be a type variable"), bad
    parameters = common.type_parameters_of([{"name": " 'a "}, {"name": "'b", "sort": ""},
                                            {"name": "'c", "sort": " {zero,\n linorder} "}, {"name": "'x⇩1"}])
    assert parameters == (Type_Parameter(IsaTerm.from_agent("'a"), None), Type_Parameter(IsaTerm.from_agent("'b"), None),
                          Type_Parameter(IsaTerm.from_agent("'c"), IsaTerm.from_agent("{zero, linorder}")),
                          Type_Parameter(IsaTerm.from_agent("'x⇩1"), None))
    assert [p.image() for p in parameters] == [{"name": "'a"}, {"name": "'b"}, {"name": "'c", "sort": "{zero, linorder}"},
                                               {"name": "'x⇩1"}]


def test_type_parameters_text_writes_section_4_s_examples():
    """§4: nothing for none, one without a sort bare, otherwise parenthesised
    and comma-separated with a sort after `::` through `print_name` — a
    keyword quoted, none known while `keywords` is None; both spellings."""
    f = Forest_Under_Test()
    (s,) = run(locked(f, edit.insert(f, 0, [session("S", theory("A", kind="fake_theory"))], ts.KINDS)))
    (a,) = s.sub_nodes
    of = common.type_parameters_of
    assert common.type_parameters_text(a, of([]), "ascii") == ""
    assert common.type_parameters_text(a, of([{"name": "'a"}]), "ascii") == "'a"
    assert common.type_parameters_text(a, of([{"name": "'a", "sort": "linorder"}]), "ascii") == "('a :: linorder)"
    assert common.type_parameters_text(a, of([{"name": "'a", "sort": "linorder"}, {"name": "'b"}]), "ascii") == "('a :: linorder, 'b)"
    assert common.type_parameters_text(a, of([{"name": "'a", "sort": "{zero, linorder}"}]), "ascii") == "('a :: \"{zero, linorder}\")"
    assert common.type_parameters_text(a, of([{"name": "'a"}, {"name": "'b"}]), "ascii") == "('a, 'b)"
    greek = of([{"name": "'α", "sort": "linorder"}, {"name": "'b"}])
    assert common.type_parameters_text(a, greek, "ascii") == "('\\<alpha> :: linorder, 'b)"
    assert common.type_parameters_text(a, greek, "unicode") == "('α :: linorder, 'b)"
    a.keywords = frozenset({"linorder"})
    assert common.type_parameters_text(a, greek, "unicode") == "('α :: \"linorder\", 'b)"


def test_mixfix_text_and_mixfix_wire_write_section_4_s_examples():
    """§4: either annotation as Isabelle writes it, the symbol or template a
    string token, a general mixfix's priorities each when given; the wire
    form the form, the `ascii`, the priority, the argument priorities, a
    left-out value None; the image the construct's shape."""
    of = common.mixfix_of
    cases = [
        ({"form": "infixr", "symbol": "#", "priority": 65}, '(infixr "#" 65)', '(infixr "#" 65)', ("infixr", "#", 65, None)),
        ({"form": "infix", "symbol": "+", "priority": 0}, '(infix "+" 0)', '(infix "+" 0)', ("infix", "+", 0, None)),
        ({"form": "infixl", "symbol": "\"", "priority": 1}, '(infixl "\\"" 1)', '(infixl "\\"" 1)', ("infixl", '"', 1, None)),
        ({"form": "binder", "symbol": "∀", "priority": 10}, '(binder "∀" 10)', '(binder "\\<forall>" 10)', ("binder", "\\<forall>", 10, None)),
        ({"form": "mixfix", "template": "⟨_, _⟩"}, '("⟨_, _⟩")', '("\\<langle>_, _\\<rangle>")', ("mixfix", "\\<langle>_, _\\<rangle>", None, None)),
        ({"form": "mixfix", "template": "_ ! _", "argument_priorities": [100, 101], "priority": 100},
         '("_ ! _" [100, 101] 100)', '("_ ! _" [100, 101] 100)', ("mixfix", "_ ! _", 100, [100, 101])),
        ({"form": "mixfix", "template": "_⇩⊥", "argument_priorities": [21]}, '("_⇩⊥" [21])', '("_\\<^sub>\\<bottom>" [21])',
         ("mixfix", "_\\<^sub>\\<bottom>", None, [21])),
        ({"form": "mixfix", "template": "_!", "priority": 999}, '("_!" 999)', '("_!" 999)', ("mixfix", "_!", 999, None)),
        ({"form": "mixfix", "template": "_", "argument_priorities": []}, '("_" [])', '("_" [])', ("mixfix", "_", None, [])),
    ]
    for raw, unicode, ascii, wire in cases:
        syntax = of(raw)
        assert isinstance(syntax, Mixfix) and syntax.image() == raw, raw
        assert (common.mixfix_text(syntax, "unicode"), common.mixfix_text(syntax, "ascii")) == (unicode, ascii), raw
        assert common.mixfix_wire(syntax) == wire and of(syntax.image()) == syntax, raw
    assert common.mixfix_wire(None) is None
    # the symbol or template normalised for newlines and tabs alone: runs of spaces are layout
    assert of({"form": "mixfix", "template": "⟨_,\n\t_⟩  "}).text.unicode == "⟨_,  _⟩  "
    assert of({"form": "infix", "symbol": "a\r\nb", "priority": 1}).text.unicode == "a b"


# --- TAT_Overloaded (§4), on a raw ML process: the std harness offers no probe

OVERLOADED_ML = Path(__file__).resolve().parent.parent / "Isabelle_Std" / "ML" / "TAT_Overloaded.ML"


async def test_tat_overloaded_needed_answers_section_4_s_two_typedefs(std_harness):
    """§4: `needed` is true for `{x :: 'a::zero. x = 0}` and false for
    `{n :: nat. n > 0}`, each made with `(overloaded)` given, as the
    classes make theirs."""
    ml = f"""
      use {M.string_token(str(OVERLOADED_ML))};
      val thy0 = Theory.begin_theory ("Probe", Position.none) [Thy_Info.get_theory "Main"];
      fun after text =
        Toplevel.theory_of (fold (Toplevel.command_exception true)
          (Outer_Syntax.parse_text thy0 (K thy0) Position.start text) (Toplevel.make_state (SOME thy0)));
      fun needed thy name = TAT_Overloaded.needed thy (Sign.full_name thy (Binding.name name));
      val zero_only = after "typedef (overloaded) 'a zero_only = \\"{{x :: 'a::zero. x = 0}}\\" by simp";
      val pos = after "typedef (overloaded) pos = \\"{{n :: nat. n > 0}}\\" by (rule exI[of _ 1]) simp";
      writeln ("needed: " ^ Value.print_bool (needed zero_only "zero_only") ^ " " ^ Value.print_bool (needed pos "pos"));
    """
    r = await std_harness.run_tool(["isabelle", "ML_process", "-l", "HOL", "-e", ml])
    assert r.returncode == 0 and "needed: true false" in r.stdout.splitlines(), (r.stdout, r.stderr)
