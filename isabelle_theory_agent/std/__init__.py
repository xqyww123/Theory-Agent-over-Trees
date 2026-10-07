"""The Python half of the plugin `Isabelle_Std` (MODULE_STRUCTURE §4.5):
the node classes of Isabelle's standard commands, one module per class,
which importing this package registers; and the theory the plugin
declares the forest's theories import, where the `aoa` method is defined
(PLUGIN_SYSTEM §1, node_classes/THEOREM.md §5)."""

from ..plugin import TAT_import
from . import theorem as theorem

TAT_import("Minilang_AoA.Minilang_AoA")
