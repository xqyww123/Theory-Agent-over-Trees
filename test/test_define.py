"""`Define` (node_classes/DEFINE.md): with no Isabelle, the schema and the
descriptions (§2, §3), `gen` and the field check (§4), the definition as
the node holds, stores and prints it (§1, §2, §8), the node's name and the
framework's `DuplicateName` on it (§9), the message, the status and the
recorded fields (§6), the carry on an amend (§4), the jobs — their calls,
their product, their sentences, the texts the proof agent reads — the
mark and the owing line (§7), the emitted text (§5); through the std
harness, the evaluation (§6), `recall` (§8) and the rendered file (§5).
Run: python -m pytest test/test_define.py
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
from IsaMini.AoA.model import Role_Major, Role_Worker
from IsaMini.AoA.task import TASK_REGISTRY
from Isabelle_RPC_Host.unicode import IsaTerm, ascii_of_unicode
from isabelle_theory_agent import compile as C, edit, isabelle_driver, model as M
from isabelle_theory_agent.exceptions import DuplicateName, InvalidField, InvalidName, RawASTError, TAT_StartupError
from isabelle_theory_agent.jobs import NOT_STARTED, PASSED, RUNNING, Failed, Succeeded
from isabelle_theory_agent.std import common, define
from isabelle_theory_agent.std.common import NO_SETUP, Infix, Proof_Check, Variable_With_Syntax
from isabelle_theory_agent.std.define import (
    INTERPRETATIONS, OBLIGATIONS, PATTERN_COMPLETENESS, TERMINATION, Define, Define_Proof_Check,
    Define_Proof_Job, Termination_Task, assertion, goal_hint, task_text)
from isabelle_theory_agent.store import Forest_Store
from ml_process import TAT_STD, read_back
from std_forest import KINDS, field_check, forest, insert, inv, refused
from test_descriptions import descriptions
from test_model import locked, run
from test_session_theory import Forest_Under_Test, session, theory
from test_theorem import BAD, INVALID, lemma, with_proof

table = ts.table                    # the fake state slot table and the fake wire, per test
DD = DOCS / "node_classes" / "DEFINE.md"

FIB, EVEN_ODD = (json.loads("\n".join(block)) for block in fenced_blocks(DD, "2.")[:2])     # §2's two examples
PROVED = Succeeded({TERMINATION: {"text": "by (relation \"measure id\") auto", "thread_cpu": 3, "wall": 5}})
SEQUENTIAL = "function (sequential, no_partials)"       # the form of a definition made under `fun`'s configuration (§1)
FUN = (SEQUENTIAL, "pat_completeness auto", "lexicographic_order")      # ... whose two goals `fun`'s methods closed


def definition(name="sum_upto", equations=("sum_upto i N = (if N < i then 0 else i + sum_upto (Suc i) N)",),
               english="The sum of the naturals from i to N", type="nat ⇒ nat ⇒ nat", auto_reduction=False, **fields):
    """A `definition` construct: §5's and §8's `sum_upto` by default, whose
    termination `fun` cannot prove by itself."""
    constant = {"name": name, **({"type": type} if type is not None else {})}
    return {"kind": "definition", "english": english, "constants": [constant], "equations": list(equations),
            "auto_reduction": auto_reduction, **fields}


SUM_UPTO = definition()
TWICE = definition("twice", ("twice n = n + n",), "Twice a natural number", type="nat ⇒ nat", auto_reduction=True)   # §5's `definition`


def evaluated(node, form, completeness_method=None, termination_method=None, status=M.READY_CLEAN):
    """The node as an evaluation left it: its records and its status."""
    node.form, node.completeness_method, node.termination_method = form, completeness_method, termination_method
    node._status = status


def fields(node, mode, depth):
    out = io.StringIO()
    node.print_fields(0, out, mode, depth)
    return out.getvalue().splitlines()


def emitted(node) -> list[str]:
    """In `unicode` (§5); the file's `\\<name>` form is the compile's conversion (COMPILATION §2)."""
    out = io.StringIO()
    assert node.emit(1, out) == 1
    assert "\\<" not in out.getvalue()
    return [line[2:] for line in out.getvalue().splitlines()]


# --- the schema and the descriptions (§2, §3) ------------------------------

def test_the_schema_and_the_descriptions_are_the_documents():
    [_, _, schema] = fenced_blocks(DD, "2.")
    text = "\n".join(line for line in schema if not line.lstrip().startswith("...MIXFIX_DEFS"))   # the spread
    expected = jsoncomment.JsonComment().loads(text)
    expected["$defs"] = {**expected["$defs"], **common.MIXFIX_DEFS}
    assert Define.construct_schema == expected
    assert list(define.KINDS) == ["definition"]
    assert sorted(descriptions(Define.construct_schema)) == sorted(fenced_lines(DD, "3.") + descriptions(common.MIXFIX_DEFS))
    assert FIB == {"kind": "definition", "english": "The Fibonacci numbers", "constants": [{"name": "fib", "type": "nat ⇒ nat"}],
                   "equations": ["fib 0 = 0", "fib (Suc 0) = 1", "fib (Suc (Suc n)) = fib n + fib (Suc n)"],
                   "auto_reduction": True}
    assert EVEN_ODD["constants"] == [{"name": "even", "type": "nat ⇒ bool"}, {"name": "odd", "type": "nat ⇒ bool"}]


# --- `gen` (§2, §4, §9) --------------------------------------------------------

def test_gen_keeps_the_definition_normalised_as_isaterms_and_names_the_node():
    f, x = forest(definition(equations=(" sum_upto  i N = (if N < i\n then 0 else i + sum_upto (Suc i) N) ",),
                             english=" The sum of the\n naturals  from i to N", type=" nat ⇒ nat ⇒\nnat "))
    (p,) = x.sub_nodes
    assert isinstance(p, Define) and p.kind == "definition" and p.name == "sum_upto" and f.id_of(p) == "definition_sum_upto"
    assert p.english == "The sum of the naturals from i to N"
    assert p.constants == (Variable_With_Syntax(IsaTerm.from_agent("sum_upto"), IsaTerm.from_agent("nat ⇒ nat ⇒ nat"), None),)
    assert [e.unicode for e in p.equations] == list(SUM_UPTO["equations"]) and all(isinstance(e, IsaTerm) for e in p.equations)
    assert p.auto_reduction is False
    assert (p.form, p.completeness_method, p.termination_method, p.failed_obligation) == (None, None, None, None)
    assert p.open_obligations() == () and p.message()[3] is None              # nothing recorded yet (§1, §6)
    slots = p._states_inside()
    assert p.completeness_state in slots and p.termination_state in slots and p.completeness_state is not p.termination_state
    assert p._slots_written_by(None) == (p.completeness_state, p.termination_state)
    (q,) = insert(f, x, 1, [EVEN_ODD | {"constants": [
        {"name": "even", "type": "nat ⇒ bool", "syntax": {"form": "infixl", "symbol": "⊕", "priority": 65}}, {"name": "odd"}]}])
    assert q.name == "even_and_odd" and f.id_of(q) == "definition_even_and_odd"
    assert q.constants[0].syntax == Infix("infixl", IsaTerm.from_agent("⊕"), 65) and q.constants[1] == Variable_With_Syntax(IsaTerm.from_agent("odd"), None, None)
    inv(f)


def test_gen_refuses_as_section_4_says():
    """§4's `gen` refuses only a constant's name outside §1's grammar
    (RENDER_BASELINES §2's line for a constant name), before any field is
    judged; a missing field, a recorded field authored, an empty list or
    the integer bound, by the framework."""
    f, x = forest()
    [invalid] = [line for line in fenced_lines(DOCS / "RENDER_BASELINES.md", "2.")
                 if line.startswith("`dl-rev` is not a valid constant name")]
    e = refused(f, x, [definition("my-fun")], InvalidName)
    assert (e.name, e.grammar) == ("my-fun", "constant name")
    assert str(e) == "At `constructs[0]`: " + invalid.replace("dl-rev", "my-fun")
    for name in ("1st", "sum_upto_", "a b", "x'y-", "", "λ", " sum_upto"):
        assert refused(f, x, [definition(name)], InvalidName).grammar == "constant name"
    assert refused(f, x, [definition("my-fun") | {"constants": [{"name": "my-fun"}, {"name": "my-fun"}]}], InvalidName).name == "my-fun"
    for raw in ({k: v for k, v in SUM_UPTO.items() if k != "auto_reduction"},         # required, no default (§1)
                SUM_UPTO | {"form": "definition"}, SUM_UPTO | {"completeness_method": None},    # recorded, not authored (§1)
                SUM_UPTO | {"constants": []}, SUM_UPTO | {"equations": []},              # `minItems` (§4)
                SUM_UPTO | {"constants": [{"name": "sum_upto", "syntax": {"form": "binder", "symbol": "∀", "priority": 10, "x": 1}}]}):
        refused(f, x, [raw], RawASTError)
    [bound] = [line for line in fenced_lines(DOCS / "RENDER_BASELINES.md", "2.") if line.endswith("must be a 64-bit integer.")]
    e = refused(f, x, [definition() | {"constants": [{"name": "sum_upto", "syntax": {"form": "infixl", "symbol": "+", "priority": 2**64}}]}],
                InvalidField)
    assert str(e) == "At `constructs[0]`: " + bound.replace("types[0].constructors[1].syntax", "constants[0].syntax")
    assert x.sub_nodes == []
    inv(f)


def test_the_field_check_refuses_as_section_4_says():
    """§4's field check: a constant twice, the plugin's one sentence (§4's
    block), told alone, no path before it."""
    f, x = forest()
    [twice] = fenced_blocks(DD, "4.")[0]
    e = field_check(f, x, [EVEN_ODD | {"constants": [{"name": "even"}, {"name": "even"}]}])
    assert str(e) == twice and e.field == "constants[1].name"
    assert field_check(f, x, [EVEN_ODD]) is None and field_check(f, x, [SUM_UPTO]) is None
    assert x.sub_nodes == []
    inv(f)


def test_a_sibling_bearing_the_node_s_id_component_is_the_framework_s_duplicate_name():
    f, x = forest(EVEN_ODD)
    e = refused(f, x, [definition("even_and_odd", ("even_and_odd n = n",), "Both at once", type="nat ⇒ nat", auto_reduction=True)], DuplicateName)
    assert e.id_component == "definition_even_and_odd" and e.taken_by == "definition_even_and_odd"       # §9
    inv(f)


def test_an_amend_with_the_same_goal_structure_carries_the_proofs():
    """§4: equal constants and equations carry the replaced job's outcome —
    `english` and `auto_reduction` aside; a changed equation, type or
    syntax does not; the stored check is never carried."""
    f, x = forest(SUM_UPTO)
    (p,) = x.sub_nodes
    with_proof(p, M.READY_CLEAN, PROVED, PASSED)
    (p2,) = run(locked(f, edit.amend(p, [definition(english="The naturals from i to N, summed", auto_reduction=True)])))
    assert p2.job().outcome == PROVED and p2.check_outcome() is None
    assert p2.goal_structure() == p.goal_structure() == (
        [("sum_upto", "nat \\<Rightarrow> nat \\<Rightarrow> nat", None)], ["sum_upto i N = (if N < i then 0 else i + sum_upto (Suc i) N)"])
    for changed in (definition(equations=("sum_upto i N = (if N < i then 0 else sum_upto (Suc i) N)",)),
                    definition(type="int ⇒ int ⇒ int"),
                    definition() | {"constants": [{"name": "sum_upto", "type": "nat ⇒ nat ⇒ nat",
                                                   "syntax": {"form": "infixl", "symbol": "⊕", "priority": 65}}]}):
        x.sub_nodes[0].job().outcome = PROVED
        x.sub_nodes[0].failed_obligation = TERMINATION
        (p3,) = run(locked(f, edit.amend(x.sub_nodes[0], [changed])))
        assert p3.job().outcome is NOT_STARTED and p3.failed_obligation is None, changed    # neither carried
    inv(f)
    # the replacement records nothing else (§6; COMMON §5): `failed_obligation` goes with the carried failure, so
    # its sentences — the refutation sentence too — read as before the amend
    f, x = forest(SUM_UPTO, lemma("P"))
    p, l = x.sub_nodes
    evaluated(p, SEQUENTIAL, "pat_completeness auto", None)
    p.failed_obligation = TERMINATION
    with_proof(p, M.READY_CLEAN, Failed("gave up", "refute"))
    (p2,) = run(locked(f, edit.amend(p, [definition(english="The naturals from i to N, summed")])))
    assert p2.job().outcome == Failed("gave up", "refute") and p2.check_outcome() is None
    assert (p2.form, p2.completeness_method, p2.termination_method, p2.failed_obligation) == (None, None, None, TERMINATION)
    assert p2.message()[3] is None and p2.open_obligations() == ()
    assert p2.job().failure_header(p2.job().outcome) == "Function `definition_sum_upto` may not terminate:"
    assert p2.job().failure_header(Failed("gave up")) == "Failed to prove that function `definition_sum_upto` terminates:"
    assert f.store.get(p2.identity, "failed_obligation") == TERMINATION
    # a node stored before the carry, its failure naming no obligation: `Proof_Job`'s header
    p2.failed_obligation = None
    assert p2.job().failure_header(Failed("gave up")) == l.job().failure_header(Failed("gave up"))
    inv(f)


# --- the store (§1, §2) --------------------------------------------------------

def test_the_definition_is_stored_and_a_missing_row_is_refused_at_start(tmp_path):
    path = tmp_path / "TAT.sqlite"
    f, x = forest(SUM_UPTO, TWICE, EVEN_ODD | {"constants": [
        {"name": "even", "type": "nat ⇒ bool", "syntax": {"form": "infixl", "symbol": "⊕", "priority": 65}}, {"name": "odd"}]},
        store=Forest_Store(path, ts.stand_ins.log()))
    nodes = x.sub_nodes
    evaluated(nodes[0], SEQUENTIAL, "pat_completeness auto", None)   # as evaluations record them (§6), unequal
    evaluated(nodes[1], "definition")
    evaluated(nodes[2], "function", None, "lexicographic_order")
    nodes[0].failed_obligation = TERMINATION
    with f.store.transaction():
        for n in nodes:
            f._store_node(n)

    def held(n):
        return (n.name, n.english, n.constants, n.equations, n.auto_reduction, n.form, n.completeness_method,
                n.termination_method, n.failed_obligation)
    before = [held(n) for n in nodes]
    rows = f.store.fields(nodes[0].identity)
    assert "name" not in rows and rows["constants"] == [{"name": "sum_upto", "type": "nat ⇒ nat ⇒ nat"}]
    assert rows["equations"] == SUM_UPTO["equations"] and rows["auto_reduction"] is False
    assert (rows["form"], rows["completeness_method"], rows["termination_method"]) == (SEQUENTIAL, "pat_completeness auto", None)
    assert rows["failed_obligation"] == TERMINATION
    rows = f.store.fields(nodes[1].identity)
    assert (rows["form"], rows["completeness_method"], rows["termination_method"], rows["failed_obligation"]) == ("definition", None, None, None)
    rows = f.store.fields(nodes[2].identity)
    assert rows["constants"] == [{"name": "even", "type": "nat ⇒ bool", "syntax": {"form": "infixl", "symbol": "⊕", "priority": 65}},
                                 {"name": "odd"}]
    assert (rows["form"], rows["termination_method"]) == ("function", "lexicographic_order")
    f.store.close()
    f2 = Forest_Under_Test(store=Forest_Store(path, ts.stand_ins.log()), kinds=KINDS)
    loaded = f2.sub_nodes[0].sub_nodes[0].sub_nodes
    assert [held(n) for n in loaded] == before and all(isinstance(n, Define) for n in loaded)
    assert loaded[0].termination_state.name != nodes[0].termination_state.name
    assert loaded[0].open_obligations() == (TERMINATION,) and loaded[1].open_obligations() == ()
    assert loaded[2].open_obligations() == (PATTERN_COMPLETENESS,)
    unevaluated = Forest_Under_Test(kinds=KINDS)
    (u,) = insert(unevaluated, unevaluated, 0, [session("Arith", theory("X") | {"children": [SUM_UPTO]})])
    assert unevaluated.store.fields(u.sub_nodes[0].sub_nodes[0].identity)["form"] is None
    f2.store.close()
    for field in ("equations", "auto_reduction", "form", "completeness_method", "termination_method", "failed_obligation"):
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


# --- the message, the status and the recorded fields (§6); the obligations (§1, §7) --------

def test_eval_opr_sends_the_definition_and_records_the_form_and_the_methods(monkeypatch):
    """§6: the callback with the input slot, the two goal slots, the
    resulting slot and the message — the goal structure, then
    `auto_reduction`; the three records taken from a clean answer; Isabelle's
    messages an obstacle, the records untouched.  What the records decide:
    the open obligations, the mark, the owing line, whether the node is
    finished with no proof."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        FIB, SUM_UPTO, TWICE, EVEN_ODD, definition("bad", ("bad (n + 1) = Suc (bad (n div 2))",), "Refused")]})])
    (x,) = s.sub_nodes
    fib, sum_upto, twice, even_odd, bad = x.sub_nodes
    calls = []
    answers = {"fib": list(FUN), "sum_upto": [SEQUENTIAL, "pat_completeness auto", None],
               "twice": ["definition", None, None], "even": list(FUN)}

    async def call(conversation, name, args):
        calls.append((name, args))
        first = args[4][0][0][0]
        if first == "bad":
            return [["Malformed definition:\nNon-constructor pattern not allowed in sequential mode.\n\\<And>n. bad (n + 1) = Suc (bad (n div 2))"], None]
        return [[], answers[first]]
    monkeypatch.setattr(isabelle_driver, "call", call)
    evaluated(bad, *FUN, M.NOT_EVALUATED)                                      # an earlier run's records
    run(x.evaluate_to(None, False))
    assert [name for name, _ in calls] == ["TAT.Define.evaluate"] * 5
    assert [args[:4] for _, args in calls] == [
        (n.state.to_msgpack(), n.completeness_state.to_msgpack(), n.termination_state.to_msgpack(), n.resulting_state().to_msgpack())
        for n in (fib, sum_upto, twice, even_odd, bad)]
    assert calls[1][1][4] == (
        [("sum_upto", "nat \\<Rightarrow> nat \\<Rightarrow> nat", None)], ["sum_upto i N = (if N < i then 0 else i + sum_upto (Suc i) N)"],
        False, None)                                                            # the first evaluation: the command to be decided
    assert calls[4][1][4][3] == SEQUENTIAL                                      # `bad`'s earlier record travels back (§6)
    assert sum_upto.message() == (*calls[1][1][4][:3], SEQUENTIAL)              # the next evaluation runs the recorded command
    assert even_odd.message() == ([("even", "nat \\<Rightarrow> bool", None), ("odd", "nat \\<Rightarrow> bool", None)],
                                  ["even 0 = True", "even (Suc n) = odd n", "odd 0 = False", "odd (Suc n) = even n"], False, SEQUENTIAL)
    assert sum_upto.message()[:2] == sum_upto.goal_structure()
    for node, (form, cm, tm) in ((fib, FUN), (sum_upto, (SEQUENTIAL, "pat_completeness auto", None)),
                                 (twice, ("definition", None, None))):
        assert isinstance(node._status, M.Ready) and node._status.messages == ()
        assert (node.form, node.completeness_method, node.termination_method) == (form, cm, tm), node.name
    assert isinstance(bad._status, M.CannotEvaluate) and (bad.form, bad.completeness_method) == (SEQUENTIAL, "pat_completeness auto")
    assert [m.unicode for m in bad._status.messages] == [
        "Malformed definition:\nNon-constructor pattern not allowed in sequential mode.\n⋀n. bad (n + 1) = Suc (bad (n div 2))"]
    # the common `Define` owes nothing: finished at once, its construction skipped, its line `valid definition`
    assert fib.open_obligations() == () and fib.is_finished() and not fib.job()._check() and fib._unfinished() is None
    assert fib.mark(M.BRIEFING, 0) == "valid definition" and fib.owing_line() is None
    assert twice.is_finished() and twice.mark(M.BRIEFING, 0) == "valid definition" and even_odd.is_finished()
    # one open obligation: the proof is owed, the owing line names it
    assert sum_upto.open_obligations() == (TERMINATION,) and not sum_upto.is_finished() and sum_upto.job()._check()
    assert sum_upto.mark(M.BRIEFING, 0) == "unverified definition, proof not started"
    assert sum_upto.owing_line() == "The definition is unverified until termination is proven."
    assert bad.mark(M.BRIEFING, 0) == "invalid definition" and bad.owing_line() is None
    (t,) = insert(f, x, 5, [definition("t", ("t n = n",), "Later", type="nat ⇒ nat", auto_reduction=True)])
    assert t.mark(M.BRIEFING, 0) == "not evaluated, proof not started" and t.owing_line() is None
    assert t.open_obligations() == () and t.message()[3] is None              # nothing recorded yet


def test_the_recorded_fields_reach_the_store_and_the_mirror_catches_an_emit_off_an_instant_status(monkeypatch):
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [FIB, SUM_UPTO]})])
    (x,) = s.sub_nodes
    fib, sum_upto = x.sub_nodes

    async def call(conversation, name, args):
        return [[], list(FUN) if args[4][0][0][0] == "fib" else [SEQUENTIAL, "pat_completeness auto", None]]
    monkeypatch.setattr(isabelle_driver, "call", call)
    run(x.evaluate_to(None, False))
    rows = {n.name: f.store.fields(n.identity) for n in (fib, sum_upto)}
    assert (rows["fib"]["form"], rows["fib"]["termination_method"], rows["sum_upto"]["form"], rows["sum_upto"]["termination_method"]) == (
        SEQUENTIAL, "lexicographic_order", SEQUENTIAL, None)
    assert_store_mirrors(f, shape=ts.shape)

    def off_the_instant_status(self):       # the command from the instant status, not the records: `fun` while `ready`
        return "fun" if all(isinstance(st, M.Ready) for st in self.evaluation_statuses()) else SEQUENTIAL
    monkeypatch.setattr(Define, "_command", off_the_instant_status)
    with pytest.raises(AssertionError, match="Arith/X.thy: the loaded forest writes another text"):
        assert_store_mirrors(f, shape=ts.shape)


