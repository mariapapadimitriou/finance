"""Ledger persistence.

Locally everything lives in one SQLite file (default `ledger.db` beside the
code, or wherever `LEDGER_DB` points) and your transaction history never leaves
the machine unless you explicitly ask for the optional Claude narrative.

Set `DATABASE_URL` to a Postgres instance and the same store runs against that
instead — which is what a serverless deployment needs, since its disk is
discarded when the function instance is recycled. Every query below is written
once, in SQLite's dialect; `db.py` translates the few constructs Postgres
spells differently.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager

from datetime import datetime, timezone

from . import db
from .models import Transaction


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

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

CREATE TABLE IF NOT EXISTS trips (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date   TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_trip_dates ON trips(start_date, end_date);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS buckets (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL UNIQUE,
    balance REAL NOT NULL DEFAULT 0
);

-- Money drawn from a bucket to cover a day's overspend. Kept per month so the
-- spend plan can add it back to that month's budget and nowhere else.
CREATE TABLE IF NOT EXISTS bucket_draws (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket_id INTEGER NOT NULL,
    month     TEXT NOT NULL,
    amount    REAL NOT NULL,
    note      TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_draw_month ON bucket_draws(month);

-- One row per bank connection made through Plaid Link.
--
-- `access_token` is stored encrypted (see finance/secrets_box.py) because it
-- is a live credential, not a record of something that already happened.
-- `cursor` is Plaid's position in the change feed for this item: /transactions
-- /sync returns everything added, modified or removed since it, so the cursor
-- is what makes a sync incremental rather than a re-download.
CREATE TABLE IF NOT EXISTS plaid_items (
    item_id      TEXT PRIMARY KEY,
    access_token TEXT NOT NULL,
    institution  TEXT,
    cursor       TEXT,
    last_synced  TEXT,
    last_error   TEXT,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dismissed_insights (
    insight_id TEXT PRIMARY KEY,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- The fixed monthly commitments the plan subtracts from income.
--
-- Declared rather than detected. The recurring-charge detector finds a lot
-- of these on its own, but a commitment you have decided on is not the same
-- as a pattern noticed in the data: rent paid from a chequing account this
-- app never sees is still a commitment, and a gym membership detected
-- correctly is still yours to call fixed or not.
CREATE TABLE IF NOT EXISTS fixed_costs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL,
    amount   REAL NOT NULL,
    category TEXT DEFAULT 'Other',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Whether each account a bank handed over should be synced.
--
-- A bank's consent screen is all-or-nothing at some institutions: you grant
-- the whole login or nothing, and every chequing, savings and investment
-- account arrives with the card you actually wanted. Removing those accounts
-- is not enough on its own, because the next sync fetches them again.
--
-- So the decision is recorded per account and outlives the rows. `decided_by`
-- separates a default this app chose ('auto' — keep cards, skip the rest)
-- from one the person made ('user'), which matters because only the first may
-- be revised: re-deriving a default is housekeeping, overruling a choice is a
-- bug. The account_id is Plaid's own, which is also the ledger's id for the
-- rows, so one key serves both.
CREATE TABLE IF NOT EXISTS account_sync (
    account_id   TEXT PRIMARY KEY,
    account_name TEXT,
    item_id      TEXT,
    enabled      INTEGER NOT NULL DEFAULT 1,
    decided_by   TEXT NOT NULL DEFAULT 'auto',
    account_type TEXT,
    account_subtype TEXT,
    updated_at   TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class Store:
    def __init__(self, path: str = DEFAULT_DB, url: str | None = None):
        self.path = path
        # Resolved once, at construction, so a Store keeps talking to the
        # database it was opened against even if the environment changes.
        self.url = url if url is not None else db.database_url()
        self._init()

    @contextmanager
    def conn(self):
        with db.connect(self.path, self.url) as c:
            yield c

    @property
    def is_postgres(self) -> bool:
        return bool(self.url)

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

    def delete_transaction(self, txn_id: str) -> bool:
        with self.conn() as c:
            cur = c.execute("DELETE FROM transactions WHERE id = ?", (txn_id,))
            return cur.rowcount > 0

    def accounts(self) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                # account_name and currency are aggregated rather than
                # grouped on: SQLite would happily return a bare column here and
                # pick a row at random, but Postgres rejects it outright, and
                # adding them to GROUP BY would split one card into several rows
                # if a name were ever re-exported differently. One row per card
                # is what this is for.
                """SELECT account_id,
                          MAX(account_name) AS account_name,
                          MAX(currency)     AS currency,
                          MAX(source)       AS source,
                          COUNT(*) AS transactions,
                          MIN(date) AS first_date, MAX(date) AS last_date,
                          -- "Spend" has to mean the same thing here as it
                          -- does everywhere else, or the Accounts table and
                          -- the Overview disagree about the same card. A
                          -- card payment and a loyalty credit are positive
                          -- on some statements and are not spending.
                          SUM(CASE WHEN amount > 0
                                    AND category NOT IN ('Income', 'Transfers')
                                   THEN amount ELSE 0 END) AS total_spend,
                          SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END)
                              AS total_inflows
                   FROM transactions
                   GROUP BY account_id
                   ORDER BY total_spend DESC"""
            ).fetchall()
        return [dict(r) for r in rows]

    def account_kinds(self) -> dict[str, dict]:
        """The Plaid account type behind each account, where one is known.

        Read off the rows because that is where it was recorded — Plaid gives
        the type alongside a sync's transactions, not with them, so once the
        sync is over the ledger is the only copy.
        """
        out: dict[str, dict] = {}
        with self.conn() as c:
            rows = c.execute(
                "SELECT account_id, raw FROM transactions "
                "WHERE source = 'plaid' AND raw IS NOT NULL"
            ).fetchall()
        for row in rows:
            if row["account_id"] in out:
                continue
            try:
                raw = json.loads(row["raw"] or "{}")
            except (ValueError, TypeError):
                continue
            kind = raw.get("account_type")
            if kind:
                out[row["account_id"]] = {
                    "type": kind, "subtype": raw.get("account_subtype", "")}
        return out

    def clear_transactions(self, account_id: str | None = None) -> int:
        # Import history goes with the transactions it describes; left behind,
        # it lists files whose data no longer exists.
        with self.conn() as c:
            if account_id:
                cur = c.execute("DELETE FROM transactions WHERE account_id = ?", (account_id,))
                c.execute("DELETE FROM imports WHERE account_id = ?", (account_id,))
            else:
                cur = c.execute("DELETE FROM transactions")
                c.execute("DELETE FROM imports")
            return cur.rowcount

    # ── Starting over ────────────────────────────────────────────────────────
    # ── Which accounts to sync ───────────────────────────────────────────

    def account_sync_rules(self) -> dict[str, dict]:
        """Every account this app has seen from a bank, keyed by account id."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT account_id, account_name, item_id, enabled, decided_by,"
                "       account_type, account_subtype"
                "  FROM account_sync ORDER BY account_name"
            ).fetchall()
        return {r["account_id"]: {
            "account_id": r["account_id"],
            "account_name": r["account_name"] or r["account_id"],
            "item_id": r["item_id"] or "",
            "enabled": bool(r["enabled"]),
            "decided_by": r["decided_by"],
            "account_type": r["account_type"] or "",
            "account_subtype": r["account_subtype"] or "",
        } for r in rows}

    def note_account(self, account_id: str, *, name: str = "", item_id: str = "",
                     enabled: bool = True, account_type: str = "",
                     subtype: str = "") -> None:
        """Record the default for an account not decided on before.

        Does nothing to an account already present, whoever decided it: a
        default must never overwrite a choice, and re-deriving one that has not
        changed would only churn the timestamp.
        """
        with self.conn() as c:
            existing = c.execute(
                "SELECT account_id FROM account_sync WHERE account_id = ?",
                (account_id,)).fetchone()
            if existing:
                # Names and types still improve as Plaid resolves them.
                c.execute(
                    "UPDATE account_sync"
                    "   SET account_name = COALESCE(NULLIF(?, ''), account_name),"
                    "       item_id = COALESCE(NULLIF(?, ''), item_id),"
                    "       account_type = COALESCE(NULLIF(?, ''), account_type),"
                    "       account_subtype = COALESCE(NULLIF(?, ''), account_subtype)"
                    " WHERE account_id = ?",
                    (name, item_id, account_type, subtype, account_id))
                return
            c.execute(
                "INSERT INTO account_sync (account_id, account_name, item_id,"
                "                          enabled, decided_by, account_type,"
                "                          account_subtype)"
                " VALUES (?, ?, ?, ?, 'auto', ?, ?)",
                (account_id, name, item_id, 1 if enabled else 0,
                 account_type, subtype))

    def set_account_sync(self, account_id: str, enabled: bool, *,
                         name: str = "", item_id: str = "") -> None:
        """Record a decision the person made, which no default may revise."""
        with self.conn() as c:
            cur = c.execute(
                "UPDATE account_sync"
                "   SET enabled = ?, decided_by = 'user',"
                "       updated_at = CURRENT_TIMESTAMP"
                " WHERE account_id = ?",
                (1 if enabled else 0, account_id))
            if not cur.rowcount or cur.rowcount <= 0:
                c.execute(
                    "INSERT INTO account_sync (account_id, account_name,"
                    "                          item_id, enabled, decided_by)"
                    " VALUES (?, ?, ?, ?, 'user')",
                    (account_id, name, item_id, 1 if enabled else 0))

    def accounts_not_synced(self) -> set[str]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT account_id FROM account_sync WHERE enabled = 0").fetchall()
        return {r["account_id"] for r in rows}

    def forget_account_rules(self, item_id: str) -> int:
        """Drop the rules for one bank, for when the bank itself is removed."""
        with self.conn() as c:
            cur = c.execute("DELETE FROM account_sync WHERE item_id = ?", (item_id,))
            return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

    def reset(self, keep_banks: bool = True) -> dict:
        """Empty the ledger and everything derived from it.

        Deliberately explicit about what it touches rather than dropping the
        schema: a reset that quietly took your password with it, or left a
        stale Plaid cursor pointing past transactions that no longer exist,
        would be worse than no reset at all.

        `keep_banks` keeps the connections but rewinds their cursors, so the
        next sync re-fetches the full history into the empty ledger instead of
        resuming from where it left off and importing nothing.
        """
        removed = {}
        tables = [
            ("transactions", "transactions"),
            ("imports", "import history"),
            ("merchant_overrides", "merchant overrides"),
            ("budgets", "budgets"),
            ("trips", "trips"),
            ("bucket_draws", "bucket draws"),
            ("buckets", "buckets"),
            ("dismissed_insights", "dismissed findings"),
        ]
        with self.conn() as c:
            for table, label in tables:
                cur = c.execute(f"DELETE FROM {table}")
                removed[label] = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

            if keep_banks:
                # The cursor is Plaid's position in the change feed. Left
                # alone against an empty ledger, the next sync would report
                # "nothing new" and the cards would stay empty forever.
                c.execute("UPDATE plaid_items SET cursor = NULL, "
                          "last_synced = NULL, last_error = NULL")
            else:
                cur = c.execute("DELETE FROM plaid_items")
                removed["bank connections"] = max(cur.rowcount, 0)
                # The account decisions belong to those connections. Keeping
                # them would leave a relink inheriting choices about accounts
                # nobody can see any more.
                c.execute("DELETE FROM account_sync")

            # Settings hold the spending plan and take-home pay, which are
            # yours rather than imported. The seed flag is the exception: it
            # records that this emptiness was deliberate.
            c.execute("DELETE FROM settings WHERE key IN "
                      "('monthly_amount', 'monthly_income')")
            c.execute(
                """INSERT INTO settings (key, value) VALUES ('seeded', 'done')
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""")
        return removed

    def seed_suppressed(self) -> bool:
        """Whether an empty ledger is empty on purpose.

        Without this the committed ledger would reload on the next cold start
        and undo the reset — the seeder only checks whether the store is
        empty, and after a reset it very much is.
        """
        return self.setting("seeded", "") == "done"

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

    # ── Settings ─────────────────────────────────────────────────────────────
    # ── Fixed monthly commitments ────────────────────────────────────────

    def fixed_costs(self) -> list:
        from .money_plan import FixedCost
        with self.conn() as c:
            rows = c.execute(
                "SELECT id, name, amount, category FROM fixed_costs"
                " ORDER BY amount DESC").fetchall()
        return [FixedCost(id=r["id"], name=r["name"], amount=float(r["amount"]),
                          category=r["category"] or "Other") for r in rows]

    def add_fixed_cost(self, name: str, amount: float,
                       category: str = "Other") -> int:
        sql = "INSERT INTO fixed_costs (name, amount, category) VALUES (?, ?, ?)"
        args = (name.strip(), float(amount), category)
        with self.conn() as c:
            # Postgres has no lastrowid; see add_trip for the same split.
            if self.is_postgres:
                return c.execute(sql + " RETURNING id", args).fetchone()["id"]
            return c.execute(sql, args).lastrowid

    def update_fixed_cost(self, cost_id: int, name: str, amount: float,
                          category: str = "Other") -> bool:
        with self.conn() as c:
            cur = c.execute(
                "UPDATE fixed_costs SET name = ?, amount = ?, category = ?"
                " WHERE id = ?", (name, float(amount), category, cost_id))
            return bool(cur.rowcount and cur.rowcount > 0)

    def delete_fixed_cost(self, cost_id: int) -> bool:
        with self.conn() as c:
            cur = c.execute("DELETE FROM fixed_costs WHERE id = ?", (cost_id,))
            return bool(cur.rowcount and cur.rowcount > 0)

    # ── Where the ledger starts ──────────────────────────────────────────

    def ledger_start(self) -> str:
        """The earliest date that counts, or "" for no limit."""
        return (self.setting("ledger_start", "") or "").strip()

    def set_ledger_start(self, iso_date: str) -> None:
        self.set_setting("ledger_start", (iso_date or "").strip())

    def delete_before(self, iso_date: str) -> int:
        """Remove every transaction earlier than a date."""
        if not iso_date:
            return 0
        with self.conn() as c:
            cur = c.execute("DELETE FROM transactions WHERE date < ?", (iso_date,))
            return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

    def setting(self, key: str, default=None):
        with self.conn() as c:
            row = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value) -> None:
        with self.conn() as c:
            c.execute(
                """INSERT INTO settings (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (key, str(value)),
            )

    def float_setting(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self.setting(key, default))
        except (TypeError, ValueError):
            return default

    # ── Buckets ──────────────────────────────────────────────────────────────
    def buckets(self) -> list:
        from .spend_plan import Bucket
        with self.conn() as c:
            rows = c.execute("SELECT id, name, balance FROM buckets ORDER BY name").fetchall()
        return [Bucket(id=r["id"], name=r["name"], balance=r["balance"]) for r in rows]

    def set_bucket(self, name: str, balance: float) -> int:
        with self.conn() as c:
            c.execute(
                """INSERT INTO buckets (name, balance) VALUES (?, ?)
                   ON CONFLICT(name) DO UPDATE SET balance = excluded.balance""",
                (name.strip(), float(balance)),
            )
            row = c.execute("SELECT id FROM buckets WHERE name = ?", (name.strip(),)).fetchone()
            return row["id"]

    def delete_bucket(self, bucket_id: int) -> bool:
        with self.conn() as c:
            c.execute("DELETE FROM bucket_draws WHERE bucket_id = ?", (bucket_id,))
            cur = c.execute("DELETE FROM buckets WHERE id = ?", (bucket_id,))
            return cur.rowcount > 0

    def draw_from_bucket(self, bucket_id: int, month: str, amount: float,
                         note: str = "") -> bool:
        """Take money from a bucket to cover a month's overspend."""
        with self.conn() as c:
            row = c.execute("SELECT balance FROM buckets WHERE id = ?",
                            (bucket_id,)).fetchone()
            if row is None or row["balance"] < amount:
                return False
            c.execute("UPDATE buckets SET balance = balance - ? WHERE id = ?",
                      (amount, bucket_id))
            c.execute(
                "INSERT INTO bucket_draws (bucket_id, month, amount, note) VALUES (?,?,?,?)",
                (bucket_id, month, float(amount), note),
            )
            return True

    def covered_in(self, month: str) -> float:
        with self.conn() as c:
            row = c.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM bucket_draws WHERE month = ?",
                (month,),
            ).fetchone()
        return round(row["total"], 2)

    def draws(self, month: str | None = None) -> list[dict]:
        sql = ("SELECT d.id, d.month, d.amount, d.note, d.created_at, b.name "
               "FROM bucket_draws d JOIN buckets b ON b.id = d.bucket_id")
        params = []
        if month:
            sql += " WHERE d.month = ?"
            params.append(month)
        sql += " ORDER BY d.id DESC"
        with self.conn() as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    # ── Trips ────────────────────────────────────────────────────────────────
    def trips(self) -> list:
        from .trips import Trip
        with self.conn() as c:
            rows = c.execute(
                "SELECT id, name, start_date, end_date FROM trips "
                "ORDER BY start_date DESC"
            ).fetchall()
        return [Trip(id=r["id"], name=r["name"], start_date=r["start_date"],
                     end_date=r["end_date"]) for r in rows]

    def add_trip(self, name: str, start_date: str, end_date: str) -> int:
        with self.conn() as c:
            # The only query in the store that needs the new row's id back, and
            # the only one that can't be written once for both databases:
            # Postgres has no lastrowid. RETURNING would work on both, but only
            # on SQLite 3.35 and newer, and this stays a local-first app.
            if self.is_postgres:
                cur = c.execute(
                    "INSERT INTO trips (name, start_date, end_date) "
                    "VALUES (?,?,?) RETURNING id",
                    (name.strip(), start_date, end_date),
                )
                return cur.fetchone()["id"]
            cur = c.execute(
                "INSERT INTO trips (name, start_date, end_date) VALUES (?,?,?)",
                (name.strip(), start_date, end_date),
            )
            return cur.lastrowid

    def update_trip(self, trip_id: int, name: str, start_date: str,
                    end_date: str) -> bool:
        with self.conn() as c:
            cur = c.execute(
                "UPDATE trips SET name = ?, start_date = ?, end_date = ? WHERE id = ?",
                (name.strip(), start_date, end_date, trip_id),
            )
            return cur.rowcount > 0

    def delete_trip(self, trip_id: int) -> bool:
        with self.conn() as c:
            cur = c.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
            return cur.rowcount > 0

    # ── Dismissed insights ───────────────────────────────────────────────────
    # ── Plaid items ──────────────────────────────────────────────────────────
    # The access token is encrypted on the way in and decrypted on the way out,
    # so it exists in plaintext only inside a request that is about to use it.

    def plaid_items(self) -> list[dict]:
        """Linked institutions, without their tokens.

        Everything the UI needs to show a connection and nothing that could
        authenticate as one, so this is safe to serialise straight to JSON.
        """
        with self.conn() as c:
            rows = c.execute(
                """SELECT item_id, institution, cursor, last_synced, last_error,
                          created_at
                   FROM plaid_items ORDER BY created_at"""
            ).fetchall()
        return [{**dict(r), "synced_before": bool(r["cursor"])} for r in rows]

    def plaid_token(self, item_id: str) -> str | None:
        from . import secrets_box
        with self.conn() as c:
            row = c.execute(
                "SELECT access_token FROM plaid_items WHERE item_id = ?", (item_id,)
            ).fetchone()
        return secrets_box.decrypt(row["access_token"]) if row else None

    def add_plaid_item(self, item_id: str, access_token: str,
                       institution: str = "") -> None:
        from . import secrets_box
        token = secrets_box.encrypt(access_token)
        with self.conn() as c:
            c.execute(
                """INSERT INTO plaid_items (item_id, access_token, institution)
                   VALUES (?,?,?)
                   ON CONFLICT(item_id) DO UPDATE SET
                       access_token = excluded.access_token,
                       institution  = excluded.institution""",
                (item_id, token, institution),
            )

    def set_plaid_cursor(self, item_id: str, cursor: str) -> None:
        with self.conn() as c:
            c.execute(
                """UPDATE plaid_items
                   SET cursor = ?, last_synced = ?, last_error = NULL
                   WHERE item_id = ?""",
                (cursor, _now(), item_id),
            )

    def set_plaid_error(self, item_id: str, message: str) -> None:
        with self.conn() as c:
            c.execute("UPDATE plaid_items SET last_error = ? WHERE item_id = ?",
                      (message[:500], item_id))

    def delete_plaid_item(self, item_id: str) -> bool:
        with self.conn() as c:
            cur = c.execute("DELETE FROM plaid_items WHERE item_id = ?", (item_id,))
            return cur.rowcount > 0

    def delete_transactions_from(self, plaid_ids: list[str]) -> int:
        """Remove rows Plaid has told us no longer exist.

        A pending charge that posts comes back as a removal plus an addition,
        so without this the ledger would keep the pending copy forever and
        count the purchase twice.
        """
        if not plaid_ids:
            return 0
        removed = 0
        with self.conn() as c:
            for pid in plaid_ids:
                cur = c.execute(
                    "DELETE FROM transactions WHERE raw LIKE ?",
                    (f'%"plaid_id": "{pid}"%',),
                )
                removed += cur.rowcount
        return removed

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
