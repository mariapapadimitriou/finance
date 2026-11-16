"""Pearl chat (PC-01 to PC-13, note 1340:8893): the evidence and the proposals
behind the iPhone's chat.

The model on the iPhone (Apple Intelligence) reads what she said and ranks and
explains; Python works out every number and every proposal (ios/bots/ai-plan.md).
The model may hand over hints it read from her words (a category, the days, who
was there); with none, this module reads the words itself, so the chat's logic
can be tested without a model.

**Nothing here writes.** Every function only reads the ledger and returns
facts, or proposals for the chat to hold as cards. A proposal changes nothing
until she taps the card's Yes, Set it or Make it, and that tap calls the
existing endpoint for the change (product owner, 2026-11-15: "Nothing changes
until you confirm"):

* a told guess (PC-05):   POST /api/transactions/<id>/mark {case: spending, category}
* a split on it (PC-06):  PUT  /api/transactions/<id>/split (held from Who was it with?)
* a trip (PC-08):         POST /api/trips/asks/<id>/yes | skip
* a pattern (PC-09):      POST /api/pattern-sort/asks/<id>/yes | skip
* a plan (PC-12):         PUT  /api/your-plan/rows/<category> {amount, source: chat}

What she told Pearl isn't kept anywhere: PC-07 "What you told Pearl is
forgotten now."
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta

from .analytics import counts_as_spending, spend_amount
from .categorize import CATEGORIES, NON_SPEND, merchant_key
from .models import Transaction

DEFAULT_DAYS = 7          # note 1340:8893, answer 3: any days with unsorted ones, default the last 7

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
SHORT_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december")

# Words for what she did, to the category they mean. Activities, never
# merchants (house rule: never hard-code merchants). The model normally names
# the category itself; these are for when it doesn't, and for tests.
WORDS: dict[str, tuple[str, ...]] = {
    "Dining": ("eating out", "ate out", "eat out", "went out", "out for dinner", "out with",
               "dinner", "lunch", "brunch", "breakfast", "restaurant", "dined"),
    "Alcohol & Bars": ("drinks", "a drink", "bar", "bars", "pub", "beers", "wine"),
    "Coffee": ("coffee", "latte", "cafe", "café"),
    "Food Delivery": ("ordered in", "delivery", "takeout", "take-out", "take out"),
    "Groceries": ("groceries", "grocery", "food shopping"),
    "Transport": ("taxi", "cab", "ride home", "transit", "subway", "bus", "train", "parking"),
    "Gas & Fuel": ("gas", "fuel", "filled up", "fill up"),
    "Travel": ("flight", "flew", "airport"),
    "Lodging": ("hotel", "motel", "hostel"),
    "Shopping": ("shopping", "clothes", "shoes"),
    "Entertainment": ("movie", "movies", "cinema", "concert", "tickets"),
    "Health": ("pharmacy", "doctor", "dentist", "medicine", "prescription"),
    "Personal Care": ("haircut", "hair cut", "salon", "spa", "nails"),
    "Fitness": ("gym", "yoga", "workout", "pilates"),
    "Gifts & Charity": ("gift", "present", "donation", "donated"),
    "Pets": ("vet", "pet food", "dog", "cat"),
}

# Categories that go together: a told "Dining" can be a guess of Coffee or a
# bar. A row whose guess is in another family doesn't fit (a gas station isn't
# dinner), unless she named the place.
FAMILIES: tuple[frozenset[str], ...] = (
    frozenset({"Dining", "Alcohol & Bars", "Coffee", "Food Delivery"}),
    frozenset({"Transport", "Gas & Fuel"}),
    frozenset({"Travel", "Lodging"}),
    frozenset({"Shopping", "Home", "Gifts & Charity", "Personal Care"}),
    frozenset({"Entertainment", "Streaming", "Fitness"}),
)

# Where a friend's share most often comes from (finance/review.py SHARED): a
# card in these may offer "Maybe split with …?" (PC-06).
SHARED = {"Dining", "Food Delivery", "Alcohol & Bars", "Coffee", "Entertainment",
          "Travel", "Lodging", "Groceries", "Transport"}

# Recurring charges that are bills, not subscriptions (Find subscriptions).
BILLS = {"Rent & Housing", "Utilities", "Insurance", "Phone & Internet", "Taxes",
         "Fees & Interest", "Education"}

NOT_NAMES = {"friends", "family", "work", "the", "my", "a", "some", "people", "everyone",
             "coworkers", "colleagues", "kids", "him", "her", "them", "me", "you"}


# ── Reading her words ──────────────────────────────────────────────────────

def _norm(text: str | None) -> str:
    return " " + re.sub(r"[^a-z0-9&é' ]+", " ", (text or "").lower().replace("’", "'")) + " "


def _has(words: str, phrase: str) -> int:
    """Where the phrase is in her words, as whole words; -1 when it isn't."""
    return words.find(" " + phrase + " ")


