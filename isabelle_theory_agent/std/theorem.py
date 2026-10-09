"""`Theorem`, the first node class of the plugin `Isabelle_Std`
(node_classes/THEOREM.md): a fact stated and admitted, never proved in
the tree — its evaluation opens the goal and admits it, its construction
job finds a proof and its evaluation job replays it, the emitted theory
carrying `by aoa`."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

import IsaMini.AoA  # noqa: F401  # the remote procedure `IsaMini.AoA`, served by this process (§7)
from Isabelle_RPC_Host.unicode import IsaTerm, is_identifier

from .. import isabelle_driver, jobs
from ..compile import paths
from ..exceptions import BadTheoremNodeParent, InvalidField, InvalidName
from ..jobs import PASSED, RUNNING, Failed, Succeeded, with_message
from ..model import (
    INDENT, RECALL, CannotEvaluate, Forest, Isar_State_Slot, Leaf, Node, Ready, Theory, _emit_lines,
    _parent_id, cartouche)
from ..plugin import TAT_compile_hook, TAT_node
from .statement import STATEMENT_DEFS, LongStatement_RawAST

KINDS = ("lemma", "theorem", "corollary", "proposition")   # the Isar commands Isabelle treats alike
_FACT_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_']*")        # the id grammar without hyphens (§1)
_RULE_SYMBOLS = ("⋀", "⟹", "\\<And>", "\\<Longrightarrow>")   # what a part is parenthesised for (§8)


class Theorem_RawAST(TypedDict):
    kind: Literal["lemma", "theorem", "corollary", "proposition"]
    name: str
    statement: LongStatement_RawAST


@dataclass(frozen=True)
class Variable:
    name: IsaTerm
    type: IsaTerm | None            # None when untyped: fixed bare (§5)


@dataclass(frozen=True)
class Premise:
    name: IsaTerm
    term: IsaTerm


@dataclass(frozen=True)
class Statement:
    """A `LongStatement` as the node holds it (§2): every piece of Isabelle
    text an `IsaTerm`, the texts normalised once by `gen`."""
    english: str
    for_any: tuple[Variable, ...]
    premises: tuple[Premise, ...]
    conclusion: IsaTerm

    def structure(self) -> Any:
        """The statement as structure, each `IsaTerm` as its `ascii`: what
        the evaluation sends to Isabelle (§6) and what an amend compares
        (§4), `english` aside."""
        return ([(v.name.ascii, v.type.ascii if v.type is not None else None) for v in self.for_any],
                [(p.name.ascii, p.term.ascii) for p in self.premises],
                self.conclusion.ascii)

    def proposition(self) -> str:
        """The whole statement in Isabelle's meta form (§8): one `⋀` per
        variable, `::T` when typed, one `⟹` per premise, names dropped, a
        part holding `⋀` or `⟹` itself in parentheses."""
        def part(term: IsaTerm) -> str:
            text = term.unicode
            return f"({text})" if any(s in text for s in _RULE_SYMBOLS) else text
        binders = "".join(f"⋀{v.name.unicode}{'::' + v.type.unicode if v.type is not None else ''}. "
                          for v in self.for_any)
        return binders + " ⟹ ".join([*(part(p.term) for p in self.premises), part(self.conclusion)])

    def image(self) -> dict[str, Any]:
        """The store's row, in the `unicode` spelling (§2)."""
        return {"english": self.english,
                "for_any": [{"name": v.name.unicode, **({"type": v.type.unicode} if v.type is not None else {})}
                            for v in self.for_any],
                "premises": [{"name": p.name.unicode, "term": p.term.unicode} for p in self.premises],
                "conclusion": self.conclusion.unicode}

    @classmethod
    def of_image(cls, image: dict[str, Any]) -> Statement:
        return cls(image["english"],
                   tuple(Variable(IsaTerm.from_agent(v["name"]),
                                  IsaTerm.from_agent(v["type"]) if "type" in v else None)
                         for v in image["for_any"]),
                   tuple(Premise(IsaTerm.from_agent(p["name"]), IsaTerm.from_agent(p["term"]))
                         for p in image["premises"]),
                   IsaTerm.from_agent(image["conclusion"]))


def _normalised(text: str) -> str:
    """Newlines spaces, runs of whitespace one space (§2)."""
    return " ".join(text.split())


_PRODUCT = ("text", "thread_cpu", "wall")    # the proof as stored (§1); on the wire, a triple in this order


class Proof_Job(jobs.Construction_Job):
    """`Theorem`'s proof construction (§7): one call of AoA's standard entry
    on the goal `goal_state` holds, forked by `TAT.Theorem.construct`; the
    product the proof — the method text with the two times of its replay —
    and the node's check `Proof_Check.passed` from the run's settlement."""

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
        """§7's table: a proof is constructed where none stands, or where
        the one standing failed its check; a proof not yet checked, or
        checked and passed, stands."""
        if not isinstance(self.outcome, Succeeded):
            return True
        return isinstance(self.node.check_outcome(), Failed)

    async def _run(self):
        node = self.node
        assert isinstance(node, Theorem)
        errors, product = await self.forked("TAT.Theorem.construct", node.goal_state.to_msgpack())
        if errors:
            return Failed("\n".join(errors))
        node.attach_evaluation_job(Proof_Check.passed(node))
        return Succeeded(dict(zip(_PRODUCT, product)))


