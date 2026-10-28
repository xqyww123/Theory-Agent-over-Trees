"""`Inductive` (node_classes/INDUCTIVE.md): with no Isabelle, the schema and
the descriptions (§2, §3), `gen` and the field check (§4), the definition
as the node holds, stores and prints it (§1, §8), the node's name (§9),
the message, the status and the recorded fixed parameters (§6), the mark
(§7), the emitted text (§5); on a raw ML process, the detection of the
fixed parameters (§6); through the std harness, the evaluation (§6), the
callback alone, `recall` (§8), the rendered file (§5) and the products
of the definition a proof cites.
Run: python -m pytest test/test_inductive.py
"""

import io
import json

import jsoncomment
import pytest

import stand_ins
import test_model as tm
import test_session_theory as ts
from baselines import DOCS, fenced_blocks, fenced_lines
from harness import text_of
from Isabelle_RPC_Host.unicode import IsaTerm, ascii_of_unicode
from isabelle_theory_agent import compile as C, edit, isabelle_driver, model as M
from isabelle_theory_agent.exceptions import InvalidField, InvalidName, RawASTError
from isabelle_theory_agent.jobs import PASSED, Succeeded
from isabelle_theory_agent.std import common, inductive, statement
from isabelle_theory_agent.std.common import Variable_With_Syntax
from isabelle_theory_agent.std.inductive import Inductive, Inductive_Rule
from isabelle_theory_agent.std.statement import Variable
from isabelle_theory_agent.store import Forest_Store
from ml_process import ROOT, ml_process, ml_string, read_back
from std_forest import KINDS, assert_a_missing_row_is_refused_at_start, field_check, forest, insert, inv, refused, reloaded
from test_descriptions import descriptions
from test_model import locked, run
from test_session_theory import Forest_Under_Test, session, theory
from test_theorem import lemma

table = ts.table                    # the fake state slot table and the fake wire, per test
DI = DOCS / "node_classes" / "INDUCTIVE.md"
STAR = json.loads("\n".join(fenced_blocks(DI, "2.")[0]))         # §2's example
STAR_T = "('a ⇒ 'a ⇒ bool) ⇒ 'a ⇒ 'a ⇒ bool"


def rule(name, conclusion, english="A rule", premises=(), for_any=()):
    return {"name": name, "english": english, "conclusion": conclusion,
            **({"premises": list(premises)} if premises else {}), **({"for_any": list(for_any)} if for_any else {})}


def definition(*rules, constants=({"name": "star", "type": STAR_T},), english="A definition", kind="inductive"):
    return {"kind": kind, "english": english, "constants": list(constants), "inductive_rules": list(rules)}


# §8's node drawing the notice, `r` last
STAR_LAST = definition(rule("refl", "star x x r"), rule("step", "star x z r", premises=("r x y", "star y z r")),
                       constants=({"name": "star", "type": "'a ⇒ 'a ⇒ ('a ⇒ 'a ⇒ bool) ⇒ bool"},))
EVEN_ODD = definition(rule("zero", "even 0"), rule("even_suc", "even (Suc n)", premises=("odd n",)),
                      rule("odd_suc", "odd (Suc n)", premises=("even n",)),
                      constants=({"name": "even", "type": "nat ⇒ bool"}, {"name": "odd", "type": "nat ⇒ bool"}),
                      english="Even and odd naturals")


def renamed(raw, name):
    """The construct with its predicate `star` named `name`."""
    return json.loads(json.dumps(raw, ensure_ascii=False).replace("star", name))


def fields(node, mode, depth) -> tuple[bool, list[str]]:
    """`print_fields` as the rendering calls it for a node at the top, one
    level in: its answer and its lines."""
    out = io.StringIO()
    answer = node.print_fields(1, out, mode, depth)
    return answer, out.getvalue().splitlines()


def emitted(node) -> list[str]:
    """In `unicode` (§5); the file's `\\<name>` form is the compile's conversion (COMPILATION §2)."""
    out = io.StringIO()
    assert node.emit(1, out) == 1
    assert "\\<" not in out.getvalue()
    return [line[2:] for line in out.getvalue().splitlines()]


def term(text):
    return IsaTerm.from_agent(text)


# --- the schema and the descriptions (§2, §3) ------------------------------

def test_the_schema_and_the_descriptions_are_the_documents():
    [_, schema] = fenced_blocks(DI, "2.")
    text = "\n".join(line for line in schema if not line.lstrip().startswith("..."))    # the spreads
    expected = jsoncomment.JsonComment().loads(text)
    expected["$defs"] = {**expected["$defs"], **common.CONSTANT_DEFS, **statement.VARIABLE_DEFS, **common.MIXFIX_DEFS}
    assert Inductive.construct_schema == expected
    assert list(inductive.KINDS) == ["inductive", "coinductive"]
    assert expected["$defs"]["InductiveRule"]["properties"]["premises"]["items"]["description"] == common.TERM_DESCRIPTION
    shared = descriptions(common.CONSTANT_DEFS) + descriptions(statement.VARIABLE_DEFS) + descriptions(common.MIXFIX_DEFS)
    assert sorted(descriptions(Inductive.construct_schema)) == sorted(
        fenced_lines(DI, "3.") + shared + [common.TERM_DESCRIPTION])
    assert STAR["constants"] == [{"name": "star", "type": STAR_T}] and [r["name"] for r in STAR["inductive_rules"]] == [
        "refl", "step"]


# --- `gen` and the field check (§2, §4, §9) ------------------------------------

