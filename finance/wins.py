"""Wins (THL-239 to THL-243; built as THL-246, THL-247, THL-249, THL-250,
THL-251): the milestone path and the pearls it earns, monthly streaks,
opt-in challenges and the monthly recap.

**Milestones** are one ordered path with no phases (THL-238). Six are on
the path — your money, assessed; Anchor set up; a quarter there; half
there; covers 3 months; investing account opened — and three more earn a
pearl beside it: first treasure chest opened as planned, first $1,000
saved, 3 months within Allowance. "A quarter" and "half" are measured
toward the 3-month Anchor (THL-230). A pearl, once earned, is never taken
away (THL-53): what's earned is written down with its date, and a later
rough month changes nothing. Someone joining with history is placed from
what's already true (THL-50). Thresholds can be changed without an app
release (THL-54): an env var or a setting overrides the defaults.

**Streaks** are monthly (within Allowance; added to your Anchor) or
weekly (cleared Needs a look). A missed period starts a new run; the best
run is kept and never lowered. No "broke" copy, nothing in rose.

**Challenges** are opt-in, short, from her own spending, stoppable any
time. Going over the target is said plainly, never in rose. When one
finishes, what she saved can go into a treasure chest.

**The recap** is made once a month closes and leads with what went well.
Every pearl, new best and finished challenge is also an event
(`wins_events`), for notifications and analytics (THL-79).
"""

from __future__ import annotations

import calendar
import json
import os
from datetime import date, timedelta

from .analytics import counts_as_spending, invested_in, share_amount, spend_amount
from .categorize import group_of

# ── Milestones ──────────────────────────────────────────────────────────

# In the order the pearl collection shows them (W-03). `path` marks the six
# on the path, which `PATH` orders.
MILESTONES = [
    {"key": "assessed", "label": "Your money, assessed", "path": True,
     "how": "Get through your first full month"},
    {"key": "anchor_setup", "label": "Anchor set up", "path": True,
     "how": "Pick the savings that make up your Anchor"},
    {"key": "anchor_quarter", "label": "Anchor a quarter there", "path": True,
     "how": "Your Anchor reaches {quarter} of Essentials"},
    {"key": "anchor_half", "label": "Anchor half there", "path": True,
     "how": "Your Anchor reaches {half} of Essentials"},
    {"key": "chest_opened", "label": "First treasure chest opened as planned", "path": False,
     "how": "Spend from a chest once it’s full"},
    {"key": "saved_1000", "label": "First {saved} saved", "path": False,
     "how": "Put away {saved} in total"},
    {"key": "anchor_full", "label": "Anchor covers 3 months", "path": True,
     "how": "Your Anchor reaches 3 months of Essentials"},
    {"key": "three_within", "label": "{within} months within Allowance", "path": False,
     "how": "{within_words} months in a row within Allowance"},
    {"key": "invest", "label": "Investing account opened", "path": True,
     "how": "Open one wherever you like, then tell Pearl"},
]
PATH = ["assessed", "anchor_setup", "anchor_quarter", "anchor_half", "anchor_full", "invest"]

# Changeable without a release (THL-54): PEARL_WINS_THRESHOLDS (JSON) in
# the environment, or the `wins_thresholds` setting, overrides any of these.
DEFAULT_THRESHOLDS = {"quarter": 0.25, "half": 0.5, "full": 1.0, "saved": 1000.0,
                      "within_months": 3}
EARNED_KEY = "wins_earned"
EVENTS_KEY = "wins_events"
# The pearls she has been shown the "You earned a pearl" sheet for (THL-256):
# once per milestone, ever.
CELEBRATED_KEY = "wins_celebrated"
BEST_KEY = "wins_streak_best"
WEEKS_KEY = "wins_review_weeks"
RECAPS_KEY = "wins_recaps"
MAX_EVENTS = 200
MONTHS_OF_ESSENTIALS = 3


def _json(st, key: str, default):
    raw = st.setting(key)
    if raw in (None, ""):
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def thresholds(st=None) -> dict:
    out = dict(DEFAULT_THRESHOLDS)
    for raw in (os.environ.get("PEARL_WINS_THRESHOLDS"), st.setting("wins_thresholds") if st else None):
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(data, dict):
            for k, v in data.items():
                if k in out and isinstance(v, (int, float)) and v > 0:
                    out[k] = float(v) if k != "within_months" else int(v)
    return out


def _months_words(fraction: float) -> str:
    """"3 weeks" for a quarter of three months, "1½ months" for half."""
    months = fraction * MONTHS_OF_ESSENTIALS
    if abs(months - 0.75) < 0.01:
        return "3 weeks"
    if abs(months - round(months)) < 0.01:
        n = int(round(months))
        return f"{n} month{'' if n == 1 else 's'}"
    if abs(months - int(months) - 0.5) < 0.01:
        return f"{int(months)}½ months"
    return f"{months:.1f} months"


def _money(x: float) -> str:
    return f"${x:,.0f}" if abs(x - round(x)) < 0.005 else f"${x:,.2f}"


