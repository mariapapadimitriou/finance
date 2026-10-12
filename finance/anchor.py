"""The Anchor: a cushion for surprises, and when it is likely to be full.

The Anchor is the emergency fund, and the whole of the Build phase: starting
it is the first Build step, filling it the second. It is money already in
savings accounts you choose, so nothing here moves money or stores a balance:
what counts is what those accounts hold, as the bank last reported it.

  * **The suggested amount** is one month of Essentials, from your last three
    full months (fewer when that is all there is), rounded to a figure you can
    recognise. Two or three months, or any amount, is your call.
  * **The first stop** is $500. A small cushion first, because it is the one
    that stops a flat tyre going on a card, and it is reachable.
  * **Full is earned once.** Reaching the target moves you on to Unveil, and a
    later month that dips into the Anchor does not move you back: dipping into
    it is what it is for.

When it will be full is a range, never one date. The pace is what you
actually put away in your last three full months (transfers marked Saved),
and the range runs from your best of those months to your quietest. A month
you mark as unusual — a car repair, a move — is left out, and the next older
month is pulled in, so the pace always rests on three. With nothing put away
lately there is no date at all, because any date would be a promise.
"""

from __future__ import annotations

import math

FIRST_STOP = 500.0
# Months the pace is taken over, and how far back to look for them.
PACE_MONTHS = 3
LOOKBACK = 12
# The cushion sizes offered, in months of Essentials. 0 is "any amount".
SIZES = (1, 2, 3)


def _month_index(month: str) -> int:
    return int(month[:4]) * 12 + int(month[5:7]) - 1


def add_months(month: str, n: int) -> str:
    total = _month_index(month) + n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def full_months(transactions, today: str, lookback: int = LOOKBACK) -> list[str]:
    """Complete months with data before this one, newest first."""
    current = today[:7]
    have = sorted({t.month for t in transactions if t.month < current}, reverse=True)
    return have[:lookback]


def round_to(amount: float, step: float = 50.0) -> float:
    return float(round(amount / step) * step)


def essentials(transactions, today: str, months: int = PACE_MONTHS) -> dict | None:
    """One month of Essentials, from the last few full months.

    Essentials are what you need rather than choose: the categories the
    transactions list groups as Essentials. Your share only, refunds netted.
    """
    from .analytics import share_amount
    from .categorize import group_of, is_spend_category

    chosen = full_months(transactions, today, lookback=months)
    if not chosen:
        return None
    totals = {m: 0.0 for m in chosen}
    for t in transactions:
        if t.month not in totals or t.excluded:
            continue
        category = t.category or "Other"
        if is_spend_category(category) and group_of(category) == "essentials":
            totals[t.month] += share_amount(t)
    rows = [{"month": m, "essentials": round(totals[m], 2)} for m in sorted(chosen)]
    average = sum(r["essentials"] for r in rows) / len(rows)
    if average <= 0:
        return None
    return {"months": rows, "average": round(average, 2),
            "amount": max(round_to(average), 50.0)}


def saved_by_month(transactions, today: str, lookback: int = LOOKBACK) -> list[dict]:
    """What you put away in each recent full month, newest first.

    Money moved to savings (transfers marked Saved, and the saved part of
    anything else), less money taken back out — the same figure the plan
    checks the saving goal against.
    """
    from .analytics import invested_in

    return [{"month": m, "saved": invested_in(transactions, m)}
            for m in full_months(transactions, today, lookback)]


def pace(months: list[dict], unusual: set[str] | None = None,
         n: int = PACE_MONTHS) -> dict | None:
    """The months the pace rests on, and the best, quietest and usual of them.

    `months` is newest first. Months marked unusual are skipped and the next
    older one is used instead, so the pace always rests on `n` months when
    there are that many.
    """
    unusual = unusual or set()
    used = [m for m in months if m["month"] not in unusual][:n]
    if not used:
        return None
    left_out = [m for m in months if m["month"] in unusual]
    values = [m["saved"] for m in used]
    best = max(used, key=lambda m: m["saved"])
    quietest = min(used, key=lambda m: m["saved"])
    return {
        "used": sorted(used, key=lambda m: m["month"]),
        "left_out": sorted(left_out, key=lambda m: m["month"]),
        "best": best,
        "quietest": quietest,
        "usual": round(sum(values) / len(values), 2),
    }


def months_to(to_go: float, monthly: float) -> int | None:
    """Whole months to put `to_go` away at `monthly`, or None if never."""
    if to_go <= 0:
        return 0
    if monthly <= 0:
        return None
    return math.ceil(round(to_go / monthly, 6))


def projection(to_go: float, p: dict | None, today: str, extra: float = 0.0) -> dict:
    """When the Anchor is likely to be full: a range, or honestly no date.

    The range runs from the best month's pace to the quietest's. `extra` is a
    what-if: that much more put aside every month, on top of each.
    """
    now = today[:7]
    if to_go <= 0:
        return {"state": "full"}
    if not p:
        return {"state": "none", "reason": "no_history"}
    best = p["best"]["saved"] + extra
    quiet = p["quietest"]["saved"] + extra
    usual = p["usual"] + extra
    if usual <= 0 or best <= 0:
        return {"state": "none", "reason": "no_pace"}
    soonest = months_to(to_go, best)
    # A quietest month that put nothing away has no date of its own: the
    # range's far end falls back to the usual pace rather than to never.
    latest = months_to(to_go, quiet) if quiet > 0 else months_to(to_go, usual)
    latest = max(latest, soonest)
    return {
        "state": "range",
        "from": add_months(now, soonest),
        "to": add_months(now, latest),
        "low": round(quiet, 2),
        "high": round(best, 2),
        "usual": round(usual, 2),
    }


def status(counted: float, target: float, earned: bool) -> dict:
    """Where the Anchor stands: the first stop, the full target, and the phase.

    `earned` is whether it has ever been full. Once it has, you are in Unveil
    whatever it holds now.
    """
    counted = round(max(counted, 0.0), 2)
    full = target > 0 and counted >= target
    first_stop = min(FIRST_STOP, target) if target > 0 else FIRST_STOP
    return {
        "counted": counted,
        "target": round(target, 2),
        "to_go": round(max(target - counted, 0.0), 2),
        "first_stop": first_stop,
        "first_stop_done": counted >= first_stop,
        "full": full,
        "earned": bool(earned or full),
        "dipped": bool(earned and not full),
        "share": round(min(counted / target, 1.0), 4) if target > 0 else 0.0,
        "first_stop_share": round(min(counted / first_stop, 1.0), 4) if first_stop else 0.0,
    }


def recent_saves(transactions, limit: int = 3) -> list[dict]:
    """The latest money put away: transfers marked Saved, newest first."""
    rows = [t for t in transactions if (t.category or "") == "Saved"
            and not t.excluded and t.amount]
    rows.sort(key=lambda t: t.date, reverse=True)
    return [{"date": t.date, "amount": round(abs(t.amount), 2),
             "saved": t.amount > 0} for t in rows[:limit]]
