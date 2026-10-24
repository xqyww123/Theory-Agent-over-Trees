"""`Theorem`, the first node class of the plugin `Isabelle_Std`
(node_classes/THEOREM.md): a fact stated and admitted, never proved in
the tree — a `Proof_Obligation` (COMMON.md §3), whose evaluation opens
the goal and admits it, whose proof construction finds a proof and whose
proof check replays it, the emitted theory carrying `by aoa`."""

from __future__ import annotations

from typing import Literal, TypedDict

from ..model import INDENT, RECALL, Leaf, Placement, Theory, emit_lines
from ..plugin import TAT_node
from .common import Proof_Obligation, require_id_name, text_line
from .statement import STATEMENT_DEFS, LongStatement_RawAST, Statement, statement_of

KINDS = ("lemma", "theorem", "corollary", "proposition")   # the Isar commands Isabelle treats alike


class Theorem_RawAST(TypedDict):
    kind: Literal["lemma", "theorem", "corollary", "proposition"]
    name: str
    statement: LongStatement_RawAST


@TAT_node
class Theorem(Proof_Obligation, Leaf):
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
    placement = Placement(within="Theory", through=("Typedef", "QuotientType", "LiftingContext"))
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
        require_id_name(raw["name"], "fact name")
        return cls(config.parent, config.state, raw["name"], statement_of(raw["statement"], "statement"))

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

    def refutation_sentence(self, shown_id):
        """§7: what the failure block and the notification say when the
        agent refuted the statement."""
        return f"`{shown_id}` may not hold"

    # --- what it prints (§8)

    def print_fields(self, indent, out, mode, depth):
        """Under `Recall` alone (§8): the proposition at depths 0 to 2,
        `english` at 0 and 1."""
        if mode is RECALL and depth <= 2:
            out.write(INDENT * indent + self.statement.proposition() + "\n")
        if mode is RECALL and depth <= 1:
            out.write(INDENT * indent + self.statement.english + "\n")
        return False

    # --- emission (§5)

    def emit(self, indent, out):
        emit_lines(indent, out, text_line(self.statement.english, f"{self.kind.capitalize()} {self.name}."))
        print_name = self.enclosing(Theory).print_name   # every piece of Isabelle text through it (§5)
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
