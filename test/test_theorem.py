"""`Theorem` (node_classes/THEOREM.md): with no Isabelle, the schema and the
descriptions, `gen`'s checks and refusals, the statement as the node
holds, stores and prints it, the mark's eleven ways, the jobs' sentences
and `_check()`, §8's examples, the emitted text, the goal slot's place
among the node's slots, the carry on an amend; through the std harness,
the evaluation (§6) and a theorem constructed, checked, invalidated and
constructed again (§7).
Run: python -m pytest test/test_theorem.py
"""

import io
import re

import jsoncomment
import pytest

import stand_ins
import test_model as tm
import test_session_theory as ts
from baselines import DOCS, fenced_blocks, fenced_lines
from Isabelle_RPC_Host.unicode import IsaTerm, ascii_of_unicode, is_identifier
from invariants import assert_invariants, assert_store_mirrors
from harness import text_of, until
from isabelle_theory_agent import compile as C, edit, isabelle_driver, jobs, model as M, plugin
from isabelle_theory_agent.exceptions import InvalidField, InvalidName, RawASTError, TAT_InternalError
from isabelle_theory_agent.jobs import NOT_STARTED, PASSED, RUNNING, Failed, Succeeded
from isabelle_theory_agent.std import common, statement, theorem
from isabelle_theory_agent.std.common import Proof_Check, Proof_Job, Proof_Obligation
from isabelle_theory_agent.std.theorem import Statement, Theorem
from isabelle_theory_agent.store import Forest_Store
from test_compile import listing
from test_descriptions import descriptions
from std_forest import KINDS, forest, insert, inv, refused
from test_launcher import compiled, leave, tat_new
from test_model import locked, run, slot
from test_session_theory import Forest_Under_Test, session, theory

table = ts.table                    # the fake state slot table and the fake wire, per test
TH = DOCS / "node_classes" / "THEOREM.md"
COMMON = DOCS / "node_classes" / "COMMON.md"


def lemma(name, conclusion="length (rev xs) = length xs", english="The length of a reversed list",
          for_any=({"name": "xs", "type": "'a list"},), premises=({"name": "ne", "term": "xs ≠ []"},),
          kind="lemma"):
    return {"kind": kind, "name": name, "statement": {
        "english": english, "for_any": list(for_any), "premises": list(premises), "conclusion": conclusion}}


# --- the schema and the descriptions (§2, §3) ------------------------------

def test_the_schema_and_the_descriptions_are_the_documents(monkeypatch):
    [schema] = fenced_blocks(TH, "2.")[1:2]
    expected = jsoncomment.JsonComment().loads(
        "\n".join(schema).replace("STATEMENT_DEFS", "{}"))
    expected["$defs"] = statement.STATEMENT_DEFS
    assert Theorem.construct_schema == expected
    assert list(theorem.KINDS) == ["lemma", "theorem", "corollary", "proposition"]
    monkeypatch.setitem(plugin.imports, "Other.Thy", __name__)        # another package's: not the plugin's
    loaded = plugin.load(["isabelle_theory_agent.std"])
    assert loaded.imports == ("TAT_Std.TAT_Std",) and loaded.kinds["lemma"] is Theorem
    long = fenced_lines(TH, "3.")
    assert sorted(descriptions(Theorem.construct_schema)) == sorted(long + [long[-1]])   # the last twice (§3)


# --- `gen` (§4) --------------------------------------------------------------

def test_gen_keeps_the_statement_normalised_as_isaterms():
    """§2: every piece of Isabelle text — the names too — and `english`
    normalised once."""
    f, x = forest(lemma("rev_length", conclusion="length  (rev xs)\n= length xs", english="The length\nof a list",
                        for_any=({"name": " xs ", "type": "'a\n list"},), premises=({"name": "ne\t", "term": "xs ≠ []"},)))
    (p,) = x.sub_nodes
    assert isinstance(p, Theorem) and (p.kind, p.name) == ("lemma", "rev_length")
    assert p.statement.english == "The length of a list"
    assert p.statement.conclusion.unicode == "length (rev xs) = length xs"
    assert p.statement.conclusion.ascii == "length (rev xs) = length xs"
    [v] = p.statement.for_any
    assert (v.name.unicode, v.type.unicode) == ("xs", "'a list")
    [ne] = p.statement.premises
    assert (ne.name.unicode, ne.term.unicode, ne.term.ascii) == ("ne", "xs ≠ []", "xs \\<noteq> []")
    assert isinstance(p, Proof_Obligation) and p.goal_state is not p.state
    assert p.goal_state in p._states_inside() and p._slots_written_by(None) == (p.goal_state,)
    assert f.id_of(p) == "lemma_rev_length" and p.statement.structure() == (
        [("xs", "'a list")], [("ne", "xs \\<noteq> []")], "length (rev xs) = length xs")
    assert p.goal_structure() == p.statement.structure()                 # COMMON §3; §4, §6
    assert p.message() == ("lemma", "rev_length", *p.goal_structure())
    inv(f)
    # an untyped variable, no premises
    (q,) = insert(f, x, 1, [lemma("q", for_any=({"name": "n"},), premises=())])
    assert q.statement.for_any[0].type is None and q.statement.premises == ()


