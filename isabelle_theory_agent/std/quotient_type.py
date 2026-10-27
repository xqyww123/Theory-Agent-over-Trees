"""`QuotientType`, the node class of the plugin `Isabelle_Std` for
`quotient_type` (node_classes/QUOTIENT_TYPE.md): a quotient type — a new
type whose values are the equivalence classes of an existing type under
an equivalence relation, with a function each way between the two — a
block whose beginning is the command, a `Beginning_Proof_Obligation`
(COMMON.md §3) whose one goal is that the relation is an equivalence,
whose children are the type's `lift_definition`s and the lemmas proved
by `transfer`, and whose ending, `Lifting_Closing`'s (COMMON.md §6),
closes the type's Lifting setup."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, NotRequired, TypedDict

from Isabelle_RPC_Host.unicode import IsaTerm

from ..model import INDENT, RECALL, Theory, emit_lines, print_name
from ..plugin import TAT_node
from .common import (
    LIFTING_CHILDREN_DESCRIPTION, TYPE_MIXFIX_DEFS, Beginning_Proof_Obligation, Lifting_Closing, Type_Parameter,
    TypeMixfix, TypeMixfix_RawAST, check_function_names, check_type_parameters, check_type_parameters_used,
    function_names, function_names_of, mixfix_of, mixfix_wire, morphisms_clause, normalised, require_id_name,
    text_line, type_head_text, type_variables_of, unverified)

KINDS = ("quotient_type",)
OWING_LINE = "The definition is unverified until the relation is proven an equivalence."                   # §7
OWING_LINE_PARTIAL = "The definition is unverified until the relation is proven a partial equivalence."   # §7
_DEFAULT_PREFIXES = ("rep_", "abs_")    # before the type's name: the Rep and the Abs function names left out (§2)


class QuotientType_RawAST(TypedDict):
    kind: Literal["quotient_type"]
    english: str
    type_parameters: NotRequired[list[str]]
    type_name: str
    syntax: NotRequired[TypeMixfix_RawAST]
    representation_type: str
    equiv_relation: str
    partial: NotRequired[bool]
    rep_function_name: NotRequired[str]
    abs_function_name: NotRequired[str]


@TAT_node
class QuotientType(Beginning_Proof_Obligation, Lifting_Closing):
    construct_schema = {
        "type": "object",
        "description": "defines a quotient type whose values are the equivalence classes of an existing type under"
                       " an equivalence relation. Example: quotient_type 'a fset = \"'a list\" /"
                       " \"λxs ys. set xs = set ys\"",
        "properties": {
            "kind": {"const": "quotient_type"},
            "english": {"type": "string", "description": "what is defined, in English"},
            "type_parameters": {"type": "array", "items": {"type": "string"},
                                "description": "the parameters of the quotient type, each a type variable such as 'a;"
                                               " a sort constraint is written inside representation_type, as in"
                                               " \"'a :: idom × 'a\""},
            "type_name": {"type": "string"},
            "syntax": {"$ref": "#/$defs/TypeMixfix"},
            "representation_type": {"type": "string", "description": "e.g., \"'a list\" in the above example"},
            "equiv_relation": {"type": "string",
                               "description": "e.g., \"λxs ys. set xs = set ys\" in the above example"},
            "partial": {"type": "boolean",
                        "description": "whether the relation is only a partial equivalence, proved as part_equivp"
                                       " instead of equivp; false when left out"},
            "rep_function_name": {"type": "string",
                                  "description": "the name of the function that sends a value of the quotient type to"
                                                 " one of its representatives in the existing type; rep_ followed by"
                                                 " the type name when left out. Example: list_of_fset"},
            "abs_function_name": {"type": "string",
                                  "description": "the name of the function that sends a value of the existing type to"
                                                 " its equivalence class, a value of the quotient type; abs_ followed"
                                                 " by the type name when left out. Example: fset_of_list"},
            "children": {"type": "array", "items": {"$ref": "#/$defs/Construct"},
                         "description": LIFTING_CHILDREN_DESCRIPTION},
        },
        "required": ["kind", "english", "type_name", "representation_type", "equiv_relation"],
        "additionalProperties": False,
        "$defs": {**TYPE_MIXFIX_DEFS},
    }
    argument_schema = QuotientType_RawAST
    evaluation_callback = "TAT.QuotientType.evaluate"
    valid_word, invalid_word = "valid definition", "invalid definition"     # the mark's first slot (§7) ...
    unverified_word = "unverified definition"                               # ... while the proof is owed
    output_omissible = input_omissible = True
    drop_priority = 1                       # after `Section`'s, with `Session`'s, before `Theory`'s (§9)

    english: str
    type_parameters: tuple[Type_Parameter, ...]     # without a sort (§1)
    syntax: TypeMixfix | None
    representation_type: IsaTerm
    equiv_relation: IsaTerm
    partial: bool
    rep_function_name: IsaTerm | None       # None when left out: Isabelle's default, `rep_` before the name (§2)
    abs_function_name: IsaTerm | None       # likewise, `abs_`

    def __init__(self, parent, state, english: str, type_parameters: tuple[Type_Parameter, ...], type_name: str,
                 syntax: TypeMixfix | None, representation_type: IsaTerm, equiv_relation: IsaTerm, partial: bool,
                 rep_function_name: IsaTerm | None, abs_function_name: IsaTerm | None):
        super().__init__(parent, state)
        self.english = english
        self.type_parameters = type_parameters
        self.name = type_name                   # the node's name (§1)
        self.syntax = syntax
        self.representation_type = representation_type
        self.equiv_relation = equiv_relation
        self.partial = partial
        self.rep_function_name = rep_function_name
        self.abs_function_name = abs_function_name

    @classmethod
    async def gen(cls, config, raw: QuotientType_RawAST):
        """§4: `type_name` against §1's grammar; the rest read."""
        require_id_name(raw["type_name"], "type name")
        return cls(config.parent, config.state, normalised(raw["english"]),
                   type_variables_of(raw.get("type_parameters", [])), raw["type_name"],
                   mixfix_of(raw["syntax"]) if "syntax" in raw else None,
                   IsaTerm.from_agent(normalised(raw["representation_type"])),
                   IsaTerm.from_agent(normalised(raw["equiv_relation"])), raw.get("partial", False),
                   *function_names_of(raw.get("rep_function_name"), raw.get("abs_function_name")))

    def check_fields(self):
        """§4's field check in its order: the type parameters by the shared
        check over bare type variables; each used in
        `representation_type`; the two function names by the shared check
        of the pair."""
        check_type_parameters(self.type_parameters, "")
        check_type_parameters_used(self.type_parameters, (self.representation_type,))
        check_function_names(self.rep_function_name, self.abs_function_name)

    # --- the store (§1): the authored fields in the `unicode` spelling, a field left out a None-valued row and
    #     `partial` false; every row read with `get`, so that a missing one is refused at start

    def to_store(self, rows):
        rows.put("english", self.english)
        rows.put("type_parameters", [p.name.unicode for p in self.type_parameters])
        rows.put("type_name", self.name)
        rows.put("syntax", self.syntax.image() if self.syntax is not None else None)
        rows.put("representation_type", self.representation_type.unicode)
        rows.put("equiv_relation", self.equiv_relation.unicode)
        rows.put("partial", self.partial)
        rows.put("rep_function_name", self.rep_function_name.unicode if self.rep_function_name is not None else None)
        rows.put("abs_function_name", self.abs_function_name.unicode if self.abs_function_name is not None else None)

    @classmethod
    def from_store(cls, config, rows):
        syntax: TypeMixfix_RawAST | None = rows.get("syntax")
        return cls(config.parent, config.state, rows.get("english"), type_variables_of(rows.get("type_parameters")),
                   rows.get("type_name"), mixfix_of(syntax) if syntax is not None else None,
                   IsaTerm.from_agent(rows.get("representation_type")), IsaTerm.from_agent(rows.get("equiv_relation")),
                   rows.get("partial"), *function_names_of(rows.get("rep_function_name"), rows.get("abs_function_name")))

    # --- evaluation (§6)

    def goal_structure(self) -> Any:
        """§4: `representation_type`, `partial` and `equiv_relation`, each
        `IsaTerm` as its `ascii` — what the goal `equivp R`, or `part_equivp
        R`, is made of."""
        return (self.representation_type.ascii, self.partial, self.equiv_relation.ascii)

    def message(self) -> Any:
        """What `TAT.QuotientType.evaluate` unpacks, two parts: the authored
        fields — `type_name`, the type parameters, the syntax as
        `mixfix_wire` writes it, the two function names with the defaults
        filled in — and the goal structure whole."""
        rep, abs_ = function_names(self.rep_function_name, self.abs_function_name, self.name, _DEFAULT_PREFIXES)
        authored = (self.name, [p.name.ascii for p in self.type_parameters], mixfix_wire(self.syntax), rep.ascii,
                    abs_.ascii)
        return authored, self.goal_structure()

    def owing_line(self):
        """§7: what the node owes, while its line reads `unverified
        definition` — by `partial`, which sentence."""
        if not unverified(self):
            return None
        return OWING_LINE_PARTIAL if self.partial else OWING_LINE

    def _relation(self) -> str:
        """§7: what the relation is to be proven, by `partial`."""
        return "a partial equivalence relation" if self.partial else "an equivalence relation"

    def failed_assertion(self, shown_id):
        """§7: what the failure block and the notification say was not proved."""
        return f"`{shown_id}`'s definitional relation is {self._relation()}"

    def refutation_sentence(self, shown_id):
        """§7: what they say when the agent refuted it."""
        return f"`{shown_id}`'s definitional relation may not be {self._relation()}"

    # --- what it prints (§8) and emission (§5)

    def _definition(self, write: Callable[[str | IsaTerm], str]) -> tuple[str, str | None]:
        """The text after the command — the head by `type_head_text`, `=`,
        the representation type, `/`, `partial:` when `partial`, and the
        relation, each piece of text through `write` (the theory's
        `print_name` for the file, the module-level one under `recall`) — and
        beside it the `morphisms` clause by the shared writer, None when
        neither function name was given."""
        head = type_head_text(self.type_parameters, self.name, self.syntax, write)
        parts = [head, "=", write(self.representation_type), "/"]
        if self.partial:
            parts.append("partial:")
        parts.append(write(self.equiv_relation))
        morphisms = morphisms_clause(self.rep_function_name, self.abs_function_name, self.name, _DEFAULT_PREFIXES,
                                     write)
        return " ".join(parts), morphisms

    def print_fields(self, indent, out, mode, depth):
        """Under `Recall` alone (§8): the definition on one line at depths 0
        to 2, against no keyword; `english` at 0; no line keyed."""
        if mode is RECALL and depth <= 2:
            out.write(INDENT * indent + " ".join(filter(None, self._definition(print_name))) + "\n")
        if mode is RECALL and depth == 0:
            out.write(INDENT * indent + self.english + "\n")
        return False

    def emit_beginning(self, indent, out):
        """§5: the `text` line; the command, the `morphisms` line and the
        terminal proof under it; one empty line when the block has children
        — the framework writes the empty lines between siblings."""
        emit_lines(indent, out, text_line(self.english))
        write = self.enclosing(Theory).print_name
        definition, morphisms = self._definition(write)
        lines = [f"{self.kind} {definition}"]
        if morphisms is not None:
            lines.append(f"  {morphisms}")
        lines.append(f"  {self.proof_text()}")
        emit_lines(indent, out, "\n".join(lines))
        if self.sub_nodes:
            out.write("\n")
        return indent
