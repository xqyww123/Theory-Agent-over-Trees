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
import os
import re
import stat
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import (TYPE_CHECKING, Any, ClassVar, Literal, NamedTuple, NotRequired, Self, TextIO,
                    TypeAlias, TypedDict, TypeVar, final)

from Isabelle_RPC_Host import Connection
from Isabelle_RPC_Host.unicode import IsaTerm

from . import isabelle_driver
from .exceptions import (
    AmbiguousId, BadEdit, BadSessionNodeParent, BadTheoryNodeParent, DuplicateName,
    DuplicateTheoryShortName, InvalidField, InvalidName, NodeNotFound, ReservedSessionName,
    ReservedTheoryName, TAT_Error, TAT_InternalError, TAT_StartupError)
from .log import Log
from .store import Forest_Store, MissingRow, Node_Rows

if TYPE_CHECKING:
    from .mcp_server import Ending


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

    def __init__(self, conversation: Conversation, name: str):
        self.conversation = conversation
        self.name = name

    @classmethod
    def assign(cls, conversation: Conversation) -> Isar_State_Slot:
        cls._counter += 1
        return cls(conversation, f"${cls._counter}")

    def to_msgpack(self) -> str:
        return self.name

    @staticmethod
    def from_msgpack(conversation: Conversation, name: str) -> Isar_State_Slot:
        return Isar_State_Slot(conversation, name)

    async def is_initialized(self) -> bool:
        return await isabelle_driver.state_exists(self.conversation, self.name)

    async def delete(self) -> None:
        """Remove the value from the table.  The slot keeps its name."""
        await isabelle_driver.state_delete(self.conversation, [self.name])

    async def copy_to(self, other: Isar_State_Slot) -> None:
        await isabelle_driver.state_copy(self.conversation, self.name, other.name)

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

@dataclass(frozen=True)
class Ready:
    """The operation ran and its resulting state is current.  Evaluation
    passes through.  `messages`: what the run reported — warnings, or the
    failure the class carried on past — empty for a clean run
    (ARCHITECTURE §3.2)."""
    messages: tuple[IsaTerm, ...] = ()

@dataclass(frozen=True)
class CannotEvaluate:
    """The operation ran and its class judged the failure fatal: the node is
    an obstacle (ARCHITECTURE §3.3) — while it stands it is not rerun
    unless a walk rewrote its input, and its input stands as its result;
    once invalidated (ARCHITECTURE §3.4) it is `NotEvaluated` and runs when
    a walk reaches it unblocked.  What it blocks is `NotEvaluated` too.
    `messages`: the reason."""
    messages: tuple[IsaTerm, ...] = ()

NOT_EVALUATED = NotEvaluated()
READY_CLEAN = Ready()              # the clean run's value: a `Ready`, compared with `==`

EvaluationStatus = NotEvaluated | Ready | CannotEvaluate


def _wrote(status: EvaluationStatus) -> bool:
    """Whether an operation in this status has written its resulting state:
    `ready`, or an obstacle, which copied its input through
    (ARCHITECTURE §3.1)."""
    return status is not NOT_EVALUATED


# The stored form of a status (COMPILATION.md §4): the kind, and the
# messages in their `unicode` spelling.
_STATUS_KINDS: dict[type, str] = {NotEvaluated: "not_evaluated", Ready: "ready",
                                  CannotEvaluate: "cannot_evaluate"}
_STATUS_OF_KIND: dict[str, Callable[[tuple[IsaTerm, ...]], EvaluationStatus]] = {
    "not_evaluated": lambda _: NOT_EVALUATED, "ready": Ready, "cannot_evaluate": CannotEvaluate}


def _status_to_store(status: EvaluationStatus) -> list[Any]:
    messages = () if isinstance(status, NotEvaluated) else status.messages
    return [_STATUS_KINDS[type(status)], [m.unicode for m in messages]]


def _status_from_store(value: Any) -> EvaluationStatus | None:
    """The status a stored value means, or None for a value no status
    writes."""
    if (isinstance(value, list) and len(value) == 2 and value[0] in _STATUS_OF_KIND
            and isinstance(value[1], list) and all(isinstance(m, str) for m in value[1])):
        return _STATUS_OF_KIND[value[0]](tuple(IsaTerm.from_agent(m) for m in value[1]))
    return None


# ---------------------------------------------------------------------------
# One evaluation (ARCHITECTURE §3.5)

_T = TypeVar("_T")


async def _timed(hook: Coroutine[Any, Any, _T]) -> tuple[_T, float]:
    """An evaluation hook's answer and how long it ran, for the setter's
    `operation` record."""
    started = time.monotonic()
    return await hook, time.monotonic() - started


class Evaluation:
    """One walk, or one edit's commit (MODULE_STRUCTURE §4.1): its
    constants, the nodes it passed, the nodes whose status it wrote, and
    the states it releases, deleted in one round trip at each flush — an
    evaluating walk's at each tree's end and when it ends
    (`Forest._handle_tree`, `Forest._run`), an edit's after its commit.
    `destination` is the node an evaluating walk runs up to and including;
    an edit's invalidation has none."""

    def __init__(self, destination: Node | None, ignore_error: bool, checks: str = "no"):
        self.destination = destination
        self.ignore_error = ignore_error
        self.checks = checks                 # "no" | "quick" | "blocking" (CONSTRUCT_INTERACTION §5)
        self.passed: list[Node] = []         # reached in `Evaluating`: a leaf when reached, a nesting node at its ending
        self.stored: set[Node] = set()       # the nodes whose status the walk wrote (COMPILATION.md §4)
        self._released: set[str] = set()
        self.releases = 0                    # the slots deleted over every flush: `walk_ended`'s `slots_released`

    def release(self, slot: Isar_State_Slot) -> None:
        self._released.add(slot.name)

    async def flush(self, conversation: Conversation) -> None:
        if self._released:
            await isabelle_driver.state_delete(conversation, sorted(self._released))
            self.releases += len(self._released)
            self._released.clear()


@dataclass(frozen=True)
class Evaluating:
    """Where an evaluating walk is: before the destination, running what
    is `not_evaluated`.  A written operation is never rerun: whatever
    stands after one that ran is `not_evaluated` already, since every
    invalidation runs forward to the tree's end (ARCHITECTURE §3.4)."""


