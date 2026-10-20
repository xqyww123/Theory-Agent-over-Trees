"""The loader (PLUGIN_SYSTEM.md): registration and its checks, the
process-wide registry and the conversation's kind table selected from it,
assembly of the `edit` schema's `$defs`.
Run: python -m pytest test/test_plugin.py
"""

import json
import sys
from typing import Annotated, Literal, NotRequired, Required, TypedDict, get_args, get_type_hints

import jsonschema
import pytest

from isabelle_theory_agent import jobs, model as M, plugin
from isabelle_theory_agent.exceptions import (
    InvalidField, MissingField, TAT_InternalError, TAT_StartupError, UnexpectedField)
from isabelle_theory_agent.model import NON_EMPTY
from isabelle_theory_agent.mcp_server import CODEX_SCHEMA_MAX_BYTES
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
    """The three methods every class must override (PLUGIN_SYSTEM §5), and
    a `placement`, naming `Sec`, the framework's class in the load tests;
    nothing here is ever built or stored."""
    placement = M.Placement(within="Sec", through=())
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


class S_RawAST(TypedDict):
    s: str


class Tree_RawAST(TypedDict):                 # nests itself, at module level where Python resolves the name: refused
    sub: NotRequired[list["Tree_RawAST"]]


class Leak_First(TypedDict):                  # declared first: typing caches its union …
    v: NotRequired[Thm_Statement | str]


class Leak_Second(TypedDict):                 # … and hands it back for the same union written the other way
    v: NotRequired[str | Thm_Statement]


class Infix_RawAST(TypedDict):
    form: Literal["infix", "infixl"]
    symbol: str


class Binder_RawAST(TypedDict):
    form: Literal["binder"]
    symbol: str
    priority: NotRequired[int]


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


class Whole(jobs.Construction_Job):
    """A complete construction job class, as the loader accepts one."""
    @classmethod
    def title(cls, plural=False): return "wholes" if plural else "whole"
    def failure_header(self, failure): return None
    async def _run(self): return jobs.Succeeded(None)


class Check(jobs.Evaluation_Job):
    """A complete evaluation job class, as the loader accepts one."""
    @classmethod
    def title(cls, plural=False): return "checks" if plural else "check"
    @classmethod
    def failure_header(cls, failure): return None
    @classmethod
    def failure_notification(cls, ids, automatic): return "failed"
    async def _start(self): pass


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
    # a `$ref`, or an `anyOf` of `$ref`s, and at most a `description` beside it
    refused(block("K3", {"type": "array", "items": {"$ref": "#/$defs/Construct", "type": "object",
                                                    "required": ["foo"]}}), "`children` must be")
    refused(block("K4", {"type": "array", "items": {"anyOf": [{"$ref": "#/$defs/Construct"}], "type": "object"}}),
            "`children` must be")
    refused(block("K5", {"type": "array", "items": {"anyOf": [{"$ref": "#/$defs/Construct", "const": "x"}]}}),
            "`children` must be")
    plugin.TAT_node(block("M", {"type": "array", "items": {"$ref": "#/$defs/Construct", "description": "the contents"}}))


def test_children_must_point_at_construct_or_a_node_class():
    class Sec_With_Statement(TypedDict):
        title: str
        s: Thm_Statement
    own = block("Own", {"type": "array", "items": {"$ref": "#/$defs/Statement"}}, defs=STATEMENT)
    own.construct_schema["properties"]["s"] = {"$ref": "#/$defs/Statement"}     # reached by a field: what
    own.construct_schema["required"] = ["kind", "title", "s"]                     # `children` points at is
    own.argument_schema = Sec_With_Statement                                      # assembly's to refuse
    plugin.TAT_node(own)
    refused_at_assembly(own, "`children` must be an array of `\\$ref`s to `Construct` or to"
                             " node classes, not to `#/\\$defs/Statement`")


def test_children_is_an_array_of_refs_and_nothing_more_and_never_required():
    """PLUGIN_SYSTEM §5: `children` is `{"type": "array", "items": X}` and
    nothing else but a `description`; and it is never required — no
    construct must carry it, and an amend's may not."""
    refused(block("Aside", {"type": "array", "prefixItems": [{"$ref": "#/$defs/Statement"}],
                            "items": {"$ref": "#/$defs/Construct"}}, defs=STATEMENT),
            "`children` carries a keyword besides")
    described = block("Described", {"type": "array", "items": {"$ref": "#/$defs/Construct"},
                                    "description": "the contents"})
    plugin.TAT_node(described)
    needy = block("Needy", {"type": "array", "items": {"$ref": "#/$defs/Construct"}})
    needy.construct_schema["required"] = ["kind", "title", "children"]
    refused(needy, "`children` is never required")


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
    misbased = type("Misbased", (Persisted, M.NonLeaf_Node), {      # none of the three bases: `Node`'s `_own_statuses`
        "construct_schema": leaf_schema(["misbased"]), "argument_schema": Empty, "__module__": __name__})
    refused(misbased, "overrides `_own_statuses`")
    refused(leaf("Liner", ["liner"], print=lambda self, i, o, m, d: None), "overrides `print`")

    async def fields(self, indent, out, mode, depth): ...
    async def mark(self, mode, depth): ...
    refused(leaf("Slow", ["slow"], print_fields=fields), "`print_fields` is a coroutine")
    refused(leaf("Slower", ["slower"], mark=mark), "`mark` is a coroutine")
    plugin.TAT_node(leaf("Marked", ["marked"], mark=lambda self, m, d: "marked",
                         print_fields=lambda self, i, o, m, d: None))