def test_gen_refuses_as_section_4_says():
    """§4's refusals: the fact name's grammar
    (RENDER_BASELINES §2's line), the identifiers and the repeated names (TH
    §4's fenced lines)."""
    f, x = forest()
    identifier, binds = fenced_lines(TH, "4.")
    [invalid] = [line for line in fenced_lines(DOCS / "RENDER_BASELINES.md", "2.")
                 if line.startswith("`rev-length` is not a valid fact name")]
    e = refused(f, x, [lemma("rev-length")], InvalidName)
    assert (e.name, e.grammar) == ("rev-length", "fact name") and str(e) == "At `constructs[0]`: " + invalid
    for name in ("1st", "rev_", "rev length", "x'y-"):
        assert refused(f, x, [lemma(name)], InvalidName).grammar == "fact name"     # the class's sentence, not the framework's
    for name in ("1x", "x_", "x y"):                       # one sentence, the grammar text the fact name's
        e = refused(f, x, [lemma("p", for_any=({"name": name},))], InvalidField)
        assert str(e) == "At `constructs[0]`: " + identifier and e.field == "statement.for_any[0].name", name
    assert identifier.endswith(": it " + invalid.split(": a fact name ")[1])
    e = refused(f, x, [lemma("p", premises=({"name": "ne", "term": "a"}, {"name": "ne", "term": "b"}))],
                InvalidField)
    assert str(e) == "At `constructs[0]`: " + binds and e.field == "statement.premises[1].name"
    e = refused(f, x, [lemma("p", for_any=({"name": "xs"}, {"name": "xs"}))], InvalidField)
    assert (e.field, e.reason) == ("statement.for_any[1].name", "repeats `xs`")
    e = refused(f, x, [lemma("p", premises=({"name": "x y", "term": "a"},))], InvalidField)
    assert e.field == "statement.premises[0].name"
    (h,) = insert(f, x, 0, [lemma("h", premises=({"name": "h_", "term": "a"},))])     # a premise may end so
    assert h.statement.premises[0].name.unicode == "h_"
    run(locked(f, edit.delete(h)))
    refused(f, x, [{"kind": "lemma", "name": "p", "statement": {"english": "e"}}], RawASTError)
    assert x.sub_nodes == []
    inv(f)


def test_the_identifier_grammar():
    """§4, COMMON §5: a letter or one of Isabelle's own letter symbols, then
    letters, digits, underscores, primes, and `\\<^sub>` before one of
    those, on the `ascii` form."""
    for good in ("xs", "x'", "x_1", "x_", "\\<epsilon>", "x\\<^sub>1", "x\\<^sub>i'", "\\<alpha>\\<beta>",
                 "x\\<^sub>_", "x\\<^sub>_a", "\\<AA>", "\\<bb>x"):
        assert is_identifier(good), good
    for bad in ("", "1x", "x-y", "x y", "_x", "x\\<^sub>", "'x", "x.y", "\\<noteq>",
                "h\\<nat>", "x\\<lambda>", "a\\<bbbA>", "f\\<real>"):     # letters are Isabelle's own list, not the symbol files'
        assert not is_identifier(bad), bad
    assert is_identifier(IsaTerm.from_agent("ε").ascii) and is_identifier(IsaTerm.from_agent("x⇩1").ascii)


def test_an_amend_with_the_same_structure_carries_the_proof():
    """§4: equal `for_any`, `premises` and `conclusion` — names included;
    `english`, `kind` and `name` aside — carry the replaced job's outcome;
    a changed structure does not; the stored check is never carried
    (CONSTRUCT_INTERACTION §3.1)."""
    f, x = forest(lemma("p"))
    (p,) = x.sub_nodes
    with_proof(p, M.READY_CLEAN, PROVED, PASSED)
    (p2,) = run(locked(f, edit.amend(p, [lemma("p", english="Another wording")])))
    assert p2.job().outcome == PROVED and p2.check_outcome() is None and p2.statement.english == "Another wording"
    (p3,) = run(locked(f, edit.amend(p2, [lemma("q", kind="theorem")])))
    assert p3.job().outcome == PROVED and (p3.kind, p3.name) == ("theorem", "q")
    (p4,) = run(locked(f, edit.amend(p3, [lemma("q", kind="theorem", conclusion="rev (rev xs) = xs")])))
    assert p4.job().outcome is NOT_STARTED
    p4.job().outcome = PROVED
    (p5,) = run(locked(f, edit.amend(p4, [lemma("q", kind="theorem", conclusion="rev (rev xs) = xs",
                                                premises=({"name": "nonempty", "term": "xs ≠ []"},))])))
    assert p5.job().outcome is NOT_STARTED                  # a premise renamed, its term unchanged
    p5.job().outcome = PROVED
    (p6,) = run(locked(f, edit.amend(p5, [lemma("q", kind="theorem", conclusion="rev (rev xs) = xs",
                                                premises=({"name": "nonempty", "term": "xs ≠ []"},),
                                                for_any=({"name": "xs", "type": "nat list"},))])))
    assert p6.job().outcome is NOT_STARTED                  # a variable's type changed
    inv(f)


# --- the store (§1) ------------------------------------------------------------

def test_the_statement_is_stored_the_goal_slot_fresh(tmp_path):
    store = Forest_Store(tmp_path / "TAT.sqlite", ts.stand_ins.log())
    f, x = forest(lemma("p"), store=store)
    (p,) = x.sub_nodes
    with f.store.transaction():
        f._store_node(p)
    before = (p.statement, p.goal_state.name)
    store.close()
    f2 = Forest_Under_Test(store=Forest_Store(tmp_path / "TAT.sqlite", ts.stand_ins.log()), kinds=KINDS)
    (p2,) = f2.sub_nodes[0].sub_nodes[0].sub_nodes
    assert isinstance(p2, Theorem) and p2.statement == before[0]
    assert p2.goal_state.name != before[1] and p2.goal_state in p2._states_inside()


# --- what it prints (§7, §8) --------------------------------------------------

