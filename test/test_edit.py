"""The four-step edit build of `edit.py` (MODULE_STRUCTURE §4.2): construct detached,
gates, commit, completed events — atomicity, hook order, the exception
paths, amend inheritance, move.  Run: python -m pytest test/test_edit.py
"""

import random
from typing import Annotated, NotRequired, TypedDict

import pytest

import stand_ins
import test_model as tm
from invariants import assert_invariants, assert_store_mirrors
from test_model import Block, T, add, locked, run, slot, st

import isabelle_theory_agent.model as M
from isabelle_theory_agent import edit, plugin
from isabelle_theory_agent.exceptions import (
    BadEdit, ChildrenNotInheritable, DuplicateName, DuplicateTheoryShortName,
    InvalidField, InvalidName, MalformedRawAST, MissingField,
    MoveIntoOwnSubtree, TAT_DisasterError, TAT_InternalError, UnexpectedChildren,
    UnexpectedField, UnknownKind)
from isabelle_theory_agent.model import NON_EMPTY, NOT_EVALUATED, Location
from test_model import CANNOT_EVALUATE, READY


@pytest.fixture(autouse=True)
def table(monkeypatch):
    tm.TABLE.clear()
    tm.TABLE.install(monkeypatch)
    EVENTS.clear()


def inv(f):
    assert_invariants(f, tm.TABLE)
    assert_store_mirrors(f)


def deletes():
    return [c for c in tm.TABLE.calls if c[0] == "delete"]


# --- recording node classes -------------------------------------------------

EVENTS: list[tuple] = []

class Recording:
    def on_invalidated(self, operation):
        EVENTS.append((self.name, "invalidated", operation))
        super().on_invalidated(operation)
    def on_deleting(self, reason): EVENTS.append((self.name, "deleting", reason))
    def on_deleted(self, reason): EVENTS.append((self.name, "deleted", reason))
    def on_inserted(self): EVENTS.append((self.name, "inserted"))
    def on_inheriting(self, new_parent):
        EVENTS.append((self.name, "inheriting", new_parent.name))
    def on_inherited(self, old_parent):
        EVENTS.append((self.name, "inherited", old_parent.name))
    def on_moving(self, new_location):
        EVENTS.append((self.name, "moving",
                       new_location.parent.name, new_location.index))
    def on_moved(self, old_location):
        EVENTS.append((self.name, "moved",
                       old_location.parent.name, old_location.index))

class RT(Recording, T):
    pass

class RBlock(Recording, Block):
    def on_removing_child(self, child, mode):
        EVENTS.append((self.name, "removing_child", child.name, mode))
    def on_added_child(self, child, mode):
        EVENTS.append((self.name, "added_child", child.name, mode))


KINDS = {"t": RT, "block": RBlock}


class CT(RT):                                # a leaf recording what its gen is given
    @classmethod
    async def gen(cls, config, raw):
        EVENTS.append((raw["name"], "gen", config))
        return await super().gen(config, raw)


def told():
    """What each `gen` was given, read after the call: a `batch_before`
    that were the framework's live list would have grown since."""
    return [(name, [n.name for n in config.batch_before], config.role, config.replaces())
            for name, _, config in events("gen")]


class Nesting_RawAST(TypedDict):             # a declaration that nests itself, at module level: refused
    child: NotRequired["Nesting_RawAST"]


def rbuild(kinds=KINDS):
    """Theory > [Section > [a, b], c], every class recording; `kinds` the
    forest's kind table."""
    f = tm.OneTreeForest(tm.CONN, kinds=kinds)
    thy = add(f, RBlock(f, slot(), "Theory"))
    sec = add(thy, RBlock(thy, slot(), "Section"))
    a = add(sec, RT(sec, slot(), "a")); b = add(sec, RT(sec, slot(), "b"))
    c = add(thy, RT(thy, slot(), "c"))
    return f, thy, sec, a, b, c


def events(*types):
    return [e for e in EVENTS if e[1] in types]


def record(node, **fields):
    """Change a node's fields outside an edit and store the node, standing
    where an evaluation hook's write of a recorded field will go (the plan's
    §2); the framework does not make that write yet (§7, step 3)."""
    for field, value in fields.items():
        setattr(node, field, value)
    f = node.forest()
    with f.store.transaction():
        f._store_node(node)


# --- insert -----------------------------------------------------------------

def test_insert_nested_and_completed_order():
    f, thy, sec, a, b, c = rbuild()
    raws = [{"kind": "block", "name": "S2",
             "children": [{"kind": "t", "name": "x"},
                          {"kind": "t", "name": "y"}]}]
    (s2,) = run(locked(f, edit.insert(thy,2, raws)))
    assert thy.sub_nodes == [sec, c, s2]
    assert [n.name for n in s2.sub_nodes] == ["x", "y"]
    assert all(n.parent is s2 for n in s2.sub_nodes)
    # the edit's one `committed` record (LOGGING.md §4), after its store
    [committed] = stand_ins.records("edit")
    x, y = s2.sub_nodes
    assert committed["event"] == "committed" and committed["data"] == {
        "operation": "insert", "parent": f.full_id(thy), "index": 2,
        "created": [[f.full_id(s2), "block"], [f.full_id(x), "t"], [f.full_id(y), "t"]],
        "removed": [], "moved": [], "invalidated": []}
    assert stand_ins.events("store")[-1] == "transaction"
    assert stand_ins.records("store")[-1]["ts"] <= committed["ts"]
    assert EVENTS == [                        # tree order over what entered
        ("Theory", "added_child", "S2", "insert_or_delete"),
        ("S2", "inserted"),
        ("S2", "added_child", "x", "insert_or_delete"),
        ("x", "inserted"),
        ("S2", "added_child", "y", "insert_or_delete"),
        ("y", "inserted"),
    ]

def test_batch_aborts_whole_with_the_path(  ):
    f, thy, sec, a, b, c = rbuild()
    run(c.evaluate_to(None, False))
    EVENTS.clear()
    before = list(thy.sub_nodes)
    before_table = dict(tm.TABLE.values)
    before_deleted = list(tm.TABLE.deleted)
    raws = [{"kind": "t", "name": "u"},
            {"kind": "block", "name": "S2",
             "children": [{"kind": "wrong", "name": "x"}]}]
    with pytest.raises(UnknownKind) as e:
        run(locked(f, edit.insert(thy,2, raws)))
    assert e.value.raw_ast_path == "constructs[1].children[0]"
    assert e.value.kind == "wrong" and e.value.available_kinds == ["t", "block"]
    assert thy.sub_nodes == before and EVENTS == []      # forest untouched
    assert tm.TABLE.values == before_table               # and nothing remote
    assert tm.TABLE.deleted == before_deleted
    inv(f)                                               # and nothing stored

def test_duplicate_name_against_sibling_and_batch():
    f, thy, sec, a, b, c = rbuild()
    with pytest.raises(DuplicateName) as e:
        run(locked(f, edit.insert(thy,
            2, [{"kind": "t", "name": "c"}])))
    assert e.value.taken_by == "block_Theory.t_c" and e.value.raw_ast_path == "constructs[0]"
    with pytest.raises(DuplicateName) as e:
        run(locked(f, edit.insert(thy,
            2, [{"kind": "t", "name": "z"}, {"kind": "t", "name": "z"}])))
    assert e.value.taken_by == "constructs[0]" and e.value.raw_ast_path == "constructs[1]"