def test_gen_keeps_the_definition_normalised_as_isaterms_and_names_the_node():
    f, x = forest(definition(rule(" refl ", " star  r\n x x ", english=" Every element\n reaches  itself"),
                             rule("step", "star r x z", premises=(" r x\ny ", "star r y z"),
                                  for_any=({"name": " x ", "type": " 'a\n"}, {"name": "y", "type": ""})),
                             english=" The reflexive\n transitive closure ",
                             constants=({"name": "star", "type": " ('a ⇒ 'a ⇒ bool) ⇒\n'a ⇒ 'a ⇒ bool "},)))
    (p,) = x.sub_nodes
    assert isinstance(p, Inductive) and p.kind == "inductive" and p.name == "star" and f.id_of(p) == "inductive_star"
    assert p.english == "The reflexive transitive closure"
    assert p.constants == (Variable_With_Syntax(term("star"), term(STAR_T), None),)
    refl, step = p.inductive_rules
    assert refl == Inductive_Rule(term("refl"), "Every element reaches itself", (), (), term("star r x x"))
    assert step == Inductive_Rule(term("step"), "A rule", (Variable(term("x"), term("'a")), Variable(term("y"), None)),
                                  (term("r x y"), term("star r y z")), term("star r x z"))
    assert p.fixed_parameters is None and p.message()[3] is None          # nothing recorded yet (§1, §6)
    (q, c) = insert(f, x, 1, [EVEN_ODD, EVEN_ODD | {"kind": "coinductive", "constants": [{"name": "ev"}, {"name": "od"}]}])
    assert q.name == "even_and_odd" and f.id_of(q) == "inductive_even_and_odd"
    assert c.kind == "coinductive" and f.id_of(c) == "coinductive_ev_and_od"
    inv(f)


def test_gen_refuses_only_a_constant_name_outside_the_grammar():
    """§4: `gen` refuses only a constant's name outside the id grammar,
    by `constants_of`; what the field check judges is accepted; a missing
    field, a recorded field authored, an empty list, by the framework."""
    f, x = forest()
    for name in ("my-star", "star_", "1st", ""):
        e = refused(f, x, [definition(rule("refl", "star r x x"), constants=({"name": name},))], InvalidName)
        assert (e.name, e.grammar) == (name, "constant name")
    (p,) = insert(f, x, 0, [definition(rule("1 bad", "star r x x", for_any=({"name": "x_"}, {"name": "x_"})),
                                       rule("1 bad", "star r x x"), constants=({"name": "star"}, {"name": "star"}))])
    assert [r.name.unicode for r in p.inductive_rules] == ["1 bad", "1 bad"]
    run(locked(f, edit.delete(p)))
    for raw in ({k: v for k, v in STAR.items() if k != "english"}, STAR | {"fixed_parameters": ["r"]},
                STAR | {"constants": []}, STAR | {"inductive_rules": []},
                STAR | {"inductive_rules": [{"name": "refl", "conclusion": "star r x x"}]},       # a rule's `english`
                STAR | {"inductive_rules": [rule("refl", "star r x x") | {"premises": [{"name": "p", "term": "P"}]}]}):
        refused(f, x, [raw], RawASTError)
    assert x.sub_nodes == []
    inv(f)


def test_the_field_check_refuses_as_section_4_says():
    """§4's three sentences and THEOREM §4's for a `for_any` variable, each
    under its field, in §4's order."""
    f, x = forest()
    twice, not_identifier, repeated = fenced_blocks(DI, "4.")[0]
    [for_any_sentence, _] = fenced_blocks(DOCS / "node_classes" / "THEOREM.md", "4.")[0]
    cases = [
        (EVEN_ODD | {"constants": [{"name": "even"}, {"name": "even"}]}, twice, "constants[1].name"),
        (definition(rule("refl", "star r x x"), rule("1st", "star r x x")), not_identifier, "inductive_rules[1].name"),
        (definition(rule("refl", "star r x x"), rule("refl", "star r x z")), repeated, "inductive_rules[1].name"),
        (definition(rule("refl", "star r x x", for_any=({"name": "x_"},))),
         for_any_sentence.replace("statement.", "inductive_rules[0]."), "inductive_rules[0].for_any[0].name"),
        (definition(rule("refl", "star r x x", for_any=({"name": "x"}, {"name": "x"}))),
         "The field `inductive_rules[0].for_any[1].name` repeats `x`.", "inductive_rules[0].for_any[1].name"),
        # the order: the constants before the rule names, the rule names before any `for_any`
        (definition(rule("refl", "star r x x"), rule("1st", "star r x x"), constants=({"name": "star"}, {"name": "star"})),
         twice.replace("even", "star"), "constants[1].name"),
        (definition(rule("refl", "star r x x", for_any=({"name": "x_"},)), rule("1st", "star r x x")),
         not_identifier, "inductive_rules[1].name")]
    for raw, sentence, field in cases:
        e = field_check(f, x, [raw])
        assert e is not None and str(e) == sentence and e.field == field, (raw, e)
    assert field_check(f, x, [definition(rule("refl_", "star r x x"))]) is None       # a fact's name may end with `_`
    assert field_check(f, x, [STAR]) is None and field_check(f, x, [EVEN_ODD]) is None
    assert x.sub_nodes == []
    inv(f)


# --- the store (§1) ------------------------------------------------------------

