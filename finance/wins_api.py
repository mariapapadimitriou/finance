"""Wins (THL-246, THL-247, THL-249, THL-250, THL-251; finance/wins.py).

* GET  /api/wins                          the whole page: the path, pearls,
  streaks, the latest recap, challenges and the Save pointer.
* GET  /api/wins/streaks/<key>            one streak with its periods (ST-01, ST-02).
* GET  /api/wins/challenges               what Pearl suggests, priced from her spending (CH-01).
* POST /api/wins/challenges               {kind, target?, merchant?}: start one (CH-02).
* GET  /api/wins/challenges/<id>          where it stands, recent rows, chests (CH-03 to CH-05).
* POST /api/wins/challenges/<id>/stop     stop it; neutral words.
* POST /api/wins/challenges/<id>/chest    {bank_id}: put what she saved in a chest (CH-04).
* GET  /api/wins/recaps/<month>           a past recap (RC-01); amounts for the share
  image are hers to switch on (RC-02).
* GET  /api/wins/events                   what was earned, for notifications and analytics.
* GET  /api/wins/moment                   the "You earned a pearl" sheet to show on open (THL-256).
* POST /api/wins/moment/seen              {keys}: shown; never again for those pearls.
"""

from __future__ import annotations

from datetime import date

from flask import jsonify, request

from . import api as core
from . import wins
from .api import bp, store


def _today() -> date:
    return date.fromisoformat(core._today_iso())


def context(st):
    """Everything the engine reads, worked out once."""
    from . import kinds as kinds_mod, safe_to_spend, usual_month
    from .growth_api import _invested
    from .review import build as review_build
    today = _today()
    txns = st.all_transactions()
    sts = core._home_sts(st, txns, today)
    types = {aid: r.get("account_type") or ""
             for aid, r in st.account_sync_rules().items() if r.get("enabled")}
    state = safe_to_spend.home_state(txns, today, sts, account_types=types,
                                     told_income=st.float_setting("home_income", 0.0),
                                     told_rent=st.float_setting("home_rent", 0.0))
    path = core._path(st, txns, today, sts, state, types)
    anchor = core._anchor(st, txns, today.isoformat())
    review = review_build(txns, dismissed=st.dismissed_reviews(), splits=st.splits(),
                          payer=st.payback_people(), skipped=st.skipped_reviews())
    kinds = kinds_mod.kind_map(st, txns, today)
    usual = usual_month.usual(txns, today, unusual=core._unusual_months(st), kinds=kinds)
    invest_done = bool(core._json_setting(st, "unveil_reported", None)) or _invested(types)
    return {"today": today, "txns": txns, "path": path, "anchor": anchor,
            "review_count": review.get("count", 0), "invest_done": invest_done, "usual": usual}


def page(st) -> dict:
    c = context(st)
    return wins.evaluate(st, c["txns"], c["today"], anchor=c["anchor"], path=c["path"],
                         review_count=c["review_count"], invest_done=c["invest_done"],
                         usual=c["usual"])


def summary(st, txns, today, *, anchor, path, review_count, usual) -> dict:
    """Home's "Your next step" card: how far along the path, and what's next."""
    from .growth_api import _invested
    types = {aid: r.get("account_type") or ""
             for aid, r in st.account_sync_rules().items() if r.get("enabled")}
    invest_done = bool(core._json_setting(st, "unveil_reported", None)) or _invested(types)
    w = wins.evaluate(st, txns, today, anchor=anchor, path=path, review_count=review_count,
                      invest_done=invest_done, usual=usual)
    return {"done": w["done"], "of": w["of"], "heading": w["heading"], "next": w["next"],
            "earned": w["earned"], "total": w["total"]}


@bp.get("/wins")
def wins_page():
    return jsonify(page(store()))


@bp.get("/wins/moment")
def wins_moment():
    """"You earned a pearl" (THL-256): the sheet to show on open, once per
    milestone, ever. Evaluating the page is what notices a new pearl."""
    st = store()
    c = context(st)
    page_ = wins.evaluate(st, c["txns"], c["today"], anchor=c["anchor"], path=c["path"],
                          review_count=c["review_count"], invest_done=c["invest_done"],
                          usual=c["usual"])
    return jsonify(wins.moment(st, page_, c["anchor"]))


@bp.post("/wins/moment/seen")
def wins_moment_seen():
    body = request.get_json(silent=True) or {}
    keys = body.get("keys") or []
    known = {m["key"] for m in wins.MILESTONES}
    if not isinstance(keys, list) or not all(isinstance(k, str) and k in known for k in keys):
        return jsonify({"error": "Which pearls?"}), 400
    return jsonify({"ok": True, "celebrated": wins.mark_celebrated(store(), keys)})


@bp.get("/wins/streaks/<key>")
def wins_streak(key):
    w = page(store())
    s = next((x for x in w["streaks"] if x["key"] == key), None)
    if s is None:
        return jsonify({"error": "There’s no streak by that name."}), 404
    return jsonify(s)


@bp.get("/wins/challenges")
def wins_challenges():
    st = store()
    c = context(st)
    return jsonify({"suggested": wins.suggestions(st, c["txns"], c["today"], c["usual"], c["anchor"]),
                    "catalogue": [{"kind": d["kind"], "title": d["title"]} for d in wins.catalogue(st)]})


