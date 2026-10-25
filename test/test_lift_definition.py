"""`LiftDefinition` (node_classes/LIFT_DEFINITION.md): with no Isabelle, the
schema and the descriptions (§2, §3), `gen`'s checks and refusals (§4),
the definition as the node holds, stores and prints it (§1, §2, §8), the
node's name and the framework's `DuplicateName` on it, the message, the
status and the recorded field (§6), the carry on an amend (§4), the mark
and the owing line (§7), the emitted text (§5); through the std harness,
the evaluation with the verdict on `(code_dt)` and the trial, the choice
recorded once (§6; COMMON §5), `recall` (§8), the rendered file (§5), a
proof constructed on a goal with no subgoal (§6, §7) and the refusals (§6);
on a raw ML process on HOL, the search, the sentence, the refusal path and
the verdict of TAT_Lift_Definition_Command, its rows measured with and
without the option (§6).
Run: python -m pytest test/test_lift_definition.py
"""

import io
import json
import re

import jsoncomment
import pytest

import stand_ins
import test_define as tdf
import test_model as tm
import test_session_theory as ts
from baselines import DOCS, fenced_blocks, fenced_lines
from harness import text_of, until
from invariants import assert_store_mirrors
from Isabelle_RPC_Host.unicode import IsaTerm, ascii_of_unicode
from isabelle_theory_agent import compile as C, edit, isabelle_driver, model as M
from isabelle_theory_agent.exceptions import DuplicateName, InvalidField, InvalidName, RawASTError
from isabelle_theory_agent.jobs import NOT_STARTED, PASSED, RUNNING, Failed, Succeeded
from isabelle_theory_agent.std import common, lift_definition
from isabelle_theory_agent.std.common import Infix, Template
from isabelle_theory_agent.std.lift_definition import OWING_LINE, LiftDefinition
from isabelle_theory_agent.store import Forest_Store
from ml_process import AFTER, ROOT, ml_process, ml_string, read_back
from std_forest import KINDS, assert_a_missing_row_is_refused_at_start, forest, insert, inv, refused
from test_descriptions import descriptions
from test_model import locked, run
from test_session_theory import Forest_Under_Test, session, theory
from test_theorem import BAD, PROVED, assert_the_eleven_ways, lemma, with_proof
from test_typedef import DLIST

table = ts.table                    # the fake state slot table and the fake wire, per test
LD = DOCS / "node_classes" / "LIFT_DEFINITION.md"
COMMAND_ML = ROOT / "Isabelle_Std" / "ML" / "TAT_Lift_Definition_Command.ML"

DL_REV, DL_CONS, DL_TL_OPT = (json.loads("\n".join(block)) for block in fenced_blocks(LD, "2.")[:3])   # §2's examples
INFIXR = {"form": "infixr", "symbol": "##", "priority": 65}                                             # `dl_cons`'s syntax


def definition(name="dl_rev", type="'a dlist ⇒ 'a dlist", is_="rev", english="Reversal of a list without repetition",
               **fields):
    """A construct of `lift_definition`: §2's first example by default."""
    return {"kind": "lift_definition", "english": english, "name": name, "type": type, "is": is_, **fields}


DLIST_ALONE = {k: v for k, v in DLIST.items() if k != "children"}                   # the block with no child
DL_LENGTH = definition("dl_length", "'a dlist ⇒ nat", "length", "The length of a list without repetition")    # §5's fourth
DL_WRAP = definition("dl_wrap", "'a dlist ⇒ 'a dlist dlist", "λxs. [xs]",
                     "A list without repetition as the one element of another", code_dt=True)             # §6's verdict without effect
DL_SUC = definition("dl_suc", "'a dlist ⇒ nat", "Suc", "A term whose type is no representation", code_dt=True)   # §6's second block
DL_PAIR = definition("dl_pair", "'a dlist ⇒ ('a dlist × 'a fset) option", "λxs. Some (xs, xs)",
                     "A list without repetition beside itself as a finite set", code_dt=True)       # §6's trial refused


# --- the schema and the descriptions (§2, §3) ------------------------------

def test_the_schema_and_the_descriptions_are_the_documents():
    [_, _, _, schema] = fenced_blocks(LD, "2.")
    text = re.sub(r'"\$defs": \{[^}]*\}.*', '"$defs": {}', "\n".join(schema))      # the spread and its comment
    expected = jsoncomment.JsonComment().loads(text)
    expected["$defs"] = {**common.MIXFIX_DEFS}
    assert LiftDefinition.construct_schema == expected
    assert list(lift_definition.KINDS) == ["lift_definition"]
    assert sorted(descriptions(LiftDefinition.construct_schema)) == sorted(
        fenced_lines(LD, "3.") + descriptions(common.MIXFIX_DEFS))
    assert DL_REV == definition()
    assert DL_CONS == definition("dl_cons", "'a ⇒ 'a dlist ⇒ 'a dlist", "λx xs. if x ∈ set xs then xs else x # xs",
                                 "Insertion at the front, unless the element is already there", syntax=INFIXR)
    assert DL_TL_OPT == definition("dl_tl_opt", "'a dlist ⇒ 'a dlist option", "λxs. if xs = [] then None else Some (tl xs)",
                                   "The tail of a list without repetition, if any", code_dt=True)


# --- `gen` (§2, §4) ----------------------------------------------------------

def test_gen_keeps_the_definition_normalised_as_isaterms_and_names_the_node():
    f, x = forest(definition(type=" 'a dlist\n ⇒  'a dlist ", is_="rev\n", english="Reversal\n of a  list without repetition ",
                             syntax={"form": "mixfix", "template": "_\n\trev  ", "argument_priorities": [21], "priority": 21}))
    (p,) = x.sub_nodes
    assert isinstance(p, LiftDefinition) and p.kind == "lift_definition" and p.name == "dl_rev"
    assert f.id_of(p) == "lift_definition_dl_rev"
    assert p.english == "Reversal of a list without repetition"
    assert p.type == IsaTerm.from_agent("'a dlist ⇒ 'a dlist") and isinstance(p.type, IsaTerm)
    assert p.is_ == IsaTerm.from_agent("rev") and isinstance(p.is_, IsaTerm)
    assert p.syntax == Template(IsaTerm.from_agent("_  rev  "), (21,), 21)          # newlines and tabs alone, the spaces layout
    assert (p.code_dt, p.with_code_dt) == (False, None)                                # left out; recorded by no evaluation yet (§1; COMMON §5)
    assert p.goal_state is not p.state and p.goal_state in p._states_inside()         # `Proof_Obligation`'s slot (COMMON §3)
    (q,) = insert(f, x, 1, [DL_CONS])
    assert q.syntax == Infix("infixr", IsaTerm.from_agent("##"), 65) and (q.code_dt, q.with_code_dt) == (False, None)
    (r,) = insert(f, x, 2, [DL_TL_OPT])
    assert r.syntax is None and (r.code_dt, r.with_code_dt) == (True, None)
    inv(f)


