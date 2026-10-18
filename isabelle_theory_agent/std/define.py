"""`Define`, the node class of the plugin `Isabelle_Std` for a definition by
equations (node_classes/DEFINE.md): one or more constants defined by
`definition`, or by `function (sequential, no_partials)` or plain
`function` with `termination`, the command the evaluation's choice,
recorded as `form`; under a function command the goals Isabelle's `fun`
could not close by itself — pattern completeness, termination — are proof
obligations, each proved by one AoA call under a task of this module and
replayed by the proof check."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, ClassVar, Literal, NotRequired, TypedDict

from Isabelle_RPC_Host.unicode import IsaTerm
from IsaMini.AoA.model import Role_Major
from IsaMini.AoA.task import StdTask, aoa_task

from .. import isabelle_driver
from ..jobs import Failed, Succeeded, series
from ..model import INDENT, NON_EMPTY, RECALL, Isar_State_Slot, Leaf, emit_lines, print_name, status_of_errors, string_token
from ..plugin import TAT_node
from .common import (
    MIXFIX_DEFS, Construction_Setup, Mixfix, Mixfix_RawAST, Proof_Check, Proof_Job, Theory_Member,
    With_Proof_Obligations, check_not_bound_twice, mixfix_of, mixfix_text, mixfix_wire, normalised, proof_from_wire,
    proof_wire, require_id_name, text_line, unverified)

KINDS = ("definition",)
DEFINITION, SEQUENTIAL, PLAIN = "definition", "function (sequential, no_partials)", "function"
Form = Literal["definition", "function (sequential, no_partials)", "function"]     # the command run (§1)

# The two obligations (§7), in command order; each names its task, `TAT.<obligation>`, and its key in the product.
PATTERN_COMPLETENESS, TERMINATION = "pattern_completeness", "termination"
OBLIGATIONS = (PATTERN_COMPLETENESS, TERMINATION)
Obligation = Literal["pattern_completeness", "termination"]
_WAITED_FOR = {PATTERN_COMPLETENESS: "pattern completeness", TERMINATION: "termination"}     # the owing line's words
_TACTICS = {PATTERN_COMPLETENESS: ("pat_completeness",), TERMINATION: ("relation", "size_change")}   # the whitelists
_GOAL_HINT_PATTERNS = ["Wellfounded.accp _ _"]       # the termination goal, `∀x. accp <name>_rel x` (§7)

# --- the texts the proof agent reads (§7), each written once here

INTERPRETATIONS = {
    "relation":
        "`relation R` proves termination with a well-founded relation `R` that the recursive calls decrease."
        " Typically `relation \"measure f\"` where `f :: arguments ⇒ nat` maps the tuple of the arguments to a"
        " number that every recursive call makes smaller, e.g. `measure (λ(xs, ys). length xs + length ys)` for"
        " `merge xs ys`. When one measure function is not enough, `relation \"measures [f1, f2]\"` compares by `f1`"
        " first and by `f2` on a tie, e.g. `measures [λ(m, n). m, λ(m, n). n]` for the Ackermann function"
        " `ack m n`. After applying the tactic, it leaves you to prove, for each recursive call, that the call's"
        " argument is below the left-hand side's argument in `R`, and that `R` is well-founded.",
    "size_change":
        "`size_change` proves termination by analyzing how the sizes of the arguments change in each recursive"
        " call. It either closes the goal or fails, leaving nothing to prove; on a large function it can take a"
        " while.",
    "pat_completeness":
        "`pat_completeness` proves the goal that the equations cover every argument, the one of the form"
        " `⋀P x. (x = … ⟹ P) ⟹ … ⟹ P`, by case analysis on the constructors of the argument types, following"
        " the patterns. It either closes that goal or fails; it fails when some constructor case is matched by no"
        " equation, or a pattern is not a constructor.",
}


def _functions(names: Sequence[str]) -> str:
    """`the function `log2``; `the functions `even` and `odd``."""
    return ("the function " if len(names) == 1 else "the functions ") + series([f"`{n}`" for n in names], "and")


def assertion(obligation: str, names: Sequence[str]) -> str:
    """What an obligation asserts (§7): the sentence the task's text, the
    failure header and the failure notification share."""
    if obligation == TERMINATION:
        return f"{_functions(names)} terminate{'s' if len(names) == 1 else ''}"
    return f"the equations of {_functions(names)} cover every argument and agree where they overlap"


def _tactics_named(obligation: str) -> str:
    return series([f"`{t}`" for t in _TACTICS[obligation]], "or")


def task_text(obligation: str, names: Sequence[str], equations: Sequence[str]) -> str:
    """The task's part of the major agent's initial message (§7): the
    goal, for termination the equations, the tactics to try; a section of
    its own, so it ends in a blank line."""
    lines = [f"Your proof goal (given in `proof.yaml`) is to show {assertion(obligation, names)}"]
    if obligation == TERMINATION:
        lines += [f"  {e}" for e in equations]
    lines.append(f"Typically you should first try applying the `Tactic` operation with {_tactics_named(obligation)}.")
    return "\n".join(lines) + "\n\n"


def goal_hint(names: Sequence[str]) -> str:
    """The termination call's goal hint (§7)."""
    return (f"The goal asserts the termination of {series([f'`{n}`' for n in names], 'and')}."
            f" You may try `Tactic` with {_tactics_named(TERMINATION)}.")


