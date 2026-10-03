"""What a case that runs without Isabelle builds in place of the product's
start: a `Log` and an `Ending` on the case's temporary directory, and a
`Conversation` on them.  `conftest.py`'s autouse fixture sets `directory`
for every case, so no `Log` ever writes into the repository."""

import logging
from pathlib import Path

from isabelle_theory_agent.log import Log
from isabelle_theory_agent.mcp_server import Ending
from isabelle_theory_agent.model import Conversation

LOGGER = "tat.test"
directory: Path | None = None           # the case's; set by conftest.py


def log() -> Log:
    """A `Log` into the case's temporary directory."""
    assert directory is not None, "a Log is built inside a case"
    directory.mkdir(exist_ok=True)
    return Log(directory, logging.getLogger(LOGGER))


def ending() -> Ending:
    return Ending(log())


def conversation(conn) -> Conversation:
    """A `Conversation` for a case that touches no working directory."""
    the_log = log()
    return Conversation(conn, Path("."), the_log, Ending(the_log))
