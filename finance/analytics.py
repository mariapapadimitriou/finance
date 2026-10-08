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
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date, timedelta

from .categorize import CATEGORIES, is_discretionary, is_spend_category
from .models import Transaction


def share_amount(t: Transaction) -> float:
    """What a charge cost you: your share of it when friends paid you back
    for the rest, otherwise the whole charge.

    A share you typed wins. Otherwise whatever friends sent back and you
    linked to the charge comes off it: an $80 dinner with three $20
    e-transfers linked cost you $20.
    """
    if t.my_share is not None:
        base = t.my_share
    elif t.paid_back:
        base = round(max(t.amount - t.paid_back, 0.0), 2)
    else:
        base = t.amount
    if t.invested:
        # The part that was put away was saved, not spent.
        return round(max(base - t.invested, 0.0), 2)
    return base


def is_others(t: Transaction) -> bool:
    """A row on a joint account that isn't yours: another member's money,
    in or out. Not your spending, your income, or money you received."""
    return bool(t.joint) and abs(t.my_share or 0.0) < 0.005


def spend_amount(t: Transaction) -> float:
    """How much of this charge the month it fell in has to pay for.

    Usually all of it. A charge allocated to a piggy bank is paid by the bank
    instead, out of contributions collected over the preceding months — but only
    up to what the bank actually held, so a $2,000 flight against a bank holding
    $400 leaves $1,600 for the month. The split is the whole point: the money
    budgeted in advance is not charged twice, and the money that was not
    budgeted is not hidden.

    Only your share counts at all: when friends paid you back for part of a
    charge, the part they paid was never yours to budget for.
    """
    return round(share_amount(t) - (t.bank_amount or 0.0), 2)


def counts_as_spending(t: Transaction) -> bool:
    """Does any of this charge belong to the month it fell in?

    Two ways it can fail to. A transfer or a card payment is not consumption at
    all — money moving between your own accounts is not a purchase. And a charge
    a piggy bank covered in full was budgeted somewhere else: the holiday was
    paid for over twelve months, so counting it against June as well would
    charge for it twice and make a month that went exactly to plan read as a
    disaster.

    This is the single gate for that question. Everything that reports spending
    passes through it, so a charge cannot be excluded from the Overview and
    still counted on the Budgets tab.
    """
    if not is_spend_category(t.category or "Other"):
        return False
    # A partly covered charge still counts, for the part nobody budgeted. A
    # charge friends paid back in full counts for nothing at all.
    if (t.bank_id is None and t.my_share is None and not t.invested
            and not t.paid_back):
        return True
    return abs(spend_amount(t)) >= 0.005


def spend_only(transactions: list[Transaction]) -> list[Transaction]:
    """Rows that represent consumption, netting refunds against purchases.

    What comes back carries the amount its own month pays, not the amount on
    the statement, so every total computed downstream nets off whatever a piggy
    bank covered without having to know that piggy banks exist. The originals
    are untouched — the Transactions tab still shows what was charged.
    """
    out = []
    for t in transactions:
        if not counts_as_spending(t):
            continue
        adjusted = (t.bank_id is not None or t.my_share is not None
                    or bool(t.invested) or bool(t.paid_back))
        out.append(replace(t, amount=spend_amount(t)) if adjusted else t)
    return out


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


def is_month_complete(transactions: list[Transaction], month: str,
                      today: str | None = None) -> bool:
    """Does the data actually cover this month to its end?

    An export pulled on the 21st leaves the current month two-thirds full.
    Comparing that against full-month baselines would manufacture a "you're
    spending less!" story every month, so anything doing comparisons needs
    to know.

    Reaching the final day is sufficient but not necessary. A quiet last
    weekend is not missing data, and requiring a charge dated the 31st called
    a finished month incomplete whenever someone happened to buy nothing —
    which, with a few cards and a spending plan, is the goal. So a month is
    also complete once the ledger holds anything dated after it: that is
    proof the data runs past the month's end, whatever happened inside it.
    """
    dates = [t.date for t in transactions if t.month == month]
    if not dates:
        return False
    if int(max(dates)[8:10]) >= _days_in_month(month):
        return True
    return any(t.month > month for t in transactions)


