"""The forest: nodes, state slots, evaluation and invalidation
(ARCHITECTURE §3, MODULE_STRUCTURE §4.1).

Every method that touches Isabelle is async, since `Connection.callback` is.
"""

from __future__ import annotations

import asyncio
import difflib
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, NamedTuple, Self

from Isabelle_RPC_Host import Connection

from . import isabelle_driver
from .exceptions import (
    AmbiguousId, BadEdit, ChildrenNotInheritable, DuplicateName, InvalidField,
    InvalidName, MalformedRawAST, MissingField, MoveIntoOwnSubtree,
    NodeNotFound, TAT_Error, TAT_InternalError, UnexpectedChildren,
    UnknownKind)


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

_NAME_GRAMMAR = re.compile(r"[A-Za-z][A-Za-z0-9_'-]*")


def is_valid_name(name: str) -> bool:
    """The name grammar of MCP_SPECIFICATION §2: a letter followed by
    letters, digits, underscores, primes and interior hyphens — a hyphen or
    underscore may not end a name, and a hyphen cannot begin one, since a
    name starts with a letter."""
    return bool(_NAME_GRAMMAR.fullmatch(name)) and not name.endswith(("-", "_"))


@dataclass(frozen=True)
class Location:
    """A resolved place in the forest (ARCHITECTURE §1): the parent and the
    index within its `sub_nodes`."""
    parent: NonLeaf_Node
    index: int