def test_the_definition_is_stored_and_read_back_as_it_was(tmp_path):
    """Every field, the recorded one `None`, `[]` or names, each loading as
    itself; a missing row refused at start."""
    path = tmp_path / "TAT.sqlite"
    f, x = forest(STAR, renamed(STAR_LAST, "walk"), EVEN_ODD, store=Forest_Store(path, ts.stand_ins.log()))
    star, last, even_odd = x.sub_nodes
    star.fixed_parameters, last.fixed_parameters = (term("r"),), ()
    with f.store.transaction():
        for n in x.sub_nodes:
            f._store_node(n)
    rows = f.store.fields(star.identity)
    assert "name" not in rows and rows["english"] == STAR["english"] and rows["constants"] == STAR["constants"]
    assert rows["inductive_rules"] == [
        {"name": "refl", "english": "Every element reaches itself", "for_any": [], "premises": [], "conclusion": "star r x x"},
        {"name": "step", "english": "A step of r followed by a path is a path", "for_any": [],
         "premises": ["r x y", "star r y z"], "conclusion": "star r x z"}]
    assert rows["fixed_parameters"] == ["r"] and f.store.fields(last.identity)["fixed_parameters"] == []
    assert f.store.fields(even_odd.identity)["fixed_parameters"] is None
    f.store.close()

    def held(n):
        return n.name, n.kind, n.english, n.constants, n.inductive_rules, n.fixed_parameters
    before = [held(n) for n in x.sub_nodes]
    f2 = Forest_Under_Test(store=Forest_Store(path, ts.stand_ins.log()), kinds=KINDS)
    loaded = f2.sub_nodes[0].sub_nodes[0].sub_nodes
    f2.store.close()
    assert [held(n) for n in loaded] == before and loaded[1].fixed_parameters == () and loaded[2].fixed_parameters is None
    assert_a_missing_row_is_refused_at_start(path, star.identity,
                                             ("english", "constants", "inductive_rules", "fixed_parameters"))


def test_a_node_stored_with_a_bad_field_loads_and_the_field_check_refuses_it(tmp_path):
    """`from_store` reads the rules back as stored, judging nothing, and the
    field check refuses each loaded node with §4's sentence."""
    _, not_identifier, repeated = fenced_blocks(DI, "4.")[0]
    inserted, loaded = reloaded(tmp_path / "TAT.sqlite",
                                definition(rule("1st", "star r x x", for_any=({"name": "x_"},))),
                                renamed(definition(rule("refl", "star r x x"), rule("refl", "star r x z")), "other"))
    assert [n.inductive_rules for n in loaded] == [n.inductive_rules for n in inserted]
    for node, sentence, field in ((loaded[0], not_identifier.replace("[1]", "[0]"), "inductive_rules[0].name"),
                                  (loaded[1], repeated, "inductive_rules[1].name")):
        with pytest.raises(InvalidField) as e:
            node.check_fields()
        assert str(e.value) == sentence and e.value.field == field


# --- the message, the status and the recorded parameters (§6); the mark (§7) -----

def notices():
    return fenced_blocks(DI, "6.")[:3]


