"""`Typedef` (node_classes/TYPEDEF.md): with no Isabelle, the schema and the
descriptions (§2, §3), `gen`'s checks and refusals (§4), the definition as
the node holds, stores and prints it (§1, §2, §8), the node's name and the
framework's `DuplicateName` on it, the message, the status and the
recorded fields (§6), the carry on an amend (§4), the mark (§7), the
emitted text (§5); through the std harness, the evaluation (§6), `recall`
(§8) and the rendered file (§5).
Run: python -m pytest test/test_typedef.py
"""

import io
import json
import re

import jsoncomment
import pytest

import stand_ins
import test_session_theory as ts
from baselines import DOCS, fenced_blocks, fenced_lines
from harness import text_of
from invariants import assert_store_mirrors
from Isabelle_RPC_Host.unicode import IsaTerm, ascii_of_unicode
from isabelle_theory_agent import compile as C, edit, isabelle_driver, model as M
from isabelle_theory_agent.exceptions import DuplicateName, InvalidField, InvalidName, RawASTError, TAT_StartupError
from isabelle_theory_agent.jobs import NOT_STARTED, PASSED, RUNNING, Failed
from isabelle_theory_agent.std import common, typedef
from isabelle_theory_agent.std.common import NotInsideTheory, Template, Type_Parameter
from isabelle_theory_agent.std.typedef import LIFTING_NOTICE, OWING_LINE, Typedef
from isabelle_theory_agent.store import Forest_Store
from ml_process import ml_process, ml_string
from std_forest import KINDS, forest, insert, inv, refused
from test_descriptions import descriptions
from test_model import locked, run
from test_session_theory import Forest_Under_Test, session, theory
from test_theorem import BAD, INVALID, PROVED, lemma, with_proof

table = ts.table                    # the fake state slot table and the fake wire, per test
TD = DOCS / "node_classes" / "TYPEDEF.md"
COMMON = DOCS / "node_classes" / "COMMON.md"

DLIST = json.loads("\n".join(fenced_blocks(TD, "2.")[0]))      # §2's example, the construct of `'a dlist`
ERRORABLE_SYNTAX = {"form": "mixfix", "template": "_⇩⊥", "argument_priorities": [21], "priority": 21}


def definition(type_name="dlist", set="{xs :: 'a list. distinct xs}", english="Lists without repetition",
               type_parameters=({"name": "'a"},), **fields):
    """A construct of `typedef`: §2's example less its function names by default."""
    return {"kind": "typedef", "english": english, "type_parameters": list(type_parameters), "type_name": type_name,
            "set": set, **fields}


# §5's other two examples, the sort of `poly`'s parameter written inside its set; then one with the sort on the parameter
POLY = definition("poly", "{f :: nat ⇒ 'a::zero. ∀⇩∞ n. f n = 0}", "Polynomials, as their coefficient sequences",
                  rep_function_name="coeff")
ERRORABLE = definition("errorable", "UNIV :: 'a option set", "A type with an error value added", syntax=ERRORABLE_SYNTAX)
ZERO_ONLY = definition("zero_only", "{x :: 'a. x = 0}", "The zero alone", type_parameters=({"name": "'a", "sort": "zero"},))


# --- the schema and the descriptions (§2, §3) ------------------------------

def test_the_schema_and_the_descriptions_are_the_documents():
    [_, schema] = fenced_blocks(TD, "2.")
    text = re.sub(r'"\$defs": \{[^}]*\}.*', '"$defs": {}', "\n".join(schema))      # the spread and its comment
    expected = jsoncomment.JsonComment().loads(text)
    expected["$defs"] = {**common.TYPE_PARAMETER_DEFS, **common.TYPE_MIXFIX_DEFS}
    assert Typedef.construct_schema == expected
    assert list(typedef.KINDS) == ["typedef"]
    shared = [d for defs in (common.TYPE_PARAMETER_DEFS, common.TYPE_MIXFIX_DEFS) for d in descriptions(defs)]
    assert sorted(descriptions(Typedef.construct_schema)) == sorted(fenced_lines(TD, "3.") + shared)
    assert DLIST == definition(rep_function_name="list_of_dlist", abs_function_name="dlist_of_list")
    [_, notice] = fenced_blocks(TD, "6.")
    assert [LIFTING_NOTICE] == notice


# --- `gen` (§2, §4) ----------------------------------------------------------

def test_gen_keeps_the_definition_normalised_as_isaterms_and_names_the_node():
    f, x = forest(definition(set=" {xs :: 'a\n list.  distinct xs} ", english="Lists\n without  repetition ",
                             type_parameters=({"name": " 'a ", "sort": ""},),
                             syntax={"form": "mixfix", "template": "_\n\tdl  ", "argument_priorities": [21], "priority": 21},
                             rep_function_name=" list_of_dlist\n", abs_function_name="dlist_of_list"))
    (p,) = x.sub_nodes
    assert isinstance(p, Typedef) and p.kind == "typedef" and p.name == "dlist" and f.id_of(p) == "typedef_dlist"
    assert p.english == "Lists without repetition"
    assert p.type_parameters == (Type_Parameter(IsaTerm.from_agent("'a"), None),)
    assert p.syntax == Template(IsaTerm.from_agent("_  dl  "), (21,), 21)          # newlines and tabs alone, the spaces layout
    assert p.set == IsaTerm.from_agent("{xs :: 'a list. distinct xs}") and isinstance(p.set, IsaTerm)
    assert (p.rep_function_name, p.abs_function_name) == (IsaTerm.from_agent("list_of_dlist"), IsaTerm.from_agent("dlist_of_list"))
    assert (p.overloaded, p.lifting) == (None, None)                                  # recorded by an evaluation, none yet (§1)
    assert p.goal_state is not p.state and p.goal_state in p._states_inside()         # `Proof_Obligation`'s slot (COMMON §3)
    (q,) = insert(f, x, 1, [definition("pos", "{n :: nat. n > 0}", "Positive naturals", type_parameters=())])
    assert (q.type_parameters, q.syntax, q.rep_function_name, q.abs_function_name) == ((), None, None, None)
    (r,) = insert(f, x, 2, [{"kind": "typedef", "english": "All", "type_name": "u", "set": "UNIV :: nat set"}])
    assert r.type_parameters == () and f.id_of(r) == "typedef_u"                    # `type_parameters` left out: none (§2)
    inv(f)


