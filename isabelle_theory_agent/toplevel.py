"""The RPC entry point Isabelle calls into (MODULE_STRUCTURE §4.6).

`TAT_Framework.start` on the ML side calls the procedure `launch_TAT`, which
does not return (ARCHITECTURE §9); everything the conversation does, it does
through this call's callbacks.  The entry contract is MODULE_STRUCTURE §4.6;
the signature lands with it (ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §7,
step 5).
"""

from Isabelle_RPC_Host import Connection, isabelle_remote_procedure


@isabelle_remote_procedure("launch_TAT")
async def launch_TAT(python_packages: list[str], connection: Connection) -> None:
    raise NotImplementedError("the conversation's Python side is not written yet")
