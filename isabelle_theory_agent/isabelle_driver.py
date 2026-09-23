"""The wire to the ML side (MODULE_STRUCTURE §4.3): `call`, the one door to
it, and one function per callback the framework itself offers.

A node class's own callback is called by that class, not from here — but
through `call`, since an exception escaping any callback is a bug
(EXCEPTIONS.md §1): the ML side answers every failure of an operation as
data, so what it lets through — or a failure of the wire contract, such as
no callback registered under the name — is raised here as
`TAT_IsabelleError`.  An interrupt of the callback (the RPC library's
`IsabelleInterrupt`, an `IsabelleError`) is treated the same for now.  The
callback names are the ML side's and are decided nowhere else.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, TypeAlias

from Isabelle_RPC_Host import Connection, IsabelleError

from .exceptions import TAT_IsabelleError


async def call(conn: Connection, name: str, args: Any) -> Any:
    """One round trip to the callback `name`.  An exception the callback
    let escape is a bug, not a result (EXCEPTIONS.md §1).  Shielded: a
    callback is a two-phase exchange the wire must see whole, so a
    cancellation of the caller unwinds the caller at once while the round
    trip completes on its own, its result dropped (MODULE_STRUCTURE §4.3)."""
    trip = asyncio.ensure_future(conn.callback(name, args))
    trip.add_done_callback(_dropped)
    try:
        return await asyncio.shield(trip)
    except IsabelleError as e:
        raise TAT_IsabelleError(
            f"the ML callback {name} failed:\n" + "\n".join(e.errors)) from e


def _dropped(trip: asyncio.Future[Any]) -> None:
    """An abandoned round trip's outcome is nobody's; read here so asyncio
    does not report an exception of it as unhandled."""
    if not trip.cancelled():
        trip.exception()


async def state_delete(conn: Connection, names: list[str]) -> None:
    """Remove the names from the conversation's state slot table, in one
    round trip.  A name that is not there is not an error."""
    await call(conn, "TAT.state_delete", names)


async def state_exists(conn: Connection, name: str) -> bool:
    return await call(conn, "TAT.state_exists", name)


async def state_copy(conn: Connection, src: str, dst: str) -> None:
    """Afterwards `dst` holds what `src` holds — including nothing, when
    `src` is not in the table."""
    await call(conn, "TAT.state_copy", (src, dst))


async def theory_delete(conn: Connection, names: list[str]) -> None:
    """Remove the qualified names from the conversation's theory table
    (MODULE_STRUCTURE §2.2), in one round trip.  A name that is not there
    is not an error."""
    await call(conn, "TAT.theory_delete", names)


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


async def check_new_theory_short_name(conn: Connection, name: str) -> Short_Name_Answer:
    """The Isabelle half of the short-name check (MODULE_STRUCTURE §2.3).
    The forest half, and the rejection itself, live in `Theory`'s gen
    (MCP_SPECIFICATION §2)."""
    match await call(conn, "TAT.check_new_theory_short_name", name):
        case ["taken", str(holder)]:
            return Taken(holder)
        case ["reserved"]:
            return Reserved()
        case ["free"]:
            return Free()
        case answer:
            raise TAT_IsabelleError(
                f"the ML callback TAT.check_new_theory_short_name answered {answer!r}")
