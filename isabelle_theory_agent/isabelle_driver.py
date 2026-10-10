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
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias

from Isabelle_RPC_Host import Connection, IsabelleError

from .exceptions import TAT_IsabelleError

if TYPE_CHECKING:
    from .log import Log
    from .model import Conversation


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
    trip.add_done_callback(partial(_trip_done, log, name, args, time.monotonic()))
    try:
        return await asyncio.shield(trip)
    except IsabelleError as e:
        raise TAT_IsabelleError(f"the ML callback {name} failed:\n{_text(e)}") from e


def _trip_done(log: Log | None, name: str, args: Any, started: float,
               trip: asyncio.Future[Any]) -> None:
    """The trip's outcome, read here so asyncio does not report an
    abandoned round trip's exception as unhandled, and recorded as
    `round_trip` with the result or the error (LOGGING.md §4)."""
    if trip.cancelled():
        return
    exn = trip.exception()
    if log is None:
        return
    duration = time.monotonic() - started
    if exn is None:
        log.round_trip.round_trip(name=name, arguments=args, result=trip.result(), duration=duration)
    else:
        log.round_trip.round_trip(name=name, arguments=args, error=_text(exn), duration=duration)


def _text(exn: BaseException) -> str:
    """An error's text as the log and `TAT_IsabelleError` carry it: an
    `IsabelleError`'s messages, one per line; anything else with its
    class."""
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


async def log_directory(conversation: Conversation, directory: Path) -> None:
    """Name the conversation's log directory to the Isabelle side, which
    appends its own records there and tells the launcher (LOGGING.md §5,
    §7); the one framework callback a compile makes too."""
    await call(conversation, "TAT.log_directory", str(directory.absolute()))


async def serving(conversation: Conversation, url: str, agent_directory: Path,
                  launch_arguments: Sequence[str]) -> None:
    """Tell the Isabelle side the conversation is served — the URL, the
    agent directory's canonical path and the arguments the client takes
    at its launch — which it passes to the launcher as the protocol message
    `TAT.serving` (MODULE_STRUCTURE §2.6, §4.6): a conversation's one round
    trip once its port is bound, after which the launcher may start the
    client."""
    await call(conversation, "TAT.serving", (url, str(agent_directory), list(launch_arguments)))


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
    the name global, or Isabelle refuses it as a file or theory name."""

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


# The answers of the session check (MODULE_STRUCTURE §2.3): the first defect
# Isabelle finds, or none.

@dataclass(frozen=True)
class Session_Ok:
    """Isabelle finds nothing to refuse."""

@dataclass(frozen=True)
class Name_Reserved:
    """Isabelle reserves the name as a file or session name."""

@dataclass(frozen=True)
class Name_Known:
    """The Isabelle session layout knows a session of the name."""

@dataclass(frozen=True)
class Option_Refused:
    """Isabelle does not know the option, or its value is of the wrong
    type: its place among the options, and Isabelle's message."""
    index: int
    message: str

@dataclass(frozen=True)
class Parent_Unknown:
    """The Isabelle session layout knows no session of the parent's name."""

Session_Answer: TypeAlias = Session_Ok | Name_Reserved | Name_Known | Option_Refused | Parent_Unknown


async def check_session(conversation: Conversation, name: str, parent_session: str | None,
                        options: Sequence[tuple[str, str]]) -> Session_Answer:
    """`Session.gen`'s one question to Isabelle (MODULE_STRUCTURE §2.3):
    the first defect of the name, the options — each a name and a value —
    and the parent; `parent_session` None when the forest settled it and
    Isabelle is not to be asked.  The forest half, and every rejection,
    live in `Session`'s gen."""
    match await call(conversation, "TAT.check_session",
                     (name, parent_session, [list(option) for option in options])):
        case ["ok"]:
            return Session_Ok()
        case ["name_reserved"]:
            return Name_Reserved()
        case ["name_known"]:
            return Name_Known()
        case ["option", str(index), str(message)]:
            return Option_Refused(int(index), message)
        case ["parent_unknown"]:
            return Parent_Unknown()
        case answer:
            raise TAT_IsabelleError(f"the ML callback TAT.check_session answered {answer!r}")


async def job_cancel(conversation: Conversation, ids: list[int]) -> None:
    """Cancel the futures of the forked works so numbered — evaluation jobs',
    construction runs' (MODULE_STRUCTURE §2.4) — in one round trip; an id
    whose work has ended is not an error."""
    await call(conversation, "TAT.job_cancel", ids)
