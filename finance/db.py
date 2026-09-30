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


def database_url() -> str | None:
    """The hosted Postgres URL, if one is configured.

    Vercel's Postgres integrations inject several aliases. The pooled URL is
    preferred: a serverless function opens a connection per request, and an
    unpooled Postgres runs out of connection slots long before it runs out of
    anything else.
    """
    for key in ("DATABASE_URL_POOLED", "POSTGRES_PRISMA_URL", "POSTGRES_URL",
                "DATABASE_URL"):
        value = os.environ.get(key)
        if value and value.startswith(("postgres://", "postgresql://")):
            return value
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


class _PgConnection:
    """A psycopg connection that speaks the SQLite dialect `store.py` writes.

    Exposes only what the store uses: `execute`, `executemany` and
    `executescript`, each returning a cursor whose rows behave like
    `sqlite3.Row` — indexable by column name and convertible with `dict()`.
    """

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        cur = self._raw.cursor()
        cur.execute(to_postgres(sql), tuple(params))
        return cur

    def executemany(self, sql, seq):
        rows = [tuple(r) for r in seq]
        if not rows:
            # A cursor that never executed reports rowcount -1, where SQLite
            # reports 0. Callers read this as "how many rows were written", and
            # an import where every row was a duplicate writes none.
            return _EmptyResult()
        cur = self._raw.cursor()
        cur.executemany(to_postgres(sql), rows)
        return cur

    def executescript(self, script):
        cur = self._raw.cursor()
        # Postgres runs a multi-statement string in one call, but only when the
        # statements carry no parameters — which is true of the schema.
        cur.execute(to_postgres(script))
        return cur

    def commit(self):
        self._raw.commit()

    def close(self):
        self._raw.close()


@contextmanager
def connect(path: str, url: str | None = None):
    """Open the ledger: Postgres when a URL is configured, SQLite otherwise."""
    url = url or database_url()
    if url:
        import psycopg
        from psycopg.rows import dict_row

        raw = psycopg.connect(url, row_factory=dict_row)
        conn = _PgConnection(raw)
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
