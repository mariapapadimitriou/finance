"""Worth a look on Home (2026-11-18): at most three things, one line each.

* GET  /api/worth-a-look   {"items": [...]}
* POST /api/worth-a-look   {"action", "ids" | "id"}: seen, not_now, clear,
                           undo_clear, yes, undo_yes, got_it. Every reply has
                           "ok" and the fresh "items".

An item is one event (`id`): the same thing again has the same id, a new
event a new one. Each comes only from what Pearl already knows; none is
plain news or a single transaction on its own.

Rules (product owner):

* At most `MAX_ITEMS`: every `yes` first, then `heads_up`, then the one best
  `good` item, last, if there's room. When there is a heads-up, `yes` items
  take at most `MAX_ITEMS - 1`, so the heads-up always shows.
* Not now is for good, for that id. Clear hides what was passed and
  everything else that qualifies today (TEST-40); Undo brings it back. Seen (she tapped it) hides it too.
* An item drops off `DROP_DAYS` after it was first shown
  (`worth_a_look_state.first_shown`).
* Questions Quick sort also asks (a possible duplicate, a trip) come from
  the same open question (`review.for_store`), so answering it there takes
  the item away. Yes here, on a new subscription, is I-04's answer
  (`income_bills_api.confirm_bills`); on a price rise, the bill's amount.
  Not now only hides the Home item: the question stays where it was.
* T-74 (AP-Paycheque): a month with a third paycheque is good news with
  its own "Got it" (`ack`), which is Home's old note's Got it
  (`/review/dismiss`); a tap opens that month's income.
* Your plan and Save are parked: no item opens either (plan pace is off;
  the new month opens Home's Allowance).
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from flask import jsonify, request

from . import api as core
from . import income_bills as ib
from .api import bp, store

MAX_ITEMS = 3
DROP_DAYS = 7
MAX_IDS = 50
# A subscription is new for this long after its first charge.
NEW_DAYS = 100
# Heads-ups: a bill this many days ahead, a card payment.
BILL_DAYS = 3
CARD_DAYS = 5
UNSETTLED_DAYS = 7
UNPAID_DAYS = 21
NEW_MONTH_DAYS = 3
# Good news: money less than last month by at least this much.
LESS_BY = 20.0
COMPARE = {"Food Delivery": "takeout", "Dining": "dining out"}
# A price rise worth asking about: at least this much, and this share.
RISE_MIN, RISE_SHARE = 1.0, 0.04
# A trip ask is news here only if it ended this recently. Quick sort asks
# about every trip in her history (finance/trips.py); after Start over that
# can be years of them, and Home stays about now.
TRIP_DAYS = 120

TIERS = ("yes", "heads_up", "good")
ACTIONS = ("seen", "not_now", "clear", "undo_clear", "yes", "undo_yes", "got_it")
ACK_KINDS = ("paycheque",)
YES_KINDS = ("subscription", "price_rise")
HIDDEN = ("seen", "not_now", "cleared", "yes")


# ── Words ─────────────────────────────────────────────────────────────────

def _money(x: float) -> str:
    return f"${x:,.2f}"


def _dollars(x: float) -> str:
    """Whole dollars when it is whole, else to the cent: "$3", "$2.50"."""
    x = round(abs(x), 2)
    return f"${round(x):,}" if abs(x - round(x)) < 0.005 else f"${x:,.2f}"


_PER = {"monthly": "/mo", "annual": "/yr", "quarterly": "/3 mo", "semiannual": "/6 mo",
        "bimonthly": "/2 mo", "weekly": "/wk", "biweekly": "/2 wk"}


def _when(day: date, today: date) -> str:
    n = (day - today).days
    return "today" if n == 0 else "tomorrow" if n == 1 else day.strftime("%A")


def _days(day: date, today: date) -> str:
    n = (day - today).days
    return "today" if n == 0 else "tomorrow" if n == 1 else f"in {n} days"


def _span(start: str, end: str) -> str:
    """"Nov 7–10", or "Oct 30–Nov 2" across a month."""
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if (a.year, a.month) == (b.year, b.month):
        return f"{a.strftime('%b')} {a.day}–{b.day}"
    return f"{a.strftime('%b')} {a.day}–{b.strftime('%b')} {b.day}"


def _key(merchant: str) -> str:
    return " ".join((merchant or "").lower().split())


def _item(id_: str, kind: str, tier: str, title: str, icon: str, tone: str, *,
          amount: str | None = None, yes: str | None = None, target: dict | None = None,
          rank: float = 0.0, data: dict | None = None, ack: str | None = None) -> dict:
    out = {"id": id_, "kind": kind, "tier": tier, "title": title, "amount": amount,
           "icon": icon, "tone": tone, "yes": yes, "ack": ack,
           "target": ({"screen": target.get("screen"), "id": target.get("id"),
                       "name": target.get("name"), "month": target.get("month")}
                      if target else None),
           "since": None}
    out["_rank"] = rank
    out["_data"] = data or {}
    return out


# ── What qualifies ────────────────────────────────────────────────────────

class _Ctx:
    """What the kinds read, worked out once a request."""

    def __init__(self, st, today: date):
        self.st = st
        self.today = today
        self.txns = st.all_transactions()
        self.names = st.merchant_names()
        self._bills = None
        self._recs = None

    def name(self, merchant: str) -> str:
        return self.names.get(_key(merchant)) or merchant or ""

    def bill_state(self) -> dict:
        return ib.load(self.st)

    def bills(self) -> list[dict]:
        if self._bills is None:
            self._bills = ib.bills(self.txns, self.today, self.bill_state())
        return self._bills

    def recs(self) -> list[dict]:
        if self._recs is None:
            from .insights.recurring import detect_recurring
            self._recs = detect_recurring(self.txns, as_of=self.today.isoformat())
        return self._recs


def _subscriptions(ctx: _Ctx) -> list[dict]:
    """A new recurring charge in a subscription category that she hasn't
    answered in I-04 (or kept on Insights)."""
    from .recommendations import SUBSCRIPTION_CADENCES, SUBSCRIPTION_CATEGORIES
    if not ctx.st.plaid_history_ready(ctx.today.isoformat()):
        return []                   # a recent slice only: everything would look new
    kept = core._json_setting(ctx.st, "subscription_choices", {})
    since = (ctx.today - timedelta(days=NEW_DAYS)).isoformat()
    out = []
    for r in ctx.bills():
        rec = r.get("rec")
        if (r["source"] != "found" or r.get("counts") is not None or r.get("question")
                or r.get("rent") or not rec or not rec.get("active")
                or rec.get("category") not in SUBSCRIPTION_CATEGORIES
                or rec.get("cadence") not in SUBSCRIPTION_CADENCES
                or rec["first_seen"] < since or rec["merchant"] in kept):
            continue
        name = ctx.name(r["name"])
        out.append(_item(f"subscription:{r['key']}", "subscription", "yes",
                         f"New subscription: {name}", "subscription", "rose",
                         amount=f"{_money(rec['amount'])}{_PER.get(rec['cadence'], '')}",
                         yes="Yes", rank=-len(rec["dates"]),
                         data={"key": r["key"], "name": name}))
    return out


def _price_rises(ctx: _Ctx) -> list[dict]:
    """A bill she counts whose last charge was more than the bill says.
    Her own amount (I-05, or a bill she added) is compared as it is; for one
    Pearl found, the last charge is compared with the one before it
    (product owner, 2026-11-19), never a median over her whole history, so
    a rise from a year ago isn't news after Start over. A bill she says
    varies isn't asked about."""
    recs = {_key(r["merchant"]): r for r in ctx.recs() if r.get("active")}
    state = ctx.bill_state()
    out = []
    for r in ctx.bills():
        if r.get("counts") is not True or r.get("rent"):
            continue
        if r["source"] == "added":
            added = next((b for b in state["added"] if f"added:{b['id']}" == r["key"]), {})
            if added.get("varies"):
                continue
            rec = recs.get(_key(r.get("merchant") or "")) or recs.get(_key(r["name"]))
            own = True
        else:
            answer = state["bills"].get(r["key"]) or {}
            if answer.get("varies") is True:
                continue
            rec = r.get("rec")
            own = bool(answer.get("amount"))
        if not rec or not rec.get("active"):
            continue
        if own:
            billed = r["full"]
        elif rec.get("previous_amount") is not None:
            billed = rec["previous_amount"]
        else:
            continue
        latest, billed = round(rec["amount"], 2), round(billed, 2)
        rise = round(latest - billed, 2)
        if rise < max(RISE_MIN, billed * RISE_SHARE):
            continue
        name = ctx.name(r["name"])
        out.append(_item(f"price_rise:{r['key']}:{int(round(latest * 100))}", "price_rise", "yes",
                         f"{name} went up {_dollars(rise)}", "price", "rose",
                         yes="Update the bill", rank=-rise,
                         data={"key": r["key"], "name": name, "amount": latest}))
    return out


