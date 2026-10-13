"""Growth: a step's own screen, where you start, the moments a phase is
done, Learn, and the partner handoff (Pearl THL-129, THL-130, THL-134,
THL-136).

* GET /api/path/step/<key>: one step of the path with her numbers (THL-129
  GR-02 not done yet, GR-03 done, GR-04 "Keep it going"): income, bills,
  essentials, first_stop, full, saved_more, cards or invest.
* GET /api/path/placement: where she starts (THL-130 GR-06, GR-07), the
  last screen of onboarding. Steps already true are credited and named;
  savings that already hold a month of Essentials are offered as her Anchor.
* POST /api/path/placement: "See my path". Credits that Anchor, and marks
  every phase already done as seen, so its moment doesn't play as well.
* GET /api/moments: a phase done that she hasn't seen the moment for
  (GR-08 Protect done, GR-09 Build done, GR-10 Unveil done), once, on the next
  app open after it passes; and GR-20's "Welcome back" after the partner.
* POST /api/moments/<phase>: she's seen it (and every phase before it).
* GET /api/learn, PUT /api/learn/<module>: the Learn modules (THL-134
  GR-11 to GR-14) and her place in each — `learn.py`.
* POST /api/unveil/partner: "Continue to [Partner]" (THL-136 GR-19): the
  link out, with a tracking ID and nothing else of hers. Only once Protect is
  done (GR-23) and only when a partner is configured.
* PUT /api/unveil/partner/welcome {answer: "not_yet"}: GR-20's "Not yet".
  "Yes, I opened one" (GR-21) is the same self-report as GR-37, PUT
  /api/unveil, so there's one record of it.
* PUT / DELETE /api/unveil/partner/notify: GR-22's "Tell me when Pearl
  partners with a provider".

The partner is post-MVP (THL-136, founders' decision 2026-10-12) and is
configured, not built in: PEARL_PARTNER_NAME and PEARL_PARTNER_URL. With
neither set there is no partner, and GR-22 "We're choosing a partner" is
shown where the handoff would start.
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import date
from types import SimpleNamespace
from urllib.parse import urlencode, urlsplit, urlunsplit

from flask import jsonify, request

from . import api as core
from . import learn, milestones
from .api import bp, store

SEEN_KEY = "moments_seen"
PLACED_KEY = "placement_on"
CLICK_KEY = "partner_click"
NOTIFY_KEY = "partner_notify_on"
REF_KEY = "partner_ref"
WELCOME_DAYS = 14

# Which phase each step belongs to, and whether it's one of Build's "also
# counts" checks rather than a step.
STEPS = {"income": ("protect", False), "bills": ("protect", False),
         "essentials": ("protect", False), "first_stop": ("build", False),
         "full": ("build", False), "saved_more": ("build", True),
         "cards": ("build", True), "invest": ("unveil", False)}


def _today() -> date:
    return date.fromisoformat(core._today_iso())


def _month_start(d: date, ahead: int = 0) -> date:
    m = d.month - 1 + ahead
    return date(d.year + m // 12, m % 12 + 1, 1)


def _add_months(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) - 1 + n
    return f"{y + m // 12:04d}-{m % 12 + 1:02d}"


def _context(st, every_step: bool = False):
    """The ledger, safe to spend, the path and the Anchor, read once."""
    from . import safe_to_spend
    today = _today()
    txns = st.all_transactions()
    sts = core._home_sts(st, txns, today)
    types = {aid: r.get("account_type") or ""
             for aid, r in st.account_sync_rules().items() if r.get("enabled")}
    told_income = st.float_setting("home_income", 0.0)
    told_rent = st.float_setting("home_rent", 0.0)
    state = safe_to_spend.home_state(txns, today, sts, account_types=types,
                                     told_income=told_income, told_rent=told_rent)
    path = core._path(st, txns, today, sts, state, types, every_step=every_step)
    anchor = core._anchor(st, txns, today.isoformat())
    return SimpleNamespace(today=today, txns=txns, sts=sts, types=types, state=state,
                           path=path, anchor=anchor)


def _row(sts: dict, key: str) -> dict | None:
    return next((r for r in sts.get("rows") or [] if r["key"] == key), None)


def _invested(types: dict) -> bool:
    return any((t or "").lower() == "investment" for t in types.values())


# ── A step's own screen (GR-02, GR-03, GR-04) ─────────────────────────────

def _biggest_essential(txns, month: str) -> dict | None:
    """The largest Essentials charge in a month: GR-04's "a car repair of
    $1,900", when one charge explains most of a bigger month."""
    from .analytics import counts_as_spending, spend_amount
    from .categorize import group_of
    best = None
    for t in txns:
        if t.month != month or not counts_as_spending(t):
            continue
        if group_of(t.category or "Other") != "essentials":
            continue
        amount = spend_amount(t)
        if best is None or amount > best["amount"]:
            best = {"merchant": t.merchant or t.description, "category": t.category,
                    "amount": round(amount, 2)}
    return best


