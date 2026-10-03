"""What a case that runs without Isabelle builds in place of the product's
start: a `Log` and an `Ending` on the case's temporary directory, and a
`Conversation` on them.  `conftest.py`'s autouse fixture sets `directory`
for every case, so no `Log` ever writes into the repository.  `records`
reads a log back, the case's or a conversation's."""

import json
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


def records(category: str, log_directory: Path | None = None) -> list[dict]:
    """The records of one category's file, each line parsed on its own
    (LOGGING.md §6); the case's log by default, none when the file is not
    there."""
    base = log_directory if log_directory is not None else directory
    assert base is not None, "a log directory: the case's, or a conversation's"
    path = base / f"{category}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_bytes().split(b"\n") if line]


def events(category: str, log_directory: Path | None = None) -> list[str]:
    return [r["event"] for r in records(category, log_directory)]