@bp.post("/wins/challenges")
def start_challenge():
    st = store()
    body = request.get_json(silent=True) or {}
    kind = str(body.get("kind") or "")
    c = context(st)
    offer = next((s for s in wins.suggestions(st, c["txns"], c["today"], c["usual"], c["anchor"])
                  if s["kind"] == kind), None)
    if offer is None:
        return jsonify({"error": "Pearl can’t price that challenge yet."}), 400
    target = offer["target"]
    if "target" in body and body["target"] is not None:
        try:
            target = round(float(body["target"]), 2)
        except (TypeError, ValueError):
            return jsonify({"error": "Enter a target, like 60."}), 400
        if target < 0 or target > 1_000_000:
            return jsonify({"error": "Enter a target above zero."}), 400
    merchant = None
    if kind == "subscription_sweep":
        merchant = str(body.get("merchant") or "").strip()
        options = {o["merchant"] for o in offer.get("options", [])}
        if merchant not in options:
            return jsonify({"error": "Pick one of your subscriptions."}), 400
        target = 0.0
    cid = st.add_challenge(kind, offer["title"], target, offer["start"], offer["end"],
                           category=offer.get("category"), merchant=merchant,
                           baseline=offer.get("baseline"))
    return jsonify({"ok": True, "id": cid, **challenge_detail(st, cid)})


def challenge_detail(st, cid: int) -> dict:
    c = st.challenge(cid)
    if c is None:
        return {}
    today = _today()
    txns = st.all_transactions()
    p = wins.progress(txns, c, today)
    words = wins.challenge_words(c, p, today)
    first, last = c["start"], c["end"]
    recent = []
    for t in sorted(txns, key=lambda t: t.date, reverse=True):
        if not (first <= t.date <= last):
            continue
        if c["kind"] == "anchor_boost":
            if (t.category or "") != "Saved" and not t.invested:
                continue
            amount = t.amount if (t.category or "") == "Saved" else t.invested
        else:
            from .analytics import counts_as_spending, share_amount
            from .categorize import group_of
            if not counts_as_spending(t):
                continue
            cat = t.category or "Other"
            if c["kind"] == "no_spend_weekend" and group_of(cat) != "lifestyle":
                continue
            if c["kind"] == "subscription_sweep" and (t.merchant or "").lower() != (c.get("merchant") or "").lower():
                continue
            if c["kind"] not in ("no_spend_weekend", "subscription_sweep") and cat != c.get("category"):
                continue
            amount = share_amount(t)
        recent.append({"id": t.fingerprint, "date": t.date, "merchant": t.merchant, "amount": round(amount, 2)})
        if len(recent) >= 6:
            break
    chests = [{"id": r["id"], "name": r["name"], "held": round(max(r["held"], 0.0), 2),
               "target": r["target"]} for r in core._bank_status(st)]
    return {"challenge": c, "progress": p, "words": words, "recent": recent, "chests": chests}


@bp.get("/wins/challenges/<int:cid>")
def get_challenge(cid):
    d = challenge_detail(store(), cid)
    if not d:
        return jsonify({"error": "There’s no challenge by that id."}), 404
    return jsonify(d)


@bp.post("/wins/challenges/<int:cid>/stop")
def stop_challenge(cid):
    st = store()
    c = st.challenge(cid)
    if c is None:
        return jsonify({"error": "There’s no challenge by that id."}), 404
    if c["status"] != "active":
        return jsonify(challenge_detail(st, cid))
    today = _today()
    p = wins.progress(st.all_transactions(), c, today)
    st.end_challenge(cid, "stopped", today.isoformat(), {"spent": p["done"], "days": p["elapsed"], "saved": 0.0})
    return jsonify(challenge_detail(st, cid))


@bp.post("/wins/challenges/<int:cid>/chest")
def challenge_to_chest(cid):
    """Put what she saved into a treasure chest (CH-04). An earmark from
    her Anchor, as "Add money" is (THL-230); she moves the money herself."""
    st = store()
    c = st.challenge(cid)
    if c is None:
        return jsonify({"error": "There’s no challenge by that id."}), 404
    if c["status"] != "finished":
        return jsonify({"error": "This challenge hasn’t finished yet."}), 409
    result = c.get("result") or {}
    saved = round(float(result.get("saved") or 0), 2)
    if saved <= 0:
        return jsonify({"error": "There’s nothing saved to move."}), 409
    if result.get("moved_to"):
        return jsonify({"error": "That’s already in a chest."}), 409
    body = request.get_json(silent=True) or {}
    try:
        bank_id = int(body.get("bank_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Pick a chest."}), 400
    bank = st.piggy_bank(bank_id)
    if bank is None:
        return jsonify({"error": "No such treasure chest."}), 404
    st.add_draw(bank_id, _today().isoformat()[:7], -saved, f"Challenge · {c['title']}")
    st.set_challenge_result(cid, {**result, "moved_to": bank_id, "moved_name": bank.name})
    return jsonify({"ok": True, "added": saved, "chest": bank.name, **challenge_detail(st, cid)})


@bp.get("/wins/recaps/<month>")
def wins_recap(month):
    st = store()
    page(st)                                                  # makes last month's if it's due
    recaps = wins._json(st, wins.RECAPS_KEY, {})
    r = recaps.get(month) if isinstance(recaps, dict) else None
    if r is None:
        return jsonify({"error": "There’s no recap for that month."}), 404
    return jsonify(r)


@bp.get("/wins/events")
def wins_events():
    st = store()
    log = wins._json(st, wins.EVENTS_KEY, [])
    return jsonify({"events": log if isinstance(log, list) else []})