def test_gen_refuses_as_section_4_says():
    """§4's refusals: the parent first (COMMON §1's `NotInsideTheory`, pinned
    for every class by test_common.py); a type name outside §1's grammar
    (RENDER_BASELINES §2's line); the type parameters by the shared check,
    each used in `set`, and the two function names by the shared check of
    the pair (COMMON §4's sentences, pinned by test_common.py) — a name
    beginning with `Rep_` or `Abs_` and a name equal to its default
    accepted, written into `morphisms` as given; a missing `set`, a binder
    syntax or a recorded field authored, by the framework."""
    f, x = forest()
    (s,) = f.sub_nodes
    e = refused(f, s, [definition("my-list")], NotInsideTheory)
    assert (e.kind, e.parent_id, e.raw_ast_path) == ("typedef", "session_Arith", "constructs[0]")
    [invalid] = [line for line in fenced_lines(DOCS / "RENDER_BASELINES.md", "2.")
                 if line.startswith("`my-list` is not a valid type name")]
    e = refused(f, x, [definition("my-list")], InvalidName)
    assert (e.name, e.grammar) == ("my-list", "type name") and str(e) == "At `constructs[0]`: " + invalid
    for name in ("1st", "dlist_", "a list", "x'y-", "", "α"):
        assert refused(f, x, [definition(name)], InvalidName).grammar == "type name"
    [identifier, twice] = [b for b in fenced_blocks(COMMON, "4.") if b[0].startswith("The field `rep_function_name`")][0]
    [unused] = [line for line in fenced_lines(COMMON, "4.") if line.endswith("which is not used.")]
    e = refused(f, x, [definition(rep_function_name="rep_")], InvalidField)
    assert str(e) == "At `constructs[0]`: " + identifier and e.field == "rep_function_name"
    assert identifier.endswith(": it " + invalid.split(": a type name ")[1])
    for name in ("1x", "x y", "", "rep-", "h\\<nat>"):
        assert refused(f, x, [definition(rep_function_name=name)], InvalidField).field == "rep_function_name"
    e = refused(f, x, [definition(abs_function_name="abs_")], InvalidField)
    assert str(e) == "At `constructs[0]`: " + identifier.replace("rep_function_name", "abs_function_name")
    e = refused(f, x, [definition(rep_function_name="list_of_dlist", abs_function_name="list_of_dlist")], InvalidField)
    assert str(e) == "At `constructs[0]`: " + twice.replace("list_of_fset", "list_of_dlist") and e.field == "abs_function_name"
    for field, name in (("rep_function_name", "Rep_dlist"), ("rep_function_name", "Abs_x"), ("rep_function_name", " Abs_dlist"),
                        ("abs_function_name", "Abs_dlist"), ("abs_function_name", "Rep_y")):   # a given name like any other
        (p,) = insert(f, x, 0, [definition(**{field: name})])
        assert p._definition(())[1] == "morphisms " + " ".join(
            name.strip() if g == field else d for g, d in (("rep_function_name", "Rep_dlist"), ("abs_function_name", "Abs_dlist")))
        run(locked(f, edit.delete(p)))
    # the type parameters: COMMON §4's check, its sentences pinned by test_common.py; then each used in `set`
    e = refused(f, x, [definition(type_parameters=({"name": "a"},))], InvalidField)
    assert (e.field, e.reason) == ("type_parameters[0].name", "must be a type variable, such as 'a")
    e = refused(f, x, [definition(type_parameters=({"name": "'a"}, {"name": "'a"}))], InvalidField)
    assert (e.field, e.reason) == ("type_parameters[1].name", "repeats `'a`")
    e = refused(f, x, [definition(type_parameters=({"name": "'a"}, {"name": "'b"}))], InvalidField)
    assert str(e) == "At `constructs[0]`: " + unused and e.field == "type_parameters[1]"
    assert refused(f, x, [definition(set="distinct")], InvalidField).field == "type_parameters[0]"
    # §4's order under two faults: the type name, then the parameters, their use, then the function names, Rep before Abs
    assert refused(f, x, [definition("my-list", type_parameters=({"name": "a"},), rep_function_name="rep_")], InvalidName).grammar == "type name"
    assert refused(f, x, [definition(type_parameters=({"name": "a"},), rep_function_name="rep_")], InvalidField).field == "type_parameters[0].name"
    assert refused(f, x, [definition(set="distinct", rep_function_name="rep_")], InvalidField).field == "type_parameters[0]"
    assert refused(f, x, [definition(rep_function_name="rep_", abs_function_name="abs_")], InvalidField).field == "rep_function_name"
    # the framework's integer bound (MODULE_STRUCTURE §4.4), RENDER_BASELINES §2's line, the forest unchanged
    [bound] = [line for line in fenced_lines(DOCS / "RENDER_BASELINES.md", "2.") if line.endswith("must be a 64-bit integer.")]
    e = refused(f, x, [definition(syntax={"form": "infixr", "symbol": "+", "priority": 2**64})], InvalidField)
    assert str(e) == "At `constructs[0]`: " + bound.replace("types[0].constructors[1].syntax", "syntax") and e.field == "syntax.priority"
    for raw in ({"kind": "typedef", "english": "e", "type_name": "t"},                                     # no `set`
                {"kind": "typedef", "english": "e", "type_name": "t", "set": "UNIV",
                 "syntax": {"form": "binder", "symbol": "+", "priority": 1}},                            # no binder on a type
                {"kind": "typedef", "english": "e", "type_name": "t", "set": "UNIV", "overloaded": True},  # recorded, not authored (§2)
                {"kind": "typedef", "english": "e", "type_name": "t", "set": "UNIV", "lifting": True}):
        refused(f, x, [raw], RawASTError)
    assert x.sub_nodes == []
    inv(f)


