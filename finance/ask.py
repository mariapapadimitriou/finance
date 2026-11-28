"""Ask Pearl (THL-308, AI Phase 2; PC-20 to PC-26): the answers behind
POST /api/ask, on every iPhone.

Python computes every number here; the model (Claude, through the gateway in
`finance/ai/`) only picks a tool and words the answer. Apple Intelligence is
never used.

* The tools only read. Today's chat answers (`finance/chat.py`: spending,
  subscriptions, trips and patterns, Tell Pearl what you did, a plan) and
  four new ones (PC-26): a shop's history, a month, a search (at most 10
  rows) and credit cards. A tool's result is a `Fact`: the card the phone
  draws (whole, never streamed), the step it names while it works ("Looking
  at November…"), a line in Python's own words, and at most one suggestion
  whose action only opens a screen.
* What the model sees of a result is `for_model`: no ids, account numbers,
  card numbers, Plaid tokens or bank text it doesn't need; every string goes
  through `safety.redact`, and the gateway refuses anything that slips by.
* With no model (no key, the kill switch, over a cap, a failure), `builtin`
  reads the words itself and answers with the same tools. Over the monthly
  or daily cap the phone also gets one quiet line (PC-23): "Pearl's keeping
  answers simple until December 1." Never dollars, tokens or "limit".
* When neither can answer (the model fails, refuses, or calls no tool),
  "couldnt": the phone's scripted line and four things it can always do.

The stream is one JSON object per line (application/x-ndjson):

    {"type": "step", "text": "Looking at November…"}
    {"type": "fact", "kind": "month", "data": {...}}
    {"type": "text", "text": "You've spent"}            words, as written
    {"type": "reset"}                                    drop the words so far
    {"type": "words", "text": "…"}                       the words, whole (Python's)
    {"type": "suggestion", "text": "…", "action": {"label", "open", …}}
    {"type": "simple", "until": "December 1"}
    {"type": "couldnt"}
    {"type": "done"}
"""

from __future__ import annotations

import calendar
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import chat
from .ai import safety
from .analytics import counts_as_spending, spend_amount
from .categorize import merchant_key

MONTH_LETTERS = "JFMAMJJASOND"
SEARCH_ROWS = 10           # PC-26c: up to 10 rows, then "See all N in Cash flow"
NEAR_LIMIT = 0.80          # PC-26d: the bar turns amber at 80% of the limit
MAX_TEXT = 500


@dataclass
class Fact:
    kind: str                      # month, merchant, search, cards, spending, subscriptions, tell, asks, plan
    data: dict
    step: str                      # "Looking at November…"
    line: str                      # the answer in Python's own words
    suggestion: dict | None = None
    model: dict = field(default_factory=dict)   # what the model may see

    @property
    def answers(self) -> bool:
        """A tool that found nothing to show still answered in words."""
        return bool(self.line)


# ── Words ────────────────────────────────────────────────────────────────

def whole(x: float) -> str:
    return f"${round(abs(x)):,}"


def money(x: float) -> str:
    return f"${abs(x):,.2f}"


def month_name(ym: str) -> str:
    return calendar.month_name[int(ym[5:7])]


