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

AI only detects; she confirms (product owner, 2026-11-15):

* A pattern strong enough to sort is only **pending** until she says Yes to
  it, once. A pending pattern sorts nothing. `pending()` lists the asks.
* It asks with one Quick sort card for the pattern (AI-18, designBOT).
* **Yes** (`confirm`) records when, from where, and after how many of her
  answers (`state[pid]["confirmed"] = {"at", "day", "how", "count"}`, for
  "You said yes on Nov 10, after sorting 5 yourself"). From then on the
  rules above apply to new matches only: the rows that matched when she said
  Yes are left for her (`state[pid]["before"]`), so nothing already in Needs
  a look is sorted by the Yes.
* **Skip** (`skip`) asks again after `need` more agreeing answers (5, or 8
  between people). A second Skip and Pearl never asks about it again.
  Forget clears both, so it may be asked about again.
* Migration (product owner, 2026-11-15, no exceptions): rows P1a sorted
  before she was asked go back to Needs a look, once (`migrate`).
"""

from __future__ import annotations

import json
import re
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
MIGRATED_KEY = "pattern_sort_asks_first"      # set once rows sorted without asking are back
SKIPS_MAX = 2                            # a second Skip and Pearl never asks again
HOW = re.compile(r"[a-z0-9_-]{1,32}")    # where she said Yes ("ask", or the screen code); designBOT picks the places


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


def after_start_over(st) -> None:
    """Start over (2026-11-19): the switch stays as she left it, but its
    baseline waits for the history to come back (`resync`), so the rows the
    resync brings aren't "new since she switched it on"."""
    if is_on(st):
        _save(st, BASELINE_KEY, {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 "known": [], "resync": True})


def settle_baseline(st) -> bool:
    """Once every bank's history is back (and there's a history), take the
    baseline again from what's there. True while it's still waiting."""
    base = _json(st, BASELINE_KEY, None)
    if not (isinstance(base, dict) and base.get("resync")):
        return False
    if not st.plaid_history_ready() or not st.all_transactions():
        return True
    switched_on(st)
    return False


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
    hers = st.confirmed_categories()
    answers: dict[str, list] = defaultdict(list)
    days: dict[str, list] = defaultdict(list)
    seen: dict[str, list] = defaultdict(list)
    meta: dict[str, dict] = {}
    for t in sorted(txns, key=lambda x: x.date):
        if t.fingerprint in pearl or t.excluded:
            continue
        if t.amount > 0 and not t.joint_from:
            cat = t.category or "Other"
            mine = t.category_source == "user" or hers.get(t.fingerprint) == cat
            if not mine or cat in NON_SPEND or cat in ("Unsorted transfers", "Other") or cat not in CATEGORIES:
                continue
            key = merchant_key(t.merchant or "")
            if not key:
                continue
            pid = _pattern_id("category", key)
            answers[pid].append(cat)
            days[pid].append(t.date[:10])
            seen[pid].append(t.fingerprint)
            meta[pid] = {"kind": "category", "key": key, "merchant": t.merchant}
        elif t.amount < 0 and t.joint and t.joint_from:
            from .joint import THEM
            sender = _sender(t)
            if not sender:
                continue
            pid = _pattern_id("joint", t.account_id or "", sender)
            answers[pid].append(t.joint_person if t.joint_from == THEM and t.joint_person else "")
            days[pid].append(t.date[:10])
            seen[pid].append(t.fingerprint)
            from .etransfers import party
            meta[pid] = {"kind": "joint", "key": sender, "account_id": t.account_id,
                         "account": t.account_name or t.joint, "joint": t.joint,
                         "merchant": (party(t) or {}).get("name") or t.merchant}
    out = {}
    state = _state(st)
    for pid, said in answers.items():
        m = meta[pid]
        s = state.get(pid) or {}
        answered = seen[pid]
        if s.get("forgot"):
            # Forget: learned again only from answers after it was forgotten.
            keep = [i for i, d in enumerate(days[pid]) if d > s["forgot"]]
            said, answered = [said[i] for i in keep], [answered[i] for i in keep]
            if not said:
                continue
        first = said[0]
        agree = all(a == first for a in said)
        need = PEOPLE_MIN if m["kind"] == "joint" else CATEGORY_MIN
        # A joint pattern is only "theirs, the same person"; hers isn't one.
        # Stopped (AI-04) is never learned again.
        usable = agree and bool(first) and len(said) >= need and not s.get("stopped_at")
        out[pid] = {**m, "id": pid, "answer": first, "count": len(said), "agree": agree, "need": need,
                    "ready": usable, "answers": said, "days": days[pid], "answered": answered}
    return out


def _state(st) -> dict:
    s = _json(st, STATE_KEY, {})
    return s if isinstance(s, dict) else {}


def enabled(st, pid: str) -> bool:
    return (_state(st).get(pid) or {}).get("on", True)


