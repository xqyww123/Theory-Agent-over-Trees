"""`Datatype`, the node class of the plugin `Isabelle_Std` for `datatype`
and `codatatype` (node_classes/DATATYPE.md): one type, or several that
are mutually recursive, each by its name, the node's type parameters and
its constructors; its evaluation runs the command and nothing more, and
the node is finished when it is `ready`."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from Isabelle_RPC_Host.unicode import IsaTerm

from .. import isabelle_driver
from ..exceptions import InvalidField
from ..model import INDENT, NON_EMPTY, RECALL, Leaf, emit_lines, status_of_errors
from ..plugin import TAT_node
from .common import (
    MIXFIX_DEFS, TYPE_MIXFIX_DEFS, TYPE_PARAMETER_DEFS, Mixfix, Mixfix_RawAST, Spelling, Theory_Member,
    Type_Parameter, TypeMixfix_RawAST, TypeParameter_RawAST, check_identifier, mixfix_of, mixfix_text, mixfix_wire,
    normalised, require_id_name, text_line, type_parameters_of, type_parameters_text)

KINDS = ("datatype", "codatatype")      # the two commands, one syntax and one implementation


class Argument_RawAST(TypedDict):
    type: str
    selector: NotRequired[str]


class Constructor_RawAST(TypedDict):
    name: str
    arguments: NotRequired[list[Argument_RawAST]]
    syntax: NotRequired[Mixfix_RawAST]


class Type_RawAST(TypedDict):
    type_name: str
    syntax: NotRequired[TypeMixfix_RawAST]
    constructors: Annotated[list[Constructor_RawAST], NON_EMPTY]


class Datatype_RawAST(TypedDict):
    kind: Literal["datatype", "codatatype"]
    english: str
    type_parameters: NotRequired[list[TypeParameter_RawAST]]
    types: Annotated[list[Type_RawAST], NON_EMPTY]


@dataclass(frozen=True)
class Argument:
    type: IsaTerm
    selector: IsaTerm | None        # None when there is none


@dataclass(frozen=True)
class Constructor:
    name: IsaTerm
    arguments: tuple[Argument, ...]
    syntax: Mixfix | None


@dataclass(frozen=True)
class Defined_Type:
    """One type of the definition (§2): its name, its optional syntax and its
    constructors; the parameters are the node's."""
    type_name: str
    syntax: Mixfix | None
    constructors: tuple[Constructor, ...]


_Name = Callable[[str | IsaTerm], str]      # how a name is written: through `print_name`, or bare


