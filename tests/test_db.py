"""The SQLite → Postgres translation.

A mistranslation here corrupts data rather than raising, so each rule is
pinned individually as well as being exercised end to end by running the whole
suite against a live server (see conftest).
"""

import pytest

from finance.db import URL_KEYS, database_url, to_postgres


class TestPlaceholders:
    def test_question_marks_become_percent_s(self):
        assert to_postgres("SELECT * FROM t WHERE a = ? AND b = ?") == \
            "SELECT * FROM t WHERE a = %s AND b = %s"

    def test_a_query_with_no_placeholders_is_left_alone(self):
        assert to_postgres("SELECT 1") == "SELECT 1"


class TestLike:
    def test_like_becomes_ilike(self):
        """SQLite's LIKE ignores ASCII case and Postgres' does not, so a
        straight copy would quietly stop matching 'blue bottle'."""
        out = to_postgres("SELECT * FROM t WHERE merchant LIKE ?")
        assert "ILIKE %s" in out
        assert "ILIKE" in out and " LIKE " not in out

    def test_the_month_filter_still_works_as_a_prefix_match(self):
        assert to_postgres("date LIKE ?") == "date ILIKE %s"


class TestInsertOrIgnore:
    def test_it_becomes_on_conflict_do_nothing(self):
        out = to_postgres("INSERT OR IGNORE INTO t (a) VALUES (?)")
        assert out == "INSERT INTO t (a) VALUES (%s) ON CONFLICT DO NOTHING"

    def test_a_trailing_semicolon_does_not_strand_the_clause(self):
        out = to_postgres("INSERT OR IGNORE INTO t (a) VALUES (?);")
        assert out.endswith("ON CONFLICT DO NOTHING")

    def test_a_plain_insert_gains_no_conflict_clause(self):
        """An upsert that already states its own conflict target must not have
        a second one appended."""
        sql = ("INSERT INTO budgets (category, monthly) VALUES (?,?) "
               "ON CONFLICT(category) DO UPDATE SET monthly = excluded.monthly")
        out = to_postgres(sql)
        assert out.count("ON CONFLICT") == 1
        assert "DO UPDATE" in out


