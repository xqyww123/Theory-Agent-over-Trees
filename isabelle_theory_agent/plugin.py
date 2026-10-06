"""Loading node classes (PLUGIN_SYSTEM.md): registration under `@TAT_node`,
the table from `kind` to class that `edit` dispatches on, the `$defs` that
complete the `edit` tool's schema at start, and the argument schema grammar
— what a class's TypedDict may declare, and how a submitted construct is
checked against it.

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
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import UnionType
from typing import (
    Any, NamedTuple, NotRequired, Required, TypeAlias, Union, get_args, get_origin,
    get_type_hints, is_typeddict)

import jsoncomment
import jsonschema

from . import model
from .jobs import Construction_Job, Evaluation_Job
from .exceptions import (
    InvalidField, MissingField, RawASTError, TAT_InternalError, TAT_StartupError,
    UnexpectedField)
from .model import (Forest, JSON_Schema, Leaf, Node, NonLeaf_Node, RawAST, StdBlock,
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
_REF = re.compile(r"^#/\$defs/([^/]+)$")
_EDIT_SCHEMA = Path(__file__).parent / "tools" / "edit.jsonc"


def TAT_node(cls: type[Node]) -> type[Node]:
    """Class decorator: check the class (PLUGIN_SYSTEM §5) and register it
    under every kind its construct schema names."""
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
    return Loaded({kind: cls for cls in classes for kind in registry[cls]}, edit_schema(classes),
                  tuple(h for h in compile_hooks if _defined_in(h, python_packages)))


def _defined_in(defined: type | Compile_Hook, packages: list[str]) -> bool:
    """Whether a class or a hook belongs to one of `packages`: its module
    is the package or lies under it."""
    module = defined.__module__
    return any(module == p or module.startswith(p + ".") for p in packages)


def edit_schema(classes: list[type[Node]]) -> JSON_Schema:
    """The `edit` tool's schema with its `$defs` filled in from `classes`
    (PLUGIN_SYSTEM §4), checked whole."""
    schema = jsoncomment.JsonComment().loads(_EDIT_SCHEMA.read_text())
    schema["$defs"] = assemble(classes)
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.SchemaError as e:
        raise CannotLoadPlugin(None, None, f"not well-formed: {e.message}") from e
    return schema


# --- registration checks ---------------------------------------------------

def _refuse(cls: type, reason: str) -> CannotLoadPlugin:
    return CannotLoadPlugin(cls.__module__, cls.__name__, reason)


def _kinds_of(cls: type[Node]) -> list[str]:
    """The kinds `properties.kind` names, as an `enum` or a `const`."""
    kind = _properties(cls).get("kind")
    if kind is None:
        raise _refuse(cls, "construct_schema has no `properties.kind`")
    if not isinstance(kind, dict):
        raise _refuse(cls, "`properties.kind` is not an object")
    if "enum" in kind:
        values = kind["enum"]
    elif "const" in kind:
        values = [kind["const"]]
    else:
        raise _refuse(cls, "`properties.kind` has neither `enum` nor `const`")
    if not values or not all(isinstance(v, str) for v in values):
        raise _refuse(cls, "`properties.kind` must name one or more strings")
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
    if cls.output_omissible and not cls.input_omissible:
        # TAT would print an id it then refuses to accept (MCP_SPECIFICATION §2.1).
        raise _refuse(cls, "omissible on output but compulsory on input")
    if _defined_by(cls, "is_finished") is not Node:
        raise _refuse(cls, "overrides `is_finished`; `_unfinished` is the override point")
    _check_job_class(cls)
    if _defined_by(cls, "_operations_ready") is not Node:
        raise _refuse(cls, "overrides `_operations_ready`, which is the framework's")
    if _defined_by(cls, "_own_statuses") not in (Leaf, StdBlock, Unchained_Node):
        raise _refuse(cls, "overrides `_own_statuses`; a node's operations are its base class's")
    if _defined_by(cls, "print") is not Node:
        raise _refuse(cls, "overrides `print`; `print_fields` and `mark` are the override points")
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
    hints, typed_required = _declared(cls.argument_schema)
    schema_fields = set(properties) - set(CONSTRUCT_FRAMEWORK_FIELDS)
    typed_fields = set(hints) - {"kind"}
    if schema_fields != typed_fields:
        raise _refuse(cls, f"construct_schema declares the fields {sorted(schema_fields)},"
                           f" argument_schema the fields {sorted(typed_fields)}")
    schema_required = set(required) - set(CONSTRUCT_FRAMEWORK_FIELDS)
    typed_required = typed_required - {"kind"}
    if schema_required != typed_required:
        raise _refuse(cls, f"construct_schema requires {sorted(schema_required)},"
                           f" argument_schema requires {sorted(typed_required)}")
    return own_kinds


def _check_job_class(cls: type[Node]) -> None:
    """The job classes a node class names (PLUGIN_SYSTEM §2, §5): each a
    subclass of its base with every abstract member implemented,
    overriding none of the framework's."""
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
        for member in base.FRAMEWORK_MEMBERS:
            if _defined_by(job_class, member) is not base:
                raise _refuse(cls, f"{job_class.__name__} overrides `{member}`, which is the framework's")


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
    if not isinstance(prop, dict) or prop.get("type") != "array" or "items" not in prop:
        return False
    items = prop["items"]
    if isinstance(items, dict) and "anyOf" in items:
        return all(_is_def_ref(i) for i in items["anyOf"])
    return _is_def_ref(items)


