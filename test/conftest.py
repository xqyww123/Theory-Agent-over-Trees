"""Shared fixtures, and the harness of the Isabelle-backed cases
(ai-artifacts/TEST_HARNESS_PLAN.md §4)."""

import functools
import inspect
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

import pytest

import harness as H
import stand_ins


@pytest.fixture(autouse=True)
def stand_ins_directory(tmp_path, monkeypatch):
    """Every `Log` a case builds without Isabelle (`stand_ins`) writes under
    the case's temporary directory."""
    monkeypatch.setattr(stand_ins, "directory", tmp_path / "log")


@pytest.fixture(autouse=True)
def no_uvicorn_error_is_logged(caplog):
    """Every ending is clean (MODULE_STRUCTURE §4.6): nothing reaches
    uvicorn's error log during the test — the call phase's records and the
    teardown phase's, where a conversation's ending happens."""
    yield
    assert [r.getMessage() for phase in ("call", "teardown") for r in caplog.get_records(phase)
            if r.name == "uvicorn.error" and r.levelno >= logging.ERROR] == []


@pytest.fixture(scope="session")
def anyio_backend():
    """Session-scoped so that `harness` may depend on it; anyio keeps its
    runner — one loop — alive for as long as that fixture is alive."""
    return "asyncio"


@asynccontextmanager
async def started(h: H.Harness):
    """The harness's three stages, each releasing itself in reverse when the
    run ends."""
    async with AsyncExitStack() as stack:
        h.start_host()
        stack.enter_context(h.server)
        await h.start_child()
        stack.push_async_callback(h.release_child)
        await h.await_launch()
        stack.push_async_callback(h.release_run)
        yield h


@pytest.fixture(scope="session")
async def harness(anyio_backend, tmp_path_factory):
    """One `isabelle TAT_mcp` for the run, started when first asked for."""
    async with started(H.Harness(logging.getLogger("tat.test.harness"), tmp_path_factory.mktemp("harness"))) as h:
        yield h


@pytest.fixture(scope="session")
async def std_harness(anyio_backend, tmp_path_factory):
    """The run of the plugin `Isabelle_Std` (MODULE_STRUCTURE §4.5): on the
    base heap `Minilang_AoA`, the plugin's directory given, the conversations
    loading the package its registrations do not name yet."""
    async with started(H.Harness(logging.getLogger("tat.test.std_harness"), tmp_path_factory.mktemp("std_harness"),
                                 plugin="TAT_Isabelle_Std.TAT_Isabelle_Std", registered=[],
                                 packages=["isabelle_theory_agent.std"], logic="Minilang_AoA",
                                 dirs=[Path(__file__).resolve().parent.parent / "Isabelle_Std"])) as h:
        yield h


HARNESSES = ("harness", "std_harness")


@pytest.fixture
async def conversation(harness, request, tmp_path):
    """A fresh conversation for the case, on a fresh working directory."""
    yield await harness.converse(tmp_path, request.node.nodeid)
    await harness.await_ending()


@pytest.fixture
async def std_conversation(std_harness, request, tmp_path):
    """A fresh conversation of the plugin's run."""
    yield await std_harness.converse(tmp_path, request.node.nodeid)
    await std_harness.await_ending()


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "isabelle(deadline=seconds): an Isabelle-backed case — derived from the "
        "fixture closure; written by hand only on such a case, to override its deadline")


def _under_deadline(item, seconds, harness_fixture):
    original = item.obj

    @functools.wraps(original)
    async def case(**kwargs):
        with item.funcargs[harness_fixture].deadline(seconds, f"the body of {item.nodeid}"):
            await original(**kwargs)
    return case


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """Using a harness is the marker.  Every such case is `async def` and
    runs under a deadline; the Isabelle-backed cases run last."""
    for item in items:
        marker = item.get_closest_marker("isabelle")
        used = [name for name in HARNESSES if name in item.fixturenames] if isinstance(item, pytest.Function) else []
        if used:
            if not inspect.iscoroutinefunction(item.obj):
                raise pytest.UsageError(f"{item.nodeid}: an Isabelle-backed case must be `async def`")
            seconds = marker.kwargs.get("deadline", H.DEADLINE) if marker else H.DEADLINE
            item.add_marker(pytest.mark.isabelle)
            item.obj = _under_deadline(item, seconds, used[0])
        elif marker is not None:
            raise pytest.UsageError(f"{item.nodeid}: marked `isabelle` but uses no harness")
    items.sort(key=lambda item: item.get_closest_marker("isabelle") is not None)