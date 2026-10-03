"""`Log` (LOGGING.md §3, §5): every event method writes one line into its
category's file, stamped from the context variables; the free `note`; the
encoding of a lone surrogate, an `IsaTerm`, a value JSON cannot hold; a
record that cannot be written is reported once and raises nothing.
Run: python -m pytest test/test_log.py
"""

import asyncio
import contextvars
import inspect
import logging
import re
from pathlib import Path

import pytest

import stand_ins
from baselines import DOCS, event_tables
from isabelle_theory_agent.isabelle_driver import IsaTerm
from isabelle_theory_agent.log import current_agent, current_call

TS = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$")


@pytest.fixture
def log():
    return stand_ins.log()


def only(category: str) -> dict:
    [record] = stand_ins.records(category)
    return record


def public_methods(category) -> dict[str, inspect.Signature]:
    """A category's public methods but `note`: by LOGGING §4, its events."""
    return {name: inspect.signature(method) for name, method in inspect.getmembers(category, callable)
            if not name.startswith("_") and name != "note"}


def event_methods(category) -> list[tuple[str, inspect.Signature]]:
    """The declared events among them: those whose parameters are all
    keyword (`ending` has a body and its own case)."""
    return [(name, signature) for name, signature in public_methods(category).items()
            if all(p.kind in (p.KEYWORD_ONLY, p.VAR_KEYWORD) for p in signature.parameters.values())]


def sample_arguments(signature: inspect.Signature) -> dict:
    """One JSON value per field, a `**` parameter contributing two."""
    arguments = {}
    for p in signature.parameters.values():
        if p.kind is p.VAR_KEYWORD:
            arguments.update({"fact_a": 1, "fact_b": [2]})
        else:
            arguments[p.name] = f"<{p.name}>"
    return arguments


# The Python side's categories and events, read from LOGGING §4's tables
TABLES = {category: table for category, table in event_tables(DOCS / "LOGGING.md", "4.").items()
          if category != "isabelle"}


def test_every_event_method_writes_one_record_into_its_category(log):
    """The categories and their events are exactly LOGGING §4's tables, each
    method declared at the table's level; the method's name is the event,
    its category's name the file, its fields the record's `data`; `ts` in
    the documented form; no agent and no call outside any context."""
    assert list(log.directory.iterdir()) == []
    assert TABLES["conversation"]["ending"] == "info or error"     # the one method with a body
    for category, table in TABLES.items():
        attribute = getattr(log, category)
        assert set(public_methods(attribute)) == set(table), category
        declared = event_methods(attribute)
        for event, signature in declared:
            arguments = sample_arguments(signature)
            getattr(attribute, event)(**arguments)
            record = stand_ins.records(category)[-1]
            assert record["category"] == category
            assert record["event"] == event
            assert record["level"] == table[event], event
            assert TS.match(record["ts"])
            assert "agent" not in record and "call" not in record
            # a parameter `class_` is the field `class`
            assert record["data"] == {name.removesuffix("_"): value for name, value in arguments.items()}
            assert list(record) == ["ts", "category", "event", "level", "data"]
        assert len(stand_ins.records(category)) == len(declared)
    assert sorted(f.name for f in log.directory.iterdir()) == sorted(f"{c}.jsonl" for c in TABLES)


def test_a_field_whose_value_is_none_is_absent(log):
    """The "absent when" of §4: a compile's `start` has no port and no
    client; a clean `operation` carries an empty list, a write no run
    produced carries no `messages`."""
    log.conversation.start(version="0.1", pid=7, working_directory="/w", python_packages=["p"])
    assert only("conversation")["data"] == {
        "version": "0.1", "pid": 7, "working_directory": "/w", "python_packages": ["p"]}
    log.evaluation.operation(node="n1", operation="own", ran=True, status="passed", messages=[], duration=0.5)
    log.evaluation.operation(node="n1", operation="own", ran=False, status="blocked")
    clean, blocked = stand_ins.records("evaluation")
    assert clean["data"]["messages"] == []
    assert "messages" not in blocked["data"] and "duration" not in blocked["data"]
    # inside a value, None stays: arguments are recorded whole
    log.tool.call(tool="edit", arguments={"target_id": None, "constructs": [None]})
    assert only("tool")["data"]["arguments"] == {"target_id": None, "constructs": [None]}


def test_a_note_lands_in_the_named_category(log):
    log.store.note("checkpoint taken", rows=3, why=None)
    record = only("store")
    assert record["event"] == "note" and record["level"] == "debug"
    assert record["data"] == {"message": "checkpoint taken", "rows": 3}
    assert stand_ins.records("conversation") == []


def test_agent_and_call_come_from_the_context_variables(log):
    """Set where a call's body begins (§3); a task inherits them from the
    code that creates it; absent again outside."""
    def body():
        current_agent.set("a3f9c1")
        current_call.set("toolu_01Hx")
        log.tool.call(tool="print", arguments={})
    contextvars.copy_context().run(body)
    record = only("tool")
    assert record["agent"] == "a3f9c1" and record["call"] == "toolu_01Hx"
    assert list(record) == ["ts", "category", "event", "level", "agent", "call", "data"]

    async def scenario():
        current_agent.set("main")
        current_call.set("toolu_02")
        await asyncio.create_task(child())     # a task created under the call
    async def child():
        log.store.note("from the child task")
    asyncio.run(scenario())
    child_record = only("store")
    assert child_record["agent"] == "main" and child_record["call"] == "toolu_02"
    log.store.note("outside")
    assert "agent" not in stand_ins.records("store")[-1]


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
        with caplog.at_level(logging.WARNING, logger=stand_ins.LOGGER):
            log.conversation.ending(bug, level="error")
    gone_record, bug_record = stand_ins.records("conversation")
    assert gone_record["level"] == "info"
    assert gone_record["data"]["class"] == "ConnectionResetError"
    assert gone_record["data"]["message"] == "ConnectionResetError: peer closed"
    assert "Traceback (most recent call last)" in gone_record["data"]["traceback"]
    assert bug_record["level"] == "error"
    assert "raise RuntimeError" in bug_record["data"]["traceback"]
    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [(logging.ERROR, "RuntimeError: a bug")]


