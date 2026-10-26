"""`Locale`, the node class of the plugin `Isabelle_Std` for the light
locale's command (node_classes/LOCALE.md): `light_locale … begin`, a
locale declared from the locales it extends, its parameters, the axioms on
them and its implicit structure, and the block that holds the local
theory's declarations; its ending is `end`.  No proof obligation, no jobs."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, TypedDict

from Isabelle_RPC_Host.unicode import IsaTerm, ascii_of_unicode

from .. import isabelle_driver
from ..exceptions import InvalidField, series
from ..model import INDENT, RECALL, Ready, StdBlock, Theory, emit_lines, print_name, status_of_errors, string_token
from ..plugin import TAT_node
from .common import (
    LOCALE_INSTANCE_DEFS, MIXFIX_DEFS, VARIABLE_WITH_SYNTAX_DEFS, Locale_Instance, LocaleInstance_RawAST, Mixfix,
    Mixfix_RawAST, Variable_With_Syntax, VariableWithSyntax_RawAST, check_identifier, check_locale_instance,
    english_cartouche, fixes_text, locale_instance_text, mixfix_of, mixfix_of_wire, normalised, require_id_name,
    text_line)
from .statement import STATEMENT_DEFS, LongStatement_RawAST, Statement, check_statement, statement_of

KINDS = ("locale",)
CHILDREN_HEADER = "locale context"       # §8 (PRINT.md §2)


class Axiom_RawAST(TypedDict):
    name: str
    statement: LongStatement_RawAST


class Locale_RawAST(TypedDict):
    kind: Literal["locale"]
    english: str
    name: str
    imports: NotRequired[list[LocaleInstance_RawAST]]
    fixes: NotRequired[list[VariableWithSyntax_RawAST]]
    assumes: NotRequired[list[Axiom_RawAST]]
    implicit_structure: str | None


@dataclass(frozen=True)
class Axiom:
    """An axiom (§1): its name and its statement, the `premises`' names
    stored and used nowhere (§2)."""
    name: IsaTerm
    statement: Statement

    def image(self) -> dict[str, Any]:
        return {"name": self.name.unicode, "statement": self.statement.image()}

    @classmethod
    def of_image(cls, raw: dict[str, Any]) -> Axiom:
        return cls(IsaTerm.from_agent(raw["name"]), Statement.of_image(raw["statement"]))


def proposition_text(statement: Statement, parenthesised: bool) -> str:
    """§5's writer of an axiom's proposition, the text inside the string
    token: one `⋀` binding the `for_any` variables in their order, a typed
    one in parentheses with its type after `::`, none when `for_any` is
    empty; the premises, their names left out, inside `⟦` and `⟧`
    separated by `; ` and followed by ` ⟹ `, none when there is none; the
    conclusion, in parentheses when `parenthesised`."""
    binders = " ".join(f"({v.name.unicode}::{v.type.unicode})" if v.type is not None else v.name.unicode
                       for v in statement.for_any)
    premises = "; ".join(p.term.unicode for p in statement.premises)
    conclusion = statement.conclusion.unicode
    return ((f"⋀{binders}. " if binders else "") + (f"⟦{premises}⟧ ⟹ " if premises else "")
            + (f"({conclusion})" if parenthesised else conclusion))


def cancellation_sentence(cancelled: Sequence[tuple[IsaTerm, IsaTerm]]) -> str:
    """§6's message when `null` cancels inherited implicit structures: each
    structure, a term through `print_name` against no keyword, with the
    authored locale name of the import it is inherited from, joined by
    `, ` and the last by ` and `."""
    items = [f"{print_name(term)} inherited from locale {locale.unicode}" for locale, term in cancelled]
    return f"`null` cancels the implicit structure{'s' if len(items) > 1 else ''} {series(items, 'and')}."


@TAT_node
class Locale(StdBlock):
    construct_schema = {
        "type": "object",
        "description": "A light-weight Isabelle locale: lets you define a local theory (like group theory) under"
                       " axioms and develop theorems under it.",
        "properties": {
            "kind": {"const": "locale"},
            "english": {"type": "string", "description": "what is defined, in English, as LaTeX text"},
            "name": {"type": "string"},
            "imports": {"type": "array", "items": {"$ref": "#/$defs/LocaleInstance"},
                        "description": "the local theories this locale extends. Example: group extends monoid; a ring"
                                       " extends an abelian group (its addition) and a monoid (its multiplication)"},
            "fixes": {"type": "array", "items": {"$ref": "#/$defs/VariableWithSyntax"},
                      "description": "the locale's parameters: fixed variables in the local theory, such as a group's"
                                     " carrier set and its operation"},
            "assumes": {"type": "array",
                        "items": {"type": "object",
                                  "properties": {"name": {"type": "string"},
                                                 "statement": {"$ref": "#/$defs/LongStatement"}},
                                  "required": ["name", "statement"], "additionalProperties": False},
                        "description": "axioms in the local theory, such as the associativity law"},
            "implicit_structure": {"anyOf": [{"type": "string"}, {"type": "null"}],
                                   "description": "the default Isabelle term that allows notation like `A ⊗⇘default⇙ B`"
                                                  " to be written `A ⊗ B`, usually the background mathematical structure"
                                                  " such as a group or ring. Set it to null for no such default."},
            "children": {"type": "array", "items": {"$ref": "#/$defs/Construct"},
                         "description": "the declarations belonging to the local theory"},
        },
        "required": ["kind", "english", "name", "implicit_structure"],
        "additionalProperties": False,
        "$defs": {**LOCALE_INSTANCE_DEFS, **VARIABLE_WITH_SYNTAX_DEFS, **STATEMENT_DEFS, **MIXFIX_DEFS},
    }
    argument_schema = Locale_RawAST

    english: str
    name: str                                       # in the id grammar without hyphens (§1)
    imports: tuple[Locale_Instance, ...]
    fixes: tuple[Variable_With_Syntax, ...]
    assumes: tuple[Axiom, ...]
    implicit_structure: IsaTerm | None              # None for `null`, no structure (§2)
    # recorded by every beginning that goes through (§1, §6); None until one has
    annotations: tuple[Mixfix | None, ...] | None               # one per parameter: the import's annotation it takes
    parenthesised_conclusions: tuple[bool, ...] | None         # one per axiom: the file's parentheses

    def __init__(self, parent, state, english: str, name: str, imports: tuple[Locale_Instance, ...],
                 fixes: tuple[Variable_With_Syntax, ...], assumes: tuple[Axiom, ...],
                 implicit_structure: IsaTerm | None, annotations: tuple[Mixfix | None, ...] | None = None,
                 parenthesised_conclusions: tuple[bool, ...] | None = None):
        super().__init__(parent, state)
        self.english = english
        self.name = name
        self.imports = imports
        self.fixes = fixes
        self.assumes = assumes
        self.implicit_structure = implicit_structure
        self.annotations = annotations
        self.parenthesised_conclusions = parenthesised_conclusions

    @classmethod
    async def gen(cls, config, raw: Locale_RawAST):
        """§4: `name` against §1's grammar; the rest read normalised, a
        blank `implicit_structure` an empty term."""
        require_id_name(raw["name"], "locale name")
        structure = raw["implicit_structure"]
        return cls(config.parent, config.state, normalised(raw["english"]), raw["name"],
                   tuple(Locale_Instance.of_image(i) for i in raw.get("imports", [])),
                   tuple(Variable_With_Syntax.of_image(v) for v in raw.get("fixes", [])),
                   tuple(Axiom(IsaTerm.from_agent(normalised(a["name"])), statement_of(a["statement"]))
                         for a in raw.get("assumes", [])),
                   IsaTerm.from_agent(normalised(structure)) if structure is not None else None)

    def check_fields(self):
        """§4's field check in its order: each import by
        `check_locale_instance`; each parameter's name an identifier not
        ending with an underscore, no two the same; each axiom's name an
        identifier, no two the same, its statement by the shared check; no
        `for_any` variable a parameter's name; `implicit_structure` a term
        not blank, or null."""
        for n, instance in enumerate(self.imports):
            check_locale_instance(instance, f"imports[{n}]")
        for n, v in enumerate(self.fixes):
            check_identifier(v.name, f"fixes[{n}].name", [x.name for x in self.fixes[:n]], in_term=True)
        for n, a in enumerate(self.assumes):
            check_identifier(a.name, f"assumes[{n}].name", [x.name for x in self.assumes[:n]], in_term=False)
            check_statement(a.statement, f"assumes[{n}].statement")
        parameters = {v.name for v in self.fixes}
        for n, a in enumerate(self.assumes):
            for m, v in enumerate(a.statement.for_any):
                if v.name in parameters:
                    raise InvalidField(f"assumes[{n}].statement.for_any[{m}].name",
                                       f"declares `{v.name.unicode}`, which is already declared in `fixes`: a variable"
                                       " declared in `fixes` must not be declared again in `for_any`")
        if self.implicit_structure is not None and not self.implicit_structure.ascii:
            raise InvalidField("implicit_structure", "must be an Isabelle term, or null for no implicit structure at all")

    # --- the store (§1): the authored fields in the `unicode` spelling, the construct's shape, and the recorded
    #     ones, None-valued until recorded; every row read with `get`, so that a missing one is refused at start

    def to_store(self, rows):
        rows.put("english", self.english)
        rows.put("name", self.name)
        rows.put("imports", [i.image() for i in self.imports])
        rows.put("fixes", [v.image() for v in self.fixes])
        rows.put("assumes", [a.image() for a in self.assumes])
        rows.put("implicit_structure", self.implicit_structure.unicode if self.implicit_structure is not None else None)
        rows.put("annotations", [a.image() if a is not None else None for a in self.annotations]
                 if self.annotations is not None else None)
        rows.put("parenthesised_conclusions",
                 list(self.parenthesised_conclusions) if self.parenthesised_conclusions is not None else None)

    @classmethod
    def from_store(cls, config, rows):
        structure: str | None = rows.get("implicit_structure")
        annotations: list[Mixfix_RawAST | None] | None = rows.get("annotations")
        parenthesised: list[bool] | None = rows.get("parenthesised_conclusions")
        return cls(config.parent, config.state, rows.get("english"), rows.get("name"),
                   tuple(Locale_Instance.of_image(i) for i in rows.get("imports")),
                   tuple(Variable_With_Syntax.of_image(v) for v in rows.get("fixes")),
                   tuple(Axiom.of_image(a) for a in rows.get("assumes")),
                   IsaTerm.from_agent(structure) if structure is not None else None,
                   tuple(mixfix_of(a) if a is not None else None for a in annotations) if annotations is not None else None,
                   tuple(parenthesised) if parenthesised is not None else None)

    # --- evaluation (§6)

    def declaration_wire(self) -> Any:
        """§6: the declaration as `TAT.Locale.open` reads it — the name; the
        imports, each `Locale_Instance`'s wire; the parameters, each
        `Variable_With_Syntax`'s wire and whether its `syntax` was left out;
        the axioms, each its name, the declared form and the form with the
        conclusion bare, in `ascii`; the implicit structure or None."""
        return (self.name, [i.wire() for i in self.imports], [(v.wire(), v.syntax is None) for v in self.fixes],
                [(a.name.ascii, ascii_of_unicode(proposition_text(a.statement, True)),
                  ascii_of_unicode(proposition_text(a.statement, False))) for a in self.assumes],
                self.implicit_structure.ascii if self.implicit_structure is not None else None)

    async def _eval_beginning_opr(self):
        """`TAT.Locale.open` with the beginning's two slots and the declaration
        (§6): its messages make the beginning an obstacle, the records
        untouched; none records `annotations` and `parenthesised_conclusions`,
        and the status is `Ready` with the cancellation's message — built
        here from the structures `null` cancelled, one per import or None —
        and the notice, each when there is one."""
        input_slot, resulting_slot = self.operation_slots("beginning")
        messages, records, cancelled, notice = await isabelle_driver.call(
            self.forest().conversation, "TAT.Locale.open",
            (input_slot.to_msgpack(), resulting_slot.to_msgpack(), self.declaration_wire()))
        if messages:
            return status_of_errors(messages)
        annotations, parenthesised = records
        self.annotations = tuple(mixfix_of_wire(a) for a in annotations)
        self.parenthesised_conclusions = tuple(parenthesised)
        reported: list[IsaTerm] = []
        structures = [(i.locale, IsaTerm.from_isabelle(t)) for i, t in zip(self.imports, cancelled) if t is not None]
        if structures:
            reported.append(IsaTerm.from_agent(cancellation_sentence(structures)))
        if notice is not None:
            reported.append(IsaTerm.from_isabelle(notice))
        return Ready(tuple(reported))

    async def _eval_ending_opr(self):
        """`TAT.Locale.close` with the ending's two slots (§6): `end` as one
        operation; its messages make the ending an obstacle, none is `Ready`."""
        input_slot, resulting_slot = self.operation_slots("ending")
        messages = await isabelle_driver.call(
            self.forest().conversation, "TAT.Locale.close", (input_slot.to_msgpack(), resulting_slot.to_msgpack()))
        return status_of_errors(messages)

    # --- what it prints (§8)

    def print_fields(self, indent, out, mode, depth):
        """Under `Recall` alone, at depths 0 to 2 (§8): the declaration as
        keyed sections mirroring the construct, every piece through
        `print_name` against no keyword; `english` first and each axiom's
        under its line at depth 0; the conclusions' parentheses the recorded
        ones while the beginning's instant status is `Ready`."""
        if mode is not RECALL or depth > 2:
            return False
        lines: list[str] = [self.english] if depth == 0 else []
        if self.imports:
            lines += ["imports:", *(INDENT + locale_instance_text(i) for i in self.imports)]
        if self.fixes:
            lines += ["fixes:", *(INDENT + fixes_text([v], print_name) for v in self.fixes)]
        lines.append("implicit_structure: "
                     + (print_name(self.implicit_structure) if self.implicit_structure is not None else "null"))
        if self.assumes:
            lines.append("assumes:")
            recorded = (self.parenthesised_conclusions
                        if isinstance(self.evaluation_status_beginning, Ready) and self.parenthesised_conclusions is not None
                        else (False,) * len(self.assumes))
            for a, parenthesised in zip(self.assumes, recorded):
                lines.append(f"{INDENT}{print_name(a.name)}: {string_token(proposition_text(a.statement, parenthesised))}")
                if depth == 0:
                    lines.append(INDENT * 2 + a.statement.english)
        for line in lines:
            out.write(INDENT * indent + line + "\n")
        return True

    def children_header(self):
        """§8: `locale context` (PRINT.md §2)."""
        return CHILDREN_HEADER

    # --- emission (§5)

    def emit_beginning(self, indent, out):
        """§5: the `text` line; `light_locale`, the name and `=`; the imports,
        the `for` clause or the `fixes` element, ` +` on every import line
        but the last and on the line before the first element; the implicit
        structure; each axiom with its `english` as a formal comment;
        `begin`; one empty line when the block has children."""
        assert self.annotations is not None and self.parenthesised_conclusions is not None   # recorded (`can_emit`)
        theory = self.enclosing(Theory)
        write: Callable[[str | IsaTerm], str] = theory.print_name
        keywords = theory.keywords or ()
        emit_lines(indent, out, text_line(self.english))
        lines = [f"light_locale {write(self.name)} ="]
        fixes = [v if v.syntax is not None else Variable_With_Syntax(v.name, v.type, annotation)
                 for v, annotation in zip(self.fixes, self.annotations)]
        imports = [locale_instance_text(i, keywords) for i in self.imports]
        if imports:
            expression = [*(line + " +" for line in imports[:-1]), imports[-1],
                          *([f"for {fixes_text(fixes, write)}"] if fixes else [])]
            expression[-1] += " +"
            lines += [f"  {line}" for line in expression]
        elif fixes:
            lines.append(f"  fixes {fixes_text(fixes, write)}")
        lines.append("  " + (f"implicit_structure {write(self.implicit_structure)}"
                             if self.implicit_structure is not None else "no_implicit_structure"))
        for a, parenthesised in zip(self.assumes, self.parenthesised_conclusions):
            lines.append(f"  assumes {write(a.name)}: {string_token(proposition_text(a.statement, parenthesised))}")
            lines.append(f"    ―{english_cartouche(a.statement.english)}")
        lines.append("begin")
        emit_lines(indent, out, "\n".join(lines))
        if self.sub_nodes:
            out.write("\n")
        return indent

    def emit_ending(self, indent, out):
        """§5: one empty line and `end` at the block's indent."""
        out.write("\n")
        emit_lines(indent, out, "end")
        return indent
