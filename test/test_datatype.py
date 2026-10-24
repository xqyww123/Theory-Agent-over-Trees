"""`Datatype` (node_classes/DATATYPE.md): with no Isabelle, the schema and
the descriptions (§2, §3), `gen`'s checks and refusals (§4), the
definition as the node holds, stores and prints it (§2, §8), the node's
name and the framework's `DuplicateName` on it, the emitted text (§5), the
message and the status (§6), the mark (§7); through the std harness, the
evaluation (§6), `recall` (§8) and the rendered file (§5).
Run: python -m pytest test/test_datatype.py
"""

import io
import json
import re

import jsoncomment
import pytest

import test_model as tm
import test_session_theory as ts
from baselines import DOCS, fenced_blocks, fenced_lines
from harness import text_of
from Isabelle_RPC_Host.unicode import IsaTerm, ascii_of_unicode
from invariants import assert_invariants, assert_store_mirrors
from isabelle_theory_agent import compile as C, edit, isabelle_driver, model as M
from isabelle_theory_agent.exceptions import BadPlacement, DuplicateName, InvalidField, InvalidName, RawASTError
from isabelle_theory_agent.std import common, datatype
from isabelle_theory_agent.std.common import Binder, Infix, Template, Type_Parameter
from isabelle_theory_agent.std.datatype import Argument, Constructor, Datatype, Defined_Type
from isabelle_theory_agent.store import Forest_Store
from ml_process import read_back
from std_forest import KINDS, forest, insert, inv, refused
from test_descriptions import descriptions
from test_model import locked, run
from test_session_theory import Forest_Under_Test, session, theory
from test_theorem import lemma

table = ts.table                    # the fake state slot table and the fake wire, per test
DT = DOCS / "node_classes" / "DATATYPE.md"

# §2's example, the construct of `'a list`, read from the document
LIST_CONSTRUCT = json.loads("\n".join(fenced_blocks(DT, "2.")[0]))
LIST = LIST_CONSTRUCT["types"][0]
EXPR = {"type_name": "expr", "constructors": [
    {"name": "Num", "arguments": [{"type": "nat"}]},
    {"name": "Plus", "arguments": [{"type": "expr"}, {"type": "expr"}]},
    {"name": "If", "arguments": [{"type": "bexp"}, {"type": "expr"}, {"type": "expr"}]}]}
BEXP = {"type_name": "bexp", "constructors": [
    {"name": "Less", "arguments": [{"type": "expr"}, {"type": "expr"}]},
    {"name": "Not", "arguments": [{"type": "bexp"}]}]}
STREAM = {"type_name": "stream", "constructors": [{"name": "SCons", "arguments": [{"type": "'a"}, {"type": "'a stream"}]}]}
# every arm of `TypeMixfix` and `Mixfix` (COMMON §4), for the Isabelle-backed case
EITHER = {"type_name": "either", "syntax": {"form": "infixr", "symbol": "⊕", "priority": 60},
          "constructors": [{"name": "L", "arguments": [{"type": "'a"}]}, {"name": "R", "arguments": [{"type": "'b"}]}]}
BOT = {"type_name": "bot", "syntax": {"form": "mixfix", "template": "_⇩⊥", "argument_priorities": [21], "priority": 21},
       "constructors": [{"name": "Bot"},
                        {"name": "Val", "arguments": [{"type": "'a"}],
                         "syntax": {"form": "mixfix", "template": "«_»", "argument_priorities": [21], "priority": 21}}]}
Q = {"type_name": "q", "constructors": [{"name": "N"}, {"name": "Q", "arguments": [{"type": "'a ⇒ 'a q"}],
                                        "syntax": {"form": "binder", "symbol": "QQ", "priority": 10}}]}


def definition(*types, kind="datatype", english="Finite sequences", type_parameters=({"name": "'a"},)):
    """A construct of `kind` defining `types`; §2's example by default."""
    return {"kind": kind, "english": english, "type_parameters": list(type_parameters), "types": list(types)}


# --- the schema and the descriptions (§2, §3) ------------------------------