# --- the jobs (§7) --------------------------------------------------------------

def test_the_construction_calls_once_per_open_obligation_under_its_setup():
    """§7: `_run` calls `TAT.Proof_Obligation.construct` per open
    obligation in command order, with the slot and the setup — the task
    with its payload, the goal hint for termination, the whitelist, the goal
    kept as it stands —; a
    failing call ends the run, `failed_obligation` recorded, the earlier
    proofs dropped; all passing, the product holds one proof per
    obligation under its name, `failed_obligation` cleared and a `PASSED`
    check attached."""
    f, x = forest(SUM_UPTO)
    (p,) = x.sub_nodes
    evaluated(p, SEQUENTIAL)                                     # both obligations open
    job = p.job()
    assert isinstance(job, Define_Proof_Job)
    names, equations = ["sum_upto"], SUM_UPTO["equations"]
    assert p.construction_setup(PATTERN_COMPLETENESS) == (
        ("TAT.pattern_completeness", (names, equations)), None, [("pat_completeness", INTERPRETATIONS["pat_completeness"])],
        True)
    assert p.construction_setup(TERMINATION) == (
        ("TAT.termination", (names, equations)), (goal_hint(names), ["Wellfounded.accp _ _"]),
        [("relation", INTERPRETATIONS["relation"]), ("size_change", INTERPRETATIONS["size_change"])], True)
    calls = []
    outcomes = {PATTERN_COMPLETENESS: (["no completeness"], None),
                TERMINATION: ([], ("gave_up", ("refute", "The agent refuted it.")))}

    async def forked(name, args):
        calls.append((name, args))
        return outcomes[PATTERN_COMPLETENESS if args[0] == p.completeness_state.to_msgpack() else TERMINATION]
    job.forked = forked
    # the first call failing ends the run: one call, the obligation it was for recorded
    assert run(job._run()) == Failed("no completeness")
    assert [(name, args[0], args[1][0][0]) for name, args in calls] == [
        ("TAT.Proof_Obligation.construct", p.completeness_state.to_msgpack(), "TAT.pattern_completeness")]
    assert p.failed_obligation == PATTERN_COMPLETENESS and p.check_outcome() is None
    # the second the agent's give-up: two calls in command order, the failure of its reason's kind
    calls.clear()
    outcomes[PATTERN_COMPLETENESS] = ([], ("proof", ("by pat_completeness auto", 1, 2)))
    assert run(job._run()) == Failed("The agent refuted it.", "refute")
    assert [(name, args[0], args[1][0][0]) for name, args in calls] == [
        ("TAT.Proof_Obligation.construct", p.completeness_state.to_msgpack(), "TAT.pattern_completeness"),
        ("TAT.Proof_Obligation.construct", p.termination_state.to_msgpack(), "TAT.termination")]
    assert p.failed_obligation == TERMINATION and p.check_outcome() is None
    outcomes[TERMINATION] = ([], ("proof", ("by (relation \"measure id\") auto", 3, 5)))
    outcome = run(job._run())
    assert outcome == Succeeded({PATTERN_COMPLETENESS: {"text": "by pat_completeness auto", "thread_cpu": 1, "wall": 2},
                                 TERMINATION: {"text": "by (relation \"measure id\") auto", "thread_cpu": 3, "wall": 5}})
    assert p.failed_obligation is None and p.check_outcome() is PASSED
    # one obligation open: one call, the completeness proof not asked for
    calls.clear()
    evaluated(p, SEQUENTIAL, "pat_completeness auto", None)
    assert run(job._run()) == Succeeded({TERMINATION: {"text": "by (relation \"measure id\") auto", "thread_cpu": 3, "wall": 5}})
    assert [args[1][0][0] for _, args in calls] == ["TAT.termination"]
    # `Proof_Job`'s call carries the empty setup: no task, no hint, no whitelist, the goal's automatic Intro kept
    assert NO_SETUP == (None, None, [], False)