def spend_categories(hidden: set[str] | None = None) -> list[str]:
    """The categories a purchase can be, as the app shows them."""
    return [c for c in CATEGORIES if c not in NON_SPEND and c != "Unsorted transfers"
            and c not in (hidden or set())]


def category_from(hint: str | None, text: str | None = None) -> str | None:
    """A category the model named, made one of Pearl's; else read from her words."""
    names = spend_categories()
    if hint:
        h = " ".join(str(hint).split()).lower()
        for c in names:
            if c.lower() == h or c.lower().replace("&", "and") == h:
                return c
        found = category_from(None, hint)
        if found:
            return found
    words = _norm(text)
    if not words.strip():
        return None
    best: tuple[int, int, str] | None = None
    for c in names:
        for name in {c.lower(), c.lower().replace(" & ", " and ")}:
            at = _has(words, name)
            if at >= 0:
                # Her naming a category beats any word for one.
                cand = (0, at, c)
                best = cand if best is None or cand < best else best
    if best:
        return best[2]
    for c, phrases in WORDS.items():
        for p in phrases:
            at = _has(words, p)
            if at >= 0:
                cand = (1, at, c)
                best = cand if best is None or cand < best else best
    return best[2] if best else None


def family(category: str | None) -> frozenset[str]:
    category = category or "Other"
    return next((f for f in FAMILIES if category in f), frozenset({category}))


def window(text: str | None, today: date, days: list[str] | None = None) -> dict:
    """The days she meant: the ones the model gave, a day she named, the
    weekend, yesterday; else the last 7. `label` reads "from the weekend"
    (PC-05), `span` reads "from Sat–Sun" (PC-10)."""
    if days:
        picked = sorted({d for d in (str(x)[:10] for x in days) if _iso(d) and d <= today.isoformat()})
        if picked:
            return _days_window(picked)
    words = _norm(text)
    if _has(words, "weekend") >= 0:
        sat = today - timedelta(days=(today.weekday() - 5) % 7)
        picked = [sat.isoformat()] + ([(sat + timedelta(days=1)).isoformat()] if sat < today else [])
        out = _days_window(picked)
        out["label"] = "the weekend"
        return out
    for word, back in (("yesterday", 1), ("last night", 1), ("today", 0), ("tonight", 0),
                       ("this morning", 0)):
        if _has(words, word) >= 0:
            d = (today - timedelta(days=back)).isoformat()
            out = _days_window([d])
            out["label"] = word if word in ("yesterday", "today") else ("yesterday" if back else "today")
            return out
    named = []
    for i, name in enumerate(WEEKDAYS):
        if _has(words, name) >= 0 or _has(words, name + "s") >= 0:
            named.append((today - timedelta(days=(today.weekday() - i) % 7)).isoformat())
    if named:
        return _days_window(sorted(named))
    start = today - timedelta(days=DEFAULT_DAYS - 1)
    return {"start": start.isoformat(), "end": today.isoformat(),
            "days": [(start + timedelta(days=i)).isoformat() for i in range(DEFAULT_DAYS)],
            "label": f"the last {DEFAULT_DAYS} days", "span": f"the last {DEFAULT_DAYS} days"}


def _iso(s: str) -> bool:
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False


def _days_window(days: list[str]) -> dict:
    ds = [date.fromisoformat(d) for d in days]
    names = [WEEKDAYS[d.weekday()].title() for d in ds]
    short = [SHORT_DAYS[d.weekday()] for d in ds]
    if len(ds) == 1:
        label, span = names[0], short[0]
    elif (ds[-1] - ds[0]).days == len(ds) - 1:
        label = f"{names[0]} to {names[-1]}"
        span = f"{short[0]}–{short[-1]}"
    else:
        label = " and ".join([", ".join(names[:-1]), names[-1]])
        span = ", ".join(short)
    return {"start": days[0], "end": days[-1], "days": days, "label": label, "span": span}


