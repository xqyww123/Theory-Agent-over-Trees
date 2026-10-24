"""`Locale` (node_classes/LOCALE.md): with no Isabelle, the schema and the
descriptions (§2, §3), `gen`'s checks and refusals (§4), the fields as the
node holds, stores and prints them (§1, §8), the emitted text (§5), the
beginning's call with its records and its messages, the ending's call
(§6), the children header (§8).  The Isabelle-backed cases come with
TAT_Locale.ML.
Run: python -m pytest test/test_locale.py
"""

import io
import json
import sys

import jsoncomment

import stand_ins
import test_session_theory as ts
from baselines import DOCS, fenced_blocks, fenced_lines
from Isabelle_RPC_Host.unicode import IsaTerm, ascii_of_unicode
from isabelle_theory_agent import isabelle_driver, model as M
from isabelle_theory_agent.exceptions import DuplicateName, InvalidField, InvalidName, RawASTError
from isabelle_theory_agent.jobs import PASSED, RUNNING
from isabelle_theory_agent.std import common, locale, statement
from isabelle_theory_agent.std.common import Infix, Instantiation, Locale_Instance, NoSyntax, Variable_With_Syntax
from isabelle_theory_agent.std.locale import Axiom, Locale, cancellation_sentence, proposition_text
from isabelle_theory_agent.store import Forest_Store
from std_forest import KINDS as STD_KINDS, assert_a_missing_row_is_refused_at_start, forest, insert, inv, refused
from test_descriptions import descriptions
from test_model import run
from test_session_theory import Forest_Under_Test, session, theory
from test_theorem import PROVED, with_proof

# `Locale` joins the package once `Section` is a class of it (COMMON.md §1); until then `plugin.load` refuses its
# placement, so the class is kept out of what the loader selects: the module leaves `sys.modules`, and the loader's
# sweep forgets the class; the cases hold the class itself.
sys.modules.pop("isabelle_theory_agent.std.locale")

table = ts.table                    # the fake state slot table and the fake wire, per test
KINDS = {**STD_KINDS, "locale": Locale}                 # the class is registered with the package when `Section` is
LD = DOCS / "node_classes" / "LOCALE.md"
RB = DOCS / "RENDER_BASELINES.md"
IDEMPOTENT, COMMUTATIVE = (json.loads("\n".join(b)) for b in fenced_blocks(LD, "2.")[:2])     # §2's two constructs
(IDEM_TWICE,) = IDEMPOTENT["children"]
ROWS = ("english", "name", "imports", "fixes", "assumes", "implicit_structure", "annotations", "parenthesised_conclusions")
G = IsaTerm.from_agent("G")
OTIMES = Infix("infix", IsaTerm.from_agent("⊗"), 70)       # an annotation as a beginning records it: the fake wire's answer


def bounded(**fields):
    """§5's third construct, extending nothing, with `fields` over it."""
    return {"kind": "locale", "english": "A positive bound", "name": "bounded",
            "fixes": [{"name": "n", "type": "nat"}],
            "assumes": [{"name": "pos", "statement": {"english": "The bound is positive", "conclusion": "0 < n"}}],
            "implicit_structure": None, **fields}


def recorded(node, annotations=None, parenthesised=None, beginning=M.READY_CLEAN, ending=M.READY_CLEAN):
    """The node as a beginning that went through leaves it (§1, §6)."""
    node.annotations = (None,) * len(node.fixes) if annotations is None else annotations
    node.parenthesised_conclusions = (False,) * len(node.assumes) if parenthesised is None else parenthesised
    node.evaluation_status_beginning, node.evaluation_status_ending = beginning, ending


# --- the schema and the descriptions (§2, §3) ------------------------------

