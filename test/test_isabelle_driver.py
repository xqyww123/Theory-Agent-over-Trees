"""`isabelle_driver.call`, the one door to the wire (MODULE_STRUCTURE §4.3):
an exception the ML callback let escape is a bug, `TAT_IsabelleError`, and
not a `TAT_Error` (EXCEPTIONS.md §1); every round trip is recorded in the
conversation's log when it completes, whether or not its caller still
waits (LOGGING.md §5); and it is the one door — no other line of the
package calls `Connection.callback`.  `Connection`'s other wire coroutines
(`config_lookup`, `writeln`, `warning`, `tracing`) are round trips too, and
a node class does not use them; they are not scanned for, since their
names are ordinary.  The ML side of the rule is exercised by
test/test_conversation.py.  Run: python -m pytest test/test_isabelle_driver.py
"""

import asyncio
import gc
from pathlib import Path
from typing import Any, cast

import pytest
from Isabelle_RPC_Host import IsabelleError, IsabelleInterrupt

import isabelle_theory_agent
import stand_ins
from isabelle_theory_agent import isabelle_driver
from isabelle_theory_agent.exceptions import TAT_Error, TAT_InternalError, TAT_IsabelleError


class Fake_Connection:
    """Answers one callback and `TAT.reset`, interrupts one under a name no
    ML callback bears, and lets every other raise as the RPC library does
    when the ML side let an exception escape: one entry per message, a
    message spanning lines."""
    async def callback(self, name, args):
        if name == "TAT.state_exists":
            return args == "held"
        if name == "TAT.reset":
            return None
        if name == "TAT.gone":                 # what the RPC library raises for a dead wire
            raise ConnectionResetError("peer closed connection")
        if name == "TAT.interrupted":
            raise IsabelleInterrupt(["Interrupt"], None)
        raise IsabelleError([f'exception Bug "{name}: tat-bug" raised (line 94)\nAt command "theory"',
                             "second message"], None)


def conversation(conn):
    return stand_ins.conversation(cast(Any, conn))


def round_trips(conv) -> list[dict]:
    return stand_ins.records("round_trip", conv.log.directory)


async def settled():
    """The done callbacks of a trip that has just completed have run."""
    for _ in range(3):
        await asyncio.sleep(0)


def test_a_result_comes_back_and_an_escaped_exception_is_a_bug():
    conv = conversation(Fake_Connection())
    assert asyncio.run(isabelle_driver.state_exists(conv, "held")) is True
    with pytest.raises(TAT_IsabelleError) as e:
        asyncio.run(isabelle_driver.call(conv, "TAT.Theory.begin", ()))
    assert isinstance(e.value, TAT_InternalError) and not isinstance(e.value, TAT_Error)
    assert isinstance(e.value.__cause__, IsabelleError)
    assert str(e.value) == (                     # the messages themselves, one per line
        "the ML callback TAT.Theory.begin failed:\n"
        'exception Bug "TAT.Theory.begin: tat-bug" raised (line 94)\nAt command "theory"\n'
        "second message")
    # each trip recorded as it completed: the result, or the error's messages
    answered, failed = round_trips(conv)
    assert answered["event"] == "round_trip" and answered["data"] == {
        "name": "TAT.state_exists", "arguments": "held", "result": True,
        "duration": answered["data"]["duration"]}
    assert failed["data"] == {
        "name": "TAT.Theory.begin", "arguments": [],
        "error": 'exception Bug "TAT.Theory.begin: tat-bug" raised (line 94)\nAt command "theory"\n'
                 "second message",
        "duration": failed["data"]["duration"]}


def test_an_interrupt_is_treated_like_any_isabelle_error_for_now():
    conv = conversation(Fake_Connection())
    with pytest.raises(TAT_IsabelleError) as e:
        asyncio.run(isabelle_driver.call(conv, "TAT.interrupted", ()))
    assert isinstance(e.value.__cause__, IsabelleInterrupt)
    assert str(e.value) == "the ML callback TAT.interrupted failed:\nInterrupt"
    assert round_trips(conv)[0]["data"]["error"] == "Interrupt"


def test_reset_runs_on_a_bare_connection():
    """Before any `Conversation` exists (MODULE_STRUCTURE §4.3): nothing to
    record it in, and nothing raised."""
    asyncio.run(isabelle_driver.reset(cast(Any, Fake_Connection())))


