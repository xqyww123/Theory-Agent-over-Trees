"""The agents (CONSTRUCT_INTERACTION §4), the messages and the mailboxes
(§3.4), the construction jobs with their questions (§3.1, §3.2), what a
node still owes (`Unfinished`, ARCHITECTURE §3.2), and the evaluation
jobs' wire (§3.3): the process's table from a job's id to the job, and
the remote procedure `job_finished` the ML side reports a job's end
through; later the evaluation jobs themselves, as MODULE_STRUCTURE §4
lists them.
"""

from __future__ import annotations

import asyncio
import itertools
import json
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol, final

from Isabelle_RPC_Host import Connection, isabelle_remote_procedure

from .exceptions import BadAnswer, TAT_InternalError
from .log import current_agent

if TYPE_CHECKING:
    from .log import Log, _Job
    from .model import Conversation, JSON_Schema, Node

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

class Source(Protocol):
    """What a message comes from — an evaluation job, or a construction
    job's run — asked at delivery whether the message still stands."""

    def dropped_for(self, message: Message) -> str | None:
        """Why delivery drops the message, or None while it stands."""
        ...


@dataclass(frozen=True)
class Message:
    """A message: its recipient, its text, whether it interrupts the
    recipient's `check_construct`, and optionally what it comes from — an
    evaluation job, or a construction job's run — and the question it
    carries."""
    recipient: Agent
    text: str
    interrupts: bool
    source: Source | None = None
    question: Interactive_Question | None = None


def post(log: Log, message: Message) -> None:
    """Put a message into its recipient's mailbox, and wake the recipient;
    anything may post one.  It is delivered with the recipient's next tool
    result (`deliver`)."""
    message.recipient.mailbox.append(message)
    log.job.message_posted(
        recipient=message.recipient.identity,
        kind="notification" if message.question is None else "question",
        source=repr(message.source) if message.source is not None else None,
        interrupts=message.interrupts, text=message.text)
    message.recipient.wake()


def waiting(agent: Agent) -> list[str]:
    """The texts the agent's mailbox holds, oldest first; they stay there."""
    return [message.text for message in agent.mailbox]


def deliver(log: Log, agent: Agent) -> list[str]:
    """Take the agent's mailbox: the texts its tool result carries after the
    body's, less each message its source says no longer stands — a run no
    longer its job's, a question no longer pending — recorded
    `message_dropped` (§3.4).  Called by the tool boundary alone, past its
    cancellation checkpoint (MODULE_STRUCTURE §4.6)."""
    messages, agent.mailbox = agent.mailbox, []
    texts: list[str] = []
    for message in messages:
        reason = message.source.dropped_for(message) if message.source is not None else None
        if reason is None:
            texts.append(message.text)
            log.job.message_delivered(recipient=agent.identity)
        else:
            log.job.message_dropped(recipient=agent.identity, reason=reason)
    return texts


# --- construction jobs (CONSTRUCT_INTERACTION §3.1, §3.2)

class Not_Started:
    """The job never ran, or its last run was cancelled; `NOT_STARTED` is
    its one value."""

    def __repr__(self) -> str:
        return "NOT_STARTED"


class Running:
    """A run is the job's; `RUNNING` is its one value."""

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


def image(outcome: Outcome) -> list[Any]:
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


def outcome_of_image(row: Any) -> Outcome | None:
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


def on_each(ids: list[str]) -> str:
    """`on \\`A\\``; `on \\`A\\` and on \\`B\\``; `on \\`A\\`, on \\`B\\` and on
    \\`C\\`` (§5)."""
    parts = [f"on `{id}`" for id in ids]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def listed(ids: list[str], sentence: Callable[[str], str], header: str) -> str:
    """§5's forms for the nodes `ids` name: up to three in one sentence —
    `sentence` given `on_each`'s phrase — more as `header` over one full
    id per line."""
    if len(ids) <= 3:
        return sentence(on_each(ids))
    return header + "\n" + "\n".join(f"  - {id}" for id in ids)


def with_message(header: str, message: str) -> str:
    """A header over a message on the lines below, two spaces deeper (§6):
    the header ends in a colon — or, when the message is empty, in a
    period with nothing below."""
    if not message:
        return header + "."
    return header + ":\n" + "\n".join("  " + line for line in message.splitlines())


