"""`isabelle_driver.call`, the one door to the wire (MODULE_STRUCTURE §4.3):
an exception the ML callback let escape is a bug, `TAT_IsabelleError`, and
not a `TAT_Error` (EXCEPTIONS.md §1); and it is the one door — no other
line of the package calls `Connection.callback`.  `Connection`'s other wire
coroutines (`config_lookup`, `writeln`, `warning`, `tracing`) are round
trips too, and a node class does not use them; they are not scanned for,
since their names are ordinary.  The ML side of the rule is exercised by
test/tat_framework_ml_test.py.  Run: python -m pytest test/test_isabelle_driver.py
"""

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest
from Isabelle_RPC_Host import IsabelleError, IsabelleInterrupt

import isabelle_theory_agent
from isabelle_theory_agent import isabelle_driver
from isabelle_theory_agent.exceptions import TAT_Error, TAT_InternalError, TAT_IsabelleError


class Fake_Connection:
    """Answers one callback, interrupts one under a name no ML callback
    bears, and lets every other raise as the RPC library does when the ML
    side let an exception escape: one entry per message, a message spanning
    lines."""
    async def callback(self, name, args):
        if name == "TAT.state_exists":
            return args == "held"
        if name == "TAT.interrupted":
            raise IsabelleInterrupt(["Interrupt"], None)
        raise IsabelleError([f'exception Bug "{name}: tat-bug" raised (line 94)\nAt command "theory"',
                             "second message"], None)


def test_a_result_comes_back_and_an_escaped_exception_is_a_bug():
    conn = cast(Any, Fake_Connection())
    assert asyncio.run(isabelle_driver.state_exists(conn, "held")) is True
    with pytest.raises(TAT_IsabelleError) as e:
        asyncio.run(isabelle_driver.call(conn, "TAT.Theory.begin", ()))
    assert isinstance(e.value, TAT_InternalError) and not isinstance(e.value, TAT_Error)
    assert isinstance(e.value.__cause__, IsabelleError)
    assert str(e.value) == (                     # the messages themselves, one per line
        "the ML callback TAT.Theory.begin failed:\n"
        'exception Bug "TAT.Theory.begin: tat-bug" raised (line 94)\nAt command "theory"\n'
        "second message")


def test_an_interrupt_is_treated_like_any_isabelle_error_for_now():
    conn = cast(Any, Fake_Connection())
    with pytest.raises(TAT_IsabelleError) as e:
        asyncio.run(isabelle_driver.call(conn, "TAT.interrupted", ()))
    assert isinstance(e.value.__cause__, IsabelleInterrupt)
    assert str(e.value) == "the ML callback TAT.interrupted failed:\nInterrupt"


def test_call_is_the_one_door_to_the_wire():
    """Every round trip goes through `call` (EXCEPTIONS.md §1, MODULE_STRUCTURE
    §4.3): a node class calling `Connection.callback` itself would let an
    escaped ML exception arrive as a raw `IsabelleError`, which no boundary
    expects.  Judged on the source: code lines only, comments left out."""
    package = Path(isabelle_theory_agent.__file__).parent
    hits = [(str(path.relative_to(package)), n) for path in sorted(package.rglob("*.py"))
            for n, line in enumerate(path.read_text().splitlines(), 1)
            if ".callback(" in line.split("#")[0]]
    assert [f for f, _ in hits] == ["isabelle_driver.py"], \
        f"Connection.callback called outside isabelle_driver.call: {hits}"