def _is_def_ref(x: Any) -> bool:
    return isinstance(x, dict) and isinstance(x.get("$ref"), str) and bool(_REF.match(x["$ref"]))


# --- the JSON types -----------------------------------------------------------
# What a value of each is in Python, and the phrase RENDER_BASELINES §2
# approves for it: the one vocabulary the two checkers below render in.

class _JSON_Type(NamedTuple):
    shape: type | tuple[type, ...]
    phrase: str

_JSON_TYPES = {"string": _JSON_Type(str, "a string"), "boolean": _JSON_Type(bool, "a boolean"),
               # a Python int: a JSON `1.0` is refused, since the same table types `gen`'s raw
               "integer": _JSON_Type(int, "an integer"), "number": _JSON_Type((int, float), "a number"),
               "array": _JSON_Type(list, "a list"), "object": _JSON_Type(Mapping, "an object")}


def _fits(value: Any, json_type: str) -> bool:
    if isinstance(value, bool):            # a flag is not a number
        return json_type == "boolean"
    return isinstance(value, _JSON_TYPES[json_type].shape)


# --- the argument schema grammar --------------------------------------------
# `str`, `bool`, `int`, `float`, `Any`, `list[X]`, a TypedDict, and unions of
# those holding at most one TypedDict, each field optionally wrapped in
# `NotRequired[X]` or `Required[X]` — closed, so every rendering stays
# within RENDER_BASELINES §2's vocabulary.  Validated once, at registration;
# then every submitted construct is checked against the declaration before
# its class's `gen` is consulted (MODULE_STRUCTURE §4.2).

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
    if td in enclosing:
        raise TAT_InternalError(f"{td.__name__} nests itself")
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
    if ann is Any or ann in _JSON_NAMES:
        return
    if is_typeddict(ann):
        _validate_typeddict(ann, top=False, enclosing=enclosing)
        return
    origin = get_origin(ann)
    if origin is list and len(get_args(ann)) == 1:
        _validate_annotation(get_args(ann)[0], where, enclosing)
        return
    if origin in (Union, UnionType):
        arms = get_args(ann)
        if any(a is Any for a in arms):
            raise TAT_InternalError(f"{where}: `Any` makes the other arms moot")
        if int in arms and float in arms:
            raise TAT_InternalError(f"{where}: `float` makes `int` moot")
        if sum(_holds_object(a) for a in arms) > 1:
            raise TAT_InternalError(
                f"{where}: a union may reach one TypedDict")
        for a in arms:
            _validate_annotation(a, where, enclosing)
        return
    raise TAT_InternalError(
        f"{where}: {ann!r} is outside the argument schema grammar")


def _holds_object(ann: Any) -> bool:
    """Whether an annotation reaches a TypedDict — directly, through lists,
    or through a union inside them; two such arms in one union could not
    be told apart."""
    while get_origin(ann) is list:
        ann = get_args(ann)[0]
    if get_origin(ann) in (Union, UnionType):
        return any(_holds_object(a) for a in get_args(ann))
    return is_typeddict(ann)


