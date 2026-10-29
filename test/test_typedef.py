"""`Typedef` (node_classes/TYPEDEF.md): with no Isabelle, the schema and the
descriptions (§2, §3), `gen` and the field check (§4), the definition as
the node holds, stores and prints it (§1, §2, §8), the node's name and the
framework's `DuplicateName` on it, the beginning's message and status and
the recorded `lifting`, the ending's call or its copy, the block refusing
children (§6), the carry on an amend (§4), the mark (§7), the emitted
text (§5), the id properties (§9); through the std harness, the
evaluation (§6), `recall` (§8), the rendered file (§5), the proof check
(§7) and the block's closing and refusing for real.
Run: python -m pytest test/test_typedef.py
"""

import io
import json
import re

import jsoncomment
import pytest

import stand_ins
import test_ids
import test_model as tm
import test_session_theory as ts
from baselines import DOCS, composed_refusal, fenced_blocks, fenced_lines
from harness import text_of
from invariants import assert_store_mirrors
from Isabelle_RPC_Host.unicode import IsaTerm, ascii_of_unicode
from isabelle_theory_agent import compile as C, edit, isabelle_driver, model as M
from isabelle_theory_agent.exceptions import (
    BadTheoryNodeParent, DuplicateName, InvalidField, InvalidName, RawASTError)
from isabelle_theory_agent.jobs import NOT_STARTED, PASSED, RUNNING, Failed, Succeeded
from isabelle_theory_agent.std import common, typedef
from isabelle_theory_agent.std.common import Lifting_Closing, Template, Type_Parameter
from isabelle_theory_agent.std.lift_definition import LiftDefinition, OWING_LINE as LD_OWING_LINE
from isabelle_theory_agent.std.typedef import LIFTING_NOTICE, OWING_LINE, Typedef
from isabelle_theory_agent.store import Forest_Store
from ml_process import read_back
from std_forest import (
    KINDS, assert_a_missing_row_is_refused_at_start, field_check, forest, insert, inv, refused, reloaded)
from test_descriptions import descriptions
from test_model import locked, run
from test_session_theory import Forest_Under_Test, session, theory
from test_theorem import BAD, INVALID, PROVED, lemma, with_proof

table = ts.table                    # the fake state slot table and the fake wire, per test
TD = DOCS / "node_classes" / "TYPEDEF.md"
COMMON = DOCS / "node_classes" / "COMMON.md"
BASELINES = DOCS / "RENDER_BASELINES.md"
[LIFTING_REFUSAL] = fenced_blocks(COMMON, "6.")[0]          # the sentence's one home; test_common pins the constant to it
[IDENTIFIER, TWICE] = [b for b in fenced_blocks(COMMON, "4.") if b[0].startswith("The field `rep_function_name`")][0]   # COMMON §4's, of a function name

DLIST = json.loads("\n".join(fenced_blocks(TD, "2.")[0]))      # §2's example, the block of `'a dlist` with its two children
DL_REV, DL_LENGTH = DLIST["children"]
ERRORABLE_SYNTAX = {"form": "mixfix", "template": "_⇩⊥", "argument_priorities": [21], "priority": 21}


def definition(type_name="dlist", set="{xs :: 'a list. distinct xs}", english="Lists without repetition",
               type_parameters=({"name": "'a"},), **fields):
    """A construct of `typedef`: §2's example less its function names and children by default."""
    return {"kind": "typedef", "english": english, "type_parameters": list(type_parameters), "type_name": type_name,
            "set": set, **fields}


def lift(name, type, is_, english):
    """A construct of `lift_definition`, a child of the block (test_lift_definition.py builds its own from this module)."""
    return {"kind": "lift_definition", "english": english, "name": name, "type": type, "is": is_}


# §5's other examples, the sort of `poly`'s parameter written inside its set; one with the sort on the parameter; the
# subtype whose lifting is not set up (§6; `fm` needs a theory importing HOL-Library, `t2` stands in for it on the wire)
POLY = definition("poly", "{f :: nat ⇒ 'a::zero. ∀⇩∞ n. f n = 0}", "Polynomials, as their coefficient sequences",
                  rep_function_name="coeff")
ERRORABLE = definition("errorable", "UNIV :: 'a option set", "A type with an error value added", syntax=ERRORABLE_SYNTAX)
ZERO_ONLY = definition("zero_only", "{x :: 'a. x = 0}", "The zero alone", type_parameters=({"name": "'a", "sort": "zero"},))
FM = definition("fm", "UNIV :: (nat, nat) fmap set", "Finite maps from naturals to naturals, as a type of their own",
                type_parameters=())
FM_EMPTY = lift("fm_empty", "fm", "fmempty", "The empty map")
T2 = definition("t2", "UNIV :: nat set", "A copy of the naturals", type_parameters=(), rep_function_name="domain")
ROWS = ("english", "type_parameters", "type_name", "syntax", "set", "rep_function_name", "abs_function_name", "lifting")


# --- the schema and the descriptions (§2, §3) ------------------------------

def test_the_schema_and_the_descriptions_are_the_documents():
    [_, schema] = fenced_blocks(TD, "2.")
    text = re.sub(r'"\$defs": \{[^}]*\}.*', '"$defs": {}', "\n".join(schema))      # the spread and its comment
    expected = jsoncomment.JsonComment().loads(text)
    expected["$defs"] = {**common.TYPE_PARAMETER_DEFS, **common.TYPE_MIXFIX_DEFS}
    assert Typedef.construct_schema == expected
    assert list(typedef.KINDS) == ["typedef"]
    shared = [d for defs in (common.TYPE_PARAMETER_DEFS, common.TYPE_MIXFIX_DEFS) for d in descriptions(defs)]
    assert sorted(descriptions(Typedef.construct_schema)) == sorted(
        fenced_lines(TD, "3.") + shared + [common.LIFTING_CHILDREN_DESCRIPTION])      # `children`'s is COMMON §6's
    assert DLIST == definition(rep_function_name="list_of_dlist", abs_function_name="dlist_of_list",
                               children=[DL_REV, DL_LENGTH])
    assert DL_REV == lift("dl_rev", "'a dlist ⇒ 'a dlist", "rev", "Reversal of a list without repetition")
    [_, notice] = fenced_blocks(TD, "6.")
    assert [LIFTING_NOTICE] == notice
    assert issubclass(Typedef, Lifting_Closing) and issubclass(Typedef, common.Beginning_Proof_Obligation)


# --- `gen` (§2, §4) ----------------------------------------------------------

def test_gen_keeps_the_definition_normalised_as_isaterms_and_names_the_node():
    f, x = forest(definition(set=" {xs :: 'a\n list.  distinct xs} ", english="Lists\n without  repetition ",
                             type_parameters=({"name": " 'a ", "sort": ""},),
                             syntax={"form": "mixfix", "template": "_\n\tdl  ", "argument_priorities": [21], "priority": 21},
                             rep_function_name=" list_of_dlist\n", abs_function_name="dlist_of_list", children=[DL_REV]))
    (p,) = x.sub_nodes
    assert isinstance(p, Typedef) and p.kind == "typedef" and p.name == "dlist" and f.id_of(p) == "typedef_dlist"
    assert p.english == "Lists without repetition"
    assert p.type_parameters == (Type_Parameter(IsaTerm.from_agent("'a"), None),)
    assert p.syntax == Template(IsaTerm.from_agent("_  dl  "), (21,), 21)          # newlines and tabs alone, the spaces layout
    assert p.set == IsaTerm.from_agent("{xs :: 'a list. distinct xs}") and isinstance(p.set, IsaTerm)
    assert (p.rep_function_name, p.abs_function_name) == (IsaTerm.from_agent("list_of_dlist"), IsaTerm.from_agent("dlist_of_list"))
    assert p.lifting is None                                                          # recorded by an evaluation, none yet (§1)
    assert p.goal_state is not p.state and p.goal_state in p._states_inside()         # `Proof_Obligation`'s slot (COMMON §3)
    assert p._state_before_ending in p._states_inside() and p.sub_nodes[0].state is not p.state
    (c,) = p.sub_nodes
    assert isinstance(c, LiftDefinition) and c.name == "dl_rev" and f.id_of(c) == "lift_definition_dl_rev"     # §9
    (q,) = insert(f, x, 1, [definition("pos", "{n :: nat. n > 0}", "Positive naturals", type_parameters=())])
    assert (q.type_parameters, q.syntax, q.rep_function_name, q.abs_function_name) == ((), None, None, None)
    assert q.sub_nodes == []
    (r,) = insert(f, x, 2, [{"kind": "typedef", "english": "All", "type_name": "u", "set": "UNIV :: nat set"}])
    assert r.type_parameters == () and f.id_of(r) == "typedef_u"                    # `type_parameters` left out: none (§2)
    inv(f)


