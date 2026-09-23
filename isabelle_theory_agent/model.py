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
import io
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import (Any, ClassVar, Literal, NamedTuple, NotRequired, Self, TextIO, TypeAlias,
                    TypedDict)

from Isabelle_RPC_Host import Connection

from . import isabelle_driver
from .exceptions import (
    AmbiguousId, BadEdit, BadSessionNodeParent, BadTheoryNodeParent,
    DuplicateTheoryShortName, InvalidField, InvalidName, NodeNotFound, ReservedTheoryName,
    TAT_Error, TAT_InternalError, TAT_StartupError)
from .store import Forest_Store, MissingRow, Node_Rows


# A JSON schema, as `json` reads it.  (`TypeAlias` rather than the `type`
# statement: the package supports Python 3.11.)
JSON_Schema: TypeAlias = dict[str, Any]

# What an id is made of (MCP_SPECIFICATION §2, MODULE_STRUCTURE §4.1).
Id: TypeAlias = str                      # the dotted string the agent sees
Id_Component: TypeAlias = str            # one `<kind>_<name>`
Id_Components: TypeAlias = list[Id_Component]
Identity: TypeAlias = int                # the stored, opaque number


def id_components(id: Id) -> Id_Components:
    return id.split(".")


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

class CannotEvaluate(_Singleton):
    """The operation ran and its class judged the failure fatal: the node is
    an obstacle (ARCHITECTURE §3.3), not rerun until edited, its input
    standing as its result.  What it blocks is `NotEvaluated`, and runs as
    soon as a walk reaches it unblocked."""

NOT_EVALUATED = NotEvaluated()
READY = Ready()
CANNOT_EVALUATE = CannotEvaluate()

EvaluationStatus = NotEvaluated | Ready | CannotEvaluate


def _wrote(status: EvaluationStatus) -> bool:
    """Whether an operation in this status has written its resulting state:
    `ready`, or an own stop, which copied its input through
    (ARCHITECTURE §3.1)."""
    return status is READY or status is CANNOT_EVALUATE


# ---------------------------------------------------------------------------
# One evaluation (ARCHITECTURE §3.5)

class Evaluation:
    """One walk: its two constants, and the states it releases, deleted in
    one round trip when it is flushed.  Whoever creates one flushes it
    once, when its walk ends (`Forest._run` does so for the walks it
    drives); the forest's evaluating walk gives each tree its own
    (`Forest._handle_tree`).  `destination` is the node an evaluating walk
    runs up to and including; an invalidation has none, and its mode says
    where it starts."""

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
    """Before the destination: run what is not `Ready`.  `rewritten`: the
    state at this position was written by an operation that ran in this
    walk, so whatever stands here runs again even if `Ready` or an own
    stop — its input changed under it."""
    rewritten: bool = False

class Blocked(_Singleton):
    """Before the destination, where nothing can run: mark `NotEvaluated`,
    an own stop kept as it is (ARCHITECTURE §3.3)."""

@dataclass(frozen=True)
class Seeking:
    """Before `destination` without evaluating: touch nothing.  The
    destination is a position, not a node, so the walk turns `Invalidating`
    before entering whatever stands there — a nesting node is then
    invalidated whole, opening first (MODULE_STRUCTURE §4.1)."""
    destination: Location

class Invalidating(_Singleton):
    """Past the destination, or throughout a walk that invalidates trees
    whole: mark `NotEvaluated`."""

BLOCKED = Blocked()
INVALIDATING = Invalidating()

EvaluationMode = Evaluating | Blocked | Seeking | Invalidating


@dataclass(frozen=True)
class EvaluationResult:
    stopped_at: Node | None      # the node evaluation stopped at, if it stopped
    mode: EvaluationMode         # the mode the node after this one runs under


# ---------------------------------------------------------------------------
# Nodes

_NAME_GRAMMAR = re.compile(r"[A-Za-z][A-Za-z0-9_'-]*")


# ---------------------------------------------------------------------------
# Rendering (PRINT.md): the print modes, the indent, the error block

class Out_Focus(_Singleton):
    """Not on the path to a focus: the node itself, no children."""

class Briefing(_Singleton):
    """The outline: every node, to the bottom."""

@dataclass(frozen=True)
class Relative_Focus:
    """The quickview's mode (PRINT.md §2, §5): every node of `nodes` is a
    focus, with what lies `depth` levels under it — its whole subtree at
    -1; a node above one is on the path."""
    nodes: frozenset[Node]
    depth: int

class Recall(_Singleton):
    """The recalled node and what is under it."""

OUT_FOCUS = Out_Focus()
BRIEFING = Briefing()
RECALL = Recall()

PrintMode = Out_Focus | Briefing | Relative_Focus | Recall

INDENT = "  "                            # one level