@dataclass(frozen=True)
class EvaluationResult:
    stopped_at: Node | None      # the node evaluation stopped at, if it stopped
    mode: Evaluating | None      # the mode the node after this one runs under; None past the
                                 # destination, past a stop when `ignore_error` is unset, or at
                                 # a failed beginning the destination lies under: nothing more runs


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


def _indented(indent: int, text: str) -> list[str]:
    """The lines of `text`, each at `indent`."""
    return [INDENT * indent + line for line in text.split("\n")]


def _emit_lines(indent: int, out: TextIO, text: str) -> None:
    """Write `text` as whole lines at `indent`, each ending in a newline
    (COMPILATION.md §3)."""
    out.write("".join(line + "\n" for line in _indented(indent, text)))


def print_error(indent: int, out: TextIO, message: str, header: str = "Error:") -> None:
    """The message block (PRINT.md §3): `header` at `indent`, every line of
    the message one level deeper."""
    _emit_lines(indent, out, header)
    _emit_lines(indent + 1, out, message.rstrip("\n"))


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
    # and reads its own fields; the rows `kind`, `children` and the stored
    # statuses are the framework's.

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
        fresh slot, no batch and nothing leaving.  Synchronous: nothing over
        the wire.  Returns the node without children; the framework loads
        them."""
        raise TAT_InternalError(f"{cls.__name__} has no from_store")

    # The stored statuses (COMPILATION.md §4): one entry per own operation
    # in `_own_statuses()`'s order, the value each `evaluation_status` was
    # last given; one framework row, restored at load (`Forest._load_subtree`).
    _last_evaluation_statuses: list[EvaluationStatus]

    def __init__(self, parent: NonLeaf_Node | None, state: Isar_State_Slot):
        self.parent = parent
        self.state = state
        self._last_evaluation_statuses = [NOT_EVALUATED for _ in self._operation_names()]

    @final
    def last_evaluation_statuses(self) -> tuple[EvaluationStatus, ...]:
        """The stored statuses, what `can_emit` and a compile read."""
        return tuple(self._last_evaluation_statuses)

    # --- What the three setters share (MODULE_STRUCTURE §4.1, "Status").
    # A setter: the guard; the release when its operation goes from written
    # to unwritten; the instant status; `_written`.

    def _unchanged(self, index: int, new: EvaluationStatus) -> bool:
        """The setter's guard: `not_evaluated` for an operation whose stored
        status is already `not_evaluated` writes nothing, so a repeated
        marking stores and logs nothing again."""
        return new is NOT_EVALUATED and self._last_evaluation_statuses[index] is NOT_EVALUATED

    def _slots_written_by(self, operation: Any) -> Sequence[Isar_State_Slot]:
        """The further slots the operation writes besides its resulting
        state (MODULE_STRUCTURE §4.1, "States"): slots of the class's own,
        which it mints in `gen` and `from_store` and appends in
        `_states_inside`.  The framework releases them with the operation's
        result.  `operation` is what `on_invalidated` is told.  None by
        default."""
        return ()

    def _release(self, ev: Evaluation, index: int, slot: Isar_State_Slot) -> None:
        """Operation `index` went from written to unwritten: `slot`, its
        resulting state, is released, and with it the further slots the
        class says the operation wrote."""
        ev.release(slot)
        for further in self._slots_written_by(self._operation_names()[index]):
            ev.release(further)

    def _written(self, ev: Evaluation, index: int, old: EvaluationStatus,
                 duration: float | None) -> None:
        """What every setter ends on, the instant status of operation `index`
        assigned (COMPILATION.md §4): the stored entry, the seen set's key
        of the operation's messages, the walk's store, and the `operation`
        record (LOGGING.md §4) — `duration` is how long the evaluation hook
        ran, None when no run produced the write; and last, both fields
        written, `on_invalidated` when the instant status, `old` before the
        write, left `Ready`."""
        new = self._own_statuses()[index]
        self._last_evaluation_statuses[index] = new
        operation = self._operation_names()[index]
        forest = self.forest()
        forest.conversation.forget((self.identity, operation))
        ev.stored.add(self)
        kind, messages = _status_to_store(new)
        forest.conversation.log.evaluation.operation(
            node=forest.full_id(self), operation=operation or "own", ran=duration is not None,
            status=kind, messages=messages if duration is not None else None, duration=duration)
        if isinstance(old, Ready) and not isinstance(new, Ready):
            _completed(self.on_invalidated, operation)

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

    def _is_under(self, ancestor: Node) -> bool:
        """Whether `ancestor` is one of this node's ancestors — strictly:
        no node is under itself."""
        n = self.parent
        while n is not None:
            if n is ancestor:
                return True
            n = n.parent
        return False

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

    @final
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
        default `mark` read; the three base classes answer, no class of
        its own (PLUGIN_SYSTEM §5)."""

    @abstractmethod
    def _operation_names(self) -> list[Any]:
        """The name of each own operation, in `_own_statuses()`'s order —
        what `on_invalidated` is told and the seen set's keys carry
        (PRINT.md §4)."""

    @final
    def _operations_ready(self) -> bool:
        """Whether every operation of this node — not its subtree — is
        `Ready`."""
        return all(isinstance(s, Ready) for s in self._own_statuses())

    # --- Rendering (PRINT.md).  The framework writes the line, the
    # operations' messages and descends; a class writes its fields, and
    # may say more in `mark`.

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
        self._print_messages(below, out, mode, depth)
        for child, child_mode in self._children_to_print(mode, depth):
            child.print(below, out, child_mode, depth + 1)

    def print_fields(self, indent: int, out: TextIO, mode: PrintMode, depth: int) -> None:
        """The class's: its fields, one per line at `indent`, chosen by mode
        and depth (PRINT.md §3).  Nothing by default."""

    def _print_messages(self, indent: int, out: TextIO, mode: PrintMode, depth: int) -> None:
        """The framework's (PRINT.md §3): each own operation's messages, the
        block headed `Error:` under a `CannotEvaluate` and `Notice:` under
        a `Ready` — whole under `recall` below depth 2, once per run
        elsewhere (the seen set, §4), never in the briefing."""
        if mode is BRIEFING:
            return
        seen = self.forest().conversation.seen
        whole = mode is RECALL and depth < 2
        for operation, status in zip(self._operation_names(), self._own_statuses()):
            if isinstance(status, NotEvaluated) or not status.messages:
                continue
            key = (self.identity, operation)
            if whole or key not in seen:
                header = "Error:" if isinstance(status, CannotEvaluate) else "Notice:"
                for message in status.messages:
                    print_error(indent, out, message.unicode, header)
                seen.add(key)

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
        if any(isinstance(s, CannotEvaluate) for s in statuses):
            return "failed"
        if any(s is NOT_EVALUATED for s in statuses):
            return "not evaluated"
        return None

    def _children_to_print(self, mode: PrintMode, depth: int) -> list[tuple[Node, PrintMode]]:
        """The children `print` descends into and the mode each gets
        (PRINT.md §2's table); none for a leaf."""
        return []

    # --- Emission (COMPILATION.md §3): the two questions a compile asks of
    # a node.  A compile runs on a forest loaded from the database and
    # never evaluated, so both read only what is stored — authored fields,
    # the recorded fields the class stores, `last_evaluation_statuses()`;
    # never an instant status.

    def can_emit(self) -> bool:
        """Whether the node writes its text.  Default: every stored status
        is a `Ready`; a class narrows it with `super().can_emit() and …`,
        or replaces it."""
        return all(isinstance(s, Ready) for s in self._last_evaluation_statuses)

    @abstractmethod
    def emit(self, indent: int, out: TextIO) -> int:
        """Write the node at `indent`, whole lines each ending in a newline;
        return the indent in effect after it.  Called only on the nodes of
        a tree every node of which answered `can_emit`."""

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
    def _resulting_status(self) -> EvaluationStatus:
        """The status of the operation that writes `resulting_state()`.
        Framework-only: what a node class asks of another node is
        `is_finished()`."""

    def _states_inside(self, out: list[Isar_State_Slot] | None = None
                       ) -> list[Isar_State_Slot]:
        """Every state owned by this subtree, appended to `out`: `state` and,
        under a nesting node, its children's and the one after them.  The
        resulting state is not among them — it is the successor's — unless
        the node owns it, as a `Theory` does.  A class appends the further
        slots it owns; what is listed here is deleted with the node."""
        if out is None:
            out = []
        out.append(self.state)
        return out

    @abstractmethod
    async def _evaluate(self, ev: Evaluation, mode: Evaluating) -> EvaluationResult:
        """The evaluating recursion (ARCHITECTURE §3.5): run what is
        `not_evaluated`, and what the walk rewrote the input of, up to the
        destination or a stop.  A nesting node is reached at its ending, so
        its children come before it."""

    @abstractmethod
    def _invalidate(self, ev: Evaluation) -> None:
        """Invalidate the node whole (ARCHITECTURE §3.4): every operation of
        it and of its subtree written `not_evaluated` through the setters,
        which release, store and log onto `ev`.  Runs and awaits nothing."""

    def _mode_after(self, ev: Evaluation, stop: Node | None) -> Evaluating | None:
        """The mode after a node the walk reached: None at the destination
        and at a stop — nothing more runs in the tree; otherwise
        `Evaluating`.  The other answer of None is a nesting node's whose
        beginning failed with the destination under it
        (`StdBlock._evaluate`)."""
        if self is ev.destination or stop is not None:
            return None
        return Evaluating()

    def _reached(self, ev: Evaluation) -> EvaluationResult:
        """The walk reached the node, its last operation settled: the node
        joins `ev.passed`, and is the walk's stop when that operation is
        not `Ready` and `ignore_error` is unset."""
        ev.passed.append(self)
        stop = self if not isinstance(self._resulting_status(), Ready) and not ev.ignore_error else None
        return EvaluationResult(stop, self._mode_after(ev, stop))

    async def evaluate_to(self, ignore_error: bool) -> EvaluationResult:
        """The `evaluate_to` tool's entry: run up to and including this
        node.  Takes the forest's lock itself — an edit, whose tool entry
        already holds it, drives the walk through `Forest._run` instead
        (MODULE_STRUCTURE §4.1)."""
        forest = self.forest()
        async with forest.lock:
            return await forest._run(self, ignore_error)