def test_the_schema_and_the_descriptions_are_the_documents():
    [_, schema] = fenced_blocks(DT, "2.")
    text = re.sub(r'"\$defs": \{[^}]*\}.*', '"$defs": {}', "\n".join(schema))      # the spread and its comment
    expected = jsoncomment.JsonComment().loads(text)
    expected["$defs"] = {**common.TYPE_PARAMETER_DEFS, **common.TYPE_MIXFIX_DEFS, **common.MIXFIX_DEFS}
    assert Datatype.construct_schema == expected
    assert list(datatype.KINDS) == ["datatype", "codatatype"]
    shared = [d for defs in (common.TYPE_PARAMETER_DEFS, common.TYPE_MIXFIX_DEFS, common.MIXFIX_DEFS)
              for d in descriptions(defs)]
    assert sorted(descriptions(Datatype.construct_schema)) == sorted(fenced_lines(DT, "3.") + shared)
    assert LIST_CONSTRUCT == definition(LIST)


# --- `gen` (§2, §4) ----------------------------------------------------------

def test_gen_keeps_the_definition_normalised_as_isaterms_and_names_the_node():
    f, x = forest(definition(
        {"type_name": "list", "syntax": {"form": "mixfix", "template": "_\n\tlist  "},
         "constructors": [
             {"name": " Nil "},
             {"name": "Cons", "arguments": [{"type": " 'a ", "selector": "hd\n"}, {"type": "'a\n  list", "selector": "tl"}],
              "syntax": {"form": "infixr", "symbol": "#", "priority": 65}}]},
        english="Finite\n sequences ", type_parameters=({"name": " 'a ", "sort": ""},)))
    (p,) = x.sub_nodes
    assert isinstance(p, Datatype) and p.kind == "datatype" and p.name == "list" and p.english == "Finite sequences"
    assert p.type_parameters == (Type_Parameter(IsaTerm.from_agent("'a"), None),)
    assert p.types == (Defined_Type(
        "list", Template(IsaTerm.from_agent("_  list  ")),                 # newlines and tabs alone, the spaces layout
        (Constructor(IsaTerm.from_agent("Nil"), (), None),
         Constructor(IsaTerm.from_agent("Cons"),
                     (Argument(IsaTerm.from_agent("'a"), IsaTerm.from_agent("hd")),
                      Argument(IsaTerm.from_agent("'a list"), IsaTerm.from_agent("tl"))),
                     Infix("infixr", IsaTerm.from_agent("#"), 65)))),)
    assert all(isinstance(t, IsaTerm) for c in p.types[0].constructors for a in c.arguments for t in (a.type, a.selector))
    (q,) = insert(f, x, 1, [definition(EXPR, BEXP, english="Arithmetic and boolean expressions", type_parameters=())])
    assert q.name == "expr_bexp" and q.type_parameters == () and f.id_of(q) == "datatype_expr_bexp"
    (r,) = insert(f, x, 2, [definition(STREAM, kind="codatatype", english="Streams")])
    assert r.kind == "codatatype" and f.id_of(r).endswith("codatatype_stream")
    inv(f)