class Node(ABC):
    """The Python half of a node class (ARCHITECTURE §6).

    `state` is the state before the node.  The state after it is not stored:
    it is the next sibling's `state`, or the parent's state after all
    children (`resulting_state`).
    """

    parent: NonLeaf_Node | None
    state: Isar_State_Slot
    name: str            # the node's one id component (MCP_SPECIFICATION §2)
    identity: int        # opaque; survives renaming and moving

    # The three id properties a node class declares (MCP_SPECIFICATION §2.1).
    # Among droppable components the lowest `drop_priority` goes first;
    # it matters only when `output_omissible`.
    output_omissible: ClassVar[bool] = False
    input_omissible: ClassVar[bool] = False
    drop_priority: ClassVar[int] = 0

    # The class's declared argument schema (MODULE_STRUCTURE §4.1): it
    # becomes the tool schema, and the framework checks a submitted
    # description against it before `gen` is consulted.
    argument_schema: ClassVar[Mapping[str, Argument]] = {}

    @classmethod
    async def gen(cls, config: NodeConfig, raw: RawAST) -> Self:
        """Semantic construction from the agent's description
        (MODULE_STRUCTURE §4.1): judge the fields' meaning, refuse a parent
        the class cannot live under, and build the node from `config`.  May
        read over the wire through the framework's query callbacks; must not
        write.  Raises `TAT_Error`s bare — the framework prefixes the
        `raw_ast_path` (EXCEPTIONS.md §5)."""
        raise TAT_InternalError(f"{cls.__name__} has no gen")

    _identity_counter: ClassVar[int] = 0

    def __init__(self, parent: NonLeaf_Node | None, state: Isar_State_Slot):
        self.parent = parent
        self.state = state
        Node._identity_counter += 1
        self.identity = Node._identity_counter

    def __setstate__(self, d):
        self.__dict__.update(d)
        # A loaded node keeps its identity; fresh ones must not reuse it.
        Node._identity_counter = max(Node._identity_counter, self.identity)

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

    @abstractmethod
    def is_finished(self) -> bool:
        """Whether the node still owes anything (ARCHITECTURE §3.2).  The one
        question asked of a node from outside; everything else it renders
        itself."""

    # --- Event hooks (MODULE_STRUCTURE §4.1), empty by default, driven by
    # the framework; two more, on_removing_child and on_added_child, live on
    # NonLeaf_Node.  The tense is the contract: a progressive hook is a gate
    # — it fires before the commit, is free of side effects, and `BadEdit`
    # is its only veto; a completed hook is for effect, and raising there is
    # the class's bug (EXCEPTIONS.md §1).

    def on_invalidated(self) -> None:
        """Completed: the node's status truly left `ready`
        (ARCHITECTURE §3.6).  A class with work in flight overrides it."""

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

    @abstractmethod
    def _invalidate_subtree(self, ev: Evaluation) -> None:
        """Every status of the subtree back to `NotEvaluated`, releasing
        what the old statuses had written.  What `_move_child` does to the
        moved subtree: its slots travel, their stale values must not
        (ARCHITECTURE §3.4)."""

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
        """The `evaluate_to` tool's entry: takes the forest's lock itself —
        an edit, whose tool entry already holds it, drives the walk through
        `Forest._run` instead (MODULE_STRUCTURE §4.1).  With
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

    def _last_status(self):
        return self._status

    def _invalidate_subtree(self, ev):
        self._set_status(ev, NOT_EVALUATED)

    def _set_status(self, ev: Evaluation, new: EvaluationStatus) -> None:
        old = self._status
        if old is READY or _is_own_stop(old):     # both wrote the resulting state
            ev.release(self.resulting_state())
        self._status = new
        if old is READY and new is not READY:
            _completed(self.on_invalidated)

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
        (MODULE_STRUCTURE §4.1 step 3).  An own stop wrote too: it copied
        its input through, so whatever follows has something to run from
        (ARCHITECTURE §3.1).  A failed beginning wrote the block's resulting
        state instead, so at position 0 only `ready` counts."""
        if index > 0:
            last = self.sub_nodes[index - 1]._last_status()
            return last is READY or _is_own_stop(last)
        return self._beginning_status() is READY

    def _invalidate_subtree(self, ev):
        for c in self.sub_nodes:
            c._invalidate_subtree(ev)

    # --- The four edit entries (MODULE_STRUCTURE §4.1).  The tool entry
    # holds the forest's lock across each; nothing before a commit has side
    # effects on the forest, so an aborted call needs no undoing.  Each ends
    # with the unconditional invalidation of MCP_SPECIFICATION §3.2; whether
    # to also evaluate is the caller's, from the call's `evaluate` flag.

    async def _insert_children(self, index: int, raws: list[RawAST],
                               kinds: Mapping[str, type[Node]]) -> list[Node]:
        """`append`/`insert_before`: construct the batch detached — `gen` is
        insertion's gate, there is no other — commit it before position
        `index`, fire the completed events, invalidate.  Returns the batch;
        its last element is the natural destination (MCP_SPECIFICATION
        §3.2)."""
        forest = self.forest()
        taken: dict[str, Node | str] = {c.name: c for c in self.sub_nodes}
        nodes = await _construct_siblings(self, raws, kinds, "nodes", taken,
                                          forest)
        # Commit: pointer surgery plus the one copy of ARCHITECTURE §3.4
        # into the first new node's slot — only when the predecessor
        # operation wrote it, judged with no round trip; every other new
        # slot stays empty, as befits `not_evaluated` nodes.  The value
        # moves with the position: the slot it came from, now written by the
        # last new node, is released.
        ev = Evaluation(nodes[0], False)
        if self._predecessor_wrote(index):
            source = self._state_at(index)
            await source.copy_to(nodes[0].state)
            ev.release(source)
        for node in nodes:
            node.parent = self
        self.sub_nodes[index:index] = nodes
        for root in nodes:                    # tree order over what entered
            for n in _tree_order(root):
                assert n.parent is not None
                _completed(n.parent.on_added_child, n, "insert_or_delete")
                _completed(n.on_inserted)
        await forest._run(ev, evaluate=False)
        return nodes

    async def _amend_children(self, old: Node, raws: list[RawAST],
                              kinds: Mapping[str, type[Node]]) -> list[Node]:
        """`amend`: `nodes[0]` is built with `replacing` set and takes
        `old`'s position, state slot, identity number and children;
        `nodes[1:]` follow it."""
        forest = self.forest()
        taken: dict[str, Node | str] = {c.name: c
                                        for c in self.sub_nodes if c is not old}
        nodes = await _construct_siblings(self, raws, kinds, "nodes", taken,
                                          forest, replacing_first=old)
        replacement = nodes[0]
        inherited = list(old.sub_nodes) if isinstance(old, NonLeaf_Node) else []
        # Gates.
        _gate(old.on_deleting, "amend")
        _gate(self.on_removing_child, old, "amend")
        for child in inherited:
            assert isinstance(old, NonLeaf_Node)
            _gate(old.on_removing_child, child, "inheritance")
            _gate(child.on_inheriting, replacement)
        # Commit.  Released, in one round trip with the walk's: `old`'s
        # slots not travelling to the replacement or the inherited children,
        # and the values `old`'s own operations wrote into travelling
        # slots — its result in the successor's input, a beginning's output
        # in the first child's input — all stale under the replacement.
        first = inherited[0] if inherited else replacement
        ev = Evaluation(first, False)
        travelling = {old.state.name} | {
            s.name for c in inherited for s in c._states_inside()}
        for s in old._states_inside():
            if s.name not in travelling:
                ev.release(s)
        last = old._last_status()
        if last is READY or _is_own_stop(last):
            ev.release(old.resulting_state())
        if (isinstance(old, StdBlock)
                and old.evaluation_status_beginning is READY):
            ev.release(old._state_after_beginning())
        index = old.index_of()
        replacement.state = old.state
        replacement.identity = old.identity
        if inherited:
            assert isinstance(replacement, NonLeaf_Node)
            replacement.sub_nodes[:] = inherited
            for child in inherited:
                child.parent = replacement
        old.parent = None
        replacement.parent = self
        self.sub_nodes[index] = replacement
        for node in nodes[1:]:
            node.parent = self
        self.sub_nodes[index + 1:index + 1] = nodes[1:]
        # Completed events (MODULE_STRUCTURE §4.1's order).
        _completed(old.on_deleted, "amend")
        for child in inherited:
            assert isinstance(replacement, NonLeaf_Node)
            _completed(child.on_inherited, old)
            _completed(replacement.on_added_child, child, "inheritance")
        _completed(self.on_added_child, replacement, "amend")
        _completed(replacement.on_inserted)
        for root in nodes[1:]:
            for n in _tree_order(root):
                assert n.parent is not None
                _completed(n.parent.on_added_child, n, "insert_or_delete")
                _completed(n.on_inserted)
        # A nesting replacement invalidates from its first child: the
        # children precede its own commands in the walk (MCP §3.2).
        await forest._run(ev, evaluate=False)
        return nodes

    async def _delete_child(self, node: Node) -> None:
        """`delete`: remove `node` with its subtree and invalidate from its
        successor on.  The predecessor's result, which lived under
        `node.state`, is copied under the state now at that position."""
        for n in _children_first(node):
            _gate(n.on_deleting, "delete")
        _gate(self.on_removing_child, node, "insert_or_delete")
        index = node.index_of()
        # When the predecessor wrote nothing, `node` never ran and the
        # successor's slot is already empty — and an unchained parent (the
        # forest) has no slot to copy into.
        if self._predecessor_wrote(index):
            await node.state.copy_to(self._state_at(index + 1))
        await isabelle_driver.state_delete(node.state.connection,
                                           [s.name for s in node._states_inside()])
        del self.sub_nodes[index]
        node.parent = None
        for n in _children_first(node):
            _completed(n.on_deleted, "delete")
        successor = self.sub_nodes[index] if index < len(self.sub_nodes) else self
        await self.forest()._run(Evaluation(successor, False), evaluate=False)

    async def _move_child(self, node: Node, new_parent: NonLeaf_Node,
                          new_index: int) -> None:
        """`move`, `self` the parent it leaves: re-home `node` with its
        subtree — a copy on the source side and one on the destination side,
        and no delete: the subtree's slots travel with their nodes
        (ARCHITECTURE §3.4).  `new_index` is the position in
        `new_parent.sub_nodes` after the removal."""
        forest = self.forest()
        p: Node | None = new_parent
        while p is not None:
            if p is node:
                raise MoveIntoOwnSubtree(forest.id_of(node),
                                         forest.id_of(new_parent))
            p = p.parent
        for c in new_parent.sub_nodes:
            if c is not node and c.name == node.name:
                raise DuplicateName(node.name, forest.id_of(c))
        limit = len(new_parent.sub_nodes) - (1 if new_parent is self else 0)
        if not 0 <= new_index <= limit:
            raise TAT_InternalError(
                f"move destination index {new_index} out of range")
        old_index = node.index_of()
        old_location = Location(self, old_index)
        _gate(node.on_moving, Location(new_parent, new_index))
        _gate(self.on_removing_child, node, "move")
        # Commit.  The source-side copy carries the predecessor's result
        # forward; the destination-side copy gives `node` its new input, and
        # the value moves with the position — the slot it came from is
        # released.  With nothing written on a side, that side's slots are
        # already empty; the stale old input alone must go.
        if self._predecessor_wrote(old_index):
            await node.state.copy_to(self._state_at(old_index + 1))
        del self.sub_nodes[old_index]
        successor = (self.sub_nodes[old_index]
                     if old_index < len(self.sub_nodes) else self)
        ev = Evaluation(successor, False)
        if new_parent._predecessor_wrote(new_index):
            source = new_parent._state_at(new_index)
            await source.copy_to(node.state)
            ev.release(source)
        else:
            await node.state.delete()
        node.parent = new_parent
        new_parent.sub_nodes.insert(new_index, node)
        _completed(new_parent.on_added_child, node, "move")
        _completed(node.on_moved, old_location)
        # The moved subtree's context changed whole: statuses back to
        # `NotEvaluated`, stale values released.  The reset runs after the
        # re-homing, so each release resolves `resulting_state` in the new
        # parent; its releases flush with the source-tail walk's.
        node._invalidate_subtree(ev)
        await forest._run(ev, evaluate=False)
        await forest._run(Evaluation(node, False), evaluate=False)

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

    def _last_status(self):
        return self.evaluation_status_ending

    def _beginning_status(self):
        return self.evaluation_status_beginning

    def _invalidate_subtree(self, ev):
        self._set_beginning(ev, NOT_EVALUATED)
        super()._invalidate_subtree(ev)
        self._set_ending(ev, NOT_EVALUATED)

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
            _completed(self.on_invalidated)

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
            beginning = self.evaluation_status_beginning
            if beginning is not READY and not _is_own_stop(beginning):
                ok = await self._eval_beginning_opr()             # a blocked one reruns
                self._set_beginning(ev, READY if ok else CannotEvaluate(None))
            if _is_own_stop(self.evaluation_status_beginning):    # the children have no context
                r = await self._evaluate_children(ev, Evaluating(self))
                if r.mode is INVALIDATING:
                    await self._mark_not_evaluated(ev)
                    return EvaluationResult(None, INVALIDATING)
                if self.evaluation_status_ending is not READY:    # already standing: re-setting would release it
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