def is_month_running(month: str, today: str | None = None) -> bool:
    """Is this month the one happening now?

    Distinct from completeness, and conflating the two is how a finished
    September came to be described as "still in progress" in October. Only
    the current month can still be in progress; a past month with a quiet
    last week is a different situation and reads differently.
    """
    from datetime import date as _date
    now = today or _date.today().isoformat()
    return month == now[:7]


def last_complete_month(transactions: list[Transaction]) -> str | None:
    """The most recent month the data covers end to end."""
    months = sorted({t.month for t in transactions})
    if not months:
        return None
    if is_month_complete(transactions, months[-1]):
        return months[-1]
    return months[-2] if len(months) > 1 else None


def monthly_totals(transactions: list[Transaction]) -> list[dict]:
    """Net spend per month, and the money that arrived alongside it.

    Income and inflows are kept apart, because they are not the same thing
    and conflating them was wrong in a way that flattered the numbers. Every
    negative amount used to count as income, which made a $2,600 card payment
    read as a $2,600 salary — projecting savings out of your own debt
    repayment. Only the Income category is income; everything else arriving
    is an inflow, which is worth reporting and is not earnings.
    """
    spend = defaultdict(float)
    income = defaultdict(float)
    inflows = defaultdict(float)
    counts = defaultdict(int)

    for t in transactions:
        cat = t.category or "Other"
        if counts_as_spending(t):
            spend[t.month] += spend_amount(t)
            if t.amount > 0:
                counts[t.month] += 1
        elif is_others(t):
            continue                      # another member's, on a joint account
        elif cat == "Income" and t.amount < 0:
            income[t.month] += abs(t.amount)
        elif t.amount < 0 and not t.repays:
            # A friend paying you back is not money in: it came off the
            # charge it was for.
            inflows[t.month] += abs(t.amount)

    return [
        {
            "month": m,
            "spend": round(spend.get(m, 0.0), 2),
            "income": round(income.get(m, 0.0), 2),
            "inflows": round(inflows.get(m, 0.0), 2),
            "transactions": counts.get(m, 0),
        }
        for m in month_range(transactions)
    ]


def ledger_currency(transactions: list[Transaction]) -> str:
    """What this ledger is denominated in.

    Every amount is stored in the currency the card was billed in, which the
    importers record and nothing afterwards changes. The figure on screen was
    nevertheless formatted as US dollars, hard-coded, so a Canadian ledger
    read as American — the data was right the whole time and the label was
    wrong on every page of the app.

    The dominant currency, because the alternative is threading a currency
    through every total, and a total that mixes two currencies is wrong in a
    way no label can rescue. A mixed ledger is reported as mixed instead.
    """
    counts = Counter((t.currency or "").upper() for t in transactions if t.currency)
    return counts.most_common(1)[0][0] if counts else ""


def currency_mix(transactions: list[Transaction]) -> list[dict]:
    """Every currency present, commonest first."""
    counts = Counter((t.currency or "").upper() for t in transactions if t.currency)
    return [{"currency": c, "transactions": n} for c, n in counts.most_common()]


def typical_month_spend(transactions: list[Transaction],
                        exclude: set[str] | None = None) -> float:
    """What a normal month costs, by the one definition the app uses.

    There were two. The Overview quoted a mean over complete months; the
    Projections tab quoted a median including the latest, possibly partial,
    one — and the two disagreed by half on the same ledger while both being
    labelled the typical month. Either is defensible; having both is not.

    Median, because one holiday should not redefine normal, and complete
    months only, because a month four days in is not a cheap month.
    """
    if exclude:
        # Used by the projection, which compares this against a leftover that
        # has already had those categories taken out as commitments.
        transactions = [t for t in transactions
                        if (t.category or "Other") not in exclude]
    monthly = monthly_totals(transactions)
    months = month_range(transactions)
    latest = months[-1] if months else None

    observed = [m for m in monthly if m["transactions"] > 0]
    complete = [m for m in observed if m["month"] != latest]
    rows = complete or observed
    if not rows:
        return 0.0
    return round(statistics.median([m["spend"] for m in rows]), 2)


