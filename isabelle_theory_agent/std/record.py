"""`Record`, the node class of the plugin `Isabelle_Std` for `record`
(node_classes/RECORD.md): a record type by its name, its type
parameters, its fields and, when it extends one, its parent record; its
evaluation runs the command and nothing more, and the node is finished
when it is `ready`."""

from __future__ import annotations

from collections.abc import Container
from dataclasses import dataclass
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from Isabelle_RPC_Host.unicode import IsaTerm, is_identifier

from .. import isabelle_driver
from ..model import INDENT, NON_EMPTY, RECALL, Leaf, Theory, emit_lines, print_name, status_of_errors
from ..plugin import TAT_node
from .common import (
    TYPE_PARAMETER_DEFS, Type_Definition, Type_Parameter, TypeParameter_RawAST, check_identifier,
    check_type_parameters, check_type_parameters_used, normalised, require_id_name, text_line, type_head_text,
    type_parameters_of, type_parameters_wire)

KINDS = ("record",)


class Field_RawAST(TypedDict):
    name: str
    type: str


class Record_RawAST(TypedDict):
    kind: Literal["record"]
    english: str
    type_parameters: NotRequired[list[TypeParameter_RawAST]]
    type_name: str
    parent: NotRequired[str]
    fields: Annotated[list[Field_RawAST], NON_EMPTY]


@dataclass(frozen=True)
class Field:
    name: IsaTerm
    type: IsaTerm