def test_job_operation_is_an_operation_of_the_class_and_no_plugin_class_is_a_container():
    """PLUGIN_SYSTEM §5 (CONSTRUCT_INTERACTION §3.1): a `Leaf` or `StdBlock`
    class's `job_operation` is among its `_operation_names()`; a plugin
    class does not derive from `Unchained_Node`, whatever job classes it
    names; `job_operation_status` is the framework's."""
    children = {"type": "array", "items": {"$ref": "#/$defs/Construct"}}
    refused(leaf("Opening_Leaf", ["opening_leaf"], job_operation="beginning"),
            "`job_operation` is 'beginning', not an operation of the class: None")
    bare = block("Bare", children)
    bare.job_operation = None
    refused(bare, "`job_operation` is None, not an operation of the class: 'beginning', 'ending'")
    middle = block("Middle", children)
    middle.job_operation = "middle"
    refused(middle, "`job_operation` is 'middle', not an operation of the class: 'beginning', 'ending'")
    opening = block("Opening", children)
    opening.job_operation = "beginning"
    plugin.TAT_node(opening)
    plugin.TAT_node(leaf("Closing", ["closing"], job_operation=None))

    def container(name, **body):
        schema = dict(Sec.construct_schema)
        schema["properties"] = dict(schema["properties"]) | {"kind": {"const": name.lower()}}
        return type(name, (Persisted, M.Unchained_Node), {
            "construct_schema": schema, "argument_schema": Sec_RawAST, "__module__": __name__, **body})
    for body in ({}, {"construction_job_class": Whole}, {"evaluation_job_class": Check}):
        refused(container("Container", **body), "derives from `Unchained_Node`, which only the framework's classes do")
    refused(leaf("Seeing", ["seeing"], job_operation_status=lambda self: M.READY_CLEAN),
            "overrides `job_operation_status`, which is the framework's")


def test_a_plugin_class_declares_its_placement_and_leaves_evaluate_to_the_framework(monkeypatch):
    """PLUGIN_SYSTEM §5: a plugin class carries a `Placement`, its own or
    inherited, and does not override `_evaluate`, on a leaf or a block,
    so that no class skips the placement check; the framework's classes
    are exempt from both."""
    async def own_evaluate(self, ev, mode): ...
    refused(leaf("Unplaced", ["unplaced"], placement=None), "declares no `placement`")
    placeless = type("Placeless", (M.Leaf,), {
        "construct_schema": leaf_schema(["placeless"]), "argument_schema": Empty, "_eval_opr": Thm._eval_opr,
        "__module__": __name__, **{m: Persisted.__dict__[m] for m in ("gen", "to_store", "from_store")}})
    refused(placeless, "declares no `placement`")
    refused(leaf("Own_Leaf", ["own_leaf"], _evaluate=own_evaluate), "overrides `_evaluate`, which is the framework's")
    children = {"type": "array", "items": {"$ref": "#/$defs/Construct"}}
    refused(type("Own_Block", (block("Plain_Block", children),), {"_evaluate": own_evaluate, "__module__": __name__}),
            "overrides `_evaluate`, which is the framework's")
    plugin.TAT_node(leaf("Inherited", ["inherited"]))
    exempt = leaf("Exempt", ["exempt"], placement=None)
    monkeypatch.setattr(M, "FRAMEWORK_NODE_CLASSES", [exempt])
    plugin.TAT_node(exempt)


