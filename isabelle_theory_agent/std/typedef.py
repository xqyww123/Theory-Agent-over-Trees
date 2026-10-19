"""`Typedef`, the node class of the plugin `Isabelle_Std` for `typedef`
(node_classes/TYPEDEF.md): a subtype — a new type whose values stand for
the elements of a non-empty subset of an existing type, with a function
each way between the two — a `Proof_Obligation` (COMMON.md §3) whose one
goal is the subset's non-emptiness; its evaluation records, once,
whether Isabelle set lifting up for the type, which every later
evaluation keeps to (COMMON.md §5)."""

from __future__ import annotations

from collections.abc import Container
from typing import Any, Literal, NotRequired, TypedDict

from Isabelle_RPC_Host.unicode import IsaTerm

from ..model import INDENT, RECALL, Leaf, emit_lines, print_name
from ..plugin import TAT_node
from .common import (
    TYPE_MIXFIX_DEFS, TYPE_PARAMETER_DEFS, Proof_Obligation, Theory_Member, Type_Parameter, TypeMixfix,
    TypeMixfix_RawAST, TypeParameter_RawAST, check_type_parameters_used, function_names, function_names_of, mixfix_of,
    mixfix_wire, morphisms_clause, normalised, require_id_name, text_line, type_head_text, type_parameters_of,
    type_parameters_wire, unverified)

