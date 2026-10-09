"""`Theorem` (node_classes/THEOREM.md): with no Isabelle, the schema and the
descriptions, `gen`'s checks and refusals, the statement as the node
holds, stores and prints it, the mark's eleven ways, the jobs' sentences
and `_check()`, §8's examples, the emitted text, the goal slot's place
among the node's slots, the carry on an amend; through the std harness,
the evaluation (§6) and a theorem constructed, checked, invalidated and
constructed again (§7).
Run: python -m pytest test/test_theorem.py
"""

import asyncio
import io
import re
import sys

import jsoncomment
import pytest

import stand_ins
import test_model as tm
import test_session_theory as ts
from baselines import DOCS, fenced_blocks, fenced_lines
from Isabelle_RPC_Host.unicode import IsaTerm, ascii_of_unicode, is_identifier
from invariants import assert_invariants, assert_store_mirrors
from harness import text_of
from isabelle_theory_agent import edit, isabelle_driver, jobs, model as M, plugin
from isabelle_theory_agent.exceptions import BadTheoremNodeParent, InvalidField, InvalidName, RawASTError
from isabelle_theory_agent.jobs import NOT_STARTED, PASSED, RUNNING, Failed, Succeeded
from isabelle_theory_agent.std import statement, theorem
from isabelle_theory_agent.std.theorem import Proof_Check, Proof_Job, Statement, Theorem
from isabelle_theory_agent.store import Forest_Store
from test_descriptions import descriptions
from test_model import locked, run, slot
from test_session_theory import Forest_Under_Test, session, theory

table = ts.table                    # the fake state slot table and the fake wire, per test
TH = DOCS / "node_classes" / "THEOREM.md"
KINDS = {**ts.KINDS, **{kind: Theorem for kind in theorem.KINDS}}


def lemma(name, conclusion="length (rev xs) = length xs", english="The length of a reversed list",
          for_any=({"name": "xs", "type": "'a list"},), premises=({"name": "ne", "term": "xs ≠ []"},),
          kind="lemma"):
    return {"kind": kind, "name": name, "statement": {
        "english": english, "for_any": list(for_any), "premises": list(premises), "conclusion": conclusion}}


def insert(f, parent, index, raws):
    return run(locked(f, edit.insert(parent, index, raws, KINDS)))


