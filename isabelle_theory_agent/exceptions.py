"""The `TAT_Error` hierarchy (EXCEPTIONS.md).

Every class carries its facts as fields; `__str__` assembles the agent-facing
sentence from them.  The approved wording lives in docs/RENDER_BASELINES.md,
and `test/test_exceptions.py` asserts it verbatim; no other test touches the
rendered strings.

Two fields on `TAT_Error` are written by the framework after the raise, never
by the raise site: `opr` with `target` at the tool entry (EXCEPTIONS.md §4),
and `raw_ast_path` by the per-element loops as the exception unwinds
(EXCEPTIONS.md §5).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod


class TAT_Error(Exception, ABC):
    """An error the agent can act on: raised anywhere, caught only at the
    tool boundary, rendered into the tool result (EXCEPTIONS.md §1)."""

    # The refused forest-changing operation and its target, echoed from the
    # call (EXCEPTIONS.md §4).  Written once by `_set_operation`; both stay
    # None for tools that do not change the forest.
    opr: str | None = None
    target: str | None = None

    # Which element of the submitted `nodes` list, e.g. "nodes[2].children[0]"
    # (EXCEPTIONS.md §5).  Accumulated by `_prefix_raw_ast_path`.
    raw_ast_path: str | None = None

    def __init__(self) -> None:
        # BaseException.__new__ skips ABC's instantiation check, so a group
        # base would instantiate; refuse it here.
        if type(self).__abstractmethods__:
            raise TypeError(
                f"abstract class {type(self).__name__} cannot be raised")
        super().__init__()

    def _set_operation(self, opr: str, target: str) -> None:
        """Framework-only, at the tool entry.  `opr` is one of the six
        operation names of TOOL_SCHEMAS.md §5; `target` is the operation's
        target echoed from the call — for `move` including the destination
        phrase, e.g. "theory_Sorting to before theory_X.lemma_P"."""
        if self.opr is not None or opr not in _OPERATIONS:
            raise TAT_InternalError(f"operation {opr!r} onto {self.opr!r}")
        self.opr = opr
        self.target = target

    def _prefix_raw_ast_path(self, step: str) -> None:
        """Framework-only, on the unwind path.  `step` is the raising
        element's coordinate in the loop's own list — "nodes[2]" at the top
        level, "children[0]" nested."""
        self.raw_ast_path = (
            step if self.raw_ast_path is None
            else f"{step}.{self.raw_ast_path}")

    @abstractmethod
    def _cause(self) -> str:
        """The cause sentence(s), without opening line or path prefix."""

    def __str__(self) -> str:
        cause = self._cause()
        if self.raw_ast_path is not None:
            cause = f"At `{self.raw_ast_path}`: {cause}"
        if self.opr is None:
            return cause
        return f"Cannot {self.opr} {self.target}\n{cause}"


class TAT_InternalError(Exception):
    """A bug: an invariant TAT itself broke.  Deliberately outside
    `TAT_Error`, so the tool boundary never catches it (EXCEPTIONS.md §1)."""


# The six forest-changing operations (TOOL_SCHEMAS.md §5).
_OPERATIONS = frozenset(
    {"append", "insert_before", "amend", "move", "delete", "new_session"})


# ---------------------------------------------------------------------------
# ResolutionError — an id failed to designate exactly one node

class ResolutionError(TAT_Error, ABC):
    """Remediation direction: fix the id you gave (EXCEPTIONS.md §2)."""


class NodeNotFound(ResolutionError):
    def __init__(self, id: str, near_matches: list[str]):
        super().__init__()
        self.id = id
        self.near_matches = near_matches

    def _cause(self) -> str:
        sentence = f"`{self.id}` is not found."
        if self.near_matches:
            quoted = [f"`{m}`" for m in self.near_matches]
            guesses = (quoted[0] if len(quoted) == 1
                       else ", ".join(quoted[:-1]) + " or " + quoted[-1])
            sentence += f" Did you mean {guesses}?"
        return sentence


class AmbiguousId(ResolutionError):
    def __init__(self, id: str, candidates: list[str]):
        super().__init__()
        self.id = id
        # Every node the id matches, each in its shortest unambiguous form
        # (MCP_SPECIFICATION §2.1).
        self.candidates = candidates

    def _cause(self) -> str:
        matches = ", ".join(f"`{c}`" for c in self.candidates)
        return (f"The id `{self.id}` matches more than one node: {matches}."
                " Choose the one you meant.")


# ---------------------------------------------------------------------------
# RawASTError — a submitted RawAST is malformed

class RawASTError(TAT_Error, ABC):
    """Remediation direction: fix the node description you submitted
    (EXCEPTIONS.md §2)."""


class MalformedRawAST(RawASTError):
    def __init__(self, missing_kind: bool):
        super().__init__()
        # True: the submitted value was an object, but had no `kind`.
        # False: it was not an object at all.
        self.missing_kind = missing_kind

    def _cause(self) -> str:
        if self.missing_kind:
            return "The field `kind` is missing."
        return "Expected a node description object."


class UnknownKind(RawASTError):
    def __init__(self, kind: str, available_kinds: list[str]):
        super().__init__()
        self.kind = kind
        self.available_kinds = available_kinds

    def _cause(self) -> str:
        kinds = ", ".join(f"`{k}`" for k in self.available_kinds)
        return f"Unknown kind `{self.kind}`. Available kinds: {kinds}."


class MissingField(RawASTError):
    def __init__(self, kind: str, field: str):
        super().__init__()
        self.kind = kind
        self.field = field

    def _cause(self) -> str:
        return f"A `{self.kind}` needs the field `{self.field}`."


class InvalidField(RawASTError):
    """Schema-derived like `MissingField`; also ready-made for `gen`
    authors' semantic checks, who derive further subclasses freely."""

    def __init__(self, field: str, reason: str):
        super().__init__()
        self.field = field
        # A predicate completing "The field `X` ..." — e.g. "must be a
        # string", "is not a well-formed term".  The rendering supplies the
        # trailing period.
        self.reason = reason

    def _cause(self) -> str:
        return f"The field `{self.field}` {self.reason.rstrip('.')}."


