"""The agents (CONSTRUCT_INTERACTION §4); later the jobs of both kinds, the
messages and the mailboxes (§3), as MODULE_STRUCTURE §4 lists them.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

Key = tuple[int, str | None]            # a seen set's key: a node's identity and what of it was shown


class Agent:
    """One agent of the client process (CONSTRUCT_INTERACTION §4): created
    when its first call or hook reaches TAT, never discarded, told apart
    from the others as an object — `identity` is how the client names it
    (LOGGING.md §3's `agent` field) and `main` whether it is the main
    conversation.  `seen` is what a class has shown this agent once, under
    keys of the class's choosing (PRINT.md §4); `Conversation.forget`
    removes a key from every agent's, and a compaction clears this one's.
    `working_calls` counts its TAT tool calls whose bodies are running: the
    tool boundary holds `working()` around each body, from before it is
    spawned until it ends, whatever the client did meanwhile
    (MODULE_STRUCTURE §4.6)."""

    def __init__(self, identity: str, main: bool):
        self.identity = identity
        self.main = main
        self.seen: set[Key] = set()
        self.working_calls = 0

    @contextmanager
    def working(self) -> Generator[None]:
        """One of the agent's TAT tool calls, for as long as its body runs."""
        self.working_calls += 1
        try:
            yield
        finally:
            self.working_calls -= 1
