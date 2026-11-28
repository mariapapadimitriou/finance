"""Pearl sorts for you: Off · Rules · Smart (AI Phase 4, THL-309; Pearl
redesign canvas, Pearl page: CN-07, CN-08, AI-03r / AI-03s, CN-09).

* **Off**: nothing sorts by itself (`ai_sort` off).
* **Rules**: today's Python pattern sorting (finance/pattern_sort.py), as it
  was. The old `ai_sort` consent maps here: on is Rules, off is Off. Nobody
  is moved to Smart.
* **Smart**: Rules, plus Claude on the harder cases, through the gateway's
  `sort_reason` route (shop names only, finance/ai/config.py). It has its
  own opt-in, `ai_sort_smart`, asked once on CN-08.

What Claude does, right after each sync (never in a batch: the Batch API is
only for full-history runs, and Smart never looks at history, only rows
that are new since the switch):

1. **A pattern she said Yes to** is about to sort a row. Python allows one
   answer, the pattern's. Claude agrees (and words the reason) or says
   `none`. `none` is a disagreement: the row goes to Quick sort as Yes or
   Skip with the pattern's answer, and is never sorted by Pearl by itself.
2. **Close or tied evidence** at a shop (her answers there split, the top
   two within one of each other). Python allows those answers; Claude picks
   one. A pick against a clear leader is a disagreement, as above.
3. **A new shop** she has never sorted: Python allows its likeliest four
   (finance/likely.py); Claude picks one.

Cases 2 and 3 never sort anything: Python's evidence gate isn't met, so the
pick is only the guess on her Quick sort card, Yes or Skip. Claude picks
through a strict tool whose `answer` is an enum of exactly what Python
allows. Every number in a reason is Python's: the model sees counts only as
placeholders ([NUM1]) and a reason with a digit of its own is thrown away.

Fallback: over the cap, offline, no key, a refusal or an error, and the rest
of that sync is Rules. Every call writes an `app_ai_usage` row (the router).
Each decision is a detection, `smart_sort@1` (finance/signals).

Stepping down (CN-09): patterns she said yes to stay; Smart → Rules is at
once and Claude's reasons go back to the plain wording, because Pearl only
shows them while Smart is on.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone

from . import pattern_sort as ps

DETECTOR = "smart_sort"
VERSION = "1"
ROUTE = "sort_reason"

OFF, RULES, SMART = "off", "rules", "smart"
MODES = (OFF, RULES, SMART)
CONSENT = "ai_sort_smart"

SMART_KEY = "sorting_smart"          # "1" while Smart is on, kept in the ledger
LOCAL_ASKED_KEY = "sorting_smart_asked"   # a local ledger with no accounts: CN-08 was answered
GUESS_KEY = "smart_sort_guesses"     # {txn id: decision}, see `_decide`
HELD_KEY = ps.HELD_KEY               # [txn ids] never sorted by Pearl by itself

PER_SYNC = 12                        # Claude calls in one sync at most
CLOSE_GAP = 1                        # top two answers within this many: close
MAX_ALLOWED = 4
# A failure that ends Claude's part of this sync (the rest is Rules).
_STOPS = ("off", "killed", "over_budget", "over_daily", "no_prompt", "no_route", "blocked",
          "refusal")
_PLACEHOLDER = re.compile(r"\[(?:AMT|DATE|PERSON|CARD|SHOP|NUM)\d+\]")
_USE_ENV = object()


def _json(st, key, default):
    raw = st.setting(key)
    if raw in (None, ""):
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── The setting (CN-07) ──────────────────────────────────────────────────

def is_smart(st) -> bool:
    """Smart is on for this ledger (and so is sorting)."""
    return st.setting(SMART_KEY) == "1" and ps.is_on(st)


def mode_from(consents: dict) -> str:
    """Her consents as one of Off · Rules · Smart. `ai_sort` on is Rules
    (THL-309 AC 2) unless she also opted in to Smart."""
    if not (consents.get("ai_sort") or {}).get("value"):
        return OFF
    return SMART if (consents.get(CONSENT) or {}).get("value") else RULES


def mode(st, user) -> str:
    if user is None:
        # A local ledger with no accounts: the switch is the baseline.
        return (SMART if is_smart(st) else RULES) if ps.is_on(st) else OFF
    from . import users
    return mode_from(users.effective_consents(user))


def asked(st, user) -> bool:
    """She has answered CN-08 before: picking Smart again needs no sheet."""
    if user is None:
        return bool(st.setting(LOCAL_ASKED_KEY))
    return CONSENT in (user.consents or {})


def patterns_kept(st) -> int:
    """"Your 14 patterns": the patterns she said Yes to."""
    return len(ps.learned(st))


def state(st, user) -> dict:
    return {"mode": mode(st, user), "asked": asked(st, user), "patterns": patterns_kept(st)}


class NeedsConsent(Exception):
    """Smart for the first time: CN-08 asks first."""


def set_mode(base, st, user, new: str, consent: bool = False):
    """Move the setting to `new`. Off ↔ on keeps pattern_sort's switch as it
    was (switched_on / switched_off); Rules ↔ Smart touches no pattern.
    Smart for the first time needs `consent` (CN-08's Turn on Smart). Returns
    the account as saved (None for a local ledger)."""
    if new not in MODES:
        raise ValueError(new)
    was = mode(st, user)
    if new == SMART and not consent and not asked(st, user):
        raise NeedsConsent()
    if user is not None:
        from . import users
        changes = {"ai_sort": new != OFF}
        if new == SMART or CONSENT in (user.consents or {}):
            changes[CONSENT] = new == SMART
        user = users.record_consents(base, user.id, changes, source="settings")
    elif new == SMART:
        st.set_setting(LOCAL_ASKED_KEY, _now())
    if (was == OFF) != (new == OFF):
        (ps.switched_off if new == OFF else ps.switched_on)(st)
    st.set_setting(SMART_KEY, "1" if new == SMART else "")
    return user


def sync_mirror(st, user) -> None:
    """The ledger's copy of Smart follows her consents (another phone may
    have changed them)."""
    if user is None:
        return
    want = "1" if mode(st, user) == SMART else ""
    if (st.setting(SMART_KEY) or "") != want:
        st.set_setting(SMART_KEY, want)


# ── What Claude is asked ─────────────────────────────────────────────────

def _tool(allowed: list[str]) -> dict:
    """The strict `pick` tool: `answer` is one of Python's answers or none."""
    return {"name": "pick",
            "description": "Pick the likeliest answer among those allowed, and word one reason.",
            "strict": True,
            "input_schema": {"type": "object", "additionalProperties": False,
                             "required": ["answer", "reason"],
                             "properties": {"answer": {"type": "string", "enum": allowed + ["none"]},
                                            "reason": {"type": "string"}}}}


