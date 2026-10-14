"""The loader (PLUGIN_SYSTEM.md): registration and its checks, the
process-wide registry and the conversation's kind table selected from it,
assembly of the `edit` schema's `$defs`.
Run: python -m pytest test/test_plugin.py
"""

import sys
from typing import Any, Literal, NotRequired, Required, TypedDict

import jsonschema
import pytest

from isabelle_theory_agent import jobs, model as M, plugin
from isabelle_theory_agent.exceptions import (
    InvalidField, MissingField, TAT_InternalError, TAT_StartupError, UnexpectedField)
from isabelle_theory_agent.plugin import CannotLoadPlugin

# The classes TAT ships, captured before the fixture below empties the list
# for each test: `test_a_construct_of_every_shipped_kind_validates` holds
# them to the plan's §7 step 2 requirement.
SHIPPED = list(M.FRAMEWORK_NODE_CLASSES)


@pytest.fixture(autouse=True)
def fresh_registry(monkeypatch):
    monkeypatch.setattr(plugin, "registry", {})
    monkeypatch.setattr(plugin, "compile_hooks", {})
    monkeypatch.setattr(M, "FRAMEWORK_NODE_CLASSES", [])


def registered():
    """Every class in the registry, for the assembly and schema tests."""
    return list(plugin.registry)


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
        plugin.assemble(registered())
    assert (e.value.package, e.value.node_class) == (__name__, cls.__name__)


# --- registration ------------------------------------------------------------

def test_a_class_registers_every_kind_its_schema_names_in_order():
    assert plugin.TAT_node(Thm) is Thm
    plugin.TAT_node(Sec)
    assert plugin.registry == {Thm: ["lemma", "theorem"], Sec: ["section"]}
    assert registered() == [Thm, Sec]


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
    # a kind heads every id component, so it keeps to the name grammar
    for bad in ("my.leaf", "my leaf", "1st", "leaf_"):
        refused(leaf("Odd", [bad]), f"kind `{bad}` is outside the name grammar")
    assert plugin.registry == {Thm: ["lemma", "theorem"]}   # nothing half-registered
    plugin.TAT_node(leaf("Hyphenated", ["my-leaf"]))        # an interior hyphen is within it


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
    plugin.TAT_node(leaf("Owing", ["owing"], _unfinished=lambda self: None))


def test_the_readiness_and_the_line_are_the_frameworks_and_rendering_is_synchronous():
    refused(leaf("Ready", ["ready"], _operations_ready=lambda self: True),
            "overrides `_operations_ready`")
    refused(leaf("Own", ["own"], _own_statuses=lambda self: []), "overrides `_own_statuses`")
    refused(leaf("Liner", ["liner"], print=lambda self, i, o, m, d: None), "overrides `print`")

    async def fields(self, indent, out, mode, depth): ...
    async def mark(self, mode, depth): ...
    refused(leaf("Slow", ["slow"], print_fields=fields), "`print_fields` is a coroutine")
    refused(leaf("Slower", ["slower"], mark=mark), "`mark` is a coroutine")
    plugin.TAT_node(leaf("Marked", ["marked"], mark=lambda self, m, d: "marked",
                         print_fields=lambda self, i, o, m, d: None))


def test_the_descent_is_the_frameworks_for_leaves_and_nesting_classes_alike():
    """`NonLeaf_Node` defines `_children_to_print` itself, so a plain
    nesting class must still register while an override in a plugin is
    refused, whichever hierarchy class it descends from."""
    descent = lambda self, mode, depth: []            # noqa: E731
    refused(leaf("Flat", ["flat"], _children_to_print=descent), "overrides `_children_to_print`")
    rogue = block("Rogue", {"type": "array", "items": {"$ref": "#/$defs/Construct"}})
    rogue._children_to_print = descent                # type: ignore[method-assign]
    refused(rogue, "overrides `_children_to_print`")
    plugin.TAT_node(block("Plain", {"type": "array", "items": {"$ref": "#/$defs/Construct"}}))