def test_a_sibling_bearing_the_node_s_id_component_is_the_framework_s_duplicate_name():
    f, x = forest(DLIST)
    e = refused(f, x, [definition(set="UNIV :: 'a list set")], DuplicateName)
    assert e.id_component == "typedef_dlist" and e.taken_by == "typedef_dlist"
    inv(f)


def test_an_amend_with_the_same_goal_structure_carries_the_proof():
    """§4: equal `type_parameters` and `set` carry the replaced job's
    outcome — a changed `type_name`, function name, `syntax` or `english`
    aside; a changed `set` or type parameter does not; the stored check is
    never carried (CONSTRUCT_INTERACTION §3.1)."""
    f, x = forest(DLIST)
    (p,) = x.sub_nodes
    with_proof(p, M.READY_CLEAN, PROVED, PASSED)
    p.lifting = True
    (p2,) = run(locked(f, edit.amend(p, [definition("dl", english="Another wording", syntax=ERRORABLE_SYNTAX,
                                                    rep_function_name="rep", abs_function_name="abs")], KINDS)))
    assert p2.job().outcome == PROVED and p2.check_outcome() is None and p2.name == "dl"
    assert p2.lifting is None                               # the recorded choice is the evaluation's to make again (COMMON §5)
    assert p2.goal_structure() == p.goal_structure() == ([("'a", None)], "{xs :: 'a list. distinct xs}")
    (p3,) = run(locked(f, edit.amend(p2, [definition("dl", set="{xs :: 'a list. sorted xs}")], KINDS)))
    assert p3.job().outcome is NOT_STARTED                  # the set changed
    p3.job().outcome = PROVED
    (p4,) = run(locked(f, edit.amend(p3, [definition("dl", set="{xs :: 'a list. sorted xs}",
                                                     type_parameters=({"name": "'a", "sort": "linorder"},))], KINDS)))
    assert p4.job().outcome is NOT_STARTED                  # a parameter's sort changed
    inv(f)


# --- the store (§1, §2) --------------------------------------------------------

def test_the_definition_is_stored_and_a_missing_row_is_refused_at_start(tmp_path):
    path = tmp_path / "TAT.sqlite"
    f, x = forest(DLIST, ERRORABLE, ZERO_ONLY, store=Forest_Store(path, ts.stand_ins.log()))
    nodes = x.sub_nodes
    nodes[1].overloaded, nodes[1].lifting = True, False           # as evaluations record them (§6), unequal; `dlist` None at birth
    nodes[2].overloaded, nodes[2].lifting = False, True
    with f.store.transaction():
        for n in nodes:
            f._store_node(n)

    def fields(n):
        return (n.name, n.english, n.type_parameters, n.syntax, n.set, n.rep_function_name, n.abs_function_name,
                n.overloaded, n.lifting)
    before = [fields(n) for n in nodes]
    rows = f.store.fields(nodes[0].identity)
    assert "name" not in rows and rows["type_name"] == "dlist" and rows["set"] == "{xs :: 'a list. distinct xs}"
    assert rows["syntax"] is None and rows["rep_function_name"] == "list_of_dlist"      # a field left out: a None-valued row
    assert rows["abs_function_name"] == "dlist_of_list" and (rows["overloaded"], rows["lifting"]) == (None, None)
    rows = f.store.fields(nodes[1].identity)
    assert rows["syntax"] == ERRORABLE_SYNTAX and rows["rep_function_name"] is None
    assert (rows["overloaded"], rows["lifting"]) == (True, False)
    rows = f.store.fields(nodes[2].identity)
    assert rows["type_parameters"] == [{"name": "'a", "sort": "zero"}] and rows["rep_function_name"] is None
    assert (rows["overloaded"], rows["lifting"]) == (False, True)
    f.store.close()
    f2 = Forest_Under_Test(store=Forest_Store(path, ts.stand_ins.log()), kinds=KINDS)
    loaded = f2.sub_nodes[0].sub_nodes[0].sub_nodes
    assert [fields(n) for n in loaded] == before and all(isinstance(n, Typedef) for n in loaded)
    assert loaded[0].goal_state.name != nodes[0].goal_state.name and loaded[0].goal_state in loaded[0]._states_inside()
    f2.store.close()
    # a row missing — an authored field's or a recorded one's — is refused at start (§1)
    for field in ("set", "rep_function_name", "overloaded", "lifting"):
        store = Forest_Store(path, ts.stand_ins.log())
        identity = nodes[0].identity
        rows = store.fields(identity)
        with store.transaction():
            store.delete_node(identity)
            for name, value in rows.items():
                if name != field:
                    store.put(identity, name, value)
        store.close()
        with pytest.raises(TAT_StartupError, match=field):
            Forest_Under_Test(store=Forest_Store(path, ts.stand_ins.log()), kinds=KINDS)
        store = Forest_Store(path, ts.stand_ins.log())
        with store.transaction():
            store.put(identity, field, rows[field])
        store.close()


# --- the message, the status and the recorded fields (§6), the mark (§7) ------

