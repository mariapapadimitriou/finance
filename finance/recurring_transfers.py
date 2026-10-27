"""Recurring transfers (2026-10-27): the same amount leaving the same bank
account on a schedule — rent by e-Transfer on the 1st, $200 into savings
every other Friday.

Pearl spots a series when two or more transfers out of one account are for
exactly the same amount, spaced weekly, every two weeks or monthly (give or
take a couple of days, for weekends and holidays), and at least one of them
is still waiting in Needs a look. It asks once for the whole series: "Is
this a recurring transfer?". Yes, and what it is, saves a rule; from then on
every transfer that matches the rule's amount and schedule is sorted the
same way, the ones already here and the ones still to come.

A rule matches on:

* the account it leaves from,
* the amount, to the cent,
* the schedule: within `TOLERANCE` days of a date the cadence lands on,
  counted from the rule's anchor (for monthly, the same day of the month,
  the last day in shorter months),
* and, when both name one, where it goes (`transfers.destination`), so two
  people paid the same rent on the same day stay apart. A nameless
  e-Transfer ("SEND E-TFR ***Ab9") has no destination; amount and schedule
  are what identify it.

A transfer whose other end is in Pearl (between her own accounts) is matched
before any rule, and anything she sorted herself is never touched.
"""

from __future__ import annotations

import calendar
import hashlib
from datetime import date, timedelta

from .models import Transaction

# Days either side of the scheduled date that still count.
TOLERANCE = {"weekly": 2, "biweekly": 3, "monthly": 3}
PERIOD = {"weekly": 7, "biweekly": 14}
CADENCE_WORDS = {"weekly": "every week", "biweekly": "every two weeks", "monthly": "every month"}
MIN_SERIES = 2
# How many it takes to call a schedule: two a month apart for the same
# amount is rent-like enough to ask; two a week apart could be anything.
MIN_FOR = {"weekly": 3, "biweekly": 3, "monthly": 2}


def _d(iso: str) -> date:
    return date.fromisoformat(iso[:10])


def _cents(x: float) -> int:
    return int(round(abs(x) * 100))


