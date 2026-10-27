"""`Text`, the node class of the plugin `Isabelle_Std` for `text`
(node_classes/SECTION_AND_TEXT.md): a passage of prose in the theory's
document.  No proof obligation, no jobs, no `english`, no ML half: its one
operation passes the state through."""

from __future__ import annotations

from typing import Literal, TypedDict

from ..exceptions import InvalidField
from ..model import READY_CLEAN, RECALL, Leaf, emit_lines
from ..plugin import TAT_node
from ..prose import document_cartouche

KINDS = ("text",)


class Text_RawAST(TypedDict):
    kind: Literal["text"]
    name: str
    text: str


@TAT_node
class Text(Leaf):
    construct_schema = {
        "type": "object",
        "description": "a passage of prose in the theory's document",
        "properties": {
            "kind": {"const": "text"},
            "name": {"type": "string", "description": "the name used in the node's id"},
            "text": {"type": "string", "description": "the passage, in English"},
        },
        "required": ["kind", "name", "text"],
        "additionalProperties": False,
    }
    argument_schema = Text_RawAST

    name: str                               # in the framework's name grammar, judged by `edit` (§4)
    text: str                               # as written (§2)

    def __init__(self, parent, state, name: str, text: str):
        super().__init__(parent, state)
        self.name = name
        self.text = text

    @classmethod
    async def gen(cls, config, raw: Text_RawAST):
        """§4: `text` as written, with some character but whitespace left;
        `name` is the framework's to judge."""
        if not raw["text"].strip():
            raise InvalidField("text", "must not be empty")
        return cls(config.parent, config.state, raw["name"], raw["text"])

    def to_store(self, rows):
        rows.put("name", self.name)
        rows.put("text", self.text)

    @classmethod
    def from_store(cls, config, rows):
        return cls(config.parent, config.state, rows.get("name"), rows.get("text"))

    # --- evaluation (§6): no command runs

    async def _eval_opr(self):
        input_slot, resulting_slot = self.operation_slots(None)
        await input_slot.copy_to(resulting_slot)
        return READY_CLEAN

    # --- what it prints (§8) and emission (§5)

    def print_fields(self, indent, out, mode, depth):
        """Under `Recall` at depths 0 and 1: the text, every line at
        `indent`, as stored but for its trailing line breaks, which it
        drops; no key."""
        if mode is RECALL and depth <= 1:
            emit_lines(indent, out, self.text.rstrip("\n"))
        return False

    def emit(self, indent, out):
        emit_lines(indent, out, f"text {document_cartouche(self.text, lists=True)}")
        return indent
