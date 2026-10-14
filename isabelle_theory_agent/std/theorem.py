"""`Theorem`, the first node class of the plugin `Isabelle_Std`
(node_classes/THEOREM.md): a fact stated and admitted, never proved in
the tree — a `Proof_Obligation` (COMMON.md §3), whose evaluation opens
the goal and admits it, whose proof construction finds a proof and whose
proof check replays it, the emitted theory carrying `by aoa`."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from Isabelle_RPC_Host.unicode import IsaTerm, is_identifier

from ..exceptions import GRAMMARS, InvalidField, InvalidName
from ..model import INDENT, RECALL, Leaf, emit_lines
from ..plugin import TAT_node
from .common import Proof_Obligation, Theory_Member, text_line
from .statement import STATEMENT_DEFS, LongStatement_RawAST

KINDS = ("lemma", "theorem", "corollary", "proposition")   # the Isar commands Isabelle treats alike
_FACT_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_']*")        # the id grammar without hyphens (§1)
_RULE_SYMBOLS = ("⋀", "⟹", "\\<And>", "\\<Longrightarrow>")   # what a part is parenthesised for (§8)


class Theorem_RawAST(TypedDict):
    kind: Literal["lemma", "theorem", "corollary", "proposition"]
    name: str
    statement: LongStatement_RawAST


@dataclass(frozen=True)
class Variable:
    name: IsaTerm
    type: IsaTerm | None            # None when untyped: fixed bare (§5)


@dataclass(frozen=True)
class Premise:
    name: IsaTerm
    term: IsaTerm


@dataclass(frozen=True)
class Statement:
    """A `LongStatement` as the node holds it (§2): every piece of Isabelle
    text an `IsaTerm`, the texts normalised once by `gen`."""
    english: str
    for_any: tuple[Variable, ...]
    premises: tuple[Premise, ...]
    conclusion: IsaTerm

    def structure(self) -> Any:
        """The statement as structure, each `IsaTerm` as its `ascii`:
        `Theorem`'s `goal_structure()` (§4, §6), `english` aside."""
        return ([(v.name.ascii, v.type.ascii if v.type is not None else None) for v in self.for_any],
                [(p.name.ascii, p.term.ascii) for p in self.premises],
                self.conclusion.ascii)

    def proposition(self) -> str:
        """The whole statement in Isabelle's meta form (§8): one `⋀` per
        variable, `::T` when typed, one `⟹` per premise, names dropped, a
        part holding `⋀` or `⟹` itself in parentheses."""
        def part(term: IsaTerm) -> str:
            text = term.unicode
            return f"({text})" if any(s in text for s in _RULE_SYMBOLS) else text
        binders = "".join(f"⋀{v.name.unicode}{'::' + v.type.unicode if v.type is not None else ''}. "
                          for v in self.for_any)
        return binders + " ⟹ ".join([*(part(p.term) for p in self.premises), part(self.conclusion)])

    def image(self) -> dict[str, Any]:
        """The store's row, in the `unicode` spelling (§2)."""
        return {"english": self.english,
                "for_any": [{"name": v.name.unicode, **({"type": v.type.unicode} if v.type is not None else {})}
                            for v in self.for_any],
                "premises": [{"name": p.name.unicode, "term": p.term.unicode} for p in self.premises],
                "conclusion": self.conclusion.unicode}

    @classmethod
    def of_image(cls, image: dict[str, Any]) -> Statement:
        return cls(image["english"],
                   tuple(Variable(IsaTerm.from_agent(v["name"]),
                                  IsaTerm.from_agent(v["type"]) if "type" in v else None)
                         for v in image["for_any"]),
                   tuple(Premise(IsaTerm.from_agent(p["name"]), IsaTerm.from_agent(p["term"]))
                         for p in image["premises"]),
                   IsaTerm.from_agent(image["conclusion"]))


def _normalised(text: str) -> str:
    """Newlines spaces, runs of whitespace one space (§2)."""
    return " ".join(text.split())