KINDS = ("typedef",)
LIFTING_NOTICE = "Because of a limitation inside Isabelle, lift_definition cannot be used on this subtype."   # §6
OWING_LINE = "The definition is unverified until the set is proven non-empty."                                # §7
_DEFAULT_PREFIXES = ("Rep_", "Abs_")    # before the type's name: the Rep and the Abs function names left out (§2)


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
    valid_word, invalid_word = "valid definition", "invalid definition"     # the mark's first slot (§7) ...
    unverified_word = "unverified definition"                               # ... while the proof is owed

    english: str
    type_parameters: tuple[Type_Parameter, ...]
    syntax: TypeMixfix | None
    set: IsaTerm
    rep_function_name: IsaTerm | None       # None when left out: Isabelle's default, `Rep_` before the name (§2)
    abs_function_name: IsaTerm | None       # likewise, `Abs_`
    lifting: bool | None                    # recorded by the first evaluation that goes through and kept to by the
                                            # later ones, None until one has (§1, §6)

    def __init__(self, parent, state, english: str, type_parameters: tuple[Type_Parameter, ...], type_name: str,
                 syntax: TypeMixfix | None, set: IsaTerm, rep_function_name: IsaTerm | None,
                 abs_function_name: IsaTerm | None, lifting: bool | None = None):
        super().__init__(parent, state)
        self.english = english
        self.type_parameters = type_parameters
        self.name = type_name                   # the node's name (§1)
        self.syntax = syntax
        self.set = set
        self.rep_function_name = rep_function_name
        self.abs_function_name = abs_function_name
        self.lifting = lifting

    @classmethod
    async def gen(cls, config, raw: Typedef_RawAST):
        """§4's checks in its order: the parent; `type_name` against §1's
        grammar; the type parameters by the shared check; each used in
        `set`; the two function names by the shared check of the pair."""
        cls.require_inside_theory(config, raw["kind"])
        require_id_name(raw["type_name"], "type name")
        type_parameters = type_parameters_of(raw.get("type_parameters", []))
        set_ = IsaTerm.from_agent(normalised(raw["set"]))
        check_type_parameters_used(type_parameters, (set_,))
        rep, abs_ = function_names_of(raw.get("rep_function_name"), raw.get("abs_function_name"))
        return cls(config.parent, config.state, normalised(raw["english"]), type_parameters, raw["type_name"],
                   mixfix_of(raw["syntax"]) if "syntax" in raw else None, set_, rep, abs_)

    # --- the store (§1): the authored fields in the `unicode` spelling and the recorded one, a field left out and a
    #     value not yet recorded a None-valued row; every row read with `get`, so that a missing one is refused at start

    def to_store(self, rows):
        rows.put("english", self.english)
        rows.put("type_parameters", [p.image() for p in self.type_parameters])
        rows.put("type_name", self.name)
        rows.put("syntax", self.syntax.image() if self.syntax is not None else None)
        rows.put("set", self.set.unicode)
        rows.put("rep_function_name", self.rep_function_name.unicode if self.rep_function_name is not None else None)
        rows.put("abs_function_name", self.abs_function_name.unicode if self.abs_function_name is not None else None)
        rows.put("lifting", self.lifting)

    @classmethod
    def from_store(cls, config, rows):
        syntax: TypeMixfix_RawAST | None = rows.get("syntax")
        rep: str | None = rows.get("rep_function_name")
        abs_: str | None = rows.get("abs_function_name")
        return cls(config.parent, config.state, rows.get("english"), type_parameters_of(rows.get("type_parameters")),
                   rows.get("type_name"), mixfix_of(syntax) if syntax is not None else None,
                   IsaTerm.from_agent(rows.get("set")), IsaTerm.from_agent(rep) if rep is not None else None,
                   IsaTerm.from_agent(abs_) if abs_ is not None else None, rows.get("lifting"))

    # --- evaluation (§6)

    def goal_structure(self) -> Any:
        """§4: the type parameters with their sorts and `set`, each `IsaTerm`
        as its `ascii` — what the goal `∃x. x ∈ S` is made of."""
        return (type_parameters_wire(self.type_parameters), self.set.ascii)

    def message(self) -> Any:
        """What `TAT.Typedef.evaluate` unpacks: the definition — `type_name`,
        the syntax as `mixfix_wire` writes it, the two function names with
        the defaults filled in, then the goal structure —, and the recorded
        `lifting`, None for one to be decided (§6; COMMON.md §5)."""
        rep, abs_ = function_names(self.rep_function_name, self.abs_function_name, self.name, _DEFAULT_PREFIXES)
        return (self.name, mixfix_wire(self.syntax), rep.ascii, abs_.ascii, *self.goal_structure()), self.lifting

    def record_from_evaluation(self, what):
        """§6: `lifting`, what `after_admission` yielded (`open_goal` yields
        nothing); the notice exactly when lifting is not set up."""
        _, self.lifting = what
        return () if self.lifting else (IsaTerm.from_agent(LIFTING_NOTICE),)

    def owing_line(self):
        """§7: what the node owes, while its line reads `unverified
        definition`."""
        return OWING_LINE if unverified(self) else None

    def failed_assertion(self, shown_id):
        """§7: what the failure block and the notification say was not proved."""
        return f"`{shown_id}`'s definitional set is non-empty"

    # --- what it prints (§8) and emission (§5)

    def _definition(self, keywords: Container[str]) -> tuple[str, str | None]:
        """The text after the command — the head by `type_head_text`, `=`
        and the set, each piece of text through `print_name` against
        `keywords` (the theory's for the file, none under `recall`) — and
        beside it the `morphisms` clause by the shared writer, None when
        neither function name was given."""
        head = type_head_text(self.type_parameters, self.name, self.syntax, keywords)
        morphisms = morphisms_clause(self.rep_function_name, self.abs_function_name, self.name, _DEFAULT_PREFIXES,
                                     keywords)
        return f"{head} = {print_name(self.set, keywords)}", morphisms

    def print_fields(self, indent, out, mode, depth):
        """Under `Recall` alone (§8): the definition on one line at depths 0
        to 2, against no keyword; `english` at 0."""
        if mode is RECALL and depth <= 2:
            out.write(INDENT * indent + " ".join(filter(None, self._definition(()))) + "\n")
        if mode is RECALL and depth == 0:
            out.write(INDENT * indent + self.english + "\n")

    def emit(self, indent, out):
        """§5: the `text` line; the command, the `morphisms` line and the
        terminal proof under it; then `setup_lifting` when the recorded
        `lifting` is true."""
        assert self.lifting is not None     # a node written is one an evaluation recorded (`can_emit`)
        emit_lines(indent, out, text_line(self.english))
        keywords = self.theory().keywords or ()
        definition, morphisms = self._definition(keywords)
        lines = [f"{self.kind} {definition}"]
        if morphisms is not None:
            lines.append(f"  {morphisms}")
        lines.append(f"  {self.proof_text()}")
        if self.lifting:
            lines.append(f"setup_lifting {print_name(f'type_definition_{self.name}', keywords)}")
        emit_lines(indent, out, "\n".join(lines))
        return indent
