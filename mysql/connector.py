"""Compatibility layer mapping mysql.connector API calls to psycopg."""

from __future__ import annotations

from typing import Any, Iterable, Optional

import psycopg
from psycopg import conninfo as pg_conninfo
from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

__all__ = [
    "connect",
    "Error",
    "ProgrammingError",
    "IntegrityError",
    "OperationalError",
    "pooling",
]


class Error(Exception):
    """Base error to mirror mysql.connector.Error."""


class ProgrammingError(Error):
    """Raised for SQL programming issues."""


class IntegrityError(Error):
    """Raised for constraint violations."""


class OperationalError(Error):
    """Raised for operational issues such as connection problems."""


class errors:  # pylint: disable=too-few-public-methods
    Error = Error
    ProgrammingError = ProgrammingError
    IntegrityError = IntegrityError
    OperationalError = OperationalError


def _translate_exception(exc: Exception) -> Error:
    if isinstance(exc, pg_errors.IntegrityError):
        return IntegrityError(str(exc))
    if isinstance(exc, pg_errors.ProgrammingError):
        return ProgrammingError(str(exc))
    if isinstance(exc, psycopg.OperationalError):
        return OperationalError(str(exc))
    if isinstance(exc, psycopg.Error):
        return Error(str(exc))
    return Error(str(exc))


def _prepare_conn_kwargs(kwargs: dict[str, Any]) -> tuple[dict[str, Any], Optional[str]]:
    params = dict(kwargs)

    # Normalise keys to psycopg style
    database = params.pop("database", params.pop("dbname", None))
    if database:
        params["dbname"] = database

    schema = params.pop("schema", None)
    options = params.get("options")

    schema_name: Optional[str] = None

    if schema:
        schema_name = schema
        params["options"] = f"-c search_path={schema_name}"
    elif isinstance(options, str) and "search_path" in options:
        # Parse search_path from options like "-c search_path=vocab" or "-c search_path='vocab'"
        try:
            fragment = options.split("search_path=")[1]
            schema_name = fragment.split()[0].strip("\"'")
        except Exception:  # pragma: no cover - defensive parsing
            schema_name = None

    if schema_name and not params.get("options"):
        params["options"] = f"-c search_path={schema_name}"

    # Drop mysql-specific parameters if callers set them
    for redundant in (
        "pool_name",
        "pool_size",
        "pool_reset_session",
        "autocommit",
        "buffered",
        "charset",
        "collation",
    ):
        params.pop(redundant, None)

    return params, schema_name


class ConnectionWrapper:
    def __init__(self, conn: psycopg.Connection, schema: Optional[str] = None):
        self._conn = conn
        self._schema = schema
        if schema:
            self._ensure_search_path()

    # Context manager support -------------------------------------------------
    def __enter__(self):  # pragma: no cover - convenience API
        return self

    def __exit__(self, exc_type, exc, tb):  # pragma: no cover - convenience API
        if exc:
            self.rollback()
        else:
            self.commit()
        self.close()
        return False

    # Helpers -----------------------------------------------------------------
    def _ensure_search_path(self):
        if self._schema:
            self._conn.execute(
                f'SET search_path TO "{self._schema}"',
                prepare=False,
            )

    # Public API --------------------------------------------------------------
    def cursor(self, dictionary: bool = False, **kwargs) -> "CursorWrapper":
        if dictionary:
            kwargs.setdefault("row_factory", dict_row)
        try:
            cur = self._conn.cursor(**kwargs)
            return CursorWrapper(cur)
        except Exception as exc:  # pragma: no cover - defensive
            raise _translate_exception(exc) from exc

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def is_connected(self) -> bool:
        return not self._conn.closed

    @property
    def autocommit(self) -> bool:
        return self._conn.autocommit

    @autocommit.setter
    def autocommit(self, value: bool) -> None:
        self._conn.autocommit = value


class CursorWrapper:
    def __init__(self, cursor: psycopg.Cursor):
        self._cursor = cursor

    def __enter__(self):  # pragma: no cover - convenience
        return self

    def __exit__(self, exc_type, exc, tb):  # pragma: no cover
        self.close()
        return False

    def execute(self, query: str, params: Optional[Iterable[Any]] = None):
        try:
            return self._cursor.execute(query, params)
        except Exception as exc:
            raise _translate_exception(exc) from exc

    def executemany(self, query: str, params_list: Iterable[Iterable[Any]]):
        try:
            return self._cursor.executemany(query, params_list)
        except Exception as exc:
            raise _translate_exception(exc) from exc

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchmany(self, size: int | None = None):
        if size is None:
            return self._cursor.fetchmany()
        return self._cursor.fetchmany(size)

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        return getattr(self._cursor, "lastrowid", None)

    @property
    def description(self):
        return self._cursor.description

    def close(self):
        self._cursor.close()


def connect(**kwargs) -> ConnectionWrapper:
    params, schema = _prepare_conn_kwargs(kwargs)
    try:
        conn = psycopg.connect(**params)
        return ConnectionWrapper(conn, schema)
    except Exception as exc:  # pragma: no cover - defensive
        raise _translate_exception(exc) from exc


class _PooledConnectionWrapper(ConnectionWrapper):
    def __init__(self, pool: ConnectionPool, schema: Optional[str]):
        self._pool = pool
        self._schema_name = schema
        self._ctx = self._pool.connection()
        conn = self._ctx.__enter__()
        super().__init__(conn, schema)

    def close(self):
        if hasattr(self, "_ctx") and self._ctx:
            self._ctx.__exit__(None, None, None)
            self._ctx = None


class pooling:  # pylint: disable=too-few-public-methods
    class MySQLConnectionPool:
        def __init__(self, **kwargs):
            params, schema = _prepare_conn_kwargs(kwargs)
            max_size = kwargs.get("pool_size", 10)
            conninfo = pg_conninfo.make_conninfo(**params)
            self._schema = schema
            self._pool = ConnectionPool(
                conninfo=conninfo,
                min_size=1,
                max_size=max_size,
                timeout=kwargs.get("timeout", 30),
                name=kwargs.get("pool_name", "vocabulary_pool"),
            )

        def get_connection(self) -> ConnectionWrapper:
            return _PooledConnectionWrapper(self._pool, self._schema)

        def close(self):
            self._pool.close()