def people_from(text: str | None, known: list[str], hint: list[str] | None = None) -> list[str]:
    """Who she said was there: names the model gave, people she already
    splits with, or names after "with"."""
    out: list[str] = []

    def add(n: str) -> None:
        n = " ".join(str(n).split())
        if n and n.lower() not in NOT_NAMES and n.lower() not in {o.lower() for o in out}:
            out.append(n)

    for n in hint or []:
        match = next((k for k in known if k.lower() == str(n).strip().lower()
                      or k.split()[0].lower() == str(n).strip().lower()), None)
        add(match or n)
    if out:
        return out
    words = _norm(text)
    for k in known:
        first = k.split()[0].lower()
        if _has(words, k.lower()) >= 0 or (len(first) > 1 and _has(words, first) >= 0):
            add(k)
    # "with Jo and Sam": capitalised names after "with", in her own spelling.
    for m in re.finditer(r"\bwith ((?:[A-Z][\w'’-]*)(?:\s*(?:,|and|&)\s*[A-Z][\w'’-]*)*)", text or ""):
        for n in re.split(r"\s*(?:,|\band\b|&)\s*", m.group(1)):
            if n and not any(n.lower() == k.split()[0].lower() for k in out):
                add(n)
    return out


def month_from(hint: str | None, text: str | None, today: date) -> str:
    """"2026-10" for "October" (the latest one so far), "last month"; else this month."""
    if hint and re.fullmatch(r"\d{4}-\d{2}", str(hint)):
        return str(hint)
    words = _norm(text) + " " + _norm(hint)
    if _has(words, "last month") >= 0:
        first = today.replace(day=1) - timedelta(days=1)
        return first.strftime("%Y-%m")
    for i, name in enumerate(MONTHS):
        if _has(words, name) >= 0 or _has(words, name[:3]) >= 0 and name[:3] not in ("may", "mar"):
            year = today.year if i + 1 <= today.month else today.year - 1
            return f"{year}-{i + 1:02d}"
    return today.strftime("%Y-%m")


def month_name(ym: str) -> str:
    return MONTHS[int(ym[5:7]) - 1].title()


def money(x: float) -> str:
    return f"${abs(x):,.2f}"


def whole(x: float) -> str:
    return f"${round(abs(x)):,}"


# ── Tell Pearl what you did (PC-05, PC-06, PC-07, PC-10) ───────────────────

def open_guesses(st, txns: list[Transaction], today: date) -> list[dict]:
    """Needs a look's category questions still open: "not sorted yet".
    review.build, not review.for_store: for_store tidies the ledger once as
    it goes, and the chat only reads."""
    from .review import build
    found_on = {k: v["found_on"] for k, v in st.duplicates().items()}
    review = build(txns, today=today.isoformat(), dismissed=st.dismissed_reviews(),
                   splits=st.splits(), payer=st.payback_people(), found_on=found_on,
                   skipped=st.skipped_reviews(), recurring=st.recurring_transfers())
    return [it for it in review.get("unsure_category") or [] if not it.get("skipped")]


def _past_split_people(st, txns: list[Transaction], t: Transaction) -> list[str]:
    """Who she split this place with last time (note 1340:8893, answer 4)."""
    key = merchant_key(t.merchant or "")
    if not key:
        return []
    by_id = {x.fingerprint: x for x in txns}
    best: tuple[str, list[str]] | None = None
    for txn_id, sp in st.splits().items():
        x = by_id.get(txn_id)
        if x is None or x.fingerprint == t.fingerprint or merchant_key(x.merchant or "") != key:
            continue
        names = [p.get("name") for p in sp.get("people") or [] if p.get("name")]
        if names and (best is None or x.date > best[0]):
            best = (x.date, names)
    return best[1] if best else []


def _named(words: str, t: Transaction) -> bool:
    """She named this place ("dinner at Bar Raval")."""
    name = " ".join(_norm(t.merchant or "").split())
    return len(name) > 2 and _has(words, name) >= 0


