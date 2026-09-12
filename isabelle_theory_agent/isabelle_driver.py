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

from typing import Any

from Isabelle_RPC_Host import Connection, IsabelleError

from .exceptions import TAT_IsabelleError


async def call(conn: Connection, name: str, args: Any) -> Any:
    """One round trip to the callback `name`.  An exception the callback
    let escape is a bug, not a result (EXCEPTIONS.md §1)."""
    try:
        return await conn.callback(name, args)
    except IsabelleError as e:
        raise TAT_IsabelleError(
            f"the ML callback {name} failed:\n" + "\n".join(e.errors)) from e


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


async def check_new_theory_short_name(conn: Connection, name: str) -> str | None:
    """The base-heap half of the short-name check (MODULE_STRUCTURE §2.3):
    the long name of the base-heap theory whose short name `name` would
    take, or None when the name is free.  The forest half, and the
    rejection itself, live in `Theory`'s gen (MCP_SPECIFICATION §2)."""
    return await call(conn, "TAT.check_new_theory_short_name", name)