def test_gen_refuses_as_section_4_says():
    """§4's refusals: a name outside §1's grammar
    (RENDER_BASELINES §2's sixth line); the integer bound on a priority, a
    missing `is`, the recorded field or an unknown one authored, by the
    framework."""
    f, x = forest()
    [invalid] = [line for line in fenced_lines(DOCS / "RENDER_BASELINES.md", "2.")
                 if line.startswith("`dl-rev` is not a valid constant name")]
    e = refused(f, x, [definition("dl-rev")], InvalidName)
    assert (e.name, e.grammar) == ("dl-rev", "constant name") and str(e) == "At `constructs[0]`: " + invalid
    for name in ("1st", "dl_rev_", "a b", "", "α"):
        assert refused(f, x, [definition(name)], InvalidName).grammar == "constant name"
    # the framework's integer bound (MODULE_STRUCTURE §4.4), RENDER_BASELINES §2's line, the forest unchanged
    [bound] = [line for line in fenced_lines(DOCS / "RENDER_BASELINES.md", "2.") if line.endswith("must be a 64-bit integer.")]
    e = refused(f, x, [definition(syntax={**INFIXR, "priority": 2**64})], InvalidField)
    assert str(e) == "At `constructs[0]`: " + bound.replace("types[0].constructors[1].syntax", "syntax") and e.field == "syntax.priority"
    for raw in ({"kind": "lift_definition", "english": "e", "name": "f", "type": "nat"},    # no `is`
                definition(with_code_dt=True),                                             # recorded, not authored (§2)
                definition(parametric="dl_rev.transfer")):                                 # not taken (§2)
        refused(f, x, [raw], RawASTError)
    assert x.sub_nodes == []
    inv(f)


def test_a_sibling_bearing_the_node_s_id_component_is_the_framework_s_duplicate_name():
    f, x = forest(DL_REV)
    e = refused(f, x, [definition(is_="id")], DuplicateName)
    assert e.id_component == "lift_definition_dl_rev" and e.taken_by == "lift_definition_dl_rev"
    inv(f)


def test_an_amend_with_the_same_goal_structure_carries_the_proof():
    """§4: equal `type` and `is` carry the replaced job's outcome — a changed
    `name`, `syntax`, `code_dt` or `english` aside; a changed `is` or `type`
    does not; the stored check is never carried (CONSTRUCT_INTERACTION §3.1)."""
    f, x = forest(DL_REV)
    (p,) = x.sub_nodes
    with_proof(p, M.READY_CLEAN, PROVED, PASSED)
    p.with_code_dt = True                                   # as an evaluation recorded it
    (p2,) = run(locked(f, edit.amend(p, [definition("dl_reverse", english="Another wording", syntax=INFIXR, code_dt=True)])))
    assert p2.job().outcome == PROVED and p2.check_outcome() is None and p2.name == "dl_reverse"
    assert p2.with_code_dt is None                          # the recorded choice is the evaluation's to make again (COMMON §5)
    assert p2.goal_structure() == p.goal_structure() == ("'a dlist \\<Rightarrow> 'a dlist", "rev")
    (p3,) = run(locked(f, edit.amend(p2, [definition("dl_reverse", is_="id")])))
    assert p3.job().outcome is NOT_STARTED                  # the term changed
    p3.job().outcome = PROVED
    (p4,) = run(locked(f, edit.amend(p3, [definition("dl_reverse", type="'a dlist ⇒ 'a list", is_="id")])))
    assert p4.job().outcome is NOT_STARTED                  # the type changed
    inv(f)


# --- the store (§1, §2) --------------------------------------------------------

def test_the_definition_is_stored_and_a_missing_row_is_refused_at_start(tmp_path):
    path = tmp_path / "TAT.sqlite"
    f, x = forest(DL_REV, DL_CONS, DL_TL_OPT, store=Forest_Store(path, ts.stand_ins.log()))
    nodes = x.sub_nodes
    nodes[1].with_code_dt = True                                  # as an evaluation records it (§6); the others' not yet recorded
    with f.store.transaction():
        for n in nodes:
            f._store_node(n)

    def fields(n):
        return (n.name, n.english, n.type, n.syntax, n.is_, n.code_dt, n.with_code_dt)
    before = [fields(n) for n in nodes]
    rows = f.store.fields(nodes[0].identity)
    assert rows["name"] == "dl_rev" and rows["type"] == "'a dlist ⇒ 'a dlist" and rows["is"] == "rev"
    assert rows["syntax"] is None and (rows["code_dt"], rows["with_code_dt"]) == (False, None)    # left out, not recorded: None-valued rows
    rows = f.store.fields(nodes[1].identity)
    assert rows["syntax"] == INFIXR and (rows["code_dt"], rows["with_code_dt"]) == (False, True)
    rows = f.store.fields(nodes[2].identity)
    assert rows["syntax"] is None and (rows["code_dt"], rows["with_code_dt"]) == (True, None)
    f.store.close()
    f2 = Forest_Under_Test(store=Forest_Store(path, ts.stand_ins.log()), kinds=KINDS)
    (s2,) = f2.sub_nodes
    assert isinstance(s2, M.Session)
    (x2,) = s2.sub_nodes
    assert isinstance(x2, M.Theory)
    loaded = x2.sub_nodes
    assert [fields(n) for n in loaded] == before and all(isinstance(n, LiftDefinition) for n in loaded)
    first = loaded[0]
    assert isinstance(first, LiftDefinition)
    assert first.goal_state.name != nodes[0].goal_state.name and first.goal_state in first._states_inside()
    f2.store.close()
    # a row missing — an authored field's, the None-valued one's or the recorded one's — is refused at start (§1)
    assert_a_missing_row_is_refused_at_start(path, nodes[0].identity, ("is", "syntax", "code_dt", "with_code_dt"))


# --- the message, the status and the recorded field (§6), the mark (§7) -------

