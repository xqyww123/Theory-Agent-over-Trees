"""`Section`, the node class of the plugin `Isabelle_Std` for the six heading
commands, `chapter` down to `subparagraph` (node_classes/SECTION_AND_TEXT.md):
a heading of the theory's document with the declarations under it.  No
Isabelle scope, no proof obligation, no jobs, no `english`, no ML half: the
level rule is its `cannot_hold`, and the beginning passes the state
through."""

from __future__ import annotations

from typing import Literal, TypedDict

from ..exceptions import InvalidField
from ..model import READY_CLEAN, THEORY_CHILDREN_HEADER, StdBlock, emit_lines
from ..plugin import TAT_node
from ..prose import document_cartouche
from .common import normalised

KINDS = ("chapter", "section", "subsection", "subsubsection", "paragraph", "subparagraph")   # from the top level down
_LEVEL = {kind: level for level, kind in enumerate(KINDS)}
USE_A_LOWER_LEVEL = "Use a lower level, or move it out."     # §6's remedy


class Section_RawAST(TypedDict):
    kind: Literal["chapter", "section", "subsection", "subsubsection", "paragraph", "subparagraph"]
    name: str
    title: str


@TAT_node
class Section(StdBlock):
    construct_schema = {
        "type": "object",
        "description": "a heading of the theory's document, with the declarations under it",
        "properties": {
            "kind": {"type": "string", "enum": list(KINDS)},
            "name": {"type": "string", "description": "the name used in the node's id"},
            "title": {"type": "string", "description": "the heading, in English"},
            "children": {"type": "array", "items": {"$ref": "#/$defs/Construct"},
                         "description": "the declarations under the heading"},
        },
        "required": ["kind", "name", "title"],
        "additionalProperties": False,
    }
    argument_schema = Section_RawAST
    output_omissible = input_omissible = True
    drop_priority = 0                       # the first component to go (§9)

    name: str                               # in the framework's name grammar, judged by `edit` (§4)
    title: str                              # normalised (§2)

    def __init__(self, parent, state, name: str, title: str):
        super().__init__(parent, state)
        self.name = name
        self.title = title

    @classmethod
    async def gen(cls, config, raw: Section_RawAST):
        """§4: `title` with its whitespace normalised (§2); `name` is the
        framework's to judge."""
        return cls(config.parent, config.state, raw["name"], normalised(raw["title"]))

    def check_fields(self):
        """§4's field check: `title` not empty."""
        if not self.title:
            raise InvalidField("title", "must not be empty")

    def to_store(self, rows):
        rows.put("name", self.name)
        rows.put("title", self.title)

    @classmethod
    def from_store(cls, config, rows):
        return cls(config.parent, config.state, rows.get("name"), rows.get("title"))

    # --- evaluation (§6): no command runs

    def cannot_hold(self, descendant, depth) -> str | None:
        """§6's level rule: a heading of the same or a higher level, at any
        depth."""
        if isinstance(descendant, Section) and _LEVEL[descendant.kind] <= _LEVEL[self.kind]:
            return USE_A_LOWER_LEVEL
        return None

    async def _eval_beginning_opr(self):
        """The input slot copied into the beginning's resulting slot."""
        input_slot, resulting_slot = self.operation_slots("beginning")
        await input_slot.copy_to(resulting_slot)
        return READY_CLEAN

    # --- what it prints (§8) and emission (§5)

    def caption(self, mode, depth):
        """The title where the node is detailed (PRINT.md §1)."""
        return self.title if self.detailed(mode, depth) else None

    def children_header(self):
        """§8: `Theory`'s phrase (SESSION_AND_THEORY §4)."""
        return THEORY_CHILDREN_HEADER

    def emit_beginning(self, indent, out):
        """§5: the heading command; one empty line when the heading has
        children — the framework writes the empty lines between siblings."""
        emit_lines(indent, out, f"{self.kind} {document_cartouche(self.title)}")
        if self.sub_nodes:
            out.write("\n")
        return indent
