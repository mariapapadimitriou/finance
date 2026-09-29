"""Aggregations over the normalized ledger.

Everything here works on plain `Transaction` lists so it can be unit-tested
without a database, and every number is derived from the positive-is-spending
convention established in `models`.

One rule applies throughout: refunds net against spending in the same category,
and transfers/income are excluded from spend totals entirely. Otherwise a
$3,200 credit card payment would show up as your biggest "purchase" of the month.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, timedelta

from .categorize import CATEGORIES, is_discretionary, is_spend_category
from .models import Transaction


def spend_only(transactions: list[Transaction]) -> list[Transaction]:
    """Rows that represent consumption, netting refunds against purchases."""
    return [t for t in transactions if is_spend_category(t.category or "Other")]


def month_range(transactions: list[Transaction]) -> list[str]:
    """Every YYYY-MM between the first and last transaction, gaps included."""
    if not transactions:
        return []
    months = sorted({t.month for t in transactions})
    first, last = months[0], months[-1]
    out, y, m = [], int(first[:4]), int(first[5:7])
    ly, lm = int(last[:4]), int(last[5:7])
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def is_month_complete(transactions: list[Transaction], month: str) -> bool:
    """Does the data actually cover this month to its end?

    An export pulled on the 21st leaves the current month two-thirds full.
    Comparing that against full-month baselines would manufacture a "you're
    spending less!" story every single month, so anything doing comparisons
    needs to know.
    """
    dates = [t.date for t in transactions if t.month == month]
    if not dates:
        return False
    return int(max(dates)[8:10]) >= _days_in_month(month)


def last_complete_month(transactions: list[Transaction]) -> str | None:
    """The most recent month the data covers end to end."""
    months = sorted({t.month for t in transactions})
    if not months:
        return None
    if is_month_complete(transactions, months[-1]):
        return months[-1]
    return months[-2] if len(months) > 1 else None


def monthly_totals(transactions: list[Transaction]) -> list[dict]:
    """Net spend per month, plus the transfers/income excluded from it."""
    spend = defaultdict(float)
    income = defaultdict(float)
    counts = defaultdict(int)

    for t in transactions:
        cat = t.category or "Other"
        if is_spend_category(cat):
            spend[t.month] += t.amount
            if t.amount > 0:
                counts[t.month] += 1
        elif cat == "Income" or t.amount < 0:
            income[t.month] += abs(t.amount)

    return [
        {
            "month": m,
            "spend": round(spend.get(m, 0.0), 2),
            "income": round(income.get(m, 0.0), 2),
            "transactions": counts.get(m, 0),
        }
        for m in month_range(transactions)
    ]


def by_category(transactions: list[Transaction], month: str | None = None) -> list[dict]:
    """Net spend per category, largest first."""
    rows = spend_only(transactions)
    if month:
        rows = [t for t in rows if t.month == month]

    totals = defaultdict(float)
    counts = defaultdict(int)
    for t in rows:
        cat = t.category or "Other"
        totals[cat] += t.amount
        if t.amount > 0:
            counts[cat] += 1

    total_spend = sum(v for v in totals.values() if v > 0) or 1.0
    out = [
        {
            "category": cat,
            "amount": round(amt, 2),
            "transactions": counts[cat],
            "share": round(max(amt, 0) / total_spend, 4),
            "discretionary": is_discretionary(cat),
            "essential": CATEGORIES.get(cat, {}).get("essential", False),
        }
        for cat, amt in totals.items()
    ]
    out.sort(key=lambda r: r["amount"], reverse=True)
    return out


def by_merchant(transactions: list[Transaction], month: str | None = None,
                limit: int = 25) -> list[dict]:
    rows = spend_only(transactions)
    if month:
        rows = [t for t in rows if t.month == month]

    agg: dict[str, dict] = {}
    for t in rows:
        e = agg.setdefault(t.merchant, {
            "merchant": t.merchant, "amount": 0.0, "transactions": 0,
            "category": t.category or "Other", "last_date": t.date, "amounts": [],
        })
        e["amount"] += t.amount
        if t.amount > 0:
            e["transactions"] += 1
            e["amounts"].append(t.amount)
        e["last_date"] = max(e["last_date"], t.date)

    out = []
    for e in agg.values():
        if e["amount"] <= 0:
            continue
        out.append({
            "merchant": e["merchant"],
            "amount": round(e["amount"], 2),
            "transactions": e["transactions"],
            "category": e["category"],
            "last_date": e["last_date"],
            "avg": round(e["amount"] / e["transactions"], 2) if e["transactions"] else 0.0,
        })
    out.sort(key=lambda r: r["amount"], reverse=True)
    return out[:limit]


def by_account(transactions: list[Transaction], month: str | None = None) -> list[dict]:
    rows = spend_only(transactions)
    if month:
        rows = [t for t in rows if t.month == month]

    agg: dict[str, dict] = {}
    for t in rows:
        e = agg.setdefault(t.account_id, {
            "account_id": t.account_id,
            "account_name": t.account_name or t.account_id,
            "amount": 0.0, "transactions": 0,
        })
        e["amount"] += t.amount
        if t.amount > 0:
            e["transactions"] += 1

    out = [{**e, "amount": round(e["amount"], 2)} for e in agg.values()]
    out.sort(key=lambda r: r["amount"], reverse=True)
    return out


def category_baselines(transactions: list[Transaction], exclude_month: str | None = None
                       ) -> dict[str, dict]:
    """Your own typical monthly spend per category — the yardstick for "high".

    Uses the median of complete months rather than the mean so one blowout
    holiday month doesn't quietly raise the bar it's being judged against.
    """
    per_month: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for t in spend_only(transactions):
        per_month[t.month][t.category or "Other"] += t.amount

    months = sorted(per_month)
    if exclude_month:
        months = [m for m in months if m != exclude_month]
    if not months:
        return {}

    all_cats = {c for m in months for c in per_month[m]}
    out = {}
    for cat in all_cats:
        series = [round(per_month[m].get(cat, 0.0), 2) for m in months]
        if not series:
            continue
        out[cat] = {
            "median": round(statistics.median(series), 2),
            "mean": round(statistics.fmean(series), 2),
            "max": round(max(series), 2),
            "months": len(series),
            "series": series,
        }
    return out


def month_over_month(transactions: list[Transaction], month: str) -> list[dict]:
    """Per-category change for `month` against your trailing median."""
    current = {r["category"]: r["amount"] for r in by_category(transactions, month)}
    baselines = category_baselines(transactions, exclude_month=month)

    out = []
    for cat in set(current) | set(baselines):
        now = current.get(cat, 0.0)
        base = baselines.get(cat, {}).get("median", 0.0)
        delta = round(now - base, 2)
        pct = round(delta / base, 4) if base > 0 else None
        out.append({
            "category": cat,
            "amount": round(now, 2),
            "baseline": base,
            "delta": delta,
            "pct": pct,
            "months_of_history": baselines.get(cat, {}).get("months", 0),
        })
    out.sort(key=lambda r: r["delta"], reverse=True)
    return out


def daily_series(transactions: list[Transaction], days: int = 90) -> list[dict]:
    """Daily spend for the trailing window, zero-filled."""
    rows = spend_only(transactions)
    if not rows:
        return []

    end = date.fromisoformat(max(t.date for t in rows))
    start = end - timedelta(days=days - 1)

    totals = defaultdict(float)
    for t in rows:
        d = date.fromisoformat(t.date)
        if start <= d <= end:
            totals[t.date] += t.amount

    out, cur = [], start
    while cur <= end:
        iso = cur.isoformat()
        out.append({"date": iso, "amount": round(totals.get(iso, 0.0), 2)})
        cur += timedelta(days=1)
    return out


def weekday_profile(transactions: list[Transaction]) -> list[dict]:
    """Average spend by day of week — where the discretionary bulges sit."""
    rows = [t for t in spend_only(transactions) if t.amount > 0]
    if not rows:
        return []

    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    totals = defaultdict(float)
    day_counts: dict[int, set] = defaultdict(set)

    for t in rows:
        d = date.fromisoformat(t.date)
        totals[d.weekday()] += t.amount
        day_counts[d.weekday()].add(t.date)

    return [
        {
            "day": names[i],
            "total": round(totals.get(i, 0.0), 2),
            "average": round(totals.get(i, 0.0) / max(len(day_counts.get(i, set())), 1), 2),
        }
        for i in range(7)
    ]


def fixed_vs_discretionary(transactions: list[Transaction], month: str | None = None) -> dict:
    rows = by_category(transactions, month)
    disc = sum(r["amount"] for r in rows if r["discretionary"] and r["amount"] > 0)
    fixed = sum(r["amount"] for r in rows if not r["discretionary"] and r["amount"] > 0)
    total = disc + fixed
    return {
        "discretionary": round(disc, 2),
        "fixed": round(fixed, 2),
        "total": round(total, 2),
        "discretionary_share": round(disc / total, 4) if total else 0.0,
    }


def summary(transactions: list[Transaction], budgets: dict[str, float] | None = None) -> dict:
    """The overview payload: headline numbers plus every breakdown the UI draws."""
    if not transactions:
        return {
            "empty": True, "months": [], "categories": [], "merchants": [],
            "accounts": [], "monthly": [], "latest_month": None,
        }

    months = month_range(transactions)
    latest = months[-1] if months else None
    monthly = monthly_totals(transactions)

    complete = [m for m in monthly if m["month"] != latest]
    avg_spend = round(statistics.fmean([m["spend"] for m in complete]), 2) if complete else (
        monthly[-1]["spend"] if monthly else 0.0
    )

    latest_spend = next((m["spend"] for m in monthly if m["month"] == latest), 0.0)
    spend_rows = [t for t in spend_only(transactions) if t.amount > 0]

    return {
        "empty": False,
        "months": months,
        "latest_month": latest,
        "latest_month_complete": is_month_complete(transactions, latest) if latest else False,
        "last_complete_month": last_complete_month(transactions),
        "monthly": monthly,
        "latest_spend": latest_spend,
        "average_monthly_spend": avg_spend,
        "vs_average": round(latest_spend - avg_spend, 2),
        "total_spend": round(sum(t.amount for t in spend_only(transactions)), 2),
        "transaction_count": len(transactions),
        "date_range": [min(t.date for t in transactions), max(t.date for t in transactions)],
        "average_transaction": round(
            statistics.fmean([t.amount for t in spend_rows]), 2) if spend_rows else 0.0,
        "categories": by_category(transactions, latest),
        "categories_all_time": by_category(transactions),
        "merchants": by_merchant(transactions, latest, limit=12),
        "merchants_all_time": by_merchant(transactions, limit=12),
        "accounts": by_account(transactions),
        "changes": month_over_month(transactions, latest) if latest else [],
        "daily": daily_series(transactions, 90),
        "weekday": weekday_profile(transactions),
        "split": fixed_vs_discretionary(transactions, latest),
        "budgets": budget_status(transactions, budgets or {}, latest),
    }


def budget_status(transactions: list[Transaction], budgets: dict[str, float],
                  month: str | None = None) -> list[dict]:
    """Actual vs. budget per category, with a pace projection for the live month."""
    if not budgets:
        return []

    actuals = {r["category"]: r["amount"] for r in by_category(transactions, month)}

    # Project the current month forward: 40% through the month and already at
    # 60% of budget is worth knowing before the month ends, not after.
    pace = 1.0
    if month:
        days_in = _days_elapsed(transactions, month)
        total_days = _days_in_month(month)
        if days_in and total_days:
            pace = total_days / days_in

    out = []
    for cat, limit in sorted(budgets.items()):
        spent = round(actuals.get(cat, 0.0), 2)
        projected = round(spent * pace, 2)
        out.append({
            "category": cat,
            "budget": round(float(limit), 2),
            "spent": spent,
            "remaining": round(limit - spent, 2),
            "used": round(spent / limit, 4) if limit else 0.0,
            "projected": projected,
            "projected_over": round(projected - limit, 2),
            "on_track": projected <= limit,
        })
    out.sort(key=lambda r: r["used"], reverse=True)
    return out


def _days_in_month(month: str) -> int:
    import calendar
    y, m = int(month[:4]), int(month[5:7])
    return calendar.monthrange(y, m)[1]


def _days_elapsed(transactions: list[Transaction], month: str) -> int:
    """How far into `month` the data actually goes."""
    dates = [t.date for t in transactions if t.month == month]
    if not dates:
        return 0
    return int(max(dates)[8:10])
