"""The forest's persistence: one SQLite database, one row per node field
(ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §2).

`fields (node, field, value)` keyed by `(node, field)`: `node` is the node's
identity number, `value` the field in MessagePack.  `meta` holds the identity
counter and the schema version.

Every write happens inside `transaction()`, one per write operation, except
`next_identity`, which is its own write when no transaction is open.  A
transaction is held within one synchronous stretch, never across an
`await`: it opens once the operation has succeeded in memory and closes
before the next `await`, or two write operations would share it.  Reads
need no transaction.

There is no per-field delete: to rewrite a node's fields, `delete_node` and
`put` them again inside the one transaction.  `delete_node` removes one node;
deleting a subtree is the caller's walk.

The connection belongs to the thread that opened the store — `sqlite3`
refuses any other — so background work hands its results to the event loop
instead of writing.

MessagePack round-trips `str`, `bytes`, `bool`, `float`, `None`, `list`, and
`dict` with scalar keys; `int` within -2**63 .. 2**64-1; a tuple comes back
as a list.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import msgpack

from .exceptions import TAT_InternalError, TAT_StartupError

SCHEMA_VERSION = 1
SQLITE_MINIMUM = (3, 37, 0)          # STRICT tables; the library Python links, not a package


# The one pack/unpack pair every row goes through: what one accepts, the
# other reads back.
def _pack(value: Any) -> bytes:
    blob = cast(bytes, msgpack.packb(value))
    _unpack(blob)         # a value _unpack refuses must not reach the file
    return blob


def _unpack(blob: bytes) -> Any:
    return msgpack.unpackb(blob, strict_map_key=False)


class IncompatibleStore(TAT_StartupError):
    """The database was written under another schema version."""


class Forest_Store:

    def __init__(self, path: str | Path):
        if sqlite3.sqlite_version_info < SQLITE_MINIMUM:
            raise TAT_StartupError(
                f"TAT needs SQLite {'.'.join(map(str, SQLITE_MINIMUM))} or newer;"
                f" this Python links {sqlite3.sqlite_version}")
        try:
            # autocommit mode: the only transactions are the explicit ones below
            self._conn = sqlite3.connect(path, isolation_level=None, check_same_thread=True)
        except sqlite3.Error as e:
            raise TAT_StartupError(f"{path}: {e}") from e
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            with self.transaction():
                self._conn.execute(
                    "CREATE TABLE IF NOT EXISTS fields ("
                    " node INTEGER NOT NULL, field TEXT NOT NULL, value BLOB NOT NULL,"
                    " PRIMARY KEY (node, field)) STRICT")
                self._conn.execute(
                    "CREATE TABLE IF NOT EXISTS meta ("
                    " key TEXT PRIMARY KEY, value BLOB NOT NULL) STRICT")
                version = self._meta("schema_version")
                if version is None:
                    self._set_meta("schema_version", SCHEMA_VERSION)
                    self._set_meta("next_identity", 1)
                elif version != SCHEMA_VERSION:
                    raise IncompatibleStore(
                        f"{path}: schema version {version}, this TAT reads {SCHEMA_VERSION}")
        except sqlite3.Error as e:
            self._conn.close()
            raise TAT_StartupError(f"{path}: {e}") from e
        except ValueError as e:              # msgpack: the meta blob is unreadable
            self._conn.close()
            raise TAT_StartupError(f"{path}: meta is not readable ({type(e).__name__})") from e
        except BaseException:
            self._conn.close()
            raise

    # -- transactions --------------------------------------------------------

    @contextmanager
    def transaction(self) -> Generator[None]:
        """One write operation.  Commits on exit; on an exception rolls back
        and lets it propagate.

        Never `await` inside: the transaction opens once the operation has
        succeeded in memory and closes before the next `await`.  Nothing
        enforces this; a transaction crossing an `await` lets another write
        operation's `next_identity` join it and roll back with it, and the
        identity is then handed out twice.  Code review keeps the rule."""
        if self._conn.in_transaction:
            raise TAT_InternalError("Forest_Store: a transaction is already open")
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self._conn.execute("COMMIT")
        finally:
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")

    def _writing(self) -> None:
        if not self._conn.in_transaction:
            raise TAT_InternalError("Forest_Store: write outside a transaction")

    # -- node fields ---------------------------------------------------------

    def put(self, node: int, field: str, value: Any) -> None:
        self._writing()
        try:
            blob = _pack(value)
        except (TypeError, ValueError, OverflowError) as e:
            raise TAT_InternalError(
                f"Forest_Store: field `{field}` of node {node} does not survive"
                f" a MessagePack round trip: {e}") from e
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO fields (node, field, value) VALUES (?, ?, ?)",
                (node, field, blob))
        except sqlite3.IntegrityError as e:     # STRICT: a node or field of the wrong type
            raise TAT_InternalError(f"Forest_Store: field `{field}` of node {node}: {e}") from e

    def get(self, node: int, field: str) -> Any:
        """KeyError when the node has no such field; a stored None is a value."""
        row = self._conn.execute(
            "SELECT value FROM fields WHERE node = ? AND field = ?", (node, field)).fetchone()
        if row is None:
            raise KeyError((node, field))
        return _unpack(row[0])

    def fields(self, node: int) -> dict[str, Any]:
        return {field: _unpack(blob) for field, blob in self._conn.execute(
            "SELECT field, value FROM fields WHERE node = ?", (node,))}

    def delete_node(self, node: int) -> None:
        self._writing()
        self._conn.execute("DELETE FROM fields WHERE node = ?", (node,))

    def nodes(self) -> list[int]:
        return [node for (node,) in self._conn.execute(
            "SELECT DISTINCT node FROM fields ORDER BY node")]

    # -- identities ----------------------------------------------------------

    def next_identity(self) -> int:
        """A fresh identity number: unique among the identities of committed
        operations, restarts included.  Inside a transaction it belongs to
        that operation and rolls back with it -- an identity handed out in a
        rolled-back operation is handed out again; outside one it is its own
        write."""
        identity = self._meta("next_identity")
        self._set_meta("next_identity", identity + 1)
        return identity

    def _meta(self, key: str) -> Any:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else _unpack(row[0])

    def _set_meta(self, key: str, value: Any) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, _pack(value)))

    # -- lifetime ------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Forest_Store:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
