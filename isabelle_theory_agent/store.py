"""The forest's persistence: one SQLite database, one row per node field
(ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §2).

`fields (node, field, value)` keyed by `(node, field)`: `node` is the node's
identity number, `value` the field in MessagePack.  `meta` holds the identity
counter and the schema version.

Every write happens inside `transaction()`, one per write operation, except
`next_identity`, which is its own write when no transaction is open.  A
transaction is held within one synchronous stretch, never across an
`await`: it opens once the operation has succeeded in memory and closes
before the next `await`, or two write operations would share it.  Because
it opens only after the operation is committed in memory, a transaction
that fails leaves memory and database apart: it raises `TAT_DisasterError`
(EXCEPTIONS.md §1) and the conversation ends.  Reads need no transaction.

There is no per-field delete: to rewrite a node's fields, `delete_node` and
`put` them again inside the one transaction.  `delete_node` removes one node;
deleting a subtree is the caller's walk.

Some rows of a node are the framework's (`FRAMEWORK_FIELDS`); a node class
reaches its own fields through `Node_Rows`, which refuses to write those.

The connection belongs to the thread that opened the store — `sqlite3`
refuses any other — so background work hands its results to the event loop
instead of writing.

MessagePack round-trips `str`, `bytes`, `bool`, `float`, `None`, `list`, and
`dict` with scalar keys; `int` within -2**63 .. 2**64-1; a tuple comes back
as a list.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import msgpack

from .exceptions import TAT_DisasterError, TAT_InternalError, TAT_StartupError

if TYPE_CHECKING:
    from .log import Log

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


def _read(node: int, field: str, blob: bytes) -> Any:
    """A stored field's value; a blob `_pack` cannot have written is damage
    to the database.  Loading is the only reader, so it is a startup error,
    as damaged meta is when the database is opened."""
    try:
        return _unpack(blob)
    except (ValueError, TypeError) as e:          # malformed bytes: msgpack raises ValueError,
        raise TAT_StartupError(                   # or TypeError for an unhashable map key
            f"the forest database's field `{field}` of node {node} is not readable"
            f" ({type(e).__name__})") from e


class IncompatibleStore(TAT_StartupError):
    """The database was written under another schema version."""


class MissingRow(KeyError):
    """`get` found no row `(node, field)`."""

    def __init__(self, node: int, field: str):
        super().__init__((node, field))
        self.node = node
        self.field = field


class Forest_Store:

    def __init__(self, path: str | Path, log: Log, read_only: bool = False):
        """`log` is the conversation's, for the `store` records of every
        transaction (LOGGING.md §4).  `read_only` is a compile's
        (COMPILATION.md §5): the connection cannot write, and a database
        without the store's tables — `TAT_new`'s, before any conversation
        — is read as the empty forest."""
        if sqlite3.sqlite_version_info < SQLITE_MINIMUM:
            raise TAT_StartupError(
                f"TAT needs SQLite {'.'.join(map(str, SQLITE_MINIMUM))} or newer;"
                f" this Python links {sqlite3.sqlite_version}")
        self._log = log
        # the open transaction's net effect: a node's fields written, or
        # None once it was deleted — what the `transaction` record says
        self._changed: dict[int, list[str] | None] = {}
        self._conn = self._connect(path)
        try:
            if read_only and self._has_tables():
                self._check_version(path)
            else:
                if read_only:                   # the empty forest, set up in memory
                    self._conn.close()
                    self._conn = self._connect(":memory:")
                self._conn.execute("PRAGMA journal_mode=WAL")
                with self._transaction():       # nothing is committed in memory yet
                    self._conn.execute(
                        "CREATE TABLE IF NOT EXISTS fields ("
                        " node INTEGER NOT NULL, field TEXT NOT NULL, value BLOB NOT NULL,"
                        " PRIMARY KEY (node, field)) STRICT")
                    self._conn.execute(
                        "CREATE TABLE IF NOT EXISTS meta ("
                        " key TEXT PRIMARY KEY, value BLOB NOT NULL) STRICT")
                    if self._meta("schema_version") is None:
                        self._set_meta("schema_version", SCHEMA_VERSION)
                        self._set_meta("next_identity", 1)  # 0 is the forest root's
                    self._check_version(path)
            if read_only:
                self._conn.execute("PRAGMA query_only = 1")
        except sqlite3.Error as e:
            self._conn.close()
            raise TAT_StartupError(f"{path}: {e}") from e
        except (ValueError, TypeError) as e:     # malformed meta bytes (see _read)
            self._conn.close()
            raise TAT_StartupError(f"{path}: meta is not readable ({type(e).__name__})") from e
        except BaseException:
            self._conn.close()
            raise

    @staticmethod
    def _connect(path: str | Path) -> sqlite3.Connection:
        try:
            # autocommit mode: the only transactions are the explicit ones below
            return sqlite3.connect(path, isolation_level=None, check_same_thread=True)
        except sqlite3.Error as e:
            raise TAT_StartupError(f"{path}: {e}") from e

    def _has_tables(self) -> bool:
        names = {name for (name,) in self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('fields', 'meta')")}
        return names == {"fields", "meta"}

    def _check_version(self, path: str | Path) -> None:
        version = self._meta("schema_version")
        if version != SCHEMA_VERSION:
            raise IncompatibleStore(
                f"{path}: schema version {version}, this TAT reads {SCHEMA_VERSION}")
        if type(self._meta("next_identity")) is not int:
            raise TAT_StartupError(f"{path}: meta `next_identity` is not an identity")

    # -- transactions --------------------------------------------------------

    @contextmanager
    def transaction(self) -> Generator[None]:
        """One write operation.  Commits on exit; on an exception rolls back
        and raises `TAT_DisasterError` from it -- the operation is already
        committed in memory, so memory and database have parted.

        Never `await` inside: the transaction opens once the operation has
        succeeded in memory and closes before the next `await`.  A
        transaction crossing an `await` lets another write operation's
        `next_identity` join it and roll back with it, and the identity is
        then handed out twice.  No runtime guard enforces this; the test
        suite's fake driver asserts it at every round trip."""
        if self._conn.in_transaction:
            raise TAT_InternalError("Forest_Store: a transaction is already open")
        self._changed = {}
        started = time.monotonic()
        try:
            with self._transaction():
                yield
        except Exception as e:
            message = f"Forest_Store: a write operation failed after its commit in memory: {e}"
            self._log.store.transaction_failed(message=message)
            raise TAT_DisasterError(message) from e
        self._log.store.transaction(
            rows_written=[[node, field] for node, fields in self._changed.items()
                          if fields is not None for field in fields],
            nodes_deleted=[node for node, fields in self._changed.items() if fields is None],
            duration=time.monotonic() - started)

    @contextmanager
    def _transaction(self) -> Generator[None]:
        """The bare transaction: commit on exit, roll back and let the
        exception through otherwise.  For opening the database, where no
        operation is committed in memory."""
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
        fields = self._changed.get(node)
        if fields is None:                      # the node's first row, or its first after a delete
            self._changed[node] = fields = []
        if field not in fields:
            fields.append(field)

    def get(self, node: int, field: str) -> Any:
        """`MissingRow`, a KeyError, when the node has no such field; a stored
        None is a value."""
        row = self._conn.execute(
            "SELECT value FROM fields WHERE node = ? AND field = ?", (node, field)).fetchone()
        if row is None:
            raise MissingRow(node, field)
        return _read(node, field, row[0])

    def fields(self, node: int) -> dict[str, Any]:
        return {field: _read(node, field, blob) for field, blob in self._conn.execute(
            "SELECT field, value FROM fields WHERE node = ?", (node,))}

    def delete_node(self, node: int) -> None:
        self._writing()
        self._conn.execute("DELETE FROM fields WHERE node = ?", (node,))
        self._changed[node] = None

    def nodes(self) -> list[int]:
        return [node for (node,) in self._conn.execute(
            "SELECT DISTINCT node FROM fields ORDER BY node")]

    def rows(self, node: int) -> Node_Rows:
        return Node_Rows(self, node)

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