def test_print_fields_writes_the_proposition_and_english_by_depth():
    f, x = forest(lemma("rev_length"))
    (p,) = x.sub_nodes
    [proposition, english] = fenced_blocks(TH, "8.")[0]

    def fields(mode, depth):
        out = io.StringIO()
        p.print_fields(0, out, mode, depth)
        return out.getvalue().splitlines()
    assert [fields(M.RECALL, d) for d in range(4)] == [[proposition, english], [proposition, english],
                                                      [proposition], []]
    assert fields(M.OUT_FOCUS, 0) == [] and fields(M.Relative_Focus(frozenset({p}), 0), 0) == []
    # a part holding `⋀` or `⟹` in either spelling is parenthesised; one `⋀` per variable
    two = Statement("e", (statement.Variable(IsaTerm.from_agent("x"), None),
                          statement.Variable(IsaTerm.from_agent("y"), IsaTerm.from_agent("nat"))),
                    (statement.Premise(IsaTerm.from_agent("h"), IsaTerm.from_agent("⋀z. P z ⟹ Q z")),),
                    IsaTerm.from_agent("A \\<Longrightarrow> B"))
    assert two.proposition() == "⋀x. ⋀y::nat. (⋀z. P z ⟹ Q z) ⟹ (A \\<Longrightarrow> B)"


INVALID = M.CannotEvaluate((IsaTerm.from_agent("no"),))
PROVED = Succeeded({"text": "by simp", "thread_cpu": 3, "wall": 5})
BAD = Failed("")                                         # a failed check: its message is empty (COMMON §3)


def with_proof(node, status, outcome, check=None):
    """The node in one of §7's states: the status of its `job_operation`'s
    operation — a leaf's `_status`, a block's `evaluation_status_beginning`
    —, its proof's outcome, its check — None, `RUNNING` (a running
    `Proof_Check` on the node), `PASSED` or `FAILED`."""
    operation = type(node).job_operation
    setattr(node, "_status" if operation is None else f"evaluation_status_{operation}", status)
    node.job().outcome = outcome
    node._evaluation_job = Proof_Check(node, None) if check is RUNNING else None
    node._check_outcome = check if check in (PASSED, BAD) else None


def assert_the_eleven_ways(node, block, owing_line):
    """§7 of a class that defines, state by state — COMMON §3's table with
    its three words: `valid definition` alone once the proof stands,
    `unverified definition` with the proof's word before, `invalid
    definition`, the three `not evaluated` ways; the eleven, and no other,
    are the document's `block`; `owing_line()` answers `owing_line` exactly
    while the line reads `unverified definition`."""
    assert node.mark(M.BRIEFING, 0) == "not evaluated, proof not started" and node.owing_line() is None
    proof = [(NOT_STARTED, None, "proof not started"), (RUNNING, None, "proving"), (Failed("no"), None, "failed to prove"),
             (PROVED, None, "unchecked proof"), (PROVED, RUNNING, "proof checking"), (PROVED, PASSED, None),
             (PROVED, BAD, "bad proof")]
    marks = set()
    for outcome, check, word in proof:
        with_proof(node, M.READY_CLEAN, outcome, check)
        expected = "valid definition" if word is None else f"unverified definition, {word}"
        assert node.mark(M.BRIEFING, 0) == expected, (outcome, check)
        assert node.owing_line() == (None if word is None else owing_line), (outcome, check)
        marks.add(f"({expected})")
        with_proof(node, INVALID, outcome, check)
        assert node.mark(M.BRIEFING, 0) == "invalid definition" and node.owing_line() is None, (outcome, check)
        marks.add("(invalid definition)")
        if outcome is not RUNNING and check is None:    # no run and no check live under `not evaluated`
            with_proof(node, M.NOT_EVALUATED, outcome, check)
            expected = "not evaluated" if outcome is PROVED else f"not evaluated, {word}"
            assert node.mark(M.BRIEFING, 0) == expected and node.owing_line() is None, (outcome, check)
            marks.add(f"({expected})")
    assert len(marks) == 11 and marks == set(re.findall(r"\([^)]*\)", "\n".join(block)))


def test_the_mark_reads_one_of_eleven_ways():
    """§7's mark, state by state: the statement slot from the status, the
    proof slot from the outcome and the check — COMMON §3's table —, left out
    under `invalid statement`, a stored proof left out under `not
    evaluated`; the eleven, and no other, are the document's block."""
    [block] = fenced_blocks(TH, "7.")
    f, x = forest(lemma("p"))
    (p,) = x.sub_nodes
    assert p.mark(M.BRIEFING, 0) == "not evaluated, proof not started"
    proof = [(NOT_STARTED, None, "proof not started"), (RUNNING, None, "proving"), (Failed("no"), None, "failed to prove"),
             (PROVED, None, "unchecked proof"), (PROVED, RUNNING, "proof checking"), (PROVED, PASSED, "proven"),
             (PROVED, BAD, "bad proof")]
    marks = set()
    for outcome, check, word in proof:
        with_proof(p, M.READY_CLEAN, outcome, check)
        assert p.mark(M.BRIEFING, 0) == f"valid statement, {word}", (outcome, check)
        marks.add(f"(valid statement, {word})")
        with_proof(p, INVALID, outcome, check)
        assert p.mark(M.BRIEFING, 0) == "invalid statement", (outcome, check)
        marks.add("(invalid statement)")
        if outcome is not RUNNING and check is None:    # no run and no check live under `not evaluated`
            with_proof(p, M.NOT_EVALUATED, outcome, check)
            expected = "not evaluated" if outcome is PROVED else f"not evaluated, {word}"
            assert p.mark(M.BRIEFING, 0) == expected, (outcome, check)
            marks.add(f"({expected})")
    assert len(marks) == 11 and marks == set(re.findall(r"\([^)]*\)", "\n".join(block)))