def _facts(st, c, key: str, step: dict) -> dict:
    """The numbers behind one step."""
    from . import income_bills
    from .usual_month import covered_months
    confirm = income_bills.load(st)
    anchor = c.anchor
    if key == "income":
        row = _row(c.sts, "income")
        return {"amount": row["amount"] if row else None, "source": c.sts.get("income_source"),
                "payer": row.get("payer") if row else None,
                "confirmed": bool(confirm.get("income_on"))}
    if key == "bills":
        row = _row(c.sts, "bills")
        return {"count": c.state.get("bills_found") or (row["count"] if row else 0),
                "to_come": row["amount"] if row else None,
                "confirmed": bool(confirm.get("bills_on"))}
    if key == "essentials":
        month = step.get("month")
        out = {"month": month, "income": step.get("income"), "essentials": step.get("essentials")}
        if month:
            out["left"] = round((step.get("income") or 0) - (step.get("essentials") or 0), 2)
            if step.get("lapsed"):
                out["biggest"] = _biggest_essential(c.txns, month)
                out["unusual"] = month in core._unusual_months(st)
        return out
    if key == "first_stop":
        first = anchor.get("first_stop") or 500
        counted = anchor.get("counted") or 0
        return {"started": anchor["started"], "first_stop": first, "counted": counted,
                "to_go": round(max(first - counted, 0), 2)}
    if key == "full":
        suggestion = anchor.get("suggestion") or {}
        target = anchor.get("target") or suggestion.get("amount") or None
        counted = anchor.get("counted") or 0
        pace = anchor.get("pace") or {}
        projection = anchor.get("projection") or {}
        return {"started": anchor["started"], "target": target, "counted": counted,
                "to_go": round(max((target or 0) - counted, 0), 2) if target else None,
                "size": anchor.get("size"), "pace": pace.get("usual"),
                "projection": projection if projection.get("state") == "range" else None}
    if key == "saved_more":
        months = covered_months(c.txns, c.today)[-3:]
        rows = []
        for m in months:
            income, spent, _ = milestones._month_income_and_spending(c.txns, m)
            rows.append({"month": m, "income": income, "spent": spent, "saved": income > spent})
        known_by = None
        if len(months) < 3:
            known_by = _add_months(c.today.strftime("%Y-%m"), 3 - len(months))
        return {"months": rows, "count": step.get("count", 0), "of": step.get("of", 0),
                "known_by": known_by}
    if key == "cards":
        months = covered_months(c.txns, c.today)
        last = months[-1] if months else None
        rules = st.account_sync_rules()
        cards = [a for a, t in c.types.items() if (t or "").lower() == "credit"]
        rows = []
        for aid in sorted(cards):
            net = sum(t.amount for t in c.txns
                      if last and t.month == last and t.account_id == aid and not t.excluded)
            rows.append({"name": (rules.get(aid) or {}).get("account_name") or "A card",
                         "grew_by": round(net, 2) if net > 0.005 else 0})
        return {"month": last, "cards": rows}
    if key == "invest":
        from .projections_api import _report
        return {"report": _report(st), "linked": _invested(c.types)}
    return {}


def step_detail(st, key: str) -> dict | None:
    if key not in STEPS:
        return None
    c = _context(st, every_step=True)
    p = c.path
    phase, also = STEPS[key]
    group = p["all"]["also" if also else phase]
    index = next(i for i, s in enumerate(group) if s["key"] == key)
    step = group[index]
    order, now = milestones.PHASES.index(phase), milestones.PHASES.index(p["phase"])
    if step["done"]:
        state = "lapsed" if step.get("lapsed") else "done"
    elif order > now:
        state = "ahead"
    elif also:
        state = "now" if p["phase"] == "build" else "todo"
    elif order == now and p["step"] == index + 1:
        state = "now"
    else:
        state = "todo"
    return {
        "key": key, "label": step["label"], "phase": phase,
        "phase_label": milestones.PHASE_LABELS[phase], "also": also,
        "index": index + 1, "of": len(group), "state": state,
        "facts": _facts(st, c, key, step),
        "checked_on": _month_start(c.today).isoformat(),
        "next_check": _month_start(c.today, 1).isoformat(),
        "current_phase": p["phase"], "next": p["next"],
    }


@bp.get("/path/step/<key>")
def path_step(key):
    detail = step_detail(store(), key)
    if detail is None:
        return jsonify({"error": "There’s no step by that name."}), 404
    return jsonify(detail)


