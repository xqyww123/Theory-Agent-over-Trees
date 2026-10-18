"""`QuotientType` (node_classes/QUOTIENT_TYPE.md): with no Isabelle, the
schema and the descriptions (§2, §3), `gen`'s checks and refusals (§4),
the definition as the node holds, stores and prints it (§1, §2, §8), the
node's name and the framework's `DuplicateName` on it, the beginning's
message, status and recorded field and the ending's call (§6), the carry
on an amend (§4), the mark and the owing line (§7), the emitted text
(§5), the id properties (§9); through the std harness, the evaluation
(§6), `recall` (§8), the rendered file (§5) and the proof check (§7).
Run: python -m pytest test/test_quotient_type.py
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
from baselines import DOCS, fenced_blocks, fenced_lines
from harness import text_of
from invariants import assert_store_mirrors
from Isabelle_RPC_Host.unicode import IsaTerm, ascii_of_unicode
from isabelle_theory_agent import compile as C, edit, isabelle_driver, model as M
from isabelle_theory_agent.exceptions import DuplicateName, InvalidField, InvalidName, RawASTError
from isabelle_theory_agent.jobs import NOT_STARTED, PASSED, RUNNING, Succeeded
from isabelle_theory_agent.std import common, quotient_type
from isabelle_theory_agent.std.common import Lifting_Closing, NotInsideTheory, Template, Type_Parameter
from isabelle_theory_agent.std.lift_definition import LiftDefinition, OWING_LINE as LD_OWING_LINE
from isabelle_theory_agent.std.quotient_type import OWING_LINE, OWING_LINE_PARTIAL, QuotientType
from isabelle_theory_agent.store import Forest_Store
from ml_process import ml_process, ml_string
from std_forest import KINDS, assert_a_missing_row_is_refused_at_start, forest, insert, inv, refused
from test_descriptions import descriptions
from test_lift_definition import definition as lift
from test_model import locked, run
from test_session_theory import Forest_Under_Test, session, theory
from test_theorem import BAD, PROVED, assert_the_eleven_ways, lemma, with_proof

table = ts.table                    # the fake state slot table and the fake wire, per test
QT = DOCS / "node_classes" / "QUOTIENT_TYPE.md"
COMMON = DOCS / "node_classes" / "COMMON.md"

# §2's three constructs: `fset` with its two children; the second under the name `zint`, HOL's `int` standing in the
# Isabelle-backed theory; the third given §5's syntax
FSET, INT, _FRACT = (json.loads("\n".join(block)) for block in fenced_blocks(QT, "2.")[:3])
ZINT = {**INT, "type_name": "zint"}
FRACT_SYNTAX = {"form": "mixfix", "template": "_ ratio", "argument_priorities": [21], "priority": 21}
FRACT = {**_FRACT, "syntax": FRACT_SYNTAX}
FEMPTY, FMEMBER = FSET["children"]


def definition(type_name="fset", representation_type="'a list", equiv_relation="λxs ys. set xs = set ys",
               english="Finite sets, as lists up to order and repetition", type_parameters=("'a",), **fields):
    """A construct of `quotient_type`: §2's example less its function names
    and children by default; `type_parameters` None leaves the field out."""
    return {"kind": "quotient_type", "english": english,
            **({"type_parameters": list(type_parameters)} if type_parameters is not None else {}), "type_name": type_name,
            "representation_type": representation_type, "equiv_relation": equiv_relation, **fields}


ROWS = ("english", "type_parameters", "type_name", "syntax", "representation_type", "equiv_relation", "partial",
        "rep_function_name", "abs_function_name", "overloaded")                                       # §1's rows


# --- the schema and the descriptions (§2, §3) ------------------------------

def test_the_schema_and_the_descriptions_are_the_documents():
    [_, _, _, schema] = fenced_blocks(QT, "2.")
    text = re.sub(r'"\$defs": \{[^}]*\}.*', '"$defs": {}', "\n".join(schema))      # the spread and its comment
    expected = jsoncomment.JsonComment().loads(text)
    expected["$defs"] = {**common.TYPE_MIXFIX_DEFS}
    assert QuotientType.construct_schema == expected
    assert list(quotient_type.KINDS) == ["quotient_type"]
    assert sorted(descriptions(QuotientType.construct_schema)) == sorted(
        fenced_lines(QT, "3.") + descriptions(common.TYPE_MIXFIX_DEFS))
    assert FSET == definition(rep_function_name="list_of_fset", abs_function_name="fset_of_list", children=[FEMPTY, FMEMBER])
    assert INT == definition("int", "nat × nat", "λ(a, b) (c, d). a + d = c + b",
                             "The integers, as pairs of naturals up to a common summand", type_parameters=None)
    assert _FRACT == definition("fract", "'a :: idom × 'a", "λ(a, b) (c, d). b ≠ 0 ∧ d ≠ 0 ∧ a * d = c * b",
                                "Rational numbers, as fractions with a non-zero denominator", partial=True)
    assert issubclass(QuotientType, Lifting_Closing) and issubclass(QuotientType, common.Beginning_Proof_Obligation)


# --- `gen` (§2, §4) ----------------------------------------------------------

def test_gen_keeps_the_definition_normalised_as_isaterms_and_names_the_node():
    f, x = forest(definition(representation_type=" 'a\n list ", equiv_relation="λxs ys.\n  set xs  = set ys",
                             english="Finite sets,\n as lists ", type_parameters=(" 'a ",),
                             syntax={"form": "mixfix", "template": "_\n\tfs  ", "argument_priorities": [21], "priority": 21},
                             rep_function_name=" list_of_fset\n", abs_function_name="fset_of_list", children=[FEMPTY]))
    (p,) = x.sub_nodes
    assert isinstance(p, QuotientType) and p.kind == "quotient_type" and p.name == "fset" and f.id_of(p) == "quotient_type_fset"
    assert p.english == "Finite sets, as lists"
    assert p.type_parameters == (Type_Parameter(IsaTerm.from_agent("'a"), None),)                    # sortless (§1)
    assert p.syntax == Template(IsaTerm.from_agent("_  fs  "), (21,), 21)          # newlines and tabs alone, the spaces layout
    assert p.representation_type == IsaTerm.from_agent("'a list") and isinstance(p.representation_type, IsaTerm)
    assert p.equiv_relation == IsaTerm.from_agent("λxs ys. set xs = set ys") and isinstance(p.equiv_relation, IsaTerm)
    assert p.partial is False                                                                       # left out: false (§2)
    assert (p.rep_function_name, p.abs_function_name) == (IsaTerm.from_agent("list_of_fset"), IsaTerm.from_agent("fset_of_list"))
    assert p.overloaded is None                                                       # recorded by an evaluation, none yet (§1)
    assert p.goal_state is not p.state and p.goal_state in p._states_inside()         # `Proof_Obligation`'s slot (COMMON §3)
    assert p._state_before_ending in p._states_inside() and p.sub_nodes[0].state is not p.state
    (c,) = p.sub_nodes
    assert isinstance(c, LiftDefinition) and c.name == "fempty" and f.id_of(c) == "lift_definition_fempty"     # §9
    (q,) = insert(f, x, 1, [ZINT])
    assert (q.type_parameters, q.syntax, q.rep_function_name, q.abs_function_name) == ((), None, None, None)
    assert q.partial is False and q.sub_nodes == [] and f.id_of(q) == "quotient_type_zint"
    (r,) = insert(f, x, 2, [FRACT])
    assert r.partial is True and r.representation_type == IsaTerm.from_agent("'a :: idom × 'a")
    (t,) = insert(f, x, 3, [definition("pair", "'a × 'b", "(=)", "Pairs", type_parameters=("'b", "'a"))])
    assert [p.name.unicode for p in t.type_parameters] == ["'b", "'a"]                 # the authored order kept
    inv(f)


def test_gen_refuses_as_section_4_says():
    """§4's refusals in its order: the parent first (COMMON §1's
    `NotInsideTheory`, pinned for every class by test_common.py); a type
    name outside §1's grammar (RENDER_BASELINES §2's line); the three
    sentences of §4's block under `type_parameters[i]`; the two function
    names by the shared check of the pair (COMMON §4's sentences) — two
    equal given names refused, a name equal to its default accepted and
    written into `morphisms` as given, `abs_fset` as the Rep name with the
    Abs name left out accepted (Isabelle's at the admission); a missing
    relation, a `partial` that is no boolean, a binder syntax or the
    recorded field authored, by the framework."""
    f, x = forest()
    (s,) = f.sub_nodes
    e = refused(f, s, [definition("my-set")], NotInsideTheory)
    assert (e.kind, e.parent_id, e.raw_ast_path) == ("quotient_type", "session_Arith", "constructs[0]")
    [invalid] = [line for line in fenced_lines(DOCS / "RENDER_BASELINES.md", "2.")
                 if line.startswith("`my-list` is not a valid type name")]
    e = refused(f, x, [definition("my-list")], InvalidName)
    assert (e.name, e.grammar) == ("my-list", "type name") and str(e) == "At `constructs[0]`: " + invalid
    for name in ("1st", "fset_", "a set", "x'y-", "", "α"):
        assert refused(f, x, [definition(name)], InvalidName).grammar == "type name"
    # the type parameters: the three sentences of §4's block, COMMON §4's check under this class's path
    [variable, twice, unused] = fenced_blocks(QT, "4.")[0]
    e = refused(f, x, [definition(type_parameters=("a",))], InvalidField)
    assert str(e) == "At `constructs[0]`: " + variable and e.field == "type_parameters[0]"
    e = refused(f, x, [definition(type_parameters=("'a", "'a"))], InvalidField)
    assert str(e) == "At `constructs[0]`: " + twice and e.field == "type_parameters[1]"
    e = refused(f, x, [definition(type_parameters=("'a", "'b"))], InvalidField)
    assert str(e) == "At `constructs[0]`: " + unused and e.field == "type_parameters[1]"
    assert refused(f, x, [definition(representation_type="'ab list")], InvalidField).field == "type_parameters[0]"
    assert refused(f, x, [definition(representation_type="nat list", equiv_relation="λxs ys. set xs = set ys ∧ (x :: 'a) = x")],
                   InvalidField).field == "type_parameters[0]"             # the relation is not scanned: `representation_type` is
    # the function names: COMMON §4's two sentences, pinned by test_common.py
    [identifier, bound_twice] = [b for b in fenced_blocks(COMMON, "4.") if b[0].startswith("The field `rep_function_name`")][0]
    e = refused(f, x, [definition(rep_function_name="rep_")], InvalidField)
    assert str(e) == "At `constructs[0]`: " + identifier and e.field == "rep_function_name"
    for name in ("1x", "x y", "", "rep-", "h\\<nat>"):
        assert refused(f, x, [definition(rep_function_name=name)], InvalidField).field == "rep_function_name"
    e = refused(f, x, [definition(abs_function_name="abs_")], InvalidField)
    assert str(e) == "At `constructs[0]`: " + identifier.replace("rep_function_name", "abs_function_name")
    e = refused(f, x, [definition(rep_function_name="list_of_fset", abs_function_name="list_of_fset")], InvalidField)
    assert str(e) == "At `constructs[0]`: " + bound_twice and e.field == "abs_function_name"
    for fields, morphisms in (({"rep_function_name": "rep_fset"}, "morphisms rep_fset abs_fset"),
                              ({"abs_function_name": " abs_fset "}, "morphisms rep_fset abs_fset"),
                              ({"rep_function_name": "abs_fset"}, "morphisms abs_fset abs_fset"),      # Isabelle's refusal (§6)
                              ({"rep_function_name": "Rep_fset", "abs_function_name": "Abs_fset"}, "morphisms Rep_fset Abs_fset")):
        (p,) = insert(f, x, 0, [definition(**fields)])
        assert p._definition(())[1] == morphisms
        run(locked(f, edit.delete(p)))
    # §4's order under two faults: the type name, the parameters, their use, then the function names, Rep before Abs
    assert refused(f, x, [definition("my-list", type_parameters=("a",), rep_function_name="rep_")], InvalidName).grammar == "type name"
    assert refused(f, x, [definition(type_parameters=("a",), rep_function_name="rep_")], InvalidField).field == "type_parameters[0]"
    assert refused(f, x, [definition(type_parameters=("'a", "'b"), rep_function_name="rep_")], InvalidField).field == "type_parameters[1]"
    assert refused(f, x, [definition(rep_function_name="rep_", abs_function_name="abs_")], InvalidField).field == "rep_function_name"
    # the framework's integer bound (MODULE_STRUCTURE §4.4), RENDER_BASELINES §2's line, the forest unchanged
    [bound] = [line for line in fenced_lines(DOCS / "RENDER_BASELINES.md", "2.") if line.endswith("must be a 64-bit integer.")]
    e = refused(f, x, [definition(syntax={"form": "infixr", "symbol": "+", "priority": 2**64})], InvalidField)
    assert str(e) == "At `constructs[0]`: " + bound.replace("types[0].constructors[1].syntax", "syntax") and e.field == "syntax.priority"
    for raw in ({"kind": "quotient_type", "english": "e", "type_name": "t", "representation_type": "nat"},    # no relation
                definition(partial="yes"),                                                                   # no boolean
                definition(syntax={"form": "binder", "symbol": "+", "priority": 1}),                        # no binder on a type
                definition(overloaded=True),                                                 # recorded, not authored (§2)
                definition(type_parameters=({"name": "'a"},))):                               # a bare variable, no object
        refused(f, x, [raw], RawASTError)
    assert x.sub_nodes == []
    inv(f)


def test_a_sibling_bearing_the_node_s_id_component_is_the_framework_s_duplicate_name():
    f, x = forest(FSET)
    e = refused(f, x, [definition(representation_type="'a list")], DuplicateName)
    assert e.id_component == "quotient_type_fset" and e.taken_by == "quotient_type_fset"
    inv(f)


def test_an_amend_with_the_same_goal_structure_carries_the_proof_and_keeps_the_children():
    """§4: equal `representation_type`, `partial` and `equiv_relation` carry
    the replaced job's outcome — a changed `type_name`, the type parameters
    reordered, a changed `syntax`, function name or `english` aside — and
    the children stay; a changed `partial`, relation or representation
    type does not; the stored check is never carried (CONSTRUCT_INTERACTION
    §3.1)."""
    f, x = forest(definition("pair", "'a × 'b", "λp q. fst p = fst q", "Pairs up to their first component",
                             type_parameters=("'a", "'b"), children=[lift("first", "('a × 'b) pair ⇒ 'a", "fst", "The first")]))
    (p,) = x.sub_nodes
    (c,) = p.sub_nodes
    with_proof(p, M.READY_CLEAN, PROVED, PASSED)
    p.overloaded = False
    (p2,) = run(locked(f, edit.amend(p, [definition("pr", "'a × 'b", "λp q. fst p = fst q", "Another wording",
                                                    type_parameters=("'b", "'a"), syntax=FRACT_SYNTAX,
                                                    rep_function_name="rep", abs_function_name="abs")], KINDS)))
    assert p2.job().outcome == PROVED and p2.check_outcome() is None and p2.name == "pr"
    assert p2.sub_nodes == [c] and c.parent is p2                                   # the children inherited
    assert p2.overloaded is None                            # the recorded choice is the evaluation's to make again (COMMON §5)
    assert p2.goal_structure() == p.goal_structure() == ("'a \\<times> 'b", False, "\\<lambda>p q. fst p = fst q")
    (p3,) = run(locked(f, edit.amend(p2, [definition("pr", "'a × 'b", "λp q. fst p = fst q", type_parameters=("'b", "'a"),
                                                     partial=True)], KINDS)))
    assert p3.job().outcome is NOT_STARTED and p3.sub_nodes == [c]                  # `partial` changed
    p3.job().outcome = PROVED
    (p4,) = run(locked(f, edit.amend(p3, [definition("pr", "'a × 'b", "λp q. snd p = snd q", type_parameters=("'b", "'a"),
                                                     partial=True)], KINDS)))
    assert p4.job().outcome is NOT_STARTED                                          # the relation changed
    p4.job().outcome = PROVED
    (p5,) = run(locked(f, edit.amend(p4, [definition("pr", "'b × 'a", "λp q. snd p = snd q", type_parameters=("'b", "'a"),
                                                     partial=True)], KINDS)))
    assert p5.job().outcome is NOT_STARTED                                          # the representation type changed
    inv(f)


# --- the store (§1, §2) --------------------------------------------------------

def test_the_definition_is_stored_and_a_missing_row_is_refused_at_start(tmp_path):
    path = tmp_path / "TAT.sqlite"
    f, x = forest(FSET, ZINT, FRACT, store=Forest_Store(path, ts.stand_ins.log()))
    nodes = x.sub_nodes
    nodes[1].overloaded, nodes[2].overloaded = False, True       # as evaluations record them (§6); `fset` unrecorded
    with f.store.transaction():
        for n in nodes:
            f._store_node(n)

    def fields(n):
        return (n.name, n.english, n.type_parameters, n.syntax, n.representation_type, n.equiv_relation, n.partial,
                n.rep_function_name, n.abs_function_name, n.overloaded)
    before = [fields(n) for n in nodes]
    rows = f.store.fields(nodes[0].identity)
    assert set(ROWS) <= set(rows) and "name" not in rows                     # the rest the framework's
    assert rows["type_name"] == "fset" and rows["type_parameters"] == ["'a"] and rows["representation_type"] == "'a list"
    assert rows["equiv_relation"] == "λxs ys. set xs = set ys" and rows["partial"] is False
    assert rows["syntax"] is None and rows["overloaded"] is None            # a field left out, a value not yet recorded: None
    assert (rows["rep_function_name"], rows["abs_function_name"]) == ("list_of_fset", "fset_of_list")
    rows = f.store.fields(nodes[1].identity)
    assert rows["type_parameters"] == [] and rows["rep_function_name"] is None and rows["overloaded"] is False
    rows = f.store.fields(nodes[2].identity)
    assert rows["syntax"] == FRACT_SYNTAX and rows["partial"] is True and rows["overloaded"] is True
    f.store.close()
    f2 = Forest_Under_Test(store=Forest_Store(path, ts.stand_ins.log()), kinds=KINDS)
    loaded = f2.sub_nodes[0].sub_nodes[0].sub_nodes
    assert [fields(n) for n in loaded] == before and all(isinstance(n, QuotientType) for n in loaded)
    assert [c.name for c in loaded[0].sub_nodes] == ["fempty", "fmember"]
    assert loaded[0].goal_state.name != nodes[0].goal_state.name and loaded[0].goal_state in loaded[0]._states_inside()
    f2.store.close()
    assert_a_missing_row_is_refused_at_start(path, nodes[0].identity, ROWS)      # every row, the recorded one too (§1)


# --- the message, the status and the recorded field (§6), the ending (§6), the mark (§7)

def fake_wire(monkeypatch, beginning):
    """The fake wire for a theory of the plugin's classes: `beginning`
    answers `TAT.QuotientType.evaluate` from the message; a child's
    callback and the ending's answer clean; every call kept."""
    calls = []

    async def call(conversation, name, args):
        calls.append((name, args))
        if name == "TAT.QuotientType.evaluate":
            return beginning(args[3])
        if name == "TAT.Lifting_Closing.close":
            return []
        return [[], [False, None]] if name == "TAT.LiftDefinition.evaluate" else [[], [None, None]]
    monkeypatch.setattr(isabelle_driver, "call", call)
    return calls


def test_eval_beginning_opr_sends_the_definition_and_records_what_the_steps_yielded(monkeypatch):
    """COMMON §3's `_eval_beginning_opr` with `QuotientType`'s own: the
    message in §6's order — the authored fields, the recorded `overloaded`,
    then the goal part whole —; the three slots on the wire — the
    beginning's input slot, `goal_state`, and the beginning's resulting
    slot, the first child's input or the slot before the ending with no
    child; what `open_goal` yielded recorded as `overloaded`, true and
    false alike; Isabelle's messages an obstacle, the recorded field
    untouched, the children `not_evaluated`, the ending `Ready` by the
    copy; a recorded value travels (COMMON §5); a syntax on the wire as
    `mixfix_text` writes it, in `ascii`."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        FSET, FRACT, definition("bad", equiv_relation="λxs ys. set xs = set ys ∧ P xs", children=[FEMPTY])]})])
    (x,) = s.sub_nodes
    p, q, r = x.sub_nodes

    def beginning(message):
        (type_name, *_), recorded, _ = message
        if type_name == "bad":              # §8's first example: Isabelle's one message
            return [['"bad": illegal variable(s) in the relation: "P"'], None]
        if recorded is False and type_name == "fract":     # refused under a recorded false: the failure (§6)
            return [['Type definition with open dependencies, use "(overloaded)"'], None]
        return [[], [type_name == "fract", None]]                      # fract: `(overloaded)` needed
    calls = fake_wire(monkeypatch, beginning)
    r.overloaded = True                                         # as an earlier successful evaluation recorded it (§6)
    run(x.evaluate_to(None, False))
    mine = [(name, args) for name, args in calls if name == "TAT.QuotientType.evaluate"]
    assert [args[:3] for _, args in mine] == [
        (p.state.to_msgpack(), p.goal_state.to_msgpack(), p.sub_nodes[0].state.to_msgpack()),
        (q.state.to_msgpack(), q.goal_state.to_msgpack(), q._state_before_ending.to_msgpack()),
        (r.state.to_msgpack(), r.goal_state.to_msgpack(), r.sub_nodes[0].state.to_msgpack())]
    assert mine[0][1][3] == (("fset", ["'a"], None, "list_of_fset", "fset_of_list"), None,
                             ("'a list", False, "\\<lambda>xs ys. set xs = set ys"))
    assert mine[1][1][3] == (("fract", ["'a"], '("_ ratio" [21] 21)', "rep_fract", "abs_fract"), None,
                             ("'a :: idom \\<times> 'a", True, "\\<lambda>(a, b) (c, d). b \\<noteq> 0 \\<and> d \\<noteq> 0 \\<and> a * d = c * b"))
    assert mine[2][1][3][1] is True                                             # the recorded choice travels (COMMON §5)
    assert p.message()[2] == p.goal_structure() and q.message()[2] == q.goal_structure()
    assert isinstance(p.evaluation_status_beginning, M.Ready) and p.evaluation_status_beginning.messages == ()
    assert p.overloaded is False and q.overloaded is True                        # recorded, true and false alike
    assert isinstance(q.evaluation_status_beginning, M.Ready) and q.evaluation_status_beginning.messages == ()
    assert (p.message()[1], q.message()[1]) == (False, True)                     # recorded: what the next evaluation keeps to
    assert isinstance(r.evaluation_status_beginning, M.CannotEvaluate) and r.overloaded is True   # untouched by a failure
    assert [m.unicode for m in r.evaluation_status_beginning.messages] == ['"bad": illegal variable(s) in the relation: "P"']
    assert all(c._status is M.NOT_EVALUATED for c in r.sub_nodes) and r.evaluation_status_ending == M.READY_CLEAN
    assert isinstance(p.evaluation_status_ending, M.Ready) and all(isinstance(c._status, M.Ready) for c in p.sub_nodes)
    assert [name for name, _ in calls].count("TAT.Lifting_Closing.close") == 2           # `bad`'s ending is the copy
    assert p.mark(M.BRIEFING, 0) == "unverified definition, proof not started" and r.mark(M.BRIEFING, 0) == "invalid definition"
    assert not p.is_finished() and not r.is_finished()                     # the proof is compulsory (COMMON §3)
    # under a recorded `overloaded` false, the refusal is the definition's failure, the record untouched (§6)
    q.overloaded = False
    status = run(q._eval_beginning_opr())
    assert calls[-1][1][3] == (mine[1][1][3][0], False, mine[1][1][3][2])
    assert isinstance(status, M.CannotEvaluate) and q.overloaded is False
    assert [m.unicode for m in status.messages] == ['Type definition with open dependencies, use "(overloaded)"']
    (z,) = insert(f, x, 3, [ZINT])
    assert z.message() == (("zint", [], None, "rep_zint", "abs_zint"), None,
                           ("nat \\<times> nat", False, "\\<lambda>(a, b) (c, d). a + d = c + b"))
    assert z.mark(M.BRIEFING, 0) == "not evaluated, proof not started"


def test_the_recorded_field_reaches_the_store_and_the_mirror_catches_an_emit_ending_off_the_live_status(monkeypatch):
    """§1, §6; COMPILATION §3: a walk's store writes `overloaded` as the
    evaluation recorded it, so a loaded forest emits the same file; an
    `emit_ending` gated on the ending's live status writes the two
    commands in memory and not once loaded, which `assert_store_mirrors`
    says at once."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [FSET, FRACT]})])
    (x,) = s.sub_nodes
    p, q = x.sub_nodes
    fake_wire(monkeypatch, lambda message: [[], [message[0][0] == "fract", None]])
    run(x.evaluate_to(None, False))
    rows = {n.name: f.store.fields(n.identity) for n in (p, q)}
    assert (rows["fset"]["overloaded"], rows["fract"]["overloaded"]) == (False, True)
    assert_store_mirrors(f, KINDS, shape=ts.shape)                           # as shipped: mirrored
    emit_ending = QuotientType.emit_ending

    def off_the_live_status(self, indent, out):
        return emit_ending(self, indent, out) if isinstance(self.evaluation_status_ending, M.Ready) else indent
    monkeypatch.setattr(QuotientType, "emit_ending", off_the_live_status)
    with pytest.raises(AssertionError, match="Arith/X.thy: the loaded forest writes another text"):
        assert_store_mirrors(f, KINDS, shape=ts.shape)


def test_the_ending_calls_close_with_the_slot_after_the_last_child_the_resulting_slot_and_the_name(monkeypatch):
    """COMMON §6: `TAT.Lifting_Closing.close` with the ending's two slots —
    the slot after the last child and the block's resulting slot — and the
    type's name; no message is `Ready`, messages `CannotEvaluate` with
    them; `emit_ending` returns the indent."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [FSET, ZINT]})])
    (x,) = s.sub_nodes
    p, q = x.sub_nodes
    calls = fake_wire(monkeypatch, lambda message: [[], [False, None]])
    run(x.evaluate_to(None, False))
    endings = [args for name, args in calls if name == "TAT.Lifting_Closing.close"]
    assert endings == [(p._state_before_ending.to_msgpack(), p.resulting_state().to_msgpack(), "fset"),
                       (q._state_before_ending.to_msgpack(), q.resulting_state().to_msgpack(), "zint")]
    assert p.operation_slots("ending") == (p._state_before_ending, p.resulting_state())
    assert p.evaluation_status_ending == M.READY_CLEAN and q.evaluation_status_ending == M.READY_CLEAN

    async def refusing(conversation, name, args):
        return ["Interrupt"] if name == "TAT.Lifting_Closing.close" else [[], [False, None]]
    monkeypatch.setattr(isabelle_driver, "call", refusing)
    status = run(q._eval_ending_opr())
    assert isinstance(status, M.CannotEvaluate) and [m.unicode for m in status.messages] == ["Interrupt"]
    out = io.StringIO()
    assert q.emit_ending(2, out) == 2 and out.getvalue() == "\n    lifting_update zint.lifting\n    lifting_forget zint.lifting\n"
    assert "_eval_ending_opr" not in vars(QuotientType) and "emit_ending" not in vars(QuotientType)    # `Lifting_Closing`'s


def test_the_mark_reads_one_of_eleven_ways_and_the_owing_line_stands_while_unverified():
    """§7's mark, state by state, reading the beginning's status — COMMON §3's
    table with the three words of a class that defines; the eleven, and no
    other, are the document's first block; the owing line, its second —
    its third under `partial` — exactly while the line reads `unverified
    definition`."""
    [block, owing, owing_partial] = fenced_blocks(QT, "7.")
    assert [OWING_LINE] == owing and [OWING_LINE_PARTIAL] == owing_partial
    f, x = forest(FSET, FRACT)
    p, q = x.sub_nodes
    assert_the_eleven_ways(p, block, OWING_LINE)
    assert_the_eleven_ways(q, block, OWING_LINE_PARTIAL)
    with_proof(p, M.READY_CLEAN, NOT_STARTED)
    p.evaluation_status_ending = M.CannotEvaluate((IsaTerm.from_agent("Interrupt"),))       # not on the line (§7)
    assert p.mark(M.BRIEFING, 0) == "unverified definition, proof not started" and p.owing_line() == OWING_LINE


# --- what it prints (§8) -----------------------------------------------------

def test_print_fields_writes_the_definition_and_english_by_depth():
    f, x = forest(FSET, ZINT, FRACT)
    p, z, q = x.sub_nodes
    [one, failed, refused_ending, bad_proof] = fenced_blocks(QT, "8.")

    def fields(node, mode, depth):
        out = io.StringIO()
        node.print_fields(0, out, mode, depth)
        return out.getvalue().splitlines()
    assert [fields(p, M.RECALL, d) for d in range(4)] == [one, one[:1], one[:1], []]
    assert fields(p, M.OUT_FOCUS, 0) == [] and fields(p, M.Relative_Focus(frozenset({p}), 0), 0) == []
    p.overloaded = True                                                 # not printed: not authored (§8)
    assert fields(p, M.RECALL, 0) == one
    assert fields(z, M.RECALL, 1) == ['zint = "nat × nat" / "λ(a, b) (c, d). a + d = c + b"']          # no `morphisms` clause
    assert fields(q, M.RECALL, 1) == [
        '\'a fract ("_ ratio" [21] 21) = "\'a :: idom × \'a" / partial: "λ(a, b) (c, d). b ≠ 0 ∧ d ≠ 0 ∧ a * d = c * b"']
    # against no keyword, whatever the theory recorded: every name bare, the two texts quoted unless an identifier
    (u,) = insert(f, x, 3, [definition("u", "nat", "intrel", "A relation by name", type_parameters=(), rep_function_name="r")])
    for keywords in (None, frozenset(), frozenset({"fset", "list_of_fset", "u", "intrel", "r", "nat"})):
        x.keywords = keywords
        assert fields(u, M.RECALL, 1) == ["u = nat / intrel morphisms r abs_u"] and fields(p, M.RECALL, 1) == one[:1], keywords
    me = stand_ins.agent(f.conversation)
    # §8's three examples whole, with their marks: the refused definition, in a forest of its own, the children not
    # evaluated; the refused ending under a valid definition, the children valid; the stored proof that failed its check
    f2, _ = forest(definition(equiv_relation="λxs ys. set xs = set ys ∧ P xs", rep_function_name="list_of_fset",
                              abs_function_name="fset_of_list", children=[FEMPTY, FMEMBER]))
    (bad,) = f2.sub_nodes[0].sub_nodes[0].sub_nodes
    bad.evaluation_status_beginning = M.CannotEvaluate((IsaTerm.from_agent('"fset": illegal variable(s) in the relation: "P"'),))
    assert f2.render(bad, M.RECALL, stand_ins.agent(f2.conversation)).splitlines() == failed
    for c in p.sub_nodes:
        with_proof(c, M.READY_CLEAN, PROVED, PASSED)
    with_proof(p, M.READY_CLEAN, PROVED, PASSED)
    p.evaluation_status_ending = M.CannotEvaluate((IsaTerm.from_agent("Interrupt"),))
    assert f.render(p, M.RECALL, me).splitlines() == refused_ending
    p.evaluation_status_ending = M.READY_CLEAN
    with_proof(p, M.READY_CLEAN, PROVED, BAD)
    assert f.render(p, M.RECALL, me).splitlines() == bad_proof
    with_proof(p, M.NOT_EVALUATED, NOT_STARTED)                          # back to a node no walk reached
    p.evaluation_status_ending = M.NOT_EVALUATED
    for c in p.sub_nodes:
        with_proof(c, M.NOT_EVALUATED, NOT_STARTED)
    inv(f)


# --- emission (§5) ------------------------------------------------------------

def test_the_emitted_text_is_section_5_s():
    [one, two, three] = fenced_blocks(QT, "5.")
    f, x = forest(FSET, INT, FRACT)
    p, z, q = x.sub_nodes
    x.keywords = frozenset()                                 # recorded by a header run, which emission presupposes

    def emitted(node) -> list[str]:
        """In `unicode` (§5); the file's `\\<name>` form is the compile's conversion (COMPILATION §2)."""
        out = io.StringIO()
        assert node.emit(1, out) == 1
        assert "\\<" not in out.getvalue()                                 # nothing written in `ascii`
        return out.getvalue().splitlines()

    def expected(*unicode_lines: str) -> list[str]:
        return ["  " + line if line else "" for line in unicode_lines]
    with pytest.raises(AssertionError):                             # nothing recorded: never written (`can_emit`; COMMON §5)
        emitted(p)
    for node, recorded in ((p, False), (z, False), (q, True)):      # as §5's examples record them
        node.overloaded = recorded
        with_proof(node, M.READY_CLEAN, PROVED, PASSED)
        for c in node.sub_nodes:
            c.with_code_dt = False                               # as §5's examples record them: no `(code_dt)`
            with_proof(c, M.READY_CLEAN, PROVED, PASSED)
    assert emitted(p) == expected(*one) and emitted(z) == expected(*two) and emitted(q) == expected(*three)
    for outcome, check in ((PROVED, BAD), (PROVED, None), (PROVED, RUNNING), (NOT_STARTED, None)):
        with_proof(z, M.READY_CLEAN, outcome, check)                                     # not proven: `sorry`
        assert emitted(z) == expected(*two[:2], "  sorry", *two[3:]), (outcome, check)
    z.overloaded = True
    assert emitted(z)[1] == '  quotient_type (overloaded) int = "nat × nat" / "λ(a, b) (c, d). a + d = c + b"'
    # a type named after a keyword of the theory: the head and the names quoted, the bundle's name bare (COMMON §6)
    (t,) = insert(f, x, 3, [definition("term", "nat list", type_parameters=(), rep_function_name="list_of_term")])
    t.overloaded = False
    x.keywords = frozenset({"term", "list_of_term", "abs_term"})
    assert emitted(t) == expected("text ‹Finite sets, as lists up to order and repetition.›",
                                  'quotient_type "term" = "nat list" / "λxs ys. set xs = set ys"',
                                  '  morphisms "list_of_term" "abs_term"', "  sorry", "",
                                  "lifting_update term.lifting", "lifting_forget term.lifting")
    x.keywords = frozenset()
    assert emitted(t)[2] == "    morphisms list_of_term abs_term"
    # two parameters and an infix syntax; a relation that is an identifier, bare
    (s,) = insert(f, x, 4, [definition("sum", "'a + 'b", "sumrel", "Sums!", type_parameters=("'a", "'b"),
                                       syntax={"form": "infixr", "symbol": "⊕", "priority": 60}, abs_function_name="mk_sum")])
    s.overloaded = False
    assert emitted(s) == expected("text ‹Sums!›", 'quotient_type (\'a, \'b) sum (infixr "⊕" 60) = "\'a + \'b" / sumrel',
                                  "  morphisms rep_sum mk_sum", "  sorry", "", "lifting_update sum.lifting",
                                  "lifting_forget sum.lifting")


def test_the_two_spellings_are_kept_apart():
    """§2, §5, §8: a name, a parameter, the representation type or the
    relation whose `unicode` and `ascii` differ is stored, printed and
    emitted in `unicode` and sent to Isabelle in `ascii`."""
    f, x = forest(definition("t", "'α list", "λxs ys. set xs ≠ set ys ∨ ε = ε", "Greek", type_parameters=("'α",),
                             rep_function_name="ρ", abs_function_name="α⇩1"))
    (p,) = x.sub_nodes
    x.keywords = frozenset()
    assert p.message() == (("t", ["'\\<alpha>"], None, "\\<rho>", "\\<alpha>\\<^sub>1"), None,
                           ("'\\<alpha> list", False, "\\<lambda>xs ys. set xs \\<noteq> set ys \\<or> \\<epsilon> = \\<epsilon>"))
    rows = {}
    p.to_store(type("Rows", (), {"put": lambda self, k, v: rows.__setitem__(k, v)})())
    assert rows["type_parameters"] == ["'α"] and rows["representation_type"] == "'α list"
    assert rows["equiv_relation"] == "λxs ys. set xs ≠ set ys ∨ ε = ε"
    assert (rows["rep_function_name"], rows["abs_function_name"]) == ("ρ", "α⇩1")
    out = io.StringIO()
    p.print_fields(0, out, M.RECALL, 1)
    assert out.getvalue() == "'α t = \"'α list\" / \"λxs ys. set xs ≠ set ys ∨ ε = ε\" morphisms ρ α⇩1\n"
    out = io.StringIO()
    p.overloaded = False                                                # recorded, as emission presupposes
    p.emit(0, out)
    assert out.getvalue().splitlines()[1:3] == ["quotient_type 'α t = \"'α list\" / \"λxs ys. set xs ≠ set ys ∨ ε = ε\"",
                                                "  morphisms ρ α⇩1"]


# --- the id properties (§9), on test_ids.py's precedent -------------------------

def test_section_9_s_id_properties():
    """§9: the component is omissible in both directions with drop priority
    1 — after `Section`'s, before `Theory`'s —, a child's id printed as
    short as the forest allows and accepted with or without it; the
    node's own component never dropped from its own id."""
    assert (QuotientType.output_omissible, QuotientType.input_omissible, QuotientType.drop_priority) == (True, True, 1)
    f, x = forest(FSET, lift("fempty", "'a fset", "[]", "Another empty set"))
    p, other = x.sub_nodes
    fempty, fmember = p.sub_nodes
    assert f.id_of(p) == "quotient_type_fset" and f.id_of(fmember) == "lift_definition_fmember"
    for form in ("lift_definition_fmember", "quotient_type_fset.lift_definition_fmember", "theory_X.lift_definition_fmember",
                 "session_Arith.theory_X.quotient_type_fset.lift_definition_fmember"):
        assert f.resolve(form) is fmember
    assert f.resolve("quotient_type_fset") is p and f.resolve("theory_X.quotient_type_fset") is p
    # the other `fempty` directly under the theory: the block's component tells the inner one apart, and the other
    # prints its full id, each shorter form of it being a form of the inner's (test_ids.py's exact-match rule)
    assert f.id_of(fempty) == "quotient_type_fset.lift_definition_fempty"
    assert f.id_of(other) == "session_Arith.theory_X.lift_definition_fempty" and f.resolve(f.id_of(other)) is other
    run(locked(f, edit.delete(other)))
    # before `Theory`'s: a second `fempty` in another theory — `theory_X.…` kept, the block's component dropped first
    (s,) = f.sub_nodes
    (y,) = insert(f, s, 1, [theory("Y") | {"children": [FSET]}])
    assert f.id_of(fempty) == "theory_X.lift_definition_fempty" and f.id_of(y.sub_nodes[0].sub_nodes[0]) == "theory_Y.lift_definition_fempty"
    run(locked(f, edit.delete(y)))
    # after `Section`'s: test_ids.py's `Sec` inside the block holding a `fcard`, another `fcard` directly under the
    # theory — the section dropped, the block kept
    sec = test_ids.mk_block(test_ids.Sec, p, "B")
    (inner,) = run(locked(f, edit.insert(sec, 0, [lift("fcard", "'a fset ⇒ nat", "λxs. card (set xs)", "The size")],
                                         {**KINDS, "section": test_ids.Sec})))
    (outer,) = insert(f, x, 1, [lift("fcard", "'a fset ⇒ nat", "λxs. card (set xs)", "The size")])
    assert f.id_of(inner) == "quotient_type_fset.lift_definition_fcard" and f.resolve("section_B.lift_definition_fcard") is inner
    assert f.id_of(outer) == "session_Arith.theory_X.lift_definition_fcard" and f.id_of(fempty) == "lift_definition_fempty"


# --- the evaluation, in the plugin's run of the harness (§5, §6, §7, §8) --------

FMEMBER_FEMPTY = lemma("fmember_fempty", english="Nothing is a member of the empty finite set",
                       for_any=({"name": "x", "type": "'a"},), premises=(), conclusion="¬ fmember x fempty")
FSET_WITH_LEMMA = {**FSET, "children": [FEMPTY, FMEMBER, FMEMBER_FEMPTY]}


@pytest.mark.isabelle(deadline=600)
async def test_a_quotient_type_is_defined_its_setup_closed_and_a_proof_checked(std_conversation, std_harness, tmp_path):
    """§6 through `TAT.QuotientType.evaluate` and `TAT.Lifting_Closing.close`:
    a theory of §2's `fset` — its two `lift_definition`s and a theorem by
    `transfer` inside the block —, `zint` and `fract`, each defined with
    its goal in `goal_state`, `overloaded` recorded false, false and true,
    every ending `Ready`, then a theorem whose statement parses through
    the morphisms, the lifted functions and the syntax; `recall` as §8
    shows; the theory rendered as §5 shows, under the recorded keywords,
    and read back whole by Isabelle; then the proof check for real (§7):
    a product on the inner theorem and one on `fset`'s goal, both `PASSED`
    under `checks: "blocking"`, `fset` at `valid definition` with no owing
    line and `by aoa` emitted.  Last, the callback alone: `[[], [a, nil]]`
    on the wire."""
    forest = std_conversation.forest
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [ts.session("TAT_Suite", ts.theory("TAT_Std_Q") | {"children": [
                FSET_WITH_LEMMA, ZINT, FRACT,
                lemma("uses_the_definitions", english="Every definition above parses",
                      for_any=({"name": "x", "type": "'a"}, {"name": "xs", "type": "'a list"},
                               {"name": "z", "type": "zint"}, {"name": "q", "type": "int ratio"}),
                      premises=(),
                      conclusion="fmember x (fset_of_list xs) = fmember x (fset_of_list xs) ∧ list_of_fset fempty = []"
                                 " ∧ rep_zint z = rep_zint z ∧ rep_fract q = rep_fract q")]})]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 0 and text.count("Notice:") == 0, text
        (s,) = forest.sub_nodes
        (a,) = s.sub_nodes
        fset, zint, fract, uses = a.sub_nodes
        fempty, fmember, inner = fset.sub_nodes
        for node in (fset, zint, fract):
            assert node.evaluation_status_beginning == M.READY_CLEAN and node.evaluation_status_ending == M.READY_CLEAN, node.name
            assert await node.goal_state.is_initialized() and await node.resulting_state().is_initialized()
            assert await node.operation_slots("beginning")[1].is_initialized()
        for node in (fempty, fmember, inner, uses):
            assert node._status == M.READY_CLEAN and await node.goal_state.is_initialized(), node.name
        assert [n.overloaded for n in (fset, zint, fract)] == [False, False, True]
        [one, _, _, _] = fenced_blocks(QT, "8.")
        recalled = await session.call_tool("recall", {"node_id": "quotient_type_fset"})
        lines = text_of(recalled).splitlines()
        assert not recalled.isError and lines[:11] == [
            "- quotient_type_fset (unverified definition, proof not started)", *("  " + line for line in one), "  " + OWING_LINE,
            "  - lift_definition_fempty (unverified definition, proof not started)", '    fempty :: "\'a fset" is "[]"',
            "    " + LD_OWING_LINE,
            "  - lift_definition_fmember (unverified definition, proof not started)",
            '    fmember :: "\'a ⇒ \'a fset ⇒ bool" is "λx xs. x ∈ set xs"', "    " + LD_OWING_LINE,
            "  - lemma_fmember_fempty (valid statement, proof not started)"], lines
        recalled = await session.call_tool("recall", {"node_id": "quotient_type_fract"})       # no child: the empty node's line
        assert not recalled.isError and text_of(recalled).splitlines() == [
            "- quotient_type_fract (unverified definition, proof not started)",
            '  \'a fract ("_ ratio" [21] 21) = "\'a :: idom × \'a" / partial: "λ(a, b) (c, d). b ≠ 0 ∧ d ≠ 0 ∧ a * d = c * b"',
            "  Rational numbers, as fractions with a non-zero denominator", "  " + OWING_LINE_PARTIAL,
            "  " + M.EMPTY_NODE.format(id="quotient_type_fract")], text_of(recalled)
        # the theory rendered as §5 shows, with `sorry`, and its body read back whole by Isabelle on the heap's Main
        rendered = C.render(forest)
        file = rendered.files[C.Path("TAT_Suite/TAT_Std_Q.thy")]
        assert file.startswith('theory "TAT_Std_Q"\n  imports "Main" "TAT_Std.TAT_Std"\nbegin\n') and file.endswith("end\n")
        [one, two, three] = fenced_blocks(QT, "5.")
        zint = [re.sub(r"\bint\b", "zint", line) for line in two]                  # §5's `int`, run here as `zint`
        for block in (one[:10], one[-3:], zint, three):
            assert "".join(ascii_of_unicode(line) + "\n" for line in block).replace(" by aoa\n", " sorry\n") in file, file
        assert "(overloaded) 'a fract" in file and "(overloaded) 'a fset" not in file and "(overloaded) zint" not in file
        body = tmp_path / "body.thy"
        body.write_text(file[file.index("begin\n") + len("begin\n"):file.rindex("end\n")])
        r = await ml_process(std_harness, f'val _ = after thy0 (File.read (Path.explode {ml_string(str(body))}));\n'
                                               'writeln "read back";')
        assert r.returncode == 0 and "read back" in r.stdout.splitlines(), (r.stdout, r.stderr)
        # the proof check for real (§7; COMMON §3): a product on the inner theorem and one on `fset`'s goal, replayed
        inner.job().outcome = Succeeded({"text": "(transfer, simp)", "thread_cpu": 2000, "wall": 2000})
        fset.job().outcome = Succeeded({"text": "(auto intro!: equivpI reflpI sympI transpI)", "thread_cpu": 2000, "wall": 2000})
        await tm._invalidate(fset)
        assert fset.mark(M.BRIEFING, 0) == "not evaluated" and inner.mark(M.BRIEFING, 0) == "not evaluated"
        result = await session.call_tool("evaluate_to", {"node_id": "theory_TAT_Std_Q", "checks": "blocking"})
        assert not result.isError, text_of(result)
        assert fset.check_outcome() is PASSED and inner.check_outcome() is PASSED
        assert fset.mark(M.BRIEFING, 0) == "valid definition" and fset.owing_line() is None
        assert inner.mark(M.BRIEFING, 0) == "valid statement, proven"
        out = io.StringIO()
        fset.emit_beginning(0, out)
        assert out.getvalue().splitlines()[3] == "  by aoa"
        # the callback alone: what the two steps yielded, `[[], [a, nil]]` (COMMON §3)
        for node, recorded in ((fset, False), (fract, True)):
            messages, what = await isabelle_driver.call(
                forest.conversation, "TAT.QuotientType.evaluate",
                (node.state.to_msgpack(), node.goal_state.to_msgpack(), node.operation_slots("beginning")[1].to_msgpack(),
                 node.message()))
            assert (messages, what) == ([], [recorded, None]), node.name


@pytest.mark.isabelle(deadline=600)
async def test_refused_definitions_a_refused_admission_and_the_recorded_value_s_rule(std_conversation):
    """§6, §8, one theory per obstacle: a relation with a free `P` is refused
    by `sanity_check` with §8's first example, the children `not_evaluated`
    and the ending `Ready`, `recall` as §8 shows; a type `clash` with
    `abs_clash` as the Rep name and the Abs name left out, accepted by
    `gen`, is refused at the admission with the duplicate constant; a
    `lift_definition` after the block of a type `fs` is refused as
    LIFT_DEFINITION.md §6 says, the setup closed — the other theories'
    types named apart, so that `fset`'s id stays short; each an obstacle
    with `goal_state` empty and nothing recorded; no such theory written.
    Then the recorded value's rule (COMMON §5) through the callback alone,
    on slots beside the tree's: `fs` recorded true runs once and goes
    through; `fract` recorded false is refused at the admission, nothing
    yielded, `goal_state` empty."""
    forest = std_conversation.forest
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [ts.session("TAT_Suite",
                ts.theory("TAT_Std_QB") | {"children": [
                    definition(equiv_relation="λxs ys. set xs = set ys ∧ P xs", rep_function_name="list_of_fset",
                               abs_function_name="fset_of_list", children=[FEMPTY, FMEMBER])]},
                ts.theory("TAT_Std_QC") | {"children": [definition("clash", rep_function_name="abs_clash")]},
                ts.theory("TAT_Std_QD") | {"children": [
                    definition("fs"), lift("fcard", "'a fs ⇒ nat", "λxs. card (set xs)", "The number of members")]},
                ts.theory("TAT_Std_QE") | {"children": [definition("fs"), FRACT]})]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 3, text
        (s,) = forest.sub_nodes
        b, c, d, e = s.sub_nodes
        (free,), (clash,), (_, after), (fs, fract) = (t.sub_nodes for t in (b, c, d, e))
        [_, failed, _, _] = fenced_blocks(QT, "8.")
        assert isinstance(free.evaluation_status_beginning, M.CannotEvaluate) and not await free.goal_state.is_initialized()
        assert [m.unicode for m in free.evaluation_status_beginning.messages] == [failed[4].strip()]
        assert all(ch._status is M.NOT_EVALUATED for ch in free.sub_nodes) and free.evaluation_status_ending == M.READY_CLEAN
        recalled = await session.call_tool("recall", {"node_id": "quotient_type_fset"})                 # §8's example whole
        assert not recalled.isError and text_of(recalled).splitlines() == failed, text_of(recalled)
        assert isinstance(clash.evaluation_status_beginning, M.CannotEvaluate) and not await clash.goal_state.is_initialized()
        assert clash.evaluation_status_beginning.messages[0].unicode.startswith("Duplicate constant declaration"), clash.evaluation_status_beginning
        [_, _, _, sentences, _] = fenced_blocks(DOCS / "node_classes" / "LIFT_DEFINITION.md", "6.")
        assert isinstance(after._status, M.CannotEvaluate)
        assert [m.unicode for m in after._status.messages] == [sentences[1].replace("fset", "fs")]
        assert not await after.goal_state.is_initialized()
        assert free.overloaded is None and clash.overloaded is None                       # nothing recorded (§1)
        assert fs.overloaded is False and fract.overloaded is True
        # the recorded value's rule through the callback alone (COMMON §5), on slots beside the tree's
        goal, resulting = (M.Isar_State_Slot.assign(forest.conversation) for _ in range(2))
        messages, what = await isabelle_driver.call(
            forest.conversation, "TAT.QuotientType.evaluate",
            (fs.state.to_msgpack(), goal.to_msgpack(), resulting.to_msgpack(), (fs.message()[0], True, fs.message()[2])))
        assert (messages, what) == ([], [True, None]) and await goal.is_initialized()
        goal, resulting = (M.Isar_State_Slot.assign(forest.conversation) for _ in range(2))
        messages, what = await isabelle_driver.call(
            forest.conversation, "TAT.QuotientType.evaluate",
            (fract.state.to_msgpack(), goal.to_msgpack(), resulting.to_msgpack(), (fract.message()[0], False, fract.message()[2])))
        assert what is None and len(messages) == 1 and "Type definition with open dependencies" in messages[0], messages
        assert not await goal.is_initialized()
    rendered = C.render(forest)
    assert not any(C.Path(f"TAT_Suite/TAT_Std_Q{t}.thy") in rendered.files for t in "BCD")   # an obstacle: not written
    assert C.Path("TAT_Suite/TAT_Std_QE.thy") in rendered.files
