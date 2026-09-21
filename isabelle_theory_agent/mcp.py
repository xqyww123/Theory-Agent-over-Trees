"""The tools of MCP_SPECIFICATION §1 (MODULE_STRUCTURE §4.6): `tools`
builds what the server advertises and runs for one conversation, and
`on_compaction` what `/on-compaction` does for it.
"""

from __future__ import annotations

from collections.abc import Callable

from .mcp_server import Tool
from .model import BRIEFING, Forest
from .plugin import Loaded


def tools(forest: Forest, loaded: Loaded) -> list[Tool]:
    """Empty until the tools land."""
    return []


def on_compaction(forest: Forest) -> Callable[[], str]:
    """The agent's context was replaced (PRINT.md §4, §5): forget what it
    was shown, and give its client the briefing."""
    def briefing() -> str:
        forest.conversation.seen.clear()
        return forest.render(forest, BRIEFING)
    return briefing