def _question(shop: str, allowed: list[str], counts: Counter, pattern: str | None) -> list:
    body = {"shop": shop, "allowed": allowed,
            "their_answers": [{"category": c, "count": n} for c, n in counts.most_common()]}
    if pattern:
        body["pattern"] = pattern
    return [{"role": "user", "content": json.dumps(body)}]


def _checks(allowed: list[str]):
    """The router's checks, on the reply as the model wrote it."""
    ok = set(allowed) | {"none"}

    def valid_tool(call) -> bool:
        if call.get("name") != "pick":
            return False
        got = call.get("input") or {}
        reason = got.get("reason")
        if got.get("answer") not in ok or not isinstance(reason, str):
            return False
        bare = _PLACEHOLDER.sub("", reason)
        # Every number is Python's: a digit of its own, and the reason goes.
        return 0 < len(reason.strip()) <= 160 and not re.search(r"\d", bare)

    def accept(reply) -> bool:
        return len([c for c in reply.tool_calls if c.get("name") == "pick"]) == 1

    return valid_tool, accept


def _ask(st, *, base, user_id, shop, allowed, counts, pattern, client, now=None):
    """(answer, reason) from Claude, or (None, why) when it fell back."""
    from .ai import router
    valid_tool, accept = _checks(allowed)
    kw = {} if client is _USE_ENV else {"client": client}
    a = router.ask(ROUTE, None, _question(shop, allowed, counts, pattern), [_tool(allowed)],
                   base=base, user_id=user_id, accept=accept, valid_tool=valid_tool, now=now, **kw)
    if a.fall_back:
        return None, a.reason, a
    call = next(c for c in a.tool_calls if c.get("name") == "pick")
    reason = " ".join(str(call["input"].get("reason") or "").split())
    if reason and reason[-1] not in ".?":
        reason += "."
    return call["input"]["answer"], reason, a


# ── The evidence ─────────────────────────────────────────────────────────

def _counts(pats: dict, t) -> Counter:
    from .categorize import merchant_key
    p = pats.get(ps._pattern_id("category", merchant_key(t.merchant or "")))
    return Counter(p["answers"]) if p else Counter()


