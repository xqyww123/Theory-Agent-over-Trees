"""Writing the forest (COMPILATION.md §2, §5): what `edit.py` is to changing
the forest, this is to writing it — one `.thy` per tree that may be
written and a ROOT with one entry per `Session`, under the working
directory.

Two steps.  `render` is a function of the stored forest alone and touches
no disk: it decides each tree, and renders every written tree's text and
the ROOT's.  `compile` then does the disk, ending on the ROOT, the one mark
that a compile finished.  Synchronous, no round trip, and under no lock of
the forest's: the caller holds the working directory's lock on a `Forest`
of its own with no server.
"""

from __future__ import annotations

import io
import os
import stat
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NamedTuple

from Isabelle_RPC_Host.unicode import ascii_of_unicode

from .exceptions import TAT_InternalError, TAT_StartupError
from .model import (
    INDENT, CannotEvaluate, EvaluationStatus, Forest, Node, NotEvaluated, Ready, Session,
    StdBlock, Theory, _indented, _option_value, cartouche, make_session_folder, session_folder_refusal,
    string_token)


# ---------------------------------------------------------------------------
# The report

@dataclass(frozen=True)
class Does_Not_Emit:
    node: Node                    # chosen as COMPILATION.md §2 says


@dataclass(frozen=True)
class Import_Not_Written:
    tree: Theory                  # the first forest tree it imports, placed before it, that is not written


@dataclass(frozen=True)
class Order_Constraint:
    tree: Theory                  # the forest tree it imports that is placed after it, or itself


Reason = Does_Not_Emit | Import_Not_Written | Order_Constraint


class Entry(NamedTuple):
    """One entry under the working directory, as `paths` yields it."""
    path: Path                    # relative to the working directory
    kind: Literal["file", "folder", "link"]      # as `lstat` reads it


@dataclass(frozen=True)
class Compile_Report:
    trees: tuple[tuple[Theory, Reason | None], ...]   # tree order; None: written
    removed: tuple[Entry, ...]    # removed and not written again, a folder after what it held


# ---------------------------------------------------------------------------
# The first step: the stored forest alone

@dataclass(frozen=True)
class Rendering:
    """What `render` answers: each tree's decision, every written tree's
    text by its file path, and the ROOT's text — both texts in Isabelle's
    `\\<name>` form."""
    trees: tuple[tuple[Theory, Reason | None], ...]
    files: dict[Path, str]
    root: str


def render(forest: Forest) -> Rendering:
    """Compile's first step (COMPILATION.md §5): decide each tree by §2's
    rule, render every written tree's text and the ROOT's in memory, and
    convert each once.  It reads only what is stored, so the store-mirror
    helper holds a loaded forest to the same answer."""
    trees = forest.trees()
    table = forest._name_table()
    written = _decide(forest, trees, table)
    decided = tuple((tree, None if written[tree] else _reason(forest, tree, written, table))
                    for tree in trees)
    files: dict[Path, str] = {}
    for tree in trees:
        if written[tree]:
            out = io.StringIO()
            tree.emit(0, out)
            files[tree.file_path()] = ascii_of_unicode(out.getvalue())
    return Rendering(decided, files, ascii_of_unicode(_root(forest, written)))


def _decide(forest: Forest, trees: list[Theory], table: dict[str, Theory]) -> dict[Theory, bool]:
    """Which trees are written: every node agrees to emit, and every forest
    tree it imports is written — a memoised recursion over the resolved
    imports, since an import may stand after its importer.  A tree reached
    again while its own decision is being made lies on an import cycle and
    is not written."""
    decided: dict[Theory, bool] = {}
    deciding: set[Theory] = set()

    def written(tree: Theory) -> bool:
        if tree in decided:
            return decided[tree]
        if tree in deciding:
            return False
        deciding.add(tree)
        answer = (all(node.can_emit() for node in tree._tree_order())
                  and all([written(i) for i in forest._resolved_imports(tree, table)]))
        deciding.discard(tree)
        decided[tree] = answer
        return answer

    return {tree: written(tree) for tree in trees}


