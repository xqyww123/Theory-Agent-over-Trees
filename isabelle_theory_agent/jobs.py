"""The agents (CONSTRUCT_INTERACTION §4), the messages and the mailboxes
(§3.4), the construction jobs with their questions (§3.1, §3.2), the
evaluation jobs (§3.3) with their wire — the process's table from a
job's id to the job, and the remote procedure `job_finished` the ML side
reports a job's end through — and what a node still owes (`Unfinished`,
ARCHITECTURE §3.2), as MODULE_STRUCTURE §4 lists them.
"""

from __future__ import annotations

import asyncio
import itertools
import json
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Iterable, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol, Self, final

from Isabelle_RPC_Host import Connection, isabelle_remote_procedure

from . import isabelle_driver
from .exceptions import BadAnswer, TAT_InternalError
from .log import current_agent

if TYPE_CHECKING:
    from .log import Log, _Job
    from .model import Conversation, Forest, JSON_Schema, Node

Key = tuple[int, str | None]            # a seen set's key: a node's identity and what of it was shown


class Agent:
    """One agent of the client process (CONSTRUCT_INTERACTION §4): created
    when its first call or hook reaches TAT, never discarded, told apart
    from the others as an object — `identity` is how the client names it
    (LOGGING.md §3's `agent` field) and `main` whether it is the main
    conversation.  `seen` is what a class has shown this agent once, under
    keys of the class's choosing (PRINT.md §4); `Conversation.forget`
    removes a key from every agent's, and a compaction clears this one's.
    `mailbox` holds the messages posted to it and not yet delivered
    (§3.4); a change to it wakes the agent.  `working_calls` counts its TAT
    tool calls whose bodies are running: the tool boundary holds
    `working()` around each body, from before it is spawned until it ends,
    whatever the client did meanwhile (MODULE_STRUCTURE §4.6)."""

    def __init__(self, identity: str, main: bool):
        self.identity = identity
        self.main = main
        self.seen: set[Key] = set()
        self.mailbox: list[Message] = []
        self.working_calls = 0
        self._woken = asyncio.Event()

    @contextmanager
    def working(self) -> Generator[None]:
        """One of the agent's TAT tool calls, for as long as its body runs."""
        self.working_calls += 1
        try:
            yield
        finally:
            self.working_calls -= 1

    def wake(self) -> None:
        """A change to the agent's mailbox or its jobs: whoever sleeps on the
        agent goes on."""
        self._woken.set()

    async def sleep_until(self, holds: Callable[[], bool]) -> None:
        """Until `holds()`, tested now and after every wake-up — with no
        await between the test and the sleep, so no wake-up is lost however
        this is called."""
        while not holds():
            self._woken.clear()
            await self._woken.wait()


# --- messages (CONSTRUCT_INTERACTION §3.4)

class Subject(Protocol):
    """What a message is about — an evaluation job, or a construction
    job's run — asked at delivery whether the message still stands."""

    def dropped_for(self, message: Message) -> str | None:
        """Why delivery drops the message, or None while it stands."""
        ...


@dataclass(frozen=True)
class Message:
    """A message: its recipient, its text, whether it interrupts the
    recipient's `check_construct`, and optionally what it is about — an
    evaluation job, or a construction job's run — and the question it
    carries."""
    recipient: Agent
    text: str
    interrupts: bool
    subject: Subject | None = None
    question: Interactive_Question | None = None
    failure: Failure | None = None


@dataclass(frozen=True)
class Failure:
    """What a failure notification carries for its delivery-time merge
    (§3.4), fixed at posting so the merge needs no live job: the class that
    words it, the node it is for, whether the failure started that node's
    construction."""
    job_class: type[Evaluation_Job]
    node_id: str
    automatic: bool


def post(log: Log, message: Message) -> None:
    """Put a message into its recipient's mailbox, and wake the recipient;
    anything may post one.  It is delivered with the recipient's next tool
    result (`deliver`)."""
    message.recipient.mailbox.append(message)
    log.job.message_posted(
        recipient=message.recipient.identity,
        kind="notification" if message.question is None else "question",
        source=repr(message.subject) if message.subject is not None else None,
        interrupts=message.interrupts, text=message.text)
    message.recipient.wake()


def _dropped_for(message: Message) -> str | None:
    """Why delivery would drop the message now, or None while it stands."""
    return message.subject.dropped_for(message) if message.subject is not None else None


def waiting(agent: Agent) -> list[str]:
    """The texts the agent's mailbox would deliver now, oldest first, as
    `deliver` would compose them; they stay there."""
    return _merged_failures([message for message in agent.mailbox if _dropped_for(message) is None])


def deliver(log: Log, agent: Agent) -> list[str]:
    """Take the agent's mailbox: the texts its tool result carries after the
    body's, less each message its subject says no longer stands — a run no
    longer its job's, a question no longer pending — recorded
    `message_dropped` (§3.4).  Called by the tool boundary alone, past its
    cancellation checkpoint (MODULE_STRUCTURE §4.6)."""
    messages, agent.mailbox = agent.mailbox, []
    delivered: list[Message] = []
    for message in messages:
        reason = _dropped_for(message)
        if reason is None:
            delivered.append(message)
            log.job.message_delivered(recipient=agent.identity)
        else:
            log.job.message_dropped(recipient=agent.identity, reason=reason)
    return _merged_failures(delivered)