def test_the_rawast_error_family():
    f, thy, sec, a, b, c = rbuild()
    def insert(raw):
        return locked(f, edit.insert(thy,2, [raw]))
    with pytest.raises(MalformedRawAST) as e:
        run(insert(42))
    assert not e.value.missing_kind
    with pytest.raises(UnexpectedField) as e:        # a row the framework stores is no field of a construct
        run(insert({"kind": "t", "name": "x", "last_evaluation_statuses": [["ready", []]]}))
    assert (e.value.holder, e.value.field) == ("t", "last_evaluation_statuses")
    with pytest.raises(MalformedRawAST) as e:
        run(insert({"name": "x"}))
    assert e.value.missing_kind
    with pytest.raises(MissingField) as e:
        run(insert({"kind": "t"}))
    assert (e.value.holder, e.value.field) == ("t", "name")
    with pytest.raises(InvalidField) as e:
        run(insert({"kind": "t", "name": 5}))
    assert e.value.reason == "must be a string"
    with pytest.raises(InvalidField) as e:
        run(insert({"kind": 5}))
    assert (e.value.field, e.value.reason) == ("kind", "must be a string")
    with pytest.raises(InvalidField):
        run(insert({"kind": "t", "name": True}))     # a flag is not a string
    with pytest.raises(InvalidName) as e:
        run(insert({"kind": "t", "name": "bad name"}))
    assert e.value.raw_ast_path == "constructs[0]"
    with pytest.raises(UnexpectedChildren) as e:
        run(insert({"kind": "t", "name": "x", "children": []}))
    assert e.value.is_leaf

FACT = {"type": "object", "properties": {"name": {"type": "string"}},
        "required": ["name"], "additionalProperties": False}


def construct_schema(fields, required=(), defs=None):
    """A construct schema of a stand-in kind `t` with `fields`."""
    schema = {"type": "object",
              "properties": {"kind": {"const": "t"}, **fields},
              "required": ["kind", *required], "additionalProperties": False}
    if defs is not None:
        schema["$defs"] = defs
    return schema


def check(schema, raw):
    plugin.check_call(schema, "t", raw, construct=True)


def refused(schema, cls, raw):
    """A construct's refusal: never marked the tool's (MODULE_STRUCTURE §4.4)."""
    with pytest.raises(cls) as e:
        check(schema, raw)
    assert not e.value.of_tool
    return e.value


INNER = {"type": "object",                                      # a nested object naming the two framework fields
         "properties": {"kind": {"type": "string"}, "children": {"type": "array", "items": {"type": "string"}}},
         "required": ["kind"], "additionalProperties": False}


def test_a_construct_is_checked_against_its_construct_schema():
    """MODULE_STRUCTURE §4.4, `check_call` over a construct: the holder is
    the kind; `kind` passes unread, since the kind table chose the class
    from it; `children` is a declared field — an array, its elements
    `edit.py`'s — which the kind does not "take", nor `kind`, the two set
    aside at the top alone; a `$ref` is followed into the class's `$defs`;
    an `enum` and `minItems` speak for a construct's field as for a tool's
    argument; the innermost field at fault is reported, a typo before its
    own hole."""
    RICH = construct_schema({
        "name": {"type": "string"},
        "priority": {"type": "integer"},
        "weight": {"type": "number"},
        "level": {"type": "string", "enum": ["low", "high"]},
        "note": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
        "facts": {"type": "array", "items": {"$ref": "#/$defs/Fact"}},
        "tags": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "inner": {"$ref": "#/$defs/Inner"},
        "children": {"type": "array", "items": {"$ref": "#/$defs/Construct"}},
    }, required=["name"], defs={"Fact": FACT, "Inner": INNER})
    check(RICH, {"kind": "t", "name": "x"})                       # optionals absent
    check(RICH, {"kind": "lemma", "name": "x"})                   # `kind` unread
    for end in (2**63 - 1, -2**63):                               # both ends of the integer range, under `number` too
        check(RICH, {"kind": "t", "name": "x", "priority": end, "weight": end})
    check(RICH, {"kind": "t", "name": "x", "weight": 1.5})
    check(RICH, {"kind": "t", "name": "x", "priority": 3, "level": "low", "note": "n",
                 "facts": [{"name": "f"}], "tags": ["a"], "inner": {"kind": "k", "children": ["a"]},
                 "children": [5, "not a construct"]})             # the elements are edit.py's
    check(RICH, {"kind": "t", "name": "x", "note": 7})            # the union's other arm
    check(RICH, {"kind": "t", "name": "x", "children": []})
    takes = ["name", "priority", "weight", "level", "note", "facts", "tags", "inner"]
    e = refused(RICH, UnexpectedField, {"kind": "t", "namee": "x"})
    assert (e.holder, e.field, e.takes, e.holder_is_top) == ("t", "namee", takes, True)
    e = refused(RICH, MissingField, {"kind": "t"})
    assert (e.holder, e.field) == ("t", "name")
    e = refused(RICH, MissingField, {"kind": "t", "name": "x", "facts": [{}]})
    assert (e.holder, e.field) == ("t", "facts[0].name")          # nested required
    e = refused(RICH, UnexpectedField, {"kind": "t", "name": "x", "facts": [{"name": "f", "extra": 1}]})
    assert (e.holder, e.field, e.takes, e.holder_is_top) == ("facts[0]", "extra", ["name"], False)
    # below the top, `kind` and `children` are fields like any other: read, and taken
    e = refused(RICH, MissingField, {"kind": "t", "name": "x", "inner": {"children": ["a"]}})
    assert (e.holder, e.field) == ("t", "inner.kind")
    e = refused(RICH, UnexpectedField, {"kind": "t", "name": "x", "inner": {"kind": "k", "x": 1}})
    assert (e.holder, e.field, e.takes, e.holder_is_top) == ("inner", "x", ["kind", "children"], False)
    for raw, field, reason in [
        ({"kind": "t", "name": 5}, "name", "must be a string"),
        ({"kind": "t", "name": True}, "name", "must be a string"),              # a flag is not a string
        ({"kind": "t", "name": "x", "priority": True}, "priority", "must be an integer"),
        ({"kind": "t", "name": "x", "priority": 1.5}, "priority", "must be an integer"),
        ({"kind": "t", "name": "x", "priority": 2**63}, "priority", "must be a 64-bit integer"),      # the signed range
        ({"kind": "t", "name": "x", "priority": -2**63 - 1}, "priority", "must be a 64-bit integer"),
        ({"kind": "t", "name": "x", "note": 2**64}, "note", "must be a 64-bit integer"),            # in an `anyOf` arm too
        ({"kind": "t", "name": "x", "weight": 2**64}, "weight", "must be a 64-bit integer"),        # an integer under `number`
        ({"kind": "t", "name": "x", "level": "mid"}, "level", "must be one of `low`, `high`"),
        ({"kind": "t", "name": "x", "note": []}, "note", "must be a string or an integer"),
        ({"kind": "t", "name": "x", "facts": [{"name": 1}]}, "facts[0].name", "must be a string"),
        ({"kind": "t", "name": "x", "tags": ["a", 5]}, "tags[1]", "must be a string"),   # the element
        ({"kind": "t", "name": "x", "tags": "a"}, "tags", "must be a list"),
        ({"kind": "t", "name": "x", "tags": []}, "tags", "must not be empty"),
        ({"kind": "t", "name": "x", "inner": {"kind": 5}}, "inner.kind", "must be a string"),
        ({"kind": "t", "name": "x", "children": {}}, "children", "must be a list"),
    ]:
        e = refused(RICH, InvalidField, raw)
        assert (e.field, e.reason) == (field, reason), raw
    # a nesting class that declares no `children` takes contents only
    # through later edits (PLUGIN_SYSTEM §3); a class with no field takes nothing
    e = refused(construct_schema({"name": {"type": "string"}}), UnexpectedField,
                {"kind": "t", "name": "x", "children": []})
    assert (e.holder, e.field, e.takes) == ("t", "children", ["name"])
    e = refused(construct_schema({}), UnexpectedField, {"kind": "t", "whatever": 1})
    assert (e.field, e.takes) == ("whatever", [])
    # `children` whose items name node classes: an array, its elements edit.py's
    check(construct_schema({"children": {"type": "array", "items": {
        "anyOf": [{"$ref": "#/$defs/Theory"}, {"$ref": "#/$defs/Construct"}]}}}), {"kind": "t", "children": [5]})