@TAT_node
class Theorem(Theory_Member, Proof_Obligation, Leaf):
    construct_schema = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": list(KINDS)},
            "name": {"type": "string"},
            "statement": {"$ref": "#/$defs/LongStatement"},
        },
        "required": ["kind", "name", "statement"],
        "additionalProperties": False,
        "$defs": STATEMENT_DEFS,
    }
    argument_schema = Theorem_RawAST
    evaluation_callback = "TAT.Theorem.evaluate"
    valid_word, invalid_word = "valid statement", "invalid statement"       # the mark's first slot (§7)

    name: str
    statement: Statement

    def __init__(self, parent, state, name: str, statement: Statement):
        super().__init__(parent, state)
        self.name = name
        self.statement = statement

    @classmethod
    async def gen(cls, config, raw: Theorem_RawAST):
        cls.require_inside_theory(config, raw["kind"])
        name = raw["name"]
        if not _FACT_NAME.fullmatch(name) or name.endswith("_"):
            raise InvalidName(name, "fact name")
        return cls(config.parent, config.state, name, _statement_of(raw["statement"]))

    def to_store(self, rows):
        rows.put("name", self.name)
        rows.put("statement", self.statement.image())

    @classmethod
    def from_store(cls, config, rows):
        return cls(config.parent, config.state, rows.get("name"), Statement.of_image(rows.get("statement")))

    def goal_structure(self):
        return self.statement.structure()

    def message(self):
        """`kind`, `name` and the goal structure, as `TAT.Theorem.evaluate`
        unpacks them (§6)."""
        return (self.kind, self.name, *self.goal_structure())

    # --- what it prints (§8)

    def print_fields(self, indent, out, mode, depth):
        """Under `Recall` alone (§8): the proposition at depths 0 to 2,
        `english` at 0 and 1."""
        if mode is RECALL and depth <= 2:
            out.write(INDENT * indent + self.statement.proposition() + "\n")
        if mode is RECALL and depth <= 1:
            out.write(INDENT * indent + self.statement.english + "\n")

    # --- emission (§5)

    def emit(self, indent, out):
        emit_lines(indent, out, text_line(self.statement.english, f"{self.kind.capitalize()} {self.name}."))
        print_name = self.theory().print_name               # every piece of Isabelle text through it (§5)
        lines = [f"{self.kind} {print_name(self.name)}:"]
        if self.statement.for_any:
            lines.append("  fixes " + " and ".join(
                print_name(v.name) + (f" :: {print_name(v.type)}" if v.type is not None else "")
                for v in self.statement.for_any))
        if self.statement.premises:
            lines.append("  assumes " + " and ".join(
                f"{print_name(p.name)}: {print_name(p.term)}" for p in self.statement.premises))
        lines.append(f"  shows {print_name(self.statement.conclusion)}")
        lines.append("  " + self.proof_text())
        emit_lines(indent, out, "\n".join(lines))
        return indent


def _statement_of(raw: LongStatement_RawAST) -> Statement:
    """The construct's statement, normalised (§2) and checked (§4): every
    variable's and premise's name an Isabelle identifier on its `ascii`
    form, a variable's not ending with an underscore, no two of either the
    same."""
    variables: list[Variable] = []
    for i, v in enumerate(raw.get("for_any", [])):
        name = IsaTerm.from_agent(v["name"])
        _check_name(name, f"statement.for_any[{i}].name", [x.name for x in variables], variable=True)
        type_ = _normalised(v.get("type", ""))
        variables.append(Variable(name, IsaTerm.from_agent(type_) if type_ else None))
    premises: list[Premise] = []
    for i, p in enumerate(raw.get("premises", [])):
        name = IsaTerm.from_agent(p["name"])
        _check_name(name, f"statement.premises[{i}].name", [x.name for x in premises], variable=False)
        premises.append(Premise(name, IsaTerm.from_agent(_normalised(p["term"]))))
    return Statement(_normalised(raw["english"]), tuple(variables), tuple(premises),
                     IsaTerm.from_agent(_normalised(raw["conclusion"])))


def _check_name(name: IsaTerm, field: str, earlier: list[IsaTerm], *, variable: bool) -> None:
    if not is_identifier(name.ascii) or (variable and name.ascii.endswith("_")):
        raise InvalidField(field, f"must be an Isabelle identifier: it {GRAMMARS['fact name']}")
    if any(e.ascii == name.ascii for e in earlier):
        raise InvalidField(field, f"binds `{name.unicode}` a second time")