def _review(ctx: _Ctx) -> dict:
    from .review import for_store
    return for_store(ctx.st, ctx.today.isoformat())


def _duplicates(ctx: _Ctx, review: dict) -> list[dict]:
    """Quick sort's "Is this the same purchase?" while it is open."""
    out = []
    for it in review.get("duplicate") or []:
        if it.get("skipped"):
            continue
        t = it["txn"]
        out.append(_item(f"duplicate:{t['id']}", "duplicate", "yes",
                         f"Double charge at {ctx.name(t.get('merchant') or '')}?", "duplicate", "rose",
                         target={"screen": "transaction", "id": t["id"]},
                         rank=-(date.fromisoformat(t["date"][:10]).toordinal())))
    return out


def _trips(ctx: _Ctx, review: dict) -> list[dict]:
    """Quick sort's trip question (TR-01) while it is open."""
    out = []
    recent = (ctx.today - timedelta(days=TRIP_DAYS)).isoformat()
    for c in review.get("trip_asks") or []:
        if c["end"] < recent:
            continue
        where = f"in {c['place']}" if c.get("place") else "away"
        out.append(_item(f"trip:{c['id']}", "trip", "yes",
                         f"Were you {where} {_span(c['start'], c['end'])}?", "trip", "rose",
                         target={"screen": "trip", "id": c["id"], "name": c.get("name") or None},
                         rank=-(date.fromisoformat(c["end"]).toordinal())))
    return out