def test_a_union_of_objects_is_told_apart_by_its_choosing_field_in_the_documents_order():
    """MODULE_STRUCTURE §4.4's order for an `anyOf`: a value of no arm's
    JSON type, `must be` the arms' distinct types, each once, in the
    schema's order; of one arm's type, that arm; among objects told apart
    by an `enum` field — a field none of them declares, over all their
    fields in the order they first appear; the choosing field missing; its
    value not a string or outside every arm, `must be one of` all their
    values; then the chosen arm.  A `$ref` arm is followed."""
    SYNTAX = {"anyOf": [
        {"type": "object",
         "properties": {"form": {"type": "string", "enum": ["infix", "infixl"]},
                        "symbol": {"type": "string"}, "priority": {"type": "integer"}},
         "required": ["form", "symbol", "priority"], "additionalProperties": False},
        {"type": "object",
         "properties": {"form": {"type": "string", "enum": ["binder"]}, "symbol": {"type": "string"}},
         "required": ["form", "symbol"], "additionalProperties": False},
        {"type": "object",
         "properties": {"form": {"type": "string", "enum": ["mixfix"]}, "template": {"type": "string"},
                        "priorities": {"type": "array", "items": {"type": "integer"}}},
         "required": ["form", "template"], "additionalProperties": False},
    ]}
    UNION = construct_schema({
        "syntax": {"$ref": "#/$defs/Syntax"},
        "either": {"anyOf": [{"$ref": "#/$defs/Fact"}, {"type": "string"}]},
        "or": {"anyOf": [{"type": "string"}, {"$ref": "#/$defs/Fact"}]},
    }, defs={"Syntax": SYNTAX, "Fact": FACT})
    check(UNION, {"kind": "t", "syntax": {"form": "infixl", "symbol": "#", "priority": 65},
                  "either": {"name": "f"}, "or": "s"})
    check(UNION, {"kind": "t", "syntax": {"form": "mixfix", "template": "_ + _"}, "either": "s"})
    for raw, field, reason in [
        ({"syntax": 5}, "syntax", "must be an object"),                          # three objects, once
        ({"either": 5}, "either", "must be an object or a string"),
        ({"or": 5}, "or", "must be a string or an object"),                      # the schema's order
        ({"syntax": {"form": "postfix", "symbol": "#"}}, "syntax.form",
         "must be one of `infix`, `infixl`, `binder`, `mixfix`"),                # all the arms' values
        ({"syntax": {"form": 5, "symbol": "#"}}, "syntax.form",
         "must be one of `infix`, `infixl`, `binder`, `mixfix`"),                # not a string
        ({"syntax": {"form": "mixfix", "template": "_", "priorities": [1, "x"]}},
         "syntax.priorities[1]", "must be an integer"),                           # inside the chosen arm
    ]:
        e = refused(UNION, InvalidField, {"kind": "t", **raw})
        assert (e.field, e.reason) == (field, reason), raw
    # a field none of the arms declares, before the choosing field's hole
    e = refused(UNION, UnexpectedField, {"kind": "t", "syntax": {"bogus": 1}})
    assert (e.holder, e.field, e.takes, e.holder_is_top) == (
        "syntax", "bogus", ["form", "symbol", "priority", "template", "priorities"], False)
    e = refused(UNION, MissingField, {"kind": "t", "syntax": {"symbol": "#"}})
    assert (e.holder, e.field) == ("t", "syntax.form")
    # the chosen arm: its own fields, its own holes
    e = refused(UNION, UnexpectedField, {"kind": "t", "syntax": {"form": "binder", "symbol": "#", "priority": 1}})
    assert (e.holder, e.field, e.takes) == ("syntax", "priority", ["form", "symbol"])
    e = refused(UNION, MissingField, {"kind": "t", "syntax": {"form": "infix", "symbol": "#"}})
    assert (e.holder, e.field) == ("t", "syntax.priority")
    # one arm of the value's type: straight to it, a `$ref` arm followed
    e = refused(UNION, UnexpectedField, {"kind": "t", "either": {"bogus": 1}})
    assert (e.holder, e.field, e.takes) == ("either", "bogus", ["name"])
    # the choosing field is the one every arm requires with an `enum`: an
    # optional `enum` field the arms share chooses nothing
    STYLED = construct_schema({"s": {"anyOf": [
        {"type": "object", "required": ["form"], "additionalProperties": False,
         "properties": {"form": {"type": "string", "enum": ["a"]}, "style": {"type": "string", "enum": ["x", "y"]}}},
        {"type": "object", "required": ["form"], "additionalProperties": False,
         "properties": {"form": {"type": "string", "enum": ["b"]}, "style": {"type": "string", "enum": ["x", "y"]}}}]}})
    check(STYLED, {"kind": "t", "s": {"form": "a"}})
    e = refused(STYLED, InvalidField, {"kind": "t", "s": {"form": "a", "style": "z"}})
    assert (e.field, e.reason) == ("s.style", "must be one of `x`, `y`")


def test_schema_grammar_is_closed_at_registration():
    """MODULE_STRUCTURE §4.4's argument schema grammar: what it admits,
    what it refuses, and the union rules — arms of distinct JSON types,
    TypedDicts told apart by one required `Literal` field with disjoint
    values, a `Literal` and a non-empty list never arms."""
    from typing import Any, Literal, NotRequired, TypedDict

    class Fact(TypedDict):
        name: str

    class Fine(TypedDict):
        kind: Literal["t"]                   # kind: the framework's, unchecked
        a: str
        b: NotRequired[bool]
        n: NotRequired[float]
        level: NotRequired[Literal["x", "y"]]
        facts: NotRequired[list[Fact]]
        some: NotRequired[Annotated[list[str], NON_EMPTY]]
        either: NotRequired[Fact | str]
        mixed: NotRequired[str | int | list[str] | Fact]
    plugin.validate_argument_schema(Fine)

    def refused(td, match=""):
        with pytest.raises(TAT_InternalError, match=match):
            plugin.validate_argument_schema(td)
    class HasChildren(TypedDict):
        children: list
    class Optional(TypedDict):
        a: str | None                        # no JSON word for null
    class Dicty(TypedDict):
        a: dict
    class Anything(TypedDict):
        a: Any                               # no field is left opaque
    class LitInt(TypedDict):
        a: Literal[1]
    class TwoObjects(TypedDict):
        a: Fact | Fine                       # no `Literal` tells them apart
    class TwoObjectsInLists(TypedDict):
        a: list[Fact] | list[Fine]           # two arrays
    class TwoObjectsThroughAUnionInAList(TypedDict):
        a: list[str | Fact] | list[Fine]
    class AnyArm(TypedDict):
        a: Any | Fact
    class Nums(TypedDict):
        n: int | float                       # both numbers
    class Dangling(TypedDict):
        a: "NoSuchType"                      # a forward reference nothing resolves
    class LitArm(TypedDict):
        a: Literal["x"] | str
    class NonEmptyArm(TypedDict):
        a: Annotated[list[str], NON_EMPTY] | int
    for td, match in [(HasChildren, "children"), (Optional, "outside"), (Dicty, "outside"),
                      (Anything, "outside"), (LitInt, "one or more strings"),
                      (TwoObjects, "one and the same"), (TwoObjectsInLists, "one JSON type"),
                      (TwoObjectsThroughAUnionInAList, "one JSON type"), (AnyArm, "outside"),
                      (Nums, "one JSON type"), (Dangling, "unresolvable"),
                      (Nesting_RawAST, "nests itself"),
                      (LitArm, "never an arm"), (NonEmptyArm, "never an arm")]:
        refused(td, match)
    refused(dict, "not a TypedDict")         # not a TypedDict at all
    # a declaration is compulsory (PLUGIN_SYSTEM §5); an empty one declares no field
    refused(None, "not a TypedDict")
    class Empty(TypedDict):
        pass
    plugin.validate_argument_schema(Empty)

    # TypedDict arms told apart by one required `Literal` field of disjoint values
    class Infix(TypedDict):
        form: Literal["infix", "infixl"]
        symbol: str
    class Binder(TypedDict):
        form: Literal["binder"]
    class Told(TypedDict):
        s: Infix | Binder
    plugin.validate_argument_schema(Told)
    class Overlapping(TypedDict):
        form: Literal["binder", "infix"]
    class Overlap(TypedDict):
        s: Infix | Overlapping
    class Unrequired(TypedDict):
        form: NotRequired[Literal["binder"]]
    class Hole(TypedDict):
        s: Infix | Unrequired
    class Infix_Mode(TypedDict):
        form: Literal["infix"]
        mode: Literal["a"]
    class Binder_Mode(TypedDict):
        form: Literal["binder"]
        mode: Literal["b"]
    class Two_Fields(TypedDict):
        s: Infix_Mode | Binder_Mode
    refused(Overlap, "not disjoint")
    refused(Hole, "one and the same")
    refused(Two_Fields, "one and the same")


