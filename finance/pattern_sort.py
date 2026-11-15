"""Pearl sorts for you, P1a (product owner, 2026-11-15; ios/bots/ai-plan.md).

Python only, no model: when she has answered the same pattern the same way
enough times, Pearl answers new ones the same way by itself, says so in
"Pearl sorted", and each can be undone.

Patterns (decision 1: categories and joint "theirs" deposits only; never
transfers or savings):

* **category** — spending at one merchant (`merchant_key`). Her own answers
  are the rows she categorised herself or confirmed. At least
  `CATEGORY_MIN` (5) of them, every one the same spending category.
* **joint** — money into one joint account from one sender, that she said
  was someone else's ("theirs", joint.THEM, with the same person). At least
  `PEOPLE_MIN` (8): money between people needs more (decision 2).

Rules of the road:

* Only transactions Pearl hadn't seen when "Pearl sorts for you" was switched
  on (decision 3). The switch writes `BASELINE_KEY`: every row there was at
  that moment. Turning it off and on again moves the start forward.
* At most `DAILY_CAP` (20) a day (decision 2).
* A row Pearl sorted never counts as her answer, so a pattern can't feed
  itself.
* Undo puts one row back and Pearl never sorts that row again (decision 4).
  Stop a pattern: every row it sorted goes back, and it's off; new ones go
  to Quick sort. Her own rules stay.
* It never saves a rule ("always for …"), and never touches splits, shares
  or the Allowance by itself.
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from .categorize import CATEGORIES, NON_SPEND, is_guess, merchant_key
from .models import Transaction

CATEGORY_MIN = 5
PEOPLE_MIN = 8
DAILY_CAP = 20
SOURCE = "pattern"            # category_source of a row Pearl sorted by a pattern

BASELINE_KEY = "pattern_sort_baseline"   # {"at": iso, "known": [ids]}
LOG_KEY = "pattern_sort_log"             # [record]
STATE_KEY = "pattern_sort_state"         # {pattern id: {"on": bool, "stopped_at": iso}}
NEVER_KEY = "pattern_sort_never"         # [txn ids she undid]


def _json(st, key: str, default):
    raw = st.setting(key)
    if raw in (None, ""):
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _save(st, key: str, value) -> None:
    st.set_setting(key, json.dumps(value, sort_keys=True))


# ── The switch ─────────────────────────────────────────────────────────────

def switched_on(st, at: str | None = None) -> None:
    """"Pearl sorts for you" was switched on: from now, only rows Pearl hasn't
    seen yet are new (decision 3)."""
    _save(st, BASELINE_KEY, {"at": at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             "known": sorted(t.fingerprint for t in st.all_transactions())})


def switched_off(st) -> None:
    _save(st, BASELINE_KEY, None)


def is_on(st) -> bool:
    return bool(_json(st, BASELINE_KEY, None))


# ── Patterns ───────────────────────────────────────────────────────────────

def _sender(t: Transaction) -> str:
    from .etransfers import party
    name = (party(t) or {}).get("name")
    return " ".join((name or merchant_key(t.merchant or "")).lower().split())


def _log(st) -> list[dict]:
    out = _json(st, LOG_KEY, [])
    return out if isinstance(out, list) else []


def _pattern_id(kind: str, *keys: str) -> str:
    return kind + ":" + "|".join(keys)


def patterns(st, txns: list[Transaction] | None = None) -> dict[str, dict]:
    """Every pattern her own answers make, whether or not it's strong enough
    yet: {id: {kind, key, answer, count, agree, label, …}}."""
    txns = st.all_transactions() if txns is None else txns
    pearl = {r["txn"] for r in _log(st) if not r.get("undone")}
    confirmed = st.confirmed_categories()
    answers: dict[str, list] = defaultdict(list)
    meta: dict[str, dict] = {}
    for t in sorted(txns, key=lambda x: x.date):
        if t.fingerprint in pearl or t.excluded:
            continue
        if t.amount > 0 and not t.joint_from:
            cat = t.category or "Other"
            mine = t.category_source == "user" or confirmed.get(t.fingerprint) == cat
            if not mine or cat in NON_SPEND or cat in ("Unsorted transfers", "Other") or cat not in CATEGORIES:
                continue
            key = merchant_key(t.merchant or "")
            if not key:
                continue
            pid = _pattern_id("category", key)
            answers[pid].append(cat)
            meta[pid] = {"kind": "category", "key": key, "merchant": t.merchant}
        elif t.amount < 0 and t.joint and t.joint_from:
            from .joint import THEM
            sender = _sender(t)
            if not sender:
                continue
            pid = _pattern_id("joint", t.account_id or "", sender)
            answers[pid].append(t.joint_person if t.joint_from == THEM and t.joint_person else "")
            meta[pid] = {"kind": "joint", "key": sender, "account_id": t.account_id,
                         "account": t.account_name or t.joint, "merchant": t.merchant}
    out = {}
    for pid, said in answers.items():
        m = meta[pid]
        first = said[0]
        agree = all(a == first for a in said)
        need = PEOPLE_MIN if m["kind"] == "joint" else CATEGORY_MIN
        # A joint pattern is only "theirs, the same person"; hers isn't one.
        usable = agree and bool(first) and len(said) >= need
        out[pid] = {**m, "id": pid, "answer": first, "count": len(said), "agree": agree, "need": need,
                    "ready": usable, "answers": said}
    return out


def _state(st) -> dict:
    s = _json(st, STATE_KEY, {})
    return s if isinstance(s, dict) else {}


def enabled(st, pid: str) -> bool:
    return (_state(st).get(pid) or {}).get("on", True)


# ── Sorting ────────────────────────────────────────────────────────────────

def _match(t: Transaction, pats: dict[str, dict]) -> dict | None:
    if t.excluded:
        return None
    if t.amount > 0 and not t.joint_from:
        p = pats.get(_pattern_id("category", merchant_key(t.merchant or "")))
        return p if p and p["kind"] == "category" else None
    if t.amount < 0 and t.joint and not t.joint_from:
        p = pats.get(_pattern_id("joint", t.account_id or "", _sender(t)))
        return p if p and p["kind"] == "joint" else None
    return None


def label(p: dict) -> str:
    """"Groceries", "Ana's share"."""
    return p["answer"] if p["kind"] == "category" else f"{p['answer'].split()[0]}’s share"


def line(p: dict) -> str:
    """AI-02's reason: "Groceries · like your last 5", "Ana's share · like the last 6"."""
    return f"{label(p)} · like your last {p['count']}" if p["kind"] == "category" \
        else f"{label(p)} · like the last {p['count']}"