def test_eval_opr_sends_the_definition_and_records_what_the_steps_yielded(monkeypatch):
    """COMMON §3's `_eval_opr` with `LiftDefinition`'s own: the message §6's
    pair — the definition in its order, the goal part last, and the recorded
    `with_code_dt`, None before an evaluation has recorded one —;
    `with_code_dt` set to what `open_goal` yielded, the fake answering as the
    ML does (COMMON §5): under a recorded value that value or a refusal,
    never the other; under None the decision; the `Ready` carrying no
    message; Isabelle's messages an obstacle, the recorded field untouched;
    a syntax on the wire as `mixfix_text` writes it, in `ascii`."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        DL_REV, DL_CONS, DL_TL_OPT, DL_WRAP, DL_SUC]})])
    (x,) = s.sub_nodes
    rev, cons, tl_opt, wrap, suc = x.sub_nodes
    [_, quot_thm, _, _, _] = fenced_blocks(LD, "6.")
    calls = []

    async def call(conversation, name, args):
        calls.append((name, args))
        (function, *_), recorded = args[3]
        if function == "dl_suc":                    # refused at the open goal, the same with the option: §6's second block
            return [["\n".join(quot_thm)], None]
        # under a recorded value that value; under None the decision: dl_rev and dl_cons, `code_dt` false, without the
        # option; dl_tl_opt undecided and its trial passing; dl_wrap without effect
        return [[], [recorded if recorded is not None else function == "dl_tl_opt", None]]
    monkeypatch.setattr(isabelle_driver, "call", call)
    suc.with_code_dt = True                                 # as an earlier evaluation recorded it (COMMON §5)
    run(x.evaluate_to(None, False))
    assert [name for name, _ in calls] == ["TAT.LiftDefinition.evaluate"] * 5
    assert [args[:3] for _, args in calls] == [
        (n.state.to_msgpack(), n.goal_state.to_msgpack(), n.resulting_state().to_msgpack()) for n in (rev, cons, tl_opt, wrap, suc)]
    assert [args[3][1] for _, args in calls] == [None, None, None, None, True]       # the recorded `with_code_dt` sent
    assert calls[0][1][3] == (("dl_rev", None, False, "'a dlist \\<Rightarrow> 'a dlist", "rev"), None)
    assert rev.message() == (calls[0][1][3][0], False)                                  # recorded by the evaluation
    assert cons.message()[0] == ("dl_cons", '(infixr "##" 65)', False, "'a \\<Rightarrow> 'a dlist \\<Rightarrow> 'a dlist",
                                 "\\<lambda>x xs. if x \\<in> set xs then xs else x # xs")
    assert tl_opt.message()[0] == ("dl_tl_opt", None, True, "'a dlist \\<Rightarrow> 'a dlist option",
                                   "\\<lambda>xs. if xs = [] then None else Some (tl xs)")
    assert all(n.message()[0][3:] == n.goal_structure() for n in (rev, cons, tl_opt, wrap, suc))
    for n in (rev, cons, tl_opt, wrap):
        assert isinstance(n._status, M.Ready) and n._status.messages == (), n.name
    assert [n.with_code_dt for n in (rev, cons, tl_opt, wrap)] == [False, False, True, False]    # wrap: False from None
    assert isinstance(suc._status, M.CannotEvaluate) and suc.with_code_dt is True       # a refusal under a recorded value:
                                                                                        # untouched, never a switch
    assert [m.unicode for m in suc._status.messages] == ["\n".join(quot_thm)]
    assert rev.mark(M.BRIEFING, 0) == "unverified definition, proof not started" and suc.mark(M.BRIEFING, 0) == "invalid definition"
    assert not rev.is_finished() and not suc.is_finished()                     # the proof is compulsory (COMMON §3)
    (t,) = insert(f, x, 5, [DL_LENGTH])
    assert t.message() == (("dl_length", None, False, "'a dlist \\<Rightarrow> nat", "length"), None)
    assert t.mark(M.BRIEFING, 0) == "not evaluated, proof not started"


def test_the_recorded_field_reaches_the_store_and_the_option_is_emitted_from_it_alone(monkeypatch):
    """§1, §6; COMPILATION §3: a walk's store writes `with_code_dt` as the
    evaluation recorded it, so a loaded forest emits the same file; the
    option is written from the recorded field, never from the authored
    `code_dt` — which the mirror cannot tell apart, both being stored, so a
    direct case does: `code_dt` true and `with_code_dt` false emits none."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [DL_CONS, DL_TL_OPT, DL_WRAP]})])
    (x,) = s.sub_nodes
    cons, tl_opt, wrap = x.sub_nodes

    async def call(conversation, name, args):
        return [[], [args[3][0][0] == "dl_tl_opt", None]]
    monkeypatch.setattr(isabelle_driver, "call", call)
    run(x.evaluate_to(None, False))
    rows = {n.name: f.store.fields(n.identity) for n in (cons, tl_opt, wrap)}
    assert [rows[n]["with_code_dt"] for n in ("dl_cons", "dl_tl_opt", "dl_wrap")] == [False, True, False]
    assert_store_mirrors(f, shape=ts.shape)
    out = io.StringIO()
    wrap.emit(0, out)
    assert (wrap.code_dt, wrap.with_code_dt) == (True, False)
    assert out.getvalue().splitlines()[1] == 'lift_definition dl_wrap :: "\'a dlist ⇒ \'a dlist dlist" is "λxs. [xs]" sorry'
    out = io.StringIO()
    tl_opt.emit(0, out)
    assert out.getvalue().splitlines()[1].startswith("lift_definition (code_dt) dl_tl_opt ::")


def test_the_mark_reads_one_of_eleven_ways_and_the_owing_line_stands_while_unverified():
    """§7's mark, state by state — COMMON §3's table with the three words of
    a class that defines: `valid definition` alone once the proof stands,
    `unverified definition` with the proof's word before; the eleven, and
    no other, are the document's first block; the owing line, its second,
    exactly while the line reads `unverified definition`."""
    [block, state, _, _] = fenced_blocks(LD, "7.")
    assert [OWING_LINE] == state
    f, x = forest(DL_REV)
    (p,) = x.sub_nodes
    assert_the_eleven_ways(p, block, OWING_LINE)


def test_the_jobs_sentences_name_the_term():
    """§7: the construction's failure header and its failure notification
    both read the document's sentence, the node by its id; the agent's
    refutation reads the refutation sentence in both; the success
    notification is `Proof_Job`'s."""
    [_, _, failed, refuted] = fenced_blocks(LD, "7.")
    f, x = forest(DL_REV)
    (p,) = x.sub_nodes
    job = p.job()
    assert failed == ["Failed to prove that `lift_definition_dl_rev`'s defining term respects the representation:"]
    assert refuted == ["`lift_definition_dl_rev`'s defining term may not respect the representation:"]
    assert job.failure_header(Failed("gave up")) == failed[0]
    assert job.finished_notification(Failed("gave up", "surrender")) == failed[0] + "\n  gave up"
    assert job.failure_header(Failed("gave up", "refute")) == refuted[0]
    assert job.finished_notification(Failed("gave up", "refute")) == refuted[0] + "\n  gave up"
    assert job.finished_notification(Succeeded({})) == "`lift_definition_dl_rev` is proven."


# --- what it prints (§8) -----------------------------------------------------

def test_print_fields_writes_the_definition_and_english_by_depth():
    f, x = forest(DL_REV, DL_CONS, DL_TL_OPT)
    p, q, r = x.sub_nodes
    [cons, tl_opt, failed, bad] = fenced_blocks(LD, "8.")
    [_, _, _, sentences, _] = fenced_blocks(LD, "6.")

    def fields(node, mode, depth):
        out = io.StringIO()
        node.print_fields(0, out, mode, depth)
        return out.getvalue().splitlines()
    assert [fields(q, M.RECALL, d) for d in range(4)] == [cons, cons[:1], cons[:1], []]
    assert fields(q, M.OUT_FOCUS, 0) == [] and fields(q, M.Relative_Focus(frozenset({q}), 0), 0) == []
    # `(code_dt)` at depth 0 alone, from the authored field: the recorded one is not printed
    bare = tl_opt[0].removeprefix("(code_dt) ")
    assert [fields(r, M.RECALL, d) for d in range(4)] == [tl_opt, [bare], [bare], []]
    q.with_code_dt = True
    assert fields(q, M.RECALL, 0) == cons
    # against no keyword, whatever the theory recorded: the name bare, the type and the term quoted unless an identifier
    for keywords in (None, frozenset(), frozenset({"dl_rev", "rev", "dl_cons"})):
        x.keywords = keywords
        assert fields(p, M.RECALL, 1) == ['dl_rev :: "\'a dlist ⇒ \'a dlist" is rev'] and fields(q, M.RECALL, 1) == cons[:1], keywords
    me = stand_ins.agent(f.conversation)
    with_proof(p, M.CannotEvaluate((IsaTerm.from_agent(sentences[0]),)), NOT_STARTED)      # §8's `Error:` example whole
    assert f.render(p, M.RECALL, me).splitlines() == failed
    with_proof(p, M.READY_CLEAN, PROVED, BAD)                                               # §8's last example whole
    assert f.render(p, M.RECALL, me).splitlines() == bad
    with_proof(p, M.NOT_EVALUATED, NOT_STARTED)                                             # back to a node no walk reached
    inv(f)