class Leaf(Node):

    _status: EvaluationStatus

    def __init__(self, parent, state):
        super().__init__(parent, state)
        self._status = NOT_EVALUATED

    @final
    def _resulting_status(self):
        return self._status

    @final
    def _own_statuses(self):
        return [self._status]

    @final
    def _operation_names(self):
        return [None]

    def _set_status(self, ev: Evaluation, new: EvaluationStatus, duration: float | None) -> None:
        """The operation's one setter: the instant status and its stored
        entry (COMPILATION.md §4); `duration` as `_written` takes it."""
        if self._unchanged(0, new):
            return
        old = self._status
        if _wrote(old) and not _wrote(new):       # written -> unwritten; a rewrite releases nothing
            self._release(ev, 0, self.resulting_state())
        self._status = new
        self._written(ev, 0, old, duration)

    def _invalidate(self, ev):
        self._set_status(ev, NOT_EVALUATED, None)

    @abstractmethod
    async def _eval_opr(self) -> Ready | CannotEvaluate:
        """Run the node from `state` into `resulting_state()`.  Return the
        status the run leaves, carrying what it reported; on a
        `CannotEvaluate` the framework copies `state` into
        `resulting_state()`, which `ignore_error` will run from."""

    async def _evaluate(self, ev, mode):
        if not _wrote(self._status):              # a Ready operation, or an obstacle, is not rerun
            status, duration = await _timed(self._eval_opr())
            if isinstance(status, CannotEvaluate):
                await self.state.copy_to(self.resulting_state())
            self._set_status(ev, status, duration)
        return self._reached(ev)


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
        (MODULE_STRUCTURE §4.2 step 3).  An obstacle wrote too: it copied
        its input through, so whatever follows has something to run from
        (ARCHITECTURE §3.1).  A failed beginning writes nothing — at
        position 0 only `ready` counts."""
        if index > 0:
            return _wrote(self.sub_nodes[index - 1]._resulting_status())
        return isinstance(self._beginning_status(), Ready)

    # The one copy of ARCHITECTURE §3.4, seen from the parent: a node
    # arriving at a position takes the predecessor's result that already
    # sits there (`_source_before`), and a node leaving one carries it into
    # the successor's slot (`_carry_forward`).  A container whose children
    # are not chained overrides both to do nothing.

    def _source_before(self, index: int) -> Isar_State_Slot | None:
        """The slot holding the predecessor's result at position `index`, for
        a node arriving there to take — or None when nothing was written."""
        return self._state_at(index) if self._predecessor_wrote(index) else None

    async def _carry_forward(self, index: int, node: Node) -> None:
        """The source side of removing `node` from position `index`: the
        predecessor's result, which lived under `node.state`, carried into
        the successor's slot.  Nothing when the predecessor wrote nothing:
        then `node` wrote nothing either (ARCHITECTURE §3.4)."""
        if self._predecessor_wrote(index):
            await node.state.copy_to(self._state_at(index + 1))

    async def _evaluate_children(self, ev: Evaluation, mode: Evaluating) -> EvaluationResult:
        """The children in order, each under the mode the one before it
        answered.  A child answering no mode — the destination or a stop
        lies in it — ends the loop, its result returned as it is."""
        for child in self.sub_nodes:
            r = await child._evaluate(ev, mode)
            if r.mode is None:
                return r
            mode = r.mode
        return EvaluationResult(None, mode)


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

    @final
    def _resulting_status(self):
        return self.evaluation_status_ending

    def _beginning_status(self):
        return self.evaluation_status_beginning

    @final
    def _own_statuses(self):
        return [self.evaluation_status_beginning, self.evaluation_status_ending]

    @final
    def _operation_names(self):
        return ["beginning", "ending"]

    def _state_after_beginning(self) -> Isar_State_Slot:
        if self.sub_nodes:
            return self.sub_nodes[0].state
        return self._state_before_ending

    def _states_inside(self, out=None):
        out = super()._states_inside(out)
        out.append(self._state_before_ending)
        return out

    def _set_beginning(self, ev: Evaluation, new: EvaluationStatus, duration: float | None) -> None:
        """The beginning's one setter: the instant status and its stored
        entry (COMPILATION.md §4); `duration` as `_written` takes it."""
        if self._unchanged(0, new):
            return
        old = self.evaluation_status_beginning
        if isinstance(old, Ready) and not isinstance(new, Ready):   # written -> unwritten: a failed beginning writes nothing
            self._release(ev, 0, self._state_after_beginning())
        self.evaluation_status_beginning = new
        self._written(ev, 0, old, duration)

    def _set_ending(self, ev: Evaluation, new: EvaluationStatus, duration: float | None) -> None:
        """The ending's one setter: the instant status and its stored
        entry (COMPILATION.md §4); `duration` as `_written` takes it."""
        if self._unchanged(1, new):
            return
        old = self.evaluation_status_ending
        if _wrote(old) and not _wrote(new):       # written -> unwritten; a rewrite releases nothing
            self._release(ev, 1, self.resulting_state())
        self.evaluation_status_ending = new
        self._written(ev, 1, old, duration)

    def _invalidate(self, ev):
        self._set_beginning(ev, NOT_EVALUATED, None)
        for child in self.sub_nodes:
            child._invalidate(ev)
        self._set_ending(ev, NOT_EVALUATED, None)

    @abstractmethod
    async def _eval_beginning_opr(self) -> Ready | CannotEvaluate:
        """Run the opening from `state` into `_state_after_beginning()`.
        Return the status the run leaves, carrying what it reported.  On a
        `CannotEvaluate` the children cannot run; when the walk goes on
        after the block the framework copies `state` into
        `resulting_state()`, so the block's input stands as its result, and
        evaluation resumes after it — unless the destination lies under the
        block: then the tree's walk ends there (ARCHITECTURE §3.3)."""

    async def _eval_ending_opr(self) -> Ready | CannotEvaluate:
        """Run the closing from `_state_before_ending` into `resulting_state()`.
        Return the status the run leaves; on a `CannotEvaluate` the
        framework copies `_state_before_ending` into `resulting_state()`.
        Default: no closing command, the copy is the whole operation."""
        await self._state_before_ending.copy_to(self.resulting_state())
        return READY_CLEAN

    @final
    def emit(self, indent, out):
        """The framework's (COMPILATION.md §3): the beginning command, the
        children in order with one empty line between siblings, the ending
        command."""
        below = self.emit_beginning(indent, out)
        for i, child in enumerate(self.sub_nodes):
            if i:
                out.write("\n")
            below = child.emit(below, out)
        return self.emit_ending(indent, out)      # the block's own indent, not the last child's

    @abstractmethod
    def emit_beginning(self, indent: int, out: TextIO) -> int:
        """The beginning command at `indent`; returns the indent the
        children get."""

    def emit_ending(self, indent: int, out: TextIO) -> int:
        """The ending command at the block's own `indent`; returns the indent
        in effect after the block.  Default: no ending command, the indent
        unchanged — a class overrides it exactly when it overrides
        `_eval_ending_opr` (PLUGIN_SYSTEM §5)."""
        return indent

    async def _evaluate(self, ev, mode):
        if self.evaluation_status_beginning is NOT_EVALUATED:          # an obstacle is not rerun
            status, duration = await _timed(self._eval_beginning_opr())
            self._set_beginning(ev, status, duration)
        if isinstance(self.evaluation_status_beginning, CannotEvaluate):   # the children have no context
            for child in self.sub_nodes:
                child._invalidate(ev)
            if ev.destination is not None and ev.destination._is_under(self):
                # the tree's walk ends here: a stop to this call alone (ARCHITECTURE §3.3)
                return EvaluationResult(None if ev.ignore_error else self, None)
            # The input stands as the result; a standing copy is left alone.
            if not isinstance(self.evaluation_status_ending, Ready):
                await self.state.copy_to(self.resulting_state())
                self._set_ending(ev, READY_CLEAN, None)
            return self._reached(ev)

        r = await self._evaluate_children(ev, mode)
        if r.mode is None:                        # the destination or a stop lies under: nothing more runs
            return r
        if not _wrote(self.evaluation_status_ending):
            status, duration = await _timed(self._eval_ending_opr())
            if isinstance(status, CannotEvaluate):
                await self._state_before_ending.copy_to(self.resulting_state())
            self._set_ending(ev, status, duration)
        return self._reached(ev)


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

    @final
    def _resulting_status(self):
        return NOT_EVALUATED                     # no operation: nothing written

    @final
    def _own_statuses(self):
        return []                                # no operation: nothing owed

    @final
    def _operation_names(self):
        return []

    def _predecessor_wrote(self, index) -> bool:
        return False                             # no child writes another's input

    def _source_before(self, index) -> Isar_State_Slot | None:
        return None                              # no predecessor's result to take

    async def _carry_forward(self, index, node):
        pass                                     # nor to carry

    def _invalidate(self, ev):
        for child in self.sub_nodes:             # no operation of its own
            child._invalidate(ev)

    def emit(self, indent, out):
        raise TAT_InternalError(
            f"{type(self).__name__} emits no Isar: a compile writes the trees under it")