def test_gen_refuses_as_section_4_says():
    """§4's `gen` refuses only a type name outside §1's grammar
    (RENDER_BASELINES §2's line), before any field is judged; a missing
    `set`, a binder syntax, an `overloaded` field given, the recorded
    `lifting` authored and the integer bound, by the framework."""
    f, x = forest()
    [invalid] = [line for line in fenced_lines(BASELINES, "2.") if line.startswith("`my-list` is not a valid type name")]
    e = refused(f, x, [definition("my-list")], InvalidName)
    assert (e.name, e.grammar) == ("my-list", "type name") and str(e) == "At `constructs[0]`: " + invalid
    for name in ("1st", "dlist_", "a list", "x'y-", "", "α"):
        assert refused(f, x, [definition(name)], InvalidName).grammar == "type name"
    assert refused(f, x, [definition("my-list", type_parameters=({"name": "a"},), rep_function_name="rep_")], InvalidName).grammar == "type name"
    # the framework's integer bound (MODULE_STRUCTURE §4.4), RENDER_BASELINES §2's line, the forest unchanged
    [bound] = [line for line in fenced_lines(BASELINES, "2.") if line.endswith("must be a 64-bit integer.")]
    e = refused(f, x, [definition(syntax={"form": "infixr", "symbol": "+", "priority": 2**64})], InvalidField)
    assert str(e) == "At `constructs[0]`: " + bound.replace("types[0].constructors[1].syntax", "syntax") and e.field == "syntax.priority"
    for raw in ({"kind": "typedef", "english": "e", "type_name": "t"},                                     # no `set`
                {"kind": "typedef", "english": "e", "type_name": "t", "set": "UNIV",
                 "syntax": {"form": "binder", "symbol": "+", "priority": 1}},                            # no binder on a type
                {"kind": "typedef", "english": "e", "type_name": "t", "set": "UNIV", "overloaded": True},  # not a field (§2)
                {"kind": "typedef", "english": "e", "type_name": "t", "set": "UNIV", "lifting": True}):
        refused(f, x, [raw], RawASTError)
    assert x.sub_nodes == []
    inv(f)


def test_the_field_check_refuses_as_section_4_says():
    """§4's field check, each sentence told alone, no path before it: the
    type parameters by the shared check, each used in `set`, and the two
    function names by the shared check of the pair (COMMON §4's sentences,
    pinned by test_common.py) — a name beginning with `Rep_` or `Abs_` and
    a name equal to its default admitted, written into `morphisms` as
    given; §4's order under two faults."""
    f, x = forest()
    [invalid] = [line for line in fenced_lines(BASELINES, "2.") if line.startswith("`my-list` is not a valid type name")]
    [unused] = [line for line in fenced_lines(COMMON, "4.") if line.startswith("The field `type_parameters[1]` declares")]
    e = field_check(f, x, [definition(rep_function_name="rep_")])
    assert str(e) == IDENTIFIER and e.field == "rep_function_name"
    assert IDENTIFIER.endswith(": it " + invalid.split(": a type name ")[1])
    for name in ("1x", "x y", "", "rep-", "h\\<nat>"):
        assert field_check(f, x, [definition(rep_function_name=name)]).field == "rep_function_name"
    e = field_check(f, x, [definition(abs_function_name="abs_")])
    assert str(e) == IDENTIFIER.replace("rep_function_name", "abs_function_name")
    e = field_check(f, x, [definition(rep_function_name="list_of_dlist", abs_function_name="list_of_dlist")])
    assert str(e) == TWICE.replace("list_of_fset", "list_of_dlist") and e.field == "abs_function_name"
    for field, name in (("rep_function_name", "Rep_dlist"), ("rep_function_name", "Abs_x"), ("rep_function_name", " Abs_dlist"),
                        ("abs_function_name", "Abs_dlist"), ("abs_function_name", "Rep_y")):   # a given name like any other
        (p,) = insert(f, x, 0, [definition(**{field: name})])
        assert p._definition(M.print_name)[1] == "morphisms " + " ".join(
            name.strip() if g == field else d for g, d in (("rep_function_name", "Rep_dlist"), ("abs_function_name", "Abs_dlist")))
        p.check_fields()
        run(locked(f, edit.delete(p)))
    # the type parameters: COMMON §4's check, its sentences pinned by test_common.py; then each used in `set`
    e = field_check(f, x, [definition(type_parameters=({"name": "a"},))])
    assert (e.field, e.reason) == ("type_parameters[0].name", "must be a type variable, such as 'a")
    e = field_check(f, x, [definition(type_parameters=({"name": "'a"}, {"name": "'a"}))])
    assert (e.field, e.reason) == ("type_parameters[1].name", "repeats `'a`")
    e = field_check(f, x, [definition(type_parameters=({"name": "'a"}, {"name": "'b"}))])
    assert str(e) == unused and e.field == "type_parameters[1]"
    assert field_check(f, x, [definition(set="distinct")]).field == "type_parameters[0]"
    assert field_check(f, x, [definition()]) is None
    # §4's order under two faults: the parameters, their use, then the function names, Rep before Abs
    assert field_check(f, x, [definition(type_parameters=({"name": "a"},), rep_function_name="rep_")]).field == "type_parameters[0].name"
    assert field_check(f, x, [definition(set="distinct", rep_function_name="rep_")]).field == "type_parameters[0]"
    assert field_check(f, x, [definition(rep_function_name="rep_", abs_function_name="abs_")]).field == "rep_function_name"
    assert x.sub_nodes == []
    inv(f)


def test_a_sibling_bearing_the_node_s_id_component_is_the_framework_s_duplicate_name():
    f, x = forest(DLIST)
    e = refused(f, x, [definition(set="UNIV :: 'a list set")], DuplicateName)
    assert e.id_component == "typedef_dlist" and e.taken_by == "typedef_dlist"
    inv(f)


def test_an_amend_with_the_same_goal_structure_carries_the_proof_and_keeps_the_children():
    """§4: equal `type_parameters` and `set` carry the replaced job's
    outcome — a changed `type_name`, function name, `syntax` or `english`
    aside — and the children stay, the replacement's `lifting` none; a
    changed `set` or type parameter does not; the stored check is never
    carried (CONSTRUCT_INTERACTION §3.1)."""
    f, x = forest(DLIST)
    (p,) = x.sub_nodes
    rev, length = p.sub_nodes
    with_proof(p, M.READY_CLEAN, PROVED, PASSED)
    p.lifting = True
    (p2,) = run(locked(f, edit.amend(p, [definition("dl", english="Another wording", syntax=ERRORABLE_SYNTAX,
                                                    rep_function_name="rep", abs_function_name="abs")])))
    assert p2.job().outcome == PROVED and p2.check_outcome() is None and p2.name == "dl"
    assert p2.lifting is None                               # the recorded choice is the evaluation's to make again (COMMON §5)
    assert p2.sub_nodes == [rev, length] and rev.parent is p2                       # the children inherited
    assert p2.goal_structure() == p.goal_structure() == ([("'a", None)], "{xs :: 'a list. distinct xs}")
    (p3,) = run(locked(f, edit.amend(p2, [definition("dl", set="{xs :: 'a list. sorted xs}")])))
    assert p3.job().outcome is NOT_STARTED and p3.sub_nodes == [rev, length]      # the set changed
    p3.job().outcome = PROVED
    (p4,) = run(locked(f, edit.amend(p3, [definition("dl", set="{xs :: 'a list. sorted xs}",
                                                     type_parameters=({"name": "'a", "sort": "linorder"},))])))
    assert p4.job().outcome is NOT_STARTED                  # a parameter's sort changed
    inv(f)


# --- the store (§1, §2) --------------------------------------------------------