def test_load_refuses_a_placement_naming_no_class_a_container_or_a_class_of_several_kinds(monkeypatch):
    """PLUGIN_SYSTEM §5, judged once every package is imported: each name a
    class of the conversation's; `within` not an `Unchained_Node` class,
    nor a class answering to several kinds; two classes naming each other
    load in either order of registration."""
    monkeypatch.setattr(M, "FRAMEWORK_NODE_CLASSES", [Sec, M.Session, M.Theory])
    def load_refusing(cls, match):
        monkeypatch.setattr(plugin, "registry", {})
        plugin.TAT_node(cls)                                       # registration cannot judge the names
        with pytest.raises(CannotLoadPlugin, match=match) as e:
            plugin.load([__name__])
        assert e.value.node_class == cls.__name__
    load_refusing(leaf("Lost", ["lost"], placement=M.Placement(within="Sec", through=("Nowhere",))),
                  "`placement` names `Nowhere`, which is not a node class of the conversation")
    load_refusing(leaf("Lost_Within", ["lost_within"], placement=M.Placement(within="Nowhere", through=())),
                  "`placement` names `Nowhere`, which is not a node class of the conversation")
    load_refusing(leaf("Unchained_Within", ["unchained_within"], placement=M.Placement(within="Session", through=())),
                  "`placement.within` names `Session`, which runs no operation")
    two_kinds = leaf("Two_Kinds", ["two_a", "two_b"])
    monkeypatch.setattr(M, "FRAMEWORK_NODE_CLASSES", [Sec, two_kinds])
    load_refusing(leaf("Within_Two", ["within_two"], placement=M.Placement(within="Two_Kinds", through=())),
                  "`placement.within` names `Two_Kinds`, which answers to several kinds")
    monkeypatch.setattr(M, "FRAMEWORK_NODE_CLASSES", [Sec])
    one = block("One", {"type": "array", "items": {"$ref": "#/$defs/Construct"}})
    one.placement = M.Placement(within="Sec", through=("Other",))
    other = block("Other", {"type": "array", "items": {"$ref": "#/$defs/Construct"}})
    other.placement = M.Placement(within="Sec", through=("One",))
    for order in ((one, other), (other, one)):
        monkeypatch.setattr(plugin, "registry", {})
        for cls in order:
            plugin.TAT_node(cls)
        assert set(plugin.load([__name__]).kinds) == {"section", "one", "other"}


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
            "_eval_opr": Thm._eval_opr, "placement": Persisted.placement, "__module__": __name__,
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
    refused(leaf("M1", ["m1"], argument_schema=Named),
            r"disagree at `construct_schema`: the fields \[\] against \['name'\]")
    named = leaf_schema(["m2"], {"name": {"type": "string"}})     # not required in the schema
    refused(leaf("M2", ["m2"], construct_schema=named, argument_schema=Named),
            r"the required fields \[\] against \['name'\]")
    class Optional_(TypedDict):
        name: NotRequired[str]
    plugin.TAT_node(leaf("M3", ["m3"],
                         construct_schema=leaf_schema(["m3"], {"name": {"type": "string"}}),
                         argument_schema=Optional_))
    refused(leaf("M6", ["m6"], argument_schema=Optional_,       # required in the schema alone
                 construct_schema=leaf_schema(["m6"], {"name": {"type": "string"}}, required=["name"])),
            r"the required fields \['name'\] against \[\]")
    # `Required` inside a `total=False` declaration is read off the annotation too
    class Mostly_Optional(TypedDict, total=False):
        name: Required[str]
        note: str
    fields = {"name": {"type": "string"}, "note": {"type": "string"}}
    plugin.TAT_node(leaf("M4", ["m4"], argument_schema=Mostly_Optional,
                         construct_schema=leaf_schema(["m4"], fields, required=["name"])))
    refused(leaf("M5", ["m5"], argument_schema=Mostly_Optional,
                 construct_schema=leaf_schema(["m5"], fields)),
            r"the required fields \[\] against \['name'\]")


def declaring(name, fields, td, required=(), defs=None):
    """A leaf class of kind `<name>` declaring `fields` and typed by `td`."""
    return leaf(name, [name.lower()], argument_schema=td,
                construct_schema=leaf_schema([name.lower()], fields, required=required, defs=defs))