def test_emission_is_the_frameworks_to_place_and_an_override_keeps_its_methods_kind():
    """COMPILATION.md §3's three rules: a `StdBlock` class does not
    override `emit`; it overrides `_eval_ending_opr` exactly when it
    overrides `emit_ending`; an override is a coroutine function exactly
    when the method it overrides is."""
    children = {"type": "array", "items": {"$ref": "#/$defs/Construct"}}
    plain = lambda self, indent, out: indent          # noqa: E731
    async def ending(self): return True

    placing = block("Placing", children)
    placing.emit = plain                              # type: ignore[method-assign]
    refused(placing, "overrides `emit`")
    runs_an_ending = block("Runs", children)
    runs_an_ending._eval_ending_opr = ending          # type: ignore[method-assign]
    refused(runs_an_ending, "one of `_eval_ending_opr` and `emit_ending` without the other")
    writes_an_ending = block("Writes", children)
    writes_an_ending.emit_ending = plain              # type: ignore[method-assign]
    refused(writes_an_ending, "one of `_eval_ending_opr` and `emit_ending` without the other")
    both = block("Both", children)
    both._eval_ending_opr, both.emit_ending = ending, plain   # type: ignore[method-assign]
    plugin.TAT_node(both)

    async def can_emit(self): return True             # would answer a coroutine object, which is true
    async def emit(self, indent, out): return indent
    async def invalidated(self, operation): ...
    refused(leaf("Eager", ["eager"], can_emit=can_emit), "`can_emit` is a coroutine")
    refused(leaf("Awaited", ["awaited"], emit=emit), "`emit` is a coroutine")
    refused(leaf("Hooked", ["hooked"], on_invalidated=invalidated), "`on_invalidated` is a coroutine")
    refused(leaf("Lazy", ["lazy"], _eval_opr=lambda self: True), "`_eval_opr` is not a coroutine")
    plugin.TAT_node(leaf("Emits", ["emits"], emit=plain, can_emit=lambda self: True))

    # the rule reads the class's whole ancestry: a method inherited from a
    # mixin overrides the framework's as one in the class's own body does
    class Eager_Mixin:
        async def can_emit(self): return True
    class Lazy_Mixin:
        def _eval_opr(self): return True
    def inheriting(name, mixin, **body):
        return type(name, (mixin, Persisted, M.Leaf), {
            "construct_schema": leaf_schema([name.lower()]), "argument_schema": Empty,
            "__module__": __name__, **body})
    refused(inheriting("Inherits_Eager", Eager_Mixin, _eval_opr=Thm._eval_opr),
            "`can_emit` is a coroutine")
    refused(inheriting("Inherits_Lazy", Lazy_Mixin), "`_eval_opr` is not a coroutine")


def test_a_node_is_equal_to_and_hashed_as_itself_alone():
    """Nodes live in sets and in lists compared with `==` (PRINT.md §2,
    `Forest.id_of`): a class defining `__eq__` or `__hash__` is refused —
    `__eq__` alone, which drops `__hash__`; `__hash__` alone; and `__eq__`
    beside `__hash__ = object.__hash__`, CPython's idiom for staying
    hashable."""
    equal = lambda self, other: True                  # noqa: E731
    refused(leaf("Equal", ["equal"], __eq__=equal), "defines `__eq__` or `__hash__`")
    refused(leaf("Hashed", ["hashed"], __hash__=lambda self: 0), "defines `__eq__` or `__hash__`")
    refused(leaf("Both", ["both"], __eq__=equal, __hash__=object.__hash__),
            "defines `__eq__` or `__hash__`")
    plugin.TAT_node(leaf("Hashable", ["hashable"]))


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
    # `Required` inside a `total=False` declaration is read off the annotation too
    class Mostly_Optional(TypedDict, total=False):
        name: Required[str]
        note: str
    fields = {"name": {"type": "string"}, "note": {"type": "string"}}
    plugin.TAT_node(leaf("M4", ["m4"], argument_schema=Mostly_Optional,
                         construct_schema=leaf_schema(["m4"], fields, required=["name"])))
    refused(leaf("M5", ["m5"], argument_schema=Mostly_Optional,
                 construct_schema=leaf_schema(["m5"], fields)),
            r"requires \[\], argument_schema requires \['name'\]")