def test_the_definition_is_stored_and_a_missing_row_is_refused_at_start(tmp_path):
    path = tmp_path / "TAT.sqlite"
    f, x = forest(DLIST, ERRORABLE, ZERO_ONLY, store=Forest_Store(path, ts.stand_ins.log()))
    nodes = x.sub_nodes
    nodes[1].lifting, nodes[2].lifting = False, True               # as evaluations record it (§6); `dlist` None at birth
    with f.store.transaction():
        for n in nodes:
            f._store_node(n)

    def fields(n):
        return (n.name, n.english, n.type_parameters, n.syntax, n.set, n.rep_function_name, n.abs_function_name, n.lifting)
    before = [fields(n) for n in nodes]
    rows = f.store.fields(nodes[0].identity)
    assert set(ROWS) <= set(rows) and "name" not in rows                     # the rest the framework's: `children` among them
    assert rows["type_name"] == "dlist" and rows["set"] == "{xs :: 'a list. distinct xs}"
    assert rows["syntax"] is None and rows["rep_function_name"] == "list_of_dlist"      # a field left out: a None-valued row
    assert rows["abs_function_name"] == "dlist_of_list" and rows["lifting"] is None
    rows = f.store.fields(nodes[1].identity)
    assert rows["syntax"] == ERRORABLE_SYNTAX and rows["rep_function_name"] is None and rows["lifting"] is False
    rows = f.store.fields(nodes[2].identity)
    assert rows["type_parameters"] == [{"name": "'a", "sort": "zero"}] and rows["rep_function_name"] is None
    assert rows["lifting"] is True
    f.store.close()
    f2 = Forest_Under_Test(store=Forest_Store(path, ts.stand_ins.log()), kinds=KINDS)
    loaded = f2.sub_nodes[0].sub_nodes[0].sub_nodes
    assert [fields(n) for n in loaded] == before and all(isinstance(n, Typedef) for n in loaded)
    assert [c.name for c in loaded[0].sub_nodes] == ["dl_rev", "dl_length"]
    assert loaded[0].goal_state.name != nodes[0].goal_state.name and loaded[0].goal_state in loaded[0]._states_inside()
    f2.store.close()
    assert_a_missing_row_is_refused_at_start(path, nodes[0].identity, ROWS)      # every row (§1)


def test_a_definition_with_a_bad_field_is_stored_and_loads_as_it_was(tmp_path):
    """`from_store` reads the type parameters and a blank function name back
    as stored, judging nothing — the blank name the empty term, which the
    recall line writes `""` —, and the field check refuses each loaded node
    with COMMON §4's sentence."""
    [variable, _] = [b for b in fenced_blocks(COMMON, "4.") if b[0].startswith("The field")][0]
    nodes, loaded = reloaded(tmp_path / "TAT.sqlite", definition(type_parameters=({"name": "a"},)),
                             definition("blank", rep_function_name=" "))
    assert [(n.type_parameters, n.rep_function_name) for n in loaded] == [(n.type_parameters, n.rep_function_name) for n in nodes]
    assert loaded[1].rep_function_name == IsaTerm.from_agent("")
    assert loaded[1]._definition(M.print_name)[1] == 'morphisms "" Abs_blank'
    messages = []
    for n in loaded:
        with pytest.raises(InvalidField) as e:
            n.check_fields()
        messages.append(str(e.value))
    assert messages == [variable, IDENTIFIER]


# --- the message and the status (§6), the ending (§6), the block refusing children (§6), the mark (§7) ---

def fake_wire(monkeypatch, beginning):
    """The fake wire for a theory of the plugin's classes: `beginning`
    answers `TAT.Typedef.evaluate` from the message; a child's callback and
    the ending's answer clean; every call kept."""
    calls = []

    async def call(conversation, name, args):
        calls.append((name, args))
        if name == "TAT.Typedef.evaluate":
            return beginning(args[3])
        if name == "TAT.Lifting_Closing.close":
            return []
        return [[], [False, None]] if name == "TAT.LiftDefinition.evaluate" else [[], [None, None]]
    monkeypatch.setattr(isabelle_driver, "call", call)
    return calls


def test_eval_beginning_opr_sends_the_definition_and_records_what_the_steps_yielded(monkeypatch):
    """COMMON §3's `_eval_beginning_opr` with `Typedef`'s own: the message in
    §6's order — the definition, its goal part last, then the recorded
    `lifting`; the three slots on the wire — the beginning's input slot,
    `goal_state`, and the beginning's resulting slot, the first child's
    input or the slot before the ending with no child; of the pair the two
    steps yielded, `[[], [nil, b]]`, `b` recorded as `lifting`, the `Ready`
    carrying the notice exactly when `lifting` is false; Isabelle's
    messages an obstacle, the children `not_evaluated`, the ending `Ready`
    by the copy, the recorded `lifting` untouched — under a recorded value
    too, which the message carries (COMMON §5); the ending's `close` for
    the block whose setup was made, the copy for the other (COMMON §6); a
    syntax on the wire as `mixfix_text` writes it, in `ascii`."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        DLIST, POLY, definition("bad", "distinct :: 'a list ⇒ bool", "A predicate is no set",
                                rep_function_name="list_of_dlist", abs_function_name="dlist_of_list",
                                children=[lift("dl_bad", "'a bad ⇒ 'a bad", "rev", "A function on the bad subtype")])]})])
    # a fake theory: its header runs no call
    (x,) = s.sub_nodes
    p, q, r = x.sub_nodes

    def beginning(message):
        (type_name, *_), recorded = message
        if type_name == "bad":              # Isabelle's one message of two lines (typedef.ML, cat_error)
            return [['Not a set type: "\'a list \\<Rightarrow> bool"\nThe error(s) above occurred in typedef "bad"'], None]
        if recorded is True and type_name == "poly":    # `setup_lifting` refused under a recorded true: the failure (§6)
            return [['Duplicate fact declaration "X.poly.domain" vs. "X.domain"'], None]
        return [[], [None, type_name == "dlist"]]                   # `open_goal` yields nothing; poly: lifting refused
    calls = fake_wire(monkeypatch, beginning)
    r.lifting = True                                            # as an earlier successful evaluation recorded it (§6)
    run(x.evaluate_to(None, False))
    mine = [(name, args) for name, args in calls if name == "TAT.Typedef.evaluate"]
    assert [args[:3] for _, args in mine] == [
        (p.state.to_msgpack(), p.goal_state.to_msgpack(), p.sub_nodes[0].state.to_msgpack()),
        (q.state.to_msgpack(), q.goal_state.to_msgpack(), q._state_before_ending.to_msgpack()),
        (r.state.to_msgpack(), r.goal_state.to_msgpack(), r.sub_nodes[0].state.to_msgpack())]
    assert mine[0][1][3] == (
        ("dlist", None, "list_of_dlist", "dlist_of_list", [("'a", None)], "{xs :: 'a list. distinct xs}"), None)
    assert mine[1][1][3] == (("poly", None, "coeff", "Abs_poly", [("'a", None)],
                              "{f :: nat \\<Rightarrow> 'a::zero. \\<forall>\\<^sub>\\<infinity> n. f n = 0}"), None)
    assert mine[2][1][3][1] is True                                           # the recorded choice travels (COMMON §5)
    assert p.message()[0][4:] == p.goal_structure() and q.message()[0][4:] == q.goal_structure()
    assert isinstance(p.evaluation_status_beginning, M.Ready) and p.evaluation_status_beginning.messages == ()
    assert p.lifting is True and all(isinstance(c._status, M.Ready) for c in p.sub_nodes)
    assert isinstance(q.evaluation_status_beginning, M.Ready)
    assert [m.unicode for m in q.evaluation_status_beginning.messages] == [LIFTING_NOTICE] and q.lifting is False
    assert (p.message()[1], q.message()[1]) == (True, False)                  # recorded: what the next evaluation keeps to
    assert isinstance(r.evaluation_status_beginning, M.CannotEvaluate) and r.lifting is True      # untouched by a failure
    assert [m.unicode for m in r.evaluation_status_beginning.messages] == ['Not a set type: "\'a list ⇒ bool"\nThe error(s) above occurred in typedef "bad"']
    assert all(c._status is M.NOT_EVALUATED for c in r.sub_nodes)
    assert [n.evaluation_status_ending for n in (p, q, r)] == [M.READY_CLEAN] * 3
    # the ending (COMMON §6): `close` with the slot after the last child, the resulting slot and the name for `dlist`
    # alone; `poly`'s, with no setup made, the copy; `bad`'s the framework's copy
    endings = [args for name, args in calls if name == "TAT.Lifting_Closing.close"]
    assert endings == [(p._state_before_ending.to_msgpack(), p.resulting_state().to_msgpack(), "dlist")]
    assert p.operation_slots("ending") == (p._state_before_ending, p.resulting_state())
    assert ("copy", q._state_before_ending.name, q.resulting_state().name) in tm.TABLE.calls
    assert p.mark(M.BRIEFING, 0) == "unverified definition, proof not started" and r.mark(M.BRIEFING, 0) == "invalid definition"
    assert not p.is_finished() and not r.is_finished()                     # the proof is compulsory (COMMON §3)
    # under a recorded `lifting` true, `setup_lifting`'s refusal is the definition's failure, the record untouched (§6)
    q.lifting = True
    status = run(q._eval_beginning_opr())
    assert calls[-1][1][3] == (mine[1][1][3][0], True)
    assert isinstance(status, M.CannotEvaluate) and q.lifting is True
    assert [m.unicode for m in status.messages] == ['Duplicate fact declaration "X.poly.domain" vs. "X.domain"']
    t, z = insert(f, x, 3, [ERRORABLE, ZERO_ONLY])
    assert t.message() == (("errorable", '("_\\<^sub>\\<bottom>" [21] 21)', "Rep_errorable", "Abs_errorable", [("'a", None)],
                            "UNIV :: 'a option set"), None)
    assert z.message() == (("zero_only", None, "Rep_zero_only", "Abs_zero_only", [("'a", "zero")], "{x :: 'a. x = 0}"), None)
    assert t.mark(M.BRIEFING, 0) == "not evaluated, proof not started"


def test_the_recorded_lifting_reaches_the_store_and_the_mirror_catches_an_emit_off_an_instant_status(monkeypatch):
    """§1, §6; COMPILATION §3: a walk's store writes `lifting` as the
    evaluation recorded it, so a loaded forest emits the same file; an
    `emit_beginning` reading the instant status instead writes
    `setup_lifting` in memory and not once loaded, which
    `assert_store_mirrors` says at once."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [DLIST, POLY]})])
    (x,) = s.sub_nodes
    p, q = x.sub_nodes
    fake_wire(monkeypatch, lambda message: [[], [None, message[0][0] == "dlist"]])
    run(x.evaluate_to(None, False))
    rows = {n.name: f.store.fields(n.identity) for n in (p, q)}
    assert rows["dlist"]["lifting"] is True and rows["poly"]["lifting"] is False
    assert_store_mirrors(f, shape=ts.shape)                           # as shipped: mirrored
    emit_beginning = Typedef.emit_beginning

    def off_the_instant_status(self, indent, out):
        recorded, self.lifting = self.lifting, all(isinstance(st, M.Ready) for st in self.evaluation_statuses())
        try:
            return emit_beginning(self, indent, out)
        finally:
            self.lifting = recorded
    monkeypatch.setattr(Typedef, "emit_beginning", off_the_instant_status)
    with pytest.raises(AssertionError, match="Arith/X.thy: the loaded forest writes another text"):
        assert_store_mirrors(f, shape=ts.shape)


