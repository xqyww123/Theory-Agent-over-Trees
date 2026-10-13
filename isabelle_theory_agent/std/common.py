"""What the classes of the plugin `Isabelle_Std` share
(node_classes/COMMON.md): `Theory_Member`, the base every class derives
from, with the plugin's one parent exception `NotInsideTheory` (§1), and
the package's compile hook for AoA's proof stores (§3; COMPILATION.md
§5)."""

from __future__ import annotations

import re

from ..compile import identity, paths
from ..exceptions import BadEdit
from ..model import Forest, Location, Node, NodeConfig, Theory
from ..plugin import TAT_compile_hook


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
