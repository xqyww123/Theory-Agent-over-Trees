"""The log of one conversation (LOGGING.md): one `Log` per conversation,
held by the `Conversation`; one attribute per category, one method per
event, the method's keyword parameters the event's fields of LOGGING §4,
and `note` on every category.  Nothing a method does reaches its caller:
a record that cannot be written is reported to the RPC host's logger once
and dropped (§5).
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
import traceback
from collections.abc import Callable
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Concatenate, Literal, ParamSpec

from Isabelle_RPC_Host.unicode import IsaTerm

Level = Literal["debug", "info", "warning", "error"]

# The agent a record is written for and the client's id of the tool call
# it belongs to (LOGGING §3): set where a call's body and a hook request
# begin; a task inherits them from the code that creates it.
current_agent: ContextVar[str | None] = ContextVar("current_agent", default=None)
current_call: ContextVar[str | None] = ContextVar("current_call", default=None)

_MIRRORED = {"warning": logging.WARNING, "error": logging.ERROR}


def now() -> str:
    """A record's `ts`: UTC to the microsecond, `2026-10-01T07:24:05.039123Z`;
    with `:` turned into `-`, the log directory's name (§2)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _plain(value: Any) -> Any:
    """What `json.dumps` cannot hold (§5): an `IsaTerm` as its stored
    spelling, anything else as its `str`."""
    return value.unicode if isinstance(value, IsaTerm) else str(value)


class Log:
    """The writer: `directory` is the conversation's log directory (§2),
    `logger` the RPC host's.  Holds no open file: each record opens its
    category's file, appends one line and closes it."""

    def __init__(self, directory: Path, logger: logging.Logger):
        self.directory = directory
        self._logger = logger
        self._failed = False
        self.conversation = _Conversation(self)
        self.tool = _Tool(self)
        self.hook = _Hook(self)
        self.agent = _Agent(self)
        self.edit = _Edit(self)
        self.evaluation = _Evaluation(self)
        self.job = _Job(self)
        self.round_trip = _Round_Trip(self)
        self.store = _Store(self)

    def _write(self, category: str, event: str, level: Level, data: dict[str, Any]) -> None:
        """Stamp, encode and append (§5).  A field whose value is None is
        absent from `data` — the "absent when" of §4's tables.  Encoding
        and writing fail together, reported once; a `warning` or `error`
        reaches the logger whether or not its line was written."""
        record: dict[str, Any] = {"ts": now(), "category": category, "event": event, "level": level}
        if (agent := current_agent.get()) is not None:
            record["agent"] = agent
        if (call := current_call.get()) is not None:
            record["call"] = call
        record["data"] = {name: value for name, value in data.items() if value is not None}
        path = self.directory / f"{category}.jsonl"
        try:
            # a lone surrogate, which UTF-8 cannot hold, as its \udXXX escape
            line = (json.dumps(record, ensure_ascii=False, default=_plain)
                    .encode("utf-8", errors="backslashreplace") + b"\n")
            with open(path, "ab") as file:
                file.write(line)
        except Exception as e:
            if not self._failed:
                self._failed = True
                reason = getattr(e, "strerror", None) or str(e) or type(e).__name__
                self._logger.error(f"TAT could not write its log file {path}: {reason}. "
                                   "Later failures are not reported.")
        if level in _MIRRORED:
            self._logger.log(_MIRRORED[level], data["message"])


P = ParamSpec("P")