def test_gen_refuses_as_section_4_says():
    """§4's refusals: the place first (the framework's `BadPlacement`, pinned
    for every class by test_common.py); a type name outside §1's grammar
    (RENDER_BASELINES §2's line); the five sentences of §4's block; the type
    parameters by the shared check, and, last, each used in some
    constructor's argument type (COMMON §4's sentences, pinned by
    test_common.py); an empty `types` or `constructors` by the framework."""
    f, x = forest()
    (s,) = f.sub_nodes
    e = refused(f, s, [definition({"type_name": "my-list", "constructors": [{"name": "N"}]})], BadPlacement)
    assert (e.kind, e.parent_id, e.raw_ast_path) == ("datatype", "session_Arith", "constructs[0]")
    [invalid] = [line for line in fenced_lines(DOCS / "RENDER_BASELINES.md", "2.")
                 if line.startswith("`my-list` is not a valid type name")]
    e = refused(f, x, [definition({"type_name": "my-list", "constructors": [{"name": "N"}]})], InvalidName)
    assert (e.name, e.grammar) == ("my-list", "type name") and str(e) == "At `constructs[0]`: " + invalid
    for name in ("1st", "list_", "a list", "x'y-", "", "α"):
        assert refused(f, x, [definition({"type_name": name, "constructors": [{"name": "N"}]})], InvalidName).grammar == "type name"
    [twice, identifier, again, selector, selector_twice] = fenced_blocks(DT, "4.")[0]
    e = refused(f, x, [definition(EXPR, {"type_name": "expr", "constructors": [{"name": "N"}]}, type_parameters=())], InvalidField)
    assert str(e) == "At `constructs[0]`: " + twice and e.field == "types[1].type_name"
    e = refused(f, x, [definition({"type_name": "list", "constructors": [{"name": "Nil"}, {"name": "Cons_"}]})], InvalidField)
    assert str(e) == "At `constructs[0]`: " + identifier and e.field == "types[0].constructors[1].name"
    for name in ("1x", "x y", "", "Cons-"):
        assert refused(f, x, [definition({"type_name": "list", "constructors": [{"name": name}]})], InvalidField).field == "types[0].constructors[0].name"
    e = refused(f, x, [definition({"type_name": "list", "constructors": [{"name": "Nil"}, {"name": "Cons"}, {"name": "Nil"}]})], InvalidField)
    assert str(e) == "At `constructs[0]`: " + again and e.field == "types[0].constructors[2].name"
    e = refused(f, x, [definition({"type_name": "list", "constructors": [
        {"name": "Nil"}, {"name": "Cons", "arguments": [{"type": "'a", "selector": "hd_"}]}]})], InvalidField)
    assert str(e) == "At `constructs[0]`: " + selector and e.field == "types[0].constructors[1].arguments[0].selector"
    e = refused(f, x, [definition({"type_name": "list", "constructors": [
        {"name": "Nil"}, {"name": "Cons", "arguments": [{"type": "'a", "selector": "hd"}, {"type": "'a list", "selector": "hd"}]}]})], InvalidField)
    assert str(e) == "At `constructs[0]`: " + selector_twice and e.field == "types[0].constructors[1].arguments[1].selector"
    assert identifier.endswith(": it " + invalid.split(": a type name ")[1])
    # two types of a group may share a constructor's name: Isabelle qualifies it by the type
    (q,) = insert(f, x, 0, [definition({"type_name": "a", "constructors": [{"name": "C"}]},
                                       {"type_name": "b", "constructors": [{"name": "C"}]}, type_parameters=())])
    run(locked(f, edit.delete(q)))
    # the type parameters: COMMON §4's check, its sentences pinned by test_common.py
    e = refused(f, x, [definition(LIST, type_parameters=({"name": "a"},))], InvalidField)
    assert (e.field, e.reason) == ("type_parameters[0].name", "must be a type variable, such as 'a")
    e = refused(f, x, [definition(LIST, type_parameters=({"name": "'a"}, {"name": "'a"}))], InvalidField)
    assert (e.field, e.reason) == ("type_parameters[1].name", "repeats `'a`")
    # every type parameter used in some constructor's argument type, last — COMMON §4's check and sentence, pinned by
    # test_common.py; a group in which only the second type uses the parameter is accepted
    [unused] = [line for line in fenced_lines(DOCS / "node_classes" / "COMMON.md", "4.") if line.endswith("which is not used.")]
    e = refused(f, x, [definition(LIST, type_parameters=({"name": "'a"}, {"name": "'b"}))], InvalidField)
    assert str(e) == "At `constructs[0]`: " + unused and e.field == "type_parameters[1]"
    e = refused(f, x, [definition({"type_name": "phantom", "constructors": [{"name": "phantom", "arguments": [{"type": "'b"}]}]},
                                  type_parameters=({"name": "'a"}, {"name": "'b"}))], InvalidField)     # the phantom idiom too
    assert (e.field, e.reason) == ("type_parameters[0]", "declares `'a`, which is not used")
    (q,) = insert(f, x, 0, [definition({"type_name": "a", "constructors": [{"name": "A", "arguments": [{"type": "nat"}]}]},
                                       {"type_name": "b", "constructors": [{"name": "B", "arguments": [{"type": "'a"}]}]})])
    run(locked(f, edit.delete(q)))
    # §4's order under two faults: the type names first, then the parameters, then the constructors and selectors, then
    # the parameters' use
    bad_name = {"type_name": "my-list", "constructors": [{"name": "Nil"}]}
    bad_constructor = {"type_name": "list", "constructors": [{"name": "Nil"}, {"name": "Cons_"}]}
    bad_selector = {"type_name": "cell", "constructors": [{"name": "Cons", "arguments": [{"type": "'a", "selector": "hd_"}]}]}
    assert refused(f, x, [definition(bad_name, type_parameters=({"name": "a"},))], InvalidName).grammar == "type name"
    assert refused(f, x, [definition(bad_constructor, {"type_name": "list", "constructors": [{"name": "N"}]})],
                   InvalidField).field == "types[1].type_name"
    assert refused(f, x, [definition(bad_constructor, type_parameters=({"name": "a"},))], InvalidField).field == "type_parameters[0].name"
    assert refused(f, x, [definition(bad_selector, bad_constructor)], InvalidField).field == "types[0].constructors[0].arguments[0].selector"
    assert refused(f, x, [definition(bad_constructor, type_parameters=({"name": "'b"},))], InvalidField).field == "types[0].constructors[1].name"
    # two constructors of one type may share a selector's name: Isabelle makes one selector of them
    (q,) = insert(f, x, 0, [definition({"type_name": "t", "constructors": [
        {"name": "A", "arguments": [{"type": "'a", "selector": "get"}]},
        {"name": "B", "arguments": [{"type": "'a", "selector": "get"}, {"type": "nat"}]}]})])
    run(locked(f, edit.delete(q)))
    # the framework's integer bound and its choice of a union's arm (MODULE_STRUCTURE §4.4), RENDER_BASELINES §2's two
    # lines, the forest unchanged
    [bound] = [line for line in fenced_lines(DOCS / "RENDER_BASELINES.md", "2.") if line.endswith("must be a 64-bit integer.")]
    e = refused(f, x, [definition({"type_name": "list", "constructors": [
        {"name": "Nil"}, {"name": "Cons", "syntax": {"form": "infixr", "symbol": "#", "priority": 2**64}}]})], InvalidField)
    assert str(e) == "At `constructs[0]`: " + bound and e.field == "types[0].constructors[1].syntax.priority"
    [form] = [line for line in fenced_lines(DOCS / "RENDER_BASELINES.md", "2.") if line.endswith("`mixfix`, `NoSyntax`.")]
    e = refused(f, x, [definition({"type_name": "list", "constructors": [
        {"name": "Nil"}, {"name": "Cons", "syntax": {"form": "postfix", "symbol": "#"}}]})], InvalidField)
    assert str(e) == "At `constructs[0]`: " + form and e.field == "types[0].constructors[1].syntax.form"
    for raw in ({"kind": "datatype", "english": "e", "types": []},
                {"kind": "datatype", "english": "e", "types": [{"type_name": "t", "constructors": []}]},
                {"kind": "datatype", "english": "e", "types": [{"type_name": "t", "constructors": [{"name": "C", "syntax": {"form": "infix", "symbol": "+"}}]}]},
                {"kind": "datatype", "english": "e", "types": [{"type_name": "t", "syntax": {"form": "binder", "symbol": "+", "priority": 1}, "constructors": [{"name": "C"}]}]}):
        refused(f, x, [raw], RawASTError)
    assert x.sub_nodes == []
    inv(f)