# --- emission (§5) ------------------------------------------------------------

def test_the_emitted_text_is_section_5_s():
    [one, two, three, four] = fenced_blocks(LD, "5.")
    f, x = forest(DL_REV, DL_CONS, DL_TL_OPT, DL_LENGTH)
    p, q, r, t = x.sub_nodes
    x.keywords = frozenset()                                 # recorded by a header run, which emission presupposes

    def emitted(node) -> list[str]:
        """In `unicode` (§5); the file's `\\<name>` form is the compile's conversion (COMPILATION §2)."""
        out = io.StringIO()
        assert node.emit(1, out) == 1
        assert "\\<" not in out.getvalue()                                 # nothing written in `ascii`
        return out.getvalue().splitlines()

    def expected(*unicode_lines: str) -> list[str]:
        return ["  " + line for line in unicode_lines]

    def admitted(block):
        """The block with `sorry` for `by aoa`: the proof not standing."""
        return expected(block[0], block[1].replace(" by aoa", " sorry"))
    with pytest.raises(AssertionError):                                # nothing recorded: never written (`can_emit`; COMMON §5)
        p.emit(1, io.StringIO())
    p.with_code_dt = r.with_code_dt = False                            # as an evaluation recorded them
    no_option = [three[0], three[1].replace("(code_dt) ", "")]         # `code_dt` authored, `with_code_dt` recorded false
    assert emitted(p) == admitted(one) and emitted(r) == admitted(no_option)
    for node, recorded in ((p, False), (q, False), (r, True), (t, False)):      # as §5's examples record them
        node.with_code_dt = recorded
        with_proof(node, M.READY_CLEAN, PROVED, PASSED)
    assert [emitted(n) for n in (p, q, r, t)] == [expected(*block) for block in (one, two, three, four)]
    for outcome, check in ((PROVED, BAD), (PROVED, None), (PROVED, RUNNING), (Failed("no"), None)):
        with_proof(p, M.READY_CLEAN, outcome, check)                                     # not proven: `sorry`
        assert emitted(p) == admitted(one), (outcome, check)
    with_proof(p, M.READY_CLEAN, PROVED, PASSED)
    x.keywords = frozenset({"dl_rev", "rev", "dl_cons", "length"})               # keywords: quoted (§5)
    assert emitted(p) == expected(one[0], 'lift_definition "dl_rev" :: "\'a dlist ⇒ \'a dlist" is "rev" by aoa')
    assert emitted(q)[1] == ('  lift_definition "dl_cons" :: "\'a ⇒ \'a dlist ⇒ \'a dlist" (infixr "##" 65)'
                             ' is "λx xs. if x ∈ set xs then xs else x # xs" by aoa')
    assert emitted(t)[1] == '  lift_definition dl_length :: "\'a dlist ⇒ nat" is "length" by aoa'
    x.keywords = frozenset()
    assert emitted(t)[1] == '  lift_definition dl_length :: "\'a dlist ⇒ nat" is length by aoa'


def test_the_two_spellings_are_kept_apart():
    """§2, §5, §8: a type, a term or a symbol whose `unicode` and `ascii`
    differ is stored, printed and emitted in `unicode` and sent to Isabelle
    in `ascii`."""
    f, x = forest(definition("dl_mem", "'α ⇒ 'α dlist ⇒ bool", "λx xs. x ∈ set xs", "Membership",
                             syntax={"form": "infix", "symbol": "∈⇩d", "priority": 50}))
    (p,) = x.sub_nodes
    x.keywords = frozenset()
    assert p.message() == (("dl_mem", '(infix "\\<in>\\<^sub>d" 50)', False, "'\\<alpha> \\<Rightarrow> '\\<alpha> dlist \\<Rightarrow> bool",
                            "\\<lambda>x xs. x \\<in> set xs"), None)
    rows = {}
    p.to_store(type("Rows", (), {"put": lambda self, k, v: rows.__setitem__(k, v)})())
    assert rows["type"] == "'α ⇒ 'α dlist ⇒ bool" and rows["is"] == "λx xs. x ∈ set xs"
    assert rows["syntax"] == {"form": "infix", "symbol": "∈⇩d", "priority": 50}
    out = io.StringIO()
    p.print_fields(0, out, M.RECALL, 1)
    assert out.getvalue() == 'dl_mem :: "\'α ⇒ \'α dlist ⇒ bool" (infix "∈⇩d" 50) is "λx xs. x ∈ set xs"\n'
    out = io.StringIO()
    p.with_code_dt = False
    p.emit(0, out)
    assert out.getvalue().splitlines()[1] == 'lift_definition dl_mem :: "\'α ⇒ \'α dlist ⇒ bool" (infix "∈⇩d" 50) is "λx xs. x ∈ set xs" sorry'


# --- the evaluation, in the plugin's run of the harness (§5, §6, §7, §8) -------

