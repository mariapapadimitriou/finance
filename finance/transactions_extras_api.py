"""Transactions: one-offs, possible duplicates and keyboard review
(Pearl THL-71 U-01 to U-03, THL-165 D-01 to D-03, THL-83 K-01 to K-04).

* PUT  /api/transactions/<id>/one-off         {on}: "This was a one-off". Left
  out of her usual month, budgets' pace, Insights' averages, projections and
  the trend card; still counted in its month and in safe to spend. Only a row
  that counts (not a transfer, not a repayment you linked). The toast names
  the usual month it moved, before and after (U-02).
* POST /api/review/duplicates/<copy id>       {answer: same | different}: "Is
  this the same purchase?" (D-02). Same soft-hides the copy — nothing is
  deleted — and different counts both. Either way the answer comes back with
  an Undo that puts the question back (D-03).
* POST /api/transactions/batch/category        {ids, category}: change many
  rows at once from the keyboard (K-02, K-03). Never writes a merchant rule:
  "Apply to all from this merchant" stays a one-at-a-time choice (R-02). One
  Undo puts the whole batch back.
* POST /api/transactions/batch/category/preview  the helper line, before.
* POST /api/transactions/batch/confirm          {ids}: Pearl's suggestions
  were right (Y), with one Undo.
* GET/PUT /api/preferences                     {single_key_shortcuts}: off for
  WCAG 2.1.4 when they clash with a screen reader or voice control. Saved
  for her account; Ctrl/⌘ shortcuts always work.

Every undo goes through POST /api/transactions/undo, which also takes
`one_off`, `duplicates` and `unconfirm` beside the category rows.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from flask import jsonify, request

from . import api as core
from . import duplicates as dup
from .api import bp, store
from .categorize import CATEGORIES, CATEGORY_GROUPS, group_of

MAX_BATCH = 500
SHORTCUTS_KEY = "single_key_shortcuts"
# Names that read better as an answer than as a ledger heading (as R-02
# says). Transfers is just Transfers (2026-10-14).
LABEL: dict[str, str] = {}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def _dollars(x: float) -> str:
    return f"${abs(x):,.2f}"


def _whole(x: float) -> str:
    return f"${round(abs(x)):,}"


def _month(iso: str) -> str:
    return MONTHS[int(iso[5:7]) - 1]


def _today() -> date:
    return date.fromisoformat(core._today_iso())


def _row(st, txn_id: str):
    """The transaction and how the list describes it, or (None, None)."""
    for t, r in core._txlist_rows(st, everything=True):
        if t.fingerprint == txn_id:
            return t, r
    return None, None


# ── One-offs (THL-71) ────────────────────────────────────────────────────

def one_off_line(st, txns, t) -> dict | None:
    """U-03's line: when it was left out, and a usual month of its group."""
    from . import usual_month
    if not t.one_off:
        return None
    effect = usual_month.one_off_effect(txns, t, _today(), core._unusual_months(st))
    since = date.fromisoformat(t.one_off_since)
    line = f"Left out since {_month(t.one_off_since)} {since.day}."
    if effect and effect["usual"] >= 0.5:
        line += f" A usual month of {effect['label']}: {_whole(effect['usual'])}."
    return {"since": t.one_off_since, "line": line}


def _one_off_toast(effect: dict | None, on: bool, month: str) -> dict:
    """U-02: which average changed, before and after."""
    if on:
        title = "Left out of your usual month."
        if effect and effect["usual"] >= 0.5 and abs(effect["without"] - effect["usual"]) >= 0.5:
            if effect["in_usual"]:
                detail = (f"A usual month of {effect['label']} is now {_whole(effect['usual'])} "
                          f"instead of {_whole(effect['without'])}.")
            else:
                detail = (f"A usual month of {effect['label']} stays {_whole(effect['usual'])} "
                          f"instead of rising to {_whole(effect['without'])}.")
            return {"title": title, "detail": f"{detail} It still counts in {month}."}
        return {"title": title, "detail": f"It still counts in {month}."}
    title = "Back in your usual month."
    if effect and effect["in_usual"] and effect["without"] >= 0.5 \
            and abs(effect["without"] - effect["usual"]) >= 0.5:
        return {"title": title,
                "detail": (f"A usual month of {effect['label']} is now "
                           f"{_whole(effect['without'])} instead of {_whole(effect['usual'])}.")}
    if effect:
        return {"title": title, "detail": f"It counts toward a usual month of {effect['label']} again."}
    return {"title": title, "detail": ""}