def test_the_check_replays_every_open_obligation_s_stored_proof_in_one_call(monkeypatch):
    f, x = forest(SUM_UPTO)
    (p,) = x.sub_nodes
    evaluated(p, SEQUENTIAL, "pat_completeness auto", None)
    calls = []

    async def call(conversation, name, args):
        calls.append((name, args))
    monkeypatch.setattr(isabelle_driver, "call", call)
    job = p.job()
    job.outcome = Succeeded({PATTERN_COMPLETENESS: {"text": "by pat_completeness auto", "thread_cpu": 1, "wall": 2},
                             TERMINATION: {"text": "by (relation \"measure id\") auto", "thread_cpu": 3, "wall": 5}})
    check = Define_Proof_Check(p, None)
    run(check._start())
    [(name, (goals, id))] = calls
    assert name == "TAT.Proof_Obligation.check" and id == check.id
    assert goals == [(p.termination_state.to_msgpack(), ("by (relation \"measure id\") auto", 3, 5))]
    evaluated(p, SEQUENTIAL)                                     # both open, the product lacking the completeness proof
    job.outcome = Succeeded({TERMINATION: {"text": "by (relation \"measure id\") auto", "thread_cpu": 3, "wall": 5}})
    calls.clear()
    run(Define_Proof_Check(p, None)._start())
    [(_, (goals, _))] = calls
    assert goals == [(p.completeness_state.to_msgpack(), None),
                     (p.termination_state.to_msgpack(), ("by (relation \"measure id\") auto", 3, 5))]
    assert isinstance(Define_Proof_Check.passed(p), Define_Proof_Check) and Define_Proof_Check.passed(p).outcome is PASSED


