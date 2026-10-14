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


def _people(raw) -> list[str]:
    try:
        out = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return [str(p) for p in out if str(p).strip()] if isinstance(out, list) else []


def _people_label(people: list[str]) -> str:
    """"Sam", "Sam and Alex", "Sam, Alex and Jo"."""
    people = [p for p in people if p]
    if len(people) <= 1:
        return people[0] if people else ""
    return f"{', '.join(people[:-1])} and {people[-1]}"


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

-- How much of a charge was really yours, when friends paid you back for the
-- rest. Kept beside the transaction rather than written into it, so the row
-- stays exactly what the card reported and a re-import or a sync can't undo it.
CREATE TABLE IF NOT EXISTS txn_shares (
    txn_id   TEXT PRIMARY KEY,
    my_share REAL NOT NULL
);

-- How much of a transaction went into investments, when only part of it did.
-- Beside the row for the same reason as a share: a sync can't undo it.
CREATE TABLE IF NOT EXISTS txn_invested (
    txn_id TEXT PRIMARY KEY,
    amount REAL NOT NULL
);

-- Where a transfer you can't see the other end of goes, decided once: an
-- e-transfer recipient, an account number, a brokerage. Applied only to what
-- matching left unmatched — see finance/transfers.py.
CREATE TABLE IF NOT EXISTS transfer_destinations (
    key      TEXT PRIMARY KEY,
    label    TEXT,
    category TEXT NOT NULL
);

-- What each connected account holds, as the bank last reported it. Comes with
-- every sync at no extra cost. Credit cards and loans report what is owed.
CREATE TABLE IF NOT EXISTS account_balance (
    account_id   TEXT PRIMARY KEY,
    current      REAL,
    available    REAL,
    credit_limit REAL,
    currency     TEXT,
    as_of        TEXT
);

-- One reading per account per day, so the history becomes exact over time.
CREATE TABLE IF NOT EXISTS account_balance_days (
    account_id TEXT NOT NULL,
    day        TEXT NOT NULL,
    current    REAL,
    PRIMARY KEY (account_id, day)
);

-- Accounts you share. A row on one that can't be matched to your own
-- accounts is another member's unless you say it was yours.
CREATE TABLE IF NOT EXISTS joint_accounts (
    account_id TEXT PRIMARY KEY,
    label      TEXT NOT NULL
);

-- Names where a purchase on a joint account is always yours.
CREATE TABLE IF NOT EXISTS joint_mine (
    merchant_key TEXT PRIMARY KEY
);

