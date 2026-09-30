"""Streaks, points and levels, earned only by spending less.

A word on the design, because gamifying money can go badly wrong. Every reward
here is for *restraint* — a day under the allowance, a day with no discretionary
spending at all, a month that lands under budget. Nothing pays out for spending,
so the mechanics can never nudge you toward a purchase. There is no currency to
buy, no streak that breaks if you fail to open the app, and no notification
pressure; the numbers simply describe what already happened.

Everything is derived from the ledger on read. There is no score to keep in
sync, and correcting a transaction immediately corrects the score.
"""

from __future__ import annotations

from datetime import date, timedelta

from .spend_plan import counts_toward_plan, days_in_month

# Points are small integers on purpose: large numbers imply a currency, and a
# currency implies spending it.
POINTS_UNDER_DAY = 10
POINTS_NO_SPEND_DAY = 25
POINTS_UNDER_MONTH = 150
STREAK_BONUS_EVERY = 7
STREAK_BONUS = 40

LEVELS = [
    (0, "Getting started"),
    (250, "Paying attention"),
    (750, "In control"),
    (1600, "Deliberate"),
    (3000, "Unbothered"),
    (5000, "Spendie master"),
]


def _daily_totals(transactions, month: str) -> dict[int, float]:
    out: dict[int, float] = {}
    for t in transactions:
        if t.month == month and counts_toward_plan(t):
            day = int(t.date[8:10])
            out[day] = round(out.get(day, 0.0) + t.amount, 2)
    return out


def _observed_days(transactions, month: str) -> set[int]:
    """Days the statements actually cover.

    A day with no rows is ambiguous: it is either a day you spent nothing, or a
    day outside the imported range. Awarding a no-spend badge for a month you
    never imported would be a lie, so only days inside the covered range count.
    """
    days = [int(t.date[8:10]) for t in transactions if t.month == month]
    if not days:
        return set()
    return set(range(min(days), max(days) + 1))


# How close the observed range has to come to each end of the month before we
# call the month fully imported. Nothing records statement periods per day, so
# coverage is inferred from the first and last charge — and a month can easily
# open or close with a few quiet days. Three days each end tolerates that
# without accepting a statement that covers half a month.
EDGE_TOLERANCE = 3


def _fully_observed(observed: set[int], total_days: int) -> bool:
    if not observed:
        return False
    return (min(observed) <= 1 + EDGE_TOLERANCE
            and max(observed) >= total_days - EDGE_TOLERANCE)


def month_stats(transactions, month: str, daily_allowance: float,
                today: date | None = None) -> dict:
    """Per-day results for one month, and the points they earn."""
    totals = _daily_totals(transactions, month)
    observed = _observed_days(transactions, month)
    total_days = days_in_month(month)

    now = today or date.today()
    if f"{now.year:04d}-{now.month:02d}" == month:
        last_day = now.day
    elif f"{now.year:04d}-{now.month:02d}" > month:
        last_day = total_days
    else:
        last_day = 0

    days = []
    for d in range(1, last_day + 1):
        if d not in observed:
            days.append({"day": d, "spent": None, "state": "no-data"})
            continue
        spent = totals.get(d, 0.0)
        if spent == 0:
            state = "no-spend"
        elif daily_allowance > 0 and spent <= daily_allowance:
            state = "under"
        else:
            state = "over"
        days.append({"day": d, "spent": spent, "state": state})

    under = sum(1 for d in days if d["state"] == "under")
    no_spend = sum(1 for d in days if d["state"] == "no-spend")
    over = sum(1 for d in days if d["state"] == "over")

    points = under * POINTS_UNDER_DAY + no_spend * POINTS_NO_SPEND_DAY
    spent_month = round(sum(t.amount for t in transactions
                            if t.month == month and counts_toward_plan(t)), 2)
    budget = daily_allowance * total_days

    # A month is only "under budget" if the whole month was imported. A
    # statement covering the 18th to the 30th always comes in under, because
    # two thirds of the month is missing — awarding 150 points and a badge for
    # that would be paying out for a gap in the data.
    ended = last_day >= total_days
    fully_observed = _fully_observed(observed, total_days)
    if budget > 0 and ended and fully_observed and spent_month <= budget:
        points += POINTS_UNDER_MONTH

    return {
        "month": month,
        "days": days,
        "under": under,
        "no_spend": no_spend,
        "over": over,
        "points": points,
        "spent": spent_month,
        "budget": round(budget, 2),
        "days_in_month": total_days,
        "days_observed": len(observed),
        "fully_observed": fully_observed,
        "complete": ended and fully_observed,
        "ended": ended,
    }


