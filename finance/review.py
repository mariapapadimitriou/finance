"""One list of everything Pearl isn't sure about, each with its best guess.

Five kinds, all from the last 60 days (nobody remembers what an e-transfer
from last spring was for):

* unsorted         money that left for somewhere Pearl can't see
                   (grouped by where it went, as the Unsorted card was)
* unsure_category  a category Plaid itself wasn't confident in, or "Other"
* money_in         money that arrived from somewhere Pearl can't see and
                   paired with none of your own transfers: a friend paying
                   you back, a gift, a loan repaid, or your own money
* income_type      income whose type is only a guess (other, or bonus-sized)
* three_pay_month  a month that held a third paycheque

Nothing is decided here; each item says what Pearl would do and why. Acting
on one goes through the ordinary endpoints (category, payback, exclusion,
income type). An item you settle without changing anything is dismissed by
its key and does not come back.
"""

from __future__ import annotations

from datetime import date, timedelta

from .analytics import is_others
from .categorize import is_unsure
from .income import KINDS, cadence, is_income, kind_of
from .models import Transaction
from .transfers import ASK_DAYS, destination, matched_inflows, unsorted

# Where a friend's share most often comes from (doc: prefer these over $40).
SHARED = {"Dining", "Food Delivery", "Alcohol & Bars", "Coffee", "Entertainment",
          "Travel", "Lodging", "Groceries", "Transport"}
LOOKBACK_DAYS = 30


def _brief(t: Transaction) -> dict:
    return {"id": t.fingerprint, "date": t.date, "merchant": t.merchant,
            "description": t.description, "amount": t.amount,
            "account_id": t.account_id, "account_name": t.account_name or "",
            "category": t.category, "logo": (t.raw or {}).get("logo_url") or ""}


def _is_bank(t: Transaction) -> bool:
    return str((t.raw or {}).get("account_type", "")).lower() == "depository"


def unsorted_groups(transactions: list[Transaction]) -> dict:
    rows = unsorted(transactions)
    groups: dict[str, dict] = {}
    for t in rows:
        where = destination(t)
        key = where[0] if where else "row:" + t.fingerprint
        g = groups.setdefault(key, {
            "key": key, "merchant": where[1] if where else t.merchant,
            "learnable": bool(where), "count": 0, "total": 0.0, "first": t.date,
            "last": t.date, "accounts": [], "ids": []})
        g["count"] += 1
        g["total"] = round(g["total"] + t.amount, 2)
        g["first"], g["last"] = min(g["first"], t.date), max(g["last"], t.date)
        if (t.account_name or "") not in g["accounts"]:
            g["accounts"].append(t.account_name or "")
        g["ids"].append(t.fingerprint)
    return {"count": len(rows),
            "total": round(sum(t.amount for t in rows), 2),
            "transfers": [_brief(t) for t in rows],
            "groups": sorted(groups.values(), key=lambda g: -g["total"])}


def charge_candidates(inflow: Transaction, transactions: list[Transaction]) -> list[dict]:
    """The charges this money most likely paid you back for, best first.

    A friend's share is the charge split evenly: $20 back on an $80 dinner is
    one of four. Within $3 or 5% for tips and rounding, in the 30 days before
    the money arrived. Shared kinds of spending over $40 rank first, and a
    charge that other arrivals in the window would finish paying off ranks
    above one they wouldn't.
    """
    got = -inflow.amount
    when = date.fromisoformat(inflow.date[:10])
    arrivals = [t for t in transactions
                if t.amount < 0 and not t.repays and t.fingerprint != inflow.fingerprint
                and abs((date.fromisoformat(t.date[:10]) - when).days) <= LOOKBACK_DAYS]
    out = []
    for c in transactions:
        if c.amount <= 0 or c.excluded or c.repays:
            continue
        if c.category in ("Transfers", "Income", "Saved", "Lent", "Unsorted transfers"):
            continue
        gap = (when - date.fromisoformat(c.date[:10])).days
        if gap < 0 or gap > LOOKBACK_DAYS:
            continue
        left = round(c.amount - (c.paid_back or 0.0), 2)
        if got > left + 0.005:
            continue
        best = None
        for n in range(2, 7):
            share = c.amount / n
            if abs(share - got) <= max(3.0, share * 0.05):
                best = n if best is None or abs(c.amount / n - got) < abs(
                    c.amount / best - got) else best
        if best is None:
            continue
        # Others in the window sending about the same share: the rest of the split.
        peers = sum(1 for a in arrivals if abs(-a.amount - got) <= max(3.0, got * 0.05))
        shared = c.category in SHARED and c.amount >= 40
        score = (0 if shared else 1, 0 if peers >= 1 else 1, gap)
        out.append((score, best, c))
    out.sort(key=lambda r: r[0])
    return [dict(_brief(c), split=n, likely=(s[0] == 0)) for s, n, c in out[:5]]


