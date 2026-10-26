"""The statement (node_classes/THEOREM.md §2, §3; COMMON.md §4): the schema
definitions `Variable` and `LongStatement`, TAT's copy of AoA's
(contrib/Isa-Mini/IsaMini/AoA/tools/cc_edit.jsonc) with the descriptions
of THEOREM.md §3, which every class stating something shares, so that the
`edit` schema merges one definition (PLUGIN_SYSTEM §5); the argument
declarations a `gen` reads them through; `Statement`, what a node keeps
of one, with its reader, which judges nothing, and its check under the
field's path — `statement` for a `Theorem`, `assumes[i].statement` for
a `Locale`'s axiom —; the reader and the check of a `for_any` list,
which `Inductive` shares; and the proposition `Theorem` prints under
`recall`."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any, NotRequired, TypedDict

from Isabelle_RPC_Host.unicode import IsaTerm

from ..model import JSON_Schema
from .common import TERM_DESCRIPTION, TYPE_DESCRIPTION, check_identifier, normalised

STATEMENT_DEFS: dict[str, JSON_Schema] = {
    "Variable": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "type": {"type": "string", "description": TYPE_DESCRIPTION},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    "LongStatement": {
        "type": "object",
        "properties": {
            "english": {"type": "string", "description": "the statement in English, as LaTeX text"},
            "for_any": {"type": "array", "items": {"$ref": "#/$defs/Variable"},
                        "description": "universally quantified variables to fix"},
            "premises": {"type": "array",
                         "items": {"type": "object",
                                   "properties": {"name": {"type": "string",
                                                           "description": "binding name for the premise"},
                                                  "term": {"type": "string", "description": TERM_DESCRIPTION}},
                                   "required": ["name", "term"],
                                   "additionalProperties": False},
                         "description": "named premises to assume"},
            "conclusion": {"type": "string", "description": TERM_DESCRIPTION},
        },
        "required": ["english", "conclusion"],
        "additionalProperties": False,
    },
}

_RULE_SYMBOLS = ("⋀", "⟹", "\\<And>", "\\<Longrightarrow>")   # what a part is parenthesised for (THEOREM.md §8)


class Variable_RawAST(TypedDict):
    name: str
    type: NotRequired[str]


class Premise_RawAST(TypedDict):
    name: str
    term: str


class LongStatement_RawAST(TypedDict):
    english: str
    for_any: NotRequired[list[Variable_RawAST]]
    premises: NotRequired[list[Premise_RawAST]]
    conclusion: str


@dataclass(frozen=True)
class Variable:
    name: IsaTerm
    type: IsaTerm | None            # None when untyped: fixed bare (THEOREM.md §5)


@dataclass(frozen=True)
class Premise:
    name: IsaTerm
    term: IsaTerm


@dataclass(frozen=True)
class Statement:
    """A `LongStatement` as the node holds it (THEOREM.md §2): every piece
    of Isabelle text an `IsaTerm`, normalised by its reader."""
    english: str
    for_any: tuple[Variable, ...]
    premises: tuple[Premise, ...]
    conclusion: IsaTerm

    def structure(self) -> Any:
        """The statement as structure, each `IsaTerm` as its `ascii`:
        `Theorem`'s `goal_structure()` (THEOREM.md §4, §6), `english` aside."""
        return ([(v.name.ascii, v.type.ascii if v.type is not None else None) for v in self.for_any],
                [(p.name.ascii, p.term.ascii) for p in self.premises],
                self.conclusion.ascii)

    def proposition(self) -> str:
        """The whole statement in Isabelle's meta form (THEOREM.md §8): one
        `⋀` per variable, `::T` when typed, one `⟹` per premise, names
        dropped, a part holding `⋀` or `⟹` itself in parentheses."""
        def part(term: IsaTerm) -> str:
            text = term.unicode
            return f"({text})" if any(s in text for s in _RULE_SYMBOLS) else text
        binders = "".join(f"⋀{v.name.unicode}{'::' + v.type.unicode if v.type is not None else ''}. "
                          for v in self.for_any)
        return binders + " ⟹ ".join([*(part(p.term) for p in self.premises), part(self.conclusion)])

    def image(self) -> dict[str, Any]:
        """The store's row, in the `unicode` spelling (THEOREM.md §2)."""
        return {"english": self.english,
                "for_any": [{"name": v.name.unicode, **({"type": v.type.unicode} if v.type is not None else {})}
                            for v in self.for_any],
                "premises": [{"name": p.name.unicode, "term": p.term.unicode} for p in self.premises],
                "conclusion": self.conclusion.unicode}

    @classmethod
    def of_image(cls, image: LongStatement_RawAST) -> Statement:
        """The reader of a statement, the construct's or a stored image's:
        its Isabelle texts normalised, `for_any` by `variables_of`, a list
        left out empty; `english` as given, which `statement_of` normalises
        for a construct.  Judges nothing."""
        return cls(image["english"], variables_of(image.get("for_any", [])),
                   tuple(Premise(IsaTerm.from_agent(normalised(p["name"])), IsaTerm.from_agent(normalised(p["term"])))
                         for p in image.get("premises", [])),
                   IsaTerm.from_agent(normalised(image["conclusion"])))


def variables_of(raw: Sequence[Variable_RawAST]) -> tuple[Variable, ...]:
    """A `for_any` list, the construct's or a stored image's, each name and
    type normalised, an empty type none (COMMON.md §4).  Judges nothing."""
    variables: list[Variable] = []
    for v in raw:
        type_ = normalised(v.get("type", ""))
        variables.append(Variable(IsaTerm.from_agent(normalised(v["name"])), IsaTerm.from_agent(type_) if type_ else None))
    return tuple(variables)


def check_variables(variables: Sequence[Variable], path: str) -> None:
    """The `for_any` check (COMMON.md §4; THEOREM.md §4), under
    `<path>.for_any[j].name`: each name an Isabelle identifier on its
    `ascii` form, not ending with an underscore, no two the same."""
    for j, v in enumerate(variables):
        check_identifier(v.name, f"{path}.for_any[{j}].name", [x.name for x in variables[:j]], in_term=True)


def statement_of(raw: LongStatement_RawAST) -> Statement:
    """The construct's statement as the node holds it (THEOREM.md §2): read
    by `Statement.of_image`, its `english` normalised.  Judges nothing."""
    return replace(Statement.of_image(raw), english=normalised(raw["english"]))


def check_statement(statement: Statement, path: str) -> None:
    """THEOREM.md §4's check of a statement under the field's `path`: its
    `for_any` by `check_variables`, then every premise's name an Isabelle
    identifier, which may end with an underscore, no two the same."""
    check_variables(statement.for_any, path)
    for i, p in enumerate(statement.premises):
        check_identifier(p.name, f"{path}.premises[{i}].name", [x.name for x in statement.premises[:i]],
                         in_term=False)