# --- construction jobs (CONSTRUCT_INTERACTION §3.1, §3.2)

class Not_Started:
    """The job never ran, or its last run was cancelled; `NOT_STARTED` is
    its one value."""

    def __repr__(self) -> str:
        return "NOT_STARTED"


class Running:
    """The work is in flight — a construction job's run is the job's, an
    evaluation job's report has not come; `RUNNING` is its one value."""

    def __repr__(self) -> str:
        return "RUNNING"


@dataclass(frozen=True)
class Succeeded:
    """The run's product, the class's: a MessagePack-representable value
    (§3.1)."""
    product: Any


@dataclass(frozen=True)
class Failed:
    message: str


NOT_STARTED = Not_Started()
RUNNING = Running()
Outcome = Not_Started | Running | Succeeded | Failed
Settled = Succeeded | Failed             # what a run returns

Cancel_Reason = Literal["NODE_DELETED", "NODE_AMENDED", "CONTEXT_CHANGED"]


def job_image(outcome: Outcome) -> list[Any]:
    """The store's `job` row (§3.1; ARCHITECTURE §4.1): a tag and an
    optional value — the product, or the failure's message.  `RUNNING` is
    written as `NOT_STARTED`, so a loaded forest holds no run."""
    match outcome:
        case Succeeded(product):
            return ["SUCCEEDED", product]
        case Failed(message):
            return ["FAILED", message]
        case _:
            return ["NOT_STARTED"]


def job_of_image(row: Any) -> Outcome | None:
    """The outcome a `job` row holds; None for a row of no known shape."""
    match row:
        case ["NOT_STARTED"]:
            return NOT_STARTED
        case ["SUCCEEDED", product]:
            return Succeeded(product)
        case ["FAILED", str(message)]:
            return Failed(message)
        case _:
            return None


class Interactive_Question(ABC):
    """A question a construction job's run asks its owner (§3.4),
    subclassed by the job class: `text` is what the owner reads; `schema`
    an object schema for the answer, within the tool schemas' grammar
    (MODULE_STRUCTURE §4.4), validated in `ask` and substituted for the
    `answer` tool's `answer` property at answer time."""
    text: str
    schema: JSON_Schema

    @abstractmethod
    def receive(self, answer: Any) -> Answered | Interactive_Question:
        """Judge a shape-valid answer.  `Answered(response)` accepts it —
        keep what the job needs on `self`; `response` is the `answer`
        tool's text, None for the framework's default.  A question
        returned is asked instead: it replaces this one as the pending
        question and is delivered in the same tool result.  `BadAnswer`
        raised refuses it: this question stays pending."""


@dataclass(frozen=True)
class Answered:
    response: str | None = None


def series(words: list[str], last: str) -> str:
    """Words joined with commas and `last` before the last: `A`; `A and B`;
    `A, B and C`."""
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + f" {last} " + words[-1]


def on_each(ids: list[str]) -> str:
    """`on \\`A\\``; `on \\`A\\` and on \\`B\\``; `on \\`A\\`, on \\`B\\` and on
    \\`C\\`` (§5)."""
    return series([f"on `{id}`" for id in ids], "and")


def listed(ids: list[str], sentence: Callable[[str], str], header: str) -> str:
    """§5's forms for the nodes `ids` name: up to three in one sentence —
    `sentence` given `on_each`'s phrase — more as `header` over one full
    id per line."""
    if len(ids) <= 3:
        return sentence(on_each(ids))
    return header + "\n" + "\n".join(f"  - {id}" for id in ids)


def phrased(cls: Job_Class, ids: list[str], opening: str, tail: str, plural_tail: str | None = None) -> str:
    """§5's two forms for the nodes `ids` name under the job class `cls`:
    `{opening} {title} {on}{tail}.` for up to three, `{opening} following
    {plural title}{plural_tail}:` over one id per line for more — the
    opening with its article (`Started the`, `The`), `plural_tail` the
    tail's plural when it has one."""
    return listed(ids, lambda on: f"{opening} {cls.title()} {on}{tail}.",
                  f"{opening} following {cls.title(plural=True)}{tail if plural_tail is None else plural_tail}:")


def with_message(header: str, message: str) -> str:
    """A header over a message on the lines below, two spaces deeper (§6):
    the header as the documents write it, ending in a colon — which a
    period replaces when the message is empty, nothing below."""
    if not header.endswith(":"):
        raise TAT_InternalError(f"a failure header ends in a colon: {header!r}")
    if not message:
        return header[:-1] + "."
    return header + "\n" + "\n".join("  " + line for line in message.splitlines())


