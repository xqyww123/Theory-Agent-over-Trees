"""The loader (PLUGIN_SYSTEM.md): registration and its checks, the kind
table, assembly of the `edit` schema's `$defs`, sealing.
Run: python -m pytest test/test_plugin.py
"""

import sys
import types
from typing import Any, Literal, NotRequired, TypedDict

try:
    import Isabelle_RPC_Host  # noqa: F401
except ImportError:                       # the test needs no Isabelle
    m = types.ModuleType("Isabelle_RPC_Host")
    m.Connection = object  # type: ignore[attr-defined]
    sys.modules["Isabelle_RPC_Host"] = m

import jsonschema
import pytest

from isabelle_theory_agent import model as M, plugin
from isabelle_theory_agent.exceptions import TAT_InternalError, TAT_StartupError
from isabelle_theory_agent.plugin import CannotLoadPlugin

# The classes TAT ships, captured before the fixture below empties the list
# for each test: `test_a_construct_of_every_shipped_kind_validates` holds
# them to the plan's §7 step 2 requirement.
SHIPPED = list(M.FRAMEWORK_NODE_CLASSES)


@pytest.fixture(autouse=True)
def fresh_table(monkeypatch):
    monkeypatch.setattr(plugin, "kinds", {})
    monkeypatch.setattr(plugin, "classes", [])
    monkeypatch.setattr(plugin, "_sealed", False)
    monkeypatch.setattr(M, "FRAMEWORK_NODE_CLASSES", [])


# --- classes to register ----------------------------------------------------

STATEMENT = {"Statement": {"type": "object",
                           "properties": {"text": {"type": "string"}},
                           "required": ["text"], "additionalProperties": False}}


def leaf_schema(kinds, fields=None, required=(), defs=None):
    props = {"kind": {"type": "string", "enum": list(kinds)}}
    props.update(fields or {})
    schema = {"type": "object", "properties": props,
              "required": ["kind", *required], "additionalProperties": False}
    if defs is not None:
        schema["$defs"] = defs
    return schema


class Persisted:
    """The three methods every class must override (PLUGIN_SYSTEM §5);
    nothing here is ever built or stored."""
    @classmethod
    async def gen(cls, config, raw): raise NotImplementedError
    def to_store(self, rows): raise NotImplementedError
    @classmethod
    def from_store(cls, config, rows): raise NotImplementedError


class Thm_Statement(TypedDict):
    text: str

class Thm_RawAST(TypedDict):
    kind: Literal["lemma", "theorem"]
    statement: Thm_Statement
    tags: NotRequired[list[str]]


class Thm(Persisted, M.Leaf):
    construct_schema = leaf_schema(
        ["lemma", "theorem"],
        {"statement": {"$ref": "#/$defs/Statement"},
         "tags": {"type": "array", "items": {"type": "string"}}},
        required=["statement"], defs=STATEMENT)
    argument_schema = Thm_RawAST
    async def _eval_opr(self): return True


class Sec_RawAST(TypedDict):
    title: str


class Sec(Persisted, M.StdBlock):
    construct_schema = {
        "type": "object",
        "properties": {
            "kind": {"const": "section"},
            "title": {"type": "string"},
            "children": {"type": "array", "items": {"$ref": "#/$defs/Construct"}},
        },
        "required": ["kind", "title"], "additionalProperties": False}
    argument_schema = Sec_RawAST
    async def _eval_beginning_opr(self): return True


class Empty(TypedDict):
    pass


def leaf(name, kinds, **overrides):
    """A fresh Leaf class with a minimal, valid declaration."""
    body = {"construct_schema": leaf_schema(kinds), "argument_schema": Empty,
            "_eval_opr": Thm._eval_opr, "__module__": __name__}
    body.update(overrides)
    return type(name, (Persisted, M.Leaf), body)


def block(name, children, defs=None):
    """A fresh StdBlock class declaring `children` as given."""
    schema = dict(Sec.construct_schema)
    schema["properties"] = dict(schema["properties"]) | {
        "kind": {"const": name.lower()}, "children": children}
    if defs is not None:
        schema["$defs"] = defs
    return type(name, (Persisted, M.StdBlock), {
        "construct_schema": schema, "argument_schema": Sec_RawAST,
        "_eval_beginning_opr": Sec._eval_beginning_opr, "__module__": __name__})


