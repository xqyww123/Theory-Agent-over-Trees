"""`Typedef`, the node class of the plugin `Isabelle_Std` for `typedef`
(node_classes/TYPEDEF.md): a subtype — a new type whose values stand for
the elements of a non-empty subset of an existing type, with a function
each way between the two — a `Proof_Obligation` (COMMON.md §3) whose one
goal is the subset's non-emptiness; its evaluation records whether the
command needs `(overloaded)` and whether Isabelle set lifting up for the
type."""

from __future__ import annotations

from collections.abc import Container
from typing import Any, Literal, NotRequired, TypedDict

from Isabelle_RPC_Host.unicode import IsaTerm

from ..exceptions import InvalidField
from ..model import INDENT, RECALL, Leaf, emit_lines, print_name
from ..plugin import TAT_node
from .common import (
    TYPE_MIXFIX_DEFS, TYPE_PARAMETER_DEFS, Proof_Obligation, Theory_Member, Type_Parameter, TypeMixfix,
    TypeMixfix_RawAST, TypeParameter_RawAST, check_identifier, mixfix_of, mixfix_text, mixfix_wire, normalised,
    require_id_name, text_line, type_parameters_of, type_parameters_text, type_parameters_wire)

KINDS = ("typedef",)
LIFTING_NOTICE = "Because of a limitation inside Isabelle, lift_definition cannot be used on this subtype."   # §6
_DEFAULT_PREFIXES = ("Rep_", "Abs_")    # before the type's name: the Rep and the Abs function names left out (§2),
                                        # which a given name may therefore not begin with (§4)


class Typedef_RawAST(TypedDict):
    kind: Literal["typedef"]
    english: str
    type_parameters: NotRequired[list[TypeParameter_RawAST]]
    type_name: str
    syntax: NotRequired[TypeMixfix_RawAST]
    set: str
    rep_function_name: NotRequired[str]
    abs_function_name: NotRequired[str]


