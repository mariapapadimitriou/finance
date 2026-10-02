"""Piggy banks: the costs that aren't monthly, budgeted monthly anyway.

A monthly budget handles rent and groceries well and handles a holiday badly.
The holiday costs $3,000 once a year, so eleven months report a surplus that
isn't real and the twelfth reports a catastrophe that was entirely predictable.
The same is true of car maintenance, insurance paid annually, Christmas, a
dentist you see twice a year, and the flights for a wedding you agreed to
attend in April.

A piggy bank fixes both halves of that at once:

  * **Going in.** The target is divided by the months available and that
    share is subtracted from every month's budget, exactly like rent. A
    holiday you will take in June is a bill you are already paying.
  * **Coming out.** Spending allocated to a bank is drawn from the bank
    instead of counting against the month it fell in. June does not look like
    a disaster, because June was never asked to pay for the holiday.

Those two together are the whole idea. Everything below is arithmetic in
service of it, and all of it is derived rather than typed: the monthly figure
comes from the target and the horizon, and the balance comes from how many
months have passed and what has been charged to the bank. Nobody has to keep a
separate number up to date, which is the only way a number like this stays
true.

Two shapes of bank, because two shapes of cost:

  `annual`  A cost that recurs forever — car maintenance, insurance,
            Christmas. Contributions never stop, and spending draws the
            balance down and leaves it to refill. Monthly = target ÷ 12.
  `once`    A cost with a date — a trip in June, a wedding in April.
            Contributions run from when you started until the month of the
            date and then stop. Monthly = what is still needed ÷ months left.

The distinction matters for the arithmetic and nowhere else; the UI calls them
"every year" and "by a date".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

ANNUAL = "annual"
ONCE = "once"
CADENCES = (ANNUAL, ONCE)

# A bank funded over more than ten years is not a plan, it is a rounding error
# with a name, and dividing by it produces a monthly figure of pennies.
MAX_MONTHS = 120

# How long a bank gets to repay itself after being spent ahead of its funding.
# A year, because the alternative to spreading it is a single month that has to
# absorb the whole overspend — which is the problem piggy banks exist to solve,
# and solving it for the planned case while reintroducing it for the unplanned
# one would be most of the way to pointless.
CATCH_UP_MONTHS = 12


@dataclass
class Bank:
    """A named pot with a target, a horizon, and money already in it."""

    id: int | None
    name: str
    target: float
    cadence: str = ANNUAL
    target_date: str | None = None
    start_month: str = ""
    opening: float = 0.0
    note: str = ""

    @property
    def is_dated(self) -> bool:
        return self.cadence == ONCE and bool(self.target_date)

    def to_dict(self, stats: dict | None = None) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "target": round(self.target, 2),
            "cadence": self.cadence,
            "target_date": self.target_date,
            "start_month": self.start_month,
            "opening": round(self.opening, 2),
            "note": self.note,
        }
        if stats:
            d.update(stats)
        return d


# ── The arithmetic ───────────────────────────────────────────────────────────

def _month_index(month: str) -> int:
    """Months since year zero, so two months can be subtracted."""
    return int(month[:4]) * 12 + int(month[5:7]) - 1


def months_between(start: str, end: str) -> int:
    """Whole calendar months from one to the other, both ends counted.

    January to January is one month, not zero: a bank started and spent in the
    same month still had that month to collect a contribution.
    """
    return _month_index(end) - _month_index(start) + 1


def funding_months(bank: Bank, today: str | None = None) -> int:
    """How many months the target is spread across.

    For an annual bank that is simply twelve, every year, forever. For a dated
    one it is the months from when you started to the month of the date — and
    never fewer than one, because a trip booked for next week still has to be
    paid for out of something.
    """
    if bank.cadence == ANNUAL or not bank.target_date:
        return 12
    start = bank.start_month or (today or _today())[:7]
    span = months_between(start, bank.target_date[:7])
    return max(min(span, MAX_MONTHS), 1)


def base_monthly(bank: Bank, today: str | None = None) -> float:
    """The rate the target and the horizon imply, before any catching up.

    What the bank actually takes out of a month can be more than this — see
    `run`, which adds whatever it takes to repay a bank that has been spent
    ahead of its funding.

    Money already in the bank reduces it: if the holiday costs $3,000 and
    $500 is already set aside, only $2,500 has to be collected. Saying
    otherwise would quietly ask for the $500 twice.
    """
    needed = max(bank.target - bank.opening, 0.0)
    return round(needed / funding_months(bank, today), 2)


def run(bank: Bank, charges: dict[str, float],
        today: str | None = None) -> dict:
    """Play the bank forward month by month and report where it stands.

    This is what makes a bank able to pay for something before it has finished
    saving for it. A trip booked in the first month of a $2,400-a-year travel
    fund costs $2,000 against a pot holding $200 — and the answer is not that
    the bank can only pay $200, nor that the month has to absorb $1,800. The
    answer is the one anybody would reach for in real life: the fund is behind,
    and it pays itself back out of the months that follow.

    So the contribution is not a constant. While the balance is negative the
    shortfall is spread over the next `CATCH_UP_MONTHS`, on top of the base
    rate, and that extra comes out of those months' budgets exactly as the base
    does. As the balance recovers the extra shrinks and disappears, which is
    why this is a loop rather than a formula: each month's rate depends on the
    balance the month before, and the balance depends on every rate before it.

    Nothing is stored. `charges` is what was taken out in each month — spending
    allocated to the bank plus anything drawn to cover an overspend — and the
    whole history is replayed on every request, so the figures cannot drift
    from the transactions behind them.
    """
    now = (today or _today())[:7]
    start = bank.start_month or now
    base = base_monthly(bank, today)
    horizon = funding_months(bank, today)

    # The replay has to begin at the earliest of the bank's start and anything
    # charged to it, not simply at the start. A bank opened *after* the trip it
    # is for — "that holiday hurt, let me spread the next one" — has charges
    # dated before it existed, and a loop that began at the start month skipped
    # them entirely: the bank reported itself fully funded while owing $2,000.
    first = min([start, *charges]) if charges else start

    balance = round(bank.opening, 2)
    months_paid = 0
    paid_in = round(bank.opening, 2)

    if now >= first:
        for i in range(months_between(first, now)):
            month = _add_months(first, i)
            # Nothing is collected before the bank existed, and a dated bank
            # stops collecting once its date has passed — but either way it
            # still has to pay off whatever it owes.
            since_start = _month_index(month) - _month_index(start)
            open_yet = month >= start
            collecting = (base if open_yet
                          and (not bank.is_dated or since_start < horizon)
                          else 0.0)
            # The catch-up is gated on the bank existing too. A fund opened
            # after the trip it covers would otherwise show itself as having
            # quietly repaid the shortfall over the preceding year — money that
            # never came out of any real month's budget.
            behind = max(-balance, 0.0) if open_yet else 0.0
            rate = round(collecting + behind / CATCH_UP_MONTHS, 2)
            balance = round(balance + rate - charges.get(month, 0.0), 2)
            paid_in = round(paid_in + rate, 2)
            if month >= start:
                months_paid += 1

    # Next month's rate, which is the one the Plan has to subtract.
    behind_now = max(-balance, 0.0)
    collecting_next = base if (not bank.is_dated or months_paid < horizon) else 0.0
    next_rate = round(collecting_next + behind_now / CATCH_UP_MONTHS, 2)

    return {
        "monthly": next_rate,
        "base_monthly": base,
        "catch_up": round(next_rate - collecting_next, 2),
        "balance": balance,
        "paid_in": paid_in,
        "charged": round(sum(charges.values()), 2),
        "months_paid": months_paid,
        "behind_by": round(behind_now, 2),
        "behind": behind_now > 0,
        # When the shortfall is cleared at the current rate, so "behind" reads
        # as a date rather than an open-ended failure.
        "caught_up_by": (_add_months(now, CATCH_UP_MONTHS)
                         if behind_now > 0 else None),
    }


def _add_months(month: str, n: int) -> str:
    total = _month_index(month) + n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def status(bank: Bank, charges, today: str | None = None) -> dict:
    """One bank's full picture: what went in, what came out, what is left.

    `charges` is either the per-month breakdown of everything taken out of the
    bank, or a single total for callers that do not have the breakdown — a
    total is treated as having been spent in the current month, which is right
    for the common case of asking what a charge made just now would do.
    """
    now = today or _today()
    if not isinstance(charges, dict):
        charges = {now[:7]: float(charges or 0.0)}

    played = run(bank, charges, today)
    per_month = played["monthly"]
    in_so_far = played["paid_in"]
    balance = played["balance"]
    months = funding_months(bank, today)

    paid_months = played["months_paid"]
    if bank.is_dated:
        remaining_months = max(months - paid_months, 0)
        funded_on = bank.target_date
    else:
        remaining_months = None
        funded_on = None

    return {
        "monthly": per_month,
        "base_monthly": played["base_monthly"],
        "catch_up": played["catch_up"],
        "accrued": in_so_far,
        "charged": played["charged"],
        "balance": balance,
        "funding_months": months,
        "months_paid": paid_months,
        "months_left": remaining_months,
        "funded_on": funded_on,
        "funded_share": round(min(in_so_far / bank.target, 1.0), 4) if bank.target > 0 else 0.0,
        "complete": bool(bank.is_dated and remaining_months == 0),
        # Spending ahead of a bank is not an error — you may have to fly before
        # you have finished saving for the flight. What it means is that the
        # bank owes itself money, which it collects from the months ahead.
        "behind": played["behind"],
        "behind_by": played["behind_by"],
        "caught_up_by": played["caught_up_by"],
    }


def total_monthly(banks: list[Bank], charges: dict[int, dict] | None = None,
                  today: str | None = None) -> float:
    """What every bank together takes out of a month, for the Plan's arithmetic.

    Includes any catch-up, because a bank repaying itself genuinely does take
    more out of this month than its base rate — that is the whole mechanism,
    and leaving it out of the Plan would hand the same money out twice.
    """
    charges = charges or {}
    return round(sum(run(b, charges.get(b.id, {}), today)["monthly"]
                     for b in banks), 2)


def _today() -> str:
    return date.today().isoformat()


# ── Validation ───────────────────────────────────────────────────────────────

def validate(name: str, target: float, cadence: str,
             target_date: str | None, today: str | None = None) -> str | None:
    """Return an error message, or None when the bank is usable."""
    if not (name or "").strip():
        return "Give the piggy bank a name."
    try:
        amount = float(target)
    except (TypeError, ValueError):
        return "The target must be a number."
    if amount <= 0:
        return "A piggy bank needs a target above zero."
    if amount > 10_000_000:
        return "That target is implausibly large."
    if cadence not in CADENCES:
        return "Choose either a yearly amount or a target date."

    if cadence == ONCE:
        if not target_date:
            return "Give the date you need the money by."
        try:
            when = date.fromisoformat(target_date)
        except (ValueError, TypeError):
            return "The date must be YYYY-MM-DD."
        now = date.fromisoformat(today or _today())
        if when < now.replace(day=1):
            return ("That date has already passed. Use a yearly amount for "
                    "something that recurs, or pick the next one.")
        if months_between(now.isoformat()[:7], target_date[:7]) > MAX_MONTHS:
            return "That is more than ten years out — pick something nearer."
    return None