def _allowed(counts: Counter, index, t) -> tuple[str | None, list[str], str | None]:
    """(case, the answers Python allows, Python's leader or None)."""
    if not counts:
        # Her likeliest four, with the row's own guess (the bank's, or a name
        # rule's, which Pearl isn't sure of) first when it is one of hers.
        own = [t.category] if t.category in index.allowed else []
        likely = list(dict.fromkeys(own + [c for c in index.likeliest(t) if c != "Other"]))[:MAX_ALLOWED]
        return ("new", likely, None) if likely else (None, [], None)
    ranked = counts.most_common()
    if len(ranked) < 2:
        return None, [], None          # one answer: Rules' own asks handle it (AI-07, AI-18)
    top_n = ranked[0][1]
    if top_n - ranked[1][1] > CLOSE_GAP:
        return None, [], None
    allowed = [c for c, n in ranked if n >= top_n - CLOSE_GAP][:MAX_ALLOWED]
    leader = ranked[0][0] if ranked[0][1] > ranked[1][1] else None
    return "close", allowed, leader


def _new_rows(st, txns, pats) -> list:
    """Rows Smart may think about: what Needs a look would ask about, new
    since the switch, not answered, not undone, not decided before."""
    from .categorize import NON_SPEND, is_guess
    base = _json(st, ps.BASELINE_KEY, None) or {}
    known = set(base.get("known") or [])
    never = set(_json(st, ps.NEVER_KEY, [])) | set(_json(st, HELD_KEY, []))
    decided = _json(st, GUESS_KEY, {})
    done = {r["txn"] for r in ps.records(st)}
    hers = st.confirmed_categories()
    out = []
    for t in sorted(txns, key=lambda x: (x.date, x.fingerprint)):
        if t.fingerprint in known or t.fingerprint in never or t.fingerprint in decided \
                or t.fingerprint in done or t.excluded or t.amount <= 0:
            continue
        if t.category_source == "user" or t.fingerprint in hers or (t.category or "Other") in NON_SPEND \
                or t.split_mode or t.my_share is not None or not is_guess(t):
            continue
        out.append(t)
    return out


# ── After each sync ──────────────────────────────────────────────────────

class _Sync:
    """One sync's Claude calls: a budget, and a stop on the first failure
    that means Rules for the rest of it."""

    def __init__(self, st, base, user_id, client, now=None):
        self.st, self.base, self.user_id, self.client, self.now = st, base, user_id, client, now
        self.calls = 0
        self.stopped: str | None = None
        self.guesses = _json(st, GUESS_KEY, {})
        self.held = list(_json(st, HELD_KEY, []))

    def ask(self, t, allowed, counts, pattern):
        if self.stopped or self.calls >= PER_SYNC:
            return None, self.stopped or "per_sync"
        self.calls += 1
        answer, reason, a = _ask(self.st, base=self.base, user_id=self.user_id,
                                 shop=t.merchant or t.description or "", allowed=allowed,
                                 counts=counts, pattern=pattern, client=self.client, now=self.now)
        if answer is None:
            why = reason
            if why in _STOPS or why.startswith("error:"):
                self.stopped = why
            return None, why
        return answer, reason

    def decide(self, t, case, allowed, leader, answer, reason, counts) -> dict:
        """Keep what was decided for this row, and the detection."""
        agree = answer != "none" and (leader is None or answer == leader)
        shown = answer if agree else leader
        d = {"case": case, "allowed": allowed, "pick": answer, "agree": agree,
             "answer": shown, "line": reason if agree else None, "at": _now(),
             "prompt": "sort_reason@1", "version": VERSION}
        self.guesses[t.fingerprint] = d
        if not agree and leader is not None:
            self.held.append(t.fingerprint)
        _detect(self.st, t, d, counts)
        return d

    def save(self):
        self.st.set_setting(GUESS_KEY, json.dumps(self.guesses, sort_keys=True))
        self.st.set_setting(HELD_KEY, json.dumps(sorted(set(self.held))))


def _detect(st, t, d: dict, counts: Counter) -> None:
    from .signals import Detection, evidence
    from .signals.ledger import save
    save(st, Detection(kind="category_pattern", txn_ids=(t.fingerprint,), detector=DETECTOR,
                       version=VERSION, key=f"txn:{t.fingerprint}",
                       evidence=evidence(count=sum(counts.values()) or None, options=d["allowed"],
                                         case=d["case"], pick=d["pick"], agree=d["agree"],
                                         answer=d["answer"])))