-- Money that came into a joint account from outside: who put it in, "me"
-- (from an account not in Pearl) or "them" (the other person), for one row
-- or for every deposit from that sender to that account. What "them" puts
-- in pays for that much of the month's joint spending. See finance/joint.py.
CREATE TABLE IF NOT EXISTS joint_deposits (
    txn_id TEXT PRIMARY KEY,
    who    TEXT NOT NULL
);
-- Who an e-Transfer was from or to, when she named them (finance/etransfers.py).
CREATE TABLE IF NOT EXISTS txn_party (
    txn_id TEXT PRIMARY KEY,
    name   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS joint_deposit_rules (
    account_id TEXT NOT NULL,
    sender_key TEXT NOT NULL,
    who        TEXT NOT NULL,
    PRIMARY KEY (account_id, sender_key)
);

-- Money friends sent back for a charge you paid for everyone. An inflow repays
-- at most one charge; the charge's share is what is left once they have: an
-- $80 dinner with $60 sent back cost you $20, and the $60 is neither income
-- nor money in — it was always theirs.
CREATE TABLE IF NOT EXISTS txn_paybacks (
    inflow_id TEXT PRIMARY KEY,
    charge_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_payback_charge ON txn_paybacks(charge_id);

-- Rows you left out, and why. A row is either excluded on its own (rule_id
-- NULL) or because a rule of yours matched it. `kept` = 1 is a row a rule
-- matched that you put back: it stays here so the rule never takes it again.
CREATE TABLE IF NOT EXISTS txn_exclusions (
    txn_id     TEXT PRIMARY KEY,
    reason     TEXT NOT NULL,
    rule_id    INTEGER,
    kept       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- "Leave out every transaction like this": an account, words in the
-- description, the person it was with, and optionally dates and amounts.
-- Applied to every row now and to every row that arrives later.
CREATE TABLE IF NOT EXISTS exclusion_rules (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   TEXT,
    keyword      TEXT,
    counterparty TEXT,
    date_from    TEXT,
    date_to      TEXT,
    amount_min   REAL,
    amount_max   REAL,
    reason       TEXT NOT NULL,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

-- What kind of income a row is (salary, bonus, interest, gifts, government,
-- tax_refund, other). Beside the row, like a share, so a sync can't undo it.
CREATE TABLE IF NOT EXISTS txn_income_type (
    txn_id TEXT PRIMARY KEY,
    kind   TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'rule'
);

-- Review items you settled without changing anything ("yes, that's right").
CREATE TABLE IF NOT EXISTS review_dismissed (
    item_key   TEXT PRIMARY KEY,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
-- Needs a look items she skipped (THL-213): still asked, but in Skipped.
CREATE TABLE IF NOT EXISTS review_skipped (
    item_key   TEXT PRIMARY KEY,
    skipped_on TEXT DEFAULT CURRENT_TIMESTAMP
);

-- A category Pearl suggested that you said was right. Kept with the category
-- you confirmed: if a later sync files the row somewhere else, that new
-- category is a suggestion again.
CREATE TABLE IF NOT EXISTS txn_confirmed (
    txn_id     TEXT PRIMARY KEY,
    category   TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- One-offs (THL-71): a transaction she marked as unusual, with the day she
-- did. Left out of her usual month, projections and trend suggestions; still
-- counted in its own month and in safe to spend.
CREATE TABLE IF NOT EXISTS txn_oneoff (
    txn_id TEXT PRIMARY KEY,
    since  TEXT NOT NULL
);

-- Likely duplicates (THL-165): the copy, the row it repeats, and her answer.
-- pending = counted once until she answers; same = the copy is soft-hidden
-- (kept, with its link to the twin, so Undo works); different = both count.
CREATE TABLE IF NOT EXISTS txn_duplicates (
    txn_id     TEXT PRIMARY KEY,
    twin_id    TEXT NOT NULL,
    state      TEXT NOT NULL DEFAULT 'pending',
    found_on   TEXT,
    decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_dup_twin ON txn_duplicates(twin_id);

-- Your private note on a transaction (140 characters at most).
CREATE TABLE IF NOT EXISTS txn_notes (
    txn_id     TEXT PRIMARY KEY,
    note       TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
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
-- A charge split with other people (Pearl S-01, THL-124): how it was split
-- and whether to watch for their repayments. Your share is written to
-- txn_shares as before, so everything that counts spending already counts
-- only your part. The people are first names you typed, nothing more, and
-- are used only to match an e-Transfer from the same name to this split.
CREATE TABLE IF NOT EXISTS txn_splits (
    txn_id TEXT PRIMARY KEY,
    mode   TEXT NOT NULL,
    watch  INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS txn_split_people (
    txn_id TEXT NOT NULL,
    pos    INTEGER NOT NULL,
    name   TEXT NOT NULL,
    amount REAL NOT NULL,
    PRIMARY KEY (txn_id, pos)
);
-- Which person in a split a repayment came from, when you said.
CREATE TABLE IF NOT EXISTS txn_payback_person (
    inflow_id TEXT PRIMARY KEY,
    person    TEXT NOT NULL
);
-- How each account counts (Pearl AM-02, AM-03, AM-07), whoever it came from.
-- `counted` = 0 keeps an account's rows in the ledger but out of safe to
-- spend, spending, income and the snapshot ("Count in my budget"), the same
-- way an exclusion does. `removed` = 1 is an account taken off the Accounts
-- page whose past rows were kept: they stay counted, nothing new comes in.
CREATE TABLE IF NOT EXISTS account_settings (
    account_id TEXT PRIMARY KEY,
    counted    INTEGER NOT NULL DEFAULT 1,
    nickname   TEXT,
    removed    INTEGER NOT NULL DEFAULT 0
);
-- A balance added by hand for a bank Pearl can't link (AM-05, AM-06). No
-- transactions: it counts in the snapshot (and, for savings, toward the
-- Anchor) and never in spending. Its account id is "hand:<id>".
CREATE TABLE IF NOT EXISTS manual_accounts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    kind       TEXT NOT NULL,
    balance    REAL NOT NULL,
    updated_on TEXT NOT NULL,
    counted    INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
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
           CASE WHEN m.amount IS NOT NULL
                     AND m.amount < COALESCE(s.my_share, t.amount - COALESCE(pb.total, 0)) - COALESCE(iv.amount, 0)
                     THEN m.amount
                WHEN COALESCE(s.my_share, t.amount - COALESCE(pb.total, 0)) - COALESCE(iv.amount, 0) < 0
                     THEN 0
                ELSE COALESCE(s.my_share, t.amount - COALESCE(pb.total, 0)) - COALESCE(iv.amount, 0)
                END AS charged,
           CASE WHEN m.txn_id IS NULL THEN 1 ELSE 0 END AS auto
      FROM transactions t
      LEFT JOIN piggy_allocations m ON m.txn_id = t.id
      LEFT JOIN txn_shares s ON s.txn_id = t.id
      LEFT JOIN txn_invested iv ON iv.txn_id = t.id
      LEFT JOIN _PAYBACKS_ pb ON pb.charge_id = t.id
      LEFT JOIN (SELECT bc.category AS category, b.id AS bank_id,
                        b.start_month AS start_month
                   FROM piggy_bank_categories bc
                   JOIN piggy_banks b ON b.id = bc.bank_id) o
             ON o.category = t.category
            AND SUBSTR(t.date, 1, 7) >= o.start_month
            AND NOT EXISTS (SELECT 1 FROM piggy_optouts x WHERE x.txn_id = t.id)
            AND (s.txn_id IS NOT NULL OR NOT EXISTS
                 (SELECT 1 FROM joint_accounts j WHERE j.account_id = t.account_id))
     WHERE (m.txn_id IS NOT NULL OR o.bank_id IS NOT NULL)
       AND NOT EXISTS (SELECT 1 FROM txn_exclusions e
                        WHERE e.txn_id = t.id AND e.kept = 0)
       AND NOT EXISTS (SELECT 1 FROM txn_duplicates d
                        WHERE d.txn_id = t.id AND d.state != 'different')
)"""

# Tables of what she said about one row, keyed by its id (`txn_id`).
_ROW_TABLES = ("txn_shares", "txn_invested", "piggy_allocations", "piggy_optouts",
               "txn_exclusions", "txn_income_type", "txn_confirmed", "txn_notes",
               "txn_splits", "txn_split_people", "txn_oneoff", "txn_duplicates",
               "joint_deposits", "txn_party")

# What friends have sent back for each charge, as a positive total.
_PAYBACKS = """(
    SELECT p.charge_id AS charge_id, -SUM(r.amount) AS total
      FROM txn_paybacks p
      JOIN transactions r ON r.id = p.inflow_id
     GROUP BY p.charge_id
)"""
_CHARGES = _CHARGES.replace("_PAYBACKS_", _PAYBACKS)

# The columns every transaction loader adds, joined as `a` on `_CHARGES`.
# A bank pays your share of a charge, never more: friends who paid you back
# for the rest are not the bank's to cover.
_CHARGE_COLUMNS = """sh.my_share AS my_share,
                          ivx.amount AS invested,
                          pbx.total AS paid_back,
                          rpx.charge_id AS repays,
                          jax.label AS joint,
                          jax.share AS joint_share,
                          jax.people AS joint_people,
                          COALESCE(jdx.person, jrx.person) AS joint_person,
                          CASE WHEN jmx.merchant_key IS NULL THEN 0 ELSE 1 END
                              AS joint_mine,
                          COALESCE(jdx.who, jrx.who) AS joint_from,
                          ptx.name AS party,
                          a.bank_id AS bank_id,
                          CASE WHEN a.bank_id IS NULL THEN 0 ELSE a.charged
                          END AS bank_amount,
                          COALESCE(a.auto, 0) AS bank_auto,
                          COALESCE(exx.reason,
                                   CASE WHEN dpx.state IN ('pending', 'same')
                                   THEN 'Possible duplicate' END,
                                   CASE WHEN acs.counted = 0
                                   THEN 'Not in your budget' END) AS excluded,
                          itx.kind AS income_type,
                          itx.source AS income_type_source,
                          oox.since AS one_off_since,
                          dpx.twin_id AS duplicate_of,
                          dpx.state AS duplicate_state,
                          acs.nickname AS account_nickname"""


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
        self._migrate_plaid_error_code()
        self._migrate_plaid_logo()
        self._migrate_joint_share()
        self._migrate_joint_people()
        self._migrate_travel_ownership()
        self._drop_bank_funded_budgets()
        self._migrate_saved()
        self._forget_mortgage_terms()
        self._retire_trips()
        self._retire_bulk_edits()
        self._drop_self_twins()

    def _drop_self_twins(self) -> None:
        """Clear "same purchase?" questions that pair a row with itself.

        Merging two copies of an account (reconnect, `rekey_rows`) used to
        carry the question between a row's copies onto the kept row, so the
        row was asked about — and hidden as a copy — against itself.
        """
        with self.conn() as c:
            c.execute("DELETE FROM txn_duplicates WHERE txn_id = twin_id")

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

    def _forget_mortgage_terms(self) -> None:
        """The Mortgage page is gone; its saved terms with it. The commitment
        it put in the plan stays, as an ordinary line you can change."""
        with self.conn() as c:
            c.execute("DELETE FROM settings WHERE key = 'mortgage'")

    def _retire_trips(self) -> None:
        """Trips are gone (2026-10-14; Sort a date range replaces them). The
        three tables are dropped, and a row a trip moved keeps its category
        as her own choice, so nothing changes on screen. Each statement on
        its own: a table already gone fails, and on Postgres a failed
        statement spoils its transaction."""
        for sql in ("UPDATE transactions SET category_source = 'user' "
                    "WHERE category_source = 'trip'",
                    "DROP TABLE IF EXISTS trip_rows",
                    "DROP TABLE IF EXISTS marked_trips",
                    "DROP INDEX IF EXISTS idx_trip_dates",
                    "DROP TABLE IF EXISTS trips"):
            try:
                with self.conn() as c:
                    c.execute(sql)
            except Exception:                                    # noqa: BLE001
                continue

    def _retire_bulk_edits(self) -> None:
        """Sort a date range is gone (2026-10-14; the selection's batch edit
        does the job). Its tables are dropped, and a row it moved keeps its
        category as her own choice. Each statement on its own, as above."""
        for sql in ("UPDATE transactions SET category_source = 'user' "
                    "WHERE category_source = 'bulk'",
                    "DROP TABLE IF EXISTS bulk_edit_rows",
                    "DROP TABLE IF EXISTS bulk_edits"):
            try:
                with self.conn() as c:
                    c.execute(sql)
            except Exception:                                    # noqa: BLE001
                continue

    def _migrate_saved(self) -> None:
        """Investments became Saved: one bucket for money put away, wherever
        it went. Idempotent — after the first open there is nothing to rename.
        Budgets and budget lines never held it (it was never spending)."""
        with self.conn() as c:
            c.execute("UPDATE transactions SET category = 'Saved' "
                      "WHERE category = 'Investments'")
            c.execute("UPDATE merchant_overrides SET category = 'Saved' "
                      "WHERE category = 'Investments'")

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

    def _migrate_plaid_error_code(self) -> None:
        """Add `plaid_items.error_code`: Plaid's own code for the last error
        (ITEM_LOGIN_REQUIRED, INSTITUTION_DOWN…), which says which connection
        state to show (THL-120). Tried, and a failure read as "already there",
        as above."""
        try:
            with self.conn() as c:
                c.execute("ALTER TABLE plaid_items ADD COLUMN error_code TEXT")
        except Exception:                                        # noqa: BLE001
            return

    def _migrate_plaid_logo(self) -> None:
        """Add `plaid_items.logo`: the bank's logo as a data URI, from
        Plaid's institution details. "" once looked up and none was found."""
        try:
            with self.conn() as c:
                c.execute("ALTER TABLE plaid_items ADD COLUMN logo TEXT")
        except Exception:                                        # noqa: BLE001
            return

    def _migrate_joint_share(self) -> None:
        """Add `joint_accounts.share`: the percent of a joint account that is
        hers (AM-04). Null on accounts marked joint before there was one,
        which keep the older rule — another member's unless she says."""
        try:
            with self.conn() as c:
                c.execute("ALTER TABLE joint_accounts ADD COLUMN share REAL")
        except Exception:                                        # noqa: BLE001
            return

    def _migrate_joint_people(self) -> None:
        """Who a joint account is shared with (`joint_accounts.people`, a JSON
        list of names), and which of them put money in (`person` on a deposit
        and on a sender rule). Each tried on its own: a column already there
        fails, and on Postgres a failed statement spoils its transaction."""
        for sql in ("ALTER TABLE joint_accounts ADD COLUMN people TEXT",
                    "ALTER TABLE joint_deposits ADD COLUMN person TEXT",
                    "ALTER TABLE joint_deposit_rules ADD COLUMN person TEXT"):
            try:
                with self.conn() as c:
                    c.execute(sql)
            except Exception:                                    # noqa: BLE001
                continue

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
                     LEFT JOIN txn_shares sh ON sh.txn_id = t.id
                     LEFT JOIN txn_invested ivx ON ivx.txn_id = t.id
                     LEFT JOIN {_PAYBACKS} pbx ON pbx.charge_id = t.id
                     LEFT JOIN txn_paybacks rpx ON rpx.inflow_id = t.id
                     LEFT JOIN joint_accounts jax ON jax.account_id = t.account_id
                     LEFT JOIN joint_mine jmx ON jmx.merchant_key = LOWER(t.merchant)
                     LEFT JOIN joint_deposits jdx ON jdx.txn_id = t.id
                     LEFT JOIN txn_party ptx ON ptx.txn_id = t.id
                     LEFT JOIN joint_deposit_rules jrx ON jrx.account_id = t.account_id
                                                      AND jrx.sender_key = LOWER(t.merchant)
                     LEFT JOIN txn_exclusions exx ON exx.txn_id = t.id AND exx.kept = 0
                     LEFT JOIN account_settings acs ON acs.account_id = t.account_id
                     LEFT JOIN txn_income_type itx ON itx.txn_id = t.id
                     LEFT JOIN txn_oneoff oox ON oox.txn_id = t.id
                     LEFT JOIN txn_duplicates dpx ON dpx.txn_id = t.id
                    ORDER BY t.date DESC, t.id""").fetchall()
        return self._loaded(rows)

    def query_transactions(self, month: str | None = None, category: str | None = None,
                           account_id: str | None = None, search: str | None = None,
                           start: str | None = None, end: str | None = None,
                           limit: int = 200, offset: int = 0
                           ) -> tuple[list[Transaction], int]:
        where, params = [], []
        if month:
            where.append("t.date LIKE ?")
            params.append(f"{month}%")
        if start:
            where.append("t.date >= ?")
            params.append(start)
        if end:
            where.append("t.date <= ?")
            params.append(end)
        if category:
            where.append("t.category = ?")
            params.append(category)
        if account_id:
            where.append("t.account_id = ?")
            params.append(account_id)
        if search:
            where.append("(t.merchant LIKE ? OR t.description LIKE ?)")
            params += [f"%{search}%", f"%{search}%"]

        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self.conn() as c:
            total = c.execute(
                f"SELECT COUNT(*) AS n FROM transactions t {clause}", params
            ).fetchone()["n"]
            # The column prefix matters: `clause` is written against the bare
            # table, and `date`/`category` are unambiguous only because
            # `_CHARGES` has neither.
            rows = c.execute(
                f"""SELECT t.*, {_CHARGE_COLUMNS}
                      FROM transactions t
                      LEFT JOIN {_CHARGES} a ON a.txn_id = t.id
                      LEFT JOIN txn_shares sh ON sh.txn_id = t.id
                      LEFT JOIN txn_invested ivx ON ivx.txn_id = t.id
                      LEFT JOIN {_PAYBACKS} pbx ON pbx.charge_id = t.id
                      LEFT JOIN txn_paybacks rpx ON rpx.inflow_id = t.id
                      LEFT JOIN joint_accounts jax ON jax.account_id = t.account_id
                      LEFT JOIN joint_mine jmx ON jmx.merchant_key = LOWER(t.merchant)
                      LEFT JOIN joint_deposits jdx ON jdx.txn_id = t.id
                      LEFT JOIN txn_party ptx ON ptx.txn_id = t.id
                      LEFT JOIN joint_deposit_rules jrx ON jrx.account_id = t.account_id
                                                       AND jrx.sender_key = LOWER(t.merchant)
                     LEFT JOIN txn_exclusions exx ON exx.txn_id = t.id AND exx.kept = 0
                     LEFT JOIN account_settings acs ON acs.account_id = t.account_id
                     LEFT JOIN txn_income_type itx ON itx.txn_id = t.id
                     LEFT JOIN txn_oneoff oox ON oox.txn_id = t.id
                     LEFT JOIN txn_duplicates dpx ON dpx.txn_id = t.id
                    {clause}
                    ORDER BY t.date DESC, t.id LIMIT ? OFFSET ?""",
                params + [limit, offset],
            ).fetchall()
        return self._loaded(rows), total

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
                     LEFT JOIN txn_shares sh ON sh.txn_id = t.id
                     LEFT JOIN txn_invested ivx ON ivx.txn_id = t.id
                     LEFT JOIN {_PAYBACKS} pbx ON pbx.charge_id = t.id
                     LEFT JOIN txn_paybacks rpx ON rpx.inflow_id = t.id
                     LEFT JOIN joint_accounts jax ON jax.account_id = t.account_id
                     LEFT JOIN joint_mine jmx ON jmx.merchant_key = LOWER(t.merchant)
                     LEFT JOIN joint_deposits jdx ON jdx.txn_id = t.id
                     LEFT JOIN txn_party ptx ON ptx.txn_id = t.id
                     LEFT JOIN joint_deposit_rules jrx ON jrx.account_id = t.account_id
                                                      AND jrx.sender_key = LOWER(t.merchant)
                     LEFT JOIN txn_exclusions exx ON exx.txn_id = t.id AND exx.kept = 0
                     LEFT JOIN account_settings acs ON acs.account_id = t.account_id
                     LEFT JOIN txn_income_type itx ON itx.txn_id = t.id
                     LEFT JOIN txn_oneoff oox ON oox.txn_id = t.id
                     LEFT JOIN txn_duplicates dpx ON dpx.txn_id = t.id
                    WHERE t.id = ?""", (txn_id,)).fetchone()
        return self._loaded([row])[0] if row else None

    def _loaded(self, rows) -> list[Transaction]:
        """Rows as transactions, with each joint charge carrying the part of
        it the other person's deposits that month didn't pay for."""
        from .joint import ratios
        dicts = [dict(r) for r in rows]
        if any(d.get("joint") for d in dicts):
            got = ratios(self)
            for d in dicts:
                if d.get("joint"):
                    d["joint_ratio"] = got.get((d["account_id"], str(d["date"])[:7]))
        return [Transaction.from_row(d) for d in dicts]
    def delete_transaction(self, txn_id: str) -> bool:
        with self.conn() as c:
            cur = c.execute("DELETE FROM transactions WHERE id = ?", (txn_id,))
            c.execute("DELETE FROM txn_shares WHERE txn_id = ?", (txn_id,))
            c.execute("DELETE FROM joint_deposits WHERE txn_id = ?", (txn_id,))
            c.execute("DELETE FROM txn_party WHERE txn_id = ?", (txn_id,))
            c.execute("DELETE FROM txn_invested WHERE txn_id = ?", (txn_id,))
            c.execute("DELETE FROM txn_paybacks WHERE inflow_id = ? OR charge_id = ?",
                      (txn_id, txn_id))
            c.execute("DELETE FROM txn_exclusions WHERE txn_id = ?", (txn_id,))
            c.execute("DELETE FROM txn_income_type WHERE txn_id = ?", (txn_id,))
            c.execute("DELETE FROM txn_confirmed WHERE txn_id = ?", (txn_id,))
            c.execute("DELETE FROM txn_notes WHERE txn_id = ?", (txn_id,))
            c.execute("DELETE FROM txn_splits WHERE txn_id = ?", (txn_id,))
            c.execute("DELETE FROM txn_split_people WHERE txn_id = ?", (txn_id,))
            c.execute("DELETE FROM txn_payback_person WHERE inflow_id = ?", (txn_id,))
            c.execute("DELETE FROM txn_oneoff WHERE txn_id = ?", (txn_id,))
            c.execute("DELETE FROM txn_duplicates WHERE txn_id = ? OR twin_id = ?",
                      (txn_id, txn_id))
            return cur.rowcount > 0

    def set_share(self, txn_id: str, my_share: float | None) -> None:
        """Say how much of a charge was yours; None says all of it again."""
        with self.conn() as c:
            c.execute("DELETE FROM txn_shares WHERE txn_id = ?", (txn_id,))
            if my_share is not None:
                c.execute("INSERT INTO txn_shares (txn_id, my_share) VALUES (?, ?)",
                          (txn_id, round(float(my_share), 2)))

    def set_invested(self, txn_id: str, amount: float | None) -> None:
        """Say how much of a transaction went to investments; None clears it."""
        with self.conn() as c:
            c.execute("DELETE FROM txn_invested WHERE txn_id = ?", (txn_id,))
            if amount is not None:
                c.execute("INSERT INTO txn_invested (txn_id, amount) VALUES (?, ?)",
                          (txn_id, round(float(amount), 2)))

    # ── Exclusions ───────────────────────────────────────────────────────
    def exclude(self, txn_id: str, reason: str, rule_id: int | None = None) -> None:
        """Leave one row out. Your own exclusion replaces whatever a rule did."""
        with self.conn() as c:
            c.execute("DELETE FROM txn_exclusions WHERE txn_id = ?", (txn_id,))
            c.execute("INSERT INTO txn_exclusions (txn_id, reason, rule_id, kept) "
                      "VALUES (?, ?, ?, 0)", (txn_id, reason, rule_id))

    def include(self, txn_id: str) -> bool:
        """Put an excluded row back. It is remembered as kept, so no rule
        takes it again."""
        with self.conn() as c:
            r = c.execute("SELECT rule_id FROM txn_exclusions WHERE txn_id = ? "
                          "AND kept = 0", (txn_id,)).fetchone()
            if r is None:
                return False
            # Kept rather than deleted, either way: a rule that also matches
            # this row must not take it straight back.
            c.execute("UPDATE txn_exclusions SET kept = 1 WHERE txn_id = ?", (txn_id,))
            return True

    def exclusion_rules(self) -> list[dict]:
        with self.conn() as c:
            rules = [dict(r) for r in c.execute(
                "SELECT * FROM exclusion_rules ORDER BY id").fetchall()]
            counts = {r["rule_id"]: int(r["n"]) for r in c.execute(
                "SELECT rule_id, COUNT(*) AS n FROM txn_exclusions "
                "WHERE rule_id IS NOT NULL AND kept = 0 GROUP BY rule_id").fetchall()}
        for r in rules:
            r["matched"] = counts.get(r["id"], 0)
        return rules

    def add_exclusion_rule(self, rule: dict) -> int:
        cols = ("account_id", "keyword", "counterparty", "date_from", "date_to",
                "amount_min", "amount_max", "reason")
        with self.conn() as c:
            c.execute(f"INSERT INTO exclusion_rules ({', '.join(cols)}) "
                      f"VALUES ({', '.join('?' for _ in cols)})",
                      tuple(rule.get(k) for k in cols))
            return int(c.execute("SELECT MAX(id) AS id FROM exclusion_rules")
                       .fetchone()["id"])

    def delete_exclusion_rule(self, rule_id: int) -> bool:
        with self.conn() as c:
            cur = c.execute("DELETE FROM exclusion_rules WHERE id = ?", (int(rule_id),))
            c.execute("DELETE FROM txn_exclusions WHERE rule_id = ?", (int(rule_id),))
            return (cur.rowcount or 0) > 0

    def exclusion_ids(self) -> set[str]:
        """Every row with an entry, excluded or kept: a rule never touches them."""
        with self.conn() as c:
            return {r["txn_id"] for r in
                    c.execute("SELECT txn_id FROM txn_exclusions").fetchall()}

    # ── Income type ──────────────────────────────────────────────────────
    def set_income_type(self, txn_id: str, kind: str | None, source: str = "user") -> None:
        with self.conn() as c:
            c.execute("DELETE FROM txn_income_type WHERE txn_id = ?", (txn_id,))
            if kind:
                c.execute("INSERT INTO txn_income_type (txn_id, kind, source) "
                          "VALUES (?, ?, ?)", (txn_id, kind, source))

    def write_income_types(self, kinds: dict[str, str]) -> int:
        """Guessed types, written over earlier guesses but never over yours."""
        if not kinds:
            return 0
        with self.conn() as c:
            mine = {r["txn_id"] for r in c.execute(
                "SELECT txn_id FROM txn_income_type WHERE source = 'user'").fetchall()}
            n = 0
            for tid, kind in kinds.items():
                if tid in mine:
                    continue
                c.execute("DELETE FROM txn_income_type WHERE txn_id = ?", (tid,))
                c.execute("INSERT INTO txn_income_type (txn_id, kind, source) "
                          "VALUES (?, ?, 'rule')", (tid, kind))
                n += 1
            return n

    # ── Review ───────────────────────────────────────────────────────────
    def dismissed_reviews(self) -> set[str]:
        with self.conn() as c:
            return {r["item_key"] for r in
                    c.execute("SELECT item_key FROM review_dismissed").fetchall()}

    def dismiss_review(self, key: str) -> None:
        with self.conn() as c:
            c.execute("INSERT OR IGNORE INTO review_dismissed (item_key) VALUES (?)",
                      (key,))

    def skipped_reviews(self) -> set[str]:
        with self.conn() as c:
            return {r["item_key"] for r in
                    c.execute("SELECT item_key FROM review_skipped").fetchall()}

    def skip_review(self, key: str, on: bool = True) -> None:
        """Into Skipped, or back to the queue."""
        with self.conn() as c:
            c.execute("DELETE FROM review_skipped WHERE item_key = ?", (key,))
            if on:
                c.execute("INSERT INTO review_skipped (item_key) VALUES (?)", (key,))

    def undismiss_review(self, key: str) -> None:
        """Ask about it again: an Undo of the answer that settled it."""
        with self.conn() as c:
            c.execute("DELETE FROM review_dismissed WHERE item_key = ?", (key,))

    # ── One-offs (THL-71) ────────────────────────────────────────────────
    def one_offs(self) -> dict[str, str]:
        """{txn_id: the day she marked it a one-off}."""
        with self.conn() as c:
            return {r["txn_id"]: r["since"] for r in
                    c.execute("SELECT txn_id, since FROM txn_oneoff").fetchall()}

    def set_one_off(self, txn_id: str, on: bool, since: str | None = None) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM txn_oneoff WHERE txn_id = ?", (txn_id,))
            if on:
                from datetime import date as _date
                c.execute("INSERT INTO txn_oneoff (txn_id, since) VALUES (?, ?)",
                          (txn_id, since or _date.today().isoformat()))

    # ── Possible duplicates (THL-165) ────────────────────────────────────
    def duplicate_ids(self) -> set[str]:
        """Every row in a pair, either side, answered or not."""
        with self.conn() as c:
            rows = c.execute("SELECT txn_id, twin_id FROM txn_duplicates").fetchall()
        return {r["txn_id"] for r in rows} | {r["twin_id"] for r in rows}

    def duplicates(self) -> dict[str, dict]:
        """copy id → {twin, state, found_on}."""
        with self.conn() as c:
            rows = c.execute("SELECT txn_id, twin_id, state, found_on "
                             "FROM txn_duplicates").fetchall()
        return {r["txn_id"]: {"twin": r["twin_id"], "state": r["state"],
                              "found_on": r["found_on"] or ""} for r in rows}

    def add_duplicate(self, txn_id: str, twin_id: str, state: str = "pending") -> None:
        from datetime import date as _date
        with self.conn() as c:
            c.execute("DELETE FROM txn_duplicates WHERE txn_id = ?", (txn_id,))
            c.execute("INSERT INTO txn_duplicates (txn_id, twin_id, state, found_on, "
                      "decided_at) VALUES (?, ?, ?, ?, ?)",
                      (txn_id, twin_id, state, _date.today().isoformat(),
                       None if state == "pending" else _now()))

    def set_duplicate_state(self, txn_id: str, state: str) -> bool:
        with self.conn() as c:
            cur = c.execute("UPDATE txn_duplicates SET state = ?, decided_at = ? "
                            "WHERE txn_id = ?",
                            (state, None if state == "pending" else _now(), txn_id))
            return (cur.rowcount or 0) > 0

    # ── Confirmed categories and notes ──────────────────────────────────
    def confirmed_categories(self) -> dict[str, str]:
        """{txn_id: the category you said was right}."""
        with self.conn() as c:
            return {r["txn_id"]: r["category"] for r in
                    c.execute("SELECT txn_id, category FROM txn_confirmed").fetchall()}

    def confirm_category(self, txn_id: str, category: str) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM txn_confirmed WHERE txn_id = ?", (txn_id,))
            c.execute("INSERT INTO txn_confirmed (txn_id, category) VALUES (?, ?)",
                      (txn_id, category))

    def unconfirm_category(self, txn_id: str) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM txn_confirmed WHERE txn_id = ?", (txn_id,))

    def notes(self) -> dict[str, str]:
        with self.conn() as c:
            return {r["txn_id"]: r["note"] for r in
                    c.execute("SELECT txn_id, note FROM txn_notes").fetchall()}

    def set_note(self, txn_id: str, note: str) -> None:
        """Save a note; an empty one removes it."""
        with self.conn() as c:
            c.execute("DELETE FROM txn_notes WHERE txn_id = ?", (txn_id,))
            if note:
                c.execute("INSERT INTO txn_notes (txn_id, note) VALUES (?, ?)",
                          (txn_id, note))

    def link_payback(self, charge_id: str, inflow_id: str, person: str | None = None) -> None:
        """Say this money coming in was a friend paying you back for that
        charge — and, for a split, which of the people it was. An inflow
        repays one charge, so linking it again moves it."""
        with self.conn() as c:
            c.execute("DELETE FROM txn_paybacks WHERE inflow_id = ?", (inflow_id,))
            c.execute("DELETE FROM txn_payback_person WHERE inflow_id = ?", (inflow_id,))
            c.execute("INSERT INTO txn_paybacks (inflow_id, charge_id) VALUES (?, ?)",
                      (inflow_id, charge_id))
            if person:
                c.execute("INSERT INTO txn_payback_person (inflow_id, person) VALUES (?, ?)",
                          (inflow_id, person))

    def unlink_payback(self, inflow_id: str) -> bool:
        with self.conn() as c:
            c.execute("DELETE FROM txn_payback_person WHERE inflow_id = ?", (inflow_id,))
            cur = c.execute("DELETE FROM txn_paybacks WHERE inflow_id = ?",
                            (inflow_id,))
            return (cur.rowcount or 0) > 0

    def payback_people(self) -> dict[str, str]:
        """inflow id → the person in a split it came from, where you said."""
        with self.conn() as c:
            rows = c.execute("SELECT inflow_id, person FROM txn_payback_person").fetchall()
        return {r["inflow_id"]: r["person"] for r in rows}

    # ── Splits (THL-124) ─────────────────────────────────────────────────
    def splits(self) -> dict[str, dict]:
        """charge id → {mode, watch, people: [{name, amount}]}."""
        with self.conn() as c:
            heads = c.execute("SELECT txn_id, mode, watch FROM txn_splits").fetchall()
            people = c.execute("SELECT txn_id, pos, name, amount FROM txn_split_people "
                               "ORDER BY txn_id, pos").fetchall()
        out = {r["txn_id"]: {"mode": r["mode"], "watch": bool(r["watch"]), "people": []}
               for r in heads}
        for r in people:
            if r["txn_id"] in out:
                out[r["txn_id"]]["people"].append(
                    {"name": r["name"], "amount": round(float(r["amount"]), 2)})
        return out

    def set_split(self, txn_id: str, mode: str, people: list[dict], watch: bool) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM txn_split_people WHERE txn_id = ?", (txn_id,))
            c.execute("DELETE FROM txn_splits WHERE txn_id = ?", (txn_id,))
            c.execute("INSERT INTO txn_splits (txn_id, mode, watch) VALUES (?, ?, ?)",
                      (txn_id, mode, 1 if watch else 0))
            for pos, p in enumerate(people):
                c.execute("INSERT INTO txn_split_people (txn_id, pos, name, amount) "
                          "VALUES (?, ?, ?, ?)", (txn_id, pos, p["name"], p["amount"]))

    def clear_split(self, txn_id: str) -> bool:
        with self.conn() as c:
            c.execute("DELETE FROM txn_split_people WHERE txn_id = ?", (txn_id,))
            cur = c.execute("DELETE FROM txn_splits WHERE txn_id = ?", (txn_id,))
            return (cur.rowcount or 0) > 0

    def paybacks_for(self, charge_id: str) -> list[str]:
        """The inflows linked to a charge, as ids."""
        with self.conn() as c:
            rows = c.execute("SELECT inflow_id FROM txn_paybacks WHERE charge_id = ?",
                             (charge_id,)).fetchall()
        return [r["inflow_id"] for r in rows]

    def set_categories(self, changes: dict[str, tuple[str, str]]) -> int:
        """Write (category, source) for many rows at once, never over a
        category you set yourself."""
        updated = 0
        with self.conn() as c:
            for txn_id, (category, source) in changes.items():
                cur = c.execute(
                    """UPDATE transactions SET category = ?, category_source = ?
                       WHERE id = ? AND category_source != 'user'""",
                    (category, source, txn_id))
                updated += max(cur.rowcount or 0, 0)
        return updated

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

    def forget_rows(self, ids: set[str], import_suffix: str = "") -> int:
        """Delete these exact rows, and the import records named with the
        suffix. Used to take out a copy of something that should never have
        been loaded here."""
        if not ids:
            return 0
        removed = 0
        ids = list(ids)
        with self.conn() as c:
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                marks = ",".join("?" * len(chunk))
                cur = c.execute(f"DELETE FROM transactions WHERE id IN ({marks})", chunk)
                removed += max(cur.rowcount or 0, 0)
                for table in _ROW_TABLES:
                    c.execute(f"DELETE FROM {table} WHERE txn_id IN ({marks})", chunk)
                c.execute(f"DELETE FROM txn_payback_person WHERE inflow_id IN ({marks})", chunk)
                c.execute(f"DELETE FROM txn_paybacks WHERE inflow_id IN ({marks})", chunk)
                c.execute(f"DELETE FROM txn_paybacks WHERE charge_id IN ({marks})", chunk)
            if import_suffix:
                c.execute("DELETE FROM imports WHERE filename LIKE ?",
                          (f"%{import_suffix}",))
        return removed

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
                "SELECT s.account_id, s.account_name, s.item_id, s.enabled, s.decided_by,"
                "       s.account_type, s.account_subtype, acs.nickname"
                "  FROM account_sync s"
                "  LEFT JOIN account_settings acs ON acs.account_id = s.account_id"
                " ORDER BY s.account_name"
            ).fetchall()
        return {r["account_id"]: {
            "account_id": r["account_id"],
            "account_name": r["account_name"] or r["account_id"],
            "item_id": r["item_id"] or "",
            "enabled": bool(r["enabled"]),
            "decided_by": r["decided_by"],
            "account_type": r["account_type"] or "",
            "account_subtype": r["account_subtype"] or "",
            # Her name for it, to show; `account_name` stays the bank's.
            "label": r["nickname"] or r["account_name"] or r["account_id"],
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

    def enable_auto_cash_accounts(self) -> set[str]:
        """Switch on chequing and savings accounts that only the old
        cards-only default had switched off. Returns their items' ids."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT account_id, item_id FROM account_sync"
                " WHERE enabled = 0 AND decided_by = 'auto'"
                "   AND lower(account_type) = 'depository'").fetchall()
            for r in rows:
                c.execute("UPDATE account_sync SET enabled = 1,"
                          " updated_at = CURRENT_TIMESTAMP WHERE account_id = ?",
                          (r["account_id"],))
        return {r["item_id"] for r in rows if r["item_id"]}

    def accounts_not_synced(self) -> set[str]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT account_id FROM account_sync WHERE enabled = 0").fetchall()
        return {r["account_id"] for r in rows}

    def rekey_rows(self, mapping: dict[str, str]) -> None:
        """Move what she said about rows to the ids they will have next: a
        reconnected bank brings the same purchases back under new account
        ids, so new fingerprints (`plaid_link._replace_superseded`)."""
        pairs = [(old, new) for old, new in mapping.items() if old != new]
        if not pairs:
            return
        # Where the new id already has an answer (both copies of a row were
        # in the ledger, and she answered the newer one), the newer stays.
        with self.conn() as c:
            for old, new in pairs:
                for table in _ROW_TABLES:
                    if c.execute(f"SELECT 1 FROM {table} WHERE txn_id = ?", (new,)).fetchone():
                        c.execute(f"DELETE FROM {table} WHERE txn_id = ?", (old,))
                    else:
                        c.execute(f"UPDATE {table} SET txn_id = ? WHERE txn_id = ?", (new, old))
                c.execute("UPDATE txn_duplicates SET twin_id = ? WHERE twin_id = ?", (new, old))
                for table, col in (("txn_paybacks", "inflow_id"), ("txn_payback_person", "inflow_id")):
                    if c.execute(f"SELECT 1 FROM {table} WHERE {col} = ?", (new,)).fetchone():
                        c.execute(f"DELETE FROM {table} WHERE {col} = ?", (old,))
                    else:
                        c.execute(f"UPDATE {table} SET {col} = ? WHERE {col} = ?", (new, old))
                c.execute("UPDATE txn_paybacks SET charge_id = ? WHERE charge_id = ?", (new, old))
            # A "same purchase?" question between the two copies is answered
            # by the merge itself: both sides are now one row. Left in, it
            # would ask whether a row is a copy of itself, and hide it.
            c.execute("DELETE FROM txn_duplicates WHERE txn_id = twin_id")

    def forget_accounts(self, account_ids: list[str]) -> None:
        """Drop what is known about these accounts themselves, for ones a
        reconnected bank has replaced."""
        with self.conn() as c:
            for aid in account_ids:
                for table in ("account_sync", "account_balance", "account_balance_days",
                              "account_settings", "joint_accounts"):
                    c.execute(f"DELETE FROM {table} WHERE account_id = ?", (aid,))

    def forget_account_rules(self, item_id: str) -> int:
        """Drop the rules for one bank, for when the bank itself is removed."""
        with self.conn() as c:
            for table in ("account_balance", "account_balance_days"):
                c.execute(f"DELETE FROM {table} WHERE account_id IN "
                          "(SELECT account_id FROM account_sync WHERE item_id = ?)",
                          (item_id,))
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
            ("piggy_allocations", "piggy-bank allocations"),
            ("piggy_optouts", "charges kept out of piggy banks"),
            ("piggy_draws", "piggy-bank draws"),
            ("txn_shares", "your shares of split charges"),
            ("txn_invested", "amounts marked as invested"),
            ("txn_paybacks", "money friends paid back"),
            ("txn_payback_person", "who paid you back"),
            ("txn_splits", "split charges"),
            ("txn_split_people", "people in split charges"),
            ("transfer_destinations", "where transfers go"),
            ("joint_accounts", "joint accounts"),
            ("joint_mine", "names always yours on a joint account"),
            ("joint_deposits", "who put money into a joint account"),
            ("joint_deposit_rules", "senders into a joint account"),
            ("txn_party", "names on e-Transfers"),
            ("dismissed_insights", "dismissed findings"),
            ("txn_exclusions", "excluded transactions"),
            ("exclusion_rules", "exclusion rules"),
            ("txn_income_type", "income types"),
            ("review_dismissed", "settled review items"),
            ("review_skipped", "skipped review items"),
            ("txn_confirmed", "confirmed categories"),
            ("txn_notes", "notes on transactions"),
            ("txn_oneoff", "one-offs"),
            ("txn_duplicates", "possible duplicates"),
            ("manual_accounts", "accounts added by hand"),
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
                          "last_synced = NULL, last_error = NULL, error_code = NULL")
            else:
                cur = c.execute("DELETE FROM plaid_items")
                removed["bank connections"] = max(cur.rowcount, 0)
                # The account decisions belong to those connections. Keeping
                # them would leave a relink inheriting choices about accounts
                # nobody can see any more.
                c.execute("DELETE FROM account_sync")
                c.execute("DELETE FROM account_settings")
                c.execute("DELETE FROM account_balance")
                c.execute("DELETE FROM account_balance_days")

            # Settings hold the spending plan and take-home pay, which are
            # yours rather than imported. The seed flag is the exception: it
            # records that this emptiness was deliberate.
            c.execute("DELETE FROM settings WHERE key IN "
                      "('monthly_amount', 'monthly_income')")
            c.execute(
                """INSERT INTO settings (key, value) VALUES ('seeded', 'done')
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""")
        return removed

    # Start over (Profile › Your data): what it clears besides the rows.
    START_OVER_TABLES = (
        ("transactions", "transactions"),
        ("imports", "import history"),
        *((tbl, "answers about transactions") for tbl in _ROW_TABLES),
        ("txn_paybacks", "money friends paid back"),
        ("txn_payback_person", "who paid you back"),
        ("dismissed_insights", "dismissed findings"),
        ("review_dismissed", "settled review items"),
        ("review_skipped", "skipped review items"),
        # Rules.
        ("merchant_overrides", "rules"),
        ("transfer_destinations", "rules"),
        ("exclusion_rules", "rules"),
        ("joint_mine", "rules"),
        ("joint_deposit_rules", "rules"),
        # Budgets.
        ("budgets", "budgets"),
    )
    START_OVER_SETTINGS = (
        # Income and bills.
        "income_bills", "home_income", "home_rent", "monthly_income", "income_overrides",
        "carryover",
        # Budgets and plan.
        "category_budgets", "monthly_amount", "savings_target", "savings_rate",
        "rec_dismissed", "subscription_choices", "budget_focus",
        # A cache: the next sync matches transfers afresh.
        "transfer_destinations",
    )

    def start_over(self) -> dict:
        """Clear the transactions and her organizing, and download them again.

        Gone: every row and every answer about one, her rules, her income and
        bills setup, and her budgets. Kept: the bank connections (rewound, so
        the next sync brings the whole history back), what she set on each
        account (nicknames, joint shares, the copies she hid), accounts added
        by hand, goals and treasure chests with the money added to them, and
        everything about signing in. Unlike `reset`, which empties the ledger
        for a demo or a test.
        """
        removed: dict[str, int] = {}
        with self.conn() as c:
            for table, label in self.START_OVER_TABLES:
                cur = c.execute(f"DELETE FROM {table}")
                removed[label] = removed.get(label, 0) + max(cur.rowcount or 0, 0)
            marks = ",".join("?" * len(self.START_OVER_SETTINGS))
            c.execute(f"DELETE FROM settings WHERE key IN ({marks})",
                      self.START_OVER_SETTINGS)
            c.execute("UPDATE plaid_items SET cursor = NULL, "
                      "last_synced = NULL, last_error = NULL, error_code = NULL")
            # Empty on purpose: the seeder must not refill it.
            c.execute("""INSERT INTO settings (key, value) VALUES ('seeded', 'done')
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
            # The same merchant under its stable Plaid id, so a differently
            # spelled row ("UBER *EATS PENDING") is caught too.
            entities = set()
            for r in c.execute("SELECT raw FROM transactions WHERE LOWER(merchant) = ?",
                               (key,)).fetchall():
                try:
                    eid = (json.loads(r["raw"] or "{}") or {}).get("merchant_entity_id")
                except (TypeError, ValueError):
                    eid = None
                if eid:
                    entities.add(eid)
            for eid in entities:
                c.execute(
                    """INSERT INTO merchant_overrides (merchant_key, category) VALUES (?, ?)
                       ON CONFLICT(merchant_key) DO UPDATE SET category = excluded.category""",
                    (f"entity:{eid}", category))
                c.execute(
                    """UPDATE transactions SET category = ?, category_source = 'merchant_override'
                       WHERE raw LIKE ? AND category_source != 'user'""",
                    (category, f'%"merchant_entity_id": "{eid}"%'))
            cur = c.execute(
                """UPDATE transactions SET category = ?, category_source = 'merchant_override'
                   WHERE LOWER(merchant) = ?""",
                (category, key),
            )
            return cur.rowcount

    def restore_override(self, key: str, category: str | None) -> None:
        """Put one rule back as it was — by its stored key, rows untouched.
        For Undo, which restores the rows itself."""
        with self.conn() as c:
            c.execute("DELETE FROM merchant_overrides WHERE merchant_key = ?", (key,))
            if category:
                c.execute("INSERT INTO merchant_overrides (merchant_key, category) "
                          "VALUES (?, ?)", (key, category))

    def clear_override(self, merchant: str) -> None:
        key = merchant.strip().lower()
        with self.conn() as c:
            c.execute("DELETE FROM merchant_overrides WHERE merchant_key = ?", (key,))
            for r in c.execute("SELECT raw FROM transactions WHERE LOWER(merchant) = ?",
                               (key,)).fetchall():
                try:
                    eid = (json.loads(r["raw"] or "{}") or {}).get("merchant_entity_id")
                except (TypeError, ValueError):
                    eid = None
                if eid:
                    c.execute("DELETE FROM merchant_overrides WHERE merchant_key = ?",
                              (f"entity:{eid}",))

    # ── Budgets ──────────────────────────────────────────────────────────────
    def budgets(self) -> dict[str, float]:
        with self.conn() as c:
            rows = c.execute("SELECT category, monthly FROM budgets").fetchall()
        return {r["category"]: r["monthly"] for r in rows}

    def category_groups(self) -> dict[str, str]:
        """Category -> the budget line it is folded into. Absent = its own.
        Read-only since Profile › Categories went (C1); see finance/groups.py."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT category, parent FROM category_groups").fetchall()
        return {r["category"]: r["parent"] for r in rows}

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

    def imports_by_account(self) -> dict[str, dict]:
        """The latest import of each account: the file it came from and the
        format it was read as."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT account_id, filename, format_label FROM imports "
                "ORDER BY id").fetchall()
        return {r["account_id"]: {"filename": r["filename"] or "",
                                  "format_label": r["format_label"] or ""}
                for r in rows if r["account_id"]}

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
            # Postgres has no lastrowid, and RETURNING needs SQLite 3.35 or
            # newer — this stays a local-first app — so the two are split.
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

    def add_draw(self, bank_id: int, month: str, amount: float, note: str = "") -> int:
        """Record money moving between a bank and a month.

        Positive is the bank lending the month money; negative is the month
        putting money into the bank ("Add money" on a treasure chest), which
        that month's budget gives up.
        """
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO piggy_draws (bank_id, month, amount, note) VALUES (?, ?, ?, ?)",
                (bank_id, month, round(float(amount), 2), note))
            return int(cur.lastrowid)

    def draws(self, month: str | None = None) -> list[dict]:
        sql = ("SELECT d.id, d.bank_id, d.month, d.amount, d.note, d.created_at, b.name "
               "FROM piggy_draws d JOIN piggy_banks b ON b.id = d.bank_id")
        params = []
        if month:
            sql += " WHERE d.month = ?"
            params.append(month)
        sql += " ORDER BY d.id DESC"
        with self.conn() as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]

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
                          error_code, created_at, logo
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

    # ── Transfer destinations ────────────────────────────────────────────
    def destinations(self) -> dict[str, str]:
        with self.conn() as c:
            rows = c.execute("SELECT key, category FROM transfer_destinations").fetchall()
        return {r["key"]: r["category"] for r in rows}

    def destination_labels(self) -> dict[str, str]:
        with self.conn() as c:
            rows = c.execute("SELECT key, label FROM transfer_destinations").fetchall()
        return {r["key"]: r["label"] or "" for r in rows}

    def set_destination(self, key: str, category: str, label: str = "") -> None:
        with self.conn() as c:
            c.execute(
                """INSERT INTO transfer_destinations (key, label, category) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET category = excluded.category,
                                                  label = excluded.label""",
                (key, label, category))

    def clear_destination(self, key: str) -> bool:
        with self.conn() as c:
            cur = c.execute("DELETE FROM transfer_destinations WHERE key = ?", (key,))
            return (cur.rowcount or 0) > 0

    # ── Balances ─────────────────────────────────────────────────────────
    def set_balance(self, account_id: str, current, available, limit,
                    currency: str, day: str) -> None:
        def num(x):
            return None if x is None else round(float(x), 2)
        cur, avail, lim = num(current), num(available), num(limit)
        with self.conn() as c:
            c.execute(
                """INSERT INTO account_balance
                       (account_id, current, available, credit_limit, currency, as_of)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(account_id) DO UPDATE SET
                       current = excluded.current, available = excluded.available,
                       credit_limit = excluded.credit_limit,
                       currency = excluded.currency, as_of = excluded.as_of""",
                (account_id, cur, avail, lim, currency or "", day))
            if cur is not None:
                c.execute(
                    """INSERT INTO account_balance_days (account_id, day, current)
                       VALUES (?, ?, ?)
                       ON CONFLICT(account_id, day) DO UPDATE SET current = excluded.current""",
                    (account_id, day, cur))

    def balances(self) -> dict[str, dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM account_balance").fetchall()
        return {r["account_id"]: {"current": r["current"], "available": r["available"],
                                  "limit": r["credit_limit"], "currency": r["currency"],
                                  "as_of": r["as_of"]} for r in rows}

    def first_balances(self) -> dict[str, dict]:
        """Each account's first reading: what it held when Pearl first synced
        it. A card's is its before-Pearl balance (THL-9 D3)."""
        with self.conn() as c:
            rows = c.execute(
                """SELECT d.account_id, d.day, d.current FROM account_balance_days d
                    WHERE d.current IS NOT NULL AND d.day = (
                          SELECT MIN(day) FROM account_balance_days
                           WHERE account_id = d.account_id AND current IS NOT NULL)"""
            ).fetchall()
        return {r["account_id"]: {"day": r["day"], "current": r["current"]} for r in rows}

    # ── Joint accounts ───────────────────────────────────────────────────
    def joint_accounts(self) -> dict[str, str]:
        with self.conn() as c:
            rows = c.execute("SELECT account_id, label FROM joint_accounts").fetchall()
        return {r["account_id"]: r["label"] for r in rows}

    def set_joint(self, account_id: str, label: str | None) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM joint_accounts WHERE account_id = ?", (account_id,))
            if label:
                c.execute("INSERT INTO joint_accounts (account_id, label) VALUES (?, ?)",
                          (account_id, label))

    def joint_people(self) -> dict[str, list[str]]:
        """{account_id: the people she shares it with}, for joint accounts."""
        with self.conn() as c:
            rows = c.execute("SELECT account_id, people FROM joint_accounts").fetchall()
        return {r["account_id"]: _people(r["people"]) for r in rows}

    def set_joint_people(self, account_id: str, people: list[str]) -> None:
        """Who a joint account is shared with. Marks it joint if it wasn't
        (no set share: the money in decides, finance/joint.py); its label
        becomes their names."""
        label = _people_label(people) or "Joint"
        with self.conn() as c:
            cur = c.execute("UPDATE joint_accounts SET people = ?, label = ? WHERE account_id = ?",
                            (json.dumps(people), label, account_id))
            if not cur.rowcount or cur.rowcount <= 0:
                c.execute("INSERT INTO joint_accounts (account_id, label, people) VALUES (?, ?, ?)",
                          (account_id, label, json.dumps(people)))

    def joint_shares(self) -> dict[str, float | None]:
        """Her share of each joint account, in percent; None where unset."""
        with self.conn() as c:
            rows = c.execute("SELECT account_id, share FROM joint_accounts").fetchall()
        return {r["account_id"]: (None if r["share"] is None else float(r["share"]))
                for r in rows}

    def set_joint_share(self, account_id: str, share: float | None,
                        label: str = "Joint") -> None:
        """Mark an account joint with her share in percent (AM-04), or not
        joint at all with None. Keeps the label it already had."""
        with self.conn() as c:
            if share is None:
                c.execute("DELETE FROM joint_accounts WHERE account_id = ?", (account_id,))
                return
            cur = c.execute("UPDATE joint_accounts SET share = ? WHERE account_id = ?",
                            (float(share), account_id))
            if not cur.rowcount or cur.rowcount <= 0:
                c.execute("INSERT INTO joint_accounts (account_id, label, share) "
                          "VALUES (?, ?, ?)", (account_id, label, float(share)))

    # ── How each account counts (AM-02 to AM-07) ─────────────────────────
    def account_settings(self) -> dict[str, dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM account_settings").fetchall()
        return {r["account_id"]: {"counted": bool(r["counted"]),
                                  "nickname": r["nickname"] or "",
                                  "removed": bool(r["removed"])} for r in rows}

    def account_nicknames(self) -> dict[str, str]:
        """{account_id: her name for it}, for the accounts she named."""
        return {aid: s["nickname"] for aid, s in self.account_settings().items()
                if s["nickname"]}

    def set_account_setting(self, account_id: str, **fields) -> None:
        """Change `counted`, `nickname` or `removed` for one account."""
        allowed = {"counted", "nickname", "removed"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        if not fields:
            return
        values = {k: (int(bool(v)) if k != "nickname" else (v or None))
                  for k, v in fields.items()}
        with self.conn() as c:
            exists = c.execute("SELECT 1 FROM account_settings WHERE account_id = ?",
                               (account_id,)).fetchone()
            if not exists:
                c.execute("INSERT INTO account_settings (account_id) VALUES (?)",
                          (account_id,))
            sets = ", ".join(f"{k} = ?" for k in values)
            c.execute(f"UPDATE account_settings SET {sets} WHERE account_id = ?",
                      (*values.values(), account_id))

    def not_counted(self) -> set[str]:
        """Accounts whose rows and balance stay out of her budget."""
        with self.conn() as c:
            rows = c.execute("SELECT account_id FROM account_settings "
                             "WHERE counted = 0").fetchall()
        return {r["account_id"] for r in rows}

    # ── Balances added by hand (AM-05, AM-06) ────────────────────────────
    MANUAL_KINDS = ("chequing", "savings", "credit")

    def manual_accounts(self) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM manual_accounts ORDER BY id").fetchall()
        return [{"id": int(r["id"]), "account_id": f"hand:{int(r['id'])}",
                 "name": r["name"], "kind": r["kind"],
                 "balance": round(float(r["balance"]), 2),
                 "updated_on": r["updated_on"], "counted": bool(r["counted"])}
                for r in rows]

    def manual_account(self, account_id: str) -> dict | None:
        return next((a for a in self.manual_accounts() if a["account_id"] == account_id),
                    None)

    def add_manual_account(self, name: str, kind: str, balance: float,
                           updated_on: str) -> str:
        with self.conn() as c:
            c.execute("INSERT INTO manual_accounts (name, kind, balance, updated_on) "
                      "VALUES (?, ?, ?, ?)", (name, kind, round(float(balance), 2),
                                              updated_on))
            new = c.execute("SELECT MAX(id) AS id FROM manual_accounts").fetchone()["id"]
        return f"hand:{int(new)}"

    def update_manual_account(self, account_id: str, **fields) -> bool:
        allowed = {"name", "balance", "updated_on", "counted", "kind"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        try:
            mid = int(str(account_id).split(":", 1)[1])
        except (IndexError, ValueError):
            return False
        if not fields:
            return self.manual_account(account_id) is not None
        if "counted" in fields:
            fields["counted"] = int(bool(fields["counted"]))
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self.conn() as c:
            cur = c.execute(f"UPDATE manual_accounts SET {sets} WHERE id = ?",
                            (*fields.values(), mid))
            return (cur.rowcount or 0) > 0

    def delete_manual_account(self, account_id: str) -> bool:
        try:
            mid = int(str(account_id).split(":", 1)[1])
        except (IndexError, ValueError):
            return False
        with self.conn() as c:
            cur = c.execute("DELETE FROM manual_accounts WHERE id = ?", (mid,))
            return (cur.rowcount or 0) > 0

    # ── Saved sorting rules (S-03) ───────────────────────────────────────
    def delete_override(self, key: str) -> bool:
        """Forget one merchant rule without touching the rows it sorted: they
        are kept as sorted by her, so nothing already sorted changes."""
        key = key.strip().lower()
        with self.conn() as c:
            found = c.execute("SELECT 1 FROM merchant_overrides WHERE merchant_key = ?",
                              (key,)).fetchone()
            if not found:
                return False
            c.execute("UPDATE transactions SET category_source = 'user' "
                      "WHERE LOWER(merchant) = ? AND category_source = 'merchant_override'",
                      (key,))
        rows_raw = []
        with self.conn() as c:
            rows_raw = c.execute("SELECT raw FROM transactions WHERE LOWER(merchant) = ?",
                                 (key,)).fetchall()
            c.execute("DELETE FROM merchant_overrides WHERE merchant_key = ?", (key,))
            for r in rows_raw:
                try:
                    eid = (json.loads(r["raw"] or "{}") or {}).get("merchant_entity_id")
                except (TypeError, ValueError):
                    eid = None
                if eid:
                    c.execute("DELETE FROM merchant_overrides WHERE merchant_key = ?",
                              (f"entity:{eid}",))
                    c.execute("UPDATE transactions SET category_source = 'user' "
                              "WHERE raw LIKE ? AND category_source = 'merchant_override'",
                              (f'%"merchant_entity_id": "{eid}"%',))
        return True

    def set_joint_deposit(self, txn_id: str, who: str | None,
                          person: str | None = None) -> None:
        """Who put this money into a joint account: "me", "them" (and which
        of the people she shares it with, `person`), or None to ask again."""
        with self.conn() as c:
            c.execute("DELETE FROM joint_deposits WHERE txn_id = ?", (txn_id,))
            if who:
                c.execute("INSERT INTO joint_deposits (txn_id, who, person) VALUES (?, ?, ?)",
                          (txn_id, who, person or None))

    def set_party(self, txn_id: str, name: str | None) -> None:
        """Who an e-Transfer was from or to, or None for the bank's name."""
        with self.conn() as c:
            c.execute("DELETE FROM txn_party WHERE txn_id = ?", (txn_id,))
            if name:
                c.execute("INSERT INTO txn_party (txn_id, name) VALUES (?, ?)", (txn_id, name))

    def set_joint_deposit_rule(self, account_id: str, sender: str, who: str | None,
                               person: str | None = None) -> None:
        """Every deposit from this sender into this joint account."""
        key = (sender or "").strip().lower()
        if not key:
            return
        with self.conn() as c:
            c.execute("DELETE FROM joint_deposit_rules WHERE account_id = ? AND sender_key = ?",
                      (account_id, key))
            if who:
                c.execute("INSERT INTO joint_deposit_rules (account_id, sender_key, who, person) "
                          "VALUES (?, ?, ?, ?)", (account_id, key, who, person or None))

    def set_joint_mine(self, merchant: str, on: bool) -> None:
        key = merchant.strip().lower()
        with self.conn() as c:
            c.execute("DELETE FROM joint_mine WHERE merchant_key = ?", (key,))
            if on:
                c.execute("INSERT INTO joint_mine (merchant_key) VALUES (?)", (key,))

    def write_categories(self, changes: dict[str, tuple[str, str]]) -> None:
        """Write (category, source) for these rows, your own choices included —
        for undoing one, which is the only time that is right."""
        with self.conn() as c:
            for txn_id, (category, source) in changes.items():
                c.execute("UPDATE transactions SET category = ?, category_source = ? "
                          "WHERE id = ?", (category, source, txn_id))

    def row_ids_for_accounts(self, account_ids: list[str]) -> set[str]:
        if not account_ids:
            return set()
        marks = ",".join("?" * len(account_ids))
        with self.conn() as c:
            rows = c.execute(f"SELECT id FROM transactions WHERE account_id IN ({marks})",
                             list(account_ids)).fetchall()
        return {r["id"] for r in rows}

    def has_plaid_rows(self) -> bool:
        with self.conn() as c:
            return c.execute("SELECT 1 FROM transactions WHERE source = 'plaid' "
                             "LIMIT 1").fetchone() is not None

    def reconcile_plaid(self, returned: dict[str, tuple[set[str], str]]) -> int:
        """After a full sync, drop stored Plaid rows Plaid no longer has.

        `returned` is, per account, every transaction id the full sync
        delivered and the earliest date among them. A stored row on that
        account, dated within that range, whose id was not delivered no longer
        exists at the bank — in practice a pending charge that posted while the
        sync was being started over, which never reports the removal. Rows
        before the range are older than what Plaid sends and are kept.
        """
        if not returned:
            return 0
        stale: set[str] = set()
        with self.conn() as c:
            for account_id, (ids, earliest) in returned.items():
                rows = c.execute(
                    "SELECT id, date, raw FROM transactions "
                    "WHERE account_id = ? AND source = 'plaid' AND date >= ?",
                    (account_id, earliest)).fetchall()
                for r in rows:
                    try:
                        pid = (json.loads(r["raw"] or "{}") or {}).get("plaid_id")
                    except (ValueError, TypeError):
                        continue
                    if pid and pid not in ids:
                        stale.add(r["id"])
        return self.forget_rows(stale)

    def rewind_plaid_cursor(self, item_id: str) -> None:
        """Make the next sync fetch this bank's whole history again.

        For an account switched back on: its rows were dropped while it was
        off, and the cursor moved past them, so without this they would never
        arrive. Rows already stored are skipped on the way in.
        """
        with self.conn() as c:
            c.execute("UPDATE plaid_items SET cursor = NULL WHERE item_id = ?",
                      (item_id,))

    def set_plaid_cursor(self, item_id: str, cursor: str) -> None:
        with self.conn() as c:
            c.execute(
                """UPDATE plaid_items
                   SET cursor = ?, last_synced = ?, last_error = NULL, error_code = NULL
                   WHERE item_id = ?""",
                (cursor, _now(), item_id),
            )

    def set_plaid_logo(self, item_id: str, logo: str) -> None:
        with self.conn() as c:
            c.execute("UPDATE plaid_items SET logo = ? WHERE item_id = ?", (logo or "", item_id))

    def set_plaid_error(self, item_id: str, message: str, code: str = "") -> None:
        with self.conn() as c:
            c.execute("UPDATE plaid_items SET last_error = ?, error_code = ? WHERE item_id = ?",
                      (message[:500], (code or "")[:64] or None, item_id))

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