def test_a_field_may_not_take_the_name_of_a_row_the_framework_stores():
    """A construct's two framework fields are `kind` and `children`; a
    class declaring a field under the name of another row the framework
    stores would load and then fail at its first store."""
    class Statuses(TypedDict):
        last_evaluation_statuses: NotRequired[str]
    schema = leaf_schema(["st"], {"last_evaluation_statuses": {"type": "string"}})
    refused(leaf("St", ["st"], construct_schema=schema, argument_schema=Statuses),
            "declares the field `last_evaluation_statuses`, the name of a row the framework stores")


# --- a tool call's arguments against its schema (TOOL_SCHEMAS.md §4) ---------

def call_schema(properties, **more):
    return {"type": "object", "additionalProperties": False, "properties": properties, **more}


CALL = call_schema({
    "names": {"type": "array", "minItems": 1, "items": {"type": "string"}},
    "at": call_schema({"row": {"type": "number"},
                       "tag": {"type": "string", "enum": ["a", "b"]},
                       "line": {"type": "integer", "enum": [1, 2, 3]}}, required=["row"]),
    "constructs": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/Construct"}},
    "flag": {"type": "boolean"},
}, required=["names", "at"], **{"$defs": {                    # as the assembled `edit` schema's (PLUGIN_SYSTEM §4)
    "Construct": {"anyOf": [{"$ref": "#/$defs/Thm"}]},
    "Thm": {"type": "object", "properties": {"kind": {"const": "lemma"}},
            "required": ["kind"], "additionalProperties": False}}})


def test_a_call_is_checked_against_its_schema_down_to_the_innermost_argument():
    """Every shape `check_call` reads, on one schema: the arguments the tool
    takes and requires, each JSON type, an `enum`, `minItems`, an object's
    fields, a typed `items`' elements — and the constructs, left alone
    though `$defs` holds `Construct`, as the assembled `edit` schema's does."""
    plugin.validate_call_schema(CALL, "t")
    plugin.check_call(CALL, "t", {"names": ["x"], "at": {"row": 1.5, "tag": "a", "line": 3},
                                  "constructs": [5, "not a construct"], "flag": True})

    def refused(cls, arguments):
        with pytest.raises(cls) as e:
            plugin.check_call(CALL, "t", arguments)
        assert e.value.of_tool
        return e.value

    e = refused(UnexpectedField, {"names": ["x"], "at": {"row": 1}, "x": 0})
    assert (e.holder, e.field, e.takes, e.holder_is_top) == (
        "t", "x", ["names", "at", "constructs", "flag"], True)
    assert refused(UnexpectedField, {"x": 0}).field == "x"        # a typo beats its own hole
    e = refused(MissingField, {"names": ["x"]})
    assert (e.holder, e.field) == ("t", "at")
    e = refused(MissingField, {"names": ["x"], "at": {}})
    assert (e.holder, e.field) == ("t", "at.row")
    e = refused(UnexpectedField, {"names": ["x"], "at": {"row": 1, "col": 2}})
    assert (e.holder, e.field, e.takes, e.holder_is_top) == ("at", "col", ["row", "tag", "line"], False)
    for arguments, field, reason in [
        ({"names": "x", "at": {"row": 1}}, "names", "must be a list"),
        ({"names": [], "at": {"row": 1}}, "names", "must not be empty"),
        ({"names": ["x", 2], "at": {"row": 1}}, "names[1]", "must be a string"),
        ({"names": ["x"], "at": 5}, "at", "must be an object"),
        ({"names": ["x"], "at": {"row": True}}, "at.row", "must be a number"),
        ({"names": ["x"], "at": {"row": "1"}}, "at.row", "must be a number"),
        ({"names": ["x"], "at": {"row": 1, "tag": 1}}, "at.tag", "must be a string"),
        ({"names": ["x"], "at": {"row": 1, "tag": "c"}}, "at.tag", "must be one of `a`, `b`"),
        ({"names": ["x"], "at": {"row": 1, "line": 1.5}}, "at.line", "must be an integer"),
        ({"names": ["x"], "at": {"row": 1, "line": 1.0}}, "at.line", "must be an integer"),
        ({"names": ["x"], "at": {"row": 1, "line": True}}, "at.line", "must be an integer"),
        # an enum is read whatever the type, as `_KEYWORDS` says
        ({"names": ["x"], "at": {"row": 1, "line": 4}}, "at.line", "must be one of `1`, `2`, `3`"),
        ({"names": ["x"], "at": {"row": 1}, "flag": 1}, "flag", "must be a boolean"),
        # falsy and not a list: the type's sentence, not `minItems`'s
        ({"names": ["x"], "at": {"row": 1}, "constructs": {}}, "constructs", "must be a list"),
        ({"names": ["x"], "at": {"row": 1}, "constructs": []}, "constructs", "must not be empty"),
    ]:
        e = refused(InvalidField, arguments)
        assert (e.field, e.reason) == (field, reason), arguments