def test_eval_opr_sends_the_definition_and_records_what_the_steps_yielded(monkeypatch):
    """COMMON §3's `_eval_opr` with `Typedef`'s own: the message in §6's
    order — the definition, its goal part last, then the recorded
    `overloaded` and the recorded `lifting`; the pair the two steps yielded
    recorded as `overloaded` and `lifting`, the `Ready` carrying the notice
    exactly when `lifting` is false; Isabelle's messages an obstacle, the
    recorded fields untouched — under recorded values too, which the
    message carries (COMMON §5); a syntax on the wire as `mixfix_text`
    writes it, in `ascii`."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        DLIST, POLY, definition("bad", "distinct :: 'a list ⇒ bool", "A predicate is no set",
                                rep_function_name="list_of_dlist", abs_function_name="dlist_of_list")]})])
    # a fake theory: its header runs no call
    (x,) = s.sub_nodes
    p, q, r = x.sub_nodes
    calls = []

    async def call(conversation, name, args):
        calls.append((name, args))
        (type_name, *_), _, recorded = args[3]
        if type_name == "bad":              # Isabelle's one message of two lines (typedef.ML, cat_error)
            return [['Not a set type: "\'a list \\<Rightarrow> bool"\nThe error(s) above occurred in typedef "bad"'], None]
        if recorded is True and type_name == "poly":    # `setup_lifting` refused under a recorded true: the failure (§6)
            return [['Duplicate fact declaration "X.poly.domain" vs. "X.domain"'], None]
        return [[], [type_name == "poly", type_name == "dlist"]]    # poly: `(overloaded)` needed, lifting refused
    monkeypatch.setattr(isabelle_driver, "call", call)
    r.overloaded, r.lifting = True, True                        # as an earlier successful evaluation recorded them (§6)
    run(x.evaluate_to(None, False))
    assert [name for name, _ in calls] == ["TAT.Typedef.evaluate"] * 3
    assert [args[:3] for _, args in calls] == [
        (n.state.to_msgpack(), n.goal_state.to_msgpack(), n.resulting_state().to_msgpack()) for n in (p, q, r)]
    assert calls[0][1][3] == (
        ("dlist", None, "list_of_dlist", "dlist_of_list", [("'a", None)], "{xs :: 'a list. distinct xs}"), None, None)
    assert calls[1][1][3] == (("poly", None, "coeff", "Abs_poly", [("'a", None)],
                               "{f :: nat \\<Rightarrow> 'a::zero. \\<forall>\\<^sub>\\<infinity> n. f n = 0}"), None, None)
    assert calls[2][1][3][1:] == (True, True)                                 # the recorded choices travel (COMMON §5)
    assert p.message()[0][4:] == p.goal_structure() and q.message()[0][4:] == q.goal_structure()
    assert isinstance(p._status, M.Ready) and p._status.messages == () and (p.overloaded, p.lifting) == (False, True)
    assert isinstance(q._status, M.Ready) and [m.unicode for m in q._status.messages] == [LIFTING_NOTICE]
    assert (q.overloaded, q.lifting) == (True, False)
    assert (p.message()[1:], q.message()[1:]) == ((False, True), (True, False))   # recorded: what the next evaluation keeps to
    assert isinstance(r._status, M.CannotEvaluate) and (r.overloaded, r.lifting) == (True, True)    # untouched by a failure
    assert [m.unicode for m in r._status.messages] == ['Not a set type: "\'a list ⇒ bool"\nThe error(s) above occurred in typedef "bad"']
    assert p.mark(M.BRIEFING, 0) == "unverified definition, proof not started" and r.mark(M.BRIEFING, 0) == "invalid definition"
    assert not p.is_finished() and not r.is_finished()                     # the proof is compulsory (COMMON §3)
    # under a recorded `lifting` true, `setup_lifting`'s refusal is the definition's failure, the record untouched (§6)
    q.lifting = True
    status = run(q._eval_opr())
    assert calls[-1][1][3] == (calls[1][1][3][0], True, True)
    assert isinstance(status, M.CannotEvaluate) and (q.overloaded, q.lifting) == (True, True)
    assert [m.unicode for m in status.messages] == ['Duplicate fact declaration "X.poly.domain" vs. "X.domain"']
    t, z = insert(f, x, 3, [ERRORABLE, ZERO_ONLY])
    assert t.message() == (("errorable", '("_\\<^sub>\\<bottom>" [21] 21)', "Rep_errorable", "Abs_errorable", [("'a", None)],
                            "UNIV :: 'a option set"), None, None)
    assert z.message() == (("zero_only", None, "Rep_zero_only", "Abs_zero_only", [("'a", "zero")], "{x :: 'a. x = 0}"),
                           None, None)
    assert t.mark(M.BRIEFING, 0) == "not evaluated, proof not started"


def test_the_recorded_fields_reach_the_store_and_the_mirror_catches_an_emit_off_an_instant_status(monkeypatch):
    """§1, §6; COMPILATION §3: a walk's store writes `overloaded` and
    `lifting` as the evaluation recorded them, so a loaded forest emits the
    same file; an `emit` reading the instant status instead writes
    `setup_lifting` in memory and not once loaded, which
    `assert_store_mirrors` says at once."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [DLIST, POLY]})])
    (x,) = s.sub_nodes
    p, q = x.sub_nodes

    async def call(conversation, name, args):
        return [[], [args[3][0][0] == "poly", args[3][0][0] == "dlist"]]
    monkeypatch.setattr(isabelle_driver, "call", call)
    run(x.evaluate_to(None, False))
    rows = {n.name: f.store.fields(n.identity) for n in (p, q)}
    assert (rows["dlist"]["overloaded"], rows["dlist"]["lifting"]) == (False, True)
    assert (rows["poly"]["overloaded"], rows["poly"]["lifting"]) == (True, False)
    assert_store_mirrors(f, KINDS, shape=ts.shape)                           # `emit` as shipped: mirrored
    emit = Typedef.emit

    def off_the_instant_status(self, indent, out):
        recorded, self.lifting = self.lifting, all(isinstance(st, M.Ready) for st in self.evaluation_statuses())
        try:
            return emit(self, indent, out)
        finally:
            self.lifting = recorded
    monkeypatch.setattr(Typedef, "emit", off_the_instant_status)
    with pytest.raises(AssertionError, match="Arith/X.thy: the loaded forest writes another text"):
        assert_store_mirrors(f, KINDS, shape=ts.shape)