@pytest.mark.isabelle(deadline=600)
async def test_a_function_is_lifted_the_option_tried_and_a_proof_constructed(std_conversation, std_harness, tmp_path):
    """§6 through `TAT.LiftDefinition.evaluate`: a theory of test_typedef's
    `dlist` block holding §2's three functions, `dl_rev` and `dl_cons` asking for the
    option and judged not needed — recorded false, nothing said —,
    `dl_tl_opt` undecided, its trial passing and the option kept,
    `dl_length`, whose goal opens with no subgoal, and `dl_wrap`, judged
    without effect — recorded false, no trial —, then a theorem parsing
    through the lifted constants and `##`; every node `Ready`, `goal_state`
    and the resulting slot written; `recall` as §8 shows; the theory
    rendered as §5 shows with `sorry` and read back whole by Isabelle; then
    `construct` on `dl_length`: the product `-`, the check `PASSED`, the
    mark `valid definition` and no owing line, the emitted line ending `by
    aoa`.  Beside it a theory `Y`: test_quotient_type's `fset` block
    holding, inside a `lifting_context` opening `dlist` — the one place
    with both setups open —, `dl_pair`, undecided — a constructor step, no
    composition — and its trial refused, the option dropped, nothing said.  Then the
    callback alone under a recorded `with_code_dt`: the command run as
    recorded, `[[], [a, nil]]` on the wire, a refused admission the
    refusal; `code_dt` false with nothing recorded, neither the verdict
    nor the trial.  Last, the recorded choice kept (COMMON §5):
    `dl_tl_opt` with `False` as an earlier evaluation would have recorded
    it, invalidated and evaluated again, keeps `False` where a fresh
    decision gives `True`, and the file carries no option for it."""
    from test_quotient_type import FSET                   # here: test_quotient_type imports this module
    forest = std_conversation.forest
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [ts.session("TAT_Suite",
                ts.theory("X") | {"children": [
                    {**DLIST, "children": [{**DL_REV, "code_dt": True}, {**DL_CONS, "code_dt": True}, DL_TL_OPT, DL_LENGTH, DL_WRAP]},
                    lemma("uses_the_definitions", english="Every definition above parses",
                          for_any=({"name": "x", "type": "'a"}, {"name": "xs", "type": "'a dlist"}), premises=(),
                          conclusion="dl_rev (x ## xs) = dl_rev (x ## xs) ∧ dl_length xs = dl_length xs"
                                     " ∧ dl_tl_opt xs = dl_tl_opt xs ∧ dl_wrap xs = dl_wrap xs")]},
                ts.theory("Y") | {"children": [DLIST_ALONE, {**FSET, "children": [
                    {"kind": "lifting_context", "name": "with_dlist", "types": ["dlist"], "children": [DL_PAIR]}]}]})]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 0 and text.count("Notice:") == 0, text
        (s,) = forest.sub_nodes
        x, y = s.sub_nodes
        dlist, uses = x.sub_nodes
        rev, cons, tl_opt, length, wrap = dlist.sub_nodes
        assert isinstance(dlist.evaluation_status_beginning, M.Ready) and dlist.evaluation_status_ending == M.READY_CLEAN
        for node in (rev, cons, tl_opt, length, wrap, uses):
            assert isinstance(node._status, M.Ready) and node._status.messages == (), (node.name, node._status)
            assert await node.goal_state.is_initialized() and await node.resulting_state().is_initialized()
        assert [(n.code_dt, n.with_code_dt) for n in (rev, cons, tl_opt, length, wrap)] == [
            (True, False), (True, False), (True, True), (False, False), (True, False)]
        (_, fset) = y.sub_nodes
        (with_dlist,) = fset.sub_nodes
        (pair,) = with_dlist.sub_nodes
        assert isinstance(pair, LiftDefinition) and isinstance(pair._status, M.Ready) and pair._status.messages == ()
        assert (pair.code_dt, pair.with_code_dt) == (True, False)          # the trial refused: the option dropped, nothing said
        [cons_block, tl_opt_block, _, _] = fenced_blocks(LD, "8.")
        recalled = await session.call_tool("recall", {"node_id": "lift_definition_dl_tl_opt"})      # §8's second block
        lines = text_of(recalled).splitlines()
        assert not recalled.isError and lines == [
            "- lift_definition_dl_tl_opt (unverified definition, proof not started)", *("  " + line for line in tl_opt_block),
            "  " + OWING_LINE], lines
        recalled = await session.call_tool("recall", {"node_id": "theory_X"})       # the nodes at depth 2: no `english`, no option,
        shown = text_of(recalled).splitlines()                                       # no owing line (PRINT §2)
        assert not recalled.isError and shown[5:16] == [
            "    - lift_definition_dl_rev (unverified definition, proof not started)",
            '      dl_rev :: "\'a dlist ⇒ \'a dlist" is rev',
            "    - lift_definition_dl_cons (unverified definition, proof not started)", "      " + cons_block[0],
            "    - lift_definition_dl_tl_opt (unverified definition, proof not started)",
            "      " + tl_opt_block[0].removeprefix("(code_dt) "),
            "    - lift_definition_dl_length (unverified definition, proof not started)",
            '      dl_length :: "\'a dlist ⇒ nat" is length',
            "    - lift_definition_dl_wrap (unverified definition, proof not started)",
            '      dl_wrap :: "\'a dlist ⇒ \'a dlist dlist" is "λxs. [xs]"',
            "  - lemma_uses_the_definitions (valid statement, proof not started)"], shown
        # the theory rendered as §5 shows, with `sorry`, and its body read back whole under what it imports
        rendered = C.render(forest)
        file = rendered.files[C.Path("TAT_Suite/X.thy")]
        assert file.startswith('theory "X"\n  imports "Main" "TAT_Std.TAT_Std"\nbegin\n') and file.endswith("end\n")
        for block in fenced_blocks(LD, "5."):
            assert "".join(ascii_of_unicode(line) + "\n" for line in block).replace(" by aoa\n", " sorry\n") in file, file
        assert ascii_of_unicode('lift_definition dl_wrap :: "\'a dlist ⇒ \'a dlist dlist" is "λxs. [xs]" sorry\n') in file, file
        assert "(code_dt) dl_wrap" not in file
        await read_back(std_harness, file, tmp_path)
        # `construct` on the goal with no subgoal (§6; COMMON §3): the product `-`, the check passed, `valid definition`
        result = await session.call_tool("construct", {"node_ids": ["lift_definition_dl_length"]})
        assert not result.isError and "Started the proof construction on `lift_definition_dl_length`" in text_of(result)
        job = length.job()
        await until(lambda: job.outcome is not RUNNING, "the proof construction's outcome", 240.0)
        assert isinstance(job.outcome, Succeeded), job.outcome
        assert job.outcome.product == {"text": "-", "thread_cpu": 0, "wall": 0}, job.outcome.product
        assert length.check_outcome() is PASSED and length.mark(M.BRIEFING, 0) == "valid definition"
        assert length.owing_line() is None
        result = await session.call_tool("check_construct", {})
        assert "`lift_definition_dl_length` is proven." in text_of(result), text_of(result)
        recalled = await session.call_tool("recall", {"node_id": "lift_definition_dl_length"})
        assert text_of(recalled).splitlines() == [
            "- lift_definition_dl_length (valid definition)", '  dl_length :: "\'a dlist ⇒ nat" is length',
            "  The length of a list without repetition"], text_of(recalled)
        out = io.StringIO()
        length.emit(0, out)
        assert out.getvalue().splitlines()[-1] == 'lift_definition dl_length :: "\'a dlist ⇒ nat" is length by aoa'
        # the callback alone, on slots beside the tree's (COMMON §3, §5): under a recorded `with_code_dt` the command run
        # as recorded, alone, `[[], [a, nil]]`; a refused admission the refusal, never a switch
        async def evaluate(node, recorded, definition=None):
            goal, resulting = (M.Isar_State_Slot.assign(forest.conversation) for _ in range(2))
            return await isabelle_driver.call(
                forest.conversation, "TAT.LiftDefinition.evaluate",
                (node.state.to_msgpack(), goal.to_msgpack(), resulting.to_msgpack(),
                 (definition or node.message()[0], recorded)))
        assert await evaluate(tl_opt, True) == [[], [True, None]]
        assert await evaluate(tl_opt, False) == [[], [False, None]]
        name, syntax, _, *goal = tl_opt.message()[0]
        assert await evaluate(tl_opt, None, (name, syntax, False, *goal)) == [[], [False, None]]   # `code_dt` false, nothing
        # recorded: neither the verdict nor the trial (§6)
        messages, what = await evaluate(wrap, True)
        assert what is None and messages == ["Composition of abstract types has not been implemented yet."], messages
        # the recorded choice kept (COMMON §5): `False` on dl_tl_opt as an earlier evaluation would have recorded it,
        # an invalidation and `evaluate_to`: still `False` where a fresh decision gives `True`, the file without the option
        tl_opt.with_code_dt = False
        await tm._invalidate(tl_opt)
        assert tl_opt.mark(M.BRIEFING, 0) == "not evaluated, proof not started"
        result = await session.call_tool("evaluate_to", {"node_id": "theory_X", "checks": "blocking"})
        assert not result.isError, text_of(result)
        assert isinstance(tl_opt._status, M.Ready) and tl_opt.with_code_dt is False
        file = C.render(forest).files[C.Path("TAT_Suite/X.thy")]
        assert ascii_of_unicode('lift_definition dl_tl_opt :: "\'a dlist ⇒ \'a dlist option"') in file and "(code_dt)" not in file