def test_a_tool_schema_may_say_nothing_the_check_does_not_enforce():
    """`validate_call_schema`: a schema that is not well formed, a top
    that is not an object, a keyword the check does not read, a JSON type
    it has no phrase for, a `minItems` its sentence cannot say, an `items`
    neither typed nor the constructs, an object without its three
    keywords, `$defs` below the top — each refused where the tools are
    built, naming the schema at fault."""
    def refused(schema, match):
        with pytest.raises(TAT_InternalError, match=match):
            plugin.validate_call_schema(schema, "t")

    plugin.validate_call_schema(call_schema({}), "t")
    refused(call_schema({}, required="z"), "t: not a well-formed JSON schema")
    refused(call_schema({"n": {"type": "string", "enum": 3}}), "t: not a well-formed JSON schema")
    refused({"type": "string"}, "t: a tool takes an object")
    refused({"type": "object", "properties": {}}, "t: an object schema needs")
    refused(call_schema({}, required=["z"]), "t: an object schema needs")
    refused(call_schema({}, maxProperties=1), r"t: \['maxProperties'\] is outside")
    refused(call_schema({"n": {"type": "null"}}), "t.n: not of one JSON type")
    refused(call_schema({"n": {"type": ["string", "null"]}}), "t.n: not of one JSON type")
    refused(call_schema({"n": {"type": "boolean", "enum": [True]}}), r"t.n: \['enum'\] is outside")
    for json_type, values in [("string", []), ("string", ["a", None]), ("integer", [1, True]),
                              ("number", [0.5, "half"])]:
        refused(call_schema({"n": {"type": json_type, "enum": values}}),
                "t.n: an `enum` needs one or more values of its own type")
    refused(call_schema({"s": {"type": "string", "pattern": "x"}}), r"t.s: \['pattern'\] is outside")
    refused(call_schema({"xs": {"type": "array"}}), r"t.xs\[\]: not of one JSON type")
    refused(call_schema({"xs": {"type": "array", "items": {"$ref": "#/$defs/Other"}}}),
            r"t.xs\[\]: not of one JSON type")
    refused(call_schema({"xs": {"type": "array", "items": {"type": "string"}, "minItems": 2}}),
            "t.xs: only `minItems: 1`")
    refused(call_schema({"o": call_schema({"z": {"type": "string", "x": 1}})}), r"t.o.z: \['x'\] is outside")
    refused(call_schema({"o": {**call_schema({}), "$defs": {}}}), r"t.o: \['\$defs'\] is outside")


