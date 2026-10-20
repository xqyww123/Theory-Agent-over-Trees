"""The `TAT_Error` hierarchy (EXCEPTIONS.md).

Every class carries its facts as fields; `__str__` assembles the agent-facing
sentence from them.  The approved wording lives in docs/RENDER_BASELINES.md,
and `test/test_exceptions.py` asserts it verbatim; every other test that
meets a cause sentence asserts the exception's class and fields, or reads
the line from the documents — the lines the framework writes itself, the
`Cannot` and `Done` openings and a node's line, a test may spell out with
its own ids (EXCEPTIONS.md §3).

Two fields on `TAT_Error` are written by the framework after the raise,
never by the raise site: `opr` with `target` at the tool entry
(EXCEPTIONS.md §4), and `raw_ast_path` by the per-element loops as the
exception unwinds (EXCEPTIONS.md §5).  `RawASTError` carries a third
framework-written field, `of_tool`: written by `plugin.check_call` as the
exception leaves it — the one place that knows it read a tool's schema
(TOOL_SCHEMAS.md §4).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Literal


class TAT_Error(Exception, ABC):
    """An error the agent can act on: raised anywhere, caught only at the
    tool boundary, rendered into the tool result (EXCEPTIONS.md §1)."""

    # The refused forest-changing operation and its target, echoed from the
    # call (EXCEPTIONS.md §4).  Written once by `_set_operation`; both stay
    # None for tools that do not change the forest.
    opr: str | None = None
    target: str | None = None

    # Which element of the submitted `constructs` list, e.g. "constructs[2].children[0]"
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
        """Framework-only, at the tool entry.  `opr` is one of the
        forest-changing operation names (TOOL_SCHEMAS.md §4); `target` is the operation's
        target echoed from the call — for `move` including the destination
        phrase, e.g. "theory_Sorting before theory_X.lemma_P"."""
        if self.opr is not None or opr not in _OPERATIONS:
            raise TAT_InternalError(f"operation {opr!r} onto {self.opr!r}")
        self.opr = opr
        self.target = target

    def _prefix_raw_ast_path(self, step: str) -> None:
        """Framework-only, on the unwind path.  `step` is the raising
        element's coordinate in the loop's own list — "constructs[2]" at the top
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
    `TAT_Error`, so the tool boundary never answers the agent with it
    (EXCEPTIONS.md §1)."""


class TAT_IsabelleError(TAT_InternalError):
    """An ML callback failed (EXCEPTIONS.md §1): it let an exception escape
    — the ML side's `Bug`, or anything it did not foresee, a callback
    answering every failure of its operation as data — or it was
    interrupted, or the wire contract broke, no callback being registered
    under the name.  Raised by
    `isabelle_driver.call`, the one door to the wire; `__cause__` is the
    RPC library's `IsabelleError`."""


class TAT_StartupError(Exception):
    """TAT cannot start in this environment -- the working directory, its
    database.  Raised before any tool boundary exists, out of `launch_TAT`
    into the ML call that started the conversation; never rendered to the
    agent (EXCEPTIONS.md §1)."""


class TAT_DisasterError(Exception):
    """The forest in memory and the forest in the database have parted: a
    store transaction failed after the operation had been committed in
    memory.  Never answered to the agent; the conversation ends
    (EXCEPTIONS.md §1).  `__cause__` is what failed."""


# The forest-changing operations (TOOL_SCHEMAS.md §4).
_OPERATIONS = frozenset(
    {"append", "insert_before", "insert_after", "amend", "move", "delete"})


def series(words: list[str], last: str) -> str:
    """Words joined with commas and `last` before the last: `A`; `A and B`;
    `A, B and C`."""
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + f" {last} " + words[-1]


def placement_rule(within: str, through: list[str]) -> str:
    """The second half of both placement refusals (RENDER_BASELINES §2,
    §3), from the kinds a placement names: where a node of the class
    stands."""
    return (f"it stands inside a node of kind `{within}`, "
            + (f"directly or under nodes of kind {series([f'`{k}`' for k in through], 'or')}." if through
               else "directly."))


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
            sentence += f" Did you mean {series([f'`{m}`' for m in self.near_matches], 'or')}?"
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
# RawASTError — a submitted RawAST, or a tool call's own arguments, is
# malformed