@pytest.mark.isabelle(deadline=600)
async def test_refused_definitions_and_a_refused_admission_are_obstacles(std_conversation):
    """§6, §8, one theory per obstacle since a walk stops at the first: inside
    `dlist`'s block, `dl_suc` and `dl_bad` are refused at the open goal with
    Isabelle's rendering, §6's second and third blocks — `dl_suc` asks for
    `(code_dt)`, undecided since `prove_quot_thm` raises, so the probe is
    refused at the open goal, the same as without the option, and no trial
    is run;
    `dl_f`, with a free
    variable, at the admission, §6's fifth; a `dl_rev` whose name a
    `definition` took, with the duplicate constant; a type that
    does not parse, with Isabelle's messages; `int_swap` on the library's
    `int`, whose setup Int.thy closed and a `lifting_context` reopens, with
    the class's sentence, §6's third, shown under `recall` as §8's `Error:`
    block; each an obstacle with `goal_state` empty and nothing recorded;
    no theory written."""
    forest = std_conversation.forest
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [ts.session("TAT_Suite",
                ts.theory("X") | {"children": [{**DLIST, "children": [DL_SUC]}]},
                ts.theory("Y") | {"children": [
                    {**DLIST, "children": [definition("dl_bad", "'a dlist ⇒ nat", "id", "A term whose type cannot be instantiated")]}]},
                ts.theory("Z") | {"children": [
                    {**DLIST, "children": [definition("dl_f", "'a dlist ⇒ 'a dlist", "λxs. g xs", "A term with a free variable")]}]},
                ts.theory("W") | {"children": [
                    tdf.definition("dl_rev", ("dl_rev = 0",), "A natural named dl_rev", type="nat", auto_reduction=True),
                    {**DLIST, "children": [DL_REV]}]},
                ts.theory("V") | {"children": [definition("dl_open", "'a dlist ⇒", "rev", "A type that does not parse")]},
                ts.theory("U") | {"children": [
                    definition("int_swap", "int ⇒ int", "λ(a, b). (b, a)", "An integer with its halves swapped")]})]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 6, text
        (s,) = forest.sub_nodes
        x, y, z, w, v, u = s.sub_nodes
        (dlist,), (dlist_y,), (dlist_z,), (defined, dlist_w), (open_,), (int_swap,) = (t.sub_nodes for t in (x, y, z, w, v, u))
        (suc,), (bad,), (f_,), (rev,) = (d.sub_nodes for d in (dlist, dlist_y, dlist_z, dlist_w))
        [_, quot_thm, check_rty, sentences, extra] = fenced_blocks(LD, "6.")
        messages = {node.name: [m.unicode for m in node._status.messages] for node in (suc, bad, f_, rev, int_swap)}
        assert messages == {"dl_suc": ["\n".join(quot_thm)], "dl_bad": ["\n".join(check_rty)], "dl_f": ["\n".join(extra)],
                            "dl_rev": ['Duplicate constant declaration "W.dl_rev" vs. "W.dl_rev"'],
                            "int_swap": [sentences[2]]}, messages
        assert open_._status.messages, open_._status
        for node in (suc, bad, f_, rev, open_, int_swap):
            assert isinstance(node._status, M.CannotEvaluate) and not await node.goal_state.is_initialized(), node.name
            assert node.with_code_dt is None                  # nothing recorded by a failure (COMMON §5)
        assert isinstance(dlist.evaluation_status_beginning, M.Ready) and isinstance(defined._status, M.Ready)
        assert dlist.evaluation_status_ending is M.NOT_EVALUATED                 # the walk stopped at the child
        recalled = await session.call_tool("recall", {"node_id": "lift_definition_int_swap"})     # §8's `Error:` block shape
        assert not recalled.isError and text_of(recalled).splitlines() == [
            "- lift_definition_int_swap (invalid definition)", '  int_swap :: "int ⇒ int" is "λ(a, b). (b, a)"',
            "  An integer with its halves swapped", "  Error:", "    " + sentences[2]], text_of(recalled)
    rendered = C.render(forest)
    assert not any(C.Path(f"TAT_Suite/{t}.thy") in rendered.files for t in "XYZWVU")     # an obstacle: not written


