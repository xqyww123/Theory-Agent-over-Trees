"""What the classes of the plugin `Isabelle_Std` share
(node_classes/COMMON.md): `Theory_Member`, the base every class derives
from, with the plugin's one parent exception `NotInsideTheory` (§1); the
`text` line (§2); `Proof_Obligation`, the base of the classes whose
command opens a proof obligation, with its two job classes (§3); the
package's compile hook for AoA's proof stores (§3; COMPILATION.md §5);
and the theory the plugin declares the forest's theories import
(PLUGIN_SYSTEM §1)."""

from __future__ import annotations

import re
from abc import abstractmethod
from typing import Any, ClassVar

import IsaMini.AoA  # noqa: F401  # the remote procedure `IsaMini.AoA`, served by this process (§3)
from Isabelle_RPC_Host.unicode import IsaTerm

from .. import isabelle_driver, jobs
from ..compile import identity, paths
from ..exceptions import BadEdit
from ..jobs import PASSED, RUNNING, Failed, Succeeded, with_message
from ..model import (
    CannotEvaluate, Forest, Isar_State_Slot, Location, Node, NodeConfig, NonLeaf_Node, Ready, Theory,
    cartouche, status_of_errors)
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
    """The base of a `Leaf` whose one command opens exactly one goal,
    admitted as the operation's last transition (§3), taken before the
    framework base: `class Theorem(Theory_Member, Proof_Obligation, Leaf)`.
    The tree holds no proof: every evaluation admits the goal, the proof
    construction finds the proof, the proof check replays it, and the
    file carries `by aoa`.  Derives from `Node`, so that the abstract
    methods are enforced at the class's first instantiation."""

    construction_job_class = Proof_Job
    evaluation_job_class = Proof_Check

    evaluation_callback: ClassVar[str]      # the class's callback, built by `TAT_Proof_Obligation.register`
                                            # from its two steps, `open_goal` and `after_admission` (§3)
    valid_word: ClassVar[str]               # the mark's first slot under `ready` ...
    invalid_word: ClassVar[str]             # ... and under `cannot_evaluate`

    goal_state: Isar_State_Slot             # the state with the goal open and no step taken, held
                                            # exactly while the node is `ready`; never stored

    def __init__(self, parent: NonLeaf_Node, state: Isar_State_Slot):
        super().__init__(parent, state)
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
        return (self.goal_state,)

    def record_from_evaluation(self, what: Any) -> tuple[IsaTerm, ...]:
        """What the two steps yielded, `[a, b]` on the wire, recorded on the
        node; answers the messages the `Ready` carries (§3).  The default
        records nothing and answers `()`."""
        return ()

    async def _eval_opr(self):
        """The class's callback (§3) with the input slot, `goal_state`, the
        resulting slot and `message()`: the goal opened into `goal_state`,
        admitted into the resulting slot with the class's commands after
        the admission.  Its answer is the messages and, when there are
        none, what the two steps yielded: the messages make the node an
        obstacle; none is `Ready` carrying what `record_from_evaluation`
        answers."""
        messages, what = await isabelle_driver.call(
            self.forest().conversation, type(self).evaluation_callback,
            (self.state.to_msgpack(), self.goal_state.to_msgpack(), self.resulting_state().to_msgpack(),
             self.message()))
        if messages:
            return status_of_errors(messages)
        return Ready(self.record_from_evaluation(what))

    def mark(self, mode, depth):
        """Two slots, `(<status>, <proof>)` (§3): the class's word for the
        evaluation status; the proof's from the job's outcome and the
        check, left out under the invalid word, a stored proof left out
        under `not evaluated`."""
        (status,) = self.evaluation_statuses()
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