def test_the_mark_reads_one_of_eleven_ways_and_the_owing_line_stands_while_unverified():
    """§7's mark, state by state — COMMON §3's table with the three words of
    a class that defines: `valid definition` alone once the proof stands,
    `unverified definition` with the proof's word before; the eleven, and
    no other, are the document's first block; the owing line, its second,
    exactly while the line reads `unverified definition`."""
    [block, state] = fenced_blocks(TD, "7.")
    assert [OWING_LINE] == state
    f, x = forest(DLIST)
    (p,) = x.sub_nodes
    assert p.mark(M.BRIEFING, 0) == "not evaluated, proof not started" and p.owing_line() is None
    proof = [(NOT_STARTED, None, "proof not started"), (RUNNING, None, "proving"), (Failed("no"), None, "failed to prove"),
             (PROVED, None, "unchecked proof"), (PROVED, RUNNING, "proof checking"), (PROVED, PASSED, None),
             (PROVED, BAD, "bad proof")]
    marks = set()
    for outcome, check, word in proof:
        with_proof(p, M.READY_CLEAN, outcome, check)
        expected = "valid definition" if word is None else f"unverified definition, {word}"
        assert p.mark(M.BRIEFING, 0) == expected, (outcome, check)
        assert p.owing_line() == (None if word is None else OWING_LINE), (outcome, check)
        marks.add(f"({expected})")
        with_proof(p, INVALID, outcome, check)
        assert p.mark(M.BRIEFING, 0) == "invalid definition" and p.owing_line() is None, (outcome, check)
        marks.add("(invalid definition)")
        if outcome is not RUNNING and check is None:    # no run and no check live under `not evaluated`
            with_proof(p, M.NOT_EVALUATED, outcome, check)
            expected = "not evaluated" if outcome is PROVED else f"not evaluated, {word}"
            assert p.mark(M.BRIEFING, 0) == expected and p.owing_line() is None, (outcome, check)
            marks.add(f"({expected})")
    assert len(marks) == 11 and marks == set(re.findall(r"\([^)]*\)", "\n".join(block)))


# --- what it prints (§8) -----------------------------------------------------

def test_print_fields_writes_the_definition_and_english_by_depth():
    f, x = forest(DLIST, ERRORABLE, POLY, definition("u", "UNIV", "All", type_parameters=()), ZERO_ONLY)
    p, q, t, u, z = x.sub_nodes
    [one, failed, notice, bad] = fenced_blocks(TD, "8.")

    def fields(node, mode, depth):
        out = io.StringIO()
        node.print_fields(0, out, mode, depth)
        return out.getvalue().splitlines()
    assert [fields(p, M.RECALL, d) for d in range(4)] == [one, one[:1], one[:1], []]
    assert fields(p, M.OUT_FOCUS, 0) == [] and fields(p, M.Relative_Focus(frozenset({p}), 0), 0) == []
    p.overloaded = p.lifting = True                                      # neither is printed: neither is authored (§8)
    assert fields(p, M.RECALL, 0) == one
    assert fields(q, M.RECALL, 1) == ['\'a errorable ("_⇩⊥" [21] 21) = "UNIV :: \'a option set"']       # no `morphisms` clause
    # against no keyword, whatever the theory recorded: every name bare, the set and a sort quoted unless an identifier
    for keywords in (None, frozenset(), frozenset({"dlist", "UNIV", "zero", "coeff", "list_of_dlist", "u"})):
        x.keywords = keywords
        assert fields(t, M.RECALL, 1) == ['\'a poly = "{f :: nat ⇒ \'a::zero. ∀⇩∞ n. f n = 0}" morphisms coeff Abs_poly']
        assert fields(z, M.RECALL, 1) == ['(\'a :: zero) zero_only = "{x :: \'a. x = 0}"']
        assert fields(u, M.RECALL, 1) == ["u = UNIV"] and fields(p, M.RECALL, 1) == one[:1], keywords
    me = stand_ins.agent(f.conversation)
    with_proof(p, M.READY_CLEAN, PROVED, BAD)                            # §8's last example whole, with its mark
    assert f.render(p, M.RECALL, me).splitlines() == bad
    with_proof(p, M.NOT_EVALUATED, NOT_STARTED)                          # back to a node no walk reached
    # §8's two other examples, in a theory of their own: the refused definition's fields, the notice's node whole
    (s,) = f.sub_nodes
    (y,) = insert(f, s, 1, [theory("Y") | {"children": [
        definition(set="distinct :: 'a list ⇒ bool", rep_function_name="list_of_dlist", abs_function_name="dlist_of_list"),
        definition("fm", "UNIV :: (nat, nat) fmap set", "Finite maps from naturals to naturals, as a type of their own",
                   type_parameters=())]}])
    v, w = y.sub_nodes
    assert fields(v, M.RECALL, 0) == [line.strip() for line in failed[1:3]]
    with_proof(w, M.Ready((IsaTerm.from_agent(LIFTING_NOTICE),)), PROVED, PASSED)
    assert f.render(w, M.RECALL, me).splitlines() == notice
    with_proof(w, M.NOT_EVALUATED, NOT_STARTED)
    inv(f)


