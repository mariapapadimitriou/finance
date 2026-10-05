"""Safe to spend: a weekly allowance that rolls over, and what to do when it doesn't.

The model is deliberately simple enough to hold in your head:

    allowance this week = the week's share of the month's budget
                        + whatever you didn't spend in the weeks before it

Underspend last week and this week's number is bigger. That carried-in amount
is reported separately so the number never looks like magic.

Weekly, not daily, and for reasons that are about the data as much as the
person. Discretionary spending arrives in lumps — a dinner on Saturday, a
quiet Tuesday — so a daily figure is broken most days by design. And the
ledger is only as fresh as the last sync, with card charges taking a day or two
to land: a two-day lag is fatal to a number about today and minor against one
about the week. Weeks run Monday to Sunday and are clipped to the month, so a
month that starts on a Thursday opens with a four-day week given four days'
share. The daily figures are still computed — the arithmetic underneath is a
daily share — and stay in the response.

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


def week_bounds(month: str, day: int) -> tuple[int, int]:
    """The Monday-to-Sunday week holding `day`, clipped to the month.

    Returned as day numbers within the month. A week straddling two months is
    two weeks as far as the budget is concerned, one at the end of each: the
    month is the pot, so a week cannot draw on two of them.
    """
    y, m = int(month[:4]), int(month[5:7])
    weekday = date(y, m, day).weekday()          # Monday is 0
    first = max(day - weekday, 1)
    last = min(day + (6 - weekday), days_in_month(month))
    return first, last


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

    week = _week(transactions, month, day, total_days, budget, flat_daily)

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
        # The headline. See the module docstring for why it is a week.
        "week": week,
    }


def _week(transactions, month: str, day: int, total_days: int,
          budget: float, flat_daily: float) -> dict:
    """This week's allowance, by the same rule as the daily one.

    The rollover is the daily rule counted from the week's first day: what the
    days before it accrued, less what they spent. Then the same choice the
    daily number makes. Ahead of pace, the surplus rolls straight into this
    week, because carrying your own restraint forward is the reward the whole
    plan is built around. Behind, the shortfall is spread — this week gets its
    days' share of what is left of the month — so the week never opens
    already lost.

    Either way the month balances: the last week of a month is allowed exactly
    what is left of it.
    """
    first, last = week_bounds(month, day)
    week_days = last - first + 1

    spent_before = _spent(transactions, month, upto_day=first - 1)
    carried_in = round(flat_daily * (first - 1) - spent_before, 2)
    remaining_at_start = round(budget - spent_before, 2)
    days_left_at_start = total_days - first + 1

    behind = carried_in < 0
    if behind:
        allowance = remaining_at_start * week_days / days_left_at_start
    else:
        allowance = flat_daily * week_days + carried_in

    spent = round(sum(
        _spent(transactions, month, on_day=d) for d in range(first, day + 1)), 2)
    left = round(allowance - spent, 2)
    days_left = last - day + 1

    return {
        "first_day": first,
        "last_day": last,
        "days": week_days,
        "short": week_days < 7,
        "share": round(flat_daily * week_days, 2),
        "carried_in": carried_in,
        "behind": behind,
        "allowance": round(allowance, 2),
        "spent": spent,
        "left": left,
        "days_left": days_left,
        # A secondary figure for anyone who still thinks in days.
        "per_day": round(left / days_left, 2) if days_left else left,
        "over": left < 0,
        # What a normal full week is worth, for the derivation on screen.
        "nominal": round(flat_daily * 7, 2),
    }


def _money(value: float) -> str:
    """Format for prose. A negative reads as −$12.00, never as $-12.00."""
    return f"{'−' if value < 0 else ''}${abs(value):,.2f}"


def simulate(state: dict, amount: float, pots=None) -> dict:
    """Answer "can I buy this?" with the consequence either way.

    Against the week, like the headline: a purchase fits if it fits in what is
    left of this week. `pots` is a list of (piggy bank, available balance)
    pairs. The balance is passed in rather than read off the bank because it
    is derived — months accrued less what has been charged — and the one
    place that derives it is finance/piggy.py.
    """
    amount = round(float(amount), 2)
    left = state["week"]["left"]
    after = round(left - amount, 2)

    if after >= 0:
        return {
            "amount": amount,
            "affordable": True,
            "leaves_week": after,
            "message": f"Yes — that leaves {_money(after)} for the rest of the week.",
            "options": [],
        }

    short = round(-after, 2)
    days_left = state["days_left"]
    # Spreading the shortfall over the rest of the month, today excluded:
    # today has already been spent by the purchase itself. Quoted per week,
    # because that is the number the reader is looking at.
    future_days = max(days_left - 1, 1)
    new_daily = round((state["remaining"] - amount) / future_days, 2)
    new_weekly = round(new_daily * 7, 2)

    if new_daily >= 0:
        detail = (f"Every week after this drops to about {_money(new_weekly)}."
                  if future_days > 7 else
                  f"What is left of the month drops to {_money(new_daily)} a day.")
    else:
        # Saying "every week drops to −$2,148" is arithmetic nobody can act on.
        # What it means is that the month has already run out.
        detail = ("There is nothing left in the month to spread it over — the "
                  f"budget is already {_money(-state['remaining'])} short "
                  "before this purchase.")

    options = [{
        "kind": "spread",
        "label": "Spread it over the rest of the month",
        "detail": detail,
        "new_daily": new_daily,
        "new_weekly": new_weekly,
        "viable": new_daily >= 0,
    }]

    # What paying from a bank would do — nothing is taken from it here. The
    # real charge is charged to the bank when it arrives, and the bank pays
    # the whole of it, so that is the figure shown.
    for bank, available in (pots or []):
        options.append({
            "kind": "cover",
            "bank_id": bank.id,
            "label": f"Pay it from {bank.name}",
            "detail": f"{bank.name} goes from {_money(available)} to "
                      f"{_money(round(available - amount, 2))}.",
            "viable": available >= amount,
        })

    if left < 0:
        message = (f"This week is already {_money(-left)} over, so that "
                   f"purchase needs {_money(short)} from somewhere.")
    else:
        message = (f"That's {_money(short)} more than the {_money(left)} left "
                   "this week.")

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
        verdict, tone = "Nothing spent yet this month", "good"
    elif spent <= expected * 0.8:
        verdict, tone = "Comfortably under", "good"
    elif spent <= expected:
        verdict, tone = "On track", "good"
    elif projected <= budget:
        verdict, tone = "Ahead of pace, but the month still balances", "warning"
    else:
        verdict, tone = "Over pace — this month lands above budget", "critical"

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