@TAT_node
class Record(Leaf, Type_Definition):
    construct_schema = {
        "type": "object",
        "properties": {
            "kind": {"const": "record"},
            "english": {"type": "string", "description": "what is defined, in English, as LaTeX text"},
            "type_parameters": {"type": "array", "items": {"$ref": "#/$defs/TypeParameter"},
                                "description": "the type's parameters; sorts are usually not specified"},
            "type_name": {"type": "string"},
            "parent": {"type": "string",
                       "description": "the parent record this one extends. The resulting record includes the"
                                      " parent's fields and the ones added here. Example: 'a point; the type"
                                      " arguments are required"},
            "fields": {"type": "array", "minItems": 1,
                       "items": {
                           "type": "object",
                           "properties": {
                               "name": {"type": "string"},
                               "type": {"type": "string", "description": "An Isabelle type expression"}},
                           "required": ["name", "type"],
                           "additionalProperties": False}},
        },
        "required": ["kind", "english", "type_name", "fields"],
        "additionalProperties": False,
        "$defs": {**TYPE_PARAMETER_DEFS},
    }
    argument_schema = Record_RawAST

    english: str
    type_parameters: tuple[Type_Parameter, ...]
    parent_record: IsaTerm | None       # the construct's `parent`; None when there is none
    fields: tuple[Field, ...]

    def __init__(self, parent, state, english: str, type_parameters: tuple[Type_Parameter, ...], type_name: str,
                 parent_record: IsaTerm | None, fields: tuple[Field, ...]):
        super().__init__(parent, state)
        self.english = english
        self.type_parameters = type_parameters
        self.name = type_name
        self.parent_record = parent_record
        self.fields = fields

    @classmethod
    async def gen(cls, config, raw: Record_RawAST):
        """§4: `type_name` against §1's grammar; the rest read."""
        require_id_name(raw["type_name"], "type name")
        parent = normalised(raw.get("parent", ""))                   # an empty `parent` is no parent (§2)
        return cls(config.parent, config.state, normalised(raw["english"]),
                   type_parameters_of(raw.get("type_parameters", [])), raw["type_name"],
                   IsaTerm.from_agent(parent) if parent else None,
                   tuple(Field(IsaTerm.from_agent(normalised(f["name"])), IsaTerm.from_agent(normalised(f["type"])))
                         for f in raw["fields"]))

    def check_fields(self):
        """§4's field check in its order: the type parameters by the shared
        check; each field's name, no two the same; then every type
        parameter used, in a field's type or `parent`."""
        check_type_parameters(self.type_parameters, ".name")
        for i, f in enumerate(self.fields):
            check_identifier(f.name, f"fields[{i}].name", [x.name for x in self.fields[:i]], in_term=True)
        parent = self.parent_type()
        check_type_parameters_used(self.type_parameters, [f.type for f in self.fields] + ([parent] if parent is not None else []))

    def parent_type(self) -> IsaTerm | None:
        """`parent` in its applied form (§2); None when there is none."""
        return _applied(self.parent_record, self.type_parameters) if self.parent_record is not None else None

    # --- the store (§1): the authored fields in the `unicode` spelling, the construct's shape, `parent` a
    # None-valued row when there is none; every row read with `rows.get`, so that a missing one is refused at start

    def to_store(self, rows):
        rows.put("english", self.english)
        rows.put("type_parameters", [p.image() for p in self.type_parameters])
        rows.put("type_name", self.name)
        rows.put("parent", self.parent_record.unicode if self.parent_record is not None else None)
        rows.put("fields", [{"name": f.name.unicode, "type": f.type.unicode} for f in self.fields])

    @classmethod
    def from_store(cls, config, rows):
        parent_record = rows.get("parent")
        return cls(config.parent, config.state, rows.get("english"), type_parameters_of(rows.get("type_parameters")),
                   rows.get("type_name"),
                   IsaTerm.from_agent(parent_record) if parent_record is not None else None,
                   tuple(Field(IsaTerm.from_agent(f["name"]), IsaTerm.from_agent(f["type"])) for f in rows.get("fields")))

    # --- evaluation (§6)

    def message(self) -> Any:
        """The definition as `TAT.Record.evaluate` unpacks it: the type
        parameters with their sorts, the type's name, `parent` in its
        applied form with whether it was authored bare (§2, §6), and the
        fields with their types — each `IsaTerm` as its `ascii`."""
        parent = self.parent_record
        return (type_parameters_wire(self.type_parameters),
                self.name,
                (_applied(parent, self.type_parameters).ascii, is_identifier(parent.ascii)) if parent is not None
                else None,
                [(f.name.ascii, f.type.ascii) for f in self.fields])

    async def _eval_opr(self):
        """One transition, the command on the input slot's state into the
        resulting slot (§6): the messages make the node an obstacle, none
        is `Ready`."""
        messages = await isabelle_driver.call(
            self.forest().conversation, "TAT.Record.evaluate",
            (self.state.to_msgpack(), self.resulting_state().to_msgpack(), self.message()))
        return status_of_errors(messages)

    # --- what it prints (§8) and emission (§5)

    def _definition(self, keywords: Container[str]) -> tuple[str, list[str]]:
        """The head — the type's head by `type_head_text`, `=`, `parent` in
        its applied form and `+` when given — and the fields' texts, every
        piece through `print_name` against `keywords`: the theory's for the
        file; none under `recall`, where every name, an identifier, comes
        out bare."""
        head = type_head_text(self.type_parameters, self.name, None, keywords) + " ="
        parent_type = self.parent_type()
        if parent_type is not None:
            head += f" {print_name(parent_type, keywords)} +"
        return head, [f"{print_name(f.name, keywords)} :: {print_name(f.type, keywords)}" for f in self.fields]

    def print_fields(self, indent, out, mode, depth):
        """Under `Recall` alone (§8): the definition, one line, at depths 0
        to 2, against no keyword; `english` at 0."""
        if mode is RECALL and depth <= 2:
            head, fields = self._definition(())
            out.write(INDENT * indent + " ".join([head, *fields]) + "\n")
        if mode is RECALL and depth == 0:
            out.write(INDENT * indent + self.english + "\n")
        return False

    def emit(self, indent, out):
        emit_lines(indent, out, text_line(self.english))
        head, fields = self._definition(self.enclosing(Theory).keywords or ())
        emit_lines(indent, out, "\n".join([f"{self.kind} {head}", *(f"  {f}" for f in fields)]))
        return indent


def _applied(parent: IsaTerm, parameters: tuple[Type_Parameter, ...]) -> IsaTerm:
    """`parent` in its applied form (§2): as authored, unless authored bare
    — an identifier —, then applied to the type parameters in their order,
    `('a, 'b) point`, `point` itself when there are none."""
    if not is_identifier(parent.ascii):
        return parent
    names = [p.name.unicode for p in parameters]
    arguments = "" if not names else names[0] + " " if len(names) == 1 else "(" + ", ".join(names) + ") "
    return IsaTerm.from_agent(arguments + parent.unicode)