def confirmed(st, pid: str) -> dict | None:
    """{"at", "day", "how"} when she said Yes to this pattern, else None."""
    c = (_state(st).get(pid) or {}).get("confirmed")
    return c if isinstance(c, dict) else None


def migrate(st) -> list[dict]:
    """Once: every row P1a sorted for a pattern she never said Yes to goes
    back to Needs a look (product owner, 2026-11-15). Pearl won't sort those
    rows again: a later Yes only sorts new matches. Returns what went back."""
    if st.setting(MIGRATED_KEY):
        return []
    log = _log(st)
    back = [r for r in log if not r.get("undone") and not confirmed(st, r["pattern"])]
    for r in back:
        _undo(st, r)
    if back:
        _save(st, LOG_KEY, log)
    st.set_setting(MIGRATED_KEY, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return back


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
    if settle_baseline(st):
        return []                           # after Start over: the history isn't back yet
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
    state = _state(st)
    # Only what she said Yes to (AI only detects; she confirms).
    pats = {pid: p for pid, p in patterns(st, txns).items()
            if p["ready"] and enabled(st, pid) and confirmed(st, pid)}
    if not pats:
        return []
    hers = st.confirmed_categories()
    new = []
    for t in sorted(txns, key=lambda x: (x.date, x.fingerprint)):
        if room <= 0:
            break
        if t.fingerprint in known or t.fingerprint in never or t.fingerprint in sorted_ids:
            continue
        if t.amount > 0 and (t.category_source == "user" or t.fingerprint in hers
                             or (t.category or "Other") in NON_SPEND or t.split_mode or t.my_share is not None
                             or not is_guess(t)):
            # She answered it, a rule of hers did, or it's a transfer, savings
            # or a split: only what Needs a look would ask about is Pearl's.
            continue
        p = _match(t, pats)
        if p is None or t.fingerprint in set((state.get(p["id"]) or {}).get("before") or []):
            # Matched before she said Yes: hers to sort.
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
    # Keeps her Yes, so Stop's Undo puts the pattern back as it was.
    s[pid] = {**(s.get(pid) or {}), "on": False,
              "stopped_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _save(st, STATE_KEY, s)
    return undone


def forget(st, pid: str, today: str) -> None:
    """AI-06 Forget this rule: it goes, the rows it sorted stay as they are,
    and Pearl may learn it again from answers she gives after today, and asks
    again before it sorts (her Yes goes with the rule)."""
    s = _state(st)
    s[pid] = {"on": True, "forgot": today}
    _save(st, STATE_KEY, s)


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
    s = _state(st)
    s[pid] = {k: v for k, v in (s.get(pid) or {}).items() if k != "stopped_at"}
    s[pid]["on"] = True
    _save(st, STATE_KEY, s)


# ── Asking first ───────────────────────────────────────────────────────────

def _held(st, p: dict) -> bool:
    """Skipped: never after SKIPS_MAX, else until `need` more agreeing answers."""
    s = _state(st).get(p["id"]) or {}
    skips = int(s.get("skips") or 0)
    if skips >= SKIPS_MAX:
        return True
    return bool(skips) and p["count"] < int(s.get("skipped_at") or 0) + p["need"]


def pending(st, today: str, txns: list[Transaction] | None = None) -> list[dict]:
    """The asks (AI-18): patterns strong enough to sort that she hasn't said
    Yes to, not stopped, and not held by a Skip."""
    txns = st.all_transactions() if txns is None else txns
    by_id = {t.fingerprint: t for t in txns}
    out = []
    for pid, p in patterns(st, txns).items():
        if not p["ready"] or confirmed(st, pid) or _held(st, p):
            continue
        amounts = sorted(round(abs(by_id[i].amount), 2) for i in p["answered"] if i in by_id)
        out.append({"id": pid, "key": "pat:" + pid, "kind": p["kind"], "merchant": p["merchant"],
                    "answer": p["answer"], "label": label(p), "count": p["count"], "need": p["need"],
                    "account": p.get("account"), "joint": p.get("joint"), "rhythm": rhythm(p["days"]),
                    "answered": p["answered"],
                    # AI-18 / AI-18b: the usual amount; "$12–$48" unless every
                    # one is within $1 of the others.
                    "amount": amounts[len(amounts) // 2] if amounts else None,
                    "low": amounts[0] if amounts else None, "high": amounts[-1] if amounts else None,
                    "same_amount": bool(amounts) and amounts[-1] - amounts[0] <= 1.0,
                    # AI-18: "e-Transfers from Ana Ruiz" only when every one was one.
                    "etransfers": p["kind"] == "joint" and bool(p["answered"])
                    and all(i in by_id and _is_etransfer(by_id[i]) for i in p["answered"]),
                    "skips": int((_state(st).get(pid) or {}).get("skips") or 0)})
    return sorted(out, key=lambda r: (r["merchant"] or "").lower())


def confirm(st, pid: str, today: str, how: str = "ask", txns: list[Transaction] | None = None) -> dict | None:
    """Yes: Pearl may sort this pattern's new matches from now on. The rows
    that match it now stay hers. None when there's nothing to say Yes to."""
    txns = st.all_transactions() if txns is None else txns
    p = patterns(st, txns).get(pid)
    if p is None or not p["ready"]:
        return None
    if not isinstance(how, str) or not HOW.fullmatch(how):
        how = "ask"
    s = _state(st)
    prior = s.get(pid) or {}
    if prior.get("confirmed"):
        return prior["confirmed"]
    yes = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "day": today, "how": how,
           "count": p["count"]}
    before = sorted(t.fingerprint for t in txns if _match(t, {pid: p}) is p)
    s[pid] = {**{k: v for k, v in prior.items() if k not in ("skips", "skipped_at")},
              "on": True, "confirmed": yes, "before": before}
    _save(st, STATE_KEY, s)
    return yes


def _is_etransfer(t: Transaction) -> bool:
    from .etransfers import is_etransfer
    return is_etransfer(t)


def unconfirm(st, pid: str) -> bool:
    """Undo on AI-18y's toast: the Yes is taken back before anything was
    sorted by it, and the pattern may be asked about again."""
    s = _state(st)
    prior = s.get(pid) or {}
    if not prior.get("confirmed"):
        return False
    log = _log(st)
    for r in log:
        if r["pattern"] == pid and not r.get("undone"):
            _undo(st, r)
    _save(st, LOG_KEY, log)
    s[pid] = {k: v for k, v in prior.items() if k not in ("confirmed", "before")}
    _save(st, STATE_KEY, s)
    return True


def skip(st, pid: str) -> dict | None:
    """Skip on AI-18: ask again after `need` more agreeing answers; after a
    second Skip, never. None when there's nothing to skip."""
    p = patterns(st).get(pid)
    if p is None or not p["ready"] or confirmed(st, pid) or _held(st, p):
        return None
    s = _state(st)
    skips = int((s.get(pid) or {}).get("skips") or 0) + 1
    s[pid] = {**(s.get(pid) or {}), "skips": skips, "skipped_at": p["count"]}
    _save(st, STATE_KEY, s)
    return {"skips": skips, "never": skips >= SKIPS_MAX, "again_after": None if skips >= SKIPS_MAX else p["need"]}


# ── What the app shows ─────────────────────────────────────────────────────

def records(st, since: str | None = None) -> list[dict]:
    """What Pearl sorted and hasn't been undone, newest first."""
    out = [r for r in _log(st) if not r.get("undone") and (since is None or r["day"] >= since)]
    return sorted(out, key=lambda r: r["at"], reverse=True)


def this_week(st, today: str) -> int:
    """AI-01: how many Pearl sorted in the last seven days."""
    since = (date.fromisoformat(today) - timedelta(days=6)).isoformat()
    return len(records(st, since))


def rhythm(days: list[str]) -> str | None:
    """"about every 2 weeks", "about every month", or None with no rhythm:
    the middle gap between her answers, when most gaps are near it."""
    ds = sorted(date.fromisoformat(d) for d in days)
    gaps = [(b - a).days for a, b in zip(ds, ds[1:]) if (b - a).days > 0]
    if len(gaps) < 3:
        return None
    mid = sorted(gaps)[len(gaps) // 2]
    if sum(1 for g in gaps if abs(g - mid) <= 3) < len(gaps) * 0.7:
        return None
    if 6 <= mid <= 8:
        return "about every week"
    if 12 <= mid <= 16:
        return "about every 2 weeks"
    if 27 <= mid <= 33:
        return "about every month"
    return None


def learned(st) -> list[dict]:
    """AI-05: the patterns she said Yes to, with whether they're on, when
    she said Yes, and how many rows each has sorted. Pending ones are asks
    (`pending`), not rules."""
    log = _log(st)
    out = []
    for pid, p in patterns(st).items():
        yes = confirmed(st, pid)
        if not p["ready"] or not yes:
            continue
        mine = [r for r in log if r["pattern"] == pid and not r.get("undone")]
        out.append({"id": pid, "kind": p["kind"], "merchant": p["merchant"], "answer": p["answer"],
                    "label": label(p), "count": p["count"], "account": p.get("account"),
                    "joint": p.get("joint"),
                    "rhythm": rhythm(p["days"]), "answered": p["answered"],
                    "on": enabled(st, pid), "sorted": [r["txn"] for r in mine], "confirmed": yes})
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
    hers = st.confirmed_categories()
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
            and (x.category_source == "user" or hers.get(x.fingerprint) == (x.category or "Other"))]
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