def test_ending_survives_an_exception_whose_str_fails_and_names_a_bare_one(log, caplog):
    """`message` is Python's one-line form: never empty, never raising."""
    class Unspeakable(Exception):
        def __str__(self):
            raise RuntimeError("no words")
    with caplog.at_level(logging.WARNING, logger=stand_ins.LOGGER):
        log.conversation.ending(Unspeakable(), level="error")
        log.conversation.ending(AssertionError(), level="error")
    unspeakable, bare = (r["data"]["message"] for r in stand_ins.records("conversation"))
    # the one-line form names a class outside the builtins by its module
    assert unspeakable == f"{__name__}.{Unspeakable.__qualname__}: <exception str() failed>"
    assert bare == "AssertionError"
    assert [r.getMessage() for r in caplog.records] == [unspeakable, bare]


def test_the_field_class_is_written_from_the_parameter_class_(log):
    """The trailing `_` is dropped from a declared parameter only; a `**`
    parameter's entry keeps its name, as in `note`."""
    log.tool.result(tool="edit", is_error=True, text="refused", messages=[], trailer=None,
                    class_="NodeNotFound", duration=0.1)
    assert only("tool")["data"]["class"] == "NodeNotFound"
    log.agent.compaction(learned_from="post_compact", seen_cleared=0, path_="/p")
    assert only("agent")["data"] == {"learned_from": "post_compact", "seen_cleared": 0, "path_": "/p"}


def test_a_warning_or_error_record_is_also_sent_to_the_logger(log, caplog):
    with caplog.at_level(logging.DEBUG, logger=stand_ins.LOGGER):
        log.agent.check_failed(check="transcript", message="The transcript moved.", path="/t")
        log.store.transaction_failed(message="disk full")
        log.tool.call(tool="print", arguments={})
        log.store.note("quiet")
    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [
        (logging.ERROR, "The transcript moved."), (logging.ERROR, "disk full")]
    assert only("agent")["data"] == {
        "check": "transcript", "message": "The transcript moved.", "path": "/t"}


def test_a_lone_surrogate_round_trips(log):
    """Non-ASCII text as it is; a lone surrogate as its escape (§5)."""
    text = "∀x. P x \ud800 tail"
    log.tool.call(tool="print", arguments={"text": text})
    raw = (log.directory / "tool.jsonl").read_bytes()
    assert "∀x. P x".encode() in raw and b"\\ud800" in raw
    assert only("tool")["data"]["arguments"]["text"] == text


def test_an_isaterm_is_written_as_its_unicode(log):
    term = IsaTerm.from_isabelle("\\<forall>x. P x")
    log.evaluation.operation(node=1, operation="own", ran=True, status="failed",
                             messages=[term], duration=1.0)
    assert only("evaluation")["data"]["messages"] == ["∀x. P x"]


def test_any_other_value_json_cannot_hold_is_written_as_its_str(log):
    log.conversation.start(version="0.1", pid=1, working_directory=Path("/w"), python_packages=[])
    assert only("conversation")["data"]["working_directory"] == "/w"


def test_a_value_that_will_not_encode_is_reported_once_and_raises_nothing(log, caplog):
    class Unspeakable:
        def __str__(self):
            raise RuntimeError("no words")
    with caplog.at_level(logging.DEBUG, logger=stand_ins.LOGGER):
        log.tool.call(tool="print", arguments=Unspeakable())
        log.tool.call(tool="print", arguments=Unspeakable())
        log.tool.call(tool="print", arguments={})       # the writer goes on
    assert [r.getMessage() for r in caplog.records] == [
        f"TAT could not write its log file {log.directory / 'tool.jsonl'}: no words. "
        "Later failures are not reported."]
    assert [r["data"] for r in stand_ins.records("tool")] == [{"tool": "print", "arguments": {}}]


def test_a_file_that_cannot_be_opened_is_reported_once_and_later_failures_are_silent(log, caplog):
    """The category's file is a directory here, which refuses `open` for
    any user; the error record's message still reaches the logger."""
    (log.directory / "store.jsonl").mkdir()
    with caplog.at_level(logging.DEBUG, logger=stand_ins.LOGGER):
        log.store.transaction(rows_written=[[1, "proof"]], nodes_deleted=[], duration=0.1)
        log.store.transaction_failed(message="disk full")
        log.store.transaction(rows_written=[], nodes_deleted=[2], duration=0.1)
        log.tool.call(tool="print", arguments={})       # another file is written as before
    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [
        (logging.ERROR, f"TAT could not write its log file {log.directory / 'store.jsonl'}: "
                        "Is a directory. Later failures are not reported."),
        (logging.ERROR, "disk full")]
    assert only("tool")["data"] == {"tool": "print", "arguments": {}}
