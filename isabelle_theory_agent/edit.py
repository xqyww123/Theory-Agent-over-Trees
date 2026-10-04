"""Editing the forest (MODULE_STRUCTURE §4.2): building nodes from the
agent's constructs, and the four entries behind the `edit`, `move` and
`delete` tools — `insert`, `amend`, `delete`, `move`.

Every entry assumes the forest's lock held by the tool entry.  Each takes
the trees' record first (`Forest._record`), builds and checks everything
before it touches the forest, so an aborted call needs no undoing.  Its
commit (MODULE_STRUCTURE §4.2 step 3) is the copies of ARCHITECTURE §3.4,
round trips, and then one synchronous block with nothing awaited inside:
the pointer surgery; the invalidation from each position whose input the
edit changed (`Forest._invalidate_from`) and of each tree whose record
changed (`Forest._invalidate_changed_trees`, ARCHITECTURE §3.4); the
completed events; the one store (`_store_transaction`).  After the block
come the round trips (`_after_commit`).  Whether to also evaluate is the
caller's, from the call's `evaluate` flag.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from . import isabelle_driver
from .exceptions import (
    BadEdit, ChildrenNotInheritable, DuplicateName, InvalidField, InvalidName,
    MalformedRawAST, MoveIntoOwnSubtree, TAT_Error, TAT_InternalError,
    UnexpectedChildren, UnknownKind)
from .model import (
    Amendment, Evaluation, Forest, Insertion, Isar_State_Slot, Leaf, Location, Node,
    NodeConfig, NonLeaf_Node, RawAST, Role, _completed, _leaving, _wrote, is_valid_name)
from .plugin import check_construct


def _gate(hook, *args) -> None:
    """Fire a progressive hook: `BadEdit` vetoes the call; anything else it
    raises is the class's bug (MODULE_STRUCTURE §4.1).  Its twin for the
    completed hooks, `_completed`, lives in `model.py`: the setters fire
    `on_invalidated` through it."""
    try:
        hook(*args)
    except BadEdit:
        raise
    except TAT_Error as e:
        raise TAT_InternalError(f"gate {hook.__qualname__} raised") from e


def _fire(fired: list[Node], hook, *args) -> None:
    """Fire a completed hook of a commit and remember the node it fired on:
    what the hook changed on it is stored with the edit
    (MODULE_STRUCTURE §4.1, "Events")."""
    _completed(hook, *args)
    fired.append(hook.__self__)


def _store_transaction(forest: Forest, ev: Evaluation,
                       operation: Literal["insert", "amend", "delete", "move"],
                       location: Location, *, changed: Sequence[Node],
                       deleted: Sequence[Node] = (), created: Sequence[Node] = (),
                       removed: Sequence[str] = (), moved: Sequence[Node] = (),
                       invalidated: Sequence[Node] = ()) -> None:
    """The end of a commit's synchronous block (MODULE_STRUCTURE §4.2 step
    3): the edit's one store — the `created` nodes, every node whose status
    the commit wrote, those of `changed` still in the forest, and the rows
    of `deleted` removed — then its `committed` record (LOGGING.md §4);
    `removed` are ids, taken while the nodes still stood."""
    forest._store_written(ev, [*created, *changed], deleted)
    forest.conversation.log.edit.committed(
        operation=operation, parent=forest.full_id(location.parent), index=location.index,
        created=[[forest.full_id(n), n.kind] for n in created], removed=list(removed),
        moved=[forest.full_id(n) for n in moved], invalidated=[forest.full_id(t) for t in invalidated])


async def _after_commit(forest: Forest, ev: Evaluation, vanished: list[str]) -> None:
    """The round trips after a commit's block (MODULE_STRUCTURE §4.2 step
    4): the qualified names that vanished leave the ML theory table, and
    the released slots are deleted."""
    if vanished:
        await isabelle_driver.theory_delete(forest.conversation, vanished)
    await ev.flush(forest.conversation)


# ---------------------------------------------------------------------------
# The four entries

async def insert(parent: NonLeaf_Node, index: int, raws: list[RawAST],
                 kinds: Mapping[str, type[Node]]) -> list[Node]:
    """`append`/`insert_before`/`insert_after`: construct the batch detached
    — `gen` is insertion's gate, there is no other — and commit it before
    position `index` of `parent`: invalidate, fire the completed events,
    store.  Returns the batch; its last element is the natural destination
    (MCP_SPECIFICATION §3.2)."""
    forest = parent.forest()
    before = forest._record()
    nodes = await _construct_siblings(parent, raws, "constructs", Edit_Call(forest, kinds),
                                      Insertion())
    # Commit: first the one copy of ARCHITECTURE §3.4 into the first new
    # node's slot — only when the predecessor operation wrote it, judged
    # with no round trip; every other new slot stays empty, as befits
    # `not_evaluated` nodes.  The value moves with the position: the slot
    # it came from, now written by the last new node, is released.
    ev = Evaluation(None, False)
    source = parent._source_before(index)
    if source is not None:
        await source.copy_to(nodes[0].state)
        ev.release(source)
    # The synchronous block.
    location = Location(parent, index)
    for node in nodes:
        node.parent = parent
    parent.sub_nodes[index:index] = nodes
    forest._invalidate_from(location, ev)
    invalidated, vanished = forest._invalidate_changed_trees(ev, before)
    fired: list[Node] = []
    created = [n for root in nodes for n in root._tree_order()]   # tree order over what entered
    for n in created:
        assert n.parent is not None
        _fire(fired, n.parent.on_added_child, n, "insert_or_delete")
        _fire(fired, n.on_inserted)
    _store_transaction(forest, ev, "insert", location, changed=fired, created=created,
                       invalidated=invalidated)
    await _after_commit(forest, ev, vanished)
    return nodes


async def amend(old: Node, raws: list[RawAST],
                kinds: Mapping[str, type[Node]]) -> list[Node]:
    """`amend`: `nodes[0]` is built as the replacement (`NodeConfig.replaces`)
    and takes `old`'s position, state slot, identity number and children;
    `nodes[1:]` follow it."""
    parent = parent_of(old)
    forest = parent.forest()
    before = forest._record()
    removed = [forest.full_id(old)]
    call = Edit_Call(forest, kinds, Amendment(old))
    nodes = await _construct_siblings(parent, raws, "constructs", call, call.role)
    replacement = nodes[0]
    inherited = list(old.sub_nodes) if isinstance(old, NonLeaf_Node) else []
    # Gates.
    _gate(old.on_deleting, "amend")
    _gate(parent.on_removing_child, old, "amend")
    for child in inherited:
        assert isinstance(old, NonLeaf_Node)
        _gate(old.on_removing_child, child, "inheritance")
        _gate(child.on_inheriting, replacement)
    # Commit.  Released, in one round trip with the invalidation's: `old`'s
    # slots not travelling to the replacement or the inherited children,
    # and the values `old`'s own operations wrote into travelling slots —
    # its result in the successor's input, a beginning's output in the
    # first child's input — all stale under the replacement.
    ev = Evaluation(None, False)
    travelling = {old.state.name} | {
        s.name for c in inherited for s in c._states_inside()}
    for s in old._states_inside():
        if s.name not in travelling:
            ev.release(s)
    if _wrote(old._resulting_status()):
        ev.release(old.resulting_state())
    beginning_wrote = old._source_before(0) if isinstance(old, NonLeaf_Node) else None
    if beginning_wrote is not None:
        ev.release(beginning_wrote)
    # The synchronous block.
    index = old.index_of()
    location = Location(parent, index)
    replacement.state = old.state          # its identity is already old's (_construct_element)
    if inherited:
        assert isinstance(old, NonLeaf_Node) and isinstance(replacement, NonLeaf_Node)
        replacement.sub_nodes[:] = inherited
        old.sub_nodes = []
        for child in inherited:
            child.parent = replacement
    old.parent = None
    replacement.parent = parent
    parent.sub_nodes[index] = replacement
    for node in nodes[1:]:
        node.parent = parent
    parent.sub_nodes[index + 1:index + 1] = nodes[1:]
    # A replacement that inherited children invalidates from its first
    # child: the children come before its own ending in the walk
    # (ARCHITECTURE §3.5), and under a `Session` its own position marks
    # nothing.
    if inherited:
        assert isinstance(replacement, NonLeaf_Node)
        forest._invalidate_from(Location(replacement, 0), ev)
    else:
        forest._invalidate_from(location, ev)
    invalidated, vanished = forest._invalidate_changed_trees(ev, before)
    # Completed events (MODULE_STRUCTURE §4.1's order).
    fired: list[Node] = []
    _fire(fired, old.on_deleted, "amend")
    for child in inherited:
        assert isinstance(replacement, NonLeaf_Node)
        _fire(fired, child.on_inherited, old)
        _fire(fired, replacement.on_added_child, child, "inheritance")
    _fire(fired, parent.on_added_child, replacement, "amend")
    _fire(fired, replacement.on_inserted)
    followers = [n for root in nodes[1:] for n in root._tree_order()]
    for n in followers:
        assert n.parent is not None
        _fire(fired, n.parent.on_added_child, n, "insert_or_delete")
        _fire(fired, n.on_inserted)
    # The replacement's rows replace `old`'s: one identity, nothing deleted.
    _store_transaction(forest, ev, "amend", location, changed=fired,
                       created=[replacement, *followers], removed=removed,
                       invalidated=invalidated)
    await _after_commit(forest, ev, vanished)
    return nodes


async def delete(node: Node) -> NonLeaf_Node:
    """`delete`: remove `node` with its subtree and invalidate from its
    successor on.  The predecessor's result, which lived under
    `node.state`, is copied under the state now at that position.
    Returns the parent it left, which the quickview focuses on
    (PRINT.md §5)."""
    parent = parent_of(node)
    forest = parent.forest()
    before = forest._record()
    for n in node._children_first():
        _gate(n.on_deleting, "delete")
    _gate(parent.on_removing_child, node, "insert_or_delete")
    index = node.index_of()
    location = Location(parent, index)
    subtree = node._tree_order()
    removed = [forest.full_id(n) for n in subtree]
    ev = Evaluation(None, False)
    await parent._carry_forward(index, node)       # the one copy, before any pointer moves
    for s in node._states_inside():   # released with the invalidation's: one round trip
        ev.release(s)
    # The synchronous block.
    del parent.sub_nodes[index]
    node.parent = None
    forest._invalidate_from(location, ev)
    invalidated, vanished = forest._invalidate_changed_trees(ev, before)
    fired: list[Node] = []
    for n in node._children_first():
        _fire(fired, n.on_deleted, "delete")
    # the parent: its `children` row changed, and no completed hook fires on it
    _store_transaction(forest, ev, "delete", location, changed=[*fired, parent],
                       deleted=subtree, removed=removed, invalidated=invalidated)
    await _after_commit(forest, ev, vanished)
    return parent


async def move(node: Node, new_parent: NonLeaf_Node, new_index: int) -> None:
    """`move`: re-home `node` with its subtree — a copy on the source side
    and one on the destination side; the subtree's slots travel with their
    nodes, none is deleted (ARCHITECTURE §3.4).  `new_index` is the
    position in `new_parent.sub_nodes` after the removal."""
    parent = parent_of(node)
    forest = parent.forest()
    before = forest._record()
    if new_parent is node or new_parent._is_under(node):
        raise MoveIntoOwnSubtree(forest.id_of(node), forest.id_of(new_parent))
    for c in new_parent.sub_nodes:
        if c is not node and c.id_component() == node.id_component():
            raise DuplicateName(node.id_component(), forest.id_of(c))
    limit = len(new_parent.sub_nodes) - (1 if new_parent is parent else 0)
    if not 0 <= new_index <= limit:
        raise TAT_InternalError(
            f"move destination index {new_index} out of range")
    old_index = node.index_of()
    old_location = Location(parent, old_index)
    new_location = Location(new_parent, new_index)
    _gate(node.on_moving, new_location)
    _gate(parent.on_removing_child, node, "move")
    # Judge the destination side against the post-removal shape, with no
    # await in between: remove, look, put back.
    del parent.sub_nodes[old_index]
    successor = (parent.sub_nodes[old_index]
                 if old_index < len(parent.sub_nodes) else None)
    destination_source = new_parent._source_before(new_index)
    parent.sub_nodes.insert(old_index, node)
    # Commit: the two copies first, then the synchronous block.  The
    # source-side copy carries the predecessor's result forward; the
    # destination side gives `node` its new input — the value moves with
    # the position, so the slot it came from is released — or, when nothing
    # was written there, releases the stale old input, which its
    # still-current writer never would.  (Two remote copies: a failure
    # between them leaves the forest untouched but the slot table
    # half-moved.)
    ev = Evaluation(None, False)
    await parent._carry_forward(old_index, node)
    if destination_source is not None:
        await destination_source.copy_to(node.state)
        ev.release(destination_source)
    else:
        ev.release(node.state)
    # The synchronous block.
    del parent.sub_nodes[old_index]
    node.parent = new_parent
    new_parent.sub_nodes.insert(new_index, node)
    # Both positions whose input the move changed: the source successor's
    # as it now is — the parent's ending when the node was last — and the
    # moved node's, which takes its whole subtree.
    source_position = (Location(parent, successor.index_of()) if successor
                       else Location(parent, len(parent.sub_nodes)))
    forest._invalidate_from(source_position, ev)
    forest._invalidate_from(new_location, ev)
    invalidated, vanished = forest._invalidate_changed_trees(ev, before)
    fired: list[Node] = []
    _fire(fired, new_parent.on_added_child, node, "move")
    _fire(fired, node.on_moved, old_location)
    # the old parent: its `children` row changed, and no completed hook fires on it
    _store_transaction(forest, ev, "move", new_location, changed=[*fired, parent],
                       moved=[node], invalidated=invalidated)
    await _after_commit(forest, ev, vanished)


def parent_of(node: Node) -> NonLeaf_Node:
    """The parent of a node an entry acts on; the root has none — it
    anchors only `into`, which `edit`'s `append` and `move`'s `into` both
    resolve to (MCP_SPECIFICATION §2, TOOL_SCHEMAS §1, §2)."""
    if node.parent is None:
        raise TAT_InternalError("the forest root has no parent")
    return node.parent


# ---------------------------------------------------------------------------
# Building nodes from constructs (MODULE_STRUCTURE §4.2, step 1)

@dataclass(frozen=True)
class Edit_Call:
    """What every construct built in one edit call shares."""
    forest: Forest
    kinds: Mapping[str, type[Node]]
    role: Role = Insertion()         # the call's: an amendment's `old` is left out
                                     # of every uniqueness check of the call
    taken: dict[str, dict[str, str]] = dataclasses.field(default_factory=dict)
                                     # the names the constructs built so far have
                                     # taken in each forest-wide namespace:
                                     # namespace name -> casefolded name -> the
                                     # construct's full path


def _holder_id(holder: Node | str, forest: Forest) -> str:
    """A taken name's holder as the agent sees it: a node's id, or the
    coordinate of the construct that took it earlier in this call."""
    return holder if isinstance(holder, str) else forest.id_of(holder)


def _take_name(node: Node, full_path: str, call: Edit_Call) -> None:
    """For a class with a `namespace`: refuse the node's name if a node of
    the forest (other than the one the call replaces) or an earlier
    construct of the call already bears it in that namespace, else record
    it for the rest of the call.  Names are compared without regard to
    case: Isabelle refuses two theory files whose names differ only in
    case (MODULE_STRUCTURE §4.2).  The forest's takers are found by
    walking it, never recorded
    (ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §3); `DuplicateName` among
    siblings is `_construct_siblings`' own `taken`."""
    namespace = type(node).namespace
    if namespace is None:
        return
    leaving = _leaving(call.role)
    name = node.name.casefold()
    for other in call.forest._all_nodes():
        theirs = type(other).namespace
        if (other is not leaving and other.name.casefold() == name
                and theirs is not None and theirs.name == namespace.name):
            raise namespace.duplicate(node.name, call.forest.id_of(other))
    taken = call.taken.setdefault(namespace.name, {})
    if name in taken:
        raise namespace.duplicate(node.name, taken[name])
    taken[name] = full_path


