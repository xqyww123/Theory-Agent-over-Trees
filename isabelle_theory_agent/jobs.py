"""The agents (CONSTRUCT_INTERACTION §4); later the jobs of both kinds, the
messages and the mailboxes (§3), as MODULE_STRUCTURE §4 lists them.
"""

from __future__ import annotations


class Agent:
    """One agent of the client process (CONSTRUCT_INTERACTION §4): created
    when its first call or hook reaches TAT, never discarded, told apart
    from the others as an object — `identity` is how the client names it
    (LOGGING.md §3's `agent` field) and `main` whether it is the main
    conversation.  `working_calls` counts its TAT tool calls whose bodies
    are still running: raised by the tool boundary as soon as
    `agent_of_call` names the agent, lowered when the body ends, whatever
    the client did meanwhile (MODULE_STRUCTURE §4.6)."""

    def __init__(self, identity: str, main: bool):
        self.identity = identity
        self.main = main
        self.working_calls = 0