# ── Where you start (GR-06, GR-07) ────────────────────────────────────────

def _anchor_credit(st, c) -> dict | None:
    """Savings that already hold a month of Essentials (GR-07's "We've
    counted it as your Anchor"), when Protect is done and no Anchor is set."""
    if not c.path["protect_done"] or c.anchor["started"]:
        return None
    suggestion = c.anchor.get("suggestion") or {}
    need = suggestion.get("amount") or 0
    savings = [a for a in core._anchor_accounts(st) if a["kind"] == "savings" and a["balance"] > 0]
    held = round(sum(a["balance"] for a in savings), 2)
    if need <= 0 or held < need:
        return None
    return {"amount": held, "target": need, "accounts": [a["account_id"] for a in savings]}


def placement(st) -> dict:
    """Which phase she starts in and what's credited, with her numbers."""
    c = _context(st, every_step=True)
    p, every = c.path, c.path["all"]
    credit = _anchor_credit(st, c)
    phase = p["phase"]
    if credit and phase == "build":
        phase = "unveil"
    invested = phase == "unveil" and all(s["done"] for s in every["unveil"])
    month = c.today.strftime("%Y-%m")
    if phase == "protect":
        income = _facts(st, c, "income", every["protect"][0])
        bills = _facts(st, c, "bills", every["protect"][1])
        ess = every["protect"][2]
        rows = [{"key": "income", "done": every["protect"][0]["done"], **income},
                {"key": "bills", "done": every["protect"][1]["done"], **bills},
                {"key": "essentials", "done": ess["done"], "month": ess.get("month"),
                 "income": ess.get("income"), "essentials": ess.get("essentials"),
                 "known_by": None if ess.get("month") else _add_months(month, 1)}]
    elif phase == "build":
        saved = _facts(st, c, "saved_more", next(s for s in every["also"] if s["key"] == "saved_more"))
        rows = [{"key": "protect", "done": True},
                {"key": "anchor", "done": False, "started": c.anchor["started"],
                 "counted": c.anchor.get("counted") or 0,
                 "target": c.anchor.get("target") or (c.anchor.get("suggestion") or {}).get("amount")},
                {"key": "saved_more", "done": len(saved["months"]) >= 3
                 and sum(1 for m in saved["months"] if m["saved"]) >= 2, **saved}]
    else:
        target = credit["target"] if credit else c.anchor.get("target")
        counted = credit["amount"] if credit else c.anchor.get("counted")
        rows = [{"key": "protect", "done": True},
                {"key": "build", "done": True, "counted": counted, "target": target},
                {"key": "invest", "done": invested}]
    done = sum(1 for r in rows if r["done"])
    return {"phase": phase, "invested": invested, "rows": rows, "done": done,
            "of": len(rows), "credit": credit}


@bp.get("/path/placement")
def path_placement():
    return jsonify(placement(store()))


@bp.post("/path/placement")
def place():
    """"See my path": credit the Anchor GR-07 named, and let no moment
    replay what the reveal already said."""
    st = store()
    c = _context(st)
    credit = _anchor_credit(st, c)
    today = _today().isoformat()
    if credit:
        st.set_setting("anchor_started", today)
        st.set_setting("anchor_accounts", json.dumps(sorted(credit["accounts"])))
        st.set_setting("anchor_target", credit["target"])
        st.set_setting("anchor_size", 1)
        c = _context(st)          # Full now: `_anchor` remembers it's earned.
    for ph in _done_phases(c):
        _mark_seen(st, ph)
    st.set_setting(PLACED_KEY, today)
    return jsonify(c.path)


# ── Moments (GR-08, GR-09, GR-10) and GR-20 ───────────────────────────────

def _done_phases(c) -> list[str]:
    p = c.path
    done = []
    if p["protect_done"]:
        done.append("protect")
    if p["phase"] == "unveil":
        done.append("build")
        if all(s["done"] for s in p["steps"]):
            done.append("unveil")
    return done


def _seen(st) -> set[str]:
    raw = core._json_setting(st, SEEN_KEY, [])
    return set(raw) if isinstance(raw, list) else set()


def _mark_seen(st, phase: str) -> None:
    """She's seen this phase's moment, and so every one before it."""
    upto = milestones.PHASES[:milestones.PHASES.index(phase) + 1]
    st.set_setting(SEEN_KEY, json.dumps(sorted(_seen(st) | set(upto))))


def partner_config() -> dict | None:
    """The configured partner, or None. Both a name and an https link."""
    name = (os.environ.get("PEARL_PARTNER_NAME") or "").strip()
    url = (os.environ.get("PEARL_PARTNER_URL") or "").strip()
    if not name or not url.lower().startswith(("https://", "http://localhost", "http://127.0.0.1")):
        return None
    return {"name": name[:60], "url": url}


