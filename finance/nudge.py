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

from .spend_plan import counts_toward_plan, days_in_month

# A few dollars over is not a story. Below this the day reads as ordinary.
MATERIAL = 5.0


def _spent_on(transactions, day: str) -> float:
    return round(sum(t.amount for t in transactions
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
    left = state["remaining"]
    days_left = max(state["days_in_month"] - state["day"] + 1, 1)
    spread = round(left / days_left, 2) if left > 0 else 0.0

    if delta > MATERIAL:
        return {
            "kind": "over",
            "spent": spent,
            "over_by": delta,
            "headline": f"You spent {_money(spent)} yesterday, "
                        f"{_money(delta)} over the daily share.",
            "detail": (
                f"Spread across the {days_left} day"
                f"{'' if days_left == 1 else 's'} left, that leaves "
                f"{_money(spread)} a day for the rest of the month instead of "
                f"{_money(share)}. Nothing is lost — the month just gets a "
                "little tighter from here."
                if left > 0 else
                f"That takes the month past its budget. What is left is "
                f"{_money(left)}, so from here anything spent is over."),
        }

    if delta < -MATERIAL:
        return {
            "kind": "under",
            "spent": spent,
            "under_by": abs(delta),
            "headline": f"You spent {_money(spent)} yesterday, "
                        f"{_money(abs(delta))} under the daily share.",
            "detail": (f"That carries forward: today has {_money(spread)} "
                       f"rather than {_money(share)}."),
        }

    return None
