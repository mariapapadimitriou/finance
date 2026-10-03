"""Safe to spend: a daily allowance that rolls over, and what to do when it doesn't.

The model is deliberately simple enough to hold in your head:

    allowance today = a flat daily share of the month's budget
                    + whatever you didn't spend on the days before it

Underspend on Monday and Tuesday's number is bigger. That carried-in amount is
reported separately so the number never looks like magic.

Overspending is where budgeting apps usually either shout or lie. Two honest
options are offered instead, both with the arithmetic shown:

  *spread*  — the shortfall is divided across the days left in the month, so
              every remaining day gets slightly less and the month still
              balances. Nothing is hidden; the daily number just drops.
  *cover*   — the shortfall comes out of a piggy bank. The money is real and
              has to come from somewhere, so borrowing from the holiday fund
              leaves less in the holiday fund.

Only discretionary spending counts. Rent and utilities are already committed;
including them would make the daily number meaningless, and no amount of
restraint on a Tuesday changes the hydro bill.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from .analytics import counts_as_spending, spend_amount
from .categorize import is_discretionary


def days_in_month(month: str) -> int:
    return calendar.monthrange(int(month[:4]), int(month[5:7]))[1]


def counts_toward_plan(t) -> bool:
    """Discretionary spending only — the part a daily number can influence."""
    return (t.amount > 0
            and counts_as_spending(t)
            and is_discretionary(t.category or "Other"))


def _spent(transactions, month: str, upto_day: int | None = None,
           on_day: int | None = None) -> float:
    total = 0.0
    for t in transactions:
        if t.month != month or not counts_toward_plan(t):
            continue
        day = int(t.date[8:10])
        if on_day is not None and day != on_day:
            continue
        if upto_day is not None and day > upto_day:
            continue
        # What this day cost the month, so a charge a piggy bank covered does
        # not come out of the daily allowance as well.
        total += spend_amount(t)
    return round(total, 2)


def compute(transactions, monthly_amount: float, month: str,
            today: date | None = None, covered: float = 0.0) -> dict:
    """The whole picture for one month, as of one day inside it."""
    total_days = days_in_month(month)

    # "Today" is clamped into the month so a past month reports its final state
    # rather than a day that never existed in it.
    now = today or date.today()
    if f"{now.year:04d}-{now.month:02d}" == month:
        day = now.day
    elif f"{now.year:04d}-{now.month:02d}" > month:
        day = total_days          # a month already finished
    else:
        day = 1                   # a month not yet started

    budget = round(monthly_amount + covered, 2)
    flat_daily = budget / total_days if total_days else 0.0

    spent_before = _spent(transactions, month, upto_day=day - 1)
    spent_today = _spent(transactions, month, on_day=day)
    spent_mtd = round(spent_before + spent_today, 2)

    # The rollover: allowance accrued on the days before today, minus what
    # those days actually used. Negative means you are running behind.
    carried_in = round(flat_daily * (day - 1) - spent_before, 2)
    todays_allowance = round(flat_daily + carried_in, 2)
    safe_today = round(todays_allowance - spent_today, 2)

    days_left = max(total_days - day + 1, 1)
    remaining = round(budget - spent_mtd, 2)
    # Spreading divides whatever is left — surplus or shortfall — evenly over
    # the rest of the month, today included.
    spread_daily = round(remaining / days_left, 2)

    # Which number to lead with.
    #
    # Strict rollover puts the whole of a bad day onto the next one, which can
    # make tomorrow's allowance negative before breakfast. That is arithmetically
    # honest and useless as guidance: an allowance you have already failed is
    # one you stop reading.
    #
    # So a shortfall is spread over the days that remain — the month still has
    # to balance, every day just gets a little less — while a surplus still
    # rolls straight onto today, because carrying your own restraint forward
    # is the reward the whole plan is built around. The strict figure stays in
    # the response, and the breakdown on screen still shows it.
    behind = carried_in < 0
    effective = spread_daily if behind else safe_today

    return {
        "month": month,
        "day": day,
        "days_in_month": total_days,
        "days_left": days_left,
        "budget": budget,
        "monthly_amount": round(monthly_amount, 2),
        "covered": round(covered, 2),
        "flat_daily": round(flat_daily, 2),
        "carried_in": carried_in,
        "todays_allowance": todays_allowance,
        "spent_today": spent_today,
        "spent_mtd": spent_mtd,
        "remaining": remaining,
        "spread_daily": spread_daily,
        "safe_today": safe_today,
        "safe_today_effective": round(effective, 2),
        "behind": behind,
        "recovering": behind and remaining > 0,
        "over": effective < 0,
        "over_strict": safe_today < 0,
        "pace": round(spent_mtd / (flat_daily * day), 4) if flat_daily and day else None,
    }


def _money(value: float) -> str:
    """Format for prose. A negative reads as −$12.00, never as $-12.00."""
    return f"{'−' if value < 0 else ''}${abs(value):,.2f}"


def simulate(state: dict, amount: float, pots=None) -> dict:
    """Answer "can I buy this?" with the consequence either way.

    `pots` is a list of (piggy bank, available balance) pairs. The balance is
    passed in rather than read off the bank because it is derived — months
    accrued less what has been charged — and the one place that derives it is
    finance/piggy.py.
    """
    amount = round(float(amount), 2)
    safe = state["safe_today"]
    after = round(safe - amount, 2)

    if after >= 0:
        return {
            "amount": amount,
            "affordable": True,
            "leaves_today": after,
            "message": f"Yes — that leaves {_money(after)} for the rest of today.",
            "options": [],
        }

    short = round(-after, 2)
    days_left = state["days_left"]
    # Spreading the shortfall over the days that remain, today excluded: today
    # has already been spent by the purchase itself.
    future_days = max(days_left - 1, 1)
    new_daily = round((state["remaining"] - amount) / future_days, 2)

    if new_daily >= 0:
        detail = f"Every remaining day drops to {_money(new_daily)}."
    else:
        # Saying "every day drops to −$306.89" is arithmetic nobody can act on.
        # What it means is that the month has already run out.
        detail = ("There is nothing left in the month to spread it over — the "
                  f"budget is already {_money(-state['remaining'])} short "
                  "before this purchase.")

    options = [{
        "kind": "spread",
        "label": f"Spread it over the {future_days} day"
                 f"{'' if future_days == 1 else 's'} left",
        "detail": detail,
        "new_daily": new_daily,
        "viable": new_daily >= 0,
    }]

    for bank, available in (pots or []):
        options.append({
            "kind": "cover",
            "bank_id": bank.id,
            "label": f"Cover {_money(short)} from {bank.name}",
            "detail": f"{bank.name} goes from {_money(available)} to "
                      f"{_money(round(available - short, 2))}.",
            "viable": available >= short,
        })

    if safe < 0:
        message = (f"Today is already {_money(-safe)} over, so that purchase "
                   f"needs {_money(short)} from somewhere.")
    else:
        message = f"That's {_money(short)} more than today's {_money(safe)}."

    return {
        "amount": amount,
        "affordable": False,
        "short_by": short,
        "message": message,
        "options": options,
    }


def how_am_i_doing(state: dict, baseline: float | None = None) -> dict:
    """A plain verdict on the month, with the number it rests on."""
    budget, spent, day = state["budget"], state["spent_mtd"], state["day"]
    total_days = state["days_in_month"]
    expected = state["flat_daily"] * day
    projected = round(spent / day * total_days, 2) if day else 0.0

    if budget <= 0:
        verdict, tone = "No budget set yet", "neutral"
    elif spent == 0:
        verdict, tone = "Nothing spent yet", "good"
    elif spent <= expected * 0.8:
        verdict, tone = "Comfortably under", "good"
    elif spent <= expected:
        verdict, tone = "On track", "good"
    elif projected <= budget:
        verdict, tone = "A bit ahead of pace", "warning"
    else:
        verdict, tone = "Over pace", "critical"

    return {
        "verdict": verdict,
        "tone": tone,
        "spent": spent,
        "expected_by_now": round(expected, 2),
        "projected_month_end": projected,
        "projected_over": round(projected - budget, 2),
        "budget": budget,
        "vs_baseline": round(projected - baseline, 2) if baseline else None,
    }


def suggest_monthly_amount(transactions) -> float:
    """A starting budget: your own median monthly discretionary spend.

    Seeded from what you actually do rather than a generic template, and
    rounded to something you would plausibly write down.
    """
    import statistics
    per_month: dict[str, float] = {}
    for t in transactions:
        if counts_toward_plan(t):
            per_month[t.month] = per_month.get(t.month, 0.0) + spend_amount(t)
    if not per_month:
        return 0.0
    median = statistics.median(per_month.values())
    return float(round(median, -1)) or round(median, 2)