def test_a_sibling_bearing_the_node_s_id_component_is_the_framework_s_duplicate_name():
    f, x = forest(definition({"type_name": "a_b", "constructors": [{"name": "C"}]}, type_parameters=()))
    e = refused(f, x, [definition({"type_name": "a", "constructors": [{"name": "C"}]},
                                  {"type_name": "b", "constructors": [{"name": "D"}]}, type_parameters=())], DuplicateName)
    assert e.id_component == "datatype_a_b" and e.taken_by == "datatype_a_b"
    (q,) = insert(f, x, 1, [definition({"type_name": "a_b", "constructors": [{"name": "C"}]}, kind="codatatype", type_parameters=())])
    assert q.name == "a_b" and x.sub_nodes[0].name == "a_b"      # another kind: another component
    inv(f)


def test_the_definition_is_stored_in_the_construct_s_shape(tmp_path):
    store = Forest_Store(tmp_path / "TAT.sqlite", ts.stand_ins.log())
    f, x = forest(definition(LIST), definition(EXPR, BEXP, english="Arithmetic and boolean expressions", type_parameters=()),
                  definition({"type_name": "t", "syntax": {"form": "mixfix", "template": "_⇩⊥", "argument_priorities": [21], "priority": 21},
                              "constructors": [{"name": "C", "syntax": {"form": "mixfix", "template": "⟨_⟩"}},
                                               {"name": "D", "arguments": [{"type": "'a"}], "syntax": {"form": "binder", "symbol": "∀", "priority": 10}}]},
                             type_parameters=({"name": "'a", "sort": "linorder"},)), store=store)
    nodes = x.sub_nodes
    with f.store.transaction():
        for n in nodes:
            f._store_node(n)
    before = [(n.name, n.english, n.type_parameters, n.types) for n in nodes]
    fields = {row[0] for row in store._conn.execute("SELECT field FROM fields WHERE node = ?", (nodes[0].identity,))}
    assert {"english", "type_parameters", "types"} <= fields and "name" not in fields     # the name never stored (§2)
    store.close()
    f2 = Forest_Under_Test(store=Forest_Store(tmp_path / "TAT.sqlite", ts.stand_ins.log()), kinds=KINDS)
    loaded = f2.sub_nodes[0].sub_nodes[0].sub_nodes
    assert [(n.name, n.english, n.type_parameters, n.types) for n in loaded] == before
    assert all(isinstance(n, Datatype) for n in loaded)