def test_the_agreement_holds_at_every_depth():
    """PLUGIN_SYSTEM §5: a `$ref` is followed into `$defs`; a string with
    an `enum` is a `Literal` of those values, as sets; `minItems: 1` is
    the non-empty list and only that; an `anyOf` pairs with a union by
    JSON type, objects by the choosing field's values; the field at fault
    is named by its path."""
    class Wrong_Statement(TypedDict):
        text: int
    class Holds(TypedDict):
        statement: Wrong_Statement
    refused(declaring("D1", {"statement": {"$ref": "#/$defs/Statement"}}, Holds,
                      required=["statement"], defs=STATEMENT),
            r"disagree at `construct_schema.statement.text`: a string against <class 'int'>")
    class Lit(TypedDict):
        level: Literal["high", "low"]                 # the other way round
    class Plain(TypedDict):
        level: str
    class Other_Lit(TypedDict):
        level: Literal["low", "mid"]
    level = {"level": {"type": "string", "enum": ["low", "high"]}}
    plugin.TAT_node(declaring("D2", level, Lit, required=["level"]))
    refused(declaring("D3", level, Plain, required=["level"]), "an `enum` of")
    refused(declaring("D4", level, Other_Lit, required=["level"]), "an `enum` of")
    class Some(TypedDict):
        xs: Annotated[list[str], NON_EMPTY]
    class Maybe(TypedDict):
        xs: list[str]
    class Ints(TypedDict):
        xs: list[int]
    non_empty = {"xs": {"type": "array", "items": {"type": "string"}, "minItems": 1}}
    maybe = {"xs": {"type": "array", "items": {"type": "string"}}}
    plugin.TAT_node(declaring("D5", non_empty, Some, required=["xs"]))
    plugin.TAT_node(declaring("D6", maybe, Maybe, required=["xs"]))
    refused(declaring("D7", non_empty, Maybe, required=["xs"]), "`minItems: 1` is `Annotated")
    refused(declaring("D8", maybe, Some, required=["xs"]), "`minItems: 1` is `Annotated")
    refused(declaring("D9", maybe, Ints, required=["xs"]),
            r"disagree at `construct_schema.xs\[\]`: a string against <class 'int'>")
    # a flat mixed union, its arms in another order than the `anyOf`'s
    class Mixed(TypedDict):
        v: str | int | list[str] | Thm_Statement
    class Fewer(TypedDict):
        v: str | int
    class Not_A_Union(TypedDict):
        v: str
    mixed = {"v": {"anyOf": [{"type": "integer"}, {"type": "array", "items": {"type": "string"}},
                             {"$ref": "#/$defs/Statement"}, {"type": "string"}]}}
    plugin.TAT_node(declaring("D10", mixed, Mixed, required=["v"], defs=STATEMENT))
    refused(declaring("D11", mixed, Fewer, required=["v"], defs=STATEMENT), "JSON types")
    refused(declaring("D12", mixed, Not_A_Union, required=["v"], defs=STATEMENT), "an `anyOf` against")
    # objects told apart by `form`, paired by its values, whatever the order
    syntax = {"syntax": {"anyOf": [
        {"type": "object", "required": ["form", "symbol"], "additionalProperties": False,
         "properties": {"form": {"type": "string", "enum": ["infix", "infixl"]}, "symbol": {"type": "string"}}},
        {"type": "object", "required": ["form", "symbol"], "additionalProperties": False,
         "properties": {"form": {"type": "string", "enum": ["binder"]}, "symbol": {"type": "string"},
                        "priority": {"type": "integer"}}}]}}
    class Syntax(TypedDict):
        syntax: Binder_RawAST | Infix_RawAST
    class Postfix_RawAST(TypedDict):
        form: Literal["postfix"]
        symbol: str
    class Other_Syntax(TypedDict):
        syntax: Infix_RawAST | Postfix_RawAST
    class Binder_Priority_Str(TypedDict):
        form: Literal["binder"]
        symbol: str
        priority: NotRequired[str]
    class Syntax_2(TypedDict):
        syntax: Infix_RawAST | Binder_Priority_Str
    plugin.TAT_node(declaring("D13", syntax, Syntax, required=["syntax"]))
    refused(declaring("D14", syntax, Other_Syntax, required=["syntax"]),
            r"the `anyOf` arms' `form` values \[\['binder'\], \['infix', 'infixl'\]\] against the union's"
            r" \[\['infix', 'infixl'\], \['postfix'\]\]")
    # one for one: two arms of one value set, and as many arms of a type as the union has
    doubled = {"syntax": {"anyOf": [syntax["syntax"]["anyOf"][0], syntax["syntax"]["anyOf"][0]]}}
    refused(declaring("D14b", doubled, Syntax, required=["syntax"]), r"the `anyOf` arms' `form` values")
    class No_Literal(TypedDict):
        x: str
    class One_Object(TypedDict):
        syntax: str | No_Literal
    refused(declaring("D14c", {"syntax": {"anyOf": [*syntax["syntax"]["anyOf"], {"type": "string"}]}},
                      One_Object, required=["syntax"]),
            "2 `anyOf` arms of JSON type object against 1 of the union's")
    refused(declaring("D15", syntax, Syntax_2, required=["syntax"]),
            r"disagree at `construct_schema.syntax<form=binder>.priority`: an integer against <class 'str'>")
    # the `anyOf`'s objects are told apart by the very field the TypedDicts are, and that one alone
    two_fields = {"syntax": {"anyOf": [
        {**arm, "required": [*arm["required"], "mode"],
         "properties": {**arm["properties"],
                        "mode": {"type": "string", "enum": [arm["properties"]["form"]["enum"][0]]}}}
        for arm in syntax["syntax"]["anyOf"]]}}
    class Infix_Mode(TypedDict):
        form: Literal["infix", "infixl"]
        symbol: str
        mode: str
    class Binder_Mode(TypedDict):
        form: Literal["binder"]
        symbol: str
        priority: NotRequired[int]
        mode: str
    class Two(TypedDict):
        syntax: Infix_Mode | Binder_Mode
    refused(declaring("D16", two_fields, Two, required=["syntax"]),
            r"told apart by \['form', 'mode'\], the union's TypedDicts by `form`")
    # an optional `enum` field the arms share chooses nothing: the class registers
    class Styled_A(TypedDict):
        form: Literal["a"]
        style: NotRequired[Literal["x", "y"]]
    class Styled_B(TypedDict):
        form: Literal["b"]
        style: NotRequired[Literal["x", "y"]]
    class Styled(TypedDict):
        s: Styled_A | Styled_B
    style = {"type": "string", "enum": ["x", "y"]}
    plugin.TAT_node(declaring("D16b", {"s": {"anyOf": [
        {"type": "object", "required": ["form"], "additionalProperties": False,
         "properties": {"form": {"type": "string", "enum": ["a"]}, "style": style}},
        {"type": "object", "required": ["form"], "additionalProperties": False,
         "properties": {"form": {"type": "string", "enum": ["b"]}, "style": style}}]}}, Styled, required=["s"]))
    # a `$ref` met again with another annotation is followed again
    class Twice(TypedDict):
        a: Thm_Statement
        b: Wrong_Statement
    refused(declaring("D17", {"a": {"$ref": "#/$defs/Statement"}, "b": {"$ref": "#/$defs/Statement"}},
                      Twice, required=["a", "b"], defs=STATEMENT),
            r"disagree at `construct_schema.b.text`")
    # `kind` and `children` are set aside at the top alone
    class Inner_Kind(TypedDict):
        kind: str
    class Nested_Kind(TypedDict):
        inner: Inner_Kind
    inner = {"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"],
             "additionalProperties": False}
    plugin.TAT_node(declaring("D18", {"inner": inner}, Nested_Kind, required=["inner"]))
    class Inner_Plain(TypedDict):
        pass
    class Nested_Plain(TypedDict):
        inner: Inner_Plain
    refused(declaring("D19", {"inner": inner}, Nested_Plain, required=["inner"]),
            r"disagree at `construct_schema.inner`: the fields \['kind'\] against \[\]")
    # the memo is by definition and annotation: another definition met with the same annotation is followed
    other = {"type": "object", "properties": {"text": {"type": "integer"}}, "required": ["text"],
             "additionalProperties": False}
    class Twice_Same(TypedDict):
        a: Thm_Statement
        b: Thm_Statement
    refused(declaring("D20", {"a": {"$ref": "#/$defs/Statement"}, "b": {"$ref": "#/$defs/Other"}},
                      Twice_Same, required=["a", "b"], defs={**STATEMENT, "Other": other}),
            r"disagree at `construct_schema.b.text`: an integer against <class 'str'>")
    # an integer is not a float, a number not an int
    class Float_N(TypedDict):
        n: float
    class Int_N(TypedDict):
        n: int
    refused(declaring("D21", {"n": {"type": "integer"}}, Float_N, required=["n"]), "an integer against <class 'float'>")
    refused(declaring("D22", {"n": {"type": "number"}}, Int_N, required=["n"]), "a number against <class 'int'>")
    class Int_Or_Str(TypedDict):
        v: int | str
    refused(declaring("D23", {"v": {"anyOf": [{"type": "integer"}, {"type": "number"}, {"type": "string"}]}},
                      Int_Or_Str, required=["v"]), "2 `anyOf` arms of JSON type number against 1 of the union's")