class _Run:
    """One run of a construction job — the subject of the run's messages
    (§3.4): a message stands unless the run was cancelled, so is no
    longer its job's, or its question, if it carries one, is no longer
    the job's pending question.  `attach` is an evaluation job attached
    from inside the run, applied at its settlement and gone with it
    (§3.3)."""

    def __init__(self, job: Construction_Job):
        self.job = job
        self.task: asyncio.Task[None] | None = None
        self.cancelled = False
        self.attach: Evaluation_Job | None = None

    def dropped_for(self, message: Message) -> str | None:
        if self.cancelled:
            return "the run is no longer its job's"
        if message.question is not None and self.job.pending_question is not message.question:
            return "the question is no longer its job's pending question"
        return None

    def __repr__(self) -> str:
        return f"run of the {self.job.title()} on `{self.job.node_id}`"


# The run whose code is running: set by the wrapper, inherited by the tasks
# the run spawns, None outside every run (§3.3's "from inside a run").
_run_here: ContextVar[_Run | None] = ContextVar("tat_run", default=None)


def current_run() -> _Run | None:
    return _run_here.get()


class Construction_Job(ABC):
    """The job `construct` starts on a node (CONSTRUCT_INTERACTION §3.2),
    built with the node by the framework (`cls(node)`).  A class gives
    the work, `_run`, its words and its two hooks; the framework owns the
    outcome, the run and its question.  A run is the job's from `start`
    until it settles or is cancelled; every legitimate cancellation
    detaches it first, so a run that is no longer the job's is one
    somebody cancelled."""

    compulsory: ClassVar[bool] = True       # the forest is not complete without the job

    def __init__(self, node: Node):
        self.node = node
        self.outcome: Outcome = NOT_STARTED
        self.auto_construct = False          # written by `edit`, `construct` and `cancel_construct` (§3.2)
        self.owner: Agent | None = None      # the agent whose `start` the last run was
        self.pending_question: Interactive_Question | None = None
        self._current: _Run | None = None    # the job's run; None when none is
        self._runs: set[asyncio.Task[None]] = set()     # every run's task not yet unwound
        self._answered: asyncio.Future[None] | None = None   # what `ask` waits on
        # recorded at `start`, for the steps that may happen off the forest
        self._conversation: Conversation | None = None
        self._id = ""

    @property
    def node_id(self) -> str:
        """The node's full id as the forest gives it; once the node has left
        the forest, the id recorded at `start`.  For logs and bugs, stable;
        the sentences the agent reads use `shown_id`."""
        return self.node.current_id() or self._id

    @property
    def shown_id(self) -> str:
        """The node's id in its shortest unambiguous form, for the sentences
        the agent reads (MCP_SPECIFICATION §2.1, PRINT §3); the recorded
        full id once the node has left the forest."""
        node = self.node
        return node.forest().id_of(node) if node.current_id() is not None else self._id

    # --- the class's (§3.2)

    @classmethod
    @abstractmethod
    def title(cls, plural: bool = False) -> str:
        """The words for the work: `proof construction`."""

    @classmethod
    @abstractmethod
    def failure_header(cls, failure: Failed) -> str | None:
        """The header of the job's failure block (§6), printed while the
        outcome is `FAILED`; None prints nothing."""

    @abstractmethod
    async def _run(self) -> Settled:
        """The work; returns the outcome.  A cancellation propagates out of
        it: its `try/finally` is its cleanup, which never starts a round
        trip on the ending's path (MODULE_STRUCTURE §4.3)."""

    def _check(self) -> bool:
        """The class's own condition for a start: whether the job can be
        started on the node as it stands.  True by default."""
        return True

    def _on_context_change(self) -> None:
        """The node's own evaluation status was written by the walk while
        the job runs — a rerun's rewrite of `ready` included; called as a
        completed hook is (MODULE_STRUCTURE §4.1).  Cancels the job by
        default; a class that can carry on overrides it and reads the
        node's status itself."""
        self.cancel("CONTEXT_CHANGED")

    # --- the wording, composed from `title` unless the class says otherwise

    @classmethod
    def starting_notice(cls, ids: list[str]) -> str:
        return phrased(cls, ids, "Started the", "; call `check_construct` before you exit")

    @classmethod
    def cancelling_notice(cls, ids: list[str]) -> str:
        return phrased(cls, ids, "Cancelled the", "")

    @final
    @classmethod
    def automatic_notice(cls, ids: list[str]) -> str:
        """The framework's line for the constructions an evaluation started
        automatically (§5): `construct`'s forms opened with `Automatically
        started`."""
        return phrased(cls, ids, "Automatically started the", "; call `check_construct` before you exit")

    def answered_notice(self) -> str:
        return f"Answered the {self.title()} on `{self.shown_id}`; call `check_construct` before you exit."

    def owned_by_another_refusal(self) -> str:
        return f"The {self.title()} on `{self.shown_id}` belongs to another agent."

    def finished_notification(self, outcome: Settled) -> str:
        head = f"The {self.title()} on `{self.shown_id}`"
        if isinstance(outcome, Succeeded):
            return head + " succeeded."
        return with_message(head + " failed:", outcome.message)

    def cancelled_notification(self, reason: Cancel_Reason) -> str:
        why = {"NODE_DELETED": "the node was deleted.", "NODE_AMENDED": "the node was amended.",
               "CONTEXT_CHANGED": "its context changed."}[reason]
        return f"The {self.title()} on `{self.shown_id}` was cancelled: {why}"

    # --- the framework's

    @final
    def can_start(self) -> bool:
        return self.outcome is not RUNNING and self._check()

    @final
    def start(self, owner: Agent) -> None:
        """Called only when `can_start()` (§3.2), synchronous: the owner
        recorded, `RUNNING`, the node stored in a transaction of its own,
        the run spawned through the ending (§9); the owner is woken, its
        jobs having changed."""
        if not self.can_start():
            raise TAT_InternalError(f"the {self.title()} on `{self.node_id}` cannot be started now")
        forest = self.node.forest()
        self._conversation, self._id = forest.conversation, forest.full_id(self.node)
        self.owner = owner
        self.node.drop_evaluation_job("construction_start")
        self.node._clear_check()
        self.outcome = RUNNING
        self._store()
        self._log.construction_started(node=self.node_id, owner=owner.identity)
        earlier = [task for task in self._runs if not task.done()]
        run = self._current = _Run(self)
        run.task = self._conversation.ending.spawn(self._running(run, owner, earlier, forest.construction_slot()))
        self._runs.add(run.task)
        run.task.add_done_callback(self._runs.discard)
        owner.wake()

    @final
    async def _running(self, run: _Run, owner: Agent, earlier: list[asyncio.Task[None]],
                       slot: Any) -> None:
        """The wrapper around `_run` (§3.2), in order: the log's agent is the
        owner, and the run is the one `current_run` names here and in every
        task it spawns; every earlier run of the job is waited for to
        unwind; the work, under the bound on runs (`slot`); then one
        question — is the run still the job's?  A run that is settles
        itself; one that is not was cancelled, and nothing is done.
        Anything raised while the run is the job's — a cancellation it
        brought on itself included — is a bug and enters the ending; so is
        a cleanup that raised after a cancellation."""
        try:
            current_agent.set(owner.identity)
            _run_here.set(run)
            if earlier:
                await asyncio.wait(earlier)
            async with slot:
                result = await self._run()
            if self._current is run:
                self._settle(run, result)
        except asyncio.CancelledError:
            if self._current is run:
                self._bug(TAT_InternalError(f"the run of the {self.title()} on `{self.node_id}` cancelled itself"))
            raise
        except Exception as bug:
            self._bug(bug)

    @final
    def _settle(self, run: _Run, outcome: Settled) -> None:
        """A run that ended on its own, in one synchronous stretch under no
        lock (§3.2): the outcome recorded, the pending question withdrawn,
        an attach made from inside the run applied (§3.3), the node stored
        once, `finished_notification` posted to the owner, who wakes."""
        if not isinstance(outcome, (Succeeded, Failed)):
            raise TAT_InternalError(f"{type(self).__name__}._run returned {outcome!r}, which is no outcome")
        self.outcome = outcome
        self._current = None
        self._withdraw()
        if run.attach is not None:
            self.node._attach_now(run.attach)
        self._store()
        self._log.construction_settled(node=self.node_id, outcome=job_image(outcome)[0],
                                       message=outcome.message if isinstance(outcome, Failed) else None)
        post(self._log_of_conversation, Message(self._owned_by(), self.finished_notification(outcome),
                                                interrupts=True))

    @final
    def cancel(self, reason: Cancel_Reason | None) -> None:
        """Synchronous (§3.2): the run detached, its pending question
        withdrawn, `NOT_STARTED`, the task cancelled.  `reason` says why
        the framework cancels — the owner is then told, even when the
        owner deleted or amended the node itself; `cancel_construct` and
        the ending pass None, and nothing is told.  Writes nothing: the
        image it leaves is the one stored.  Nothing to cancel when no run
        is the job's."""
        if self.outcome is not RUNNING:
            return
        run, self._current = self._current, None
        self._withdraw()
        self.outcome = NOT_STARTED
        if run is not None:                      # its attach goes with it (§3.3)
            run.cancelled = True
            if run.task is not None:
                run.task.cancel()
        self._log.construction_cancelled(node=self.node_id, reason=reason)
        owner = self._owned_by()
        if reason is not None:
            post(self._log_of_conversation, Message(owner, self.cancelled_notification(reason), interrupts=True))
        else:
            owner.wake()

    @final
    async def ask(self, question: Interactive_Question) -> None:
        """For `_run` (§3.4): the question's schema validated — a failure is
        a bug in `_run` — the question posted to the owner's mailbox as the
        job's pending question, and the run suspended until some `receive`
        accepts an answer; the job then reads its data off the question.  A
        cancellation while it waits withdraws the question.  A job has at
        most one pending question, and a run asks only while it is the
        job's: an `ask` otherwise is a bug of `_run`."""
        run = current_run()
        if run is None or run is not self._current:
            raise TAT_InternalError(f"the {self.title()} on `{self.node_id}` asks a question from no run of its")
        if self.pending_question is not None:
            raise TAT_InternalError(f"the {self.title()} on `{self.node_id}` asks while a question is pending")
        self._post_question(question, run)
        answered = self._answered = asyncio.get_running_loop().create_future()
        try:
            await answered
        finally:
            if self._answered is answered:
                self._answered = None
                self._withdraw()

    @final
    def receive_answer(self, value: Any) -> str | None:
        """The `answer` tool's judgement of a shape-valid answer to the
        pending question (§3.4, §5): `receive` accepts it — the pending
        question cleared, the `ask` released, the result the question's
        response or `answered_notice` — refuses it with `BadAnswer`, which
        propagates and leaves the question pending, or asks instead — the
        new question pending and posted, the result None."""
        question = self.pending_question
        if question is None:
            raise TAT_InternalError(f"the {self.title()} on `{self.node_id}` has no pending question to answer")
        try:
            judged = question.receive(value)
        except BadAnswer:
            self._log.question_answered(node=self.node_id, outcome="refused")
            raise
        if isinstance(judged, Answered):
            self.pending_question = None
            if self._answered is not None and not self._answered.done():
                self._answered.set_result(None)
            self._log.question_answered(node=self.node_id, outcome="accepted")
            return judged.response if judged.response is not None else self.answered_notice()
        if isinstance(judged, Interactive_Question):
            if judged is question:
                raise TAT_InternalError(f"{type(question).__name__}.receive returned the pending question itself")
            self._log.question_answered(node=self.node_id, outcome="replaced")
            assert self._current is not None             # a pending question has a run
            self._post_question(judged, self._current)
            return None
        raise TAT_InternalError(f"{type(question).__name__}.receive returned {judged!r}")

    @final
    def repeat_question(self) -> None:
        """The pending question posted to the owner again when the mailbox
        no longer holds it — one entry per job at most (§5)."""
        question = self.pending_question
        if question is None:
            return
        assert self._current is not None             # a pending question has a run
        if not any(m.question is question for m in self._owned_by().mailbox):
            self._post(question, self._current)

    @final
    def question_message(self, question: Interactive_Question) -> str:
        """The delivered form of a question (§3.4)."""
        return (f"The {self.title()} on `{self.shown_id}` asks:\n{question.text}\n"
                f"Answer with the `answer` tool, node_id `{self.shown_id}`; the answer must follow the JSON schema:\n"
                + json.dumps(question.schema, indent=2))

    @final
    def _post_question(self, question: Interactive_Question, run: _Run) -> None:
        """A question validated and made the job's pending question, posted
        to the owner from `run`."""
        from .plugin import validate_call_schema      # plugin imports model, which imports this module
        where = f"the question of the {self.title()} on `{self.node_id}`"
        validate_call_schema(question.schema, where)
        if "$defs" in question.schema:                # it stands in for `answer`'s property, which has none
            raise TAT_InternalError(f"{where}: the schema carries `$defs`")
        self.pending_question = question
        self._post(question, run)

    def _post(self, question: Interactive_Question, run: _Run) -> None:
        post(self._log_of_conversation, Message(self._owned_by(), self.question_message(question),
                                                interrupts=True, subject=run, question=question))

    @final
    def _withdraw(self) -> None:
        """The pending question withdrawn (§3.4): cleared,
        `question_withdrawn`, the `ask` waiting on it cancelled, so a stray
        asking branch ends with it; nothing when none is pending.  No
        mailbox is touched: delivery drops the question."""
        if self.pending_question is None:
            return
        self.pending_question = None
        self._log.question_withdrawn(node=self.node_id)
        if self._answered is not None and not self._answered.done():
            self._answered.cancel()

    @final
    def _carry_from(self, old: Construction_Job) -> None:
        """An amend's commit copying the replaced node's job image (§3.1):
        the old outcome, `RUNNING` read as `NOT_STARTED`."""
        self.outcome = old.outcome if isinstance(old.outcome, (Succeeded, Failed)) else NOT_STARTED

    @final
    def _store(self) -> None:
        self.node._store_alone()

    @final
    def _bug(self, bug: BaseException) -> None:
        self._conversation_of().ending.end(bug)

    def _conversation_of(self) -> Conversation:
        if self._conversation is None:
            raise TAT_InternalError(f"the {self.title()} was never started")
        return self._conversation

    @property
    def _log_of_conversation(self) -> Log:
        return self._conversation_of().log

    @property
    def _log(self) -> _Job:
        return self._conversation_of().log.job

    def _owned_by(self) -> Agent:
        if self.owner is None:
            raise TAT_InternalError(f"the {self.title()} on `{self.node_id}` has no owner")
        return self.owner


