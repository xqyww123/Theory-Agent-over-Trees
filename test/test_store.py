"""Forest_Store (ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §2)."""

import os
import sqlite3
import subprocess
import sys
import threading

import msgpack
import pytest

from isabelle_theory_agent.exceptions import TAT_InternalError, TAT_StartupError
from isabelle_theory_agent.store import SCHEMA_VERSION, Forest_Store, IncompatibleStore


@pytest.fixture
def store(tmp_path):
    with Forest_Store(tmp_path / "theory_forest.sqlite") as s:
        yield s


def test_round_trip_of_every_representable_shape(store):
    values = {
        "s": "lemma_P", "b": b"\x00\xff", "t": True, "i": -7, "f": 2.5, "n": None,
        "big": 2**64 - 1, "neg": -2**63,
        "l": [1, "two", [3.0, None]], "d": {"kind": "lemma", "facts": [{"name": "x"}]},
    }
    with store.transaction():
        for field, value in values.items():
            store.put(17, field, value)
    assert store.fields(17) == values
    for field, value in values.items():
        assert store.get(17, field) == value
    # a tuple comes back as a list
    with store.transaction():
        store.put(17, "tuple", (1, 2))
    assert store.get(17, "tuple") == [1, 2]


def test_what_put_accepts_get_reads_back_after_reopen(tmp_path):
    # dict keys of every scalar kind, nested: the write side and the read
    # side agree, including across a close and reopen
    path = tmp_path / "f.sqlite"
    value = {2: "a", True: "b", 2.5: "c", b"k": "d", None: {7: [{"x": 1}]}}
    assert len(value) == 5                       # True is not 2: five key kinds
    with Forest_Store(path) as s:
        with s.transaction():
            s.put(1, "d", value)
        assert s.get(1, "d") == value
    with Forest_Store(path) as s:
        assert s.get(1, "d") == value


def test_put_overwrites(store):
    with store.transaction():
        store.put(1, "proof", "not_started")
        store.put(1, "proof", "proven")
    assert store.fields(1) == {"proof": "proven"}
    with store.transaction():
        store.put(1, "proof", "failed")
    assert store.get(1, "proof") == "failed"


def test_get_distinguishes_absent_from_none(store):
    with store.transaction():
        store.put(1, "none", None)
    assert store.get(1, "none") is None
    with pytest.raises(KeyError):
        store.get(1, "absent")
    with pytest.raises(KeyError):
        store.get(2, "none")
    assert store.fields(2) == {}


def test_writes_need_a_transaction(store):
    with pytest.raises(TAT_InternalError):
        store.put(1, "kind", "lemma")
    with pytest.raises(TAT_InternalError):
        store.delete_node(1)
    # reads do not
    assert store.nodes() == []
    assert store.fields(1) == {}


def test_transactions_do_not_nest(store):
    with store.transaction():
        with pytest.raises(TAT_InternalError):
            with store.transaction():
                pass
        store.put(1, "kind", "lemma")           # the outer one is still open
    assert store.get(1, "kind") == "lemma"


def test_an_exception_rolls_the_whole_operation_back(store):
    with store.transaction():
        store.put(1, "kind", "theory")
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.put(1, "kind", "lemma")
            store.put(2, "kind", "lemma")
            store.delete_node(1)
            raise RuntimeError("gate vetoed")
    assert store.nodes() == [1]
    assert store.fields(1) == {"kind": "theory"}
    # and the store is usable afterwards
    with store.transaction():
        store.put(3, "kind", "section")
    assert store.nodes() == [1, 3]


def _nested(depth: int) -> list:
    value: list = []
    for _ in range(depth):
        value = [value]
    return value


@pytest.mark.parametrize("value", [object(), 2**64, -2**63 - 1, _nested(700),
                                   {(1, 2): "a tuple key packs, and unpacks to a list"}])
def test_unrepresentable_value_names_the_field(store, value):
    with pytest.raises(TAT_InternalError, match=r"field `statement` of node 5"):
        with store.transaction():
            store.put(5, "statement", value)
    assert store.nodes() == []


def test_a_failed_write_raises_the_real_error_and_leaves_the_store_usable(store):
    store._conn.execute("PRAGMA max_page_count = 12")      # fault injection: a full disk
    with pytest.raises(sqlite3.OperationalError, match="full"):
        with store.transaction():
            for node in range(200):
                store.put(node, "text", "x" * 4096)
    store._conn.execute("PRAGMA max_page_count = 1073741823")
    assert store.nodes() == []
    with store.transaction():
        store.put(1, "kind", "lemma")
    assert store.nodes() == [1]


