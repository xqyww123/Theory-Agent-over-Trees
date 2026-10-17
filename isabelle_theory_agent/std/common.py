"""What the classes of the plugin `Isabelle_Std` share
(node_classes/COMMON.md): `Theory_Member`, the base every class derives
from, with the plugin's one parent exception `NotInsideTheory` (§1); the
`text` line (§2); `Proof_Obligation`, the base of the classes whose
command opens a proof obligation — a `Leaf`'s one operation, or a
block's beginning through `Beginning_Proof_Obligation` — with its two
job classes (§3); the
shared `$defs` — the type parameter and the two mixfix annotations —
with their checks and writers, and the checks of a name (§4, §5); the
package's compile hook for AoA's proof stores (§3; COMPILATION.md §5);
and the theory the plugin declares the forest's theories import
(PLUGIN_SYSTEM §1)."""

from __future__ import annotations

import re
from abc import abstractmethod
from collections.abc import Container, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, NotRequired, TypedDict, final, overload

import IsaMini.AoA  # noqa: F401  # the remote procedure `IsaMini.AoA`, served by this process (§3)
from Isabelle_RPC_Host.unicode import IsaTerm, ascii_of_unicode, is_identifier

from .. import isabelle_driver, jobs
from ..compile import identity, paths
from ..exceptions import GRAMMARS, BadEdit, InvalidField, InvalidName
from ..jobs import PASSED, RUNNING, Failed, Succeeded, with_message
from ..model import (
    CannotEvaluate, Forest, Isar_State_Slot, JSON_Schema, Location, Node, NodeConfig, NonLeaf_Node, Ready, Theory,
    cartouche, print_name, status_of_errors, string_token)
from ..plugin import TAT_compile_hook, TAT_import

TAT_import("Minilang_AoA.Minilang_AoA")      # the `aoa` method's theory, for every theory of the forest (§3)


class NotInsideTheory(BadEdit):
    """The plugin's one parent exception (§1; EXCEPTIONS.md §3): raised by
    `Theory_Member` for a parent outside a theory — a `Session` or the
    forest root — in `gen` and on a move."""

    def __init__(self, kind: str, parent_id: str):
        super().__init__()
        self.kind = kind
        self.parent_id = parent_id

    def _cause(self) -> str:
        return f"A `{self.kind}` cannot be placed under `{self.parent_id}`; it belongs inside a theory."


class Theory_Member(Node):
    """The base every class of the plugin derives from, before its
    framework base (§1): each lives inside a theory — under a `Theory`,
    or under a nesting node under one."""

    @classmethod
    def require_inside_theory(cls, config: NodeConfig, kind: str) -> None:
        """`NotInsideTheory` for a parent outside a theory; the class's `gen`
        calls it first, the plugin's convention."""
        _require_inside_theory(config.parent, kind)

    def on_moving(self, new_location: Location) -> None:
        _require_inside_theory(new_location.parent, self.kind)

    def theory(self) -> Theory:
        """The `Theory` the node lives in, the root of its tree, which the
        two checks guarantee exists."""
        theory = _theory_above(self.parent)
        assert theory is not None, "a Theory_Member outside every theory"
        return theory


def _theory_above(node: Node | None) -> Theory | None:
    """The `Theory` that `node` is or lives under; None outside every theory."""
    while node is not None and not isinstance(node, Theory):
        node = node.parent
    return node


def _require_inside_theory(parent: Node, kind: str) -> None:
    """`NotInsideTheory` for a `kind` placed under a parent outside every
    theory, with the parent's id as the agent sees it."""
    if _theory_above(parent) is None:
        raise NotInsideTheory(kind, parent.forest().id_of(parent))


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


def require_id_name(name: str, grammar: Literal["fact name", "type name"]) -> None:
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
        raise InvalidField(field, f"binds `{IsaTerm.to_unicode(name)}` a second time")


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
        name = IsaTerm.from_agent(normalised(p["name"]))
        if not (name.ascii.startswith("'") and is_identifier(name.ascii[1:])):
            raise InvalidField(f"type_parameters[{i}].name", "must be a type variable, such as 'a")
        check_not_bound_twice(name, f"type_parameters[{i}].name", [q.name for q in parameters])
        sort = normalised(p.get("sort", ""))
        parameters.append(Type_Parameter(name, IsaTerm.from_agent(sort) if sort else None))
    return tuple(parameters)


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


# --- Proof_Obligation and its jobs (§3)

_PRODUCT = ("text", "thread_cpu", "wall")    # the proof as stored (§3); on the wire, a triple in this order