def test_check_answers_common_section_3_s_table_and_no_open_obligation():
    f, x = forest(SUM_UPTO)
    (p,) = x.sub_nodes
    job = p.job()
    evaluated(p, SEQUENTIAL, "pat_completeness auto", None)
    for outcome, check, expected in ((NOT_STARTED, None, True), (Failed("no"), None, True), (PROVED, PASSED, False),
                                     (PROVED, None, False), (PROVED, RUNNING, False), (PROVED, BAD, True)):
        with_proof(p, M.READY_CLEAN, outcome, check)
        assert job._check() is expected, (outcome, check)
        assert job.can_start() is expected
    with_proof(p, M.READY_CLEAN, NOT_STARTED)
    evaluated(p, *FUN)
    assert not job._check() and not job.can_start() and p.is_finished()


def test_the_jobs_sentences_are_section_7_s():
    """§7: the construction's failure header and notification name the
    failed obligation, the node by its id, the same sentence in both, the
    refutation sentence for the agent's refutation; without a recorded
    obligation they are `Proof_Job`'s plain forms, a refutation's too; the
    success notification and the titles are `Proof_Job`'s; the check's are
    `Proof_Check`'s."""
    f, x = forest(SUM_UPTO, EVEN_ODD, lemma("P"))
    p, q, l = x.sub_nodes
    job, qjob, ljob = p.job(), q.job(), l.job()
    assert (Define_Proof_Job.title(), Define_Proof_Job.title(plural=True)) == ("proof construction", "proof constructions")
    assert (Define_Proof_Check.title(), Define_Proof_Check.title(plural=True)) == ("proof check", "proof checks")
    assert job.finished_notification(PROVED) == "`definition_sum_upto` is proven."
    p.failed_obligation = TERMINATION
    assert job.failure_header(Failed("gave up")) == "Failed to prove that function `definition_sum_upto` terminates:"
    assert job.finished_notification(Failed("gave up")) == (
        "Failed to prove that function `definition_sum_upto` terminates:\n  gave up")
    p.failed_obligation = PATTERN_COMPLETENESS
    assert job.failure_header(Failed("")) == (
        "Failed to prove that `definition_sum_upto`'s definitional equations cover every argument:")
    q.failed_obligation = TERMINATION
    assert qjob.failure_header(Failed("")) == "Failed to prove that function `definition_even_and_odd` terminates:"
    q.failed_obligation = PATTERN_COMPLETENESS
    assert qjob.finished_notification(Failed("x")) == (
        "Failed to prove that `definition_even_and_odd`'s definitional equations cover every argument:\n  x")
    # a refutation reads the refutation sentence of the failed obligation; any other kind the assertion's
    p.failed_obligation = TERMINATION
    assert job.failure_header(Failed("gave up", "refute")) == "Function `definition_sum_upto` may not terminate:"
    assert job.finished_notification(Failed("gave up", "refute")) == (
        "Function `definition_sum_upto` may not terminate:\n  gave up")
    assert job.failure_header(Failed("gave up", "surrender")) == "Failed to prove that function `definition_sum_upto` terminates:"
    p.failed_obligation = PATTERN_COMPLETENESS
    assert job.failure_header(Failed("", "refute")) == (
        "`definition_sum_upto`'s definitional equations may not cover every argument:")
    assert job.finished_notification(Failed("", "refute")) == (          # an empty message: a period, nothing below
        "`definition_sum_upto`'s definitional equations may not cover every argument.")
    assert qjob.finished_notification(Failed("x", "resource_exhausted")) == (
        "Failed to prove that `definition_even_and_odd`'s definitional equations cover every argument:\n  x")
    p.failed_obligation = None
    assert job.failure_header(Failed("gave up")) == ljob.failure_header(Failed("gave up"))
    assert job.failure_header(Failed("gave up", "refute")) == "No proof was found:"      # no obligation recorded
    assert job.finished_notification(Failed("gave up")) == ljob.finished_notification(Failed("gave up")).replace(
        "lemma_P", "definition_sum_upto")
    assert job.finished_notification(PROVED) == ljob.finished_notification(PROVED).replace("lemma_P", "definition_sum_upto")
    assert Define_Proof_Check.failure_header(BAD) == Proof_Check.failure_header(BAD)
    # §8's three failure blocks whole, the header over AoA's message; `bad proof` the check's
    [_, _, _, _, failed, refuted, bad] = fenced_blocks(DD, "8.")
    me = stand_ins.agent(f.conversation)
    evaluated(p, SEQUENTIAL, "pat_completeness auto", None)
    p.failed_obligation = TERMINATION
    with_proof(p, M.READY_CLEAN, Failed(failed[-1].strip()))
    assert f.render(p, M.RECALL, me).splitlines() == failed
    with_proof(p, M.READY_CLEAN, Failed(refuted[-1].strip(), "refute"))
    assert f.render(p, M.RECALL, me).splitlines() == refuted
    with_proof(p, M.READY_CLEAN, PROVED, BAD)
    assert f.render(p, M.RECALL, me).splitlines() == bad


def test_a_construction_failure_block_stands_only_while_the_obligation_it_names_is_open():
    """§7: the failure block is printed while the failed obligation is still
    open — or, for a carried failure naming none, while any is —; once a
    later evaluation recorded a form under which it is not, the header is
    None and nothing is printed; a node without a recorded form keeps
    `Proof_Job`'s header."""
    f, x = forest(SUM_UPTO)
    (p,) = x.sub_nodes
    me = stand_ins.agent(f.conversation)
    failure = Failed("Sledgehammer timed out on every prover.")
    focus = M.Relative_Focus(frozenset({p}), 0)
    assert p.job().failure_header(failure) == "No proof was found:"                # not evaluated yet: form None
    # termination open and named: the block
    evaluated(p, SEQUENTIAL, "pat_completeness auto", None)
    p.failed_obligation = TERMINATION
    with_proof(p, M.READY_CLEAN, failure)
    assert f.render(p, focus, me).splitlines() == [
        "- definition_sum_upto (unverified definition, failed to prove)",
        "  The definition is unverified until termination is proven.",
        "  Failed to prove that function `definition_sum_upto` terminates:", "    Sledgehammer timed out on every prover."]
    # a rerun closed termination by itself: nothing open, the line `valid definition`, no block
    evaluated(p, *FUN)
    with_proof(p, M.READY_CLEAN, failure)
    assert p.job().failure_header(failure) is None
    assert f.render(p, focus, me).splitlines() == ["- definition_sum_upto (valid definition)"]
    # under plain `function`, termination closed and pattern completeness still open: the block names a closed one
    evaluated(p, "function", None, "lexicographic_order")
    with_proof(p, M.READY_CLEAN, failure)
    assert p.job().failure_header(failure) is None
    assert f.render(p, focus, me).splitlines() == [
        "- definition_sum_upto (unverified definition, failed to prove)",
        "  The definition is unverified until pattern completeness is proven."]
    # a failure naming no obligation, a node stored before the carry: `Proof_Job`'s header while any is open, none when none is
    p.failed_obligation = None
    assert p.job().failure_header(failure) == "No proof was found:"
    evaluated(p, *FUN)
    with_proof(p, M.READY_CLEAN, failure)
    assert p.job().failure_header(failure) is None


