"""Loading node classes (PLUGIN_SYSTEM.md): registration under `@TAT_node`,
the table from `kind` to class that `edit` dispatches on, the `$defs` that
complete the `edit` tool's schema at start, and the argument schema grammar
— what a class's TypedDict may declare, and how a submitted construct is
checked against it.

Importing a plugin's package is what registers its classes; `load` imports
every package `launch_TAT` received, after the framework's own classes, and
then assembles and seals.  Every check failure is a `CannotLoadPlugin`
(EXCEPTIONS.md §1): a plugin's bug fails the conversation start.  One
conversation per process, so the table, the class list and the seal are
module state.
"""

from __future__ import annotations

import copy
import importlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints, is_typeddict

import jsoncomment
import jsonschema

from . import model
from .exceptions import (
    InvalidField, MissingField, TAT_InternalError, TAT_StartupError, UnexpectedField)
from .model import JSON_Schema, Leaf, Node, RawAST
from .store import FRAMEWORK_FIELDS


class CannotLoadPlugin(TAT_StartupError):
    """A node class failed a check of PLUGIN_SYSTEM §5; `node_class` is None
    for a check on the assembled schema."""

    def __init__(self, package: str | None, node_class: str | None, reason: str):
        where = (f"{package}.{node_class}" if node_class
                 else package or "the assembled edit schema")
        super().__init__(f"cannot load {where}: {reason}")
        self.package = package
        self.node_class = node_class
        self.reason = reason


# kind -> node class, in registration order — the order agent-facing lists
# of kinds render in (EXCEPTIONS.md §3, `UnknownKind`) and the order of the
# `Construct` union.
kinds: dict[str, type[Node]] = {}
classes: list[type[Node]] = []
_sealed = False

CONSTRUCT = "Construct"                        # the union's reserved `$defs` name
_REF = re.compile(r"^#/\$defs/([^/]+)$")
_EDIT_SCHEMA = Path(__file__).parent / "tools" / "edit.jsonc"


def TAT_node(cls: type[Node]) -> type[Node]:
    """Class decorator: check the class (PLUGIN_SYSTEM §5) and register it
    under every kind its construct schema names."""
    if _sealed:
        raise TAT_InternalError(
            f"{cls.__name__} registers after load returned; the conversation is running")
    for kind in _check_class(cls):               # nothing is written before the checks pass
        kinds[kind] = cls
    classes.append(cls)
    return cls


@dataclass(frozen=True)
class Loaded:
    """What `load` hands the conversation: the `edit` tool's schema with
    its `$defs` filled in (PLUGIN_SYSTEM §4)."""
    edit_schema: JSON_Schema


def load(python_packages: list[str]) -> Loaded:
    """Register the framework's classes, import every package — importing
    registers — then assemble the `edit` schema and seal the table."""
    global _sealed
    for cls in model.FRAMEWORK_NODE_CLASSES:
        TAT_node(cls)
    for package in python_packages:
        importlib.import_module(package)
    loaded = Loaded(edit_schema())
    _sealed = True
    return loaded


def edit_schema() -> JSON_Schema:
    """The `edit` tool's schema with its `$defs` filled in (PLUGIN_SYSTEM
    §4), checked whole."""
    schema = jsoncomment.JsonComment().loads(_EDIT_SCHEMA.read_text())
    schema["$defs"] = assemble()
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
        if kind in kinds:
            raise _refuse(cls, f"kind `{kind}` is already registered by {kinds[kind].__name__}")
    if "kind" not in required:
        raise _refuse(cls, "`kind` must be in `required`")
    if any(c.__name__ == cls.__name__ for c in classes):
        raise _refuse(cls, "another node class has this name")
    properties = _properties(cls)
    if "children" in properties:
        if issubclass(cls, Leaf):
            raise _refuse(cls, "a Leaf declares no `children`")
        if not _is_construct_array(properties["children"]):
            raise _refuse(cls, "`children` must be an array of `#/$defs/<Name>` `$ref`s")
    if cls.output_omissible and not cls.input_omissible:
        # TAT would print an id it then refuses to accept (MCP_SPECIFICATION §2.1).
        raise _refuse(cls, "omissible on output but compulsory on input")
    if _defined_by(cls, "is_finished") is not Node:
        raise _refuse(cls, "overrides `is_finished`; `_owes_nothing` is the override point")
    for method in ("gen", "to_store", "from_store"):
        if _defined_by(cls, method) is Node:
            raise _refuse(cls, f"does not override `{method}`")
    try:
        validate_argument_schema(cls.argument_schema)
    except TAT_InternalError as e:
        raise _refuse(cls, f"argument_schema: {e}") from e
    hints = get_type_hints(cls.argument_schema)
    schema_fields = set(properties) - set(FRAMEWORK_FIELDS)
    typed_fields = set(hints) - {"kind"}
    if schema_fields != typed_fields:
        raise _refuse(cls, f"construct_schema declares the fields {sorted(schema_fields)},"
                           f" argument_schema the fields {sorted(typed_fields)}")
    schema_required = set(required) - set(FRAMEWORK_FIELDS)
    typed_required = set(cls.argument_schema.__required_keys__) - {"kind"}
    if schema_required != typed_required:
        raise _refuse(cls, f"construct_schema requires {sorted(schema_required)},"
                           f" argument_schema requires {sorted(typed_required)}")
    return own_kinds


