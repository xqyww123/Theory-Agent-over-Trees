"""The forest: nodes, state slots, evaluation and invalidation, ids,
persistence, the `Conversation`, and the two node classes that carry the
forest's structure, `Session` and `Theory` (ARCHITECTURE §3,
MODULE_STRUCTURE §4.1).  Changing the forest is `edit.py`; what a node
class may declare is `plugin.py`.

Every method that touches Isabelle is async, since `Connection.callback` is.
"""

from __future__ import annotations

import asyncio
import difflib
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, ClassVar, Literal, NamedTuple, NotRequired, Self, TypeAlias, TypedDict

from Isabelle_RPC_Host import Connection

from . import isabelle_driver
from .exceptions import (
    AmbiguousId, BadEdit, BadSessionNodeParent, BadTheoryNodeParent,
    DuplicateTheoryShortName, InvalidField, InvalidName, NodeNotFound, TAT_Error,
    TAT_InternalError, TAT_StartupError)
from .store import Forest_Store, MissingRow, Node_Rows


# A JSON schema, as `json` reads it.  (`TypeAlias` rather than the `type`
# statement: the package supports Python 3.11.)
JSON_Schema: TypeAlias = dict[str, Any]


# ---------------------------------------------------------------------------
# State slots

class Isar_State_Slot:
    """A name in the ML side's state slot table (EVALUATOR_DESIGN §1.1).

    Python never holds the `Toplevel.state`; it holds the name.  Whether the
    table currently has a value under the name is asked of the table
    (`is_initialized`), never mirrored here.  On the wire a slot is its name.
    """

    _counter: ClassVar[int] = 0

    def __init__(self, connection: Connection, name: str):
        self.connection = connection
        self.name = name

    @classmethod
    def assign(cls, connection: Connection) -> Isar_State_Slot:
        cls._counter += 1
        return cls(connection, f"${cls._counter}")

    def to_msgpack(self) -> str:
        return self.name

    @staticmethod
    def from_msgpack(conn: Connection, name: str) -> Isar_State_Slot:
        return Isar_State_Slot(conn, name)

    async def is_initialized(self) -> bool:
        return await isabelle_driver.state_exists(self.connection, self.name)

    async def delete(self) -> None:
        """Remove the value from the table.  The slot keeps its name."""
        await isabelle_driver.state_delete(self.connection, [self.name])

    async def copy_to(self, other: Isar_State_Slot) -> None:
        await isabelle_driver.state_copy(self.connection, self.name, other.name)

    def __repr__(self) -> str:
        return f"Isar_State_Slot({self.name})"


# ---------------------------------------------------------------------------
# Evaluation status (ARCHITECTURE §3.2, §3.3)

class _Singleton:
    """One instance per class, so `is` is always right."""

    def __new__(cls) -> Self:
        inst = cls.__dict__.get("_instance")
        if inst is None:
            inst = super().__new__(cls)
            cls._instance = inst
        return inst

    def __repr__(self) -> str:
        return type(self).__name__


class NotEvaluated(_Singleton):
    """No current result; nothing in the resulting state to rely on."""

class Ready(_Singleton):
    """The operation ran and its resulting state is current.  Evaluation
    passes through."""

@dataclass(frozen=True)
class CannotEvaluate:
    """Evaluation does not pass through.  `blocked_by` None: the node itself
    is the obstacle (its class judged the failure fatal); it is not rerun
    until edited.  Otherwise: the node sits under or after the obstacle
    named, and runs as soon as it is reached unblocked."""
    blocked_by: Node | None

NOT_EVALUATED = NotEvaluated()
READY = Ready()

EvaluationStatus = NotEvaluated | Ready | CannotEvaluate


def _is_own_stop(status: EvaluationStatus) -> bool:
    return isinstance(status, CannotEvaluate) and status.blocked_by is None


def _wrote(status: EvaluationStatus) -> bool:
    """Whether an operation in this status has written its resulting state:
    `ready`, or an own stop, which copied its input through
    (ARCHITECTURE §3.1)."""
    return status is READY or _is_own_stop(status)


# ---------------------------------------------------------------------------
# One evaluation (ARCHITECTURE §3.5)

class Evaluation:
    """One walk: its two constants, and the states it releases, deleted in
    one round trip when it ends.  `destination` is the node an evaluating
    walk runs up to and including; an invalidate-only walk has none — its
    starting position rides in its `Seeking` mode."""

    def __init__(self, destination: Node | None, ignore_error: bool):
        self.destination = destination
        self.ignore_error = ignore_error
        self._released: set[str] = set()

    def release(self, slot: Isar_State_Slot) -> None:
        self._released.add(slot.name)

    async def flush(self, connection: Connection) -> None:
        if self._released:
            await isabelle_driver.state_delete(connection, sorted(self._released))
            self._released.clear()


@dataclass(frozen=True)
class Evaluating:
    """Before the destination: run what is not `Ready` — unless `blocked_by`
    is set, when nothing runs and each node is marked `CannotEvaluate` with
    it.  `rewritten`: the state at this position was written by an
    operation that ran in this walk, so whatever stands here runs again
    even if `Ready` or an own stop — its input changed under it."""
    blocked_by: Node | None = None
    rewritten: bool = False

@dataclass(frozen=True)
class Seeking:
    """Before `destination` without evaluating: touch nothing.  The
    destination is a position, not a node, so the walk turns `Invalidating`
    before entering whatever stands there — a nesting node is then
    invalidated whole, opening first (MODULE_STRUCTURE §4.1)."""
    destination: Location

class Invalidating(_Singleton):
    """Past the destination: mark `NotEvaluated`."""

INVALIDATING = Invalidating()

Mode = Evaluating | Seeking | Invalidating


@dataclass(frozen=True)
class EvaluationResult:
    stopped_at: Node | None      # the obstacle that ended evaluation, if one did
    mode: Mode                   # the mode the node after this one runs under


# ---------------------------------------------------------------------------
# Nodes

_NAME_GRAMMAR = re.compile(r"[A-Za-z][A-Za-z0-9_'-]*")