def test_the_texts_the_proof_agent_reads_are_section_7_s():
    """§7's blocks: the termination task's text and the pattern completeness
    task's, through the registered tasks for the major agent, nothing for a
    worker and nothing in the system prompt; the goal hint; the three
    interpretations, by tactic."""
    [termination, completeness, hint, interpretations, _] = fenced_blocks(DD, "7.")
    names, equations = ["sum_upto"], SUM_UPTO["equations"]
    termination_task, completeness_task = TASK_REGISTRY["TAT.termination"], TASK_REGISTRY["TAT.pattern_completeness"]
    assert termination_task((names, equations)).task_initial(Role_Major(), True) == "\n".join(termination) + "\n\n"
    assert completeness_task((names, equations)).task_initial(Role_Major(), False) == "\n".join(completeness) + "\n\n"
    worker = Role_Worker(target=None)   # type: ignore[arg-type]
    for task in (termination_task, completeness_task):
        assert task((names, equations)).task_initial(worker, True) == task((names, equations)).task_initial(worker, False) == ""
        assert task((names, equations)).task_system(Role_Major()) == task((names, equations)).task_system(worker) == ""
    assert task_text(TERMINATION, names, equations) == "\n".join(termination) + "\n\n"
    assert task_text(PATTERN_COMPLETENESS, names, equations) == "\n".join(completeness) + "\n\n"
    assert termination_task((["even", "odd"], [])).task_initial(Role_Major(), True).splitlines()[0] == (
        "Your proof goal (given in `proof.yaml`) is to show the functions `even` and `odd` terminate")
    assert assertion(TERMINATION, ["even", "odd"]) == "the functions `even` and `odd` terminate"
    assert assertion(TERMINATION, ["f", "g", "h"]) == "the functions `f`, `g` and `h` terminate"
    assert [goal_hint(names)] == hint
    assert goal_hint(["even", "odd"]).startswith("The goal asserts the termination of `even` and `odd`.")
    assert {line.split(" ", 1)[0]: line.split(" ", 1)[1].strip() for line in interpretations} == INTERPRETATIONS


def test_the_theory_tat_std_registers_the_two_tasks_under_the_names_the_python_classes_bear():
    """§7: `TAT_Std.thy` registers, under this module's package, exactly the
    names `TAT.<obligation>`, each a key of AoA's registry."""
    thy = TAT_STD.read_text()
    registered = re.findall(r'register_task \{python_packages = \["([^"]+)"\]\}\s*\{name = "([^"]+)"\}', thy)
    assert {name for _, name in registered} == {f"TAT.{o}" for o in OBLIGATIONS} and len(registered) == len(OBLIGATIONS)
    assert all(name in TASK_REGISTRY for _, name in registered)
    assert {package for package, _ in registered} == {Termination_Task.__module__}


# --- the mark and the owing line (§7) -------------------------------------------

def test_the_mark_reads_one_of_eleven_ways():
    """§7's mark, state by state, with termination open: `valid definition`
    alone when the node owes nothing, `unverified definition` with the proof's
    word while it does; the eleven, and no other, are the document's block;
    with no open obligation the node owes nothing under `ready`."""
    [_, _, _, _, block] = fenced_blocks(DD, "7.")
    f, x = forest(SUM_UPTO)
    (p,) = x.sub_nodes
    assert p.mark(M.BRIEFING, 0) == "not evaluated, proof not started"
    evaluated(p, SEQUENTIAL, "pat_completeness auto", None)
    proof = [(NOT_STARTED, None, "proof not started"), (RUNNING, None, "proving"), (Failed("no"), None, "failed to prove"),
             (PROVED, None, "unchecked proof"), (PROVED, RUNNING, "proof checking"), (PROVED, PASSED, None),
             (PROVED, BAD, "bad proof")]
    marks = set()
    for outcome, check, word in proof:
        with_proof(p, M.READY_CLEAN, outcome, check)
        expected = "valid definition" if word is None else f"unverified definition, {word}"
        assert p.mark(M.BRIEFING, 0) == expected, (outcome, check)
        assert (p.owing_line() is None) == (word is None)
        marks.add(f"({expected})")
        with_proof(p, INVALID, outcome, check)
        assert p.mark(M.BRIEFING, 0) == "invalid definition" and p.owing_line() is None, (outcome, check)
        marks.add("(invalid definition)")
        if outcome is not RUNNING and check is None:
            with_proof(p, M.NOT_EVALUATED, outcome, check)
            expected = "not evaluated" if outcome is PROVED else f"not evaluated, {word}"
            assert p.mark(M.BRIEFING, 0) == expected and p.owing_line() is None, (outcome, check)
            marks.add(f"({expected})")
    assert len(marks) == 11 and marks == set(re.findall(r"\([^)]*\)", "\n".join(block)))
    evaluated(p, *FUN)
    for outcome, check in ((NOT_STARTED, None), (Failed("no"), None), (PROVED, BAD)):
        with_proof(p, M.READY_CLEAN, outcome, check)
        assert p.mark(M.BRIEFING, 0) == "valid definition" and p.owing_line() is None, (outcome, check)


def test_the_owing_line_names_the_open_obligations_in_command_order():
    f, x = forest(SUM_UPTO)
    (p,) = x.sub_nodes
    for cm, tm, line in (("pat_completeness auto", None, "The definition is unverified until termination is proven."),
                         (None, "lexicographic_order", "The definition is unverified until pattern completeness is proven."),
                         (None, None, "The definition is unverified until pattern completeness and termination are proven.")):
        evaluated(p, SEQUENTIAL, cm, tm)
        with_proof(p, M.READY_CLEAN, NOT_STARTED)
        assert p.owing_line() == line, (cm, tm)
        with_proof(p, M.READY_CLEAN, PROVED, PASSED)
        assert p.owing_line() is None
    assert [define.task_text(TERMINATION, ["sum_upto"], SUM_UPTO["equations"]).count("\n")] == [4]


# --- what it prints (§8) -----------------------------------------------------

def test_print_fields_writes_the_definition_and_english_by_depth():
    f, x = forest(SUM_UPTO, FIB, EVEN_ODD | {"constants": [
        {"name": "even", "type": "nat ⇒ bool", "syntax": {"form": "infixl", "symbol": "⊕", "priority": 65}}, {"name": "odd"}]})
    p, fib, even_odd = x.sub_nodes
    [layout, quickview, valid, invalid, _, _, _] = fenced_blocks(DD, "8.")
    assert fields(p, M.RECALL, 0) == layout
    assert fields(p, M.RECALL, 1) == fields(p, M.RECALL, 2) == layout[:-1] and fields(p, M.RECALL, 3) == []
    assert fields(p, M.OUT_FOCUS, 0) == [] and fields(p, M.Relative_Focus(frozenset({p}), 0), 0) == []
    assert fields(even_odd, M.RECALL, 1) == ['  even :: nat ⇒ bool (infixl "⊕" 65) and odd', "  even 0 = True", "  even (Suc n) = odd n",
                                            "  odd 0 = False", "  odd (Suc n) = even n"]
    for keywords in (None, frozenset(), frozenset({"sum_upto", "nat", "Suc"})):     # the stored text, whatever the theory recorded
        x.keywords = keywords
        assert fields(p, M.RECALL, 1) == layout[:-1]
    me = stand_ins.agent(f.conversation)
    evaluated(p, SEQUENTIAL, "pat_completeness auto", None)
    assert f.render(p, M.Relative_Focus(frozenset({p}), 0), me).splitlines() == quickview      # a focus: the owing line alone
    evaluated(fib, *FUN)
    assert f.render(fib, M.RECALL, me).splitlines() == valid
    for node in (p, fib):
        evaluated(node, None, status=M.NOT_EVALUATED)                        # back to nodes no walk reached
    inv(f)
    f, x = forest(definition(equations=("sum_upto i N = (if N < i then 0 else i + suma (Suc i) N)",)))   # §8's refused definition, alone
    (q,) = x.sub_nodes
    q._status = M.CannotEvaluate((IsaTerm.from_agent("\n".join(line.strip() for line in invalid[5:])),))     # one message, three lines
    assert f.render(q, M.RECALL, stand_ins.agent(f.conversation)).splitlines() == invalid


# --- emission (§5) ------------------------------------------------------------

