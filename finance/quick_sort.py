"""Quick sort when you come back (THL-244 QS-01 to QS-06; THL-254).

On sign-in, when there are new transactions Pearl isn't sure of — the same
rows Needs a look asks about (THL-227): Plaid's label at low confidence, or
a row filed as Other — offer to sort them one card at a time. Shown at most
once a day, and only for rows she hasn't been offered before: "Later" and
"Skip this one" leave a row in Needs a look, and it isn't new next time.

Each card is ✓ Right (the guess is confirmed, as Needs a look does), a
different category (saved, and a rule for the merchant, so the next one
sorts itself), "It wasn't a purchase…" (What was this?, so the payback and
transfer rules apply), or Skip. The done screen shows safe to spend before
and after, one line on why, and how many rules were saved.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date

from .models import Transaction

SHOWN_KEY = "quick_sort_shown_on"      # the day the prompt was last shown
OFFERED_KEY = "quick_sort_offered"     # rows already offered (list, newest last)
BATCH_KEY = "quick_sort_batch"         # the batch in progress and what it changed
MAX_ITEMS = 10
OFFERED_CAP = 500


def _json(st, key: str, default):
    raw = st.setting(key)
    if raw in (None, ""):
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _save(st, key: str, value) -> None:
    st.set_setting(key, json.dumps(value, sort_keys=True))


def offered(st) -> list[str]:
    out = _json(st, OFFERED_KEY, [])
    return out if isinstance(out, list) else []


def mark_offered(st, ids: list[str]) -> None:
    seen = offered(st)
    have = set(seen)
    for i in ids:
        if i not in have:
            seen.append(i)
            have.add(i)
    _save(st, OFFERED_KEY, seen[-OFFERED_CAP:])


def unsure_rows(st, transactions: list[Transaction], today: date, everything: bool = False) -> list[dict]:
    """Needs a look's unsure categories, newest first, not yet offered and
    not in Skipped — or, for "Quick sort all" on To review (2026-10-21),
    every one still there whether or not it was offered before."""
    from .review import build
    review = build(transactions, today=today.isoformat(), dismissed=st.dismissed_reviews(),
                   splits=st.splits(), payer=st.payback_people(), skipped=st.skipped_reviews())
    seen = set() if everything else set(offered(st))
    rows = [u for u in review.get("unsure_category", [])
            if not u.get("skipped") and u["txn"]["id"] not in seen]
    rows.sort(key=lambda u: u["txn"]["date"], reverse=True)
    return rows


def recent_categories(transactions: list[Transaction], n: int = 4) -> list[str]:
    """The categories she chose most recently, by hand."""
    out: list[str] = []
    for t in sorted(transactions, key=lambda t: t.date, reverse=True):
        if t.category_source != "user" or not t.category:
            continue
        if t.category not in out:
            out.append(t.category)
        if len(out) >= n:
            break
    return out


def suggested_categories(t: Transaction, transactions: list[Transaction], guess: str,
                         n: int = 3) -> list[str]:
    """Pearl's guess, then where other rows from this merchant went."""
    out = [guess] if guess and guess != "Other" else []
    key = " ".join((t.merchant or "").lower().split())
    if key:
        same = Counter(x.category for x in transactions
                       if " ".join((x.merchant or "").lower().split()) == key
                       and x.fingerprint != t.fingerprint and x.category
                       and x.category_source in ("user", "merchant_override"))
        for cat, _ in same.most_common():
            if cat not in out:
                out.append(cat)
    return out[:n]


