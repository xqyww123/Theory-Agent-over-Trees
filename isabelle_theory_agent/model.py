"""The forest: nodes, state slots, evaluation and invalidation
(ARCHITECTURE §3, MODULE_STRUCTURE §4.1).

Every method that touches Isabelle is async, since `Connection.callback` is.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar, Self

from Isabelle_RPC_Host import Connection

from . import isabelle_driver


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

    # Neither the connection nor the name survives persistence
    # (ARCHITECTURE §4.1): the loader reassigns every slot of a loaded forest.
    def __getstate__(self):
        return {}

    def __setstate__(self, _):
        self.__dict__.update(connection=None, name=None)   # unassigned until the loader reassigns

    def __repr__(self) -> str:
        return f"Isar_State_Slot({self.name})"


# ---------------------------------------------------------------------------
# Evaluation status (ARCHITECTURE §3.2, §3.3)

class _Singleton:
    """One instance per class, also across pickling, so `is` is always right."""

    def __new__(cls) -> Self:
        inst = cls.__dict__.get("_instance")
        if inst is None:
            inst = super().__new__(cls)
            cls._instance = inst
        return inst

    def __reduce__(self):
        return (type(self), ())

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


# ---------------------------------------------------------------------------
# One evaluation (ARCHITECTURE §3.5)

class Evaluation:
    """One `evaluate_to` call: its two constants, and the states it releases,
    deleted in one round trip when it ends."""

    def __init__(self, destination: Node, ignore_error: bool):
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
    it."""
    blocked_by: Node | None = None

class Seeking(_Singleton):
    """Before the destination without evaluating: touch nothing."""

class Invalidating(_Singleton):
    """Past the destination: mark `NotEvaluated`."""

SEEKING = Seeking()
INVALIDATING = Invalidating()

Mode = Evaluating | Seeking | Invalidating


@dataclass(frozen=True)
class EvaluationResult:
    stopped_at: Node | None      # the obstacle that ended evaluation, if one did
    mode: Mode                   # the mode the node after this one runs under


# ---------------------------------------------------------------------------
# Nodes

class Node(ABC):
    """The Python half of a node class (ARCHITECTURE §6).

    `state` is the state before the node.  The state after it is not stored:
    it is the next sibling's `state`, or the parent's state after all
    children (`resulting_state`).
    """

    parent: NonLeaf_Node | None
    state: Isar_State_Slot

    def __init__(self, parent: NonLeaf_Node | None, state: Isar_State_Slot):
        self.parent = parent
        self.state = state

    def resulting_state(self) -> Isar_State_Slot:
        if self.parent is None:
            raise ValueError("a node without a parent has no resulting state")
        return self.parent._resulting_state_of_child(self)

    def forest(self) -> Forest:
        n = self
        while n.parent is not None:
            n = n.parent
        assert isinstance(n, Forest)
        return n

    @abstractmethod
    def is_finished(self) -> bool:
        """Whether the node still owes anything (ARCHITECTURE §3.2).  The one
        question asked of a node from outside; everything else it renders
        itself."""

    def invalidate(self) -> None:
        """Hook: the node's context is no longer current (ARCHITECTURE §3.6).
        A class with work in flight overrides it."""

    @abstractmethod
    def _states_inside(self) -> list[Isar_State_Slot]:
        """Every state owned by this subtree: `state` and, under a nesting
        node, its children's and the one after them.  The resulting state is
        not among them — it is the successor's."""

    @abstractmethod
    async def _evaluate(self, ev: Evaluation, mode: Mode) -> EvaluationResult:
        """One recursion for evaluation and invalidation (ARCHITECTURE §3.5),
        visiting every node of the subtree under `mode`.  A nesting node is
        reached at its ending, so its children come before it."""

    @abstractmethod
    async def _mark_not_evaluated(self, ev: Evaluation) -> None:
        """Mark the node — for a nesting node, its ending — `NotEvaluated`.
        What an edit does before evaluating."""

    def _mode_after(self, ev: Evaluation, mode: Evaluating, stop: Node | None) -> Mode:
        """The one place the mode changes: the destination turns it into
        `Invalidating`; otherwise a stop blocks what follows."""
        if self is ev.destination:
            return INVALIDATING
        if stop is not None:
            return Evaluating(stop)
        return mode

    async def evaluate_to(self, ignore_error: bool, evaluate: bool = True) -> EvaluationResult:
        """The one entry to `_evaluate`, holding the forest's lock.  With
        `evaluate`: run up to and including this node.  Without: only
        invalidate from this node on.  The walk visits every node, so the
        result's `mode` is always `Invalidating`; what happened to this node
        it reports itself."""
        async with self.forest().lock:
            return await self.forest()._run(Evaluation(self, ignore_error), evaluate)