def test_the_schema_and_the_descriptions_are_the_documents():
    [_, _, schema, null_sentence] = fenced_blocks(LD, "2.")
    text = "\n".join('"$defs": {}' if line.strip().startswith('"$defs"') else line for line in schema)
    expected = jsoncomment.JsonComment().loads(text)
    expected["$defs"] = {**common.LOCALE_INSTANCE_DEFS, **common.VARIABLE_WITH_SYNTAX_DEFS, **statement.STATEMENT_DEFS,
                         **common.MIXFIX_DEFS}
    assert Locale.construct_schema == expected
    assert list(locale.KINDS) == ["locale"]
    shared = [d for defs in (common.LOCALE_INSTANCE_DEFS, common.VARIABLE_WITH_SYNTAX_DEFS, statement.STATEMENT_DEFS,
                             common.MIXFIX_DEFS) for d in descriptions(defs)]
    assert sorted(descriptions(Locale.construct_schema)) == sorted(fenced_lines(LD, "3.") + shared)
    assert null_sentence == ["The field `implicit_structure` must be a string or null."]
    assert issubclass(Locale, M.StdBlock) and not issubclass(Locale, common.With_Proof_Obligations)
    assert Locale.construction_job_class is None and Locale.evaluation_job_class is None          # no jobs (§1)
    assert {"_eval_beginning_opr", "_eval_ending_opr", "emit_beginning", "emit_ending"} <= set(vars(Locale))
    assert "mark" not in vars(Locale) and "owing_line" not in vars(Locale)                          # the framework's (§7)
    assert Locale.placement == M.Placement(within="Theory", through=("Section",))                  # §1
    assert not Locale.output_omissible and not Locale.input_omissible and Locale.drop_priority == 0   # §9
    assert IDEMPOTENT["name"] == "idempotent_semigroup" and COMMUTATIVE["implicit_structure"] == "G"


# --- `gen` (§2, §4) ----------------------------------------------------------

def test_gen_keeps_the_fields_normalised_as_isaterms_and_names_the_node():
    f, x = forest(IDEMPOTENT, COMMUTATIVE, bounded(english="A positive\n  bound ", implicit_structure=" n "), kinds=KINDS)
    i, c, b = x.sub_nodes
    assert isinstance(i, Locale) and i.kind == "locale" and f.id_of(i) == "locale_idempotent_semigroup"
    assert i.english == "A semigroup whose operation is idempotent" and i.name == "idempotent_semigroup"
    assert i.imports == (Locale_Instance(IsaTerm.from_agent("semigroup"), IsaTerm.from_agent("S"),
                                         (Instantiation(IsaTerm.from_agent("f"), IsaTerm.from_agent("f")),)),)
    assert i.fixes == (Variable_With_Syntax(IsaTerm.from_agent("f"), IsaTerm.from_agent("'a ⇒ 'a ⇒ 'a"),
                                            Infix("infixl", IsaTerm.from_agent("⊗"), 70)),)
    (idem,) = i.assumes
    assert isinstance(idem, Axiom) and idem.name == IsaTerm.from_agent("idem")
    assert idem.statement.english == "Applying the operation to an element and itself gives it back"
    assert [v.name.unicode for v in idem.statement.for_any] == ["x"] and idem.statement.premises == ()
    assert idem.statement.conclusion == IsaTerm.from_agent("x ⊗ x = x")
    assert i.implicit_structure is None and i.annotations is None and i.parenthesised_conclusions is None
    (child,) = i.sub_nodes
    assert f.id_of(child) == "locale_idempotent_semigroup.lemma_idem_twice" and child.state is not i.state
    assert i._state_before_ending in i._states_inside()
    assert c.implicit_structure == G and c.fixes[0].syntax is None and c.imports[0].qualifier == IsaTerm.from_agent("M")
    (comm,) = c.assumes
    assert [p.term.unicode for p in comm.statement.premises] == ["x ∈ carrier G", "y ∈ carrier G"]
    assert b.english == "A positive bound" and b.implicit_structure == IsaTerm.from_agent("n") and b.imports == ()
    assert b.fixes[0].type == IsaTerm.from_agent("nat") and b.fixes[0].syntax is None
    (n,) = insert(f, x, 3, [bounded(name="unsyntaxed", fixes=[{"name": "n", "syntax": {"form": "NoSyntax"}}])])
    assert n.fixes == (Variable_With_Syntax(IsaTerm.from_agent("n"), None, NoSyntax()),)
    inv(f)