class _Define_Task(StdTask):
    """The task of a construction's call (§7; AoA's USER_OPERATIONS.md
    §4.2): the payload the constants' names and the equations, in the
    `unicode` spelling; the major agent's initial message opens with
    `task_text`, a worker's and the system prompt get nothing."""
    obligation: ClassVar[str]

    def __init__(self, payload: Any):
        self.names, self.equations = payload

    def task_initial(self, role, has_system):
        return task_text(self.obligation, self.names, self.equations) if isinstance(role, Role_Major) else ""


@aoa_task(f"TAT.{PATTERN_COMPLETENESS}")
class Pattern_Completeness_Task(_Define_Task):
    obligation = PATTERN_COMPLETENESS


@aoa_task(f"TAT.{TERMINATION}")
class Termination_Task(_Define_Task):
    obligation = TERMINATION


# --- the node

class Constant_RawAST(TypedDict):
    name: str
    type: NotRequired[str]
    syntax: NotRequired[Mixfix_RawAST]


class Define_RawAST(TypedDict):
    kind: Literal["definition"]
    english: str
    constants: Annotated[list[Constant_RawAST], NON_EMPTY]
    equations: Annotated[list[str], NON_EMPTY]
    auto_reduction: bool


@dataclass(frozen=True)
class Constant:
    """A constant defined (§1, §2): its name in the id grammar, its type and
    its syntax when given."""
    name: str
    type: IsaTerm | None
    syntax: Mixfix | None

    def image(self) -> dict[str, Any]:
        """The store's row, the construct's shape in the `unicode` spelling."""
        return {"name": self.name,
                **({"type": self.type.unicode} if self.type is not None else {}),
                **({"syntax": self.syntax.image()} if self.syntax is not None else {})}

    @classmethod
    def of_image(cls, raw: Constant_RawAST) -> Constant:
        """The construct's constant, normalised, and a stored image read back."""
        type_ = normalised(raw.get("type", ""))
        return cls(raw["name"], IsaTerm.from_agent(type_) if type_ else None,
                   mixfix_of(raw["syntax"]) if "syntax" in raw else None)


class Define_Proof_Job(Proof_Job):
    """`Define`'s proof construction (§7): `Proof_Job`'s call once per open
    obligation, in command order, each under the obligation's setup; a
    failing call ends the run, the node keeping which obligation failed
    for the sentences; the product one proof per open obligation, by its
    key."""

    def _check(self):
        node = self.node
        assert isinstance(node, Define)
        return bool(node.open_obligations()) and super()._check()     # the common `Define` has nothing to prove

    def _failed_assertion(self):
        """The assertion of the obligation the last run did not prove;
        None when the node does not know it (a carried outcome)."""
        node = self.node
        assert isinstance(node, Define)
        failed = node.failed_obligation
        return assertion(failed, node.constant_names()) if failed is not None else None

    def failure_header(self, failure):
        """§7: `Proof_Job`'s header while the failure is still owed — the
        obligation it names open, or, for a carried failure naming none,
        any obligation open —; None once an evaluation has recorded a
        form under which it is not, the block then stale; a node without
        a recorded form keeps the header."""
        node = self.node
        assert isinstance(node, Define)
        if node.form is not None:
            open_ = node.open_obligations()
            failed = node.failed_obligation
            if not (failed in open_ if failed is not None else open_):
                return None
        return super().failure_header(failure)

    async def _run(self):
        node = self.node
        assert isinstance(node, Define)
        proofs: dict[str, Any] = {}
        for obligation in node.open_obligations():
            errors, product = await self.forked(
                "TAT.Proof_Obligation.construct",
                (node.slot_of(obligation).to_msgpack(), node.construction_setup(obligation)))
            if errors:
                node.failed_obligation = obligation
                return Failed("\n".join(errors))
            proofs[obligation] = proof_from_wire(product)
        node.failed_obligation = None
        node.attach_evaluation_job(Define_Proof_Check.passed(node))
        return Succeeded(proofs)