def build(transactions: list[Transaction], today: str | None = None,
          dismissed: set[str] | None = None) -> dict:
    today_d = date.fromisoformat(today) if today else date.today()
    since = (today_d - timedelta(days=ASK_DAYS)).isoformat()
    dismissed = dismissed or set()
    live = [t for t in transactions if not t.excluded]

    # 1. Unsorted transfers.
    groups = unsorted_groups(live)

    # 2. Categories Pearl isn't sure of.
    unsure = []
    for t in live:
        if t.date[:10] < since or t.amount <= 0 or t.category_source == "user":
            continue
        key = "cat:" + t.fingerprint
        if key in dismissed:
            continue
        if is_unsure(t) or (t.category or "Other") == "Other":
            reason = ("Plaid wasn’t confident about this category." if is_unsure(t)
                      else "Pearl couldn’t tell what this was.")
            unsure.append({"key": key, "txn": _brief(t), "guess": t.category or "Other",
                           "reason": reason})

    # 3. Money in from somewhere Pearl can't see.
    paired = matched_inflows(transactions, today=today_d.isoformat())
    money_in = []
    for t in live:
        if (t.amount >= 0 or t.date[:10] < since or not _is_bank(t) or t.repays
                or t.category not in ("Transfers",) or t.category_source == "user"
                or t.fingerprint in paired or is_others(t)):
            continue
        key = "in:" + t.fingerprint
        if key in dismissed:
            continue
        candidates = charge_candidates(t, transactions)
        if candidates and candidates[0]["likely"]:
            top = candidates[0]
            guess = {"action": "payback", "charge": top}
            reason = (f"About a 1/{top['split']} share of {top['merchant']} "
                      f"(${top['amount']:,.2f}) a few days before.")
        elif candidates:
            guess = {"action": "payback", "charge": candidates[0]}
            reason = "Could be someone paying you back; more than one charge fits."
        else:
            guess = {"action": "own"}
            reason = "It didn’t pair with any of your accounts or charges."
        money_in.append({"key": key, "txn": _brief(t), "guess": guess,
                         "candidates": candidates, "reason": reason})

    # 4. Income whose type is a guess.
    income = []
    for t in live:
        if not is_income(t) or t.date[:10] < since or t.income_type_source == "user":
            continue
        kind = kind_of(t)
        if kind not in ("other", "bonus"):
            continue
        key = "inc:" + t.fingerprint
        if key in dismissed:
            continue
        reason = ("Bigger than your usual paycheque." if kind == "bonus"
                  else "Pearl couldn’t tell what kind of income this is.")
        income.append({"key": key, "txn": _brief(t), "guess": kind,
                       "guess_label": KINDS[kind], "reason": reason})

    # 5. Months with a third paycheque.
    pay = cadence(transactions, today_d.isoformat())
    three = []
    for m in (pay or {}).get("three_pay_months", []):
        key = "pay3:" + m
        if key in dismissed:
            continue
        three.append({"key": key, "month": m, "paycheque": pay["paycheque"],
                      "monthly": pay["monthly"],
                      "reason": "Paid every two weeks, so two months a year hold a "
                                "third paycheque. Your plan uses a typical month: "
                                "one paycheque × 26 ÷ 12."})

    count = (len(groups["groups"]) + len(unsure) + len(money_in) + len(income)
             + len(three))
    return {"count": count, "unsorted": groups, "unsure_category": unsure,
            "money_in": money_in, "income_type": income, "three_pay_month": three,
            "kinds": KINDS}