def test_gen_refuses_as_section_4_says():
    """§4's refusals in its order: the name (`InvalidName`, the locale name's
    grammar, RENDER_BASELINES §2's line); an import by `Locale_Instance`'s
    reader; a parameter's name, a repeat; an axiom's name, a repeat, its
    statement by the shared reader under `assumes[i].statement`; a
    `for_any` variable that is a parameter; a blank implicit structure;
    the framework's: a missing field, a value of another type, a recorded
    field authored, a sibling of the same name."""
    f, x = forest(COMMUTATIVE, kinds=KINDS)
    [identifier, repeats_f, axiom_identifier, repeats_idem, clash, blank] = fenced_blocks(LD, "4.")[0]
    [invalid] = [line for line in fenced_lines(RB, "2.") if line.startswith("`idempotent-semigroup` is not a valid locale")]
    e = refused(f, x, [bounded(name="idempotent-semigroup")], InvalidName)
    assert (e.name, e.grammar) == ("idempotent-semigroup", "locale name") and invalid in str(e)
    for name in ("bounded_", "Bounded-1", "1st", "x y", "a.b", "ε", ""):
        assert refused(f, x, [bounded(name=name)], InvalidName).grammar == "locale name", name
    e = refused(f, x, [bounded(imports=[{"locale": "semi-group", "instantiations": []}])], InvalidField)
    assert e.field == "imports[0].locale" and str(e).startswith("At `constructs[0]`: The field `imports[0].locale` must be a locale's name")
    e = refused(f, x, [bounded(imports=[{"locale": "s", "instantiations": []},
                                        {"locale": "t", "instantiations": [{"name": "f", "term": "f"}, {"name": "f", "term": "g"}]}])],
                InvalidField)
    assert str(e) == "At `constructs[0]`: The field `imports[1].instantiations[1].name` repeats `f`."
    e = refused(f, x, [bounded(fixes=[{"name": "f"}, {"name": "1g"}])], InvalidField)
    assert str(e) == "At `constructs[0]`: " + identifier
    for name in ("f_", "x y", "a.b", "", "h\\<nat>"):
        assert refused(f, x, [bounded(fixes=[{"name": "f"}, {"name": name}])], InvalidField).field == "fixes[1].name", name
    assert str(refused(f, x, [bounded(fixes=[{"name": "f"}, {"name": " f "}])], InvalidField)) == "At `constructs[0]`: " + repeats_f
    (ax,) = bounded()["assumes"]
    e = refused(f, x, [bounded(assumes=[ax, {"name": "1x", "statement": ax["statement"]}])], InvalidField)
    assert str(e) == "At `constructs[0]`: " + axiom_identifier
    (p_,) = insert(f, x, 1, [bounded(name="pos_locale", assumes=[ax, {"name": "pos_", "statement": ax["statement"]}])])
    assert p_.assumes[1].name == IsaTerm.from_agent("pos_")          # a fact's name may end with an underscore (COMMON §5)
    e = refused(f, x, [bounded(assumes=[{**ax, "name": "idem"}, {**ax, "name": "idem"}])], InvalidField)
    assert str(e) == "At `constructs[0]`: " + repeats_idem
    e = refused(f, x, [bounded(assumes=[{**ax, "statement": {**ax["statement"], "for_any": [{"name": "1x"}]}}])], InvalidField)
    assert e.field == "assumes[0].statement.for_any[0].name" and "must be an Isabelle identifier" in str(e)
    e = refused(f, x, [bounded(assumes=[{**ax, "statement": {**ax["statement"], "for_any": [{"name": "n"}]}}])], InvalidField)
    assert str(e) == "At `constructs[0]`: " + clash
    for structure in ("", "  \n"):
        assert str(refused(f, x, [bounded(implicit_structure=structure)], InvalidField)) == "At `constructs[0]`: " + blank
    # §4's order under two faults: the name, then the imports, the parameters, the axioms — every axiom read before the
    # `for_any` clash is looked for —, then the implicit structure
    bad_import = [{"locale": "semi-group", "instantiations": []}]
    bad_fix = [{"name": "1g"}]
    clashing = {**ax, "statement": {**ax["statement"], "for_any": [{"name": "n"}]}}
    assert refused(f, x, [bounded(name="idempotent-semigroup", imports=bad_import)], InvalidName).grammar == "locale name"
    assert refused(f, x, [bounded(imports=bad_import, fixes=bad_fix)], InvalidField).field == "imports[0].locale"
    assert refused(f, x, [bounded(fixes=bad_fix, assumes=[{**ax, "name": "1x"}])], InvalidField).field == "fixes[0].name"
    assert refused(f, x, [bounded(assumes=[clashing, {**ax, "name": "1x"}])], InvalidField).field == "assumes[1].name"
    assert refused(f, x, [bounded(assumes=[clashing], implicit_structure="")], InvalidField).field == "assumes[0].statement.for_any[0].name"
    # the framework's: `implicit_structure` required and a string or null; no recorded field authored; `english` required
    e = refused(f, x, [{k: v for k, v in bounded().items() if k != "implicit_structure"}], RawASTError)
    assert "implicit_structure" in str(e)
    [null] = [line for line in fenced_lines(RB, "2.") if line.startswith("The field `implicit_structure`")]
    assert str(refused(f, x, [bounded(implicit_structure=1)], InvalidField)) == "At `constructs[0]`: " + null
    for raw in (bounded(annotations=[None]), bounded(parenthesised_conclusions=[False]),
                {k: v for k, v in bounded().items() if k != "english"}, bounded(fixes=[{"name": "n", "syntax": {}}])):
        refused(f, x, [raw], RawASTError)
    e = refused(f, x, [bounded(name="commutative_monoid")], DuplicateName)
    assert e.id_component == "locale_commutative_monoid"
    assert len(x.sub_nodes) == 2
    inv(f)


