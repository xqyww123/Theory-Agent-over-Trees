"""The invariants every edit path and every walk maintains, checked against
the fake state slot table of `test_model.py` and the forest's real store
(not a pytest module).

- Release: a slot holds a value iff the operation that writes it is still
  current — `ready`, or an own stop, which copied its input through; a
  beginning writes only when `ready` (ARCHITECTURE §3.1, §3.4).  Under an
  unchained container nobody writes a child's input, and a child owning
  its resulting slot (a `Theory`) holds a value there exactly when its
  ending really wrote one — not after a failed beginning, whose
  copy-through copied an input holding nothing (the plan's §6).
- Provenance: every operation still `ready` consumed exactly what its input
  slot holds now (MCP_SPECIFICATION §3.2's "invalidates … unconditionally").
  Judged on the recording fakes of `test_model.py`, which remember it.
- Mirror: the store loads back as this forest — same nodes in the same
  order with the same identities, kinds, names and fields — and holds no
  row of a node that has left (the plan's §2).
- The theory table, two one-way statements over the fake one of
  `test_model.py`, which the fakes' endings write: every tree answering
  `_operations_ready()` has its qualified name in the table, and every
  name in the table is the qualified name of a current tree.  Neither
  converse holds — an entry stays after the tree is invalidated, and a
  failed header leaves the ending `ready` with no value (EVALUATOR_DESIGN
  §3).
- A tree one of whose resolved imports does not answer
  `_operations_ready()` is `not_evaluated` throughout: the premise the
  `Theory` ending's rule rests on (ARCHITECTURE §3.4), since a tree runs
  only after its imports have their theory value, and is invalidated
  whole the moment one of them loses it.
"""

import isabelle_theory_agent.model as M
from isabelle_theory_agent.exceptions import TAT_InternalError
from isabelle_theory_agent.model import NOT_EVALUATED, StdBlock
from test_model import CANNOT_EVALUATE, NOT_RUN, READY, Block, CONN, T, shape


def _current(status, beginning=False):
    if beginning:
        return isinstance(status, M.Ready)
    return M._wrote(status)


def _chained(parent):
    """Whether the container chains its children: it keeps a slot after
    them; an unchained one refuses to name it (the plan's §6)."""
    try:
        parent._resulting_state_of_all_children()
    except TAT_InternalError:
        return False
    return True


def assert_invariants(forest, table):
    values = table.values
    for parent in [forest] + [n for n in forest._all_nodes()
                              if isinstance(n, M.NonLeaf_Node)]:
        if not _chained(parent):
            for child in parent.sub_nodes:
                assert child.state.name not in values, f"{child}: input written by nobody"
                if isinstance(child, StdBlock):
                    wrote = (_current(child.evaluation_status_ending)
                             and not isinstance(child.evaluation_status_beginning, M.CannotEvaluate))
                    held = child.resulting_state().name in values
                    assert held == wrote, f"{child}: result held={held}, ending wrote={wrote}"
            continue
        for i, child in enumerate(parent.sub_nodes):
            if i == 0:
                written = isinstance(parent, StdBlock) and _current(
                    parent.evaluation_status_beginning, beginning=True)
            else:
                written = _current(parent.sub_nodes[i - 1]._resulting_status())
            assert (child.state.name in values) == written, \
                f"{child}: input held={child.state.name in values}, writer current={written}"
        slot = parent._resulting_state_of_all_children()
        if parent.sub_nodes:
            written = _current(parent.sub_nodes[-1]._resulting_status())
        else:
            written = isinstance(parent, StdBlock) and _current(
                parent.evaluation_status_beginning, beginning=True)
        assert (slot.name in values) == written, \
            f"{parent}: after-children slot held={slot.name in values}, writer current={written}"
    for node in forest._all_nodes():
        if isinstance(node, T) and node._status is READY:
            assert values.get(node.state.name) == node.consumed, \
                f"{node}: ready, consumed {node.consumed!r}, input now {values.get(node.state.name)!r}"
        if isinstance(node, T) and node._status is CANNOT_EVALUATE:
            # its copy-through stands, and still matches its input where that is current
            assert values.get(node.resulting_state().name) == node.copied, \
                f"{node}: own stop, copied {node.copied!r}, result now {values.get(node.resulting_state().name)!r}"
            if node.state.name in values:
                assert values[node.state.name] == node.copied, \
                    f"{node}: own stop copied {node.copied!r}, input now {values[node.state.name]!r}"
        if isinstance(node, Block) and node.evaluation_status_ending is CANNOT_EVALUATE:
            assert values.get(node.resulting_state().name) == node.copied_end, \
                f"{node}: ending own stop, copied {node.copied_end!r}"
        if isinstance(node, Block):
            if node.evaluation_status_beginning is READY:
                assert values.get(node.state.name) == node.consumed_begin, \
                    f"{node}: beginning ready, consumed {node.consumed_begin!r}"
            if node.evaluation_status_ending is READY:
                if node.consumed_end is NOT_RUN:   # the failed opening's copy-through
                    assert node.evaluation_status_beginning is CANNOT_EVALUATE, \
                        f"{node}: ending ready without a run, yet the beginning stands"
                    assert (values.get(node.resulting_state().name)
                            == values.get(node.state.name)), \
                        f"{node}: the input no longer stands as the result"
                else:
                    assert values.get(node._state_before_ending.name) == node.consumed_end, \
                        f"{node}: ending ready, consumed {node.consumed_end!r}"
    trees = forest._trees()
    for tree in trees:
        if tree._operations_ready():
            assert tree.qualified_name() in table.theories, \
                f"{tree}: ready, but the theory table lacks {tree.qualified_name()}"
        if not all(i._operations_ready() for i in forest._resolved_imports(tree)):
            assert all(s is NOT_EVALUATED for n in tree._tree_order() for s in n._own_statuses()), \
                f"{tree}: an import has no theory value, yet it holds a status"
    assert table.theories <= {t.qualified_name() for t in trees}, \
        f"the theory table names no current tree: {table.theories}"
    # At rest the stored status equals the instant one wherever the instant
    # one is not `not_evaluated` (COMPILATION.md §4).
    for node in forest._all_nodes():
        for instant, stored in zip(node._own_statuses(), node.last_evaluation_statuses()):
            if instant is not NOT_EVALUATED:
                assert instant == stored, f"{node}: instant {instant!r}, stored {stored!r}"


def assert_store_mirrors(forest, kinds, shape=shape):
    """The same store, loaded again by the forest's own class, has the
    `shape` of this forest — what a round trip must preserve, node by node
    in tree order."""
    store = forest.store
    live = {n.identity for n in forest._all_nodes()}
    assert set(store.nodes()) - {forest.identity} == live, "rows of nodes not in the forest"
    assert set(store.fields(forest.identity)) <= {"children"}, "the root has one row"
    twin = type(forest)(CONN, store, kinds)
    assert shape(twin) == shape(forest)
    for n in twin._all_nodes():
        assert n.parent is not None and n in n.parent.sub_nodes