def test_children_field_must_be_a_list():
    f, thy, sec, a, b, c = rbuild()
    for bad in (None, 5, {}, "xy"):
        with pytest.raises(InvalidField) as e:
            run(locked(f, edit.insert(thy,
                2, [{"kind": "block", "name": "S2", "children": bad}])))
        assert e.value.field == "children"

class Undeclared_Block(RBlock):              # a nesting class whose construct declares no `children`
    construct_schema = tm.T_SCHEMA


def test_given_later_stands_for_children_given_in_later_calls():
    """MCP_SPECIFICATION §3.1: `GivenLater` where the class declares
    `children` is a construct without them, nested or an amend's
    replacement; elsewhere it is refused as any `children` is."""
    f, thy, sec, a, b, c = rbuild({**KINDS, "bare": Undeclared_Block})
    (s2, s3) = run(locked(f, edit.insert(thy, 2, [
        {"kind": "block", "name": "S2", "children": plugin.GIVEN_LATER},
        {"kind": "block", "name": "S3", "children": [
            {"kind": "block", "name": "S4", "children": plugin.GIVEN_LATER}]}])))
    assert s2.sub_nodes == [] and [n.name for n in s3.sub_nodes] == ["S4"] and s3.sub_nodes[0].sub_nodes == []
    (s9,) = run(locked(f, edit.amend(sec, [{"kind": "block", "name": "S9", "children": plugin.GIVEN_LATER}])))
    assert [n.name for n in s9.sub_nodes] == ["a", "b"]       # inherited
    with pytest.raises(UnexpectedChildren) as e:
        run(locked(f, edit.insert(thy, 0, [{"kind": "t", "name": "L", "children": plugin.GIVEN_LATER}])))
    assert e.value.is_leaf
    with pytest.raises(UnexpectedField) as e:
        run(locked(f, edit.insert(thy, 0, [{"kind": "bare", "name": "U", "children": plugin.GIVEN_LATER}])))
    assert e.value.field == "children"
    inv(f)


def test_insert_moves_the_value_from_the_source_slot():
    f, thy, sec, a, b, c = rbuild()
    run(c.evaluate_to(None, False))
    (u,) = run(locked(f, edit.insert(thy,
        1, [{"kind": "t", "name": "u"}])))
    # The predecessor's result moved: it is u's input now, and the slot it
    # came from — written by u after the commit — is empty.
    assert tm.TABLE.values[u.state.name] == "end Section"
    assert c.state.name not in tm.TABLE.values

def test_insert_after_an_obstacle_receives_the_written_input():
    f, thy, sec, t1, t2, t3, t4 = tm.build(T1=True)
    run(t4.evaluate_to(None, True))
    assert st(t1) is CANNOT_EVALUATE
    (n,) = run(locked(f, edit.insert(sec,
        1, [{"kind": "t", "name": "N"}])))
    # An obstacle wrote its resulting state (the input copied through), so
    # the one ARCHITECTURE-§3.4 copy happens.
    assert tm.TABLE.values[n.state.name] == "begin Section"
    assert t2.state.name not in tm.TABLE.values


class Fussy(RT):
    @classmethod
    async def gen(cls, config, raw):
        raise InvalidField("name", "never good enough")    # raised bare

def test_gen_raises_bare_and_the_framework_prefixes_the_path():
    f, thy, sec, a, b, c = rbuild(KINDS | {"fussy": Fussy})
    with pytest.raises(InvalidField) as e:
        run(locked(f, edit.insert(thy,
            2, [{"kind": "block", "name": "S2",
                 "children": [{"kind": "t", "name": "x"},
                              {"kind": "fussy", "name": "y"}]}])))
    assert e.value.raw_ast_path == "constructs[0].children[1]"

def test_duplicate_name_inside_a_children_list():
    f, thy, sec, a, b, c = rbuild()
    with pytest.raises(DuplicateName) as e:
        run(locked(f, edit.insert(thy,
            2, [{"kind": "block", "name": "S2",
                 "children": [{"kind": "t", "name": "x"},
                              {"kind": "t", "name": "x"}]}])))
    assert e.value.taken_by == "children[0]"
    assert e.value.raw_ast_path == "constructs[0].children[1]"


# --- amend ------------------------------------------------------------------

def test_amend_inherits_position_slot_identity_children():
    f, thy, sec, a, b, c = rbuild()
    run(c.evaluate_to(None, False))
    old_slot, old_identity, old_sbe = sec.state.name, sec.identity, \
        sec._state_before_ending.name
    EVENTS.clear()
    (s9,) = run(locked(f, edit.amend(
        sec, [{"kind": "block", "name": "S9"}])))
    assert thy.sub_nodes[0] is s9 and s9.parent is thy
    assert s9.state.name == old_slot and s9.identity == old_identity
    assert s9.sub_nodes == [a, b] and a.parent is s9 and b.parent is s9
    assert sec.parent is None and sec.sub_nodes == []
    assert old_sbe in tm.TABLE.deleted            # the orphaned slot released
    # what old's own operations wrote is released too: its result (the
    # successor's input) and its beginning's output (a's input)
    assert c.state.name not in tm.TABLE.values
    assert a.state.name not in tm.TABLE.values
    gates_and_completed = [e for e in EVENTS if e[1] != "invalidated"]
    assert gates_and_completed == [
        ("Section", "deleting", "amend"),
        ("Theory", "removing_child", "Section", "amend"),
        ("Section", "removing_child", "a", "inheritance"),
        ("a", "inheriting", "S9"),
        ("Section", "removing_child", "b", "inheritance"),
        ("b", "inheriting", "S9"),
        ("Section", "deleted", "amend"),
        ("a", "inherited", "Section"),
        ("S9", "added_child", "a", "inheritance"),
        ("b", "inherited", "Section"),
        ("S9", "added_child", "b", "inheritance"),
        ("Theory", "added_child", "S9", "amend"),
        ("S9", "inserted"),
    ]
    # invalidated from the first child: exactly the ready a, b and c left ready
    assert set(events("invalidated")) == {("a", "invalidated", None),
                                          ("b", "invalidated", None),
                                          ("c", "invalidated", None)}
    assert st(a) is NOT_EVALUATED and st(b) is NOT_EVALUATED
    assert len(deletes()) == 1                    # one round trip releases all
    inv(f)

def test_amending_a_childless_block_counts_each_deleted_slot_once():
    """A block with no children ends on the state its beginning wrote, so
    the amend releases that slot twice; the edit's one `state_delete`
    names it once.  An edit's invalidation is no walk: it writes no
    `walk_started` (LOGGING.md §4)."""
    f, thy, sec, a, b, c = rbuild()
    (e,) = run(locked(f, edit.insert(thy, 1, [{"kind": "block", "name": "E"}])))
    run(c.evaluate_to(None, False))
    assert st(e) == (READY, READY)
    tm.TABLE.calls.clear()
    walks = stand_ins.events("evaluation").count("walk_started")
    run(locked(f, edit.amend(e, [{"kind": "block", "name": "E2"}])))
    [(_, names)] = deletes()
    assert len(names) == len(set(names)) == 3
    assert stand_ins.events("evaluation").count("walk_started") == walks
    inv(f)