@bp.put("/transactions/<txn_id>/one-off")
def set_one_off(txn_id: str):
    from . import usual_month
    st = store()
    t, r = _row(st, txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    on = bool((request.get_json(silent=True) or {}).get("on"))
    if on and not r["can_one_off"]:
        return jsonify({"error": "Only a transaction that counts can be a one-off. "
                                 "Transfers and repayments already stay out of your "
                                 "usual month."}), 400
    was = t.one_off_since
    st.set_one_off(txn_id, on, since=(was or _today().isoformat()) if on else None)
    txns = st.all_transactions()
    now = next(x for x in txns if x.fingerprint == txn_id)
    effect = usual_month.one_off_effect(txns, now, _today(), core._unusual_months(st))
    toast = _one_off_toast(effect, on, _month(t.date))
    return jsonify({"ok": True, "one_off": on, "id": txn_id, **toast,
                    "undo": {"one_off": {txn_id: was}}})


# ── Possible duplicates (THL-165) ────────────────────────────────────────

@bp.post("/review/duplicates/<txn_id>")
def answer_duplicate(txn_id: str):
    st = store()
    pairs = st.duplicates()
    pair = pairs.get(txn_id)
    if pair is None:
        return jsonify({"error": "That isn’t a possible duplicate."}), 404
    answer = (request.get_json(silent=True) or {}).get("answer")
    if answer not in (dup.SAME, dup.DIFFERENT):
        return jsonify({"error": "Say whether it was the same purchase."}), 400
    before = st.all_transactions()
    st.set_duplicate_state(txn_id, answer)
    after = st.all_transactions()
    out = {"ok": True, "id": txn_id, "kept": pair["twin"], "state": answer,
           "undo": {"duplicates": {txn_id: pair["state"]}}}
    if answer == dup.SAME:
        out.update(title="Kept one. Your numbers didn’t change.",
                   detail="We were already counting it once.")
        return jsonify(out)
    was, now = core._safe_left(st, before), core._safe_left(st, after)
    delta = round(now - was, 2)
    copy = next((t for t in after if t.fingerprint == txn_id), None)
    month = _month(copy.date) if copy else ""
    if abs(delta) >= 0.005:
        title = (f"Kept both. Allowance is now {_dollars(now)}, "
                 f"{_dollars(delta)} {'less' if delta < 0 else 'more'}." if now >= 0
                 else f"Kept both. You’re {_dollars(now)} over for this week.")
        out.update(title=title, detail="Both count as spending.")
    else:
        out.update(title="Kept both. Your Allowance stays the same.",
                   detail=f"Both count as spending in {month}." if month
                   else "Both count as spending.")
    return jsonify(out)


# ── Keyboard review: many at once (THL-83) ───────────────────────────────

def _ids(body) -> list[str] | None:
    ids = body.get("ids")
    if not isinstance(ids, list) or not ids or len(ids) > MAX_BATCH \
            or not all(isinstance(i, str) for i in ids):
        return None
    return list(dict.fromkeys(ids))


def _batch_words(n: int, cats_from: list[str], cat_to: str, delta: float, after: float,
                 spent_delta: float, month: str) -> dict:
    """K-02's helper line and K-03's toast, from safe to spend before and after."""
    label = LABEL.get(cat_to, cat_to)
    g_to = group_of(cat_to)
    same_group = all(group_of(c) == g_to for c in cats_from)
    group = CATEGORY_GROUPS[g_to]
    moved = f"Changed {n} to {label}." if n > 1 else f"Moved to {label}."
    if abs(delta) >= 0.005:
        up = delta > 0
        line = (f"Your Allowance goes {'up' if up else 'down'} by {_dollars(delta)}.")
        title = (f"{moved} Allowance is now {_dollars(after)}." if after >= 0
                 else f"{moved} You’re {_dollars(after)} over for this week.")
        detail = f"{_dollars(delta)} {'more' if up else 'less'} than before."
        return {"line": line, "title": title, "detail": detail}
    if same_group:
        line = (f"All {n} are {group} now, so your Allowance stays the same." if n > 1
                else f"It’s {group} either way, so your Allowance stays the same.")
        detail = f"All {n} were already {group}." if n > 1 else f"It was already {group}."
    else:
        line = "Your Allowance stays the same."
        detail = ""
        if abs(spent_delta) >= 0.005 and month:
            detail = (f"{_dollars(spent_delta)} {'less' if spent_delta < 0 else 'more'} "
                      f"counted as spending in {month}.")
            line = f"{detail} Your Allowance stays the same."
    return {"line": line, "title": f"{moved} Your Allowance stays the same.",
            "detail": detail}


def _batch(dry: bool):
    from .impact import snapshot, undo_payload
    body = request.get_json(silent=True) or {}
    ids = _ids(body)
    category = body.get("category")
    if ids is None:
        return jsonify({"error": "Choose at least one transaction."}), 400
    if not category or category not in CATEGORIES or category == "Unsorted transfers":
        return jsonify({"error": "A valid category is required."}), 400
    st = store()
    txns = st.all_transactions()
    by_id = {t.fingerprint: t for t in txns}
    if any(i not in by_id for i in ids):
        return jsonify({"error": "No such transaction."}), 404
    rows = [by_id[i] for i in ids]
    months = sorted({t.date[:7] for t in rows})
    month = months[-1]
    after_txns = [replace(t, category=category, category_source="user")
                  if t.fingerprint in set(ids) else t for t in txns]
    before_left, after_left = core._safe_left(st, txns), core._safe_left(st, after_txns)
    spent_delta = sum(core._month_spent(after_txns, m) - core._month_spent(txns, m)
                      for m in months)
    words = _batch_words(len(ids), [t.category or "Other" for t in rows], category,
                         round(after_left - before_left, 2), after_left,
                         round(spent_delta, 2), _month(month + "-01") if len(months) == 1 else "")
    if dry:
        return jsonify({"count": len(ids), "category": category, **words})
    before = snapshot(st, txns)
    # One row at a time, as a person chose it: no merchant rule is written,
    # so nothing else is re-filed (R-02 keeps "Apply to all").
    for i in ids:
        st.set_transaction_category(i, category)
    from .transfers import apply_transfer_matches
    apply_transfer_matches(st)
    out = {"ok": True, "updated": len(ids), "ids": ids, "category": category, **words,
           "undo": undo_payload(before, snapshot(st))}
    return jsonify(out)


@bp.post("/transactions/batch/category/preview")
def batch_category_preview():
    return _batch(dry=True)


@bp.post("/transactions/batch/category")
def batch_category():
    return _batch(dry=False)


@bp.post("/transactions/batch/confirm")
def batch_confirm():
    """Y on the selection: Pearl's suggestion was right, for each of them
    that has one. Rows with nothing to confirm are left alone."""
    body = request.get_json(silent=True) or {}
    ids = _ids(body)
    if ids is None:
        return jsonify({"error": "Choose at least one transaction."}), 400
    st = store()
    rows = {t.fingerprint: (t, r) for t, r in core._txlist_rows(st, everything=True)}
    if any(i not in rows for i in ids):
        return jsonify({"error": "No such transaction."}), 404
    done = []
    for i in ids:
        t, r = rows[i]
        if not r["suggested"] or t.category == "Unsorted transfers" \
                or r["chip"]["label"] in ("Possible duplicate",):
            continue
        st.confirm_category(i, t.category or "Other")
        st.dismiss_review("cat:" + i)
        done.append(i)
    n = len(done)
    title = ("Nothing to confirm." if not n else
             "Confirmed." if n == 1 else f"Confirmed {n} suggestions.")
    return jsonify({"ok": True, "confirmed": done, "title": title,
                    "detail": "" if n else "These were already yours.",
                    "undo": {"unconfirm": done} if n else None})


# ── The shortcuts preference (K-04, WCAG 2.1.4) ──────────────────────────

def _prefs(st) -> dict:
    return {"single_key_shortcuts": st.setting(SHORTCUTS_KEY, "1") != "0"}


@bp.get("/preferences")
def get_preferences():
    return jsonify(_prefs(store()))


@bp.put("/preferences")
def put_preferences():
    body = request.get_json(silent=True) or {}
    st = store()
    if "single_key_shortcuts" in body:
        value = body["single_key_shortcuts"]
        if not isinstance(value, bool):
            return jsonify({"error": "single_key_shortcuts is true or false."}), 400
        st.set_setting(SHORTCUTS_KEY, "1" if value else "0")
    return jsonify(_prefs(st))


# ── Undo, for everything above ───────────────────────────────────────────

def undo_extras(st, body: dict) -> tuple[int, str | None]:
    """Put back one-offs, duplicate answers and confirmations named in an
    undo payload. Returns (how many, a problem in words)."""
    one_off = body.get("one_off") or {}
    dupes = body.get("duplicates") or {}
    unconfirm = body.get("unconfirm") or []
    if not isinstance(one_off, dict) or not isinstance(dupes, dict) \
            or not isinstance(unconfirm, list):
        return 0, "Nothing to undo."
    if len(one_off) + len(dupes) + len(unconfirm) > MAX_BATCH:
        return 0, "Nothing to undo."
    known = {t.fingerprint for t in st.all_transactions()}
    pairs = st.duplicates()
    for i, since in one_off.items():
        if i not in known or (since is not None and (
                not isinstance(since, str) or len(since) != 10)):
            return 0, "That change can’t be undone."
    for i, state in dupes.items():
        if i not in pairs or state not in dup.STATES:
            return 0, "That change can’t be undone."
    if not all(isinstance(i, str) and i in known for i in unconfirm):
        return 0, "That change can’t be undone."
    for i, since in one_off.items():
        st.set_one_off(i, since is not None, since=since)
    for i, state in dupes.items():
        st.set_duplicate_state(i, state)
    for i in unconfirm:
        st.unconfirm_category(i)
        st.undismiss_review("cat:" + i)
    # A recurring transfer's question comes back with Undo (2026-10-27).
    for key in body.get("undismiss") or []:
        if isinstance(key, str) and key.startswith("rt:") and len(key) < 40:
            st.undismiss_review(key)
    # What was this? (2026-10-14): the parts a category doesn't cover.
    extra = 0
    if body.get("marks"):
        from . import marks
        try:
            extra = marks.undo_marks(st, body["marks"])
        except marks.Problem as exc:
            return 0, str(exc)
    return len(one_off) + len(dupes) + len(unconfirm) + extra, None