def _event(level: Level) -> Callable[[Callable[Concatenate[Any, P], None]],
                                     Callable[Concatenate[Any, P], None]]:
    """Declares an event method: its name is the event, its keyword
    parameters are the record's fields (a `**` parameter's entries among
    them; a parameter named `class_` for the field `class`, PEP 8's way
    around a keyword), `level` the record's level; the body is never run."""
    def declare(signature_of: Callable[Concatenate[Any, P], None]) -> Callable[Concatenate[Any, P], None]:
        signature = inspect.signature(signature_of)
        parameters = {name: p for name, p in signature.parameters.items() if name != "self"}
        # each declared parameter's field, then the `**` parameter's entries as they are
        fields = {name: name.removesuffix("_") for name, p in parameters.items() if p.kind is not p.VAR_KEYWORD}
        var_keyword = [name for name, p in parameters.items() if p.kind is p.VAR_KEYWORD]

        @functools.wraps(signature_of)
        def method(self: Any, *args: P.args, **kwargs: P.kwargs) -> None:
            bound = signature.bind(self, *args, **kwargs)
            bound.apply_defaults()
            data = {field: bound.arguments[name] for name, field in fields.items()}
            for name in var_keyword:
                data.update(bound.arguments[name])
            self._log._write(self.category, signature_of.__name__, level, data)
        return method
    return declare


def _exception_data(exception: BaseException) -> dict[str, str]:
    """An exception's `class`, `message` and `traceback` (§4).  `message`
    is Python's one-line form, class first, which the standard library
    renders even when the exception's own `str` fails."""
    return {"class": type(exception).__name__,
            "message": "".join(traceback.format_exception_only(exception)).rstrip("\n"),
            "traceback": "".join(traceback.format_exception(exception))}


class _Category:
    category: ClassVar[str]

    def __init__(self, log: Log):
        self._log = log

    def note(self, message: str, **fields: Any) -> None:
        """The free record (§3): level `debug`, `message` and whatever
        fields its writer adds."""
        self._log._write(self.category, "note", "debug", {"message": message, **fields})


class _Conversation(_Category):
    category = "conversation"

    @_event("info")
    def start(self, *, version: str, pid: int, working_directory: str, python_packages: list[str],
              port: int | None = None, client: str | None = None) -> None: ...

    @_event("info")
    def store_opened(self, *, schema_version: int, nodes: int) -> None: ...

    @_event("info")
    def plugins_loaded(self, *, kinds: dict[str, str]) -> None: ...

    @_event("info")
    def configured(self, *, files: list[str]) -> None: ...

    @_event("info")
    def serving(self, *, url: str) -> None: ...

    @_event("info")
    def client_connected(self, *, name: str, version: str) -> None: ...

    @_event("error")
    def client_refused(self, *, name: str, version: str, message: str, _meta: Any = None) -> None: ...

    def ending(self, ended_by: BaseException) -> None:
        """What ended the conversation (§4)."""
        self._log._write(self.category, "ending", "error", _exception_data(ended_by))

    def while_ending(self, cause: BaseException) -> None:
        """A cause reaching the ending once it is entered (§4): the same
        data as `ending`'s, the end unchanged."""
        self._log._write(self.category, "while_ending", "error", _exception_data(cause))

    @_event("info")
    def ended(self, *, duration: float) -> None: ...


class _Tool(_Category):
    category = "tool"

    @_event("info")
    def call(self, *, tool: str, arguments: Any) -> None: ...

    @_event("info")
    def result(self, *, tool: str, is_error: bool, text: str, messages: list[Any], trailer: Any,
               class_: str | None = None, duration: float) -> None: ...

    @_event("info")
    def given_up(self, *, tool: str, text: str | None, messages: list[Any], duration: float) -> None: ...

    @_event("error")
    def unannounced(self, *, tool: str, _meta: Any, message: str) -> None: ...

    @_event("info")
    def while_ending(self, *, tool: str) -> None: ...


# What a hook request was judged to be (§4, `hook.answer`).
Judged = Literal["announcement", "interruption", "stop", "compaction", "session_start", "ignored"]


class _Hook(_Category):
    category = "hook"

    @_event("info")
    def request(self, *, payload: Any) -> None: ...

    @_event("info")
    def answer(self, *, judged: Judged | None, status: int, body: Any, duration: float) -> None: ...


# How TAT learned of a compaction (§4, `agent.compaction`).
Learned_From = Literal["compact_boundary", "transcript_path_changed", "transcript_changed",
                       "session_start", "pre_compact", "post_compact"]