def test_the_jobs_sentences_are_common_section_3_s():
    """`Proof_Job`'s and `Proof_Check`'s words: the titles, the two
    notifications, the failure headers, the check's failure block — the
    header alone, its colon a period — and the notification's forms for
    one, three and four nodes, with and without automatic construction,
    COMMON §3's lines verbatim."""
    [sentences, automatic] = fenced_blocks(COMMON, "3.")
    f, x = forest(lemma("p"))
    (p,) = x.sub_nodes
    job = p.job()
    assert (Proof_Job.title(), Proof_Job.title(plural=True)) == ("proof construction", "proof constructions")
    assert (Proof_Check.title(), Proof_Check.title(plural=True)) == ("proof check", "proof checks")
    assert job.finished_notification(PROVED) == f"`{f.id_of(p)}` is proven."
    assert job.finished_notification(Failed("no proof")) == f"No proof of `{f.id_of(p)}` was found:\n  no proof"
    assert job.failure_header(Failed("no proof")) == "No proof was found:"
    assert job.failure_header(Failed("no proof", "surrender")) == "No proof was found:"
    # the agent's refutation: THEOREM §7's refutation sentence in both
    assert job.finished_notification(Failed("no proof", "refute")) == f"`{f.id_of(p)}` may not hold:\n  no proof"
    assert job.failure_header(Failed("no proof", "refute")) == f"`{f.id_of(p)}` may not hold:"
    assert jobs.with_message(Proof_Check.failure_header(BAD), "") == sentences[0]
    one, three = ["theory_X.lemma_P"], ["theory_X.lemma_P", "theory_X.lemma_Q", "theory_X.lemma_R"]
    four = three + ["theory_Y.lemma_S"]
    assert Proof_Check.failure_notification(one, False) == sentences[1]
    assert Proof_Check.failure_notification(three, False) == sentences[2]
    assert Proof_Check.failure_notification(four, False) == "\n".join(sentences[3:8])
    one, three = ["theory_X.lemma_C"], ["theory_X.lemma_C", "theory_X.lemma_G", "theory_X.lemma_K"]
    four = three + ["theory_X.lemma_M"]
    assert Proof_Check.failure_notification(one, True) == automatic[0]
    assert Proof_Check.failure_notification(three, True) == automatic[1]
    assert Proof_Check.failure_notification(four, True) == "\n".join(automatic[2:7])
    passed = Proof_Check.passed(p)
    assert passed.outcome is PASSED and passed.starter is None and passed.node is p


def test_the_construction_reads_the_report_and_keeps_a_give_ups_kind():
    """COMMON §3: `Proof_Job._run` calls `TAT.Proof_Obligation.construct`
    with the goal slot and the empty setup; the report's errors are the
    failure's message, of no kind, nothing attached; the agent's give-up
    the failure of its reason's kind, so that the header reads the
    refutation sentence; the proof the product, a `PASSED` check attached."""
    f, x = forest(lemma("p"))
    (p,) = x.sub_nodes
    job = p.job()
    calls, report = [], {}

    async def forked(name, args):
        calls.append((name, args))
        return report["value"]
    job.forked = forked
    report["value"] = (["e1", "e2"], None)
    assert run(job._run()) == Failed("e1\ne2") and p.check_outcome() is None
    assert calls == [("TAT.Proof_Obligation.construct", (p.goal_state.to_msgpack(), common.NO_SETUP))]
    report["value"] = ([], ["gave_up", ["refute", "w"]])              # the lists msgpack delivers
    outcome = run(job._run())
    assert outcome == Failed("w", "refute") and p.check_outcome() is None
    assert job.failure_header(outcome) == f"`{f.id_of(p)}` may not hold:"
    report["value"] = ([], ["proof", ["by simp", 1, 2]])
    assert run(job._run()) == Succeeded({"text": "by simp", "thread_cpu": 1, "wall": 2})
    assert p.check_outcome() is PASSED


@pytest.mark.parametrize("product", [("bogus",), ["gave_up", ["refute"]], ["gave_up", ["refute", 3]], ["proof"], None])
def test_a_construction_report_of_no_known_shape_is_a_bug(product):
    with pytest.raises(TAT_InternalError, match="not a construction's report"):
        common.construction_from_wire([], product)


def test_check_answers_common_section_3_s_table():
    """`_check()`: true with no proof — `NOT_STARTED` or `FAILED`; on a
    proof, true only when its check `FAILED`; `can_start()` false off
    `ready` whatever `_check()` says, and false while `RUNNING`."""
    f, x = forest(lemma("p"))
    (p,) = x.sub_nodes
    job = p.job()
    for status in (M.NOT_EVALUATED, INVALID):
        for outcome, check in ((NOT_STARTED, None), (Failed("no"), None), (PROVED, BAD), (PROVED, PASSED)):
            with_proof(p, status, outcome, check)
            assert not job.can_start()
    for outcome, check, answer in ((NOT_STARTED, None, True), (Failed("no"), None, True), (PROVED, PASSED, False),
                                   (PROVED, None, False), (PROVED, RUNNING, False), (PROVED, BAD, True)):
        with_proof(p, M.READY_CLEAN, outcome, check)
        assert job._check() is answer, (outcome, check)
        assert job.can_start() is answer
    with_proof(p, M.READY_CLEAN, RUNNING)
    assert job._check() and not job.can_start()