def is_valid_name(name: str) -> bool:
    """The name grammar of MCP_SPECIFICATION §2: a letter followed by
    letters, digits, underscores, primes and interior hyphens — a hyphen or
    underscore may not end a name, and a hyphen cannot begin one, since a
    name starts with a letter.  Judged on both halves of an id component
    `<kind>_<name>`: the agent's name by `edit._construct_siblings`, a
    class's kinds by `plugin._check_class`.  The forest root's id
    `Sessions` needs no reservation: an id component always carries an
    underscore."""
    return bool(_NAME_GRAMMAR.fullmatch(name)) and not name.endswith(("-", "_"))


@dataclass(frozen=True)
class Location:
    """A resolved place in the forest (ARCHITECTURE §1): the parent and the
    index within its `sub_nodes`."""
    parent: NonLeaf_Node
    index: int


class Node(ABC):
    """The Python half of a node class (ARCHITECTURE §6).

    `state` is the state before the node.  The state after it,
    `resulting_state()`, is under a chaining parent the next sibling's
    `state` or the parent's state after all children, and under an
    `Unchained_Node` a slot the node owns (`Theory`).
    """

    parent: NonLeaf_Node | None
    state: Isar_State_Slot
    name: str            # the name as the agent supplied it, set by `gen`: the `P`
                         # of `lemma_P` (MCP_SPECIFICATION §2); `id_component` is
                         # what the id shows
    # The framework's two fields, set by it when the node enters the forest
    # (`edit._construct_element`) or is loaded (`Forest._load_subtree`); no class
    # sets or stores them.
    identity: int        # opaque; survives renaming, moving and restarts
    kind: str            # the construct's `kind`, under which the class was registered

    # The three id properties a node class declares (MCP_SPECIFICATION §2.1).
    # Among droppable components the lowest `drop_priority` goes first;
    # it matters only when `output_omissible`.
    output_omissible: ClassVar[bool] = False
    input_omissible: ClassVar[bool] = False
    drop_priority: ClassVar[int] = 0

    # The two schemas of a construct of this class (PLUGIN_SYSTEM §2): the
    # complete JSON schema for the agent, and a TypedDict of the same fields
    # the framework checks a submitted construct against before `gen` is
    # consulted, and which types `gen`'s `raw` for the static checker.  The
    # loader requires both and holds them to each other (PLUGIN_SYSTEM §5).
    construct_schema: ClassVar[JSON_Schema | None] = None
    argument_schema: ClassVar[Any] = None

    # The forest-wide namespace the node's `name` lives in, if any
    # (PLUGIN_SYSTEM §2): `Theory`'s short names.  The framework checks the
    # name against the forest and the call when the node is built
    # (`edit._take_name`).
    namespace: ClassVar[Namespace | None] = None

    @classmethod
    async def gen(cls, config: NodeConfig, raw: Any) -> Self:
        """Semantic construction from the agent's construct — `raw`, the
        RawAST, which the class annotates with its own `argument_schema`
        TypedDict (MODULE_STRUCTURE §4.1): judge the fields' meaning, refuse
        a parent the class cannot live under, and build the node from
        `config`.  May read over the wire through the framework's query
        callbacks; must not write.  Raises `TAT_Error`s bare — the framework
        prefixes the `raw_ast_path` (EXCEPTIONS.md §5)."""
        raise TAT_InternalError(f"{cls.__name__} has no gen")

    # --- Persistence (ARCHITECTURE §4.1, the plan's §2): each class writes
    # and reads its own fields; `kind` and `children` are the framework's.

    def to_store(self, rows: Node_Rows) -> None:
        """Write the authored fields, and the recorded fields the class keeps
        across a restart — not one held only for the life of the
        conversation, such as `Theory`'s error messages.  Every value must
        be MessagePack-representable, and no recorded value may mean "work
        is running": a loaded forest holds results, never work in flight."""
        raise TAT_InternalError(f"{type(self).__name__} has no to_store")

    @classmethod
    def from_store(cls, config: NodeConfig, rows: Node_Rows) -> Self:
        """Rebuild the node from what `to_store` wrote: `gen` with `rows` in
        place of `raw` — `config.parent` the rebuilt parent, `config.state` a
        fresh slot, `config.replacing` None.  Synchronous: nothing over the
        wire.  Returns the node without children; the framework loads them."""
        raise TAT_InternalError(f"{cls.__name__} has no from_store")

    def __init__(self, parent: NonLeaf_Node | None, state: Isar_State_Slot):
        self.parent = parent
        self.state = state

    def id_component(self) -> str:
        """The node's one component of an id, `<kind>_<name>`
        (MCP_SPECIFICATION §2): `lemma_P`, `theory_X`, `session_Arith`."""
        return f"{self.kind}_{self.name}"

    def index_of(self) -> int:
        """The node's position in its parent's `sub_nodes` — computed, never
        stored (MODULE_STRUCTURE §4.1)."""
        if self.parent is None:
            raise TAT_InternalError("a node without a parent has no position")
        for i, c in enumerate(self.parent.sub_nodes):
            if c is self:
                return i
        raise TAT_InternalError("not my child")

    def resulting_state(self) -> Isar_State_Slot:
        if self.parent is None:
            raise TAT_InternalError(
                "a node without a parent has no resulting state")
        return self.parent._resulting_state_of_child(self)

    def forest(self) -> Forest:
        n = self
        while n.parent is not None:
            n = n.parent
        assert isinstance(n, Forest)
        return n

    # --- Subtree traversals.  Each appends to `out` and returns it, so a
    # walk over many nodes fills one list instead of concatenating one per
    # node; a nesting class extends them over its children.

    def _tree_order(self, out: list[Node] | None = None) -> list[Node]:
        """The node and its subtree: parents before children, siblings in
        order (ARCHITECTURE §1)."""
        if out is None:
            out = []
        out.append(self)
        return out

    def _children_first(self, out: list[Node] | None = None) -> list[Node]:
        """The subtree with children before parents: the order of
        `on_deleting` and `on_deleted` (MODULE_STRUCTURE §4.1)."""
        if out is None:
            out = []
        out.append(self)
        return out

    def is_finished(self) -> bool:
        """Whether the node still owes anything (ARCHITECTURE §3.2): every
        operation of the node and of its subtree `Ready`, and it and every
        node below owing nothing.  The one question asked of a node from
        outside, and the framework's derivation: a class overrides
        `_owes_nothing`, never this (PLUGIN_SYSTEM §5)."""
        return all(n._operations_ready() and n._owes_nothing() for n in self._tree_order())

    def _owes_nothing(self) -> bool:
        """The class's own part of `is_finished`: `Theorem` owes a proof
        until it has one.  True by default (ARCHITECTURE §3.2)."""
        return True

    @abstractmethod
    def _operations_ready(self) -> bool:
        """Whether every operation of this node — not its subtree — is
        `Ready`."""

    # --- Event hooks (MODULE_STRUCTURE §4.1), empty by default, driven by
    # the framework; two more, on_removing_child and on_added_child, live on
    # NonLeaf_Node.  The tense is the contract: a progressive hook is a gate
    # — it fires before the commit, is free of side effects, and `BadEdit`
    # is its only veto; a completed hook is for effect, and raising there is
    # the class's bug (EXCEPTIONS.md §1).

    def on_invalidated(self, operation: Any) -> None:
        """Completed: an operation's status truly left `ready`
        (ARCHITECTURE §3.6).  `operation` says which — a `StdBlock` passes
        "beginning" or "ending", a `Leaf` passes None, a class with its own
        statuses passes its own value.  A class with work in flight
        overrides it."""

    def on_deleting(self, reason: Literal["delete", "amend"]) -> None:
        """Gate: the node is to leave for good — `delete` takes the whole
        subtree, children first; `amend`, the replaced node alone."""

    def on_deleted(self, reason: Literal["delete", "amend"]) -> None:
        """Completed: it left; the Python object is still whole — cancel
        running work here."""

    def on_inserted(self) -> None:
        """Completed: linked in, children and all."""

    def on_inheriting(self, new_parent: NonLeaf_Node) -> None:
        """Gate: this node, a direct child of a replaced node, is to pass to
        the replacement; never recursive — grandchildren see nothing."""

    def on_inherited(self, old_parent: NonLeaf_Node) -> None:
        """Completed: the reparenting happened."""

    def on_moving(self, new_location: Location) -> None:
        """Gate: the node is to move; `new_location` is where it is going."""

    def on_moved(self, old_location: Location) -> None:
        """Completed: it moved; `old_location` is where it came from."""

    @abstractmethod
    def _last_status(self) -> EvaluationStatus:
        """The status of the node's last operation — the one that writes its
        resulting state.  Framework-only: what a node class asks of another
        node is `is_finished()`."""

    def _states_inside(self, out: list[Isar_State_Slot] | None = None
                       ) -> list[Isar_State_Slot]:
        """Every state owned by this subtree, appended to `out`: `state` and,
        under a nesting node, its children's and the one after them.  The
        resulting state is not among them — it is the successor's — unless
        the node owns it, as a `Theory` does."""
        if out is None:
            out = []
        out.append(self.state)
        return out

    @abstractmethod
    async def _evaluate(self, ev: Evaluation, mode: Mode) -> EvaluationResult:
        """One recursion for evaluation and invalidation (ARCHITECTURE §3.5),
        visiting every node of the subtree under `mode`.  A nesting node is
        reached at its ending, so its children come before it."""

    @abstractmethod
    async def _mark_not_evaluated(self, ev: Evaluation) -> None:
        """Mark the node — for a nesting node, its ending — `NotEvaluated`.
        What an edit does before evaluating."""

    def _mode_after(self, ev: Evaluation, mode: Evaluating, stop: Node | None,
                    ran: bool) -> Mode:
        """The one place the mode changes: the destination turns it into
        `Invalidating`; otherwise a stop blocks what follows, and `ran` tells
        the successor whether its input was just rewritten."""
        if self is ev.destination:
            return INVALIDATING
        if stop is not None:
            return Evaluating(stop)
        return Evaluating(mode.blocked_by, rewritten=ran)

    async def evaluate_to(self, ignore_error: bool, evaluate: bool = True) -> EvaluationResult:
        """The `evaluate_to` tool's entry: takes the forest's lock itself —
        an edit, whose tool entry already holds it, drives the walk through
        `Forest._run` instead (MODULE_STRUCTURE §4.1).  With
        `evaluate`: run up to and including this node.  Without: only
        invalidate from this node on.  The walk visits every node, so the
        result's `mode` is always `Invalidating`; what happened to this node
        it reports itself."""
        forest = self.forest()
        async with forest.lock:
            if evaluate:
                return await forest._run(Evaluation(self, ignore_error), Evaluating())
            if self.parent is None:
                raise TAT_InternalError("the forest root has no position")
            return await forest._invalidate_from(Location(self.parent, self.index_of()))