class Define_Proof_Check(Proof_Check):
    """`Define`'s proof check (§7): every open obligation's stored proof
    replayed on its slot's goal in one fork of `TAT.Proof_Obligation.check`,
    an obligation whose proof the product lacks failing it."""

    async def _start(self):
        node = self.node
        assert isinstance(node, Define)
        job = node.job()
        assert job is not None and isinstance(job.outcome, Succeeded)
        proofs = job.outcome.product
        goals = [(node.slot_of(o).to_msgpack(), proof_wire(proofs[o]) if o in proofs else None)
                 for o in node.open_obligations()]
        await isabelle_driver.call(self.conversation, "TAT.Proof_Obligation.check", (goals, self.id))


@TAT_node
class Define(Theory_Member, With_Proof_Obligations, Leaf):
    construct_schema = {
        "type": "object",
        "description": "defines constants by (recursive) equations",
        "properties": {
            "kind": {"const": "definition"},
            "english": {"type": "string", "description": "what is defined, in English, as LaTeX text"},
            "constants": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/Constant"},
                          "description": "the constants defined; several for mutually recursive functions"},
            "equations": {"type": "array", "minItems": 1, "items": {"type": "string"},
                          "description": "the defining equations, one Isabelle equation each, the constant applied to"
                                         " patterns on the left. Example: fib (Suc (Suc n)) = fib n + fib (Suc n)"},
            "auto_reduction": {"type": "boolean",
                               "description": "whether to add the defining equations to the system simplification set"},
        },
        "required": ["kind", "english", "constants", "equations", "auto_reduction"],
        "additionalProperties": False,
        "$defs": {
            "Constant": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string",
                             "description": "the constant's type; left out, Isabelle infers it from the equations"},
                    "syntax": {"$ref": "#/$defs/Mixfix"},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
            **MIXFIX_DEFS,
        },
    }
    argument_schema = Define_RawAST
    construction_job_class = Define_Proof_Job
    evaluation_job_class = Define_Proof_Check
    valid_word, invalid_word = "valid definition", "invalid definition"     # the mark's words (§7) ...
    unverified_word = "unverified definition"                               # ... while a proof is owed

    english: str
    constants: tuple[Constant, ...]
    equations: tuple[IsaTerm, ...]
    auto_reduction: bool
    form: Form | None                       # recorded by the first evaluation that goes through, run again by the
                                            # later ones (§1, §6)
    completeness_method: str | None         # under a function command, the method that closed the goal; None: open
    termination_method: str | None
    failed_obligation: str | None           # recorded by the construction (§7): the obligation its last run did not prove
    completeness_state: Isar_State_Slot     # the two goal slots (§6): each holds its goal open exactly while the
    termination_state: Isar_State_Slot      # node is `ready` and the obligation is open

    def __init__(self, parent, state, english: str, constants: tuple[Constant, ...], equations: tuple[IsaTerm, ...],
                 auto_reduction: bool, form: Form | None = None, completeness_method: str | None = None,
                 termination_method: str | None = None, failed_obligation: str | None = None):
        super().__init__(parent, state)
        self.english = english
        self.constants = constants
        self.name = "_and_".join(c.name for c in constants)    # the node's name: `definition_even_and_odd` (§9)
        self.equations = equations
        self.auto_reduction = auto_reduction
        self.form = form
        self.completeness_method = completeness_method
        self.termination_method = termination_method
        self.failed_obligation = failed_obligation
        self.completeness_state = Isar_State_Slot.assign(state.conversation)    # as `Proof_Obligation` mints `goal_state`
        self.termination_state = Isar_State_Slot.assign(state.conversation)

    @classmethod
    async def gen(cls, config, raw: Define_RawAST):
        """§4's checks in its order: the parent; each constant's name against
        §1's grammar, no two the same; the texts normalised."""
        cls.require_inside_theory(config, raw["kind"])
        constants: list[Constant] = []
        for i, c in enumerate(raw["constants"]):
            require_id_name(c["name"], "constant name")
            check_not_bound_twice(c["name"], f"constants[{i}].name", [x.name for x in constants])
            constants.append(Constant.of_image(c))
        return cls(config.parent, config.state, normalised(raw["english"]), tuple(constants),
                   tuple(IsaTerm.from_agent(normalised(e)) for e in raw["equations"]), raw["auto_reduction"])

    # --- the store (§1): the authored fields in the `unicode` spelling, the construct's shape, and the recorded
    #     ones; every row read with `get`, so that a missing one is refused at start

    def to_store(self, rows):
        rows.put("english", self.english)
        rows.put("constants", [c.image() for c in self.constants])
        rows.put("equations", [e.unicode for e in self.equations])
        rows.put("auto_reduction", self.auto_reduction)
        rows.put("form", self.form)
        rows.put("completeness_method", self.completeness_method)
        rows.put("termination_method", self.termination_method)
        rows.put("failed_obligation", self.failed_obligation)

    @classmethod
    def from_store(cls, config, rows):
        return cls(config.parent, config.state, rows.get("english"),
                   tuple(Constant.of_image(c) for c in rows.get("constants")),
                   tuple(IsaTerm.from_agent(e) for e in rows.get("equations")), rows.get("auto_reduction"),
                   rows.get("form"), rows.get("completeness_method"), rows.get("termination_method"),
                   rows.get("failed_obligation"))

    # --- the obligations (§1, §7)

    def constant_names(self) -> list[str]:
        return [c.name for c in self.constants]

    def _method_of(self, obligation: Obligation) -> str | None:
        """The recorded method that closed the obligation's goal; None while
        the goal stands open (§1)."""
        return {PATTERN_COMPLETENESS: self.completeness_method, TERMINATION: self.termination_method}[obligation]

    def slot_of(self, obligation: Obligation) -> Isar_State_Slot:
        return {PATTERN_COMPLETENESS: self.completeness_state, TERMINATION: self.termination_state}[obligation]

    def open_obligations(self) -> tuple[Obligation, ...]:
        """The obligations the last evaluation left open, in command order:
        under a function command, each whose method is None; none under
        `definition` or before any evaluation."""
        if self.form in (None, DEFINITION):
            return ()
        return tuple(o for o in OBLIGATIONS if self._method_of(o) is None)

    def owes_proof(self):
        return bool(self.open_obligations())

    def construction_setup(self, obligation: Obligation) -> Construction_Setup:
        """The call's setup (§7): the task with its payload, the goal hint for
        termination, the whitelist, and the goal kept as it stands — both
        goals open with a binder, and AoA's automatic Intro on either breaks
        the method it is for."""
        names, equations = self.constant_names(), [e.unicode for e in self.equations]
        hint = (goal_hint(names), _GOAL_HINT_PATTERNS) if obligation == TERMINATION else None
        return ((f"TAT.{obligation}", (names, equations)), hint, [(t, INTERPRETATIONS[t]) for t in _TACTICS[obligation]],
                True)

    def _unfinished(self):
        return super()._unfinished() if self.open_obligations() else None

    # --- the evaluation (§6)

    def goal_structure(self) -> Any:
        """§4: the constants — names, types, syntaxes — and the equations,
        each `IsaTerm` as its `ascii`: what both goals are made of."""
        return ([(c.name, c.type.ascii if c.type is not None else None, mixfix_wire(c.syntax)) for c in self.constants],
                [e.ascii for e in self.equations])

    def message(self) -> Any:
        """The definition as `TAT.Define.evaluate` unpacks it: the goal
        structure, `auto_reduction`, and the recorded `form` — the command
        to run again, None for one to be decided (§6; COMMON.md §5)."""
        return (*self.goal_structure(), self.auto_reduction, self.form)

    def _states_inside(self, out=None):
        out = super()._states_inside(out)
        out += [self.completeness_state, self.termination_state]
        return out

    def _slots_written_by(self, operation):
        return (self.completeness_state, self.termination_state)

    async def _eval_opr(self):
        """The callback with the input slot, the two goal slots, the resulting
        slot and `message()` (§6): the messages make the node an obstacle,
        the records untouched; none records the form — decided on this run
        when none was recorded, the recorded one otherwise — and the two
        methods."""
        messages, what = await isabelle_driver.call(
            self.forest().conversation, "TAT.Define.evaluate",
            (self.state.to_msgpack(), self.completeness_state.to_msgpack(), self.termination_state.to_msgpack(),
             self.resulting_state().to_msgpack(), self.message()))
        if not messages:
            self.form, self.completeness_method, self.termination_method = what
        return status_of_errors(messages)

    # --- the owing line (§7); the mark is `With_Proof_Obligations`'s

    def owing_line(self):
        """What the node owes, the open obligations in command order, while
        its line reads `unverified definition`."""
        if not unverified(self):
            return None
        open_ = self.open_obligations()
        return (f"The definition is unverified until {' and '.join(_WAITED_FOR[o] for o in open_)}"
                f" {'is' if len(open_) == 1 else 'are'} proven.")

    # --- what it prints (§8) and emission (§5)

    def _head(self, write: Callable[[str | IsaTerm], str]) -> str:
        """The constants after the command: each its name, `:: T` when typed,
        its syntax when given, joined by `and`, the name and the type
        through `write`."""
        return " and ".join(" ".join(filter(None, (
            write(c.name), f":: {write(c.type)}" if c.type is not None else "",
            mixfix_text(c.syntax) if c.syntax is not None else ""))) for c in self.constants)

    def print_fields(self, indent, out, mode, depth):
        """Under `Recall` alone (§8): the constants and the equations one
        level deeper at depths 0 to 2, in the stored text; `english` at 0."""
        if mode is RECALL and depth <= 2:
            out.write(INDENT * (indent + 1) + self._head(IsaTerm.to_unicode) + "\n")
            for e in self.equations:
                out.write(INDENT * (indent + 1) + e.unicode + "\n")
        if mode is RECALL and depth == 0:
            out.write(INDENT * indent + self.english + "\n")

    def _command(self) -> str:
        """The command the file carries (§5): `fun` when the recorded form is
        `function (sequential, no_partials)` and no obligation is open —
        `fun` is that command with the two methods that closed the goals —,
        the recorded form otherwise."""
        assert self.form is not None                      # a node written is one an evaluation recorded (`can_emit`)
        return "fun" if self.form == SEQUENTIAL and not self.open_obligations() else self.form

    def _terminal(self, obligation: Obligation) -> str:
        """The terminal proof after an obligation's command (§5): the recorded
        method's `by`, or `proof_text()` for an open one."""
        method = self._method_of(obligation)
        return f"by {method}" if method is not None else self.proof_text()

    def emit(self, indent, out):
        """§5: the `text` line; the command `_command()` names, the equations
        as string tokens, under a function command the two terminal proofs
        around `termination`; the `declare` line where `auto_reduction`
        says otherwise than the command does."""
        names = self.constant_names()
        emit_lines(indent, out, text_line(self.english, f"Definition {' and '.join(names)}."))
        keywords = self.theory().keywords or ()
        def write(text: str | IsaTerm) -> str:
            return print_name(text, keywords)
        command = self._command()
        lines = [f"{command} {self._head(write)} where"]
        lines += [("  " if i == 0 else "| ") + string_token(e.unicode) for i, e in enumerate(self.equations)]
        if command not in (DEFINITION, "fun"):
            lines += [f"  {self._terminal(PATTERN_COMPLETENESS)}", "termination", f"  {self._terminal(TERMINATION)}"]
        if self.form == DEFINITION and self.auto_reduction:
            lines.append(f"declare {write(names[0] + '_def')} [simp]")
        elif self.form != DEFINITION and not self.auto_reduction:
            # a long identifier, which no keyword can be: written bare
            lines.append("declare " + " ".join(f"{n}.simps" for n in names) + " [simp del]")
        emit_lines(indent, out, "\n".join(lines))
        return indent
