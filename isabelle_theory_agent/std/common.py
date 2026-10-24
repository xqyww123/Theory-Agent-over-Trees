"""What the classes of the plugin `Isabelle_Std` share
(node_classes/COMMON.md): the `text` line (§2); `With_Proof_Obligations`, the base of the classes
whose commands open proof obligations, and under it `Proof_Obligation`,
the base of those whose one command opens one goal — a `Leaf`'s one
operation, or a block's beginning through `Beginning_Proof_Obligation`
— with its two job classes (§3); the
shared `$defs` — the type parameter and the two mixfix annotations —
with their checks and writers, and the checks of a name (§4, §5); the
package's compile hook for AoA's proof stores (§3; COMPILATION.md §5);
`Lifting_Closing`, the plugin's `StdBlock` whose ending closes a type's
Lifting setup, its ML half Isabelle_Std/ML/TAT_Lifting_Closing.ML, with
`lifting_closing_text`, the two lines its ending and `LiftingContext`'s
write (§6);
and the theory the plugin declares the forest's theories import
(PLUGIN_SYSTEM §1)."""

from __future__ import annotations

import re
from abc import abstractmethod
from collections.abc import Container, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, NotRequired, TypedDict, final, overload

import IsaMini.AoA  # noqa: F401  # the remote procedure `IsaMini.AoA`, served by this process (§3)
from Isabelle_RPC_Host.unicode import IsaTerm, ascii_of_unicode, is_identifier, symbol_explode

from .. import isabelle_driver, jobs
from ..compile import identity, paths
from ..exceptions import GRAMMARS, InvalidField, InvalidName, TAT_InternalError
from ..jobs import PASSED, RUNNING, Failed, Succeeded, with_message
from ..model import (
    CannotEvaluate, Forest, Isar_State_Slot, JSON_Schema, Node, NonLeaf_Node, Ready, StdBlock, cartouche, emit_lines,
    print_name, status_of_errors, string_token)
from ..plugin import TAT_compile_hook, TAT_import

# every theory of the forest imports it: the `aoa` method, the plugin's AoA tasks and the configuration option
# `typedef_overloaded` (§3, §4)
TAT_import("TAT_Std.TAT_Std")


def text_line(english: str, lead: str | None = None) -> str:
    """The `text` command a class writes before its own (§2): `english`,
    a period added when it ends without `.`, `!` or `?`, after the
    class's lead when it has one, through the framework's `cartouche`."""
    if english and english[-1] not in ".!?":
        english += "."
    return f"text {cartouche(english if lead is None else f'{lead} {english}')}"


# --- the texts and the names (§5)

def normalised(text: str) -> str:
    """A piece of Isabelle text, or `english`, as `gen` stores it: newlines
    spaces, runs of whitespace one space."""
    return " ".join(text.split())


def layout_normalised(text: str) -> str:
    """A mixfix symbol or template as `gen` stores it (§4): newlines and
    tabs alone become spaces, runs of spaces being layout."""
    return re.sub(r"[\t\n]", " ", text.replace("\r\n", "\n").replace("\r", "\n"))


_ID_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_']*")      # the id grammar without hyphens (§5)


def require_id_name(name: str, grammar: Literal["fact name", "type name", "constant name"]) -> None:
    """`InvalidName` unless `name` is in the id grammar without hyphens and
    does not end with an underscore (§5): a node's own name, and each
    authored field a class computes it from."""
    if not _ID_NAME.fullmatch(name) or name.endswith("_"):
        raise InvalidName(name, grammar)


def check_identifier(text: str, field: str, earlier: Iterable[IsaTerm], *, in_term: bool) -> IsaTerm:
    """A name the construct gives, normalised, as the node holds it (§5):
    `InvalidField` unless an Isabelle identifier on its `ascii` form, not
    ending with an underscore when Isabelle reads it in a term, and not
    among `earlier`."""
    name = IsaTerm.from_agent(normalised(text))
    if not is_identifier(name.ascii) or (in_term and name.ascii.endswith("_")):
        raise InvalidField(field, f"must be an Isabelle identifier: it {GRAMMARS['fact name']}")
    check_not_bound_twice(name, field, earlier)
    return name


def check_not_bound_twice(name: IsaTerm | str, field: str, earlier: Iterable[IsaTerm | str]) -> None:
    """`InvalidField` with the plugin's one sentence when `name` is among
    `earlier` (§4, §5)."""
    if any(e == name for e in earlier):
        raise InvalidField(field, f"repeats `{IsaTerm.to_unicode(name)}`")