def items(st, transactions: list[Transaction], today: date, everything: bool = False) -> list[dict]:
    """The cards: one per unsure row, at most MAX_ITEMS (every one, for
    "Quick sort all"), described as the transactions list describes them."""
    from . import kinds, marks, txlist
    rows = unsure_rows(st, transactions, today, everything)
    if not everything:
        rows = rows[:MAX_ITEMS]
    if not rows:
        return []
    ctx = txlist.Context(transactions, st.confirmed_categories(), st.notes(),
                         {b.id: b.name for b in st.piggy_banks()}, splits=st.splits(),
                         kinds=kinds.kind_map(st, transactions, today),
                         tags=st.tags(), saved_to=st.saved_to(), refunds=st.refunds(),
                         payback_kinds=st.payback_kinds(), names=st.merchant_names(),
                         accounts=marks.account_labels(st), payer=st.payback_people())
    by_id = {t.fingerprint: t for t in transactions}
    recent = recent_categories(transactions)
    out = []
    for u in rows:
        t = by_id.get(u["txn"]["id"])
        if t is None:
            continue
        r = txlist.describe(t, ctx)
        suggested = suggested_categories(t, transactions, u["guess"])
        out.append({
            "id": t.fingerprint, "merchant": r["merchant"], "date": r["date"],
            "account": r["account"], "amount": r["amount"], "inflow": r["inflow"],
            "logo": r.get("logo") or "", "guess": u["guess"], "reason": u["reason"],
            "suggested": suggested,
            "recent": [c for c in recent if c not in suggested],
        })
    return out


def safe_to_spend(st, transactions: list[Transaction], today: date) -> float | None:
    from . import api as core
    sts = core._home_sts(st, transactions, today)
    return sts.get("shown") if sts.get("shown") is not None else sts.get("amount")


def questions(review: dict) -> list[tuple[str, str | None]]:
    """Every question Needs a look asks, as (key, transaction id): the same
    list, so Quick sort and Needs a look count the same (2026-10-24)."""
    out = [("u:" + t["id"], t["id"]) for t in (review.get("unsorted") or {}).get("transfers", [])]
    for part in ("recurring_transfer", "unsure_category", "money_in", "joint_in", "who_sent",
                 "income_type", "three_pay_month", "duplicate"):
        for it in review.get(part) or []:
            out.append((it["key"], (it.get("txn") or {}).get("id")))
    return out


def prompt(st, transactions: list[Transaction], today: date, everything: bool = False) -> dict:
    """What the app asks on open: whether to show the prompt, and what is in it.

    One number for the whole app (2026-10-24): the prompt counts everything
    Needs a look asks about, and Quick sort walks that same list (`review`,
    which the app turns into cards the way Needs a look does). It shows once
    a day, only when something is new since it last offered — or always,
    with `everything`, for the Quick sort button on Home and To review.
    `items` are the category cards on their own, kept for older apps."""
    from .review import for_store
    review = for_store(st, today.isoformat())
    asked = questions(review)
    seen = set(offered(st))
    new = [k for k, tid in asked if k not in seen and (tid is None or tid not in seen)]
    shown_today = st.setting(SHOWN_KEY) == today.isoformat()
    count = review.get("count", 0)
    show = count > 0 and (everything or (bool(new) and not shown_today))
    cards = items(st, transactions, today, everything)
    return {"show": show, "count": count, "keys": [k for k, _ in asked], "review": review,
            "items": cards, "shown_today": shown_today,
            "safe_to_spend": safe_to_spend(st, transactions, today) if count else None}


def begin(st, transactions: list[Transaction], today: date, ids: list[str], start: bool) -> dict:
    """Start (QS-02) or Later (QS-01): either way the prompt is done for
    today and these rows aren't new any more."""
    st.set_setting(SHOWN_KEY, today.isoformat())
    # The app sends the questions' keys (2026-10-24); the rows they ask
    # about are offered too, so neither comes back as new.
    from .review import for_store
    asked = dict(questions(for_store(st, today.isoformat())))
    mark_offered(st, list(ids) + [asked[i] for i in ids if asked.get(i)])
    if start:
        by_id = {t.fingerprint: t for t in transactions}
        _save(st, BATCH_KEY, {
            "started": today.isoformat(),
            "before": safe_to_spend(st, transactions, today),
            "items": {i: (by_id[i].category or "Other") for i in ids if i in by_id},
            "changes": [],
        })
    return {"ok": True}