def test_eval_opr_sends_the_definition_and_records_the_parameters(monkeypatch):
    """§6: the callback with the input slot, the resulting slot and the
    message, in the order pinned; a clean answer records the parameters run
    — `[]` as `[]` — and the notice its variables call for; Isabelle's
    messages an obstacle, the record untouched and sent again; the mark's
    three words; an amend's node sends None."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        renamed(STAR_LAST, "walk"), EVEN_ODD, definition(rule("refl", "two x x r"), rule("step", "two x z r s",
                                                                                         premises=("two y z r s",)),
                                                               constants=({"name": "two"},)), STAR]})])
    (x,) = s.sub_nodes
    last, even_odd, two, star = x.sub_nodes
    calls = []
    answers = {"refl": [[], [["r"], []]], "zero": [[], [[], ["n"]]]}
    refusal = "\n".join(line.strip() for line in fenced_blocks(DI, "8.")[2][8:])     # §8's, `⟦…⟧` in it

    async def call(conversation, name, args):
        calls.append((name, args))
        first_rule = args[2][2][0][0]
        constant = args[2][1][0][0]
        if constant in ("walk", "two"):
            return [[], [[], ["r"] if constant == "walk" else ["r", "s"]]]
        return answers[first_rule] if args[2][3] is None else [[ascii_of_unicode(refusal)], None]   # Isabelle's spelling
    monkeypatch.setattr(isabelle_driver, "call", call)
    star.fixed_parameters = (term("x"),)                                       # an earlier run's record, refused now
    run(x.evaluate_to(None, False))
    assert [name for name, _ in calls] == ["TAT.Inductive.evaluate"] * 4
    assert [args[:2] for _, args in calls] == [(n.state.to_msgpack(), n.resulting_state().to_msgpack())
                                               for n in (last, even_odd, two, star)]
    assert calls[3][1][2] == star.message() == (
        "inductive", [("star", "('a \\<Rightarrow> 'a \\<Rightarrow> bool) \\<Rightarrow> 'a \\<Rightarrow> 'a \\<Rightarrow> bool", None)],
        [("refl", "star r x x", [], []), ("step", "star r x z", ["r x y", "star r y z"], [])], ["x"])
    assert isinstance(star._status, M.CannotEvaluate) and [m.unicode for m in star._status.messages] == [refusal]
    assert star.fixed_parameters == (term("x"),) and star.mark(M.BRIEFING, 0) == "failed"
    one, two_names, two_constants = notices()
    assert last.fixed_parameters == () and last.message()[3] == []
    assert isinstance(last._status, M.Ready) and [m.unicode for m in last._status.messages] == [
        one[0].replace("`star`", "`walk`")]
    assert [m.unicode for m in two._status.messages] == [two_names[0].replace("`star`", "`two`")]
    assert [m.unicode for m in even_odd._status.messages] == [two_constants[0].replace("`r`", "`n`")]
    assert last.mark(M.BRIEFING, 0) == "complete" and last.is_finished() and last._unfinished() is None
    (t,) = insert(f, x, 4, [renamed(STAR, "later")])
    assert t.mark(M.BRIEFING, 0) == "not evaluated" and t.message()[3] is None
    # the record kept through a refusal is sent again; an amend's node sends None, and its clean answer records
    calls.clear()
    run(tm._invalidate(star))
    run(x.evaluate_to(None, False))
    assert [args[2][3] for _, args in calls] == [["x"]] and star.fixed_parameters == (term("x"),)
    (star2,) = run(locked(f, edit.amend(star, [STAR])))
    assert star2.fixed_parameters is None and star2.message()[3] is None
    calls.clear()
    run(x.evaluate_to(None, False))
    assert [args[2][3] for _, args in calls if args[2][1][0][0] == "star"] == [None]
    assert star2.fixed_parameters == (term("r"),) and star2._status == M.READY_CLEAN and star2.message()[3] == ["r"]
    assert f.store.fields(star2.identity)["fixed_parameters"] == ["r"]


def test_the_notice_s_three_forms():
    one, two_names, two_constants = notices()
    r, s = term("r"), term("s")
    assert [inductive.notice([r], [term("star")])] == one
    assert [inductive.notice([r, s], [term("star")])] == two_names
    assert [inductive.notice([r], [term("even"), term("odd")])] == two_constants


def test_the_two_spellings_are_kept_apart(monkeypatch):
    """The message in Isabelle ASCII; the answer read from it; the stored
    rows, the record, the notice and the recall line in Unicode."""
    greek = definition(rule("refl", "star ρ x x", for_any=({"name": "ρ", "type": "'α ⇒ 'α ⇒ bool"}, {"name": "x"})),
                       constants=({"name": "star", "type": "('α ⇒ 'α ⇒ bool) ⇒ 'α ⇒ 'α ⇒ bool"},))
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [greek]})])
    (x,) = s.sub_nodes
    (p,) = x.sub_nodes
    assert p.message() == ("inductive", [("star", "('\\<alpha> \\<Rightarrow> '\\<alpha> \\<Rightarrow> bool) \\<Rightarrow> '\\<alpha>"
                                                  " \\<Rightarrow> '\\<alpha> \\<Rightarrow> bool", None)],
                           [("refl", "star \\<rho> x x", [], [("\\<rho>", "'\\<alpha> \\<Rightarrow> '\\<alpha> \\<Rightarrow> bool"),
                                                               ("x", None)])], None)

    async def call(conversation, name, args):
        return [[], [["\\<rho>"], ["\\<sigma>"]]]
    monkeypatch.setattr(isabelle_driver, "call", call)
    run(x.evaluate_to(None, False))
    assert p.fixed_parameters is not None and p.fixed_parameters[0].unicode == "ρ" and p.message()[3] == ["\\<rho>"]
    assert [m.unicode for m in p._status.messages] == [inductive.notice([term("σ")], [term("star")])]
    assert "`σ`" in p._status.messages[0].unicode
    assert f.store.fields(p.identity)["fixed_parameters"] == ["ρ"]
    assert f.store.fields(p.identity)["inductive_rules"][0]["for_any"][0] == {"name": "ρ", "type": "'α ⇒ 'α ⇒ bool"}
    assert fields(p, M.RECALL, 1)[1][0] == "    star :: ('α ⇒ 'α ⇒ bool) ⇒ 'α ⇒ 'α ⇒ bool for ρ"
    assert fields(p, M.RECALL, 1)[1][1] == "    refl: star ρ x x for x"


# --- what it prints (§8) -----------------------------------------------------

def test_print_fields_writes_the_definition_and_english_by_depth():
    layout, notice, failed = fenced_blocks(DI, "8.")
    f, x = forest(STAR)
    (star,) = x.sub_nodes
    star.fixed_parameters = (term("r"),)
    me = stand_ins.agent(f.conversation)
    star._status = M.READY_CLEAN
    assert f.render(star, M.RECALL, me).splitlines() == layout
    assert fields(star, M.RECALL, 0) == (False, layout[1:])
    assert fields(star, M.RECALL, 1) == fields(star, M.RECALL, 2) == (False, [layout[1], layout[2], layout[4]])
    assert fields(star, M.RECALL, 3) == (False, []) and fields(star, M.OUT_FOCUS, 0) == (False, [])
    assert fields(star, M.Relative_Focus(frozenset({star}), 0), 0) == (False, [])
    for keywords in (None, frozenset(), frozenset({"star", "refl", "r"})):       # the stored text, whatever the theory
        x.keywords = keywords
        assert fields(star, M.RECALL, 0) == (False, layout[1:])
    f, x = forest(STAR_LAST)
    (last,) = x.sub_nodes
    last.fixed_parameters = ()
    assert fields(last, M.RECALL, 1) == (False, notice[1:4])
    last._status = M.Ready((term(notice[5].strip()),))
    rendered = f.render(x, M.RECALL, stand_ins.agent(f.conversation)).splitlines()     # the node at depth 1
    start = rendered.index("    " + notice[0])
    assert [line[4:] for line in rendered[start:start + len(notice)]] == notice
    f, x = forest(definition(rule("refl", "star r x x", english="Every element reaches itself"),
                             rule("step", "r x z", english="A step of r followed by a path is a path",
                                  premises=("r x y", "star r y z")),
                             english=STAR["english"]))
    (bad,) = x.sub_nodes
    me = stand_ins.agent(f.conversation)
    bad._status = M.CannotEvaluate((term("\n".join(line.strip() for line in failed[8:])),))     # one message, three lines
    assert f.render(bad, M.RECALL, me).splitlines() == failed
    # the recall of a rule's own variables, less the fixed parameters, typed bare
    (r,) = insert(f, x, 1, [definition(rule("refl", "star r x x", for_any=({"name": "r", "type": "T"}, {"name": "x", "type": "'a"})),
                                       constants=({"name": "s2"},))])
    r.fixed_parameters = (term("r"),)
    assert fields(r, M.RECALL, 1) == (False, ["    s2 for r", "    refl: star r x x for x :: 'a"])


# --- emission (§5) ------------------------------------------------------------

def test_the_emitted_text_is_section_5_s():
    [block] = fenced_blocks(DI, "5.")
    f, x = forest(STAR)
    (star,) = x.sub_nodes
    x.keywords = frozenset()
    star.fixed_parameters = (term("r"),)
    assert emitted(star) == block
    star.fixed_parameters = ()
    assert emitted(star)[1] == block[1].replace(" for r where", " where")
    # prose through `english_cartouche`; coinductive; several predicates; no `for` when none is recorded
    (c, eo) = insert(f, x, 1, [definition(rule("step", "alw P xs", english="Sums of n²", premises=("P (xs 0)",)),
                                          constants=({"name": "alw"},), english="Always", kind="coinductive"),
                               EVEN_ODD])
    c.fixed_parameters, eo.fixed_parameters = (term("P"),), ()
    assert emitted(c) == ["text ‹Coinductive ‹alw›. Always.›", "coinductive alw for P where",
                          '  step: "alw P xs" if "P (xs 0)"', "    ―‹Sums of ‹n²›.›"]
    assert emitted(eo)[:4] == ["text ‹Inductive ‹even› and ‹odd›. Even and odd naturals.›",
                               'inductive even :: "nat ⇒ bool" and odd :: "nat ⇒ bool" where', '  zero: "even 0"',
                               "    ―‹A rule.›"]
    # keywords quoted: a constant's name, a fixed parameter's, a rule's name, a `for_any` variable's name
    (k,) = insert(f, x, 3, [definition(rule("refl", "k r x x", for_any=({"name": "x", "type": "'a"},)),
                                       constants=({"name": "k"},))])
    k.fixed_parameters = (term("r"),)
    x.keywords = frozenset({"k", "refl", "x", "r"})
    assert emitted(k)[1:3] == ['inductive "k" for "r" where', '  "refl": "k r x x" for "x" :: "\'a"']
    x.keywords = frozenset()
    # a nullary rule: its conclusion and its premise bare (an identifier)
    (n,) = insert(f, x, 4, [definition(rule("b", "Q", premises=("P",)), constants=({"name": "Q"},))])
    n.fixed_parameters = ()
    assert emitted(n)[1:3] == ["inductive Q where", "  b: Q if P"]
    # the first type a rule's `for_any` gives a parameter; no rule's `for` keeps it
    (t,) = insert(f, x, 5, [definition(rule("a", "tc r x x", for_any=({"name": "r"}, {"name": "x"})),
                                       rule("b", "tc r x x", for_any=({"name": "r", "type": "T1"},)),
                                       rule("c", "tc r x x", for_any=({"name": "r", "type": "T2"},)),
                                       constants=({"name": "tc"},))])
    t.fixed_parameters = (term("r"),)
    assert emitted(t)[1:] == ['inductive tc for r :: T1 where', '  a: "tc r x x" for x', "    ―‹A rule.›",
                              '| b: "tc r x x"', "    ―‹A rule.›", '| c: "tc r x x"', "    ―‹A rule.›"]
    inv(f)


# --- the detection (§6), on a raw ML process ---------------------------------

DETECT_ML = [str(ROOT / "ML" / "TAT_Framework.ML"), str(ROOT / "ML" / "TAT_Common_Nodes.ML"),
             str(ROOT / "Isabelle_Std" / "ML" / "TAT_Mixfix.ML"), str(ROOT / "Isabelle_Std" / "ML" / "TAT_Inductive.ML")]

DETECT_CASES = r"""
  val thy0 = Context.the_theory (Context.the_generic_context ());
  fun lthy text = Toplevel.context_of (fold (Toplevel.command_exception true)
    (Outer_Syntax.parse_text thy0 (K thy0) Position.start text) (Toplevel.make_state (SOME thy0)));
  val top = lthy "";
  val in_L = lthy "locale L = fixes r :: \"'a \<Rightarrow> 'a \<Rightarrow> bool\"\ncontext L begin";
  fun case' recorded label ctxt constants rules =
    let val definition = ("inductive", map (fn (n, T) => (n, SOME T, NONE)) constants, rules, SOME recorded)
        val (run, notice) = TAT_Inductive.detect ctxt (TAT_Inductive.args ctxt definition recorded)
    in writeln (label ^ ": [" ^ commas run ^ "] [" ^ commas notice ^ "]") end;
  val case_ = case' [];
  val starT = "('a \<Rightarrow> 'a \<Rightarrow> bool) \<Rightarrow> 'a \<Rightarrow> 'a \<Rightarrow> bool";
  val star = [("refl", "star r x x", [], []), ("step", "star r x z", ["r x y", "star r y z"], [])];
  val _ = case_ "a" top [("star", starT)] star;
  val _ = case_ "b" in_L [("star", starT)] star;
  val _ = case_ "c" top [("p", "nat \<Rightarrow> bool"), ("q", "int \<Rightarrow> bool")] [("p0", "p n", [], []), ("q0", "q n", [], [])];
  val _ = case_ "d" top [("star", starT), ("Q", "nat \<Rightarrow> bool")] star;
  val _ = case_ "e" top [("p", "nat \<Rightarrow> nat \<Rightarrow> bool")] [("a", "p 0 n", [], []), ("b", "p 0 (Suc n)", ["p 0 n"], [])];
  val _ = case_ "f" top [("p", "'a \<Rightarrow> 'a \<Rightarrow> bool")] [("a", "p x x", [], []), ("b", "p x x", ["p x x"], [])];
  val _ = case_ "g" top [("p", "nat \<Rightarrow> 'a \<Rightarrow> bool")] [("a", "p 0 c", [], []), ("b", "p (Suc 0) c", [], [])];
  val _ = case_ "h" top [("star", "'a \<Rightarrow> 'a \<Rightarrow> ('a \<Rightarrow> 'a \<Rightarrow> bool) \<Rightarrow> bool")]
    [("refl", "star x x r", [], []), ("step", "star x z r", ["r x y", "star y z r"], [])];
  val _ = case_ "i" top [("acc", "('a \<Rightarrow> 'a \<Rightarrow> bool) \<Rightarrow> 'a \<Rightarrow> bool")]
    [("intro", "acc r x", ["\<forall>y. r y x \<longrightarrow> acc r y"], [])];
  val _ = case_ "j" top [("p", "nat \<Rightarrow> nat \<Rightarrow> bool")] [("a", "p x 0", [], []), ("b", "p x (Suc n)", ["\<forall>y. p y n"], [])];
  val _ = case' ["r"] "k" top [("p", "nat \<Rightarrow> nat \<Rightarrow> bool")] [("a", "p r x", [], []), ("b", "p r x", ["p r x"], [])];
  val _ = case_ "l" top [("p", "nat \<Rightarrow> 'a \<Rightarrow> 'a \<Rightarrow> bool")]
    [("a", "p 0 r r", [], []), ("b", "p (Suc n) r r", ["p n r r"], [])];
  val _ = case_ "m" top [("A", "nat \<Rightarrow> bool")] [("a", "A r", [], []), ("b", "\<And>r. A r", ["A r"], [])];
  val _ = case' ["r"] "n" top [("p", "nat \<Rightarrow> bool"), ("q", "int \<Rightarrow> bool")] [("a", "p r", [], []), ("b", "\<And>r. q r", [], [])];
  val _ = case_ "o" top [("A", "nat \<Rightarrow> bool")] [("a", "\<And>r. A r", [], [])];
  val _ = case_ "p" in_L [("A", "('a \<Rightarrow> 'a \<Rightarrow> bool) \<Rightarrow> bool")] [("a", "\<And>r. A r", [], [])];
  val _ = case_ "q" top [("le", "nat \<Rightarrow> nat \<Rightarrow> bool")] [("a", "le 0 _", [], [])];
  val _ = case_ "r" top [("p", "nat \<Rightarrow> bool")] [("a", "p size", [], [("size", SOME "nat")])];
  val two_F = lthy ("consts f1 :: \"nat \<Rightarrow> bool\" f2 :: \"int \<Rightarrow> bool\"\n" ^
    "notation f1 (\"F _\" [100] 100) and f2 (\"F _\" [100] 100)");
  val _ = case_ "s" two_F [("p", "bool \<Rightarrow> bool")] [("a", "p (F x)", [], [("x", SOME "nat")])];
  val _ = writeln "DETECT DONE";
