"""`Record` (node_classes/RECORD.md): with no Isabelle, the schema and the
descriptions (§2, §3), `gen` and the field check (§4), the definition
as the node holds, stores and prints it (§2, §8), the node's name and
the framework's `DuplicateName` on it, the emitted text (§5), the
message and the status (§6), the mark (§7).
Run: python -m pytest test/test_record.py
"""

import io
import json
import re

import jsoncomment
import pytest

import test_session_theory as ts
from baselines import DOCS, fenced_blocks, fenced_lines
from Isabelle_RPC_Host.unicode import IsaTerm
from isabelle_theory_agent import edit, isabelle_driver, model as M
from isabelle_theory_agent.exceptions import DuplicateName, InvalidField, InvalidName, RawASTError
from isabelle_theory_agent.std import common, record
from isabelle_theory_agent.std.common import Type_Parameter
from isabelle_theory_agent.std.record import Field, Record
from isabelle_theory_agent.store import FRAMEWORK_FIELDS, Forest_Store
from std_forest import (
    KINDS, assert_a_missing_row_is_refused_at_start, field_check, forest, insert, inv, refused, reloaded)
from test_descriptions import descriptions
from test_model import locked, run
from test_session_theory import Forest_Under_Test, session, theory

table = ts.table                    # the fake state slot table and the fake wire, per test
RD = DOCS / "node_classes" / "RECORD.md"
COMMON = DOCS / "node_classes" / "COMMON.md"
ROWS = ("english", "type_parameters", "type_name", "parent", "fields")      # the class's rows (§1)
[VARIABLE, VARIABLE_TWICE] = [b for b in fenced_blocks(COMMON, "4.") if b[0].startswith("The field")][0]     # COMMON §4's, of a type parameter

# §2's example, the construct of `'a point`, read from the document
POINT = json.loads("\n".join(fenced_blocks(RD, "2.")[0]))
CPOINT = {"kind": "record", "english": "A point with a colour", "type_name": "cpoint",
          "type_parameters": [{"name": "'a"}], "parent": "'a point", "fields": [{"name": "colour", "type": "colour"}]}
PAIR = {"kind": "record", "english": "A pair of values", "type_name": "pair",
        "type_parameters": [{"name": "'a"}], "fields": [{"name": "fst", "type": "'a"}, {"name": "snd", "type": "'b"}]}


def definition(type_name="point", fields=({"name": "xcoord", "type": "'a"}, {"name": "ycoord", "type": "'a"}),
               english="A point in the plane", type_parameters=({"name": "'a"},), parent=None):
    """A `record` construct; §2's example by default; `type_parameters` or
    `parent` None leaves the key out."""
    return {"kind": "record", "english": english,
            **({"type_parameters": list(type_parameters)} if type_parameters is not None else {}),
            "type_name": type_name, **({"parent": parent} if parent is not None else {}), "fields": list(fields)}


GREEK = definition("t", type_parameters=({"name": "'α", "sort": "linorder"},), fields=({"name": "x⇩1", "type": "'α"},),
                   english="Greek", parent="ε")          # names whose `unicode` and `ascii` differ; a bare parent


# --- the schema and the descriptions (§2, §3) ------------------------------

def test_the_schema_and_the_descriptions_are_the_documents():
    [_, schema] = fenced_blocks(RD, "2.")
    text = re.sub(r'"\$defs": \{[^}]*\}.*', '"$defs": {}', "\n".join(schema))      # the spread and its comment
    expected = jsoncomment.JsonComment().loads(text)
    expected["$defs"] = {**common.TYPE_PARAMETER_DEFS}
    assert Record.construct_schema == expected
    assert list(record.KINDS) == ["record"]
    assert sorted(descriptions(Record.construct_schema)) == sorted(
        fenced_lines(RD, "3.") + descriptions(common.TYPE_PARAMETER_DEFS))
    assert POINT == definition()


# --- `gen` (§2, §4) ----------------------------------------------------------