# --- the message and the status (§6), the mark (§7) ------------------------

def test_eval_opr_sends_the_definition_and_reads_the_messages(monkeypatch):
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        definition(LIST), definition(STREAM, english="An infinite sequence")]})])      # a fake theory: its header runs no call
    (x,) = s.sub_nodes
    p, q = x.sub_nodes
    calls = []

    async def call(conversation, name, args):
        calls.append((name, args))
        return ['Cannot define empty datatype "stream"'] if args[2][2][0][0] == "stream" else []
    monkeypatch.setattr(isabelle_driver, "call", call)
    run(x.evaluate_to(None, False))
    assert [name for name, _ in calls] == ["TAT.Datatype.evaluate"] * 2
    assert [args[:2] for _, args in calls] == [(n.state.to_msgpack(), n.resulting_state().to_msgpack()) for n in (p, q)]
    assert calls[0][1][2] == p.message() == (
        "datatype", [("'a", None)],
        [("list", None, [("Nil", [], None),
                         ("Cons", [("'a", "hd"), ("'a list", "tl")], '(infixr "#" 65)')])])
    assert isinstance(p._status, M.Ready) and p._status.messages == () and p.mark(M.BRIEFING, 0) == "complete"
    assert isinstance(q._status, M.CannotEvaluate) and [m.unicode for m in q._status.messages] == ['Cannot define empty datatype "stream"']
    assert q.mark(M.BRIEFING, 0) == "failed" and p.is_finished() and not q.is_finished()
    # a syntax on the wire (COMMON §4): the annotation as `mixfix_text` writes it, in `ascii`; None for none
    (r,) = insert(f, x, 2, [definition(
        {"type_name": "t", "syntax": {"form": "mixfix", "template": "_⇩⊥", "argument_priorities": [21], "priority": 21},
         "constructors": [{"name": "C", "syntax": {"form": "mixfix", "template": "⟨_⟩"}},
                          {"name": "D", "arguments": [{"type": "'a"}], "syntax": {"form": "binder", "symbol": "∀", "priority": 10}}]},
        type_parameters=({"name": "'a", "sort": "linorder"},))])
    assert r.message() == ("datatype", [("'a", "linorder")], [("t", '("_\\<^sub>\\<bottom>" [21] 21)',
                                                               [("C", [], '("\\<langle>_\\<rangle>")'),
                                                                ("D", [("'a", None)], '(binder "\\<forall>" 10)')])])
    assert r.mark(M.BRIEFING, 0) == "not evaluated"


# --- what it prints (§8) -----------------------------------------------------