def test_a_block_whose_lifting_is_false_refuses_children(monkeypatch):
    """§6; COMMON §6: `is_lifting_setup_made()` true while `lifting` is none
    or true, false when false, `refuses_children()` true exactly then and
    `cannot_hold` the sentence; a child the block holds when its beginning
    records false is refused at its first own operation — `CannotEvaluate`
    with the head and COMMON §6's sentence, the parent's full id, its
    callback never called, the walk stopped there, the ending
    `not_evaluated` —; a node appended, inserted or moved into the block
    enters at the edit and is refused at evaluation likewise; a theory
    appended into the block is its own gate's (`BadTheoryNodeParent`);
    with the children gone the ending is `Ready` by the copy and no empty
    node's line stands under the block; an amend decides anew, and a child
    runs under a `lifting` recorded true."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        {**FM, "children": [FM_EMPTY]}, lift("fm_other", "fm", "fmempty", "Another map")]})])
    (x,) = s.sub_nodes
    p, other = x.sub_nodes
    (c,) = p.sub_nodes
    assert p.is_lifting_setup_made() is True and p.refuses_children() is False and p.cannot_hold(c, 1) is None   # none recorded
    calls = fake_wire(monkeypatch, lambda message: [[], [None, False]])
    run(x.evaluate_to(None, False))
    assert p.lifting is False and p.is_lifting_setup_made() is False and p.refuses_children() is True
    assert p.cannot_hold(c, 1) == LIFTING_REFUSAL
    full = f.full_id(p)
    expected = composed_refusal("lift_definition", full, LIFTING_REFUSAL)
    assert full == "session_Arith.fake_theory_X.typedef_fm"
    assert isinstance(c._status, M.CannotEvaluate) and [m.unicode for m in c._status.messages] == [expected]
    assert c._refusal() == expected
    assert not any(name == "TAT.LiftDefinition.evaluate" for name, _ in calls)     # the child's hook never ran
    assert p.evaluation_status_ending is M.NOT_EVALUATED and other._status is M.NOT_EVALUATED   # the walk stopped at `c`
    assert not any(name == "TAT.Lifting_Closing.close" for name, _ in calls)
    assert_store_mirrors(f, shape=ts.shape)           # the fake wire writes no slot: the mirror alone
    # at the edit: an append, an insert before the held child, a move in — each enters, and is refused at evaluation
    (more,) = insert(f, p, 1, [lift("fm_more", "fm", "fmempty", "More")])
    (first,) = insert(f, p, 0, [lift("fm_first", "fm", "fmempty", "First")])
    run(locked(f, edit.move(other, p, 3)))
    assert p.sub_nodes == [first, c, more, other] and x.sub_nodes == [p]
    with pytest.raises(BadTheoryNodeParent) as e:                                  # a theory: its own gate's
        insert(f, p, 0, [theory("Z")])
    assert e.value.parent_id == full and p.sub_nodes == [first, c, more, other]
    run(x.evaluate_to(None, True))
    for child in (first, more, other):
        assert isinstance(child._status, M.CannotEvaluate) and [m.unicode for m in child._status.messages] == [expected]
    assert not any(name == "TAT.LiftDefinition.evaluate" for name, _ in calls)
    assert_store_mirrors(f, shape=ts.shape)           # the fake wire writes no slot: the mirror alone
    # the children gone: the ending `Ready` by the copy, no `close`; no empty node's line under the block
    for child in (first, c, more):
        run(locked(f, edit.delete(child)))
    run(locked(f, edit.move(other, x, 1)))
    run(x.evaluate_to(None, False))
    assert p.evaluation_status_ending == M.READY_CLEAN and other._status == M.READY_CLEAN
    assert not any(name == "TAT.Lifting_Closing.close" for name, _ in calls)
    assert ("copy", p._state_before_ending.name, p.resulting_state().name) in tm.TABLE.calls
    me = stand_ins.agent(f.conversation)
    for rendering in (f.render(p, M.RECALL, me), f.render(f, M.BRIEFING, me), f.render(x, M.Relative_Focus(frozenset({p}), 0), me)):
        assert "typedef_fm" in rendering and "Empty so far" not in rendering
    assert_store_mirrors(f, shape=ts.shape)           # the fake wire writes no slot: the mirror alone
    # an amend decides anew: the replacement takes children, and under `lifting` true they run
    (p2,) = run(locked(f, edit.amend(p, [FM])))
    assert p2.lifting is None and p2.is_lifting_setup_made() is True and p2.refuses_children() is False
    (c2,) = insert(f, p2, 0, [FM_EMPTY])
    fake_wire(monkeypatch, lambda message: [[], [None, True]])
    run(x.evaluate_to(None, False))
    assert p2.lifting is True and c2._status == M.READY_CLEAN and p2.evaluation_status_ending == M.READY_CLEAN
    assert_store_mirrors(f, shape=ts.shape)           # the fake wire writes no slot: the mirror alone


def test_the_jobs_sentences_name_the_set():
    """§7: the construction's failure header and its failure notification
    both read the document's sentence, the node by its id; the agent's
    refutation reads the refutation sentence in both; the success
    notification is `Proof_Job`'s."""
    [failed, refuted, _, _] = fenced_blocks(TD, "7.")
    f, x = forest(DLIST)
    (p,) = x.sub_nodes
    job = p.job()
    assert failed == ["Failed to prove that `typedef_dlist`'s definitional set is non-empty:"]
    assert job.failure_header(Failed("gave up")) == failed[0]
    assert job.finished_notification(Failed("gave up")) == failed[0] + "\n  gave up"
    assert job.failure_header(Failed("gave up", "surrender")) == failed[0]
    # the agent's refutation: the refutation sentence in both
    assert refuted == ["`typedef_dlist`'s definitional set may be empty:"]
    assert job.failure_header(Failed("gave up", "refute")) == refuted[0]
    assert job.finished_notification(Failed("gave up", "refute")) == refuted[0] + "\n  gave up"
    assert job.finished_notification(PROVED) == "`typedef_dlist` is proven."