# The cases of TAT_Lift_Definition_Command on a raw ML process on HOL (§6): a
# theory `Probe` begun on `Complex_Main` — for `rat`; a theory `Thy_Info` does
# not hold, so that its types are a node's — declaring `'a dlist` by typedef,
# `'a fset` by quotient_type, the phantom `'a ph` and `'a wrap`, each setup
# closed again; the function with its type and the term read as the command
# reads them, through the structure's `read`; then the verdict on `(code_dt)`
# on the panel's 23 cases, 24 rows — case 2 as rows 02 and 02b —, in a theory
# `Verdicts` whose setups stay open, each
# row's context entered by its Isar text, a not needed or without effect row
# also run with and without the option, `sorry` its proof, what the option
# declared beyond the plain definition counted; every answer `writeln`ed for
# the test to read from stdout.
CASES = r"""
val probe = Theory.begin_theory ("Probe", Position.none) [Thy_Info.get_theory "Complex_Main"];
val thy = after probe (cat_lines [
  "typedef 'a dlist = \"{xs :: 'a list. distinct xs}\" morphisms list_of_dlist dlist_of_list by (rule exI[of _ \"[]\"]) simp",
  "setup_lifting type_definition_dlist", "lifting_update dlist.lifting", "lifting_forget dlist.lifting",
  "quotient_type 'a fset = \"'a list\" / \"\<lambda>xs ys. set xs = set ys\" by (auto intro!: equivpI reflpI sympI transpI)",
  "lifting_update fset.lifting", "lifting_forget fset.lifting",
  "typedef 'a ph = \"UNIV :: nat set\" by simp", "setup_lifting type_definition_ph",
  "lifting_update ph.lifting", "lifting_forget ph.lifting",
  "typedef 'a wrap = \"UNIV :: 'a set\" by simp", "setup_lifting type_definition_wrap",
  "lifting_update wrap.lifting", "lifting_forget wrap.lifting"]);
val lthy = Named_Target.theory_init thy;
fun read (q, r) = TAT_Lift_Definition_Command.read lthy ((Binding.name "f", SOME q, NoSyn), r);
fun show NONE = "NONE"
  | show (SOME sets) = "[" ^ commas (map (fn s => "[" ^ commas s ^ "]") sets) ^ "]";
fun needed name (q, r) =
  let val (lthy1, types) = read (q, r)
  in writeln ("needed " ^ name ^ ": " ^ show (TAT_Lift_Definition_Command.needed lthy1 types)) end;
fun sentence i (q, r) given =
  let
    val (lthy1, types as (_, T)) = read (q, r)
    val sets = (case given of SOME sets => SOME sets | NONE => TAT_Lift_Definition_Command.needed lthy1 types)
  in
    writeln ("sentence " ^ string_of_int i ^ ": " ^
      (case sets of NONE => "NONE" | SOME sets => TAT_Lift_Definition_Command.sentence lthy1 T sets))
  end;
fun refusal name (q, r) =
  (TAT_Lift_Definition_Command.lift_def_cmd_with_err_handling ([], (Binding.name name, SOME q, NoSyn), r) lthy;
   writeln ("refusal " ^ name ^ ": accepted"))
  handle ERROR msg => writeln ("refusal " ^ name ^ ": " ^ hd (split_lines msg));
val _ = needed "rev" ("'a dlist => 'a dlist", "rev");
val _ = needed "int_swap" ("int => int", "%(a, b). (b, a)");
val _ = needed "dl_two" ("'a dlist => 'a dlist * natural", "%xs. (xs, length xs)");
val _ = needed "ph" ("natural ph => nat ph", "id");
val _ = needed "dl_int" ("'a dlist => int", "id");
val _ = needed "fract" ("int => int => rat", "%a b. if b = 0 then (0, 1) else (a, b)");
val _ = sentence 1 ("'a dlist => 'a dlist", "rev") (SOME [["Probe.dlist"]]);
val _ = sentence 2 ("'a fset => 'a fset", "rev") (SOME [["Probe.fset"]]);
val _ = sentence 3 ("int => int", "%(a, b). (b, a)") (SOME [["Int.int"]]);
val _ = sentence 4 ("'a dlist => 'a dlist * natural", "%xs. (xs, length xs)") NONE;
val _ = sentence 5 ("'a wrap => 'a dlist", "id") (SOME [["Probe.wrap"], ["Probe.dlist"]]);
val _ = refusal "dl_two" ("'a dlist => 'a dlist * natural", "%xs. (xs, length xs)");
val _ = refusal "ph" ("natural ph => nat ph", "id");
val _ = refusal "dl_hd" ("'a => 'b dlist => 'b", "%(y::'b) (xs::'a list). hd xs");
val _ = refusal "dl_int" ("'a dlist => int", "id");

val verdicts = after (Theory.begin_theory ("Verdicts", Position.none) [Thy_Info.get_theory "Complex_Main"]) (cat_lines [
  "typedef 'a dlist = \"{xs :: 'a list. distinct xs}\" morphisms list_of_dlist dlist_of_list by (rule exI[of _ \"[]\"]) simp",
  "setup_lifting type_definition_dlist",
  "quotient_type 'a fset = \"'a list\" / \"\<lambda>xs ys. set xs = set ys\" by (auto intro!: equivpI reflpI sympI transpI)",
  "typedef 'a wrap = \"UNIV :: 'a set\" by simp", "setup_lifting type_definition_wrap",
  "typedef 'a pz = \"{n :: nat. 0 < n}\" by auto", "setup_lifting type_definition_pz",
  "typedef 'a nn = \"{x :: 'a. True}\" by auto", "setup_lifting type_definition_nn",
  "typedef fnp = \"{f :: nat \<Rightarrow> nat. f 0 = 0}\" by (rule exI[of _ \"\<lambda>_. 0\"]) simp",
  "setup_lifting type_definition_fnp",
  "definition c :: \"'a list \<Rightarrow> 'a dlist\" where \"c = dlist_of_list\"",
  "locale L = fixes n :: nat",
  "class cl = fixes cz :: 'a",
  "locale LT = fixes z :: 'a", "interpretation LT \"0::nat\" .",
  "locale L3 = fixes k :: nat", "interpretation L3 \"0::nat\" rewrites \"dlist_of_list = c\" by (simp add: c_def)",
  "locale L4 = fixes k :: nat", "interpretation L4 \"0::nat\" ."]);
fun string_of_verdict TAT_Lift_Definition_Command.Not_Needed = "not needed"
  | string_of_verdict TAT_Lift_Definition_Command.Without_Effect = "without effect"
  | string_of_verdict TAT_Lift_Definition_Command.Undecided = "undecided";
(*the constants and the types a run declared beyond its theory*)
fun declared thy0 thy1 =
  (subtract (op =) (Name_Space.get_names (Sign.const_space thy0)) (Name_Space.get_names (Sign.const_space thy1)),
   subtract (op =) (Name_Space.get_names (Sign.type_space thy0)) (Name_Space.get_names (Sign.type_space thy1)));
fun row id (pre, post) (ty, tm) =
  let
    val verdict =
      TAT_Lift_Definition_Command.code_dt_verdict (Toplevel.context_of (state_after verdicts pre))
        ((Binding.name "f", SOME ty, NoSyn), tm)
    fun run flag =
      Exn.Res (after verdicts (pre ^ "\nlift_definition " ^ (if flag then "(code_dt) " else "") ^
        "f :: \"" ^ ty ^ "\" is \"" ^ tm ^ "\" sorry\n" ^ post))
      handle Runtime.EXCURSION_FAIL (exn, _) => Exn.Exn exn
    fun refused exn = "refused (" ^ hd (split_lines (Runtime.exn_message exn)) ^ ")"
    fun behaviour () =
      (case (run true, run false) of
        (Exn.Res thy1, Exn.Res thy0) =>
          (case declared thy0 thy1 of
            ([], []) => "with: accepted, nothing beyond the plain definition; without: accepted"
          | (cs, ts) =>
              "with: accepted, " ^ string_of_int (length cs) ^ " constants and " ^ string_of_int (length ts) ^
              " types beyond; without: accepted")
      | (Exn.Exn e, Exn.Res _) => "with: " ^ refused e ^ "; without: accepted"
      | (Exn.Res _, Exn.Exn e) => "with: accepted; without: " ^ refused e
      | (Exn.Exn e, Exn.Exn e') => "with: " ^ refused e ^ "; without: " ^ refused e')
  in
    writeln ("ROW " ^ id ^ ": " ^ string_of_verdict verdict ^
      (case verdict of TAT_Lift_Definition_Command.Undecided => "" | _ => " || " ^ behaviour ()))
  end;
val T = ("", "");
val LOC = ("context L begin", "end");
val CLS = ("context cl begin", "end");
val LTC = ("context LT begin", "end");
val L3C = ("context L3 begin", "end");
val L4C = ("context L4 begin", "end");
val _ = row "01" T ("'a dlist \<Rightarrow> nat", "length");
val _ = row "02" T ("'a dlist \<Rightarrow> 'a dlist", "rev");
val _ = row "02b" T ("'a \<Rightarrow> 'a dlist \<Rightarrow> 'a dlist", "\<lambda>x xs. if x \<in> set xs then xs else x # xs");
val _ = row "03" LOC ("'a dlist \<Rightarrow> 'a dlist", "\<lambda>xs. if length xs < n then xs else tl xs");
val _ = row "04" T ("'a dlist \<Rightarrow> 'a dlist dlist", "\<lambda>xs::'a dlist. [xs]");
val _ = row "05" T ("'a dlist \<Rightarrow> 'a dlist pz", "\<lambda>xs. Suc (length xs)");
val _ = row "06" T ("nat \<Rightarrow> int dlist", "\<lambda>n. [int n]");
val _ = row "07" LOC ("nat \<Rightarrow> ('b \<Rightarrow> 'c) nn", "\<lambda>m (x::'b). (undefined::'c)");
val _ = row "08" T ("'a dlist \<Rightarrow> 'a dlist dlist", "\<lambda>xs. [xs]");
val _ = row "09" LOC ("'a dlist \<Rightarrow> 'a dlist dlist", "\<lambda>xs. if n = 0 then [] else [xs]");
val _ = row "10" CLS ("'b dlist \<Rightarrow> 'b dlist dlist", "\<lambda>xs. [xs]");
val _ = row "11" LTC ("'a dlist \<Rightarrow> 'a dlist dlist", "\<lambda>xs. if z \<in> set xs then [xs] else []");
val _ = row "12" T ("'a dlist \<Rightarrow> ('a dlist dlist \<Rightarrow> 'a dlist) option", "\<lambda>xs. Some (\<lambda>xss. xs)");
val _ = row "W05c" L4C ("nat \<Rightarrow> 'a dlist dlist", "\<lambda>m. if m = k then [] else [[]]");
val _ = row "W05" L3C ("nat \<Rightarrow> 'a dlist dlist", "\<lambda>m. if m = k then [] else [[]]");
val _ = row "13" T ("nat \<Rightarrow> ('a dlist dlist \<Rightarrow> nat) option", "\<lambda>n. Some (\<lambda>xss. n)");
val _ = row "14" T ("nat \<Rightarrow> nat fset fset", "\<lambda>n. [[n]]");
val _ = row "15" T ("nat \<Rightarrow> (('a dlist \<Rightarrow> nat) \<Rightarrow> 'b) wrap", "\<lambda>n (g::'a dlist \<Rightarrow> nat). (undefined::'b)");
val _ = row "16" T ("'a dlist \<Rightarrow> 'a dlist dlist option", "\<lambda>xs::'a dlist. Some [xs]");
val _ = row "17" T ("'a dlist \<Rightarrow> 'a dlist option", "\<lambda>xs. if xs = [] then None else Some (tl xs)");
val _ = row "18" T ("'a dlist \<Rightarrow> 'a fset", "\<lambda>xs. xs");
val _ = row "19" T ("'a dlist \<Rightarrow> ('a dlist \<times> 'a fset) option", "\<lambda>xs. Some (xs, xs)");
val _ = row "20" LOC ("nat \<Rightarrow> fnp", "\<lambda>m x. x * (m + n)");
val _ = row "21" T ("'a dlist \<Rightarrow> nat", "Suc");
val _ = writeln "CASES DONE";
"""