"""


DETECTED = ["a: [r] []", "b: [] []", "c: [] []", "d: [] []", "e: [] []", "f: [x] []", "g: [] []", "h: [] [r]",
            "i: [r] []", "j: [] []", "k: [r, x] []", "l: [] [r]", "m: [] []", "n: [] []", "o: [] []", "p: [] []",
            "q: [] []", "r: [size] []", "s: [] []"]


@pytest.mark.isabelle(deadline=300)
async def test_the_detection_answers_the_table(std_harness, tmp_path):
    """§6's detection, `TAT_Inductive.detect`, on rows each measured by
    probe: (a) `star`'s `r` leads; (b) a context fixing `r` makes it no
    rule's variable; (c) the same name at two types; (d) a predicate with
    no occurrence; (e) a constant argument; (f) a variable twice; (g) a
    predicate no premise mentions draws no notice; (h) `r` last, the
    notice; (i) an occurrence under a quantifier; (j) a varying first
    argument; (k) under recorded `[r]`, a parameter step 1 fixed leads; (l)
    a variable common at two later positions, named once; (m) a `⋀` inside a
    conclusion kept apart from the rule's variable of the same name; (n)
    under recorded `[r]`, a parameter and a conclusion's own `r` at another
    type; (o) a conclusion's own `⋀` no rule variable; (p) the same where
    the context fixes `r`; (q) a dummy pattern in a conclusion and (r) a
    `for_any` variable named like a constant, each read as the command
    reads it; (s) ambiguous notation that a `for_any` type resolves.  The structure's files evaluated from source inside the
    context of a theory on the heap's top theory."""
    cases = tmp_path / "detect_cases.ML"
    cases.write_text(DETECT_CASES)
    files = ", ".join(ml_string(f) for f in [*DETECT_ML, str(cases)])
    r = await ml_process(std_harness, f"val _ = in_theory thy0 [{files}];",
                         logic="Minilang_AoA", base="Minilang_AoA.Minilang_AoA")
    lines = r.stdout.splitlines()
    assert r.returncode == 0 and "DETECT DONE" in lines, (r.stdout[-3000:], r.stderr[-3000:])
    assert [line for line in lines if line[:1] in "abcdefghijklmnopqrs" and line[1:3] == ": "] == DETECTED, lines