def test_the_emitted_text_is_section_5_s():
    [one, two, three] = fenced_blocks(DD, "5.")
    f, x = forest(TWICE, FIB, SUM_UPTO)
    twice, fib, sum_upto = x.sub_nodes
    x.keywords = frozenset()
    evaluated(twice, "definition")
    evaluated(fib, *FUN)                                             # both goals closed by `fun`'s methods: written `fun`
    evaluated(sum_upto, SEQUENTIAL, "pat_completeness auto", None)
    assert emitted(twice) == one and emitted(fib) == two
    assert emitted(sum_upto) == [*three[:5], "  sorry", *three[6:]]                       # no proof: `sorry`
    assert three[1].startswith("function (sequential, no_partials) sum_upto")             # the command as the evaluation ran it
    with_proof(sum_upto, M.READY_CLEAN, PROVED, PASSED)
    assert emitted(sum_upto) == three
    for outcome, check in ((PROVED, BAD), (PROVED, None), (PROVED, RUNNING), (Failed("no"), None)):
        with_proof(sum_upto, M.READY_CLEAN, outcome, check)
        assert emitted(sum_upto)[5] == "  sorry", (outcome, check)
    with_proof(sum_upto, M.READY_CLEAN, PROVED, PASSED)
    evaluated(sum_upto, SEQUENTIAL, None, None)                                          # both open: both `by aoa`, or neither
    assert emitted(sum_upto)[3:6] == ["  by aoa", "termination", "  by aoa"]
    with_proof(sum_upto, M.READY_CLEAN, PROVED, BAD)
    assert emitted(sum_upto)[3:6] == ["  sorry", "termination", "  sorry"]
    evaluated(sum_upto, SEQUENTIAL, None, "lexicographic_order")
    assert emitted(sum_upto)[3:6] == ["  sorry", "termination", "  by lexicographic_order"]
    evaluated(sum_upto, "function", "pat_completeness auto", "lexicographic_order")     # plain `function`, both closed: never `fun`
    assert emitted(sum_upto)[1:6] == [three[1].replace("function (sequential, no_partials)", "function"), three[2],
                                      "  by pat_completeness auto", "termination", "  by lexicographic_order"]
    # `auto_reduction` the other way round: no `declare` after a `definition`, `simp del` after a `fun`
    twice.auto_reduction, fib.auto_reduction = False, False
    assert emitted(twice) == one[:3] and emitted(fib) == [*two, "declare fib.simps [simp del]"]
    # keywords quoted; a constant without a type; several constants with a syntax
    x.keywords = frozenset({"twice", "nat", "twice_def"})
    twice.auto_reduction = True
    assert emitted(twice)[1:] == ['definition "twice" :: "nat ⇒ nat" where', '  "twice n = n + n"', 'declare "twice_def" [simp]']
    x.keywords = frozenset()
    u, eo = insert(f, x, 3, [definition("u", ("u n = n",), "Untyped", type=None, auto_reduction=True),
                             EVEN_ODD | {"constants": [{"name": "even", "type": "nat ⇒ bool",
                                                        "syntax": {"form": "infixl", "symbol": "⊕", "priority": 65}}, {"name": "odd"}]}])
    evaluated(u, "definition")
    evaluated(eo, *FUN)
    assert emitted(u) == ["text ‹Definition ‹u›. Untyped.›", "definition u where", '  "u n = n"', "declare u_def [simp]"]
    assert emitted(eo) == ["text ‹Definition ‹even› and ‹odd›. Parity of a natural number, by mutual recursion.›",
                           'fun even :: "nat ⇒ bool" (infixl "⊕" 65) and odd where', '  "even 0 = True"', '| "even (Suc n) = odd n"',
                           '| "odd 0 = False"', '| "odd (Suc n) = even n"', "declare even.simps odd.simps [simp del]"]
    # prose through `latex_of`, a formal comment in a constant's type and in an equation translated (COMPILATION.md §3);
    # `recall` as written
    (c,) = insert(f, x, 5, [definition("c", ("c n = n ― ‹x₁›",), "Sums of n²", type="nat ⇒ nat ― ‹x₁›", auto_reduction=True)])
    evaluated(c, "definition")
    assert emitted(c)[:3] == ["text ‹Definition ‹c›. Sums of ‹n²›.›", 'definition c :: "nat ⇒ nat ― ‹‹x₁››" where',
                              '  "c n = n ― ‹‹x₁››"']
    assert fields(c, M.RECALL, 1) == ["  c :: nat ⇒ nat ― ‹x₁›", "  c n = n ― ‹x₁›"]


def test_the_two_spellings_are_kept_apart():
    f, x = forest(definition("f", ("f n = n ⊕ ε",), "Greek", type="'α ⇒ 'α", auto_reduction=True))
    (p,) = x.sub_nodes
    x.keywords = frozenset()
    assert p.message() == ([("f", "'\\<alpha> \\<Rightarrow> '\\<alpha>", None)], ["f n = n \\<oplus> \\<epsilon>"], True, None)
    rows = {}
    p.to_store(type("Rows", (), {"put": lambda self, k, v: rows.__setitem__(k, v)})())
    assert rows["constants"] == [{"name": "f", "type": "'α ⇒ 'α"}] and rows["equations"] == ["f n = n ⊕ ε"]
    assert fields(p, M.RECALL, 1) == ["  f :: 'α ⇒ 'α", "  f n = n ⊕ ε"]
    assert p.construction_setup(TERMINATION)[0] == ("TAT.termination", (["f"], ["f n = n ⊕ ε"]))    # the payload in `unicode`
    evaluated(p, "definition")
    assert emitted(p)[1:3] == ["definition f :: \"'α ⇒ 'α\" where", '  "f n = n ⊕ ε"']


# --- the evaluation, in the plugin's run of the harness (§5, §6, §8) --------

def over_the_wire(*definitions):
    return ts.session("TAT_Suite", ts.theory("TAT_Std_A") | {"children": list(definitions)})


