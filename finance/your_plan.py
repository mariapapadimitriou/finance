"""Your plan (YP-01 to YP-06, note 1353:11493; THL-127, THL-45, THL-198,
THL-117): an amount a month for some spending categories, and, once she uses
it, the Allowance that follows from it.

Profile › Income and bills › Your plan. The rules this keeps (product owner,
2026-11-15):

* **A plan only proposes.** Pearl's suggestion (from her last three months),
  her changes and a plan set in Pearl chat are rows here; none of them touches
  the Allowance until she taps "Use this plan" and confirms it (YP-02).
* **In use, the Allowance follows it.** Each planned category's amount is set
  aside this month, as a bill is: what she has spent on it this month already
  comes off in "Already spent", and the rest of the plan is held back in a row
  of its own ("plan"), never below $0. So with nothing spent yet the Allowance
  is her income less her bills less the plan, which is the figure YP-01 says
  (YOUR ALLOWANCE "$1,180 a month · plan total $1,160", LT-05).
  A charge that is a bill is a bill: it isn't counted again against a plan.
* **While in use, a change counts at once**: Save or Remove (YP-04, YP-05)
  and the chat's Set it (the chat's confirm is the confirm; PC-12/PC-13).
* **Rounding:** every amount rounds to the nearest $5 (not to the budgets'
  5% steps), so the chat's $220 stays $220 here and in the Allowance. A
  suggestion (Suggest a plan, and the chat's) is her usual rounded UP to the
  next $10, $214 to $220 (note 1353:11493, "one rule for suggestions").
* Removing the last row stops the plan: an empty plan is never in use.
* **Stop asks first** (YP-07), and Undo on its toast uses it again the way it
  was: in use since the same day.

One setting, `your_plan` (JSON): {"rows": [{category, amount, source}],
"in_use": bool, "since": "YYYY-MM-DD" | null, "stopped_since": "YYYY-MM-DD"
| null}. `stopped_since` is the day a plan stopped on YP-07 had been in use
since, for Undo. `source` is "pearl" (the
suggestion), "chat" (set in Pearl chat) or "you" (changed on YP-04).
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date

from .analytics import counts_as_spending, spend_amount
from .models import Transaction

KEY = "your_plan"
SOURCES = ("pearl", "chat", "you")
STEP = 5
# YP-01 draws five; the budgets' "five largest come first" (B2).
SUGGEST = 5
MAX_AMOUNT = 100_000
MAX_CATEGORY = 60


class PlanError(ValueError):
    """Words for her, with the status to send them with."""

    def __init__(self, words: str, status: int = 400):
        super().__init__(words)
        self.words = words
        self.status = status


def round_up_10(amount: float) -> int:
    """A suggestion: her usual rounded UP to the next $10, $214 to $220,
    $210 stays $210. A multiple of $10 is a multiple of $5, so it's kept as
    it is shown (YP-06's Suggest a plan, and the chat's PC-12)."""
    return int(math.ceil(round(float(amount), 2) / 10)) * 10


def round_5(amount: float) -> int:
    """To the nearest $5, halves up: $220 stays $220, $214 is $215, $212.50
    is $215. The number shown, kept and set aside are all this one."""
    return int(math.floor(float(amount) / STEP + 0.5)) * STEP


def empty() -> dict:
    return {"rows": [], "in_use": False, "since": None, "stopped_since": None}


def load(st) -> dict:
    raw = st.setting(KEY)
    try:
        data = json.loads(raw) if raw not in (None, "") else {}
    except (TypeError, ValueError):
        data = {}
    out = empty()
    if isinstance(data, dict):
        rows = []
        for r in data.get("rows") or []:
            if isinstance(r, dict) and r.get("category") and isinstance(r.get("amount"), (int, float)):
                rows.append({"category": str(r["category"]), "amount": round_5(r["amount"]),
                             "source": r.get("source") if r.get("source") in SOURCES else "you"})
        out["rows"] = rows
        out["in_use"] = bool(data.get("in_use")) and bool(rows)
        out["since"] = data.get("since") if out["in_use"] else None
        stopped = data.get("stopped_since")
        out["stopped_since"] = stopped if isinstance(stopped, str) and not out["in_use"] and rows else None
    return out


def save(st, state: dict) -> None:
    if not state["rows"]:
        state["in_use"], state["since"] = False, None
        state["stopped_since"] = None
    st.set_setting(KEY, json.dumps(state))


def in_use(state: dict) -> dict[str, float]:
    """{category: amount} while the plan is in use; {} otherwise. What the
    Allowance reads (`safe_to_spend.compute`'s `plan`)."""
    if not state.get("in_use"):
        return {}
    return {r["category"]: float(r["amount"]) for r in state["rows"]}


# ── The Allowance ───────────────────────────────────────────────────────

def set_aside(transactions: list[Transaction], today: date, plan: dict[str, float],
              bill_charges: set[tuple[str, str]] | None = None) -> dict | None:
    """What the plan holds back this month: each category's amount less what
    she has spent on it so far this month (that is in "Already spent"), never
    below $0. Bills are bills: a charge that pays one isn't counted again here.
    Returns {"amount_c", "lines"} or None with no plan in use."""
    if not plan:
        return None
    month = today.strftime("%Y-%m")
    spent_c: dict[str, int] = defaultdict(int)
    for t in transactions:
        if t.month != month or t.date > today.isoformat() or not counts_as_spending(t):
            continue
        cat = t.category or "Other"
        if cat not in plan or (bill_charges and (t.merchant, t.date) in bill_charges):
            continue
        spent_c[cat] += int(round(spend_amount(t) * 100))
    lines, total_c = [], 0
    for cat, amount in plan.items():
        left_c = max(int(round(amount * 100)) - spent_c.get(cat, 0), 0)
        total_c += left_c
        lines.append({"label": cat, "amount": round(left_c / 100, 2), "plan": amount,
                      "spent": round(spent_c.get(cat, 0) / 100, 2)})
    return {"amount_c": total_c, "lines": lines}


# ── Changing it ─────────────────────────────────────────────────────────

def clean_category(category) -> str:
    from .category_budgets import LEFT_OUT
    from .categorize import NON_SPEND
    name = " ".join(str(category or "").split())
    if not name or len(name) > MAX_CATEGORY:
        raise PlanError("Choose a category.")
    if name in NON_SPEND or name in LEFT_OUT or name == "Unsorted transfers":
        raise PlanError("Plans are for spending categories.")
    return name


def clean_amount(amount) -> int:
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount):
        raise PlanError("Enter an amount a month.")
    if amount < 0 or amount > MAX_AMOUNT:
        raise PlanError("Enter an amount a month.")
    rounded = round_5(amount)
    if rounded <= 0:
        raise PlanError("Plans start at $5 a month.")
    return rounded