# --- the evaluation, in the plugin's run of the harness (§5, §6, §8) --------

ACC = definition(rule("intro", "acc r x", english="Sums of n²", premises=("∀y. r y x ⟶ acc r y",)),
                 constants=({"name": "acc", "type": "('a ⇒ 'a ⇒ bool) ⇒ 'a ⇒ bool"},), english="The accessible part")
ALW = definition(rule("step", "alw P xs", english="The head satisfies P and so does the tail",
                      premises=("P (xs 0)", "alw P (λn. xs (Suc n))")),
                 constants=({"name": "alw", "type": "(nat ⇒ bool) ⇒ (nat ⇒ nat) ⇒ bool"},), english="Always P",
                 kind="coinductive")
TRANS = lemma("trans", "star r x z", "A path followed by a path is a path",
              ({"name": "r", "type": "'a ⇒ 'a ⇒ bool"}, {"name": "x", "type": "'a"}, {"name": "y", "type": "'a"},
               {"name": "z", "type": "'a"}),
              ({"name": "h1", "term": "star r x y"}, {"name": "h2", "term": "star r y z"}))
ALWAYS = lemma("always", "alw (λn. True) xs", "Always true", ({"name": "xs", "type": "nat ⇒ nat"},), ())
# the products the proof check replays (measured by probe): each cites a rule whose shape only `for` gives
PROOFS = {"trans": "(use h1 h2 in \\<open>induct x y rule: star.induct[where r = r]\\<close>, auto intro: star.step)",
          "always": "(rule alw.coinduct[of \"\\<lambda>x. True\"], auto)"}
