"""The schema must create on Postgres too (2026-10-15).

Tests run on SQLite, which accepts column names Postgres reserves. A column
called `end` (THL-250's challenges) passed every test here and took the
hosted app down at startup. This reads every column out of SCHEMA and checks
it against Postgres's reserved words, and checks that a SQLite ledger made
with the old challenge columns is migrated.
"""

import re
import sqlite3

from finance import store as store_mod
from finance.db import to_postgres

# Postgres reserved key words (SQL Key Words appendix, "reserved" and
# "reserved (can be function or type)"): never usable as a bare column name.
RESERVED = set("""
all analyse analyze and any array as asc asymmetric authorization binary both case cast check
collate collation column concurrently constraint create cross current_catalog current_date
current_role current_schema current_time current_timestamp current_user default deferrable desc
distinct do else end except false fetch for foreign freeze from full grant group having ilike in
initially inner intersect into is isnull join lateral leading left like limit localtime
localtimestamp natural not notnull null offset on only or order outer overlaps placing primary
references returning right select session_user similar some symmetric system_user table tablesample
then to trailing true union unique user using variadic verbose when where window with
""".split())


def columns(schema: str) -> list[tuple[str, str]]:
    out = []
    for table, body in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", schema, re.S):
        for line in body.splitlines():
            line = line.split("--")[0].strip()
            m = re.match(r'^"?(\w+)"?\s+[A-Z]', line)
            if m and m.group(1).upper() not in ("PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT"):
                out.append((table, m.group(1)))
    return out


def test_every_table_was_read():
    cols = columns(store_mod.SCHEMA)
    tables = {t for t, _ in cols}
    assert "challenges" in tables and "transactions" in tables and len(cols) > 100


def test_no_column_is_a_postgres_reserved_word():
    bad = [f"{t}.{c}" for t, c in columns(store_mod.SCHEMA) if c.lower() in RESERVED]
    assert not bad, f"reserved in Postgres, so the schema won't create there: {bad}"


def test_the_postgres_schema_has_the_new_challenge_columns():
    sql = to_postgres(store_mod.SCHEMA)
    body = sql[sql.index("CREATE TABLE IF NOT EXISTS challenges"):]
    body = body[:body.index(");")]
    assert "starts_on" in body and "ends_on" in body
    assert not re.search(r"^\s*end\s", body, re.M)


def test_an_old_sqlite_ledger_keeps_its_challenges(tmp_path):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE challenges (
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, title TEXT NOT NULL,
        category TEXT, merchant TEXT, target REAL NOT NULL, baseline REAL,
        start TEXT NOT NULL, end TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
        ended_on TEXT, result TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    con.execute("INSERT INTO challenges (kind, title, target, start, end) "
                "VALUES ('coffee', 'Coffee for a month', 115, '2026-10-15', '2026-10-31')")
    con.commit()
    con.close()
    st = store_mod.Store(str(path))
    c = st.challenges()[0]
    assert (c["start"], c["end"], c["title"]) == ("2026-10-15", "2026-10-31", "Coffee for a month")
    cid = st.add_challenge("cook_at_home", "Cook-at-home week", 35, "2026-10-15", "2026-10-21")
    assert st.challenge(cid)["end"] == "2026-10-21"
