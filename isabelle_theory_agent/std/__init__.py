"""The Python half of the plugin `Isabelle_Std` (MODULE_STRUCTURE §4.5):
what its classes share (`common`, node_classes/COMMON.md), then the node
classes of Isabelle's standard commands, one module per class, which
importing this package registers."""

from . import (
    common as common, datatype as datatype, define as define, lift_definition as lift_definition,
    lifting_context as lifting_context, quotient_type as quotient_type, record as record, section as section,
    text as text, theorem as theorem, typedef as typedef)
