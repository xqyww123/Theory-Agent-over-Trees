"""`LiftingContext`, the node class of the plugin `Isabelle_Std` for
`context includes t.lifting begin … end` (node_classes/LIFTING_CONTEXT.md):
a block that opens the Lifting setup of one or more types again, so that
inside it a `lift_definition` on an opened type defines its function and
a theorem about the type is proved by `transfer`; its ending is `end`,
then `Lifting_Closing`'s two commands (COMMON.md §6) for each type the
beginning found closed and opened — the recorded `opened` —, which close
the setups again and store the block's transfer rules into the types'
bundles.  No proof obligation, no jobs, no `english`."""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from Isabelle_RPC_Host.unicode import IsaTerm, is_identifier

from .. import isabelle_driver
from ..exceptions import GRAMMARS, InvalidField
from ..model import INDENT, NON_EMPTY, RECALL, StdBlock, emit_lines, status_of_errors
from ..plugin import TAT_node
from .common import Theory_Member, check_not_bound_twice, lifting_closing_text, normalised

KINDS = ("lifting_context",)


class LiftingContext_RawAST(TypedDict):
    kind: Literal["lifting_context"]
    name: str
    types: Annotated[list[str], NON_EMPTY]


def type_names_of(raw: list[str]) -> tuple[IsaTerm, ...]:
    """§4's check of `types`, each entry normalised and as the node holds
    it: an Isabelle identifier, or identifiers joined by dots, each part on
    its `ascii` an identifier not ending with an underscore (COMMON.md §5),
    refused on `types[i]` with §4's sentence; no two the same (COMMON.md
    §4).  A stored image is read back through it too."""
    names: list[IsaTerm] = []
    for i, text in enumerate(raw):
        name = IsaTerm.from_agent(normalised(text))
        if not all(is_identifier(part) and not part.endswith("_") for part in name.ascii.split(".")):
            raise InvalidField(f"types[{i}]", "must be a type's name: an Isabelle identifier, or identifiers joined"
                                              " by dots, each of which " + GRAMMARS["type name"])
        check_not_bound_twice(name, f"types[{i}]", names)
        names.append(name)
    return tuple(names)


@TAT_node
class LiftingContext(Theory_Member, StdBlock):
    construct_schema = {
        "type": "object",
        "description": "opens the Lifting setup of one or more subtypes (by `typedef`) or quotient types (such as fset)"
                       " again, so that lift_definition and the `transfer` tactic are available, working through the"
                       " representation of the types (the lists under fset); in Isabelle code, context includes"
                       " fset.lifting begin … end",
        "properties": {
            "kind": {"const": "lifting_context"},
            "name": {"type": "string", "description": "the block's name, by which it is referred to"},
            "types": {"type": "array", "minItems": 1, "items": {"type": "string"},
                      "description": "the types whose Lifting setup the block opens again, each by its name"},
            "children": {"type": "array", "items": {"$ref": "#/$defs/Construct"},
                         "description": "the lift_definitions on the opened types, and any other declarations whose"
                                        " proofs need transfer"},
        },
        "required": ["kind", "name", "types"],
        "additionalProperties": False,
    }
    argument_schema = LiftingContext_RawAST
    output_omissible = input_omissible = True
    drop_priority = 1                       # after `Section`'s, with `Session`'s, before `Theory`'s (§9)

    name: str                               # in the framework's name grammar, judged by `edit` (§4)
    types: tuple[IsaTerm, ...]
    opened: tuple[IsaTerm, ...] | None      # the entries of `types` the last beginning that went through found
                                            # closed and opened (§1, §6); None until one has

    def __init__(self, parent, state, name: str, types: tuple[IsaTerm, ...],
                 opened: tuple[IsaTerm, ...] | None = None):
        super().__init__(parent, state)
        self.name = name
        self.types = types
        self.opened = opened

    @classmethod
    async def gen(cls, config, raw: LiftingContext_RawAST):
        """§4: the parent, then `types` by `type_names_of`; `name` is the
        framework's to judge."""
        cls.require_inside_theory(config, raw["kind"])
        return cls(config.parent, config.state, raw["name"], type_names_of(raw["types"]))

    # --- the store (§1): `name`, `types` and the recorded `opened`, the names in the `unicode` spelling, `opened`
    #     None-valued until recorded; every row read with `get`, so that a missing one is refused at start

    def to_store(self, rows):
        rows.put("name", self.name)
        rows.put("types", [t.unicode for t in self.types])
        rows.put("opened", [t.unicode for t in self.opened] if self.opened is not None else None)

    @classmethod
    def from_store(cls, config, rows):
        opened: list[str] | None = rows.get("opened")
        return cls(config.parent, config.state, rows.get("name"), type_names_of(rows.get("types")),
                   tuple(IsaTerm.from_agent(t) for t in opened) if opened is not None else None)

    # --- evaluation (§6)

    async def _eval_beginning_opr(self):
        """`TAT.LiftingContext.open` with the beginning's two slots and `types`
        in `ascii`: its messages make the beginning an obstacle, `opened`
        untouched; none, and the entries it answers — those it opened — are
        recorded as `opened`, in `types`' order."""
        input_slot, resulting_slot = self.operation_slots("beginning")
        messages, opened = await isabelle_driver.call(
            self.forest().conversation, "TAT.LiftingContext.open",
            (input_slot.to_msgpack(), resulting_slot.to_msgpack(), [t.ascii for t in self.types]))
        if not messages:
            answered = set(opened)
            self.opened = tuple(t for t in self.types if t.ascii in answered)
        return status_of_errors(messages)

    async def _eval_ending_opr(self):
        """`TAT.LiftingContext.close` with the ending's two slots and `opened`
        in `ascii` — `end`, then the two closing commands per entry, as one
        operation —: its messages make the ending an obstacle, none is
        `Ready`."""
        assert self.opened is not None          # the ending runs after a beginning that went through
        input_slot, resulting_slot = self.operation_slots("ending")
        messages = await isabelle_driver.call(
            self.forest().conversation, "TAT.LiftingContext.close",
            (input_slot.to_msgpack(), resulting_slot.to_msgpack(), [t.ascii for t in self.opened]))
        return status_of_errors(messages)

    # --- what it prints (§8) and emission (§5)

    def _beginning_text(self) -> str:
        """§5's command on one line: `context includes`, the bundles
        `t.lifting` of the entries of `types` in their order joined by
        ` and `, `begin`; the bundle's name bare (COMMON.md §6)."""
        return "context includes " + " and ".join(f"{t.unicode}.lifting" for t in self.types) + " begin"

    def print_fields(self, indent, out, mode, depth):
        """Under `Recall` alone, at depths 0 to 2 (§8): the beginning command."""
        if mode is RECALL and depth <= 2:
            out.write(INDENT * indent + self._beginning_text() + "\n")

    def emit_beginning(self, indent, out):
        """§5: the command; one empty line when the block has children — the
        framework writes the empty lines between siblings."""
        emit_lines(indent, out, self._beginning_text())
        if self.sub_nodes:
            out.write("\n")
        return indent

    def emit_ending(self, indent, out):
        """§5: one empty line, `end`, then the two closing commands for each
        entry of `opened`, each line at the block's indent."""
        assert self.opened is not None          # a node written is one whose beginning went through (`can_emit`)
        out.write("\n")
        emit_lines(indent, out, "\n".join(["end", *(lifting_closing_text(t.unicode) for t in self.opened)]))
        return indent