def test_the_mark_reads_one_of_eleven_ways_and_the_owing_line_stands_while_unverified():
    """§7's mark, state by state, reading the beginning's status — COMMON §3's
    table with the three words of a class that defines: `valid definition`
    alone once the proof stands, `unverified definition` with the proof's
    word before; the eleven, and no other, are the document's third block;
    the owing line, its fourth, exactly while the line reads `unverified
    definition`; the ending's status not on the line."""
    [_, _, block, state] = fenced_blocks(TD, "7.")
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
    with_proof(p, M.READY_CLEAN, NOT_STARTED)
    p.evaluation_status_ending = M.CannotEvaluate((IsaTerm.from_agent("Interrupt"),))       # not on the line (§7)
    assert p.mark(M.BRIEFING, 0) == "unverified definition, proof not started" and p.owing_line() == OWING_LINE


# --- what it prints (§8) -----------------------------------------------------

def test_print_fields_writes_the_definition_and_english_by_depth():
    f, x = forest(DLIST, ERRORABLE, POLY, definition("u", "UNIV", "All", type_parameters=()), ZERO_ONLY)
    p, q, t, u, z = x.sub_nodes
    [one, failed, notice, refused_child, bad] = fenced_blocks(TD, "8.")

    def fields(node, mode, depth):
        out = io.StringIO()
        node.print_fields(0, out, mode, depth)
        return out.getvalue().splitlines()
    assert [fields(p, M.RECALL, d) for d in range(4)] == [one, one[:1], one[:1], []]
    assert fields(p, M.OUT_FOCUS, 0) == [] and fields(p, M.Relative_Focus(frozenset({p}), 0), 0) == []
    p.lifting = True                                                     # not printed: not authored (§8)
    assert fields(p, M.RECALL, 0) == one
    assert fields(q, M.RECALL, 1) == ['\'a errorable ("_⇩⊥" [21] 21) = "UNIV :: \'a option set"']       # no `morphisms` clause
    # against no keyword, whatever the theory recorded: every name bare, the set and a sort quoted unless an identifier
    for keywords in (None, frozenset(), frozenset({"dlist", "UNIV", "zero", "coeff", "list_of_dlist", "u"})):
        x.keywords = keywords
        assert fields(t, M.RECALL, 1) == ['\'a poly = "{f :: nat ⇒ \'a::zero. ∀⇩∞ n. f n = 0}" morphisms coeff Abs_poly']
        assert fields(z, M.RECALL, 1) == ['(\'a :: zero) zero_only = "{x :: \'a. x = 0}"']
        assert fields(u, M.RECALL, 1) == ["u = UNIV"] and fields(p, M.RECALL, 1) == one[:1], keywords
    me = stand_ins.agent(f.conversation)
    for c in p.sub_nodes:
        with_proof(c, M.READY_CLEAN, PROVED, PASSED)
    with_proof(p, M.READY_CLEAN, PROVED, BAD)                            # §8's last example whole, with its mark and children
    assert f.render(p, M.RECALL, me).splitlines() == bad
    with_proof(p, M.NOT_EVALUATED, NOT_STARTED)                          # back to a node no walk reached
    for c in p.sub_nodes:
        with_proof(c, M.NOT_EVALUATED, NOT_STARTED)
    # §8's refused definition, in a forest of its own, the children not evaluated
    f2, _ = forest(definition(set="distinct :: 'a list ⇒ bool", rep_function_name="list_of_dlist",
                              abs_function_name="dlist_of_list", children=[DL_REV, DL_LENGTH]))
    (v,) = f2.sub_nodes[0].sub_nodes[0].sub_nodes
    v.evaluation_status_beginning = M.CannotEvaluate((IsaTerm.from_agent("\n".join(line.strip() for line in failed[4:6])),))
    assert fields(v, M.RECALL, 0) == [line.strip() for line in failed[1:3]]
    assert f2.render(v, M.RECALL, stand_ins.agent(f2.conversation)).splitlines() == failed
    # §8's two renderings of the subtype whose lifting was not set up, in a theory of their own: the block refusing
    # children with no empty node's line under it; the same block holding a child refused at its first own operation
    (s,) = f.sub_nodes
    (y,) = insert(f, s, 1, [theory("Y") | {"children": [FM]}])
    (w,) = y.sub_nodes
    with_proof(w, M.Ready((IsaTerm.from_agent(LIFTING_NOTICE),)), PROVED, PASSED)
    w.lifting = False
    assert f.render(w, M.RECALL, me).splitlines() == notice
    with_proof(w, M.NOT_EVALUATED, NOT_STARTED)                          # as stored, for the edit's store of the parent
    w.lifting = None                                                     # a child enters while none is recorded
    (child,) = insert(f, w, 0, [FM_EMPTY])
    with_proof(w, M.Ready((IsaTerm.from_agent(LIFTING_NOTICE),)), PROVED, PASSED)
    w.lifting = False
    refusal = child._refusal()
    assert refusal is not None
    child._status = M.CannotEvaluate((IsaTerm.from_agent(refusal),))
    assert f.render(w, M.RECALL, me).splitlines() == [
        line.replace("session_S.theory_T.typedef_fm", f.full_id(w)) for line in refused_child]
    with_proof(w, M.NOT_EVALUATED, NOT_STARTED)
    with_proof(child, M.NOT_EVALUATED, NOT_STARTED)
    w.lifting = None
    inv(f)


# --- emission (§5) ------------------------------------------------------------

def test_the_emitted_text_is_section_5_s():
    [one, two, three, four] = fenced_blocks(TD, "5.")
    f, x = forest(DLIST, POLY, ERRORABLE, FM)
    p, q, r, fm = x.sub_nodes
    x.keywords = frozenset()                                 # recorded by a header run, which emission presupposes

    def emitted(node) -> list[str]:
        """In `unicode` (§5); the file's `\\<name>` form is the compile's conversion (COMPILATION §2)."""
        out = io.StringIO()
        assert node.emit(1, out) == 1
        assert "\\<" not in out.getvalue()                                 # nothing written in `ascii`
        return out.getvalue().splitlines()

    def expected(*unicode_lines: str) -> list[str]:
        return ["  " + line if line else "" for line in unicode_lines]
    with pytest.raises(AssertionError):                             # `lifting` unrecorded: never written (`can_emit`; COMMON §5)
        emitted(q)
    q.lifting = False
    assert emitted(q) == expected(*two[:3], "  sorry")              # recorded false, no proof: no line, `sorry`, no ending
    for node in (p, q, r, fm):                                      # as §5's examples record it
        node.lifting = node is not fm
        with_proof(node, M.READY_CLEAN, PROVED, PASSED)
        for c in node.sub_nodes:
            c.with_code_dt = False                                  # no `(code_dt)`
            with_proof(c, M.READY_CLEAN, PROVED, PASSED)
    assert emitted(p) == expected(*one) and emitted(q) == expected(*two) and emitted(r) == expected(*three)
    assert emitted(fm) == expected(*four)
    for outcome, check in ((PROVED, BAD), (PROVED, None), (PROVED, RUNNING), (Failed("no"), None)):
        with_proof(p, M.READY_CLEAN, outcome, check)                                     # not proven: `sorry`
        assert emitted(p) == expected(*one[:3], "  sorry", *one[4:]), (outcome, check)
    q.lifting = False
    assert emitted(q) == expected(*two[:4])                                              # lifting not set up: no line, no ending
    with_proof(p, M.READY_CLEAN, PROVED, PASSED)
    q.lifting = True
    x.keywords = frozenset({"dlist", "list_of_dlist", "dlist_of_list", "zero", "UNIV", "type_definition_dlist"})   # keywords: quoted (§5)
    lines = emitted(p)
    assert lines[:5] == expected("text ‹Lists without repetition.›", 'typedef \'a "dlist" = "{xs :: \'a list. distinct xs}"',
                                 '  morphisms "list_of_dlist" "dlist_of_list"', "  by aoa", 'setup_lifting "type_definition_dlist"')
    assert lines[-2:] == expected("lifting_update dlist.lifting", "lifting_forget dlist.lifting")   # the bundle's name bare
    assert emitted(q)[1] == '  typedef \'a poly = "{f :: nat ⇒ \'a::zero. ∀⇩∞ n. f n = 0}"'
    assert emitted(r)[1:3] == expected('typedef \'a errorable ("_⇩⊥" [21] 21) = "UNIV :: \'a option set"', "  by aoa")
    z, u = insert(f, x, 4, [ZERO_ONLY, definition("u", "UNIV", "All", type_parameters=())])
    z.lifting = u.lifting = False                                                    # recorded, as emission presupposes
    assert emitted(z)[1:] == expected('typedef (\'a :: "zero") zero_only = "{x :: \'a. x = 0}"', "  sorry")   # a sort quoted
    assert emitted(u)[1:] == expected('typedef u = "UNIV"', "  sorry")                                       # a set quoted
    x.keywords = frozenset()
    assert emitted(z)[1] == "  typedef ('a :: zero) zero_only = \"{x :: 'a. x = 0}\""
    assert emitted(u)[1] == "  typedef u = UNIV"                                                    # a set that is an identifier
    # the Abs name alone given: Rep written as its default; an infix syntax; two parameters
    (t,) = insert(f, x, 6, [definition("sum", "UNIV :: ('a + 'b) set", "Sums!", type_parameters=({"name": "'a"}, {"name": "'b"}),
                                       syntax={"form": "infixr", "symbol": "⊕", "priority": 60}, abs_function_name="mk_sum")])
    t.lifting = False
    assert emitted(t) == expected("text ‹Sums!›", 'typedef (\'a, \'b) sum (infixr "⊕" 60) = "UNIV :: (\'a + \'b) set"',
                                  "  morphisms Rep_sum mk_sum", "  sorry")
    t.english = "Sums of n²"                                      # prose through `latex_of` (COMPILATION.md §3)
    assert emitted(t)[0] == "  text ‹Sums of ‹n²›.›"
    assert "emit_ending" not in vars(Typedef) and "_eval_ending_opr" not in vars(Typedef)      # `Lifting_Closing`'s