def _click(st) -> dict | None:
    raw = core._json_setting(st, CLICK_KEY, None)
    return raw if isinstance(raw, dict) and raw.get("on") else None


def partner_state(st, path: dict, report: dict | None) -> dict:
    """GR-16's partner card: who, whether GR-20 should ask, GR-22's sign-up."""
    cfg = partner_config()
    click = _click(st)
    unveiled = path["phase"] == "unveil" and all(s["done"] for s in path["steps"])
    welcome = bool(cfg and click and not click.get("answered") and not report and not unveiled
                   and (_today() - date.fromisoformat(click["on"])).days <= WELCOME_DAYS)
    return {"configured": bool(cfg), "name": cfg["name"] if cfg else None,
            "welcome": welcome, "clicked_on": click["on"] if click else None,
            "notify": st.setting(NOTIFY_KEY) not in (None, "")}


def moments(st) -> dict:
    from .projections_api import _report
    c = _context(st)
    pending = [ph for ph in _done_phases(c) if ph not in _seen(st)]
    phase = pending[-1] if pending else None
    a = c.anchor
    out = {"phase": phase, "path": c.path, "partner_welcome": False,
           "anchor": {"started": a["started"], "counted": a.get("counted"),
                      "target": a.get("target"), "size": a.get("size")}}
    out["partner_welcome"] = partner_state(st, c.path, _report(st))["welcome"]
    return out


@bp.get("/moments")
def get_moments():
    return jsonify(moments(store()))


@bp.post("/moments/<phase>")
def see_moment(phase):
    if phase not in milestones.PHASES:
        return jsonify({"error": "There’s no phase by that name."}), 404
    st = store()
    _mark_seen(st, phase)
    return jsonify({"seen": sorted(_seen(st))})


# ── Learn (GR-11 to GR-14) ────────────────────────────────────────────────

@bp.get("/learn")
def learn_page():
    return jsonify(learn.payload(store()))


@bp.put("/learn/<module_id>")
def learn_progress(module_id):
    out, error = learn.update(store(), module_id, request.get_json(silent=True) or {},
                              _today().isoformat())
    if error:
        return jsonify({"error": error}), 404 if module_id not in learn.BY_ID else 400
    return jsonify(out)


# ── The partner handoff (GR-19 to GR-23, post-MVP) ────────────────────────

def _with_ref(url: str, ref: str) -> str:
    parts = urlsplit(url)
    query = f"{parts.query}&" if parts.query else ""
    return urlunsplit(parts._replace(query=query + urlencode({"pearl_ref": ref})))


@bp.post("/unveil/partner")
def go_to_partner():
    """GR-19's "Continue to [Partner]". The link carries a tracking ID only:
    no transaction, balance or name of hers goes to the partner (THL-13)."""
    cfg = partner_config()
    if not cfg:
        return jsonify({"error": "Pearl doesn’t have a partner yet."}), 404
    st = store()
    if not _context(st).path["protect_done"]:
        return jsonify({"error": "This opens once Protect is done."}), 409
    ref = st.setting(REF_KEY)
    if not ref:
        ref = secrets.token_urlsafe(12)
        st.set_setting(REF_KEY, ref)
    st.set_setting(CLICK_KEY, json.dumps({"on": _today().isoformat(), "answered": False}))
    return jsonify({"url": _with_ref(cfg["url"], ref), "name": cfg["name"]})


@bp.put("/unveil/partner/welcome")
def partner_welcome():
    """GR-20's "Not yet": stop asking until she goes to the partner again."""
    body = request.get_json(silent=True) or {}
    if body.get("answer") != "not_yet":
        return jsonify({"error": "Say not_yet, or mark Unveil done."}), 400
    st = store()
    answered(st)
    from .projections_api import unveil
    return jsonify(unveil(st))


def answered(st) -> None:
    """GR-20 has had its answer, either way."""
    click = _click(st)
    if click:
        st.set_setting(CLICK_KEY, json.dumps({**click, "answered": True}))


@bp.put("/unveil/partner/notify")
def partner_notify():
    """GR-22's "Tell me when Pearl partners with a provider"."""
    from .projections_api import unveil
    st = store()
    if st.setting(NOTIFY_KEY) in (None, ""):
        st.set_setting(NOTIFY_KEY, _today().isoformat())
    return jsonify(unveil(st))


@bp.delete("/unveil/partner/notify")
def partner_notify_off():
    from .projections_api import unveil
    st = store()
    st.set_setting(NOTIFY_KEY, "")
    return jsonify(unveil(st))


def mark_unveil_seen(st) -> None:
    """GR-37 and GR-21 lead straight to GR-10, so it needn't play again."""
    _mark_seen(st, "unveil")
