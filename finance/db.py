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
        # Postgres runs a multi-statement string in one call, but only when the
        # statements carry no parameters — which is true of the schema.
        cur.execute(to_postgres(script))
        return cur

    def commit(self):
        self._raw.commit()
        self._path_set = False          # the next transaction sets it again

    def close(self):
        self._raw.close()


@contextmanager
def connect(path: str, url: str | None = None, schema: str = "public"):
    """Open the ledger: Postgres when a URL is configured, SQLite otherwise.

    `schema` picks the account's ledger on Postgres. On SQLite each account
    has its own file instead, so it is the path that differs and this is
    unused.
    """
    url = url or database_url()
    if url:
        import psycopg
        from psycopg.rows import dict_row

        raw = psycopg.connect(url, row_factory=dict_row)
        conn = _PgConnection(raw, schema)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
        return

    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


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
