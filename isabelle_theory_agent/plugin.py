"""Loading node classes (PLUGIN_SYSTEM.md): registration under `@TAT_node`,
the table from `kind` to class that `edit` dispatches on, the `$defs` that
complete the `edit` tool's schema at start, the one checker — of a tool
call's arguments and of a submitted construct, each against its schema
(MODULE_STRUCTURE §4.4) — and the argument schema grammar, what a class's
TypedDict may declare.

Importing a plugin's package is what registers its classes, into the
process-wide `registry`; `load` imports every package `launch_TAT`
received, after the framework's own classes, and selects this
conversation's kind table from the registry (MODULE_STRUCTURE §4.4), so a
second conversation in the process registers nothing again.  Every check
failure is a `CannotLoadPlugin` (EXCEPTIONS.md §1): a plugin's bug fails
the conversation start.
"""

from __future__ import annotations

import copy
import importlib
import inspect
import re
import sys
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import UnionType
from typing import (
    Annotated, Any, Literal, NamedTuple, NotRequired, Required, TypeAlias, TypeVar, Union, get_args,
    get_origin, get_type_hints, is_typeddict)

import jsoncomment
import jsonschema

from . import model
from .jobs import Construction_Job, Evaluation_Job
from .exceptions import (
    InvalidField, MissingField, RawASTError, TAT_InternalError, TAT_StartupError,
    UnexpectedField)
from .model import (NON_EMPTY, Forest, JSON_Schema, Leaf, Node, NonLeaf_Node, Placement, StdBlock,
                    Unchained_Node, is_valid_name)
from .store import CONSTRUCT_FRAMEWORK_FIELDS, FRAMEWORK_FIELDS


class CannotLoadPlugin(TAT_StartupError):
    """A package would not import, or a node class failed a check of
    PLUGIN_SYSTEM §5; `node_class` is None when no class is named."""

    def __init__(self, package: str | None, node_class: str | None, reason: str):
        where = (f"{package}.{node_class}" if node_class
                 else package or "the assembled edit schema")
        super().__init__(f"cannot load {where}: {reason}")
        self.package = package
        self.node_class = node_class
        self.reason = reason


# The process-wide registry (PLUGIN_SYSTEM §1): every class registered in
# this process, in registration order, with the kinds its construct schema
# names.  A conversation's kind table is a selection from it, in this
# order — the order agent-facing lists of kinds render in (EXCEPTIONS.md
# §3, `UnknownKind`) and the order of the `Construct` union.
registry: dict[type[Node], list[str]] = {}

CONSTRUCT = "Construct"                        # the union's reserved `$defs` name
GIVEN_LATER = "GivenLater"                     # `children` given in later calls (MCP_SPECIFICATION §3.1)
_REF = re.compile(r"^#/\$defs/([^/]+)$")
_EDIT_SCHEMA = Path(__file__).parent / "tools" / "edit.jsonc"


_N = TypeVar("_N", bound=Node)


def TAT_node(cls: type[_N]) -> type[_N]:
    """Class decorator: check the class (PLUGIN_SYSTEM §5) and register it
    under every kind its construct schema names; the class comes back as
    itself, so that `isinstance` narrows to it."""
    registry[cls] = _check_class(cls)            # nothing is written before the checks pass
    return cls


# A compile hook (COMPILATION.md §5): a function of the forest root, which
# a compile runs after it has written its files.
Compile_Hook: TypeAlias = Callable[[Forest], None]

# The process-wide registry of compile hooks, in registration order
# (PLUGIN_SYSTEM §1), each once; like `registry`, it holds a hook exactly
# while the module defining it is in `sys.modules`.
compile_hooks: dict[Compile_Hook, None] = {}


