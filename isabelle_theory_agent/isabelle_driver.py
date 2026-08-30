"""Typed calls to the ML side's callbacks (MODULE_STRUCTURE §4.2).

One function per callback the framework offers.  A node class's own callback
is called by that class, not from here.  The callback names are the ML side's
and are decided nowhere else.
"""

from Isabelle_RPC_Host import Connection


async def state_delete(conn: Connection, names: list[str]) -> None:
    """Remove the names from the session's state slot table, in one round
    trip.  A name that is not there is not an error."""
    await conn.callback("TAT.state_delete", names)


async def state_exists(conn: Connection, name: str) -> bool:
    return await conn.callback("TAT.state_exists", name)


async def state_copy(conn: Connection, src: str, dst: str) -> None:
    """Afterwards `dst` holds what `src` holds — including nothing, when
    `src` is not in the table."""
    await conn.callback("TAT.state_copy", (src, dst))