# --- evaluation jobs (CONSTRUCT_INTERACTION §3.3)

class Passed:
    """The check passed; `PASSED` is its one value."""

    def __repr__(self) -> str:
        return "PASSED"


PASSED = Passed()
Check_Outcome = Running | Passed | Failed
Stored_Check = Passed | Failed            # what the node keeps of a settled check (the `check` row)

Dropped_By = Literal["status_write", "delete", "amend", "construction_start", "attached", "ending"]


def check_image(outcome: Stored_Check) -> list[Any]:
    """The store's `check` row (ARCHITECTURE §4.1): a tag and, for a
    failure, its message; a node without a stored check has no row."""
    return ["FAILED", outcome.message] if isinstance(outcome, Failed) else ["PASSED"]


def check_of_image(row: Any) -> Stored_Check | None:
    """The stored check a `check` row holds; None for a row of no known
    shape."""
    match row:
        case ["PASSED"]:
            return PASSED
        case ["FAILED", str(message)]:
            return Failed(message)
        case _:
            return None


class Evaluation_Job(ABC):
    """The job an evaluation starts on a node it passes (CONSTRUCT_INTERACTION
    §3.3): the class builds it, does the work through its own ML callback
    and writes `outcome`; the framework attaches it, starts it, reads the
    outcome and drops it.  The job holds a process-unique `id` from its
    making; it is in the process's table only from its start
    (`start_evaluation_job`, which `register`s it just before the work
    begins) until its report or drop, so a report for a dropped job is
    nobody's (§3.3)."""

    def __init__(self, node: Node, starter: Agent | None):
        self.node = node
        self.starter = starter                   # None when never started
        self.id = next(_ids)
        self.outcome: Check_Outcome = RUNNING
        self._ended = asyncio.Event()            # settled by its report, or dropped
        self.started_construction = False        # its failure started the node's construction (§3.3)
        forest = node.forest()
        self.conversation: Conversation = forest.conversation
        self._id = forest.full_id(node)

    @property
    def node_id(self) -> str:
        """The node's full id as the forest gives it; once the node has left
        the forest, the id recorded when the job was built.  For logs,
        stable; the agent's sentences use `shown_id`."""
        return self.node.current_id() or self._id

    @property
    def shown_id(self) -> str:
        """The node's id in its shortest unambiguous form, for the sentences
        the agent reads (MCP_SPECIFICATION §2.1, PRINT §3); the recorded
        full id once the node has left the forest."""
        node = self.node
        return node.forest().id_of(node) if node.current_id() is not None else self._id

    @property
    def ended(self) -> bool:
        """Settled by its report, or dropped (§3.3)."""
        return self._ended.is_set()

    @final
    def mark_ended(self) -> None:
        self._ended.set()

    @final
    async def wait_ended(self) -> None:
        """Until the job has ended — `blocking`'s wait (§5)."""
        await self._ended.wait()

    @classmethod
    @abstractmethod
    def title(cls, plural: bool = False) -> str:
        """The words for the work: `proof check`."""

    @classmethod
    def make(cls, node: Node, starter: Agent | None) -> Self:
        """Builds the instance and begins nothing; a class whose constructor
        takes more overrides it."""
        return cls(node, starter)

    @abstractmethod
    async def _start(self) -> None:
        """Begin the work through the class's own ML callback, passing
        `self.id`, and return at once."""

    def _finished(self, errors: list[str]) -> None:
        """The ML report, synchronously, under no lock: `PASSED` on no
        errors, else `FAILED` with the errors joined by newlines."""
        self.outcome = PASSED if not errors else Failed("\n".join(errors))

    @classmethod
    @abstractmethod
    def failure_header(cls, failure: Failed) -> str | None:
        """The header of the check's failure block (§6), printed from a
        `FAILED` check's outcome whether or not a job is on the node; None
        prints nothing."""

    @classmethod
    @abstractmethod
    def failure_notification(cls, ids: list[str], automatic: bool) -> str:
        """The sentence its failure sends (§3.4) for these nodes, in §5's
        forms; `automatic` says that the failure started their
        construction."""

    @final
    def _report(self, errors: list[str]) -> None:
        """The report's body, run only for a job the table still held — one
        still on its node, since a drop discards it (§3.3): `_finished`, the
        outcome stored as the node's check in a transaction of its own,
        `evaluation_reported`, a failure posted to the starter — not
        interrupting, merged at delivery with the class's others; carrying
        no job when the failure starts the node's construction under
        automatic construction (§3.4), which the body then does, the
        starter its owner — the job ended and the starter woken.  An
        outcome left `RUNNING` is a bug."""
        log = self.conversation.log.job
        self._finished(errors)
        outcome = self.outcome
        if not isinstance(outcome, (Passed, Failed)):
            raise TAT_InternalError(f"{type(self).__name__}._finished left the job RUNNING")
        self.node._store_check(outcome)
        log.evaluation_reported(id=self.id, outcome=check_image(outcome)[0], failure=errors or None)
        construction = None
        if isinstance(outcome, Failed) and self.starter is not None:
            job = self.node.job()
            if job is not None and job.auto_construct and job.can_start():
                construction, self.started_construction = job, True
            post(self.conversation.log, Message(
                self.starter, self.failure_notification([self.shown_id], self.started_construction),
                interrupts=False, subject=None if self.started_construction else self,
                failure=Failure(type(self), self.shown_id, self.started_construction)))
            if construction is not None:
                construction.start(self.starter)          # drops this job from its node
        self.mark_ended()
        if self.starter is not None:
            self.starter.wake()

    @final
    def dropped_for(self, message: Message) -> str | None:
        return None if self.node.evaluation_job() is self else "the evaluation job is no longer on its node"

    def __repr__(self) -> str:
        return f"{self.title()} {self.id} on `{self.node_id}`"