# ---------------------------------------------------------------------------
# Building nodes from RawASTs (MODULE_STRUCTURE §4.1)

# The JSON object the agent submitted.  `kind` and `children` belong to the
# framework; the other fields are the node class's own.
RawAST = Mapping[str, Any]


@dataclass(frozen=True)
class Argument:
    """One field of a class's argument schema: its JSON type(s), whether it
    is required, and the description the tool schema shows."""
    type: type | tuple[type, ...]
    required: bool = True
    description: str = ""


class NodeConfig(NamedTuple):
    state: Isar_State_Slot   # the state before the node.  A name: the slot
                             # may hold nothing, and gen neither reads nor
                             # writes through it — only evaluation hooks may
                             # assume a slot holds a state
    parent: NonLeaf_Node     # never None: the forest root is not made this
                             # way.  During an edit this may be a node not
                             # yet in the forest
    replacing: Node | None   # on the amend path, the node this description
                             # is replacing; None on every other path.  Read
                             # it for exactly two things: leave it out of any
                             # uniqueness check, and carry over recorded
                             # fields the class judges still valid.
                             # Read-only; never mutate it


_JSON_TYPE_NAMES = {str: "a string", bool: "a boolean", int: "a number",
                    float: "a number", list: "a list", dict: "an object"}


