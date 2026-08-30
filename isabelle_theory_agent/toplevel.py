"""The RPC entry point Isabelle calls into (MODULE_STRUCTURE §4.5).

`TAT_Framework.start` on the ML side calls the procedure `launch_TAT` and
does not return for the life of the session (ARCHITECTURE §9); everything
the session does, it does through this call's callbacks.  The argument and
the result are both empty for now; both will grow.
"""

from Isabelle_RPC_Host import Connection, isabelle_remote_procedure


@isabelle_remote_procedure("launch_TAT")
async def launch_TAT(_: None, connection: Connection) -> None:
    raise NotImplementedError("the session's Python side is not written yet")