class TestSchemaTypes:
    def test_autoincrement_becomes_serial(self):
        out = to_postgres("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT)")
        assert out == "CREATE TABLE t (id SERIAL PRIMARY KEY)"

    def test_real_becomes_double_precision(self):
        """Postgres REAL is a 4-byte float, which cannot hold a cent-accurate
        five-figure amount."""
        assert "DOUBLE PRECISION" in to_postgres("CREATE TABLE t (amount REAL NOT NULL)")

    def test_a_text_timestamp_default_is_cast(self):
        out = to_postgres("CREATE TABLE t (created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        assert "now()::text" in out


def _clear(monkeypatch):
    for k in list(URL_KEYS) + ["POSTGRES_PRISMA_URL"]:
        monkeypatch.delenv(k, raising=False)


class TestDatabaseUrl:
    def test_no_url_configured_means_sqlite(self, monkeypatch):
        _clear(monkeypatch)
        assert database_url() is None

    def test_a_pooled_url_wins(self, monkeypatch):
        """A serverless function opens a connection per request, so the pooled
        endpoint is the one that survives traffic."""
        monkeypatch.setenv("DATABASE_URL_UNPOOLED", "postgres://direct/db")
        monkeypatch.setenv("DATABASE_URL_POOLED", "postgres://pooled/db")
        assert database_url() == "postgres://pooled/db"

    def test_neons_database_url_is_preferred_over_the_direct_one(self, monkeypatch):
        _clear(monkeypatch)
        monkeypatch.setenv("DATABASE_URL", "postgres://pooled/db")
        monkeypatch.setenv("DATABASE_URL_UNPOOLED", "postgres://direct/db")
        assert database_url() == "postgres://pooled/db"

    def test_the_prisma_url_is_never_used(self, monkeypatch):
        """Connecting Neon injects POSTGRES_PRISMA_URL: the same pooled host
        with Prisma's own options glued on. libpq rejects the entire connection
        string on the first option it doesn't recognise, so picking this one
        would fail every request."""
        _clear(monkeypatch)
        monkeypatch.setenv("POSTGRES_PRISMA_URL",
                           "postgres://h/db?pgbouncer=true&connect_timeout=15")
        assert database_url() is None

        monkeypatch.setenv("DATABASE_URL", "postgres://pooled/db?sslmode=require")
        assert database_url() == "postgres://pooled/db?sslmode=require"


class TestDriverOnlyParameters:
    """Options that belong to an ORM, not to libpq."""

    def test_pgbouncer_is_stripped(self, monkeypatch):
        _clear(monkeypatch)
        monkeypatch.setenv("DATABASE_URL",
                           "postgres://h/db?sslmode=require&pgbouncer=true")
        assert database_url() == "postgres://h/db?sslmode=require"

    def test_real_libpq_options_survive(self, monkeypatch):
        """sslmode and channel_binding are Neon's, and required to connect."""
        _clear(monkeypatch)
        url = "postgres://u:p@h/db?sslmode=require&channel_binding=require"
        monkeypatch.setenv("DATABASE_URL", url)
        assert database_url() == url

    def test_a_url_with_no_query_is_untouched(self, monkeypatch):
        _clear(monkeypatch)
        monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h/db")
        assert database_url() == "postgres://u:p@h/db"

    @pytest.mark.parametrize("value", ["", "file:///tmp/x", "mysql://h/db"])
    def test_anything_that_is_not_postgres_is_ignored(self, monkeypatch, value):
        _clear(monkeypatch)
        monkeypatch.setenv("DATABASE_URL", value)
        assert database_url() is None


class TestEachAccountIsItsOwnSchema:
    """On a pooled Postgres the search path must be per transaction, or one
    person's query could land in another person's tables."""

    class _Raw:
        def __init__(self):
            self.log = []

        def cursor(self):
            raw = self

            class _Cur:
                rowcount = 0

                def execute(self, sql, params=()):
                    raw.log.append(sql)

                def executemany(self, sql, rows):
                    raw.log.append(sql)
            return _Cur()

        def commit(self):
            self.log.append("COMMIT")

    def test_set_local_opens_every_transaction(self):
        from finance.db import _PgConnection
        raw = self._Raw()
        conn = _PgConnection(raw, "u_7")
        conn.execute("SELECT 1")
        conn.execute("SELECT 2")
        conn.commit()
        conn.execute("SELECT 3")
        assert raw.log == ['SET LOCAL search_path TO "u_7"', "SELECT 1", "SELECT 2",
                           "COMMIT",
                           'SET LOCAL search_path TO "u_7"', "SELECT 3"]

    def test_creating_the_schema_waits_its_turn(self):
        """Two cold starts at once raced to create the same table and one
        failed on its type name (seen in production); the lock serialises them."""
        from finance.db import SCHEMA_LOCK, _PgConnection
        raw = self._Raw()
        _PgConnection(raw, "u_7").executescript("CREATE TABLE IF NOT EXISTS x (a TEXT);")
        assert raw.log[:2] == ['SET LOCAL search_path TO "u_7"',
                               f"SELECT pg_advisory_xact_lock({SCHEMA_LOCK})"]
        assert raw.log[2].startswith("CREATE TABLE IF NOT EXISTS x")

    def test_the_owner_is_pinned_to_public_too(self):
        from finance.db import _PgConnection
        raw = self._Raw()
        _PgConnection(raw).execute("SELECT 1")
        assert raw.log[0] == 'SET LOCAL search_path TO "public"'

    def test_only_ledger_schema_names_reach_sql(self):
        from finance.db import valid_schema
        for good in ("public", "u_1", "u_42"):
            assert valid_schema(good) == good
        for bad in ("", "u_", "u_1; DROP TABLE x", 'u_1"', "pg_catalog", "U_1"):
            with pytest.raises(ValueError):
                valid_schema(bad)


class TestOneConnectionPerThread:
    """A kept Postgres connection (2026-10-16): the store's many short
    transactions share one connection instead of a handshake each."""

    @pytest.fixture
    def pg(self, monkeypatch):
        import sys, types
        from finance import db

        class Cursor:
            def __init__(self, raw):
                self.raw = raw
            def execute(self, sql, params=()):
                if self.raw.closed:
                    raise RuntimeError("closed")
                if self.raw.fail_next:
                    self.raw.fail_next = False
                    self.raw.broken = True
                    raise RuntimeError("gone")
                self.raw.sql.append(sql)
                return self
            def executemany(self, sql, rows):
                self.raw.sql.append(sql)
                return self
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        class Raw:
            def __init__(self):
                self.closed = False
                self.broken = False
                self.fail_next = False
                self.sql, self.commits, self.rollbacks = [], 0, 0
            def cursor(self):
                return Cursor(self)
            def commit(self):
                self.commits += 1
            def rollback(self):
                self.rollbacks += 1
            def close(self):
                self.closed = True

        made = []
        fake = types.ModuleType("psycopg")
        fake.connect = lambda url, row_factory=None: made.append(Raw()) or made[-1]
        rows = types.ModuleType("psycopg.rows")
        rows.dict_row = object()
        monkeypatch.setitem(sys.modules, "psycopg", fake)
        monkeypatch.setitem(sys.modules, "psycopg.rows", rows)
        db.close_cached()
        yield db, made
        db.close_cached()

    def test_sequential_transactions_share_one_connection(self, pg):
        db, made = pg
        for _ in range(3):
            with db.connect("", "postgres://x", "public") as c:
                c.execute("SELECT 1")
        assert len(made) == 1
        raw = made[0]
        assert raw.commits == 3 and not raw.closed
        # Each transaction sets the search path afresh.
        assert sum(1 for s in raw.sql if s.startswith("SET LOCAL search_path")) == 3

    def test_a_nested_with_joins_the_outer_transaction(self, pg):
        db, made = pg
        with db.connect("", "postgres://x", "public") as outer:
            outer.execute("SELECT 1")
            with db.connect("", "postgres://x", "public") as inner:
                assert inner is outer
                inner.execute("SELECT 2")
            assert made[0].commits == 0
        assert made[0].commits == 1 and len(made) == 1

    def test_an_exception_rolls_back_and_keeps_the_connection(self, pg):
        db, made = pg
        with pytest.raises(ValueError):
            with db.connect("", "postgres://x", "public") as c:
                c.execute("SELECT 1")
                raise ValueError("nope")
        assert made[0].rollbacks == 1 and made[0].commits == 0 and not made[0].closed
        with db.connect("", "postgres://x", "public") as c:
            c.execute("SELECT 1")
        assert len(made) == 1 and made[0].commits == 1

    def test_a_broken_connection_is_replaced(self, pg):
        db, made = pg
        with db.connect("", "postgres://x", "public") as c:
            c.execute("SELECT 1")
        made[0].fail_next = True
        with pytest.raises(RuntimeError):
            with db.connect("", "postgres://x", "public") as c:
                c.execute("SELECT 1")
        assert made[0].closed
        with db.connect("", "postgres://x", "public") as c:
            c.execute("SELECT 1")
        assert len(made) == 2 and made[1].commits == 1

    def test_an_idle_connection_is_pinged_first(self, pg, monkeypatch):
        db, made = pg
        with db.connect("", "postgres://x", "public") as c:
            c.execute("SELECT 1")
        raw, url, last = db._local.pg
        db._local.pg = (raw, url, last - db.IDLE_PING_AFTER - 1)
        with db.connect("", "postgres://x", "public") as c:
            c.execute("SELECT 2")
        assert len(made) == 1 and "SELECT 1" in made[0].sql[-3:]      # the ping, then the work
        # A ping that fails means a new connection.
        raw, url, last = db._local.pg
        db._local.pg = (raw, url, last - db.IDLE_PING_AFTER - 1)
        raw.fail_next = True
        with db.connect("", "postgres://x", "public") as c:
            c.execute("SELECT 3")
        assert len(made) == 2

    def test_another_schema_inside_a_transaction_gets_its_own_connection(self, pg):
        db, made = pg
        with db.connect("", "postgres://x", "u_1") as outer:
            outer.execute("SELECT 1")
            with db.connect("", "postgres://x", "u_2") as other:
                assert other is not outer
                other.execute("SELECT 2")
            assert made[1].closed and made[1].commits == 1
        assert made[0].commits == 1 and not made[0].closed
