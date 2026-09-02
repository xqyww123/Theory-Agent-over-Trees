"""Loading node classes and their table (MODULE_STRUCTURE §4.3).

Importing a node class package fills `kinds` through `@TAT_node`; the table
is what `edit` dispatches on and what builds the tool schemas.  One
conversation per process, so the table is module state.
"""

from __future__ import annotations

import importlib

from .exceptions import TAT_InternalError
from .model import Node

# kind -> node class, in registration order — the order agent-facing lists
# of kinds render in (EXCEPTIONS.md §3, `UnknownKind`).
kinds: dict[str, type[Node]] = {}


def TAT_node(registered_kinds: list[str]):
    """Class decorator: register the class under every kind it answers to —
    `Theorem` registers `lemma`, `theorem` and `corollary`."""
    def register(cls: type[Node]) -> type[Node]:
        # A class omissible on output but compulsory on input would let TAT
        # print an id it then refuses to accept (MCP_SPECIFICATION §2.1).
        if cls.output_omissible and not cls.input_omissible:
            raise TAT_InternalError(
                f"{cls.__name__} is omissible on output but compulsory on"
                " input")
        for kind in registered_kinds:      # validate whole before writing any
            if kind in kinds:
                raise TAT_InternalError(
                    f"kind {kind!r} is already registered by"
                    f" {kinds[kind].__name__}")
        for kind in registered_kinds:
            kinds[kind] = cls
        return cls
    return register


def load(python_packages: list[str]) -> None:
    """Import every package `launch_TAT` received (MODULE_STRUCTURE §2.6):
    importing is what registers."""
    for package in python_packages:
        importlib.import_module(package)
