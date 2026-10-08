"""`Theorem` with no Isabelle (node_classes/THEOREM.md §1–§5, §7, §8): the
schema and the descriptions, `gen`'s checks and refusals, the statement
as the node holds, stores and prints it, the mark's statement slot, the
emitted text, the goal slot's place among the node's slots, the carry on
an amend.  The evaluation, and the proof slot of the mark, need the jobs
plan's steps 14b and 15.
Run: python -m pytest test/test_theorem.py
"""

import io

import jsoncomment
import pytest

import test_model as tm
import test_session_theory as ts
from baselines import DOCS, fenced_blocks, fenced_lines
from Isabelle_RPC_Host.unicode import IsaTerm, ascii_of_unicode, is_identifier
from invariants import assert_invariants, assert_store_mirrors
from harness import text_of
from isabelle_theory_agent import edit, isabelle_driver, model as M, plugin
from isabelle_theory_agent.exceptions import BadTheoremNodeParent, InvalidField, InvalidName, RawASTError
from isabelle_theory_agent.std import statement, theorem
from isabelle_theory_agent.std.theorem import Statement, Theorem
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


def test_the_marks_statement_slot_while_no_job_class_is_named():
    f, x = forest(lemma("p"))
    (p,) = x.sub_nodes
    assert p.job() is None and p.mark(M.BRIEFING, 0) == "not evaluated"
    p._status = M.READY_CLEAN
    assert p.mark(M.BRIEFING, 0) == "valid statement"
    p._status = M.CannotEvaluate((IsaTerm.from_agent("no"),))
    assert p.mark(M.BRIEFING, 0) == "invalid statement"


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
    assert emitted(p) == expected(*("  " + line for line in lines[:-1]), "    sorry")     # `by aoa` needs the jobs
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
            "  - lemma_rev_length (valid statement)",
            "    ⋀xs::'a list. xs ≠ [] ⟹ length (rev xs) = length xs",
            "    The length of a reversed list",
            "  - lemma_shows_it (valid statement)",
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