# ---------------------------------------------------------------------------
# The shared types of the node class contract (MODULE_STRUCTURE §4.1), and
# the firing of a completed hook

# The JSON object the agent submitted.  `kind` and `children` belong to the
# framework; the other fields are the node class's own.
RawAST = Mapping[str, Any]


@dataclass(frozen=True)
class Insertion:
    """The batch joins `parent`'s children and none of them leaves:
    `append`, `insert_before`, `insert_after`, and every construct's
    `children`, an amend's included."""


@dataclass(frozen=True)
class Amendment:
    """`amend`: `old`, one of `parent`'s children, leaves the forest with
    the call — every construct of the batch leaves it out of whatever it
    looks up among the forest's nodes, uniqueness and existence alike;
    never mutate it.  The batch's first construct takes its place, the
    rest follow it."""
    old: Node


Role: TypeAlias = Insertion | Amendment


def _leaving(role: Role) -> Node | None:
    """The node the call takes out of the forest, if any."""
    return role.old if isinstance(role, Amendment) else None


class NodeConfig(NamedTuple):
    state: Isar_State_Slot   # the state before the node.  A name: the slot
                             # may hold nothing, and gen neither reads nor
                             # writes through it — only evaluation hooks may
                             # assume a slot holds a state
    parent: NonLeaf_Node     # never None: the forest root is not made this
                             # way.  Its sub_nodes are the children before
                             # the call; during an edit the parent may itself
                             # be a node not yet in the forest
    batch_before: tuple[Node, ...]
                             # the batch's constructs built before this one,
                             # in submission order.  Built, not placed:
                             # fields, kind and identity set, `parent` the
                             # one their gen was given, but not among its
                             # children and not in the forest — read their
                             # fields; never resolve, print or walk up from
                             # them
    role: Role               # what the call does to `parent`'s children

    def replaces(self) -> Node | None:
        """The node this construct takes the place of: an amendment's `old`
        for the batch's first construct, else None.  Read it to carry over
        recorded fields the class judges still valid."""
        return _leaving(self.role) if not self.batch_before else None


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
    """What one conversation, or one compile, is given and the forest does
    not store (ARCHITECTURE §1, §9; MODULE_STRUCTURE §4.1): the connection
    to the Isabelle side, the working directory (ARCHITECTURE §4), the log
    (LOGGING.md) and the ending object (MODULE_STRUCTURE §4.6); the bound
    on the construction jobs running at once, None for none
    (node_classes/THEOREM.md §7); and, until the agents hold their own, the
    seen set (PRINT.md §4) — what a class has shown the agent once, under
    keys of the class's choosing; cleared whole when the agent's context is
    replaced.  A node reaches it through `forest().conversation`."""
    connection: Connection
    working_directory: Path
    log: Log
    ending: Ending
    max_concurrent_construction_jobs: int | None = None
    seen: set[Any] = field(default_factory=set)

    def forget(self, key: Any) -> None:
        """Remove a key from the seen set: the status setter's, at every
        write of the operation the key names (COMPILATION.md §4)."""
        self.seen.discard(key)


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
        super().__init__(None, Isar_State_Slot.assign(conversation), [])
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
    # rebuilds one (the plan's §2).  `_store_written` is the one writer,
    # in one transaction: a walk's at each tree's end and when it ends, an
    # edit's in its commit.

    def _in_forest(self, node: Node) -> bool:
        """Whether the node's parent chain reaches this root."""
        return node is self or node._is_under(self)

    def _store_node(self, node: Node) -> None:
        """Rewrite one node's rows, inside an open transaction: `kind`, a
        nesting node's `children`, the stored statuses, then what the class
        writes; of the root, its `children` row alone.  A node that is not
        in the forest is refused (MODULE_STRUCTURE §4.2)."""
        if node is self:
            self._store_children(self)
            return
        if not self._in_forest(node):
            raise TAT_InternalError(
                f"{type(node).__name__} `{getattr(node, 'name', '?')}` is not in the forest:"
                " its rows cannot be stored")
        self.store.delete_node(node.identity)
        self.store.put(node.identity, "kind", node.kind)
        if isinstance(node, NonLeaf_Node):
            self._store_children(node)
        self.store.put(node.identity, "last_evaluation_statuses",
                       [_status_to_store(s) for s in node._last_evaluation_statuses])
        node.to_store(self.store.rows(node.identity))

    def _store_written(self, ev: Evaluation, changed: Sequence[Node] = (),
                       deleted: Sequence[Node] = ()) -> None:
        """The one store of a walk's stretch or of an edit's commit
        (COMPILATION.md §4, MODULE_STRUCTURE §4.2): every node whose status
        `ev` wrote, and each node of `changed` that is still in the forest,
        whole and once, the rows of `deleted` removed first — one
        transaction with nothing awaited inside, none when there is nothing
        to write.  A status written on a node outside the forest is refused
        before the transaction opens."""
        for node in ev.stored:
            if not self._in_forest(node):
                raise TAT_InternalError(
                    f"a status was written on {type(node).__name__}"
                    f" `{getattr(node, 'name', '?')}`, which is not in the forest")
        nodes = list(ev.stored)
        nodes += [n for n in dict.fromkeys(changed) if n not in ev.stored and self._in_forest(n)]
        if nodes or deleted:
            with self.store.transaction():
                for node in deleted:
                    self.store.delete_node(node.identity)
                for node in nodes:
                    self._store_node(node)
        ev.stored.clear()

    def _restore_statuses(self, node: Node, identity: int) -> None:
        """The `last_evaluation_statuses` row (COMPILATION.md §4): a missing
        row, or one not of the node's number of operations, reads as the
        constructor's list; a row that is not a list of statuses is
        refused."""
        row = self.store.fields(identity).get("last_evaluation_statuses")
        if row is None:
            return
        statuses = [_status_from_store(v) for v in row] if isinstance(row, list) else [None]
        if any(s is None for s in statuses):
            raise TAT_StartupError(
                f"the forest database's `last_evaluation_statuses` row of node {identity}"
                " is not a list of statuses")
        if len(statuses) == len(node._last_evaluation_statuses):
            node._last_evaluation_statuses = [s for s in statuses if s is not None]

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
        config = NodeConfig(state=Isar_State_Slot.assign(parent.state.conversation),
                            parent=parent, batch_before=(), role=Insertion())
        node = cls.from_store(config, self.store.rows(identity))
        if isinstance(node, NonLeaf_Node) and node.sub_nodes:
            raise TAT_InternalError(
                f"{cls.__name__}.from_store returned children; the framework loads them")
        node.parent = parent                   # the framework owns placement
        node.kind = kind
        node.identity = identity
        self._restore_statuses(node, identity)
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
                if self.full_id(n) == id:
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

    def full_id(self, node: Node) -> Id:
        """The full id (MCP_SPECIFICATION §2): the components of the node's
        ancestors and its own, dotted; `Sessions` for the root.  Linear in
        the node's depth, so the one the log's records use."""
        if node is self:
            return "Sessions"
        return ".".join(c.id_component() for c in self._chain(node))

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

    async def _run(self, destination: Node, ignore_error: bool, checks: str = "no"
                   ) -> EvaluationResult:
        """The evaluating walk up to and including `destination`, under the
        lock, already held; it makes the walk's `Evaluation`.  Each tree
        stores and flushes at its end (`_handle_tree`), and the walk once
        more when it ends.  A `TAT_Error` escaping the walk comes from an
        evaluation hook and is its class's bug, so that none is rendered to
        the agent; anything else passes as it is (EXCEPTIONS.md §1)."""
        assert self.lock.locked(), "a walk runs under the forest lock"
        ev = Evaluation(destination, ignore_error, checks)
        log = self.conversation.log.evaluation
        log.walk_started(destination=self.full_id(destination),
                         ignore_error=ignore_error, checks=checks)
        started = time.monotonic()
        try:
            r = await self._evaluate(ev, Evaluating())
        except TAT_Error as e:
            raise TAT_InternalError("an evaluation hook raised a TAT_Error") from e
        self._store_written(ev)
        await ev.flush(self.conversation)
        log.walk_ended(outcome="continue" if r.stopped_at is None else self.full_id(r.stopped_at),
                       slots_released=ev.releases, duration=time.monotonic() - started)
        return r

    def _invalidate_from(self, position: Location, ev: Evaluation) -> None:
        """Invalidate from `position` to the end of its tree (ARCHITECTURE
        §3.4, §3.5): the siblings from that index, each whole, then the
        parent's ending, then the parent's later siblings, and so on up to
        the tree's `end`; the index after the last child is the parent's
        ending.  Nothing under a `Session` or the root, where sibling trees
        are independent — what an edit there disturbed is
        `_invalidate_changed_trees`'.  Runs and awaits nothing."""
        parent, index = position.parent, position.index
        while isinstance(parent, StdBlock):
            for child in parent.sub_nodes[index:]:
                child._invalidate(ev)
            parent._set_ending(ev, NOT_EVALUATED, None)
            index, parent = parent.index_of() + 1, parent.parent

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
        misplaced = self._misplaced_imports(node)
        return misplaced[0][0] if misplaced else None

    def _misplaced_imports(self, tree: Theory, table: dict[str, Theory] | None = None
                           ) -> list[tuple[str, Theory]]:
        """The order constraint's position test, which the walk and the
        compile share (COMPILATION.md §2): the `imports` items of `tree`
        whose forest tree does not lie strictly earlier in tree order, each
        with that tree, in the items' order."""
        trees = self._trees()
        if table is None:
            table = {t.qualified_name(): t for t in trees}
        position = trees.index(tree)
        out: list[tuple[str, Theory]] = []
        for item in tree.imports:
            target = self._import_of(tree, item, table)
            if target is not None and trees.index(target) >= position:
                out.append((item, target))
        return out

    async def _evaluate_tree(self, ev: Evaluation, tree: Node) -> Node | None:
        """The run of one tree and its one `_invalidate_from`
        (MODULE_STRUCTURE §4.1): after the stop the run ended at — after the
        destination instead when that stop is a nesting node above it whose
        beginning failed; else after the destination, when it lies in the
        tree; not at all for a tree run to its own `end`.  Returns the
        stop."""
        destination = ev.destination
        assert destination is not None                    # an evaluating walk has one (`_run`)
        stop = (await tree._evaluate(ev, Evaluating())).stopped_at
        after = destination if stop is None or destination._is_under(stop) else stop
        if self._tree_of(after) is tree:
            assert after.parent is not None               # a node of a tree
            self._invalidate_from(Location(after.parent, after.index_of() + 1), ev)
        return stop

    async def _handle_tree(self, ev: Evaluation, tree: Theory) -> Node | None:
        """One tree of an evaluating walk, and its stop, if any, by the
        first case that applies: the order constraint's stop, the stop
        crossing an import dependency, the run (MODULE_STRUCTURE §4.1;
        ARCHITECTURE §3.3).  Under either stop the tree is not run but
        invalidated whole.  The walk's store and flush at the tree's end
        are here, so a slot released for one tree is gone before a later
        tree of the walk could write it."""
        if self._order_violation(tree) is not None:
            tree._invalidate(ev)
            stop: Node | None = tree                      # reported whatever ignore_error says
            reason = "order_constraint"
        else:
            # both operations: after a failed header the ending is ready with no theory value
            missing = next((i for i in self._resolved_imports(tree)
                            if not i._operations_ready()), None)
            if missing is not None:
                tree._invalidate(ev)
                stop = None if ev.ignore_error else missing
                reason = "import_without_theory"
            else:
                stop = await self._evaluate_tree(ev, tree)
                reason = "command_failed"
        if stop is not None:                              # the one place a stop is recorded (LOGGING.md §4)
            self.conversation.log.evaluation.stopped(
                node=self.full_id(stop), reason=reason,
                tree=self.full_id(tree) if reason == "import_without_theory" else None)
        self._store_written(ev)
        await ev.flush(self.conversation)
        return stop

    async def _evaluate(self, ev, mode):
        """The forest's part of the recursion (ARCHITECTURE §3.5), which
        works on the trees directly: the closure of the trees the
        destination stands for, in tree order, each by `_handle_tree` — a
        tree reaching the second case there has every resolved import
        earlier in tree order and already handled, so its statuses are
        current.  The result names the first stop in tree order
        (MCP_SPECIFICATION §4)."""
        assert ev.destination is not None                 # an evaluating walk has one (`_run`)
        stopped_at: Node | None = None
        for tree in self._closure(self._trees_under(ev.destination)):
            stop = await self._handle_tree(ev, tree)
            if stopped_at is None:
                stopped_at = stop
        return EvaluationResult(stopped_at, None)

    # --- what an edit compares (ARCHITECTURE §3.4)

    def _record(self) -> Tree_Records:
        """Every tree's `TreeRecord`, by identity."""
        table = self._name_table()
        return {t.identity: TreeRecord(t.qualified_name(),
                                       frozenset(self._resolved_imports(t, table)))
                for t in self._trees()}

    def _invalidate_changed_trees(self, ev: Evaluation, before: Tree_Records
                                  ) -> tuple[list[Theory], list[str]]:
        """Inside an edit's commit, against the record taken at its start:
        every tree present in both whose record changed — its `Session`
        renamed, itself renamed, moved into another `Session`, a tree it
        imports vanished, appeared or replaced by an `amend`, or a name it
        imports now naming another tree — is invalidated whole, its ending
        then carrying the rule of `Theory._set_ending` onward.  Returns
        those trees, for the edit's `committed` record, and every qualified
        name present before and absent after, sorted, which the edit
        removes from the ML theory table after its commit
        (EVALUATOR_DESIGN §3)."""
        after = self._record()
        changed = [t for t in self._trees()
                   if t.identity in before and before[t.identity] != after[t.identity]]
        for tree in changed:
            tree._invalidate(ev)
        kept = {record.qualified_name for record in after.values()}
        vanished = sorted(record.qualified_name for record in before.values()
                          if record.qualified_name not in kept)
        return changed, vanished


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


