"""What your accounts hold, and what they held on any day.

Plaid reports each account's balance with every sync. That is today's figure
only, but the transactions say how it got there, so the balance on an earlier
day is today's with everything since undone:

* a bank account: today's balance + money out since − money in since;
* a credit card, which reports what is owed: owed today − charges since +
  payments since.

That only works for an account whose transactions are tracked; for one that
isn't, the daily readings kept from each sync are used where they exist.

The change in what your accounts hold over a month is the bank's own answer to
"income minus spending" — a check on the figure Spendie works out from the
transactions, and a pointer to money moving through accounts it can't see.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

# Which way a balance counts: what a bank account holds is yours, what a card
# reports is owed. Loans and investments are left out of the everyday
# position: a mortgage balance would swamp it, and markets move investments
# by amounts that have nothing to do with spending.
_SIGN = {"depository": 1, "credit": -1}


def sign_of(account_type: str) -> int | None:
    return _SIGN.get((account_type or "").lower())


def balance_on(current: float, account_type: str, day: str, as_of: str,
               transactions) -> float:
    """What the account held at the end of `day`, from today's `current`."""
    delta = sum(t.amount for t in transactions if day < t.date[:10] <= as_of)
    if (account_type or "").lower() == "credit":
        return round(current - delta, 2)
    return round(current + delta, 2)


def position(balances: dict, rules: dict, joint: dict) -> dict:
    """Today's everyday position: cash in bank accounts, owed on cards, and
    joint accounts shown apart (their money isn't all yours)."""
    cash = owed = 0.0
    shared = []
    as_of = ""
    for aid, b in balances.items():
        if b.get("current") is None:
            continue
        kind = (rules.get(aid) or {}).get("account_type", "")
        sign = sign_of(kind)
        if sign is None:
            continue
        as_of = max(as_of, b.get("as_of") or "")
        if aid in joint:
            shared.append({"label": joint[aid], "current": b["current"],
                           "name": (rules.get(aid) or {}).get("account_name", "")})
            continue
        if sign > 0:
            cash += b["current"]
        else:
            owed += b["current"]
    if not as_of:
        return None
    return {"cash": round(cash, 2), "owed": round(owed, 2),
            "net": round(cash - owed, 2), "joint": shared, "as_of": as_of}


def monthly_growth(months: list[str], balances: dict, rules: dict, joint: dict,
                   transactions, snapshots: dict | None = None) -> dict | None:
    """How much your everyday position grew in each of `months`.

    Counts the bank accounts and cards whose transactions are tracked (so the
    balance can be wound back), and not joint ones. Returns {month: growth}
    and how many accounts went in, or None when none can be.
    """
    by_account = defaultdict(list)
    for t in transactions:
        by_account[t.account_id].append(t)
    usable = []
    for aid, b in balances.items():
        rule = rules.get(aid) or {}
        if (b.get("current") is None or aid in joint
                or sign_of(rule.get("account_type", "")) is None
                or not rule.get("enabled", False)):
            continue
        usable.append(aid)
    if not usable or not months:
        return None

    def net(day: str) -> float:
        total = 0.0
        for aid in usable:
            b, kind = balances[aid], rules[aid]["account_type"]
            value = balance_on(b["current"], kind, day, b["as_of"] or day,
                               by_account[aid])
            total += sign_of(kind) * value
        return total

    out = {}
    for month in months:
        y, m = int(month[:4]), int(month[5:7])
        first = date(y, m, 1)
        last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
        start = (first - timedelta(days=1)).isoformat()
        out[month] = round(net(last.isoformat()) - net(start), 2)
    return {"months": out, "accounts": len(usable)}