class _Run:
    """One run of a construction job — the source of the run's messages
    (§3.4): a message stands unless the run was cancelled, so is no
    longer its job's, or its question, if it carries one, is no longer
    the job's pending question."""

    def __init__(self, job: Construction_Job):
        self.job = job
        self.task: asyncio.Task[None] | None = None
        self.cancelled = False

    def dropped_for(self, message: Message) -> str | None:
        if self.cancelled:
            return "the run is no longer its job's"
        if message.question is not None and self.job.pending_question is not message.question:
            return "the question is no longer its job's pending question"
        return None

    def __repr__(self) -> str:
        return f"run of the {self.job.title()} on `{self.job._id}`"


class Construction_Job(ABC):
    """The job `construct` starts on a node (CONSTRUCT_INTERACTION §3.2),
    built with the node by the framework (`cls(node)`).  A class gives
    the work, `_run`, its words and its two hooks; the framework owns the
    outcome, the run and its question.  A run is the job's from `start`
    until it settles or is cancelled; every legitimate cancellation
    detaches it first, so a run that is no longer the job's is one
    somebody cancelled."""

    compulsory: ClassVar[bool] = True       # the forest is not complete without the job
    # the members a class never overrides (PLUGIN_SYSTEM §2, §5)
    FRAMEWORK_MEMBERS: ClassVar[tuple[str, ...]] = (
        "can_start", "start", "cancel", "ask", "receive_answer", "question_message")

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
        self._id = ""                        # the node's id, named by every record and notification

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
        return listed(ids, lambda on: f"Started the {cls.title()} {on}; call `check_construct` before you exit.",
                      f"Started the following {cls.title(plural=True)}; call `check_construct` before you exit:")

    @classmethod
    def cancelling_notice(cls, ids: list[str]) -> str:
        return listed(ids, lambda on: f"Cancelled the {cls.title()} {on}.",
                      f"Cancelled the following {cls.title(plural=True)}:")

    def answered_notice(self) -> str:
        return f"Answered the {self.title()} on `{self._id}`; call `check_construct` before you exit."

    def owned_by_another_refusal(self) -> str:
        return f"The {self.title()} on `{self._id}` belongs to another agent."

    def finished_notification(self, outcome: Settled) -> str:
        head = f"The {self.title()} on `{self._id}`"
        if isinstance(outcome, Succeeded):
            return head + " succeeded."
        return with_message(head + " failed", outcome.message)

    def cancelled_notification(self, reason: Cancel_Reason) -> str:
        why = {"NODE_DELETED": "the node was deleted.", "NODE_AMENDED": "the node was amended.",
               "CONTEXT_CHANGED": "its context changed."}[reason]
        return f"The {self.title()} on `{self._id}` was cancelled: {why}"

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
            raise TAT_InternalError(f"the {self.title()} on `{self._id}` cannot be started now")
        forest = self.node.forest()
        self._conversation, self._id = forest.conversation, forest.full_id(self.node)
        self.owner = owner
        self.outcome = RUNNING
        self._store()
        self._log.construction_started(node=self._id, owner=owner.identity)
        earlier = [task for task in self._runs if not task.done()]
        run = self._current = _Run(self)
        run.task = self._conversation.ending.spawn(self._running(run, owner, earlier, forest.construction_slot()))
        self._runs.add(run.task)
        run.task.add_done_callback(self._runs.discard)
        owner.wake()

    async def _running(self, run: _Run, owner: Agent, earlier: list[asyncio.Task[None]],
                       slot: Any) -> None:
        """The wrapper around `_run` (§3.2), in order: the log's agent is the
        owner; every earlier run of the job is waited for to unwind; the
        work, under the bound on runs (`slot`); then one question — is the
        run still the job's?  A run that is settles itself; one that is not
        was cancelled, and nothing is done.  Anything raised while the run
        is the job's — a cancellation it brought on itself included — is a
        bug and enters the ending; so is a cleanup that raised after a
        cancellation."""
        try:
            current_agent.set(owner.identity)
            if earlier:
                await asyncio.wait(earlier)
            async with slot:
                result = await self._run()
            if self._current is run:
                self._settle(result)
        except asyncio.CancelledError:
            if self._current is run:
                self._bug(TAT_InternalError(f"the run of the {self.title()} on `{self._id}` cancelled itself"))
            raise
        except Exception as bug:
            self._bug(bug)

    def _settle(self, outcome: Settled) -> None:
        """A run that ended on its own, in one synchronous stretch under no
        lock (§3.2): the outcome recorded and stored, the pending question
        withdrawn, `finished_notification` posted to the owner, who wakes."""
        if not isinstance(outcome, (Succeeded, Failed)):
            raise TAT_InternalError(f"{type(self).__name__}._run returned {outcome!r}, which is no outcome")
        self.outcome = outcome
        self._current = None
        self._withdraw()
        self._store()
        # an attach made from inside `_run` is applied here (§3.3; evaluation jobs)
        self._log.construction_settled(node=self._id, outcome=image(outcome)[0],
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
        if run is not None:
            run.cancelled = True
            if run.task is not None:
                run.task.cancel()
        self._log.construction_cancelled(node=self._id, reason=reason)
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
        cancellation while it waits withdraws the question."""
        self._post_question(question)
        self._answered = asyncio.get_running_loop().create_future()
        try:
            await self._answered
        finally:
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
            raise TAT_InternalError(f"the {self.title()} on `{self._id}` has no pending question to answer")
        try:
            judged = question.receive(value)
        except BadAnswer:
            self._log.question_answered(node=self._id, outcome="refused")
            raise
        if isinstance(judged, Answered):
            self.pending_question = None
            if self._answered is not None and not self._answered.done():
                self._answered.set_result(None)
            self._log.question_answered(node=self._id, outcome="accepted")
            return judged.response if judged.response is not None else self.answered_notice()
        if isinstance(judged, Interactive_Question):
            self._log.question_answered(node=self._id, outcome="replaced")
            self._post_question(judged)
            return None
        raise TAT_InternalError(f"{type(question).__name__}.receive returned {judged!r}")

    def question_message(self, question: Interactive_Question) -> str:
        """The delivered form of a question (§3.4)."""
        return (f"The {self.title()} on `{self._id}` asks:\n{question.text}\n"
                f"Answer with the `answer` tool, node_id `{self._id}`; the answer must follow the JSON schema:\n"
                + json.dumps(question.schema, indent=2))

    def _post_question(self, question: Interactive_Question) -> None:
        """The job's pending question, posted to the owner from the run."""
        from .plugin import validate_call_schema      # plugin imports model, which imports this module
        where = f"the question of the {self.title()} on `{self._id}`"
        validate_call_schema(question.schema, where)
        if "$defs" in question.schema:                # it stands in for `answer`'s property, which has none
            raise TAT_InternalError(f"{where}: the schema carries `$defs`")
        if self._current is None:
            raise TAT_InternalError(f"the {self.title()} on `{self._id}` asks a question with no run")
        self.pending_question = question
        post(self._log_of_conversation, Message(self._owned_by(), self.question_message(question),
                                                interrupts=True, source=self._current, question=question))

    def _withdraw(self) -> None:
        """The pending question withdrawn (§3.4): cleared,
        `question_withdrawn`, the `ask` waiting on it cancelled, so a stray
        asking branch ends with it; nothing when none is pending.  No
        mailbox is touched: delivery drops the question."""
        if self.pending_question is None:
            return
        self.pending_question = None
        self._log.question_withdrawn(node=self._id)
        if self._answered is not None and not self._answered.done():
            self._answered.cancel()

    def _carry_from(self, old: Construction_Job) -> None:
        """An amend's commit copying the replaced node's job image (§3.1):
        the old outcome, `RUNNING` read as `NOT_STARTED`."""
        self.outcome = old.outcome if isinstance(old.outcome, (Succeeded, Failed)) else NOT_STARTED

    def _store(self) -> None:
        """The node stored in a transaction of its own (ARCHITECTURE §4.1)."""
        forest = self.node.forest()
        with forest.store.transaction():
            forest._store_node(self.node)

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
            raise TAT_InternalError(f"the {self.title()} on `{self._id}` has no owner")
        return self.owner


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