def test_the_one_bare_object_the_grammar_admits():
    """MODULE_STRUCTURE §4.4: a property declared as a bare `object` passes
    in one place, `answer`'s `answer` — the grammar's own fact, nothing a
    builder passes — with at most a `description` on it and at the top
    alone; the check reads it as "an object" and no deeper."""
    bare = {"type": "object", "description": "the answer"}
    schema = call_schema({"node_id": {"type": "string"}, "answer": bare}, required=["node_id", "answer"])
    with pytest.raises(TAT_InternalError, match="t.answer: an object schema needs"):
        plugin.validate_call_schema(schema, "t")                       # another tool's `answer`
    plugin.validate_call_schema(schema, "answer")
    plugin.check_call(schema, "answer", {"node_id": "x", "answer": {"anything": [1, 2]}})
    with pytest.raises(InvalidField) as e:
        plugin.check_call(schema, "answer", {"node_id": "x", "answer": "yes"})
    assert (e.value.field, e.value.reason) == ("answer", "must be an object")
    for wrong, where in [({**bare, "required": []}, "answer.answer"),
                         (call_schema({"o": bare}, required=["o"]), "answer.answer.o")]:
        with pytest.raises(TAT_InternalError, match=f"{where}: an object schema needs"):
            plugin.validate_call_schema(call_schema({"answer": wrong}), "answer")
    with pytest.raises(TAT_InternalError, match="answer.node_id: an object schema needs"):
        plugin.validate_call_schema(call_schema({"node_id": bare}), "answer")   # another property of the tool's


# --- assembly ----------------------------------------------------------------

def test_assembly_hoists_defs_builds_the_union_and_changes_nothing_else():
    plugin.TAT_node(Thm)
    plugin.TAT_node(Sec)
    defs = plugin.assemble([Thm, Sec])
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
    defs = plugin.assemble(registered())
    assert "Tree" in defs and defs["U"]["properties"]["inner"] == {"$ref": "#/$defs/Thm"}


# --- the edit schema, loading and the conversation's table -----------------

def envelope(*constructs):
    return {"action": "append", "target_id": "theory_X", "evaluate": False,
            "constructs": list(constructs)}


def test_the_completed_edit_schema_validates_constructs():
    plugin.TAT_node(Thm)
    plugin.TAT_node(Sec)
    plugin.TAT_node(block("Thms", {"type": "array", "items": {"$ref": "#/$defs/Thm"}}))
    schema = plugin.edit_schema(registered())
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
SHIPPED_EXAMPLES: dict[str, dict] = {
    "session": {"kind": "session", "name": "Arith", "parent_session": "HOL",
                "options": [{"name": "document", "value": "pdf"}],
                "description": "Arithmetic, from scratch",
                "children": [{"kind": "theory", "name": "X", "imports": ["Main"]}]},
    "theory": {"kind": "theory", "name": "Y",
               "imports": ["Arith.X", "HOL-Library.Multiset"]},
}


def test_a_construct_of_every_shipped_kind_validates():
    for cls in SHIPPED:
        plugin.TAT_node(cls)
    assert set(SHIPPED_EXAMPLES) == {k for kinds in plugin.registry.values() for k in kinds}
    if SHIPPED:
        validator = jsonschema.Draft202012Validator(plugin.edit_schema(SHIPPED))
        for kind, construct in SHIPPED_EXAMPLES.items():
            assert construct["kind"] == kind
            validator.validate(envelope(construct))


