"""Questions Pearl asks about her plan, not about one transaction's category
(the logic review, 2026-11-07). Each one is a Yes or No card in Needs a look
and Quick sort, tied to the transaction that raised it.

* Is this where you save? (decision 2): once per savings account she moves
  money into. Yes counts money moved there as put away, and money moved back
  out as taken out of savings. An account picked for her Anchor counts
  without asking.
* Still paid by Acme? (decision 8): her confirmed pay hasn't arrived for two
  of its cycles. Pearl keeps expecting it until she answers; No stops it.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

SAVERS_KEY = "saver_accounts"
NOT_SAVERS_KEY = "saver_no"
# Two missed cycles, and a few days' grace, before Pearl asks.
STALE_DAYS = {"weekly": 16, "biweekly": 33, "semimonthly": 36, "monthly": 66}
SAVINGS_SUBTYPES = {"savings", "money market", "hisa", "cash management", "tfsa savings"}


def _list(st, key: str) -> list[str]:
    try:
        out = json.loads(st.setting(key) or "[]")
    except (TypeError, ValueError):
        return []
    return out if isinstance(out, list) else []


def savers(st) -> set[str]:
    """Accounts money is put away in: the ones she said yes to, and the ones
    she picked for her Anchor."""
    return set(_list(st, SAVERS_KEY)) | set(_list(st, "anchor_accounts"))


def _money(x: float) -> str:
    return f"${abs(x):,.0f}" if abs(x) == round(abs(x)) else f"${abs(x):,.2f}"


def build(st, txns, today: str) -> list[dict]:
    from .review import _brief
    out = []
    since = (date.fromisoformat(today) - timedelta(days=60)).isoformat()
    decided = savers(st) | set(_list(st, NOT_SAVERS_KEY))
    dismissed = st.dismissed_reviews()
    skipped = st.skipped_reviews()
    for aid, rule in st.account_sync_rules().items():
        if aid in decided or (rule.get("account_subtype") or "").lower() not in SAVINGS_SUBTYPES:
            continue
        arrivals = sorted((t for t in txns if t.account_id == aid and t.amount < 0
                           and t.date[:10] >= since and t.category in ("Transfers", "Saved")),
                          key=lambda t: t.date)
        if not arrivals:
            continue
        key = f"chk:saver:{aid}"
        if key in dismissed:
            continue
        last = arrivals[-1]
        name = rule.get("label") or rule.get("account_name") or "This account"
        out.append({"key": key, "txn": _brief(last), "skipped": key in skipped,
                    "pair": {"question": f"Is {name} where you save?",
                             "evidence": f"You moved {_money(last.amount)} into it on "
                                         f"{date.fromisoformat(last.date[:10]).strftime('%b %-d')}.",
                             "line": "Yes counts money moved there as put away.", "other": ""}})
    from . import income_bills as ib
    state = ib.load(st)
    day = date.fromisoformat(today)
    for p in state.get("pays") or []:
        limit = STALE_DAYS.get(p.get("cadence"))
        if not limit or not p.get("payer"):
            continue
        theirs = sorted((t for t in txns if t.amount < 0 and (t.merchant or t.description) == p["payer"]),
                        key=lambda t: t.date)
        if not theirs:
            continue
        last = theirs[-1]
        quiet = (day - date.fromisoformat(last.date[:10])).days
        checked = p.get("checked_on")
        if quiet <= limit or (checked and (day - date.fromisoformat(checked)).days <= limit):
            continue
        key = f"chk:pay:{p['id']}"
        if key in dismissed:
            continue
        out.append({"key": key, "txn": _brief(last), "skipped": key in skipped,
                    "pair": {"question": f"Still paid by {p.get('name') or p['payer']}?",
                             "evidence": f"Nothing from {p['payer']} since "
                                         f"{date.fromisoformat(last.date[:10]).strftime('%b %-d')}.",
                             "line": "Yes keeps it in your Allowance. No stops expecting it.", "other": ""}})
    return out


def answer(st, key: str, yes: bool, today: str) -> str | None:
    """What she said. Returns the line to show, or None for an unknown key."""
    kind, _, ref = key.partition(":")[2].partition(":")
    if kind == "saver":
        target = SAVERS_KEY if yes else NOT_SAVERS_KEY
        st.set_setting(target, json.dumps(sorted(set(_list(st, target)) | {ref})))
        from .transfers import apply_transfer_matches
        apply_transfer_matches(st)
        return "Money moved there counts as put away." if yes else "Pearl won’t count it as saving."
    if kind == "pay":
        from . import income_bills as ib
        state = ib.load(st)
        pay = next((p for p in state["pays"] if p["id"] == ref), None)
        if pay is None:
            return None
        if yes:
            pay["checked_on"] = today
            line = f"Still expecting {pay.get('name') or pay['payer']}."
        else:
            state["pays"] = [p for p in state["pays"] if p["id"] != ref]
            line = f"{pay.get('name') or pay['payer']} isn’t expected any more."
        ib.save(st, state)
        return line
    return None
