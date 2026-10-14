"""Income and recurring bills, confirmed (Pearl THL-45, designed in THL-127).

The first-session check after a bank is linked (I-01 to I-06), and the same
answers behind Profile › Income and bills afterwards:

* I-01 "Is this your paycheque?": pay candidates are regular deposits from
  one payer — a gap of about 7, 14, 15 or 30 days and a similar amount over
  the last three months. Repayments (e-Transfers matched to a split, THL-124)
  and e-Transfers that look like a friend paying back are never candidates,
  and never Income. Only an employer or another payer counts.
* I-02 "Edit your pay": name, usual amount after tax, how often, next date.
* I-03 "No pay found": an expected monthly income, which is the same figure
  as the income she tells Home (`home_income`): one number, not two.
  "My income varies" plans with the lowest of the last three months once
  there is data for it.
  "Skip for now" is remembered, so Home can make a rough estimate from the
  deposits it has seen instead of showing no number (H-03).
* I-04 "Are these your regular bills?": the recurring bills Pearl found,
  high-confidence ones pre-ticked. What she leaves ticked counts; what she
  unticks stops counting in "Bills still to come". Rent paid by e-Transfer is
  asked about first (only when that pattern exists); "Yes" names it Rent,
  files it under Essentials, and is remembered for that recipient.
* I-05 "Add or edit a bill": a bill she adds counts from its next due date.
* I-06 "All set": income each month and regular bills each month.

Her answers live in one setting (`income_bills`, JSON). Before she has run
the check nothing changes: safe-to-spend and the path keep their old rules.
"""

from __future__ import annotations

import json
import re
import statistics
from datetime import date, timedelta

from .analytics import is_others
from .income import is_income, kind_of
from .models import Transaction

KEY = "income_bills"

PAY_CADENCES = ("weekly", "biweekly", "semimonthly", "monthly", "irregular")
# A typical month, as I-06 counts it ("Pay 2 × $2,150"): months with a third
# paycheque are a bonus, not the plan.
PAY_PER_MONTH = {"weekly": 4, "biweekly": 2, "semimonthly": 2, "monthly": 1, "irregular": 1}

BILL_CADENCES = ("weekly", "biweekly", "monthly", "bimonthly", "quarterly",
                 "semiannual", "annual")
PER_YEAR = {"weekly": 52, "biweekly": 26, "monthly": 12, "bimonthly": 6,
            "quarterly": 4, "semiannual": 2, "annual": 1}
MONTHS_APART = {"monthly": 1, "bimonthly": 2, "quarterly": 3, "semiannual": 6, "annual": 12}

# Pre-ticked in I-04 only at this confidence (THL-127: "Only high-confidence
# matches are pre-ticked").
TICK_CONFIDENCE = 0.6
# Rent by e-Transfer is asked about only from this much a month: a $20
# e-Transfer every month is a friend, not a landlord.
RENT_MIN = 200.0
RENT = "Rent & Housing"
PAY_LOOKBACK_DAYS = 100
MAX_NAME = 60
MAX_AMOUNT = 1_000_000

_ETRANSFER = re.compile(r"\b(e-?\s?transfer|e-?tfr|etfr|interac|autodeposit)\b", re.I)


# ── Her answers ──────────────────────────────────────────────────────────

def empty() -> dict:
    return {"income_on": None, "bills_on": None, "pays": [], "pay_no": [],
            "varies": False, "bills": {}, "added": [], "rent": {}, "seq": 0,
            "income_skipped": None}


def load(st) -> dict:
    """Her answers, with every field present."""
    raw = st.setting(KEY)
    out = empty()
    if raw:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            data = {}
        if isinstance(data, dict):
            out.update({k: v for k, v in data.items() if k in out})
    return out


def save(st, state: dict) -> None:
    st.set_setting(KEY, json.dumps(state, sort_keys=True))


def next_id(state: dict, prefix: str) -> str:
    state["seq"] = int(state.get("seq") or 0) + 1
    return f"{prefix}{state['seq']}"


def checked(state: dict | None) -> bool:
    """Has she answered the income part of the check?"""
    return bool(state and state.get("income_on"))


# ── Small date helpers ──────────────────────────────────────────────────

def _d(iso: str) -> date:
    return date.fromisoformat(iso[:10])


def _on_day(year: int, month: int, day: int) -> date:
    import calendar
    last = calendar.monthrange(year, month)[1]
    return date(year, month, last if day >= 28 else min(day, last))