async def cancel_jobs(conversation: Conversation, ids: list[int]) -> None:
    """One `cancel(ids)` round trip for dropped jobs' works, recorded
    `cancel_sent` (§3.3; MODULE_STRUCTURE §2.4)."""
    conversation.log.job.cancel_sent(ids=ids)
    await isabelle_driver.job_cancel(conversation, ids)


async def cancel_jobs_at_once(conversation: Conversation, ids: list[int]) -> None:
    """`cancel_jobs` from synchronous code, in a task of the ending's: what
    it raises ends the conversation, as every spawned task's does."""
    try:
        await cancel_jobs(conversation, ids)
    except Exception as bug:
        conversation.ending.end(bug)


def _merged_failures(messages: list[Message]) -> list[str]:
    """The texts of delivered messages, the failures of one evaluation job
    class merged into one sentence for the nodes whose construction the
    failure started and one for the others (§3.4), each where its first
    message stood."""
    texts: list[str] = []
    groups: dict[tuple[type, bool], tuple[int, list[str]]] = {}
    for message in messages:
        failure = message.failure
        if failure is None:
            texts.append(message.text)
            continue
        key = (failure.job_class, failure.automatic)
        if key in groups:
            groups[key][1].append(failure.node_id)
        else:
            groups[key] = (len(texts), [failure.node_id])
            texts.append("")
    for (cls, automatic), (at, ids) in groups.items():
        texts[at] = cls.failure_notification(ids, automatic)
    return texts