# --- the store (§1) ---------------------------------------------------------------

def test_the_fields_are_stored_and_a_missing_row_is_refused_at_start(tmp_path):
    path = tmp_path / "TAT.sqlite"
    f, x = forest(IDEMPOTENT, COMMUTATIVE, bounded(), store=Forest_Store(path, ts.stand_ins.log()), kinds=KINDS)
    i, c, b = x.sub_nodes
    recorded(c, annotations=(Infix("infixl", IsaTerm.from_agent("⊗"), 70),), parenthesised=(True,))     # as a beginning records
    recorded(b)
    with f.store.transaction():
        for n in x.sub_nodes:
            f._store_node(n)

    def fields(n):
        return (n.english, n.name, n.imports, n.fixes, n.assumes, n.implicit_structure, n.annotations,
                n.parenthesised_conclusions)
    before = [fields(n) for n in x.sub_nodes]
    rows = f.store.fields(i.identity)
    assert set(ROWS) <= set(rows)
    assert rows["imports"] == IDEMPOTENT["imports"] and rows["fixes"] == IDEMPOTENT["fixes"]
    assert rows["assumes"] == [{"name": "idem", "statement": {**IDEMPOTENT["assumes"][0]["statement"], "premises": []}}]
    assert rows["implicit_structure"] is None and rows["annotations"] is None and rows["parenthesised_conclusions"] is None
    rows = f.store.fields(c.identity)
    assert rows["implicit_structure"] == "G" and rows["parenthesised_conclusions"] == [True]
    assert rows["annotations"] == [{"form": "infixl", "symbol": "⊗", "priority": 70}]
    assert f.store.fields(b.identity)["annotations"] == [None]
    f.store.close()
    f2 = Forest_Under_Test(store=Forest_Store(path, ts.stand_ins.log()), kinds=KINDS)
    loaded = f2.sub_nodes[0].sub_nodes[0].sub_nodes
    assert [fields(n) for n in loaded] == before and all(isinstance(n, Locale) for n in loaded)
    assert [c.name for c in loaded[0].sub_nodes] == ["idem_twice"]
    f2.store.close()
    assert_a_missing_row_is_refused_at_start(path, i.identity, ROWS, kinds=KINDS)


# --- emission (§5) ------------------------------------------------------------

