"""Optionally run the whole suite against a real Postgres.

The store is written once in SQLite's dialect and translated for Postgres (see
`finance/db.py`), which means the translation is only as trustworthy as the
coverage behind it. Unit-testing the rewriter catches typos; it does not catch
the differences that only a real server objects to — Postgres rejecting a bare
column in a GROUP BY, or reporting a different rowcount for a statement that
wrote nothing. Both of those were found this way.

So the entire suite can be pointed at a live database:

    SPENDIE_TEST_DATABASE_URL=postgresql://... python -m pytest

Every test then runs against Postgres instead of SQLite, with the schema
dropped and recreated between tests so they stay isolated. Without that
variable nothing changes and the suite runs on SQLite as usual, so this costs
contributors nothing.
"""

import os

import pytest

PG_URL = os.environ.get("SPENDIE_TEST_DATABASE_URL")


@pytest.fixture(autouse=True)
def _database(monkeypatch):
    if not PG_URL:
        yield
        return

    import psycopg

    # DATABASE_URL is what `finance.db` looks for, so setting it here redirects
    # every Store the tests build — including the ones inside create_app.
    monkeypatch.setenv("DATABASE_URL", PG_URL)
    from finance import db
    db.close_cached()                   # a kept connection into the dropped schema
    try:
        from finance import memo
        memo.forget_across()            # and what was remembered about it
    except ImportError:                 # pragma: no cover - older trees
        pass
    with psycopg.connect(PG_URL) as c:
        # Every account's schema too (2026-11-20): a test's second account
        # used to find the rows an earlier test's second account left.
        others = [r[0] for r in c.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'u\\_%'").fetchall()]
        for name in others:
            c.execute(f'DROP SCHEMA "{name}" CASCADE')
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        c.commit()
    yield
    db.close_cached()


@pytest.fixture(autouse=True)
def _no_pwned_lookups(monkeypatch):
    """Tests never ask Have I Been Pwned (finance/passwords.py): the short
    list of common passwords is checked, the network isn't."""
    monkeypatch.setenv("PEARL_PWNED_CHECK", "0")