class Leaf(Node):

    _status: EvaluationStatus

    def __init__(self, parent, state):
        super().__init__(parent, state)
        self._status = NOT_EVALUATED

    def _last_status(self):
        return self._status

    def _operations_ready(self):
        return self._status is READY

    def _set_status(self, ev: Evaluation, new: EvaluationStatus) -> None:
        old = self._status
        if _wrote(old) and not _wrote(new):       # written -> unwritten; a rewrite releases nothing
            ev.release(self.resulting_state())
        self._status = new
        if old is READY and new is not READY:
            _completed(self.on_invalidated, None)

    async def _mark_not_evaluated(self, ev):
        if self._status is not NOT_EVALUATED:
            self._set_status(ev, NOT_EVALUATED)

    @abstractmethod
    async def _eval_opr(self) -> bool:
        """Run the node from `state` into `resulting_state()`.  Return whether
        evaluation passes through it; on False the framework copies `state`
        into `resulting_state()`, which `ignore_error` will run from."""

    async def _evaluate(self, ev, mode):
        if isinstance(mode, Evaluating):
            stop, ran = None, False
            if mode.blocked_by is not None:
                if not _is_own_stop(self._status):        # an own stop keeps reporting itself
                    self._set_status(ev, CannotEvaluate(mode.blocked_by))
            else:
                # Not rerun: a Ready operation, or an own stop — unless the
                # input under it was rewritten this walk.
                if mode.rewritten or not _wrote(self._status):
                    ran = True
                    if await self._eval_opr():
                        self._set_status(ev, READY)
                    else:
                        await self.state.copy_to(self.resulting_state())
                        self._set_status(ev, CannotEvaluate(None))
                if self._status is not READY and not ev.ignore_error:
                    stop = self
            return EvaluationResult(stop, self._mode_after(ev, mode, stop, ran))
        if isinstance(mode, Seeking):
            return EvaluationResult(None, mode)
        await self._mark_not_evaluated(ev)                 # past the destination
        return EvaluationResult(None, INVALIDATING)