def test_the_two_spellings_are_kept_apart():
    """§2, §5, §8: a name, a parameter or a set whose `unicode` and `ascii`
    differ is stored, printed and emitted in `unicode` and sent to Isabelle
    in `ascii`."""
    f, x = forest(definition("t", "{x :: 'α. x ≠ ε}", "Greek", type_parameters=({"name": "'α", "sort": "linorder"},),
                             rep_function_name="ρ", abs_function_name="α⇩1"))
    (p,) = x.sub_nodes
    x.keywords = frozenset()
    assert p.message() == (("t", None, "\\<rho>", "\\<alpha>\\<^sub>1", [("'\\<alpha>", "linorder")],
                            "{x :: '\\<alpha>. x \\<noteq> \\<epsilon>}"), None)
    rows = {}
    p.to_store(type("Rows", (), {"put": lambda self, k, v: rows.__setitem__(k, v)})())
    assert rows["type_parameters"] == [{"name": "'α", "sort": "linorder"}] and rows["set"] == "{x :: 'α. x ≠ ε}"
    assert (rows["rep_function_name"], rows["abs_function_name"]) == ("ρ", "α⇩1")
    out = io.StringIO()
    p.print_fields(0, out, M.RECALL, 1)
    assert out.getvalue() == "('α :: linorder) t = \"{x :: 'α. x ≠ ε}\" morphisms ρ α⇩1\n"
    out = io.StringIO()
    p.lifting = False                                                   # recorded, as emission presupposes
    p.emit(0, out)
    assert out.getvalue().splitlines()[1:3] == ["typedef ('α :: linorder) t = \"{x :: 'α. x ≠ ε}\"", "  morphisms ρ α⇩1"]


# --- the id properties (§9), on test_quotient_type.py's precedent --------------

def test_section_9_s_id_properties():
    """§9: the component is omissible in both directions with drop priority
    1 — after `Section`'s, before `Theory`'s —, a child's id printed as
    short as the forest allows and accepted with or without it; the
    node's own component never dropped from its own id."""
    assert (Typedef.output_omissible, Typedef.input_omissible, Typedef.drop_priority) == (True, True, 1)
    f, x = forest(DLIST, lift("dl_rev", "'a dlist ⇒ 'a dlist", "rev", "Another reversal"))
    p, other = x.sub_nodes
    rev, length = p.sub_nodes
    assert f.id_of(p) == "typedef_dlist" and f.id_of(length) == "lift_definition_dl_length"
    for form in ("lift_definition_dl_length", "typedef_dlist.lift_definition_dl_length", "theory_X.lift_definition_dl_length",
                 "session_Arith.theory_X.typedef_dlist.lift_definition_dl_length"):
        assert f.resolve(form) is length
    assert f.resolve("typedef_dlist") is p and f.resolve("theory_X.typedef_dlist") is p
    # the other `dl_rev` directly under the theory: the block's component tells the inner one apart, and the other
    # prints its full id, each shorter form of it being a form of the inner's (test_ids.py's exact-match rule)
    assert f.id_of(rev) == "typedef_dlist.lift_definition_dl_rev"
    assert f.id_of(other) == "session_Arith.theory_X.lift_definition_dl_rev" and f.resolve(f.id_of(other)) is other
    run(locked(f, edit.delete(other)))
    # before `Theory`'s: a second `dl_rev` in another theory — `theory_X.…` kept, the block's component dropped first
    (s,) = f.sub_nodes
    (y,) = insert(f, s, 1, [theory("Y") | {"children": [DLIST]}])
    assert f.id_of(rev) == "theory_X.lift_definition_dl_rev" and f.id_of(y.sub_nodes[0].sub_nodes[0]) == "theory_Y.lift_definition_dl_rev"
    run(locked(f, edit.delete(y)))
    # after `Section`'s: test_ids.py's `Sec` inside the block holding a `dl_card`, another `dl_card` directly under the
    # theory — the section dropped, the block kept
    sec = test_ids.mk_block(test_ids.Sec, p, "B")
    (inner,) = run(locked(f, edit.insert(sec, 0, [lift("dl_card", "'a dlist ⇒ nat", "length", "The size")])))
    (outer,) = insert(f, x, 1, [lift("dl_card", "'a dlist ⇒ nat", "length", "The size")])
    assert f.id_of(inner) == "typedef_dlist.lift_definition_dl_card" and f.resolve("section_B.lift_definition_dl_card") is inner
    assert f.id_of(outer) == "session_Arith.theory_X.lift_definition_dl_card" and f.id_of(length) == "lift_definition_dl_length"


# --- the evaluation, in the plugin's run of the harness (§5, §6, §7, §8) --------

DL_LENGTH_REV = lemma("dl_length_rev", english="Reversal keeps the length",
                      for_any=({"name": "xs", "type": "'a dlist"},), premises=(), conclusion="dl_length (dl_rev xs) = dl_length xs")
DLIST_WITH_LEMMA = {**DLIST, "children": [DL_REV, DL_LENGTH, DL_LENGTH_REV]}