def _matches(value: Any, ann: Any) -> bool:
    """Whether a JSON value fits a field annotation of the grammar; a
    TypedDict is matched as an object here, its fields by `_check_value`."""
    if ann is Any:
        return True
    if is_typeddict(ann):
        return isinstance(value, Mapping)
    origin = get_origin(ann)
    if origin is list:
        return isinstance(value, list) and all(
            _matches(v, get_args(ann)[0]) for v in value)
    if origin in (Union, UnionType):
        return any(_matches(value, a) for a in get_args(ann))
    if ann not in _JSON_NAMES:
        raise TAT_InternalError(f"{ann!r} is outside the argument schema grammar")
    return _fits(value, _JSON_NAMES[ann])


def _json_name(ann: Any) -> str:
    """The approved rendering of a type (RENDER_BASELINES §2)."""
    if is_typeddict(ann):
        return _JSON_TYPES["object"].phrase
    if get_origin(ann) is list:
        return _JSON_TYPES["array"].phrase
    if get_origin(ann) in (Union, UnionType):
        names = []
        for a in get_args(ann):
            if _json_name(a) not in names:
                names.append(_json_name(a))
        return " or ".join(names)
    if ann not in _JSON_NAMES:
        raise TAT_InternalError(f"{ann!r} is outside the argument schema grammar")
    return _JSON_TYPES[_JSON_NAMES[ann]].phrase


def check_fields(cls: type[Node], kind: str, raw: RawAST) -> None:
    """The mechanical shape of a submitted construct, before its class is
    consulted: no field the class does not declare, required fields
    present, types right — against the class's `argument_schema`."""
    _check_fields(cls.argument_schema, kind, raw, prefix="", framework=CONSTRUCT_FRAMEWORK_FIELDS)


def _check_names(declared: Collection[str], required: Collection[str], holder: str,
                 mapping: Mapping[str, Any], prefix: str, framework: Collection[str] = ()) -> None:
    """The names a mapping carries against those declared for it, for both
    checkers: one the declaration does not name first — a typo beats its
    own hole — then a required one missing, in declaration order.
    `framework` are the framework's own fields, which pass unread and
    which the holder does not "take" (RENDER_BASELINES.md §2)."""
    for field in mapping:
        if field not in framework and field not in declared:
            raise UnexpectedField(prefix[:-1] if prefix else holder, field,
                                  [f for f in declared if f not in framework],
                                  holder_is_top=not prefix)
    for field in declared:
        if field in required and field not in mapping:
            raise MissingField(holder, prefix + field)


def _check_fields(td: Any, holder: str, mapping: Mapping[str, Any], prefix: str,
                  framework: Collection[str] = ()) -> None:
    """`holder` is the kind; `framework` the fields of the framework's own
    that pass unread, `kind` and `children` at a construct's top level."""
    hints, required = _declared(td)
    _check_names(hints, required, holder, mapping, prefix, framework)
    for field, value in mapping.items():
        if field in framework:
            continue
        _check_value(value, hints[field], holder, prefix + field)


def _check_value(value: Any, ann: Any, holder: str, path: str) -> None:
    """One value against its annotation, descending so that the field
    reported is the innermost at fault: a list element by its index, a
    TypedDict's field by its name, a union by the arm the value fits."""
    if get_origin(ann) is list:
        if not isinstance(value, list):
            raise InvalidField(path, "must be a list")
        for i, v in enumerate(value):
            _check_value(v, get_args(ann)[0], holder, f"{path}[{i}]")
    elif get_origin(ann) in (Union, UnionType):
        arm = next((a for a in get_args(ann) if _matches(value, a)), None)
        if arm is None:
            raise InvalidField(path, f"must be {_json_name(ann)}")
        _check_value(value, arm, holder, path)
    elif is_typeddict(ann):
        if not isinstance(value, Mapping):
            raise InvalidField(path, "must be an object")
        _check_fields(ann, holder, value, path + ".")
    elif not _matches(value, ann):
        raise InvalidField(path, f"must be {_json_name(ann)}")


# --- a tool call's own arguments (TOOL_SCHEMAS.md §4) ------------------------
# Checked against the very schema the tool advertises, so what the agent is
# told and what it is held to are one object.  The keywords listed below are
# the whole of it — closed like the grammar above, so every rendering stays
# within RENDER_BASELINES §2's vocabulary; `validate_call_schema` refuses a
# schema saying anything more.

# By the JSON type of the value, the keywords a schema may carry there
# besides `type` and `description`, each enforced by `check_call`:
# `additionalProperties` by construction (it refuses an argument the
# `properties` do not name, always), which is why `_validate_schema` demands
# the word be `false` — `true` would advertise a freedom the check does not
# grant.  A boolean has no `enum`: its values would render as Python's.
_KEYWORDS = {"string": {"enum"}, "boolean": set(), "integer": {"enum"}, "number": {"enum"},
             "array": {"items", "minItems"},
             "object": {"properties", "required", "additionalProperties"}}