def invested_in(transactions: list[Transaction], month: str) -> float:
    """What was put away in a month.

    A transaction categorised Saved counts in full (money taken back out, as
    a negative, reduces it). Any other transaction counts the part marked as
    saved. A row is never counted both ways.
    """
    total = 0.0
    for t in transactions:
        if t.month != month:
            continue
        if (t.category or "") == "Saved":
            total += t.amount
        elif t.invested:
            total += t.invested
    return round(total, 2)


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
    """Spending per card, and how many rows that card holds.

    The two figures are counted over different sets on purpose, and the
    column names have to say so. `amount` is spending, so transfers are
    excluded; `transactions` is every row on the card, because that is what
    the Accounts tab counts and what removing the card would delete. Counting
    only the spend rows here put 199 under one heading and 207 under the
    same heading elsewhere.
    """
    scope = [t for t in transactions if not month or t.month == month]
    spending = {id(t) for t in spend_only(scope)}

    agg: dict[str, dict] = {}
    for t in scope:
        e = agg.setdefault(t.account_id, {
            "account_id": t.account_id,
            "account_name": t.account_name or t.account_id,
            "amount": 0.0, "transactions": 0,
        })
        e["transactions"] += 1
        if id(t) in spending:
            e["amount"] += t.amount

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


def month_pace(transactions: list[Transaction], month: str,
               today: date | None = None, compare: int = 3,
               exclude: set[str] | frozenset = frozenset()) -> dict:
    """This month's spending as a running total, beside a usual month's.

    Day by day, what has been spent so far — through today for the month
    under way — and, under it, the average running total of the `compare`
    months before it that have spending in them, by day of the month. The
    same gate as every other total, so the last point is the month's spend.
    """
    import calendar

    today = today or date.today()
    # `exclude` takes out the bills a plan already set aside — the mortgage
    # is not this month's spending to watch — from this month and the months
    # it is compared with alike.
    rows = [t for t in spend_only(transactions)
            if (t.category or "Other") not in exclude]
    year, mon = int(month[:4]), int(month[5:7])
    days = calendar.monthrange(year, mon)[1]
    through = today.day if month == today.isoformat()[:7] else days

    def running(m: str, length: int) -> list[float]:
        by_day: dict[int, float] = defaultdict(float)
        for t in rows:
            if t.month == m:
                by_day[int(t.date[8:10])] += t.amount
        out, total = [], 0.0
        for d in range(1, length + 1):
            total += by_day.get(d, 0.0)
            out.append(round(total, 2))
        return out

    this = running(month, through)
    earlier = sorted({t.month for t in rows if t.month < month})[-compare:]
    curves = []
    for m in earlier:
        y, mo = int(m[:4]), int(m[5:7])
        curve = running(m, calendar.monthrange(y, mo)[1])
        # A shorter month holds its last total for the days it doesn't have.
        curves.append([curve[min(d, len(curve)) - 1] for d in range(1, days + 1)])
    average = ([round(sum(c[d] for c in curves) / len(curves), 2) for d in range(days)]
               if curves else [])
    return {
        "month": month,
        "days": days,
        "through": through,
        "this": this,
        "total": this[-1] if this else 0.0,
        "average": average,
        "average_total": average[-1] if average else None,
        "compared": earlier,
    }


def bill_categories(fixed) -> set[str]:
    """The categories a plan's fixed costs are paid under: its bills.

    "Other" is left out — a fixed cost nobody categorised would otherwise
    take every uncategorised charge with it.
    """
    return {f.category for f in fixed
            if f.category and f.category != "Other" and is_spend_category(f.category)}


