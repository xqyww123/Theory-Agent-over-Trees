"""`Inductive`, the node class of the plugin `Isabelle_Std` for predicates
defined by rules (node_classes/INDUCTIVE.md): `inductive`, the least
predicates satisfying the rules, or `coinductive`, the greatest consistent
with them; the `for` clause decided by the evaluation and recorded as
`fixed_parameters`."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from Isabelle_RPC_Host.unicode import IsaTerm

from .. import isabelle_driver
from ..exceptions import series
from ..model import INDENT, NON_EMPTY, READY_CLEAN, RECALL, Leaf, Ready, Theory, emit_lines, status_of_errors
from ..plugin import TAT_node
from .common import (
    CONSTANT_DEFS, MIXFIX_DEFS, TERM_DESCRIPTION, Variable_With_Syntax, VariableWithSyntax_RawAST,
    check_identifier, check_not_bound_twice, constants_of, english_cartouche, fixes_text, normalised, text_line)
from .statement import VARIABLE_DEFS, Variable, Variable_RawAST, check_variables, variables_of

KINDS = ("inductive", "coinductive")


class InductiveRule_RawAST(TypedDict):
    name: str
    english: str
    for_any: NotRequired[list[Variable_RawAST]]
    premises: NotRequired[list[str]]
    conclusion: str


class Inductive_RawAST(TypedDict):
    kind: Literal["inductive", "coinductive"]
    english: str
    constants: Annotated[list[VariableWithSyntax_RawAST], NON_EMPTY]
    inductive_rules: Annotated[list[InductiveRule_RawAST], NON_EMPTY]


@dataclass(frozen=True)
class Inductive_Rule:
    """A rule as the node holds it (§1): every piece of Isabelle text an
    `IsaTerm`, normalised by its reader."""
    name: IsaTerm
    english: str
    for_any: tuple[Variable, ...]
    premises: tuple[IsaTerm, ...]
    conclusion: IsaTerm

    def image(self) -> dict[str, Any]:
        """The store's row, the construct's shape in the `unicode` spelling."""
        return {"name": self.name.unicode, "english": self.english, "for_any": [v.image() for v in self.for_any],
                "premises": [p.unicode for p in self.premises], "conclusion": self.conclusion.unicode}

    @classmethod
    def of_image(cls, image: InductiveRule_RawAST) -> Inductive_Rule:
        """The reader of a rule, the construct's or a stored image's: its
        Isabelle texts normalised, `for_any` by `variables_of`, a list left
        out empty; `english` as given, which `gen` normalises for a
        construct.  Judges nothing."""
        def term(text: str) -> IsaTerm:
            return IsaTerm.from_agent(normalised(text))
        return cls(term(image["name"]), image["english"], variables_of(image.get("for_any", [])),
                   tuple(term(p) for p in image.get("premises", [])), term(image["conclusion"]))


def notice(variables: Sequence[IsaTerm], constants: Sequence[IsaTerm]) -> str:
    """§6's notice: the variables unchanged throughout the rules but not
    leading, and the predicates, each list by `series`."""
    one = len(variables) == 1
    return (f"An optimization is possible: {series([f'`{v.unicode}`' for v in variables], 'and')}"
            f" {'is' if one else 'are'} unchanged throughout the rules but {'is' if one else 'are'} not the first"
            f" argument{'' if one else 's'} of {series([f'`{c.unicode}`' for c in constants], 'and')};"
            f" make {'it the first argument' if one else 'them the first arguments'}.")


@TAT_node
class Inductive(Leaf):
    construct_schema = {
        "type": "object",
        "description": "inductive/coinductive predicate definition: defining the predicate as the least one that"
                       " satisfies the provided inductive rules, or the greatest one consistent with the provided"
                       " coinductive rules. Example: inductive star :: \"('a ⇒ 'a ⇒ bool) ⇒ 'a ⇒ 'a ⇒ bool\" where"
                       " refl: \"star r x x\" | step: \"star r x z\" if \"r x y\" \"star r y z\"",
        "properties": {
            "kind": {"type": "string", "enum": list(KINDS)},
            "english": {"type": "string", "description": "what is defined, in English"},
            "constants": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/Constant"},
                          "description": "the predicates defined; several for mutually inductive predicates"},
            "inductive_rules": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/InductiveRule"},
                                "description": "the inductive/coinductive rules. An optimization: when an argument of"
                                               " the predicates is unchanged throughout the rules, such as the `r` in"
                                               " `star r x y`, make it the first argument and give it the same"
                                               " variable name in every rule."},
        },
        "required": ["kind", "english", "constants", "inductive_rules"],
        "additionalProperties": False,
        "$defs": {
            "InductiveRule": {
                "type": "object",
                "properties": {
                    "name": {"type": "string",
                             "description": "the rule's name. Example: refl, which a later proof cites as star.refl"},
                    "english": {"type": "string", "description": "the rule in English"},
                    "for_any": {"type": "array", "items": {"$ref": "#/$defs/Variable"},
                                "description": "universally quantified variables to fix"},
                    "premises": {"type": "array", "items": {"type": "string", "description": TERM_DESCRIPTION},
                                 "description": "premises to assume"},
                    "conclusion": {"type": "string",
                                   "description": "an Isabelle/HOL term, which must be an application of one of the"
                                                  " predicates. Example: star r x z"},
                },
                "required": ["name", "english", "conclusion"],
                "additionalProperties": False,
            },
            **CONSTANT_DEFS, **VARIABLE_DEFS, **MIXFIX_DEFS,
        },
    }
    argument_schema = Inductive_RawAST

    english: str
    constants: tuple[Variable_With_Syntax, ...]    # each its name in the id grammar (COMMON.md §4)
    inductive_rules: tuple[Inductive_Rule, ...]
    fixed_parameters: tuple[IsaTerm, ...] | None   # recorded by the first evaluation that goes through, run again by
                                                   # the later ones (§1, §6)

    def __init__(self, parent, state, english: str, constants: tuple[Variable_With_Syntax, ...],
                 inductive_rules: tuple[Inductive_Rule, ...], fixed_parameters: tuple[IsaTerm, ...] | None = None):
        super().__init__(parent, state)
        self.english = english
        self.constants = constants
        self.name = "_and_".join(c.name.unicode for c in constants)    # `inductive_even_and_odd` (§9)
        self.inductive_rules = inductive_rules
        self.fixed_parameters = fixed_parameters

    @classmethod
    async def gen(cls, config, raw: Inductive_RawAST):
        """§4: the constants by `constants_of`, each name against the id
        grammar; the texts read normalised.  An amend's node is fresh: its
        `fixed_parameters` None."""
        return cls(config.parent, config.state, normalised(raw["english"]), constants_of(raw["constants"]),
                   tuple(replace(Inductive_Rule.of_image(r), english=normalised(r["english"]))
                         for r in raw["inductive_rules"]))

    def check_fields(self):
        """§4's field check, in its order: no two constants the same; each
        rule's name an identifier, no two the same; each rule's `for_any`."""
        for i, c in enumerate(self.constants):
            check_not_bound_twice(c.name, f"constants[{i}].name", [x.name for x in self.constants[:i]])
        for i, r in enumerate(self.inductive_rules):
            check_identifier(r.name, f"inductive_rules[{i}].name", [x.name for x in self.inductive_rules[:i]],
                             in_term=False)
        for i, r in enumerate(self.inductive_rules):
            check_variables(r.for_any, f"inductive_rules[{i}]")

    # --- the store (§1): the authored fields in the `unicode` spelling, and the recorded one; every row read with
    #     `get`, so that a missing one is refused at start

    def to_store(self, rows):
        rows.put("english", self.english)
        rows.put("constants", [c.image() for c in self.constants])
        rows.put("inductive_rules", [r.image() for r in self.inductive_rules])
        rows.put("fixed_parameters",
                 [p.unicode for p in self.fixed_parameters] if self.fixed_parameters is not None else None)

    @classmethod
    def from_store(cls, config, rows):
        fixed = rows.get("fixed_parameters")
        return cls(config.parent, config.state, rows.get("english"),
                   tuple(Variable_With_Syntax.of_image(c) for c in rows.get("constants")),
                   tuple(Inductive_Rule.of_image(r) for r in rows.get("inductive_rules")),
                   tuple(IsaTerm.from_agent(p) for p in fixed) if fixed is not None else None)

    # --- the evaluation (§6)

    def message(self) -> Any:
        """The definition as `TAT.Inductive.evaluate` unpacks it: `kind`, the
        constants as `Variable_With_Syntax`'s wire, the rules — each its
        name, conclusion, premises and `for_any` —, every `IsaTerm` as its
        `ascii`, and the recorded fixed parameters, None for them to be
        decided (COMMON.md §5)."""
        return (self.kind, [c.wire() for c in self.constants],
                [(r.name.ascii, r.conclusion.ascii, [p.ascii for p in r.premises], [v.wire() for v in r.for_any])
                 for r in self.inductive_rules],
                [p.ascii for p in self.fixed_parameters] if self.fixed_parameters is not None else None)

    async def _eval_opr(self):
        """The callback with the input slot, the resulting slot and
        `message()` (§6): the messages make the node an obstacle, the record
        untouched; none records the parameters run, and the status is
        `Ready` with the notice when there are variables for it."""
        messages, what = await isabelle_driver.call(
            self.forest().conversation, "TAT.Inductive.evaluate",
            (self.state.to_msgpack(), self.resulting_state().to_msgpack(), self.message()))
        if messages:
            return status_of_errors(messages)
        parameters, variables = what
        self.fixed_parameters = tuple(IsaTerm.from_isabelle(p) for p in parameters)
        if not variables:
            return READY_CLEAN
        return Ready((IsaTerm.from_agent(notice([IsaTerm.from_isabelle(v) for v in variables],
                                                [c.name for c in self.constants])),))

    # --- what it prints (§8) and emission (§5)

    def _fixed(self) -> tuple[IsaTerm, ...]:
        return self.fixed_parameters or ()

    def _for_any_less_fixed(self, rule: Inductive_Rule) -> list[Variable_With_Syntax]:
        """The rule's `for_any` less the fixed parameters, as `fixes_text`
        takes them."""
        fixed = self._fixed()
        return [Variable_With_Syntax(v.name, v.type, None) for v in rule.for_any if v.name not in fixed]

    def _predicates_text(self, write: Callable[[str | IsaTerm], str],
                         type_of: Callable[[IsaTerm], IsaTerm | None]) -> str:
        """The constants as `fixes_text` writes them, then `for` and the fixed
        parameters, each with `type_of`'s type, when there are any."""
        parameters = [Variable_With_Syntax(p, type_of(p), None) for p in self._fixed()]
        return " ".join(filter(None, (fixes_text(self.constants, write),
                                      "for " + fixes_text(parameters, write) if parameters else "")))

    def _rule_text(self, rule: Inductive_Rule, write: Callable[[str | IsaTerm], str], joiner: str) -> str:
        """A rule's line: its name, the conclusion, `if` and the premises,
        `for` and its `for_any` less the fixed parameters, each when there
        are any."""
        remaining = self._for_any_less_fixed(rule)
        return " ".join(filter(None, (
            f"{write(rule.name)}: {write(rule.conclusion)}",
            "if " + joiner.join(write(p) for p in rule.premises) if rule.premises else "",
            "for " + fixes_text(remaining, write) if remaining else "")))

    def print_fields(self, indent, out, mode, depth):
        """Under `Recall` alone (§8): at depths 0 to 2 the constants with the
        fixed parameters' names and the rules, one level deeper; at 0 also
        each rule's `english`, one level deeper still, and `english`; the
        stored text bare."""
        if mode is RECALL and depth <= 2:
            write = IsaTerm.to_unicode
            out.write(INDENT * (indent + 1) + self._predicates_text(write, lambda _: None) + "\n")
            for r in self.inductive_rules:
                out.write(INDENT * (indent + 1) + self._rule_text(r, write, " and ") + "\n")
                if depth == 0:
                    out.write(INDENT * (indent + 2) + r.english + "\n")
        if mode is RECALL and depth == 0:
            out.write(INDENT * indent + self.english + "\n")
        return False

    def _first_type(self, name: IsaTerm) -> IsaTerm | None:
        """The first type a rule's `for_any` gives the variable, or none."""
        return next((v.type for r in self.inductive_rules for v in r.for_any if v.name == name and v.type is not None),
                    None)

    def emit(self, indent, out):
        """§5: the `text` line; the command, every piece of Isabelle text
        through the theory's `print_name`, the fixed parameters after `for`
        each with its first type; each rule with its `english` as a formal
        comment under it."""
        assert self.fixed_parameters is not None     # a node written is one an evaluation recorded (`can_emit`)
        names = [c.name.unicode for c in self.constants]     # in the id grammar: one spelling
        emit_lines(indent, out, text_line(self.english, (self.kind.capitalize(), names)))
        write = self.enclosing(Theory).print_name
        lines = [f"{self.kind} {self._predicates_text(write, self._first_type)} where"]
        for i, r in enumerate(self.inductive_rules):
            lines.append(("  " if i == 0 else "| ") + self._rule_text(r, write, " "))
            lines.append(f"    ―{english_cartouche(r.english)}")
        emit_lines(indent, out, "\n".join(lines))
        return indent