def print_error(indent: int, out: TextIO, message: str) -> None:
    """The error block (PRINT.md §3): `Error:` at `indent`, every line of
    the message one level deeper."""
    out.write(INDENT * indent + "Error:\n")
    for line in message.rstrip("\n").split("\n"):
        out.write(INDENT * (indent + 1) + line + "\n")


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
    identity: Identity   # opaque; survives renaming, moving and restarts
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
        functions (MODULE_STRUCTURE §4.3); must not write.  Raises
        `TAT_Error`s bare — the framework prefixes the `raw_ast_path`
        (EXCEPTIONS.md §5)."""
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

    def id_component(self) -> Id_Component:
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
    def _own_statuses(self) -> list[EvaluationStatus]:
        """The statuses of the node's own operations, in the order it runs
        them: a leaf's one, a nesting node's beginning and ending, none for
        a container that runs nothing.  What `_operations_ready` and the
        default `mark` read; a class with statuses of its own answers them
        here and overrides neither (PLUGIN_SYSTEM §5)."""

    def _operations_ready(self) -> bool:
        """Whether every operation of this node — not its subtree — is
        `Ready`."""
        return all(s is READY for s in self._own_statuses())

    # --- Rendering (PRINT.md).  The framework writes the line and descends;
    # a class writes its fields and errors, and may say more in `mark`.

    def print(self, indent: int, out: TextIO, mode: PrintMode, depth: int) -> None:
        """The line at `indent`, then `print_fields` and the children one
        level deeper (PRINT.md §2).  The root's only child, reached from the
        root, writes its line without the dash and its body at the same
        indent (§6)."""
        forest = self.forest()
        mark = self.mark(mode, depth)
        line = forest.id_of(self) + (f" ({mark})" if mark else "")
        alone = self.parent is forest and len(forest.sub_nodes) == 1 and depth >= 1
        out.write(INDENT * indent + ("" if alone else "- ") + line + "\n")
        below = indent if alone else indent + 1
        self.print_fields(below, out, mode, depth)
        for child, child_mode in self._children_to_print(mode, depth):
            child.print(below, out, child_mode, depth + 1)

    def print_fields(self, indent: int, out: TextIO, mode: PrintMode, depth: int) -> None:
        """The class's: its fields and its errors, one per line at `indent`,
        chosen by mode and depth (PRINT.md §3).  Nothing by default."""

    def detailed(self, mode: PrintMode, depth: int) -> bool:
        """A helper for a class's `print_fields`: this node is a focus, or
        under `recall` above the grandchildren."""
        return ((isinstance(mode, Relative_Focus) and self in mode.nodes)
                or (mode is RECALL and depth < 2))

    def mark(self, mode: PrintMode, depth: int) -> str | None:
        """The default of PRINT.md §1, first row wins; a class overrides it
        to say more where this says nothing."""
        if self.is_finished():
            return "success"
        statuses = self._own_statuses()
        if any(s is CANNOT_EVALUATE for s in statuses):
            return "failed"
        if any(s is NOT_EVALUATED for s in statuses):
            return "not evaluated"
        return None

    def _children_to_print(self, mode: PrintMode, depth: int) -> list[tuple[Node, PrintMode]]:
        """The children `print` descends into and the mode each gets
        (PRINT.md §2's table); none for a leaf."""
        return []

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
    async def _evaluate(self, ev: Evaluation, mode: EvaluationMode) -> EvaluationResult:
        """One recursion for evaluation and invalidation (ARCHITECTURE §3.5),
        visiting every node of the subtree under `mode`.  A nesting node is
        reached at its ending, so its children come before it."""

    @abstractmethod
    async def _mark_not_evaluated(self, ev: Evaluation) -> None:
        """Mark the node — for a nesting node, its ending — `NotEvaluated`.
        What an edit does before evaluating."""

    def _mode_after(self, ev: Evaluation, mode: Evaluating | Blocked, stop: Node | None,
                    ran: bool) -> EvaluationMode:
        """The one place the mode changes: the destination turns it into
        `Invalidating`; otherwise a stop blocks what follows, and `ran` tells
        the successor whether its input was just rewritten."""
        if self is ev.destination:
            return INVALIDATING
        if stop is not None or mode is BLOCKED:
            return BLOCKED
        return Evaluating(rewritten=ran)

    async def evaluate_to(self, ignore_error: bool, evaluate: bool = True) -> EvaluationResult:
        """The `evaluate_to` tool's entry: takes the forest's lock itself —
        an edit, whose tool entry already holds it, drives the walk through
        `Forest._run` instead (MODULE_STRUCTURE §4.1).  With
        `evaluate`: run up to and including this node.  Without: only
        invalidate from this node on — a node nothing chains, the child of
        an `Unchained_Node`, whole (ARCHITECTURE §3.5).  The walk visits
        every node, so the result's `mode` is always `Invalidating`; what
        happened to this node it reports itself."""
        forest = self.forest()
        async with forest.lock:
            if evaluate:
                return await forest._run(Evaluation(self, ignore_error), Evaluating())
            if self.parent is None:
                raise TAT_InternalError("the forest root has no position")
            if isinstance(self.parent, Unchained_Node):
                return await forest._invalidate_whole(self)
            return await forest._invalidate_from(Location(self.parent, self.index_of()))


class Leaf(Node):

    _status: EvaluationStatus

    def __init__(self, parent, state):
        super().__init__(parent, state)
        self._status = NOT_EVALUATED

    def _last_status(self):
        return self._status

    def _own_statuses(self):
        return [self._status]

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
        if mode is BLOCKED:
            if self._status is not CANNOT_EVALUATE:      # an own stop keeps reporting itself
                self._set_status(ev, NOT_EVALUATED)
            return EvaluationResult(None, self._mode_after(ev, BLOCKED, None, False))
        if isinstance(mode, Evaluating):
            stop, ran = None, False
            # Not rerun: a Ready operation, or an own stop — unless the
            # input under it was rewritten this walk.
            if mode.rewritten or not _wrote(self._status):
                ran = True
                if await self._eval_opr():
                    self._set_status(ev, READY)
                else:
                    await self.state.copy_to(self.resulting_state())
                    self._set_status(ev, CANNOT_EVALUATE)
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

    def _children_to_print(self, mode: PrintMode, depth: int) -> list[tuple[Node, PrintMode]]:
        pairs: list[tuple[Node, PrintMode]] = []
        if mode is BRIEFING:
            pairs = [(c, BRIEFING) for c in self.sub_nodes]
        elif mode is RECALL and depth < 3:
            pairs = [(c, RECALL) for c in self.sub_nodes]
        elif isinstance(mode, Relative_Focus):
            if self in mode.nodes:                   # a focus: its children are focuses one level shallower
                if mode.depth == 0:
                    pairs = [(c, OUT_FOCUS) for c in self.sub_nodes]
                else:
                    below = Relative_Focus(frozenset(self.sub_nodes), max(mode.depth - 1, -1))
                    pairs = [(c, below) for c in self.sub_nodes]
            else:                                    # on the path: only what leads to a focus continues
                above = self.forest()._above
                assert above is not None and self in above, "Relative_Focus off its path"
                pairs = [(c, mode if c in mode.nodes or c in above else OUT_FOCUS)
                         for c in self.sub_nodes]
        return pairs                                 # none for Out_Focus and Recall at depth 3

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

    async def _evaluate_children(self, ev: Evaluation, mode: EvaluationMode) -> EvaluationResult:
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

    def _own_statuses(self):
        return [self.evaluation_status_beginning, self.evaluation_status_ending]

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

    async def _set_ending(self, ev: Evaluation, new: EvaluationStatus) -> None:
        """Async, alone among the three setters: `Theory`'s carries a rule
        that walks other trees (ARCHITECTURE §3.4)."""
        old = self.evaluation_status_ending
        if _wrote(old) and not _wrote(new):               # written -> unwritten; a rewrite releases nothing
            ev.release(self.resulting_state())
        self.evaluation_status_ending = new
        if old is READY and new is not READY:
            _completed(self.on_invalidated, "ending")

    async def _mark_not_evaluated(self, ev):
        if self.evaluation_status_ending is not NOT_EVALUATED:
            await self._set_ending(ev, NOT_EVALUATED)

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
        if isinstance(mode, Evaluating):
            beginning = self.evaluation_status_beginning
            began = mode.rewritten or not _wrote(beginning)   # not evaluated reruns; an own stop does not
            if began:
                ok = await self._eval_beginning_opr()
                self._set_beginning(ev, READY if ok else CANNOT_EVALUATE)
            if self.evaluation_status_beginning is CANNOT_EVALUATE:   # the children have no context
                r = await self._evaluate_children(ev, BLOCKED)
                if r.mode is INVALIDATING:
                    await self._mark_not_evaluated(ev)
                    return EvaluationResult(None, INVALIDATING)
                # The input stands as the result — copied again when the
                # input was rewritten; a standing copy is left alone.
                copied = mode.rewritten or self.evaluation_status_ending is not READY
                if copied:
                    await self.state.copy_to(self.resulting_state())
                    await self._set_ending(ev, READY)
                return EvaluationResult(None, self._mode_after(ev, mode, None, copied))

            r = await self._evaluate_children(ev, Evaluating(rewritten=began))
            if r.mode is INVALIDATING:                    # the ending lies past the destination
                await self._mark_not_evaluated(ev)
                return EvaluationResult(r.stopped_at, INVALIDATING)
            if r.stopped_at is not None:                  # no state to run the ending from
                if self.evaluation_status_ending is not CANNOT_EVALUATE:
                    await self._set_ending(ev, NOT_EVALUATED)
                return EvaluationResult(r.stopped_at, self._mode_after(ev, mode, r.stopped_at, False))
            assert isinstance(r.mode, Evaluating)
            ended = r.mode.rewritten or not _wrote(self.evaluation_status_ending)
            if ended:
                if await self._eval_ending_opr():
                    await self._set_ending(ev, READY)
                else:
                    await self._state_before_ending.copy_to(self.resulting_state())
                    await self._set_ending(ev, CANNOT_EVALUATE)
            stop = None                                   # an ending that failed stays a stop until edited
            if self.evaluation_status_ending is not READY and not ev.ignore_error:
                stop = self
            return EvaluationResult(stop, self._mode_after(ev, mode, stop, ended))

        # Not running here: blocked, past the destination, or seeking.  A
        # blocked walk never overwrites an own stop: the node keeps
        # reporting itself as the obstacle, and is not rerun
        # (ARCHITECTURE §3.3); an invalidating walk resets it.
        if mode is BLOCKED:
            if self.evaluation_status_beginning is not CANNOT_EVALUATE:
                self._set_beginning(ev, NOT_EVALUATED)
        elif mode is INVALIDATING:
            self._set_beginning(ev, NOT_EVALUATED)
        r = await self._evaluate_children(ev, mode)
        if r.mode is INVALIDATING:
            await self._mark_not_evaluated(ev)
        elif mode is BLOCKED:
            if self.evaluation_status_ending is not CANNOT_EVALUATE:
                await self._set_ending(ev, NOT_EVALUATED)
        reached = r.mode is INVALIDATING or self is ev.destination
        if reached:
            return EvaluationResult(None, INVALIDATING)
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

    def _own_statuses(self):
        return []                                # no operation: nothing owed

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
    """What one conversation is given and the forest does not store
    (ARCHITECTURE §1, §9): the connection to the Isabelle side, the
    working directory (ARCHITECTURE §4), and the seen set (PRINT.md §4) —
    what a class has shown the agent once, under keys of the class's
    choosing; cleared whole when the agent's context is replaced.  A node
    reaches it through `forest().conversation`."""
    connection: Connection
    working_directory: Path
    seen: set[Any] = field(default_factory=set)


# The empty forest's one line under `Sessions:` (PRINT.md §6), approved wording.
EMPTY_FOREST = ('There are no Isabelle sessions yet. Call `edit` with `{"action": "append",'
                ' "target_id": "Sessions", "constructs": [{"kind": "session", ...}],'
                ' "evaluate": false}` to declare one.')


class TreeRecord(NamedTuple):
    """What an edit compares per tree (ARCHITECTURE §3.4): the two things
    an edit can change without moving any ending."""
    qualified_name: str
    resolved_imports: frozenset[Theory]     # the nodes themselves: an `amend` replaces one


Tree_Records: TypeAlias = dict[Identity, TreeRecord]


class Forest(Unchained_Node):
    """The root above every `Session` (MODULE_STRUCTURE §4.1): holds the
    lock, the store and the `Conversation`, resolves and prints ids."""

    conversation: Conversation
    lock: asyncio.Lock                         # held across every evaluation and tree change
    store: Forest_Store                        # the working directory's database (the plan's §2)
    _index: dict[Id_Component, list[Node]] | None   # id component -> its bearers, while `render` runs
    _above: frozenset[Node] | None             # the nodes above a focus, while `render` runs in Relative_Focus

    ROOT_IDENTITY: ClassVar[Identity] = 0      # `next_identity` starts at 1

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
        self._index = None
        self._above = None
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

    def _bearing(self, component: Id_Component) -> list[Node]:
        """The nodes whose own component is `component`, in tree order: from
        the index while a rendering runs, else by walking the forest."""
        if self._index is not None:
            return self._index.get(component, [])
        return [n for n in self._all_nodes() if n.id_component() == component]

    def _read(self, parts: Id_Components) -> list[Node]:
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
        return [n for n in self._bearing(parts[-1]) if admits(self._chain(n))]

    def resolve(self, id: Id) -> Node:
        """The node an agent-supplied id designates; `Sessions` is the forest
        itself.  No match: `NodeNotFound`, with the closest printed ids as
        guesses.  Several: the exact match wins — the one whose chain
        equals the id component for component, nothing dropped; sibling
        names are unique, so there is at most one, and a full id therefore
        always designates its node (MCP_SPECIFICATION §2.1).  Otherwise:
        `AmbiguousId`, the candidates in tree order."""
        if id == "Sessions":
            return self
        parts = id_components(id)
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

    def id_of(self, node: Node) -> Id:
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

    # --- rendering (PRINT.md §5, §6)

    def render(self, node: Node, mode: PrintMode) -> str:
        """Every rendering's entry (MODULE_STRUCTURE §4.1).  The index that
        makes every printed id linear in the forest lives exactly as long
        as this call, which is synchronous: a move could change a short
        form.  So does `_above`, what `Relative_Focus`'s path is made of:
        every focus must lie under `node` and under no other focus."""
        if self._index is not None:
            raise TAT_InternalError("a rendering started inside a rendering")
        out = io.StringIO()
        index: dict[Id_Component, list[Node]] = {}
        for n in self._all_nodes():
            index.setdefault(n.id_component(), []).append(n)
        above: set[Node] = set()
        if isinstance(mode, Relative_Focus):
            if not mode.nodes:
                raise TAT_InternalError("a Relative_Focus with no focus")
            for focus in mode.nodes:
                ancestors: list[Node] = []
                p = focus.parent
                while p is not None:
                    ancestors.append(p)
                    p = p.parent
                if focus is not node and node not in ancestors:
                    raise TAT_InternalError("a focus outside the rendered node")
                if any(a in mode.nodes for a in ancestors):
                    raise TAT_InternalError("a focus under another focus")
                above.update(ancestors)
        self._index, self._above = index, frozenset(above)
        try:
            node.print(0, out, mode, 0)
        finally:
            self._index = self._above = None
        return out.getvalue()

    def print(self, indent, out, mode, depth):
        """The root's three forms (PRINT.md §6): `Sessions:` over the list,
        the lone session alone — its own `print` drops the dash — or the
        empty forest's hint.  `Sessions:` carries no dash and opens no
        level; the hint, the root's one line under it, sits one level in."""
        if not self.sub_nodes:
            out.write(INDENT * indent + "Sessions:\n")
            out.write(INDENT * (indent + 1) + EMPTY_FOREST + "\n")
            return
        if len(self.sub_nodes) > 1:
            out.write(INDENT * indent + "Sessions:\n")
        for child, child_mode in self._children_to_print(mode, depth):
            child.print(indent, out, child_mode, depth + 1)

    # --- the walk (ARCHITECTURE §3.5): its entries, the trees, the import
    # graph, and `_evaluate` over the trees.  The graph is a function of
    # the forest, recomputed by every walk and every edit that reads it,
    # never stored; it may hold a cycle, a self-import included, since
    # `Theory.gen` judges nothing about what an item names, and every
    # reading of it is finite under cycles.

    async def _run(self, ev: Evaluation, mode: EvaluationMode) -> EvaluationResult:
        """One walk under the lock, already held, then one round trip
        releasing every state it invalidated — nothing, after an evaluating
        walk, whose trees each flushed their own (`_handle_tree`)."""
        assert self.lock.locked(), "a walk runs under the forest lock"
        r = await self._evaluate(ev, mode)
        await ev.flush(self.state.connection)
        return r

    async def _invalidate_from(self, position: Location) -> EvaluationResult:
        """An edit's unconditional invalidation (MCP_SPECIFICATION §3.2):
        everything from `position` on in its tree, the node standing there
        whole; nothing under a `Session` or the root, where sibling trees
        are independent — what an edit there disturbed is
        `_invalidate_changed_trees`'."""
        return await self._run(Evaluation(None, False), Seeking(position))

    async def _invalidate_whole(self, node: Node) -> EvaluationResult:
        """`evaluate_to(evaluate=False)` on a node nothing chains, the child
        of an `Unchained_Node`: the node whole — for a `Session`, every tree
        under it — under one `Evaluation`, flushed here."""
        ev = Evaluation(None, False)
        await self._invalidate_trees(
            ev, list(node.sub_nodes) if isinstance(node, Session) else [node])
        await ev.flush(self.state.connection)
        return EvaluationResult(None, INVALIDATING)

    async def _invalidate_trees(self, ev: Evaluation, trees: Sequence[Node]) -> None:
        """Walk each of `trees` whole in `Invalidating` mode under the
        caller's `Evaluation`, which the caller flushes."""
        assert self.lock.locked(), "a walk runs under the forest lock"
        for tree in trees:
            await tree._evaluate(ev, INVALIDATING)

    def _trees(self) -> list[Theory]:
        """The trees in tree order: the `Theory` nodes under the `Session`
        nodes under the root, selected by class at both levels — a root
        holding something else, as a test double's does, holds no tree."""
        return [t for s in self.sub_nodes if isinstance(s, Session)
                for t in s.sub_nodes if isinstance(t, Theory)]

    def _tree_of(self, node: Node) -> Node:
        """The child of an `Unchained_Node` above `node`, or `node` itself."""
        while node.parent is not None and not isinstance(node.parent, Unchained_Node):
            node = node.parent
        return node

    def _trees_under(self, node: Node) -> list[Theory]:
        """The trees a destination stands for (ARCHITECTURE §3.5): every
        tree for the root, every tree under a `Session`, else the tree
        containing the node."""
        if node is self:
            return self._trees()
        if isinstance(node, Session):
            return [t for t in node.sub_nodes if isinstance(t, Theory)]
        tree = self._tree_of(node)
        assert isinstance(tree, Theory), "a node outside every tree"
        return [tree]

    def _name_table(self) -> dict[str, Theory]:
        return {t.qualified_name(): t for t in self._trees()}

    @staticmethod
    def _import_of(tree: Theory, item: str, table: dict[str, Theory]) -> Theory | None:
        """The forest tree an `imports` item names, or None when the item is
        external: a dotted item as written, a bare one under the tree's own
        `Session`.  This agrees with `Resources.theory_name`: on a dotted
        item it is the same rule; on a bare item the two differ exactly
        when the name is global, and then both answer no tree — no tree
        bears a global name (`ReservedTheoryName`), and every qualified name
        carries a dot."""
        return table.get(item if "." in item else f"{tree.session().name}.{item}")

    def _resolved_imports(self, tree: Theory,
                          table: dict[str, Theory] | None = None) -> list[Theory]:
        """The forest trees among `tree`'s `imports`, in the items' order as
        the agent wrote them, each at its first occurrence."""
        if table is None:
            table = self._name_table()
        out: list[Theory] = []
        for item in tree.imports:
            target = self._import_of(tree, item, table)
            if target is not None and target not in out:
                out.append(target)
        return out

    def _importers(self, tree: Theory) -> list[Theory]:
        """The trees whose resolved imports contain `tree`, in tree order —
        `tree` itself when it imports itself."""
        table = self._name_table()
        return [t for t in self._trees() if tree in self._resolved_imports(t, table)]

    def _closure(self, trees: Sequence[Theory]) -> list[Theory]:
        """The least set containing `trees` and closed under resolved
        imports, in tree order."""
        table = self._name_table()
        closed: set[Theory] = set()
        pending = list(trees)
        while pending:
            tree = pending.pop()
            if tree not in closed:
                closed.add(tree)
                pending.extend(self._resolved_imports(tree, table))
        return [t for t in self._trees() if t in closed]

    def _order_violation(self, node: Node) -> str | None:
        """The order constraint (ARCHITECTURE §3.3): the first `imports`
        item, as the agent wrote it, whose forest tree does not lie strictly
        earlier in tree order — placed after the tree, or the tree itself —
        or None.  Total on nodes, None off a `Theory`, so the renderer may
        ask it of any `stopped_at` and compose RENDER_BASELINES §3's sentence
        from the answer.  No edit refuses the state; the check runs before
        every run of the tree, so a repairing `move` clears it by itself."""
        if not isinstance(node, Theory):
            return None
        trees = self._trees()
        table = {t.qualified_name(): t for t in trees}
        position = trees.index(node)
        for item in node.imports:
            target = self._import_of(node, item, table)
            if target is not None and trees.index(target) >= position:
                return item
        return None

    async def _handle_tree(self, ev: Evaluation, tree: Theory) -> Node | None:
        """One tree of an evaluating walk, and its stop, if any, by the
        first case that applies: the order constraint's stop, the stop
        crossing an import dependency, the run (MODULE_STRUCTURE §4.1;
        ARCHITECTURE §3.3).  Under either stop the tree is not run but
        walked whole in `Invalidating` mode.  The tree has its own
        `Evaluation`, flushed here, so a slot released for one tree is gone
        before a later tree of the walk could write it."""
        own = Evaluation(ev.destination, ev.ignore_error)
        if self._order_violation(tree) is not None:
            await self._invalidate_trees(own, [tree])
            stop: Node | None = tree                      # reported whatever ignore_error says
        else:
            # both operations: after a failed header the ending is ready with no theory value
            missing = next((i for i in self._resolved_imports(tree)
                            if not i._operations_ready()), None)
            if missing is not None:
                await self._invalidate_trees(own, [tree])
                stop = None if ev.ignore_error else missing
            else:
                stop = (await tree._evaluate(own, Evaluating())).stopped_at
        await own.flush(self.state.connection)
        return stop

    async def _evaluate(self, ev, mode):
        """The forest's part of the recursion (ARCHITECTURE §3.5), which
        works on the trees directly.  `Seeking`: routed to the one tree the
        position lies in; under a `Session` or the root nothing is walked.
        `Evaluating`, with `ev.destination` set: the closure of the trees
        the destination stands for, in tree order, each by `_handle_tree`
        — a tree reaching the second case there has every resolved import
        earlier in tree order and already handled, so its statuses are
        current.  The result names the first stop in tree order
        (MCP_SPECIFICATION §4)."""
        if isinstance(mode, Seeking):
            parent = mode.destination.parent
            if isinstance(parent, Unchained_Node):
                return EvaluationResult(None, INVALIDATING)
            return await self._tree_of(parent)._evaluate(ev, mode)
        if not isinstance(mode, Evaluating) or ev.destination is None:
            raise TAT_InternalError("a forest walk evaluates to a destination or seeks a position")
        stopped_at: Node | None = None
        for tree in self._closure(self._trees_under(ev.destination)):
            stop = await self._handle_tree(ev, tree)
            if stopped_at is None:
                stopped_at = stop
        return EvaluationResult(stopped_at, INVALIDATING)

    # --- what an edit compares (ARCHITECTURE §3.4)

    def _record(self) -> Tree_Records:
        """Every tree's `TreeRecord`, by identity."""
        table = self._name_table()
        return {t.identity: TreeRecord(t.qualified_name(),
                                       frozenset(self._resolved_imports(t, table)))
                for t in self._trees()}

    async def _invalidate_changed_trees(self, ev: Evaluation, before: Tree_Records) -> None:
        """After an edit's commit, against the record taken at its start:
        every tree present in both whose record changed — its `Session`
        renamed, itself renamed, moved into another `Session`, a tree it
        imports vanished, appeared or replaced by an `amend`, or a name it
        imports now naming another tree — is walked whole in `Invalidating`
        mode, its ending then carrying the rule of `Theory._set_ending`
        onward; every qualified name present before and absent after is
        removed from the ML theory table, in one round trip
        (EVALUATOR_DESIGN §3)."""
        after = self._record()
        await self._invalidate_trees(
            ev, [t for t in self._trees()
                 if t.identity in before and before[t.identity] != after[t.identity]])
        kept = {record.qualified_name for record in after.values()}
        vanished = sorted(record.qualified_name for record in before.values()
                          if record.qualified_name not in kept)
        if vanished:
            await isabelle_driver.theory_delete(self.state.connection, vanished)


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


# The two names that become path elements — `<session>/<short name>.thy`,
# and every import through `Path.explode` — and so take no prime, which
# Isabelle refuses in a path element (Pure/General/path.ML, `illegal_char`).
# A theory short name is an Isabelle identifier without the prime: no
# hyphen, no dot; a trailing underscore, legal here, is the framework's
# name grammar to refuse, with the rendering that says so.  A session name
# is the same with interior hyphens (`HOL-Library`), not ending in a hyphen
# or an underscore: strictly narrower than the framework's grammar, whose
# rendering therefore never fires for a `Session`.
_THEORY_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_SESSION_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


def is_valid_session_name(name: str) -> bool:
    return bool(_SESSION_NAME.fullmatch(name)) and not name.endswith(("-", "_"))


def is_theory_name_item(item: str) -> bool:
    """An item of `imports` (SESSION_AND_THEORY §2): `<short name>` or
    `<session>.<short name>`, each half in the session name's grammar so
    that the AFP's hyphenated theory names (`AList-Utils`) can be imported;
    no quotes, no path, no `.thy`.  Isabelle's two steps in Isabelle's
    order — the `.thy` suffix refused on the whole item before the halves
    are read (`Thy_Header.import_name`, Pure/Thy/thy_header.ML:131-134),
    since `thy` is itself a legal half — so that on this domain
    `Thy_Header.import_name` is the identity and the forest's reading of
    an item (`Forest._import_of`) agrees with Isabelle's."""
    if item.endswith(".thy"):
        return False
    halves = item.split(".")
    return len(halves) <= 2 and all(is_valid_session_name(half) for half in halves)


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
        if not is_valid_session_name(raw["name"]):
            raise InvalidName(raw["name"], "session name")
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

    def print_fields(self, indent, out, mode, depth):
        """SESSION_AND_THEORY §4: `parent_session` in the briefing and when
        detailed; `options` and `description`, when there are any, when
        detailed."""
        if mode is BRIEFING or self.detailed(mode, depth):
            out.write(INDENT * indent + f"parent_session: {self.parent_session}\n")
        if self.detailed(mode, depth):
            if self.options:
                out.write(INDENT * indent + "options: "
                          + ", ".join(f"{o['name']} = {o['value']}" for o in self.options) + "\n")
            if self.description:
                out.write(INDENT * indent + "description:\n")
                for line in self.description.rstrip("\n").split("\n"):
                    out.write(INDENT * (indent + 1) + line + "\n")

    async def _evaluate(self, ev, mode):
        raise TAT_InternalError(
            "a walk reached a Session: evaluation is transparent to the Session layer")


class Theory_RawAST(TypedDict):
    kind: Literal["theory"]
    name: str
    imports: list[str]


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
        if not _THEORY_NAME.fullmatch(name):
            raise InvalidName(name, "theory name")
        # The Isabelle half of the short-name check; the forest half is the
        # framework's, through `namespace` (the plan's §3).
        connection = config.parent.forest().conversation.connection
        match await isabelle_driver.check_new_theory_short_name(connection, name):
            case isabelle_driver.Taken(holder):
                raise DuplicateTheoryShortName(name, holder)
            case isabelle_driver.Reserved():
                raise ReservedTheoryName(name)
            case isabelle_driver.Free():
                pass
        # The item's shape only; whether it names anything is
        # `begin_theory`'s report at evaluation (SESSION_AND_THEORY §2).
        if not raw["imports"]:
            raise InvalidField("imports", "must not be empty")
        for i, item in enumerate(raw["imports"]):
            if not item:
                raise InvalidField(f"imports[{i}]", "must not be empty")
            if not is_theory_name_item(item):
                raise InvalidField(f"imports[{i}]",
                                   "must be a theory name without quotes; a path is not allowed")
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

    def qualified_name(self) -> str:
        """`<Session name>.<short name>`, computed, never stored: the key of
        the ML theory table (EVALUATOR_DESIGN §7)."""
        return f"{self.session().name}.{self.name}"

    def header(self) -> str:
        """The `theory … begin` span, as the tree's file will open; every
        import quoted, so a hyphenated name is one token to Isabelle's
        lexer."""
        imports = " ".join(f'"{item}"' for item in self.imports)
        return f"theory {self.name}\n  imports {imports}\nbegin"

    async def _set_ending(self, ev, new):
        """ARCHITECTURE §3.4's rule, a property of the status: whenever the
        ending was `ready` and no longer is, the tree's direct importers are
        walked whole in `Invalidating` mode under the same `Evaluation`,
        each ending so moved firing the same rule for its own importers.
        The assignment comes first, so within one cascade no ending leaves
        `ready` twice, cycles included: a tree importing itself re-enters
        its own walk, and the inner call finds the ending already
        `not_evaluated`."""
        old = self.evaluation_status_ending
        await super()._set_ending(ev, new)
        if old is READY and new is not READY:
            forest = self.forest()
            await forest._invalidate_trees(ev, forest._importers(self))

    def print_fields(self, indent, out, mode, depth):
        """SESSION_AND_THEORY §4: `imports` in the briefing, when detailed
        and at `recall`'s depth 2; the two operations' messages — only for
        an operation that is an own stop, the one status a failed run
        leaves standing — whole under `recall` below depth 2, once per run
        elsewhere (the seen set, PRINT.md §4), never in the briefing."""
        if mode is BRIEFING or self.detailed(mode, depth) or (mode is RECALL and depth == 2):
            out.write(INDENT * indent + f"imports: {' '.join(self.imports)}\n")
        if mode is BRIEFING:
            return
        seen = self.forest().conversation.seen
        whole = mode is RECALL and depth < 2
        for operation, status, messages in (
                ("beginning", self.evaluation_status_beginning, self.beginning_errors),
                ("ending", self.evaluation_status_ending, self.ending_errors)):
            if status is not CANNOT_EVALUATE:
                continue
            key = (self.identity, operation)
            if whole or key not in seen:
                for message in messages:
                    print_error(indent, out, message)
                seen.add(key)

    # The two callbacks are `TAT_Common_Nodes.ML`'s; each answers the
    # operation's errors, empty when it passed (ARCHITECTURE §6.2), and
    # whatever it lets escape is a bug (`isabelle_driver.call`).  The
    # previous run's messages go before the call, so a failed call leaves
    # none standing; and the run's key leaves the seen set, so its
    # messages show again (PRINT.md §4).

    async def _eval_beginning_opr(self):
        session = self.session()
        conversation = self.forest().conversation
        conversation.seen.discard((self.identity, "beginning"))
        self.beginning_errors = []
        self.beginning_errors = await isabelle_driver.call(
            conversation.connection, "TAT.Theory.begin",
            (self._state_after_beginning().to_msgpack(),
             (session.name,
              str(conversation.working_directory / session.name),   # the plan's §1
              self.header())))
        return not self.beginning_errors

    async def _eval_ending_opr(self):
        conversation = self.forest().conversation
        conversation.seen.discard((self.identity, "ending"))
        self.ending_errors = []
        self.ending_errors = await isabelle_driver.call(
            conversation.connection, "TAT.Theory.end",
            (self._state_before_ending.to_msgpack(), self._state_after_ending.to_msgpack()))
        return not self.ending_errors


FRAMEWORK_NODE_CLASSES: list[type[Node]] = [Session, Theory]