async def _construct_siblings(parent: NonLeaf_Node, raws: list[RawAST], listname: str,
                              call: Edit_Call, role: Role, path: str = "") -> list[Node]:
    """Step 1 of an edit: one batch, every construct in submission order,
    built under `role` — an amend's top-level batch under
    `Amendment(old)`, whose first element replaces it; every other batch
    under `Insertion` — and detached.  The framework checks the name the
    class set against the grammar and the id component against the
    siblings: `taken` maps each surviving sibling's id component to the
    node, each batch element's to its coordinate — printed only at the
    raise — so `DuplicateName` points either way.  A class with a
    `namespace` is then checked across the forest and the call
    (`_take_name`); that holder may sit in another batch of the call, so
    it is recorded under the element's full path — `path`, the enclosing
    construct's, plus the coordinate (RENDER_BASELINES §2).  The check
    comes after the sibling checks and after the element's children are
    built, so a class nesting its own namespace blames the enclosing
    construct.  The element's coordinate is prefixed onto an exception
    here, around everything done for it — the framework's own checks
    included (EXCEPTIONS.md §5)."""
    taken: dict[str, Node | str] = {c.id_component(): c for c in parent.sub_nodes
                                    if c is not _leaving(role)}
    nodes: list[Node] = []
    for i, raw in enumerate(raws):
        coordinate = f"{listname}[{i}]"
        full_path = f"{path}.{coordinate}" if path else coordinate
        try:
            node = await _construct_element(raw, parent, tuple(nodes), role, call, full_path)
            name = getattr(node, "name", None)
            if not isinstance(name, str):
                raise TAT_InternalError(
                    f"{type(node).__name__}.gen set no name")
            if not is_valid_name(name):
                raise InvalidName(name)
            component = node.id_component()
            if component in taken:
                raise DuplicateName(component, _holder_id(taken[component], call.forest))
            taken[component] = coordinate
            _take_name(node, full_path, call)
            nodes.append(node)
        except TAT_Error as e:
            e._prefix_raw_ast_path(coordinate)
            raise
    return nodes