def tell(st, txns: list[Transaction], today: date, text: str, category: str | None = None,
         days: list[str] | None = None, people: list[str] | None = None,
         ids: list[str] | None = None) -> dict:
    """What she told Pearl, matched to what isn't sorted yet in those days:
    one proposal per transaction (one card each, never grouped).

    A row fits when its guess is in the told category's family, or Pearl
    couldn't tell what it was (Other). When she names a place, only that
    place fits. `ids` is the model's pick among the rows that fit (it ranks;
    it can't add a row that doesn't)."""
    from .etransfers import known_people
    from .review import _brief
    win = window(text, today, days)
    cat = category_from(category, text)
    wanted = set(win["days"])
    items = [it for it in open_guesses(st, txns, today)
             if it["txn"]["date"][:10] in wanted and it["txn"]["amount"] > 0]
    by_id = {t.fingerprint: t for t in txns}
    words = _norm(text)
    who = people_from(text, known_people(txns, st.splits(), st.payback_people()), people)
    named_any = any(_named(words, by_id[it["txn"]["id"]]) for it in items if it["txn"]["id"] in by_id)
    picked = set(ids) if ids else None
    proposals = []
    for it in sorted(items, key=lambda i: (i["txn"]["date"], -i["txn"]["amount"])):
        t = by_id.get(it["txn"]["id"])
        if t is None or (picked is not None and t.fingerprint not in picked):
            continue
        guess = it.get("guess") or t.category or "Other"
        named = _named(words, t)
        if named_any:
            fits = named
        else:
            fits = cat is not None and (guess == "Other" or guess in family(cat))
        if not fits:
            continue
        to = cat or guess
        split = []
        if to in SHARED:
            split = who or _past_split_people(st, txns, t)
        proposals.append({
            "id": "sort:" + t.fingerprint, "kind": "sort", "key": it["key"], "category": to,
            "was": guess, "split_with": split, "txn": _brief(t),
            # The card's What was this? (T-96) opens on the told category.
            "item": {**it, "guess": to}})
    n, m = len(proposals), len(items)
    return {"said": text, "category": cat, "people": who, "window": win, "open": m,
            "matched": n, "nothing": n == 0, "proposals": proposals,
            # PC-05's line over the first card; PC-10's when nothing fits.
            "line": (f"A guess for {n} of {m} from {win['label']}" if n else
                     f"None of the {m} not sorted yet from {win['span']} fit what you said. "
                     "Your cards stay as they were." if m else
                     f"Nothing from {win['span']} is waiting to be sorted. Your cards stay as they were.")}


# ── Ask about my spending (PC-04) ──────────────────────────────────────────

def _merchant_in(words: str, txns: list[Transaction]) -> str | None:
    """The longest merchant name she said, as the ledger spells it."""
    best = None
    for t in txns:
        name = " ".join(_norm(t.merchant or "").split())
        if len(name) > 2 and _has(words, name) >= 0 and (best is None or len(name) > len(best[0])):
            best = (name, t.merchant)
    return best[1] if best else None


def spending(st, txns: list[Transaction], today: date, text: str | None = None,
             category: str | None = None, month: str | None = None,
             merchant: str | None = None) -> dict:
    """A short answer with the transactions behind it: what went to a
    category (or a place) in a month, against her usual month."""
    from .api import _unusual_months
    from .review import _brief
    from .usual_month import usual
    words = _norm(text)
    ym = month_from(month, text, today)
    cat = category_from(category, text)
    place = merchant or _merchant_in(words, txns)
    if place and not merchant and cat and _has(words, cat.lower()) < 0:
        cat = None                     # "at Pai" names a place, not a category
    if not cat and not place:
        return {"nothing": True, "month": ym,
                "line": "Pearl couldn’t tell which spending you meant."}
    rows = [t for t in txns if t.month == ym and counts_as_spending(t) and t.amount > 0
            and (cat is None or (t.category or "Other") == cat)
            and (place is None or merchant_key(t.merchant or "") == merchant_key(place))]
    rows.sort(key=lambda t: (t.date, t.fingerprint), reverse=True)
    total = round(sum(spend_amount(t) for t in rows), 2)
    the_usual = None
    if cat and not place:
        info = usual(txns, today, unusual=_unusual_months(st))["categories"].get(cat)
        the_usual = info["usual"] if info else None
    per: dict[str, list[float]] = defaultdict(list)
    for t in rows:
        per[t.merchant or t.description].append(spend_amount(t))
    top = None
    if per and (len(per) > 1 or cat):
        name, amounts = max(per.items(), key=lambda kv: (sum(kv[1]), -len(kv[0])))
        top = {"merchant": name, "amount": round(sum(amounts), 2), "count": len(amounts)}
    what = place or cat
    title = f"{what}, {month_name(ym)}"
    if not rows:
        line = f"You didn’t spend anything on {what} in {month_name(ym)}."
    else:
        line = f"You spent {whole(total)} {'at' if place else 'on'} {what} in {month_name(ym)}"
        if the_usual is not None:
            diff = total - the_usual
            if abs(diff) < 1:
                line += ", about your usual"
            else:
                line += f", {whole(diff)} {'more' if diff > 0 else 'less'} than usual"
        line += "."
        if top and len(per) > 1:
            line += (f" {top['merchant']} was {whole(top['amount'])} of it"
                     + (f", across {top['count']} purchases." if top["count"] > 1 else "."))
    return {"nothing": False, "title": title, "category": cat, "merchant": place, "month": ym,
            "month_name": month_name(ym), "total": total, "usual": the_usual, "top": top,
            "count": len(rows), "rows": [_brief(t) for t in rows[:25]], "line": line}