# --- emission (§5) ------------------------------------------------------------

def test_the_emitted_text_is_section_5_s():
    [one, two, three] = fenced_blocks(TD, "5.")
    f, x = forest(DLIST, POLY, ERRORABLE)
    p, q, r = x.sub_nodes
    x.keywords = frozenset()                                 # recorded by a header run, which emission presupposes

    def emitted(node) -> list[str]:
        """In `unicode` (§5); the file's `\\<name>` form is the compile's conversion (COMPILATION §2)."""
        out = io.StringIO()
        assert node.emit(1, out) == 1
        assert "\\<" not in out.getvalue()                                 # nothing written in `ascii`
        return out.getvalue().splitlines()

    def expected(*unicode_lines: str) -> list[str]:
        return ["  " + line for line in unicode_lines]
    with pytest.raises(AssertionError):                             # nothing recorded: never written (`can_emit`; COMMON §5)
        emitted(p)
    for p.overloaded, p.lifting in ((False, None), (None, False)):  # either field unrecorded still
        with pytest.raises(AssertionError):
            emitted(p)
    p.overloaded = p.lifting = False
    assert emitted(p) == expected(*one[:3], "  sorry")              # both recorded false, no proof: no option, no line, `sorry`
    for node, recorded in ((p, (False, True)), (q, (True, True)), (r, (False, True))):      # as §5's examples record them
        node.overloaded, node.lifting = recorded
        with_proof(node, M.READY_CLEAN, PROVED, PASSED)
    assert emitted(p) == expected(*one) and emitted(q) == expected(*two) and emitted(r) == expected(*three)
    for outcome, check in ((PROVED, BAD), (PROVED, None), (PROVED, RUNNING), (Failed("no"), None)):
        with_proof(p, M.READY_CLEAN, outcome, check)                                     # not proven: `sorry`
        assert emitted(p) == expected(*one[:3], "  sorry", one[4]), (outcome, check)
    p.lifting = False
    assert emitted(p) == expected(*one[:3], "  sorry")                                   # lifting not set up: no line
    with_proof(p, M.READY_CLEAN, PROVED, PASSED)
    p.lifting = True
    x.keywords = frozenset({"dlist", "list_of_dlist", "dlist_of_list", "zero", "UNIV", "type_definition_dlist"})   # keywords: quoted (§5)
    assert emitted(p) == expected("text ‹Lists without repetition.›", 'typedef \'a "dlist" = "{xs :: \'a list. distinct xs}"',
                                  '  morphisms "list_of_dlist" "dlist_of_list"', "  by aoa", 'setup_lifting "type_definition_dlist"')
    assert emitted(q)[1] == '  typedef (overloaded) \'a poly = "{f :: nat ⇒ \'a::zero. ∀⇩∞ n. f n = 0}"'
    assert emitted(r)[1:3] == expected('typedef \'a errorable ("_⇩⊥" [21] 21) = "UNIV :: \'a option set"', "  by aoa")
    z, u = insert(f, x, 3, [ZERO_ONLY, definition("u", "UNIV", "All", type_parameters=())])
    z.overloaded = z.lifting = u.overloaded = u.lifting = False                      # recorded, as emission presupposes
    assert emitted(z)[1:] == expected('typedef (\'a :: "zero") zero_only = "{x :: \'a. x = 0}"', "  sorry")   # a sort quoted
    assert emitted(u)[1:] == expected('typedef u = "UNIV"', "  sorry")                                       # a set quoted
    x.keywords = frozenset()
    assert emitted(z)[1] == "  typedef ('a :: zero) zero_only = \"{x :: 'a. x = 0}\""
    assert emitted(u)[1] == "  typedef u = UNIV"                                                    # a set that is an identifier
    # the Abs name alone given: Rep written as its default; an infix syntax; two parameters
    (t,) = insert(f, x, 5, [definition("sum", "UNIV :: ('a + 'b) set", "Sums!", type_parameters=({"name": "'a"}, {"name": "'b"}),
                                       syntax={"form": "infixr", "symbol": "⊕", "priority": 60}, abs_function_name="mk_sum")])
    t.overloaded = t.lifting = False
    assert emitted(t) == expected("text ‹Sums!›", 'typedef (\'a, \'b) sum (infixr "⊕" 60) = "UNIV :: (\'a + \'b) set"',
                                  "  morphisms Rep_sum mk_sum", "  sorry")


def test_the_two_spellings_are_kept_apart():
    """§2, §5, §8: a name, a parameter or a set whose `unicode` and `ascii`
    differ is stored, printed and emitted in `unicode` and sent to Isabelle
    in `ascii`."""
    f, x = forest(definition("t", "{x :: 'α. x ≠ ε}", "Greek", type_parameters=({"name": "'α", "sort": "linorder"},),
                             rep_function_name="ρ", abs_function_name="α⇩1"))
    (p,) = x.sub_nodes
    x.keywords = frozenset()
    assert p.message() == (("t", None, "\\<rho>", "\\<alpha>\\<^sub>1", [("'\\<alpha>", "linorder")],
                            "{x :: '\\<alpha>. x \\<noteq> \\<epsilon>}"), None, None)
    rows = {}
    p.to_store(type("Rows", (), {"put": lambda self, k, v: rows.__setitem__(k, v)})())
    assert rows["type_parameters"] == [{"name": "'α", "sort": "linorder"}] and rows["set"] == "{x :: 'α. x ≠ ε}"
    assert (rows["rep_function_name"], rows["abs_function_name"]) == ("ρ", "α⇩1")
    out = io.StringIO()
    p.print_fields(0, out, M.RECALL, 1)
    assert out.getvalue() == "('α :: linorder) t = \"{x :: 'α. x ≠ ε}\" morphisms ρ α⇩1\n"
    out = io.StringIO()
    p.overloaded = p.lifting = False                                    # recorded, as emission presupposes
    p.emit(0, out)
    assert out.getvalue().splitlines()[1:3] == ["typedef ('α :: linorder) t = \"{x :: 'α. x ≠ ε}\"", "  morphisms ρ α⇩1"]