def test_gen_keeps_the_definition_normalised_as_isaterms_and_names_the_node():
    f, x = forest(definition(fields=({"name": " xcoord ", "type": " 'a "}, {"name": "ycoord\n", "type": "'a\n  list"}),
                             english="A point\n in the plane ", type_parameters=({"name": " 'a ", "sort": ""},)))
    (p,) = x.sub_nodes
    assert isinstance(p, Record) and p.kind == "record" and p.name == "point" and p.english == "A point in the plane"
    assert p.type_parameters == (Type_Parameter(IsaTerm.from_agent("'a"), None),)
    assert p.parent_record is None
    assert p.fields == (Field(IsaTerm.from_agent("xcoord"), IsaTerm.from_agent("'a")),
                        Field(IsaTerm.from_agent("ycoord"), IsaTerm.from_agent("'a list")))
    assert all(isinstance(t, IsaTerm) for g in p.fields for t in (g.name, g.type))
    assert f.id_of(p) == "record_point"
    (q,) = insert(f, x, 1, [CPOINT | {"parent": " 'a\tpoint "}])
    assert q.name == "cpoint" and q.parent_record == IsaTerm.from_agent("'a point") and f.id_of(q) == "record_cpoint"
    assert q.parent_type() == q.parent_record                  # authored with its arguments: as authored
    (r,) = insert(f, x, 2, [definition("pt", type_parameters=None, fields=({"name": "px", "type": "nat"},))])
    assert r.type_parameters == () and r.parent_record is None and r.parent_type() is None   # `type_parameters` left out: none (§2)
    for empty in ("", " \n "):                                     # an empty `parent` is no parent (§2)
        (w,) = insert(f, x, 3, [definition("e", parent=empty)])
        assert w.parent_record is None and w.parent_type() is None and w.message()[2] is None
        run(locked(f, edit.delete(w)))
    # a bare parent takes the record's type parameters in their order (§2): kept as authored, applied in use
    (s,) = insert(f, x, 3, [definition("cp", type_parameters=({"name": "'a"}, {"name": "'b"}), parent=" point ",
                                       fields=({"name": "z", "type": "nat"},))])
    assert s.parent_record == IsaTerm.from_agent("point") and s.parent_type() == IsaTerm.from_agent("('a, 'b) point")
    (u,) = insert(f, x, 4, [definition("cp1", parent="point", fields=({"name": "z", "type": "'a"},))])
    assert u.parent_type() == IsaTerm.from_agent("'a point")
    (v,) = insert(f, x, 5, [definition("cp0", type_parameters=(), parent="point", fields=({"name": "z", "type": "nat"},))])
    assert v.parent_type() == IsaTerm.from_agent("point")
    inv(f)


def test_gen_refuses_as_section_4_says():
    """§4's `gen` refuses only a type name outside §1's grammar
    (RENDER_BASELINES §2's line), before any field is judged; an empty
    `fields`, a field without a type and an unknown field by the
    framework."""
    f, x = forest()
    [invalid] = [line for line in fenced_lines(DOCS / "RENDER_BASELINES.md", "2.")
                 if line.startswith("`my-list` is not a valid type name")]
    e = refused(f, x, [definition("my-list")], InvalidName)
    assert (e.name, e.grammar) == ("my-list", "type name") and str(e) == "At `constructs[0]`: " + invalid
    for name in ("1st", "point_", "a point", "x'y-", "", "α"):
        assert refused(f, x, [definition(name)], InvalidName).grammar == "type name"
    assert refused(f, x, [definition("my-list", type_parameters=({"name": "a"},))], InvalidName).grammar == "type name"
    for raw in ({"kind": "record", "english": "e", "type_name": "t", "fields": []},
                {"kind": "record", "english": "e", "type_name": "t", "fields": [{"name": "x"}]},
                {"kind": "record", "english": "e", "type_name": "t", "fields": [{"name": "x", "type": "nat"}], "overloaded": True}):
        refused(f, x, [raw], RawASTError)
    assert x.sub_nodes == []
    inv(f)