def current_streak(transactions, daily_allowance: float,
                   today: date | None = None) -> dict:
    """Consecutive good days ending today, counting back through months.

    A day with no imported data stops the count rather than continuing or
    breaking it — pretending to know about a day we never saw would inflate the
    number, and breaking on it would punish you for a missing statement.
    """
    now = today or date.today()
    by_date: dict[str, float] = {}
    for t in transactions:
        if counts_toward_plan(t):
            by_date[t.date] = round(by_date.get(t.date, 0.0) + t.amount, 2)

    covered = {t.date for t in transactions}
    if not covered:
        return {"days": 0, "best_possible": False, "reason": "No transactions yet."}

    newest = max(covered)
    cursor = now
    # Walk back to the newest day we actually have data for.
    if newest < cursor.isoformat():
        cursor = date.fromisoformat(newest)

    streak = 0
    while True:
        iso = cursor.isoformat()
        month_days = {d for d in covered if d[:7] == iso[:7]}
        if not month_days or iso < min(month_days) or iso > max(month_days):
            break                      # outside the imported range
        spent = by_date.get(iso, 0.0)
        if daily_allowance > 0 and spent > daily_allowance:
            break
        streak += 1
        cursor -= timedelta(days=1)
        if streak > 400:
            break

    return {
        "days": streak,
        "through": cursor.isoformat(),
        "bonus_at": STREAK_BONUS_EVERY - (streak % STREAK_BONUS_EVERY)
                    if streak else STREAK_BONUS_EVERY,
    }


def level_for(points: int) -> dict:
    name, floor, nxt = LEVELS[0][1], 0, None
    for threshold, label in LEVELS:
        if points >= threshold:
            name, floor = label, threshold
        elif nxt is None:
            nxt = (threshold, label)

    span = (nxt[0] - floor) if nxt else 1
    return {
        "name": name,
        "points": points,
        "floor": floor,
        "next_at": nxt[0] if nxt else None,
        "next_name": nxt[1] if nxt else None,
        "progress": round(min((points - floor) / span, 1.0), 3) if nxt else 1.0,
    }


BADGES = [
    ("first-import", "Opened the books", "Imported your first statement"),
    ("no-spend-day", "Quiet day", "A day with no discretionary spending"),
    ("no-spend-5", "Five quiet days", "Five no-spend days in one month"),
    ("week-under", "Week under", "Seven days running under the allowance"),
    ("month-under", "Month under", "Finished a month inside the budget"),
    ("trip-logged", "Trip logged", "Declared a trip so its spending reads as travel"),
    ("category-fixed", "Taught it something", "Corrected a category by hand"),
]


def badges(transactions, month_stats_list: list[dict], streak: dict,
           trips: list, has_user_override: bool) -> list[dict]:
    """Which badges are earned, each with the fact that earned it."""
    earned = {}

    if transactions:
        earned["first-import"] = f"{len(transactions)} transactions imported"

    best_no_spend = max((m["no_spend"] for m in month_stats_list), default=0)
    if best_no_spend >= 1:
        earned["no-spend-day"] = f"{best_no_spend} in your best month"
    if best_no_spend >= 5:
        earned["no-spend-5"] = f"{best_no_spend} no-spend days"

    if streak.get("days", 0) >= 7:
        earned["week-under"] = f"{streak['days']}-day streak"

    under_months = [m for m in month_stats_list
                    if m["complete"] and m["budget"] > 0 and m["spent"] <= m["budget"]]
    if under_months:
        earned["month-under"] = f"{len(under_months)} month(s) under budget"

    if trips:
        earned["trip-logged"] = f"{len(trips)} trip(s) declared"

    if has_user_override:
        earned["category-fixed"] = "You corrected a category"

    return [
        {"key": k, "name": n, "description": d,
         "earned": k in earned, "detail": earned.get(k, "")}
        for k, n, d in BADGES
    ]


def profile(transactions, daily_allowance: float, trips: list,
            today: date | None = None) -> dict:
    """The whole gamified picture, derived fresh from the ledger."""
    months = sorted({t.month for t in transactions})
    stats = [month_stats(transactions, m, daily_allowance, today) for m in months]
    streak = current_streak(transactions, daily_allowance, today)

    points = sum(m["points"] for m in stats)
    if streak["days"] >= STREAK_BONUS_EVERY:
        points += (streak["days"] // STREAK_BONUS_EVERY) * STREAK_BONUS

    has_override = any(t.category_source == "user" for t in transactions)

    return {
        "level": level_for(points),
        "streak": streak,
        "totals": {
            "under_days": sum(m["under"] for m in stats),
            "no_spend_days": sum(m["no_spend"] for m in stats),
            "over_days": sum(m["over"] for m in stats),
            "months_tracked": len(stats),
        },
        "badges": badges(transactions, stats, streak, trips, has_override),
        "months": stats[-6:],
    }