def test_the_columns_are_typed(store):
    # STRICT tables: the node column holds nothing but integers and the
    # field column nothing but text, so nodes() can never return anything
    # but ints.  A value SQLite can convert without loss ("7") is
    # converted; one it cannot is a caller bug
    with pytest.raises(TAT_InternalError, match=r"field `kind` of node x/y"):
        with store.transaction():
            store.put("x/y", "kind", "lemma")
    with pytest.raises(TAT_InternalError, match=r"of node 1"):
        with store.transaction():
            store.put(1, b"\x00", "lemma")
    assert store.nodes() == []
    with store.transaction():
        store.put("7", "kind", "lemma")
    assert store.nodes() == [7]


def test_delete_node_removes_its_fields_and_nothing_else(store):
    with store.transaction():
        for node in (1, 2, 3):
            store.put(node, "kind", "lemma")
            store.put(node, "name", f"P{node}")
    with store.transaction():
        store.delete_node(2)
    assert store.nodes() == [1, 3]
    assert store.fields(2) == {}
    assert store.fields(1) == {"kind": "lemma", "name": "P1"}
    with store.transaction():
        store.delete_node(42)                   # absent: not an error


def test_identities_are_fresh_across_reopen(tmp_path):
    path = tmp_path / "f.sqlite"
    with Forest_Store(path) as s:
        assert [s.next_identity() for _ in range(2)] == [1, 2]      # outside a transaction
        with s.transaction():
            assert s.next_identity() == 3
            s.put(3, "kind", "theory")
    with Forest_Store(path) as s:
        assert s.nodes() == [3]
        assert s.fields(3) == {"kind": "theory"}
        assert s.next_identity() == 4


def test_a_rolled_back_identity_is_handed_out_again(store):
    with pytest.raises(RuntimeError):
        with store.transaction():
            assert store.next_identity() == 1
            raise RuntimeError
    assert store.next_identity() == 1


def test_schema_version_mismatch_is_refused(tmp_path):
    path = tmp_path / "f.sqlite"
    Forest_Store(path).close()
    conn = sqlite3.connect(path)
    conn.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'",
                 (msgpack.packb(SCHEMA_VERSION + 1),))
    conn.commit()
    conn.close()
    with pytest.raises(IncompatibleStore, match=f"schema version {SCHEMA_VERSION + 1}") as e:
        Forest_Store(path)
    assert isinstance(e.value, TAT_StartupError)


def test_a_corrupt_meta_blob_is_a_startup_error(tmp_path):
    path = tmp_path / "f.sqlite"
    Forest_Store(path).close()
    conn = sqlite3.connect(path)
    conn.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'", (b"\xc1",))
    conn.commit()
    conn.close()
    with pytest.raises(TAT_StartupError, match="meta is not readable"):
        Forest_Store(path)


def test_an_old_sqlite_library_is_a_startup_error(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 36, 0))
    monkeypatch.setattr(sqlite3, "sqlite_version", "3.36.0")
    with pytest.raises(TAT_StartupError, match="3.37.0 or newer"):
        Forest_Store(tmp_path / "f.sqlite")


def test_an_unopenable_path_is_a_startup_error(tmp_path):
    with pytest.raises(TAT_StartupError, match="unable to open"):
        Forest_Store(tmp_path / "nope" / "f.sqlite")


def test_a_file_that_is_not_a_database_is_a_startup_error(tmp_path):
    path = tmp_path / "f.sqlite"
    path.write_bytes(b"this is not a database, and longer than a header\n" * 4)
    with pytest.raises(TAT_StartupError, match="f.sqlite"):
        Forest_Store(path)


def test_other_threads_are_refused(store):
    outcome: list = []

    def use() -> None:
        try:
            store.nodes()
            outcome.append("ran")
        except sqlite3.ProgrammingError as e:
            outcome.append(e)

    t = threading.Thread(target=use)
    t.start()
    t.join()
    assert isinstance(outcome[0], sqlite3.ProgrammingError), outcome


CRASH_SCRIPT = """
import os, sys
sys.path.insert(0, sys.argv[2])
from isabelle_theory_agent.store import Forest_Store
s = Forest_Store(sys.argv[1])
with s.transaction():
    s.put(1, "kind", "theory")
    s.put(1, "name", "X")
with s.transaction():
    s.put(2, "kind", "lemma")
    s.next_identity()
    s.delete_node(1)
    os._exit(17)          # dies mid-operation: no COMMIT, no ROLLBACK, no close
"""


def test_a_process_dying_mid_operation_leaves_the_last_committed_forest(tmp_path):
    path = tmp_path / "f.sqlite"
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run([sys.executable, "-c", CRASH_SCRIPT, str(path), repo],
                          capture_output=True, text=True)
    assert proc.returncode == 17, proc.stderr
    with Forest_Store(path) as s:
        assert s.nodes() == [1]
        assert s.fields(1) == {"kind": "theory", "name": "X"}
        assert s.fields(2) == {}
        assert s.next_identity() == 1