class NonLeaf_Node(Node):

    sub_nodes: list[Node]

    def __init__(self, parent, state, sub_nodes: list[Node]):
        super().__init__(parent, state)
        self.sub_nodes = sub_nodes

    def _tree_order(self, out=None):
        out = super()._tree_order(out)
        for c in self.sub_nodes:
            c._tree_order(out)
        return out

    def _children_first(self, out=None):
        if out is None:
            out = []
        for c in self.sub_nodes:
            c._children_first(out)
        out.append(self)
        return out

    def _states_inside(self, out=None):
        out = super()._states_inside(out)
        for c in self.sub_nodes:
            c._states_inside(out)
        return out

    def _resulting_state_of_child(self, child: Node) -> Isar_State_Slot:
        for i, c in enumerate(self.sub_nodes):
            if c is child:
                if i + 1 < len(self.sub_nodes):
                    return self.sub_nodes[i + 1].state
                return self._resulting_state_of_all_children()
        raise TAT_InternalError("not my child")

    @abstractmethod
    def _resulting_state_of_all_children(self) -> Isar_State_Slot: ...

    def on_removing_child(self, child: Node,
                          mode: Literal["insert_or_delete", "move",
                                        "inheritance", "amend"]) -> None:
        """Gate: `child` is to leave this node's `sub_nodes`; `mode` says
        why the membership changes (MODULE_STRUCTURE §4.1)."""

    def on_added_child(self, child: Node,
                       mode: Literal["insert_or_delete", "move",
                                     "inheritance", "amend"]) -> None:
        """Completed: `child` entered this node's `sub_nodes`."""

    def _state_at(self, index: int) -> Isar_State_Slot:
        """The state before position `index`: the child there, or the state
        after all children when the position is the end."""
        if index < len(self.sub_nodes):
            return self.sub_nodes[index].state
        return self._resulting_state_of_all_children()

    def _beginning_status(self) -> EvaluationStatus:
        """The status of the operation that writes the first child's input.
        A class without a beginning operation has nothing ready."""
        return NOT_EVALUATED

    def _predecessor_wrote(self, index: int) -> bool:
        """Whether the predecessor operation — the one that writes the state
        at position `index` — has written it, judged with no round trip
        (MODULE_STRUCTURE §4.2 step 3).  An own stop wrote too: it copied
        its input through, so whatever follows has something to run from
        (ARCHITECTURE §3.1).  A failed beginning wrote the block's resulting
        state instead, so at position 0 only `ready` counts."""
        if index > 0:
            return _wrote(self.sub_nodes[index - 1]._last_status())
        return self._beginning_status() is READY

    # The one copy of ARCHITECTURE §3.4, seen from the parent: a node
    # arriving at a position takes the predecessor's result that already
    # sits there (`_source_before`), and a node leaving one carries it into
    # the successor's slot (`_carry_forward`).  A container whose children
    # are not chained overrides both to do nothing.

    def _source_before(self, index: int) -> Isar_State_Slot | None:
        """The slot holding the predecessor's result at position `index`, for
        a node arriving there to take — or None when nothing was written."""
        return self._state_at(index) if self._predecessor_wrote(index) else None

    async def _carry_forward(self, index: int, node: Node, ev: Evaluation) -> None:
        """The source side of removing `node` from position `index`: the
        predecessor's result, which lived under `node.state`, carried into
        the successor's slot.  When the predecessor wrote nothing, that slot
        is instead released if `node` wrote it — an own stop's copy-through
        would otherwise outlive its writer.  Nothing when neither wrote."""
        if self._predecessor_wrote(index):
            await node.state.copy_to(self._state_at(index + 1))
        elif _wrote(node._last_status()):
            ev.release(self._state_at(index + 1))

    async def _evaluate_children(self, ev: Evaluation, mode: Mode) -> EvaluationResult:
        """The children in order.  A seeking walk turns `Invalidating` on
        reaching its destination position — before the child standing
        there, or after all children when the position is the end."""
        stopped_at = None
        for i, child in enumerate(self.sub_nodes):
            if isinstance(mode, Seeking) and mode.destination == Location(self, i):
                mode = INVALIDATING
            r = await child._evaluate(ev, mode)
            mode = r.mode
            if r.stopped_at is not None:                  # at most once: the rest run blocked
                stopped_at = r.stopped_at
        if (isinstance(mode, Seeking)
                and mode.destination == Location(self, len(self.sub_nodes))):
            mode = INVALIDATING
        return EvaluationResult(stopped_at, mode)