def test_amend_may_keep_the_name():
    f, thy, sec, a, b, c = rbuild()
    (s,) = run(locked(f, edit.amend(
        sec, [{"kind": "block", "name": "Section"}])))
    assert thy.sub_nodes[0] is s

def test_amend_batch_follows_the_replacement():
    f, thy, sec, a, b, c = rbuild()
    s9, u = run(locked(f, edit.amend(
        sec, [{"kind": "block", "name": "S9"}, {"kind": "t", "name": "u"}])))
    assert thy.sub_nodes == [s9, u, c] and u.parent is thy
    assert u.state.name not in tm.TABLE.values    # its predecessor is fresh
    inv(f)

def test_gen_is_told_the_batch_before_it_and_the_batch_s_role():
    """`NodeConfig.batch_before` and `role` (MODULE_STRUCTURE §4.1): an
    insertion's batch under `Insertion`, an amend's under `Amendment(old)`
    with only its first construct replacing `old`, and a construct's
    `children` a batch of their own, inserted."""
    kinds = KINDS | {"ct": CT}
    f, thy, sec, a, b, c = rbuild(kinds)
    run(locked(f, edit.insert(thy, 1, [{"kind": "ct", "name": "p"},
                                       {"kind": "ct", "name": "q"}])))
    assert told() == [("p", [], M.Insertion(), None), ("q", ["p"], M.Insertion(), None)]
    EVENTS.clear()
    run(locked(f, edit.amend(c, [{"kind": "ct", "name": "c9"},
                                 {"kind": "block", "name": "B",
                                  "children": [{"kind": "ct", "name": "u"},
                                               {"kind": "ct", "name": "v"}]},
                                 {"kind": "ct", "name": "r"}])))
    assert told() == [("c9", [], M.Amendment(c), c),
                      ("u", [], M.Insertion(), None), ("v", ["u"], M.Insertion(), None),
                      ("r", ["c9", "B"], M.Amendment(c), None)]
    assert_invariants(f, tm.TABLE)


def test_amend_across_kinds_leaves_no_field_of_the_old_class():
    f, thy, sec, a, b, c = rbuild()
    (blk,) = run(locked(f, edit.insert(thy,2, [{"kind": "block", "name": "B"}])))
    assert set(f.store.fields(blk.identity)) == {
        "kind", "children", "last_evaluation_statuses", "name", "fail_beginning", "fail_ending"}
    (leaf,) = run(locked(f, edit.amend(blk, [{"kind": "t", "name": "L"}])))
    assert leaf.identity == blk.identity
    assert set(f.store.fields(leaf.identity)) == {
        "kind", "last_evaluation_statuses", "name", "fail"}
    inv(f)

def test_amend_replacement_refuses_children_and_leaves():
    f, thy, sec, a, b, c = rbuild()
    with pytest.raises(UnexpectedChildren) as e:
        run(locked(f, edit.amend(
            sec, [{"kind": "block", "name": "S9",
                   "children": [{"kind": "t", "name": "x"}]}])))
    assert not e.value.is_leaf
    with pytest.raises(ChildrenNotInheritable) as e:
        run(locked(f, edit.amend(
            sec, [{"kind": "t", "name": "L"}])))
    assert (e.value.old_id, e.value.new_kind, e.value.children_count) == \
        ("block_Theory.block_Section", "t", 2)


# --- delete -----------------------------------------------------------------

def test_delete_fires_children_first_and_a_gate_can_veto():
    f, thy, sec, a, b, c = rbuild()
    subtree = [f.full_id(n) for n in sec._tree_order()]     # named before they detach
    run(locked(f, edit.delete(sec)))
    assert stand_ins.records("edit")[-1]["data"]["removed"] == subtree
    # the store's `transaction` record (LOGGING.md §4): the subtree's
    # identities, in tree order
    assert stand_ins.records("store")[-1]["data"]["nodes_deleted"] == [
        sec.identity, a.identity, b.identity]
    assert [e for e in EVENTS if e[1] in ("deleting", "deleted",
                                          "removing_child")] == [
        ("a", "deleting", "delete"),
        ("b", "deleting", "delete"),
        ("Section", "deleting", "delete"),
        ("Theory", "removing_child", "Section", "insert_or_delete"),
        ("a", "deleted", "delete"),
        ("b", "deleted", "delete"),
        ("Section", "deleted", "delete"),
    ]
    assert thy.sub_nodes == [c] and sec.parent is None
    assert len(deletes()) == 1                    # the subtree's states, one round trip
    inv(f)

class Veto(BadEdit):
    def _cause(self): return "vetoed."

class Stubborn(RT):
    def on_deleting(self, reason):
        raise Veto()

def test_gate_veto_aborts_with_forest_untouched():
    f, thy, sec, a, b, c = rbuild()
    s = add(sec, Stubborn(sec, slot(), "s"))
    with pytest.raises(Veto):
        run(locked(f, edit.delete(s)))
    assert s in sec.sub_nodes and s.parent is sec
    assert events("deleted") == []
    inv(f)

class Buggy(RT):
    def on_inserted(self):
        raise InvalidName("oops")                # a TAT_Error from a completed hook

def test_completed_hook_raise_is_the_class_bug():
    f, thy, sec, a, b, c = rbuild({**KINDS, "t": Buggy})
    with pytest.raises(TAT_InternalError):
        run(locked(f, edit.insert(thy,
            2, [{"kind": "t", "name": "u"}])))
    # the commit had happened in memory; the bug ends the conversation
    # before the edit's one store transaction (MODULE_STRUCTURE §4.2)
    assert [n.name for n in thy.sub_nodes] == ["Section", "c", "u"]
    assert set(f.store.nodes()) - {f.identity} == {n.identity for n in (thy, sec, a, b, c)}


# --- a name in a forest-wide namespace ---------------------------------------

class Named(RT):
    namespace = M.Namespace("theory short names", DuplicateTheoryShortName)

class AlsoNamed(RT):                    # another class in the same namespace
    namespace = M.Namespace("theory short names", DuplicateTheoryShortName)

class Labelled(RT):                     # a class in a namespace of its own
    namespace = M.Namespace("labels", DuplicateTheoryShortName)