def TAT_compile_hook(hook: Compile_Hook) -> Compile_Hook:
    """Function decorator: check the hook (PLUGIN_SYSTEM §5) — a plain
    function of one positional argument, neither a coroutine nor a
    generator, either of which a call would make and never run — and
    register it."""
    def refuse(reason: str) -> CannotLoadPlugin:
        return CannotLoadPlugin(getattr(hook, "__module__", None),
                                getattr(hook, "__name__", repr(hook)), reason)
    if not inspect.isfunction(hook):
        raise refuse("a compile hook is a plain function")
    if inspect.iscoroutinefunction(hook):
        raise refuse("a compile hook is not a coroutine; a compile is synchronous")
    if inspect.isgeneratorfunction(hook) or inspect.isasyncgenfunction(hook):
        raise refuse("a compile hook is not a generator")
    parameters = list(inspect.signature(hook).parameters.values())
    if len(parameters) != 1 or parameters[0].kind not in (
            inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
        raise refuse("a compile hook takes one positional argument, the forest root")
    compile_hooks[hook] = None
    return hook


# The theories the plugins declare the forest's theories import besides
# what the agent wrote (PLUGIN_SYSTEM §1), each to the module declaring
# it; like `registry`, kept while that module is in `sys.modules`.
imports: dict[str, str] = {}


def TAT_import(theory: str) -> None:
    """Module-level call: declare a theory the forest's theories import, in
    the `imports` field's qualified shape, `<session>.<short name>`
    (PLUGIN_SYSTEM §1; node_classes/SESSION_AND_THEORY.md §2)."""
    module = sys._getframe(1).f_globals.get("__name__")
    if "." not in theory or not model.is_theory_name_item(theory):
        raise CannotLoadPlugin(module, None, f"`{theory}` is not a theory name of the shape `<session>.<short name>`")
    imports[theory] = str(module)


@dataclass(frozen=True)
class Loaded:
    """What `load` hands the conversation, or the compile: its kind table —
    what `edit` dispatches on and `Forest` rebuilds nodes with — the `edit`
    tool's schema with its `$defs` filled in from the table's classes
    (PLUGIN_SYSTEM §4), and the compile hooks the listed packages define,
    in registration order."""
    kinds: dict[str, type[Node]]
    edit_schema: JSON_Schema
    compile_hooks: tuple[Compile_Hook, ...] = ()
    # the job classes the loaded classes name, each once, by title: what the
    # construct tools' existence and descriptions follow (CONSTRUCT_INTERACTION §3.1, §5)
    construction_job_classes: tuple[type[Construction_Job], ...] = ()
    evaluation_job_classes: tuple[type[Evaluation_Job], ...] = ()
    imports: tuple[str, ...] = ()             # the theories the listed packages declare (PLUGIN_SYSTEM §1)


def load(python_packages: list[str]) -> Loaded:
    """Register the framework's classes unless an earlier load did, import
    every package — importing registers, and a package the process holds
    already registers nothing again — then select this conversation's
    classes: the framework's, and those defined in a listed package or a
    module under it."""
    # a module a failed import dropped from sys.modules re-executes below;
    # what it registered before it failed goes with it
    for cls in [c for c in registry if c.__module__ not in sys.modules]:
        del registry[cls]
    for hook in [h for h in compile_hooks if h.__module__ not in sys.modules]:
        del compile_hooks[hook]
    for theory in [t for t, module in imports.items() if module not in sys.modules]:
        del imports[theory]
    for cls in model.FRAMEWORK_NODE_CLASSES:
        if cls not in registry:
            TAT_node(cls)
    for package in python_packages:
        try:
            importlib.import_module(package)
        except CannotLoadPlugin:
            raise
        except Exception as e:              # missing, or failing before any class registers
            raise CannotLoadPlugin(package, None, f"{type(e).__name__}: {e}") from e
    classes = [cls for cls in registry
               if cls in model.FRAMEWORK_NODE_CLASSES or _defined_in(cls, python_packages)]
    _check_placements(classes)
    return Loaded({kind: cls for cls in classes for kind in registry[cls]}, edit_schema(classes),
                  tuple(h for h in compile_hooks if _defined_in(h, python_packages)),
                  _job_classes(classes, lambda cls: cls.construction_job_class),
                  _job_classes(classes, lambda cls: cls.evaluation_job_class),
                  tuple(t for t, module in imports.items() if _module_in(module, python_packages)))


def _check_placements(classes: list[type[Node]]) -> None:
    """The names of each class's `placement` (PLUGIN_SYSTEM §5), judgeable
    only once every package is imported: each a class of the
    conversation's, `within` one outside `Unchained_Node` answering to one
    kind."""
    by_name = {cls.__name__: cls for cls in classes}
    for cls in classes:
        placement = cls.placement
        if placement is None:
            continue
        for name in (placement.within, *placement.through):
            if name not in by_name:
                raise _refuse(cls, f"`placement` names `{name}`, which is not a node class of the conversation")
        within = by_name[placement.within]
        if issubclass(within, Unchained_Node):
            raise _refuse(cls, f"`placement.within` names `{placement.within}`, which runs no operation")
        if len(registry[within]) != 1:
            raise _refuse(cls, f"`placement.within` names `{placement.within}`, which answers to several kinds")


def _job_classes(classes: list[type[Node]], named_by: Callable[[type[Node]], Any]) -> tuple[Any, ...]:
    """The job classes the node classes name, `named_by` reading the name
    off a class, each once, in the alphabetical order of their titles."""
    named = {job_class for cls in classes if (job_class := named_by(cls)) is not None}
    return tuple(sorted(named, key=lambda job_class: job_class.title()))


def _defined_in(defined: type | Compile_Hook, packages: list[str]) -> bool:
    """Whether a class or a hook belongs to one of `packages`."""
    return _module_in(defined.__module__, packages)


def _module_in(module: str, packages: list[str]) -> bool:
    """Whether `module` is one of `packages` or lies under one."""
    return any(module == p or module.startswith(p + ".") for p in packages)


# `edit`'s `auto_construct`, there when a loaded class names a construction
# job class (TOOL_SCHEMAS §1)
AUTO_CONSTRUCT_PROPERTY: JSON_Schema = {
    "type": "boolean",
    "description": "True turns the new nodes' automatic construction on; false leaves it off. Default: false."}


def edit_schema(classes: list[type[Node]]) -> JSON_Schema:
    """The `edit` tool's schema with its `$defs` filled in from `classes`
    (PLUGIN_SYSTEM §4), checked whole."""
    schema = jsoncomment.JsonComment().loads(_EDIT_SCHEMA.read_text())
    schema["$defs"] = assemble(classes)
    if any(cls.construction_job_class is not None for cls in classes):
        schema["properties"]["auto_construct"] = AUTO_CONSTRUCT_PROPERTY
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.SchemaError as e:
        raise CannotLoadPlugin(None, None, f"not well-formed: {e.message}") from e
    return schema


# --- registration checks ---------------------------------------------------

def _refuse(cls: type, reason: str) -> CannotLoadPlugin:
    return CannotLoadPlugin(cls.__module__, cls.__name__, reason)


def _kinds_of(cls: type[Node]) -> list[str]:
    """The kinds `properties.kind` names, as an `enum` or a `const`, not
    both, with nothing else but `type` — `string` when present — and
    `description` (PLUGIN_SYSTEM §5)."""
    kind = _properties(cls).get("kind")
    if kind is None:
        raise _refuse(cls, "construct_schema has no `properties.kind`")
    if not isinstance(kind, dict):
        raise _refuse(cls, "`properties.kind` is not an object")
    if "enum" in kind and "const" in kind:
        raise _refuse(cls, "`properties.kind` has both `enum` and `const`")
    if "enum" in kind:
        values = kind["enum"]
    elif "const" in kind:
        values = [kind["const"]]
    else:
        raise _refuse(cls, "`properties.kind` has neither `enum` nor `const`")
    if not values or not all(isinstance(v, str) for v in values):
        raise _refuse(cls, "`properties.kind` must name one or more strings")
    extra = set(kind) - {"enum", "const", "type", "description"}
    if extra:
        raise _refuse(cls, f"`properties.kind` carries {sorted(extra)}")
    if kind.get("type", "string") != "string":
        raise _refuse(cls, "`properties.kind` is of a `type` other than `string`")
    return values


def _properties(cls: type[Node]) -> dict[str, Any]:     # unchecked plugin input
    assert cls.construct_schema is not None
    return cls.construct_schema.get("properties", {})


def _check_class(cls: type[Node]) -> list[str]:
    """Every registration check of PLUGIN_SYSTEM §5; returns the kinds the
    class answers to, so registration cannot happen without the checks."""
    schema = cls.construct_schema
    if not isinstance(schema, dict):
        raise _refuse(cls, "construct_schema must be a dict holding the construct's JSON schema")
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.SchemaError as e:
        raise _refuse(cls, f"construct_schema is not a well-formed JSON schema: {e.message}") from e
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise _refuse(cls, "construct_schema must be an object schema with"
                           " `additionalProperties: false`")
    required = schema.get("required", [])
    own_kinds = _kinds_of(cls)
    for kind in own_kinds:
        if not is_valid_name(kind):
            # the kind heads every id component `<kind>_<name>` (MCP_SPECIFICATION §2)
            raise _refuse(cls, f"kind `{kind}` is outside the name grammar")
        for other, other_kinds in registry.items():
            if kind in other_kinds:
                raise _refuse(cls, f"kind `{kind}` is already registered by {other.__name__}")
    if "kind" not in required:
        raise _refuse(cls, "`kind` must be in `required`")
    if any(c.__name__ == cls.__name__ for c in registry):
        raise _refuse(cls, "another node class has this name")
    properties = _properties(cls)
    for field in properties:                # such a class would fail at its first store
        if field in FRAMEWORK_FIELDS and field not in CONSTRUCT_FRAMEWORK_FIELDS:
            raise _refuse(cls, f"declares the field `{field}`, the name of a row the framework stores")
    if "children" in properties:
        if issubclass(cls, Leaf):
            raise _refuse(cls, "a Leaf declares no `children`")
        if not _is_construct_array(properties["children"]):
            raise _refuse(cls, "`children` must be an array of `#/$defs/<Name>` `$ref`s")
        if set(properties["children"]) - {"type", "items", "description"}:
            raise _refuse(cls, "`children` carries a keyword besides `type`, `items` and `description`")
        if "children" in required:      # no construct must carry it, and an amend's may not
            raise _refuse(cls, "`children` is never required")
    if cls.output_omissible and not cls.input_omissible:
        # TAT would print an id it then refuses to accept (MCP_SPECIFICATION §2.1).
        raise _refuse(cls, "omissible on output but compulsory on input")
    if _defined_by(cls, "is_finished") is not Node:
        raise _refuse(cls, "overrides `is_finished`; `_unfinished` is the override point")
    _check_job_class(cls)
    for member in ("_operations_ready", "job_operation_status"):
        if _defined_by(cls, member) is not Node:
            raise _refuse(cls, f"overrides `{member}`, which is the framework's")
    if _defined_by(cls, "_own_statuses") not in (Leaf, StdBlock, Unchained_Node):
        raise _refuse(cls, "overrides `_own_statuses`; a node's operations are its base class's")
    if issubclass(cls, Unchained_Node):                 # one of the three bases, by the check above
        if cls not in model.FRAMEWORK_NODE_CLASSES:
            raise _refuse(cls, "derives from `Unchained_Node`, which only the framework's classes do")
    elif cls.job_operation not in cls._operation_names():
        raise _refuse(cls, f"`job_operation` is {cls.job_operation!r}, not an operation of the class:"
                           f" {', '.join(repr(name) for name in cls._operation_names())}")
    if cls not in model.FRAMEWORK_NODE_CLASSES:
        if not isinstance(cls.placement, Placement):
            raise _refuse(cls, "declares no `placement`")
        if _defined_by(cls, "_evaluate") not in (Leaf, StdBlock):
            raise _refuse(cls, "overrides `_evaluate`, which is the framework's")
    if _defined_by(cls, "print") is not Node:
        raise _refuse(cls, "overrides `print`; `print_fields`, `children_header`, `owing_line` and `mark` are the override points")
    if _defined_by(cls, "_children_to_print") not in (Node, NonLeaf_Node):
        raise _refuse(cls, "overrides `_children_to_print`; the descent is the framework's")
    # nodes live in sets, and in lists compared with `==` (PRINT.md §2, `Forest.id_of`)
    if cls.__hash__ is not object.__hash__ or cls.__eq__ is not object.__eq__:
        raise _refuse(cls, "defines `__eq__` or `__hash__`; a node is equal to, and hashed as, itself alone")
    if issubclass(cls, StdBlock):
        if _defined_by(cls, "emit") is not StdBlock:
            # the children are the framework's to place (COMPILATION.md §3)
            raise _refuse(cls, "overrides `emit`; `emit_beginning` and `emit_ending` are the"
                               " override points")
        if (_defined_by(cls, "_eval_ending_opr") is StdBlock) != (_defined_by(cls, "emit_ending") is StdBlock):
            raise _refuse(cls, "overrides one of `_eval_ending_opr` and `emit_ending` without the"
                               " other; both say whether the class has an ending command")
    _check_coroutines(cls)
    for method in ("gen", "to_store", "from_store"):
        if _defined_by(cls, method) is Node:
            raise _refuse(cls, f"does not override `{method}`")
    try:
        validate_argument_schema(cls.argument_schema)
    except TAT_InternalError as e:
        raise _refuse(cls, f"argument_schema: {e}") from e
    _validate_construct_schema(cls)
    agreement = _Agreement(cls, schema.get("$defs", {}))
    agreement.object(schema, cls.argument_schema, "construct_schema", top=True)
    return own_kinds


def _check_job_class(cls: type[Node]) -> None:
    """The job classes a node class names (PLUGIN_SYSTEM §2, §5): each a
    subclass of its base with every abstract member implemented,
    overriding none of the framework's — the base's members marked
    `typing.final` — and each override a coroutine exactly when the
    member it overrides is."""
    for attribute, base in (("construction_job_class", Construction_Job),
                            ("evaluation_job_class", Evaluation_Job)):
        job_class = getattr(cls, attribute)
        if job_class is None:
            continue
        if not (isinstance(job_class, type) and issubclass(job_class, base)):
            raise _refuse(cls, f"`{attribute}` is not a subclass of `{base.__name__}`")
        if inspect.isabstract(job_class):
            missing = ", ".join(f"`{name}`" for name in sorted(job_class.__abstractmethods__))
            raise _refuse(cls, f"{job_class.__name__} does not implement {missing}")
        for member, framework in vars(base).items():
            if getattr(framework, "__final__", False) and _defined_by(job_class, member) is not base:
                raise _refuse(cls, f"{job_class.__name__} overrides `{member}`, which is the framework's")
            override = _function(getattr(job_class, member, None))
            if (callable(framework) and override is not None
                    and inspect.iscoroutinefunction(override) != inspect.iscoroutinefunction(_function(framework))):
                raise _refuse(cls, f"{job_class.__name__}.{member} is a coroutine exactly when the"
                                   " member it overrides is not")


def _check_coroutines(cls: type[Node]) -> None:
    """An override is a coroutine function exactly when the method it
    overrides is (PLUGIN_SYSTEM §5): rendering, emission and the event
    hooks are synchronous, the evaluation hooks and `gen` are coroutines.
    An `async def can_emit` would answer with a coroutine object, which
    is true."""
    mro = cls.__mro__
    for i, c in enumerate(mro):
        for name, own in c.__dict__.items():
            overridden = next((b.__dict__[name] for b in mro[i + 1:] if name in b.__dict__), None)
            f, g = _function(own), _function(overridden)
            if f is None or g is None:
                continue
            if inspect.iscoroutinefunction(f) and not inspect.iscoroutinefunction(g):
                raise _refuse(cls, f"`{name}` is a coroutine; the method it overrides is not")
            if inspect.iscoroutinefunction(g) and not inspect.iscoroutinefunction(f):
                raise _refuse(cls, f"`{name}` is not a coroutine; the method it overrides is")


def _function(attribute: Any) -> Any:
    """The function behind a class attribute — a plain function, or a
    classmethod's or a staticmethod's — or None for anything else."""
    if isinstance(attribute, (classmethod, staticmethod)):
        attribute = attribute.__func__
    return attribute if inspect.isfunction(attribute) else None


def _defined_by(cls: type, name: str) -> type:
    """The class in `cls`'s MRO whose body defines `name` — read off the
    class dicts, since a classmethod binds afresh on every access.  Each
    override check compares it with the framework class that defines the
    method: `Node` for most; `NonLeaf_Node` too for `_children_to_print`;
    `StdBlock` for `emit`, `_eval_ending_opr` and `emit_ending`; `Leaf`,
    `StdBlock` and `Unchained_Node` for `_own_statuses`.  A framework class
    a check does not name must not define that method itself, or the check
    goes blind for its subclasses."""
    return next(c for c in cls.__mro__ if name in c.__dict__)


def _is_construct_array(prop: Any) -> bool:
    """`{"type": "array", "items": X}` with X a `$ref` of the form
    `#/$defs/<Name>`, or an `anyOf` of such, each with at most a
    `description` beside it (PLUGIN_SYSTEM §5)."""
    if not isinstance(prop, dict) or prop.get("type") != "array" or "items" not in prop:
        return False
    items = prop["items"]
    if isinstance(items, dict) and "anyOf" in items:
        return set(items) <= {"anyOf", "description"} and all(_is_def_ref(i) for i in items["anyOf"])
    return _is_def_ref(items)


def _is_def_ref(x: Any) -> bool:
    return (isinstance(x, dict) and set(x) <= {"$ref", "description"}
            and isinstance(x.get("$ref"), str) and bool(_REF.match(x["$ref"])))


# --- the JSON types -----------------------------------------------------------
# What a value of each is in Python, and the phrase RENDER_BASELINES §2
# approves for it: the one vocabulary `check_call` renders in.

class _JSON_Type(NamedTuple):
    shape: type | tuple[type, ...]
    phrase: str

_NULL = type(None)

_JSON_TYPES = {"string": _JSON_Type(str, "a string"), "boolean": _JSON_Type(bool, "a boolean"),
               # a Python int: a JSON `1.0` is refused, since the same table types `gen`'s raw
               "integer": _JSON_Type(int, "an integer"), "number": _JSON_Type((int, float), "a number"),
               "array": _JSON_Type(list, "a list"), "object": _JSON_Type(Mapping, "an object"),
               # JSON null: an arm of a construct schema's `anyOf` alone (PLUGIN_SYSTEM §5), which the
               # `anyOf` walk admits itself — not in `_KEYWORDS`, so a bare `{"type": "null"}` is refused
               "null": _JSON_Type(_NULL, "null")}


def _fits(value: Any, json_type: str) -> bool:
    if isinstance(value, bool):            # a flag is not a number
        return json_type == "boolean"
    return isinstance(value, _JSON_TYPES[json_type].shape)


def _within_integer_range(value: Any) -> bool:
    """An integer — under `integer` or `number` — within `INTEGER_RANGE`;
    any other value passes."""
    return not isinstance(value, int) or INTEGER_RANGE[0] <= value <= INTEGER_RANGE[1]


# By the JSON type of the value, the keywords a schema may carry there
# besides `type` and `description`, each enforced by `check_call` — in a
# tool's schema and a construct's alike: `additionalProperties` by
# construction (it refuses an argument the `properties` do not name,
# always), which is why `_validate_node` demands the word be `false` —
# `true` would advertise a freedom the check does not grant.  A boolean has
# no `enum`: its values would render as Python's.
_KEYWORDS = {"string": {"enum"}, "boolean": set(), "integer": {"enum"}, "number": {"enum"},
             "array": {"items", "minItems"},
             "object": {"properties", "required", "additionalProperties"}}


def _validate_node(schema: Any, top: bool, grammar: str, refuse: Callable[[str], Exception]) -> str:
    """The rules a schema of one JSON type keeps in either grammar, the
    tool's or the construct's — what `check_call` reads unguarded: a type
    of `_KEYWORDS`; no keyword besides `type`, `description`, the type's
    own and `$defs` at the top; only `minItems: 1`; an `enum` of one or
    more values of the type; an object with `properties`,
    `additionalProperties: false` and a `required` within them.  Answers
    the JSON type; `refuse` makes the caller's exception from a reason."""
    json_type = schema.get("type") if isinstance(schema, dict) else None
    if not isinstance(json_type, str) or json_type not in _KEYWORDS:   # a well-formed `type` may be a list
        raise refuse(f"not of one JSON type of the {grammar} grammar")
    extra = set(schema) - {"type", "description", *_KEYWORDS[json_type]} - ({"$defs"} if top else set())
    if extra:
        raise refuse(f"{sorted(extra)} is outside the {grammar} grammar")
    if schema.get("minItems", 1) != 1:
        raise refuse("only `minItems: 1` has a sentence")
    if "enum" in schema and not (schema["enum"] and all(_fits(v, json_type) for v in schema["enum"])):
        raise refuse("an `enum` needs one or more values of its own type")
    if json_type == "object" and (schema.get("additionalProperties") is not False
                                  or not isinstance(schema.get("properties"), dict)
                                  or not set(schema.get("required", ())) <= set(schema["properties"])):
        raise refuse("an object schema needs `properties`, `additionalProperties: false`"
                     " and a `required` within its properties")
    return json_type


# --- the argument schema grammar (MODULE_STRUCTURE §4.4) ----------------------
# `str`, `bool`, `int`, `float`, `Literal[...]` of strings, `list[X]`, a
# non-empty list `Annotated[list[X], NON_EMPTY]`, a TypedDict, and unions of
# `str`, `bool`, `int`, `float`, `list[X]`, TypedDicts and `None` — no two of
# one JSON type (`int` and `float` both numbers), but TypedDicts told apart by
# one `Literal` field — each field
# optionally wrapped in `NotRequired[X]` or `Required[X]`.  Closed, so that
# every construct schema the agreement below admits is one `check_call`
# enforces and its sentences can say.  Validated once, at registration; a
# submitted construct is checked against the class's construct schema, not
# the declaration (`check_call`, MODULE_STRUCTURE §4.2).

_JSON_NAMES = {str: "string", bool: "boolean", int: "integer", float: "number"}   # the scalars


def _declared(td: Any) -> tuple[dict[str, Any], frozenset[str]]:
    """A TypedDict's fields — each annotation with its `Required` or
    `NotRequired` wrapper removed — and which of them are required.  The
    wrappers are read here rather than trusted to `__required_keys__`,
    which under postponed annotations (`from __future__ import
    annotations`) cannot see them and calls every key required."""
    hints = get_type_hints(td, include_extras=True)
    required = set()
    fields = {}
    for field, ann in hints.items():
        wrapper = get_origin(ann)
        if wrapper is Required or wrapper is NotRequired:
            fields[field] = get_args(ann)[0]
        else:
            fields[field] = ann
        if wrapper is Required or (wrapper is not NotRequired
                                   and field in td.__required_keys__):
            required.add(field)
    return fields, frozenset(required)


def validate_argument_schema(td: Any) -> None:
    """Refuse a declaration outside the grammar — loudly, at registration,
    where the class's author sees it (PLUGIN_SYSTEM §5).  A TypedDict is
    compulsory: an empty one for a class with no fields."""
    _validate_typeddict(td, top=True, enclosing=())


def _validate_typeddict(td: Any, top: bool, enclosing: tuple) -> None:
    if not is_typeddict(td):
        raise TAT_InternalError(f"argument schema {td!r} is not a TypedDict")
    if td in enclosing:                    # being validated above
        raise TAT_InternalError(f"{td.__name__} nests itself; recursion happens only at `children`")
    try:
        hints, _ = _declared(td)
    except NameError as e:
        raise TAT_InternalError(f"{td.__name__}: unresolvable annotation") from e
    if top and "children" in hints:
        raise TAT_InternalError(
            "`children` belongs to the framework, not an argument schema")
    for field, ann in hints.items():
        if top and field == "kind":        # the framework's; declared only
            continue                       # for the static checker
        _validate_annotation(ann, f"{td.__name__}.{field}", enclosing + (td,))


def _validate_annotation(ann: Any, where: str, enclosing: tuple) -> None:
    if ann in _JSON_NAMES:
        return
    if get_origin(ann) is Literal:
        if not get_args(ann) or not all(isinstance(v, str) for v in get_args(ann)):
            raise TAT_InternalError(f"{where}: a `Literal` is of one or more strings")
        return
    if (item := _list_item(ann)) is not None:
        _validate_annotation(item[0], where, enclosing)
        return
    if is_typeddict(ann):
        _validate_typeddict(ann, top=False, enclosing=enclosing)
        return
    if get_origin(ann) in (Union, UnionType):
        _validate_union(get_args(ann), where, enclosing)
        return
    raise TAT_InternalError(
        f"{where}: {ann!r} is outside the argument schema grammar")


def _validate_union(arms: tuple, where: str, enclosing: tuple) -> None:
    """A union's arms, no two of one JSON type but TypedDicts told apart by
    `_choosing_field`; `None`, JSON null, is an arm and nothing else.  A
    `Literal` and a non-empty list are never arms: their refusals speak
    for the whole field, and would be false where another arm accepts what
    they refuse."""
    for arm in arms:
        if get_origin(arm) is Literal or (_list_item(arm) or (None, False))[1]:
            raise TAT_InternalError(f"{where}: a `Literal` or a non-empty list is never an arm")
        if arm is not _NULL:
            _validate_annotation(arm, where, enclosing)
    types = [_arm_type(_json_type(arm)) for arm in arms]
    if any(types.count(t) > 1 for t in types if t != "object"):
        raise TAT_InternalError(f"{where}: two arms of one JSON type could not be told apart")
    if types.count("object") > 1:
        _choosing_field([arm for arm in arms if is_typeddict(arm)], where)


def _choosing_field(tds: list[Any], where: str) -> str:
    """The one field required in every TypedDict and a `Literal` in each,
    its values disjoint between them: what tells the arms apart, on both
    sides of the agreement."""
    declared = [_declared(td) for td in tds]
    candidates = [f for f in declared[0][0]
                  if all(f in required and get_origin(hints.get(f)) is Literal
                         for hints, required in declared)]
    if len(candidates) != 1:
        raise TAT_InternalError(f"{where}: TypedDict arms are told apart by one and the same"
                                " required `Literal` field")
    (field,) = candidates
    values = [get_args(hints[field]) for hints, _ in declared]
    if len({v for vs in values for v in vs}) != sum(len(vs) for vs in values):
        raise TAT_InternalError(f"{where}: the arms' `{field}` values are not disjoint")
    return field


def _list_item(ann: Any) -> tuple[Any, bool] | None:
    """`(X, non_empty)` for `list[X]` or `Annotated[list[X], NON_EMPTY]`;
    None for anything else."""
    non_empty = False
    if get_origin(ann) is Annotated:
        inner, *marks = get_args(ann)
        if marks != [NON_EMPTY]:
            return None
        ann, non_empty = inner, True
    if get_origin(ann) is list and len(get_args(ann)) == 1:
        return get_args(ann)[0], non_empty
    return None


def _arm_type(json_type: str) -> str:
    """The JSON type by which a union's arms are told apart: an integer is
    a number, so `int` and `float` are both numbers."""
    return "number" if json_type == "integer" else json_type


def _json_type(ann: Any) -> str:
    """The JSON type of an annotation of the grammar, `None`'s — an arm of
    a union alone — `null`."""
    if ann is _NULL:
        return "null"
    if ann in _JSON_NAMES:
        return _JSON_NAMES[ann]
    if get_origin(ann) is Literal:
        return "string"
    if _list_item(ann) is not None:
        return "array"
    if is_typeddict(ann):
        return "object"
    raise TAT_InternalError(f"{ann!r} is outside the argument schema grammar")


# --- the construct schema's own rules, and the agreement (PLUGIN_SYSTEM §5) ----

def _validate_construct_schema(cls: type[Node]) -> None:
    """The construct schema on its own (PLUGIN_SYSTEM §5): `$defs` keys
    identifiers, every entry a schema and none a bare `$ref`; every `$ref`
    outside the top-level `children` of the form `#/$defs/<Name>` naming
    an own entry; no `anyOf` arm, its `$ref` followed, an `anyOf`;
    `{"type": "null"}`, JSON null, an arm of an `anyOf` and nothing else;
    no keyword besides the grammar's, `description`, and `$defs` at the
    top alone; every entry reached by a `$ref` outside the top-level
    `children`, and none reaching itself — recursion happens only at
    `children`.  `kind` and `children` have rules of their own
    (`_kinds_of`, `_check_class`)."""
    schema = cls.construct_schema
    assert schema is not None
    defs = schema.get("$defs", {})
    for name, entry in defs.items():
        if not name.isidentifier():
            raise _refuse(cls, f"`$defs` key `{name}` is not a Python identifier")
        if not isinstance(entry, dict):
            raise _refuse(cls, f"$defs.{name}: not a schema")
        if "$ref" in entry:
            raise _refuse(cls, f"`$defs` entry `{name}` is a bare `$ref`")

    def allowed(s: dict, keywords: set[str], where: str) -> None:
        extra = set(s) - keywords - {"description"}
        if extra:
            raise _refuse(cls, f"{where}: {sorted(extra)} is outside the construct schema grammar")

    reached: set[str] = set()
    path: list[str] = []                    # the entries being walked, outermost first

    def walk(s: Any, where: str, top: bool = False) -> None:
        if isinstance(s, dict) and "$ref" in s:
            allowed(s, {"$ref"}, where)
            m = _REF.match(s["$ref"]) if isinstance(s["$ref"], str) else None
            if m is None:
                raise _refuse(cls, f"`$ref` `{s['$ref']}` is not of the form `#/$defs/<Name>`")
            name = m.group(1)
            if name not in defs:
                raise _refuse(cls, f"`$ref` `{s['$ref']}` names no `$defs` entry of the class")
            if name in path:
                raise _refuse(cls, f"`$defs` entry `{name}` refers back to itself;"
                                   " recursion happens only at `children`")
            if name not in reached:
                reached.add(name)
                path.append(name)
                walk(defs[name], f"$defs.{name}")
                path.pop()
            return
        if isinstance(s, dict) and "anyOf" in s:
            allowed(s, {"anyOf"}, where)
            for i, arm in enumerate(s["anyOf"]):
                if isinstance(arm, dict) and arm.get("type") == "null":     # JSON null: an arm of an `anyOf`, and nothing else
                    allowed(arm, {"type"}, f"{where}<{i}>")
                    continue
                walk(arm, f"{where}<{i}>")             # a schema, its `$ref` naming an own entry
                if "anyOf" in _resolved(arm, defs):
                    raise _refuse(cls, f"{where}: an `anyOf` arm is itself an `anyOf`")
            return
        json_type = _validate_node(s, top, "construct schema", lambda what: _refuse(cls, f"{where}: {what}"))
        if json_type == "object":
            for field, property in s["properties"].items():
                if not (top and field in CONSTRUCT_FRAMEWORK_FIELDS):
                    walk(property, f"{where}.{field}")
        elif json_type == "array":
            walk(s.get("items"), f"{where}[]")

    walk(schema, "construct_schema", top=True)
    unreached = sorted(set(defs) - reached)
    if unreached:
        raise _refuse(cls, f"`$defs` entry `{unreached[0]}` is reached by no `$ref` outside the"
                           " top-level `children`")


def _required_enum_fields(arms: list[JSON_Schema]) -> list[str]:
    """The fields every object arm requires and declares with an `enum`, in
    the first arm's order — the schema side of `_choosing_field`: one field
    when the arms are told apart."""
    return [f for f in arms[0]["properties"]
            if all(f in arm.get("required", ()) and "enum" in arm["properties"].get(f, {}) for arm in arms)]


@dataclass(frozen=True)
class _Agreement:
    """The two schemas held to each other at every depth (PLUGIN_SYSTEM §5),
    a `$ref` followed into `$defs`; neither side recurses, so the walk
    ends.  Values, fields and arms are compared as sets, never by
    position: typing's cache hands one union's arms, or one `Literal`'s
    values, to an equal one written in another order."""
    cls: type[Node]
    defs: Mapping[str, Any]

    def disagree(self, where: str, what: str) -> CannotLoadPlugin:
        return _refuse(self.cls, f"construct_schema and argument_schema disagree at `{where}`: {what}")

    def agree(self, schema: JSON_Schema, ann: Any, where: str) -> None:
        if "$ref" in schema:
            schema = self.defs[_def_name(schema["$ref"])]
        if "anyOf" in schema:
            self.union(schema["anyOf"], ann, where)
            return
        json_type = schema["type"]
        if json_type == "object":
            if not is_typeddict(ann):
                raise self.disagree(where, f"an object against {ann!r}")
            self.object(schema, ann, where, top=False)
        elif json_type == "array":
            item = _list_item(ann)
            if item is None:
                raise self.disagree(where, f"an array against {ann!r}")
            if ("minItems" in schema) != item[1]:
                raise self.disagree(where, "`minItems: 1` is `Annotated[list[X], NON_EMPTY]`, and only that")
            self.agree(schema["items"], item[0], where + "[]")
        elif "enum" in schema:                 # a `Literal` of the grammar is of strings: a non-string `enum` disagrees
            if get_origin(ann) is not Literal or set(get_args(ann)) != set(schema["enum"]):
                raise self.disagree(where, f"an `enum` of {schema['enum']} against {ann!r}")
        elif json_type == "null":              # reached as a union's arm alone
            if ann is not _NULL:
                raise self.disagree(where, f"null against {ann!r}")
        elif _JSON_NAMES.get(ann) != json_type:
            raise self.disagree(where, f"{_JSON_TYPES[json_type].phrase} against {ann!r}")

    def object(self, schema: JSON_Schema, td: Any, where: str, top: bool) -> None:
        """`properties` are the TypedDict's keys and `required` its required
        keys — at the top, `kind` and `children` set aside on the schema's
        side and `kind` on the TypedDict's — and each field agrees."""
        hints, required = _declared(td)
        aside_schema = set(CONSTRUCT_FRAMEWORK_FIELDS) if top else set()
        aside_td = {"kind"} if top else set()
        fields, typed = set(schema["properties"]) - aside_schema, set(hints) - aside_td
        if fields != typed:
            raise self.disagree(where, f"the fields {sorted(fields)} against {sorted(typed)}")
        needs, typed_needs = set(schema.get("required", ())) - aside_schema, required - aside_td
        if needs != typed_needs:
            raise self.disagree(where, f"the required fields {sorted(needs)} against {sorted(typed_needs)}")
        for field, property in schema["properties"].items():
            if field not in aside_schema:
                self.agree(property, hints[field], f"{where}.{field}")

    def union(self, arms: list[JSON_Schema], ann: Any, where: str) -> None:
        """The `anyOf`'s arms and the union's pair one for one: by JSON
        type, as many of each on both sides, and objects by the values of
        the choosing field."""
        if get_origin(ann) not in (Union, UnionType):
            raise self.disagree(where, f"an `anyOf` against {ann!r}")
        by_type: dict[str, list[JSON_Schema]] = {}
        for arm in arms:
            by_type.setdefault(_arm_type(_resolved(arm, self.defs)["type"]), []).append(arm)
        typed_by_type: dict[str, list[Any]] = {}
        for typed in get_args(ann):
            typed_by_type.setdefault(_arm_type(_json_type(typed)), []).append(typed)
        if set(by_type) != set(typed_by_type):
            raise self.disagree(where, f"the `anyOf`'s JSON types {sorted(by_type)} against the"
                                       f" union's {sorted(typed_by_type)}")
        for json_type, schema_arms in by_type.items():
            typed_arms = typed_by_type[json_type]
            if len(schema_arms) != len(typed_arms):
                raise self.disagree(where, f"{len(schema_arms)} `anyOf` arms of JSON type {json_type}"
                                           f" against {len(typed_arms)} of the union's")
            if len(schema_arms) == 1:
                self.agree(schema_arms[0], typed_arms[0], f"{where}<{json_type}>")
            else:
                self.told_apart(schema_arms, typed_arms, where)

    def told_apart(self, arms: list[JSON_Schema], typed_arms: list[Any], where: str) -> None:
        """Objects among objects: the one field every arm requires with an
        `enum` is the TypedDicts' choosing field, and the arms' value sets
        are the TypedDicts' `Literal` value sets, one for one."""
        field = _choosing_field(typed_arms, where)
        resolved = [_resolved(arm, self.defs) for arm in arms]
        choosing = _required_enum_fields(resolved)
        if choosing != [field]:
            raise self.disagree(where, f"the `anyOf`'s objects are told apart by {choosing},"
                                       f" the union's TypedDicts by `{field}`")
        by_values = {frozenset(get_args(_declared(td)[0][field])): td for td in typed_arms}
        arm_values = [frozenset(r["properties"][field]["enum"]) for r in resolved]
        if Counter(arm_values) != Counter(by_values.keys()):
            shown = [sorted(map(str, values)) for values in arm_values]
            raise self.disagree(where, f"the `anyOf` arms' `{field}` values {sorted(shown)} against the"
                                       f" union's {sorted(sorted(values) for values in by_values)}")
        for arm, values in zip(arms, arm_values):
            self.agree(arm, by_values[values], f"{where}<{field}={'|'.join(sorted(values))}>")


# --- the check (MODULE_STRUCTURE §4.4) ------------------------------------------
# One checker: of a tool call's own arguments against the very schema the
# tool advertises (TOOL_SCHEMAS.md §4), and of each submitted construct
# against its class's construct schema, so that what the agent is told and
# what it is held to are one object.  Its sentences stay within
# RENDER_BASELINES §2's vocabulary — the JSON types' phrases, `must be one
# of`, `must not be empty`, the nesting bound — each held once here.

NESTING_LEVELS = 100      # a tool call's argument nests no deeper, each object or array a level
INTEGER_RANGE = (-2**63, 2**63 - 1)   # a JSON integer lies within it: the signed 64-bit range, which
                                      # MessagePack holds on the wire and in the store


def check_call(schema: JSON_Schema, holder: str, arguments: Mapping[str, Any], *,
               construct: bool = False) -> None:
    """A tool call's own arguments against the schema the tool advertises
    — one `validate_call_schema` has passed, whose keywords the check
    therefore reads unguarded —, the holder the tool's name: an argument
    nested deeper than `NESTING_LEVELS` refused before anything else, and
    every refusal marked the call's on its way out, so that its sentence
    says tool and argument (EXCEPTIONS.md §3).  Or, with `construct`, a
    submitted construct against its class's construct schema, handed by
    `edit.py` (§4.2), the holder the kind: `kind` passed over unread — the
    kind table chose the class from it —, `kind` and `children` left out
    of what the kind "takes", nothing marked."""
    check = _Check(schema.get("$defs", {}) if construct else {}, construct)
    if construct:
        check.object(schema, holder, arguments, prefix="")
        return
    try:
        for argument, value in arguments.items():
            if _nested_deeper_than(value, NESTING_LEVELS):
                raise InvalidField(argument, f"must not be nested deeper than {NESTING_LEVELS} levels")
        check.object(schema, holder, arguments, prefix="")
    except RawASTError as e:
        e._mark_of_tool()
        raise


def _nested_deeper_than(value: Any, levels: int) -> bool:
    """Whether an object or array lies more than `levels` levels down in
    `value`, each object or array a level; the descent stops there, so no
    depth of input exhausts the stack."""
    if not isinstance(value, (Mapping, list)):
        return False
    if levels == 0:
        return True
    members = value.values() if isinstance(value, Mapping) else value
    return any(_nested_deeper_than(m, levels - 1) for m in members)


@dataclass(frozen=True)
class _Check:
    """One check's standing knowledge: the `$defs` its `$ref`s are followed
    into — a construct schema's own; a tool's none, since a tool's one
    `$ref` names the constructs, which are edit.py's — and whether the
    top-level object is a construct."""
    defs: Mapping[str, Any]
    construct: bool

    def holds_constructs(self, items: JSON_Schema) -> bool:
        """Whether an `items` names `Construct` or a node class: a `$ref`,
        or an `anyOf` of `$ref`s, the check holds no definition for — no
        `$defs` entry of a class bears their names (PLUGIN_SYSTEM §5)."""
        arms = items["anyOf"] if "anyOf" in items else [items]
        return all("$ref" in arm and _def_name(arm["$ref"]) not in self.defs for arm in arms)

    def object(self, schema: JSON_Schema, holder: str, mapping: Mapping[str, Any], prefix: str) -> None:
        """An object's fields against its `properties`: the names, then each
        value; at a construct's top, `kind` passed over."""
        properties = schema["properties"]
        top = self.construct and not prefix
        _check_names(properties, schema.get("required", ()), holder, mapping, prefix,
                     unlisted=CONSTRUCT_FRAMEWORK_FIELDS if top else ())
        for field, value in mapping.items():
            if top and field == "kind":
                continue
            self.value(value, properties[field], holder, prefix + field)

    def value(self, value: Any, schema: JSON_Schema, holder: str, path: str) -> None:
        """One value against its schema — its JSON type, an integer's
        range, its `enum`, an empty list against `minItems` — descending so that the field
        reported is the innermost at fault: an object's field by its name,
        a typed `items`' element by its index, an `anyOf` by the arm the
        value is for.  The constructs are opaque here, `edit.py`'s to
        check."""
        schema = _resolved(schema, self.defs)
        if "anyOf" in schema:
            schema = self.arm(value, [_resolved(arm, self.defs) for arm in schema["anyOf"]], holder, path)
        json_type = schema["type"]
        if not _fits(value, json_type):
            raise InvalidField(path, _must_be([json_type]))
        if not _within_integer_range(value):
            raise InvalidField(path, "must be a 64-bit integer")
        if "enum" in schema and value not in schema["enum"]:
            raise InvalidField(path, _one_of(schema["enum"]))
        if "minItems" in schema and not value:
            raise InvalidField(path, "must not be empty")
        if json_type == "object" and not _is_bare_object(schema):     # a bare object is "an object", no more
            self.object(schema, holder, value, path + ".")
        elif json_type == "array" and not self.holds_constructs(schema["items"]):
            for i, v in enumerate(value):
                self.value(v, schema["items"], holder, f"{path}[{i}]")

    def arm(self, value: Any, arms: list[JSON_Schema], holder: str, path: str) -> JSON_Schema:
        """The arm of an `anyOf` the value is checked against: by its JSON
        type — of no arm's, `must be` the arms' distinct types, each once,
        in the schema's order; among objects told apart by a required
        `enum` field, the one every arm requires with an `enum`: a field
        none of them declares first, `UnexpectedField` over all their
        fields in the order they first appear, then the choosing field
        missing, then its value outside every arm, `must be one of` all
        their values."""
        fitting = [arm for arm in arms if _fits(value, arm["type"])]
        if not fitting:
            raise InvalidField(path, _must_be([arm["type"] for arm in arms]))
        if len(fitting) == 1:
            return fitting[0]
        declared = list(dict.fromkeys(field for arm in fitting for field in arm["properties"]))
        _check_names(declared, (), holder, value, path + ".")
        choosing, = _required_enum_fields(fitting)
        if choosing not in value:
            raise MissingField(holder, f"{path}.{choosing}")
        for arm in fitting:
            if value[choosing] in arm["properties"][choosing]["enum"]:
                return arm
        raise InvalidField(f"{path}.{choosing}",
                           _one_of([v for arm in fitting for v in arm["properties"][choosing]["enum"]]))


def _check_names(declared: Collection[str], required: Collection[str], holder: str,
                 mapping: Mapping[str, Any], prefix: str, unlisted: Collection[str] = ()) -> None:
    """The names a mapping carries against those declared for it: one the
    declaration does not name first — a typo beats its own hole — then a
    required one missing, in declaration order.  `unlisted` are the
    declared fields the holder does not "take" (RENDER_BASELINES §2)."""
    for field in mapping:
        if field not in declared:
            raise UnexpectedField(prefix[:-1] if prefix else holder, field,
                                  [f for f in declared if f not in unlisted], holder_is_top=not prefix)
    for field in declared:
        if field in required and field not in mapping:
            raise MissingField(holder, prefix + field)


def _def_name(ref: str) -> str:
    """`<Name>` of a `$ref` `#/$defs/<Name>`, the one form the loader admits."""
    return ref.removeprefix("#/$defs/")


def _resolved(schema: JSON_Schema, defs: Mapping[str, Any]) -> JSON_Schema:
    """`schema`, its `$ref` followed one step into `defs`."""
    return defs[_def_name(schema["$ref"])] if "$ref" in schema else schema


def _must_be(json_types: Iterable[str]) -> str:
    """`must be` the types' phrases, each once, in the order given, joined by `or`."""
    return "must be " + " or ".join(dict.fromkeys(_JSON_TYPES[t].phrase for t in json_types))


def _one_of(values: Iterable[Any]) -> str:
    return "must be one of " + ", ".join(f"`{v}`" for v in values)


# --- the tool schema grammar (TOOL_SCHEMAS.md §4) ------------------------------
# `_KEYWORDS` is the whole of what a tool's schema may say — closed like the
# argument schema grammar above, so that every rendering stays within
# RENDER_BASELINES §2's vocabulary; `validate_call_schema` refuses a schema
# saying anything more.
_CONSTRUCTS = {"$ref": f"#/$defs/{CONSTRUCT}"}   # `items` the check leaves to `edit.py`


def validate_call_schema(schema: JSON_Schema, where: str) -> None:
    """Refuse a tool schema saying anything `check_call` does not enforce,
    or its sentences cannot say, or too little for the check to read —
    where the tools are built (MODULE_STRUCTURE §4.6), so that what the
    agent is told and what it is held to cannot drift apart.  `where`
    names the schema in the refusal."""
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.SchemaError as e:
        raise TAT_InternalError(f"{where}: not a well-formed JSON schema: {e.message}") from e
    _validate_schema(schema, where, top=True)


# The one property the grammar admits as a bare `object` (MODULE_STRUCTURE
# §4.4): the tool's name and the property's.
_BARE_OBJECTS = {("answer", "answer")}


def _validate_schema(schema: Any, where: str, top: bool) -> None:
    def refuse(what: str) -> TAT_InternalError:
        return TAT_InternalError(f"{where}: {what}")
    json_type = _validate_node(schema, top, "tool schema", refuse)
    if top and json_type != "object":
        raise refuse("a tool takes an object of arguments")
    if json_type == "array" and schema.get("items") != _CONSTRUCTS:
        _validate_schema(schema.get("items"), where + "[]", top=False)
    if json_type == "object":
        for field, property in schema["properties"].items():
            if top and (where, field) in _BARE_OBJECTS and _is_bare_object(property):
                continue
            _validate_schema(property, f"{where}.{field}", top=False)


def _is_bare_object(schema: Any) -> bool:
    """`{"type": "object"}` with at most a `description`."""
    return isinstance(schema, dict) and schema.get("type") == "object" and set(schema) <= {"type", "description"}


# --- assembly ----------------------------------------------------------------

def assemble(classes: list[type[Node]]) -> dict[str, JSON_Schema]:
    """The `$defs` of the `edit` schema (PLUGIN_SYSTEM §4): each class under
    its name, less its own `$defs`, which are merged at the top level; then
    `Construct`, the union of the classes.  References are kept, never
    inlined."""
    names = {c.__name__ for c in classes}
    reserved = names | {CONSTRUCT}
    defs: dict[str, JSON_Schema] = {}
    shared: dict[str, tuple[type, Any]] = {}
    for cls in classes:
        # A deep copy: the assembled schema shares nothing with the class's
        # declaration, so neither can be changed through the other.
        assert cls.construct_schema is not None      # registration checked it
        schema = copy.deepcopy(cls.construct_schema)
        own = schema.pop("$defs", {})
        for name in own:
            if name in reserved:
                raise _refuse(cls, f"`$defs` uses the reserved name `{name}`")
        for ref in _refs(schema.get("properties", {}).get("children")):
            if _def_name(ref) not in reserved:                       # only judgeable now
                raise _refuse(cls, f"`children` must be an array of `$ref`s to `{CONSTRUCT}`"
                                   f" or to node classes, not to `{ref}`")
        for name, definition in own.items():
            if name in shared and shared[name][1] != definition:
                raise _refuse(cls, f"defines `$defs` `{name}` differently from"
                                   f" {shared[name][0].__name__}")
            shared.setdefault(name, (cls, definition))
        defs[cls.__name__] = schema
    for name, (_, definition) in shared.items():
        defs[name] = definition
    defs[CONSTRUCT] = {"anyOf": [{"$ref": f"#/$defs/{c.__name__}"} for c in classes]}
    return defs


def _refs(x: Any) -> list[str]:
    """Every `$ref` value under `x`, in document order."""
    if isinstance(x, dict):
        return ([x["$ref"]] if isinstance(x.get("$ref"), str) else []) + [
            r for v in x.values() for r in _refs(v)]
    if isinstance(x, list):
        return [r for v in x for r in _refs(v)]
    return []


def given_later_inlined(schema: JSON_Schema) -> JSON_Schema:
    """`schema` as a client that cannot take recursion is shown it
    (PLUGIN_SYSTEM §4): the top-level `children` of every class in
    `Construct` takes `GIVEN_LATER` alone, its description kept, and every
    `$ref` is inlined, the site's own keys over the entry; then no cycle is
    left (PLUGIN_SYSTEM §3).  A schema without `$defs` is returned as is."""
    if "$defs" not in schema:
        return schema
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs")
    for arm in defs[CONSTRUCT]["anyOf"]:
        properties = defs[_def_name(arm["$ref"])]["properties"]
        if "children" in properties:
            children = properties["children"]
            del children["items"]
            children.update(type="string", enum=[GIVEN_LATER])

    def inline(x: Any) -> Any:
        if isinstance(x, dict):
            if "$ref" in x:
                site = {k: v for k, v in x.items() if k != "$ref"}
                return {**inline(defs[_def_name(x["$ref"])]), **site}
            return {k: inline(v) for k, v in x.items()}
        if isinstance(x, list):
            return [inline(v) for v in x]
        return x
    return inline(schema)