def test_arms_are_paired_as_sets_since_typing_hands_a_union_back_in_another_order():
    """MODULE_STRUCTURE §4.4: `NotRequired[str | Thm_Statement]`, written
    after `NotRequired[Thm_Statement | str]`, comes back from typing's
    cache with the first's arms; the agreement pairs arms by JSON type,
    never by position, so the class loads."""
    (union,) = get_args(get_type_hints(Leak_Second, include_extras=True)["v"])
    assert get_args(union) == (Thm_Statement, str), "typing no longer leaks the order; revisit this case"
    schema = leaf_schema(["leak"], {"v": {"anyOf": [{"type": "string"}, {"$ref": "#/$defs/Statement"}]}},
                         defs=STATEMENT)
    plugin.TAT_node(leaf("Leak", ["leak"], construct_schema=schema, argument_schema=Leak_Second))


def test_the_construct_schema_keeps_to_its_grammar():
    """PLUGIN_SYSTEM §5: `$defs` keys are identifiers; no keyword besides
    the grammar's, `description`, and `$defs` at the top alone; an `enum`
    is a string's; only `minItems: 1`; no `anyOf` arm an `anyOf`; `kind`
    an `enum` or a `const`, not both, with nothing else but a `type` of
    `string` and a `description`."""
    def refused_schema(fields, match, defs=None, **top):
        refused(leaf("G", ["g"], construct_schema=leaf_schema(["g"], fields, defs=defs) | top), match)
    refused_schema({}, "not a Python identifier", defs={"not-an-identifier": {"type": "string"}})
    refused_schema({"s": {"type": "string", "pattern": "x"}}, r"\['pattern'\] is outside")
    refused_schema({"s": {"type": "string", "$defs": {}}}, r"\['\$defs'\] is outside")
    refused_schema({}, r"\['title'\] is outside", title="t")
    refused_schema({"s": {"type": "string", "enum": []}}, "an `enum` needs one or more values of its own type")
    refused_schema({"xs": {"type": "array", "items": {"type": "string"}, "minItems": 2}}, "only `minItems: 1`")
    refused_schema({"xs": {"type": "array"}}, r"construct_schema.xs\[\]: not of one JSON type")
    refused_schema({"o": {"type": "object"}}, "an object schema needs")
    refused_schema({"o": {"type": "object", "properties": {}}}, "an object schema needs")
    refused_schema({"v": {"anyOf": [{"anyOf": [{"type": "string"}]}, {"type": "integer"}]}},
                   "an `anyOf` arm is itself an `anyOf`")
    refused_schema({"v": {"anyOf": [{"$ref": "#/$defs/U"}, {"type": "integer"}]}},
                   "an `anyOf` arm is itself an `anyOf`", defs={"U": {"anyOf": [{"type": "string"}]}})
    refused_schema({"v": {"anyOf": [{"$ref": "#/$defs/B"}, {"type": "integer"}]}},
                   r"\$defs\.B: not a schema", defs={"B": True})
    refused_schema({"v": {"anyOf": [{"$ref": "#/$defs/Nope"}, {"type": "integer"}]}},   # the arm walked first
                   r"names no `\$defs` entry")
    class Ints(TypedDict):
        n: int
    refused(declaring("G", {"n": {"type": "integer", "enum": [1]}}, Ints, required=["n"]),    # an `enum` is a `Literal`'s
            r"an `enum` of \[1\] against <class 'int'>")
    refused_schema({"s": {"$ref": "#/$defs/Statement", "pattern": "x"}}, r"\['pattern'\] is outside",
                   defs=STATEMENT)
    for kind, match in [({"enum": ["g"], "const": "g"}, "both `enum` and `const`"),
                        ({"const": "g", "type": "integer"}, "a `type` other than `string`"),
                        ({"const": "g", "pattern": "g"}, "`properties.kind` carries")]:
        schema = leaf_schema(["g"]); schema["properties"]["kind"] = kind
        refused(leaf("G", ["g"], construct_schema=schema), match)
    fine = leaf_schema(["g"]); fine["properties"]["kind"] = {"const": "g", "type": "string", "description": "the kind"}
    plugin.TAT_node(leaf("G", ["g"], construct_schema=fine))