def _add_months(d: date, n: int, day: int | None = None) -> date:
    m = d.month - 1 + n
    return _on_day(d.year + m // 12, m % 12 + 1, day or d.day)


def occurrences(anchor: date, cadence: str, start: date, end: date) -> list[date]:
    """Every date on a schedule through `anchor` that falls in [start, end]."""
    out: list[date] = []
    if cadence in ("weekly", "biweekly"):
        step = 7 if cadence == "weekly" else 14
        offset = (start - anchor).days
        k = -(-offset // step)          # ceil
        d = anchor + timedelta(days=k * step)
        while d <= end:
            out.append(d)
            d += timedelta(days=step)
        return out
    if cadence == "semimonthly":
        days = (anchor.day, anchor.day + 15) if anchor.day <= 15 else (anchor.day - 15, anchor.day)
        cursor = start.replace(day=1)
        while cursor <= end:
            for day in days:
                d = _on_day(cursor.year, cursor.month, day)
                if start <= d <= end:
                    out.append(d)
            cursor = _add_months(cursor, 1, 1)
        return sorted(set(out))
    gap = MONTHS_APART.get(cadence)
    if not gap:
        return out
    # Walk back from the anchor to before `start`, then forward.
    d, k = anchor, 0
    while d > start:
        k -= gap
        d = _add_months(anchor, k, anchor.day)
    while d <= end:
        if d >= start:
            out.append(d)
        k += gap
        d = _add_months(anchor, k, anchor.day)
    return out


# ── I-01: pay candidates ────────────────────────────────────────────────

def looks_like_etransfer(t: Transaction) -> bool:
    raw = t.raw or {}
    return bool(_ETRANSFER.search(" ".join(str(x or "") for x in (
        t.description, t.merchant, raw.get("counterparty")))))


def payer_of(t: Transaction) -> str:
    return (t.merchant or t.description or "").strip()


def could_be_pay(t: Transaction) -> bool:
    """A deposit that could be pay: income, from an employer or another
    payer. A repayment (THL-124) never is, and neither is an e-Transfer that
    isn't marked salary — that's a friend paying back, not a paycheque."""
    if not is_income(t) or t.repays or is_others(t):
        return False
    kind = kind_of(t)
    if kind in ("interest", "tax_refund", "gifts", "bonus"):
        return False
    if looks_like_etransfer(t) and kind != "salary":
        return False
    return True


def _cadence_of(days: list[date]) -> str | None:
    gaps = [(b - a).days for a, b in zip(days, days[1:])]
    if not gaps:
        return None
    gap = statistics.median(gaps)
    if 5 <= gap <= 9:
        return "weekly"
    if sum(1 for g in gaps if g == 14) / len(gaps) >= 0.6 or (13 <= gap <= 14.5 and all(12 <= g <= 16 for g in gaps)):
        return "biweekly"
    if 12 <= gap <= 18:
        return "semimonthly"
    if 25 <= gap <= 35:
        return "monthly"
    return None


def predict_next(days: list[date], cadence: str, today: date) -> date:
    last = days[-1]
    if cadence in ("weekly", "biweekly"):
        step = 7 if cadence == "weekly" else 14
        d = last + timedelta(days=step)
        while d <= today:
            d += timedelta(days=step)
        return d
    if cadence == "semimonthly":
        # The two days of the month pay comes on, from the last few.
        upcoming = occurrences(last, "semimonthly", today + timedelta(days=1),
                               today + timedelta(days=40))
        return upcoming[0] if upcoming else last + timedelta(days=15)
    d = last
    while d <= today:
        d = _add_months(d, 1, last.day)
    return d


def pay_candidates(transactions: list[Transaction], today: date,
                   state: dict | None = None) -> list[dict]:
    """Regular deposits that look like pay, strongest first (I-01)."""
    state = state or empty()
    skip = set(state.get("pay_no") or []) | {p.get("payer") for p in state.get("pays") or []}
    since = (today - timedelta(days=PAY_LOOKBACK_DAYS)).isoformat()
    by_payer: dict[str, dict[str, float]] = {}
    salary: dict[str, bool] = {}
    for t in transactions:
        if t.date[:10] < since or t.date[:10] > today.isoformat() or not could_be_pay(t):
            continue
        payer = payer_of(t)
        if not payer or payer in skip:
            continue
        days = by_payer.setdefault(payer, {})
        days[t.date[:10]] = days.get(t.date[:10], 0.0) - t.amount
        salary[payer] = salary.get(payer, False) or kind_of(t) == "salary"
    out = []
    for payer, by_day in by_payer.items():
        days = sorted(_d(d) for d in by_day)
        if len(days) < 3:
            continue
        cadence = _cadence_of(days)
        if not cadence:
            continue
        amounts = list(by_day.values())
        usual = statistics.median(amounts)
        if usual <= 0 or any(abs(a - usual) / usual > 0.2 for a in amounts):
            continue
        out.append({
            "payer": payer, "name": payer, "amount": round(usual, 2), "cadence": cadence,
            "last": days[-1].isoformat(), "next": predict_next(days, cadence, today).isoformat(),
            "count": len(days), "salary": salary[payer],
        })
    out.sort(key=lambda c: (not c["salary"], -c["count"], -c["amount"]))
    return out


# ── I-04: rent by e-Transfer ───────────────────────────────────────────

def rent_series(transactions: list[Transaction], today: date) -> list[dict]:
    """e-Transfers to one recipient that go out monthly at a similar amount."""
    from .insights.recurring import _analyze_merchant
    from .transfers import destination

    groups: dict[str, tuple[str, list[Transaction]]] = {}
    for t in transactions:
        if t.amount <= 0 or is_others(t) or not looks_like_etransfer(t):
            continue
        if t.category not in ("Transfers", "Unsorted transfers", RENT):
            continue
        where = destination(t)
        if not where:
            continue
        key, label = where
        groups.setdefault(key, (label, []))[1].append(t)
    out = []
    for key, (label, rows) in groups.items():
        rec = _analyze_merchant(label, rows, today)
        if not rec or rec["cadence"] != "monthly" or not rec["active"]:
            continue
        if rec["typical_amount"] < RENT_MIN:
            continue
        out.append({**rec, "key": f"rent:{key}", "recipient": label,
                    "category": RENT, "ids": [t.fingerprint for t in rows]})
    out.sort(key=lambda r: -r["typical_amount"])
    return out


# ── I-04 and the bills that count ──────────────────────────────────────

def _estimate(rec: dict) -> bool:
    return abs(round(rec["amount"] * 100) - round(rec["typical_amount"] * 100)) >= 50


def bills(transactions: list[Transaction], today: date, state: dict | None) -> list[dict]:
    """Every bill she can see in I-04 and on Income and bills: what Pearl
    found, rent by e-Transfer, and what she added. `counts` says whether it
    is in her bills; `ticked` is what I-04 starts with."""
    from .insights.recurring import detect_recurring
    from .safe_to_spend import _is_bill

    state = state or empty()
    answers = state.get("bills") or {}
    rent_answers = state.get("rent") or {}
    series = rent_series(transactions, today)
    covered = set()
    for s in series:
        covered.update(s["dates"])
    out = []

    def row(rec, key, name, *, question=False):
        a = answers.get(key) or {}
        estimate = _estimate(rec)
        cadence = a.get("cadence") or rec["cadence"]
        amount = a.get("amount") or (rec["typical_amount"] if estimate else rec["amount"])
        varies = a["varies"] if "varies" in a else estimate
        day = round(statistics.median(_d(x).day for x in rec["dates"]))
        nxt = rec["next_expected"]
        if rec["cadence"] == "monthly":
            # The usual day of the month, after the last charge: rent paid
            # on the 1st is due on the 1st, not 30 days after the last one.
            nxt = _add_months(_d(rec["dates"][-1]), 1, day).isoformat()
        nxt = a.get("next") or nxt
        if a.get("state") == "yes":
            counts = True
        elif a.get("state") == "no":
            counts = False
        elif question:
            counts = False
        else:
            counts = None                      # not answered: S9's rule applies
        ticked = counts if counts is not None else rec.get("confidence", 0) >= TICK_CONFIDENCE
        return {
            "key": key, "name": a.get("name") or name, "merchant": rec["merchant"],
            "amount": round(float(amount), 2), "varies": bool(varies), "cadence": cadence,
            "next": nxt, "day": _d(nxt).day if a.get("next") else day,
            "category": rec.get("category") or "Other",
            "counts": counts, "ticked": bool(ticked), "source": "found",
            "edited": bool(a.get("amount") or a.get("cadence") or a.get("next")),
            "dates": rec["dates"], "rec": rec,
        }

    for rec in detect_recurring(transactions, as_of=today.isoformat()):
        key = rec["merchant"]
        a = answers.get(key) or {}
        if not (_is_bill(rec) or (a.get("state") == "yes" and rec.get("active"))):
            continue
        if set(rec["dates"]) <= covered and len(rec["dates"]) > 0:
            continue                            # the rent series below has it
        out.append(row(rec, key, rec["merchant"]))
    for s in series:
        said = rent_answers.get(s["key"][5:])
        if said == "yes":
            r = row(s, s["key"], "Rent")
            r["category"] = RENT
            r["rent"] = True
            out.append(r)
        else:
            r = row(s, s["key"], f"e-Transfer to {s['recipient']}", question=said is None)
            r["question"] = said is None
            r["recipient"] = s["recipient"]
            out.append(r)
    out.sort(key=lambda r: (not r.get("question"), r["day"], r["name"].lower()))
    for b in state.get("added") or []:
        key = f"added:{b['id']}"
        out.append({
            "key": key, "name": b["name"], "merchant": "", "amount": b["amount"],
            "varies": bool(b.get("varies")), "cadence": b["cadence"], "next": b["next"],
            "day": _d(b["next"]).day, "category": "Other", "counts": True, "ticked": True,
            "source": "added", "edited": False, "dates": [], "rec": None,
        })
    return out


def rent_question(rows: list[dict]) -> dict | None:
    q = next((r for r in rows if r.get("question")), None)
    if not q:
        return None
    return {"key": q["key"], "recipient": q["recipient"], "amount": q["amount"], "day": q["day"]}


def monthly(amount: float, cadence: str) -> float:
    return amount * PER_YEAR.get(cadence, 12) / 12


def bills_each_month(rows: list[dict], told_rent: float = 0.0) -> float:
    """What the ticked bills come to each month — with the rent she told
    Home about until a rent bill is among them, so Profile and Home count
    the same bills (2026-10-14)."""
    total = sum(monthly(r["amount"], r["cadence"]) for r in rows if r["ticked"])
    rent_in = any(r["ticked"] and (r.get("rent") or r.get("category") == RENT) for r in rows)
    if told_rent and told_rent > 0 and not rent_in:
        total += told_rent
    return round(total, 2)


def income_each_month(state: dict, told: float = 0.0, estimate: float | None = None) -> float | None:
    """A typical month's income, as I-06 and Income and bills count it: her
    own amount when she gave one (it overrides the rest, 2026-10-13), else
    her pay, else Pearl's estimate from her last three months."""
    if told > 0:
        return round(told, 2)
    pays = state.get("pays") or []
    if pays:
        return round(sum(p["amount"] * PAY_PER_MONTH.get(p["cadence"], 1) for p in pays), 2)
    return round(estimate, 2) if estimate else None


# ── Validation (the endpoints) ──────────────────────────────────────────

def clean_name(value) -> str:
    return " ".join(str(value or "").split())[:MAX_NAME]


def clean_amount(value) -> float | None:
    try:
        n = round(float(str(value).replace("$", "").replace(",", "").strip()), 2)
    except (TypeError, ValueError):
        return None
    return n if 0 < n <= MAX_AMOUNT else None


def clean_date(value) -> str | None:
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (TypeError, ValueError):
        return None


def pay_from(body: dict) -> tuple[dict | None, str | None]:
    """A pay from I-02's fields, or what's wrong with them."""
    name = clean_name(body.get("name"))
    if not name:
        return None, "Give your pay a name, like your employer."
    amount = clean_amount(body.get("amount"))
    if amount is None:
        return None, "Enter what lands in your account, like 2150."
    cadence = body.get("cadence")
    if cadence not in PAY_CADENCES:
        return None, "Choose how often you’re paid."
    nxt = clean_date(body.get("next"))
    if nxt is None and cadence != "irregular":
        return None, "Choose your next pay date."
    return {"name": name, "amount": amount, "cadence": cadence,
            "next": nxt, "payer": clean_name(body.get("payer")) or ""}, None


def bill_from(body: dict) -> tuple[dict | None, str | None]:
    """A bill from I-05's fields, or what's wrong with them."""
    name = clean_name(body.get("name"))
    if not name:
        return None, "Give the bill a name."
    amount = clean_amount(body.get("amount"))
    if amount is None:
        return None, "Enter the amount, like 45."
    cadence = body.get("cadence")
    if cadence not in BILL_CADENCES:
        return None, "Choose how often it’s due."
    nxt = clean_date(body.get("next"))
    if nxt is None:
        return None, "Choose the next due date."
    return {"name": name, "amount": amount, "cadence": cadence, "next": nxt,
            "varies": bool(body.get("varies"))}, None