def step(st, transactions: list[Transaction], today: date, txn_id: str, action: str,
         category: str | None = None, title: str | None = None) -> dict | tuple[dict, int]:
    """One card answered."""
    from .categorize import CATEGORIES
    t = next((x for x in transactions if x.fingerprint == txn_id), None)
    if t is None:
        return {"error": "No such transaction."}, 404
    before = t.category or "Other"
    key = "cat:" + txn_id
    rule = False
    if action == "right":
        st.confirm_category(txn_id, before)
        st.dismiss_review(key)
        change = {"id": txn_id, "action": "right", "from": before, "to": before}
    elif action == "category":
        if not category or category not in CATEGORIES:
            return {"error": "Pick a category."}, 400
        if (t.merchant or "").strip():
            st.set_override(t.merchant, category)
            rule = True
        else:
            st.set_transaction_category(txn_id, category)
        st.dismiss_review(key)
        change = {"id": txn_id, "action": "category", "from": before, "to": category, "rule": rule}
    elif action == "marked":
        # What was this? did the work (finance/marks.py); note what it said.
        st.dismiss_review(key)
        change = {"id": txn_id, "action": "marked", "from": before, "to": None,
                  "title": (title or "")[:120]}
    elif action == "skip":
        change = {"id": txn_id, "action": "skip", "from": before, "to": before}
    else:
        return {"error": "Say what to do with it."}, 400
    mark_offered(st, [txn_id])
    batch = _json(st, BATCH_KEY, None)
    if isinstance(batch, dict):
        batch["changes"] = [c for c in batch.get("changes", []) if c.get("id") != txn_id] + [change]
        _save(st, BATCH_KEY, batch)
    fresh = st.all_transactions()
    return {"ok": True, "rule_saved": rule, "safe_to_spend": safe_to_spend(st, fresh, today)}


def _count_words(n: int) -> str:
    return {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six"}.get(n, str(n))


def reason_words(changes: list[dict]) -> str:
    """"Two were Groceries Pearl had counted as Shopping, and one transfer
    was Saved." Only what moved; confirmations and skips say nothing."""
    moved = Counter((c["from"], c["to"]) for c in changes
                    if c.get("action") == "category" and c.get("to") and c["to"] != c["from"])
    marked = [c for c in changes if c.get("action") == "marked" and c.get("title")]
    parts = []
    for (frm, to), n in moved.most_common():
        parts.append(f"{_count_words(n)} {'was' if n == 1 else 'were'} {to} Pearl had counted as {frm}")
    for c in marked:
        parts.append(f"one was “{c['title'].rstrip('.')}”")
    if not parts:
        return "Every guess was right, so nothing moved."
    if len(parts) == 1:
        return parts[0][0].upper() + parts[0][1:] + "."
    body = ", ".join(parts[:-1]) + f", and {parts[-1]}"
    return body[0].upper() + body[1:] + "."


def finish(st, transactions: list[Transaction], today: date) -> dict:
    """The done screen (QS-04)."""
    batch = _json(st, BATCH_KEY, None)
    if not isinstance(batch, dict):
        return {"sorted": 0, "before": None, "after": safe_to_spend(st, transactions, today),
                "reason": "", "rules": 0, "skipped": 0}
    changes = batch.get("changes", [])
    done = [c for c in changes if c.get("action") in ("right", "category", "marked")]
    rules = sum(1 for c in changes if c.get("rule"))
    after = safe_to_spend(st, transactions, today)
    st.set_setting(BATCH_KEY, "")
    return {"sorted": len(done), "skipped": sum(1 for c in changes if c.get("action") == "skip"),
            "before": batch.get("before"), "after": after,
            "reason": reason_words(changes), "rules": rules}