def forest(*theorems, store=None):
    """session_Arith > theory_X > the theorems; the forest and the theory."""
    f = Forest_Under_Test(store=store, kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X") | {"children": list(theorems)})])
    return f, s.sub_nodes[0]


def inv(f):
    assert_invariants(f, tm.TABLE)
    assert_store_mirrors(f, KINDS, shape=ts.shape)


def refused(f, parent, raws, cls):
    with pytest.raises(cls) as e:
        insert(f, parent, 0, raws)
    return e.value


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
    assert loaded.imports == ("Minilang_AoA.Minilang_AoA",) and loaded.kinds["lemma"] is Theorem
    name, *long = fenced_lines(TH, "3.")
    assert sorted(descriptions(Theorem.construct_schema)) == sorted([name] + long + [long[-1]])   # the last twice (§3)


# --- `gen` (§4) --------------------------------------------------------------

def test_gen_keeps_the_statement_normalised_as_isaterms():
    f, x = forest(lemma("rev_length", conclusion="length  (rev xs)\n= length xs", english="The length\nof a list"))
    (p,) = x.sub_nodes
    assert isinstance(p, Theorem) and (p.kind, p.name) == ("lemma", "rev_length")
    assert p.statement.english == "The length of a list"
    assert p.statement.conclusion.unicode == "length (rev xs) = length xs"
    assert p.statement.conclusion.ascii == "length (rev xs) = length xs"
    [v] = p.statement.for_any
    assert (v.name.unicode, v.type.unicode) == ("xs", "'a list")
    [ne] = p.statement.premises
    assert (ne.name.unicode, ne.term.unicode, ne.term.ascii) == ("ne", "xs ≠ []", "xs \\<noteq> []")
    assert p.reserved_names == frozenset() and p.goal_state is not p.state
    assert p.goal_state in p._states_inside() and p._slots_written_by(None) == (p.goal_state,)
    assert f.id_of(p) == "lemma_rev_length" and p.statement.structure() == (
        [("xs", "'a list")], [("ne", "xs \\<noteq> []")], "length (rev xs) = length xs")
    inv(f)
    # an untyped variable, no premises
    (q,) = insert(f, x, 1, [lemma("q", for_any=({"name": "n"},), premises=())])
    assert q.statement.for_any[0].type is None and q.statement.premises == ()


def test_gen_refuses_as_section_4_says():
    """TH §4's fenced lines and RB §2's: the parent outside a theory, the
    fact name's grammar, the identifiers and the repeated names."""
    f, x = forest()
    (s,) = f.sub_nodes
    e = refused(f, s, [lemma("p")], BadTheoremNodeParent)
    assert (e.kind, e.parent_id) == ("lemma", "session_Arith")
    assert str(e) == "At `constructs[0]`: " + [line for line in fenced_lines(DOCS / "RENDER_BASELINES.md", "2.")
                                               if line.startswith("A `lemma` cannot be placed")][0]
    e = refused(f, f, [lemma("p", kind="theorem")], BadTheoremNodeParent)
    assert (e.kind, e.parent_id) == ("theorem", "Sessions")
    invalid, *fields = fenced_lines(TH, "4.")[3:4] + fenced_lines(TH, "4.")[:3]
    e = refused(f, x, [lemma("rev-length")], InvalidName)
    assert (e.name, e.grammar) == ("rev-length", "fact name") and str(e) == "At `constructs[0]`: " + invalid
    for name in ("1st", "rev_", "rev length", "x'y-"):
        assert refused(f, x, [lemma(name)], InvalidName).grammar == "fact name"     # the class's sentence, not the framework's
    e = refused(f, x, [lemma("p", for_any=({"name": "1x"},))], InvalidField)
    assert str(e) == "At `constructs[0]`: " + fields[0] and e.field == "statement.for_any[0].name"
    e = refused(f, x, [lemma("p", for_any=({"name": "x_"},))], InvalidField)
    assert str(e) == "At `constructs[0]`: " + fields[1]
    e = refused(f, x, [lemma("p", premises=({"name": "ne", "term": "a"}, {"name": "ne", "term": "b"}))],
                InvalidField)
    assert str(e) == "At `constructs[0]`: " + fields[2] and e.field == "statement.premises[1].name"
    e = refused(f, x, [lemma("p", for_any=({"name": "xs"}, {"name": "xs"}))], InvalidField)
    assert (e.field, e.reason) == ("statement.for_any[1].name", "binds `xs` a second time")
    e = refused(f, x, [lemma("p", premises=({"name": "x y", "term": "a"},))], InvalidField)
    assert e.field == "statement.premises[0].name"
    (h,) = insert(f, x, 0, [lemma("h", premises=({"name": "h_", "term": "a"},))])     # a premise may end so
    assert h.statement.premises[0].name.unicode == "h_"
    run(locked(f, edit.delete(h)))
    refused(f, x, [{"kind": "lemma", "name": "p", "statement": {"english": "e"}}], RawASTError)
    assert x.sub_nodes == []
    inv(f)


def test_the_identifier_grammar():
    """§4: a letter or a letter symbol, then letters, digits, underscores,
    primes, and `\\<^sub>` before a letter or digit, on the `ascii` form."""
    for good in ("xs", "x'", "x_1", "x_", "\\<epsilon>", "x\\<^sub>1", "x\\<^sub>i'", "\\<alpha>\\<beta>"):
        assert is_identifier(good), good
    for bad in ("", "1x", "x-y", "x y", "_x", "x\\<^sub>", "x\\<^sub>_", "'x", "x.y", "\\<noteq>"):
        assert not is_identifier(bad), bad
    assert is_identifier(IsaTerm.from_agent("ε").ascii) and is_identifier(IsaTerm.from_agent("x⇩1").ascii)


def test_an_amend_with_the_same_structure_asks_for_the_carry():
    """§4: equal `for_any`, `premises` and `conclusion` — names included,
    `english` aside — ask the framework to carry the replaced job's
    outcome; a changed structure does not."""
    f, x = forest(lemma("p"))
    (p,) = x.sub_nodes
    (p2,) = run(locked(f, edit.amend(p, [lemma("p", english="Another wording")], KINDS)))
    assert p2._carry_job_from is p and p2.statement.english == "Another wording"
    (p3,) = run(locked(f, edit.amend(p2, [lemma("p", conclusion="rev (rev xs) = xs")], KINDS)))
    assert p3._carry_job_from is None
    (p4,) = run(locked(f, edit.amend(p3, [lemma("p", conclusion="rev (rev xs) = xs",
                                                for_any=({"name": "ys", "type": "'a list"},))], KINDS)))
    assert p4._carry_job_from is None
    inv(f)


# --- the store (§1) ------------------------------------------------------------

def test_the_statement_and_the_reserved_names_are_stored_the_goal_slot_fresh(tmp_path):
    store = Forest_Store(tmp_path / "TAT.sqlite", ts.stand_ins.log())
    f, x = forest(lemma("p"), store=store)
    (p,) = x.sub_nodes
    p.reserved_names = frozenset({"for", "p"})
    with f.store.transaction():
        f._store_node(p)
    before = (p.statement, p.reserved_names, p.goal_state.name)
    store.close()
    f2 = Forest_Under_Test(store=Forest_Store(tmp_path / "TAT.sqlite", ts.stand_ins.log()), kinds=KINDS)
    (p2,) = f2.sub_nodes[0].sub_nodes[0].sub_nodes
    assert isinstance(p2, Theorem) and p2.statement == before[0] and p2.reserved_names == before[1]
    assert p2.goal_state.name != before[2] and p2.goal_state in p2._states_inside()


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
    two = Statement("e", (theorem.Variable(IsaTerm.from_agent("x"), None),
                          theorem.Variable(IsaTerm.from_agent("y"), IsaTerm.from_agent("nat"))),
                    (theorem.Premise(IsaTerm.from_agent("h"), IsaTerm.from_agent("⋀z. P z ⟹ Q z")),),
                    IsaTerm.from_agent("A \\<Longrightarrow> B"))
    assert two.proposition() == "⋀x. ⋀y::nat. (⋀z. P z ⟹ Q z) ⟹ (A \\<Longrightarrow> B)"


INVALID = M.CannotEvaluate((IsaTerm.from_agent("no"),))
PROVED = Succeeded({"text": "by simp", "thread_cpu": 3, "wall": 5})
BAD = Failed("")                                         # a failed check: its message is empty (§7)


def with_proof(node, status, outcome, check=None):
    """The node in one of §7's states: its statement's status, its proof's
    outcome, its check — None, `RUNNING` (a running `Proof_Check` on the
    node), `PASSED` or `FAILED`."""
    node._status = status
    node.job().outcome = outcome
    node._evaluation_job = Proof_Check(node, None) if check is RUNNING else None
    node._check_outcome = check if check in (PASSED, BAD) else None


def test_the_mark_reads_one_of_eleven_ways():
    """§7's mark: the statement slot from the status, the proof slot from
    the outcome and the check, left out under `invalid statement`, a
    stored proof left out under `not evaluated` — the eleven of the
    document's block, no other."""
    [_, _, block] = fenced_blocks(TH, "7.")
    f, x = forest(lemma("p"))
    (p,) = x.sub_nodes
    assert p.mark(M.BRIEFING, 0) == "not evaluated, proof not started"
    marks = []
    for status in (M.READY_CLEAN, INVALID, M.NOT_EVALUATED):
        for outcome, check in ((NOT_STARTED, None), (RUNNING, None), (Failed("no"), None), (PROVED, None),
                               (PROVED, RUNNING), (PROVED, PASSED), (PROVED, BAD)):
            if status is M.NOT_EVALUATED and (outcome is RUNNING or check is not None):
                continue                                 # no run and no check live under `not evaluated`
            with_proof(p, status, outcome, check)
            marks.append(f"({p.mark(M.BRIEFING, 0)})")
    assert len(marks) == 17 and len(set(marks)) == 11
    assert set(marks) == set(re.findall(r"\([^)]*\)", "\n".join(block)))
    with_proof(p, M.READY_CLEAN, PROVED, PASSED)
    assert p.mark(M.BRIEFING, 0) == "valid statement, proven"


def test_the_jobs_sentences_are_section_7_s():
    """`Proof_Job`'s and `Proof_Check`'s words: the titles, the two
    notifications, the failure headers, the check's failure block — the
    header alone, its colon a period — and the notification's forms for
    one, three and four nodes, with and without automatic construction,
    the document's lines verbatim."""
    [sentences, automatic, _] = fenced_blocks(TH, "7.")
    f, x = forest(lemma("p"))
    (p,) = x.sub_nodes
    job = p.job()
    assert (Proof_Job.title(), Proof_Job.title(plural=True)) == ("proof construction", "proof constructions")
    assert (Proof_Check.title(), Proof_Check.title(plural=True)) == ("proof check", "proof checks")
    assert job.finished_notification(PROVED) == f"`{f.id_of(p)}` is proven."
    assert job.finished_notification(Failed("no proof")) == f"No proof of `{f.id_of(p)}` was found:\n  no proof"
    assert Proof_Job.failure_header(Failed("no proof")) == "No proof was found:"
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


def test_check_answers_section_7_s_table():
    """`_check()`: false off `ready`; true with no proof — `NOT_STARTED`
    or `FAILED`; on a proof, true only when its check `FAILED`."""
    f, x = forest(lemma("p"))
    (p,) = x.sub_nodes
    job = p.job()
    for outcome, check in ((NOT_STARTED, None), (Failed("no"), None), (PROVED, BAD)):
        with_proof(p, M.NOT_EVALUATED, outcome, check)
        assert not job._check()
    for outcome, check, answer in ((NOT_STARTED, None, True), (Failed("no"), None, True), (PROVED, PASSED, False),
                                   (PROVED, None, False), (PROVED, RUNNING, False), (PROVED, BAD, True)):
        with_proof(p, M.READY_CLEAN, outcome, check)
        assert job._check() is answer, (outcome, check)
        assert job.can_start() is answer
    with_proof(p, INVALID, NOT_STARTED)
    assert not job._check()


def test_what_it_prints_with_a_job_is_section_8_s_three_examples():
    """§8's examples: the line with a question waiting, for the owner; a
    focus after a failed proof construction, the failure block below;
    a node under `recall` whose stored proof failed its check, the
    header alone with a period — the document's blocks verbatim."""
    [_, asking, failed, bad] = fenced_blocks(TH, "8.")
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
    with_proof(p, M.READY_CLEAN, PROVED, BAD)
    assert f.render(p, M.RECALL, me).splitlines() == bad


# --- emission (§5) -----------------------------------------------------------

def test_the_emitted_text_is_section_5_s_with_sorry_until_the_proof_is_checked():
    [lines] = fenced_blocks(TH, "5.")
    f, x = forest(lemma("rev_length"))
    (p,) = x.sub_nodes

    def emitted(node) -> list[str]:
        """In the `\\<name>` form the file takes (§5), as the expected lines are read."""
        out = io.StringIO()
        assert node.emit(1, out) == 1
        assert "≠" not in out.getvalue()                                     # the terms in their `ascii`
        return ascii_of_unicode(out.getvalue()).splitlines()

    def expected(*unicode_lines: str) -> list[str]:
        return [ascii_of_unicode(line) for line in unicode_lines]
    assert emitted(p) == expected(*("  " + line for line in lines[:-1]), "    sorry")
    with_proof(p, M.READY_CLEAN, PROVED, PASSED)                                         # proven: the document's block whole
    assert emitted(p) == expected(*("  " + line for line in lines))
    with_proof(p, M.READY_CLEAN, PROVED, BAD)                                            # a bad proof: `sorry` again
    assert emitted(p)[-1] == "    sorry"
    with_proof(p, M.NOT_EVALUATED, NOT_STARTED)
    p.reserved_names = frozenset({"rev_length", "xs", "ne"})
    assert emitted(p)[1:5] == expected('  lemma "rev_length":', '    fixes "xs" :: "\'a list"',
                                       '    assumes "ne": "xs ≠ []"', '    shows "length (rev xs) = length xs"')
    (q,) = insert(f, x, 1, [lemma("q", english="Ends with a question? ‹Quoted› \\<open>here\\<close>",
                                  for_any=({"name": "n"},), premises=())])
    assert emitted(q) == expected('  text ‹Lemma q. Ends with a question? "Quoted" "here".›', "  lemma q:",
                                  "    fixes n", '    shows "length (rev xs) = length xs"', "    sorry")
    (r,) = insert(f, x, 2, [lemma("r", english="Bang!", kind="corollary", for_any=(), premises=())])
    assert emitted(r)[:2] == expected("  text ‹Corollary r. Bang!›", "  corollary r:")


# --- the evaluation, in the plugin's run of the harness (§6, §8) -----------------

def over_the_wire(*theorems):
    """session_TAT_Std > theory_TAT_Std_A > the theorems, as the `edit` tool takes them."""
    return ts.session("TAT_Std", ts.theory("TAT_Std_A") | {"children": list(theorems)})


async def test_a_statement_is_admitted_and_a_bad_one_is_an_obstacle(std_conversation):
    """§6 through `TAT.Theorem.evaluate`: a theory of theorems built through
    `edit` and evaluated, each statement admitted — the `goal_state` slot
    holding the open goal and the resulting slot the admitted fact; a
    statement Isabelle refuses makes its node an obstacle with Isabelle's
    message, `goal_state` empty; a reserved name recorded; the rows of §8
    under `recall`; the plugin's declared import in the theory's header.
    Last, the callback alone: a failure empties a `goal_state` an earlier
    run had written."""
    forest, kinds = std_conversation.forest, std_conversation.kinds
    assert set(theorem.KINDS) <= set(kinds)
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
        assert x.import_sessions == ["HOL", "Minilang_AoA"]                 # the declared import ran
        for node in (p, q):
            assert isinstance(node._status, M.Ready) and node._status.messages == ()
            assert await node.goal_state.is_initialized() and await node.resulting_state().is_initialized()
        assert (p.reserved_names, q.reserved_names) == (frozenset(), frozenset({"shows"}))
        assert isinstance(r._status, M.CannotEvaluate) and not await r.goal_state.is_initialized()
        assert r._status.messages[0].unicode.startswith("Type unification failed"), r._status.messages
        recalled = await session.call_tool("recall", {"node_id": "theory_TAT_Std_A"})
        lines = text_of(recalled).splitlines()
        assert not recalled.isError and lines[:12] == [
            "- theory_TAT_Std_A (incomplete)",
            "  imports: Main",
            "  - lemma_rev_length (valid statement, proof not started)",
            "    ⋀xs::'a list. xs ≠ [] ⟹ length (rev xs) = length xs",
            "    The length of a reversed list",
            "  - lemma_shows_it (valid statement, proof not started)",
            "    ⋀shows::'a list. length (rev shows) = length shows",
            "    A reserved name",
            "  - lemma_clash (invalid statement)",
            "    ⋀xs::'a list. xs = (0::nat)",
            "    Refused",
            "    Error:"], lines
        assert lines[12].startswith("      Type unification failed"), lines
    passed, messages, reserved = await isabelle_driver.call(
        forest.conversation, "TAT.Theorem.evaluate",
        (p.state.to_msgpack(), p.goal_state.to_msgpack(), p.resulting_state().to_msgpack(),
         ("lemma", "again", [["xs", "'a list"]], [], "xs = (0::nat)")))
    assert (passed, reserved) == (False, []) and messages
    assert not await p.goal_state.is_initialized() and await p.resulting_state().is_initialized()


async def until(condition, seconds: float = 180.0) -> None:
    async with asyncio.timeout(seconds):
        while not condition():
            await asyncio.sleep(0.05)


async def test_a_theorem_is_constructed_checked_invalidated_and_constructed_again(std_conversation):
    """§7 through the two callbacks, on a goal Sledgehammer's automation
    closes without the agent: `construct` starts the proof construction,
    which settles `SUCCEEDED` with the proof and its times and attaches a
    `PASSED` check; invalidated and evaluated with checks, the node gets a
    proof check that replays the product and passes; a product that no
    longer proves the goal fails its check with an empty message, the
    notification sending the agent to `construct`, whose construction
    proves the node again.  AoA's Python half is served by this process."""
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
        assert "IsaMini.AoA.toplevel" in sys.modules                  # the remote procedure `IsaMini.AoA` is this process's
        result = await session.call_tool("construct", {"node_ids": ["lemma_rev_rev"]})
        assert not result.isError and "Started the proof construction on `lemma_rev_rev`" in text_of(result)
        job = p.job()
        assert job.outcome is RUNNING and p.mark(M.BRIEFING, 0) == "valid statement, proving"
        await until(lambda: job.outcome is not RUNNING)
        assert isinstance(job.outcome, Succeeded), job.outcome
        product = job.outcome.product
        assert set(product) == {"text", "thread_cpu", "wall"} and product["text"]
        assert all(isinstance(product[k], int) and product[k] >= 0 for k in ("thread_cpu", "wall"))
        assert p.check_outcome() is PASSED and p.mark(M.BRIEFING, 0) == "valid statement, proven"
        result = await session.call_tool("check_construct", {})
        assert "`lemma_rev_rev` is proven." in text_of(result), text_of(result)
        # invalidated: the check is cleared; an evaluation with checks replays the product
        await tm._invalidate(p)
        assert p.check_outcome() is None and p.mark(M.BRIEFING, 0) == "not evaluated"
        result = await session.call_tool("evaluate_to", {"node_id": "theory_TAT_Std_A", "checks": "blocking"})
        assert not result.isError, text_of(result)
        assert p.check_outcome() is PASSED and p.mark(M.BRIEFING, 0) == "valid statement, proven"
        # a product that no longer proves the goal: the check fails with an empty message
        job.outcome = Succeeded({**product, "text": "(rule refl)"})
        await tm._invalidate(p)
        result = await session.call_tool("evaluate_to", {"node_id": "theory_TAT_Std_A", "checks": "blocking"})
        assert p.check_outcome() == Failed("") and p.mark(M.BRIEFING, 0) == "valid statement, bad proof"
        text = text_of(result)
        assert "The proof of `lemma_rev_rev` no longer holds. Call `construct` to prove it again." in text, text
        assert job.can_start()
        result = await session.call_tool("construct", {"node_ids": ["lemma_rev_rev"]})
        assert not result.isError, text_of(result)
        await until(lambda: job.outcome is not RUNNING)
        assert isinstance(job.outcome, Succeeded) and p.check_outcome() is PASSED
        assert p.mark(M.BRIEFING, 0) == "valid statement, proven"
        out = io.StringIO()
        p.emit(0, out)
        assert out.getvalue().splitlines()[-1] == "  by aoa"