def test_what_it_prints_with_a_job_is_section_8_s_four_examples():
    """§8's examples: the line with a question waiting, for the owner; a
    focus after a failed proof construction, the failure block below,
    and after the agent refuted the statement, the refutation sentence
    over the agent's own words; a node under `recall` whose stored proof failed its
    check, the header alone with a period — the document's blocks
    verbatim."""
    [_, asking, failed, refuted, bad] = fenced_blocks(TH, "8.")
    f, x = forest(lemma("rev_length"))
    (p,) = x.sub_nodes
    me = stand_ins.agent(f.conversation)
    job = p.job()
    with_proof(p, M.READY_CLEAN, RUNNING)
    job.owner = me
    job._questions.append(jobs._Pending(object(), None))                    # a question waiting for its owner
    assert f.render(p, M.Relative_Focus(frozenset([p]), 0), me).splitlines() == asking
    job._questions.clear()
    with_proof(p, M.READY_CLEAN, Failed(
        "Sledgehammer timed out on every prover; the goal needs an induction the search did not attempt."))
    assert f.render(p, M.Relative_Focus(frozenset([p]), 0), me).splitlines() == failed
    with_proof(p, M.READY_CLEAN, Failed(refuted[-1].strip(), "refute"))
    assert f.render(p, M.Relative_Focus(frozenset([p]), 0), me).splitlines() == refuted
    with_proof(p, M.READY_CLEAN, PROVED, BAD)
    assert f.render(p, M.RECALL, me).splitlines() == bad


# --- emission (§5) -----------------------------------------------------------

def test_the_emitted_text_is_section_5_s_with_sorry_until_the_proof_is_checked():
    [lines] = fenced_blocks(TH, "5.")
    f, x = forest(lemma("rev_length"))
    (p,) = x.sub_nodes
    x.keywords = frozenset()                                 # recorded by a header run, which emission presupposes

    def emitted(node) -> list[str]:
        """In the `unicode` spelling (§5); the file's `\\<name>` form is the compile's conversion (COMPILATION §2)."""
        out = io.StringIO()
        assert node.emit(1, out) == 1
        return out.getvalue().splitlines()

    def expected(*unicode_lines: str) -> list[str]:
        return list(unicode_lines)
    assert emitted(p) == expected(*("  " + line for line in lines[:-1]), "    sorry")
    with_proof(p, M.READY_CLEAN, PROVED, PASSED)                                         # proven: the document's block whole
    assert emitted(p) == expected(*("  " + line for line in lines))
    for outcome, check in ((PROVED, BAD), (PROVED, None), (PROVED, RUNNING), (Failed("no"), None)):
        with_proof(p, M.READY_CLEAN, outcome, check)                                     # not proven: `sorry`
        assert emitted(p)[-1] == "    sorry", (outcome, check)
    with_proof(p, M.NOT_EVALUATED, NOT_STARTED)
    x.keywords = frozenset({"rev_length", "xs", "ne"})       # keywords of the theory: quoted (§5)
    assert emitted(p)[1:5] == expected('  lemma "rev_length":', '    fixes "xs" :: "\'a list"',
                                       '    assumes "ne": "xs ≠ []"', '    shows "length (rev xs) = length xs"')
    (q,) = insert(f, x, 1, [lemma("q", english="Ends with a question? ‹Quoted› \\<open>here\\<close>",
                                  for_any=({"name": "n"},), premises=())])
    assert emitted(q) == expected('  text ‹Lemma q. Ends with a question? "Quoted" "here".›', "  lemma q:",
                                  "    fixes n", '    shows "length (rev xs) = length xs"', "    sorry")
    (r,) = insert(f, x, 2, [lemma("r", english="Bang!", kind="corollary", for_any=(), premises=())])
    assert emitted(r)[:2] == expected("  text ‹Corollary r. Bang!›", "  corollary r:")
    # every piece of Isabelle text through the theory's `print_name` (§5): a string token
    # (COMPILATION.md §3) unless an identifier that is no keyword
    (t,) = insert(f, x, 3, [lemma("t", conclusion='v = "q"', for_any=({"name": "v", "type": 'foo "bar"'},),
                                  premises=({"name": "h", "term": 'v \\<noteq> "r"'},))])
    assert emitted(t)[2:5] == expected('    fixes v :: "foo \\"bar\\""', '    assumes h: "v \\<noteq> \\"r\\""',   # as authored
                                       '    shows "v = \\"q\\""')
    (u,) = insert(f, x, 4, [lemma("u", conclusion="True", for_any=({"name": "v", "type": "'a"},),
                                  premises=({"name": "h", "term": "P"},))])
    assert emitted(u)[2:5] == expected('    fixes v :: "\'a"', "    assumes h: P", "    shows True")


