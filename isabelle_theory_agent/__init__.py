"""TAT: an agent that writes Isabelle theories by editing a forest of trees.

Importing the package registers the RPC entry point (`toplevel.launch_TAT`),
which is what `Remote_Procedure_Calling.load ["isabelle_theory_agent"]` on
the ML side relies on.
"""

from . import toplevel as toplevel