def _words(th: dict) -> dict:
    n = th["within_months"]
    return {"quarter": _months_words(th["quarter"]), "half": _months_words(th["half"]),
            "saved": _money(th["saved"]), "within": str(n),
            "within_words": {2: "Two", 3: "Three", 4: "Four", 6: "Six"}.get(n, str(n))}


def _month_add(month: str, n: int) -> str:
    y, m = int(month[:4]), int(month[5:7])
    total = y * 12 + m - 1 + n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _month_end(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    return f"{month}-{calendar.monthrange(y, m)[1]:02d}"


def month_name(month: str) -> str:
    return calendar.month_name[int(month[5:7])]


def day_words(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{calendar.month_abbr[d.month]} {d.day}"


# ── What's true now ─────────────────────────────────────────────────────

def saved_by_date(transactions, threshold: float) -> str | None:
    """The day the money put away first added up to `threshold`, or None."""
    rows = sorted((t for t in transactions if not t.excluded), key=lambda t: t.date)
    total = 0.0
    for t in rows:
        if (t.category or "") == "Saved":
            total += t.amount
        elif t.invested:
            total += t.invested
        if total >= threshold - 0.005:
            return t.date
    return None


def chest_opened_on(st) -> tuple[str | None, str | None]:
    """The first time a purchase was paid from a treasure chest that had the
    money in it: the day and the chest's name, or (None, None)."""
    from . import piggy
    charges = st.bank_charges_by_month()
    banks = {b.id: b for b in st.piggy_banks()}
    best = None
    for t in st.all_transactions():
        if t.bank_id is None or t.amount <= 0 or t.bank_id not in banks:
            continue
        bank = banks[t.bank_id]
        upto = {m: v for m, v in charges.get(bank.id, {}).items() if m <= t.month}
        status = piggy.status(bank, upto, today=t.date)
        if status["over"]:
            continue
        if best is None or t.date < best[0]:
            best = (t.date, bank.name)
    return best or (None, None)


def within_months(transactions, today: date, n: int = 12) -> list[dict]:
    """Each full month Pearl saw, oldest first: did spending stay within
    Allowance? `counted` is None for a month it couldn't tell."""
    from . import carryover
    from .usual_month import covered_months
    out = []
    for m in covered_months(transactions, today, n=n):
        r = carryover.result(transactions, m)
        out.append({"period": m, "counted": None if r is None else r["amount"] >= -0.005})
    return out


def anchor_months(transactions, today: date, started_on: str | None, n: int = 12) -> list[dict]:
    """Each full month since the Anchor was set up: was something put away?"""
    from .usual_month import covered_months
    if not started_on:
        return []
    first = started_on[:7]
    return [{"period": m, "counted": invested_in(transactions, m) > 0.005}
            for m in covered_months(transactions, today, n=n) if m >= first]


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def review_weeks(st, today: date, review_count: int, n: int = 12) -> list[dict]:
    """Weeks (Monday to Sunday) with Needs a look cleared. Pearl can only
    know a week it watched: each week it records whether the queue was
    empty at some point. A week counts once it has ended; the one under
    way is recorded but not yet in the run."""
    weeks = _json(st, WEEKS_KEY, {})
    this = week_start(today).isoformat()
    if review_count == 0:
        weeks[this] = True
    else:
        weeks.setdefault(this, False)
    keep = sorted(weeks)[-n * 2:]
    weeks = {k: weeks[k] for k in keep}
    st.set_setting(WEEKS_KEY, json.dumps(weeks, sort_keys=True))
    out = []
    cursor = week_start(today) - timedelta(weeks=n)
    for _ in range(n):
        k = cursor.isoformat()
        out.append({"period": k, "counted": weeks.get(k)})
        cursor += timedelta(weeks=1)
    return out


# ── Streaks ─────────────────────────────────────────────────────────────

STREAKS = [
    {"key": "within", "label": "Months within Allowance", "unit": "month",
     "starts": "Starts after your first full month",
     "rule": "A month counts when your spending stayed within Allowance. Months Pearl "
             "couldn’t see fully, like your first one, don’t count either way."},
    {"key": "anchor", "label": "Months you added to your Anchor", "unit": "month",
     "starts": "Starts once your Anchor is set up",
     "rule": "A month counts when you moved something to savings. Months before your Anchor "
             "was set up don’t count either way."},
    {"key": "review", "label": "Weeks you cleared Needs a look", "unit": "week",
     "starts": "Starts this week",
     "rule": "A week counts when Needs a look was empty at some point in it. Weeks before "
             "Pearl don’t count either way."},
]


def runs(periods: list[dict]) -> dict:
    """The current run (trailing counted periods), the best run, and the
    last period that didn't count before the current run."""
    this = 0
    missed = None
    for p in reversed(periods):
        if p["counted"] is True:
            this += 1
        elif p["counted"] is False:
            missed = p["period"]
            break
        # None: unknown, skip it
    best = run = 0
    for p in periods:
        if p["counted"] is True:
            run += 1
            best = max(best, run)
        elif p["counted"] is False:
            run = 0
    return {"this": this, "best": best, "missed": missed}


def period_words(n: int, unit: str) -> str:
    return f"{n} {unit}{'' if n == 1 else 's'}"


def streak(st, key: str, periods: list[dict], today: date, events: list, starts: str | None = None) -> dict:
    meta = next(s for s in STREAKS if s["key"] == key)
    unit = meta["unit"]
    known = [p for p in periods if p["counted"] is not None]
    r = runs(periods)
    stored = _json(st, BEST_KEY, {})
    before = int(stored.get(key, 0) or 0)
    best = max(before, r["best"])
    new_best = r["this"] > 0 and r["this"] >= best and r["this"] > before
    if best > before:
        stored[key] = best
        st.set_setting(BEST_KEY, json.dumps(stored, sort_keys=True))
    if new_best:
        events.append({"kind": "streak_best", "key": key, "run": r["this"], "on": today.isoformat()})
    note = None
    if r["missed"] and r["this"] > 0:
        after = (_month_add(r["missed"], 1) if unit == "month"
                 else (date.fromisoformat(r["missed"]) + timedelta(weeks=1)).isoformat())
        when = month_name(r["missed"]) if unit == "month" else f"the week of {day_words(r['missed'])}"
        then = month_name(after) if unit == "month" else f"the week of {day_words(after)}"
        verb = "went over" if key == "within" else "was missed"
        note = (f"{when[0].upper() + when[1:]} {verb}. A new run started in {then}, and your best "
                f"run of {period_words(best, unit)} is kept.")
    elif new_best and r["this"] > 1:
        first = next((p["period"] for p in periods[-r["this"]:] if p["counted"]), None)
        since = month_name(first) if unit == "month" and first else (f"the week of {day_words(first)}" if first else "")
        what = {"within": "stayed within Allowance",
                "anchor": "put something toward your Anchor",
                "review": "cleared Needs a look"}[key]
        note = f"Every {unit} since {since}, you’ve {what}." if since else None
    return {
        "key": key, "label": meta["label"], "unit": unit,
        "this": r["this"], "best": best, "new_best": new_best,
        "started": bool(known),
        "starts": starts or meta["starts"], "rule": meta["rule"],
        "this_words": period_words(r["this"], unit) if known else (starts or meta["starts"]),
        "best_words": (f"Best {best}" + (" · new best" if new_best else "")) if known else "",
        "note": note,
        "periods": periods[-12:],
    }


def _streaks(st, transactions, today: date, anchor: dict, review_count: int, events: list) -> list[dict]:
    series = {
        "within": within_months(transactions, today),
        "anchor": anchor_months(transactions, today, anchor.get("started_on") if anchor.get("started") else None),
        "review": review_weeks(st, today, review_count),
    }
    starts = {}
    if anchor.get("started"):
        # Set up this month: the first month that can count is the next full one.
        starts["anchor"] = f"Counts from {month_name(_month_add(today.isoformat()[:7], 1))}"
    return [streak(st, s["key"], series[s["key"]], today, events, starts.get(s["key"])) for s in STREAKS]


# ── Challenges ──────────────────────────────────────────────────────────

# Changeable without a release (THL-250): PEARL_WINS_CHALLENGES (JSON) in
# the environment, or the `wins_challenges` setting, replaces the list.
DEFAULT_CATALOGUE = [
    {"kind": "coffee", "title": "Coffee for a month", "category": "Coffee", "span": "month",
     "cut": 0.3, "direction": "under"},
    {"kind": "no_spend_weekend", "title": "No-spend weekend", "group": "lifestyle", "span": "weekend",
     "target": 0, "direction": "under"},
    {"kind": "cook_at_home", "title": "Cook-at-home week", "category": "Dining", "span": "week",
     "cut": 0.3, "direction": "under"},
    {"kind": "subscription_sweep", "title": "Subscription sweep", "span": "30", "target": 0,
     "direction": "under", "pick": "subscription"},
    {"kind": "anchor_boost", "title": "30-day Anchor boost", "span": "30", "extra": 100,
     "direction": "over"},
]


def catalogue(st=None) -> list[dict]:
    for raw in (st.setting("wins_challenges") if st else None, os.environ.get("PEARL_WINS_CHALLENGES")):
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(data, list) and data:
            return data
    return DEFAULT_CATALOGUE


def _spent_in(transactions, first: str, last: str, *, category: str | None = None,
              group: str | None = None, merchant: str | None = None, weekends_only: bool = False) -> float:
    total = 0.0
    for t in transactions:
        if t.date < first or t.date > last or not counts_as_spending(t):
            continue
        cat = t.category or "Other"
        if category and cat != category:
            continue
        if group and group_of(cat) != group:
            continue
        if merchant and (t.merchant or "").lower() != merchant.lower():
            continue
        if weekends_only and date.fromisoformat(t.date).weekday() < 5:
            continue
        total += share_amount(t)
    return round(total, 2)


def _round5(x: float) -> float:
    return float(max(5, int(round(x / 5.0)) * 5))


def window(kind_def: dict, today: date) -> tuple[str, str]:
    span = str(kind_def.get("span", "30"))
    if span == "month":
        return today.isoformat(), _month_end(today.strftime("%Y-%m"))
    if span == "weekend":
        sat = today + timedelta(days=(5 - today.weekday()) % 7)
        if today.weekday() == 6:                         # a Sunday: next weekend
            sat = today + timedelta(days=6)
        return sat.isoformat(), (sat + timedelta(days=1)).isoformat()
    days = 7 if span == "week" else int(span)
    return today.isoformat(), (today + timedelta(days=days - 1)).isoformat()


def suggestions(st, transactions, today: date, usual: dict, anchor: dict) -> list[dict]:
    """The catalogue with her numbers in it; only the ones Pearl can price."""
    from .insights.recurring import detect_recurring, recurring_summary
    last_month = _month_add(today.strftime("%Y-%m"), -1)
    active = {c["kind"] for c in st.challenges() if c["status"] == "active"}
    cats = usual.get("categories") or {}
    out = []
    for d in catalogue(st):
        kind = d["kind"]
        if kind in active:
            continue
        first, last = window(d, today)
        item = {"kind": kind, "title": d["title"], "start": first, "end": last,
                "direction": d.get("direction", "under"), "category": d.get("category"),
                "group": d.get("group")}
        if kind == "coffee" or (d.get("category") and str(d.get("span")) == "month"):
            cat = d["category"]
            spent = _spent_in(transactions, f"{last_month}-01", _month_end(last_month), category=cat)
            if spent < 10:
                continue
            target = _round5(spent * (1 - d.get("cut", 0.3)))
            item.update({"baseline": spent, "target": target,
                         "line": f"You spent {_money(spent)} on {cat.lower()} in {month_name(last_month)}. Try {_money(target)}.",
                         "counts": f"Everything sorted as {cat} from today to {month_name(last)[:3] if False else month_name(last[:7])} {int(last[8:10])}."})
        elif kind == "no_spend_weekend":
            months = usual.get("months") or []
            if not months:
                continue
            per = []
            for m in months:
                per.append(_spent_in(transactions, f"{m}-01", _month_end(m), group="lifestyle", weekends_only=True))
            weekends = sum(per) / len(per) / 4.33 if per else 0
            if weekends < 10:
                continue
            item.update({"baseline": round(weekends, 2), "target": 0.0,
                         "line": f"Your weekends average {_money(round(weekends))} of Lifestyle.",
                         "counts": f"Lifestyle spending on {month_name(first[:7])} {int(first[8:10])} and {int(last[8:10])}."})
        elif kind == "cook_at_home":
            cat = d.get("category", "Dining")
            usual_cat = (cats.get(cat) or {}).get("usual", 0)
            if usual_cat < 20:
                continue
            month = today.strftime("%Y-%m")
            so_far = _spent_in(transactions, f"{month}-01", today.isoformat(), category=cat)
            by_today = usual_cat * today.day / calendar.monthrange(today.year, today.month)[1]
            weekly = usual_cat / 30 * 7
            target = _round5(weekly * (1 - d.get("cut", 0.3)))
            above = (so_far / by_today - 1) if by_today > 0 else 0
            line = (f"Dining out ran {int(round(above * 100))}% above usual this month."
                    if above > 0.05 else f"A week of dining out is usually about {_money(round(weekly))}.")
            item.update({"baseline": round(weekly, 2), "target": target, "line": line,
                         "counts": f"Everything sorted as {cat} for the next 7 days."})
        elif kind == "subscription_sweep":
            recs = detect_recurring(transactions)
            summary = recurring_summary(recs)
            if summary["count"] == 0:
                continue
            subs = [{"merchant": r["merchant"], "monthly": round(r["monthly_cost"], 2)}
                    for r in recs if r["active"]]
            subs.sort(key=lambda s: -s["monthly"])
            item.update({"baseline": summary["monthly_total"], "target": 0.0, "options": subs[:8],
                         "line": f"{summary['count']} subscription{'' if summary['count'] == 1 else 's'} · "
                                 f"about {_money(summary['annual_total'])} a year. Pick one to cancel.",
                         "counts": "No charge from the one you pick for 30 days."})
        elif kind == "anchor_boost":
            if not anchor.get("started"):
                continue
            pace = (anchor.get("pace") or {}).get("usual") or 0
            base = max(float(pace), 0.0)
            extra = float(d.get("extra", 100))
            item.update({"baseline": round(base, 2), "target": round(base + extra, 2),
                         "line": f"Put away {_money(extra)} more than usual in 30 days.",
                         "counts": "Transfers you mark as Saved over the next 30 days."})
        else:
            continue
        out.append(item)
    return out


def progress(transactions, c: dict, today: date) -> dict:
    """Where a challenge stands: spent (or put away), the pace, days left."""
    first, last = c["start"], min(c["end"], today.isoformat()) if c["status"] == "active" else c["end"]
    kind = c["kind"]
    if kind == "anchor_boost":
        done = 0.0
        for t in transactions:
            if first <= t.date <= last and not t.excluded:
                if (t.category or "") == "Saved":
                    done += t.amount
                elif t.invested:
                    done += t.invested
        done = round(max(done, 0.0), 2)
    elif kind == "no_spend_weekend":
        done = _spent_in(transactions, first, last, group="lifestyle")
    elif kind == "subscription_sweep":
        done = _spent_in(transactions, first, last, merchant=c.get("merchant"))
    else:
        done = _spent_in(transactions, first, last, category=c.get("category"))
    end = date.fromisoformat(c["end"])
    start = date.fromisoformat(c["start"])
    total_days = (end - start).days + 1
    elapsed = min(max((today - start).days + 1, 0), total_days)
    days_left = max((end - today).days, 0) if c["status"] == "active" else 0
    target = float(c["target"])
    over = kind != "anchor_boost" and done > target + 0.005
    share = min(done / target, 1.0) if target > 0 else (1.0 if done > 0 else 0.0)
    # On pace: at this rate the window ends under last time's figure (or the
    # target, when there is no last time); for the Anchor boost, over it.
    projected = done / elapsed * total_days if elapsed else 0.0
    bar = float(c.get("baseline") or target)
    on_pace = projected >= target if kind == "anchor_boost" else projected <= bar + 0.005
    return {"done": done, "target": target, "share": round(share, 4), "over": over, "on_pace": on_pace,
            "days_left": days_left, "elapsed": elapsed, "total_days": total_days}


def _noun(c: dict) -> str:
    return {"coffee": "coffee", "cook_at_home": "dining out", "no_spend_weekend": "Lifestyle",
            "subscription_sweep": (c.get("merchant") or "that subscription"),
            "anchor_boost": "put away"}.get(c["kind"], (c.get("category") or "it").lower())


def challenge_words(c: dict, p: dict, today: date) -> dict:
    """What the card and the panel say, in every state. Nothing in rose."""
    kind, noun = c["kind"], _noun(c)
    base = c.get("baseline")
    last_month = _month_add(c["start"][:7], -1)
    out = {"title": c["title"], "status": c["status"], "tone": "champagne" if p["over"] else "brand"}
    if c["status"] == "active":
        if kind == "anchor_boost":
            out["line"] = (f"{_money(p['done'])} of {_money(p['target'])} put away. "
                           + ("On pace." if p["on_pace"] else "A little behind pace; anything you move counts."))
        elif p["over"]:
            out["line"] = f"{_money(p['done'])} of {_money(p['target'])}. Over the target; the rest of the window still counts."
        elif p["on_pace"] and base:
            out["line"] = (f"{_money(p['done'])} of {_money(p['target'])}. You’re on pace to spend less than "
                           f"{month_name(last_month)}’s {_money(base)}.")
        else:
            out["line"] = f"{_money(p['done'])} of {_money(p['target'])}."
        out["short"] = f"{_money(p['done'])} of {_money(p['target'])}"
        out["days"] = f"{p['days_left']} day{'' if p['days_left'] == 1 else 's'} left"
        return out
    r = c.get("result") or {}
    spent = r.get("spent", p["done"])
    if c["status"] == "stopped":
        days = r.get("days", p["elapsed"])
        out["title"] = "Challenge stopped"
        out["line"] = (f"You put away {_money(spent)} in {days} day{'' if days == 1 else 's'}. "
                       if kind == "anchor_boost" else
                       f"You spent {_money(spent)} on {noun} in {days} day{'' if days == 1 else 's'}. ") \
            + "Try again any time, or pick another challenge."
        return out
    # Finished.
    saved = r.get("saved", 0.0)
    if kind == "anchor_boost":
        out["title"] = f"You put away {_money(spent)}"
        out["line"] = (f"That’s {_money(spent - (base or 0))} more than usual. Nicely done."
                       if spent > (base or 0) + 0.005 else "About your usual pace. Every bit counts.")
        out["saved"] = 0.0
    else:
        out["title"] = f"You spent {_money(spent)} on {noun}"
        if saved > 0.005 and base:
            out["line"] = f"That’s {_money(saved)} less than {month_name(last_month)}. Nicely done."
        elif base:
            out["line"] = f"About the same as {month_name(last_month)}. Try again any time."
        else:
            out["line"] = "Done. Try again any time."
        out["saved"] = saved
    return out


def _close_challenges(st, transactions, today: date, events: list) -> None:
    for c in st.challenges():
        if c["status"] != "active" or c["end"] >= today.isoformat():
            continue
        p = progress(transactions, c, today)
        saved = round(max((c.get("baseline") or 0) - p["done"], 0.0), 2) if c["kind"] != "anchor_boost" else 0.0
        result = {"spent": p["done"], "saved": saved, "over": p["over"]}
        st.end_challenge(c["id"], "finished", c["end"], result)
        events.append({"kind": "challenge_finished", "key": c["kind"], "id": c["id"],
                       "saved": saved, "on": c["end"]})


# ── The recap ───────────────────────────────────────────────────────────

def _recap_for(st, transactions, month: str, earned: dict, streaks: list[dict], usual: dict,
               anchor: dict) -> dict:
    from . import carryover
    r = carryover.result(transactions, month)
    within = None if r is None else r["amount"] >= -0.005
    put_away = round(invested_in(transactions, month), 2)
    finished = [c for c in st.challenges()
                if c["status"] == "finished" and (c.get("ended_on") or c["end"])[:7] == month]
    well = []
    if within:
        well.append({"key": "within", "text": "You stayed within Allowance.", "share": "Stayed within my plan"})
    if put_away > 0:
        well.append({"key": "put_away", "text": f"You put away {_money(put_away)}.",
                     "share": "Kept building my Anchor" if anchor.get("started") else "Put money away",
                     "amount": put_away})
    for c in finished:
        saved = (c.get("result") or {}).get("saved", 0)
        what = c["title"].lower()
        if saved > 0.005:
            well.append({"key": f"challenge:{c['id']}",
                         "text": f"You finished a {what}: {_money(saved)} less on {_noun(c)}.",
                         "share": f"Finished a {what}", "amount": saved})
        else:
            well.append({"key": f"challenge:{c['id']}", "text": f"You finished a {what}.",
                         "share": f"Finished a {what}"})
    pearls = [{"key": k, "label": label_for(k, st), "on": v["on"]}
              for k, v in earned.items() if (v.get("on") or "")[:7] == month]
    if not well:
        well.append({"key": "kept_going", "text": "You kept going, and every month Pearl sees makes the next one clearer.",
                     "share": "Kept going"})
    anchor_pearl = any(p["key"].startswith("anchor") for p in pearls)
    title = ("A good month for your Anchor" if anchor_pearl or (put_away > 0 and within)
             else "A month within plan" if within else f"{month_name(month)}, in short")
    lines = []
    for s in streaks:
        if not s["started"]:
            continue
        name = {"within": "Within Allowance", "anchor": "Added to your Anchor",
                "review": "Cleared Needs a look"}[s["key"]]
        if s["this"] >= 2:
            lines.append(f"{name}: {period_words(s['this'], s['unit'])} in a row.")
        elif s["this"] == 1:
            lines.append(f"{name}: a new run started.")
    opportunity = None
    cats = usual.get("categories") or {}
    worst = None
    for cat, info in cats.items():
        spent = _spent_in(transactions, f"{month}-01", _month_end(month), category=cat)
        if info["usual"] >= 20 and spent > info["usual"] * 1.1:
            ratio = spent / info["usual"]
            if worst is None or ratio > worst[1]:
                worst = (cat, ratio)
    if worst:
        cat, ratio = worst
        how = "a little above usual" if ratio < 1.35 else "above usual"
        name = {"Dining": "Dining out", "Coffee": "Coffee"}.get(cat, cat)
        challenge = {"Dining": "cook_at_home", "Coffee": "coffee"}.get(cat)
        helps = {"cook_at_home": "A cook-at-home week could help.", "coffee": "Coffee for a month could help."}
        opportunity = {"text": f"{name} ran {how}. {helps.get(challenge, 'A short challenge could help.')}",
                       "challenge": challenge, "category": cat}
    return {"month": month, "title": title, "went_well": well, "pearls": pearls,
            "streaks": " ".join(lines), "opportunity": opportunity, "within": within,
            "put_away": put_away, "made_on": None}


def label_for(key: str, st=None) -> str:
    th = thresholds(st)
    m = next((m for m in MILESTONES if m["key"] == key), None)
    return m["label"].format(**_words(th)) if m else key


# ── Everything together ─────────────────────────────────────────────────

def evaluate(st, transactions, today: date, *, anchor: dict, path: dict, review_count: int,
             invest_done: bool, usual: dict | None = None) -> dict:
    """Work out every milestone, streak, challenge and recap as they stand,
    write down what's newly earned, and answer with the whole Wins page."""
    th = thresholds(st)
    words = _words(th)
    events = []
    earned = _json(st, EARNED_KEY, {})
    earned = earned if isinstance(earned, dict) else {}
    usual = usual or {}

    _close_challenges(st, transactions, today, events)
    streaks = _streaks(st, transactions, today, anchor, review_count, events)
    within = next(s for s in streaks if s["key"] == "within")

    counted = float(anchor.get("counted") or 0)
    target = float(anchor.get("target") or 0)
    share = counted / target if target > 0 else 0.0
    chest_on, chest_name = chest_opened_on(st)
    saved_on = saved_by_date(transactions, th["saved"])
    within_run = runs(within["periods"])
    three_on = None
    if within_run["this"] >= th["within_months"] or within_run["best"] >= th["within_months"]:
        # The day after the month that completed the run.
        run = 0
        for p in within["periods"]:
            if p["counted"] is True:
                run += 1
                if run == th["within_months"] and three_on is None:
                    three_on = f"{_month_add(p['period'], 1)}-01"
            elif p["counted"] is False:
                run = 0

    # A pearl earned from her bank history is dated the day Pearl could see it,
    # never before she started: "Earned Jan 1" on her first day would be odd.
    joined = (st.setting("protect_done_on") or today.isoformat())[:10]
    saved_on = max(saved_on, joined) if saved_on else None
    three_on = max(three_on, joined) if three_on else None

    now = {
        "assessed": (bool(path.get("protect_done")), st.setting("protect_done_on") or today.isoformat(), None),
        "anchor_setup": (bool(anchor.get("started")), anchor.get("started_on") or today.isoformat(), None),
        "anchor_quarter": (target > 0 and share >= th["quarter"] - 1e-9, today.isoformat(), None),
        "anchor_half": (target > 0 and share >= th["half"] - 1e-9, today.isoformat(), None),
        "anchor_full": (bool(anchor.get("earned")), anchor.get("earned_on") or today.isoformat(), None),
        "chest_opened": (chest_on is not None, chest_on, chest_name),
        "saved_1000": (saved_on is not None, saved_on, None),
        "three_within": (three_on is not None, three_on, None),
        "invest": (bool(invest_done), today.isoformat(), None),
    }
    changed = False
    for m in MILESTONES:
        key = m["key"]
        done, on, note = now[key]
        if done and key not in earned:
            earned[key] = {"on": (on or today.isoformat())[:10], "note": note}
            events.append({"kind": "milestone_earned", "key": key, "on": earned[key]["on"]})
            changed = True
    if changed:
        st.set_setting(EARNED_KEY, json.dumps(earned, sort_keys=True))

    pearls = []
    for m in MILESTONES:
        key = m["key"]
        e = earned.get(key)
        pearls.append({
            "key": key, "label": m["label"].format(**words), "path": m["path"],
            "earned": e is not None, "on": e["on"] if e else None,
            "note": e.get("note") if e else None,
            "how": m["how"].format(**words),
        })
    earned_count = sum(1 for p in pearls if p["earned"])

    # The path: six, in order, with the next one called out.
    by_key = {p["key"]: p for p in pearls}
    next_key = next((k for k in PATH if not by_key[k]["earned"]), None)
    path_items = []
    for k in PATH:
        p = by_key[k]
        state = "earned" if p["earned"] else "next" if k == next_key else "todo"
        when = day_words(p["on"]) if p["earned"] else None
        if state == "next":
            if k.startswith("anchor_") and k != "anchor_setup" and target > 0:
                when = f"Next · {int(round(share * 100))}%"
            elif k == "assessed":
                when = "After your first full month"
            else:
                when = "Next"
        elif state == "todo":
            when = "Any time after" if k == "invest" and next_key not in (None, "assessed", "anchor_setup") else "Comes later"
        path_items.append({**p, "state": state, "when": when})
    done_on_path = sum(1 for k in PATH if by_key[k]["earned"])
    first_month_away = done_on_path == 0 and not path.get("protect_done")
    heading = ("Your first milestone is a month away" if first_month_away
               else f"{done_on_path} of {len(PATH)} milestones on your path")
    nxt = next_step(next_key, anchor, share)

    recaps = _json(st, RECAPS_KEY, {})
    recaps = recaps if isinstance(recaps, dict) else {}
    last_month = _month_add(today.strftime("%Y-%m"), -1)
    covered = {p["period"] for p in within["periods"]}
    if last_month not in recaps and last_month in covered:
        recap = _recap_for(st, transactions, last_month, earned, streaks, usual, anchor)
        recap["made_on"] = today.isoformat()
        recaps[last_month] = recap
        keep = sorted(recaps)[-12:]
        recaps = {k: recaps[k] for k in keep}
        st.set_setting(RECAPS_KEY, json.dumps(recaps, sort_keys=True))
        events.append({"kind": "recap_ready", "key": last_month, "on": today.isoformat()})
    latest = recaps.get(max(recaps)) if recaps else None

    if events:
        log = _json(st, EVENTS_KEY, [])
        log = (log if isinstance(log, list) else []) + events
        st.set_setting(EVENTS_KEY, json.dumps(log[-MAX_EVENTS:]))

    challenges = []
    for c in st.challenges():
        p = progress(transactions, c, today)
        challenges.append({**c, "progress": p, "words": challenge_words(c, p, today)})
    active = [c for c in challenges if c["status"] == "active"]
    suggested = suggestions(st, transactions, today, usual, anchor)

    return {
        "month": today.strftime("%Y-%m"),
        "heading": heading,
        "first_month_away": first_month_away,
        "path": path_items,
        "done": done_on_path, "of": len(PATH),
        "next": nxt,
        "pearls": sorted(pearls, key=lambda p: (not p["earned"], MILESTONES.index(next(m for m in MILESTONES if m["key"] == p["key"])))),
        "earned": earned_count, "total": len(pearls),
        "streaks": streaks,
        "recap": latest,
        "recaps": sorted(recaps),
        "next_recap": month_name(_month_add(today.strftime("%Y-%m"), 1)),
        "challenges": {"active": active, "past": [c for c in challenges if c["status"] != "active"][:6],
                       "suggested": suggested, "ready": bool(usual.get("months"))},
        "suggestion": save_suggestion(earned),
        "events": events,
        "thresholds": th,
    }


def next_step(key: str | None, anchor: dict, share: float) -> dict:
    """The one next step on the path, in her numbers (W-01, W-03)."""
    if key is None:
        return {"key": None, "title": "Every milestone on your path is done.",
                "line": "What you’ve built stays yours.", "label": None, "action": None}
    if key == "assessed":
        return {"key": key, "title": "Next: your money, assessed",
                "line": "After your first full month in Pearl, you’ll see where your money goes: what you "
                        "need, what you choose, and what’s left to build with.",
                "label": "Sort your first transactions", "action": "review"}
    if key == "anchor_setup":
        return {"key": key, "title": "Next: set up your Anchor",
                "line": "Pick the savings that make up your Anchor. The milestone is 3 months of Essentials.",
                "label": "Set up your Anchor", "action": "goals:start"}
    if key in ("anchor_quarter", "anchor_half", "anchor_full"):
        counted, target, to_go = anchor.get("counted") or 0, anchor.get("target") or 0, anchor.get("to_go") or 0
        p = anchor.get("projection") or {}
        when = (f" · likely {month_name(p['from'])} {p['from'][:4]} to {month_name(p['to'])} {p['to'][:4]}"
                if p.get("state") == "range" else "")
        line = (f"{_money(counted)} of {_money(target)} · {_money(to_go)} to go{when}" if target > 0
                else "Pearl needs a full month to work out your milestone.")
        return {"key": key, "title": "Next: grow your Anchor to 3 months", "line": line,
                "label": "See your Anchor", "action": "goals:anchor"}
    return {"key": key, "title": "Next: open an investing account, any time",
            "line": "Open one wherever you like, then tell Pearl. Guidance, not a gate.",
            "label": "Tell Pearl", "action": "invested"}


def save_suggestion(earned: dict) -> dict | None:
    """"New for you in Save": what a reached milestone makes a good next read.
    Learn and the calculator are open from day one; this only points."""
    if "anchor_full" in earned:
        return {"text": "Your Anchor covers 3 months. The growth calculator in Save shows what regular investing could grow to.",
                "to": "calculator", "label": "Open Save"}
    if "anchor_half" in earned:
        return {"text": "Your Anchor is half there. The growth calculator in Save is a good next read.",
                "to": "calculator", "label": "Open Save"}
    if "anchor_setup" in earned:
        return {"text": "Your Anchor is set up. Learn’s TFSA, RRSP and FHSA in Save is a good next read.",
                "to": "learn", "label": "Open Save"}
    return None


# ── "You earned a pearl" (THL-112 EP-01 to EP-05; THL-256) ───────────────

def celebrated(st) -> list[str]:
    out = _json(st, CELEBRATED_KEY, [])
    return out if isinstance(out, list) else []


def mark_celebrated(st, keys: list[str]) -> list[str]:
    seen = celebrated(st)
    for k in keys:
        if k not in seen:
            seen.append(k)
    st.set_setting(CELEBRATED_KEY, json.dumps(seen))
    return seen


def moment_line(key: str, pearl: dict, anchor: dict, th: dict) -> str:
    """One line under the title, in her numbers (EP-01: "$8,700 ready for
    a big surprise. It’s in your collection on Wins.")."""
    target = float(anchor.get("target") or 0)
    counted = float(anchor.get("counted") or 0)
    words = _words(th)
    lines = {
        "assessed": "Your income, bills and first month are sorted.",
        "anchor_setup": "Your Anchor is set up and counting.",
        "anchor_quarter": (f"{_money(counted)} toward 3 months of Essentials." if counted > 0
                           else "A quarter of the way to 3 months of Essentials."),
        "anchor_half": (f"{_money(counted)} toward 3 months of Essentials." if counted > 0
                        else "Halfway to 3 months of Essentials."),
        "anchor_full": (f"{_money(target)} ready for a big surprise." if target > 0
                        else "Three months of Essentials, ready for a big surprise."),
        "chest_opened": (f"{pearl['note']} opened as planned." if pearl.get("note")
                         else "A treasure chest opened as planned."),
        "saved_1000": f"{words['saved']} put away in total.",
        "three_within": f"{words['within_words']} months in a row within Allowance.",
        "invest": "An investing account, opened.",
    }
    return lines.get(key, "")


def moment(st, page: dict, anchor: dict) -> dict:
    """What the sheet says, or `show: False`. Several earned since the last
    look make one sheet ("You earned 2 pearls"), played once (EP-03)."""
    th = thresholds(st)
    seen = set(celebrated(st))
    fresh = [p for p in page.get("pearls", []) if p.get("earned") and p["key"] not in seen]
    # In the order the collection shows them, oldest earned first.
    fresh.sort(key=lambda p: (p.get("on") or "", MILESTONES.index(next(m for m in MILESTONES if m["key"] == p["key"]))))
    if not fresh:
        return {"show": False, "pearls": [], "title": "", "line": "", "overline": ""}
    pearls = [{"key": p["key"], "label": p["label"], "on": p.get("on"),
               "line": moment_line(p["key"], p, anchor, th)} for p in fresh]
    if len(pearls) == 1:
        title = pearls[0]["label"]
        line = f"{pearls[0]['line']} It’s in your collection on Wins.".strip()
        overline = "Pearl earned"
    else:
        title = f"You earned {len(pearls)} pearls"
        names = [p["label"] for p in pearls]
        line = f"{', '.join(names[:-1])} and {names[-1]}. They’re in your collection on Wins."
        overline = "Pearls earned"
    return {"show": True, "pearls": pearls, "title": title, "line": line, "overline": overline,
            "announce": f"{overline}. {title}."}