LIFTED = definition(rule("a", "star r x x", for_any=({"name": "r"},)),
                    rule("b", "star r x z", premises=("r x y", "star r y z"),
                         for_any=({"name": "r", "type": "nat ⇒ nat ⇒ bool"},)),
                    rule("c", "star r x z", premises=("r z x", "star r x z"),
                         for_any=({"name": "r", "type": "nat ⇒ nat ⇒ bool"},)),
                    constants=({"name": "star"},))


@pytest.mark.isabelle(deadline=900)
async def test_the_definitions_are_made_with_their_parameters_and_their_rules_proved(std_conversation, std_harness,
                                                                                     tmp_path):
    """§6 through `TAT.Inductive.evaluate`: §2's `star` (`r` recorded),
    `acc` (`r`, a premise under a quantifier), a coinductive `alw` (`P`),
    mutual `even` and `odd` (none), §8's `walk`, `r` last (none, and the
    notice); `recall` as §8 shows; the file as §5 shows, read back whole;
    then the proofs for real under `checks: "blocking"`, each citing a rule
    whose shape the `for` clause gives — `star.induct`, `alw.coinduct` —,
    `PASSED`.  Last, the callback alone on slots beside the tree's: under
    recorded `[]` nothing fixed and no notice; under recorded `["x"]`
    Isabelle's refusal, never a switch."""
    forest = std_conversation.forest
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [ts.session("TAT_Suite", ts.theory("TAT_Std_I") | {"children": [
                STAR, ACC, ALW, EVEN_ODD, renamed(STAR_LAST, "walk"), TRANS, ALWAYS]})]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 0, text
        (s,) = forest.sub_nodes
        (i,) = s.sub_nodes
        star, acc, alw, even_odd, walk, trans, always = i.sub_nodes
        for node in (star, acc, alw, even_odd, walk):
            assert isinstance(node._status, M.Ready) and node.mark(M.BRIEFING, 0) == "complete", (node.name, node._status)
            assert await node.resulting_state().is_initialized()
        assert [[p.unicode for p in n.fixed_parameters or ()] for n in (star, acc, alw, even_odd, walk)] == [
            ["r"], ["r"], ["P"], [], []]
        assert all(n.fixed_parameters is not None for n in (star, acc, alw, even_odd, walk))
        assert [n._status.messages for n in (star, acc, alw, even_odd)] == [()] * 4
        [one, _, _] = notices()
        assert [m.unicode for m in walk._status.messages] == [one[0].replace("`star`", "`walk`")]
        [layout, _, _] = fenced_blocks(DI, "8.")
        recalled = await session.call_tool("recall", {"node_id": "inductive_star"})
        assert not recalled.isError and text_of(recalled).splitlines() == layout, text_of(recalled)
        rendered = C.render(forest)
        file = rendered.files[C.Path("TAT_Suite/TAT_Std_I.thy")]
        [block] = fenced_blocks(DI, "5.")
        assert "".join(ascii_of_unicode(line) + "\n" for line in block) in file, file
        assert ascii_of_unicode("coinductive alw :: \"(nat ⇒ bool) ⇒ (nat ⇒ nat) ⇒ bool\" for P :: \"nat ⇒ bool\" where") \
            not in file                                       # `P` takes the first type a rule's `for_any` gives: none
        assert ascii_of_unicode('coinductive alw :: "(nat ⇒ bool) ⇒ (nat ⇒ nat) ⇒ bool" for P where\n') in file, file
        assert "\\<comment>\\<open>Sums of \\<open>n\\<^sup>2\\<close>.\\<close>" in file, file
        await read_back(std_harness, file, tmp_path)
        # the proofs for real (COMMON §3)
        for node in (trans, always):
            node.job().outcome = Succeeded({"text": PROOFS[node.name], "thread_cpu": 2000, "wall": 2000})
        await tm._invalidate(trans)
        result = await session.call_tool("evaluate_to", {"node_id": "theory_TAT_Std_I", "checks": "blocking"})
        assert not result.isError, text_of(result)
        for node in (trans, always):
            assert node.check_outcome() is PASSED and node.mark(M.BRIEFING, 0) == "valid statement, proven", node.name
        # the callback alone (§6; COMMON §5): the recorded parameters run as recorded, a refusal never a switch
        async def evaluate(recorded):
            resulting = M.Isar_State_Slot.assign(forest.conversation)
            return await isabelle_driver.call(forest.conversation, "TAT.Inductive.evaluate",
                                              (star.state.to_msgpack(), resulting.to_msgpack(),
                                               (*star.message()[:3], recorded)))
        assert await evaluate([]) == [[], [[], []]]
        messages, what = await evaluate(["x"])
        assert what is None and len(messages) == 1, messages
        assert messages[0].endswith("Inductive predicate must be applied to parameter(s) x"), messages