def refused(cls, match):
    with pytest.raises(CannotLoadPlugin, match=match) as e:
        plugin.TAT_node(cls)
    assert isinstance(e.value, TAT_StartupError)
    assert (e.value.package, e.value.node_class) == (__name__, cls.__name__)
    return e.value


def refused_at_assembly(cls, match):
    with pytest.raises(CannotLoadPlugin, match=match) as e:
        plugin.assemble()
    assert (e.value.package, e.value.node_class) == (__name__, cls.__name__)


# --- registration ------------------------------------------------------------

def test_a_class_registers_every_kind_its_schema_names_in_order():
    assert plugin.TAT_node(Thm) is Thm
    plugin.TAT_node(Sec)
    assert plugin.kinds == {"lemma": Thm, "theorem": Thm, "section": Sec}
    assert list(plugin.kinds) == ["lemma", "theorem", "section"]
    assert plugin.classes == [Thm, Sec]


def test_the_schema_must_be_a_well_formed_object_schema():
    refused(leaf("A", ["a"], construct_schema=None), "must be a dict")
    refused(leaf("B", ["b"], construct_schema={"type": "object", "properties": 7}),
            "not a well-formed JSON schema")
    refused(leaf("C", ["c"], construct_schema=leaf_schema(["c"]) | {"type": "string"}),
            "object schema")
    open_ = leaf_schema(["d"]); del open_["additionalProperties"]
    refused(leaf("D", ["d"], construct_schema=open_), "additionalProperties")


def test_kind_is_read_from_the_schema_and_must_be_sound():
    no_kind = leaf_schema(["e"]); del no_kind["properties"]["kind"]
    refused(leaf("E", ["e"], construct_schema=no_kind), "no `properties.kind`")
    not_object = leaf_schema(["e2"]); not_object["properties"]["kind"] = True
    refused(leaf("E2", ["e2"], construct_schema=not_object), "`properties.kind` is not an object")
    loose = leaf_schema(["f"]); loose["properties"]["kind"] = {"type": "string"}
    refused(leaf("F", ["f"], construct_schema=loose), "neither `enum` nor `const`")
    numbers = leaf_schema(["g"]); numbers["properties"]["kind"] = {"enum": [1]}
    refused(leaf("G", ["g"], construct_schema=numbers), "one or more strings")
    none = leaf_schema(["g2"]); none["properties"]["kind"] = {"enum": []}
    refused(leaf("G2", ["g2"], construct_schema=none), "one or more strings")
    optional = leaf_schema(["h"]); optional["required"] = []
    refused(leaf("H", ["h"], construct_schema=optional), "`kind` must be in `required`")


def test_a_kind_and_a_class_name_are_taken_once():
    plugin.TAT_node(Thm)
    refused(leaf("Other", ["lemma"]), "kind `lemma` is already registered by Thm")
    refused(leaf("Thm", ["corollary"]), "another node class has this name")
    assert list(plugin.kinds) == ["lemma", "theorem"]     # nothing half-registered


def test_children_only_on_a_nesting_class_and_only_as_refs():
    with_children = leaf_schema(["i"])
    with_children["properties"]["children"] = {
        "type": "array", "items": {"$ref": "#/$defs/Construct"}}
    refused(leaf("I", ["i"], construct_schema=with_children), "a Leaf declares no `children`")
    refused(block("J", {"type": "array", "items": {"type": "string"}}), "`children` must be")
    refused(block("K", {"type": "object"}), "`children` must be")
    refused(block("K2", {"type": "array", "items": {"anyOf": [
        {"$ref": "#/$defs/Construct"}, {"type": "string"}]}}), "`children` must be")
    plugin.TAT_node(block("L", {"type": "array", "items": {
        "anyOf": [{"$ref": "#/$defs/Thm"}, {"$ref": "#/$defs/Construct"}]}}))


