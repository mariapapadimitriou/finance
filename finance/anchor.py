"""The Anchor: the cash savings she already has, and when it will cover three
months of Essentials (THL-229, THL-230, 2026-10-14).

The Anchor is not a goal she sets. It is the cash savings accounts she picks,
added up, less what her treasure chests hold: money for big surprises, like
a car repair or a vet bill. Nothing here moves money or stores a balance;
what counts is what those accounts hold, as the bank last reported it, and
what the chests have taken from it.

  * **The milestone** is three months of her usual Essentials: the average
    of her last three full months (unusual months left out, fewer months when
    that is all there is), rounded to a figure she can recognise, times
    three. A benchmark, not a goal; she can't change it.
  * **Reached stays reached.** Once the Anchor covers three months, a later
    month that dips into it does not undo that: dipping into it is what it
    is for. Pearl says so, and nudges her to top it up.
  * **Chests fill from the Anchor.** Each chest's monthly amount moves out of
    the Anchor's value on the 1st (an earmark; Pearl never moves money), so
    the Anchor grows by what she puts away less what the chests take.

When it will get there is a range, never one date. The pace is what the
Anchor actually grew by in her last three full months — transfers marked
Saved, less what the chests took — and the range runs from her best of
those months to her quietest. A month she marks as unusual is left out and
the next older month pulled in, so the pace always rests on three. With
nothing put away lately there is no date at all, because any date would be
a promise.
"""

from __future__ import annotations

import math

# How many months of Essentials the Anchor should cover.
MONTHS_OF_ESSENTIALS = 3
# Months the pace is taken over, and how far back to look for them.
PACE_MONTHS = 3
LOOKBACK = 12


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


def essentials(transactions, today: str, months: int = PACE_MONTHS,
               unusual: set[str] | None = None) -> dict | None:
    """A usual month of Essentials, from the last few full months.

    Essentials are what you need rather than choose: the categories the
    transactions list groups as Essentials. Your share only, refunds netted.
    Months marked unusual are left out and the next older one is pulled in.
    """
    from .analytics import share_amount
    from .categorize import group_of, is_spend_category

    unusual = unusual or set()
    chosen = [m for m in full_months(transactions, today) if m not in unusual][:months]
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
    usual = max(round_to(average), 50.0)
    return {"months": rows, "average": round(average, 2), "amount": usual,
            "target": round(usual * MONTHS_OF_ESSENTIALS, 2)}


def saved_by_month(transactions, today: str, lookback: int = LOOKBACK,
                   chests_by_month=None) -> list[dict]:
    """What the Anchor grew by in each recent full month, newest first.

    Money moved to savings (transfers marked Saved, and the saved part of
    anything else), less money taken back out, less what the chests took
    from the Anchor that month (`chests_by_month(month)`, in dollars).
    """
    from .analytics import invested_in

    out = []
    for m in full_months(transactions, today, lookback):
        put_away = invested_in(transactions, m)
        chests = round(float(chests_by_month(m)), 2) if chests_by_month else 0.0
        out.append({"month": m, "put_away": round(put_away, 2), "chests": chests,
                    "saved": round(put_away - chests, 2)})
    return out


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
    """When the Anchor is likely to cover three months: a range, or honestly
    no date.

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


def status(savings: float, chests: float, usual: float | None, earned: bool) -> dict:
    """Where the Anchor stands: what it is, how many months of Essentials it
    covers, and whether it has reached three.

    `savings` is what the picked accounts hold, `chests` what the treasure
    chests hold, `usual` a usual month of Essentials (None before there is
    one). `earned` is whether it has ever covered three months; once it
    has, that stays true whatever it holds now.
    """
    savings = round(max(savings, 0.0), 2)
    chests = round(max(chests, 0.0), 2)
    counted = round(max(savings - chests, 0.0), 2)
    target = round((usual or 0.0) * MONTHS_OF_ESSENTIALS, 2)
    months = round(counted / usual, 1) if usual else None
    full = target > 0 and counted >= target - 0.005
    return {
        "savings": savings,
        "chests": chests,
        "counted": counted,
        "usual": round(usual, 2) if usual else None,
        "months_of_essentials": MONTHS_OF_ESSENTIALS,
        "months": months,
        "target": target,
        "to_go": round(max(target - counted, 0.0), 2),
        "full": full,
        "earned": bool(earned or full),
        "dipped": bool(earned and not full),
        "share": round(min(counted / target, 1.0), 4) if target > 0 else 0.0,
    }


def recent_saves(transactions, limit: int = 3) -> list[dict]:
    """The latest money put away: transfers marked Saved, newest first."""
    rows = [t for t in transactions if (t.category or "") == "Saved"
            and not t.excluded and t.amount]
    rows.sort(key=lambda t: t.date, reverse=True)
    return [{"date": t.date, "amount": round(abs(t.amount), 2),
             "saved": t.amount > 0} for t in rows[:limit]]