# The framework's two fields of a construct (MODULE_STRUCTURE §4.2): `kind`
# selects the class and `children` holds a nesting node's contents.  Each
# is also a row the framework stores.
CONSTRUCT_FRAMEWORK_FIELDS = ("kind", "children")

# The rows the framework stores of a node, never a class's (the plan's §2;
# the stored statuses, COMPILATION.md §4; the jobs' images and the
# automatic-construction setting, ARCHITECTURE §4.1).
FRAMEWORK_FIELDS = (*CONSTRUCT_FRAMEWORK_FIELDS, "last_evaluation_statuses", "job", "check",
                    "auto_construct")


class Node_Rows:
    """One node's rows, as a node class sees them in `to_store` and
    `from_store` (ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §2): its own
    fields to write and read, the framework's rows (`FRAMEWORK_FIELDS`) to
    read only.  Made by `Forest_Store.rows` for one call; a class never
    keeps it."""

    def __init__(self, store: Forest_Store, node: int):
        self._store = store
        self._node = node

    def put(self, field: str, value: Any) -> None:
        if field in FRAMEWORK_FIELDS:
            raise TAT_InternalError(
                f"Node_Rows: `{field}` is the framework's field, not the class's")
        self._store.put(self._node, field, value)

    def get(self, field: str) -> Any:
        """`MissingRow`, a KeyError, when the node has no such field; a stored
        None is a value."""
        return self._store.get(self._node, field)

    def fields(self) -> dict[str, Any]:
        """The class's own fields; the framework's rows are left out."""
        return {field: value for field, value in self._store.fields(self._node).items()
                if field not in FRAMEWORK_FIELDS}