def test_the_field_check_refuses_as_section_4_says():
    """§4's field check, each sentence told alone, no path before it: the
    type parameters and their use by the shared checks, COMMON §4's
    sentences pinned by test_common.py; the fields, the two sentences of
    §4's block; what §4 admits; §4's order under two faults."""
    f, x = forest()
    [invalid] = [line for line in fenced_lines(DOCS / "RENDER_BASELINES.md", "2.")
                 if line.startswith("`my-list` is not a valid type name")]
    [identifier, twice] = fenced_blocks(RD, "4.")[0]
    e = field_check(f, x, [definition(type_parameters=({"name": "a"},))])
    assert str(e) == VARIABLE and e.field == "type_parameters[0].name"
    e = field_check(f, x, [definition(type_parameters=({"name": "'a"}, {"name": "'a"}))])
    assert str(e) == VARIABLE_TWICE and e.field == "type_parameters[1].name"
    e = field_check(f, x, [definition(fields=({"name": "xcoord", "type": "'a"}, {"name": "ycoord_", "type": "'a"}))])
    assert str(e) == identifier and e.field == "fields[1].name"
    for name in ("1x", "x y", "", "x-"):
        assert field_check(f, x, [definition(fields=({"name": name, "type": "'a"},))]).field == "fields[0].name"
    e = field_check(f, x, [definition(fields=({"name": "xcoord", "type": "'a"}, {"name": "xcoord", "type": "'a"}))])
    assert str(e) == twice and e.field == "fields[1].name"
    assert identifier.endswith(": it " + invalid.split(": a type name ")[1])
    # every type parameter used, in a field's type or `parent` — COMMON §4's check and sentence, pinned by test_common.py
    [unused] = [line for line in fenced_lines(COMMON, "4.") if line.endswith("which is not used.")]
    e = field_check(f, x, [definition(type_parameters=({"name": "'a"}, {"name": "'b"}))])
    assert str(e) == unused and e.field == "type_parameters[1]"
    assert field_check(f, x, [definition(fields=({"name": "x", "type": "'ab"},))]).field == "type_parameters[0]"
    # what §4 admits: a parameter used in `parent` alone, in its applied form or bare (§2); `parent`, a field's type and
    # the reserved field name `more`, which are Isabelle's to judge
    assert field_check(f, x, [definition("cp", type_parameters=({"name": "'a"}, {"name": "'b"}), parent="'a point",
                                         fields=({"name": "extra", "type": "'b"},))]) is None
    assert field_check(f, x, [definition("cp", type_parameters=({"name": "'a"}, {"name": "'b"}), parent="point",
                                         fields=({"name": "extra", "type": "nat"},))]) is None
    assert field_check(f, x, [definition("odd", parent="nat", type_parameters=(),
                                         fields=({"name": "z", "type": "not a type"}, {"name": "more", "type": "nat"}))]) is None
    assert field_check(f, x, [definition()]) is None
    # §4's order under two faults: the parameters, then the fields, then their use
    assert field_check(f, x, [definition(type_parameters=({"name": "a"},), fields=({"name": "x_", "type": "'a"},))]).field == "type_parameters[0].name"
    assert field_check(f, x, [definition(fields=({"name": "x_", "type": "nat"},))]).field == "fields[0].name"
    assert x.sub_nodes == []
    inv(f)


def test_a_sibling_bearing_the_node_s_id_component_is_the_framework_s_duplicate_name():
    f, x = forest(definition())
    e = refused(f, x, [definition(fields=({"name": "z", "type": "'a"},))], DuplicateName)
    assert e.id_component == "record_point" and e.taken_by == "record_point"
    inv(f)


def test_the_definition_is_stored_in_the_construct_s_shape(tmp_path):
    """§1: the authored fields in the construct's shape, in `unicode`,
    `parent` as authored and a None-valued row when there is none; every
    row read with `rows.get`, a missing one refused at start."""
    store = Forest_Store(tmp_path / "TAT.sqlite", ts.stand_ins.log())
    f, x = forest(definition(), CPOINT,
                  definition("entry", type_parameters=({"name": "'a", "sort": "linorder"}, {"name": "'b"}),
                             fields=({"name": "key", "type": "'a"}, {"name": "value", "type": "'b"}), english="Entries"),
                  GREEK, store=store)
    nodes = x.sub_nodes
    with f.store.transaction():
        for n in nodes:
            f._store_node(n)
    before = [(n.name, n.english, n.type_parameters, n.parent_record, n.fields) for n in nodes]
    rows = [store.fields(n.identity) for n in nodes]
    assert all(set(r) - set(FRAMEWORK_FIELDS) == set(ROWS) for r in rows)
    assert [r["parent"] for r in rows] == [None, "'a point", None, "ε"] and rows[3]["fields"] == [{"name": "x⇩1", "type": "'α"}]
    store.close()
    f2 = Forest_Under_Test(store=Forest_Store(tmp_path / "TAT.sqlite", ts.stand_ins.log()), kinds=KINDS)
    loaded = f2.sub_nodes[0].sub_nodes[0].sub_nodes
    assert [(n.name, n.english, n.type_parameters, n.parent_record, n.fields) for n in loaded] == before
    assert all(isinstance(n, Record) for n in loaded)
    f2.store.close()
    assert_a_missing_row_is_refused_at_start(tmp_path / "TAT.sqlite", nodes[1].identity, ROWS)