def test_print_fields_writes_the_definition_and_english_by_depth():
    f, x = forest(definition(LIST), definition(EXPR, BEXP, english="Arithmetic and boolean expressions", type_parameters=()))
    p, q = x.sub_nodes
    [one, two, failed] = fenced_blocks(DT, "8.")

    def fields(node, mode, depth):
        out = io.StringIO()
        node.print_fields(0, out, mode, depth)
        return out.getvalue().splitlines()
    assert [fields(p, M.RECALL, d) for d in range(4)] == [one, one[:1], one[:1], []]
    assert [fields(q, M.RECALL, d) for d in range(4)] == [two, two[:2], two[:2], []]
    assert fields(p, M.OUT_FOCUS, 0) == [] and fields(p, M.Relative_Focus(frozenset({p}), 0), 0) == []
    (r,) = insert(f, x, 2, [definition(STREAM, english="An infinite sequence")])
    assert fields(r, M.RECALL, 0) == [line.strip() for line in failed[1:3]]      # §8's last example, under its node line
    # against no keyword, whatever the theory recorded: every name bare, a sort and a type quoted unless an identifier
    (t,) = insert(f, x, 3, [definition(
        {"type_name": "map", "syntax": {"form": "infixr", "symbol": "⇒", "priority": 60},
         "constructors": [{"name": "M", "arguments": [{"type": "nat"}, {"type": "'a ⇒ 'b"}], "syntax": {"form": "mixfix", "template": "⟨_, _⟩"}}]},
        english="Maps", type_parameters=({"name": "'a", "sort": "linorder"}, {"name": "'b"}))])
    line = ['(\'a :: linorder, \'b) map (infixr "⇒" 60) = M nat "\'a ⇒ \'b" ("⟨_, _⟩")']
    for keywords in (None, frozenset(), frozenset({"list", "Nil", "hd", "nat", "linorder", "map", "M"})):
        x.keywords = keywords
        assert fields(t, M.RECALL, 1) == line and fields(p, M.RECALL, 1) == one[:1], keywords


# --- emission (§5) ------------------------------------------------------------

def test_the_emitted_text_is_section_5_s():
    [one, two] = fenced_blocks(DT, "5.")
    f, x = forest(definition(LIST), definition(EXPR, BEXP, english="Arithmetic and boolean expressions", type_parameters=()))
    p, q = x.sub_nodes
    x.keywords = frozenset()                                 # recorded by a header run, which emission presupposes

    def emitted(node) -> list[str]:
        """In `unicode` (§5); the file's `\\<name>` form is the compile's conversion (COMPILATION §2)."""
        out = io.StringIO()
        assert node.emit(1, out) == 1
        assert "\\<" not in out.getvalue()                                 # nothing written in `ascii`
        return out.getvalue().splitlines()

    def expected(*unicode_lines: str) -> list[str]:
        return ["  " + line for line in unicode_lines]
    assert emitted(p) == expected(*one) and emitted(q) == expected(*two)
    x.keywords = frozenset({"list", "Nil", "hd", "nat", "linorder"})    # keywords of the theory: quoted (§5)
    assert emitted(p) == expected("text ‹Finite sequences.›", 'datatype \'a "list" =', '    "Nil"',
                                  '  | Cons ("hd": "\'a") (tl: "\'a list") (infixr "#" 65)')
    assert emitted(q)[2] == '      Num "nat"'
    (t,) = insert(f, x, 2, [definition(
        {"type_name": "map", "syntax": {"form": "infixr", "symbol": "⇒", "priority": 60},
         "constructors": [{"name": "M", "arguments": [{"type": "nat"}, {"type": "'a ⇒ 'b"}], "syntax": {"form": "mixfix", "template": "⟨_, _⟩"}},
                          {"name": "B", "arguments": [{"type": "'a"}], "syntax": {"form": "binder", "symbol": "∀", "priority": 10}},
                          {"name": "G", "syntax": {"form": "mixfix", "template": "_ ! _", "argument_priorities": [100, 101], "priority": 100}}]},
        english="Maps!", type_parameters=({"name": "'a", "sort": "{zero, linorder}"}, {"name": "'b"}))])
    assert emitted(t) == expected("text ‹Maps!›", 'datatype (\'a :: "{zero, linorder}", \'b) map (infixr "⇒" 60) =',
                                  '    M "nat" "\'a ⇒ \'b" ("⟨_, _⟩")', '  | B "\'a" (binder "∀" 10)', '  | G ("_ ! _" [100, 101] 100)')
    (u,) = insert(f, x, 3, [definition({"type_name": "tree", "constructors": [{"name": "Leaf"}, {"name": "Node", "arguments": [{"type": "tree", "selector": "left"}, {"type": "tree"}]}]},
                                       english="Trees", type_parameters=())])
    assert emitted(u)[1:] == expected("datatype tree =", "    Leaf", "  | Node (left: tree) tree")
    (v,) = insert(f, x, 4, [definition({"type_name": "either", "syntax": {"form": "infixr", "symbol": "⊕", "priority": 60},
                                        "constructors": [{"name": "L", "arguments": [{"type": "'a"}]}, {"name": "R", "arguments": [{"type": "'b"}]}]},
                                       english="Sums", type_parameters=({"name": "'a"}, {"name": "'b"}))])
    assert emitted(v)[1] == '  datatype (\'a, \'b) either (infixr "⊕" 60) ='