@pytest.mark.isabelle(deadline=600)
async def test_tat_lift_definition_command_s_search_sentence_and_refusals(std_harness, tmp_path):
    """§6 on a raw ML process on HOL, the structure's file evaluated inside
    a theory's context as the plugin's theory loads it: `needed`'s answers
    as the long names it returns — one set of one type, of two in the order
    of their first occurrence, a phantom parameter, none, and Rat.thy's own
    definition of `Fract`, where opening `int` too would not do —;
    `sentence`'s five forms verbatim from §6's fourth block — one set of
    one type a node's by typedef, one a node's by quotient_type, one not a
    node's, one set of two types on `needed`'s own answer, several sets on
    hand-given ones —; and the refusal path whole: the sentence for a
    `QUOT_THM` and for a `CHECK_RTY` the search answers, Isabelle's
    rendering of each when it does not — `hd xs`, for which the search
    answers a set only outside the context the command reads in.  Then
    `code_dt_verdict` on the panel's cases to pin (heuristic_judgment.json's
    21, with the verifier's W05 and its control, 23), called on each row's
    texts in the context its Isar text enters, without `quick_and_dirty`, as
    TAT runs: rows 1–7 not needed, the option accepted and declaring
    nothing beyond the plain definition; without effect — rows 8–12 and
    W05's control, a composition, the option refused, "Composition of
    abstract types has not been implemented yet."; W05, inside an
    interpreted locale whose `rewrites` turns the abstraction function
    into a plain constant, and rows 13–15, whose plain definition already
    has a code equation, accepted and declaring nothing; row 18, one lift
    of `fset`, no subtype, refused, `code_dt: "Verdicts.fset" was not
    defined as a subtype.` —; rows 16, 17 and 19 undecided, a constructor
    step with no composition, row 20, where the walk raises, and row 21,
    where `prove_quot_thm` raises."""
    cases = tmp_path / "lift_definition_cases.ML"
    cases.write_text(AFTER + CASES)
    r = await ml_process(std_harness, f"val _ = in_theory thy0 [{ml_string(str(COMMAND_ML))}, {ml_string(str(cases))}];")
    lines = r.stdout.splitlines()
    assert r.returncode == 0 and "CASES DONE" in lines, (r.stdout, r.stderr)
    [_, _, _, sentences, _] = fenced_blocks(LD, "6.")
    assert [line for line in lines if line.startswith(("needed ", "sentence ", "refusal "))] == [
        "needed rev: [[Probe.dlist]]", "needed int_swap: [[Int.int]]", "needed dl_two: [[Probe.dlist, Code_Numeral.natural]]",
        "needed ph: [[Probe.ph]]", "needed dl_int: NONE", "needed fract: [[Rat.rat]]",
        *(f"sentence {i}: {sentence}" for i, sentence in enumerate(sentences, 1)),
        "refusal dl_two: " + sentences[3],
        "refusal ph: The lifting of `natural ph` is not open here. Place this lift_definition under the typedef that"
        " defines `ph`, or under a lifting_context opening `ph`.",
        "refusal dl_hd: Lifting failed for the following types:",
        "refusal dl_int: Lifting failed for the following term:"]
    accepted = "with: accepted, nothing beyond the plain definition; without: accepted"
    composition = "with: refused (Composition of abstract types has not been implemented yet.); without: accepted"
    no_subtype = 'with: refused (code_dt: "Verdicts.fset" was not defined as a subtype.); without: accepted'
    assert [line for line in lines if line.startswith("ROW ")] == [
        *(f"ROW {row}: not needed || {accepted}" for row in ("01", "02", "02b", "03", "04", "05", "06", "07")),
        *(f"ROW {row}: without effect || {composition}" for row in ("08", "09", "10", "11", "12", "W05c")),
        f"ROW W05: without effect || {accepted}",
        *(f"ROW {row}: without effect || {accepted}" for row in ("13", "14", "15")),
        "ROW 16: undecided", "ROW 17: undecided",
        f"ROW 18: without effect || {no_subtype}",
        *(f"ROW {row}: undecided" for row in ("19", "20", "21"))]