class StdBlock(NonLeaf_Node):
    """A node with a beginning operation, children, and an ending operation
    (which by default is a copy: the class has no closing command).  Each of
    the two operations has its own status."""

    _state_before_ending: Isar_State_Slot      # after all children; the ending runs from it
    evaluation_status_beginning: EvaluationStatus
    evaluation_status_ending: EvaluationStatus

    def __init__(self, parent, state, sub_nodes, state_before_ending: Isar_State_Slot):
        super().__init__(parent, state, sub_nodes)
        self._state_before_ending = state_before_ending
        self.evaluation_status_beginning = NOT_EVALUATED
        self.evaluation_status_ending = NOT_EVALUATED

    def _resulting_state_of_all_children(self) -> Isar_State_Slot:
        return self._state_before_ending

    def _last_status(self):
        return self.evaluation_status_ending

    def _beginning_status(self):
        return self.evaluation_status_beginning

    def _operations_ready(self):
        return (self.evaluation_status_beginning is READY
                and self.evaluation_status_ending is READY)

    def _state_after_beginning(self) -> Isar_State_Slot:
        if self.sub_nodes:
            return self.sub_nodes[0].state
        return self._state_before_ending

    def _states_inside(self, out=None):
        out = super()._states_inside(out)
        out.append(self._state_before_ending)
        return out

    def _set_beginning(self, ev: Evaluation, new: EvaluationStatus) -> None:
        old = self.evaluation_status_beginning
        if old is READY and new is not READY:             # written -> unwritten; a rewrite releases nothing
            ev.release(self._state_after_beginning())
        self.evaluation_status_beginning = new
        if old is READY and new is not READY:
            _completed(self.on_invalidated, "beginning")

    def _set_ending(self, ev: Evaluation, new: EvaluationStatus) -> None:
        old = self.evaluation_status_ending
        if _wrote(old) and not _wrote(new):               # written -> unwritten; a rewrite releases nothing
            ev.release(self.resulting_state())
        self.evaluation_status_ending = new
        if old is READY and new is not READY:
            _completed(self.on_invalidated, "ending")

    async def _mark_not_evaluated(self, ev):
        if self.evaluation_status_ending is not NOT_EVALUATED:
            self._set_ending(ev, NOT_EVALUATED)

    @abstractmethod
    async def _eval_beginning_opr(self) -> bool:
        """Run the opening from `state` into `_state_after_beginning()`.
        Return whether it succeeded.  On False the children cannot run, the
        framework copies `state` into `resulting_state()` so the block's
        input stands as its result, and evaluation resumes after it
        (ARCHITECTURE §3.3)."""

    async def _eval_ending_opr(self) -> bool:
        """Run the closing from `_state_before_ending` into `resulting_state()`.
        Return whether evaluation passes through; on False the framework
        copies `_state_before_ending` into `resulting_state()`.  Default: no
        closing command, the copy is the whole operation."""
        await self._state_before_ending.copy_to(self.resulting_state())
        return True

    async def _evaluate(self, ev, mode):
        if isinstance(mode, Evaluating) and mode.blocked_by is None:
            beginning = self.evaluation_status_beginning
            began = mode.rewritten or not _wrote(beginning)   # a blocked one reruns; an own stop does not
            if began:
                ok = await self._eval_beginning_opr()
                self._set_beginning(ev, READY if ok else CannotEvaluate(None))
            if _is_own_stop(self.evaluation_status_beginning):    # the children have no context
                r = await self._evaluate_children(ev, Evaluating(self))
                if r.mode is INVALIDATING:
                    await self._mark_not_evaluated(ev)
                    return EvaluationResult(None, INVALIDATING)
                # The input stands as the result — copied again when the
                # input was rewritten; a standing copy is left alone.
                copied = mode.rewritten or self.evaluation_status_ending is not READY
                if copied:
                    await self.state.copy_to(self.resulting_state())
                    self._set_ending(ev, READY)
                return EvaluationResult(None, self._mode_after(ev, mode, None, copied))

            r = await self._evaluate_children(ev, replace(mode, rewritten=began))
            if r.mode is INVALIDATING:                    # the ending lies past the destination
                await self._mark_not_evaluated(ev)
                return EvaluationResult(r.stopped_at, INVALIDATING)
            if r.stopped_at is not None:                  # no state to run the ending from
                if not _is_own_stop(self.evaluation_status_ending):
                    self._set_ending(ev, CannotEvaluate(r.stopped_at))
                return EvaluationResult(r.stopped_at, self._mode_after(ev, mode, r.stopped_at, False))
            assert isinstance(r.mode, Evaluating)
            ended = r.mode.rewritten or not _wrote(self.evaluation_status_ending)
            if ended:
                if await self._eval_ending_opr():
                    self._set_ending(ev, READY)
                else:
                    await self._state_before_ending.copy_to(self.resulting_state())
                    self._set_ending(ev, CannotEvaluate(None))
            stop = None                                   # an ending that failed stays a stop until edited
            if self.evaluation_status_ending is not READY and not ev.ignore_error:
                stop = self
            return EvaluationResult(stop, self._mode_after(ev, mode, stop, ended))

        # Not running here: blocked, past the destination, or seeking.  A
        # blocked status never overwrites an own stop: the node keeps
        # reporting itself as the obstacle, and is not rerun
        # (ARCHITECTURE §3.3).
        if isinstance(mode, Evaluating):
            if not _is_own_stop(self.evaluation_status_beginning):
                self._set_beginning(ev, CannotEvaluate(mode.blocked_by))
        elif mode is INVALIDATING:
            self._set_beginning(ev, NOT_EVALUATED)
        r = await self._evaluate_children(ev, mode)
        if r.mode is INVALIDATING:
            await self._mark_not_evaluated(ev)
        elif isinstance(mode, Evaluating):
            if not _is_own_stop(self.evaluation_status_ending):
                self._set_ending(ev, CannotEvaluate(mode.blocked_by))
        reached = r.mode is INVALIDATING or self is ev.destination
        if reached:
            return EvaluationResult(None, INVALIDATING)
        if isinstance(mode, Evaluating):                 # blocked: nothing ran here
            mode = replace(mode, rewritten=False)
        return EvaluationResult(None, mode)


class Unchained_Node(NonLeaf_Node):
    """A container whose children are not chained — a `Session`'s trees,
    the root's `Session`s: no child's result is the next child's input, and
    the container runs no operation of its own
    (ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §6).  It mints no slot: a
    child that has a result owns the slot for it, as a `Theory` does."""

    def _resulting_state_of_child(self, child) -> Isar_State_Slot:
        raise TAT_InternalError(
            f"{type(self).__name__} chains no children: a child owns its resulting state")

    def _resulting_state_of_all_children(self) -> Isar_State_Slot:
        raise TAT_InternalError(
            f"{type(self).__name__} keeps no slot after its children")

    def _last_status(self):
        return NOT_EVALUATED                     # no operation: nothing written

    def _operations_ready(self):
        return True                              # no operation: nothing owed

    def _predecessor_wrote(self, index) -> bool:
        return False                             # no child writes another's input

    def _source_before(self, index) -> Isar_State_Slot | None:
        return None                              # no predecessor's result to take

    async def _carry_forward(self, index, node, ev):
        pass                                     # nor to carry

    async def _mark_not_evaluated(self, ev):
        pass                                     # no ending to mark


# ---------------------------------------------------------------------------
# The shared types of the node class contract (MODULE_STRUCTURE §4.1), and
# the firing of a completed hook

# The JSON object the agent submitted.  `kind` and `children` belong to the
# framework; the other fields are the node class's own.
RawAST = Mapping[str, Any]