def test_a_namespaced_name_collides_across_the_forest_and_the_batch():
    kinds = KINDS | {"named": Named, "also_named": AlsoNamed, "labelled": Labelled}
    f, thy, sec, a, b, c = rbuild(kinds)
    (n1,) = run(locked(f, edit.insert(sec,0, [{"kind": "named", "name": "N"}])))
    # the same name under another parent: no sibling collision, the namespace refuses
    with pytest.raises(DuplicateTheoryShortName) as e:
        run(locked(f, edit.insert(thy,0, [{"kind": "named", "name": "N"}])))
    assert (e.value.short_name, e.value.holder) == ("N", "block_Theory.block_Section.named_N")
    assert e.value.raw_ast_path == "constructs[0]"
    # it is the namespace that collides, not the class
    with pytest.raises(DuplicateTheoryShortName):
        run(locked(f, edit.insert(thy,0, [{"kind": "also_named", "name": "N"}])))
    run(locked(f, edit.insert(thy,0, [{"kind": "labelled", "name": "N"}])))
    # within one call, across different parents: the holder is a full path,
    # whichever way round (RENDER_BASELINES §2)
    with pytest.raises(DuplicateTheoryShortName) as e:
        run(locked(f, edit.insert(thy,0, [
            {"kind": "named", "name": "M"},
            {"kind": "block", "name": "S2", "children": [{"kind": "named", "name": "M"}]}])))
    assert e.value.holder == "constructs[0]"
    assert e.value.raw_ast_path == "constructs[1].children[0]"
    with pytest.raises(DuplicateTheoryShortName) as e:
        run(locked(f, edit.insert(thy,0, [
            {"kind": "block", "name": "S2", "children": [{"kind": "named", "name": "M"}]},
            {"kind": "named", "name": "M"}])))
    assert e.value.holder == "constructs[0].children[0]"
    assert e.value.raw_ast_path == "constructs[1]"
    # under one parent the sibling check comes first: DuplicateName, not the namespace's
    with pytest.raises(DuplicateName) as e:
        run(locked(f, edit.insert(thy,0, [
            {"kind": "named", "name": "M"}, {"kind": "named", "name": "M"}])))
    assert e.value.taken_by == "constructs[0]"
    # a class without a namespace takes no forest-wide name, whatever its name
    run(locked(f, edit.insert(thy,0, [{"kind": "t", "name": "N2"}])))
    # amend: the replaced node's name is not held against the call — not
    # against its replacement, nor against a later construct of the same call
    n2, n3 = run(locked(f, edit.amend(n1, [
        {"kind": "named", "name": "N"},
        {"kind": "block", "name": "S3", "children": [{"kind": "t", "name": "z"}]}])))
    assert n2.identity == n1.identity
    assert n3.sub_nodes[0].identity != n1.identity      # only the replacement takes the identity
    # the name the replaced node gives up is free to a later construct of the same call
    run(locked(f, edit.amend(n2, [
        {"kind": "named", "name": "N_new"},
        {"kind": "block", "name": "S4", "children": [{"kind": "named", "name": "N"}]}])))
    assert_invariants(f, tm.TABLE)
    assert_store_mirrors(f)


# --- one transaction per write operation, storing only what changed ----------

def test_each_edit_is_one_transaction_touching_what_it_changed():
    """One store transaction per edit, writing the new nodes, the nodes a
    completed hook fired on and the parents whose `children` row changed
    (MODULE_STRUCTURE §4.2 step 3); its `transaction` record naming the
    nodes it deleted by identity, and after it the edit's `committed`
    record (LOGGING.md §4), naming what the edit changed by full ids."""
    def committed():
        return stand_ins.records("edit")[-1]["data"]
    def nodes_deleted():
        return stand_ins.records("store")[-1]["data"]["nodes_deleted"]
    f, thy, sec, a, b, c = rbuild()
    tm.TABLE.clear_writes()
    (u,) = run(locked(f, edit.insert(sec,1, [{"kind": "t", "name": "u"}])))
    assert tm.TABLE.transactions == 1 and tm.TABLE.touched == {u.identity, sec.identity}
    assert nodes_deleted() == []
    assert committed() == {"operation": "insert", "parent": f.full_id(sec), "index": 1,
                           "created": [[f.full_id(u), "t"]], "removed": [], "moved": [],
                           "invalidated": []}
    tm.TABLE.clear_writes()
    run(locked(f, edit.move(c, thy, 0)))                 # within one parent
    assert tm.TABLE.transactions == 1 and tm.TABLE.touched == {thy.identity, c.identity}
    assert nodes_deleted() == []
    assert committed() == {"operation": "move", "parent": f.full_id(thy), "index": 0,
                           "created": [], "removed": [], "moved": [f.full_id(c)], "invalidated": []}
    tm.TABLE.clear_writes()
    run(locked(f, edit.move(c, sec, 0)))                 # across parents
    assert tm.TABLE.transactions == 1
    assert tm.TABLE.touched == {thy.identity, sec.identity, c.identity}
    assert nodes_deleted() == []
    assert (committed()["parent"], committed()["index"], committed()["moved"]) == (
        f.full_id(sec), 0, [f.full_id(c)])
    tm.TABLE.clear_writes()
    old_sec, sec_index = f.full_id(sec), sec.index_of()
    (s9,) = run(locked(f, edit.amend(sec, [{"kind": "block", "name": "S9"}])))
    assert tm.TABLE.transactions == 1                    # the replacement, its parent, the inherited children
    assert tm.TABLE.touched == {s9.identity, thy.identity} | {n.identity for n in s9.sub_nodes}
    assert [n.name for n in s9.sub_nodes] == ["c", "a", "u", "b"]
    assert nodes_deleted() == []                         # one identity, its rows rewritten
    assert committed() == {"operation": "amend", "parent": f.full_id(thy), "index": sec_index,
                           "created": [[f.full_id(s9), "block"]], "removed": [old_sec],
                           "moved": [], "invalidated": []}
    tm.TABLE.clear_writes()
    old_a, a_index = f.full_id(a), a.index_of()
    run(locked(f, edit.delete(a)))
    assert tm.TABLE.transactions == 1 and tm.TABLE.touched == {a.identity, s9.identity}
    assert nodes_deleted() == [a.identity]
    assert committed() == {"operation": "delete", "parent": f.full_id(s9), "index": a_index,
                           "created": [], "removed": [old_a], "moved": [], "invalidated": []}
    inv(f)


# --- move -------------------------------------------------------------------

def test_move_between_parents():
    f, thy, sec, a, b, c = rbuild()
    run(c.evaluate_to(None, False))
    EVENTS.clear()
    written = len(stand_ins.events("evaluation"))
    run(locked(f, edit.move(b, thy, 0)))   # to the front of the theory
    assert sec.sub_nodes == [a] and thy.sub_nodes == [b, sec, c]
    assert b.parent is thy
    # the move's invalidation is no walk (LOGGING.md §4): it writes the
    # statuses it changed and no walk record
    assert set(stand_ins.events("evaluation")[written:]) == {"operation"}
    # The destination-side copy survives: b's new input is written by the
    # theory's beginning, which stays ready.
    assert tm.TABLE.values[b.state.name] == "begin Theory"
    # Everything after b is downstream of the move and left ready, its
    # values released — "slot holds a value iff its writer is ready".
    assert st(b) is NOT_EVALUATED and st(a) is NOT_EVALUATED
    assert st(sec) == (NOT_EVALUATED, NOT_EVALUATED) and st(c) is NOT_EVALUATED
    assert sec._state_before_ending.name not in tm.TABLE.values
    assert [e for e in EVENTS if e[1] in ("moving", "removing_child",
                                          "added_child", "moved")] == [
        ("b", "moving", "Theory", 0),
        ("Section", "removing_child", "b", "move"),
        ("Theory", "added_child", "b", "move"),
        ("b", "moved", "Section", 1),
    ]

def test_move_within_one_parent():
    f, thy, sec, a, b, c = rbuild()
    run(c.evaluate_to(None, False))
    run(locked(f, edit.move(a, sec, 1)))
    assert sec.sub_nodes == [b, a]
    # b's input survives, written by the section's still-ready beginning;
    # a's input was copied from b's result and released with b.
    assert tm.TABLE.values[b.state.name] == "begin Section"
    assert a.state.name not in tm.TABLE.values
    assert st(a) is NOT_EVALUATED and st(b) is NOT_EVALUATED
    # the gate sees the post-removal index, the completed hook the old one
    assert ("a", "moving", "Section", 1) in EVENTS
    assert ("a", "moved", "Section", 0) in EVENTS
    inv(f)

def test_move_carries_the_subtree_reset():
    f, thy, sec, a, b, c = rbuild()
    run(c.evaluate_to(None, False))
    run(locked(f, edit.move(sec, thy, 1)))
    assert thy.sub_nodes == [c, sec]
    assert st(sec) == (NOT_EVALUATED, NOT_EVALUATED)
    assert st(a) is NOT_EVALUATED and st(b) is NOT_EVALUATED

def test_on_invalidated_distinguishes_the_operation():
    f, thy, sec, a, b, c = rbuild()
    run(c.evaluate_to(None, False))
    EVENTS.clear()
    tm.invalidate(a)                             # invalidate from a on
    inv = events("invalidated")
    assert ("a", "invalidated", None) in inv
    assert ("Section", "invalidated", "ending") in inv
    # its beginning stands: the invalidation starts at a, inside the block
    assert ("Section", "invalidated", "beginning") not in inv