def test_emit_writes_section_5_s_three_examples():
    """§5's three fences whole: the `text` line, the head, the imports with
    ` +`, the `for` clause or the `fixes` element, the implicit structure,
    the axioms with their comments, `begin`, the children, `end`; the
    recorded annotation and parentheses read."""
    f, x = forest(IDEMPOTENT, COMMUTATIVE, bounded(), kinds=KINDS)
    i, c, b = x.sub_nodes
    for node in (i, c, b):
        recorded(node)
    with_proof(i.sub_nodes[0], M.READY_CLEAN, PROVED, check=PASSED)     # the child proven: `by aoa`
    for node, block in zip((i, c, b), fenced_blocks(LD, "5.")):
        out = io.StringIO()
        node.emit(0, out)
        assert out.getvalue().splitlines() == block, node.name
    # an annotation taken from an import where `syntax` is left out; `NoSyntax` and none write nothing; two imports; an
    # implicit structure that is not an identifier, quoted
    (r,) = insert(f, x, 3, [bounded(name="r", imports=[
        {"locale": "A", "qualifier": "P", "instantiations": [{"name": "f", "term": "f"}]},
        {"locale": "B", "instantiations": [{"name": "g", "term": "g"}, {"name": "h", "term": "_"}]}],
        fixes=[{"name": "f"}, {"name": "g", "type": "'a", "syntax": {"form": "NoSyntax"}}, {"name": "h"}],
        implicit_structure="padic_int p")])
    recorded(r, annotations=(Infix("infixr", IsaTerm.from_agent("⊕"), 60), None, None))
    out = io.StringIO()
    assert r.emit_beginning(1, out) == 1
    assert out.getvalue().splitlines() == [
        "  text ‹A positive bound.›", "  light_locale r =", "    P: A where f = f +", "    B where g = g and h = _",
        '    for f (infixr "⊕" 60) and g :: "\'a" and h +', '    implicit_structure "padic_int p"', '    assumes pos: "0 < n"',
        "      ―‹The bound is positive.›", "  begin"]
    # two imports and no parameter: ` +` on both; a parenthesised conclusion; the theory's keywords quoted — the name, the
    # implicit structure, the axiom's name
    (q,) = insert(f, x, 4, [bounded(name="q", imports=[{"locale": "A", "instantiations": []}, {"locale": "B", "instantiations": []}],
                                    fixes=[], assumes=[{"name": "ax", "statement": {"english": "Both", "for_any": [{"name": "x"}, {"name": "y", "type": "nat"}],
                                                                                        "premises": [{"name": "h1", "term": "P x"}, {"name": "h2", "term": "Q y"}],
                                                                                        "conclusion": "R x y"}}],
                                    implicit_structure="ax")])
    recorded(q, parenthesised=(True,))
    x.keywords = frozenset({"q", "ax"})
    out = io.StringIO()
    q.emit_beginning(0, out)
    assert out.getvalue().splitlines() == [
        "text ‹A positive bound.›", 'light_locale "q" =', "  A +", "  B +", '  implicit_structure "ax"',
        '  assumes "ax": "⋀x (y::nat). ⟦P x; Q y⟧ ⟹ (R x y)"', "    ―‹Both.›", "begin"]
    out = io.StringIO()
    assert q.emit_ending(2, out) == 2 and out.getvalue() == "\n    end\n"
    assert proposition_text(q.assumes[0].statement, False) == "⋀x (y::nat). ⟦P x; Q y⟧ ⟹ R x y"
    assert proposition_text(b.assumes[0].statement, True) == "(0 < n)"


# --- the beginning, its records and its messages, the ending (§6) -------------

def fake_wire(monkeypatch, beginning):
    """The fake wire: `beginning` answers `TAT.Locale.open` from the
    declaration sent; the ending's answer and a child's callback clean;
    every call kept.  A `Theorem` stands inside the block: its `through`
    gains `"Locale"` when the class joins the package (COMMON.md §1)."""
    from isabelle_theory_agent.std.theorem import Theorem
    monkeypatch.setattr(Theorem, "placement", M.Placement(within="Theory", through=(*Theorem.placement.through, "Locale")))
    calls = []

    async def call(conversation, name, args):
        calls.append((name, args))
        if name == "TAT.Locale.open":
            return beginning(args[2])
        if name == "TAT.Locale.close":
            return []
        return [[], [None, None]]
    monkeypatch.setattr(isabelle_driver, "call", call)
    return calls


