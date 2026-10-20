"""`LiftDefinition`, the node class of the plugin `Isabelle_Std` for
`lift_definition` (node_classes/LIFT_DEFINITION.md): a function on a
subtype or a quotient type, defined from a term on its representation
type — a `Proof_Obligation` (COMMON.md §3) whose one goal is that the
term respects the representation; its evaluation records, once, whether
the command carries `(code_dt)`, which every later evaluation keeps to
(COMMON.md §5)."""

from __future__ import annotations

from collections.abc import Container
from typing import Any, Literal, NotRequired, TypedDict

from Isabelle_RPC_Host.unicode import IsaTerm

from ..model import INDENT, RECALL, Leaf, Placement, Theory, emit_lines, print_name
from ..plugin import TAT_node
from .common import (
    MIXFIX_DEFS, Mixfix, Mixfix_RawAST, Proof_Obligation, mixfix_of, mixfix_text, mixfix_wire,
    normalised, require_id_name, text_line, unverified)

KINDS = ("lift_definition",)
OWING_LINE = "The definition is unverified until the term is proven to respect the representation."    # §7

# §2's fields in its order, in TypedDict's functional form: no class body can declare the key `is`, a keyword
LiftDefinition_RawAST = TypedDict("LiftDefinition_RawAST", {
    "kind": Literal["lift_definition"],
    "english": str,
    "name": str,
    "type": str,
    "syntax": NotRequired[Mixfix_RawAST],
    "is": str,
    "code_dt": NotRequired[bool],
})