@pytest.mark.isabelle(deadline=600)
async def test_refused_definitions_are_obstacles_and_a_record_runs_as_recorded(std_conversation):
    """§6, §8, one theory per obstacle: a conclusion applying no predicate,
    Isabelle's message as §8 shows under `recall`; a rule needing a
    monotonicity lemma, the failed proof; the record untouched.  A
    recorded `r` under a constant `r :: nat` declared before the node
    later still accepted (step 1 under the record); and the lifted type:
    `star` untyped, `r` typed by a later rule's `for_any`, fixes `star`
    at that type, so a theorem stating it at a type variable is refused."""
    forest = std_conversation.forest
    refused_concl = definition(rule("refl", "star r x x", english="Every element reaches itself"),
                               rule("step", "r x z", english="A step of r followed by a path is a path",
                                    premises=("r x y", "star r y z")),
                               english=STAR["english"])
    myor = {"kind": "definition", "english": "Or", "constants": [{"name": "myor", "type": "bool ⇒ bool ⇒ bool"}],
            "equations": ["myor a b = (a ∨ b)"], "auto_reduction": False}
    mono = definition(rule("zero", "ev 0"), rule("suc", "ev n", premises=("myor (ev n) False",)),
                      constants=({"name": "ev", "type": "nat ⇒ bool"},))
    at_b = lemma("at_b", "lstar r x x", "At a type variable",
                 ({"name": "r", "type": "'b ⇒ 'b ⇒ bool"}, {"name": "x", "type": "'b"}), ())
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [ts.session("TAT_Suite",
                ts.theory("TAT_Std_J") | {"children": [refused_concl]},
                ts.theory("TAT_Std_K") | {"children": [myor, mono]},
                ts.theory("TAT_Std_L") | {"children": [renamed(STAR, "path")]},
                ts.theory("TAT_Std_M") | {"children": [renamed(LIFTED, "lstar"), at_b]})]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 3, text
        (s,) = forest.sub_nodes
        j, k, l, m = s.sub_nodes
        (bad,) = j.sub_nodes
        _, ev = k.sub_nodes
        (path,) = l.sub_nodes
        lifted, theorem = m.sub_nodes
        [_, _, failed] = fenced_blocks(DI, "8.")
        assert isinstance(bad._status, M.CannotEvaluate) and bad.fixed_parameters is None
        assert [msg.unicode for msg in bad._status.messages] == ["\n".join(line.strip() for line in failed[8:])]
        recalled = await session.call_tool("recall", {"node_id": "inductive_star"})
        assert text_of(recalled).splitlines() == failed, text_of(recalled)
        assert isinstance(ev._status, M.CannotEvaluate) and ev.fixed_parameters is None
        assert ev._status.messages[0].unicode.startswith("Proof failed."), ev._status.messages
        assert [p.unicode for p in lifted.fixed_parameters or ()] == ["r"] and isinstance(lifted._status, M.Ready)
        assert isinstance(theorem._status, M.CannotEvaluate), theorem._status
        assert theorem._status.messages[0].unicode.startswith("Type unification failed"), theorem._status.messages
        # a constant `r` declared before `path` later: the recorded `r` still fixed, the definition accepted
        assert [p.unicode for p in path.fixed_parameters or ()] == ["r"]
        result = await session.call_tool("edit", {
            "action": "insert_before", "target_id": "inductive_path", "evaluate": True,
            "constructs": [{"kind": "definition", "english": "A number", "constants": [{"name": "r", "type": "nat"}],
                            "equations": ["r = (0::nat)"], "auto_reduction": False}]})
        assert not result.isError and "Error:" not in text_of(result), text_of(result)
        result = await session.call_tool("evaluate_to", {"node_id": "theory_TAT_Std_L"})
        assert not result.isError and "Error:" not in text_of(result), text_of(result)
        assert isinstance(l.sub_nodes[0]._status, M.Ready) and l.sub_nodes[1] is path
        assert isinstance(path._status, M.Ready) and [p.unicode for p in path.fixed_parameters or ()] == ["r"]