def test_children_must_point_at_construct_or_a_node_class():
    own = plugin.TAT_node(block(
        "Own", {"type": "array", "items": {"$ref": "#/$defs/Statement"}}, defs=STATEMENT))
    refused_at_assembly(own, "`children` must be an array of `\\$ref`s to `Construct` or to"
                             " node classes, not to `#/\\$defs/Statement`")


def test_children_target_is_checked_wherever_a_ref_appears():
    aside = plugin.TAT_node(block(
        "Aside", {"type": "array", "prefixItems": [{"$ref": "#/$defs/Statement"}],
                  "items": {"$ref": "#/$defs/Construct"}}, defs=STATEMENT))
    refused_at_assembly(aside, "not to `#/\\$defs/Statement`")


def test_output_omissible_but_input_compulsory_is_refused():
    refused(leaf("Bad", ["bad"], output_omissible=True), "omissible on output")
    plugin.TAT_node(leaf("Fine", ["fine"], output_omissible=True, input_omissible=True))
    plugin.TAT_node(leaf("AlsoFine", ["also_fine"], input_omissible=True))


def test_is_finished_is_the_frameworks():
    refused(leaf("Done", ["done"], is_finished=lambda self: True), "overrides `is_finished`")
    plugin.TAT_node(leaf("Owing", ["owing"], _owes_nothing=lambda self: False))


def test_gen_and_both_persistence_methods_must_be_overridden():
    methods = ("gen", "to_store", "from_store")
    for missing in methods:
        cls = type("No_" + missing, (M.Leaf,), {         # not Persisted: one method short
            "construct_schema": leaf_schema(["no_" + missing]), "argument_schema": Empty,
            "_eval_opr": Thm._eval_opr, "__module__": __name__,
            **{m: Persisted.__dict__[m] for m in methods if m != missing}})
        refused(cls, f"does not override `{missing}`")


def test_the_argument_schema_is_compulsory_and_within_the_grammar():
    refused(leaf("NoTD", ["notd"], argument_schema=None), "argument_schema: .*not a TypedDict")
    class Wide(TypedDict):
        x: dict
    wide = leaf_schema(["wide"], {"x": {"type": "object"}}, required=["x"])
    refused(leaf("Wide", ["wide"], construct_schema=wide, argument_schema=Wide),
            "outside the argument schema grammar")


def test_the_two_schemas_must_agree():
    class Named(TypedDict):
        name: str
    refused(leaf("M1", ["m1"], argument_schema=Named), r"declares the fields \[\].*\['name'\]")
    named = leaf_schema(["m2"], {"name": {"type": "string"}})     # not required in the schema
    refused(leaf("M2", ["m2"], construct_schema=named, argument_schema=Named),
            r"requires \[\], argument_schema requires \['name'\]")
    class Optional_(TypedDict):
        name: NotRequired[str]
    plugin.TAT_node(leaf("M3", ["m3"],
                         construct_schema=leaf_schema(["m3"], {"name": {"type": "string"}}),
                         argument_schema=Optional_))


# --- assembly ----------------------------------------------------------------

def test_assembly_hoists_defs_builds_the_union_and_changes_nothing_else():
    plugin.TAT_node(Thm)
    plugin.TAT_node(Sec)
    defs = plugin.assemble()
    assert list(defs) == ["Thm", "Sec", "Statement", "Construct"]
    assert defs["Thm"] == {k: v for k, v in Thm.construct_schema.items() if k != "$defs"}
    assert defs["Sec"] == Sec.construct_schema
    assert defs["Statement"] == STATEMENT["Statement"]
    assert defs["Construct"] == {"anyOf": [{"$ref": "#/$defs/Thm"}, {"$ref": "#/$defs/Sec"}]}
    # the class's declaration is untouched and shares nothing with the result
    assert "$defs" in Thm.construct_schema
    defs["Thm"]["properties"]["tags"]["items"]["type"] = "number"
    assert Thm.construct_schema["properties"]["tags"]["items"]["type"] == "string"


