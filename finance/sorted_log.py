"""Sorted today and Pearl sorted: answers can be seen, and taken back, from
where you would look.

Today's answers are written as they happen, by the blueprint's after_request,
so every way of answering lands in one list with its Undo. What Pearl sorted
without asking is worked out from the ledger, each row with its reason.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, timedelta

from .analytics import is_others
from .models import Transaction

LOG_KEY = "sorted_today"
MAX_ROWS = 300

# What answers a question: (method, path). Skips and other edits are not answers.
_ANSWERS = (
    ("POST", re.compile(r"/transactions/([^/]+)/mark$")),
    ("PUT", re.compile(r"/transactions/([^/]+)/confirm$")),
    ("PUT", re.compile(r"/transactions/([^/]+)/joint-from$")),
    ("PUT", re.compile(r"/transactions/([^/]+)/income-type$")),
    ("PUT", re.compile(r"/quick-sort/([^/]+)$")),
    ("POST", re.compile(r"/review/pair/([^/]+)$")),
    ("POST", re.compile(r"/review/duplicates/([^/]+)$")),
    ("PATCH", re.compile(r"/transactions/([^/]+)$")),
)


def answered(method: str, path: str, body: dict) -> str | None:
    """The transaction this request answered, or None."""
    for m, pattern in _ANSWERS:
        hit = pattern.search(path) if m == method else None
        if not hit or hit.group(1) in ("batch", "undo"):
            continue
        # marked: the mark before it was logged. skip and undo aren't answers.
        if "/quick-sort/" in path and body.get("action") not in ("right", "category"):
            return None
        if method == "PATCH" and "category" not in body:
            return None
        return hit.group(1)
    return None


def _rows(st, today: str) -> list[dict]:
    raw = st.setting(LOG_KEY)
    try:
        rows = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        rows = []
    return [r for r in rows if isinstance(r, dict) and r.get("on") == today]


def record(st, today: str, txn_id: str, reply: dict) -> str:
    """Note one answer. Returns its entry id, which its Undo carries."""
    entry = uuid.uuid4().hex[:12]
    rows = [r for r in _rows(st, today) if r.get("id") != txn_id]
    rows.insert(0, {"entry": entry, "id": txn_id, "on": today, "title": reply.get("title") or "",
                    "also": len(reply.get("also") or []), "undo": reply.get("undo")})
    st.set_setting(LOG_KEY, json.dumps(rows[:MAX_ROWS]))
    return entry


def record_undo(st, today: str, entry: str, undo: dict) -> None:
    rows = _rows(st, today)
    for r in rows:
        if r.get("entry") == entry:
            r["undo"] = undo
    st.set_setting(LOG_KEY, json.dumps(rows))


def forget(st, today: str, entry: str) -> None:
    """Undo: the answer leaves the list."""
    st.set_setting(LOG_KEY, json.dumps([r for r in _rows(st, today) if r.get("entry") != entry]))


def count_today(st, today: str) -> int:
    return len(_rows(st, today))


def today_rows(st, today: str) -> list[dict]:
    by_id = {t.fingerprint: t for t in st.all_transactions()}
    out = []
    for r in _rows(st, today):
        t = by_id.get(r["id"])
        if t is None:
            continue
        also = r.get("also") or 0
        line = r.get("title") or t.category or "Sorted"
        out.append({"id": t.fingerprint, "date": t.date[:10], "merchant": t.merchant or t.description,
                    "amount": t.amount, "line": f"{line} · {also + 1} rows" if also else line,
                    "undo": r.get("undo")})
    return out


def reason(t: Transaction) -> str:
    """Why this row is sorted, in plain words."""
    category = t.category or "Other"
    if t.excluded:
        return f"Left out · {t.excluded}"
    return {
        "merchant_override": f"{category} · your rule",
        "transfer_match": "Moved between your accounts",
        "destination": f"{category} · where you said these go",
        "range": f"{category} · dates you sorted",
        "issuer": f"{category} · your bank said so",
        "rule": f"{category} · from its name",
        "card_inflow": "A payment to your card",
    }.get(t.category_source or "", f"{category} · Pearl’s best match")


def pearl_rows(st, review: dict, today: str, ids_in) -> list[dict]:
    """The rows nobody was asked about, newest first, each with its reason."""
    since = (date.fromisoformat(today) - timedelta(days=60)).isoformat()
    asked = ids_in(review)
    confirmed = st.confirmed_categories()
    rows = [t for t in st.all_transactions()
            if t.date[:10] >= since and t.fingerprint not in asked and t.fingerprint not in confirmed
            and t.category_source != "user" and not (is_others(t) and not t.excluded)]
    rows.sort(key=lambda t: t.date, reverse=True)
    return [{"id": t.fingerprint, "date": t.date[:10], "merchant": t.merchant or t.description,
             "amount": t.amount, "line": reason(t)} for t in rows]