def test_a_compile_writes_section_5_s_text_and_the_hook_removes_the_proof_stores_of_no_tree(monkeypatch):
    """A compile with the package's hook (COMPILATION.md §5): a theory of a
    proven, an unchecked and an unproven theorem is written with `by aoa`,
    `sorry`, `sorry`; each `<T>.proof-store` and `<T>.proof-store.*` the
    path listing yields whose folder and `T` are no tree's goes — a lock, a
    temporary file, a link, a store in the wrong folder —, a tree's stay, an
    unwritten tree's included, and nothing else is touched: not a `.thy`,
    not a folder of that name, not a `.proof-cache`, not a name that
    continues `.proof-store` without a dot, not a link's target."""
    assert common.remove_proof_stores_of_no_tree in plugin.compile_hooks         # registered at import
    [lines] = fenced_blocks(TH, "5.")
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        lemma("rev_length"), lemma("unchecked"), lemma("unproven")]}, theory("Y", kind="fake_theory"))])
    x, y = s.sub_nodes
    p, q, r = x.sub_nodes

    async def evaluate(conversation, name, args):
        assert name == "TAT.Theorem.evaluate"
        return [[], [None, None]]
    monkeypatch.setattr(isabelle_driver, "call", evaluate)
    run(x.evaluate_to(None, False))                                          # `Y` stays unevaluated: not written
    with_proof(p, M.READY_CLEAN, PROVED, PASSED)
    with_proof(q, M.READY_CLEAN, PROVED, None)

    directory = f.conversation.working_directory
    (directory / "Arith" / "Dir.proof-store").mkdir(parents=True)
    for file in ("Arith/.proof-store", "Arith/Dir.proof-store/keep", "Arith/Gone.proof-cache",
                 "Arith/Gone.proof-stored", "Arith/X.proof-cache", "Arith/X.proof-store",
                 "Arith/X.proof-store.lock", "Arith/Y.proof-store", "elsewhere"):
        (directory / file).write_text("kept")
    for file in ("Arith/Gone.proof-store", "Arith/Gone.proof-store.lock", "Arith/Gone.proof-store.tmp.123",
                 "Arith/notes.proof-store.txt", "X.proof-store"):
        (directory / file).write_text("of no tree")
    (directory / "Arith" / "Gone.proof-store.tmp.7").symlink_to("../elsewhere")     # the link goes, its target stays
    report = C.compile(f, [common.remove_proof_stores_of_no_tree])
    assert listing(directory) == [
        ("Arith/.proof-store", "file"),
        ("Arith/Dir.proof-store/keep", "file"), ("Arith/Dir.proof-store", "folder"),
        ("Arith/Gone.proof-cache", "file"), ("Arith/Gone.proof-stored", "file"),
        ("Arith/X.proof-cache", "file"), ("Arith/X.proof-store", "file"), ("Arith/X.proof-store.lock", "file"),
        ("Arith/X.thy", "file"), ("Arith/Y.proof-store", "file"), ("Arith", "folder"), ("ROOT", "file"),
        ("elsewhere", "file")]
    assert all((directory / path).read_text() == "kept" for path, kind in listing(directory)
               if kind == "file" and path not in ("Arith/X.thy", "ROOT"))
    assert [(str(e.path), e.kind) for e in report.removed] == [
        ("Arith/Gone.proof-store", "file"), ("Arith/Gone.proof-store.lock", "file"),
        ("Arith/Gone.proof-store.tmp.123", "file"), ("Arith/Gone.proof-store.tmp.7", "link"),
        ("Arith/notes.proof-store.txt", "file"), ("X.proof-store", "file")]
    assert report.trees == ((x, None), (y, C.Does_Not_Emit(y)))
    text = (directory / "Arith" / "X.thy").read_text()
    assert text == C.render(f).files[C.Path("Arith/X.thy")]                  # the hook left the file whole
    assert "\n".join(ascii_of_unicode(line) for line in lines) in text         # the document's block, proven
    assert [line for line in text.splitlines() if line in ("  by aoa", "  sorry")] == ["  by aoa", "  sorry", "  sorry"]