def test_a_ref_names_an_own_def_in_the_one_form_judged_at_registration():
    """PLUGIN_SYSTEM §5: every `$ref` outside the top-level `children` has
    the form `#/$defs/<Name>` and names a key of the class's own `$defs`
    — inside an own entry too; a `$ref` to another class lives under
    `children` alone."""
    refused(declaring("P", {"s": {"$ref": "#/$defs/Nowhere"}}, S_RawAST, required=["s"]),
            r"names no `\$defs` entry")
    wrap = {"Wrap": {"type": "array", "items": {"$ref": "#/$defs/Nowhere"}}}
    refused(declaring("P2", {"s": {"$ref": "#/$defs/Wrap"}}, S_RawAST, required=["s"], defs=wrap),
            r"names no `\$defs` entry")
    refused(declaring("Q", {"s": {"$ref": "https://example.org/s"}}, S_RawAST, required=["s"]),
            "not of the form")
    plugin.TAT_node(Thm)
    class Holds_Thm(TypedDict):
        inner: Thm_Statement
    refused(declaring("U", {"inner": {"$ref": "#/$defs/Thm"}}, Holds_Thm, required=["inner"]),
            r"names no `\$defs` entry")


def test_every_def_is_reached_by_a_ref_of_the_schema():
    """PLUGIN_SYSTEM §5: a `$defs` entry no `$ref` reaches, directly or
    through other entries, is refused by the construct schema's walk,
    naming the key; one reached only through another entry is admitted."""
    class Holds_Statement(TypedDict):
        s: Thm_Statement

    class Outer_TD(TypedDict):
        inner: Thm_Statement

    class Holds_Outer(TypedDict):
        s: Outer_TD
    unused = {**STATEMENT, "Unused": {"type": "string"}}
    refused(declaring("P", {"s": {"$ref": "#/$defs/Statement"}}, Holds_Statement, required=["s"], defs=unused),
            r"`\$defs` entry `Unused` is reached by no `\$ref` outside the top-level `children`")
    outer = {"Outer": {"type": "object", "properties": {"inner": {"$ref": "#/$defs/Statement"}},
                       "required": ["inner"], "additionalProperties": False}, **STATEMENT}
    plugin.TAT_node(declaring("Q", {"s": {"$ref": "#/$defs/Outer"}}, Holds_Outer, required=["s"], defs=outer))
    loop = {"Loop": {"type": "object", "properties": {"next": {"$ref": "#/$defs/Loop"}}, "additionalProperties": False}}
    refused(declaring("R", {}, Empty, defs=loop), r"`\$defs` entry `Loop` is reached by no `\$ref`")   # reaching itself alone
    # the natural mistake: an own entry pointed at by `children` alone, which the agreement sets aside
    refused(block("Own_Children", {"type": "array", "items": {"$ref": "#/$defs/Statement"}}, defs=STATEMENT),
            r"`\$defs` entry `Statement` is reached by no `\$ref` outside the top-level `children`")