def _bills_due(ctx: _Ctx) -> list[dict]:
    """A bill she confirmed comes out in the next few days."""
    end = ctx.today + timedelta(days=BILL_DAYS)
    out = []
    for r in ctx.bills():
        if r.get("counts") is not True or not r.get("next"):
            continue
        anchor = date.fromisoformat(r["next"][:10])
        days = ib.occurrences(anchor, r["cadence"], ctx.today, end)
        if not days:
            continue
        day = days[0]
        rent = bool(r.get("rent")) or r.get("category") == ib.RENT
        name = "Rent" if rent else ctx.name(r["name"])
        out.append(_item(f"bill_due:{r['key']}:{day.isoformat()}", "bill_due", "heads_up",
                         f"{name} comes out {_when(day, ctx.today)}", "home" if rent else "bill", "warn",
                         amount=_money(r["amount"]),
                         target={"screen": "bill", "id": r["key"], "name": r["name"]},
                         rank=day.toordinal()))
    return out


def _cards_due(ctx: _Ctx) -> list[dict]:
    """A debt payment due within a few days, from the due day she gave."""
    import calendar

    from . import debts as debt_math, safe_to_spend
    debts = core._debts(ctx.st, ctx.txns, ctx.today)["debts"]
    lines = {b["label"]: b for b in debt_math.bills(
        debts, ctx.txns, ctx.today, safe_to_spend.recurring_bills(ctx.txns, ctx.today))["lines"]}
    out = []
    for d in debts:
        if not d.get("due_day"):
            continue
        due = date.fromisoformat(d["due_date"])
        this_month = due >= ctx.today
        if not this_month:
            nxt = ib._add_months(ctx.today.replace(day=1), 1, 1)
            due = nxt.replace(day=min(int(d["due_day"]), calendar.monthrange(nxt.year, nxt.month)[1]))
        if (due - ctx.today).days > CARD_DAYS:
            continue
        amount = None
        if d.get("minimum"):
            line = lines.get(f"{d['name']} minimum")
            if this_month:
                if line is None:
                    continue                    # paid already this month
                amount = line["amount"]
            else:
                amount = d["minimum"]
        out.append(_item(f"card_due:{d['account_id']}:{due.isoformat()}", "card_due", "heads_up",
                         f"{d['name']} is due {_days(due, ctx.today)}", "card", "warn",
                         amount=_money(amount) if amount else None,
                         target={"screen": "debt", "id": d["account_id"], "name": d["name"]},
                         rank=due.toordinal()))
    return out


def _owed(ctx: _Ctx) -> dict:
    from . import parts
    return parts.owed(ctx.st, ctx.txns, ctx.today)