def test_shared_defs_must_be_equal():
    plugin.TAT_node(Thm)
    other = leaf_schema(["other"], {"s": {"$ref": "#/$defs/Statement"}}, required=["s"],
                        defs={"Statement": {"type": "string"}})
    class Other_RawAST(TypedDict):
        s: str
    other = plugin.TAT_node(leaf("Other", ["other"], construct_schema=other,
                                 argument_schema=Other_RawAST))
    refused_at_assembly(other, "defines `\\$defs` `Statement` differently from Thm")


class S_RawAST(TypedDict):
    s: str


def test_a_ref_must_name_an_own_def_construct_or_a_class():
    dangling = leaf_schema(["p"], {"s": {"$ref": "#/$defs/Nowhere"}}, required=["s"])
    p = plugin.TAT_node(leaf("P", ["p"], construct_schema=dangling, argument_schema=S_RawAST))
    refused_at_assembly(p, "names neither")


def test_a_ref_inside_an_own_def_is_checked_too():
    wrapped = leaf_schema(["p2"], {"s": {"$ref": "#/$defs/Wrap"}}, required=["s"],
                          defs={"Wrap": {"type": "array", "items": {"$ref": "#/$defs/Nowhere"}}})
    p2 = plugin.TAT_node(leaf("P2", ["p2"], construct_schema=wrapped, argument_schema=S_RawAST))
    refused_at_assembly(p2, "names neither")


def test_a_ref_must_have_the_defs_form():
    external = leaf_schema(["q"], {"s": {"$ref": "https://example.org/s"}}, required=["s"])
    q = plugin.TAT_node(leaf("Q", ["q"], construct_schema=external, argument_schema=S_RawAST))
    refused_at_assembly(q, "not of the form")


def test_own_defs_may_not_take_construct_or_a_class_name():
    r = plugin.TAT_node(leaf("R", ["r"], construct_schema=leaf_schema(
        ["r"], defs={"Construct": {"type": "string"}})))
    refused_at_assembly(r, "reserved name `Construct`")


def test_own_defs_may_not_take_another_class_name():
    plugin.TAT_node(Thm)
    s = plugin.TAT_node(leaf("S", ["s"], construct_schema=leaf_schema(
        ["s"], defs={"Thm": {"type": "string"}})))
    refused_at_assembly(s, "reserved name `Thm`")


def test_a_class_may_refer_to_another_class_and_to_itself():
    nested = leaf_schema(["u"], {"inner": {"$ref": "#/$defs/Thm"},
                                 "more": {"type": "array", "items": {"$ref": "#/$defs/Tree"}}},
                         required=["inner"],
                         defs={"Tree": {"type": "object",
                                        "properties": {"sub": {"type": "array",
                                                               "items": {"$ref": "#/$defs/Tree"}}},
                                        "additionalProperties": False}})
    class U_RawAST(TypedDict):
        inner: Thm_Statement
        more: NotRequired[list[Any]]     # the grammar has no recursion; `Any` stands for the tree
    plugin.TAT_node(Thm)
    plugin.TAT_node(leaf("U", ["u"], construct_schema=nested, argument_schema=U_RawAST))
    defs = plugin.assemble()
    assert "Tree" in defs and defs["U"]["properties"]["inner"] == {"$ref": "#/$defs/Thm"}


# --- the edit schema, loading and sealing -----------------------------------

def envelope(*constructs):
    return {"action": "append", "target_id": "theory_X", "evaluate": False,
            "constructs": list(constructs)}