class RawASTError(TAT_Error, ABC):
    """Remediation direction: fix the construct, or the call, you submitted
    (EXCEPTIONS.md §2)."""

    # The holder is a tool and its fields the call's arguments, not a kind
    # and a construct's (TOOL_SCHEMAS.md §4); the three shape errors' sentences
    # say so.  Written by `plugin.check_call` as the exception leaves it, so
    # no raise site knows whose shape it reads.  Inert on `MalformedRawAST`
    # and `UnknownKind`.
    of_tool: bool = False

    def _mark_of_tool(self) -> None:
        """Framework-only, at `plugin.check_call`."""
        self.of_tool = True


class MalformedRawAST(RawASTError):
    def __init__(self, missing_kind: bool):
        super().__init__()
        # True: the submitted value was an object, but had no `kind`.
        # False: it was not an object at all.
        self.missing_kind = missing_kind

    def _cause(self) -> str:
        if self.missing_kind:
            return "The field `kind` is missing."
        return "Expected a construct object."


class UnknownKind(RawASTError):
    def __init__(self, kind: str, available_kinds: list[str]):
        super().__init__()
        self.kind = kind
        self.available_kinds = available_kinds

    def _cause(self) -> str:
        kinds = ", ".join(f"`{k}`" for k in self.available_kinds)
        return f"Unknown kind `{self.kind}`. Available kinds: {kinds}."


class MissingField(RawASTError):
    def __init__(self, holder: str, field: str):
        super().__init__()
        self.holder = holder             # the kind, or the tool (of_tool)
        self.field = field

    def _cause(self) -> str:
        if self.of_tool:
            return f"The `{self.holder}` tool needs the argument `{self.field}`."
        return f"A `{self.holder}` needs the field `{self.field}`."


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
        what = "argument" if self.of_tool else "field"
        return f"The {what} `{self.field}` {self.reason.rstrip('.')}."


class UnexpectedField(RawASTError):
    """A field the class does not declare.  Schema-derived like
    `MissingField`, its dual."""

    def __init__(self, holder: str, field: str, takes: list[str],
                 holder_is_top: bool):
        super().__init__()
        # At the top: the kind, or the tool (of_tool).  Below: the path of
        # the nested object the field sits in, e.g. "facts[1]".
        self.holder = holder
        self.holder_is_top = holder_is_top
        self.field = field
        # Every field the holder declares, in declaration order.
        self.takes = takes

    def _cause(self) -> str:
        if not self.holder_is_top:
            subject = f"`{self.holder}`"
        elif self.of_tool:
            subject = f"The `{self.holder}` tool"
        else:
            subject = f"A `{self.holder}`"
        what = "argument" if self.of_tool else "field"
        takes = ", ".join(f"`{t}`" for t in self.takes) or f"no {what}s"
        return f"{subject} has no {what} `{self.field}`; it takes {takes}."


# ---------------------------------------------------------------------------
# BadEdit — the request is well formed, but the change would break a
# standing rule

class BadEdit(TAT_Error, ABC):
    """Remediation direction: rethink the change — "edit" in the broad sense
    of the glossary (ARCHITECTURE §1)."""


# A coordinate into the submitted call ("constructs[0]", "children[2]"), which no
# id can be: a name never contains a bracket (MCP_SPECIFICATION §2).  Used
# with `match`, a prefix test, so a full path ("constructs[1].children[0]")
# is recognised too.
_COORDINATE = re.compile(r"(?:constructs|children)\[\d+\]")


class DuplicateName(BadEdit):
    """Two siblings would share an id component `<kind>_<name>`
    (MCP_SPECIFICATION §2) — what must be unique, since ids are made of
    them; a name alone need not be."""

    def __init__(self, id_component: str, taken_by: str):
        super().__init__()
        self.id_component = id_component
        # An existing sibling's id, or the coordinate of the colliding
        # element of the same call: the two ask for opposite remedies.
        self.taken_by = taken_by

    def _cause(self) -> str:
        if _COORDINATE.match(self.taken_by):
            return (f"The id component `{self.id_component}` is already used by"
                    f" `{self.taken_by}` of this call.")
        return (f"The id component `{self.id_component}` is already taken by"
                f" `{self.taken_by}`. Amend that node, or give this one another name.")