# --- the evaluation, in the plugin's run of the harness (§5, §6, §8) --------

@pytest.mark.isabelle(deadline=300)
async def test_a_subtype_is_defined_and_lifting_set_up(std_conversation, std_harness, tmp_path):
    """§6 through `TAT.Typedef.evaluate`: a theory of §2's `dlist`, §5's
    `poly` — its set open on `zero`, `(overloaded)` recorded — and
    `errorable` with its type syntax, and a `t2` whose Rep function is
    named `domain`, a fact `setup_lifting` declares under the type —
    `lifting` false, the notice on the `Ready` —, each defined with its
    goal in `goal_state` and the resulting slot written, then a theorem
    whose statement parses only through the morphisms, the syntax and the
    relation `setup_lifting` defines; `recall` as §8 shows; the theory
    rendered as §5 shows, under the recorded keywords, and read back whole
    by Isabelle.  Last, the callback alone: `[[], [a, b]]` on the wire; and
    the recorded values' rule (COMMON §5) through it, on slots beside the
    tree's: a recorded value runs once, a refusal under it the failure."""
    forest = std_conversation.forest
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [ts.session("TAT_Suite", ts.theory("TAT_Std_A") | {"children": [
                DLIST, POLY, ERRORABLE,
                definition("t2", "UNIV :: nat set", "A copy of the naturals", type_parameters=(), rep_function_name="domain"),
                ZERO_ONLY,
                lemma("uses_the_definitions", english="Every definition above parses",
                      for_any=({"name": "xs", "type": "'a list"}, {"name": "y", "type": "nat⇩⊥"},
                               {"name": "p", "type": "'b::zero poly"}),
                      premises=(),
                      conclusion="list_of_dlist (dlist_of_list xs) = xs ∧ y = y ∧ coeff p 0 = coeff p 0"
                                 " ∧ pcr_dlist = pcr_dlist ∧ domain (Abs_t2 0) = 0")]})]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 0 and text.count("Notice:") == 1, text
        (s,) = forest.sub_nodes
        (a,) = s.sub_nodes
        dlist, poly, errorable, t2, zero_only, uses = a.sub_nodes
        for node in (dlist, poly, errorable, t2, zero_only, uses):
            assert isinstance(node._status, M.Ready), (node.name, node._status)
            assert await node.goal_state.is_initialized() and await node.resulting_state().is_initialized()
        assert [(n.overloaded, n.lifting) for n in (dlist, poly, errorable, t2, zero_only)] == [
            (False, True), (True, True), (False, True), (False, False), (True, True)]
        assert all(n._status.messages == () for n in (dlist, poly, errorable, zero_only, uses))
        assert [m.unicode for m in t2._status.messages] == [LIFTING_NOTICE]
        [one, _, notice, _] = fenced_blocks(TD, "8.")
        recalled = await session.call_tool("recall", {"node_id": "typedef_t2"})                          # §8's notice
        lines = text_of(recalled).splitlines()
        assert not recalled.isError and lines == [
            "- typedef_t2 (unverified definition, proof not started)", '  t2 = "UNIV :: nat set" morphisms domain Abs_t2',
            "  A copy of the naturals", *notice[3:5], "  " + OWING_LINE], lines
        recalled = await session.call_tool("recall", {"node_id": "theory_TAT_Std_A"})      # the nodes at depth 1: no `english`
        shown = text_of(recalled).splitlines()
        assert not recalled.isError and shown[:20] == [
            "- theory_TAT_Std_A (incomplete)", "  imports: Main",
            "  - typedef_dlist (unverified definition, proof not started)", "    " + one[0], "    " + OWING_LINE,
            "  - typedef_poly (unverified definition, proof not started)",
            '    \'a poly = "{f :: nat ⇒ \'a::zero. ∀⇩∞ n. f n = 0}" morphisms coeff Abs_poly', "    " + OWING_LINE,
            "  - typedef_errorable (unverified definition, proof not started)",
            '    \'a errorable ("_⇩⊥" [21] 21) = "UNIV :: \'a option set"', "    " + OWING_LINE,
            "  - typedef_t2 (unverified definition, proof not started)", '    t2 = "UNIV :: nat set" morphisms domain Abs_t2',
            "    Notice:", "      " + LIFTING_NOTICE, "    " + OWING_LINE,
            "  - typedef_zero_only (unverified definition, proof not started)", '    (\'a :: zero) zero_only = "{x :: \'a. x = 0}"',
            "    " + OWING_LINE,
            "  - lemma_uses_the_definitions (valid statement, proof not started)"], shown
    rendered = C.render(forest)
    file = rendered.files[C.Path("TAT_Suite/TAT_Std_A.thy")]
    assert file.startswith('theory "TAT_Std_A"\n  imports "Main" "TAT_Std.TAT_Std"\nbegin\n') and file.endswith("end\n")
    [one, two, three] = fenced_blocks(TD, "5.")
    blocks = [[*one[:3], "  sorry", one[4]], [*two[:3], "  sorry", two[4]], [*three[:2], "  sorry", three[3]],
              ["text ‹A copy of the naturals.›", 'typedef t2 = "UNIV :: nat set"', "  morphisms domain Abs_t2", "  sorry"],
              ["text ‹The zero alone.›", 'typedef (overloaded) (\'a :: zero) zero_only = "{x :: \'a. x = 0}"', "  sorry",
               "setup_lifting type_definition_zero_only"]]
    for block in blocks:
        assert "".join(ascii_of_unicode(line) + "\n" for line in block) in file, file
    assert "setup_lifting type_definition_t2" not in file
    # the file's body read back whole by Isabelle on the heap's Main, through the same commands
    body = tmp_path / "body.thy"
    body.write_text(file[file.index("begin\n") + len("begin\n"):file.rindex("end\n")])
    r = await ml_process(std_harness, f'val _ = after thy0 (File.read (Path.explode {ml_string(str(body))}));\n'
                                           'writeln "read back";')
    assert r.returncode == 0 and "read back" in r.stdout.splitlines(), (r.stdout, r.stderr)
    # the callback alone: the pair the two steps yielded, `[[], [a, b]]` (COMMON §3)
    messages, what = await isabelle_driver.call(
        forest.conversation, "TAT.Typedef.evaluate",
        (poly.state.to_msgpack(), poly.goal_state.to_msgpack(), poly.resulting_state().to_msgpack(), poly.message()))
    assert (messages, what) == ([], [True, True])
    messages, what = await isabelle_driver.call(
        forest.conversation, "TAT.Typedef.evaluate",
        (t2.state.to_msgpack(), t2.goal_state.to_msgpack(), t2.resulting_state().to_msgpack(), t2.message()))
    assert (messages, what) == ([], [False, False])
    # under a recorded `lifting`, on slots beside the tree's (COMMON §5): false, `setup_lifting` not run — `dlist`'s would be
    # accepted —; true on `t2`, whose `setup_lifting` Isabelle refuses, the definition's failure with Isabelle's message
    goal, resulting = (M.Isar_State_Slot.assign(forest.conversation) for _ in range(2))
    messages, what = await isabelle_driver.call(
        forest.conversation, "TAT.Typedef.evaluate",
        (dlist.state.to_msgpack(), goal.to_msgpack(), resulting.to_msgpack(), (dlist.message()[0], dlist.overloaded, False)))
    assert (messages, what) == ([], [False, False])
    messages, what = await isabelle_driver.call(
        forest.conversation, "TAT.Typedef.evaluate",
        (t2.state.to_msgpack(), goal.to_msgpack(), resulting.to_msgpack(), (t2.message()[0], t2.overloaded, True)))
    assert what is None and len(messages) == 1 and "domain" in messages[0], messages
    # under a recorded `overloaded`: true on `dlist`, which needs no option, run once and through; false on `poly`, which
    # needs it, refused at the open with Isabelle's demand, nothing yielded (§6)
    messages, what = await isabelle_driver.call(
        forest.conversation, "TAT.Typedef.evaluate",
        (dlist.state.to_msgpack(), goal.to_msgpack(), resulting.to_msgpack(), (dlist.message()[0], True, dlist.lifting)))
    assert (messages, what) == ([], [True, True])
    messages, what = await isabelle_driver.call(
        forest.conversation, "TAT.Typedef.evaluate",
        (poly.state.to_msgpack(), goal.to_msgpack(), resulting.to_msgpack(), (poly.message()[0], False, poly.lifting)))
    assert what is None and len(messages) == 1 and "Type definition with open dependencies" in messages[0], messages


