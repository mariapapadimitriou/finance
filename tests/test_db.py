"""The SQLite → Postgres translation.

A mistranslation here corrupts data rather than raising, so each rule is
pinned individually as well as being exercised end to end by running the whole
suite against a live server (see conftest).
"""

import pytest

from finance.db import database_url, to_postgres


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


class TestDatabaseUrl:
    def test_no_url_configured_means_sqlite(self, monkeypatch):
        for k in ("DATABASE_URL_POOLED", "POSTGRES_PRISMA_URL", "POSTGRES_URL",
                  "DATABASE_URL"):
            monkeypatch.delenv(k, raising=False)
        assert database_url() is None

    def test_a_pooled_url_wins(self, monkeypatch):
        """A serverless function opens a connection per request, so the pooled
        endpoint is the one that survives traffic."""
        monkeypatch.setenv("DATABASE_URL", "postgres://direct/db")
        monkeypatch.setenv("DATABASE_URL_POOLED", "postgres://pooled/db")
        assert database_url() == "postgres://pooled/db"

    @pytest.mark.parametrize("value", ["", "file:///tmp/x", "mysql://h/db"])
    def test_anything_that_is_not_postgres_is_ignored(self, monkeypatch, value):
        for k in ("DATABASE_URL_POOLED", "POSTGRES_PRISMA_URL", "POSTGRES_URL"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("DATABASE_URL", value)
        assert database_url() is None
