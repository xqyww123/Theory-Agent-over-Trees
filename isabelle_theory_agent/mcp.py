"""The tools of MCP_SPECIFICATION §1 (MODULE_STRUCTURE §4.6): `tools`
builds what the server advertises and runs for one conversation.
"""

from __future__ import annotations

from .mcp_server import Tool
from .model import Forest
from .plugin import Loaded


def tools(forest: Forest, loaded: Loaded) -> list[Tool]:
    """Empty until the tools land."""
    return []