@TAT_node
class Datatype(Theory_Member, Leaf):
    construct_schema = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": list(KINDS)},
            "english": {"type": "string", "description": "what is defined, in English, as LaTeX text"},
            "type_parameters": {"type": "array", "items": {"$ref": "#/$defs/TypeParameter"},
                                "description": "the parameters of the types defined; sorts are usually not specified"},
            "types": {"type": "array", "minItems": 1,
                      "description": "the types defined by this command: usually one; several only when they are"
                                     " mutually recursive",
                      "items": {
                          "type": "object",
                          "properties": {
                              "type_name": {"type": "string"},
                              "syntax": {"$ref": "#/$defs/TypeMixfix"},
                              "constructors": {"type": "array", "minItems": 1,
                                               "items": {
                                                   "type": "object",
                                                   "properties": {
                                                       "name": {"type": "string"},
                                                       "arguments": {"type": "array",
                                                                     "items": {
                                                                         "type": "object",
                                                                         "properties": {
                                                                             "type": {"type": "string",
                                                                                      "description": "An Isabelle type expression"},
                                                                             "selector": {"type": "string",
                                                                                          "description": "the name of the function that extracts this argument from the constructor, as hd and tl in Cons (hd: 'a) (tl: \"'a list\"). Leave out if none"}},
                                                                         "required": ["type"],
                                                                         "additionalProperties": False}},
                                                       "syntax": {"$ref": "#/$defs/Mixfix"}},
                                                   "required": ["name"],
                                                   "additionalProperties": False}}},
                          "required": ["type_name", "constructors"],
                          "additionalProperties": False}},
        },
        "required": ["kind", "english", "types"],
        "additionalProperties": False,
        "$defs": {**TYPE_PARAMETER_DEFS, **TYPE_MIXFIX_DEFS, **MIXFIX_DEFS},
    }
    argument_schema = Datatype_RawAST

    english: str
    type_parameters: tuple[Type_Parameter, ...]
    types: tuple[Defined_Type, ...]

    def __init__(self, parent, state, english: str, type_parameters: tuple[Type_Parameter, ...],
                 types: tuple[Defined_Type, ...]):
        super().__init__(parent, state)
        self.english = english
        self.type_parameters = type_parameters
        self.types = types
        self.name = "_".join(t.type_name for t in types)       # Isabelle's own name for the group (§2)

    @classmethod
    async def gen(cls, config, raw: Datatype_RawAST):
        cls.require_inside_theory(config, raw["kind"])
        types: list[Defined_Type] = []
        for i, t in enumerate(raw["types"]):
            require_id_name(t["type_name"], "type name")
            if any(u.type_name == t["type_name"] for u in types):
                raise InvalidField(f"types[{i}].type_name", f"binds `{t['type_name']}` a second time")
            constructors: list[Constructor] = []
            for j, c in enumerate(t["constructors"]):
                name = IsaTerm.from_agent(normalised(c["name"]))
                check_identifier(name, f"types[{i}].constructors[{j}].name", [x.name for x in constructors],
                                 in_term=True)
                arguments: list[Argument] = []
                for k, a in enumerate(c.get("arguments", [])):
                    selector = None
                    if "selector" in a:
                        selector = IsaTerm.from_agent(normalised(a["selector"]))
                        check_identifier(selector, f"types[{i}].constructors[{j}].arguments[{k}].selector",
                                         [x.selector for x in arguments if x.selector is not None], in_term=True)
                    arguments.append(Argument(IsaTerm.from_agent(normalised(a["type"])), selector))
                constructors.append(Constructor(name, tuple(arguments),
                                                mixfix_of(c["syntax"]) if "syntax" in c else None))
            types.append(Defined_Type(t["type_name"], mixfix_of(t["syntax"]) if "syntax" in t else None,
                                      tuple(constructors)))
        return cls(config.parent, config.state, normalised(raw["english"]),
                   type_parameters_of(raw.get("type_parameters", [])), tuple(types))

    # --- the store (§2): the authored fields in the `unicode` spelling, the construct's shape

    def to_store(self, rows):
        rows.put("english", self.english)
        rows.put("type_parameters", [p.image() for p in self.type_parameters])
        rows.put("types", [_type_image(t) for t in self.types])

    @classmethod
    def from_store(cls, config, rows):
        return cls(config.parent, config.state, rows.get("english"), type_parameters_of(rows.get("type_parameters")),
                   tuple(_type_of_image(t) for t in rows.get("types")))

    # --- evaluation (§6)

    def message(self) -> Any:
        """The definition as `TAT.Datatype.evaluate` unpacks it: `kind`, the
        type parameters with their sorts, the types each with its name, its
        syntax and its constructors with their arguments, selectors and
        syntax — each `IsaTerm` as its `ascii`."""
        return (self.kind,
                [(p.name.ascii, p.sort.ascii if p.sort is not None else None) for p in self.type_parameters],
                [(t.type_name, mixfix_wire(t.syntax),
                  [(c.name.ascii, [(a.type.ascii, a.selector.ascii if a.selector is not None else None)
                                   for a in c.arguments], mixfix_wire(c.syntax))
                   for c in t.constructors])
                 for t in self.types])

    async def _eval_opr(self):
        """One transition, the command on the input slot's state into the
        resulting slot (§6): the messages make the node an obstacle, none
        is `Ready`."""
        messages = await isabelle_driver.call(
            self.forest().conversation, "TAT.Datatype.evaluate",
            (self.state.to_msgpack(), self.resulting_state().to_msgpack(), self.message()))
        return status_of_errors(messages)

    # --- what it prints (§8) and emission (§5)

    def _definition(self, spelling: Spelling, name: _Name) -> list[tuple[str, list[str]]]:
        """Each type's head — the parameters, the name, the syntax — and its
        constructors' texts, in `spelling`, names written by `name`, a sort
        and an argument's type through the theory's `print_name`."""
        theory = self.theory()
        parameters = type_parameters_text(theory, self.type_parameters, spelling)
        definition = []
        for t in self.types:
            head = " ".join(filter(None, (parameters, name(t.type_name),
                                          mixfix_text(t.syntax, spelling) if t.syntax is not None else "")))
            constructors = []
            for c in t.constructors:
                parts = [name(c.name)]
                for a in c.arguments:
                    type_text = theory.print_name(a.type, spelling)
                    parts.append(f"({name(a.selector)}: {type_text})" if a.selector is not None else type_text)
                if c.syntax is not None:
                    parts.append(mixfix_text(c.syntax, spelling))
                constructors.append(" ".join(parts))
            definition.append((head, constructors))
        return definition

    def print_fields(self, indent, out, mode, depth):
        """Under `Recall` alone (§8): the definition, one line per type, at
        depths 0 to 2, in `unicode` with every name bare; `english` at 0."""
        if mode is RECALL and depth <= 2:
            for i, (head, constructors) in enumerate(self._definition("unicode", _bare)):
                out.write(INDENT * indent + ("and " if i else "") + f"{head} = " + " | ".join(constructors) + "\n")
        if mode is RECALL and depth == 0:
            out.write(INDENT * indent + self.english + "\n")

    def emit(self, indent, out):
        emit_lines(indent, out, text_line(self.english))
        lines = []
        for i, (head, constructors) in enumerate(self._definition("ascii", self.theory().print_name)):
            lines.append(f"{self.kind if i == 0 else 'and'} {head} =")
            lines.append(f"    {constructors[0]}")
            lines.extend(f"  | {c}" for c in constructors[1:])
        emit_lines(indent, out, "\n".join(lines))
        return indent


def _bare(name: str | IsaTerm) -> str:
    return name if isinstance(name, str) else name.unicode


def _type_image(t: Defined_Type) -> dict[str, Any]:
    return {"type_name": t.type_name,
            **({"syntax": t.syntax.image()} if t.syntax is not None else {}),
            "constructors": [
                {"name": c.name.unicode,
                 "arguments": [{"type": a.type.unicode,
                                **({"selector": a.selector.unicode} if a.selector is not None else {})}
                               for a in c.arguments],
                 **({"syntax": c.syntax.image()} if c.syntax is not None else {})}
                for c in t.constructors]}


def _type_of_image(image: dict[str, Any]) -> Defined_Type:
    return Defined_Type(
        image["type_name"], mixfix_of(image["syntax"]) if "syntax" in image else None,
        tuple(Constructor(IsaTerm.from_agent(c["name"]),
                          tuple(Argument(IsaTerm.from_agent(a["type"]),
                                         IsaTerm.from_agent(a["selector"]) if "selector" in a else None)
                                for a in c["arguments"]),
                          mixfix_of(c["syntax"]) if "syntax" in c else None)
              for c in image["constructors"]))