def test_the_completed_edit_schema_validates_constructs():
    plugin.TAT_node(Thm)
    plugin.TAT_node(Sec)
    plugin.TAT_node(block("Thms", {"type": "array", "items": {"$ref": "#/$defs/Thm"}}))
    schema = plugin.edit_schema()
    assert schema["properties"]["constructs"]["items"] == {"$ref": "#/$defs/Construct"}
    validator = jsonschema.Draft202012Validator(schema)
    lemma = {"kind": "lemma", "statement": {"text": "P"}, "tags": ["easy"]}
    validator.validate(envelope(
        {"kind": "section", "title": "Basics", "children": [lemma]},
        {"kind": "theorem", "statement": {"text": "Q"}},
        {"kind": "thms", "title": "Only theorems", "children": [lemma]}))
    for bad in (
        {"kind": "lemma"},                                   # statement missing
        {"kind": "lemna", "statement": {"text": "P"}},       # unknown kind
        {"kind": "lemma", "statement": {"text": "P"}, "proof": "by simp"},   # extra field
        {"kind": "section", "title": "T", "children": [{"kind": "section"}]},  # nested, incomplete
        {"kind": "thms", "title": "T", "children": [{"kind": "section", "title": "S"}]},  # narrowed
    ):
        assert not validator.is_valid(envelope(bad)), bad
    # the envelope itself (TOOL_SCHEMAS §1)
    good = envelope(lemma)
    for bad_envelope in (
        {},
        good | {"action": "replace"},
        {k: v for k, v in good.items() if k != "evaluate"},
        good | {"constructs": []},
        good | {"dry_run": True},
    ):
        assert not validator.is_valid(bad_envelope), bad_envelope


# One construct of every kind TAT ships, validated against the assembled
# schema (the plan's §7 step 2): a class registering a kind without an
# example here fails this test.
SHIPPED_EXAMPLES: dict[str, dict] = {}


def test_a_construct_of_every_shipped_kind_validates():
    for cls in SHIPPED:
        plugin.TAT_node(cls)
    assert set(SHIPPED_EXAMPLES) == set(plugin.kinds)
    if SHIPPED:
        validator = jsonschema.Draft202012Validator(plugin.edit_schema())
        for kind, construct in SHIPPED_EXAMPLES.items():
            assert construct["kind"] == kind
            validator.validate(envelope(construct))


def test_load_registers_the_framework_first_then_imports_then_seals(tmp_path, monkeypatch):
    (tmp_path / "fake_tat_pkg.py").write_text(
        "from typing import TypedDict\n"
        "from isabelle_theory_agent import model, plugin\n"
        "class Empty(TypedDict): pass\n"
        "@plugin.TAT_node\n"
        "class Fake(model.Leaf):\n"
        "    construct_schema = {'type': 'object', 'additionalProperties': False,\n"
        "        'properties': {'kind': {'const': 'fake'}}, 'required': ['kind']}\n"
        "    argument_schema = Empty\n"
        "    @classmethod\n"
        "    async def gen(cls, config, raw): raise NotImplementedError\n"
        "    def to_store(self, rows): raise NotImplementedError\n"
        "    @classmethod\n"
        "    def from_store(cls, config, rows): raise NotImplementedError\n"
        "    async def _eval_opr(self): return True\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "fake_tat_pkg", raising=False)
    monkeypatch.setattr(M, "FRAMEWORK_NODE_CLASSES", [Sec])
    loaded = plugin.load(["fake_tat_pkg"])
    assert list(plugin.kinds) == ["section", "fake"]
    assert list(loaded.edit_schema["$defs"]) == ["Sec", "Fake", "Construct"]
    with pytest.raises(TAT_InternalError, match="after load returned"):
        plugin.TAT_node(Thm)
    assert list(plugin.kinds) == ["section", "fake"]


def test_a_package_that_fails_its_checks_fails_the_load(tmp_path, monkeypatch):
    (tmp_path / "broken_tat_pkg.py").write_text(
        "from isabelle_theory_agent import model, plugin\n"
        "@plugin.TAT_node\n"
        "class Broken(model.Leaf):\n"
        "    construct_schema = {'type': 'object'}\n"
        "    async def _eval_opr(self): return True\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "broken_tat_pkg", raising=False)
    with pytest.raises(CannotLoadPlugin) as e:
        plugin.load(["broken_tat_pkg"])
    assert (e.value.package, e.value.node_class) == ("broken_tat_pkg", "Broken")
    assert plugin.kinds == {} and not plugin._sealed


def test_an_empty_table_cannot_complete_the_edit_schema():
    with pytest.raises(CannotLoadPlugin, match="cannot load the assembled edit schema") as e:
        plugin.edit_schema()
    assert e.value.node_class is None and e.value.package is None
