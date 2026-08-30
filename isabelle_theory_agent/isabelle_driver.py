"""Typed calls to the ML side's callbacks (MODULE_STRUCTURE §4.2).

One function per callback the framework offers.  A node class's own callback
is called by that class, not from here.  The callback names are the ML side's
and are decided nowhere else.
"""

from Isabelle_RPC_Host import Connection


async def delete_state(conn: Connection, name: str) -> None:
    """Remove `name` from the session's state slot table.  A name that is not
    there is not an error."""
    await conn.callback("TAT.delete_state", name)


async def delete_states(conn: Connection, names: list[str]) -> None:
    """`delete_state` for many names in one round trip."""
    await conn.callback("TAT.delete_states", names)


async def state_exists(conn: Connection, name: str) -> bool:
    return await conn.callback("TAT.state_exists", name)


async def copy_state(conn: Connection, src: str, dst: str) -> None:
    """Afterwards `dst` holds what `src` holds — including nothing, when
    `src` is not in the table."""
    await conn.callback("TAT.copy_state", (src, dst))