# --- what stands for an agent (CONSTRUCT_INTERACTION §4, §5, §7)

Job = Construction_Job | Evaluation_Job                        # a job of either kind
Job_Class = type[Construction_Job] | type[Evaluation_Job]


@dataclass(frozen=True)
class Standing:
    """An agent's jobs and messages at one moment, read off the forest and
    the mailbox: the construction jobs it owns that wait for its answer
    and that run, the evaluation jobs it started that run, and the
    mailbox's messages that stand.  `check_construct` judges its return
    on it, and the stop rule its answer (§5, §7)."""
    waiting: list[Construction_Job]
    running: list[Construction_Job]
    checks: list[Evaluation_Job]
    messages: list[Message]

    def nothing(self) -> bool:
        """`check_construct` would answer `No job is running.` and deliver
        no message: the stop is allowed (§7)."""
        return not (self.jobs or self.messages)

    @property
    def jobs(self) -> list[Job]:
        return [*self.waiting, *self.running, *self.checks]

    def facts(self) -> dict[str, Any]:
        """The `stop_judged` record's `stands` (LOGGING.md §4)."""
        return {"waiting": [job.node_id for job in self.waiting], "running": [job.node_id for job in self.running],
                "checks": [job.node_id for job in self.checks], "messages": len(self.messages)}