class Proof_Check(jobs.Evaluation_Job):
    """`Theorem`'s proof check (§7): the stored product replayed on the goal
    `goal_state` holds, through the function AoA exports, forked by
    `TAT.Theorem.check`; no theorem out is `FAILED` with an empty message."""

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
        """The check a proof construction attaches at its settlement (§7):
        `PASSED` without running."""
        job = cls(node, None)
        job.outcome = PASSED
        return job

    async def _start(self):
        node = self.node
        assert isinstance(node, Theorem)
        job = node.job()
        assert job is not None and isinstance(job.outcome, Succeeded)   # a check runs on a proven node (§3.3)
        product = job.outcome.product
        await isabelle_driver.call(self.conversation, "TAT.Theorem.check",
                                   (node.goal_state.to_msgpack(), tuple(product[k] for k in _PRODUCT), self.id))


@TAT_node
class Theorem(Leaf):
    construct_schema = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": list(KINDS)},
            "name": {"type": "string", "description": "The fact's name"},
            "statement": {"$ref": "#/$defs/LongStatement"},
        },
        "required": ["kind", "name", "statement"],
        "additionalProperties": False,
        "$defs": STATEMENT_DEFS,
    }
    argument_schema = Theorem_RawAST
    construction_job_class = Proof_Job
    evaluation_job_class = Proof_Check

    name: str
    statement: Statement
    reserved_names: frozenset[str]      # the statement's names the last evaluation found reserved,
                                        # in their `ascii` spelling, quoted at emission (§1, §5); stored
    goal_state: Isar_State_Slot         # the state with the goal open and no step taken, held
                                        # exactly while the node is `ready` (§1, §6); never stored

    def __init__(self, parent, state, name: str, statement: Statement, goal_state: Isar_State_Slot,
                 reserved_names: frozenset[str] = frozenset()):
        super().__init__(parent, state)
        self.name = name
        self.statement = statement
        self.goal_state = goal_state
        self.reserved_names = reserved_names

    @classmethod
    async def gen(cls, config, raw: Theorem_RawAST):
        if not _inside_a_theory(config.parent):
            raise BadTheoremNodeParent(raw["kind"], _parent_id(config))
        name = raw["name"]
        if not _FACT_NAME.fullmatch(name) or name.endswith("_"):
            raise InvalidName(name, "fact name")
        statement = _statement_of(raw["statement"])
        conversation = config.parent.forest().conversation
        node = cls(config.parent, config.state, name, statement, Isar_State_Slot.assign(conversation))
        old = config.replaces()
        if isinstance(old, cls) and old.statement.structure() == statement.structure():
            node.carry_job_from(old)             # the proof stands: its outcome is carried (§4)
        return node

    def to_store(self, rows):
        rows.put("name", self.name)
        rows.put("statement", self.statement.image())
        rows.put("reserved_names", sorted(self.reserved_names))

    @classmethod
    def from_store(cls, config, rows):
        conversation = config.parent.forest().conversation
        return cls(config.parent, config.state, rows.get("name"), Statement.of_image(rows.get("statement")),
                   Isar_State_Slot.assign(conversation), frozenset(rows.fields().get("reserved_names", [])))

    def _states_inside(self, out=None):
        out = super()._states_inside(out)
        out.append(self.goal_state)
        return out

    def _slots_written_by(self, operation):
        return (self.goal_state,)

    async def _eval_opr(self):
        """`TAT.Theorem.evaluate` (§6): the statement opened and admitted in
        two transitions, the goal into `goal_state`, the admitted fact into
        the resulting slot; failed, the node is an obstacle with the
        messages; passed, `Ready` with what Isabelle said, the names it
        would quote recorded."""
        conversation = self.forest().conversation
        passed, messages, reserved = await isabelle_driver.call(
            conversation, "TAT.Theorem.evaluate",
            (self.state.to_msgpack(), self.goal_state.to_msgpack(), self.resulting_state().to_msgpack(),
             (self.kind, self.name, *self.statement.structure())))
        texts = tuple(IsaTerm.from_isabelle(m) for m in messages)
        if not passed:
            return CannotEvaluate(texts)
        self.reserved_names = frozenset(reserved)
        return Ready(texts)

    # --- what it prints (§7, §8)

    def mark(self, mode, depth):
        """Two slots, `(<statement>, <proof>)` (§7): the statement's from the
        evaluation status; the proof's from the job's outcome and the
        check, left out under `invalid statement`, a stored proof left out
        under `not evaluated`; no proof slot while no job class is named."""
        if isinstance(self._status, CannotEvaluate):
            return "invalid statement"
        statement = "valid statement" if isinstance(self._status, Ready) else "not evaluated"
        job = self.job()
        if job is None:
            return statement
        outcome = job.outcome
        if outcome is RUNNING:
            proof = "proving"
        elif isinstance(outcome, Failed):
            proof = "failed to prove"
        elif isinstance(outcome, Succeeded):
            if statement == "not evaluated":
                return statement
            check = self.check_outcome()
            proof = ("unchecked proof" if check is None else "proof checking" if check is RUNNING
                     else "proven" if check is PASSED else "bad proof")
        else:
            proof = "proof not started"
        return f"{statement}, {proof}"

    def print_fields(self, indent, out, mode, depth):
        """Under `Recall` alone (§8): the proposition at depths 0 to 2,
        `english` at 0 and 1."""
        if mode is RECALL and depth <= 2:
            out.write(INDENT * indent + self.statement.proposition() + "\n")
        if mode is RECALL and depth <= 1:
            out.write(INDENT * indent + self.statement.english + "\n")

    # --- emission (§5)

    def emit(self, indent, out):
        english = self.statement.english
        if english and english[-1] not in ".!?":
            english += "."
        _emit_lines(indent, out, f"text {cartouche(f'{self.kind.capitalize()} {self.name}. {english}')}")
        lines = [f"{self.kind} {self._quoted(self.name)}:"]
        if self.statement.for_any:
            lines.append("  fixes " + " and ".join(
                self._quoted(v.name.ascii) + (f' :: "{v.type.ascii}"' if v.type is not None else "")
                for v in self.statement.for_any))
        if self.statement.premises:
            lines.append("  assumes " + " and ".join(
                f'{self._quoted(p.name.ascii)}: "{p.term.ascii}"' for p in self.statement.premises))
        lines.append(f'  shows "{self.statement.conclusion.ascii}"')
        job = self.job()
        proven = job is not None and isinstance(job.outcome, Succeeded) and self.check_outcome() is PASSED
        lines.append("  by aoa" if proven else "  sorry")
        _emit_lines(indent, out, "\n".join(lines))
        return indent

    def _quoted(self, name: str) -> str:
        """A reserved name in double quotes, as `Token.print_name` would
        write it (§5); every other bare."""
        return f'"{name}"' if name in self.reserved_names else name