def _reason(forest: Forest, tree: Theory, written: dict[Theory, bool],
            table: dict[str, Theory]) -> Reason:
    """Why a tree is not written: the first of COMPILATION.md §2's four
    that holds."""
    misplaced = [target for _, target in forest._misplaced_imports(tree, table)]
    for imported in forest._resolved_imports(tree, table):            # 1
        if imported not in misplaced and not written[imported]:
            return Import_Not_Written(imported)
    refusing = _refusing(tree, [])
    for node, status in refusing:                                      # 2
        if not isinstance(status, NotEvaluated):
            return Does_Not_Emit(node)
    if misplaced:                                                      # 3
        return Order_Constraint(next((t for t in misplaced if not written[t]), misplaced[0]))
    for node, status in refusing:                                      # 4
        return Does_Not_Emit(node)
    raise TAT_InternalError(f"{tree.qualified_name()} is not written, for no reason")


def _placed(node: Node) -> EvaluationStatus | None:
    """The stored status of the operation a refusing node is placed at
    (COMPILATION.md §2): its first that is not a `Ready`, or its last when
    all are; None for a node that has none."""
    stored = node.last_evaluation_statuses()
    return next((s for s in stored if not isinstance(s, Ready)), stored[-1] if stored else None)


def _refusing(node: Node, out: list[tuple[Node, EvaluationStatus | None]]
              ) -> list[tuple[Node, EvaluationStatus | None]]:
    """The nodes of a subtree whose `can_emit` is false, each with the
    stored status of the operation it is placed at, in the order the walk
    runs operations: a nesting node whose beginning did not pass is met at
    its beginning, before its children, and otherwise at its ending, after
    them."""
    stored = node.last_evaluation_statuses()
    placed = _placed(node)
    refuses = not node.can_emit()
    if not isinstance(node, StdBlock):
        if refuses:
            out.append((node, placed))
        return out
    at_its_beginning = not isinstance(stored[0], Ready)
    if refuses and at_its_beginning:
        out.append((node, placed))
    for child in node.sub_nodes:
        _refusing(child, out)
    if refuses and not at_its_beginning:
        out.append((node, placed))
    return out


def _root(forest: Forest, written: dict[Theory, bool]) -> str:
    """The ROOT's text (COMPILATION.md §2): one entry per `Session`, in the
    forest's order, the clauses in the order Isabelle's grammar fixes."""
    entries = []
    for session in forest.sub_nodes:
        if not isinstance(session, Session):
            continue
        lines = [f"session {string_token(session.name)} in {string_token(str(session.folder()))}"
                 f" = {string_token(session.parent_session)} +"]
        if session.description:
            lines.append(f"{INDENT}description {cartouche(session.description)}")
        if session.options:
            options = ", ".join(f"{string_token(o['name'])} = {string_token(_option_value(o))}"
                                for o in session.options)
            lines.append(f"{INDENT}options [{options}]")
        theories = [t for t in session.sub_nodes if isinstance(t, Theory) and written[t]]
        # the exclusion is made here: an amend of `parent_session` invalidates no tree
        sessions = sorted({s for t in theories for s in t.import_sessions}
                          - {session.name, session.parent_session})
        for clause, names in (("sessions", sessions), ("theories", [t.name for t in theories])):
            if names:
                lines.append(INDENT + clause)
                lines.extend(INDENT * 2 + string_token(n) for n in names)
        entries.append("".join(line + "\n" for line in lines))
    return "\n".join(entries)


# ---------------------------------------------------------------------------
# The second step: the disk

def paths(working_directory: Path) -> Iterator[Entry]:
    """Every entry under the working directory, relative to it, with its
    kind as `lstat` reads it (COMPILATION.md §5): a link is yielded and not
    entered, a folder whose name begins with a dot is neither yielded nor
    entered, and a folder comes after what it holds.  Everything a compile
    removes, a hook's removals included, it finds here."""
    def under(folder: Path, relative: Path) -> Iterator[Entry]:
        for name in sorted(os.listdir(folder)):
            mode = os.lstat(folder / name).st_mode
            if stat.S_ISLNK(mode):
                yield Entry(relative / name, "link")
            elif stat.S_ISDIR(mode):
                if not name.startswith("."):
                    yield from under(folder / name, relative / name)
                    yield Entry(relative / name, "folder")
            else:
                yield Entry(relative / name, "file")
    yield from under(working_directory, Path())


def _create(path: Path, text: str) -> None:
    """Create a file afresh, so that nothing still at the path, a link
    included, is written through."""
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666), "w",
                   encoding="utf-8", newline="\n") as file:
        file.write(text)


def identity(path: Path) -> tuple[int, int]:
    """What the file system says a path is, so that a folder is known for
    a `Session`'s whatever spelling its name has on disk; a compile hook
    knows a tree's folder the same way."""
    status = os.lstat(path)
    return status.st_dev, status.st_ino