def test_recursion_happens_only_at_children():
    """PLUGIN_SYSTEM §3, §5: a TypedDict that nests itself is refused, at
    module level as inside a function; so is a `$defs` entry a `$ref`
    reaches that refers back to itself, directly or through other entries;
    a bare `$ref` entry is refused."""
    tree = {"Tree": {"type": "object", "additionalProperties": False,
                     "properties": {"sub": {"type": "array", "items": {"$ref": "#/$defs/Tree"}}}}}
    class Forest_RawAST(TypedDict):
        more: NotRequired[list[Tree_RawAST]]
    refused(declaring("U", {"more": {"type": "array", "items": {"$ref": "#/$defs/Tree"}}},
                      Forest_RawAST, defs=tree), "Tree_RawAST nests itself; recursion happens only at `children`")
    class Strings(TypedDict):
        more: list[str]
    loop = {"Loop": {"type": "array", "items": {"$ref": "#/$defs/Loop"}}}
    refused(declaring("V", {"more": {"$ref": "#/$defs/Loop"}}, Strings, required=["more"], defs=loop),
            r"`\$defs` entry `Loop` refers back to itself; recursion happens only at `children`")
    two_step = {"A": {"type": "array", "items": {"$ref": "#/$defs/B"}},
                "B": {"anyOf": [{"$ref": "#/$defs/A"}, {"type": "string"}]}}
    refused(declaring("V2", {"more": {"$ref": "#/$defs/A"}}, Strings, required=["more"], defs=two_step),
            r"`\$defs` entry `A` refers back to itself")
    bare = {"Alias": {"$ref": "#/$defs/Statement"}, **STATEMENT}
    refused(declaring("V3", {"more": {"$ref": "#/$defs/Alias"}}, Strings, required=["more"], defs=bare),
            r"`\$defs` entry `Alias` is a bare `\$ref`")
    class Local_Tree(TypedDict):
        sub: NotRequired[list["Local_Tree"]]
    class Local_Forest(TypedDict):
        more: NotRequired[list[Local_Tree]]
    refused(declaring("W", {"more": {"type": "array", "items": {"$ref": "#/$defs/Tree"}}},
                      Local_Forest, defs=tree), "unresolvable annotation")


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


class Uses_C(TypedDict):          # the own entry reached by a field, so that assembly judges its name
    c: str


def test_own_defs_may_not_take_construct_or_a_class_name():
    r = plugin.TAT_node(leaf("R", ["r"], argument_schema=Uses_C, construct_schema=leaf_schema(
        ["r"], {"c": {"$ref": "#/$defs/Construct"}}, required=["c"], defs={"Construct": {"type": "string"}})))
    refused_at_assembly(r, "reserved name `Construct`")


def test_own_defs_may_not_take_another_class_name():
    plugin.TAT_node(Thm)
    s = plugin.TAT_node(leaf("S", ["s"], argument_schema=Uses_C, construct_schema=leaf_schema(
        ["s"], {"c": {"$ref": "#/$defs/Thm"}}, required=["c"], defs={"Thm": {"type": "string"}})))
    refused_at_assembly(s, "reserved name `Thm`")


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