# A `Session`'s folder, `Session.folder()` under the working directory
# (COMPILATION.md §2): a compile writes the session's files into it, and a
# theory's header is evaluated under it.  The two functions answer a
# reason, and each caller puts its own opening before it (COMPILATION.md
# §7).

def session_folder_refusal(working_directory: Path, folder: Path) -> str | None:
    """Why the path cannot be a session's folder, or None: the folder is a
    directory or absent."""
    try:
        mode = os.lstat(working_directory / folder).st_mode
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(mode):
        return f"{folder}/ is a symbolic link; a session's folder must be a directory or absent"
    if not stat.S_ISDIR(mode):
        return f"{folder}/ is not a directory; a session's folder must be a directory or absent"
    return None


def make_session_folder(working_directory: Path, folder: Path) -> str | None:
    """Make a `Session`'s folder when it is absent.  Answers None, or the
    reason it cannot be made: `session_folder_refusal`'s, or the system's."""
    reason = session_folder_refusal(working_directory, folder)
    if reason is None:
        try:
            (working_directory / folder).mkdir(exist_ok=True)
        except OSError as e:
            reason = f"{folder}/ cannot be made: {e.strerror}"
    return reason


class CannotUseWorkingDirectory(TAT_StartupError):
    """A `Session`'s folder cannot be made when a theory of it begins
    (MODULE_STRUCTURE §4.1): the working directory's structure is TAT's
    alone, nothing an agent can do repairs it, and the conversation ends."""


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