def a_leaf_module(name, kind):
    """The source of a module defining one registered Leaf class."""
    return ("from typing import TypedDict\n"
            "from isabelle_theory_agent import model, plugin\n"
            "class Empty(TypedDict): pass\n"
            "@plugin.TAT_node\n"
            f"class {name}(model.Leaf):\n"
            "    construct_schema = {'type': 'object', 'additionalProperties': False,\n"
            f"        'properties': {{'kind': {{'const': '{kind}'}}}}, 'required': ['kind']}}\n"
            "    argument_schema = Empty\n"
            "    @classmethod\n"
            "    async def gen(cls, config, raw): raise NotImplementedError\n"
            "    def to_store(self, rows): raise NotImplementedError\n"
            "    @classmethod\n"
            "    def from_store(cls, config, rows): raise NotImplementedError\n"
            "    async def _eval_opr(self): return True\n")


@pytest.fixture
def two_packages(tmp_path, monkeypatch):
    """`fake_tat_pkg`, a package whose class lives in a submodule, and
    `other_tat_pkg`, a module that imports it and defines a class of its
    own — importing `other_tat_pkg` registers both classes."""
    pkg = tmp_path / "fake_tat_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from . import nodes\n")
    (pkg / "nodes.py").write_text(a_leaf_module("Fake", "fake"))
    (tmp_path / "other_tat_pkg.py").write_text(
        "import fake_tat_pkg\n" + a_leaf_module("Other", "other"))
    monkeypatch.syspath_prepend(str(tmp_path))
    for module in ("fake_tat_pkg", "fake_tat_pkg.nodes", "other_tat_pkg"):
        monkeypatch.delitem(sys.modules, module, raising=False)


def test_load_registers_the_framework_first_then_imports_then_selects(two_packages, monkeypatch):
    monkeypatch.setattr(M, "FRAMEWORK_NODE_CLASSES", [Sec])
    loaded = plugin.load(["fake_tat_pkg"])
    assert list(loaded.kinds) == ["section", "fake"]        # the submodule's class counts
    assert list(loaded.edit_schema["$defs"]) == ["Sec", "Fake", "Construct"]
    assert [c.__name__ for c in registered()] == ["Sec", "Fake"]


def test_a_second_load_in_the_process_registers_nothing_again(two_packages, monkeypatch):
    monkeypatch.setattr(M, "FRAMEWORK_NODE_CLASSES", [Sec])
    first = plugin.load(["fake_tat_pkg"])
    before = dict(plugin.registry)
    again = plugin.load(["fake_tat_pkg"])
    assert again.kinds == first.kinds and plugin.registry == before
    # a class registering after a load joins the registry, not that load's table
    plugin.TAT_node(Thm)
    assert "lemma" not in first.kinds and Thm in plugin.registry


def test_the_table_holds_the_listed_packages_classes_only(two_packages, monkeypatch):
    monkeypatch.setattr(M, "FRAMEWORK_NODE_CLASSES", [Sec])
    # importing other_tat_pkg registers Fake too, but Fake's package is not listed
    loaded = plugin.load(["other_tat_pkg"])
    assert list(loaded.kinds) == ["section", "other"]
    assert [c.__name__ for c in registered()] == ["Sec", "Fake", "Other"]
    # and a conversation listing both, in either order, gets both in registration order
    assert list(plugin.load(["fake_tat_pkg", "other_tat_pkg"]).kinds) == ["section", "fake", "other"]
    assert list(plugin.load(["other_tat_pkg", "fake_tat_pkg"]).kinds) == ["section", "fake", "other"]
    assert list(plugin.load([]).kinds) == ["section"]


