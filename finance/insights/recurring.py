"""Detect recurring charges: subscriptions, memberships, bills.

The signal is regularity, not the word "subscription" in a descriptor. For each
merchant we look at the gaps between charges and ask whether they cluster around
a known billing cadence. Amount is allowed to drift a little -- utilities vary
month to month, and subscription prices get raised -- but a merchant whose
amounts are all over the map is shopping, not a subscription.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, timedelta

from ..models import Transaction

# Known cadences: (label, expected days, tolerance, charges per year)
CADENCES = [
    ("weekly", 7, 2, 52),
    ("biweekly", 14, 3, 26),
    ("monthly", 30.4, 6, 12),
    ("quarterly", 91.3, 12, 4),
    ("semiannual", 182.6, 20, 2),
    ("annual", 365.25, 35, 1),
]

MIN_OCCURRENCES = 3          # two points make a line, three make a pattern
AMOUNT_TOLERANCE = 0.18      # how much a "same" charge may drift, proportionally
MAX_INTERVAL_CV = 0.35       # coefficient of variation above which it's not regular


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def _match_cadence(median_gap: float):
    for label, expected, tol, per_year in CADENCES:
        if abs(median_gap - expected) <= tol:
            return label, expected, per_year
    return None


def _level_ratio(amounts: list[float]) -> float:
    """Share of charges sitting close to the median of the set."""
    med = statistics.median(amounts)
    if med <= 0:
        return 0.0
    return sum(1 for a in amounts if abs(a - med) / med <= AMOUNT_TOLERANCE) / len(amounts)


def _amounts_consistent(amounts: list[float]) -> bool:
    """True when the charges look like the same recurring line item.

    Two shapes qualify. The simple one is a single stable level. The second is a
    step: a subscription that was $15.49 for seven months and $22.99 after that
    is still one subscription, and detecting exactly that case is the point of
    price-creep analysis -- so a series that splits cleanly into two stable
    levels counts as consistent rather than being thrown away as erratic.
    """
    if len(amounts) < 2:
        return False
    if _level_ratio(amounts) >= 0.6:
        return True

    for k in range(2, len(amounts) - 1):
        before, after = amounts[:k], amounts[k:]
        if _level_ratio(before) >= 0.8 and _level_ratio(after) >= 0.8:
            return True
    return False


def detect_recurring(transactions: list[Transaction],
                     as_of: str | None = None) -> list[dict]:
    """Return one record per detected recurring charge, priciest first."""
    by_merchant: dict[str, list[Transaction]] = defaultdict(list)
    for t in transactions:
        # Fees and interest recur too, but they are not subscriptions and the
        # fees rule already reports them with far better framing.
        if t.amount > 0 and t.category not in {"Transfers", "Income", "Fees & Interest"}:
            by_merchant[t.merchant].append(t)

    today = date.fromisoformat(as_of) if as_of else (
        max((date.fromisoformat(t.date) for t in transactions), default=date.today())
    )

    found = []
    for merchant, rows in by_merchant.items():
        rec = _analyze_merchant(merchant, rows, today)
        if rec:
            found.append(rec)

    found.sort(key=lambda r: r["annual_cost"], reverse=True)
    return found


def _analyze_merchant(merchant: str, rows: list[Transaction], today: date) -> dict | None:
    rows = sorted(rows, key=lambda t: t.date)
    if len(rows) < MIN_OCCURRENCES:
        return None

    # Try the merchant's charges as a single series first: a subscription whose
    # price changed is one line item, and amount clustering would split it in
    # two. Only if the whole series isn't regular do we look for a recurring
    # band inside a merchant that also has one-off purchases (Amazon Prime
    # sitting among Amazon orders).
    for cluster in [rows, *_amount_clusters(rows)]:
        if len(cluster) < MIN_OCCURRENCES:
            continue

        # Guard against coincidence: three evenly spaced charges out of a
        # merchant's thirty is a pharmacy run that happened to look regular,
        # not a subscription. Either the cluster dominates the merchant's
        # activity, or there are enough occurrences to stand on their own.
        if len(cluster) / len(rows) < 0.5 and len(cluster) < 6:
            continue

        dates = [t.date for t in cluster]
        gaps = [_days(dates[i], dates[i + 1]) for i in range(len(dates) - 1)]
        gaps = [g for g in gaps if g > 0]
        if len(gaps) < MIN_OCCURRENCES - 1:
            continue

        median_gap = statistics.median(gaps)
        match = _match_cadence(median_gap)
        if not match:
            continue

        cadence, expected, per_year = match
        cv = (statistics.pstdev(gaps) / median_gap) if median_gap else 1.0
        if cv > MAX_INTERVAL_CV:
            continue

        amounts = [t.amount for t in cluster]
        if not _amounts_consistent(amounts):
            continue

        latest_amount = amounts[-1]
        typical = round(statistics.median(amounts), 2)
        annual = round(latest_amount * per_year, 2)

        last_date = date.fromisoformat(dates[-1])
        next_expected = last_date + timedelta(days=round(expected))
        days_since = (today - last_date).days

        # A subscription that missed its window by a wide margin has probably
        # been cancelled; keep it, but say so rather than counting it as live.
        active = days_since <= expected * 1.6

        price_change = _price_change(cluster)

        yield_rec = {
            "merchant": merchant,
            "category": cluster[-1].category or "Other",
            "account_name": cluster[-1].account_name or cluster[-1].account_id,
            "cadence": cadence,
            "charges_per_year": per_year,
            "occurrences": len(cluster),
            "amount": round(latest_amount, 2),
            "typical_amount": typical,
            "annual_cost": annual,
            "monthly_cost": round(annual / 12, 2),
            "first_seen": dates[0],
            "last_seen": dates[-1],
            "next_expected": next_expected.isoformat(),
            "days_since_last": days_since,
            "active": active,
            "confidence": round(_confidence(len(cluster), cv, amounts), 2),
            "interval_days": round(median_gap, 1),
            "price_change": price_change,
            "total_paid": round(sum(amounts), 2),
            "dates": dates,
        }
        return yield_rec

    return None


def _amount_clusters(rows: list[Transaction]) -> list[list[Transaction]]:
    """Group a merchant's charges into bands of similar amount.

    Sorted by amount, then split wherever the jump to the next charge exceeds
    the tolerance. Each resulting band is a candidate recurring line item.
    """
    by_amount = sorted(rows, key=lambda t: t.amount)
    clusters: list[list[Transaction]] = []
    current: list[Transaction] = []

    for t in by_amount:
        if not current:
            current = [t]
            continue
        ref = statistics.median([x.amount for x in current])
        if ref > 0 and abs(t.amount - ref) / ref <= AMOUNT_TOLERANCE:
            current.append(t)
        else:
            clusters.append(current)
            current = [t]
    if current:
        clusters.append(current)

    # Test the biggest, most expensive bands first.
    clusters.sort(key=lambda c: (len(c), statistics.median([t.amount for t in c])),
                  reverse=True)
    return [sorted(c, key=lambda t: t.date) for c in clusters]


def _confidence(n: int, cv: float, amounts: list[float]) -> float:
    """0-1 score: more occurrences and tighter intervals mean more certainty."""
    count_score = min(n / 6.0, 1.0)
    interval_score = max(0.0, 1.0 - cv / MAX_INTERVAL_CV)
    med = statistics.median(amounts) or 1.0
    spread = statistics.pstdev(amounts) / med if len(amounts) > 1 else 0.0
    amount_score = max(0.0, 1.0 - spread / AMOUNT_TOLERANCE)
    return max(0.0, min(1.0, 0.4 * count_score + 0.35 * interval_score + 0.25 * amount_score))


def _price_change(cluster: list[Transaction]) -> dict | None:
    """Detect a subscription whose price went up, and by how much per year."""
    if len(cluster) < 4:
        return None

    amounts = [t.amount for t in cluster]
    half = len(amounts) // 2
    early = statistics.median(amounts[:half])
    late = statistics.median(amounts[half:])
    if early <= 0:
        return None

    delta = late - early
    if abs(delta) / early < 0.04:   # under 4% is noise, not a repricing
        return None

    return {
        "from": round(early, 2),
        "to": round(late, 2),
        "delta": round(delta, 2),
        "pct": round(delta / early, 4),
        "direction": "increase" if delta > 0 else "decrease",
    }


def recurring_summary(recurring: list[dict]) -> dict:
    active = [r for r in recurring if r["active"]]
    return {
        "count": len(active),
        "inactive_count": len(recurring) - len(active),
        "monthly_total": round(sum(r["monthly_cost"] for r in active), 2),
        "annual_total": round(sum(r["annual_cost"] for r in active), 2),
    }