class NodeConfig(NamedTuple):
    state: Isar_State_Slot   # the state before the node.  A name: the slot
                             # may hold nothing, and gen neither reads nor
                             # writes through it — only evaluation hooks may
                             # assume a slot holds a state
    parent: NonLeaf_Node     # never None: the forest root is not made this
                             # way.  During an edit this may be a node not
                             # yet in the forest
    replacing: Node | None   # on the amend path, the node this construct
                             # is replacing; None on every other path.  Read
                             # it for exactly two things: leave it out of any
                             # uniqueness check, and carry over recorded
                             # fields the class judges still valid.
                             # Read-only; never mutate it


class Namespace(NamedTuple):
    """A forest-wide namespace a class's names live in (PLUGIN_SYSTEM §2):
    its name, and the `BadEdit` raised when the name is taken, built as
    `duplicate(name, holder)` with `holder` the holder's id or its full path
    in the call (RENDER_BASELINES §2)."""
    name: str
    duplicate: Callable[[str, str], BadEdit]


def _completed(hook, *args) -> None:
    """Fire a completed hook: raising anything is the class's bug — in
    particular a `TAT_Error` must not escape dressed as agent-actionable
    (EXCEPTIONS.md §1)."""
    try:
        hook(*args)
    except TAT_Error as e:
        raise TAT_InternalError(
            f"completed hook {hook.__qualname__} raised") from e


@dataclass(frozen=True)
class Conversation:
    """One run of TAT (ARCHITECTURE §1, §9): what the run is given and the
    forest does not store — the connection to the Isabelle side, and the
    working directory (ARCHITECTURE §4).  A node reaches it through
    `forest().conversation`."""
    connection: Connection
    working_directory: Path


class Forest(Unchained_Node):
    """The root above every `Session` (MODULE_STRUCTURE §4.1): holds the
    lock, the store and the `Conversation`, resolves and prints ids."""

    conversation: Conversation
    lock: asyncio.Lock                         # held across every evaluation and tree change
    store: Forest_Store                        # the working directory's database (the plan's §2)

    ROOT_IDENTITY: ClassVar[int] = 0           # `next_identity` starts at 1

    def __init__(self, conversation: Conversation, store: Forest_Store,
                 kinds: Mapping[str, type[Node]]):
        """The forest the store holds, loaded whole: its trees are the root's
        `children` row, each rebuilt by `_load_subtree` with the classes of
        `kinds`; a fresh database, one without a row, is the empty forest.
        `not_evaluated` throughout, every slot fresh (ARCHITECTURE §4.1).
        A database TAT could not have written is refused (`TAT_StartupError`)."""
        super().__init__(None, Isar_State_Slot.assign(conversation.connection), [])
        self.conversation = conversation
        self.identity = self.ROOT_IDENTITY
        self.store = store
        self.lock = asyncio.Lock()
        try:
            if store.nodes():
                seen = {self.identity}
                for identity in self._child_identities(self.identity, seen):
                    self.sub_nodes.append(self._load_subtree(identity, self, kinds, seen))
        except MissingRow as e:                # a framework row, or a field a class reads
            raise TAT_StartupError(
                f"the forest database has no field `{e.field}` for node {e.node}") from e

    # --- persistence: what the framework stores of a node, and how it
    # rebuilds one (the plan's §2).  Every write below needs an open
    # transaction; the edit entries open one each.

    def _store_node(self, node: Node) -> None:
        """Rewrite one node's rows: `kind`, a nesting node's `children`,
        then what the class writes.  Also how an evaluation hook stores a
        recorded field it wrote."""
        self.store.delete_node(node.identity)
        self.store.put(node.identity, "kind", node.kind)
        if isinstance(node, NonLeaf_Node):
            self._store_children(node)
        node.to_store(self.store.rows(node.identity))

    def _store_subtree(self, node: Node) -> None:
        for n in node._tree_order():
            self._store_node(n)

    def _store_children(self, parent: NonLeaf_Node) -> None:
        """The ordered identities of `parent`'s children — the root's one
        row, the only one it has."""
        self.store.put(parent.identity, "children",
                       [c.identity for c in parent.sub_nodes])

    def _child_identities(self, identity: int, seen: set[int]) -> list[int]:
        """The `children` row of `identity`, checked before it is walked: a
        list of identities, none seen before in this load — a damaged row
        is refused, not recursed into or loaded twice."""
        children = self.store.get(identity, "children")
        if not isinstance(children, list) or not all(type(c) is int for c in children):
            raise TAT_StartupError(
                f"the forest database's `children` row of node {identity} is not a"
                " list of identities")
        for child in children:
            if child in seen:
                raise TAT_StartupError(
                    f"the forest database names node {child} as a child, but it is"
                    " already in the forest being loaded")
            seen.add(child)
        return children

    def _load_subtree(self, identity: int, parent: NonLeaf_Node,
                      kinds: Mapping[str, type[Node]], seen: set[int]) -> Node:
        kind = self.store.get(identity, "kind")
        cls = kinds.get(kind) if isinstance(kind, str) else None
        if cls is None:
            raise TAT_StartupError(
                f"the forest database holds a node of kind `{kind}`, for which no"
                " node class is loaded")
        config = NodeConfig(state=Isar_State_Slot.assign(parent.state.connection),
                            parent=parent, replacing=None)
        node = cls.from_store(config, self.store.rows(identity))
        if isinstance(node, NonLeaf_Node) and node.sub_nodes:
            raise TAT_InternalError(
                f"{cls.__name__}.from_store returned children; the framework loads them")
        node.parent = parent                   # the framework owns placement
        node.kind = kind
        node.identity = identity
        if isinstance(node, NonLeaf_Node):
            for child_identity in self._child_identities(identity, seen):
                node.sub_nodes.append(self._load_subtree(child_identity, node, kinds, seen))
        return node

    # --- ids: resolution and shortest-form printing (MCP_SPECIFICATION §2.1).
    # Ambiguity is judged across the whole forest, so both live here.

    def _all_nodes(self) -> list[Node]:
        """Every node below the root, in tree order."""
        out: list[Node] = []
        for t in self.sub_nodes:
            t._tree_order(out)
        return out

    def _chain(self, node: Node) -> list[Node]:
        """The node's ancestors below the root and itself, outermost first."""
        chain: list[Node] = []
        n: Node | None = node
        while n is not None and n is not self:
            chain.append(n)
            n = n.parent
        if n is not self:
            raise TAT_InternalError("not in this forest")
        chain.reverse()
        return chain

    def _read(self, parts: list[str]) -> list[Node]:
        """Every node the id designates: its chain's component sequence
        yields `parts` by dropping input-omissible components — never the
        node's own."""
        if not parts:
            return []
        def admits(chain: list[Node]) -> bool:
            if chain[-1].id_component() != parts[-1]:
                return False
            memo: dict[tuple[int, int], bool] = {}
            def match(ci: int, pi: int) -> bool:   # chain[ci:-1] vs parts[pi:-1]
                key = (ci, pi)
                if key not in memo:
                    if pi == len(parts) - 1:
                        memo[key] = all(c.input_omissible
                                        for c in chain[ci:-1])
                    elif ci == len(chain) - 1:
                        memo[key] = False
                    else:
                        memo[key] = (
                            (chain[ci].id_component() == parts[pi]
                             and match(ci + 1, pi + 1))
                            or (chain[ci].input_omissible
                                and match(ci + 1, pi)))
                return memo[key]
            return match(0, 0)
        return [n for n in self._all_nodes() if admits(self._chain(n))]

    def resolve(self, id: str) -> Node:
        """The node an agent-supplied id designates; `Sessions` is the forest
        itself.  No match: `NodeNotFound`, with the closest printed ids as
        guesses.  Several: the exact match wins — the one whose chain
        equals the id component for component, nothing dropped; sibling
        names are unique, so there is at most one, and a full id therefore
        always designates its node (MCP_SPECIFICATION §2.1).  Otherwise:
        `AmbiguousId`, the candidates in tree order."""
        if id == "Sessions":
            return self
        parts = id.split(".")
        matches = self._read(parts)
        if len(matches) > 1:
            for n in matches:
                if [c.id_component() for c in self._chain(n)] == parts:
                    return n
        if len(matches) == 1:
            return matches[0]
        if not matches:
            # Guess by the last component — printing an id for every node
            # would be quadratic in the forest.
            nodes = self._all_nodes()
            close = set(difflib.get_close_matches(
                parts[-1], sorted({n.id_component() for n in nodes})))
            near = [self.id_of(n)
                    for n in [n for n in nodes if n.id_component() in close][:3]]
            raise NodeNotFound(id, near)
        raise AmbiguousId(id, [self.id_of(m) for m in matches])

    def id_of(self, node: Node) -> str:
        """The shortest form: starting from the full id, repeatedly delete —
        among the output-omissible components whose deletion still resolves
        to exactly this node — the one with the lowest drop priority, the
        outermost on ties, until none can go."""
        if node is self:
            return "Sessions"
        chain = self._chain(node)
        kept = list(range(len(chain)))
        while True:
            best = None
            for pos in kept:
                c = chain[pos]
                if not c.output_omissible:
                    continue
                candidate = [chain[p].id_component() for p in kept if p != pos]
                if self._read(candidate) == [node]:
                    key = (c.drop_priority, pos)
                    if best is None or key < best[0]:
                        best = (key, pos)
            if best is None:
                return ".".join(chain[p].id_component() for p in kept)
            kept.remove(best[1])

    async def _run(self, ev: Evaluation, mode: Mode) -> EvaluationResult:
        """One walk under the lock, already held, then one round trip
        releasing every state it invalidated."""
        r = await self._evaluate(ev, mode)
        await ev.flush(self.state.connection)
        return r

    async def _invalidate_from(self, position: Location) -> EvaluationResult:
        """An edit's unconditional invalidation (MCP_SPECIFICATION §3.2):
        everything from `position` on, the node standing there whole."""
        return await self._run(Evaluation(None, False), Seeking(position))

    async def _evaluate(self, ev, mode):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# The framework's own node classes (node_classes/SESSION_AND_THEORY.md): the
