"""The two invariants every edit path and every walk maintains, checked
against the fake state slot table of `test_model.py` (not a pytest module).

- Release: a slot holds a value iff the operation that writes it is still
  current — `ready`, or an own stop, which copied its input through; a
  beginning writes only when `ready` (ARCHITECTURE §3.1, §3.4).
- Provenance: every operation still `ready` consumed exactly what its input
  slot holds now (MCP_SPECIFICATION §3.2's "invalidates … unconditionally").
"""

import isabelle_theory_agent.model as M
from isabelle_theory_agent.model import READY, StdBlock, Leaf
from test_model import NOT_RUN


def _current(status, beginning=False):
    if beginning:
        return status is READY
    return status is READY or M._is_own_stop(status)


def assert_invariants(forest, table):
    values = table.values
    for parent in [forest] + [n for n in forest._all_nodes()
                              if isinstance(n, M.NonLeaf_Node)]:
        chained = parent is not forest
        for i, child in enumerate(parent.sub_nodes):
            if not chained:            # trees are not chained; nothing writes their input
                assert child.state.name not in values, f"{child}: input written by nobody"
                continue
            if i == 0:
                written = isinstance(parent, StdBlock) and _current(
                    parent.evaluation_status_beginning, beginning=True)
            else:
                written = _current(parent.sub_nodes[i - 1]._last_status())
            assert (child.state.name in values) == written, \
                f"{child}: input held={child.state.name in values}, writer current={written}"
        slot = parent._resulting_state_of_all_children()
        if parent.sub_nodes:
            written = _current(parent.sub_nodes[-1]._last_status())
        else:
            written = chained and isinstance(parent, StdBlock) and _current(
                parent.evaluation_status_beginning, beginning=True)
        assert (slot.name in values) == written, \
            f"{parent}: after-children slot held={slot.name in values}, writer current={written}"
    for node in forest._all_nodes():
        if isinstance(node, Leaf) and node._status is READY:
            assert values.get(node.state.name) == node.consumed, \
                f"{node}: ready, consumed {node.consumed!r}, input now {values.get(node.state.name)!r}"
        if isinstance(node, Leaf) and M._is_own_stop(node._status):
            # its copy-through stands, and still matches its input where that is current
            assert values.get(node.resulting_state().name) == node.copied, \
                f"{node}: own stop, copied {node.copied!r}, result now {values.get(node.resulting_state().name)!r}"
            if node.state.name in values:
                assert values[node.state.name] == node.copied, \
                    f"{node}: own stop copied {node.copied!r}, input now {values[node.state.name]!r}"
        if isinstance(node, StdBlock) and M._is_own_stop(node.evaluation_status_ending):
            assert values.get(node.resulting_state().name) == node.copied_end, \
                f"{node}: ending own stop, copied {node.copied_end!r}"
        if isinstance(node, StdBlock):
            if node.evaluation_status_beginning is READY:
                assert values.get(node.state.name) == node.consumed_begin, \
                    f"{node}: beginning ready, consumed {node.consumed_begin!r}"
            if node.evaluation_status_ending is READY:
                if node.consumed_end is NOT_RUN:   # the failed opening's copy-through
                    assert M._is_own_stop(node.evaluation_status_beginning), \
                        f"{node}: ending ready without a run, yet the beginning stands"
                    assert (values.get(node.resulting_state().name)
                            == values.get(node.state.name)), \
                        f"{node}: the input no longer stands as the result"
                else:
                    assert values.get(node._state_before_ending.name) == node.consumed_end, \
                        f"{node}: ending ready, consumed {node.consumed_end!r}"