def _check_schema(cls: type[Node], kind: str, raw: RawAST) -> None:
    """The mechanical shape, before the class is consulted: required fields
    present, types right."""
    for field, arg in cls.argument_schema.items():
        if field not in raw:
            if arg.required:
                raise MissingField(kind, field)
            continue
        types = arg.type if isinstance(arg.type, tuple) else (arg.type,)
        # bool passes isinstance against int; a flag is not a number.
        if not isinstance(raw[field], types) or (
                isinstance(raw[field], bool) and bool not in types):
            names = " or ".join(_JSON_TYPE_NAMES.get(t, t.__name__)
                                for t in types)
            raise InvalidField(field, f"must be {names}")


def _gate(hook, *args) -> None:
    """Fire a progressive hook: `BadEdit` vetoes the call; anything else it
    raises is the class's bug (MODULE_STRUCTURE §4.1)."""
    try:
        hook(*args)
    except BadEdit:
        raise
    except TAT_Error as e:
        raise TAT_InternalError(f"gate {hook.__qualname__} raised") from e


def _completed(hook, *args) -> None:
    """Fire a completed hook: raising anything is the class's bug — in
    particular a `TAT_Error` must not escape dressed as agent-actionable
    (EXCEPTIONS.md §1)."""
    try:
        hook(*args)
    except TAT_Error as e:
        raise TAT_InternalError(
            f"completed hook {hook.__qualname__} raised") from e