class UnexpectedField(RawASTError):
    """A field the class does not declare.  Schema-derived like
    `MissingField`, its dual."""

    def __init__(self, holder: str, field: str, takes: list[str],
                 holder_is_kind: bool):
        super().__init__()
        # The kind (holder_is_kind), or the path of the nested object the
        # field sits in, e.g. "facts[1]".
        self.holder = holder
        self.holder_is_kind = holder_is_kind
        self.field = field
        # Every field the holder declares, in declaration order.
        self.takes = takes

    def _cause(self) -> str:
        subject = (f"A `{self.holder}`" if self.holder_is_kind
                   else f"`{self.holder}`")
        takes = ", ".join(f"`{t}`" for t in self.takes)
        return f"{subject} has no field `{self.field}`; it takes {takes}."


# ---------------------------------------------------------------------------
# BadEdit — the request is well formed, but the change would break a
# standing rule

class BadEdit(TAT_Error, ABC):
    """Remediation direction: rethink the change — "edit" in the broad sense
    of the glossary (ARCHITECTURE §1).  Node classes derive their own
    `Bad<Class>NodeParent` from this class (EXCEPTIONS.md §3)."""


# A coordinate into the submitted call ("nodes[0]", "children[2]"), which no
# id can be: a name never contains a bracket (MCP_SPECIFICATION §2).
_COORDINATE = re.compile(r"(?:nodes|children)\[\d+\]")


class DuplicateName(BadEdit):
    def __init__(self, name: str, taken_by: str):
        super().__init__()
        self.name = name
        # An existing sibling's id, or the coordinate of the colliding
        # element of the same call: the two ask for opposite remedies.
        self.taken_by = taken_by

    def _cause(self) -> str:
        if _COORDINATE.match(self.taken_by):
            return (f"The name `{self.name}` is already used by"
                    f" `{self.taken_by}` of this call.")
        return (f"The name `{self.name}` is already taken by"
                f" `{self.taken_by}`. Amend that node, or pick another name.")


class InvalidName(BadEdit):
    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def _cause(self) -> str:
        return (f"`{self.name}` is not a valid name: a name starts with a"
                " letter and continues with letters, digits, underscores and"
                " primes ('), and does not end with an underscore.")


class DuplicateTheoryShortName(BadEdit):
    """Raised by `Theory.gen` (EXCEPTIONS.md §3)."""

    def __init__(self, short_name: str, holder: str):
        super().__init__()
        self.short_name = short_name
        # The qualified name whose short name collides: a theory of the base
        # heap, or another tree's.
        self.holder = holder

    def _cause(self) -> str:
        return (f"The theory name `{self.short_name}` conflicts with the"
                f" short name of `{self.holder}`. No two theories can share"
                " a short name.")


class UnexpectedChildren(BadEdit):
    """Raised before any gen runs (EXCEPTIONS.md §3)."""

    def __init__(self, kind: str, is_leaf: bool):
        super().__init__()
        self.kind = kind
        # True: the class is a Leaf and can hold no children.  False: the
        # class could, but the description is an amend's replacement, which
        # inherits the replaced node's children instead.
        self.is_leaf = is_leaf

    def _cause(self) -> str:
        if self.is_leaf:
            return (f"`children` is not allowed: a `{self.kind}` holds no"
                    " children.")
        return ("When amending a non-leaf node, `children` is not allowed:"
                " the amended node inherits its existing children. To change"
                " the children, use `delete` to remove them and `append` or"
                " `insert_before` to add new ones.")


class ChildrenNotInheritable(BadEdit):
    """Raised before any gen runs (EXCEPTIONS.md §3)."""

    def __init__(self, old_id: str, new_kind: str, children_count: int):
        super().__init__()
        self.old_id = old_id
        self.new_kind = new_kind
        self.children_count = children_count

    def _cause(self) -> str:
        one = self.children_count == 1
        return (f"`{self.old_id}` has"
                f" {'1 child' if one else f'{self.children_count} children'},"
                f" which a `{self.new_kind}` cannot hold."
                f" Move or delete {'it' if one else 'them'} first.")


class MoveIntoOwnSubtree(BadEdit):
    def __init__(self, id: str, destination: str):
        super().__init__()
        self.id = id
        self.destination = destination

    def _cause(self) -> str:
        return f"`{self.id}` cannot move into its own subtree."


class ProtectedNode(BadEdit):
    def __init__(self, id: str):
        super().__init__()
        self.id = id

    def _cause(self) -> str:
        return f"The `{self.id}` cannot be edited."


# ---------------------------------------------------------------------------
# ConstructFailed — `construct` could not start

class ConstructFailed(TAT_Error, ABC):
    """The node's class does not offer the operation, so reach the goal
    another way (EXCEPTIONS.md §2)."""


class ConstructNotSupported(ConstructFailed):
    """Raised by `Node.construct`'s default implementation; a class with a
    `construct` overrides it (MCP_SPECIFICATION §1)."""

    def __init__(self, id: str):
        super().__init__()
        self.id = id

    def _cause(self) -> str:
        return f"`{self.id}` does not support construct."