def test_a_compile_hook_is_checked_and_registered_at_import_and_returned_by_load(tmp_path, monkeypatch):
    """PLUGIN_SYSTEM §1, §5: a module-level function under
    `@TAT_compile_hook` — a plain function of one positional argument, not
    a coroutine — joins `compile_hooks` in registration order when its
    module is imported; `load` returns those the listed packages define,
    and sweeps the hooks of a module that is gone."""
    def hook_module(*names):
        return ("from isabelle_theory_agent import plugin\n"
                + "".join(f"@plugin.TAT_compile_hook\ndef {n}(forest): return None\n" for n in names))
    pkg = tmp_path / "hooked_tat_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from . import hooks\n" + hook_module("tidy"))
    (pkg / "hooks.py").write_text(hook_module("first", "second"))
    (tmp_path / "other_hooks_pkg.py").write_text(hook_module("elsewhere"))
    monkeypatch.syspath_prepend(str(tmp_path))
    for module in ("hooked_tat_pkg", "hooked_tat_pkg.hooks", "other_hooks_pkg"):
        monkeypatch.delitem(sys.modules, module, raising=False)
    monkeypatch.setattr(M, "FRAMEWORK_NODE_CLASSES", [Sec])

    loaded = plugin.load(["other_hooks_pkg", "hooked_tat_pkg"])
    names = lambda hooks: [h.__name__ for h in hooks]         # noqa: E731
    assert names(plugin.compile_hooks) == ["elsewhere", "first", "second", "tidy"]   # as imported
    assert names(loaded.compile_hooks) == ["elsewhere", "first", "second", "tidy"]
    assert names(plugin.load(["hooked_tat_pkg"]).compile_hooks) == ["first", "second", "tidy"]
    assert plugin.load([]).compile_hooks == () and len(plugin.compile_hooks) == 4    # nothing twice
    monkeypatch.delitem(sys.modules, "other_hooks_pkg")                 # the module is gone
    assert names(plugin.load(["hooked_tat_pkg"]).compile_hooks) == ["first", "second", "tidy"]
    assert names(plugin.compile_hooks) == ["first", "second", "tidy"]

    async def awaited(forest): ...
    def yielding(forest): yield
    async def yielding_awaited(forest): yield
    def two(forest, more): ...
    def keyword(*, forest): ...
    for hook, reason in ((awaited, "not a coroutine"), (yielding, "not a generator"),
                         (yielding_awaited, "not a generator"), (two, "one positional argument"),
                         (keyword, "one positional argument"), (print, "a plain function")):
        with pytest.raises(CannotLoadPlugin, match=reason) as e:
            plugin.TAT_compile_hook(hook)
        assert isinstance(e.value, TAT_StartupError)
    assert names(plugin.compile_hooks) == ["first", "second", "tidy"]    # a refused hook registers nothing


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
    assert plugin.registry == {}