class _Agent(_Category):
    category = "agent"

    @_event("info")
    def created(self, *, identity: str, main: bool, first: Literal["call", "hook"]) -> None: ...

    @_event("debug")
    def transcript_read(self, *, file: str, offset: int, bytes: int, lines: int,
                        boundaries: list[Any]) -> None: ...

    @_event("info")
    def compaction(self, *, learned_from: Learned_From, seen_cleared: int, **facts: Any) -> None: ...

    @_event("debug")
    def seen(self, *, key: Any) -> None: ...

    @_event("error")
    def check_failed(self, *, check: str, message: str, **facts: Any) -> None: ...

    @_event("info")
    def stop_judged(self, *, allowed: bool, stands: Any = None) -> None: ...

    @_event("info")
    def interruption_judged(self, *, allowed: bool, holding_work: list[str] | None = None) -> None: ...

    @_event("error")
    def left_with_jobs(self, *, agent: str, jobs: list[Any], message: str) -> None: ...


class _Edit(_Category):
    category = "edit"

    @_event("info")
    def committed(self, *, operation: Literal["insert", "amend", "delete", "move"], parent: Any,
                  index: Any, created: list[Any], removed: list[Any], moved: list[Any],
                  invalidated: list[Any]) -> None: ...


class _Evaluation(_Category):
    category = "evaluation"

    @_event("info")
    def walk_started(self, *, destination: Any, ignore_error: bool, checks: Any) -> None: ...

    @_event("info")
    def operation(self, *, node: Any, operation: Literal["own", "beginning", "ending"], ran: bool,
                  status: Any, messages: list[Any] | None = None,
                  duration: float | None = None) -> None: ...

    @_event("info")
    def stopped(self, *, node: Any,
                reason: Literal["command_failed", "order_constraint", "import_without_theory"],
                tree: Any = None) -> None: ...

    @_event("info")
    def walk_ended(self, *, outcome: Any, slots_released: int, duration: float) -> None: ...


class _Job(_Category):
    category = "job"

    @_event("info")
    def construction_started(self, *, node: Any, owner: str) -> None: ...

    @_event("info")
    def construction_settled(self, *, node: Any, outcome: str, message: str | None = None) -> None: ...

    @_event("info")
    def construction_cancelled(self, *, node: Any,
                               reason: Literal["NODE_DELETED", "NODE_AMENDED", "CONTEXT_CHANGED"] | None = None
                               ) -> None: ...

    @_event("info")
    def evaluation_started(self, *, node: Any, id: Any, starter: str) -> None: ...

    @_event("info")
    def evaluation_reported(self, *, id: Any, outcome: str, failure: Any = None) -> None: ...

    @_event("info")
    def evaluation_dropped(self, *, id: Any, dropped_by: str) -> None: ...

    @_event("info")
    def report_ignored(self, *, id: Any) -> None: ...

    @_event("info")
    def cancel_sent(self, *, ids: list[Any]) -> None: ...

    @_event("info")
    def message_posted(self, *, recipient: str, kind: Literal["notification", "question"],
                       source: Any, interrupts: bool, text: str) -> None: ...

    @_event("info")
    def message_delivered(self, *, recipient: str) -> None: ...

    @_event("info")
    def message_dropped(self, *, recipient: str, reason: str) -> None: ...

    @_event("info")
    def question_answered(self, *, node: Any, outcome: str) -> None: ...

    @_event("info")
    def question_withdrawn(self, *, node: Any) -> None: ...


class _Round_Trip(_Category):
    category = "round_trip"

    @_event("info")
    def round_trip(self, *, name: str, arguments: Any, result: Any = None, error: str | None = None,
                   duration: float) -> None: ...


class _Store(_Category):
    category = "store"

    @_event("info")
    def transaction(self, *, rows_written: list[Any], nodes_deleted: list[Any], duration: float) -> None: ...

    @_event("error")
    def transaction_failed(self, *, message: str) -> None: ...
