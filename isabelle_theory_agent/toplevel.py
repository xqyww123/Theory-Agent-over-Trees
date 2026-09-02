"""The RPC entry point Isabelle calls into (MODULE_STRUCTURE §4.5).

`TAT_Framework.start` on the ML side calls the procedure `launch_TAT` and
does not return for the life of the conversation (ARCHITECTURE §9);
everything the conversation does, it does through this call's callbacks.
The argument is the node classes' Python halves — the `python_packages` of
every registration, deduplicated (MODULE_STRUCTURE §2.6) — for the plugin
loader to import (MODULE_STRUCTURE §4.3).
"""

from Isabelle_RPC_Host import Connection, isabelle_remote_procedure


@isabelle_remote_procedure("launch_TAT")
async def launch_TAT(python_packages: list[str], connection: Connection) -> None:
    raise NotImplementedError("the conversation's Python side is not written yet")