def _tree_order(node: Node) -> list[Node]:
    """The node and its subtree: parents before children, siblings in
    order (ARCHITECTURE §1)."""
    out = [node]
    if isinstance(node, NonLeaf_Node):
        for c in node.sub_nodes:
            out += _tree_order(c)
    return out


def _children_first(node: Node) -> list[Node]:
    """The subtree with children before parents: the order of `on_deleting`
    and `on_deleted` (MODULE_STRUCTURE §4.1)."""
    out: list[Node] = []
    if isinstance(node, NonLeaf_Node):
        for c in node.sub_nodes:
            out += _children_first(c)
    out.append(node)
    return out


async def _construct_siblings(parent: NonLeaf_Node, raws: list[RawAST],
                              kinds: Mapping[str, type[Node]], listname: str,
                              taken: dict[str, Node | str], forest: Forest,
                              replacing_first: Node | None = None
                              ) -> list[Node]:
    """Step 1 of an edit: every description in submission order, detached.
    `taken` maps each surviving sibling's name to the node, each batch
    element's to its coordinate — printed only at the raise — so
    `DuplicateName` points either way.  The element's coordinate is
    prefixed here, around everything done for it — the framework's own
    checks included (EXCEPTIONS.md §5)."""
    nodes = []
    for i, raw in enumerate(raws):
        coordinate = f"{listname}[{i}]"
        try:
            node = await _construct_element(
                raw, kinds, parent,
                replacing_first if i == 0 else None, forest)
            name = getattr(node, "name", None)
            if not isinstance(name, str):
                raise TAT_InternalError(
                    f"{type(node).__name__}.gen set no name")
            if not is_valid_name(name):
                raise InvalidName(name)
            if name in taken:
                holder = taken[name]
                raise DuplicateName(name, holder if isinstance(holder, str)
                                    else forest.id_of(holder))
            taken[name] = coordinate
            nodes.append(node)
        except TAT_Error as e:
            e._prefix_raw_ast_path(coordinate)
            raise
    return nodes