def test_a_connection_error_reaches_the_caller_unwrapped_and_is_the_trips_error():
    """The connection going is the conversation's ending, not a bug
    (MODULE_STRUCTURE §4.3): no `TAT_IsabelleError`; the one record names
    the trip and carries the error."""
    conv = conversation(Fake_Connection())
    with pytest.raises(ConnectionResetError):
        asyncio.run(isabelle_driver.call(conv, "TAT.gone", ()))
    [record] = round_trips(conv)
    assert record["event"] == "round_trip" and record["data"] == {
        "name": "TAT.gone", "arguments": [], "error": "ConnectionResetError: peer closed connection",
        "duration": record["data"]["duration"]}


def test_a_cancelled_caller_unwinds_while_the_round_trip_completes():
    """The shield of MODULE_STRUCTURE §4.3: the caller sees its cancellation
    at once; the round trip in flight is neither cancelled nor waited for,
    and finishes on its own with nobody reading its result — which the log
    still records."""
    class Slow_Connection:
        def __init__(self):
            self.release = asyncio.Event()
            self.finished = False
        async def callback(self, name, args):
            await self.release.wait()          # the wire's phases, in flight
            self.finished = True
            return args

    async def scenario():
        conn = Slow_Connection()
        conv = conversation(conn)
        caller = asyncio.create_task(isabelle_driver.call(conv, "TAT.slow", 1))
        await asyncio.sleep(0)                 # the round trip is in flight
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert not conn.finished               # unwound before the wire answered
        assert round_trips(conv) == []
        conn.release.set()
        await settled()
        assert conn.finished                   # the round trip ran to its end
        [record] = round_trips(conv)
        assert record["data"]["name"] == "TAT.slow" and record["data"]["result"] == 1
    asyncio.run(scenario())


def test_an_abandoned_round_trips_failure_is_nobodys_and_not_reported():
    """The dropped round trip fails after its caller has gone: nothing is
    raised anywhere, asyncio does not report it as unhandled, and the trip
    is recorded with its error."""
    class Failing_Connection:
        def __init__(self):
            self.release = asyncio.Event()
        async def callback(self, name, args):
            await self.release.wait()
            raise ConnectionResetError("peer closed connection")

    async def scenario():
        reported = []
        asyncio.get_running_loop().set_exception_handler(lambda loop, ctx: reported.append(ctx))
        conn = Failing_Connection()
        conv = conversation(conn)
        caller = asyncio.create_task(isabelle_driver.call(conv, "TAT.slow", 1))
        await asyncio.sleep(0)
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        conn.release.set()
        await settled()                        # the abandoned round trip fails now
        gc.collect()                           # its task is unreferenced; asyncio would report it here
        assert reported == []
        [record] = round_trips(conv)
        assert record["event"] == "round_trip" and record["data"]["name"] == "TAT.slow"
        assert record["data"]["error"] == "ConnectionResetError: peer closed connection"
        assert "result" not in record["data"] and "duration" in record["data"]
    asyncio.run(scenario())


def test_call_is_the_one_door_to_the_wire():
    """Every round trip goes through `call` (EXCEPTIONS.md §1, MODULE_STRUCTURE
    §4.3): a node class calling `Connection.callback` itself would let an
    escaped ML exception arrive as a raw `IsabelleError`, which no boundary
    expects — and a test case doing so would let a deadline cut the
    two-phase exchange in the middle.  Judged on the source of the package
    and of the suite: code lines only, comments left out; the door's one
    call and this guard's own needle are the two lines that may name it."""
    root = Path(isabelle_theory_agent.__file__).parent.parent
    hits = [(str(path.relative_to(root)), n)
            for folder in ("isabelle_theory_agent", "test")
            for path in sorted((root / folder).rglob("*.py"))
            for n, line in enumerate(path.read_text().splitlines(), 1)
            if ".callback(" in line.split("#")[0]]
    assert [f for f, _ in hits] == ["isabelle_theory_agent/isabelle_driver.py",
                                    "test/test_isabelle_driver.py"], \
        f"Connection.callback called outside isabelle_driver.call: {hits}"