def test_a_definition_with_a_bad_field_is_stored_and_loads_as_it_was(tmp_path):
    """`from_store` reads the type parameters back as stored, judging
    nothing, and the field check refuses the loaded node with COMMON §4's
    sentence."""
    (r,), (loaded,) = reloaded(tmp_path / "TAT.sqlite", definition(type_parameters=({"name": "a"},)))
    assert loaded.type_parameters == r.type_parameters and loaded.fields == r.fields
    with pytest.raises(InvalidField) as e:
        loaded.check_fields()
    assert str(e.value) == VARIABLE


# --- the message and the status (§6), the mark (§7) ------------------------

def test_eval_opr_sends_the_definition_and_reads_the_messages(monkeypatch):
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        definition(), CPOINT, PAIR]})])                       # a fake theory: its header runs no call
    (x,) = s.sub_nodes
    p, q, r = x.sub_nodes
    calls = []
    [*_, failed] = fenced_blocks(RD, "8.")
    refusal = "\n".join(line.strip() for line in failed[4:])          # Isabelle's one message of two lines (§8)

    async def call(conversation, name, args):
        calls.append((name, args))
        return [refusal] if args[2][1] == "pair" else []
    monkeypatch.setattr(isabelle_driver, "call", call)
    run(x.evaluate_to(None, False))
    assert [name for name, _ in calls] == ["TAT.Record.evaluate"] * 3
    assert [args[:2] for _, args in calls] == [(n.state.to_msgpack(), n.resulting_state().to_msgpack()) for n in (p, q, r)]
    assert calls[0][1][2] == p.message() == ([("'a", None)], "point", None, [("xcoord", "'a"), ("ycoord", "'a")])
    assert q.message() == ([("'a", None)], "cpoint", ("'a point", False), [("colour", "colour")])
    for n in (p, q):
        assert isinstance(n._status, M.Ready) and n._status.messages == () and n.mark(M.BRIEFING, 0) == "complete"
    assert isinstance(r._status, M.CannotEvaluate) and [m.unicode for m in r._status.messages] == [refusal]
    assert r.mark(M.BRIEFING, 0) == "failed" and p.is_finished() and q.is_finished() and not r.is_finished()
    (t,) = insert(f, x, 3, [definition("entry", type_parameters=({"name": "'a", "sort": "linorder"}, {"name": "'b"}),
                                       fields=({"name": "key", "type": "'a ⇒ 'b"},), english="Entries", parent="point")])
    assert t.message() == ([("'a", "linorder"), ("'b", None)], "entry", ("('a, 'b) point", True),
                           [("key", "'a \\<Rightarrow> 'b")])          # a bare parent: applied, and flagged bare (§6)
    assert t.mark(M.BRIEFING, 0) == "not evaluated"


# --- what it prints (§8) -----------------------------------------------------

def test_print_fields_writes_the_definition_and_english_by_depth():
    f, x = forest(definition(), CPOINT)
    p, q = x.sub_nodes
    [one, two, failed] = fenced_blocks(RD, "8.")

    def fields(node, mode, depth):
        out = io.StringIO()
        node.print_fields(0, out, mode, depth)
        return out.getvalue().splitlines()
    assert [fields(p, M.RECALL, d) for d in range(4)] == [one, one[:1], one[:1], []]
    assert [fields(q, M.RECALL, d) for d in range(4)] == [two, two[:1], two[:1], []]
    assert fields(p, M.OUT_FOCUS, 0) == [] and fields(p, M.Relative_Focus(frozenset({p}), 0), 0) == []
    (r,) = insert(f, x, 2, [PAIR])
    assert fields(r, M.RECALL, 0) == [line.strip() for line in failed[1:3]]      # §8's last example, under its node line
    # against no keyword, whatever the theory recorded: every name bare, a sort and a type quoted unless an identifier
    (t,) = insert(f, x, 3, [definition("entry", type_parameters=({"name": "'a", "sort": "linorder"}, {"name": "'b"}),
                                       fields=({"name": "key", "type": "'a"}, {"name": "value", "type": "'b list"}),
                                       english="Entries", parent="nat")])
    line = ["('a :: linorder, 'b) entry = \"('a, 'b) nat\" + key :: \"'a\" value :: \"'b list\""]   # a bare parent, applied (§2)
    for keywords in (None, frozenset(), frozenset({"point", "xcoord", "nat", "linorder", "entry", "key"})):
        x.keywords = keywords
        assert fields(t, M.RECALL, 1) == line and fields(p, M.RECALL, 1) == one[:1], keywords