class Proof_Job(jobs.Construction_Job):
    """`Proof_Obligation`'s proof construction (§3): one call of AoA's
    standard entry on the goal `goal_state` holds, forked by
    `TAT.Proof_Obligation.construct`; the product the proof — the method
    text with the two times of its replay — and the node's check
    `Proof_Check.passed` from the run's settlement."""

    @classmethod
    def title(cls, plural=False):
        return "proof constructions" if plural else "proof construction"

    @classmethod
    def failure_header(cls, failure):
        return "No proof was found:"

    def finished_notification(self, outcome):
        if isinstance(outcome, Succeeded):
            return f"`{self.shown_id}` is proven."
        return with_message(f"No proof of `{self.shown_id}` was found:", outcome.message)

    def _check(self):
        """§3's table: a proof is constructed where none stands, or where
        the one standing failed its check; a proof not yet checked, or
        checked and passed, stands."""
        if not isinstance(self.outcome, Succeeded):
            return True
        return isinstance(self.node.check_outcome(), Failed)

    async def _run(self):
        node = self.node
        assert isinstance(node, Proof_Obligation)
        errors, product = await self.forked("TAT.Proof_Obligation.construct", node.goal_state.to_msgpack())
        if errors:
            return Failed("\n".join(errors))
        node.attach_evaluation_job(Proof_Check.passed(node))
        return Succeeded(dict(zip(_PRODUCT, product)))


class Proof_Check(jobs.Evaluation_Job):
    """`Proof_Obligation`'s proof check (§3): the stored product replayed on
    the goal `goal_state` holds, through the function AoA exports, forked
    by `TAT.Proof_Obligation.check`; no theorem out is `FAILED` with an
    empty message."""

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
        product = job.outcome.product
        await isabelle_driver.call(self.conversation, "TAT.Proof_Obligation.check",
                                   (node.goal_state.to_msgpack(), tuple(product[k] for k in _PRODUCT), self.id))


class Proof_Obligation(Node):
    """The base of a class whose command opens exactly one goal, which is
    admitted, the class's `after_admission` step following in the same
    operation (§3): the operation the goal opens on, the class's
    `job_operation` — a `Leaf`'s one operation here, a block's beginning
    in `Beginning_Proof_Obligation`.  Taken before the framework base: `class
    Theorem(Theory_Member, Proof_Obligation, Leaf)`.  The tree holds no
    proof: every evaluation admits the goal, the proof construction finds
    the proof, the proof check replays it, and the file carries `by aoa`.
    Derives from `Node`, so that the abstract methods are enforced at the
    class's first instantiation."""

    construction_job_class = Proof_Job
    evaluation_job_class = Proof_Check
    job_operation = None                    # a Leaf's one operation, which `_eval_opr` runs

    evaluation_callback: ClassVar[str]      # the class's callback, built by `TAT_Proof_Obligation.register`
                                            # from its two steps, `open_goal` and `after_admission` (§3)
    valid_word: ClassVar[str]               # the mark's first slot under `ready` ...
    invalid_word: ClassVar[str]             # ... and under `cannot_evaluate`

    goal_state: Isar_State_Slot             # the state with the goal open and no step taken, held
                                            # exactly while `job_operation_status()` is `Ready`; never stored

    def __init__(self, parent: NonLeaf_Node, state: Isar_State_Slot, *base: Any):
        super().__init__(parent, state, *base)      # a block's `sub_nodes` and slot before its ending
        self.goal_state = Isar_State_Slot.assign(parent.forest().conversation)

    @abstractmethod
    def goal_structure(self) -> Any:
        """The fields that determine the goal, `english` aside, each
        `IsaTerm` as its `ascii`: what an amend compares with `==` (§3)."""

    @abstractmethod
    def message(self) -> Any:
        """What the evaluation sends the class's callback: its fields as
        structure, `goal_structure()` its goal part (§3)."""

    def _carries_job_from(self, old):
        return old.goal_structure() == self.goal_structure()    # the proof stands when the goal does (§3)

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

    def mark(self, mode, depth):
        """Two slots, `(<status>, <proof>)` (§3): the class's word for
        `job_operation_status()`; the proof's from the job's outcome and
        the check, left out under the invalid word, a stored proof left out
        under `not evaluated`."""
        status = self.job_operation_status()       # what `can_start` and the failure blocks read too
        if isinstance(status, CannotEvaluate):
            return self.invalid_word
        evaluated = isinstance(status, Ready)
        first = self.valid_word if evaluated else "not evaluated"
        job = self.job()
        assert job is not None
        outcome = job.outcome
        if outcome is RUNNING:
            proof = "proving"
        elif isinstance(outcome, Failed):
            proof = "failed to prove"
        elif isinstance(outcome, Succeeded):
            if not evaluated:
                return first
            check = self.check_outcome()
            proof = ("unchecked proof" if check is None else "proof checking" if check is RUNNING
                     else "proven" if check is PASSED else "bad proof")
        else:
            proof = "proof not started"
        return f"{first}, {proof}"

    def proof_text(self) -> str:
        """The terminal proof after the class's command (§3): `by aoa` when
        the proof is `SUCCEEDED` and its stored check `PASSED`, `sorry`
        otherwise; a build finds the proof in the theory's proof store."""
        job = self.job()
        assert job is not None
        return "by aoa" if isinstance(job.outcome, Succeeded) and self.check_outcome() is PASSED else "sorry"


class Beginning_Proof_Obligation(Proof_Obligation):
    """`Proof_Obligation` whose goal opens on a `StdBlock`'s beginning (§3):
    `class QuotientType(Theory_Member, Beginning_Proof_Obligation,
    StdBlock)`.  The jobs depend on the beginning alone, so the children
    and the class's own ending leave the proof standing."""

    job_operation = "beginning"

    @final
    async def _eval_beginning_opr(self):
        return await self._eval_goal()


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
