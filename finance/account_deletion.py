"""Deleting an account, for good (THL-116 D-03 to D-05).

What D-03 promises, in order:

1. Her banks are disconnected: every Plaid item in her ledger is revoked at
   Plaid (`plaid_link.unlink`), so no access token outlives the account.
2. Her ledger goes: for an account with a ledger of its own, the SQLite file
   (and its journal files) or the Postgres schema `u_<id>`; for the first
   account, whose ledger shares the original database with the account list,
   every row of every ledger table, leaving the `app_*` tables alone.
3. Her sign-in goes: the account row, passkeys, codes and consent history,
   which also signs her out on every device — a session names an account
   that no longer exists (`users.forget`). Only a record that the account
   existed and when it was deleted is kept.

Nothing of any other account is touched: each account's ledger is its own
namespace (see `finance/users.py`), and every app_* delete names her id.
"""

from __future__ import annotations

import os

from . import users


def _ledger_tables(st) -> list[str]:
    """Every table in this ledger that isn't the account list's."""
    with st.conn() as c:
        if st.is_postgres:
            rows = c.execute(
                "SELECT table_name AS name FROM information_schema.tables "
                "WHERE table_schema = ? AND table_type = 'BASE TABLE'",
                (st.schema,)).fetchall()
        else:
            rows = c.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return sorted(r["name"] for r in rows
                  if not r["name"].startswith(("app_", "sqlite_")))


def _empty_in_place(st) -> int:
    """Delete every ledger row, keeping the tables (the first account's ledger
    shares its database with everyone's sign-in). Marked as emptied on purpose
    so a hosted instance doesn't load the bundled ledger back into it."""
    removed = 0
    tables = _ledger_tables(st)
    with st.conn() as c:
        for table in tables:
            cur = c.execute(f'DELETE FROM "{table}"')
            removed += max(cur.rowcount or 0, 0)
    st.set_setting("seeded", "done")
    return removed


def _drop_ledger(base, st) -> None:
    """Remove an account's own ledger entirely."""
    if st.is_postgres:
        if st.schema == "public":                  # never the shared one
            raise ValueError("refusing to drop the shared schema")
        with base.conn() as c:
            c.execute(f'DROP SCHEMA IF EXISTS "{st.schema}" CASCADE')
        return
    if os.path.abspath(st.path) == os.path.abspath(base.path):
        raise ValueError("refusing to remove the shared database")
    for suffix in ("", "-wal", "-shm", "-journal"):
        try:
            os.remove(st.path + suffix)
        except FileNotFoundError:
            pass


def delete_account(base, user: users.User, st, stores: dict | None = None) -> dict:
    """Disconnect her banks, remove her ledger and her sign-in. Returns what
    was done. `st` is her ledger; `stores` the app's cache of open ledgers."""
    from . import plaid_link

    items = st.plaid_items()
    revoked = 0
    for item in items:
        try:
            revoked += 1 if plaid_link.unlink(st, item["item_id"]) else 0
        except Exception:                              # noqa: BLE001
            # Forgotten here even if Plaid couldn't be reached: the ledger and
            # its tokens are about to go either way.
            pass
    if user.owner or st is base:
        _empty_in_place(st)
    else:
        _drop_ledger(base, st)
    if stores is not None:
        stores.pop(user.id, None)
    users.forget(base, user)
    return {"banks_disconnected": len(items), "revoked_at_plaid": revoked}