def _is_folder(path: Path) -> bool:
    try:
        return stat.S_ISDIR(os.lstat(path).st_mode)
    except FileNotFoundError:
        return False


ROOT = Path("ROOT")
ROOT_SIBLING = Path("ROOT.new.thy")   # the ROOT's temporary sibling; the next compile's `.thy` removal takes one left behind


def compile(forest: Forest, hooks: Sequence[Callable[[Forest], None]]) -> Compile_Report:
    """Write the forest under its working directory and answer the report
    (COMPILATION.md §5).  Refused before anything is removed
    (`TAT_StartupError`): a `Session` folder's path holding anything but a
    directory, and a folder at a path the compile will create; a failure
    after that leaves no ROOT, which Isabelle refuses."""
    rendering = render(forest)
    directory = forest.conversation.working_directory
    folders = [s.folder() for s in forest.sub_nodes if isinstance(s, Session)]
    for folder in folders:
        reason = session_folder_refusal(directory, folder)
        if reason is not None:
            raise TAT_StartupError(f"TAT cannot compile into {directory}: {reason}")
    for path in (*rendering.files, ROOT, ROOT_SIBLING):
        if _is_folder(directory / path):
            raise TAT_StartupError(
                f"TAT cannot compile into {directory}: {path}/ is a folder; compile writes a file there")
    before = list(paths(directory))
    (directory / ROOT).unlink(missing_ok=True)
    for entry in before:                                  # every `.thy`, a link included
        if entry.path.name.endswith(".thy") and entry.kind != "folder":
            (directory / entry.path).unlink()
    for folder in folders:
        reason = make_session_folder(directory, folder)
        if reason is not None:                            # the system's refusal: a bug midway
            raise OSError(f"TAT cannot compile into {directory}: {reason}")
    made = {identity(directory / folder) for folder in folders}
    for path, text in rendering.files.items():
        _create(directory / path, text)
    for hook in hooks:
        hook(forest)
    for entry in list(paths(directory)):                  # each folder after what it holds
        if (entry.kind == "folder" and identity(directory / entry.path) not in made
                and not os.listdir(directory / entry.path)):
            (directory / entry.path).rmdir()
    # The ROOT last, through its sibling: Isabelle accepts a ROOT cut off
    # between two entries.
    _create(directory / ROOT_SIBLING, rendering.root)
    os.replace(directory / ROOT_SIBLING, directory / ROOT)
    after = {entry.path for entry in paths(directory)}
    return Compile_Report(rendering.trees,
                          tuple(entry for entry in before if entry.path not in after))


def report_lines(report: Compile_Report) -> list[str]:
    """The report as COMPILATION.md §2's lines: one per tree in tree
    order, with the messages of the operation that refused; the ROOT's;
    one per entry removed and not written again."""
    lines: list[str] = []
    for tree, reason in report.trees:
        forest = tree.forest()
        line = f"{tree.file_path()} "
        messages: tuple[str, ...] = ()
        match reason:
            case None:
                line += "written"
            case Import_Not_Written(imported):
                line += f"not written: it imports {imported.qualified_name()}, which is not written"
            case Order_Constraint(imported) if imported is tree:
                line += "not written: it imports itself"
            case Order_Constraint(imported):
                line += (f"not written: it imports {imported.qualified_name()},"
                         " which is placed after it")
            case Does_Not_Emit(node):
                placed = _placed(node)
                if isinstance(placed, CannotEvaluate):
                    what, messages = "failed", tuple(m.unicode for m in placed.messages)
                elif isinstance(placed, NotEvaluated):
                    what = "is not evaluated"
                else:
                    what = "does not emit"
                line += f"not written: {forest.id_of(node)} {what}"
        lines.append(line)
        for message in messages:
            lines.extend(_indented(1, message.rstrip("\n")))
    lines.append("ROOT written")
    for entry in report.removed:
        lines.append(f"removed {_spelled(entry.path)}" + ("/" if entry.kind == "folder" else ""))
    return lines


def _spelled(path: Path) -> str:
    """A path as the report spells it.  A name that is not valid UTF-8
    comes from the listing with lone surrogates, which no line that
    travels can hold: each is written as its `\\udXXX` escape, as the log
    writes one (LOGGING.md §5)."""
    return str(path).encode("utf-8", "backslashreplace").decode("utf-8")