def _check_type_variable(text: str, field: str, earlier: Iterable[IsaTerm]) -> IsaTerm:
    """A type parameter's name, normalised, as the node holds it (§4):
    `InvalidField` on `field` unless, on its `ascii`, a prime then an
    Isabelle identifier, and not among `earlier`."""
    name = IsaTerm.from_agent(normalised(text))
    if not (name.ascii.startswith("'") and is_identifier(name.ascii[1:])):
        raise InvalidField(field, "must be a type variable, such as 'a")
    check_not_bound_twice(name, field, earlier)
    return name


# --- the shared `$defs` (§4): the type parameter and the two mixfix annotations

TYPE_PARAMETER_DEFS: dict[str, JSON_Schema] = {
    "TypeParameter": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "sort": {"type": "string", "description": "an Isabelle sort, such as linorder"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}

_INFIX_ARM: JSON_Schema = {
    "type": "object",
    "properties": {
        "form": {"type": "string", "enum": ["infix", "infixl", "infixr"]},
        "symbol": {"type": "string"},
        "priority": {"type": "integer"},
    },
    "required": ["form", "symbol", "priority"], "additionalProperties": False,
}

_TEMPLATE_ARM: JSON_Schema = {
    "type": "object",
    "properties": {
        "form": {"type": "string", "enum": ["mixfix"]},
        "template": {"type": "string"},
        "argument_priorities": {"type": "array", "items": {"type": "integer"},
                                "description": "one per _; 0 when left out"},
        "priority": {"type": "integer", "description": "the result's; 1000 when left out"},
    },
    "required": ["form", "template"], "additionalProperties": False,
}

MIXFIX_DEFS: dict[str, JSON_Schema] = {
    "Mixfix": {
        "description": "Isabelle's mixfix annotation",
        "anyOf": [
            {**_INFIX_ARM, "description": 'an infix operator, as in (infixr "#" 65)'},
            {"type": "object", "description": 'a binder, as in (binder "∀" 10)',
             "properties": {
                 "form": {"type": "string", "enum": ["binder"]},
                 "symbol": {"type": "string"},
                 "priority": {"type": "integer"}},
             "required": ["form", "symbol", "priority"], "additionalProperties": False},
            {**_TEMPLATE_ARM,
             "description": 'a template with one _ per argument, as in ("⟨_, _⟩") or ("_ ! _" [100, 101] 100)'},
        ],
    },
}

TYPE_MIXFIX_DEFS: dict[str, JSON_Schema] = {
    "TypeMixfix": {
        "description": "Isabelle's mixfix annotation for a type",
        "anyOf": [
            {**_INFIX_ARM, "description": 'an infix type constructor. Example: (infixr "+" 10)'},
            {**_TEMPLATE_ARM, "description": 'a template with one _ per type parameter. Example: ("_⇩⊥" [21] 21)'},
        ],
    },
}


class TypeParameter_RawAST(TypedDict):
    name: str
    sort: NotRequired[str]


class Infix_RawAST(TypedDict):
    form: Literal["infix", "infixl", "infixr"]
    symbol: str
    priority: int


class Binder_RawAST(TypedDict):
    form: Literal["binder"]
    symbol: str
    priority: int


class Template_RawAST(TypedDict):
    form: Literal["mixfix"]
    template: str
    argument_priorities: NotRequired[list[int]]
    priority: NotRequired[int]


Mixfix_RawAST = Infix_RawAST | Binder_RawAST | Template_RawAST
TypeMixfix_RawAST = Infix_RawAST | Template_RawAST


@dataclass(frozen=True)
class Type_Parameter:
    name: IsaTerm
    sort: IsaTerm | None            # None when there is none

    def image(self) -> dict[str, Any]:
        """The store's row, in the `unicode` spelling, the construct's shape."""
        return {"name": self.name.unicode, **({"sort": self.sort.unicode} if self.sort is not None else {})}


def type_parameters_of(raw: list[TypeParameter_RawAST]) -> tuple[Type_Parameter, ...]:
    """The shared check (§4), the construct's `type_parameters` normalised
    and as the node holds them: each `name`, on its `ascii`, a prime and
    an Isabelle identifier, no two the same; an empty `sort` is no sort.
    A stored image is read back through it too."""
    parameters: list[Type_Parameter] = []
    for i, p in enumerate(raw):
        name = _check_type_variable(p["name"], f"type_parameters[{i}].name", [q.name for q in parameters])
        sort = normalised(p.get("sort", ""))
        parameters.append(Type_Parameter(name, IsaTerm.from_agent(sort) if sort else None))
    return tuple(parameters)


def type_variables_of(raw: list[str]) -> tuple[Type_Parameter, ...]:
    """The shared check (§4) over type variables written bare, under the
    path `type_parameters[i]`: `Type_Parameter`s without a sort.  A
    stored image — the names — is read back through it too."""
    parameters: list[Type_Parameter] = []
    for i, name in enumerate(raw):
        variable = _check_type_variable(name, f"type_parameters[{i}]", [q.name for q in parameters])
        parameters.append(Type_Parameter(variable, None))
    return tuple(parameters)


def check_type_parameters_used(parameters: Sequence[Type_Parameter], texts: Iterable[IsaTerm]) -> None:
    """§4's check that every declared type parameter is used: a lexical
    scan of the class's Isabelle text in `ascii` — `texts`, the types the
    construct gives — for type-variable tokens; the first parameter found
    in none refused on its path with the one sentence §4 pins."""
    used = set().union(*(_type_variables(t.ascii) for t in texts))
    for i, p in enumerate(parameters):
        if p.name.ascii not in used:
            raise InvalidField(f"type_parameters[{i}]", f"declares `{p.name.unicode}`, which is not used")


def _type_variables(ascii: str) -> set[str]:
    """The type-variable tokens of a piece of Isabelle text in `ascii`: each
    maximal run of identifier symbols — a letter or letter symbol, a
    digit, an underscore, a prime, a subscript — that starts with a prime
    and continues as an identifier, so `'a` is one and `'ab`, `'a⇩1` and
    `x'a` are not it; taken outside cartouches, since Isabelle's lexer
    reads a cartouche, and so an inner comment's body, as no part of the
    type."""
    found: set[str] = set()
    run, depth = "", 0
    for symbol in [*symbol_explode(ascii), " "]:
        if symbol == "\\<open>":
            depth += 1
        elif symbol == "\\<close>":
            depth = max(depth - 1, 0)
        elif depth == 0 and (is_identifier(symbol) or symbol in "0123456789_'" or symbol == "\\<^sub>"):
            run += symbol
            continue
        if run.startswith("'") and is_identifier(run[1:]):
            found.add(run)
        run = ""
    return found


def type_parameters_text(parameters: Sequence[Type_Parameter], keywords: Container[str] = ()) -> str:
    """§4's writer: nothing for none; one without a sort bare, `'a`;
    otherwise parenthesised and comma-separated, a sort after `::`
    through `print_name` against `keywords` — `('a :: linorder, 'b)`."""
    if not parameters:
        return ""
    if len(parameters) == 1 and parameters[0].sort is None:
        return parameters[0].name.unicode
    return "(" + ", ".join(
        p.name.unicode + (f" :: {print_name(p.sort, keywords)}" if p.sort is not None else "")
        for p in parameters) + ")"


def type_parameters_wire(parameters: Sequence[Type_Parameter]) -> list[tuple[str, str | None]]:
    """The parameters as the ML reads them (§4): each its name and its sort
    in `ascii`, None for no sort."""
    return [(p.name.ascii, p.sort.ascii if p.sort is not None else None) for p in parameters]


@dataclass(frozen=True)
class Infix:
    """An infix arm of `Mixfix` and `TypeMixfix` (§4)."""
    form: Literal["infix", "infixl", "infixr"]
    symbol: IsaTerm
    priority: int

    def image(self) -> dict[str, Any]:
        return {"form": self.form, "symbol": self.symbol.unicode, "priority": self.priority}


@dataclass(frozen=True)
class Binder:
    """The binder arm of `Mixfix` (§4)."""
    symbol: IsaTerm
    priority: int

    def image(self) -> dict[str, Any]:
        return {"form": "binder", "symbol": self.symbol.unicode, "priority": self.priority}


@dataclass(frozen=True)
class Template:
    """The template arm of `Mixfix` and `TypeMixfix` (§4): the priorities as
    authored, None when left out."""
    template: IsaTerm
    argument_priorities: tuple[int, ...] | None = None
    priority: int | None = None

    def image(self) -> dict[str, Any]:
        return {"form": "mixfix", "template": self.template.unicode,
                **({"argument_priorities": list(self.argument_priorities)}
                   if self.argument_priorities is not None else {}),
                **({"priority": self.priority} if self.priority is not None else {})}


Mixfix = Infix | Binder | Template           # as a node holds an annotation; its store image the construct's shape
TypeMixfix = Infix | Template


@overload
def mixfix_of(raw: TypeMixfix_RawAST) -> TypeMixfix: ...
@overload
def mixfix_of(raw: Mixfix_RawAST) -> Mixfix: ...
def mixfix_of(raw: Mixfix_RawAST) -> Mixfix:
    """The construct's annotation as the node holds it, the symbol or
    template normalised for newlines and tabs alone (§4); a stored image
    is read back through it too."""
    if raw["form"] == "mixfix":
        return Template(IsaTerm.from_agent(layout_normalised(raw["template"])),
                        tuple(raw["argument_priorities"]) if "argument_priorities" in raw else None,
                        raw.get("priority"))
    symbol = IsaTerm.from_agent(layout_normalised(raw["symbol"]))
    return Binder(symbol, raw["priority"]) if raw["form"] == "binder" else Infix(raw["form"], symbol, raw["priority"])


def mixfix_text(syntax: Mixfix) -> str:
    """§4's writer, either annotation as Isabelle writes it, the symbol or
    template a string token: `(infixr "#" 65)`, `(binder "∀" 10)`,
    `("⟨_, _⟩")`, `("_ ! _" [100, 101] 100)` — a template's argument
    priorities in brackets and its result priority after them, each when
    given."""
    if isinstance(syntax, Template):
        parts = [string_token(syntax.template.unicode)]
        if syntax.argument_priorities is not None:
            parts.append("[" + ", ".join(str(p) for p in syntax.argument_priorities) + "]")
        if syntax.priority is not None:
            parts.append(str(syntax.priority))
        return "(" + " ".join(parts) + ")"
    form = "binder" if isinstance(syntax, Binder) else syntax.form
    return f"({form} {string_token(syntax.symbol.unicode)} {syntax.priority})"


def mixfix_wire(syntax: Mixfix | None) -> str | None:
    """The annotation as the ML reads it with Isabelle's `Parse.mixfix`
    (§4): `mixfix_text`'s text in `ascii`, the conversion the compile
    applies to a file; None for none."""
    return None if syntax is None else ascii_of_unicode(mixfix_text(syntax))


def type_head_text(parameters: Sequence[Type_Parameter], name: str, syntax: TypeMixfix | None,
                   keywords: Container[str]) -> str:
    """§4's writer of a type's head, as the commands write it: the type
    parameters by `type_parameters_text`, the name through `print_name`
    against `keywords`, and the syntax by `mixfix_text` when one is given
    — `'a fset`, `('a, 'b) t (infixr "+" 10)`."""
    return " ".join(filter(None, (type_parameters_text(parameters, keywords), print_name(name, keywords),
                                  mixfix_text(syntax) if syntax is not None else "")))


# --- the Rep and the Abs function names of a type (§4): the check, the defaults and the `morphisms` clause

def function_names_of(raw_rep: str | None, raw_abs: str | None) -> tuple[IsaTerm | None, IsaTerm | None]:
    """§4's check of the pair, the fields `rep_function_name` and
    `abs_function_name`: each given name an Isabelle identifier Isabelle
    reads in a term (§5), the two given names, as given, not the same —
    the later refused —; None for a name left out."""
    rep = check_identifier(raw_rep, "rep_function_name", (), in_term=True) if raw_rep is not None else None
    abs_ = (check_identifier(raw_abs, "abs_function_name", () if rep is None else (rep,), in_term=True)
            if raw_abs is not None else None)
    return rep, abs_


def function_names(rep: IsaTerm | None, abs_: IsaTerm | None, type_name: str,
                   prefixes: tuple[str, str]) -> tuple[IsaTerm, IsaTerm]:
    """The two names with the defaults filled in (§4): a name left out is
    its prefix before the type's name."""
    rep_prefix, abs_prefix = prefixes
    return (rep if rep is not None else IsaTerm.from_agent(rep_prefix + type_name),
            abs_ if abs_ is not None else IsaTerm.from_agent(abs_prefix + type_name))


def morphisms_clause(rep: IsaTerm | None, abs_: IsaTerm | None, type_name: str, prefixes: tuple[str, str],
                     keywords: Container[str]) -> str | None:
    """§4's writer of the `morphisms` clause: the two names with the
    defaults filled in, each through `print_name` against `keywords`;
    None when neither was given."""
    if rep is None and abs_ is None:
        return None
    return "morphisms " + " ".join(print_name(f, keywords) for f in function_names(rep, abs_, type_name, prefixes))


# --- Proof_Obligation and its jobs (§3)

_PRODUCT = ("text", "thread_cpu", "wall")    # the proof as stored (§3); on the wire, a triple in this order

# The setup of one call of `TAT.Proof_Obligation.construct` (§3; DEFINE.md
# §7), a quadruple on the wire: the task — its name and its payload — or
# None for AoA's `usual`; the goal hint — its text and its `whole_prop`
# patterns — or None; the tactic whitelist, each a method name and its
# interpretation; whether the goal is kept as it stands, AoA's automatic
# Intro not inserted on it.  The hint, the whitelist and the goal kept are
# declared in the goal's proof context for the call alone.
Construction_Setup = tuple[tuple[str, Any] | None, tuple[str, list[str]] | None, list[tuple[str, str]], bool]
NO_SETUP: Construction_Setup = (None, None, [], False)


def proof_wire(product: Any) -> tuple[Any, ...]:
    """A stored proof as `TAT.Proof_Obligation.check` reads it (§3)."""
    return tuple(product[k] for k in _PRODUCT)


def proof_from_wire(product: Any) -> dict[str, Any]:
    """A proof as `TAT.Proof_Obligation.construct` reports it, stored (§3)."""
    return dict(zip(_PRODUCT, product))


REFUTE = "refute"       # AoA's reason for a refutation, the kind of failure with sentences of its own (§3)


def construction_from_wire(errors: list[str], product: Any) -> dict[str, Any] | Failed:
    """What a call of `TAT.Proof_Obligation.construct` reports (§3), from
    `forked`'s errors and product: the proof, stored, or the failure — the
    errors joined, or the agent's give-up, its message under AoA's reason
    as the kind."""
    if errors:
        return Failed("\n".join(errors))
    match product:
        case ["proof", proof]:
            return proof_from_wire(proof)
        case ["gave_up", [str(reason), str(message)]]:
            return Failed(message, reason)
        case _:
            raise TAT_InternalError(f"not a construction's report: {product!r}")


class Proof_Job(jobs.Construction_Job):
    """`Proof_Obligation`'s proof construction (§3): one call of AoA's
    standard entry on the goal `goal_state` holds, forked by
    `TAT.Proof_Obligation.construct`; the product the proof — the method
    text with the two times of its replay — and the node's check
    `Proof_Check.passed` from the run's settlement."""

    @classmethod
    def title(cls, plural=False):
        return "proof constructions" if plural else "proof construction"

    def _failure_sentence(self, failure: Failed, without_assertion: str) -> str:
        """§3's sentence over a failure's message, the node by its shown id:
        the node's `refutation_sentence` when the failure is the agent's
        refutation and the class has one; else `Failed to prove that
        <assertion>:` with the node's `failed_assertion`; else
        `without_assertion`."""
        node = self.node
        assert isinstance(node, With_Proof_Obligations)
        if failure.kind == REFUTE:
            refutation = node.refutation_sentence(self.shown_id)
            if refutation is not None:
                return f"{refutation}:"
        assertion = node.failed_assertion(self.shown_id)
        return without_assertion if assertion is None else f"Failed to prove that {assertion}:"

    def failure_header(self, failure) -> str | None:
        return self._failure_sentence(failure, "No proof was found:")

    def finished_notification(self, outcome):
        if isinstance(outcome, Succeeded):
            return f"`{self.shown_id}` is proven."
        return with_message(self._failure_sentence(outcome, f"No proof of `{self.shown_id}` was found:"),
                            outcome.message)

    def _check(self):
        """§3's table: a proof is constructed where none stands, or where
        the one standing failed its check; a proof not yet checked, or
        checked and passed, stands."""
        if not isinstance(self.outcome, Succeeded):
            return True
        return isinstance(self.node.check_outcome(), Failed)

    async def _construct(self, slot: Isar_State_Slot, setup: Construction_Setup = NO_SETUP) -> dict[str, Any] | Failed:
        """One call of `TAT.Proof_Obligation.construct` (§3) on the goal
        `slot` holds, under `setup`, and what it reports."""
        return construction_from_wire(*await self.forked("TAT.Proof_Obligation.construct", (slot.to_msgpack(), setup)))

    async def _run(self):
        node = self.node
        assert isinstance(node, Proof_Obligation)
        construction = await self._construct(node.goal_state)
        if isinstance(construction, Failed):
            return construction
        node.attach_evaluation_job(Proof_Check.passed(node))
        return Succeeded(construction)


class Proof_Check(jobs.Evaluation_Job):
    """`Proof_Obligation`'s proof check (§3): the stored product replayed on
    the goal `goal_state` holds, through the function AoA exports, forked
    by `TAT.Proof_Obligation.check` — which replays a list of goals, each
    with its proof, one here; no theorem out is `FAILED` with an empty
    message."""

    @classmethod
    def title(cls, plural=False):
        return "proof checks" if plural else "proof check"

    @classmethod
    def failure_header(cls, failure):
        return "The proof no longer holds:"

    @classmethod
    def failure_notification(cls, ids, automatic):
        several = len(ids) > 1
        if automatic:
            tail = (", so " + ("their proof constructions were" if several else "its proof construction was")
                    + " started automatically; call `check_construct` before you exit")
        else:
            tail = ". Call `construct` to prove " + ("them" if several else "it") + " again"
        return jobs.listed(ids, lambda of: f"The proof {of} no longer holds{tail}.",
                           "The following proofs no longer hold"
                           + (tail if automatic else "; call `construct` to prove them again") + ":",
                           preposition="of")

    @classmethod
    def passed(cls, node):
        """The check a proof construction attaches at its settlement (§3):
        `PASSED` without running."""
        job = cls(node, None)
        job.outcome = PASSED
        return job

    async def _start(self):
        node = self.node
        assert isinstance(node, Proof_Obligation)
        job = node.job()
        assert job is not None and isinstance(job.outcome, Succeeded)   # a check runs on a node whose proof
                                                                        # SUCCEEDED (CONSTRUCT_INTERACTION §3.3)
        await isabelle_driver.call(self.conversation, "TAT.Proof_Obligation.check",
                                   ([(node.goal_state.to_msgpack(), proof_wire(job.outcome.product))], self.id))


# --- the words of the mark (§3), one computation for every class whose line
#     reads `(<status>, <proof>)`, `With_Proof_Obligations.mark`

def proven(node: Node) -> bool:
    """Whether the node's proof stands: `proof` `SUCCEEDED` and the proof
    check `PASSED` (§3) — what `by aoa` and `valid definition` need."""
    job = node.job()
    assert job is not None
    return isinstance(job.outcome, Succeeded) and node.check_outcome() is PASSED


def unverified(node: With_Proof_Obligations) -> bool:
    """Whether a class that defines reads `unverified definition` (§3):
    under `ready`, while it owes a proof — `owes_proof()` — that does not
    stand."""
    return node.owes_proof() and isinstance(node.job_operation_status(), Ready) and not proven(node)


def proof_mark(node: With_Proof_Obligations) -> str:
    """The two slots, `(<status>, <proof>)` (§3): the first the class's word
    for `job_operation_status()`; the second from the job's outcome and
    the check, left out under the invalid word, a stored proof left out
    under `not evaluated`.  A class that defines sets `unverified_word`:
    then under `ready` the line is `valid_word` alone when the node owes
    nothing — `owes_proof()` false, or the proof standing — and
    `unverified_word` with the proof's word otherwise; `proven` never
    appears."""
    status = node.job_operation_status()       # what `can_start` and the failure blocks read too
    if isinstance(status, CannotEvaluate):
        return node.invalid_word
    evaluated = isinstance(status, Ready)
    if evaluated and node.unverified_word is not None:
        if not unverified(node):
            return node.valid_word
        first = node.unverified_word
    else:
        first = node.valid_word if evaluated else "not evaluated"
    job = node.job()
    assert job is not None
    outcome = job.outcome
    if outcome is RUNNING:
        proof = "proving"
    elif isinstance(outcome, Failed):
        proof = "failed to prove"
    elif isinstance(outcome, Succeeded):
        if not evaluated:
            return first
        check = node.check_outcome()
        proof = ("unchecked proof" if check is None else "proof checking" if check is RUNNING
                 else "proven" if check is PASSED else "bad proof")
    else:
        proof = "proof not started"
    return f"{first}, {proof}"


class With_Proof_Obligations(Node):
    """The base of a class whose commands open proof obligations (§3):
    `Proof_Obligation` below, one command opening one goal, and `Define`,
    up to two goals on two commands (DEFINE.md).  What the proofs'
    standing decides for every such class: the mark's three words and the
    two-slot `mark`, the terminal proof `proof_text()`, the amend's carry
    by `goal_structure()`, and `owes_proof()`.  Taken before the framework
    base: `class Define(With_Proof_Obligations, Leaf)`.
    Derives from `Node`, so that the abstract methods are enforced at the
    class's first instantiation."""

    valid_word: ClassVar[str]               # the mark's first slot under `ready` ...
    invalid_word: ClassVar[str]             # ... and under `cannot_evaluate`
    unverified_word: ClassVar[str | None] = None    # a class that defines: its word while it owes a proof

    @abstractmethod
    def goal_structure(self) -> Any:
        """The fields that determine the goals, `english` aside, each
        `IsaTerm` as its `ascii`: what an amend compares with `==` (§3)."""

    @abstractmethod
    def message(self) -> Any:
        """What the evaluation sends the class's callback: its fields as
        structure, `goal_structure()` its goal part (§3)."""

    def owes_proof(self) -> bool:
        """Whether the node has a proof to owe (§3): always, the default —
        `Proof_Obligation`'s one goal —; `Define` answers whether an
        obligation is open (DEFINE.md §7)."""
        return True

    def failed_assertion(self, shown_id: str) -> str | None:
        """What the construction that failed was to prove, the clause after
        `Failed to prove that` in `Proof_Job`'s two failure sentences (§3),
        the node named by `shown_id`; None, the default, names nothing and
        leaves the sentences `No proof was found`.  `Theorem` keeps the
        default; `Define`'s names the failed obligation (DEFINE.md §7), the
        other classes that define name what theirs proves."""
        return None

    def refutation_sentence(self, shown_id: str) -> str | None:
        """The sentence `Proof_Job`'s two failure sentences become when the
        agent refuted the obligation (§3), the node named by `shown_id` —
        what may fail, without the colon: `` Function `definition_sum_upto`
        may not terminate ``; None, the default, leaves them as for any
        failure."""
        return None

    def _carries_job_from(self, old):
        return old.goal_structure() == self.goal_structure()    # the proofs stand when the goals do (§3)

    def mark(self, mode, depth):
        """Two slots, `(<status>, <proof>)`, by `proof_mark` with the class's
        words (§3)."""
        return proof_mark(self)

    def proof_text(self) -> str:
        """The terminal proof after the class's command (§3): `by aoa` when
        the proof stands, `sorry` otherwise; a build finds the proof in the
        theory's proof store."""
        return "by aoa" if proven(self) else "sorry"


class Proof_Obligation(With_Proof_Obligations):
    """The base of a class whose command opens exactly one goal, which is
    admitted, the class's `after_admission` step following in the same
    operation (§3): the operation the goal opens on, the class's
    `job_operation` — a `Leaf`'s one operation here, a block's beginning
    in `Beginning_Proof_Obligation`.  Taken before the framework base: `class
    Theorem(Proof_Obligation, Leaf)`.  The tree holds no
    proof: every evaluation admits the goal, the proof construction finds
    the proof, the proof check replays it, and the file carries `by aoa`."""

    construction_job_class = Proof_Job
    evaluation_job_class = Proof_Check
    job_operation = None                    # a Leaf's one operation, which `_eval_opr` runs

    evaluation_callback: ClassVar[str]      # the class's callback, built by `TAT_Proof_Obligation.register`
                                            # from its two steps, `open_goal` and `after_admission` (§3)

    goal_state: Isar_State_Slot             # the state with the goal open and no step taken, held
                                            # exactly while `job_operation_status()` is `Ready`; never stored

    def __init__(self, parent: NonLeaf_Node, state: Isar_State_Slot):
        super().__init__(parent, state)
        self.goal_state = Isar_State_Slot.assign(state.conversation)

    def _states_inside(self, out=None):
        out = super()._states_inside(out)
        out.append(self.goal_state)
        return out

    def _slots_written_by(self, operation):
        return (self.goal_state,) if operation == type(self).job_operation else ()

    def record_from_evaluation(self, what: Any) -> tuple[IsaTerm, ...]:
        """What the two steps yielded, `[a, b]` on the wire, recorded on the
        node; answers the messages the `Ready` carries (§3).  The default
        records nothing and answers `()`."""
        return ()

    @final
    async def _eval_goal(self) -> Ready | CannotEvaluate:
        """The class's callback (§3) with `job_operation`'s input slot,
        `goal_state`, its resulting slot and `message()`: the goal opened
        into `goal_state`, admitted into the resulting slot with the
        class's commands after the admission.  Its answer is the messages
        and, when there are none, what the two steps yielded: the messages
        make the operation an obstacle; none is `Ready` carrying what
        `record_from_evaluation` answers.  What the hook of the class that
        sets `job_operation` runs."""
        input_slot, resulting_slot = self.operation_slots(type(self).job_operation)
        messages, what = await isabelle_driver.call(
            self.forest().conversation, type(self).evaluation_callback,
            (input_slot.to_msgpack(), self.goal_state.to_msgpack(), resulting_slot.to_msgpack(), self.message()))
        if messages:
            return status_of_errors(messages)
        return Ready(self.record_from_evaluation(what))

    @final
    async def _eval_opr(self):
        return await self._eval_goal()


class Beginning_Proof_Obligation(Proof_Obligation):
    """`Proof_Obligation` whose goal opens on a `StdBlock`'s beginning (§3):
    `class QuotientType(Beginning_Proof_Obligation, Lifting_Closing)`,
    `class Typedef(Beginning_Proof_Obligation, Lifting_Closing)`.  The
    jobs depend on the beginning alone, so the children and the class's
    own ending leave the proof standing."""

    job_operation = "beginning"

    @final
    async def _eval_beginning_opr(self):
        return await self._eval_goal()


# --- Lifting_Closing (§6)

def lifting_closing_text(name: str) -> str:
    """§6's two lines, `lifting_update t.lifting` then `lifting_forget
    t.lifting`, the bundle's name bare — `t.lifting` is one token to
    Isabelle's outer lexer even where `t` is a keyword: what
    `Lifting_Closing`'s ending writes for its type and `LiftingContext`'s
    for each type it opened (LIFTING_CONTEXT.md §5)."""
    return f"lifting_update {name}.lifting\nlifting_forget {name}.lifting"


# §6's two sentences, the one home of each: what a block on the base says while it refuses children, and the
# description its `children` field carries
LIFTING_REFUSAL = ("For technical reasons, this subtype does not support lifting; you cannot use the transfer tactic or"
                   " lift_definitions on this type.")
LIFTING_CHILDREN_DESCRIPTION = ("lift_definitions and lemmas whose proofs transfer the defined type to its representation"
                                " type. Outside this block the defined type is opaque — its representation is closed to"
                                " lift_definition and the transfer tactic — unless a lifting_context opens it again")
# §6's children header, the base's and `LiftingContext`'s (PRINT.md §2)
LIFTING_CHILDREN_HEADER = "lifting context"


class Lifting_Closing(StdBlock):
    """The plugin's `StdBlock` whose ending closes the Lifting setup its
    beginning made (§6): `lifting_update t.lifting` then `lifting_forget
    t.lifting`, `t` the node's `name`.  It defines the ending's two hooks
    together (PLUGIN_SYSTEM §5); a class on it writes neither.  While
    `is_lifting_setup_made()` answers false the block refuses children and
    its ending runs nothing and writes nothing.  A class takes it as its
    framework base, after the class that sets its `job_operation`: `class
    QuotientType(Beginning_Proof_Obligation, Lifting_Closing)`; listed
    before that class, it puts `StdBlock`'s abstract `_eval_beginning_opr`
    first, and the class cannot be instantiated."""

    def is_lifting_setup_made(self) -> bool:
        """§6: whether the beginning made the setup — true on the base;
        `Typedef` answers false exactly when its recorded `lifting` is
        false."""
        return True

    def children_refusal(self):
        return None if self.is_lifting_setup_made() else LIFTING_REFUSAL

    def children_header(self):
        return LIFTING_CHILDREN_HEADER

    @final
    async def _eval_ending_opr(self):
        """`TAT.Lifting_Closing.close` with the ending's two slots and the
        type's name, the two transitions as one operation into the
        resulting slot (§6): its messages make the ending an obstacle,
        none is `Ready`; with no setup made, `StdBlock`'s copy."""
        if not self.is_lifting_setup_made():
            return await super()._eval_ending_opr()
        input_slot, resulting_slot = self.operation_slots("ending")
        messages = await isabelle_driver.call(
            self.forest().conversation, "TAT.Lifting_Closing.close",
            (input_slot.to_msgpack(), resulting_slot.to_msgpack(), self.name))
        return status_of_errors(messages)

    @final
    def emit_ending(self, indent, out):
        """§6: one empty line, then the two commands by `lifting_closing_text`,
        each on its own line at the block's indent; with no setup made,
        nothing."""
        if not self.is_lifting_setup_made():
            return super().emit_ending(indent, out)
        out.write("\n")
        emit_lines(indent, out, lifting_closing_text(self.name))
        return indent


# --- the compile hook (§3; COMPILATION.md §5)

_PROOF_STORE = re.compile(r"(.+?)\.proof-store(?:\..*)?", re.DOTALL)   # `<T>.proof-store`, `<T>.proof-store.*`


@TAT_compile_hook
def remove_proof_stores_of_no_tree(forest: Forest) -> None:
    """The package's compile hook (§3; COMPILATION.md §5): AoA keeps a
    theory's proofs in `<T>.proof-store` beside its file, with
    `<T>.proof-store.*` — its lock and temporary files among them.  Each
    such entry the path listing yields, not a folder, whose folder and `T`
    are no tree's is removed, and nothing else; the folder by its identity,
    as the compile knows its own, since its spelling on disk may differ
    from the session's."""
    directory = forest.conversation.working_directory
    trees = {(identity(directory / tree.file_path().parent), tree.name) for tree in forest.trees()}
    for entry in list(paths(directory)):
        if (entry.kind != "folder" and (found := _PROOF_STORE.fullmatch(entry.path.name))
                and (identity(directory / entry.path.parent), found[1]) not in trees):
            (directory / entry.path).unlink()