def test_the_store_mirror_catches_a_proof_text_read_off_an_instant_status(monkeypatch):
    """COMPILATION.md §3: `proof_text()` reads the job's image and the stored
    check, which a loaded forest holds too; one that reads an instant
    status writes `by aoa` in memory and `sorry` once loaded, which the
    package's helper says at once."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [lemma("p")]})])
    (x,) = s.sub_nodes
    (p,) = x.sub_nodes

    async def evaluate(conversation, name, args):
        return [[], [None, None]]
    monkeypatch.setattr(isabelle_driver, "call", evaluate)
    run(x.evaluate_to(None, False))
    with_proof(p, M.READY_CLEAN, PROVED, PASSED)
    p._store_alone()                                                         # as a settlement stores it
    assert_store_mirrors(f, shape=ts.shape)                           # `proof_text()` as shipped: mirrored
    monkeypatch.setattr(Theorem, "proof_text", lambda self: "by aoa" if all(
        isinstance(st, M.Ready) for st in self.evaluation_statuses()) else "sorry")
    with pytest.raises(AssertionError, match="Arith/X.thy: the loaded forest writes another text"):
        assert_store_mirrors(f, shape=ts.shape)


# --- the evaluation, in the plugin's run of the harness (§6, §8) -----------------

def over_the_wire(*theorems):
    """session_TAT_Suite > theory_TAT_Std_A > the theorems, as the `edit` tool takes them."""
    return ts.session("TAT_Suite", ts.theory("TAT_Std_A") | {"children": list(theorems)})


async def test_a_statement_is_admitted_and_a_bad_one_is_an_obstacle(std_conversation):
    """§6 through `TAT.Theorem.evaluate`: a theory of theorems built through
    `edit` and evaluated, each statement admitted — the `goal_state` slot
    holding the open goal and the resulting slot the admitted fact; a
    statement Isabelle refuses makes its node an obstacle with Isabelle's
    message, `goal_state` empty; the theory's keywords recorded, a name
    among them quoted at emission; the rows of §8 under `recall`; the
    plugin's declared import in the theory's header.
    Last, the callback alone: a failure empties a `goal_state` an earlier
    run had written."""
    forest = std_conversation.forest
    assert set(theorem.KINDS) <= set(forest.kinds)
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [over_the_wire(
                lemma("rev_length"),
                lemma("shows_it", for_any=({"name": "shows", "type": "'a list"},), premises=(),
                      conclusion="length (rev shows) = length shows", english="A reserved name"),
                lemma("clash", for_any=({"name": "xs", "type": "'a list"},), premises=(),
                      conclusion="xs = (0::nat)", english="Refused"))]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 1, text
        (s,) = forest.sub_nodes
        (x,) = s.sub_nodes
        p, q, r = x.sub_nodes
        assert x.import_sessions == ["HOL", "TAT_Std"]                 # the declared import ran
        for node in (p, q):
            assert isinstance(node._status, M.Ready) and node._status.messages == ()
            assert await node.goal_state.is_initialized() and await node.resulting_state().is_initialized()
        assert x.keywords is not None and {"shows", "lemma", "and"} <= x.keywords and "rev_length" not in x.keywords
        out = io.StringIO()
        q.emit(0, out)
        assert '  fixes "shows" :: "\'a list"' in out.getvalue().splitlines()   # a keyword as a name (§5)
        assert isinstance(r._status, M.CannotEvaluate) and not await r.goal_state.is_initialized()
        assert r._status.messages[0].unicode.startswith("Type unification failed"), r._status.messages
        recalled = await session.call_tool("recall", {"node_id": "theory_TAT_Std_A"})
        lines = text_of(recalled).splitlines()
        assert not recalled.isError and lines[:13] == [
            "- theory_TAT_Std_A (incomplete)",
            "  imports: Main",
            "  declarations:",
            "    - lemma_rev_length (valid statement, proof not started)",
            "      ⋀xs::'a list. xs ≠ [] ⟹ length (rev xs) = length xs",
            "      The length of a reversed list",
            "    - lemma_shows_it (valid statement, proof not started)",
            "      ⋀shows::'a list. length (rev shows) = length shows",
            "      A reserved name",
            "    - lemma_clash (invalid statement)",
            "      ⋀xs::'a list. xs = (0::nat)",
            "      Refused",
            "      Error:"], lines
        assert lines[13].startswith("        Type unification failed"), lines
    messages, what = await isabelle_driver.call(
        forest.conversation, "TAT.Theorem.evaluate",
        (p.state.to_msgpack(), p.goal_state.to_msgpack(), p.resulting_state().to_msgpack(),
         ("lemma", "again", [["xs", "'a list"]], [], "xs = (0::nat)")))
    assert messages and what is None                                         # `[[msgs], nil]` (COMMON.md §3)
    assert not await p.goal_state.is_initialized() and await p.resulting_state().is_initialized()
    messages, what = await isabelle_driver.call(                             # `[[], [a, b]]`: `Theorem` yields nothing twice
        forest.conversation, "TAT.Theorem.evaluate",
        (p.state.to_msgpack(), p.goal_state.to_msgpack(), p.resulting_state().to_msgpack(), p.message()))
    assert (messages, what) == ([], [None, None]) and await p.goal_state.is_initialized()
    messages, what = await isabelle_driver.call(                             # the second operation refused: `rev_length` is
        forest.conversation, "TAT.Theorem.evaluate",                         # a fact of the input state already, which only
        (p.resulting_state().to_msgpack(), p.goal_state.to_msgpack(),        # the admission records (COMMON §3: a failure
         p.resulting_state().to_msgpack(), p.message()))                     # anywhere empties `goal_state`)
    assert what is None and messages[0].startswith("Duplicate fact declaration"), messages
    assert not await p.goal_state.is_initialized() and await p.resulting_state().is_initialized()


async def test_an_undeclared_variable_is_refused(std_conversation):
    """§2, §6: a variable the premises or the conclusion use that `for_any`
    does not declare — Isabelle fixed it by itself — makes the statement
    an obstacle, `goal_state` empty, with §6's sentence naming the
    variables in alphabetical order; a declared but unused one is not."""
    forest = std_conversation.forest
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [over_the_wire(
                lemma("one", for_any=(), premises=(), conclusion="rev (rev ys) = ys", english="One"),
                lemma("two", for_any=({"name": "xs", "type": "'a list"},),
                      premises=({"name": "ne", "term": "zs ≠ []"},),
                      conclusion="rev (rev ys) = ys", english="Two, one of them in a premise"),
                lemma("unused", for_any=({"name": "xs", "type": "'a list"}, {"name": "n", "type": "nat"}),
                      premises=(), conclusion="rev (rev xs) = xs", english="A declared variable unused"))]})
        assert not result.isError and "evaluation stopped at lemma_one" in text_of(result), text_of(result)
        result = await session.call_tool("evaluate_to", {"node_id": "theory_TAT_Std_A", "ignore_error": True})
        assert not result.isError, text_of(result)
        (s,) = forest.sub_nodes
        (x,) = s.sub_nodes
        one, two, unused = x.sub_nodes
        assert isinstance(one._status, M.CannotEvaluate) and not await one.goal_state.is_initialized()
        assert [m.unicode for m in one._status.messages] == ["Undeclared variable `ys`: declare it in `for_any`."]
        assert isinstance(two._status, M.CannotEvaluate)
        assert [m.unicode for m in two._status.messages] == [
            "Undeclared variables `ys` and `zs`: declare them in `for_any`."]
        assert isinstance(unused._status, M.Ready) and unused._status.messages == ()


@pytest.mark.isabelle(deadline=300)
async def test_a_theorem_is_constructed_checked_invalidated_and_constructed_again(std_conversation):
    """§7 through the two callbacks, on a goal Sledgehammer's automation
    closes without the agent: `construct` starts the proof construction,
    which settles `SUCCEEDED` with the proof and its times and attaches a
    `PASSED` check, after which `construct` starts nothing; invalidated,
    `goal_state` empty, and evaluated with checks, the node gets a proof
    check that replays the product and passes; a product that no longer
    proves the goal fails its check with an empty message, the
    notification sending the agent to `construct`, which proves the node
    again; under automatic construction the failed check starts it
    itself, the notification saying so."""
    forest = std_conversation.forest
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [over_the_wire(
                lemma("rev_rev", for_any=({"name": "xs", "type": "'a list"},), premises=(),
                      conclusion="rev (rev xs) = xs", english="Reversing twice is the identity"))]})
        assert not result.isError, text_of(result)
        (s,) = forest.sub_nodes
        (x,) = s.sub_nodes
        (p,) = x.sub_nodes
        result = await session.call_tool("construct", {"node_ids": ["lemma_rev_rev"]})
        assert not result.isError and "Started the proof construction on `lemma_rev_rev`" in text_of(result)
        job = p.job()
        assert job.outcome is RUNNING and p.mark(M.BRIEFING, 0) == "valid statement, proving"
        await until(lambda: job.outcome is not RUNNING, "the proof construction's outcome", 240.0)
        assert isinstance(job.outcome, Succeeded), job.outcome
        product = job.outcome.product
        assert set(product) == {"text", "thread_cpu", "wall"} and product["text"]
        assert all(isinstance(product[k], int) and product[k] >= 0 for k in ("thread_cpu", "wall"))
        assert p.check_outcome() is PASSED and p.mark(M.BRIEFING, 0) == "valid statement, proven"
        result = await session.call_tool("check_construct", {})
        assert "`lemma_rev_rev` is proven." in text_of(result), text_of(result)
        proven = job.outcome
        result = await session.call_tool("construct", {"node_ids": ["lemma_rev_rev"]})
        assert text_of(result).startswith("No construction job was started."), text_of(result)
        assert job.outcome is proven and p.check_outcome() is PASSED   # proven: `_check()` says no
        # invalidated: the check is cleared, the goal gone; an evaluation with checks replays the product
        await tm._invalidate(p)
        assert p.check_outcome() is None and p.mark(M.BRIEFING, 0) == "not evaluated"
        assert not await p.goal_state.is_initialized()
        result = await session.call_tool("evaluate_to", {"node_id": "theory_TAT_Std_A", "checks": "blocking"})
        assert not result.isError, text_of(result)
        assert p.check_outcome() is PASSED and p.mark(M.BRIEFING, 0) == "valid statement, proven"
        # a product that no longer proves the goal: the check fails with an empty message
        bad = Succeeded({**product, "text": "(rule refl)"})
        job.outcome = bad
        await tm._invalidate(p)
        result = await session.call_tool("evaluate_to", {"node_id": "theory_TAT_Std_A", "checks": "blocking"})
        assert p.check_outcome() == Failed("") and p.mark(M.BRIEFING, 0) == "valid statement, bad proof"
        text = text_of(result)
        assert "The proof of `lemma_rev_rev` no longer holds. Call `construct` to prove it again." in text, text
        assert job.can_start()
        result = await session.call_tool("construct", {"node_ids": ["lemma_rev_rev"]})
        assert not result.isError, text_of(result)
        await until(lambda: job.outcome is not RUNNING, "the proof construction's outcome", 240.0)
        assert isinstance(job.outcome, Succeeded) and p.check_outcome() is PASSED
        assert p.mark(M.BRIEFING, 0) == "valid statement, proven"
        out = io.StringIO()
        p.emit(0, out)
        assert out.getvalue().splitlines()[-1] == "  by aoa"
        # under automatic construction, the failed check starts the construction itself
        job.outcome, job.auto_construct = bad, True
        await tm._invalidate(p)
        result = await session.call_tool("evaluate_to", {"node_id": "theory_TAT_Std_A", "checks": "blocking"})
        text = text_of(result)
        assert ("The proof of `lemma_rev_rev` no longer holds, so its proof construction was started"
                " automatically; call `check_construct` before you exit.") in text, text
        assert job.outcome is RUNNING and p.check_outcome() is None
        await until(lambda: job.outcome is not RUNNING, "the proof construction's outcome", 240.0)
        assert isinstance(job.outcome, Succeeded) and p.check_outcome() is PASSED


@pytest.mark.isabelle(deadline=300)
async def test_isabelle_tat_compile_writes_the_theory_and_isabelle_reads_it(std_harness, request, tmp_path):
    """`isabelle TAT_compile` on a directory made with the plugin (`TAT_new
    -P`, which the tool reads the plugin from) that a conversation of the
    plugin's run left, a theory of one theorem admitted: the file holds
    §5's text with `sorry` under the header carrying the declared import,
    the ROOT's `sessions` clause names `TAT_Std`, the package's hook
    ran in the tool's process — a proof store of no tree is gone —, and
    the tool's Isabelle read the ROOT and the header, the import resolved:
    exit 0."""
    wd = tmp_path / "wd"
    wd.mkdir()
    assert tat_new("-P", std_harness.plugin, str(wd)).returncode == 0
    await leave(std_harness, request, wd, "TAT_Std_C",
                ts.theory("TAT_Std_C_A") | {"children": [lemma("rev_length")]}, evaluate=1)
    (wd / "TAT_Std_C" / "Gone.proof-store").write_text("of no tree")
    r = await compiled(std_harness, str(wd))
    assert r.returncode == 0 and r.stderr == "", r
    assert r.stdout.splitlines()[1:] == [
        "TAT_Std_C/TAT_Std_C_A.thy written", "ROOT written", "removed TAT_Std_C/Gone.proof-store"]
    [lines] = fenced_blocks(TH, "5.")
    assert (wd / "TAT_Std_C" / "TAT_Std_C_A.thy").read_text() == (
        'theory "TAT_Std_C_A"\n  imports "Main" "TAT_Std.TAT_Std"\nbegin\n'
        + "".join(ascii_of_unicode(line) + "\n" for line in lines[:-1]) + "  sorry\nend\n")
    assert (wd / "ROOT").read_text() == (
        'session "TAT_Std_C" in "TAT_Std_C" = "HOL" +\n'
        '  sessions\n    "TAT_Std"\n  theories\n    "TAT_Std_C_A"\n')
