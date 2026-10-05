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

-- Categories folded into one budget line. A row says "budget this category as
-- part of that line"; a category with no row is a line of its own. The line
-- may be another category (Lodging under Travel) or a name of your own
-- (Health and Personal Care under "Health & care"). Budgeting only — the
-- transactions keep their own categories everywhere else.
CREATE TABLE IF NOT EXISTS category_groups (
    category TEXT PRIMARY KEY,
    parent   TEXT NOT NULL
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

-- Piggy banks: the costs that do not arrive monthly. See finance/piggy.py.
--
-- `target` and the horizon are what you decide; the monthly contribution and
-- the balance are derived from them and from the calendar, never stored, so
-- they cannot drift from what the Plan has been subtracting.
--
-- `opening` is money already set aside when the bank was made. It reduces
-- what has to be collected rather than adding to the target.
CREATE TABLE IF NOT EXISTS piggy_banks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    target      REAL NOT NULL,
    cadence     TEXT NOT NULL DEFAULT 'annual',
    target_date TEXT,
    start_month TEXT NOT NULL,
    opening     REAL NOT NULL DEFAULT 0,
    note        TEXT,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Spending charged to a bank instead of to the month it fell in.
--
-- A row here is a decision about an existing transaction, like a merchant
-- override, so it is keyed by the transaction and survives a re-import: the
-- id is the fingerprint, which is stable across exports.
--
-- `amount` is how much of the charge the bank actually paid, which is not
-- always the whole of it: a bank holding $400 can only take $400 of a $2,000
-- flight, and the remaining $1,600 stays in the month it was spent. Stored
-- rather than derived, because it is a record of what the bank held at the
-- moment you charged it, and that balance moves afterwards.
CREATE TABLE IF NOT EXISTS piggy_allocations (
    txn_id     TEXT PRIMARY KEY,
    bank_id    INTEGER NOT NULL,
    amount     REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_alloc_bank ON piggy_allocations(bank_id);

-- What each bank pays for: a category belongs to at most one bank. Every
-- charge in it, dated from the month the bank opened, is paid by that bank
-- without anyone having to allocate it — big spending is not habit spending,
-- so it stays out of the weekly number. See `_CHARGES`.
CREATE TABLE IF NOT EXISTS piggy_bank_categories (
    category TEXT PRIMARY KEY,
    bank_id  INTEGER NOT NULL
);

-- Charges in a bank's categories that you chose to pay from the week anyway:
-- "count this one as everyday". Keyed by the transaction, like an allocation.
CREATE TABLE IF NOT EXISTS piggy_optouts (
    txn_id     TEXT PRIMARY KEY,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Money drawn from a bank to cover a month's overspend, as opposed to a
-- specific charge allocated to it. Kept per month so the spend plan can add
-- it back to that month's budget and nowhere else.
CREATE TABLE IF NOT EXISTS piggy_draws (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_id   INTEGER NOT NULL,
    month     TEXT NOT NULL,
    amount    REAL NOT NULL,
    note      TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_draw_month ON piggy_draws(month);

-- The two tables piggy banks replaced. They exist only so the one-time copy
-- in `_migrate_buckets` has something to read on a database that predates
-- them; the copy empties them, so on every database made since they stay
-- empty. Nothing else reads or writes them.
CREATE TABLE IF NOT EXISTS buckets (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL UNIQUE,
    balance REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS bucket_draws (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket_id INTEGER NOT NULL,
    month     TEXT NOT NULL,
    amount    REAL NOT NULL,
    note      TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

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


# Every charge a bank pays, one row per transaction: `bank_id`, how much of it
# the bank paid (`charged`) and whether it got there by itself (`auto`).
#
# Two ways in. An allocation is a decision about one charge and always wins.
# Otherwise a charge whose category a bank owns is that bank's, from the month
# the bank opened, unless it was opted out. That second half is derived on
# every read rather than written, so an import, a sync, a recategorisation or
# a change of what a bank pays for is reflected at once, with no write path
# that could forget to keep it up to date.
_CHARGES = """(
    SELECT t.id AS txn_id,
           COALESCE(m.bank_id, o.bank_id) AS bank_id,
           CASE WHEN m.txn_id IS NOT NULL THEN COALESCE(m.amount, t.amount)
                ELSE t.amount END AS charged,
           CASE WHEN m.txn_id IS NULL THEN 1 ELSE 0 END AS auto
      FROM transactions t
      LEFT JOIN piggy_allocations m ON m.txn_id = t.id
      LEFT JOIN (SELECT bc.category AS category, b.id AS bank_id,
                        b.start_month AS start_month
                   FROM piggy_bank_categories bc
                   JOIN piggy_banks b ON b.id = bc.bank_id) o
             ON o.category = t.category
            AND SUBSTR(t.date, 1, 7) >= o.start_month
            AND NOT EXISTS (SELECT 1 FROM piggy_optouts x WHERE x.txn_id = t.id)
     WHERE m.txn_id IS NOT NULL OR o.bank_id IS NOT NULL
)"""

# The columns every transaction loader adds, joined as `a` on `_CHARGES`.
_CHARGE_COLUMNS = """a.bank_id AS bank_id,
                          CASE WHEN a.bank_id IS NULL THEN 0 ELSE a.charged
                          END AS bank_amount,
                          COALESCE(a.auto, 0) AS bank_auto"""


class Store:
    def __init__(self, path: str = DEFAULT_DB, url: str | None = None,
                 schema: str = "public"):
        self.path = path
        # Resolved once, at construction, so a Store keeps talking to the
        # database it was opened against even if the environment changes.
        self.url = url if url is not None else db.database_url()
        # One account's ledger. On Postgres a schema per account; on SQLite
        # the account's own file is the path, and this stays "public".
        self.schema = db.valid_schema(schema)
        self._init()

    @contextmanager
    def conn(self):
        with db.connect(self.path, self.url, self.schema) as c:
            yield c

    @property
    def is_postgres(self) -> bool:
        return bool(self.url)

    def _init(self) -> None:
        if self.is_postgres and self.schema != "public":
            # Created before anything is pointed at it: with no schema on the
            # search path there is nowhere for the tables below to go.
            with self.conn() as c:
                c.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
        with self.conn() as c:
            c.executescript(SCHEMA)
        self._migrate_buckets()
        self._migrate_allocation_amounts()
        self._migrate_travel_ownership()
        self._drop_bank_funded_budgets()

    def _migrate_buckets(self) -> None:
        """Carry the buckets that piggy banks replaced into piggy banks.

        A bucket was a name and a balance: money already set aside, drawn on
        to cover an overspent month. That is a piggy bank whose target has
        already been met, so it becomes one — target and opening both the old
        balance, which derives a monthly contribution of zero and leaves the
        balance exactly where it was. Nothing is asked of the next month on
        account of a pot that is already full.

        Runs on every open and does nothing after the first, because it
        empties what it copies.
        """
        from datetime import date

        with self.conn() as c:
            old = c.execute("SELECT id, name, balance FROM buckets").fetchall()
            if not old:
                return

            this_month = date.today().isoformat()[:7]
            moved: dict[int, int] = {}
            for row in old:
                c.execute(
                    """INSERT INTO piggy_banks
                           (name, target, cadence, target_date, start_month,
                            opening, note)
                       VALUES (?, ?, 'annual', NULL, ?, ?, ?)
                       ON CONFLICT(name) DO NOTHING""",
                    (row["name"], row["balance"], this_month, row["balance"],
                     "Carried over from the bucket of the same name."),
                )
                new_row = c.execute("SELECT id FROM piggy_banks WHERE name = ?",
                                    (row["name"],)).fetchone()
                if new_row:
                    moved[row["id"]] = new_row["id"]

            for old_id, new_id in moved.items():
                c.execute(
                    """INSERT INTO piggy_draws (bank_id, month, amount, note)
                       SELECT ?, month, amount, note
                         FROM bucket_draws WHERE bucket_id = ?""",
                    (new_id, old_id),
                )

            c.execute("DELETE FROM bucket_draws")
            c.execute("DELETE FROM buckets")

    def _migrate_travel_ownership(self) -> None:
        """Give a travel bank the categories it used to fund by rule.

        Travel and Lodging were bank-funded by a hard-coded rule before banks
        chose what they pay for. A database from then, with a bank named for
        travel, keeps that behaviour: the bank now owns them. Done once — a
        later decision to own nothing must not be undone on the next open.
        """
        if self.setting("bank_categories_migrated"):
            return
        with self.conn() as c:
            owned = c.execute(
                "SELECT 1 FROM piggy_bank_categories LIMIT 1").fetchone()
            bank = c.execute(
                "SELECT id FROM piggy_banks WHERE LOWER(name) LIKE ? "
                "ORDER BY id LIMIT 1", ("%travel%",)).fetchone()
            if not owned and bank:
                for category in ("Travel", "Lodging"):
                    c.execute(
                        "INSERT OR IGNORE INTO piggy_bank_categories "
                        "(category, bank_id) VALUES (?, ?)",
                        (category, bank["id"]))
        self.set_setting("bank_categories_migrated", "1")

    def _drop_bank_funded_budgets(self) -> None:
        """Remove budget lines for categories a piggy bank pays for.

        A category a bank owns is paid by the bank, so a budget line for it
        would count it twice. `set_bank_categories` clears them as it goes;
        this catches anything written before that — idempotent, and a no-op
        on every open after the first.
        """
        with self.conn() as c:
            c.execute("DELETE FROM budgets WHERE category IN "
                      "(SELECT category FROM piggy_bank_categories)")

    def _migrate_allocation_amounts(self) -> None:
        """Add `piggy_allocations.amount` to a database that predates it.

        Allocation used to be all-or-nothing, so a row written before this
        column meant the bank paid the whole charge — which is what the backfill
        records. Afterwards the column holds however much the bank could cover.

        `ALTER TABLE ... ADD COLUMN` is spelled the same in both dialects but
        neither offers a portable way to ask first: SQLite has no
        `IF NOT EXISTS` for it, and probing the catalogue needs different SQL
        per dialect. So the attempt is made and a failure is read as "already
        there" — in its own transaction, because in Postgres a failed statement
        poisons the one it ran in.
        """
        try:
            with self.conn() as c:
                c.execute("ALTER TABLE piggy_allocations ADD COLUMN amount REAL")
        except Exception:                                        # noqa: BLE001
            return
        with self.conn() as c:
            c.execute(
                """UPDATE piggy_allocations SET amount = (
                       SELECT t.amount FROM transactions t WHERE t.id = txn_id)
                    WHERE amount IS NULL""")

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
        """Every row, each carrying the piggy bank it was allocated to.

        The allocation is joined on here rather than left for callers to look
        up, so that no analysis can forget to ask: a charge charged to a bank
        arrives already marked, and `analytics.counts_as_spending` keeps it out
        of the month's totals without anything else having to know.
        """
        with self.conn() as c:
            rows = c.execute(
                f"""SELECT t.*, {_CHARGE_COLUMNS}
                     FROM transactions t
                     LEFT JOIN {_CHARGES} a ON a.txn_id = t.id
                    ORDER BY t.date DESC, t.id""").fetchall()
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
            # The column prefix matters: `clause` is written against the bare
            # table, and `date`/`category` are unambiguous only because
            # `_CHARGES` has neither.
            rows = c.execute(
                f"""SELECT t.*, {_CHARGE_COLUMNS}
                      FROM transactions t
                      LEFT JOIN {_CHARGES} a ON a.txn_id = t.id
                    {clause}
                    ORDER BY t.date DESC, t.id LIMIT ? OFFSET ?""",
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
        """One row, carrying its piggy-bank allocation like the other loaders.

        Without the join this returned a transaction that always looked
        unallocated, so re-charging one to the same bank measured the bank's
        balance against a figure its own allocation had already reduced.
        """
        with self.conn() as c:
            row = c.execute(
                f"""SELECT t.*, {_CHARGE_COLUMNS}
                     FROM transactions t
                     LEFT JOIN {_CHARGES} a ON a.txn_id = t.id
                    WHERE t.id = ?""", (txn_id,)).fetchone()
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
            ("piggy_allocations", "piggy-bank allocations"),
            ("piggy_optouts", "charges kept out of piggy banks"),
            ("piggy_draws", "piggy-bank draws"),
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

    def category_groups(self) -> dict[str, str]:
        """Category -> the budget line it is folded into. Absent = its own."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT category, parent FROM category_groups").fetchall()
        return {r["category"]: r["parent"] for r in rows}

    def set_category_groups(self, mapping: dict[str, str]) -> None:
        """Replace the whole grouping. Validation is the caller's job."""
        with self.conn() as c:
            c.execute("DELETE FROM category_groups")
            for category, parent in sorted(mapping.items()):
                c.execute(
                    "INSERT INTO category_groups (category, parent) VALUES (?, ?)",
                    (category, parent))

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

    # ── The mortgage ──────────────────────────────────────────────────────
    # What you typed, kept as one setting; the arithmetic is in
    # finance/mortgage.py. It owns one fixed commitment, whose amount is the
    # mortgage's monthly cost, so the plan subtracts it like rent.

    def mortgage(self) -> dict | None:
        raw = self.setting("mortgage")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    def save_mortgage(self, terms: dict, monthly: float) -> int:
        """Store the mortgage and make its commitment say `monthly`.

        Adopts a commitment already called Mortgage rather than adding a
        second one beside it, which would subtract the same payment twice.
        """
        current = self.mortgage() or {}
        costs = self.fixed_costs()
        owned = next((f for f in costs if f.id == current.get("fixed_cost_id")), None)
        if owned is None:
            owned = next((f for f in costs if f.name.strip().lower() == "mortgage"), None)
        if owned is None:
            cost_id = self.add_fixed_cost("Mortgage", monthly, "Rent & Housing")
        else:
            cost_id = owned.id
            self.update_fixed_cost(cost_id, "Mortgage", monthly, "Rent & Housing")
        self.set_setting("mortgage", json.dumps({**terms, "fixed_cost_id": cost_id}))
        return cost_id

    def delete_mortgage(self) -> bool:
        current = self.mortgage()
        if current is None:
            return False
        if current.get("fixed_cost_id"):
            self.delete_fixed_cost(int(current["fixed_cost_id"]))
        with self.conn() as c:
            c.execute("DELETE FROM settings WHERE key = 'mortgage'")
        return True

    # ── CoastFIRE ─────────────────────────────────────────────────────────
    # What you typed into the retirement calculator. It changes nothing else.

    def coastfire(self) -> dict | None:
        raw = self.setting("coastfire")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    def save_coastfire(self, inputs: dict) -> None:
        self.set_setting("coastfire", json.dumps(inputs))

    def clear_coastfire(self) -> bool:
        with self.conn() as c:
            cur = c.execute("DELETE FROM settings WHERE key = 'coastfire'")
            return bool(cur.rowcount and cur.rowcount > 0)

    def mortgage_cost_id(self) -> int | None:
        current = self.mortgage()
        return int(current["fixed_cost_id"]) if current and current.get("fixed_cost_id") else None

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

    # ── Piggy banks ──────────────────────────────────────────────────────────
    # The arithmetic lives in finance/piggy.py; this only stores the decisions.

    def piggy_banks(self) -> list:
        from .piggy import Bank
        with self.conn() as c:
            rows = c.execute(
                "SELECT id, name, target, cadence, target_date, start_month, "
                "opening, note FROM piggy_banks ORDER BY name").fetchall()
        return [Bank(id=r["id"], name=r["name"], target=r["target"],
                     cadence=r["cadence"], target_date=r["target_date"],
                     start_month=r["start_month"], opening=r["opening"],
                     note=r["note"] or "") for r in rows]

    def piggy_bank(self, bank_id: int):
        return next((b for b in self.piggy_banks() if b.id == bank_id), None)

    def add_piggy_bank(self, name: str, target: float, cadence: str,
                       target_date: str | None, start_month: str,
                       opening: float = 0.0, note: str = "") -> int:
        with self.conn() as c:
            c.execute(
                """INSERT INTO piggy_banks
                       (name, target, cadence, target_date, start_month, opening, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (name.strip(), float(target), cadence, target_date,
                 start_month, float(opening), note.strip()),
            )
            row = c.execute("SELECT id FROM piggy_banks WHERE name = ?",
                            (name.strip(),)).fetchone()
            return row["id"]

    def update_piggy_bank(self, bank_id: int, name: str, target: float,
                          cadence: str, target_date: str | None,
                          opening: float = 0.0, note: str = "") -> bool:
        """Change a bank's terms, keeping the month it started.

        The start month is deliberately not editable here: it is what the
        accrued balance is measured from, and letting it move would rewrite
        how much the bank is supposed to hold today.
        """
        with self.conn() as c:
            cur = c.execute(
                """UPDATE piggy_banks
                      SET name = ?, target = ?, cadence = ?, target_date = ?,
                          opening = ?, note = ?
                    WHERE id = ?""",
                (name.strip(), float(target), cadence, target_date,
                 float(opening), note.strip(), bank_id),
            )
            return cur.rowcount > 0

    def delete_piggy_bank(self, bank_id: int) -> bool:
        """Remove a bank, releasing whatever was charged to it.

        The allocations go with it, which puts that spending back into the
        months it happened in. That is the honest outcome — the money was
        always spent — but it does change past months, so the UI says so
        before asking.
        """
        with self.conn() as c:
            c.execute("DELETE FROM piggy_allocations WHERE bank_id = ?", (bank_id,))
            c.execute("DELETE FROM piggy_draws WHERE bank_id = ?", (bank_id,))
            c.execute("DELETE FROM piggy_bank_categories WHERE bank_id = ?",
                      (bank_id,))
            cur = c.execute("DELETE FROM piggy_banks WHERE id = ?", (bank_id,))
            return cur.rowcount > 0

    # ── Allocations: spending charged to a bank rather than to its month ──────

    def allocations(self) -> dict[str, int]:
        """Transaction id → bank id, for every charge a bank pays — allocated
        by hand or paid automatically because the bank owns its category."""
        with self.conn() as c:
            rows = c.execute(f"SELECT txn_id, bank_id FROM {_CHARGES} a").fetchall()
        return {r["txn_id"]: r["bank_id"] for r in rows}

    def allocate(self, txn_id: str, bank_id: int, amount: float) -> None:
        """Charge `amount` of this transaction to a bank.

        `amount` is never more than the charge itself. Charging it by hand
        also withdraws an earlier "count as everyday" — the latest decision
        about a charge is the one that stands.
        """
        with self.conn() as c:
            c.execute(
                """INSERT INTO piggy_allocations (txn_id, bank_id, amount)
                   VALUES (?, ?, ?)
                   ON CONFLICT(txn_id) DO UPDATE SET bank_id = excluded.bank_id,
                                                     amount = excluded.amount""",
                (txn_id, bank_id, round(float(amount), 2)),
            )
            c.execute("DELETE FROM piggy_optouts WHERE txn_id = ?", (txn_id,))

    def unallocate(self, txn_id: str) -> bool:
        """Put a charge back in the month it fell in.

        Removing the allocation is not enough for a charge in a category a
        bank owns: the bank would pick it straight back up. So that case is
        recorded as an opt-out — "count this one as everyday".
        """
        with self.conn() as c:
            cur = c.execute("DELETE FROM piggy_allocations WHERE txn_id = ?", (txn_id,))
            removed = cur.rowcount > 0
            still = c.execute(f"SELECT 1 FROM {_CHARGES} a WHERE a.txn_id = ?",
                              (txn_id,)).fetchone()
            if still:
                c.execute("INSERT OR IGNORE INTO piggy_optouts (txn_id) VALUES (?)",
                          (txn_id,))
                removed = True
            return removed

    # ── What each bank pays for ───────────────────────────────────────────────

    def bank_categories(self) -> dict[int, list[str]]:
        """Bank id → the categories it pays for, alphabetically."""
        with self.conn() as c:
            rows = c.execute(
                """SELECT bc.category AS category, bc.bank_id AS bank_id
                     FROM piggy_bank_categories bc
                     JOIN piggy_banks b ON b.id = bc.bank_id
                    ORDER BY bc.category""").fetchall()
        out: dict[int, list[str]] = {}
        for r in rows:
            out.setdefault(r["bank_id"], []).append(r["category"])
        return out

    def bank_funded_categories(self) -> set[str]:
        """Every category some bank pays for — out of the budget split and the
        weekly number, because the bank pays for it instead."""
        return {c for cats in self.bank_categories().values() for c in cats}

    def set_bank_categories(self, bank_id: int, categories) -> None:
        """Make `categories` exactly what this bank pays for.

        A budget line for a category the bank now owns is removed, since the
        bank pays for it; the caller has already checked that no other bank
        owns any of them.
        """
        wanted = sorted({c.strip() for c in categories if c and c.strip()})
        with self.conn() as c:
            c.execute("DELETE FROM piggy_bank_categories WHERE bank_id = ?",
                      (bank_id,))
            for category in wanted:
                c.execute(
                    "INSERT INTO piggy_bank_categories (category, bank_id) "
                    "VALUES (?, ?)", (category, bank_id))
                c.execute("DELETE FROM budgets WHERE category = ?", (category,))

    def bank_charges_by_month(self) -> dict[int, dict[str, float]]:
        """Bank id → month → what came out of it that month.

        The per-month breakdown rather than a total, because a bank's
        contribution now depends on *when* it was spent: a trip charged in
        January is repaid over the months since, and one charged yesterday is
        not. See `piggy.status`.
        """
        out: dict[int, dict[str, float]] = {}
        with self.conn() as c:
            rows = c.execute(
                f"""SELECT a.bank_id AS bank_id,
                          SUBSTR(t.date, 1, 7) AS month,
                          COALESCE(SUM(a.charged), 0) AS total
                     FROM {_CHARGES} a
                     JOIN transactions t ON t.id = a.txn_id
                    GROUP BY a.bank_id, SUBSTR(t.date, 1, 7)""").fetchall()
            for r in rows:
                out.setdefault(r["bank_id"], {})[r["month"]] = round(r["total"], 2)

            drawn = c.execute(
                "SELECT bank_id, month, COALESCE(SUM(amount), 0) AS total "
                "FROM piggy_draws GROUP BY bank_id, month").fetchall()
            for r in drawn:
                months = out.setdefault(r["bank_id"], {})
                months[r["month"]] = round(months.get(r["month"], 0.0)
                                           + r["total"], 2)
        return out

    def charged_to_banks(self) -> dict[int, float]:
        """Bank id → everything taken out of it: allocated charges and draws.

        Joined against transactions rather than summing a stored total, so a
        charge that was deleted, refunded or recategorised stops counting
        without anything having to remember to adjust a balance.
        """
        totals: dict[int, float] = {}
        with self.conn() as c:
            rows = c.execute(
                f"""SELECT a.bank_id AS bank_id,
                          COALESCE(SUM(a.charged), 0) AS total
                     FROM {_CHARGES} a
                    GROUP BY a.bank_id""").fetchall()
            for r in rows:
                totals[r["bank_id"]] = round(r["total"], 2)

            drawn = c.execute(
                "SELECT bank_id, COALESCE(SUM(amount), 0) AS total "
                "FROM piggy_draws GROUP BY bank_id").fetchall()
            for r in drawn:
                totals[r["bank_id"]] = round(
                    totals.get(r["bank_id"], 0.0) + r["total"], 2)
        return totals

    def allocated_in(self, month: str) -> float:
        """What this month's spending charged to banks comes to."""
        with self.conn() as c:
            row = c.execute(
                f"""SELECT COALESCE(SUM(a.charged), 0) AS total
                     FROM {_CHARGES} a
                     JOIN transactions t ON t.id = a.txn_id
                    WHERE t.date LIKE ?""", (f"{month}-%",)).fetchone()
        return round(row["total"], 2)

    def delete_draw(self, draw_id: int) -> bool:
        """Undo a draw: the bank gets the money back, the month loses it."""
        with self.conn() as c:
            cur = c.execute("DELETE FROM piggy_draws WHERE id = ?", (draw_id,))
            return (cur.rowcount or 0) > 0

    def covered_in(self, month: str) -> float:
        with self.conn() as c:
            row = c.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM piggy_draws WHERE month = ?",
                (month,),
            ).fetchone()
        return round(row["total"], 2)

    def draws(self, month: str | None = None) -> list[dict]:
        sql = ("SELECT d.id, d.month, d.amount, d.note, d.created_at, b.name "
               "FROM piggy_draws d JOIN piggy_banks b ON b.id = d.bank_id")
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