class Leaf(Node):

    _status: EvaluationStatus

    def __init__(self, parent, state):
        super().__init__(parent, state)
        self._status = NOT_EVALUATED

    def _states_inside(self):
        return [self.state]

    def _set_status(self, ev: Evaluation, new: EvaluationStatus) -> None:
        old = self._status
        if old is READY or _is_own_stop(old):     # both wrote the resulting state
            ev.release(self.resulting_state())
        self._status = new
        if old is READY and new is not READY:
            self.invalidate()

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
            stop = None
            if mode.blocked_by is not None:
                self._set_status(ev, CannotEvaluate(mode.blocked_by))
            elif self._status is not READY:
                if not _is_own_stop(self._status):        # an own stop is not rerun
                    if await self._eval_opr():
                        self._set_status(ev, READY)
                    else:
                        await self.state.copy_to(self.resulting_state())
                        self._set_status(ev, CannotEvaluate(None))
                if self._status is not READY and not ev.ignore_error:
                    stop = self
            return EvaluationResult(stop, self._mode_after(ev, mode, stop))
        if mode is SEEKING and self is not ev.destination:
            return EvaluationResult(None, mode)
        await self._mark_not_evaluated(ev)                 # past the destination, or the sought one
        return EvaluationResult(None, INVALIDATING)

    def __getstate__(self):
        d = dict(self.__dict__)
        d["_status"] = NOT_EVALUATED                      # a loaded forest is not evaluated
        return d


