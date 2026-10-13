"""A copy of her data to download (THL-116 D-01, D-02).

One .zip, as the design decided: `accounts.csv` and `transactions.csv` — the
spreadsheet D-01 promises, with the categories she chose — and
`settings.json` with everything else Pearl keeps about her: her profile, her
consents and their history, her notification choices, her goals, her rules
and budgets, and her settings. Bank access tokens are never in it.

Built on request, in memory, from her own ledger only.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime, timezone

from . import users

ACCOUNT_COLUMNS = ("name", "institution", "kind", "mask", "how_added", "balance",
                   "counted_in_budget", "joint_share", "transactions", "history_from",
                   "updated_at")
TRANSACTION_COLUMNS = ("id", "date", "post_date", "merchant", "description", "amount",
                       "money", "currency", "category", "account", "account_id",
                       "left_out", "note", "source")
_HOW = {"plaid": "Linked through Plaid", "hand": "Added by hand", "statement": "From a statement"}


def _csv(columns, rows) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(columns)
    for row in rows:
        w.writerow(["" if row.get(c) is None else row.get(c) for c in columns])
    # A byte-order mark so a spreadsheet opens the accents and curly
    # apostrophes as written.
    return ("﻿" + out.getvalue()).encode("utf-8")


def _accounts(st) -> list[dict]:
    from .profile_api import _all_rows
    return [{"name": a["name"], "institution": a["institution"], "kind": a["kind"],
             "mask": a["mask"], "how_added": _HOW.get(a["source"], a["source"]),
             "balance": a["balance"], "counted_in_budget": "yes" if a["counted"] else "no",
             "joint_share": a["joint_share"], "transactions": a["transactions"],
             "history_from": a["history_from"], "updated_at": a["updated_at"]}
            for a in _all_rows(st)]


def _transactions(st) -> list[dict]:
    notes = st.notes()
    out = []
    for t in st.all_transactions():
        tid = t.fingerprint
        out.append({"id": tid, "date": t.date, "post_date": t.post_date,
                    "merchant": t.merchant, "description": t.description,
                    "amount": abs(t.amount), "money": "out" if t.amount > 0 else "in",
                    "currency": t.currency, "category": t.category,
                    "account": t.account_name, "account_id": t.account_id,
                    "left_out": t.excluded or "", "note": notes.get(tid, ""),
                    "source": t.source})
    return out


def _everything_else(base, user, st) -> dict:
    from .profile_api import _rules
    settings = {}
    with st.conn() as c:
        for r in c.execute("SELECT key, value FROM settings ORDER BY key").fetchall():
            if r["key"] == "seeded":
                continue
            try:
                settings[r["key"]] = json.loads(r["value"])
            except (TypeError, ValueError):
                settings[r["key"]] = r["value"]
    profile, consents, log, notifications = {}, {}, [], None
    if user is not None:
        profile = {"email": user.email, "first_name": user.first_name,
                   "province": user.province, "username": user.username}
        consents = users.effective_consents(user)
        log = users.consent_log(base, user.id)
        notifications = users.notification_prefs(user)
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "profile": profile,
        "consents": consents,
        "consent_history": log,
        "notifications": notifications,
        "goals": [{"name": b.name, "target": b.target, "cadence": b.cadence,
                   "target_date": b.target_date, "start_month": b.start_month,
                   "opening": b.opening, "note": b.note} for b in st.piggy_banks()],
        "rules": [{k: v for k, v in r.items() if k != "id"} for r in _rules(st)],
        "budgets": st.budgets(),
        "settings": settings,
    }


def build(base, user, st) -> tuple[bytes, dict]:
    """(the .zip, what's in it: accounts and transactions counted)."""
    accounts = _accounts(st)
    txns = _transactions(st)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("accounts.csv", _csv(ACCOUNT_COLUMNS, accounts))
        z.writestr("transactions.csv", _csv(TRANSACTION_COLUMNS, txns))
        z.writestr("settings.json", json.dumps(_everything_else(base, user, st),
                                               indent=2, ensure_ascii=False, default=str))
    data = buf.getvalue()
    return data, {"accounts": len(accounts), "transactions": len(txns), "bytes": len(data)}