def bills_paid(transactions: list[Transaction], month: str, fixed) -> dict:
    """What the plan's bills cost this month, beside what the plan expected.

    One item per category: a mortgage and a property tax both under Rent &
    Housing are one line, because the ledger can't tell their payments apart.
    """
    cats = bill_categories(fixed)
    planned: dict[str, float] = defaultdict(float)
    names: dict[str, list[str]] = defaultdict(list)
    for f in fixed:
        if f.category in cats:
            planned[f.category] += f.amount
            names[f.category].append(f.name)
    paid: dict[str, float] = defaultdict(float)
    for t in transactions:
        if t.month == month and t.category in cats \
                and is_spend_category(t.category):
            paid[t.category] += share_amount(t) if t.amount > 0 else t.amount
    items = []
    for cat in sorted(cats, key=lambda c: -planned[c]):
        label = names[cat][0] if len(names[cat]) == 1 else cat
        items.append({"name": label, "category": cat, "names": names[cat],
                      "planned": round(planned[cat], 2),
                      "paid": round(max(paid.get(cat, 0.0), 0.0), 2)})
    return {"paid": round(sum(i["paid"] for i in items), 2),
            "planned": round(sum(i["planned"] for i in items), 2),
            "items": items}


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


def coverage_gaps(transactions: list[Transaction]) -> list[str]:
    """Months where a card that was being tracked has no transactions.

    Statements are often imported with holes in them — you download a few, not
    every one. Those holes quietly corrupt anything that reasons about months:
    a monthly average divides by months you never imported, and a subscription
    whose charges straddle a gap looks quarterly rather than monthly. Callers
    surface this so the numbers can be read with it in mind.

    Measured per account, then combined, which matters as soon as there is
    more than one card. Taken across the whole ledger, a card closed last year
    and a card connected last week make every month between them look missing
    — when in truth nothing was being tracked then, and there is no statement
    to go and find. A month is a gap only for a card that has data on both
    sides of it.
    """
    by_account: dict[str, set[str]] = {}
    for t in transactions:
        by_account.setdefault(t.account_id, set()).add(t.month)

    gaps: set[str] = set()
    for months in by_account.values():
        gaps.update(m for m in _months_between(min(months), max(months))
                    if m not in months)
    return sorted(gaps)


def _months_between(first: str, last: str) -> list[str]:
    out, y, m = [], int(first[:4]), int(first[5:7])
    ly, lm = int(last[:4]), int(last[5:7])
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


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

    # Months that actually contain data: a gap is a month we never imported,
    # not a month of zero spending, and averaging it in would understate the
    # true monthly figure.
    avg_spend = typical_month_spend(transactions)

    latest_spend = next((m["spend"] for m in monthly if m["month"] == latest), 0.0)
    spend_rows = [t for t in spend_only(transactions) if t.amount > 0]

    return {
        "empty": False,
        "months": months,
        "latest_month": latest,
        "latest_month_complete": is_month_complete(transactions, latest) if latest else False,
        # Whether the month is still running, which is not the same question:
        # a finished month whose last few days were quiet is complete, and a
        # finished month the data stops short of is neither.
        "latest_month_running": is_month_running(latest) if latest else False,
        "last_complete_month": last_complete_month(transactions),
        "coverage_gaps": coverage_gaps(transactions),
        "monthly": monthly,
        "latest_spend": latest_spend,
        "currency": ledger_currency(transactions),
        "currency_mix": currency_mix(transactions),
        "average_monthly_spend": avg_spend,
        # Same number, under the name the rest of the app uses for it.
        "typical_monthly_spend": avg_spend,
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
                  month: str | None = None,
                  groups: dict[str, str] | None = None) -> list[dict]:
    """Actual vs. budget per line, with a pace projection for the live month.

    A line is a category, or several folded together by `groups`; with no
    grouping every category is its own line and nothing changes.
    """
    if not budgets:
        return []

    actuals: dict[str, float] = {}
    for r in by_category(transactions, month):
        line = (groups or {}).get(r["category"], r["category"])
        actuals[line] = actuals.get(line, 0.0) + r["amount"]

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