class InvalidName(BadEdit):
    """Raised against one of six grammars, which `grammar` names: the
    framework's name grammar (MCP_SPECIFICATION §2), by the framework; the
    theory name's, by `Theory.gen`; the session name's, by `Session.gen`;
    the fact name's, by `Theorem.gen` (node_classes/THEOREM.md §4); the
    type name's, by `Datatype.gen` and `Typedef.gen` (node_classes/DATATYPE.md
    §4, TYPEDEF.md §4); the constant name's, by `LiftDefinition.gen` and
    `Define.gen` (node_classes/LIFT_DEFINITION.md §4, DEFINE.md §4).  Each
    renders its own grammar, so the agent can correct the name from the
    message."""

    def __init__(self, name: str,
                 grammar: Literal["name", "theory name", "session name", "fact name", "type name",
                                  "constant name"] = "name"):
        super().__init__()
        self.name = name
        self.grammar = grammar

    def _cause(self) -> str:
        return f"`{self.name}` is not a valid {self.grammar}: a {self.grammar} {GRAMMARS[self.grammar]}."


# Each grammar's text, a predicate of the name, rendered by `InvalidName`
# after its subject.  The fact name's, the type name's and the constant
# name's are one text (RENDER_BASELINES §2), which `Isabelle_Std` also
# renders when it refuses a field that is no Isabelle identifier
# (node_classes/COMMON.md §5).
_FACT_OR_TYPE_NAME = ("starts with a letter and continues with letters, digits, underscores and primes ('), and"
                      " does not end with an underscore")
GRAMMARS = {
    "name": "starts with a letter and continues with letters, digits, underscores, primes (') and interior"
            " hyphens, and does not end with a hyphen or an underscore",
    "theory name": "starts with a letter and continues with letters, digits and underscores, with no hyphen"
                   " and no dot",
    "session name": "starts with a letter and continues with letters, digits, underscores and interior"
                    " hyphens, and does not end with a hyphen or an underscore",
    "fact name": _FACT_OR_TYPE_NAME,
    "type name": _FACT_OR_TYPE_NAME,
    "constant name": _FACT_OR_TYPE_NAME,
}


class DuplicateTheoryShortName(BadEdit):
    """Raised by `Theory.gen` against the base heap, and by the framework's
    namespace check against the forest and the batch (EXCEPTIONS.md §3)."""

    def __init__(self, short_name: str, holder: str):
        super().__init__()
        self.short_name = short_name
        # The qualified name whose short name collides — a theory of the
        # base heap, or another tree's — or the colliding construct's full
        # path in this call.
        self.holder = holder

    def _cause(self) -> str:
        if _COORDINATE.match(self.holder):
            return (f"The theory name `{self.short_name}` is also used by"
                    f" `{self.holder}` of this call.")
        return (f"The theory name `{self.short_name}` conflicts with the"
                f" short name of `{self.holder}`. No two theories can share"
                " a short name.")


class ReservedTheoryName(BadEdit):
    """Raised by `Theory.gen`: no loaded theory bears the name, and either
    the Isabelle session layout declares it global — `FOL`, `ZF`, … on a
    HOL heap — so Isabelle would leave a tree so named unqualified, or
    Isabelle reserves it as a file name or a theory name — `Aux`, `ROOT`,
    `bib`, … (EXCEPTIONS.md §3)."""

    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def _cause(self) -> str:
        return f"`{self.name}` is a reserved theory name; choose another name."


class ReservedSessionName(BadEdit):
    """Raised by `Session.gen`: Isabelle reserves the name as a file or
    session name, or it is `ROOT` in some spelling, where the session's
    folder would be the ROOT file's path (EXCEPTIONS.md §3)."""

    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def _cause(self) -> str:
        return f"`{self.name}` is a reserved session name; choose another name."


class UnexpectedChildren(BadEdit):
    """Raised before any gen runs (EXCEPTIONS.md §3)."""

    def __init__(self, kind: str, is_leaf: bool):
        super().__init__()
        self.kind = kind
        # True: the class is a Leaf and can hold no children.  False: the
        # class could, but the construct is an amend's replacement, which
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