@TAT_compile_hook
def remove_proof_stores_of_no_tree(forest: Forest) -> None:
    """The package's compile hook (COMPILATION.md §5): AoA keeps a theory's
    proofs in `<T>.proof-store` beside its file, with `<T>.proof-store.*`
    for its lock and a temporary file.  Each the path listing yields whose
    `<folder>/<T>.thy` is no tree's file path goes, and nothing else."""
    directory = forest.conversation.working_directory
    files = {tree.file_path() for tree in forest._trees()}
    for entry in list(paths(directory)):
        name, found, rest = entry.path.name.partition(".proof-store")
        if (entry.kind != "folder" and name and found and (not rest or rest.startswith("."))
                and entry.path.parent / f"{name}.thy" not in files):
            (directory / entry.path).unlink()


def _inside_a_theory(parent: Node) -> bool:
    """Whether `parent` is a `Theory` or a nesting node under one (§4)."""
    n: Node | None = parent
    while n is not None:
        if isinstance(n, Theory):
            return True
        n = n.parent
    return False


def _statement_of(raw: LongStatement_RawAST) -> Statement:
    """The construct's statement, normalised (§2) and checked (§4): every
    variable's and premise's name an Isabelle identifier on its `ascii`
    form, a variable's not ending with an underscore, no two of either the
    same."""
    variables: list[Variable] = []
    for i, v in enumerate(raw.get("for_any", [])):
        name = IsaTerm.from_agent(v["name"])
        _check_name(name, f"statement.for_any[{i}].name", [x.name for x in variables], variable=True)
        type_ = _normalised(v.get("type", ""))
        variables.append(Variable(name, IsaTerm.from_agent(type_) if type_ else None))
    premises: list[Premise] = []
    for i, p in enumerate(raw.get("premises", [])):
        name = IsaTerm.from_agent(p["name"])
        _check_name(name, f"statement.premises[{i}].name", [x.name for x in premises], variable=False)
        premises.append(Premise(name, IsaTerm.from_agent(_normalised(p["term"]))))
    return Statement(_normalised(raw["english"]), tuple(variables), tuple(premises),
                     IsaTerm.from_agent(_normalised(raw["conclusion"])))


def _check_name(name: IsaTerm, field: str, earlier: list[IsaTerm], *, variable: bool) -> None:
    if not is_identifier(name.ascii):
        raise InvalidField(field, "must be an Isabelle identifier")
    if variable and name.ascii.endswith("_"):
        raise InvalidField(field, "must not end with an underscore")
    if any(e.ascii == name.ascii for e in earlier):
        raise InvalidField(field, f"binds `{name.unicode}` a second time")
