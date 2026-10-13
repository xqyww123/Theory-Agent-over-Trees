"""What a case that runs without Isabelle builds in place of the product's
start: a `Log` and an `Ending` on the case's temporary directory, and a
`Conversation` on them; a `Recorder` in place of the RPC connection, and
the RPC host's cancellation of a task.  `conftest.py`'s autouse fixture
sets `directory` for every case, so no `Log` ever writes into the
repository.  `records` reads a log back, the case's or a conversation's."""

import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from isabelle_theory_agent.jobs import Agent
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


class Recorder:
    """What `launch_TAT` says to the Isabelle side — the round trips,
    answered with nothing; `served` once `TAT.serving` arrives, and the
    lock's text at that moment, when the launcher may start the client;
    the RPC host's logger, which the `Log` reports to."""
    def __init__(self):
        self.calls: list[tuple[str, Any]] = []
        self.served = asyncio.Event()
        self.lock: str | None = None
        self.server = SimpleNamespace(logger=logging.getLogger(LOGGER))

    async def callback(self, name: str, args: Any) -> None:
        self.calls.append((name, args))
        if name == "TAT.serving":
            _, agent_directory, _ = args          # the lock lies beside the agent directory
            self.lock = (Path(agent_directory).parent / "tat.lock").read_text()
            self.served.set()


async def cancelled_by_the_host(task: asyncio.Task) -> None:
    """The RPC host cancelling the task, as when its connection closes."""
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def working_directory() -> Path:
    """The case's working directory, beside its log under the case's
    temporary directory: a `Theory`'s beginning makes its session's folder
    there, never in the repository."""
    assert directory is not None, "a working directory is built inside a case"
    path = directory.parent / "work"
    path.mkdir(parents=True, exist_ok=True)
    return path


def conversation(conn) -> Conversation:
    """A `Conversation` for a case that runs without Isabelle."""
    the_log = log()
    return Conversation(conn, working_directory(), the_log, Ending(the_log))


def agent(conversation: Conversation, identity: str = "main", main: bool = True) -> Agent:
    """The conversation's agent of that identity, created as the server
    would create it: the main conversation unless the case says otherwise."""
    return conversation.agents.setdefault(identity, Agent(identity, main))


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