def test_a_codatatype_is_the_same_class_under_its_own_kind():
    """§1, §5, §6: `codatatype` heads the id component, the message and the
    emitted command; the definition is otherwise the same."""
    f, x = forest(definition(STREAM, kind="codatatype", english="Streams"))
    (p,) = x.sub_nodes
    x.keywords = frozenset()
    assert p.kind == "codatatype" and f.id_of(p) == "codatatype_stream" and p.message()[0] == "codatatype"
    out = io.StringIO()
    p.emit(0, out)
    assert out.getvalue() == "text ‹Streams.›\ncodatatype 'a stream =\n    SCons \"'a\" \"'a stream\"\n"


def test_the_two_spellings_are_kept_apart():
    """§2, §5, §8: a name or type whose `unicode` and `ascii` differ — `'α`,
    `C⇩1`, `ε` — is stored, printed and emitted in `unicode` and sent to
    Isabelle in `ascii`."""
    f, x = forest(definition(
        {"type_name": "t", "constructors": [{"name": "C⇩1", "arguments": [{"type": "'α", "selector": "ε"}]}]},
        english="Greek", type_parameters=({"name": "'α", "sort": "linorder"},)))
    (p,) = x.sub_nodes
    x.keywords = frozenset()
    assert p.message() == ("datatype", [("'\\<alpha>", "linorder")],
                           [("t", None, [("C\\<^sub>1", [("'\\<alpha>", "\\<epsilon>")], None)])])
    rows = {}
    p.to_store(type("Rows", (), {"put": lambda self, k, v: rows.__setitem__(k, v)})())
    assert rows["type_parameters"] == [{"name": "'α", "sort": "linorder"}]
    assert rows["types"] == [{"type_name": "t", "constructors": [
        {"name": "C⇩1", "arguments": [{"type": "'α", "selector": "ε"}]}]}]
    out = io.StringIO()
    p.print_fields(0, out, M.RECALL, 1)
    assert out.getvalue() == "('α :: linorder) t = C⇩1 (ε: \"'α\")\n"
    out = io.StringIO()
    p.emit(0, out)
    assert out.getvalue().splitlines()[1:] == ["datatype ('α :: linorder) t =", "    C⇩1 (ε: \"'α\")"]


# --- the evaluation, in the plugin's run of the harness (§5, §6, §8) --------