def test_on_invalidated_fires_once_per_operation():
    f, thy, sec, a, b, c = rbuild()
    run(c.evaluate_to(None, False))
    EVENTS.clear()
    run(locked(f, edit.insert(thy,         # everything after u leaves ready
        0, [{"kind": "t", "name": "u"}])))
    inv = events("invalidated")
    assert inv.count(("Section", "invalidated", "beginning")) == 1
    assert inv.count(("Section", "invalidated", "ending")) == 1
    assert ("a", "invalidated", None) in inv and ("b", "invalidated", None) in inv


def test_blocked_beginning_reruns_when_unblocked():
    f = tm.OneTreeForest(tm.CONN)
    thy = add(f, Block(f, slot(), "Theory"))
    d = add(thy, T(thy, slot(), "d", fail=True))
    sec = add(thy, Block(thy, slot(), "Sec"))
    a = add(sec, T(sec, slot(), "a"))
    r = run(a.evaluate_to(None, False))                # strict: d stops, sec blocked
    assert r.stopped_at is d
    assert st(sec)[0] is NOT_EVALUATED and sec.begin_runs == 0
    r = run(a.evaluate_to(None, True))                 # resumes past the obstacle
    assert sec.begin_runs == 1 and st(sec)[0] is READY and st(a) is READY
    assert tm.TABLE.values[a.state.name] == "begin Sec"

def test_failed_opening_repeated_pass_keeps_the_result():
    f, thy, sec, t1, t2, t3, t4 = tm.build(Section="begin")
    for _ in range(3):
        run(t4.evaluate_to(None, False))
    assert st(sec) == (CANNOT_EVALUATE, READY)
    assert tm.TABLE.values[sec.resulting_state().name] == "begin Theory"
    assert sec.begin_runs == 1                   # an obstacle is not rerun


# --- the invariants, and the shapes that escaped every earlier sweep --------

def build_x_sec_c():
    """Theory > [x, Section > [a, b], c]: a nesting node right after x."""
    f = tm.OneTreeForest(tm.CONN)
    thy = add(f, Block(f, slot(), "Theory"))
    x = add(thy, T(thy, slot(), "x"))
    sec = add(thy, Block(thy, slot(), "Section"))
    a = add(sec, T(sec, slot(), "a")); b = add(sec, T(sec, slot(), "b"))
    c = add(thy, T(thy, slot(), "c"))
    return f, thy, x, sec, a, b, c

def test_delete_before_a_nesting_successor_invalidates_it_whole():
    f, thy, x, sec, a, b, c = build_x_sec_c()
    run(c.evaluate_to(None, False)); inv(f)
    run(locked(f, edit.delete(x)))
    assert st(sec) == (NOT_EVALUATED, NOT_EVALUATED)
    assert st(a) is NOT_EVALUATED and st(b) is NOT_EVALUATED and st(c) is NOT_EVALUATED
    inv(f)
    run(c.evaluate_to(None, False))
    assert sec.begin_runs == 2 and a.runs == 2    # rerun against the new input
    inv(f)

def test_move_past_a_nesting_successor_invalidates_it_whole():
    f, thy, x, sec, a, b, c = build_x_sec_c()
    run(c.evaluate_to(None, False))
    run(locked(f, edit.move(x, thy, 2)))    # -> [Section, c, x]
    assert thy.sub_nodes == [sec, c, x]
    assert st(sec) == (NOT_EVALUATED, NOT_EVALUATED) and st(a) is NOT_EVALUATED
    assert len(deletes()) == 1                    # one round trip after the commit
    inv(f)

def test_amend_with_a_nesting_first_child_invalidates_it_whole():
    f = tm.OneTreeForest(tm.CONN)
    thy = add(f, Block(f, slot(), "Theory"))
    sec = add(thy, Block(thy, slot(), "Section"))
    inner = add(sec, Block(sec, slot(), "Inner"))
    a = add(inner, T(inner, slot(), "a"))
    b = add(sec, T(sec, slot(), "b"))
    run(b.evaluate_to(None, False)); inv(f)
    (s9,) = run(locked(f, edit.amend(
        sec, [{"kind": "block", "name": "S9"}])))
    assert s9.sub_nodes == [inner, b]
    assert st(inner) == (NOT_EVALUATED, NOT_EVALUATED) and st(a) is NOT_EVALUATED
    inv(f)

def test_a_beginning_failing_after_its_block_was_invalidated_copies_the_input_through():
    """Theory > [A(fails), B > [z], Y]: a strict walk ends at A and
    invalidates B whole; B's beginning then fails on its second run, and
    the block's input stands as its result."""
    f = tm.OneTreeForest(tm.CONN)
    thy = add(f, Block(f, slot(), "Theory"))
    a = add(thy, T(thy, slot(), "A", fail=True))
    b = add(thy, Block(thy, slot(), "B", fail_ending=True))
    z = add(b, T(b, slot(), "z"))
    y = add(thy, T(thy, slot(), "Y"))
    run(y.evaluate_to(None, True)); inv(f)
    assert st(b) == (READY, CANNOT_EVALUATE)
    run(y.evaluate_to(None, False)); inv(f)            # A stops: everything after it is invalidated
    assert st(b) == (NOT_EVALUATED, NOT_EVALUATED)
    record(b, fail_beginning=True)
    run(y.evaluate_to(None, True)); inv(f)             # B's beginning reruns and fails
    assert st(b) == (CANNOT_EVALUATE, READY) and st(y) is READY
    assert (tm.TABLE.values[b.resulting_state().name]
            == tm.TABLE.values[b.state.name])

def test_an_obstacle_after_a_strict_stop_runs_again_when_a_walk_reaches_it():
    """Theory > [A(fails), P, X(fails), Y]: a strict walk ends at A and
    invalidates everything after it, the obstacle X included; the next walk
    that goes past A runs P and X again."""
    f = tm.OneTreeForest(tm.CONN)
    thy = add(f, Block(f, slot(), "Theory"))
    a = add(thy, T(thy, slot(), "A", fail=True)); p = add(thy, T(thy, slot(), "P"))
    x = add(thy, T(thy, slot(), "X", fail=True)); y = add(thy, T(thy, slot(), "Y"))
    run(y.evaluate_to(None, True)); inv(f)
    assert (p.runs, x.runs) == (1, 1)
    run(y.evaluate_to(None, False)); inv(f)            # A stops: P, X and Y are invalidated
    assert st(p) is NOT_EVALUATED and st(x) is NOT_EVALUATED
    run(y.evaluate_to(None, True)); inv(f)             # P runs again, and X after it
    assert (p.runs, x.runs) == (2, 2) and st(x) is CANNOT_EVALUATE
    run(y.evaluate_to(None, True)); inv(f)             # nothing rewritten: nothing reruns
    assert (p.runs, x.runs) == (2, 2)

def test_the_root_has_no_parent():
    f, thy, sec, a, b, c = rbuild()
    with pytest.raises(TAT_InternalError):
        run(locked(f, edit.delete(f)))

def test_on_invalidated_fires_before_the_other_completed_hooks():
    """MODULE_STRUCTURE §4.1, "Events": `on_invalidated` fires in the
    commit's invalidation, so before every other completed hook of the
    edit."""
    changes = {
        "insert": lambda f, thy, sec, a: edit.insert(sec, 0, [{"kind": "t", "name": "u"}]),
        "amend": lambda f, thy, sec, a: edit.amend(sec, [{"kind": "block", "name": "S9"}]),
        "delete": lambda f, thy, sec, a: edit.delete(a),
        "move": lambda f, thy, sec, a: edit.move(a, thy, 1),
    }
    for name, change in changes.items():
        f, thy, sec, a, b, c = rbuild()
        run(c.evaluate_to(None, False))
        EVENTS.clear()
        run(locked(f, change(f, thy, sec, a)))
        kinds = [e[1] for e in EVENTS]
        last_invalidated = max(i for i, kind in enumerate(kinds) if kind == "invalidated")
        first_completed = min(i for i, kind in enumerate(kinds)
                              if kind in ("deleted", "inserted", "inherited", "added_child", "moved"))
        assert last_invalidated < first_completed, (name, EVENTS)