def set_row(state: dict, category, amount, source: str = "you") -> dict:
    """Add or change one row (YP-04's Save; the chat's Set it). Rounded to
    the nearest $5. In use, the Allowance follows at once."""
    cat = clean_category(category)
    value = clean_amount(amount)
    src = source if source in SOURCES else "you"
    for r in state["rows"]:
        if r["category"] == cat:
            r["amount"], r["source"] = value, src
            return state
    state["rows"].append({"category": cat, "amount": value, "source": src})
    return state


def remove_row(state: dict, category) -> dict:
    """YP-05's Remove: the category goes back to her usual. The last one
    out stops the plan."""
    cat = " ".join(str(category or "").split())
    before = len(state["rows"])
    state["rows"] = [r for r in state["rows"] if r["category"] != cat]
    if len(state["rows"]) == before:
        raise PlanError("That category isn't in your plan.", 404)
    if not state["rows"]:
        state["in_use"], state["since"] = False, None
        state["stopped_since"] = None
    return state


def use(state: dict, today: date) -> dict:
    """YP-02's Use this plan: the Allowance follows it from today."""
    if not state["rows"]:
        raise PlanError("Add a category to your plan first.", 409)
    if not state["in_use"]:
        state["in_use"], state["since"] = True, today.isoformat()
    state["stopped_since"] = None
    return state


def stop(state: dict) -> dict:
    """YP-07's Stop using it: back to her usual amounts. The rows stay, as a
    proposal again, and the day it was in use since is kept for Undo."""
    if state["in_use"]:
        state["stopped_since"] = state["since"]
    state["in_use"], state["since"] = False, None
    return state


def undo_use(state: dict) -> dict:
    """Undo on YP-03's toast: as before Use this plan."""
    state["in_use"], state["since"], state["stopped_since"] = False, None, None
    return state