@pytest.mark.isabelle(deadline=300)
async def test_a_definition_runs_and_a_refused_one_is_an_obstacle(std_conversation, std_harness, tmp_path):
    """§6 through `TAT.Datatype.evaluate`: a theory of §2's `'a list`, the
    mutually recursive `expr`/`bexp`, three types carrying every arm of
    `TypeMixfix` and `Mixfix` with a sort, and a `codatatype` — each
    defined, the resulting slot written — and a theorem whose statement
    parses only through the selector `hd`, the set function of `bot`'s
    live parameter, the type syntax `⊕`, the template `«_»` and the
    binder `QQ`, admitted; a second theory of a
    `datatype` with no finite value, and a third of a theorem whose type
    breaks the sort, each an obstacle with Isabelle's message; `recall` as
    §8 shows; the first theory rendered as §5 shows, under the recorded
    keywords, and read back whole by Isabelle."""
    forest = std_conversation.forest
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [ts.session("TAT_Suite",
                                      ts.theory("TAT_Std_A") | {"children": [
                                          definition(LIST),
                                          definition(EXPR, BEXP, english="Arithmetic and boolean expressions", type_parameters=()),
                                          definition(EITHER, english="Sums", type_parameters=({"name": "'a"}, {"name": "'b"})),
                                          definition(BOT, english="Lifted", type_parameters=({"name": "'a", "sort": "linorder"},)),
                                          definition(Q, english="Binders"),
                                          definition(STREAM, kind="codatatype", english="Streams"),
                                          lemma("uses_the_syntax", english="Every syntax defined above parses",
                                                for_any=({"name": "x", "type": "'a :: linorder"}, {"name": "xs", "type": "'a list"},
                                                         {"name": "P", "type": "bool"}),
                                                premises=({"name": "h", "term": "P"},),
                                                conclusion="hd (Cons x xs) = x ∧ (L x :: 'a ⊕ 'b) = L x ∧ («x») = Val x"
                                                           " ∧ (QQ z. N) = Q (λz. N) ∧ set_bot (Val x) = {x}")]},   # `«x»` of priority 21: parenthesised
                                      ts.theory("TAT_Std_B") | {"children": [definition(STREAM, english="An infinite sequence")]})]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 1, text
        result = await session.call_tool("edit", {                    # a walk stops at an obstacle: the third theory after it
            "action": "append", "target_id": "session_TAT_Suite", "evaluate": True,
            "constructs": [ts.theory("TAT_Std_C", "TAT_Suite.TAT_Std_A") | {"children": [
                lemma("sort_broken", english="A sort the argument lacks", premises=(), conclusion="Val y = Val y",
                      for_any=({"name": "y", "type": "bool set"},))]}]})      # `bool set` is no `linorder`
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 1, text
        (s,) = forest.sub_nodes
        a, b, c = s.sub_nodes
        (r,) = b.sub_nodes
        (sort_broken,) = c.sub_nodes
        for node in a.sub_nodes:                                      # the six definitions and the theorem
            assert isinstance(node._status, M.Ready) and node._status.messages == (), (node.name, node._status)
            assert await node.resulting_state().is_initialized()
        assert len(a.sub_nodes) == 7
        assert isinstance(r._status, M.CannotEvaluate)
        [one, two, failed] = fenced_blocks(DT, "8.")
        assert r._status.messages[0].unicode == failed[4].strip(), r._status.messages
        assert isinstance(sort_broken._status, M.CannotEvaluate) and "linorder" in sort_broken._status.messages[0].unicode
        recalled = await session.call_tool("recall", {"node_id": "theory_TAT_Std_A"})      # the nodes at depth 1: no `english`
        shown = text_of(recalled).splitlines()
        assert not recalled.isError and shown[2:15] == [
            "  - datatype_list (complete)", "    " + one[0],
            "  - datatype_expr_bexp (complete)", *("    " + line for line in two[:2]),
            "  - datatype_either (complete)", '    (\'a, \'b) either (infixr "⊕" 60) = L "\'a" | R "\'b"',
            "  - datatype_bot (complete)", '    (\'a :: linorder) bot ("_⇩⊥" [21] 21) = Bot | Val "\'a" ("«_»" [21] 21)',
            "  - datatype_q (complete)", '    \'a q = N | Q "\'a ⇒ \'a q" (binder "QQ" 10)',
            "  - codatatype_stream (complete)", "    " + failed[1].strip()], shown
        assert shown[15] == "  - lemma_uses_the_syntax (valid statement, proof not started)", shown
        recalled = await session.call_tool("recall", {"node_id": "datatype_stream"})       # §8's last example whole
        assert not recalled.isError and text_of(recalled).splitlines() == failed, text_of(recalled)
    rendered = C.render(forest)
    file = rendered.files[C.Path("TAT_Suite/TAT_Std_A.thy")]
    assert file.startswith('theory "TAT_Std_A"\n  imports "Main" "TAT_Std.TAT_Std"\nbegin\n') and file.endswith("end\n")
    blocks = fenced_blocks(DT, "5.") + [
        ["text ‹Sums.›", 'datatype (\'a, \'b) either (infixr "⊕" 60) =', '    L "\'a"', '  | R "\'b"'],
        ["text ‹Lifted.›", 'datatype (\'a :: linorder) bot ("_⇩⊥" [21] 21) =', "    Bot", '  | Val "\'a" ("«_»" [21] 21)'],
        ["text ‹Binders.›", "datatype 'a q =", "    N", '  | Q "\'a ⇒ \'a q" (binder "QQ" 10)'],
        ["text ‹Streams.›", "codatatype 'a stream =", '    SCons "\'a" "\'a stream"']]
    for block in blocks:
        assert "".join(ascii_of_unicode(line) + "\n" for line in block) in file, file
    assert not any(C.Path(f"TAT_Suite/TAT_Std_{t}.thy") in rendered.files for t in "BC")   # an obstacle: not written
    await read_back(std_harness, file, tmp_path)