class NonLeaf_Node(Node):

    sub_nodes: list[Node]

    def __init__(self, parent, state, sub_nodes: list[Node]):
        super().__init__(parent, state)
        self.sub_nodes = sub_nodes

    def _resulting_state_of_child(self, child: Node) -> Isar_State_Slot:
        for i, c in enumerate(self.sub_nodes):
            if c is child:
                if i + 1 < len(self.sub_nodes):
                    return self.sub_nodes[i + 1].state
                return self._resulting_state_of_all_children()
        raise ValueError("not my child")

    @abstractmethod
    def _resulting_state_of_all_children(self) -> Isar_State_Slot: ...

    def _state_at(self, index: int) -> Isar_State_Slot:
        """The state before position `index`: the child there, or the state
        after all children when the position is the end."""
        if index < len(self.sub_nodes):
            return self.sub_nodes[index].state
        return self._resulting_state_of_all_children()

    async def _insert_child(self, index: int, node: Node, ignore_error: bool,
                            evaluate: bool) -> EvaluationResult:
        """Insert `node` before position `index` and evaluate it, or only
        invalidate from it.  The predecessor's result, which lived under the
        state formerly at that position, is copied under the new node's
        `state`, so the predecessor stays as it is."""
        async with self.forest().lock:
            await self._state_at(index).copy_to(node.state)
            node.parent = self
            self.sub_nodes.insert(index, node)
            return await self.forest()._run(Evaluation(node, ignore_error), evaluate)

    async def _delete_child(self, node: Node) -> None:
        """Remove `node` with its subtree and invalidate from its successor
        on.  The predecessor's result, which lived under `node.state`, is
        copied under the state now at that position."""
        async with self.forest().lock:
            index = next(i for i, c in enumerate(self.sub_nodes) if c is node)
            await node.state.copy_to(self._state_at(index + 1))
            await isabelle_driver.state_delete(node.state.connection,
                                               [s.name for s in node._states_inside()])
            del self.sub_nodes[index]
            node.parent = None
            successor = self.sub_nodes[index] if index < len(self.sub_nodes) else self
            await self.forest()._run(Evaluation(successor, False), evaluate=False)

    async def _evaluate_children(self, ev: Evaluation, mode: Mode) -> EvaluationResult:
        stopped_at = None
        for child in self.sub_nodes:
            r = await child._evaluate(ev, mode)
            mode = r.mode
            if r.stopped_at is not None:                  # at most once: the rest run blocked
                stopped_at = r.stopped_at
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

    def _state_after_beginning(self) -> Isar_State_Slot:
        if self.sub_nodes:
            return self.sub_nodes[0].state
        return self._state_before_ending

    def _states_inside(self):
        inside = [self.state]
        for c in self.sub_nodes:
            inside += c._states_inside()
        inside.append(self._state_before_ending)
        return inside

    def _set_beginning(self, ev: Evaluation, new: EvaluationStatus) -> None:
        old = self.evaluation_status_beginning
        if old is READY:
            ev.release(self._state_after_beginning())
        self.evaluation_status_beginning = new
        if old is READY and new is not READY:
            self.invalidate()

    def _set_ending(self, ev: Evaluation, new: EvaluationStatus) -> None:
        old = self.evaluation_status_ending
        if old is READY or _is_own_stop(old):             # both wrote the resulting state
            ev.release(self.resulting_state())
        self.evaluation_status_ending = new

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
            if self.evaluation_status_beginning is NOT_EVALUATED:
                ok = await self._eval_beginning_opr()
                self._set_beginning(ev, READY if ok else CannotEvaluate(None))
            if _is_own_stop(self.evaluation_status_beginning):    # the children have no context
                r = await self._evaluate_children(ev, Evaluating(self))
                if r.mode is INVALIDATING:
                    await self._mark_not_evaluated(ev)
                    return EvaluationResult(None, INVALIDATING)
                await self.state.copy_to(self.resulting_state())   # the input stands as the result
                self._set_ending(ev, READY)
                return EvaluationResult(None, self._mode_after(ev, mode, None))

            r = await self._evaluate_children(ev, mode)
            if r.mode is INVALIDATING:                    # the ending lies past the destination
                await self._mark_not_evaluated(ev)
                return EvaluationResult(r.stopped_at, INVALIDATING)
            if r.stopped_at is not None:                  # no state to run the ending from
                self._set_ending(ev, CannotEvaluate(r.stopped_at))
                return EvaluationResult(r.stopped_at, self._mode_after(ev, mode, r.stopped_at))
            ending = self.evaluation_status_ending
            if ending is not READY and not _is_own_stop(ending):
                if await self._eval_ending_opr():
                    self._set_ending(ev, READY)
                else:
                    await self._state_before_ending.copy_to(self.resulting_state())
                    self._set_ending(ev, CannotEvaluate(None))
            stop = None                                   # an ending that failed stays a stop until edited
            if self.evaluation_status_ending is not READY and not ev.ignore_error:
                stop = self
            return EvaluationResult(stop, self._mode_after(ev, mode, stop))

        # Not running here: blocked, past the destination, or seeking.
        if isinstance(mode, Evaluating):
            self._set_beginning(ev, CannotEvaluate(mode.blocked_by))
        elif mode is INVALIDATING:
            self._set_beginning(ev, NOT_EVALUATED)
        r = await self._evaluate_children(ev, mode)
        if r.mode is INVALIDATING or (mode is SEEKING and self is ev.destination):
            await self._mark_not_evaluated(ev)
        elif isinstance(mode, Evaluating):
            self._set_ending(ev, CannotEvaluate(mode.blocked_by))
        reached = r.mode is INVALIDATING or self is ev.destination
        return EvaluationResult(None, INVALIDATING if reached else mode)

    def __getstate__(self):
        d = dict(self.__dict__)
        d["evaluation_status_beginning"] = NOT_EVALUATED
        d["evaluation_status_ending"] = NOT_EVALUATED
        return d


class Forest(NonLeaf_Node):
    """The root above every tree.  Trees are not chained: a tree's result is
    not the next tree's input.  Undecided with `Theory` (OPEN_QUESTIONS §1)."""

    lock: asyncio.Lock                         # held across every evaluation and tree change

    def __init__(self, state, sub_nodes):
        super().__init__(None, state, sub_nodes)
        self.lock = asyncio.Lock()

    def is_finished(self) -> bool:
        return all(t.is_finished() for t in self.sub_nodes)

    def _resulting_state_of_all_children(self) -> Isar_State_Slot:
        raise NotImplementedError

    def _states_inside(self):
        raise NotImplementedError

    async def _mark_not_evaluated(self, ev):
        pass                                    # no ending

    async def _run(self, ev: Evaluation, evaluate: bool) -> EvaluationResult:
        """One evaluation under the lock, already held: the walk, then one
        round trip releasing every state it invalidated."""
        r = await self._evaluate(ev, Evaluating() if evaluate else SEEKING)
        await ev.flush(ev.destination.state.connection)
        return r

    async def _evaluate(self, ev, mode):
        raise NotImplementedError