def _defined_by(cls: type, name: str) -> type:
    """The class in `cls`'s MRO whose body defines `name` — read off the
    class dicts, since a classmethod binds afresh on every access.  The
    override checks compare it with `Node`: a framework class between
    `Node` and the plugin's (`Leaf`, `StdBlock`) must not define these
    methods itself, or the check goes blind for its subclasses."""
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


# --- the argument schema grammar --------------------------------------------
# `str`, `bool`, `int`, `float`, `Any`, `list[X]`, a TypedDict, and unions of
# those holding at most one TypedDict — closed, so every rendering stays
# within RENDER_BASELINES §2's vocabulary.  Validated once, at registration;
# then every submitted construct is checked against the declaration before
# its class's `gen` is consulted (MODULE_STRUCTURE §4.2).

_JSON_NAMES = {str: "a string", bool: "a boolean", int: "a number",
               float: "a number"}


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
        hints = get_type_hints(td)
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
    if isinstance(value, bool):            # a flag is not a number
        return ann is bool
    if ann is float:                       # JSON has one number type
        return isinstance(value, (int, float))
    return isinstance(value, ann)


def _json_name(ann: Any) -> str:
    """The approved rendering of a type (RENDER_BASELINES §2)."""
    if is_typeddict(ann):
        return "an object"
    if get_origin(ann) is list:
        return "a list"
    if get_origin(ann) in (Union, UnionType):
        names = []
        for a in get_args(ann):
            if _json_name(a) not in names:
                names.append(_json_name(a))
        return " or ".join(names)
    if ann not in _JSON_NAMES:
        raise TAT_InternalError(f"{ann!r} is outside the argument schema grammar")
    return _JSON_NAMES[ann]


def check_construct(cls: type[Node], kind: str, raw: RawAST) -> None:
    """The mechanical shape of a submitted construct, before its class is
    consulted: no field the class does not declare, required fields
    present, types right — against the class's `argument_schema`."""
    _check_fields(cls.argument_schema, kind, raw, prefix="")


def _check_fields(td: Any, kind: str, mapping: Mapping[str, Any],
                  prefix: str) -> None:
    hints = get_type_hints(td)
    for field in mapping:                  # first: a typo beats its own hole
        if not prefix and field in FRAMEWORK_FIELDS:
            continue                       # the framework's own fields
        if field not in hints:
            # At the top level `kind` is the framework's field, not one the
            # class "takes" (RENDER_BASELINES.md §2).
            takes = [f for f in hints if prefix or f != "kind"]
            raise UnexpectedField(prefix[:-1] if prefix else kind, field,
                                  takes, holder_is_kind=not prefix)
    for field in td.__required_keys__:
        if field not in mapping:
            raise MissingField(kind, prefix + field)
    for field, value in mapping.items():
        if not prefix and field in FRAMEWORK_FIELDS:
            continue
        _check_value(value, hints[field], kind, prefix + field)


def _check_value(value: Any, ann: Any, kind: str, path: str) -> None:
    """One value against its annotation, descending so that the field
    reported is the innermost at fault: a list element by its index, a
    TypedDict's field by its name, a union by the arm the value fits."""
    if get_origin(ann) is list:
        if not isinstance(value, list):
            raise InvalidField(path, "must be a list")
        for i, v in enumerate(value):
            _check_value(v, get_args(ann)[0], kind, f"{path}[{i}]")
    elif get_origin(ann) in (Union, UnionType):
        arm = next((a for a in get_args(ann) if _matches(value, a)), None)
        if arm is None:
            raise InvalidField(path, f"must be {_json_name(ann)}")
        _check_value(value, arm, kind, path)
    elif is_typeddict(ann):
        if not isinstance(value, Mapping):
            raise InvalidField(path, "must be an object")
        _check_fields(ann, kind, value, path + ".")
    elif not _matches(value, ann):
        raise InvalidField(path, f"must be {_json_name(ann)}")


# --- assembly ----------------------------------------------------------------

def assemble() -> dict[str, JSON_Schema]:
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