def test_a_construct_of_every_shipped_kind_validates(monkeypatch):
    monkeypatch.setattr(M, "FRAMEWORK_NODE_CLASSES", SHIPPED)
    for cls in SHIPPED:
        plugin.TAT_node(cls)
    assert set(SHIPPED_EXAMPLES) == {k for kinds in plugin.registry.values() for k in kinds}
    if SHIPPED:
        validator = jsonschema.Draft202012Validator(plugin.edit_schema(SHIPPED))
        for kind, construct in SHIPPED_EXAMPLES.items():
            assert construct["kind"] == kind
            validator.validate(envelope(construct))


def test_given_later_inlined_marks_children_and_inlines_every_ref():
    """PLUGIN_SYSTEM §4: each class's top-level `children` takes
    `GivenLater` alone, its description kept; every `$ref` is inlined, the
    site's keys over the entry's, the entries' own descriptions kept; a
    field named `children` inside an entry is an ordinary field."""
    schema = {"type": "object", "properties": {"constructs": {"type": "array", "items": {"$ref": "#/$defs/Construct"}}},
              "$defs": {
                  "A": {"type": "object", "properties": {
                      "kind": {"const": "a"},
                      "children": {"type": "array", "items": {"$ref": "#/$defs/Construct"}, "description": "A's parts"},
                      "syntax": {"$ref": "#/$defs/M", "description": "site"}}},
                  "B": {"type": "object", "properties": {
                      "kind": {"const": "b"},
                      "children": {"type": "array", "items": {"$ref": "#/$defs/A"}}}},
                  "M": {"description": "M's own", "anyOf": [{"$ref": "#/$defs/X", "description": "arm"},
                                                            {"type": "string"}]},
                  "X": {"type": "object", "properties": {"y": {"$ref": "#/$defs/Y"}, "children": {"type": "string"}}},
                  "Y": {"type": "string", "description": "Y's own"},
                  "Construct": {"anyOf": [{"$ref": "#/$defs/A"}, {"$ref": "#/$defs/B"}]}}}
    a = {"type": "object", "properties": {
        "kind": {"const": "a"},
        "children": {"type": "string", "enum": ["GivenLater"], "description": "A's parts"},
        "syntax": {"description": "site", "anyOf": [
            {"type": "object", "description": "arm",
             "properties": {"y": {"type": "string", "description": "Y's own"}, "children": {"type": "string"}}},
            {"type": "string"}]}}}
    b = {"type": "object", "properties": {"kind": {"const": "b"},
                                          "children": {"type": "string", "enum": ["GivenLater"]}}}
    before = json.dumps(schema)
    assert plugin.given_later_inlined(schema) == {
        "type": "object", "properties": {"constructs": {"type": "array", "items": {"anyOf": [a, b]}}}}
    assert json.dumps(schema) == before                # the argument untouched
    plain = {"type": "object", "properties": {"s": {"type": "string"}}}
    assert plugin.given_later_inlined(plain) is plain


# The classes TAT's package registers, loaded before the fixture above
# empties the registry for each test: their `edit` schema and their table.
STD_LOADED = plugin.load(["isabelle_theory_agent.std"])
STD_EDIT_SCHEMA = STD_LOADED.edit_schema


def test_the_view_without_recursion_admits_what_the_server_accepts():
    """PLUGIN_SYSTEM §4: over the classes TAT ships, the view holds no
    `$ref` and no `$defs`, is a well-formed schema, admits every example and
    every example of a class declaring `children` with `GivenLater` there,
    and refuses nested children; it stays far under the bound Codex is
    given (CLIENT_HOOKS.md §3)."""
    from test_common import EXAMPLES
    view = plugin.given_later_inlined(STD_EDIT_SCHEMA)
    text = json.dumps(view, separators=(",", ":"))
    assert "$ref" not in text and "$defs" not in text
    jsonschema.Draft202012Validator.check_schema(view)
    assert len(text.encode()) < CODEX_SCHEMA_MAX_BYTES // 10
    validator = jsonschema.Draft202012Validator(view)
    nested = SHIPPED_EXAMPLES["theory"]
    for example in [*SHIPPED_EXAMPLES.values(), *EXAMPLES.values()]:
        bare = {k: v for k, v in example.items() if k != "children"}
        validator.validate(envelope(bare))
        if "children" in STD_LOADED.kinds[example["kind"]].construct_schema["properties"]:   # the classes declaring it
            validator.validate(envelope({**bare, "children": plugin.GIVEN_LATER}))
            assert not validator.is_valid(envelope({**bare, "children": [nested]}))
        else:
            assert not validator.is_valid(envelope({**bare, "children": plugin.GIVEN_LATER}))


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
            "    placement = model.Placement(within='Sec', through=())\n"
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
    monkeypatch.setattr(M, "FRAMEWORK_NODE_CLASSES", [Sec])
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
    assert list(loaded.kinds) == ["section", "good"] and [c.__name__ for c in registered()] == ["Sec", "Good"]


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