def test_eval_beginning_opr_sends_the_declaration_and_records_what_the_callback_answers(monkeypatch):
    """§6: `TAT.Locale.open` with the beginning's two slots and the
    declaration as structure — the name, each import's wire, each parameter's
    wire with whether its `syntax` was left out, each axiom's name and its
    two forms, the implicit structure or None, every piece in `ascii`; the
    answer's records recorded, its cancelled structures — each with its
    import, one giving none left out, the term in `unicode` — and notice
    the `Ready`'s messages, in that order; messages an obstacle with the
    records untouched, the children `not_evaluated`, the ending the copy."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        IDEMPOTENT, COMMUTATIVE, bounded(name="lf", imports=[{"locale": "padic_integers", "instantiations": [
            {"name": "Zp", "term": "_"}, {"name": "p", "term": "p"}]}],
            fixes=[{"name": "p", "type": "int", "syntax": {"form": "NoSyntax"}}], assumes=[]),
        bounded(name="gr", imports=[{"locale": "semigrp", "instantiations": []},
                                    {"locale": "group", "qualifier": "M", "instantiations": []},
                                    {"locale": "ring", "qualifier": "R", "instantiations": []}]),
        bounded(name="sym", imports=[{"locale": "monoid", "instantiations": []}]),
        bounded(name="bad", imports=[{"locale": "semigrp", "instantiations": []}]) | {"children": [IDEM_TWICE]}]})])
    (x,) = s.sub_nodes
    i, c, lf, gr, sym, bad = x.sub_nodes
    notice = ("The following definitions from `padic_integers` are unfolded.\n  Zp \\<equiv> padic_int p\n"
              "The names `Zp` are not bound and shouldn't be used any more. Write their unfolded terms instead.")
    answers = {
        "idempotent_semigroup": [[], [[None], [False]], [None], None],
        "commutative_monoid": [[], [[["infix", "\\<otimes>", None, 70]], [True]], [None], None],
        "lf": [[], [[None], []], ["padic_int p"], notice],
        "gr": [[], [[None], [False]], [None, "G", "R"], None],
        "sym": [[], [[None], [False]], ["\\<one>"], None],
        "bad": [['Undefined locale: "semigrp"'], None, None, None]}
    calls = fake_wire(monkeypatch, lambda declaration: answers[declaration[0]])
    run(x.evaluate_to(None, False))
    mine = [args for name, args in calls if name == "TAT.Locale.open"]
    assert [(a[0], a[1]) for a in mine] == [(n.state.to_msgpack(), n.operation_slots("beginning")[1].to_msgpack())
                                            for n in (i, c, lf, gr, sym, bad)]
    assert mine[0][1] == i.sub_nodes[0].state.to_msgpack() and mine[1][1] == c._state_before_ending.to_msgpack()
    arrow = "\\<Rightarrow>"
    assert mine[0][2] == ("idempotent_semigroup", [("semigroup", "S", [("f", "f")])],
                          [(("f", f"'a {arrow} 'a {arrow} 'a", '(infixl "\\<otimes>" 70)'), False)],
                          [("idem", "\\<And>(x::'a). (x \\<otimes> x = x)", "\\<And>(x::'a). x \\<otimes> x = x")], None)
    assert mine[0][2] == i.declaration_wire()
    declared = ascii_of_unicode("⋀(x::'a) (y::'a). ⟦x ∈ carrier G; y ∈ carrier G⟧ ⟹ (x ⊗ y = y ⊗ x)")
    bare = ascii_of_unicode("⋀(x::'a) (y::'a). ⟦x ∈ carrier G; y ∈ carrier G⟧ ⟹ x ⊗ y = y ⊗ x")
    assert mine[1][2] == ("commutative_monoid", [("monoid", "M", [("G", "G")])],
                          [(("G", "('a, 'b) monoid_scheme", None), True)], [("comm", declared, bare)], "G")
    assert mine[2][2] == ("lf", [("padic_integers", None, [("Zp", "_"), ("p", "p")])], [(("p", "int", None), False)], [], None)
    # the records and the messages
    assert i.evaluation_status_beginning == M.READY_CLEAN and i.annotations == (None,) and i.parenthesised_conclusions == (False,)
    assert c.annotations == (OTIMES,) and c.parenthesised_conclusions == (True,)
    assert c.evaluation_status_beginning == M.READY_CLEAN
    assert isinstance(lf.evaluation_status_beginning, M.Ready) and lf.annotations == (None,) and lf.parenthesised_conclusions == ()
    [cancellation, two, _] = [b for b in fenced_blocks(LD, "6.") if b[0].startswith("`null` cancels")][0]
    assert [m.unicode for m in lf.evaluation_status_beginning.messages] == [
        cancellation, notice.replace("\\<equiv>", "≡")]
    assert [m.unicode for m in gr.evaluation_status_beginning.messages] == [two]       # `semigrp` gives none: left out
    assert [m.unicode for m in sym.evaluation_status_beginning.messages] == [
        '`null` cancels the implicit structure "𝟭" inherited from locale monoid.']
    assert isinstance(bad.evaluation_status_beginning, M.CannotEvaluate) and bad.annotations is None
    assert [m.unicode for m in bad.evaluation_status_beginning.messages] == ['Undefined locale: "semigrp"']
    assert bad.evaluation_status_ending == M.READY_CLEAN and i.evaluation_status_ending == M.READY_CLEAN
    assert i.sub_nodes[0]._status == M.READY_CLEAN and bad.sub_nodes[0]._status is M.NOT_EVALUATED
    assert [name for name, _ in calls].count("TAT.Locale.close") == 5                    # `bad`'s ending is the copy
    assert (i.mark(M.BRIEFING, 0), c.mark(M.BRIEFING, 0), bad.mark(M.BRIEFING, 0)) == ("incomplete", "complete", "failed")
    # a refusal leaves the records; recorded anew by a beginning that goes through
    answers["commutative_monoid"] = [["Interrupt"], None, None, None]
    status = run(c._eval_beginning_opr())
    assert isinstance(status, M.CannotEvaluate) and c.annotations == (OTIMES,) and c.parenthesised_conclusions == (True,)
    answers["commutative_monoid"] = [[], [[None], [False]], [None], None]
    assert run(c._eval_beginning_opr()) == M.READY_CLEAN and c.annotations == (None,) and c.parenthesised_conclusions == (False,)


def test_the_cancellation_s_message_is_section_6_s_in_its_three_forms():
    """§6: each cancelled structure through `print_name` against no keyword,
    with its import's authored locale name, joined by `, ` and ` and `;
    the noun in number."""
    [one, two, three] = [b for b in fenced_blocks(LD, "6.") if b[0].startswith("`null` cancels")][0]
    padic = (IsaTerm.from_agent("padic_integers"), IsaTerm.from_agent("padic_int p"))
    assert cancellation_sentence([padic]) == one
    assert cancellation_sentence([(IsaTerm.from_agent("group"), G), (IsaTerm.from_agent("ring"), IsaTerm.from_agent("R"))]) == two
    assert cancellation_sentence([(IsaTerm.from_agent(f"l{i}"), IsaTerm.from_agent(t)) for i, t in ((1, "A"), (2, "B"), (3, "C"))]) == three


def test_the_ending_calls_close_with_the_slot_after_the_last_child_and_the_resulting_slot(monkeypatch):
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [IDEMPOTENT, bounded()]})])
    (x,) = s.sub_nodes
    i, b = x.sub_nodes
    calls = fake_wire(monkeypatch, lambda declaration: [[], [[None], [False]], [None], None])
    run(x.evaluate_to(None, False))
    endings = [args for name, args in calls if name == "TAT.Locale.close"]
    assert endings == [(i._state_before_ending.to_msgpack(), i.resulting_state().to_msgpack()),
                       (b._state_before_ending.to_msgpack(), b.resulting_state().to_msgpack())]
    assert i.evaluation_status_ending == M.READY_CLEAN

    async def refusing(conversation, name, args):
        return ["Interrupt"] if name == "TAT.Locale.close" else [[], [[None], [False]], [None], None]
    monkeypatch.setattr(isabelle_driver, "call", refusing)
    status = run(b._eval_ending_opr())
    assert isinstance(status, M.CannotEvaluate) and [m.unicode for m in status.messages] == ["Interrupt"]


# --- what it prints (§8) -----------------------------------------------------

def test_print_fields_writes_the_declaration_by_depth_and_recall_renders_section_8_s_examples():
    """§8: the keyed sections under `Recall` to depth 2, `english` and the
    axioms' `english` at depth 0, nothing elsewhere; `print_fields`
    answering whether it wrote a keyed line; the recorded parentheses while
    the beginning is `Ready`; `children_header` the phrase; the recorded
    annotation and the theory's keywords not read; the section's five
    renderings whole."""
    f, x = forest(COMMUTATIVE | {"children": [{"kind": "lemma", "name": "comm_inv", "statement": {
        "english": "The inverse of an element commutes with it", "for_any": [{"name": "x", "type": "'a"}],
        "premises": [{"name": "hx", "term": "x ∈ carrier G"}], "conclusion": "inv x ⊗ x = x ⊗ inv x"}}]},
        IDEMPOTENT | {"imports": [{"locale": "semigrp", "qualifier": "S", "instantiations": [{"name": "f", "term": "f"}]}]},
        bounded(name="LF", english="The p-adic integers for a prime p", imports=[{"locale": "padic_integers", "instantiations": [
            {"name": "Zp", "term": "_"}, {"name": "p", "term": "p"}]}], fixes=[{"name": "p", "type": "int"}], assumes=[]),
        bounded(name="pb", implicit_structure="padic_int p"), kinds=KINDS)
    c, i, lf, pb = x.sub_nodes
    [recall_c, recall_i, recall_lf, quick_lf, quick_c] = fenced_blocks(LD, "8.")

    def fields(node, mode, depth):
        out = io.StringIO()
        keyed = node.print_fields(0, out, mode, depth)
        return keyed, out.getvalue().splitlines()
    declaration = [line[2:] for line in recall_c[1:10]]                         # the fence's lines, less the node's indent
    assert fields(c, M.RECALL, 0) == (True, declaration)                       # the declaration, `english` first
    assert fields(c, M.RECALL, 1) == (True, [line for line in declaration[1:] if not line.startswith("    ")])
    assert fields(c, M.RECALL, 2) == fields(c, M.RECALL, 1) and fields(c, M.RECALL, 3) == (False, [])
    for mode in (M.OUT_FOCUS, M.Relative_Focus(frozenset({c}), 0), M.Relative_Focus(frozenset({x}), -1)):
        assert fields(c, mode, 0) == (False, [])
    for keywords in (None, frozenset(), frozenset({"comm", "G", "M"})):     # the stored text, whatever the theory recorded
        x.keywords = keywords
        assert fields(c, M.RECALL, 1) == (True, [line for line in declaration[1:] if not line.startswith("    ")])
    x.keywords = None
    assert fields(lf, M.RECALL, 1) == (True, ["imports:", "  padic_integers where Zp = _ and p = p", "fixes:", "  p :: int",
                                            "implicit_structure: null"])
    assert fields(pb, M.RECALL, 1) == (True, ["fixes:", "  n :: nat", 'implicit_structure: "padic_int p"', "assumes:", '  pos: "0 < n"'])
    assert Locale.children_header(c) == "locale context" == locale.CHILDREN_HEADER
    # the parentheses: the recorded ones under a `Ready` beginning, none otherwise
    recorded(c, parenthesised=(True,))
    assert fields(c, M.RECALL, 2)[1][-1] == '  comm: "⋀(x::\'a) (y::\'a). ⟦x ∈ carrier G; y ∈ carrier G⟧ ⟹ (x ⊗ y = y ⊗ x)"'
    c.evaluation_status_beginning = M.CannotEvaluate((IsaTerm.from_agent("e"),))
    assert fields(c, M.RECALL, 2)[1][-1] == recall_c[8][2:]
    # §8's renderings whole; the recorded annotation is not printed (§8): the fence's `G :: "('a, 'b) monoid_scheme"` carries none
    recorded(c, annotations=(OTIMES,))
    with_proof(c.sub_nodes[0], M.READY_CLEAN, RUNNING)
    me = stand_ins.agent(f.conversation)
    assert f.render(c, M.RECALL, me).splitlines() == recall_c
    i.evaluation_status_beginning = M.CannotEvaluate((IsaTerm.from_agent('Undefined locale: "semigrp"'),))
    i.evaluation_status_ending = M.READY_CLEAN
    assert f.render(i, M.RECALL, me).splitlines() == recall_i
    [cancellation, _, _] = [b for b in fenced_blocks(LD, "6.") if b[0].startswith("`null` cancels")][0]
    [unfolded] = [b for b in fenced_blocks(LD, "6.") if b[0].startswith("The following definitions") and "names" in b[2]]
    recorded(lf, beginning=M.Ready((IsaTerm.from_agent(cancellation), IsaTerm.from_agent("\n".join(unfolded)))))
    assert f.render(lf, M.RECALL, me).splitlines() == recall_lf
    # the quickview: the node a focus under its theory, its fields unwritten, the message blocks once per run
    me.seen.clear()

    def part(node, block):
        lines = f.render(x, M.Relative_Focus(frozenset({node}), 0), me).splitlines()
        at = lines.index(block[0])
        return lines[at:at + len(block)]
    assert part(lf, quick_lf) == quick_lf
    seen = [quick_lf[0], quick_lf[-1][2:]]                  # the notice shown: no keyed line, so no header (PRINT.md §2)
    assert part(lf, seen) == seen
    assert part(c, quick_c) == quick_c