@TAT_node
class Typedef(Theory_Member, Proof_Obligation, Leaf):
    construct_schema = {
        "type": "object",
        "description": "defines a subtype: a new type whose values stand for the elements of a non-empty subset of an"
                       " existing type. Example: typedef 'a dlist = \"{xs :: 'a list. distinct xs}\", the subtype of"
                       " lists without repetition",
        "properties": {
            "kind": {"const": "typedef"},
            "english": {"type": "string", "description": "what is defined, in English, as LaTeX text"},
            "type_parameters": {"type": "array", "items": {"$ref": "#/$defs/TypeParameter"},
                                "description": "the parameters of the subtype; sorts are usually not specified"},
            "type_name": {"type": "string"},
            "syntax": {"$ref": "#/$defs/TypeMixfix"},
            "set": {"type": "string", "description": "the subset defining the subtype"},
            "rep_function_name": {"type": "string",
                                  "description": "the name of the function that sends a value of the subtype to its"
                                                 " representation in the existing type; Rep_ followed by the type name"
                                                 " when left out. Example: list_of_dlist"},
            "abs_function_name": {"type": "string",
                                  "description": "the name of the function that sends a representation in the existing"
                                                 " type back to the value of the subtype it represents; Abs_ followed"
                                                 " by the type name when left out. Example: dlist_of_list"},
        },
        "required": ["kind", "english", "type_name", "set"],
        "additionalProperties": False,
        "$defs": {**TYPE_PARAMETER_DEFS, **TYPE_MIXFIX_DEFS},
    }
    argument_schema = Typedef_RawAST
    evaluation_callback = "TAT.Typedef.evaluate"
    valid_word, invalid_word = "valid definition", "invalid definition"     # the mark's first slot (§7)

    english: str
    type_parameters: tuple[Type_Parameter, ...]
    syntax: TypeMixfix | None
    set: IsaTerm
    rep_function_name: IsaTerm | None       # None when left out: Isabelle's default, `Rep_` before the name (§2)
    abs_function_name: IsaTerm | None       # likewise, `Abs_`
    overloaded: bool                        # recorded by the evaluation (§6): false until one has
    lifting: bool

    def __init__(self, parent, state, english: str, type_parameters: tuple[Type_Parameter, ...], type_name: str,
                 syntax: TypeMixfix | None, set: IsaTerm, rep_function_name: IsaTerm | None,
                 abs_function_name: IsaTerm | None, overloaded: bool = False, lifting: bool = False):
        super().__init__(parent, state)
        self.english = english
        self.type_parameters = type_parameters
        self.name = type_name                   # the node's name (§1)
        self.syntax = syntax
        self.set = set
        self.rep_function_name = rep_function_name
        self.abs_function_name = abs_function_name
        self.overloaded = overloaded
        self.lifting = lifting

    @classmethod
    async def gen(cls, config, raw: Typedef_RawAST):
        """§4's checks in its order: the parent; `type_name` against §1's
        grammar; the type parameters by the shared check; each function
        name given an identifier not beginning with `Rep_` or `Abs_`, the
        two not the same."""
        cls.require_inside_theory(config, raw["kind"])
        require_id_name(raw["type_name"], "type name")
        type_parameters = type_parameters_of(raw.get("type_parameters", []))
        rep = _function_name_of(raw.get("rep_function_name"), "rep_function_name", ())
        abs_ = _function_name_of(raw.get("abs_function_name"), "abs_function_name", () if rep is None else (rep,))
        return cls(config.parent, config.state, normalised(raw["english"]), type_parameters, raw["type_name"],
                   mixfix_of(raw["syntax"]) if "syntax" in raw else None, IsaTerm.from_agent(normalised(raw["set"])),
                   rep, abs_)

    # --- the store: the authored fields in the `unicode` spelling and the recorded ones (§1), every row read with
    #     `get`, so that a missing one is refused at start; a field left out is a None row, this class's own choice

    def to_store(self, rows):
        rows.put("english", self.english)
        rows.put("type_parameters", [p.image() for p in self.type_parameters])
        rows.put("type_name", self.name)
        rows.put("syntax", self.syntax.image() if self.syntax is not None else None)
        rows.put("set", self.set.unicode)
        rows.put("rep_function_name", self.rep_function_name.unicode if self.rep_function_name is not None else None)
        rows.put("abs_function_name", self.abs_function_name.unicode if self.abs_function_name is not None else None)
        rows.put("overloaded", self.overloaded)
        rows.put("lifting", self.lifting)

    @classmethod
    def from_store(cls, config, rows):
        syntax: TypeMixfix_RawAST | None = rows.get("syntax")
        rep: str | None = rows.get("rep_function_name")
        abs_: str | None = rows.get("abs_function_name")
        return cls(config.parent, config.state, rows.get("english"), type_parameters_of(rows.get("type_parameters")),
                   rows.get("type_name"), mixfix_of(syntax) if syntax is not None else None,
                   IsaTerm.from_agent(rows.get("set")), IsaTerm.from_agent(rep) if rep is not None else None,
                   IsaTerm.from_agent(abs_) if abs_ is not None else None, rows.get("overloaded"), rows.get("lifting"))

    # --- evaluation (§6)

    def goal_structure(self) -> Any:
        """§4: the type parameters with their sorts and `set`, each `IsaTerm`
        as its `ascii` — what the goal `∃x. x ∈ S` is made of."""
        return (type_parameters_wire(self.type_parameters), self.set.ascii)

    def message(self) -> Any:
        """The definition as `TAT.Typedef.evaluate` unpacks it: `type_name`,
        the syntax as `mixfix_wire` writes it, the two function names with
        the defaults filled in, then the goal structure."""
        rep, abs_ = self._function_names()
        return (self.name, mixfix_wire(self.syntax), rep.ascii, abs_.ascii, *self.goal_structure())

    def record_from_evaluation(self, what):
        """§6: `overloaded` and `lifting`, what the two steps yielded; the
        notice exactly when Isabelle could not set lifting up."""
        self.overloaded, self.lifting = what
        return () if self.lifting else (IsaTerm.from_agent(LIFTING_NOTICE),)

    # --- what it prints (§8) and emission (§5)

    def _function_names(self) -> tuple[IsaTerm, IsaTerm]:
        """The Rep and the Abs function names, one left out as its default (§2)."""
        rep, abs_ = ((given if given is not None else IsaTerm.from_agent(prefix + self.name))
                     for given, prefix in zip((self.rep_function_name, self.abs_function_name), _DEFAULT_PREFIXES))
        return rep, abs_

    def _definition(self, keywords: Container[str]) -> tuple[str, str | None]:
        """The text after the command — the head (the parameters, the name,
        the syntax), `=` and the set — a name, a sort and the set through
        `print_name` against `keywords` (the theory's for the file, none
        under `recall`), a type variable and the syntax as their writers
        write them; beside it the `morphisms` clause when either function
        name was given, the other as its default, None when neither was."""
        head = " ".join(filter(None, (type_parameters_text(self.type_parameters, keywords),
                                      print_name(self.name, keywords),
                                      mixfix_text(self.syntax) if self.syntax is not None else "")))
        morphisms = (None if self.rep_function_name is None and self.abs_function_name is None
                     else "morphisms " + " ".join(print_name(f, keywords) for f in self._function_names()))
        return f"{head} = {print_name(self.set, keywords)}", morphisms

    def print_fields(self, indent, out, mode, depth):
        """Under `Recall` alone (§8): the definition on one line at depths 0
        to 2, against no keyword; `english` at 0."""
        if mode is RECALL and depth <= 2:
            out.write(INDENT * indent + " ".join(filter(None, self._definition(()))) + "\n")
        if mode is RECALL and depth == 0:
            out.write(INDENT * indent + self.english + "\n")

    def emit(self, indent, out):
        """§5: the `text` line; the command, `(overloaded)` when recorded,
        the `morphisms` line and the terminal proof under it; then
        `setup_lifting` when recorded."""
        emit_lines(indent, out, text_line(self.english))
        keywords = self.theory().keywords or ()
        definition, morphisms = self._definition(keywords)
        command = f"{self.kind} (overloaded)" if self.overloaded else self.kind
        lines = [f"{command} {definition}"]
        if morphisms is not None:
            lines.append(f"  {morphisms}")
        lines.append(f"  {self.proof_text()}")
        if self.lifting:
            lines.append(f"setup_lifting {print_name(f'type_definition_{self.name}', keywords)}")
        emit_lines(indent, out, "\n".join(lines))
        return indent


def _function_name_of(text: str | None, field: str, earlier: tuple[IsaTerm, ...]) -> IsaTerm | None:
    """§4: a function name given is an Isabelle identifier Isabelle reads
    in a term, not among `earlier`, and does not begin with `Rep_` or
    `Abs_`, so that no given name is a default's; None when left out."""
    if text is None:
        return None
    name = check_identifier(text, field, earlier, in_term=True)
    if name.ascii.startswith(_DEFAULT_PREFIXES):
        raise InvalidField(field, "must not begin with `Rep_` or `Abs_`")
    return name