async def _construct_element(raw: RawAST, parent: NonLeaf_Node, batch_before: tuple[Node, ...],
                             role: Role, call: Edit_Call, path: str) -> Node:
    forest, kinds = call.forest, call.kinds
    if not isinstance(raw, Mapping):
        raise MalformedRawAST(missing_kind=False)
    if "kind" not in raw:
        raise MalformedRawAST(missing_kind=True)
    kind = raw["kind"]
    if not isinstance(kind, str):
        raise InvalidField("kind", "must be a string")
    if kind not in kinds:
        raise UnknownKind(kind, list(kinds))
    cls = kinds[kind]
    config = NodeConfig(state=Isar_State_Slot.assign(parent.state.conversation),
                        parent=parent, batch_before=batch_before, role=role)
    replacing = config.replaces()
    # The children-legality checks run before any gen (MODULE_STRUCTURE
    # §4.2): a Leaf holds no children, an amend's replacement inherits them.
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
    check_construct(cls, kind, raw)
    node = await cls.gen(config, {k: v for k, v in raw.items()
                                  if k != "children"})
    if isinstance(node, NonLeaf_Node) and node.sub_nodes:
        raise TAT_InternalError(
            f"{cls.__name__}.gen returned children; the framework builds them")
    node.kind = kind
    # A replacement keeps the identity of what it replaces (MCP_SPECIFICATION
    # §3.1).  A fresh one is the store's own write, outside any transaction:
    # nothing of this edit is in one until its commit (the plan's §2).
    node.identity = (replacing.identity if replacing is not None
                     else forest.store.next_identity())
    if "children" in raw:
        if not isinstance(node, NonLeaf_Node):
            raise TAT_InternalError(
                f"{cls.__name__} took children but is no nesting class")
        children = await _construct_siblings(
            node, raw["children"], "children", call, Insertion(), path=path)
        for child in children:                # the framework owns placement
            child.parent = node
        node.sub_nodes.extend(children)
    return node