@pytest.mark.isabelle(deadline=300)
async def test_a_refused_definition_and_a_refused_admission_are_obstacles(std_conversation):
    """§6, §8: a `dlist` whose set is a predicate where a set is expected, is
    an obstacle with Isabelle's messages, `goal_state` empty, shown under
    `recall` as §8's example; a `g` whose Rep name `g_inverse` is the fact the
    admission notes under it is an obstacle too, nothing recorded,
    `goal_state` empty; neither theory is written."""
    forest = std_conversation.forest
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [ts.session("TAT_Suite",
                                      ts.theory("TAT_Std_B") | {"children": [
                                          definition(set="distinct :: 'a list ⇒ bool", rep_function_name="list_of_dlist",
                                                     abs_function_name="dlist_of_list")]},
                                      ts.theory("TAT_Std_C") | {"children": [
                                          definition("g", "UNIV :: nat set", "A copy whose Rep name is a fact the admission notes",
                                                     type_parameters=(), rep_function_name="g_inverse", abs_function_name="g")]})]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 2, text
        (s,) = forest.sub_nodes
        b, c = s.sub_nodes
        (bad,) = b.sub_nodes
        (g,) = c.sub_nodes
        [_, failed, _, _] = fenced_blocks(TD, "8.")
        assert isinstance(bad._status, M.CannotEvaluate) and not await bad.goal_state.is_initialized()
        assert [m.unicode for m in bad._status.messages] == ["\n".join(line.strip() for line in failed[4:6])]   # one message, two lines
        assert (bad.overloaded, bad.lifting) == (None, None)                                   # nothing recorded (§1)
        recalled = await session.call_tool("recall", {"node_id": "typedef_dlist"})                      # §8's example whole
        assert not recalled.isError and text_of(recalled).splitlines() == failed, text_of(recalled)
        assert isinstance(g._status, M.CannotEvaluate) and (g.overloaded, g.lifting) == (None, None)
        assert g._status.messages[0].unicode.startswith("Duplicate fact declaration"), g._status.messages
        assert not await g.goal_state.is_initialized()      # emptied; after the walk the resulting slot holds the framework's
                                                            # copy of the input, so it says nothing of the callback
    rendered = C.render(forest)
    assert not any(C.Path(f"TAT_Suite/TAT_Std_{t}.thy") in rendered.files for t in "BC")   # an obstacle: not written