# --- emission (§5) ------------------------------------------------------------

def test_the_emitted_text_is_section_5_s():
    [one, two] = fenced_blocks(RD, "5.")
    f, x = forest(definition(), CPOINT)
    p, q = x.sub_nodes
    x.keywords = frozenset()                                 # recorded by a header run, which emission presupposes

    def emitted(node) -> list[str]:
        """In `unicode` (§5); the file's `\\<name>` form is the compile's conversion (COMPILATION §2)."""
        out = io.StringIO()
        assert node.emit(1, out) == 1
        assert "\\<" not in out.getvalue()                                 # nothing written in `ascii`
        return out.getvalue().splitlines()

    def expected(*unicode_lines: str) -> list[str]:
        return ["  " + line for line in unicode_lines]
    assert emitted(p) == expected(*one) and emitted(q) == expected(*two)
    x.keywords = frozenset({"point", "xcoord", "colour", "linorder", "unit"})   # keywords of the theory: quoted (§5)
    assert emitted(p) == expected("text ‹A point in the plane.›", 'record \'a "point" =', '  "xcoord" :: "\'a"', '  ycoord :: "\'a"')
    assert emitted(q)[1:] == expected("record 'a cpoint = \"'a point\" +", '  "colour" :: "colour"')
    (t,) = insert(f, x, 2, [definition("entry", type_parameters=({"name": "'a", "sort": "{zero, linorder}"}, {"name": "'b"}),
                                       fields=({"name": "key", "type": "'a"}, {"name": "value", "type": "'b ⇒ nat"}),
                                       english="Entries!")])
    assert emitted(t) == expected("text ‹Entries!›", 'record (\'a :: "{zero, linorder}", \'b) entry =',
                                  '  key :: "\'a"', '  value :: "\'b ⇒ nat"')
    (u,) = insert(f, x, 3, [definition("pt", type_parameters=(), fields=({"name": "px", "type": "nat"}, {"name": "py", "type": "int"}),
                                       english="Points", parent="unit")])
    assert emitted(u)[1:] == expected('record pt = "unit" +', "  px :: nat", "  py :: int")   # the parent, a keyword: quoted
    (v,) = insert(f, x, 4, [definition("cp", type_parameters=({"name": "'a"}, {"name": "'b"}), parent="point",
                                       fields=({"name": "z", "type": "nat"},), english="Extended")])
    assert emitted(v)[1:] == expected("record ('a, 'b) cp = \"('a, 'b) point\" +", "  z :: nat")   # a bare parent, applied (§2)
    v.english = "Sums of n²"                                      # prose through `latex_of` (COMPILATION.md §3)
    assert emitted(v)[0] == "  text ‹Sums of ‹n²›.›"


def test_the_two_spellings_are_kept_apart():
    """§2, §5, §8: a name or type whose `unicode` and `ascii` differ — `'α`,
    `x⇩1`, `ε` — is stored, printed and emitted in `unicode` and sent to
    Isabelle in `ascii`."""
    f, x = forest(GREEK)
    (p,) = x.sub_nodes
    x.keywords = frozenset()
    assert p.message() == ([("'\\<alpha>", "linorder")], "t", ("'\\<alpha> \\<epsilon>", True), [("x\\<^sub>1", "'\\<alpha>")])
    rows = {}
    p.to_store(type("Rows", (), {"put": lambda self, k, v: rows.__setitem__(k, v)})())
    assert rows["type_parameters"] == [{"name": "'α", "sort": "linorder"}]
    assert rows["parent"] == "ε" and rows["fields"] == [{"name": "x⇩1", "type": "'α"}]      # as authored: bare
    out = io.StringIO()
    p.print_fields(0, out, M.RECALL, 1)
    assert out.getvalue() == "('α :: linorder) t = \"'α ε\" + x⇩1 :: \"'α\"\n"
    out = io.StringIO()
    p.emit(0, out)
    assert out.getvalue().splitlines()[1:] == ["record ('α :: linorder) t = \"'α ε\" +", "  x⇩1 :: \"'α\""]
