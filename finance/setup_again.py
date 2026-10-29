"""Set up again, after Start over (2026-10-29).

Start over wipes what she set up — which accounts she shares, her income
and bills, how each account counts (nicknames, in the budget or not, the
Anchor), debt details — and downloads the history again. What the
banks send back comes back on its own; what only she can say doesn't. So
Start over leaves a short list of those things, shown after it and on Home
until each is done or she hides it:

    shared    Which accounts do you share?   (answered here, or "none")
    income    Confirm your income and bills  (done once both are confirmed)
    accounts  Check how each account counts  (done once she opens Accounts)
    debts     Add your debt details          (with a card or loan linked;
                                              done once she opens Debts)

First-time setup asks "Which accounts do you share?" too, after linking a
bank, so the two match.
"""

from __future__ import annotations

import json
from datetime import date

KEY = "setup_again"

STEPS = (
    ("shared", "Which accounts do you share?",
     "Mark joint accounts so only your share counts."),
    ("income", "Confirm your income and bills",
     "Pearl found them again. Say which are right."),
    ("accounts", "Check how each account counts",
     "Nicknames, which count in your budget, and your Anchor."),
    ("debts", "Add your debt details",
     "Interest rates and minimum payments, for your cards and loans."),
)
KEYS = tuple(k for k, _, _ in STEPS)


def _load(st) -> dict | None:
    raw = st.setting(KEY)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _save(st, data: dict | None) -> None:
    st.set_setting(KEY, json.dumps(data) if data else "")


def begin(st, today: date | None = None) -> None:
    """Start over just ran: every step waits."""
    _save(st, {"since": (today or date.today()).isoformat(), "done": [], "hidden": False})


def _income_done(st) -> bool:
    from . import income_bills as ib
    state = ib.load(st)
    return bool(state.get("income_on") and state.get("bills_on"))


def _has_debts(st) -> bool:
    """A card or a loan linked, so there are debt details to give."""
    try:
        from .profile_api import _all_rows
        return any(a["kind"] in ("card", "loan") and a["status"] != "removed"
                   for a in _all_rows(st))
    except Exception:                                    # noqa: BLE001
        return False


def status(st) -> dict:
    """{"active": bool, "since": iso, "steps": [{key, title, sub, done}],
    "left": n}. Not active when nothing was started over, every step is
    done, or she hid it."""
    data = _load(st)
    if not data:
        return {"active": False, "steps": [], "left": 0}
    done = set(data.get("done") or [])
    if _income_done(st):
        done.add("income")
    owes = _has_debts(st)
    steps = [{"key": k, "title": t, "sub": s, "done": k in done} for k, t, s in STEPS
             if k != "debts" or owes]
    left = sum(1 for s in steps if not s["done"])
    return {"active": bool(left) and not data.get("hidden"), "since": data.get("since"),
            "steps": steps, "left": left}


def mark(st, step: str) -> dict:
    """One step done."""
    if step not in KEYS:
        raise ValueError("No such step.")
    data = _load(st)
    if data is None:
        return status(st)
    done = list(data.get("done") or [])
    if step not in done:
        done.append(step)
    data["done"] = done
    _save(st, data)
    return status(st)


def hide(st) -> dict:
    """"Hide this": she'll do the rest from Profile when she wants."""
    data = _load(st)
    if data is not None:
        data["hidden"] = True
        _save(st, data)
    return status(st)