@pytest.mark.isabelle(deadline=300)
async def test_the_three_forms_are_defined_and_the_open_goals_held(std_conversation, std_harness, tmp_path):
    """§6 through `TAT.Define.evaluate`: §5's `twice`, `fib` and `sum_upto`, §2's
    `even` and `odd`, a `half` with a case left out, which `sequential`
    completes, so that `fun`'s two methods close both goals, a `step` by
    a non-constructor pattern and a `pred_pos` by one conditional equation,
    which `function (sequential, no_partials)` refuses and plain `function`
    takes with its completeness goal open — each with its form and its
    methods recorded and its open goal, and no other, in its slot; a
    theorem using every constant; `recall` as §8 shows; the theory rendered
    as §5 shows, with `sorry` for the open obligations, and read back whole
    by Isabelle.  Last, the callback alone: `[[], [form, method, method]]`
    on the wire; given the recorded form it runs that command alone —
    `step` under `function (sequential, no_partials)` is refused, under
    `None` decided as `function` —, and a refused rerun empties both
    slots."""
    forest = std_conversation.forest
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [over_the_wire(
                TWICE, FIB, SUM_UPTO, EVEN_ODD,
                definition("half", ("half 0 = 0", "half (Suc (Suc n)) = Suc (half n)"), "Half, undefined on one", type="nat ⇒ nat", auto_reduction=True),
                definition("step", ("step (n + 1) = step n", "step 0 = 0"), "Down to zero, by a non-constructor pattern",
                           type="nat ⇒ nat", auto_reduction=True),
                definition("pred_pos", ("0 < n ⟹ pred_pos n = n - 1",), "The predecessor, on the positive naturals",
                           type="nat ⇒ nat", auto_reduction=True),
                lemma("uses_the_definitions", english="Every definition above parses", premises=(),
                      for_any=({"name": "n", "type": "nat"},),
                      conclusion="twice n = fib n + sum_upto n n + half n + step n + pred_pos n ∧ (even n ∨ odd n)"))]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 0, text
        (s,) = forest.sub_nodes
        (a,) = s.sub_nodes
        twice, fib, sum_upto, even_odd, half, step, pred_pos, uses = a.sub_nodes
        defined = (twice, fib, sum_upto, even_odd, half, step, pred_pos)
        for node in (*defined, uses):
            assert isinstance(node._status, M.Ready) and node._status.messages == (), (node.name, node._status)
            assert await node.resulting_state().is_initialized()
        assert [(n.form, n.completeness_method, n.termination_method) for n in defined] == [
            ("definition", None, None), FUN, (SEQUENTIAL, "pat_completeness auto", None), FUN, FUN,
            ("function", None, "lexicographic_order"), ("function", None, "lexicographic_order")]
        assert [(await n.completeness_state.is_initialized(), await n.termination_state.is_initialized()) for n in defined] == [
            (False, False), (False, False), (False, True), (False, False), (False, False), (True, False), (True, False)]
        assert [n.mark(M.BRIEFING, 0) for n in (twice, fib, sum_upto, half, step, pred_pos)] == [
            "valid definition", "valid definition", "unverified definition, proof not started", "valid definition",
            "unverified definition, proof not started", "unverified definition, proof not started"]
        assert sum_upto.owing_line() == "The definition is unverified until termination is proven."
        assert step.owing_line() == pred_pos.owing_line() == "The definition is unverified until pattern completeness is proven."
        assert fib.is_finished() and twice.is_finished() and not sum_upto.is_finished() and half.is_finished()
        assert [n.message()[3] for n in (twice, fib, sum_upto, step)] == ["definition", SEQUENTIAL, SEQUENTIAL, "function"]
        [layout, _, valid, _, _, _, _] = fenced_blocks(DD, "8.")
        recalled = await session.call_tool("recall", {"node_id": "definition_sum_upto"})
        assert not recalled.isError and text_of(recalled).splitlines() == [
            "- definition_sum_upto (unverified definition, proof not started)", *("  " + line for line in layout),
            "  The definition is unverified until termination is proven."], text_of(recalled)
        recalled = await session.call_tool("recall", {"node_id": "definition_fib"})
        assert not recalled.isError and text_of(recalled).splitlines() == valid, text_of(recalled)
    rendered = C.render(forest)
    file = rendered.files[C.Path("TAT_Suite/TAT_Std_A.thy")]
    assert file.startswith('theory "TAT_Std_A"\n  imports "Main" "TAT_Std.TAT_Std"\nbegin\n') and file.endswith("end\n")
    [one, two, three] = fenced_blocks(DD, "5.")
    for block in (one, two, [*three[:5], "  sorry", *three[6:]],
                  ["text ‹Definition ‹even› and ‹odd›. Parity of a natural number, by mutual recursion.›",
                   'fun even :: "nat ⇒ bool" and odd :: "nat ⇒ bool" where', '  "even 0 = True"', '| "even (Suc n) = odd n"',
                   '| "odd 0 = False"', '| "odd (Suc n) = even n"', "declare even.simps odd.simps [simp del]"],
                  ["text ‹Definition ‹half›. Half, undefined on one.›", 'fun half :: "nat ⇒ nat" where', '  "half 0 = 0"',
                   '| "half (Suc (Suc n)) = Suc (half n)"'],
                  ["text ‹Definition ‹step›. Down to zero, by a non-constructor pattern.›", 'function step :: "nat ⇒ nat" where',
                   '  "step (n + 1) = step n"', '| "step 0 = 0"', "  sorry", "termination", "  by lexicographic_order"],
                  ["text ‹Definition ‹pred_pos›. The predecessor, on the positive naturals.›", 'function pred_pos :: "nat ⇒ nat" where',
                   '  "0 < n ⟹ pred_pos n = n - 1"', "  sorry", "termination", "  by lexicographic_order"]):
        assert "".join(ascii_of_unicode(line) + "\n" for line in block) in file, file
    await read_back(std_harness, file, tmp_path)
    messages, what = await isabelle_driver.call(
        forest.conversation, "TAT.Define.evaluate",
        (fib.state.to_msgpack(), fib.completeness_state.to_msgpack(), fib.termination_state.to_msgpack(),
         fib.resulting_state().to_msgpack(), fib.message()))
    assert (messages, what) == ([], list(FUN))
    recorded = step.message()
    for form, expected in ((None, ([], ["function", None, "lexicographic_order"])),
                           ("function", ([], ["function", None, "lexicographic_order"])),
                           (SEQUENTIAL, (["Malformed definition:\nNon-constructor pattern not allowed in sequential mode.\n"
                                          "⋀n. step (n + 1) = step n"], None))):
        messages, what = await isabelle_driver.call(
            forest.conversation, "TAT.Define.evaluate",
            (step.state.to_msgpack(), step.completeness_state.to_msgpack(), step.termination_state.to_msgpack(),
             step.resulting_state().to_msgpack(), (*recorded[:3], form)))
        assert ([IsaTerm.from_isabelle(m).unicode for m in messages], what) == expected, form
        assert await step.completeness_state.is_initialized() == (not messages)      # the open goal held, or both emptied
        assert not await step.termination_state.is_initialized()


@pytest.mark.isabelle(deadline=300)
async def test_a_refused_definition_is_an_obstacle_with_both_slots_empty(std_conversation):
    """§6, §8: a `sum_upto` whose right side names a constant that does not
    exist is an obstacle with Isabelle's message — `function (sequential,
    no_partials)` and plain `function` refusing it alike —, both goal slots empty, shown under
    `recall` as §8's example; a `g` whose right side mentions an unknown
    constant likewise; neither theory is written."""
    forest = std_conversation.forest
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [ts.session("TAT_Suite",
                                      ts.theory("TAT_Std_B") | {"children": [definition(equations=("sum_upto i N = (if N < i then 0 else i + suma (Suc i) N)",))]},
                                      ts.theory("TAT_Std_C") | {"children": [definition("g", ("g n = h n",), "Unknown", type="nat ⇒ nat", auto_reduction=True)]})]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 2, text
        (s,) = forest.sub_nodes
        b, c = s.sub_nodes
        (bad,) = b.sub_nodes
        (g,) = c.sub_nodes
        [_, _, _, invalid, _, _, _] = fenced_blocks(DD, "8.")
        for node in (bad, g):
            assert isinstance(node._status, M.CannotEvaluate), node._status
            assert not await node.completeness_state.is_initialized() and not await node.termination_state.is_initialized()
            assert (node.form, node.completeness_method, node.termination_method) == (None, None, None)
        assert [m.unicode for m in bad._status.messages] == ["\n".join(line.strip() for line in invalid[5:])]   # one message, three lines
        recalled = await session.call_tool("recall", {"node_id": "definition_sum_upto"})
        assert not recalled.isError and text_of(recalled).splitlines() == invalid, text_of(recalled)
        assert g._status.messages[0].unicode.startswith("Extra variables on rhs"), g._status.messages
    rendered = C.render(forest)
    assert not any(C.Path(f"TAT_Suite/TAT_Std_{t}.thy") in rendered.files for t in "BC")


@pytest.mark.isabelle(deadline=300)
async def test_a_template_with_a_malformed_symbol_is_refused_at_evaluation(std_conversation):
    """COMMON.md §4: a constant's template holding a malformed symbol, which
    a build's token check refuses, is an obstacle at evaluation with
    Isabelle's own message (`TAT_Mixfix.read_text`); a well-formed one is
    defined."""
    forest = std_conversation.forest
    syntax = {"form": "mixfix", "argument_priorities": [10], "priority": 10}
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [ts.session("TAT_Suite", ts.theory("TAT_Std_B") | {"children": [
                definition("bad", ("bad n = n",), "Bad", type=None, auto_reduction=True,
                           constants=[{"name": "bad", "type": "nat ⇒ nat", "syntax": syntax | {"template": "\\<foo _"}}]),
                definition("good", ("good n = n",), "Good", type=None, auto_reduction=True,
                           constants=[{"name": "good", "type": "nat ⇒ nat", "syntax": syntax | {"template": "⊙ _"}}])]})]})
        assert not result.isError, text_of(result)
    (s,) = forest.sub_nodes
    (b,) = s.sub_nodes
    bad, good = b.sub_nodes
    assert isinstance(bad._status, M.CannotEvaluate), bad._status
    assert [m.unicode for m in bad._status.messages] == ['Malformed symbolic character: "\\<foo"'], bad._status.messages
    assert not isinstance(good._status, M.CannotEvaluate), good._status


# --- the construction, end to end, the proof agent a scripted one (§7) -------

