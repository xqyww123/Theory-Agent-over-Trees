"""`Log` (LOGGING.md §3, §5): every event method writes one line into its
category's file, stamped from the context variables; the free `note`; the
encoding of a lone surrogate, an `IsaTerm`, a value JSON cannot hold; a
record that cannot be written is reported once and raises nothing.
Run: python -m pytest test/test_log.py
"""

import asyncio
import contextvars
import inspect
import json
import logging
import re
from pathlib import Path

import pytest

from isabelle_theory_agent import log as L
from isabelle_theory_agent.isabelle_driver import IsaTerm
from isabelle_theory_agent.log import Log, current_agent, current_call

TS = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$")
LOGGER = "tat.test.log"


@pytest.fixture
def log(tmp_path):
    return Log(tmp_path, logging.getLogger(LOGGER))


def records(directory: Path, category: str) -> list[dict]:
    """The file's records, each line parsed on its own (§6)."""
    path = directory / f"{category}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_bytes().split(b"\n") if line]


def only(directory: Path, category: str) -> dict:
    [record] = records(directory, category)
    return record


def event_methods(category) -> list[tuple[str, inspect.Signature]]:
    """The declared events of a category: its public methods but `note`,
    whose parameters are all keyword (`ending` is the one exception and
    has its own case)."""
    return [(name, inspect.signature(method)) for name, method in inspect.getmembers(category, callable)
            if not name.startswith("_") and name != "note"
            and all(p.kind in (p.KEYWORD_ONLY, p.VAR_KEYWORD)
                    for p in inspect.signature(method).parameters.values())]


def sample_arguments(signature: inspect.Signature) -> dict:
    """One JSON value per field, a `**` parameter contributing two."""
    arguments = {}
    for p in signature.parameters.values():
        if p.kind is p.VAR_KEYWORD:
            arguments.update({"fact_a": 1, "fact_b": [2]})
        else:
            arguments[p.name] = f"<{p.name}>"
    return arguments


def test_every_event_method_writes_one_record_into_its_category(log, tmp_path):
    """The method's name is the event, its category's name the file, its
    fields the record's `data`; `ts` in the documented form; no agent and
    no call outside any context."""
    categories = ["conversation", "tool", "hook", "agent", "edit", "evaluation", "job",
                  "round_trip", "store"]
    assert sorted(f.name for f in Path(tmp_path).iterdir()) == []
    counted = 0
    for category in categories:
        attribute = getattr(log, category)
        for event, signature in event_methods(attribute):
            arguments = sample_arguments(signature)
            getattr(attribute, event)(**arguments)
            counted += 1
            record = records(tmp_path, category)[-1]
            assert record["category"] == category
            assert record["event"] == event
            assert record["level"] in ("debug", "info", "warning", "error")
            assert TS.match(record["ts"])
            assert "agent" not in record and "call" not in record
            assert record["data"] == arguments, event
            assert list(record) == ["ts", "category", "event", "level", "data"]
        assert len(records(tmp_path, category)) == len(event_methods(attribute))
    assert counted == 45                       # the Python side's named events, `ending` apart
    assert sorted(f.name for f in Path(tmp_path).iterdir()) == sorted(f"{c}.jsonl" for c in categories)


def test_the_levels_are_the_tables(log):
    """The level each event is declared with, against LOGGING §4."""
    def level(category, event):
        getattr(getattr(log, category), event)(**sample_arguments(
            inspect.signature(getattr(getattr(log, category), event))))
        return records(log.directory, category)[-1]["level"]
    assert level("conversation", "client_refused") == "error"
    assert level("tool", "unannounced") == "error"
    assert level("agent", "check_failed") == "error"
    assert level("agent", "left_with_jobs") == "error"
    assert level("store", "transaction_failed") == "error"
    assert level("agent", "transcript_read") == "debug"
    assert level("agent", "seen") == "debug"
    assert level("tool", "call") == "info"
    assert level("conversation", "start") == "info"


def test_a_field_whose_value_is_none_is_absent(log):
    """The "absent when" of §4: a compile's `start` has no port and no
    client; a clean `operation` carries an empty list, a write no run
    produced carries no `messages`."""
    log.conversation.start(version="0.1", pid=7, working_directory="/w", python_packages=["p"])
    assert only(log.directory, "conversation")["data"] == {
        "version": "0.1", "pid": 7, "working_directory": "/w", "python_packages": ["p"]}
    log.evaluation.operation(node="n1", operation="own", ran=True, status="passed", messages=[], duration=0.5)
    log.evaluation.operation(node="n1", operation="own", ran=False, status="blocked")
    clean, blocked = records(log.directory, "evaluation")
    assert clean["data"]["messages"] == []
    assert "messages" not in blocked["data"] and "duration" not in blocked["data"]
    # inside a value, None stays: arguments are recorded whole
    log.tool.call(tool="edit", arguments={"target_id": None, "constructs": [None]})
    assert only(log.directory, "tool")["data"]["arguments"] == {"target_id": None, "constructs": [None]}


def test_a_note_lands_in_the_named_category(log):
    log.store.note("checkpoint taken", rows=3, why=None)
    record = only(log.directory, "store")
    assert record["event"] == "note" and record["level"] == "debug"
    assert record["data"] == {"message": "checkpoint taken", "rows": 3}
    assert records(log.directory, "conversation") == []