def test_a_repeated_invalidation_stores_and_logs_nothing():
    """The setter's guard (MODULE_STRUCTURE §4.1, "Status"): `not_evaluated`
    for an operation whose stored status is already `not_evaluated` writes
    nothing — no transaction, no `operation` record, nothing released."""
    f, thy, sec, a, b, c = rbuild()
    run(c.evaluate_to(None, False))
    tm.invalidate(a)
    assert st(a) is NOT_EVALUATED and st(c) is NOT_EVALUATED
    tm.TABLE.clear_writes(); tm.TABLE.calls.clear(); EVENTS.clear()
    operations = stand_ins.events("evaluation").count("operation")
    tm.invalidate(a)
    assert tm.TABLE.transactions == 0 and not tm.TABLE.touched
    assert stand_ins.events("evaluation").count("operation") == operations
    assert deletes() == [] and events("invalidated") == []
    inv(f)


class Noting:
    """Completed hooks that record on the node, in a stored field `note`."""
    note = ""
    def to_store(self, rows):
        super().to_store(rows)
        rows.put("note", self.note)
    @classmethod
    def from_store(cls, config, rows):
        node = super().from_store(config, rows)
        node.note = rows.get("note")
        return node
    def on_inherited(self, old_parent): self.note = f"inherited from {old_parent.name}"
    def on_moved(self, old_location): self.note = f"moved from {old_location.parent.name}"
    def on_deleted(self, reason): self.note = f"deleted by {reason}"

class NT(Noting, T):
    pass

class NBlock(Noting, Block):
    def on_added_child(self, child, mode): self.note = f"added {child.name} by {mode}"


def test_what_a_completed_hook_records_is_stored_with_the_edit():
    """MODULE_STRUCTURE §4.1, "Events": a completed hook fires before the
    edit's store, so what it changes on a node still in the forest is in
    the database when the edit returns."""
    kinds = {"t": NT, "block": NBlock}
    f = tm.OneTreeForest(tm.CONN, kinds=kinds)
    (thy,) = run(locked(f, edit.insert(f, 0, [
        {"kind": "block", "name": "Theory", "children": [
            {"kind": "block", "name": "Section", "children": [
                {"kind": "t", "name": "a"}, {"kind": "t", "name": "b"}]},
            {"kind": "t", "name": "c"}]}])))
    sec, c = thy.sub_nodes
    a, b = sec.sub_nodes
    def stored(node):
        return f.store.get(node.identity, "note")
    def mirrors():
        assert_store_mirrors(f, shape=lambda forest: [
            (n.identity, n.kind, n.name, n.note) for n in forest._all_nodes()])
    assert stored(sec) == "added b by insert_or_delete"        # a new node's own hooks, too
    # an amend: the inherited children and the parent; the replacement's
    # rows are its own — what `on_deleted` wrote on the node it replaced
    # is stored nowhere
    (s9,) = run(locked(f, edit.amend(sec, [{"kind": "block", "name": "S9"}])))
    assert stored(a) == stored(b) == "inherited from Section"
    assert stored(thy) == "added S9 by amend"
    assert sec.note == "deleted by amend" and stored(s9) == "added b by inheritance"
    mirrors()
    # a move: the moved node and its new parent
    run(locked(f, edit.move(c, s9, 0)))
    assert stored(c) == "moved from Theory" and stored(s9) == "added c by move"
    mirrors()
    # a delete: the hooks fire on nodes that have left; none is refused, no row remains
    gone = {n.identity for n in s9._tree_order()}
    run(locked(f, edit.delete(s9)))
    assert s9.note == a.note == "deleted by delete" and not gone & set(f.store.nodes())
    mirrors()


def test_a_node_outside_the_forest_is_not_stored():
    """MODULE_STRUCTURE §4.2 step 3: a status written on a node whose parent
    chain does not reach the forest is refused before any transaction
    opens; `_store_node` on such a node inside one is the cause of that
    transaction's `TAT_DisasterError`."""
    f, thy, sec, a, b, c = rbuild()
    run(locked(f, edit.delete(b)))
    ev = M.Evaluation(None, False)
    ev.stored.add(b)
    tm.TABLE.clear_writes()
    with pytest.raises(TAT_InternalError, match="not in the forest"):
        f._store_written(ev)
    assert tm.TABLE.transactions == 0
    with pytest.raises(TAT_DisasterError) as e:
        with f.store.transaction():
            f._store_node(b)
    assert isinstance(e.value.__cause__, TAT_InternalError)
    inv(f)


def test_random_interleavings_keep_the_invariants():
    for seed in range(300):
        rng = random.Random(seed)
        f, thy, sec, t1, t2, t3, t4 = tm.build(T1=rng.random() < 0.3)
        counter = 0

        def fresh(kind):
            nonlocal counter
            counter += 1
            raw = {"kind": kind, "name": f"n{counter}"}
            if rng.random() < 0.3:
                raw["fail"] = True
            return raw

        async def step():
            nodes = f._all_nodes()
            blocks = [n for n in nodes if isinstance(n, M.NonLeaf_Node)]
            movable = [n for n in nodes if n is not thy]
            op = rng.choice(["insert", "delete", "amend", "move",
                             "evaluate", "invalidate", "flip"])
            if op == "flip" and movable:     # a verdict changes between runs; not the
                n = rng.choice(movable)      # tree root's, whose input nobody writes (the plan's §6)
                if isinstance(n, Block):
                    which = rng.choice(["fail_beginning", "fail_ending"])
                else:
                    which = "fail"
                record(n, **{which: not getattr(n, which)})
            elif op == "insert":
                p = rng.choice(blocks)
                raws = [fresh(rng.choice(["t", "block"]))
                        for _ in range(rng.randint(1, 2))]
                async with f.lock:
                    await edit.insert(p,rng.randint(0, len(p.sub_nodes)), raws)
            elif op == "delete" and movable:
                n = rng.choice(movable)
                async with f.lock:
                    await edit.delete(n)
            elif op == "amend" and movable:
                n = rng.choice(movable)
                if isinstance(n, M.NonLeaf_Node) and n.sub_nodes:
                    kind = "block"               # a leaf could not inherit them
                else:
                    kind = rng.choice(["t", "block"])
                raws = [fresh(kind)] + [fresh(rng.choice(["t", "block"]))
                                        for _ in range(rng.randint(0, 1))]
                async with f.lock:
                    await edit.amend(n, raws)
            elif op == "move" and movable:
                n = rng.choice(movable)
                dests = [b for b in blocks if b not in n._tree_order()]
                if dests:
                    p = rng.choice(dests)
                    i = rng.randint(0, len(p.sub_nodes) - (1 if p is n.parent else 0))
                    async with f.lock:
                        await edit.move(n, p, i)
            elif op == "evaluate":
                await rng.choice(nodes).evaluate_to(None, rng.random() < 0.5)
            elif op == "invalidate":
                await tm._invalidate(rng.choice(nodes))

        for _ in range(60):                  # the budget at which the invariants catch
            run(step())                      # each of the three release-side mechanisms
            inv(f)


def test_move_refusals():
    f, thy, sec, a, b, c = rbuild()
    with pytest.raises(MoveIntoOwnSubtree) as e:
        run(locked(f, edit.move(sec, sec, 0)))
    assert (e.value.id, e.value.destination) == \
        ("block_Theory.block_Section", "block_Theory.block_Section")
    mk = add(sec, RT(sec, slot(), "c"))                      # a second "c"
    with pytest.raises(DuplicateName) as e:
        run(locked(f, edit.move(mk, thy, 2)))
    assert e.value.taken_by == "block_Theory.t_c"