def resume(state: dict, today: date) -> dict:
    """Undo on YP-07's toast: in use again the way it was, since the same
    day (today if that's not known)."""
    if not state["rows"]:
        raise PlanError("Add a category to your plan first.", 409)
    if not state["in_use"]:
        state["in_use"] = True
        state["since"] = state.get("stopped_since") or today.isoformat()
    state["stopped_since"] = None
    return state


# ── Pearl's suggestion (YP-06's Suggest a plan) ─────────────────────────

def suggestions(transactions: list[Transaction], today: date, usual: dict) -> list[dict]:
    """Her largest spending categories from her usual month (the last three
    full months), each at its usual rounded up to the next $10, as the chat
    suggests one (note 1353:11493). Left out as
    the budgets leave them out (B2): rent, and a category that's all bills
    (bills are set aside already)."""
    from . import category_budgets as cb
    built = cb.build(transactions, today, usual, {}, [])
    out = []
    for row in sorted(built["rows"], key=lambda r: (-r["usual"], r["category"])):
        if row["bill"]:
            continue
        amount = round_up_10(row["usual"])
        if amount <= 0:
            continue
        out.append({"category": row["category"], "amount": amount, "source": "pearl"})
        if len(out) == SUGGEST:
            break
    return out


def suggest(state: dict, transactions: list[Transaction], today: date, usual: dict) -> dict:
    """Pearl's suggestion joins the plan; rows set in the chat or by her
    stay as they are. Only a plan not in use: a suggestion never changes
    the Allowance."""
    if state["in_use"]:
        raise PlanError("Your plan is in use. Stop using it first.", 409)
    found = suggestions(transactions, today, usual)
    if not found:
        raise PlanError("Pearl needs a month or more of spending to suggest a plan.", 409)
    have = {r["category"] for r in state["rows"]}
    state["rows"] += [r for r in found if r["category"] not in have]
    return state


# ── YP-08's Add a category ──────────────────────────────────────────────

def not_in_plan(state: dict, transactions: list[Transaction], today: date, usual: dict,
                hidden: set[str] | None = None) -> list[dict]:
    """NOT IN YOUR PLAN: every spending category a plan can have that isn't
    in it, each with her usual and the amount YP-04 starts at (the usual to
    the nearest $5). Largest usual first; those with no spending in her
    usual month last, at $0, by name. Left out as Suggest a plan leaves them
    out (B2): rent, and a category that's all bills, which is set aside as a
    bill already, so a plan would hold it back twice."""
    from . import category_budgets as cb
    from .chat import spend_categories
    from .categorize import NON_SPEND
    have = {r["category"] for r in state["rows"]}
    built = cb.build(transactions, today, usual, {}, [])
    bills = {r["category"] for r in built["rows"] if r["bill"]}
    cats = usual.get("categories") or {}
    names = set(spend_categories(hidden)) | {c for c, info in cats.items() if (info.get("usual") or 0) > 0}
    out = []
    for cat in names:
        if (cat in have or cat in bills or cat in cb.LEFT_OUT or cat in NON_SPEND
                or cat == "Unsorted transfers" or (hidden and cat in hidden)):
            continue
        the_usual = round(float((cats.get(cat) or {}).get("usual") or 0.0), 2)
        out.append({"category": cat, "usual": the_usual, "amount": round_5(the_usual)})
    out.sort(key=lambda r: (-r["usual"], r["category"]))
    return out


# ── The page ────────────────────────────────────────────────────────────

def page(state: dict, usual: dict, income: float | None, bills: float) -> dict:
    """YP-01, YP-03 and YP-06: each row with her usual, the total, and the
    Allowance a month it leaves with her income and bills."""
    cats = usual.get("categories") or {}
    rows = [{**r, "usual": round(float((cats.get(r["category"]) or {}).get("usual") or 0.0), 2)}
            for r in state["rows"]]
    total = sum(r["amount"] for r in rows)
    return {
        "rows": rows,
        "in_use": state["in_use"],
        "since": state["since"],
        "total": total,
        "income": income,
        "bills": bills,
        "allowance": round(income - bills - total, 2) if income else None,
        # YP-07: the Allowance a month without the plan, her usual amounts.
        "allowance_without": round(income - bills, 2) if income else None,
        "months": len(usual.get("months") or []),
    }
