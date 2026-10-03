"""The wire to the ML side (MODULE_STRUCTURE §4.3): `call`, the one door to
it, and one function per callback the framework itself offers.

A node class's own callback is called by that class, not from here — but
through `call`, since an exception escaping any callback is a bug
(EXCEPTIONS.md §1): the ML side answers every failure of an operation as
data, so what it lets through — or a failure of the wire contract, such as
no callback registered under the name — is raised here as
`TAT_IsabelleError`.  An interrupt of the callback (the RPC library's
`IsabelleInterrupt`, an `IsabelleError`) is treated the same for now.  The
callback names are the ML side's and are decided nowhere else.  Every
round trip of a conversation is recorded in its log (LOGGING.md §5).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any, TypeAlias

from Isabelle_RPC_Host import Connection, IsabelleError
from Isabelle_RPC_Host.unicode import ascii_of_unicode, pretty_unicode

from .exceptions import TAT_IsabelleError

if TYPE_CHECKING:
    from .log import Log
    from .model import Conversation


class IsaTerm:
    """One piece of Isabelle text in both spellings (THEOREM.md §2):
    `unicode` as the agent writes and reads it, `ascii` in Isabelle's
    `\\<name>` form, the only form Isabelle/ML reads.  Built at the two
    boundaries, `from_agent` and `from_isabelle`; equal when their `ascii`
    is; `str()` refused — the reader says which spelling it wants."""
    __slots__ = ("unicode", "ascii")

    def __init__(self, unicode: str, ascii: str):
        self.unicode = unicode
        self.ascii = ascii

    @classmethod
    def from_isabelle(cls, ascii: str) -> IsaTerm:
        return cls(pretty_unicode(ascii), ascii)

    @classmethod
    def from_agent(cls, unicode: str) -> IsaTerm:
        return cls(unicode, ascii_of_unicode(unicode))

    def __str__(self) -> str:
        raise TypeError("str() on an IsaTerm: read .unicode or .ascii")

    def __repr__(self) -> str:
        return f"IsaTerm({self.unicode!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, IsaTerm):
            return self.ascii == other.ascii
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.ascii)


async def call(conversation: Conversation, name: str, args: Any) -> Any:
    """One round trip to the callback `name`, recorded in the
    conversation's log.  An exception the callback let escape is a bug,
    not a result (EXCEPTIONS.md §1)."""
    return await _call(conversation.connection, name, args, conversation.log)


async def _call(conn: Connection, name: str, args: Any, log: Log | None) -> Any:
    """The round trip on a connection.  Shielded: a callback is a two-phase
    exchange the wire must see whole, so a cancellation of the caller
    unwinds the caller at once while the round trip completes on its own,
    its result dropped (MODULE_STRUCTURE §4.3); the record is written when
    the trip completes, whether or not the caller still waits.  `reset`
    alone passes no log: it runs before any `Conversation` exists."""
    trip = asyncio.ensure_future(conn.callback(name, args))
    trip.add_done_callback(partial(_completed, log, name, args, time.monotonic()))
    try:
        return await asyncio.shield(trip)
    except IsabelleError as e:
        raise TAT_IsabelleError(
            f"the ML callback {name} failed:\n" + "\n".join(e.errors)) from e


def _completed(log: Log | None, name: str, args: Any, started: float,
               trip: asyncio.Future[Any]) -> None:
    """The trip's outcome, read here so asyncio does not report an
    abandoned round trip's exception as unhandled, and recorded:
    `round_trip`, or `connection_lost` when the wire went (LOGGING.md §4)."""
    if trip.cancelled():
        return
    exn = trip.exception()
    if log is None:
        return
    duration = time.monotonic() - started
    if exn is None:
        log.round_trip.round_trip(name=name, arguments=args, result=trip.result(), duration=duration)
    elif isinstance(exn, ConnectionError):
        log.round_trip.connection_lost(error=_text(exn))
    else:
        log.round_trip.round_trip(name=name, arguments=args, error=_text(exn), duration=duration)


def _text(exn: BaseException) -> str:
    """An error as the log carries it: an `IsabelleError`'s messages, one
    per line; anything else with its class."""
    if isinstance(exn, IsabelleError):
        return "\n".join(exn.errors)
    return f"{type(exn).__name__}: {exn}"


async def state_delete(conversation: Conversation, names: list[str]) -> None:
    """Remove the names from the conversation's state slot table, in one
    round trip.  A name that is not there is not an error."""
    await call(conversation, "TAT.state_delete", names)


async def state_exists(conversation: Conversation, name: str) -> bool:
    return await call(conversation, "TAT.state_exists", name)


async def state_copy(conversation: Conversation, src: str, dst: str) -> None:
    """Afterwards `dst` holds what `src` holds — including nothing, when
    `src` is not in the table."""
    await call(conversation, "TAT.state_copy", (src, dst))


async def theory_delete(conversation: Conversation, names: list[str]) -> None:
    """Remove the qualified names from the conversation's theory table
    (MODULE_STRUCTURE §2.2), in one round trip.  A name that is not there
    is not an error."""
    await call(conversation, "TAT.theory_delete", names)


async def reset(conn: Connection) -> None:
    """Empty the state slot table and the theory table: a fresh conversation
    begins on the same Isabelle process (ARCHITECTURE §9).  The first act of
    every conversation the test harness hands out, and called by nothing
    else; `Thy_Info`, the process's cache, stays.  On a bare connection,
    before any `Conversation` exists: recorded nowhere on this side."""
    await _call(conn, "TAT.reset", None, None)


# The three answers of the short-name check (MODULE_STRUCTURE §2.3).

@dataclass(frozen=True)
class Taken:
    """A loaded theory bears the short name: its long name, which for a
    global theory is the short name itself."""
    holder: str

@dataclass(frozen=True)
class Reserved:
    """No loaded theory bears it, but the Isabelle session layout declares
    the name global."""

@dataclass(frozen=True)
class Free:
    """Nobody bears it."""

Short_Name_Answer: TypeAlias = Taken | Reserved | Free


async def check_new_theory_short_name(conversation: Conversation, name: str) -> Short_Name_Answer:
    """The Isabelle half of the short-name check (MODULE_STRUCTURE §2.3).
    The forest half, and the rejection itself, live in `Theory`'s gen
    (MCP_SPECIFICATION §2)."""
    match await call(conversation, "TAT.check_new_theory_short_name", name):
        case ["taken", str(holder)]:
            return Taken(holder)
        case ["reserved"]:
            return Reserved()
        case ["free"]:
            return Free()
        case answer:
            raise TAT_IsabelleError(
                f"the ML callback TAT.check_new_theory_short_name answered {answer!r}")


async def is_known_session(conversation: Conversation, name: str) -> bool:
    """Whether the Isabelle session layout knows a session of the name: the
    Isabelle half of `parent_session`'s check (MODULE_STRUCTURE §2.3).  The
    forest half, and the rejection, live in `Session`'s gen."""
    return await call(conversation, "TAT.is_known_session", name)
