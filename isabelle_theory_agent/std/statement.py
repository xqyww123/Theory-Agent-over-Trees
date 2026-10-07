"""The statement's schema definitions (node_classes/THEOREM.md §2, §3):
`Variable` and `LongStatement`, TAT's copy of AoA's
(contrib/Isa-Mini/IsaMini/AoA/tools/cc_edit.jsonc) with the descriptions
of §3, which every class stating something shares, so that the `edit`
schema merges one definition (PLUGIN_SYSTEM §5); and the argument
declarations a `gen` reads them through."""

from __future__ import annotations

from typing import NotRequired, TypedDict

from ..model import JSON_Schema

_TERM = "Isabelle/HOL term with all literal numbers annotated with types"

STATEMENT_DEFS: dict[str, JSON_Schema] = {
    "Variable": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "type": {"type": "string", "description": 'An Isabelle type expression. Leave empty ("") if unsure'},
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
                                                  "term": {"type": "string", "description": _TERM}},
                                   "required": ["name", "term"],
                                   "additionalProperties": False},
                         "description": "named premises to assume"},
            "conclusion": {"type": "string", "description": _TERM},
        },
        "required": ["english", "conclusion"],
        "additionalProperties": False,
    },
}


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