def test_a_failed_load_does_not_poison_the_retry(tmp_path, monkeypatch):
    """A package whose second class fails its checks: the first is
    registered by then, and the failed import drops the module.  Once the
    author has fixed the package, the next load must take it."""
    package = tmp_path / "halfbroken_pkg.py"
    good = a_leaf_module("Good", "good")
    package.write_text(good + "\n@plugin.TAT_node\nclass Broken(model.Leaf):\n"
                       "    construct_schema = {'type': 'object'}\n"
                       "    async def _eval_opr(self): return True\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "halfbroken_pkg", raising=False)
    with pytest.raises(CannotLoadPlugin) as e:
        plugin.load(["halfbroken_pkg"])
    assert e.value.node_class == "Broken"
    package.write_text(good + "\n# the broken class removed\n")   # another size: no stale bytecode
    loaded = plugin.load(["halfbroken_pkg"])
    assert list(loaded.kinds) == ["good"] and [c.__name__ for c in registered()] == ["Good"]


def test_a_package_that_cannot_be_imported_fails_the_load_the_same_way():
    with pytest.raises(CannotLoadPlugin) as e:
        plugin.load(["no_such_tat_pkg"])
    assert (e.value.package, e.value.node_class) == ("no_such_tat_pkg", None)
    assert str(e.value) == \
        "cannot load no_such_tat_pkg: ModuleNotFoundError: No module named 'no_such_tat_pkg'"
    assert isinstance(e.value.__cause__, ModuleNotFoundError)


def test_an_empty_table_cannot_complete_the_edit_schema():
    with pytest.raises(CannotLoadPlugin, match="cannot load the assembled edit schema") as e:
        plugin.edit_schema([])
    assert e.value.node_class is None and e.value.package is None


def test_a_construction_job_class_is_checked():
    """PLUGIN_SYSTEM §5: a `Construction_Job` subclass, complete, overriding
    none of the framework's members."""
    class Half(jobs.Construction_Job):
        @classmethod
        def title(cls, plural=False): return "halves" if plural else "half"

    class Whole(Half):
        @classmethod
        def failure_header(cls, failure): return None
        async def _run(self): return jobs.Succeeded(None)

    class Overriding(Whole):
        def start(self, owner): pass

    refused(leaf("Odd", ["odd"], construction_job_class=object), "not a subclass of `Construction_Job`")
    refused(leaf("Partial", ["partial"], construction_job_class=Half),
            "Half does not implement `_run`, `failure_header`")
    refused(leaf("Framework", ["framework"], construction_job_class=Overriding),
            "Overriding overrides `start`, which is the framework's")
    plugin.TAT_node(leaf("Constructed", ["constructed"], construction_job_class=Whole))

    class Half_Check(jobs.Evaluation_Job):
        @classmethod
        def title(cls, plural=False): return "checks" if plural else "check"
        async def _start(self): pass

    class Check(Half_Check):
        @classmethod
        def failure_header(cls, failure): return None
        @classmethod
        def failure_notification(cls, ids, automatic): return "failed"

    class Reporting(Check):
        def _report(self, errors, product=None): pass

    refused(leaf("Odd_Check", ["odd_check"], evaluation_job_class=Whole), "not a subclass of `Evaluation_Job`")
    refused(leaf("Partial_Check", ["partial_check"], evaluation_job_class=Half_Check),
            "Half_Check does not implement `failure_header`, `failure_notification`")
    refused(leaf("Reporting_Check", ["reporting_check"], evaluation_job_class=Reporting),
            "Reporting overrides `_report`, which is the framework's")
    plugin.TAT_node(leaf("Checked", ["checked"], evaluation_job_class=Check))


def test_edit_takes_auto_construct_when_a_class_names_a_construction_job_class_inherited_or_not():
    """TOOL_SCHEMAS §1: `edit`'s `auto_construct` is there when a loaded
    class names a construction job class — one it inherits included — and
    absent otherwise."""
    class Whole(jobs.Construction_Job):
        @classmethod
        def title(cls, plural=False): return "wholes" if plural else "whole"
        @classmethod
        def failure_header(cls, failure): return None
        async def _run(self): return jobs.Succeeded(None)

    plain = leaf("Plain", ["plain"])
    constructed = leaf("Constructed", ["constructed"], construction_job_class=Whole)
    inheriting = type("Inheriting", (constructed,), {"construct_schema": leaf_schema(["inheriting"]),
                                                       "__module__": __name__})
    for cls in (plain, constructed, inheriting):
        plugin.TAT_node(cls)
    assert "auto_construct" not in plugin.edit_schema([plain])["properties"]
    for classes in ([plain, constructed], [plain, inheriting]):
        assert plugin.edit_schema(classes)["properties"]["auto_construct"] is plugin.AUTO_CONSTRUCT_PROPERTY


def test_a_package_declares_the_theories_the_forests_theories_import(monkeypatch):
    """PLUGIN_SYSTEM §1: `TAT_import(<session>.<short name>)` at import,
    registered as a compile hook is and returned by `load` for the listed
    packages; a name outside the shape is refused."""
    monkeypatch.setattr(plugin, "imports", {})
    plugin.TAT_import("Minilang_AoA.Minilang_AoA")
    assert plugin.imports == {"Minilang_AoA.Minilang_AoA": __name__}
    for bad in ("Minilang_AoA", "S..A", 'S."A"', ""):
        with pytest.raises(CannotLoadPlugin, match="is not a theory name of the shape"):
            plugin.TAT_import(bad)