def standings(forest: Forest | None, agents: Iterable[Agent]) -> dict[Agent, Standing]:
    """What stands for each of `agents`, in one pass over the forest (§4) —
    none before the forest is built: a job is an agent's by its owner, a
    check by its starter."""
    waiting: dict[Agent, list[Construction_Job]] = {agent: [] for agent in agents}
    running: dict[Agent, list[Construction_Job]] = {agent: [] for agent in waiting}
    checks: dict[Agent, list[Evaluation_Job]] = {agent: [] for agent in waiting}
    for node in forest._tree_order() if forest is not None else []:
        job = node.job()
        if job is not None and job.outcome is RUNNING and job.owner in waiting:
            (waiting if job.pending_question is not None else running)[job.owner].append(job)
        check = node.evaluation_job()
        if check is not None and check.outcome is RUNNING and check.starter in checks:
            checks[check.starter].append(check)
    return {agent: Standing(waiting[agent], running[agent], checks[agent],
                            [m for m in agent.mailbox if _dropped_for(m) is None]) for agent in waiting}


def standing(forest: Forest | None, agent: Agent) -> Standing:
    return standings(forest, [agent])[agent]


def by_title(jobs: Sequence[Job]) -> list[tuple[str, Job_Class, list[str]]]:
    """The jobs grouped by title, alphabetical: each group's title, the
    class of its first job — which words the group — and its nodes' ids."""
    groups: dict[str, tuple[Job_Class, list[str]]] = {}
    for job in jobs:
        groups.setdefault(type(job).title(), (type(job), []))[1].append(job.shown_id)
    return [(title, *groups[title]) for title in sorted(groups)]