@TAT_node
class LiftDefinition(Proof_Obligation, Leaf):
    construct_schema = {
        "type": "object",
        "description": "defines a function on a subtype or a quotient type from a term on its representation type; its"
                       " proof obligation, which the proof construction proves, is that the term respects the subtype's"
                       " defining set or the quotient type's equivalence relation. Example: lift_definition dl_rev ::"
                       " \"'a dlist ⇒ 'a dlist\" is rev, reversal on the subtype 'a dlist of lists without repetition,"
                       " with the obligation distinct xs ⟹ distinct (rev xs); placed inside the quotient_type or typedef"
                       " that defines the type, or inside a lifting_context that opens it",
        "properties": {
            "kind": {"const": "lift_definition"},
            "english": {"type": "string", "description": "what is defined, in English, as LaTeX text"},
            "name": {"type": "string"},
            "type": {"type": "string",
                     "description": "the type of the function, on the subtype or quotient type. Example: 'a dlist ⇒ 'a dlist"},
            "syntax": {"$ref": "#/$defs/Mixfix"},
            "is": {"type": "string",
                   "description": "the term on the representation type the function is defined from. Example: rev"},
            "code_dt": {"type": "boolean",
                        "description": "whether to declare the function's code generation rule by its representation type"},
        },
        "required": ["kind", "english", "name", "type", "is"],
        "additionalProperties": False,
        "$defs": {**MIXFIX_DEFS},
    }
    argument_schema = LiftDefinition_RawAST
    placement = Placement(within="Theory", through=("QuotientType", "LiftingContext"))
    evaluation_callback = "TAT.LiftDefinition.evaluate"
    valid_word, invalid_word = "valid definition", "invalid definition"     # the mark's first slot (§7) ...
    unverified_word = "unverified definition"                               # ... while the proof is owed

    english: str
    type: IsaTerm
    syntax: Mixfix | None
    is_: IsaTerm                    # the field `is`, a Python keyword
    code_dt: bool
    with_code_dt: bool | None       # recorded by the first evaluation that goes through and kept to by the later
                                    # ones, None until one has (§1, §6)

    def __init__(self, parent, state, english: str, name: str, type: IsaTerm, syntax: Mixfix | None, is_: IsaTerm,
                 code_dt: bool, with_code_dt: bool | None = None):
        super().__init__(parent, state)
        self.english = english
        self.name = name                        # the node's and the function's (§1)
        self.type = type
        self.syntax = syntax
        self.is_ = is_
        self.code_dt = code_dt
        self.with_code_dt = with_code_dt

    @classmethod
    async def gen(cls, config, raw: LiftDefinition_RawAST):
        """§4's check: `name` against §1's grammar.  The rest is Isabelle's
        at evaluation."""
        require_id_name(raw["name"], "constant name")
        return cls(config.parent, config.state, normalised(raw["english"]), raw["name"],
                   IsaTerm.from_agent(normalised(raw["type"])), mixfix_of(raw["syntax"]) if "syntax" in raw else None,
                   IsaTerm.from_agent(normalised(raw["is"])), raw.get("code_dt", False))

    # --- the store (§1): the authored fields in the `unicode` spelling and the recorded one, `syntax` left out and
    #     `with_code_dt` not yet recorded each a None-valued row; every row read with `get`, so that a missing one is
    #     refused at start

    def to_store(self, rows):
        rows.put("english", self.english)
        rows.put("name", self.name)
        rows.put("type", self.type.unicode)
        rows.put("syntax", self.syntax.image() if self.syntax is not None else None)
        rows.put("is", self.is_.unicode)
        rows.put("code_dt", self.code_dt)
        rows.put("with_code_dt", self.with_code_dt)

    @classmethod
    def from_store(cls, config, rows):
        syntax: Mixfix_RawAST | None = rows.get("syntax")
        return cls(config.parent, config.state, rows.get("english"), rows.get("name"),
                   IsaTerm.from_agent(rows.get("type")), mixfix_of(syntax) if syntax is not None else None,
                   IsaTerm.from_agent(rows.get("is")), rows.get("code_dt"), rows.get("with_code_dt"))

    # --- evaluation (§6)

    def goal_structure(self) -> Any:
        """§4: `type` and `is`, each `IsaTerm` as its `ascii` — what the
        obligation is made of."""
        return (self.type.ascii, self.is_.ascii)

    def message(self) -> Any:
        """What `TAT.LiftDefinition.evaluate` unpacks: the definition — `name`,
        the syntax as `mixfix_wire` writes it, `code_dt`, then the goal
        structure — and the recorded `with_code_dt`, None for one to be
        decided (§6; COMMON.md §5)."""
        return ((self.name, mixfix_wire(self.syntax), self.code_dt, *self.goal_structure()), self.with_code_dt)

    def record_from_evaluation(self, what):
        """§6: `with_code_dt`, what `open_goal` yielded — the option the
        command ran with, as decided or as recorded —; `after_admission`
        yields nothing."""
        self.with_code_dt, _ = what
        return ()

    def owing_line(self):
        """§7: what the node waits for, while its line reads `unverified
        definition`."""
        return OWING_LINE if unverified(self) else None

    def failed_assertion(self, shown_id):
        """§7: what the failure block and the notification say was not proved."""
        return f"`{shown_id}`'s defining term respects the representation"

    def refutation_sentence(self, shown_id):
        """§7: what they say when the agent refuted it."""
        return f"`{shown_id}`'s defining term may not respect the representation"

    # --- what it prints (§8) and emission (§5)

    def _definition(self, keywords: Container[str]) -> str:
        """The text after the command: the name, `::`, the type, the syntax
        when given, `is` and the term — the name, the type and the term
        through `print_name` against `keywords` (the theory's for the file,
        none under `recall`), the syntax as its writer writes it."""
        return " ".join(filter(None, (print_name(self.name, keywords), "::", print_name(self.type, keywords),
                                      mixfix_text(self.syntax) if self.syntax is not None else "",
                                      "is", print_name(self.is_, keywords))))

    def print_fields(self, indent, out, mode, depth):
        """Under `Recall` alone (§8): the definition on one line at depths 0
        to 2, against no keyword, `(code_dt)` before it at depth 0 when the
        authored `code_dt` is true; `english` at 0."""
        if mode is RECALL and depth <= 2:
            option = "(code_dt) " if depth == 0 and self.code_dt else ""
            out.write(INDENT * indent + option + self._definition(()) + "\n")
        if mode is RECALL and depth == 0:
            out.write(INDENT * indent + self.english + "\n")

    def emit(self, indent, out):
        """§5: the `text` line; then the command, `(code_dt)` when the recorded
        `with_code_dt` is true, the definition and the terminal proof on one
        line."""
        assert self.with_code_dt is not None        # a node written is one an evaluation recorded (`can_emit`)
        emit_lines(indent, out, text_line(self.english))
        keywords = self.enclosing(Theory).keywords or ()
        command = f"{self.kind} (code_dt)" if self.with_code_dt else self.kind
        emit_lines(indent, out, f"{command} {self._definition(keywords)} {self.proof_text()}")
        return indent