def _on(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _month_gap(when: date, anchor: date) -> int:
    """Days from `when` to the nearest date the monthly schedule lands on."""
    best = None
    for shift in (-1, 0, 1):
        m = when.month + shift
        y = when.year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        gap = abs((when - _on(y, m, anchor.day)).days)
        best = gap if best is None else min(best, gap)
    return best


def off_schedule(when: date, anchor: date, cadence: str) -> int:
    """How many days `when` is from the schedule."""
    if cadence == "monthly":
        return _month_gap(when, anchor)
    period = PERIOD[cadence]
    r = (when - anchor).days % period
    return min(r, period - r)


def on_schedule(when: date, anchor: date, cadence: str) -> bool:
    return off_schedule(when, anchor, cadence) <= TOLERANCE[cadence]


def cadence_of(days: list[date]) -> str | None:
    """The schedule a run of dates keeps, or None. Every gap has to be one
    step of it (give or take); a month or two missed in between is fine."""
    days = sorted(set(days))
    if len(days) < MIN_SERIES:
        return None
    gaps = [(b - a).days for a, b in zip(days, days[1:])]
    if any(g < 4 for g in gaps):
        return None
    for cadence in ("weekly", "biweekly", "monthly"):
        if len(days) < MIN_FOR[cadence]:
            continue
        anchor = days[-1]
        if not all(on_schedule(d, anchor, cadence) for d in days):
            continue
        step = 30.4 if cadence == "monthly" else PERIOD[cadence]
        # Mostly consecutive steps: a weekly run isn't "monthly" because its
        # days happen to fit, and two transfers a year apart aren't a series.
        if sum(1 for g in gaps if g <= step * 1.5 + TOLERANCE[cadence]) * 2 >= len(gaps) \
                and max(gaps) <= step * 3 + TOLERANCE[cadence]:
            return cadence
    return None


def when_words(cadence: str, anchor: date) -> str:
    """"every month, around the 1st"."""
    if cadence == "monthly":
        n = anchor.day
        suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"every month, around the {n}{suffix}"
    if cadence == "biweekly":
        return f"every two weeks, on {anchor.strftime('%A')}s"
    return f"every week, on {anchor.strftime('%A')}s"


def _dest(t: Transaction) -> tuple[str, str] | None:
    from .transfers import destination
    return destination(t)


def key_for(account_id: str, cents: int, cadence: str, dest: str | None) -> str:
    raw = f"{account_id}|{cents}|{cadence}|{dest or ''}"
    return "rt:" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def matches(t: Transaction, rule: dict) -> bool:
    """Whether a transfer is one of a rule's."""
    if t.amount <= 0 or t.account_id != rule["account_id"]:
        return False
    if _cents(t.amount) != _cents(rule["amount"]):
        return False
    if rule.get("dest_key"):
        where = _dest(t)
        if where and where[0] != rule["dest_key"]:
            return False
    return on_schedule(_d(t.date), _d(rule["anchor"]), rule["cadence"])


def rule_for(t: Transaction, rules: list[dict]) -> dict | None:
    return next((r for r in rules if matches(t, r)), None)


def _is_bank(t: Transaction) -> bool:
    return str((t.raw or {}).get("account_type", "")).lower() == "depository"


def series(transactions: list[Transaction], rules: list[dict] | None = None,
           paired: set[str] | None = None) -> list[dict]:
    """Runs of transfers out that look recurring and are still asked about:
    the same account and amount (and destination, when there is one), on a
    schedule, at least one of them in Unsorted transfers, and not already a
    rule's. Newest first."""
    from .transfers import NEUTRAL, UNSORTED
    rules = rules or []
    paired = paired or set()
    groups: dict[tuple, list[Transaction]] = {}
    for t in transactions:
        if t.amount <= 0 or not _is_bank(t) or t.excluded or t.fingerprint in paired:
            continue
        if t.category not in (NEUTRAL, UNSORTED) or t.category_source in ("user", "merchant_override"):
            continue
        if rule_for(t, rules):
            continue
        where = _dest(t)
        groups.setdefault((t.account_id, _cents(t.amount), where[0] if where else None),
                          []).append(t)
    out = []
    for (account, cents, dest), pool in groups.items():
        pool = sorted(pool, key=lambda t: t.date)
        while True:
            found = _best_run(pool)
            if not found:
                break
            cadence, rows = found
            taken = {t.fingerprint for t in rows}
            pool = [t for t in pool if t.fingerprint not in taken]
            if not any(t.category == UNSORTED for t in rows):
                continue
            out.append(_series(account, cents, dest, cadence, rows))
    out.sort(key=lambda s: s["last"], reverse=True)
    return out


def _best_run(rows: list[Transaction]) -> tuple[str, list[Transaction]] | None:
    """The longest run among same-amount transfers that keeps a schedule:
    one for the same amount on another day (a one-off) doesn't spoil it."""
    best = None
    for anchor in reversed(rows):
        for cadence in ("weekly", "biweekly", "monthly"):
            run = [t for t in rows if on_schedule(_d(t.date), _d(anchor.date), cadence)]
            # One a day: two the same day are not two steps of a schedule.
            by_day = {}
            for t in run:
                by_day.setdefault(t.date[:10], t)
            run = sorted(by_day.values(), key=lambda t: t.date)
            if len(run) < MIN_SERIES or cadence_of([_d(t.date) for t in run]) != cadence:
                continue
            score = _score(run, cadence)
            if best is None or score > best[0]:
                best = (score, cadence, run)
    return (best[1], best[2]) if best else None


def _score(run: list[Transaction], cadence: str) -> tuple:
    """A run that keeps its schedule step by step beats one that only fits
    by skipping steps: $1,500 on the 1st of each month, with another $1,500
    on the 14th once, is monthly, not every two weeks with gaps."""
    step = 30.4 if cadence == "monthly" else PERIOD[cadence]
    days = [_d(t.date) for t in run]
    steps = [max(1, round((b - a).days / step)) for a, b in zip(days, days[1:])]
    single = sum(1 for k in steps if k == 1)
    missed = sum(k - 1 for k in steps)
    return (single - missed, len(run))


def _series(account: str, cents: int, dest: str | None, cadence: str,
            rows: list[Transaction]) -> dict:
    last = rows[-1]
    where = _dest(last)
    return {
        "key": key_for(account, cents, cadence, dest),
        "account_id": account, "amount": round(cents / 100, 2), "cadence": cadence,
        "anchor": last.date[:10], "dest_key": dest,
        "to": where[1] if where else "", "ids": [t.fingerprint for t in rows],
        "first": rows[0].date[:10], "last": last.date[:10], "count": len(rows),
        "when": when_words(cadence, _d(last.date)),
    }


def rule_from(found: dict, category: str, label: str = "") -> dict:
    return {"id": found["key"], "account_id": found["account_id"], "amount": found["amount"],
            "cadence": found["cadence"], "anchor": found["anchor"],
            "dest_key": found.get("dest_key"), "label": label or found.get("to") or "",
            "category": category}


def rule_words(rule: dict, account_name: str = "") -> str:
    """"$1,500.00 every month, around the 1st, from Chequing"."""
    where = f" to {rule['label']}" if rule.get("label") else ""
    frm = f" from {account_name}" if account_name else ""
    return (f"${rule['amount']:,.2f}{where} {when_words(rule['cadence'], _d(rule['anchor']))}"
            f"{frm}")


def next_after(rule: dict, today: date) -> date:
    """The next date the schedule lands on after today."""
    anchor = _d(rule["anchor"])
    if rule["cadence"] == "monthly":
        y, m = today.year, today.month
        for _ in range(3):
            d = _on(y, m, anchor.day)
            if d > today:
                return d
            m += 1
            if m > 12:
                y, m = y + 1, 1
        return _on(y, m, anchor.day)
    period = PERIOD[rule["cadence"]]
    d = anchor
    while d <= today:
        d += timedelta(days=period)
    return d
