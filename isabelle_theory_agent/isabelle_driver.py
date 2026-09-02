"""Typed calls to the ML side's callbacks (MODULE_STRUCTURE §4.2).

One function per callback the framework offers.  A node class's own callback
is called by that class, not from here.  The callback names are the ML side's
and are decided nowhere else.
"""

from Isabelle_RPC_Host import Connection


async def state_delete(conn: Connection, names: list[str]) -> None:
    """Remove the names from the conversation's state slot table, in one
    round trip.  A name that is not there is not an error."""
    await conn.callback("TAT.state_delete", names)


async def state_exists(conn: Connection, name: str) -> bool:
    return await conn.callback("TAT.state_exists", name)


async def state_copy(conn: Connection, src: str, dst: str) -> None:
    """Afterwards `dst` holds what `src` holds — including nothing, when
    `src` is not in the table."""
    await conn.callback("TAT.state_copy", (src, dst))


async def check_new_theory_short_name(conn: Connection, name: str) -> str | None:
    """The base-heap half of the short-name check (MODULE_STRUCTURE §2.3):
    the long name of the base-heap theory whose short name `name` would
    take, or None when the name is free.  The forest half, and the
    rejection itself, live in `Theory`'s gen (MCP_SPECIFICATION §2)."""
    return await conn.callback("TAT.check_new_theory_short_name", name)