def run(st, today: str) -> list[dict]:
    """Sort what can be sorted now; return the new records. Nothing when
    the switch is off, nothing older than the switch, at most DAILY_CAP a day."""
    base = _json(st, BASELINE_KEY, None)
    if not base:
        return []
    known = set(base.get("known") or [])
    log = _log(st)
    done_today = sum(1 for r in log if r.get("day") == today)
    room = DAILY_CAP - done_today
    if room <= 0:
        return []
    never = set(_json(st, NEVER_KEY, []))
    sorted_ids = {r["txn"] for r in log}
    txns = st.all_transactions()
    pats = {pid: p for pid, p in patterns(st, txns).items() if p["ready"] and enabled(st, pid)}
    if not pats:
        return []
    confirmed = st.confirmed_categories()
    new = []
    for t in sorted(txns, key=lambda x: (x.date, x.fingerprint)):
        if room <= 0:
            break
        if t.fingerprint in known or t.fingerprint in never or t.fingerprint in sorted_ids:
            continue
        if t.amount > 0 and (t.category_source == "user" or t.fingerprint in confirmed
                             or (t.category or "Other") in NON_SPEND or t.split_mode or t.my_share is not None
                             or not is_guess(t)):
            # She answered it, a rule of hers did, or it's a transfer, savings
            # or a split: only what Needs a look would ask about is Pearl's.
            continue
        p = _match(t, pats)
        if p is None:
            continue
        rec = _apply(st, t, p, today)
        if rec:
            log.append(rec)
            new.append(rec)
            room -= 1
    if new:
        _save(st, LOG_KEY, log[-2000:])
    return new


def _apply(st, t: Transaction, p: dict, today: str) -> dict | None:
    rec = {"id": uuid.uuid4().hex[:12], "txn": t.fingerprint, "pattern": p["id"], "kind": p["kind"],
           "answer": p["answer"], "count": p["count"], "line": line(p), "day": today,
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "undone": False}
    if p["kind"] == "category":
        rec["was"] = [t.category, t.category_source]
        st.write_categories({t.fingerprint: (p["answer"], SOURCE)})
        st.confirm_category(t.fingerprint, p["answer"])
        st.dismiss_review("cat:" + t.fingerprint)
        return rec
    from .joint import THEM
    person = p["answer"]
    if person not in (t.joint_people or []):
        return None
    rec["was"] = [t.joint_from, t.joint_person]
    st.set_joint_deposit(t.fingerprint, THEM, person)
    return rec


def _undo(st, rec: dict) -> None:
    if rec["kind"] == "category":
        cat, src = rec.get("was") or [None, None]
        st.write_categories({rec["txn"]: (cat or "Other", src or "rule")})
        st.unconfirm_category(rec["txn"])
        st.undismiss_review("cat:" + rec["txn"])
    else:
        who, person = rec.get("was") or [None, None]
        st.set_joint_deposit(rec["txn"], who, person)
    rec["undone"] = True


def undo(st, record_id: str) -> dict | None:
    """Undo one row (decision 4): back to Needs a look, never sorted by Pearl again."""
    log = _log(st)
    rec = next((r for r in log if r["id"] == record_id and not r.get("undone")), None)
    if rec is None:
        return None
    _undo(st, rec)
    never = _json(st, NEVER_KEY, [])
    if rec["txn"] not in never:
        never.append(rec["txn"])
    _save(st, NEVER_KEY, never)
    _save(st, LOG_KEY, log)
    return rec


def set_enabled(st, pid: str, on: bool) -> None:
    """AI-06's switch: off sends new ones to Quick sort; what it sorted stays."""
    s = _state(st)
    s[pid] = {**(s.get(pid) or {}), "on": bool(on)}
    _save(st, STATE_KEY, s)