def _option_value(option: Session_Option) -> str:
    """An option's value as Isabelle is to read it: what the agent
    supplied, less the double quotes it may have come in
    (SESSION_AND_THEORY §1).  The one reading: creation's check sends it,
    and the ROOT carries it."""
    value = option["value"]
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


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
    # Names compared without regard to case (SESSION_AND_THEORY §1), the
    # refusal the id component's: on a file system that does not
    # distinguish case, two such sessions would share one folder.
    namespace = Namespace("session names",
                          lambda name, holder: DuplicateName(f"session_{name}", holder))

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
        name = raw["name"]
        if not is_valid_session_name(name):
            raise InvalidName(name, "session name")
        if name.upper() == "ROOT":          # the session's folder would be the ROOT file's path
            raise ReservedSessionName(name)
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
        # What only Isabelle can say, in one round trip that answers the
        # first defect, after every check that costs none: the name
        # reserved, the name one the Isabelle session layout knows, an
        # option refused, the parent unknown.  The parent is judged last
        # (SESSION_AND_THEORY §1), and Isabelle is not asked about it in
        # two cases: a session the call keeps in the forest or adds before
        # this one bears its name; or it is the session's own name, so
        # that "must not name the session itself", below, is not hidden
        # behind "must name an existing session".
        parent_session = raw["parent_session"]
        sessions = [s for s in (*config.parent.sub_nodes, *config.batch_before)
                    if isinstance(s, Session) and s is not _leaving(config.role)]
        settled = parent_session == name or any(s.name == parent_session for s in sessions)
        match await isabelle_driver.check_session(
                config.parent.conversation, name, None if settled else parent_session,
                [(option["name"], _option_value(option)) for option in options]):
            case isabelle_driver.Name_Reserved():
                raise ReservedSessionName(name)
            case isabelle_driver.Name_Known():
                raise InvalidField(
                    "name", f"must not be the name of an existing Isabelle session; `{name}` is one")
            case isabelle_driver.Option_Refused(i, message):
                raise InvalidField(f"options[{i}]",                 # one line: the agent's sentence is one
                                   f"is not accepted by Isabelle: {' '.join(message.splitlines())}")
            case isabelle_driver.Parent_Unknown():
                raise InvalidField("parent_session",
                                   f"must name an existing session; `{parent_session}` is not one")
            case isabelle_driver.Session_Ok():
                pass
        if parent_session == name:
            raise InvalidField("parent_session", "must not name the session itself")
        return cls(config.parent, config.state, name, parent_session,
                   list(options), raw.get("description", ""))

    def on_moving(self, new_location):
        if not isinstance(new_location.parent, Forest):
            raise BadSessionNodeParent(self.kind, self.forest().id_of(new_location.parent))

    def folder(self) -> Path:
        """The session's folder, relative to the working directory: its
        name (COMPILATION.md §2).  The one place that says so — its trees'
        files, the folder made for them and the ROOT's `in` path follow."""
        return Path(self.name)

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
                print_error(indent, out, self.description, "description:")

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
    import_sessions: list[str]          # recorded when the header runs: the session of each
                                        # import, which the ROOT's `sessions` clause is written
                                        # from (COMPILATION.md §2); stored
    _state_after_ending: Isar_State_Slot    # the resulting slot: owned, since no successor's
                                            # input is (`Unchained_Node`); nothing reads it

    def __init__(self, parent, state, name: str, imports: list[str],
                 state_before_ending: Isar_State_Slot, state_after_ending: Isar_State_Slot):
        super().__init__(parent, state, [], state_before_ending)
        self.name = name
        self.imports = imports
        self.import_sessions = []
        self._state_after_ending = state_after_ending

    @classmethod
    async def gen(cls, config, raw: Theory_RawAST):
        if not isinstance(config.parent, Session):
            raise BadTheoryNodeParent(raw["kind"], _parent_id(config))
        name = raw["name"]
        if not _THEORY_NAME.fullmatch(name):
            raise InvalidName(name, "theory name")
        # The Isabelle half of the short-name check; the forest half is the
        # framework's, through `namespace` (the plan's §3).
        conversation = config.parent.forest().conversation
        match await isabelle_driver.check_new_theory_short_name(conversation, name):
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
                   Isar_State_Slot.assign(conversation), Isar_State_Slot.assign(conversation))

    def on_moving(self, new_location):
        if not isinstance(new_location.parent, Session):
            raise BadTheoryNodeParent(self.kind, self.forest().id_of(new_location.parent))

    def to_store(self, rows):
        rows.put("name", self.name)
        rows.put("imports", self.imports)
        rows.put("import_sessions", self.import_sessions)

    @classmethod
    def from_store(cls, config, rows):
        conversation = config.parent.forest().conversation
        node = cls(config.parent, config.state, rows.get("name"), rows.get("imports"),
                   Isar_State_Slot.assign(conversation), Isar_State_Slot.assign(conversation))
        # a missing row reads as the empty list (COMPILATION.md §4, "Storage")
        node.import_sessions = rows.fields().get("import_sessions", [])
        return node

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

    def file_path(self) -> Path:
        """The tree's file, `<Session name>/<short name>.thy`, relative to
        the working directory (COMPILATION.md §2): what a compile writes,
        and its folder the `master_dir` the header is evaluated under."""
        return self.session().folder() / f"{self.name}.thy"

    def header(self) -> str:
        """The `theory … begin` span, as the tree's file will open; every
        import quoted, so a hyphenated name is one token to Isabelle's
        lexer."""
        imports = " ".join(f'"{item}"' for item in self.imports)
        return f"theory {self.name}\n  imports {imports}\nbegin"

    def emit_beginning(self, indent, out):
        """The header, the one `_eval_beginning_opr` runs."""
        _emit_lines(indent, out, self.header())
        return indent

    def emit_ending(self, indent, out):
        _emit_lines(indent, out, "end")
        return indent

    def _set_ending(self, ev, new, duration):
        """ARCHITECTURE §3.4's rule, a property of the stored status: whenever
        a stored `Ready` ending is replaced by a value that is not a `Ready`,
        the tree's direct importers are invalidated whole under the same
        `Evaluation`, each ending so moved firing the same rule for its own
        importers.  The assignment comes first, so within one cascade no
        ending leaves `Ready` twice, cycles included: a tree importing
        itself re-enters its own invalidation, and the inner call finds the
        ending already `not_evaluated`."""
        old = self._last_evaluation_statuses[1]
        super()._set_ending(ev, new, duration)
        if isinstance(old, Ready) and not isinstance(new, Ready):
            for importer in self.forest()._importers(self):
                importer._invalidate(ev)

    def print_fields(self, indent, out, mode, depth):
        """SESSION_AND_THEORY §4: `imports` in the briefing, when detailed
        and at `recall`'s depth 2.  The operations' messages are the
        framework's (PRINT.md §3)."""
        if mode is BRIEFING or self.detailed(mode, depth) or (mode is RECALL and depth == 2):
            out.write(INDENT * indent + f"imports: {' '.join(self.imports)}\n")

    # The two callbacks are `TAT_Common_Nodes.ML`'s; each answers the
    # operation's errors, empty when it passed (ARCHITECTURE §6.2) — the
    # beginning's also the session of each import, recorded when it passed
    # — and whatever it lets escape is a bug (`isabelle_driver.call`).  The
    # status the run leaves carries the errors (COMPILATION.md §4); a
    # rendering inside the call — a `recall` takes no lock — reads the
    # previous run's.

    async def _eval_beginning_opr(self):
        session = self.session()
        conversation = self.forest().conversation
        # The session's folder, before the header runs: AoA's proof store
        # beside the tree's file needs a directory to be written in.
        reason = make_session_folder(conversation.working_directory, session.folder())
        if reason is not None:
            raise CannotUseWorkingDirectory(
                f"TAT cannot use {conversation.working_directory} as its working directory:"
                f" {reason}")
        errors, import_sessions = await isabelle_driver.call(
            conversation, "TAT.Theory.begin",
            (self._state_after_beginning().to_msgpack(),
             (session.name,
              str(conversation.working_directory / self.file_path().parent),   # the `master_dir`
              self.header())))
        if not errors:
            self.import_sessions = import_sessions          # stored with the status this run leaves
        return _status_of_errors(errors)

    async def _eval_ending_opr(self):
        conversation = self.forest().conversation
        errors = await isabelle_driver.call(
            conversation, "TAT.Theory.end",
            (self._state_before_ending.to_msgpack(), self._state_after_ending.to_msgpack()))
        return _status_of_errors(errors)


def _status_of_errors(errors: list[str]) -> Ready | CannotEvaluate:
    """The status a callback's answer leaves: the errors it reported, in
    Isabelle's spelling, or a clean `Ready`."""
    if errors:
        return CannotEvaluate(tuple(IsaTerm.from_isabelle(e) for e in errors))
    return READY_CLEAN


FRAMEWORK_NODE_CLASSES: list[type[Node]] = [Session, Theory]