@pytest.mark.isabelle(deadline=600)
async def test_a_subtype_is_defined_lifting_set_up_and_the_block_closed(std_conversation, std_harness, tmp_path):
    """§6 through `TAT.Typedef.evaluate` and `TAT.Lifting_Closing.close`: a
    theory of §2's `dlist` — its two `lift_definition`s and a theorem by
    `transfer` inside the block —, §5's `poly` — its open dependency on
    `zero`, accepted under `typedef_overloaded`, which TAT_Std sets (COMMON
    §4) — and `errorable` with its type syntax, a `t2` whose Rep function is
    named `domain`, a fact `setup_lifting` declares under the type —
    `lifting` false, the notice on the `Ready`, the block refusing children
    —, and `zero_only`, each defined with its goal in `goal_state`, every
    ending `Ready`, then a theorem whose statement parses only through the
    morphisms, the syntax, the lifted functions and the relation
    `setup_lifting` defines; `recall` as §8 shows, `t2` without the empty
    node's line; a `lift_definition` appended into `t2`'s block accepted
    at the edit and refused at its first own operation, then deleted; the theory rendered as §5
    shows, under the recorded keywords, `t2`'s `typedef` alone, and read
    back whole by Isabelle; then the proof check for real (§7): a product
    on the inner theorem and one on `dlist`'s goal, both `PASSED` under
    `checks: "blocking"`.  Last, the callback alone: `[[], [nil, b]]` on
    the wire; and the recorded `lifting`'s rule (COMMON §5) through it, on
    slots beside the tree's: true runs `setup_lifting` once, a refusal the
    failure; false runs nothing."""
    forest = std_conversation.forest
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [ts.session("TAT_Suite", ts.theory("TAT_Std_A") | {"children": [
                DLIST_WITH_LEMMA, POLY, ERRORABLE, T2, ZERO_ONLY,
                lemma("uses_the_definitions", english="Every definition above parses",
                      for_any=({"name": "xs", "type": "'a list"}, {"name": "y", "type": "nat⇩⊥"},
                               {"name": "p", "type": "'b::zero poly"}),
                      premises=(),
                      conclusion="list_of_dlist (dlist_of_list xs) = xs ∧ y = y ∧ coeff p 0 = coeff p 0"
                                 " ∧ pcr_dlist = pcr_dlist ∧ domain (Abs_t2 0) = 0"
                                 " ∧ dl_length (dl_rev (dlist_of_list xs)) = dl_length (dlist_of_list xs)")]})]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 0 and text.count("Notice:") == 1, text
        (s,) = forest.sub_nodes
        (a,) = s.sub_nodes
        dlist, poly, errorable, t2, zero_only, uses = a.sub_nodes
        rev, length, inner = dlist.sub_nodes
        for node in (dlist, poly, errorable, t2, zero_only):
            assert isinstance(node.evaluation_status_beginning, M.Ready) and node.evaluation_status_ending == M.READY_CLEAN, node.name
            assert await node.goal_state.is_initialized() and await node.resulting_state().is_initialized()
            assert await node.operation_slots("beginning")[1].is_initialized()
        for node in (rev, length, inner, uses):
            assert node._status == M.READY_CLEAN and await node.goal_state.is_initialized(), node.name
        assert [n.lifting for n in (dlist, poly, errorable, t2, zero_only)] == [True, True, True, False, True]
        assert all(n.evaluation_status_beginning.messages == () for n in (dlist, poly, errorable, zero_only))
        assert [m.unicode for m in t2.evaluation_status_beginning.messages] == [LIFTING_NOTICE]
        assert t2.refuses_children() is True and dlist.refuses_children() is False
        [one, _, notice, _, _] = fenced_blocks(TD, "8.")
        recalled = await session.call_tool("recall", {"node_id": "typedef_t2"})                 # §8's notice, no empty node's line
        lines = text_of(recalled).splitlines()
        assert not recalled.isError and lines == [
            "- typedef_t2 (unverified definition, proof not started)", '  t2 = "UNIV :: nat set" morphisms domain Abs_t2',
            "  A copy of the naturals", *notice[3:5], "  " + OWING_LINE], lines
        recalled = await session.call_tool("recall", {"node_id": "theory_TAT_Std_A"})      # the nodes at depth 1: no `english`;
        shown = text_of(recalled).splitlines()                                              # at depth 2 no owing line (PRINT §2)
        expected = [                                                                # the theory's children under `declarations:`
            "- theory_TAT_Std_A (incomplete)", "  imports: Main", "  declarations:",   # (PRINT.md §2); a typedef writes no keyed line
            "    - typedef_dlist (unverified definition, proof not started)", "      " + one[0], "      " + OWING_LINE,
            "      - lift_definition_dl_rev (unverified definition, proof not started)",
            '        dl_rev :: "\'a dlist ⇒ \'a dlist" is rev',
            "      - lift_definition_dl_length (unverified definition, proof not started)",
            '        dl_length :: "\'a dlist ⇒ nat" is length',
            "      - lemma_dl_length_rev (valid statement, proof not started)",
            "        ⋀xs::'a dlist. dl_length (dl_rev xs) = dl_length xs",
            "    - typedef_poly (unverified definition, proof not started)",
            '      \'a poly = "{f :: nat ⇒ \'a::zero. ∀⇩∞ n. f n = 0}" morphisms coeff Abs_poly', "      " + OWING_LINE,
            "      " + M.EMPTY_NODE.format(id="typedef_poly"),                      # a block with no child, open to children
            "    - typedef_errorable (unverified definition, proof not started)",
            '      \'a errorable ("_⇩⊥" [21] 21) = "UNIV :: \'a option set"', "      " + OWING_LINE,
            "      " + M.EMPTY_NODE.format(id="typedef_errorable"),
            "    - typedef_t2 (unverified definition, proof not started)",          # refusing children: no header, no empty node's line
            '      t2 = "UNIV :: nat set" morphisms domain Abs_t2', "      Notice:", "        " + LIFTING_NOTICE, "      " + OWING_LINE,
            "    - typedef_zero_only (unverified definition, proof not started)"]
        assert not recalled.isError and shown[:len(expected)] == expected, shown
        # a node hung into `t2`'s block: accepted at the edit, refused at its first own operation under `t2`'s full id
        result = await session.call_tool("edit", {"action": "append", "target_id": "typedef_t2", "evaluate": True,
                                                  "constructs": [lift("t2_zero", "t2", "0", "Zero")]})
        expected = composed_refusal("lift_definition", "session_TAT_Suite.theory_TAT_Std_A.typedef_t2", LIFTING_REFUSAL)
        (zero,) = t2.sub_nodes
        assert not result.isError and expected in text_of(result), text_of(result)
        assert isinstance(zero._status, M.CannotEvaluate) and [m.unicode for m in zero._status.messages] == [expected]
        result = await session.call_tool("delete", {"node_id": "lift_definition_t2_zero"})
        assert not result.isError and t2.sub_nodes == [], text_of(result)
        result = await session.call_tool("evaluate_to", {"node_id": "theory_TAT_Std_A"})      # the obstacle gone: to `end` again
        assert not result.isError and t2.evaluation_status_ending == M.READY_CLEAN, text_of(result)
    rendered = C.render(forest)
    file = rendered.files[C.Path("TAT_Suite/TAT_Std_A.thy")]
    assert file.startswith('theory "TAT_Std_A"\n  imports "Main" "TAT_Std.TAT_Std"\nbegin\n') and file.endswith("end\n")
    [one, two, three, _] = fenced_blocks(TD, "5.")
    blocks = [[*one[:3], "  sorry", *one[4:12]], one[-2:], [*two[:3], "  sorry", *two[4:]], [*three[:2], "  sorry", *three[3:]],
              ["text ‹A copy of the naturals.›", 'typedef t2 = "UNIV :: nat set"', "  morphisms domain Abs_t2", "  sorry", "",
               "text ‹The zero alone.›"],
              ["text ‹The zero alone.›", 'typedef (\'a :: zero) zero_only = "{x :: \'a. x = 0}"', "  sorry",
               "setup_lifting type_definition_zero_only", "", "lifting_update zero_only.lifting", "lifting_forget zero_only.lifting"]]
    for block in blocks:
        assert "".join(ascii_of_unicode(line) + "\n" for line in block).replace(" by aoa\n", " sorry\n") in file, file
    assert "setup_lifting type_definition_t2" not in file and "t2.lifting" not in file
    await read_back(std_harness, file, tmp_path)
    async with std_conversation.client() as session:
        # the proof check for real (§7; COMMON §3): a product on the inner theorem and one on `dlist`'s goal, replayed
        inner.job().outcome = Succeeded({"text": "(transfer, simp)", "thread_cpu": 2000, "wall": 2000})
        dlist.job().outcome = Succeeded({"text": '(rule exI[of _ "[]"], simp)', "thread_cpu": 2000, "wall": 2000})
        await tm._invalidate(dlist)
        assert dlist.mark(M.BRIEFING, 0) == "not evaluated" and inner.mark(M.BRIEFING, 0) == "not evaluated"
        result = await session.call_tool("evaluate_to", {"node_id": "theory_TAT_Std_A", "checks": "blocking"})
        assert not result.isError, text_of(result)
        assert dlist.check_outcome() is PASSED and inner.check_outcome() is PASSED
        assert dlist.mark(M.BRIEFING, 0) == "valid definition" and dlist.owing_line() is None
        assert inner.mark(M.BRIEFING, 0) == "valid statement, proven"
        out = io.StringIO()
        dlist.emit_beginning(0, out)
        assert out.getvalue().splitlines()[3] == "  by aoa"
    # the callback alone: the pair the two steps yielded, `[[], [nil, b]]` (COMMON §3)
    for node, recorded in ((poly, True), (t2, False)):
        messages, what = await isabelle_driver.call(
            forest.conversation, "TAT.Typedef.evaluate",
            (node.state.to_msgpack(), node.goal_state.to_msgpack(), node.operation_slots("beginning")[1].to_msgpack(),
             node.message()))
        assert (messages, what) == ([], [None, recorded]), node.name
    # under a recorded `lifting`, on slots beside the tree's (COMMON §5): false, `setup_lifting` not run — `dlist`'s would be
    # accepted —; true on `t2`, whose `setup_lifting` Isabelle refuses, the definition's failure with Isabelle's message
    goal, resulting = (M.Isar_State_Slot.assign(forest.conversation) for _ in range(2))
    messages, what = await isabelle_driver.call(
        forest.conversation, "TAT.Typedef.evaluate",
        (dlist.state.to_msgpack(), goal.to_msgpack(), resulting.to_msgpack(), (dlist.message()[0], False)))
    assert (messages, what) == ([], [None, False])
    messages, what = await isabelle_driver.call(
        forest.conversation, "TAT.Typedef.evaluate",
        (t2.state.to_msgpack(), goal.to_msgpack(), resulting.to_msgpack(), (t2.message()[0], True)))
    assert what is None and len(messages) == 1 and "domain" in messages[0], messages