# ── Find subscriptions ─────────────────────────────────────────────────────

def subscriptions(st, txns: list[Transaction], today: date) -> dict:
    """What she pays for again and again that isn't a bill, newest charge of each."""
    from .insights.recurring import detect_recurring
    from .review import _brief
    found = [r for r in detect_recurring(txns, as_of=today.isoformat())
             if r["active"] and r["category"] not in BILLS]
    rows = []
    for r in found:
        last = max((t for t in txns if t.merchant == r["merchant"] and t.amount > 0
                    and t.date[:10] == r["last_seen"][:10]), key=lambda t: t.fingerprint, default=None)
        if last is not None:
            rows.append({**_brief(last), "cadence": r["cadence"], "monthly": r["monthly_cost"]})
    monthly = round(sum(r["monthly_cost"] for r in found), 2)
    n = len(rows)
    line = (f"You have {n} subscription{'s' if n != 1 else ''}, about {whole(monthly)} a month."
            if n else "Pearl didn’t find any subscriptions.")
    return {"count": n, "monthly": monthly, "rows": rows, "line": line}


# ── Trips and patterns (PC-08, PC-09) ──────────────────────────────────────

def asks(st, txns: list[Transaction], today: date) -> dict:
    """The trip and pattern questions Quick sort has too (review's
    `trip_asks` and `pattern_asks`): one pending state, so answering in
    either place clears the other."""
    from . import pattern_sort, trips
    if not pattern_sort.is_on(st):
        return {"patterns": [], "trips": []}
    day = today.isoformat()
    return {"patterns": pattern_sort.pending(st, day, txns), "trips": trips.candidates(st, txns, day)}


# ── A plan (PC-12, PC-13) ──────────────────────────────────────────────────

def plan(st, txns: list[Transaction], today: date, text: str | None = None,
         category: str | None = None) -> dict:
    """"Make a Dining out plan of $220 a month?": her usual month for the
    category, rounded up to the next $10, the one rule for suggestions that
    Your plan's Suggest a plan follows too (`your_plan.round_up_10`). Plans
    keep the nearest $5 (note 1353:11493), so $220 stays $220: what she's
    shown is what Set it keeps, in Your plan and, once the plan is in use,
    in the Allowance."""
    from . import category_budgets as cb
    from . import your_plan
    from .api import _unusual_months
    from .usual_month import usual
    cat = category_from(category, text)
    u = usual(txns, today, unusual=_unusual_months(st))
    info = u["categories"].get(cat) if cat else None
    if not cat or not info or info["usual"] <= 0 or cat in cb.LEFT_OUT:
        return {"nothing": True, "category": cat,
                "line": "Pearl needs a month or more of that spending to make a plan."}
    the_usual = info["usual"]
    amount = your_plan.round_up_10(the_usual)
    state = your_plan.load(st)
    now = next((r["amount"] for r in state["rows"] if r["category"] == cat), None)
    return {"nothing": False, "category": cat, "usual": the_usual, "amount": amount,
            "months": len(u["months"]), "current": now, "in_use": state["in_use"]}


# ── The button and the start (PB-01, PC-03) ────────────────────────────────

def start(st, txns: list[Transaction], today: date) -> dict:
    """PB-01's "has a suggestion" (a trip or pattern waiting), and what the
    model may name: her categories and the people she splits with."""
    from .etransfers import known_people
    from .marks import hidden_categories
    waiting = asks(st, txns, today)
    # The cards themselves too (2026-11-15): the chat opens on them, and
    # asking /api/chat/asks after this was a second trip for the same answer.
    return {"suggest": bool(waiting["patterns"] or waiting["trips"]), "asks": waiting,
            "categories": spend_categories(hidden_categories(st)),
            "people": known_people(txns, st.splits(), st.payback_people()),
            "today": today.isoformat()}