def test_agent_and_call_come_from_the_context_variables(log):
    """Set where a call's body begins (§3); a task inherits them from the
    code that creates it; absent again outside."""
    def body():
        current_agent.set("a3f9c1")
        current_call.set("toolu_01Hx")
        log.tool.call(tool="print", arguments={})
    contextvars.copy_context().run(body)
    record = only(log.directory, "tool")
    assert record["agent"] == "a3f9c1" and record["call"] == "toolu_01Hx"
    assert list(record) == ["ts", "category", "event", "level", "agent", "call", "data"]

    async def scenario():
        current_agent.set("main")
        current_call.set("toolu_02")
        await asyncio.create_task(child())     # a task created under the call
    async def child():
        log.store.note("from the child task")
    asyncio.run(scenario())
    child_record = only(log.directory, "store")
    assert child_record["agent"] == "main" and child_record["call"] == "toolu_02"
    log.store.note("outside")
    assert "agent" not in records(log.directory, "store")[-1]


def test_ending_takes_the_exception_and_the_level(log, caplog):
    """Its class, `message`, the traceback (§4); `error` is mirrored to the
    logger, `info` is not."""
    try:
        raise ConnectionResetError("peer closed")
    except ConnectionResetError as gone:
        log.conversation.ending(gone, level="info")
    try:
        raise RuntimeError("a bug")
    except RuntimeError as bug:
        with caplog.at_level(logging.WARNING, logger=LOGGER):
            log.conversation.ending(bug, level="error")
    gone_record, bug_record = records(log.directory, "conversation")
    assert gone_record["level"] == "info"
    assert gone_record["data"]["class"] == "ConnectionResetError"
    assert gone_record["data"]["message"] == "peer closed"
    assert "Traceback (most recent call last)" in gone_record["data"]["traceback"]
    assert bug_record["level"] == "error"
    assert "raise RuntimeError" in bug_record["data"]["traceback"]
    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [(logging.ERROR, "a bug")]


def test_a_warning_or_error_record_is_also_sent_to_the_logger(log, caplog):
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        log.agent.check_failed(check="transcript", message="The transcript moved.", path="/t")
        log.store.transaction_failed(message="disk full")
        log.tool.call(tool="print", arguments={})
        log.store.note("quiet")
    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [
        (logging.ERROR, "The transcript moved."), (logging.ERROR, "disk full")]
    assert only(log.directory, "agent")["data"] == {
        "check": "transcript", "message": "The transcript moved.", "path": "/t"}


def test_a_lone_surrogate_round_trips(log):
    """Non-ASCII text as it is; a lone surrogate as its escape (§5)."""
    text = "∀x. P x \ud800 tail"
    log.tool.call(tool="print", arguments={"text": text})
    raw = (log.directory / "tool.jsonl").read_bytes()
    assert "∀x. P x".encode() in raw and b"\\ud800" in raw
    assert only(log.directory, "tool")["data"]["arguments"]["text"] == text


def test_an_isaterm_is_written_as_its_unicode(log):
    term = IsaTerm.from_isabelle("\\<forall>x. P x")
    log.evaluation.operation(node=1, operation="own", ran=True, status="failed",
                             messages=[term], duration=1.0)
    assert only(log.directory, "evaluation")["data"]["messages"] == ["∀x. P x"]


def test_any_other_value_json_cannot_hold_is_written_as_its_str(log):
    log.conversation.start(version="0.1", pid=1, working_directory=Path("/w"), python_packages=[])
    assert only(log.directory, "conversation")["data"]["working_directory"] == "/w"


def test_a_value_that_will_not_encode_is_reported_once_and_raises_nothing(log, caplog):
    class Unspeakable:
        def __str__(self):
            raise RuntimeError("no words")
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        log.tool.call(tool="print", arguments=Unspeakable())
        log.tool.call(tool="print", arguments=Unspeakable())
        log.tool.call(tool="print", arguments={})       # the writer goes on
    assert [r.getMessage() for r in caplog.records] == [
        f"TAT could not write its log file {log.directory / 'tool.jsonl'}: no words. "
        "Later failures are not reported."]
    assert [r["data"] for r in records(log.directory, "tool")] == [{"tool": "print", "arguments": {}}]


def test_a_file_that_cannot_be_opened_is_reported_once_and_later_failures_are_silent(log, caplog):
    """The category's file is a directory here, which refuses `open` for
    any user; the error record's message still reaches the logger."""
    (log.directory / "store.jsonl").mkdir()
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        log.store.transaction(rows_written=[[1, "proof"]], nodes_deleted=[], duration=0.1)
        log.store.transaction_failed(message="disk full")
        log.store.transaction(rows_written=[], nodes_deleted=[2], duration=0.1)
        log.tool.call(tool="print", arguments={})       # another file is written as before
    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [
        (logging.ERROR, f"TAT could not write its log file {log.directory / 'store.jsonl'}: "
                        "Is a directory. Later failures are not reported."),
        (logging.ERROR, "disk full")]
    assert only(log.directory, "tool")["data"] == {"tool": "print", "arguments": {}}


def test_now_is_the_documented_form():
    ts = L.now()
    assert TS.match(ts)
    assert re.match(r"^\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d\.\d{6}Z$", ts.replace(":", "-"))
