"""One sentence about yesterday, for the top of the app.

A budgeting app that only answers questions you think to ask is a
spreadsheet. The useful moment is the morning after: you spent too much
yesterday and nobody has told you, so today starts exactly like yesterday
did.

Rules this follows, because a nudge that gets ignored is worse than none:

  *about yesterday, not about you* — it reports what happened and what today
   now costs. No praise, no scolding, nothing about discipline.
  *silent when there is nothing to say* — an ordinary day produces no
   message. A banner that appears every single day stops being read by the
   end of the week.
  *never nudges toward spending* — an underspent day may say you are ahead,
   because that is true and useful, but it never suggests a reward. The whole
   app is built so that nothing in it pays out for buying something.
"""

from __future__ import annotations

from datetime import date, timedelta

from .analytics import spend_amount
from .spend_plan import compute, counts_toward_plan, days_in_month

# A few dollars over is not a story. Below this the day reads as ordinary.
MATERIAL = 5.0


def _spent_on(transactions, day: str) -> float:
    return round(sum(spend_amount(t) for t in transactions
                     if t.date == day and counts_toward_plan(t)), 2)


def _money(value: float) -> str:
    return f"${abs(value):,.0f}"


def for_yesterday(transactions, state: dict, today: date | None = None) -> dict | None:
    """What yesterday did to today's number, or None if nothing worth saying.

    `state` is spend_plan.compute() for the current month, which already
    knows the daily share and what is left. The point of this is not new
    arithmetic — it is saying the arithmetic out loud, unprompted, on the one
    morning it can change what you do.
    """
    now = today or date.today()
    yesterday = now - timedelta(days=1)

    # Only speaks about the month it has a plan for, and never on the 1st:
    # "yesterday" then belongs to a month that has already been settled.
    if state.get("month") != f"{now.year:04d}-{now.month:02d}" or now.day == 1:
        return None
    if not state.get("budget"):
        return None

    iso = yesterday.isoformat()
    # Nothing imported for yesterday is not the same as nothing spent, and
    # guessing which would make this untrustworthy on its first wrong day.
    if not any(t.date == iso for t in transactions):
        return None

    spent = _spent_on(transactions, iso)
    share = state["flat_daily"]
    delta = round(spent - share, 2)

    # What it did to the week — the number the reader is actually holding.
    # On a Monday, yesterday belongs to a week that has just closed, so the
    # useful thing to say is how that week finished and what this one starts
    # with, not what is "left" of a week that is over.
    week = state["week"]
    new_week = week["first_day"] == now.day
    if state["remaining"] < 0:
        # Past the whole month's budget is the larger fact, and saying "the
        # weeks after this get a little less" would be false: there is
        # nothing left to give them.
        consequence = (f"That takes the month past its budget: it is "
                       f"{_money(state['remaining'])} over, so from here "
                       "anything spent is over too.")
    elif new_week:
        last = compute(transactions, state["monthly_amount"], state["month"],
                       today=yesterday, covered=state.get("covered", 0.0))["week"]
        closed = last["left"]
        consequence = (
            f"That closed last week {_money(closed)} "
            f"{'under' if closed >= 0 else 'over'} its allowance, and this "
            f"week starts with {_money(week['allowance'])}."
            if abs(closed) >= 1 else
            f"Last week finished on its allowance; this one starts with "
            f"{_money(week['allowance'])}.")
    else:
        left = week["left"]
        consequence = (
            f"That leaves {_money(left)} for the rest of the week."
            if left >= 0 else
            f"This week is now {_money(left)} over. Spread across the rest of "
            "the month, every week after this gets a little less — nothing is "
            "lost, the month just gets tighter from here.")

    if delta > MATERIAL:
        return {
            "kind": "over",
            "spent": spent,
            "over_by": delta,
            "headline": f"You spent {_money(spent)} yesterday, "
                        f"{_money(delta)} more than a typical day's share.",
            "detail": consequence,
        }

    if delta < -MATERIAL:
        return {
            "kind": "under",
            "spent": spent,
            "under_by": abs(delta),
            "headline": f"You spent {_money(spent)} yesterday, "
                        f"{_money(abs(delta))} under a typical day's share.",
            "detail": (consequence if new_week or state["remaining"] < 0
                       or week["left"] < 0 else
                       f"That carries forward — {_money(week['left'])} left "
                       "for the rest of the week."),
        }

    return None