def _unsettled(ctx: _Ctx, owed: dict) -> list[dict]:
    """A Not sure yet split on a purchase more than a week old."""
    cutoff = (ctx.today - timedelta(days=UNSETTLED_DAYS)).isoformat()
    out = []
    for r in owed.get("not_settled") or []:
        if r["date"] >= cutoff:
            continue
        out.append(_item(f"unsettled_split:{r['charge_id']}", "unsettled_split", "heads_up",
                         f"{ctx.name(r['merchant'])} isn’t settled yet", "people", "rose",
                         target={"screen": "transaction", "id": r["charge_id"]},
                         rank=date.fromisoformat(r["date"]).toordinal()))
    return out


def _unpaid(ctx: _Ctx, owed: dict) -> list[dict]:
    """Someone who has owed her a share for three weeks or more."""
    out = []
    for p in owed.get("owes_you") or []:
        items = sorted(p.get("items") or [], key=lambda i: i["date"])
        if not items:
            continue
        oldest = items[0]
        age = (ctx.today - date.fromisoformat(oldest["date"])).days
        if age < UNPAID_DAYS:
            continue
        weeks = age // 7
        out.append(_item(f"unpaid:{_key(p['name'])}:{oldest['charge_id']}", "unpaid", "heads_up",
                         f"{p['name']} hasn’t paid back in {weeks} weeks", "person", "rose",
                         target={"screen": "owed_person", "name": p["name"]}, rank=-age))
    return out


def _new_month(ctx: _Ctx) -> list[dict]:
    """The first days of a month, once the Allowance has a number."""
    if ctx.today.day > NEW_MONTH_DAYS:
        return []
    sts = core._home_sts(ctx.st, ctx.txns, ctx.today)
    shown = sts.get("shown")
    if shown is None or sts.get("state") != "ok":
        return []
    month = ctx.today.strftime("%Y-%m")
    return [_item(f"new_month:{month}", "new_month", "heads_up",
                  f"New month · Allowance is ${int(shown):,}", "calendar", "rose",
                  target={"screen": "allowance", "month": month})]


def _paycheque(ctx: _Ctx, review: dict) -> list[dict]:
    """T-74: a month that held a third paycheque (review's three_pay_month,
    what Home's note showed), until she says Got it."""
    import calendar
    out = []
    for m in review.get("three_pay_month") or []:
        if m.get("skipped"):
            continue
        month = m["month"]
        name = calendar.month_name[int(month[5:7])]
        out.append(_item(f"paycheque:{month}", "paycheque", "good", f"3 paycheques in {name}",
                         "pay", "good", ack="Got it", data={"key": m["key"]},
                         target={"screen": "income", "month": month},
                         rank=-date.fromisoformat(month + "-01").toordinal()))
    return out


def _piggy_halfway(ctx: _Ctx) -> list[dict]:
    """A piggy bank that has reached half its goal (and isn't full)."""
    from . import piggy
    charges = ctx.st.bank_charges_by_month()
    out = []
    for b in ctx.st.piggy_banks():
        if b.target <= 0:
            continue
        s = piggy.status(b, charges.get(b.id, {}), ctx.today.isoformat())
        share = max(s["held"], 0.0) / b.target
        if not 0.5 <= share < 1.0:
            continue
        out.append(_item(f"piggy_halfway:{b.id}", "piggy_halfway", "good",
                         f"{b.name} is halfway there", "piggy", "good",
                         target={"screen": "piggy", "id": b.id, "name": b.name}, rank=-share))
    return out


def _month_compare(ctx: _Ctx) -> list[dict]:
    """Less on takeout or dining out than last month by this day."""
    from .analytics import counts_as_spending, spend_amount
    if not ctx.txns:
        return []
    first = ctx.today.replace(day=1)
    last_start = ib._add_months(first, -1, 1)
    if min(t.date[:10] for t in ctx.txns) > last_start.isoformat():
        return []                               # no full last month to compare with
    import calendar
    upto = last_start.replace(day=min(ctx.today.day,
                                      calendar.monthrange(last_start.year, last_start.month)[1]))
    now, then = {}, {}
    for t in ctx.txns:
        if t.category not in COMPARE or not counts_as_spending(t):
            continue
        d = t.date[:10]
        if first.isoformat() <= d <= ctx.today.isoformat():
            now[t.category] = now.get(t.category, 0.0) + spend_amount(t)
        elif last_start.isoformat() <= d <= upto.isoformat():
            then[t.category] = then.get(t.category, 0.0) + spend_amount(t)
    month = ctx.today.strftime("%Y-%m")
    out = []
    for cat, words in COMPARE.items():
        less = round(then.get(cat, 0.0) - now.get(cat, 0.0), 2)
        if less < LESS_BY:
            continue
        out.append(_item(f"month_compare:{cat}:{month}", "month_compare", "good",
                         f"{_dollars(round(less))} less on {words} than {last_start.strftime('%B')}",
                         "trend_down", "good", target={"screen": "category", "name": cat, "month": month},
                         rank=-less + 1_000_000))       # after any piggy bank
    return out


