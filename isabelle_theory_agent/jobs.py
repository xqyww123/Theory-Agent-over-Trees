"""The agents (CONSTRUCT_INTERACTION §4) and the evaluation jobs' wire (§3.3):
the process's table from a job's id to the job, and the remote procedure
`job_finished` the ML side reports a job's end through; later the jobs of
both kinds, the messages and the mailboxes (§3), as MODULE_STRUCTURE §4
lists them.
"""

from __future__ import annotations

import itertools
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Protocol

from Isabelle_RPC_Host import Connection, isabelle_remote_procedure

from .exceptions import TAT_InternalError

if TYPE_CHECKING:
    from .model import Conversation

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


# --- the evaluation jobs' wire (CONSTRUCT_INTERACTION §3.3; MODULE_STRUCTURE §2.4)

class Reported(Protocol):
    """What the report needs of an evaluation job: the conversation it was
    made in — the report arrives on a pooled connection, which belongs to
    no conversation — and the body that takes the work's errors, none when
    it passed."""
    conversation: Conversation

    def _report(self, errors: list[str]) -> None: ...


# The process's: an id is unique across the conversations a process hosts,
# and a job is in the table from its id's making until its report arrives or
# it is discarded.
_ids = itertools.count(1)
_evaluation_jobs: dict[int, Reported] = {}


def register(job: Reported) -> int:
    """Enter `job` into the table under a fresh id, which its ML work is
    forked with (`fork_job`): made before any work begins, so no report
    arrives for a job the table does not hold."""
    id = next(_ids)
    _evaluation_jobs[id] = job
    return id


def discard(id: int) -> None:
    """Take a job out of the table whose report will not come, or is not
    wanted; one that is not there is not an error."""
    _evaluation_jobs.pop(id, None)


@isabelle_remote_procedure("job_finished")
async def job_finished(arg: tuple[int, list[Any]], connection: Connection) -> None:
    """The ML side's report that an evaluation job's work ended, answered at
    once: the job's id and the failure — `["ok"]`, `["messages", [...]]` or
    `["bug", <message>]`.  The body is synchronous and takes no lock.  A
    report carrying a `Bug` ends the conversation of the job the table
    holds, whatever became of the job; any other is the job's to take, and
    whatever its body raises ends the conversation too.  A report for an
    id the table no longer holds is nobody's."""
    id, failure = arg
    job = _evaluation_jobs.pop(id, None)
    if job is None:
        return
    try:
        match failure:
            case ["ok"]:
                job._report([])
            case ["messages", [*messages]]:
                job._report([str(message) for message in messages])
            case ["bug", str(message)]:
                raise TAT_InternalError(message)
            case _:
                raise TAT_InternalError(f"job_finished was told {failure!r} of evaluation job {id}")
    except Exception as bug:
        job.conversation.ending.end(bug)
