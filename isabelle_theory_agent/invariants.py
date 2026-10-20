"""The store-mirror invariant (COMPILATION.md §3): what a compile reads is
what the database holds.  A helper for test suites — TAT's own and every
node class's, each on its own forests — that takes the forest and
nothing class-specific: the twin is loaded with the forest's own kind
table.

A compile runs on a forest loaded from the database and never evaluated,
so `can_emit`, `emit` and a compile hook may read only what is stored.  A
class that reads an instant status there, or a recorded field it does not
store, answers differently on the loaded forest, and fails here at once.
"""

from __future__ import annotations

from .compile import Compile_Report, render, report_lines
from .model import Forest, _status_to_store


def assert_store_mirrors(forest: Forest) -> None:
    """Reload the forest from its store beside the one in memory and
    require, node by node, the same stored statuses in their stored form
    and the same `can_emit`; and of the two forests the same result of
    compile's first step as text — every file's text by its path, the
    ROOT's, and the report's lines.  Raises `AssertionError`, naming the
    first difference."""
    twin = Forest(forest.conversation, forest.store, forest.kinds, forest.imports)
    mine, loaded = forest._all_nodes(), twin._all_nodes()
    _require([n.identity for n in loaded] == [n.identity for n in mine],
             "the database's nodes are not the forest's, in its order")
    for node, other in zip(mine, loaded):
        name = forest.full_id(node)
        stored = [_status_to_store(s) for s in node.last_evaluation_statuses()]
        read = [_status_to_store(s) for s in other.last_evaluation_statuses()]
        _require(read == stored, f"{name}: stored statuses {stored}, the database's {read}")
        _require(other.can_emit() == node.can_emit(),
                 f"{name}: can_emit is {node.can_emit()}, and {other.can_emit()} once loaded")
    here, there = render(forest), render(twin)
    for path in sorted({*here.files, *there.files}):
        _require(there.files.get(path) == here.files.get(path),
                 f"{path}: the loaded forest writes another text")
    _require(there.root == here.root, "ROOT: the loaded forest writes another text")
    lines, other_lines = (report_lines(Compile_Report(r.trees, ())) for r in (here, there))
    _require(other_lines == lines, f"the report: {lines}, and {other_lines} once loaded")


def _require(holds: bool, message: str) -> None:
    if not holds:
        raise AssertionError(message)