# two that carry the forest's structure — a `Session` groups trees, a
# `Theory` roots one — which is why they live here and not in `builtins.py`
# (the plan's §6).  `plugin.load` registers them before any package
# (PLUGIN_SYSTEM §1).

def _parent_id(config: NodeConfig) -> str:
    """The parent as the agent sees it, for a `Bad<Class>NodeParent`.  A
    parent still under construction in the same call prints its full id."""
    return config.parent.forest().id_of(config.parent)


class Session_Option(TypedDict):
    name: str
    value: str


class Session_RawAST(TypedDict):
    kind: Literal["session"]
    name: str
    parent_session: str
    options: NotRequired[list[Session_Option]]
    description: NotRequired[str]


class Session(Unchained_Node):
    """One Isabelle session under construction (SESSION_AND_THEORY §1): the
    ROOT entry's fields, and the trees under it.  It runs no Isabelle
    commands and is not on the evaluation path — the forest works on the
    trees directly, so a walk reaching a `Session` is a framework bug (the
    plan's §6)."""

    construct_schema = {
        "type": "object",
        "description": "Isabelle session",
        "properties": {
            "kind": {"const": "session"},
            "name": {"type": "string"},
            "parent_session": {"type": "string"},
            "options": {"type": "array", "items": {"$ref": "#/$defs/Session_Option"},
                        "description": "Session options, as in a ROOT entry"},
            "description": {"type": "string"},
            "children": {"type": "array", "items": {"$ref": "#/$defs/Theory"},
                         "description": "The session's theories"},
        },
        "required": ["kind", "name", "parent_session"],
        "additionalProperties": False,
        "$defs": {
            "Session_Option": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "value": {"type": "string"}},
                "required": ["name", "value"],
                "additionalProperties": False,
            },
        },
    }
    argument_schema = Session_RawAST
    output_omissible = input_omissible = True
    drop_priority = 1                   # after `Section`, before `Theory` (MCP_SPECIFICATION §2.1)

    name: str                           # the Isabelle session name
    parent_session: str
    options: list[Session_Option]
    description: str

    def __init__(self, parent, state, name: str, parent_session: str,
                 options: list[Session_Option], description: str):
        super().__init__(parent, state, [])
        self.name = name
        self.parent_session = parent_session
        self.options = options
        self.description = description

    @classmethod
    async def gen(cls, config, raw: Session_RawAST):
        if not isinstance(config.parent, Forest):
            raise BadSessionNodeParent(raw["kind"], _parent_id(config))
        if not raw["parent_session"]:
            raise InvalidField("parent_session", "must not be empty")
        options = raw.get("options", [])
        seen: set[str] = set()
        for i, option in enumerate(options):
            for field in ("name", "value"):
                if not option[field]:
                    raise InvalidField(f"options[{i}].{field}", "must not be empty")
            if option["name"] in seen:
                raise InvalidField(f"options[{i}].name",
                                   f"sets the option `{option['name']}` a second time")
            seen.add(option["name"])
        return cls(config.parent, config.state, raw["name"], raw["parent_session"],
                   list(options), raw.get("description", ""))

    def on_moving(self, new_location):
        if not isinstance(new_location.parent, Forest):
            raise BadSessionNodeParent(self.kind, self.forest().id_of(new_location.parent))

    def to_store(self, rows):
        rows.put("name", self.name)
        rows.put("parent_session", self.parent_session)
        rows.put("options", self.options)
        rows.put("description", self.description)

    @classmethod
    def from_store(cls, config, rows):
        return cls(config.parent, config.state, rows.get("name"), rows.get("parent_session"),
                   rows.get("options"), rows.get("description"))

    async def _evaluate(self, ev, mode):
        raise TAT_InternalError(
            "a walk reached a Session: evaluation is transparent to the Session layer")