async def _construct_element(raw: RawAST, kinds: Mapping[str, type[Node]],
                             parent: NonLeaf_Node, replacing: Node | None,
                             forest: Forest) -> Node:
    if not isinstance(raw, Mapping):
        raise MalformedRawAST(missing_kind=False)
    if "kind" not in raw:
        raise MalformedRawAST(missing_kind=True)
    kind = raw["kind"]
    if kind not in kinds:
        raise UnknownKind(kind, list(kinds))
    cls = kinds[kind]
    # The children-legality checks run before any gen (MODULE_STRUCTURE
    # §4.1): a Leaf holds no children, an amend's replacement inherits them.
    if "children" in raw:
        if issubclass(cls, Leaf):
            raise UnexpectedChildren(kind, is_leaf=True)
        if replacing is not None:
            raise UnexpectedChildren(kind, is_leaf=False)
        if not isinstance(raw["children"], list):
            raise InvalidField("children", "must be a list")
    if (replacing is not None and isinstance(replacing, NonLeaf_Node)
            and replacing.sub_nodes and issubclass(cls, Leaf)):
        raise ChildrenNotInheritable(forest.id_of(replacing), kind,
                                     len(replacing.sub_nodes))
    _check_schema(cls, kind, raw)
    config = NodeConfig(
        state=Isar_State_Slot.assign(parent.state.connection),
        parent=parent, replacing=replacing)
    node = await cls.gen(config, {k: v for k, v in raw.items()
                                  if k != "children"})
    if "children" in raw:
        if not isinstance(node, NonLeaf_Node):
            raise TAT_InternalError(
                f"{cls.__name__} took children but is no nesting class")
        children = await _construct_siblings(
            node, raw["children"], kinds, "children", {}, forest)
        for child in children:                # the framework owns placement
            child.parent = node
        node.sub_nodes.extend(children)
    return node


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

    def _last_status(self):
        raise NotImplementedError                # the forest is nobody's sibling

    def _predecessor_wrote(self, index):
        return False                             # trees are not chained

    async def _mark_not_evaluated(self, ev):
        pass                                    # no ending

    # --- ids: resolution and shortest-form printing (MCP_SPECIFICATION §2.1).
    # Ambiguity is judged across the whole forest, so both live here.

    def _all_nodes(self) -> list[Node]:
        """Every node below the root, in tree order."""
        return [n for t in self.sub_nodes for n in _tree_order(t)]

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
            if chain[-1].name != parts[-1]:
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
                            (chain[ci].name == parts[pi]
                             and match(ci + 1, pi + 1))
                            or (chain[ci].input_omissible
                                and match(ci + 1, pi)))
                return memo[key]
            return match(0, 0)
        return [n for n in self._all_nodes() if admits(self._chain(n))]

    def resolve(self, id: str) -> Node:
        """The node an agent-supplied id designates; `$Root` is the forest
        itself.  No match: `NodeNotFound`, with the closest printed ids as
        guesses.  Several: `AmbiguousId`, the candidates in tree order."""
        if id == "$Root":
            return self
        parts = id.split(".")
        matches = self._read(parts)
        if len(matches) == 1:
            return matches[0]
        if not matches:
            # Guess by the last component — printing an id for every node
            # would be quadratic in the forest.
            nodes = self._all_nodes()
            close = set(difflib.get_close_matches(
                parts[-1], sorted({n.name for n in nodes})))
            near = [self.id_of(n) for n in nodes if n.name in close][:3]
            raise NodeNotFound(id, near)
        raise AmbiguousId(id, [self.id_of(m) for m in matches])

    def id_of(self, node: Node) -> str:
        """The shortest form: starting from the full id, repeatedly delete —
        among the output-omissible components whose deletion still resolves
        to exactly this node — the one with the lowest drop priority, the
        outermost on ties, until none can go."""
        if node is self:
            return "$Root"
        chain = self._chain(node)
        kept = list(range(len(chain)))
        while True:
            best = None
            for pos in kept:
                c = chain[pos]
                if not c.output_omissible:
                    continue
                candidate = [chain[p].name for p in kept if p != pos]
                if self._read(candidate) == [node]:
                    key = (c.drop_priority, pos)
                    if best is None or key < best[0]:
                        best = (key, pos)
            if best is None:
                return ".".join(chain[p].name for p in kept)
            kept.remove(best[1])

    async def _run(self, ev: Evaluation, evaluate: bool) -> EvaluationResult:
        """One evaluation under the lock, already held: the walk, then one
        round trip releasing every state it invalidated."""
        r = await self._evaluate(ev, Evaluating() if evaluate else SEEKING)
        await ev.flush(ev.destination.state.connection)
        return r

    async def _evaluate(self, ev, mode):
        raise NotImplementedError
