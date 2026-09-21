"""Shared fixtures."""

import logging

import pytest


@pytest.fixture(autouse=True)
def no_uvicorn_error_is_logged(caplog):
    """Every ending is clean (MODULE_STRUCTURE §4.6): nothing reaches
    uvicorn's error log during the test — the call phase's records, the
    ones a fixture's tail can read."""
    yield
    assert [r.getMessage() for r in caplog.get_records("call")
            if r.name == "uvicorn.error" and r.levelno >= logging.ERROR] == []