class Theory_RawAST(TypedDict):
    kind: Literal["theory"]
    name: str
    imports: list[str]


# An Isabelle identifier: no hyphen, no dot (SESSION_AND_THEORY §2).  A
# trailing underscore, legal here, is the framework's name grammar to
# refuse, with the rendering that says so.
_ISABELLE_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_']*")


class Theory(StdBlock):
    """The root of every tree (SESSION_AND_THEORY §2): the header, the
    imports and the `end`.  Its beginning runs the header through the
    framework's `begin_theory`, from a fresh toplevel state — its input
    slot `state` is written by nobody; its ending runs `end` into a
    resulting slot of its own, which nothing reads, and puts the theory
    value into the theory table (the plan's §6).  The ML half is
    `TAT_Common_Nodes.ML`'s `Theory` section."""

    construct_schema = {
        "type": "object",
        "properties": {
            "kind": {"const": "theory"},
            "name": {"type": "string", "description": "The theory's short name"},
            "imports": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                        "description": "Theories to import"},
            "children": {"type": "array", "items": {"$ref": "#/$defs/Construct"},
                         "description": "The theory's declarations"},
        },
        "required": ["kind", "name", "imports"],
        "additionalProperties": False,
    }
    argument_schema = Theory_RawAST
    output_omissible = input_omissible = True
    drop_priority = 2
    namespace = Namespace("theory short names", DuplicateTheoryShortName)

    name: str                           # the short name; the qualified name is computed
    imports: list[str]
    _state_after_ending: Isar_State_Slot    # the resulting slot: owned, since no successor's
                                            # input is (`Unchained_Node`); nothing reads it
    # Recorded, and held only for the life of the conversation, never stored
    # (SESSION_AND_THEORY §2): what the last run of each operation reported,
    # empty when it passed.
    beginning_errors: list[str]
    ending_errors: list[str]

    def __init__(self, parent, state, name: str, imports: list[str],
                 state_before_ending: Isar_State_Slot, state_after_ending: Isar_State_Slot):
        super().__init__(parent, state, [], state_before_ending)
        self.name = name
        self.imports = imports
        self._state_after_ending = state_after_ending
        self.beginning_errors = []
        self.ending_errors = []

    @classmethod
    async def gen(cls, config, raw: Theory_RawAST):
        if not isinstance(config.parent, Session):
            raise BadTheoryNodeParent(raw["kind"], _parent_id(config))
        name = raw["name"]
        if not _ISABELLE_IDENTIFIER.fullmatch(name):
            raise InvalidName(name, theory_name=True)
        # The base-heap half of the short-name check; the forest half is the
        # framework's, through `namespace` (the plan's §3).
        connection = config.parent.forest().conversation.connection
        holder = await isabelle_driver.check_new_theory_short_name(connection, name)
        if holder is not None:
            raise DuplicateTheoryShortName(name, holder)
        if not raw["imports"]:
            raise InvalidField("imports", "must not be empty")
        for i, item in enumerate(raw["imports"]):
            if not item:
                raise InvalidField(f"imports[{i}]", "must not be empty")
        return cls(config.parent, config.state, name, list(raw["imports"]),
                   Isar_State_Slot.assign(connection), Isar_State_Slot.assign(connection))

    def on_moving(self, new_location):
        if not isinstance(new_location.parent, Session):
            raise BadTheoryNodeParent(self.kind, self.forest().id_of(new_location.parent))

    def to_store(self, rows):
        rows.put("name", self.name)
        rows.put("imports", self.imports)

    @classmethod
    def from_store(cls, config, rows):
        connection = config.parent.forest().conversation.connection
        return cls(config.parent, config.state, rows.get("name"), rows.get("imports"),
                   Isar_State_Slot.assign(connection), Isar_State_Slot.assign(connection))

    def resulting_state(self):
        return self._state_after_ending

    def _states_inside(self, out=None):
        out = super()._states_inside(out)
        out.append(self._state_after_ending)
        return out

    def session(self) -> Session:
        assert isinstance(self.parent, Session)     # gen and on_moving admit no other parent
        return self.parent

    def header(self) -> str:
        """The `theory … begin` span, as the tree's file will open."""
        return f"theory {self.name}\n  imports {' '.join(self.imports)}\nbegin"

    # The two callbacks are `TAT_Common_Nodes.ML`'s; each answers the
    # operation's errors, empty when it passed (ARCHITECTURE §6.2).  The
    # previous run's messages go before the call, so a failed call leaves
    # none standing.

    async def _eval_beginning_opr(self):
        session = self.session()
        conversation = self.forest().conversation
        self.beginning_errors = []
        self.beginning_errors = await conversation.connection.callback(
            "TAT.Theory.begin",
            (self._state_after_beginning().to_msgpack(),
             (session.name,
              str(conversation.working_directory / session.name),   # the plan's §1
              self.header())))
        return not self.beginning_errors

    async def _eval_ending_opr(self):
        self.ending_errors = []
        self.ending_errors = await self.forest().conversation.connection.callback(
            "TAT.Theory.end",
            (self._state_before_ending.to_msgpack(), self._state_after_ending.to_msgpack()))
        return not self.ending_errors


FRAMEWORK_NODE_CLASSES: list[type[Node]] = [Session, Theory]
