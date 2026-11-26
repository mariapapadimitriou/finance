"""One store, two databases.

Locally the ledger is a SQLite file and nothing leaves the machine. On a
serverless host there is no durable disk — `/tmp` belongs to one function
instance and is discarded when that instance is recycled — so an upload made
there would survive minutes, not days. Pointing `DATABASE_URL` at a hosted
Postgres makes it durable and makes every instance see the same ledger.

Rather than maintain two copies of every query, `store.py` stays written in
SQLite's dialect and the handful of places Postgres spells things differently
are translated here, on the way to the driver:

  ``?`` → ``%s``            positional placeholders
  ``LIKE`` → ``ILIKE``      SQLite's LIKE ignores ASCII case; Postgres' does not,
                            so the merchant search would quietly stop matching
  ``INSERT OR IGNORE``      → ``INSERT … ON CONFLICT DO NOTHING``
  ``AUTOINCREMENT`` keys    → ``SERIAL``
  ``REAL``                  → ``DOUBLE PRECISION`` (Postgres' REAL is a 4-byte
                            float, which loses cents on large sums)

The translation is small enough to read in one sitting and is unit-tested
directly, because a silent mistranslation would corrupt data rather than raise.
It is deliberately not a general SQL parser: it assumes the queries in
`store.py`, which contain no string literals with ``?`` or ``%`` in them.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


# Connecting a database on Vercel injects a dozen aliases of the same
# credentials, and they are not interchangeable. These are tried in order:
# pooled first, because a serverless function opens a connection per request and
# an unpooled Postgres runs out of connection slots long before anything else
# gives way. Neon's DATABASE_URL is already the pooled endpoint.
#
# POSTGRES_PRISMA_URL is deliberately absent. It is the same pooled host with
# Prisma's own options glued on, and libpq rejects the whole connection string
# on the first one it doesn't recognise.
URL_KEYS = (
    "DATABASE_URL_POOLED",       # some providers spell it this way
    "DATABASE_URL",              # Neon: pooled
    "POSTGRES_URL",              # Vercel Postgres: pooled
    "DATABASE_URL_UNPOOLED",     # last resorts — direct connections
    "POSTGRES_URL_NON_POOLING",
)

# Query parameters that belong to an ORM rather than to libpq. Passing any of
# them to psycopg raises `invalid URI query parameter`, which would take every
# request down, so they are dropped rather than trusted.
_DRIVER_ONLY_PARAMS = frozenset({
    "pgbouncer", "schema", "connection_limit", "pool_timeout",
    "statement_cache_size", "prepare_threshold", "prepareThreshold",
    "sslaccept", "supa",
})


def _strip_driver_params(url: str) -> str:
    """Remove options libpq doesn't understand, keeping everything it does."""
    split = urlsplit(url)
    if not split.query:
        return url
    kept = [(k, v) for k, v in parse_qsl(split.query, keep_blank_values=True)
            if k not in _DRIVER_ONLY_PARAMS]
    return urlunsplit(split._replace(query=urlencode(kept)))


def database_url() -> str | None:
    """The hosted Postgres URL, if one is configured."""
    for key in URL_KEYS:
        value = os.environ.get(key)
        if value and value.startswith(("postgres://", "postgresql://")):
            return _strip_driver_params(value)
    return None


# ── SQL translation ──────────────────────────────────────────────────────────