@pytest.mark.isabelle(deadline=900)
async def test_a_termination_proof_is_constructed_by_a_scripted_agent_checked_and_emitted(std_conversation):
    """§7 through `TAT.Proof_Obligation.construct` and `check`, the proof
    agent AoA's test driver — test/TAT_Define_Helper.thy declares it for a
    theory that imports it, and the case registered under its name here
    drives the proof tree by hand: it sees the call's task, `TAT.termination`
    with the constants' names and the equations, the major's initial message
    opening with §7's text, the whitelist `relation` and `size_change`, the
    goal hint under the goal, and proves termination with `Tactic` `relation`.
    `construct` on `sum_upto` settles `SUCCEEDED` with the proof under
    `termination`, the check `PASSED`, the line `valid definition`, the file
    `termination by aoa`; invalidated and evaluated with checks, the proof
    is replayed and passes again."""
    from IsaMini.AoA import test as aoa_test
    from IsaMini.AoA.helper import MyIO
    from IsaMini.AoA.model import GoalNode, Obvious, Role_Major, Tactic
    import test_model as tm
    from harness import until
    seen: dict = {}

    async def script(root, file):
        session = root.session
        seen["task"] = (type(session.task), session.task.names, session.task.equations)
        seen["tactics"] = [entry.name.unicode for entry in session.runtime.tactics.values()]
        seen["initial"] = await session.task.initial_prompt(Role_Major(), session, True)
        shown = io.StringIO()
        root.print(0, MyIO(shown))
        seen["shown"] = shown.getvalue()
        session.age += 1

        def tree(node):
            yield node
            for child in getattr(node, "sub_nodes", []):
                yield from tree(child)

        def picture(label):
            out = io.StringIO()
            root.print(0, MyIO(out))
            seen[label] = out.getvalue()
        # the goal is kept as it stands (§7): no automatic `Intro` opens its `∀`, and `relation` applies at step 1
        outcome = await root.fill("1", [Tactic.gen_single({"thought": "the gap to N shrinks", "tactic": "relation",
                                                           "arguments": '"measure (λ(i, N). N + 1 - i)"'})])
        seen["relation"] = (len(outcome.committed), str(outcome.failure))
        picture("after relation")
        session.age += 1
        tactic = next((n for n in tree(root) if isinstance(n, Tactic)), None)
        seen["subgoals"] = []
        for subgoal in [c for c in getattr(tactic, "sub_nodes", []) if isinstance(c, GoalNode)]:
            # the next step of the derived subgoal, after an automatic `Intro` when AoA made one
            step = f"{subgoal.id}.{len(subgoal.sub_nodes) + 1}"
            outcome = await root.fill(step, [Obvious.gen_single({"facts": []})])
            seen["subgoals"].append((step, len(outcome.committed), str(outcome.failure)))
        picture("after the subgoals")
        seen["unfinished"] = aoa_test._count_unfinished(root, file)

    class Scripted(aoa_test.ModelTestCase):           # no golden: nothing compared, nothing written
        def correct_yaml_path(self):
            return None

        def write_expected_yaml(self, yaml):
            pass

    aoa_test.TESTS["tat_define_termination"] = Scripted("tat_define_termination", "", 0, script, isolated_db=True)
    forest = std_conversation.forest
    try:
        with aoa_test._isolated_semantic_db_process():      # the whitelist's interpretations go into a throwaway DB
            async with std_conversation.client() as session:
                result = await session.call_tool("edit", {
                    "action": "append", "target_id": "Sessions", "evaluate": True,
                    "constructs": [ts.session("TAT_Suite", ts.theory("TAT_Std_A", "Main", "Theory_Agent_over_Trees.TAT_Define_Helper")
                                              | {"children": [SUM_UPTO]})]})
                assert not result.isError, text_of(result)
                (s,) = forest.sub_nodes
                (x,) = s.sub_nodes
                (p,) = x.sub_nodes
                assert p.open_obligations() == (TERMINATION,) and p.mark(M.BRIEFING, 0) == "unverified definition, proof not started"
                result = await session.call_tool("construct", {"node_ids": ["definition_sum_upto"]})
                assert not result.isError and "Started the proof construction on `definition_sum_upto`" in text_of(result)
                job = p.job()
                assert job.outcome is RUNNING and p.mark(M.BRIEFING, 0) == "unverified definition, proving"
                await until(lambda: job.outcome is not RUNNING, "the proof construction's outcome", 600.0)
                assert isinstance(job.outcome, Succeeded), (job.outcome, seen)
                # what the scripted agent saw
                assert seen["task"] == (Termination_Task, ["sum_upto"], SUM_UPTO["equations"])
                assert seen["tactics"] == ["relation", "size_change"]
                assert seen["initial"].startswith(task_text(TERMINATION, ["sum_upto"], SUM_UPTO["equations"]))
                assert goal_hint(["sum_upto"]) in seen["shown"], seen["shown"]          # the hint, a `notice:` under the goal
                assert "operation: Intro" not in seen["shown"], seen["shown"]      # the goal kept as it stands (§7)
                assert seen["relation"] == (1, "None") and "derived subgoals:" in seen["after relation"]
                assert seen["subgoals"] == [("1.1.1", 1, "None"), ("1.2.2", 1, "None")] and seen["unfinished"] == 0
                product = job.outcome.product
                assert set(product) == {TERMINATION} and product[TERMINATION]["text"]
                assert all(isinstance(product[TERMINATION][k], int) for k in ("thread_cpu", "wall"))
                assert p.check_outcome() is PASSED and p.mark(M.BRIEFING, 0) == "valid definition" and p.owing_line() is None
                assert p.failed_obligation is None and p.is_finished()
                result = await session.call_tool("check_construct", {})
                assert "`definition_sum_upto` is proven." in text_of(result), text_of(result)
                assert emitted(p)[3:6] == ["  by pat_completeness auto", "termination", "  by aoa"]
                # invalidated and evaluated with checks: the stored proof replayed on the new termination goal
                await tm._invalidate(p)
                assert p.check_outcome() is None and p.mark(M.BRIEFING, 0) == "not evaluated"
                assert not await p.termination_state.is_initialized()
                result = await session.call_tool("evaluate_to", {"node_id": "theory_TAT_Std_A", "checks": "blocking"})
                assert not result.isError, text_of(result)
                assert p.check_outcome() is PASSED and p.mark(M.BRIEFING, 0) == "valid definition"
                # a proof that no longer proves the goal fails its check with the empty message, the agent sent to `construct`
                job.outcome = Succeeded({TERMINATION: {**product[TERMINATION], "text": "(rule refl)"}})
                await tm._invalidate(p)
                result = await session.call_tool("evaluate_to", {"node_id": "theory_TAT_Std_A", "checks": "blocking"})
                assert p.check_outcome() == Failed("") and p.mark(M.BRIEFING, 0) == "unverified definition, bad proof"
                assert "The proof of `definition_sum_upto` no longer holds. Call `construct` to prove it again." in text_of(result)
    finally:
        aoa_test.TESTS.pop("tat_define_termination", None)


@pytest.mark.isabelle(deadline=900)
async def test_the_agents_give_up_settles_the_construction_failed_of_its_reasons_kind(std_conversation):
    """§7 through `TAT.Proof_Obligation.construct`, the proof agent AoA's
    test driver and a case that proves nothing: AoA gives up — the reason
    `resource_exhausted`, no detail — and the construction settles `FAILED`
    of that kind, AoA's banner alone the message, stored beside it; the
    notification and the failure block read `Failed to prove that function
    `definition_sum_from` terminates:` over the banner.  The function is
    `sum_upto` under another name: AoA's proof store, one per run of the
    suite, holds the proof the case before this one found for `sum_upto`'s
    goal, and would answer it here before any agent runs."""
    from IsaMini.AoA import test as aoa_test
    from harness import until
    seen: dict = {}
    sum_from = definition("sum_from", ("sum_from i N = (if N < i then 0 else i + sum_from (Suc i) N)",))

    async def script(root, file):
        seen["task"] = type(root.session.task)           # the agent was reached, and proved nothing

    class Scripted(aoa_test.ModelTestCase):           # no golden: nothing compared, nothing written
        def correct_yaml_path(self):
            return None

        def write_expected_yaml(self, yaml):
            pass

    aoa_test.TESTS["tat_define_termination"] = Scripted("tat_define_termination", "", 0, script, isolated_db=True)
    forest = std_conversation.forest
    banner = ("The proof agent exhausted its budget before finding a proof. "
              "This usually means the goal is too hard for the agent to solve.")
    try:
        with aoa_test._isolated_semantic_db_process():
            async with std_conversation.client() as session:
                result = await session.call_tool("edit", {
                    "action": "append", "target_id": "Sessions", "evaluate": True,
                    "constructs": [ts.session("TAT_Suite", ts.theory("TAT_Std_A", "Main", "Theory_Agent_over_Trees.TAT_Define_Helper")
                                              | {"children": [sum_from]})]})
                assert not result.isError, text_of(result)
                (s,) = forest.sub_nodes
                (x,) = s.sub_nodes
                (p,) = x.sub_nodes
                result = await session.call_tool("construct", {"node_ids": ["definition_sum_from"]})
                assert not result.isError, text_of(result)
                job = p.job()
                await until(lambda: job.outcome is not RUNNING, "the proof construction's outcome", 600.0)
                assert seen.get("task") is Termination_Task, (seen, job.outcome)
                assert job.outcome == Failed(banner, "resource_exhausted"), job.outcome
                assert p.failed_obligation == TERMINATION and p.check_outcome() is None
                assert p.mark(M.BRIEFING, 0) == "unverified definition, failed to prove"
                assert forest.store.get(p.identity, "job") == ["FAILED", banner, "resource_exhausted"]
                result = await session.call_tool("check_construct", {})
                assert f"Failed to prove that function `definition_sum_from` terminates:\n  {banner}" in text_of(result), text_of(result)
                result = await session.call_tool("recall", {"node_id": "definition_sum_from"})
                assert [line for line in text_of(result).splitlines() if "Failed to prove" in line or banner in line] == [
                    "  Failed to prove that function `definition_sum_from` terminates:", f"    {banner}"], text_of(result)
    finally:
        aoa_test.TESTS.pop("tat_define_termination", None)
