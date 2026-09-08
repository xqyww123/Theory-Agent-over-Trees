"""Shared by every test module: without an Isabelle installation the
`Isabelle_RPC_Host` package is absent, and the tests that need no Isabelle
only ever pass a `Connection` around, so a stub module stands in for it."""

import sys
import types

try:
    import Isabelle_RPC_Host  # noqa: F401
except ImportError:
    m = types.ModuleType("Isabelle_RPC_Host")
    m.Connection = object  # type: ignore[attr-defined]
    sys.modules["Isabelle_RPC_Host"] = m