def candidates(st, today: date) -> list[dict]:
    """Every item that qualifies today, before her answers and the cap."""
    ctx = _Ctx(st, today)
    review = _review(ctx)
    owed = _owed(ctx)
    groups = [
        _subscriptions(ctx), _price_rises(ctx), _duplicates(ctx, review), _trips(ctx, review),
        # Plan pace waits while Your plan is parked (no item opens it).
        _bills_due(ctx), _cards_due(ctx), _unsettled(ctx, owed), _unpaid(ctx, owed),
        _new_month(ctx), _paycheque(ctx, review), _piggy_halfway(ctx), _month_compare(ctx),
    ]
    out = []
    for order, group in enumerate(groups):
        for it in group:
            it["_order"] = order
            out.append(it)
    return out


# ── Her answers ───────────────────────────────────────────────────────────

def _rows(st) -> dict[str, dict]:
    with st.conn() as c:
        rows = c.execute("SELECT item_id, first_shown, state, at, undo FROM worth_a_look_state").fetchall()
    return {r["item_id"]: dict(r) for r in rows}


def _set_state(st, item_id: str, state: str | None, today: date, undo: str | None = None) -> None:
    with st.conn() as c:
        c.execute("INSERT OR IGNORE INTO worth_a_look_state (item_id, first_shown) VALUES (?, ?)",
                  (item_id, today.isoformat()))
        c.execute("UPDATE worth_a_look_state SET state = ?, at = ?, undo = ? WHERE item_id = ?",
                  (state, today.isoformat(), undo, item_id))


def _shown(st, ids: list[str], today: date) -> None:
    if not ids:
        return
    with st.conn() as c:
        for i in ids:
            c.execute("INSERT OR IGNORE INTO worth_a_look_state (item_id, first_shown) VALUES (?, ?)",
                      (i, today.isoformat()))


def _rank(found: list[dict], rows: dict[str, dict], today: date) -> list[dict]:
    drop = (today - timedelta(days=DROP_DAYS)).isoformat()
    live = []
    for it in found:
        row = rows.get(it["id"])
        if row and (row["state"] in HIDDEN or row["first_shown"] <= drop):
            continue
        live.append(it)
    live.sort(key=lambda it: (TIERS.index(it["tier"]), it["_order"], it["_rank"], it["id"]))
    yes = [it for it in live if it["tier"] == "yes"]
    heads = [it for it in live if it["tier"] == "heads_up"]
    good = [it for it in live if it["tier"] == "good"]
    # A heads-up (a bill, a card due) always has a place (product owner,
    # 2026-11-19): questions take at most MAX_ITEMS - 1 then.
    if heads:
        yes = yes[:MAX_ITEMS - 1]
    return (yes + heads + good[:1])[:MAX_ITEMS]


def items(st, today: date, found: list[dict] | None = None) -> list[dict]:
    """What Home shows now, in order. Showing an item starts its 7 days."""
    found = candidates(st, today) if found is None else found
    shown = _rank(found, _rows(st), today)
    _shown(st, [it["id"] for it in shown], today)
    rows = _rows(st)
    return [{**{k: v for k, v in it.items() if not k.startswith("_")},
             "since": rows[it["id"]]["first_shown"]} for it in shown]


# ── Yes, and Undo ─────────────────────────────────────────────────────────

def _yes(st, it: dict, today: date) -> tuple[str, dict]:
    """Do what Yes says; return the toast and what Undo needs."""
    state = ib.load(st)
    key = it["_data"]["key"]
    undo = json.loads(json.dumps({"key": key, "bill": state["bills"].get(key),
                                  "bills_on": state["bills_on"]}))       # a copy, not the live entry
    if it["kind"] == "subscription":
        from .income_bills_api import confirm_bills
        confirm_bills(st, {key: True}, today)
        return f"{it['_data']['name']} added to subscriptions", undo
    amount = it["_data"]["amount"]
    if key.startswith("added:"):
        bill = next((b for b in state["added"] if f"added:{b['id']}" == key), None)
        if bill is not None:
            undo["added_amount"] = bill["amount"]
            bill["amount"] = amount
    else:
        entry = state["bills"].setdefault(key, {})
        entry["amount"] = amount
        entry["state"] = "yes"
    ib.save(st, state)
    return f"{it['_data']['name']} bill updated", undo


