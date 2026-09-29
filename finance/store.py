"""SQLite persistence.

Everything lives in one local file (default `ledger.db` beside the code, or
wherever `LEDGER_DB` points). Your transaction history never leaves the machine
unless you explicitly ask for the optional Claude narrative.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager

from .models import Transaction

DEFAULT_DB = os.environ.get(
    "LEDGER_DB", os.path.join(os.path.dirname(os.path.dirname(__file__)), "ledger.db")
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id              TEXT PRIMARY KEY,
    date            TEXT NOT NULL,
    post_date       TEXT,
    description     TEXT NOT NULL,
    merchant        TEXT NOT NULL,
    amount          REAL NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'USD',
    account_id      TEXT NOT NULL,
    account_name    TEXT,
    category        TEXT,
    category_source TEXT,
    source          TEXT,
    seq             INTEGER DEFAULT 0,
    raw             TEXT
);
CREATE INDEX IF NOT EXISTS idx_txn_date     ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_txn_merchant ON transactions(merchant);
CREATE INDEX IF NOT EXISTS idx_txn_category ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_txn_account  ON transactions(account_id);

CREATE TABLE IF NOT EXISTS merchant_overrides (
    merchant_key TEXT PRIMARY KEY,
    category     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budgets (
    category TEXT PRIMARY KEY,
    monthly  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS imports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    filename     TEXT,
    format_key   TEXT,
    format_label TEXT,
    account_id   TEXT,
    account_name TEXT,
    imported     INTEGER,
    duplicates   INTEGER,
    skipped      INTEGER,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dismissed_insights (
    insight_id TEXT PRIMARY KEY,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class Store:
    def __init__(self, path: str = DEFAULT_DB):
        self.path = path
        self._init()

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def _init(self) -> None:
        with self.conn() as c:
            c.executescript(SCHEMA)

    # ── Transactions ─────────────────────────────────────────────────────────
    def add_transactions(self, transactions: list[Transaction]) -> int:
        rows = []
        for t in transactions:
            rows.append((
                t.fingerprint, t.date, t.post_date, t.description, t.merchant,
                t.amount, t.currency, t.account_id, t.account_name, t.category,
                t.category_source, t.source, t.seq,
                json.dumps(t.raw or {}),
            ))
        with self.conn() as c:
            cur = c.executemany(
                """INSERT OR IGNORE INTO transactions
                   (id, date, post_date, description, merchant, amount, currency,
                    account_id, account_name, category, category_source, source, seq, raw)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                rows,
            )
            return cur.rowcount

    def all_transactions(self) -> list[Transaction]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM transactions ORDER BY date DESC, id").fetchall()
        return [Transaction.from_row(dict(r)) for r in rows]

    def query_transactions(self, month: str | None = None, category: str | None = None,
                           account_id: str | None = None, search: str | None = None,
                           start: str | None = None, end: str | None = None,
                           limit: int = 200, offset: int = 0
                           ) -> tuple[list[Transaction], int]:
        where, params = [], []
        if month:
            where.append("date LIKE ?")
            params.append(f"{month}%")
        if start:
            where.append("date >= ?")
            params.append(start)
        if end:
            where.append("date <= ?")
            params.append(end)
        if category:
            where.append("category = ?")
            params.append(category)
        if account_id:
            where.append("account_id = ?")
            params.append(account_id)
        if search:
            where.append("(merchant LIKE ? OR description LIKE ?)")
            params += [f"%{search}%", f"%{search}%"]

        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self.conn() as c:
            total = c.execute(
                f"SELECT COUNT(*) AS n FROM transactions {clause}", params
            ).fetchone()["n"]
            rows = c.execute(
                f"""SELECT * FROM transactions {clause}
                    ORDER BY date DESC, id LIMIT ? OFFSET ?""",
                params + [limit, offset],
            ).fetchall()
        return [Transaction.from_row(dict(r)) for r in rows], total

    def set_transaction_category(self, txn_id: str, category: str) -> bool:
        with self.conn() as c:
            cur = c.execute(
                "UPDATE transactions SET category = ?, category_source = 'user' WHERE id = ?",
                (category, txn_id),
            )
            return cur.rowcount > 0

    def get_transaction(self, txn_id: str) -> Transaction | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM transactions WHERE id = ?", (txn_id,)).fetchone()
        return Transaction.from_row(dict(row)) if row else None

    def accounts(self) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                """SELECT account_id, account_name, currency,
                          COUNT(*) AS transactions,
                          MIN(date) AS first_date, MAX(date) AS last_date,
                          SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS total_spend
                   FROM transactions
                   GROUP BY account_id
                   ORDER BY total_spend DESC"""
            ).fetchall()
        return [dict(r) for r in rows]

    def clear_transactions(self, account_id: str | None = None) -> int:
        with self.conn() as c:
            if account_id:
                cur = c.execute("DELETE FROM transactions WHERE account_id = ?", (account_id,))
            else:
                cur = c.execute("DELETE FROM transactions")
            return cur.rowcount

    # ── Merchant overrides ───────────────────────────────────────────────────
    def overrides(self) -> dict[str, str]:
        with self.conn() as c:
            rows = c.execute("SELECT merchant_key, category FROM merchant_overrides").fetchall()
        return {r["merchant_key"]: r["category"] for r in rows}

    def set_override(self, merchant: str, category: str) -> int:
        key = merchant.strip().lower()
        with self.conn() as c:
            c.execute(
                """INSERT INTO merchant_overrides (merchant_key, category) VALUES (?, ?)
                   ON CONFLICT(merchant_key) DO UPDATE SET category = excluded.category""",
                (key, category),
            )
            cur = c.execute(
                """UPDATE transactions SET category = ?, category_source = 'merchant_override'
                   WHERE LOWER(merchant) = ?""",
                (category, key),
            )
            return cur.rowcount

    def clear_override(self, merchant: str) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM merchant_overrides WHERE merchant_key = ?",
                      (merchant.strip().lower(),))

    # ── Budgets ──────────────────────────────────────────────────────────────
    def budgets(self) -> dict[str, float]:
        with self.conn() as c:
            rows = c.execute("SELECT category, monthly FROM budgets").fetchall()
        return {r["category"]: r["monthly"] for r in rows}

    def set_budget(self, category: str, monthly: float) -> None:
        with self.conn() as c:
            if monthly is None or monthly <= 0:
                c.execute("DELETE FROM budgets WHERE category = ?", (category,))
            else:
                c.execute(
                    """INSERT INTO budgets (category, monthly) VALUES (?, ?)
                       ON CONFLICT(category) DO UPDATE SET monthly = excluded.monthly""",
                    (category, float(monthly)),
                )

    # ── Import log ───────────────────────────────────────────────────────────
    def log_import(self, filename: str, result, imported: int, duplicates: int) -> None:
        with self.conn() as c:
            c.execute(
                """INSERT INTO imports
                   (filename, format_key, format_label, account_id, account_name,
                    imported, duplicates, skipped)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (filename, result.format_key, result.format_label, result.account_id,
                 result.account_name, imported, duplicates, result.skipped_rows),
            )

    def import_history(self, limit: int = 25) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM imports ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Dismissed insights ───────────────────────────────────────────────────
    def dismissed(self) -> set[str]:
        with self.conn() as c:
            rows = c.execute("SELECT insight_id FROM dismissed_insights").fetchall()
        return {r["insight_id"] for r in rows}

    def dismiss(self, insight_id: str) -> None:
        with self.conn() as c:
            c.execute("INSERT OR IGNORE INTO dismissed_insights (insight_id) VALUES (?)",
                      (insight_id,))

    def undismiss(self, insight_id: str) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM dismissed_insights WHERE insight_id = ?", (insight_id,))