class BadSessionNodeParent(BadEdit):
    """`Session`'s parent check (EXCEPTIONS.md §3): raised by its gen and
    its `on_moving` for every parent but the forest root."""

    def __init__(self, kind: str, parent_id: str):
        super().__init__()
        self.kind = kind
        self.parent_id = parent_id

    def _cause(self) -> str:
        return (f"A `{self.kind}` cannot be placed under `{self.parent_id}`;"
                " a session lives directly under `Sessions`.")


class BadTheoryNodeParent(BadEdit):
    """`Theory`'s parent check (EXCEPTIONS.md §3): raised by its gen and
    its `on_moving` for every parent but a `Session`."""

    def __init__(self, kind: str, parent_id: str):
        super().__init__()
        self.kind = kind
        self.parent_id = parent_id

    def _cause(self) -> str:
        return (f"A `{self.kind}` cannot be placed under `{self.parent_id}`;"
                " a theory lives directly under a session.")


class BadPlacement(BadEdit):
    """A plugin's node placed under a `Session` or the forest root
    (EXCEPTIONS.md §3): raised by the framework at an insert, an amend and
    a move.  `within` and `through` are the kinds of the classes the
    class's `placement` names (`model.placement_kinds`)."""

    def __init__(self, kind: str, parent_id: str, within: str, through: list[str]):
        super().__init__()
        self.kind = kind
        self.parent_id = parent_id
        self.within = within
        self.through = through

    def _cause(self) -> str:
        return (f"A node of kind `{self.kind}` cannot be placed under `{self.parent_id}`; "
                + placement_rule(self.within, self.through))


class MoveIntoOwnSubtree(BadEdit):
    def __init__(self, id: str, destination: str):
        super().__init__()
        self.id = id
        self.destination = destination

    def _cause(self) -> str:
        return f"`{self.id}` cannot move into its own subtree."


class MoveBesideItself(BadEdit):
    """`move` `before` or `after` the moved node itself (TOOL_SCHEMAS.md §2)."""

    def __init__(self, id: str):
        super().__init__()
        self.id = id

    def _cause(self) -> str:
        return f"`{self.id}` is already in that position; a move must name another node."


class HoldsNoChildren(BadEdit):
    """The target of an `append` or a `move … into` is a leaf
    (TOOL_SCHEMAS.md §1, §2)."""

    def __init__(self, id: str, kind: str):
        super().__init__()
        self.id = id
        self.kind = kind

    def _cause(self) -> str:
        return f"`{self.id}` is a `{self.kind}`, and it cannot hold children."


class ProtectedNode(BadEdit):
    def __init__(self, id: str):
        super().__init__()
        self.id = id

    def _cause(self) -> str:
        return f"The `{self.id}` cannot be edited."


# ---------------------------------------------------------------------------
# ConstructionError — a construct tool refused (CONSTRUCT_INTERACTION §5)

class ConstructionError(TAT_Error, ABC):
    """`construct`, `cancel_construct` or `answer` refused the call
    (EXCEPTIONS.md §2, §3)."""


class ConstructNotSupported(ConstructionError):
    """`construct` or `cancel_construct` named no node with a construction
    job: the one id the call named, or None when it named several."""

    def __init__(self, id: str | None):
        super().__init__()
        self.id = id

    def _cause(self) -> str:
        if self.id is None:
            return "None of these nodes has anything to construct."
        return f"`{self.id}` has nothing to construct."


class ConstructOwnedByAnother(ConstructionError):
    """`answer` on a question of another agent's run; the sentence is the
    job class's `owned_by_another_refusal` (RENDER_BASELINES §2)."""

    def __init__(self, id: str, refusal: str):
        super().__init__()
        self.id = id
        self.refusal = refusal

    def _cause(self) -> str:
        return self.refusal


class NoQuestionPending(ConstructionError):
    """`answer` on a node where no question of the caller's waits: no
    construction job, a job not running, a run that asked nothing."""

    def __init__(self, id: str):
        super().__init__()
        self.id = id

    def _cause(self) -> str:
        return f"`{self.id}` has no question waiting for an answer."


# ---------------------------------------------------------------------------
# BadAnswer — the question refused the answer (CONSTRUCT_INTERACTION §3.4)

class BadAnswer(TAT_Error):
    """The question's `receive` refused a shape-valid answer, with its own
    sentence; the question stays pending.  Raised by a job class's
    `Interactive_Question`."""

    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def _cause(self) -> str:
        return self.message