@pytest.mark.isabelle(deadline=600)
async def test_the_setup_is_closed_after_the_block_and_a_child_held_by_a_refusing_block_is_refused(std_conversation):
    """§2, §6, in theories of their own: a `lift_definition` on `dlist`
    after the block is refused with LIFT_DEFINITION.md §6's sentence, the
    setup closed; a `lifting_context` opening `dlist` after the block,
    holding one, is accepted; one inside the block opening `dlist` is
    silent, `opened` empty; `t2` submitted with a `lift_definition` — the
    beginning `Ready` with the notice, the child `CannotEvaluate` with
    RENDER_BASELINES §3's form line filled with COMMON §6's sentence, its
    callback never run, the ending
    `not_evaluated`; the child deleted, `evaluate_to` leaves the ending
    `Ready` by the copy and the theory is written with the `typedef`
    alone."""
    forest = std_conversation.forest
    ld = DOCS / "node_classes" / "LIFT_DEFINITION.md"
    [_, _, _, sentences, _] = fenced_blocks(ld, "6.")
    after = lift("dl_after", "'a dlist ⇒ 'a dlist", "rev", "After the block")
    again = {"kind": "lifting_context", "name": "dlist_again", "types": ["dlist"],
             "children": [lift("dl_again", "'a dlist ⇒ 'a dlist", "rev", "Opened again")]}
    inside = {"kind": "lifting_context", "name": "inside", "types": ["dlist"],
              "children": [lift("dl_inside", "'a dlist ⇒ 'a dlist", "rev", "Inside the block")]}
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [ts.session("TAT_Suite",
                                      ts.theory("TAT_Std_D") | {"children": [DLIST, after]},
                                      ts.theory("TAT_Std_E") | {"children": [DLIST, again]},
                                      ts.theory("TAT_Std_F") | {"children": [{**DLIST, "children": [DL_REV, inside]}]},
                                      ts.theory("TAT_Std_G") | {"children": [{**T2, "children": [lift("t2_zero", "t2", "0", "Zero")]}]})]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 2 and text.count("Notice:") == 1, text
        (s,) = forest.sub_nodes
        d, e, f_, g = s.sub_nodes
        (_, refused_after), (_, ctx), (block,), (t2,) = (t.sub_nodes for t in (d, e, f_, g))
        assert isinstance(refused_after._status, M.CannotEvaluate)
        assert [m.unicode for m in refused_after._status.messages] == [sentences[0]]           # "under the typedef that defines `dlist`"
        assert ctx.evaluation_status_beginning == M.READY_CLEAN and ctx.evaluation_status_ending == M.READY_CLEAN
        assert [t.unicode for t in ctx.opened] == ["dlist"] and ctx.sub_nodes[0]._status == M.READY_CLEAN
        (_, ctx_inside) = block.sub_nodes
        assert ctx_inside.opened == () and ctx_inside.sub_nodes[0]._status == M.READY_CLEAN       # open already: silent
        assert block.evaluation_status_ending == M.READY_CLEAN
        (child,) = t2.sub_nodes
        assert t2.lifting is False and [m.unicode for m in t2.evaluation_status_beginning.messages] == [LIFTING_NOTICE]
        assert isinstance(child._status, M.CannotEvaluate) and not await child.goal_state.is_initialized()
        assert [m.unicode for m in child._status.messages] == [
            composed_refusal("lift_definition", "session_TAT_Suite.theory_TAT_Std_G.typedef_t2", LIFTING_REFUSAL)]
        assert t2.evaluation_status_ending is M.NOT_EVALUATED
        recalled = await session.call_tool("recall", {"node_id": "typedef_t2"})
        assert not recalled.isError and "Empty so far" not in text_of(recalled) and "lift_definition_t2_zero (invalid definition)" in text_of(recalled)
        result = await session.call_tool("delete", {"node_id": "lift_definition_t2_zero"})
        assert not result.isError and t2.sub_nodes == [], text_of(result)
        result = await session.call_tool("evaluate_to", {"node_id": "theory_TAT_Std_G"})
        assert not result.isError, text_of(result)
        assert t2.evaluation_status_ending == M.READY_CLEAN and await t2.resulting_state().is_initialized()
    rendered = C.render(forest)
    assert not any(C.Path(f"TAT_Suite/TAT_Std_{t}.thy") in rendered.files for t in "D")     # an obstacle: not written
    g_file = rendered.files[C.Path("TAT_Suite/TAT_Std_G.thy")]
    assert 'typedef t2 = "UNIV :: nat set"\n  morphisms domain Abs_t2\n  sorry\nend\n' == g_file[g_file.index("typedef t2"):]
    e_file = rendered.files[C.Path("TAT_Suite/TAT_Std_E.thy")]
    assert "lifting_forget dlist.lifting\n\ncontext includes dlist.lifting begin" in e_file, e_file


@pytest.mark.isabelle(deadline=300)
async def test_a_refused_definition_and_a_refused_admission_are_obstacles(std_conversation):
    """§6, §8: a `dlist` whose set is a predicate where a set is expected, is
    an obstacle with Isabelle's messages, `goal_state` empty, its children
    `not_evaluated` and its ending `Ready`, shown under `recall` as §8's
    example; a `g` whose Rep name `g_inverse` is the fact the admission
    notes under it is an obstacle too, nothing recorded, `goal_state`
    empty; neither theory is written."""
    forest = std_conversation.forest
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [ts.session("TAT_Suite",
                                      ts.theory("TAT_Std_B") | {"children": [
                                          definition(set="distinct :: 'a list ⇒ bool", rep_function_name="list_of_dlist",
                                                     abs_function_name="dlist_of_list", children=[DL_REV, DL_LENGTH])]},
                                      ts.theory("TAT_Std_C") | {"children": [
                                          definition("g", "UNIV :: nat set", "A copy whose Rep name is a fact the admission notes",
                                                     type_parameters=(), rep_function_name="g_inverse", abs_function_name="g")]})]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 2, text
        (s,) = forest.sub_nodes
        b, c = s.sub_nodes
        (bad,) = b.sub_nodes
        (g,) = c.sub_nodes
        [_, failed, _, _, _] = fenced_blocks(TD, "8.")
        assert isinstance(bad.evaluation_status_beginning, M.CannotEvaluate) and not await bad.goal_state.is_initialized()
        assert [m.unicode for m in bad.evaluation_status_beginning.messages] == ["\n".join(line.strip() for line in failed[4:6])]
        assert bad.lifting is None                                                            # nothing recorded (§1)
        assert all(ch._status is M.NOT_EVALUATED for ch in bad.sub_nodes) and bad.evaluation_status_ending == M.READY_CLEAN
        recalled = await session.call_tool("recall", {"node_id": "typedef_dlist"})                      # §8's example whole
        assert not recalled.isError and text_of(recalled).splitlines() == failed, text_of(recalled)
        assert isinstance(g.evaluation_status_beginning, M.CannotEvaluate) and g.lifting is None
        assert g.evaluation_status_beginning.messages[0].unicode.startswith("Duplicate fact declaration")
        assert not await g.goal_state.is_initialized()      # emptied; after the walk the resulting slot holds the framework's
                                                            # copy of the input, so it says nothing of the callback
    rendered = C.render(forest)
    assert not any(C.Path(f"TAT_Suite/TAT_Std_{t}.thy") in rendered.files for t in "BC")   # an obstacle: not written