_PLACEHOLDER = re.compile(r"\?")
_LIKE = re.compile(r"\bLIKE\b", re.IGNORECASE)
_INSERT_OR_IGNORE = re.compile(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", re.IGNORECASE)
_AUTOINC = re.compile(r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", re.IGNORECASE)
_REAL = re.compile(r"\bREAL\b", re.IGNORECASE)
_CURRENT_TS = re.compile(r"\bTEXT\s+DEFAULT\s+CURRENT_TIMESTAMP\b", re.IGNORECASE)


def to_postgres(sql: str) -> str:
    """Rewrite one SQLite statement for Postgres."""
    had_or_ignore = bool(_INSERT_OR_IGNORE.search(sql))
    sql = _INSERT_OR_IGNORE.sub("INSERT INTO", sql)
    sql = _AUTOINC.sub("SERIAL PRIMARY KEY", sql)
    sql = _CURRENT_TS.sub("TEXT DEFAULT (now()::text)", sql)
    sql = _REAL.sub("DOUBLE PRECISION", sql)
    sql = _LIKE.sub("ILIKE", sql)
    sql = _PLACEHOLDER.sub("%s", sql)

    if had_or_ignore:
        # Appending is safe because every INSERT OR IGNORE in this codebase is a
        # plain `INSERT … VALUES (…)` with nothing after it.
        sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return sql


class _EmptyResult:
    """Stands in for a cursor when there was nothing to execute."""

    rowcount = 0

    def fetchone(self):
        return None

    def fetchall(self):
        return []


_SCHEMA_NAME = re.compile(r"^(public|u_[0-9]+)$")


def valid_schema(name: str) -> str:
    """A schema name this module will put into SQL: public, or u_<id>."""
    if not _SCHEMA_NAME.match(name or ""):
        raise ValueError(f"not a ledger schema: {name!r}")
    return name


class _PgConnection:
    """A psycopg connection that speaks the SQLite dialect `store.py` writes.

    Exposes only what the store uses: `execute`, `executemany` and
    `executescript`, each returning a cursor whose rows behave like
    `sqlite3.Row` — indexable by column name and convertible with `dict()`.

    Each account's ledger is its own schema, chosen per transaction with
    `SET LOCAL search_path`. LOCAL is the whole point: the URL is a pooled
    endpoint, and a plain `SET` would stay on the shared server connection
    after this one hands it back — the next person's query could then run
    against someone else's tables. `SET LOCAL` ends with the transaction, so
    it is issued again at the start of each one.
    """

    def __init__(self, raw, schema: str = "public"):
        self._raw = raw
        self._schema = valid_schema(schema)
        self._path_set = False

    def _cursor(self):
        cur = self._raw.cursor()
        if not self._path_set:
            cur.execute(f'SET LOCAL search_path TO "{self._schema}"')
            self._path_set = True
        return cur

    def execute(self, sql, params=()):
        cur = self._cursor()
        cur.execute(to_postgres(sql), tuple(params))
        return cur

    def executemany(self, sql, seq):
        rows = [tuple(r) for r in seq]
        if not rows:
            # A cursor that never executed reports rowcount -1, where SQLite
            # reports 0. Callers read this as "how many rows were written", and
            # an import where every row was a duplicate writes none.
            return _EmptyResult()
        cur = self._cursor()
        cur.executemany(to_postgres(sql), rows)
        return cur

    def executescript(self, script):
        cur = self._cursor()
        # Two requests on a cold start both create the schema, and Postgres
        # lets CREATE TABLE IF NOT EXISTS race: the second fails on the table's
        # type name instead of finding the table. A lock held until this
        # transaction ends makes the second wait, then find it there.
        cur.execute(f"SELECT pg_advisory_xact_lock({SCHEMA_LOCK})")
        # Postgres runs a multi-statement string in one call, but only when the
        # statements carry no parameters — which is true of the schema.
        cur.execute(to_postgres(script))
        return cur

    def commit(self):
        self._raw.commit()
        self._path_set = False          # the next transaction sets it again

    def close(self):
        self._raw.close()


# The advisory lock schema creation takes (any fixed number will do).
SCHEMA_LOCK = 7_370_517


# One kept Postgres connection per ledger per thread (2026-10-16, reworked
# 2026-11-19). The store opens a transaction per method, and a page like Home
# called it a hundred and more times; opening a fresh TLS connection to the
# pooled endpoint for each one was most of what made every page take seconds.
# Keeping the connection saved the handshake; what remained was SET LOCAL and
# COMMIT per method, a few network round trips each, seventy-odd times a
# page. So a request now runs in ONE transaction per ledger: the first
# `connect(..., request_scope=True)` opens it, every later `with` on the same
# ledger joins it, and `finish_request()` commits at the end of the request
# (`abandon_request()` rolls back if it failed). Outside a request, or when
# `request_scope` is False, a `with` is one transaction as before.
#
# A connection that sat idle is pinged before reuse, and one that broke is
# dropped and replaced.
_local = threading.local()
IDLE_PING_AFTER = 30.0          # seconds idle before a SELECT 1 checks it


class _Open:
    """A transaction in progress on this thread."""
    __slots__ = ("conn", "raw", "depth", "scoped")

    def __init__(self, conn, raw, scoped: bool):
        self.conn, self.raw, self.depth, self.scoped = conn, raw, 1, scoped


def _state():
    if not hasattr(_local, "open"):
        _local.open = {}        # key -> _Open: transactions in progress
        _local.raws = {}        # key -> (raw psycopg connection, last used)
    return _local


def _key(path: str, url: str | None, schema: str) -> tuple:
    if url:
        return ("pg", url, valid_schema(schema))
    return ("sqlite", os.path.abspath(path))


def _drop_pg(key=None) -> None:
    st = _state()
    for k in ([key] if key is not None else list(st.raws)):
        raw, _ = st.raws.pop(k, (None, None))
        if raw is not None:
            try:
                raw.close()
            except Exception:                                    # noqa: BLE001
                pass


def _pg_raw(key, url: str):
    """The thread's kept connection for `key`, checked, or a new one."""
    import psycopg
    from psycopg.rows import dict_row

    st = _state()
    now = time.monotonic()
    cached = st.raws.get(key)
    if cached is not None:
        raw, last = cached
        alive = not raw.closed and not getattr(raw, "broken", False)
        if alive and now - last > IDLE_PING_AFTER:
            try:
                with raw.cursor() as cur:
                    cur.execute("SELECT 1")
                raw.rollback()
            except Exception:                                    # noqa: BLE001
                alive = False
        if alive:
            return raw
        _drop_pg(key)
    raw = psycopg.connect(url, row_factory=dict_row)
    st.raws[key] = (raw, now)
    return raw


def close_cached() -> None:
    """Close this thread's kept connections (tests, and a clean shutdown)."""
    st = _state()
    for key in list(st.open):
        _end(key, commit=False)
    _drop_pg()


def _count_transaction() -> None:
    """Tell the request's Server-Timing a transaction began (finance/timing.py)."""
    from . import timing
    timing.transaction()


def _end(key, commit: bool) -> None:
    """Finish the transaction on `key`: commit or roll back, then keep a
    Postgres connection for the next one and close a SQLite one."""
    st = _state()
    open_ = st.open.pop(key, None)
    if open_ is None:
        return
    raw = open_.raw
    if key[0] == "pg":
        try:
            if commit:
                open_.conn.commit()
            else:
                try:
                    raw.rollback()
                except Exception:                                # noqa: BLE001
                    pass
        finally:
            if raw.closed or getattr(raw, "broken", False):
                _drop_pg(key)
            else:
                st.raws[key] = (raw, time.monotonic())
        return
    try:
        if commit:
            raw.commit()
        else:
            raw.rollback()
    finally:
        raw.close()


def finish_request(commit: bool = True) -> None:
    """End every request-scoped transaction on this thread, the latest
    opened first: an account's ledger commits before the accounts table."""
    st = _state()
    for key in reversed(list(st.open)):
        if st.open[key].scoped:
            _end(key, commit)


def abandon_request() -> None:
    """Roll back whatever a failed request left open."""
    finish_request(commit=False)


@contextmanager
def connect(path: str, url: str | None = None, schema: str = "public", *,
            request_scope: bool = False):
    """Open the ledger: Postgres when a URL is configured, SQLite otherwise.

    `schema` picks the account's ledger on Postgres. On SQLite each account
    has its own file instead, so it is the path that differs and this is
    unused.

    Each outermost `with` is one transaction: committed on the way out,
    rolled back on an exception. A `with` inside another one on the same
    ledger and thread joins the outer transaction instead of starting its own.
    With `request_scope`, the transaction stays open after the `with` and is
    ended by `finish_request()` / `abandon_request()`, so a whole request is
    one transaction; every later `with` on that ledger joins it.
    """
    # None means "whatever is configured"; an empty string is a store opened
    # on SQLite on purpose (`Store(path, url="")`), which says it isn't
    # Postgres and must not be handed the configured database anyway.
    url = database_url() if url is None else url
    st = _state()
    key = _key(path, url, schema)
    open_ = st.open.get(key)
    if open_ is not None:
        open_.depth += 1
        try:
            yield open_.conn
        finally:
            open_.depth -= 1
        return

    _count_transaction()
    if url:
        raw = _pg_raw(key, url)
        conn = _PgConnection(raw, schema)
    else:
        raw = sqlite3.connect(path, timeout=10)
        raw.row_factory = sqlite3.Row
        conn = raw
    open_ = _Open(conn, raw, scoped=request_scope)
    st.open[key] = open_
    try:
        yield conn
    except BaseException:
        _end(key, commit=False)
        raise
    else:
        open_.depth -= 1
        if not request_scope:
            _end(key, commit=True)


def is_postgres() -> bool:
    return database_url() is not None


def is_hosted() -> bool:
    """True on a serverless host rather than a developer machine."""
    return bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))


def storage_mode() -> str:
    """How durable this instance's ledger is — reported by /api/health.

    `ephemeral` is the one the UI warns about: a hosted instance with no
    database keeps the ledger in its own /tmp, so an upload lasts only as long
    as that instance and is invisible to every other one.
    """
    if database_url():
        return "postgres"
    if is_hosted():
        return "ephemeral"
    return "sqlite"