_CONSTRUCTS = {"$ref": f"#/$defs/{CONSTRUCT}"}   # `items` the check leaves to `edit.py`


def check_call(schema: JSON_Schema, tool: str, arguments: Mapping[str, Any]) -> None:
    """A tool call's own arguments against the schema the tool advertises
    — one `validate_call_schema` has passed, whose keywords the check
    therefore reads unguarded — as a construct's fields are checked
    against its class's declaration: the tool's name where the kind would
    be, and the refusal marked on its way out, so that its sentence says
    tool and argument (EXCEPTIONS.md §3)."""
    try:
        _check_arguments(schema, tool, arguments, prefix="")
    except RawASTError as e:
        e._mark_of_tool()
        raise


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


def _check_arguments(schema: JSON_Schema, tool: str, mapping: Mapping[str, Any],
                     prefix: str) -> None:
    properties = schema["properties"]
    _check_names(properties, schema.get("required", ()), tool, mapping, prefix)
    for field, value in mapping.items():
        _check_argument(value, properties[field], tool, prefix + field)


def _check_argument(value: Any, schema: JSON_Schema, tool: str, path: str) -> None:
    """One argument against its schema — its JSON type, its `enum`, an
    empty list against `minItems` — descending so that the argument
    reported is the innermost at fault: an object's field by its name, a
    typed `items`' element by its index.  The constructs are opaque here,
    `edit.py`'s to check."""
    json_type = schema["type"]
    if not _fits(value, json_type):
        raise InvalidField(path, f"must be {_JSON_TYPES[json_type].phrase}")
    if "enum" in schema and value not in schema["enum"]:
        raise InvalidField(path, "must be one of " + ", ".join(f"`{a}`" for a in schema["enum"]))
    if "minItems" in schema and not value:
        raise InvalidField(path, "must not be empty")
    if json_type == "object":
        _check_arguments(schema, tool, value, path + ".")
    elif json_type == "array" and schema["items"] != _CONSTRUCTS:
        for i, v in enumerate(value):
            _check_argument(v, schema["items"], tool, f"{path}[{i}]")


def _validate_schema(schema: Any, where: str, top: bool) -> None:
    def refuse(what: str) -> TAT_InternalError:
        return TAT_InternalError(f"{where}: {what}")
    json_type = schema.get("type") if isinstance(schema, dict) else None
    if not isinstance(json_type, str) or json_type not in _KEYWORDS:   # a well-formed `type` may be a list
        raise refuse("not of one JSON type of the tool schema grammar")
    if top and json_type != "object":
        raise refuse("a tool takes an object of arguments")
    extra = set(schema) - {"type", "description", *_KEYWORDS[json_type]} - ({"$defs"} if top else set())
    if extra:
        raise refuse(f"{sorted(extra)} is outside the tool schema grammar")
    if schema.get("minItems", 1) != 1:
        raise refuse("only `minItems: 1` has a sentence")
    if "enum" in schema and not (schema["enum"] and all(_fits(v, json_type) for v in schema["enum"])):
        raise refuse("an `enum` needs one or more values of its own type")
    if json_type == "array" and schema.get("items") != _CONSTRUCTS:
        _validate_schema(schema.get("items"), where + "[]", top=False)
    if json_type == "object":
        if (schema.get("additionalProperties") is not False
                or not isinstance(schema.get("properties"), dict)
                or not set(schema.get("required", ())) <= set(schema["properties"])):
            raise refuse("an object schema needs `properties`, `additionalProperties: false`"
                         " and a `required` within its properties")
        for field, property in schema["properties"].items():
            _validate_schema(property, f"{where}.{field}", top=False)


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
        under_children = set(_refs(schema.get("properties", {}).get("children")))
        for ref in _refs(schema) + _refs(own):
            m = _REF.match(ref)
            if m is None:
                raise _refuse(cls, f"`$ref` `{ref}` is not of the form `#/$defs/<Name>`")
            name = m.group(1)
            if name not in own and name not in reserved:
                raise _refuse(cls, f"`$ref` `{ref}` names neither a `$defs` entry of the"
                                   f" class, nor `{CONSTRUCT}`, nor a node class")
            if ref in under_children and name not in reserved:   # only judgeable now
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