def state_lines(stands: Standing) -> list[str]:
    """`check_construct`'s state lines (§5): the caller's jobs by title and
    situation — construction titles first, each one's waiting then running,
    then evaluation titles — up to three nodes as one sentence, more as a
    header over one id per line, each in its shortest form."""
    lines: list[str] = []
    waiting = {title: (cls, ids) for title, cls, ids in by_title(stands.waiting)}
    running = {title: (cls, ids) for title, cls, ids in by_title(stands.running)}
    for title in sorted(waiting | running):
        if title in waiting:
            lines.append(phrased(*waiting[title], "The", " is waiting for your answer", " are waiting for your answer"))
        if title in running:
            lines.append(phrased(*running[title], "The", " is still running", " are still running"))
    for _, cls, ids in by_title(stands.checks):
        lines.append(phrased(cls, ids, "The", " is still running", " are still running"))
    return lines


BLOCKED = "The `TAT` server blocked your exit:"  # the stop reason's opening line (§7)


def running_titles(stands: Standing) -> str:
    """The titles of the running jobs in their own numbers — construction
    titles first, then evaluation titles, alphabetical within, the same
    title merged — joined with commas and `and` (§7)."""
    def words(jobs: Sequence[Job]) -> list[str]:
        return [cls.title(plural=len(ids) > 1) for _, cls, ids in by_title(jobs)]
    return series(words(stands.running) + words(stands.checks), "and")


def blocked_reason(stands: Standing) -> str | None:
    """The stop hook's reason when the stop is blocked (§7): the opening
    line, the state lines, and one instruction composed from what stands;
    None when the stop is allowed."""
    if stands.nothing():
        return None
    questions = len(stands.waiting)
    the_question = "the questions" if questions > 1 else "the question"
    it = "them" if questions > 1 else "it"
    running = stands.running or stands.checks
    if questions and running:
        instruction = (f"Call `check_construct` to see {the_question} and to wait for the running "
                       f"{running_titles(stands)}; answer {it} before you exit.")
    elif questions:
        instruction = f"Call `check_construct` to see {the_question}; answer {it} before you exit."
    elif running:
        instruction = f"Call `check_construct` to wait for the running {running_titles(stands)} before you exit."
    else:
        instruction = "Call `check_construct` to read your messages before you exit."
    return "\n".join([BLOCKED, *state_lines(stands), instruction])


# --- what a node still owes (ARCHITECTURE §3.2; CONSTRUCT_INTERACTION §3.1)

class Unfinished(ABC):
    """What `_unfinished()` answers when a node owes something — the
    construction, the check, or a check not yet run; `title` the words the
    summary of CONSTRUCT_INTERACTION §6 groups by."""

    @abstractmethod
    def title(self, plural: bool = False) -> str: ...


@dataclass(frozen=True)
class Unfinished_Construction(Unfinished):
    """The construction job's outcome is not `SUCCEEDED`."""
    job: Construction_Job

    def title(self, plural: bool = False) -> str:
        return self.job.title(plural)


@dataclass(frozen=True)
class Unfinished_Check(Unfinished):
    """The check's outcome is `RUNNING` or `FAILED`."""
    outcome: Running | Failed
    job_class: type[Evaluation_Job]

    def title(self, plural: bool = False) -> str:
        return self.job_class.title(plural)


@dataclass(frozen=True)
class Unchecked(Unfinished):
    """The construction succeeded and no check has an outcome."""
    job_class: type[Evaluation_Job]

    def title(self, plural: bool = False) -> str:
        return self.job_class.title(plural)


# --- the evaluation jobs' wire (CONSTRUCT_INTERACTION §3.3; MODULE_STRUCTURE §2.4)

class Reported(Protocol):
    """What the report needs of an evaluation job: its `id` (the table's
    key), the conversation it was made in — the report arrives on a pooled
    connection, which belongs to no conversation — and the body that takes
    the work's errors, none when it passed."""
    id: int
    conversation: Conversation

    def _report(self, errors: list[str]) -> None: ...


# The process's: an id is unique across the conversations a process hosts,
# and a job is in the table from its id's making until its report arrives or
# it is discarded.
_ids = itertools.count(1)
_evaluation_jobs: dict[int, Reported] = {}


def register(job: Reported) -> None:
    """Enter `job` into the table under its id, just before its ML work is
    forked (`start_evaluation_job`, §3.3), so that no report arrives for a
    job the table does not hold; discarded at every drop and at the
    ending."""
    _evaluation_jobs[job.id] = job


def discard(id: int) -> None:
    """Take a job out of the table whose report will not come, or is not
    wanted — every drop and the ending (§3.3); one that is not there is not
    an error."""
    _evaluation_jobs.pop(id, None)


@isabelle_remote_procedure("job_finished")
async def job_finished(arg: tuple[int, list[Any]], connection: Connection) -> None:
    """The ML side's report that an evaluation job's work ended, answered at
    once: the job's id and the failure — `["ok"]`, `["messages", [...]]` or
    `["bug", <message>]`.  The body is synchronous and takes no lock.  A
    report carrying a `Bug` ends the conversation of the job the table
    holds, whatever became of the job; any other is the job's to take, and
    whatever its body raises ends the conversation too.  A report for an
    id the table no longer holds is nobody's, and a conversation that has
    ended hears none."""
    id, failure = arg
    job = _evaluation_jobs.pop(id, None)
    if job is None or job.conversation.ending.entered:      # nobody's, or a conversation that ended
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