def _undo_yes(st, undo: dict) -> None:
    state = ib.load(st)
    key = undo["key"]
    if "added_amount" in undo:
        bill = next((b for b in state["added"] if f"added:{b['id']}" == key), None)
        if bill is not None:
            bill["amount"] = undo["added_amount"]
    elif undo.get("bill") is None:
        state["bills"].pop(key, None)
    else:
        state["bills"][key] = undo["bill"]
    if not undo.get("bills_on"):
        state["bills_on"] = None
    ib.save(st, state)


# ── The endpoints ─────────────────────────────────────────────────────────

def _today() -> date:
    return date.fromisoformat(core._today_iso())


@bp.get("/worth-a-look")
def worth_a_look_get():
    return jsonify({"items": items(store(), _today())})


@bp.post("/worth-a-look")
def worth_a_look_post():
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}
    action = body.get("action")
    if action not in ACTIONS:
        return jsonify({"error": "Say what to do with it."}), 400
    ids = body.get("ids")
    if ids is None:
        ids = [body["id"]] if "id" in body else []
    if not isinstance(ids, list) or len(ids) > MAX_IDS or not all(isinstance(i, str) for i in ids):
        return jsonify({"error": "Which items?"}), 400
    ids = list(dict.fromkeys(ids))
    st, today = store(), _today()
    rows = _rows(st)
    out: dict = {"ok": True}

    if action in ("seen", "not_now", "clear"):
        found = candidates(st, today)
        known = {it["id"] for it in found} | set(rows)
        if action == "clear":
            # TEST-40: Clear leaves Home calm until something new happens, so
            # it clears everything that qualifies today, not only what shows.
            ids = list(dict.fromkeys(ids + [it["id"] for it in found]))
        done = []
        for i in ids:
            if i not in known:
                continue                        # unknown ids are ignored
            row = rows.get(i)
            if action == "clear" and row and row["state"] in HIDDEN:
                continue
            _set_state(st, i, {"seen": "seen", "not_now": "not_now", "clear": "cleared"}[action], today)
            done.append(i)
        if action == "clear":
            out["cleared"] = done
        return jsonify({**out, "items": items(st, today, found)})

    if action == "got_it":
        # T-74's Got it: the note doesn't come back (as /review/dismiss).
        if not ids or not {i.split(":", 1)[0] for i in ids} <= set(ACK_KINDS):
            return jsonify({"error": "Only a paycheque note has Got it."}), 400
        found = {it["id"]: it for it in candidates(st, today)}
        for i in ids:
            it = found.get(i)
            if it is None:
                continue
            st.dismiss_review(it["_data"]["key"])
            _set_state(st, i, "seen", today)
        return jsonify({**out, "items": items(st, today)})

    if action == "undo_clear":
        done = [i for i in ids if (rows.get(i) or {}).get("state") == "cleared"]
        for i in done:
            _set_state(st, i, None, today)
        return jsonify({**out, "restored": done, "items": items(st, today)})

    if action == "yes":
        kinds = {i.split(":", 1)[0] for i in ids}
        if not ids or not kinds <= set(YES_KINDS):
            return jsonify({"error": "Only a new subscription or a price rise can be answered here."}), 400
        found = {it["id"]: it for it in candidates(st, today)}
        toasts = []
        for i in ids:
            it = found.get(i)
            if it is None or (rows.get(i) or {}).get("state") in HIDDEN:
                continue
            toast, undo = _yes(st, it, today)
            _set_state(st, i, "yes", today, undo=json.dumps(undo))
            toasts.append(toast)
        out["toast"] = toasts[0] if len(toasts) == 1 else (f"{len(toasts)} updated" if toasts else None)
        return jsonify({**out, "items": items(st, today)})

    # undo_yes
    done = []
    for i in ids:
        row = rows.get(i) or {}
        if row.get("state") != "yes" or not row.get("undo"):
            continue
        try:
            _undo_yes(st, json.loads(row["undo"]))
        except (TypeError, ValueError, KeyError):
            continue
        _set_state(st, i, None, today, undo=None)
        done.append(i)
    return jsonify({**out, "undone": done, "items": items(st, today)})