def stop(st, pid: str) -> list[dict]:
    """AI-04: every row this pattern sorted goes back to Needs a look, and
    it's off. Her own rules stay. Returns what was undone."""
    log = _log(st)
    undone = [r for r in log if r["pattern"] == pid and not r.get("undone")]
    for r in undone:
        _undo(st, r)
    _save(st, LOG_KEY, log)
    s = _state(st)
    s[pid] = {"on": False, "stopped_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _save(st, STATE_KEY, s)
    return undone


def restart(st, pid: str, records: list[str]) -> None:
    """Undo for Stop: the pattern is on again and its rows sorted again."""
    log = _log(st)
    for r in log:
        if r["pattern"] == pid and r["id"] in records and r.get("undone"):
            t = st.get_transaction(r["txn"])
            if t is None:
                continue
            p = {"id": pid, "kind": r["kind"], "answer": r["answer"], "count": r["count"]}
            fresh = _apply(st, t, p, r["day"])
            if fresh:
                r.update(undone=False, was=fresh.get("was"))
    _save(st, LOG_KEY, log)
    set_enabled(st, pid, True)


# ── What the app shows ─────────────────────────────────────────────────────

def records(st, since: str | None = None) -> list[dict]:
    """What Pearl sorted and hasn't been undone, newest first."""
    out = [r for r in _log(st) if not r.get("undone") and (since is None or r["day"] >= since)]
    return sorted(out, key=lambda r: r["at"], reverse=True)


def this_week(st, today: str) -> int:
    """AI-01: how many Pearl sorted in the last seven days."""
    since = (date.fromisoformat(today) - timedelta(days=6)).isoformat()
    return len(records(st, since))


def learned(st) -> list[dict]:
    """AI-05: the patterns strong enough to sort, with whether they're on and
    how many rows each has sorted."""
    log = _log(st)
    out = []
    for pid, p in patterns(st).items():
        if not p["ready"]:
            continue
        mine = [r for r in log if r["pattern"] == pid and not r.get("undone")]
        out.append({"id": pid, "kind": p["kind"], "merchant": p["merchant"], "answer": p["answer"],
                    "label": label(p), "count": p["count"], "account": p.get("account"),
                    "on": enabled(st, pid), "sorted": [r["txn"] for r in mine]})
    return sorted(out, key=lambda r: (r["merchant"] or "").lower())


def caption(st, t: Transaction, txns: list[Transaction] | None = None) -> dict | None:
    """AI-07: why Pearl won't sort this one by itself, as the first case that
    applies (designBOT, 2026-11-15). The app words it:

    1. {"case": "category", "k", "n", "category"}: k of her last n here were another category.
    2. {"case": "split", "k", "n"}: she split k of her last n here.
    3. {"case": "person", "k", "n", "name"}: k of the last n from Name were Name's share.
    4. {"case": "few", "n"}: she has sorted only n here so far.

    n is up to 8 for money from a person, up to 5 otherwise. None when she
    has never answered this pattern."""
    txns = st.all_transactions() if txns is None else txns
    pearl = {r["txn"] for r in _log(st) if not r.get("undone")}
    confirmed = st.confirmed_categories()
    if t.amount < 0 and t.joint and not t.joint_from:
        from .joint import THEM
        sender = _sender(t)
        said = [x for x in sorted(txns, key=lambda x: x.date)
                if x.fingerprint not in pearl and x.fingerprint != t.fingerprint and x.amount < 0
                and x.joint and x.joint_from and x.account_id == t.account_id and _sender(x) == sender]
        last = said[-PEOPLE_MIN:]
        if not last:
            return None
        theirs = [x.joint_person for x in last if x.joint_from == THEM and x.joint_person]
        if theirs:
            name = max(set(theirs), key=theirs.count)
            k = theirs.count(name)
            if k < len(last):
                return {"case": "person", "k": k, "n": len(last), "name": name.split()[0]}
        if len(last) < PEOPLE_MIN:
            return {"case": "few", "n": len(last)}
        return None
    if t.amount <= 0:
        return None
    key = merchant_key(t.merchant or "")
    said = [x for x in sorted(txns, key=lambda x: x.date)
            if x.fingerprint not in pearl and x.fingerprint != t.fingerprint and x.amount > 0
            and not x.excluded and merchant_key(x.merchant or "") == key
            and (x.category_source == "user" or confirmed.get(x.fingerprint) == (x.category or "Other"))]
    last = said[-CATEGORY_MIN:]
    if not last:
        return None
    guess = t.category or "Other"
    others = [x.category or "Other" for x in last if (x.category or "Other") != guess]
    if others:
        other = max(set(others), key=others.count)
        return {"case": "category", "k": others.count(other), "n": len(last), "category": other}
    splits = sum(1 for x in last if x.split_mode or x.my_share is not None)
    if splits:
        return {"case": "split", "k": splits, "n": len(last)}
    if len(last) < CATEGORY_MIN:
        return {"case": "few", "n": len(last)}
    return None