def run(st, today: str, *, base, user_id, client=_USE_ENV, now=None) -> dict:
    """Smart's sync: Rules, with each auto-sort checked by Claude first, then
    a guess for the close and new ones. {"sorted": [records], "guessed": n,
    "held": n, "fallback": reason or None}."""
    sync = _Sync(st, base, user_id, client, now)
    held_now = []

    def vet(t, p):
        if p["kind"] != "category":
            return True                              # money between people: Rules
        counts = Counter(p["answers"])
        answer, reason = sync.ask(t, [p["answer"]], counts, p["answer"])
        if answer is None:
            return True                              # fell back: Rules
        d = sync.decide(t, "pattern", [p["answer"]], p["answer"], answer, reason, counts)
        if not d["agree"]:
            held_now.append(t.fingerprint)
            return False                             # Quick sort, never by itself
        return {"smart_line": reason}

    new = ps.run(st, today, vet=vet)
    txns = st.all_transactions()
    pats = ps.patterns(st, txns)
    guessed = 0
    rows = _new_rows(st, txns, pats)
    if rows:
        from . import likely
        from .marks import hidden_categories
        index = likely.Index(txns, hidden_categories(st))
        ready = {pid for pid, p in pats.items()
                 if p["ready"] and ps.enabled(st, pid) and ps.confirmed(st, pid)}
        for t in rows:
            if sync.stopped or sync.calls >= PER_SYNC:
                break
            m = ps._match(t, pats)
            if m is not None and m["id"] in ready:
                continue                             # a pattern's, above
            counts = _counts(pats, t)
            case, allowed, leader = _allowed(counts, index, t)
            if not case:
                continue
            answer, reason = sync.ask(t, allowed, counts, None)
            if answer is None:
                continue
            sync.decide(t, case, allowed, leader, answer, reason, counts)
            guessed += 1
    sync.save()
    return {"sorted": new, "guessed": guessed, "held": len(held_now), "fallback": sync.stopped,
            "calls": sync.calls}


# ── What the app shows (AI-03r / AI-03s) ─────────────────────────────────

def guesses(st) -> dict:
    return _json(st, GUESS_KEY, {})


def shown_guess(st, t) -> dict | None:
    """The decision Quick sort shows for this row while Smart is on."""
    if not is_smart(st):
        return None
    d = guesses(st).get(t.fingerprint)
    return d if d and d.get("answer") else None


def rules_line(n: int, shop: str) -> str:
    """AI-03r: "Like your last 5 at Pizzeria Bella." (the tidy name)."""
    return f"Like your last {n} at {shop}."


def annotate(st, review: dict, txns) -> None:
    """Each What was this? card's reason: `why` (one quiet grey line),
    {"text", "by"}: "claude" in Smart (AI-03s), else "pearl". In Smart, Claude's pick is the
    card's guess (`guess`), and its reason replaces Pearl's not sure."""
    items = review.get("unsure_category") or []
    if not items or not ps.is_on(st):
        return
    from .categorize import merchant_key
    by_id = {t.fingerprint: t for t in txns}
    pats = ps.patterns(st, txns)
    for it in items:
        t = by_id.get(it["txn"]["id"])
        if t is None:
            continue
        d = shown_guess(st, t)
        if d:
            it["guess"] = d["answer"]
            if d.get("line"):
                it["why"] = {"text": d["line"], "by": "claude"}
                it.pop("unsure", None)
                continue
        if it.get("unsure"):
            continue
        p = pats.get(ps._pattern_id("category", merchant_key(t.merchant or "")))
        if not p:
            continue
        last = p["answers"][-ps.CATEGORY_MIN:]
        if len(last) >= 2 and all(a == it.get("guess") for a in last):
            it["why"] = {"text": rules_line(len(last), p.get("merchant") or t.merchant), "by": "pearl"}


def record_reason(st, rec: dict) -> dict:
    """A Pearl sorted row's reason fields: Claude's words only while Smart is
    on (CN-09: back to plain at once)."""
    line = rec.get("smart_line")
    if line and is_smart(st):
        return {"reason": line, "reason_by": "claude"}
    return {}


def answered(st, txn_id: str, what: str) -> None:
    """Her answer to a card Smart guessed, against smart_sort@1."""
    d = guesses(st).get(txn_id)
    if not d or not d.get("answer"):
        return
    from .signals import outcome
    outcome(st, DETECTOR, f"txn:{txn_id}", "category_pattern", what, txn_ids=[txn_id],
            version=d.get("version") or VERSION)


def detections(st, version: str = VERSION) -> list:
    """smart_sort@1's detections as kept (finance/signals registry)."""
    from .signals import Detection, Evidence
    from .signals.ledger import rows
    return [Detection(kind=r["kind"], txn_ids=tuple(r["txn_ids"]), detector=DETECTOR,
                      version=r["version"], key=r["key"], status=r["status"],
                      evidence=Evidence.from_dict(r["evidence"]))
            for r in rows(st, DETECTOR) if r["version"] == version]