def short_day(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{calendar.month_abbr[d.month]} {d.day}"


def compared(diff: float) -> str:
    """A difference Python worked out, in words for the model (Phase 2b):
    the model never gets a comparison as a number."""
    return "about usual" if abs(diff) < 1 else "more than usual" if diff > 0 else "less than usual"


_COMPARED = re.compile(r"\$[\d,]+(?:\.\d+)?\s+(more|less|over|under)\b")


def comparison_words(line: str) -> str:
    """Python's line for the model: "That’s $40 more than usual" becomes
    "That’s more than usual"; the figure stays in the card."""
    return _COMPARED.sub(lambda m: m.group(1), line or "")


def first_of_next_month(today: date) -> str:
    """"December 1", for the quiet line (PC-23)."""
    nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    return f"{calendar.month_name[nxt.month]} 1"


def nickname(name: str) -> str:
    """A card's name with any number taken off: "Amex Cobalt ••1234" → "Amex
    Cobalt" (PC-26d: nicknames only)."""
    name = re.sub(r"[\s(]*(?:[•·*xX#-]+\s*)?\d{3,}\)?\s*$", "", name or "").strip()
    name = re.sub(r"\d{4,}", "", name).strip(" -•·*()")
    return name or "Card"


# ── The ledger, as the transactions list sees it ─────────────────────────

class Ledger:
    """One request's view of her money, read once and shared by the tools."""

    def __init__(self, st, today: date):
        self.st = st
        self.today = today
        self._rows = None
        self._txns = None

    @property
    def txns(self):
        if self._txns is None:
            self._txns = self.st.all_transactions()
        return self._txns

    @property
    def rows(self):
        """(Transaction, row) pairs, as Cash flow lists them: the same totals."""
        if self._rows is None:
            from .api import _txlist_rows
            self._rows = _txlist_rows(self.st)
        return self._rows


def known_terms(led: Ledger) -> dict:
    """Her people, cards and shops by name, for the gateway to mask (AI
    Phase 2b): split names, joint holders, who paid her back and e-Transfer
    senders; every account's label and nickname; every merchant."""
    from . import etransfers, marks
    st, txns = led.st, led.txns
    people = etransfers.known_people(txns, st.splits(), st.payback_people())
    shops: set[str] = set()
    for t in txns:
        if t.party:
            people.append(t.party)
        p = etransfers.party(t, people) if etransfers.is_etransfer(t) else None
        if p and p.get("name"):
            people.append(p["name"])
            if t.merchant and t.merchant != p["name"]:
                shops.add(t.merchant)
        elif t.merchant:
            shops.add(t.merchant)
    cards: set[str] = set()
    for label in marks.account_labels(st).values():
        if label:
            cards.add(nickname(label))
    for a in st.accounts():
        if a.get("account_name"):
            cards.add(nickname(a["account_name"]))
    return {"person": sorted(set(people)), "card": sorted(c for c in cards if c != "Card"),
            "shop": sorted(shops)}


def _spent(pairs) -> float:
    from .txlist import card_part
    return round(sum(card_part(t, r, "spent") or 0.0 for t, r in pairs), 2)


def _brief(t) -> dict:
    from .review import _brief as brief
    return brief(t)


# ── PC-26b and PC-22: a month ────────────────────────────────────────────

def month(led: Ledger, ym: str | None = None) -> Fact:
    """A month: money in, spent, the Allowance left and where it went most.
    This month, how it compares with where she usually is by today, and the
    category furthest past its usual as a suggestion (PC-22)."""
    from . import txlist
    from .api import _home_sts, _invested_in, _unusual_months
    today = led.today
    ym = ym if ym and re.fullmatch(r"\d{4}-\d{2}", ym) else today.strftime("%Y-%m")
    if ym > today.strftime("%Y-%m"):
        ym = today.strftime("%Y-%m")
    pairs = txlist.select(led.rows, month=ym)
    tot = txlist.totals(pairs)
    spent, money_in = tot["spent"], tot["income"]
    by_cat: dict[str, float] = defaultdict(float)
    count: dict[str, int] = defaultdict(int)
    for t, r in pairs:
        if r["counts"] == "spending":
            by_cat[r["category"] or "Other"] += txlist.card_part(t, r, "spent") or 0.0
            count[r["category"] or "Other"] += 1
    top = [{"category": c, "amount": round(a, 2), "share": round(a / spent, 4) if spent else 0.0}
           for c, a in sorted(by_cat.items(), key=lambda kv: -kv[1]) if a > 0.005][:3]
    name = month_name(ym)
    current = ym == today.strftime("%Y-%m")
    data = {"month": ym, "name": name, "current": current, "money_in": round(money_in, 2),
            "spent": round(spent, 2), "top": top, "allowance_left": None, "over_by": None,
            "usual_by_now": None, "day": today.day if current else None, "changes": []}
    suggestion = None
    if current:
        from .usual_month import usual
        u = usual(led.txns, today, unusual=_unusual_months(led.st))
        days = calendar.monthrange(today.year, today.month)[1]
        by_now = 0.0
        have = False
        for g in u.get("groups", {}).values():
            if g.get("by_day"):
                by_now += g["by_day"][today.day - 1]
                have = True
            elif g.get("usual") is not None:
                by_now += g["usual"] * today.day / days
                have = True
        if have:
            data["usual_by_now"] = round(by_now, 2)
        changes = []
        for cat, info in u.get("categories", {}).items():
            diff = by_cat.get(cat, 0.0) - info["usual"] * today.day / days
            if diff >= 1:
                changes.append({"category": cat, "over": round(diff, 2), "count": count.get(cat, 0)})
        changes.sort(key=lambda c: -c["over"])
        data["changes"] = changes[:2]
        sts = _home_sts(led.st, led.txns, today)
        if sts.get("state") == "over":
            data["over_by"] = sts.get("over_by")
        elif sts.get("state") == "ok":
            data["allowance_left"] = sts.get("shown") if sts.get("shown") is not None else sts.get("amount")
        line = f"You’ve spent {whole(spent)} so far in {name}."
        if data["usual_by_now"] is not None:
            diff = spent - data["usual_by_now"]
            if abs(diff) < 1:
                line += " That’s about usual by now."
            else:
                line += f" That’s {whole(diff)} {'more' if diff > 0 else 'less'} than usual by now."
        if changes and changes[0]["count"]:
            c = changes[0]
            n = c["count"]
            suggestion = {"text": f"{c['category']} is the biggest change. Want to look at "
                                  f"{'that purchase' if n == 1 else f'those {n} purchases'}?",
                          "action": {"label": f"See {c['category']}", "open": "category",
                                     "category": c["category"], "month": ym}}
    else:
        saved = round(_invested_in(led.txns, ym), 2)
        left = round(money_in - spent - saved, 2)
        data["allowance_left"] = left if left >= 0 else None
        data["over_by"] = -left if left < 0 else None
        line = (f"In {name}, {whole(money_in)} came in and you spent {whole(spent)}. "
                + (f"You had {whole(left)} of your Allowance left at the end." if left >= 0
                   else f"You went {whole(-left)} over."))
    # Comparisons go to the model as words, never as numbers (Phase 2b).
    model = {k: v for k, v in data.items() if k not in ("changes", "usual_by_now", "day", "top")}
    for k in ("money_in", "spent", "allowance_left", "over_by"):
        model[k] = whole(data[k]) if data[k] is not None else None
    model["top"] = [{"category": x["category"], "amount": whole(x["amount"])} for x in top]
    if data["usual_by_now"] is not None:
        model["compared_with_usual_by_now"] = compared(spent - data["usual_by_now"])
    model["changes"] = [{"category": c["category"], "compared_with_usual": "more than usual"}
                        for c in data["changes"]]
    model["line"] = comparison_words(line)
    return Fact("month", data, f"Looking at {name}…", line, suggestion, model)


# ── PC-26a: a shop's history ─────────────────────────────────────────────

def _shop_rows(led: Ledger, name: str, year: int | None = None):
    key = merchant_key(name)
    pairs = [(t, r) for t, r in led.rows if r["counts"] == "spending"
             and (year is None or r["date"][:4] == str(year))]
    exact = [(t, r) for t, r in pairs
             if merchant_key(t.merchant or "") == key or merchant_key(r.get("merchant") or "") == key]
    if exact or len(key) < 3:
        return exact
    return [(t, r) for t, r in pairs if key in merchant_key(r.get("merchant") or "")
            or key in merchant_key(t.merchant or "")]


def merchant_history(led: Ledger, name: str, year: int | None = None) -> Fact:
    """A shop this year: the total, how many visits, about how much each,
    and a bar per month so far (PC-26a)."""
    today = led.today
    year = int(year) if year else today.year
    pairs = _shop_rows(led, name, year)
    shown = (pairs[0][1].get("merchant") if pairs else None) or name.strip()
    total = _spent(pairs)
    visits = len(pairs)
    last = today.month if year == today.year else 12
    per = defaultdict(float)
    from .txlist import card_part
    for t, r in pairs:
        per[int(r["date"][5:7])] += card_part(t, r, "spent") or 0.0
    months = [{"month": f"{year}-{m:02d}", "label": MONTH_LETTERS[m - 1],
               "amount": round(per.get(m, 0.0), 2), "now": year == today.year and m == today.month}
              for m in range(1, last + 1)]
    data = {"merchant": shown, "year": year, "total": total, "visits": visits,
            "average": round(total / visits, 2) if visits else None,
            "per_month": round(total / last, 2) if last else None,
            "months": months, "query": shown}
    when = "this year" if year == today.year else f"in {year}"
    if not visits:
        line = f"Pearl didn’t find anything at {shown} {when}."
    else:
        line = f"{whole(total)} at {shown} {when}, about {whole(total / last)} a month."
        biggest = max(months, key=lambda m: m["amount"])
        if biggest["now"] and len(months) > 1 and biggest["amount"] > 0:
            line += f" {month_name(biggest['month'])} is your biggest so far."
    model = {"merchant": shown, "year": year, "total": whole(total), "visits": visits,
             "about_each": whole(data["average"]) if visits else None,
             "about_a_month": whole(data["per_month"] or 0),
             "by_month": [{"month": m["month"], "amount": whole(m["amount"])} for m in months], "line": line}
    return Fact("merchant", data, f"Looking at {shown}…", line, None, model)


# ── PC-26c: a search ─────────────────────────────────────────────────────

def search(led: Ledger, words: str, ym: str | None = None) -> Fact:
    """Up to 10 rows that match, newest first, and how many in all; the
    rest are in Cash flow ("See all 12 in Cash flow")."""
    from . import txlist
    words = " ".join(str(words or "").split())[:80]
    pairs = txlist.select(led.rows, month=ym if ym and re.fullmatch(r"\d{4}-\d{2}", ym) else "all",
                          q=words) if words else []
    n = len(pairs)
    rows = [_brief(t) for t, _ in pairs[:SEARCH_ROWS]]
    spending = [(t, r) for t, r in pairs if r["counts"] == "spending"]
    total = _spent(spending) if spending else round(sum(abs(r["amount"]) for _, r in pairs), 2)
    since = month_name(min(r["date"] for _, r in pairs)[:7]) if pairs else None
    data = {"query": words, "count": n, "total": total, "rows": rows, "since": since,
            "month": ym}
    if not n:
        line = f"Nothing matches “{words}”." if words else "Pearl needs a word to look for."
    else:
        line = (f"{n} {'match' if n == 1 else 'matches'} for “{words}” since {since}, "
                f"{whole(total)} in all.")
        if n > SEARCH_ROWS:
            line += f" Here are the latest {SEARCH_ROWS}."
    model = {"query": words, "count": n, "total": whole(total), "since": since, "line": line,
             "latest": [{"name": r["merchant"], "date": short_day(r["date"]),
                         "amount": money(r["amount"])} for r in rows]}
    return Fact("search", data, f"Searching for “{words}”…", line, None, model)


# ── PC-26d: credit cards ─────────────────────────────────────────────────

def _next_due(today: date, day) -> str | None:
    try:
        day = int(day)
    except (TypeError, ValueError):
        return None
    if not 1 <= day <= 31:
        return None
    last = calendar.monthrange(today.year, today.month)[1]
    due = today.replace(day=min(day, last))
    if due < today:
        nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        due = nxt.replace(day=min(day, calendar.monthrange(nxt.year, nxt.month)[1]))
    return due.isoformat()


def cards(led: Ledger) -> Fact:
    """Each credit card by its nickname: spent this month, the balance
    against the limit, and when it's due. Near: 80% of the limit or more;
    over: past it. Never a card number."""
    from . import debts, marks
    from .api import _counted_balances, _counted_rules, _json_setting
    st, today = led.st, led.today
    labels = marks.account_labels(st)
    details = _json_setting(st, "debt_details", {})
    balances = _counted_balances(st)
    ym = today.strftime("%Y-%m")
    out = []
    for aid, rule in _counted_rules(st).items():
        if debts.kind_of(rule) != "card":
            continue
        b = balances.get(aid) or {}
        balance = b.get("current")
        limit = b.get("limit")
        spent = round(sum(spend_amount(t) for t in led.txns
                          if t.account_id == aid and t.month == ym and counts_as_spending(t)
                          and t.amount > 0), 2)
        used = (balance / limit) if balance is not None and limit else None
        state = ("over" if used is not None and used > 1 else
                 "near" if used is not None and used >= NEAR_LIMIT else "ok")
        out.append({"name": nickname(labels.get(aid) or rule.get("label") or rule.get("account_name")),
                    "account_id": aid, "spent": spent,
                    "balance": round(balance, 2) if balance is not None else None,
                    "limit": round(limit, 2) if limit else None,
                    "used": round(used, 4) if used is not None else None, "state": state,
                    "due": _next_due(today, (details.get(aid) or {}).get("due_day"))})
    out.sort(key=lambda c: (c["due"] or "9999", c["name"]))
    n = len(out)
    if not n:
        line = "Pearl doesn’t see a credit card yet."
    else:
        line = f"{'One card' if n == 1 else f'{n} cards'}."
        dated = [c for c in out if c["due"]]
        if dated:
            c = dated[0]
            line += (f" {c['name']} is due {'first, ' if n > 1 else ''}on {short_day(c['due'])}.")
        near = [c for c in out if c["state"] != "ok"]
        for c in near[:1]:
            line += (f" {c['name']} is over its limit." if c["state"] == "over"
                     else f" {c['name']} is close to its limit.")
    against = {"over": "over its limit", "near": "close to its limit", "ok": "well under its limit"}
    model = {"cards": [{"name": c["name"], "spent_this_month": whole(c["spent"]),
                        "balance": whole(c["balance"]) if c["balance"] is not None else None,
                        "limit": whole(c["limit"]) if c["limit"] else None,
                        "against_limit": against[c["state"]] if c["used"] is not None else None,
                        "due": short_day(c["due"]) if c["due"] else None}
                       for c in out], "line": line}
    data = {"cards": [{k: v for k, v in c.items() if k != "account_id"} for c in out]}
    return Fact("cards", data, "Looking at your cards…", line, None, model)


# ── Today's chat answers (finance/chat.py) ───────────────────────────────

def _strip_rows(rows: list[dict]) -> list[dict]:
    return [{"name": r.get("merchant") or "", "date": short_day(r["date"]),
             "amount": money(r.get("amount") or 0)} for r in rows[:10]]


def spending(led: Ledger, text: str, category=None, ym=None, merchant=None) -> Fact:
    a = chat.spending(led.st, led.txns, led.today, text=text, category=category, month=ym,
                      merchant=merchant)
    model = {k: a.get(k) for k in ("nothing", "title", "category", "merchant", "month", "count", "line")}
    model["total"] = whole(a["total"]) if a.get("total") is not None else None
    if a.get("total") is not None and a.get("usual") is not None:
        model["compared_with_usual"] = compared(a["total"] - a["usual"])
    model["line"] = comparison_words(model.get("line") or "")
    model["rows"] = _strip_rows(a.get("rows") or [])
    return Fact("spending", a, "Looking at your spending…", a.get("line") or "", None, model)


def subscriptions(led: Ledger) -> Fact:
    a = chat.subscriptions(led.st, led.txns, led.today)
    model = {"count": a["count"], "monthly": whole(a["monthly"]), "line": a["line"],
             "rows": _strip_rows(a["rows"])}
    return Fact("subscriptions", a, "Looking for subscriptions…", a["line"], None, model)


def trips_and_patterns(led: Ledger) -> Fact:
    a = chat.asks(led.st, led.txns, led.today)
    n_t, n_p = len(a["trips"]), len(a["patterns"])
    line = ("" if n_t or n_p else "Pearl didn’t spot a trip.")
    model = {"trips": [{"name": t.get("name"), "place": t.get("place"), "days": t.get("days"),
                        "count": t.get("count")} for t in a["trips"]],
             "patterns": [{"title": p.get("title") or p.get("merchant"), "count": p.get("count")}
                          for p in a["patterns"]], "line": line or "The cards show what Pearl found."}
    return Fact("asks", a, "Looking for trips…", line, None, model)


def tell(led: Ledger, text: str, category=None, days=None, people=None) -> Fact:
    a = chat.tell(led.st, led.txns, led.today, text, category=category, days=days, people=people)
    model = {"matched": a["matched"], "open": a["open"], "category": a["category"],
             "line": a["line"], "when": a["window"]["label"]}
    return Fact("tell", a, "Matching what you did…", a["line"], None, model)


def plan(led: Ledger, text: str, category=None) -> Fact:
    a = chat.plan(led.st, led.txns, led.today, text=text, category=category)
    model = {"nothing": a["nothing"], "category": a.get("category"),
             "usual": whole(a["usual"]) if a.get("usual") else None,
             "amount": whole(a["amount"]) if a.get("amount") else None,
             "line": comparison_words(a.get("line") or "")}
    return Fact("plan", a, "Working out a plan…", a.get("line") or "", None, model)


# ── The tools the model may call ─────────────────────────────────────────

def _schema(props: dict, required: tuple = ()) -> dict:
    return {"type": "object", "properties": props, "required": list(required),
            "additionalProperties": False}


_MONTH = {"type": "string", "description": "The month: a placeholder such as [DATE1], "
          "or words such as \"last month\". Leave out for this month."}

TOOLS = [
    {"name": "month", "description": "How a month went: money in, spent, the Allowance left "
     "and where it went most. This month also compares with their usual by today. Use for "
     "\"How's this month going?\" or \"How did [DATE1] go?\".",
     "input_schema": _schema({"month": _MONTH})},
    {"name": "merchant_history", "description": "One shop or merchant over a year: the total, "
     "how many visits and a figure per month. Use for \"How much at [SHOP1] this year?\".",
     "input_schema": _schema({"merchant": {"type": "string", "description": "The shop's "
                                           "placeholder, such as [SHOP1]."},
                              "year": {"type": "string", "description": "A placeholder such as [DATE1]. "
                                       "Leave out for this year."}},
                             ("merchant",))},
    {"name": "search", "description": "Find transactions by words (a shop, a note, an amount). "
     "Returns how many match, their total and the latest ten. Use for \"Show my [SHOP1] rides\".",
     "input_schema": _schema({"words": {"type": "string"}, "month": _MONTH}, ("words",))},
    {"name": "cards", "description": "Their credit cards: spent this month, the balance against "
     "the limit, and the due date. Use for \"When are my cards due?\".",
     "input_schema": _schema({})},
    {"name": "spending", "description": "What went to one category, or one place, in one "
     "month, against their usual month.",
     "input_schema": _schema({"category": {"type": "string"}, "month": _MONTH,
                              "merchant": {"type": "string"}})},
    {"name": "subscriptions", "description": "What they pay for again and again that isn't a "
     "bill, and about how much a month.", "input_schema": _schema({})},
    {"name": "trips_and_patterns", "description": "Trips and sorting patterns Pearl has spotted "
     "and is waiting to ask about. Use for \"Was this a trip?\".", "input_schema": _schema({})},
    {"name": "tell", "description": "They told Pearl what they did (\"went out for dinner "
     "Saturday\"): matches it to purchases not sorted yet, as cards they confirm.",
     "input_schema": _schema({"category": {"type": "string"},
                              "days": {"type": "array", "items": {"type": "string"},
                                       "description": "The days they meant, as "
                                       "placeholders such as [DATE1]."},
                              "people": {"type": "array", "items": {"type": "string"}}})},
]

PLAN_TOOL = {"name": "plan", "description": "A monthly plan for one category, from their "
             "usual month. Only when they ask for a plan or budget.",
             "input_schema": _schema({"category": {"type": "string"}}, ("category",))}


def tools(plans: bool = False) -> list[dict]:
    return TOOLS + ([PLAN_TOOL] if plans else [])


def _s(inp: dict, key: str) -> str | None:
    v = inp.get(key)
    return " ".join(v.split())[:80] if isinstance(v, str) and v.strip() else None


def _ym(led: Ledger, value: str | None) -> str | None:
    """A month the model named, filled back in (Phase 2b): "2026-10", or
    what she said ("October", "last month"); None when it named none."""
    if not value:
        return None
    if re.fullmatch(r"\d{4}-\d{2}", value):
        return value
    m = re.fullmatch(r"(\d{4})-(\d{2})-\d{2}", value)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return chat.month_from(None, value, led.today)


def _year(led: Ledger, value) -> int | None:
    """A year the model named, filled back in: None for none, -1 for one
    Pearl can't use (not a year, or still to come)."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return -1
    if isinstance(value, int):
        year = value
    else:
        m = re.search(r"\b(20\d\d)\b", str(value))
        year = int(m.group(1)) if m else -1
    return year if 2000 <= year <= led.today.year else -1


def _day(led: Ledger, value: str) -> str | None:
    """A day the model named, filled back in: "2026-11-21" or "Nov 21"."""
    value = str(value or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value[:10]):
        return value[:10]
    m = re.fullmatch(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})(?:,?\s+(\d{4}))?", value)
    if not m:
        return None
    abbr = [a.lower() for a in calendar.month_abbr]
    if m.group(1).lower() not in abbr:
        return None
    mon = abbr.index(m.group(1).lower())
    year = int(m.group(3)) if m.group(3) else (led.today.year if mon <= led.today.month
                                               else led.today.year - 1)
    try:
        return date(year, mon, int(m.group(2))).isoformat()
    except ValueError:
        return None


def run_tool(led: Ledger, name: str, inp: dict, text: str, plans: bool = False) -> Fact:
    """One tool, by name, with the model's input. Raises ToolInputError for
    input it can't take."""
    from .ai.loop import ToolInputError
    if not isinstance(inp, dict):
        raise ToolInputError("The input must be an object.")
    if name == "month":
        return month(led, _ym(led, _s(inp, "month")))
    if name == "merchant_history":
        shop = _s(inp, "merchant")
        if not shop:
            raise ToolInputError("Name the shop.")
        year = _year(led, inp.get("year"))
        if year == -1:
            raise ToolInputError("The year must be this year or earlier.")
        return merchant_history(led, shop, year)
    if name == "search":
        words = _s(inp, "words")
        if not words:
            raise ToolInputError("Give the words to look for.")
        return search(led, words, _ym(led, _s(inp, "month")))
    if name == "cards":
        return cards(led)
    if name == "spending":
        return spending(led, text, _s(inp, "category"), _ym(led, _s(inp, "month")),
                        _s(inp, "merchant"))
    if name == "subscriptions":
        return subscriptions(led)
    if name == "trips_and_patterns":
        return trips_and_patterns(led)
    if name == "tell":
        days = [d for d in (_day(led, x) for x in inp.get("days") or [] if isinstance(x, str))
                if d][:31] or None
        people = [str(p)[:40] for p in inp.get("people") or [] if isinstance(p, str)][:12] or None
        return tell(led, text, _s(inp, "category"), days, people)
    if name == "plan" and plans:
        return plan(led, text, _s(inp, "category"))
    raise ToolInputError(f"There is no tool called {name}.")


def step_for(led: Ledger, name: str, inp: dict) -> str:
    """The thinking step, named before the tool runs (PC-23)."""
    inp = inp if isinstance(inp, dict) else {}
    if name == "month":
        ym = _ym(led, _s(inp, "month")) or led.today.strftime("%Y-%m")
        return f"Looking at {month_name(ym)}…"
    if name == "merchant_history" and _s(inp, "merchant"):
        return f"Looking at {_s(inp, 'merchant')}…"
    if name == "search" and _s(inp, "words"):
        return f"Searching for “{_s(inp, 'words')}”…"
    return {"cards": "Looking at your cards…", "spending": "Looking at your spending…",
            "subscriptions": "Looking for subscriptions…",
            "trips_and_patterns": "Looking for trips…", "tell": "Matching what you did…",
            "plan": "Working out a plan…"}.get(name, "Looking…")


# ── What the model may see ───────────────────────────────────────────────

_DROP = {"id", "ids", "account_id", "account_name", "logo", "description", "memo", "key",
         "item", "txn", "proposals", "learnable"}


def scrub(value):
    """Safe to send: no ids or bank text, every string redacted
    (`safety.redact`), and no key the gateway refuses."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()
                if k not in _DROP and not safety._KEY.search(str(k))}
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        return safety.redact(value)
    return value


def for_model(fact: Fact) -> str:
    return json.dumps(scrub(fact.model), sort_keys=True, ensure_ascii=False)


_FIGURE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")


def _figures(value, out: set) -> set:
    if isinstance(value, dict):
        for v in value.values():
            _figures(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _figures(v, out)
    elif isinstance(value, bool) or value is None:
        pass
    elif isinstance(value, (int, float)):
        out.add(whole(value))
        out.add(money(value))
    elif isinstance(value, str):
        out.update(_norm_fig(m) for m in _FIGURE.findall(value))
    return out


def _norm_fig(s: str) -> str:
    return s.replace(" ", "")


def figures_ok(text: str, facts: list[Fact]) -> bool:
    """Every dollar figure in the model's words is one Python worked out.
    A figure it made up, or did sums for, means its words aren't used."""
    allowed: set = set()
    for f in facts:
        _figures(f.data, allowed)
        _figures(f.model, allowed)
    for m in _FIGURE.findall(text or ""):
        fig = _norm_fig(m)
        if fig not in allowed and fig.rstrip("0").rstrip(".") not in allowed:
            return False
    return True


# ── With no model: reading her words in Python ───────────────────────────

_CARD_WORDS = ("card due", "cards due", "credit card", "my cards", "my card", "card limit",
               "credit limit", "due date", "cards")
_SEARCH_WORDS = ("show", "find", "search", "list", "rides", "every")


def builtin(led: Ledger, text: str, plans: bool = False) -> Fact | None:
    """The answer from Python alone, or None when it can't tell what she meant."""
    words = chat._norm(text)
    has = lambda *ps: any(chat._has(words, p) >= 0 for p in ps)   # noqa: E731
    # Advice ("Can I afford a trip?") needs a judgement no tool makes: Pearl
    # says what it can do instead of answering a different question.
    if has("afford", "should i", "worth it", "invest"):
        return None
    if has(*_CARD_WORDS):
        return cards(led)
    if has("subscription", "subscriptions"):
        return subscriptions(led)
    if has("trip", "trips", "travel", "vacation", "holiday"):
        return trips_and_patterns(led)
    if plans and has("plan", "budget"):
        f = plan(led, text)
        if not f.data.get("nothing"):
            return f
    shop = chat._merchant_in(words, led.txns)
    if shop and has(*_SEARCH_WORDS):
        return search(led, shop)
    if shop:
        year = None
        m = re.search(r"\b(20\d\d)\b", text or "")
        if m and int(m.group(1)) <= led.today.year:
            year = int(m.group(1))
        if has("this month", "last month") or any(chat._has(words, n) >= 0 for n in chat.MONTHS):
            f = spending(led, text, merchant=shop)
            if not f.data.get("nothing"):
                return f
        return merchant_history(led, shop, year)
    if has("month", "going", "how did", "so far") or \
            any(chat._has(words, n) >= 0 for n in chat.MONTHS):
        if not chat.category_from(None, text):
            return month(led, chat.month_from(None, text, led.today))
    f = spending(led, text)
    if not f.data.get("nothing"):
        return f
    return None


# ── The examples on the start (PC-21) ────────────────────────────────────

def examples(st, txns, today: date) -> list[str]:
    """Four questions, each sent with one tap: never a hard-coded shop. The
    second names the shop she spends most at this year."""
    year = str(today.year)
    per: dict[str, float] = defaultdict(float)
    names: dict[str, str] = {}
    for t in txns:
        if t.date[:4] == year and t.amount > 0 and counts_as_spending(t) and (t.merchant or "").strip():
            k = merchant_key(t.merchant)
            per[k] += spend_amount(t)
            names.setdefault(k, t.merchant.strip())
    top = max(per.items(), key=lambda kv: kv[1])[0] if per else None
    shop = (f"How much at {names[top]} this year?" if top and not safety.problem(names[top])
            else "Where did my money go last month?")
    return ["How’s this month going?", shop, "When are my cards due?",
            "Any subscriptions I forgot?"]


# ── The answer, as the phone's stream ────────────────────────────────────

MASK_FALLBACK = ("mask_unknown", "mask_number")


def answer(st, *, base, user_id, text: str, today: date, plans: bool = False, client=None,
           now: float | None = None):
    """Yield the stream's events for one question (see the module's doc)."""
    from .ai import loop
    led = Ledger(st, today)
    text = " ".join(str(text or "").split())[:MAX_TEXT]
    facts: list[Fact] = []

    def fact_events(f: Fact):
        yield {"type": "fact", "kind": f.kind, "data": f.data}

    def python_answer(simple_until: str | None = None):
        if simple_until:
            yield {"type": "simple", "until": simple_until}
        f = builtin(led, text, plans)
        if f is None:
            yield {"type": "couldnt"}
            return
        yield {"type": "step", "text": f.step}
        yield from fact_events(f)
        if f.line:
            yield {"type": "words", "text": f.line}
        if f.suggestion:
            yield {"type": "suggestion", **f.suggestion}

    def execute(name, inp):
        f = run_tool(led, name, inp, text, plans)
        facts.append(f)
        return for_model(f), f

    # Her words go after the frozen prompt and tools. No date: the model
    # would only see a placeholder for it, and the tools know what today is.
    # Her people, cards and shops go as placeholders (Phase 2b, mask.py).
    messages = [{"role": "user", "content": safety.redact(text)}]
    kwargs = {"base": base, "user_id": user_id, "now": now, "known": known_terms(led)}
    if client is not None:
        kwargs["client"] = client
    for ev in loop.run("ask", messages, tools(plans), execute, **kwargs):
        kind = ev["kind"]
        if kind == "text":
            yield {"type": "text", "text": ev["text"]}
        elif kind == "reset":
            yield {"type": "reset"}
        elif kind == "step":
            yield {"type": "step", "text": step_for(led, ev["name"], ev["input"])}
        elif kind == "tool":
            yield from fact_events(ev["payload"])
        elif kind == "end":
            reason = ev["reason"]
            if ev["ok"] and ev["tools"]:
                if not figures_ok(ev["text"], facts) or not ev["text"].strip():
                    yield {"type": "words", "text": " ".join(f.line for f in facts if f.line)}
                sugg = next((f.suggestion for f in facts if f.suggestion), None)
                if sugg:
                    yield {"type": "suggestion", **sugg}
            elif ev["ok"]:
                # Words with no tool behind them: unsure, so Pearl's own line.
                yield {"type": "reset"}
                yield {"type": "couldnt"}
            elif reason in ("over_budget", "over_daily"):
                until = first_of_next_month(today) if reason == "over_budget" else "tomorrow"
                if facts:
                    yield {"type": "simple", "until": until}
                    yield {"type": "words", "text": " ".join(f.line for f in facts if f.line)}
                else:
                    yield from python_answer(until)
            elif reason in ("off", "killed", "no_prompt", "no_route", "blocked") and not facts:
                yield from python_answer()
            elif reason in MASK_FALLBACK:
                # A placeholder it made up, or a figure of its own (Phase 2b):
                # Python's answer instead, never the model's words.
                if facts:
                    yield {"type": "words", "text": " ".join(f.line for f in facts if f.line)}
                    sugg = next((f.suggestion for f in facts if f.suggestion), None)
                    if sugg:
                        yield {"type": "suggestion", **sugg}
                else:
                    yield from python_answer()
            elif facts:
                # The model stopped after a tool ran: what Python found stands.
                yield {"type": "words", "text": " ".join(f.line for f in facts if f.line)}
            else:
                yield {"type": "couldnt"}
    yield {"type": "done"}
