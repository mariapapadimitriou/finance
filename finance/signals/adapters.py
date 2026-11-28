"""Adapters, not rewrites (THL-310): each detection module as it is, its
answer turned into `Detection`s.

Every adapter is `detect(st, txns, today) -> [Detection]` and only reads:
it calls the module's own function and changes nothing in it, so what the
app shows is exactly what it was. Their output on the demo ledger is held
to the modules' own in tests/test_signals.py. Nothing names a merchant:
every key comes from her ledger.

Two read the Needs a look review the app reads (`review.for_store`), because
their modules answer questions in it: `likely` and `pairs`.
"""

from __future__ import annotations

from datetime import date, timedelta

from .model import CONFIRMED, PROPOSED, REJECTED, Detection, evidence


def _ids(rows) -> tuple[str, ...]:
    return tuple(t.fingerprint for t in rows)


def _sorted(rows):
    return sorted(rows, key=lambda t: (t.date, t.fingerprint))


# ── pattern_sort.py: category patterns and joint "theirs" ─────────────────

def pattern_sort(st, txns, today, version):
    """Patterns strong enough to sort (5 the same, 8 between people):
    proposed until her Yes (`confirm`), rejected after a second Skip.
    A pattern held by one Skip is still proposed, with `held`."""
    from .. import pattern_sort as ps
    out = []
    state = ps._state(st)
    for pid, p in ps.patterns(st, txns).items():
        if not p["ready"]:
            continue
        s = state.get(pid) or {}
        yes = ps.confirmed(st, pid)
        held = ps._held(st, p)
        status = CONFIRMED if yes else REJECTED if int(s.get("skips") or 0) >= ps.SKIPS_MAX else PROPOSED
        kind = "category_pattern" if p["kind"] == "category" else "joint_theirs"
        days = list(p["days"])
        out.append(Detection(
            kind=kind, txn_ids=tuple(p["answered"]), detector=f"pattern_sort.{p['kind']}",
            version=version, key=pid, status=status,
            evidence=evidence(count=p["count"], first=days[0] if days else None,
                              last=days[-1] if days else None, dates=days,
                              cadence=ps.rhythm(days), options=(p["answer"],),
                              need=p["need"], held=bool(held) and not yes, on=ps.enabled(st, pid))))
    return out


# ── likely.py: the four likeliest categories ──────────────────────────────

def likely(st, txns, today, version, review=None):
    """Each What was this? card's likeliest categories, in order."""
    review = review if review is not None else _review(st, today)
    out = []
    for it in review.get("unsure_category") or []:
        options = it.get("likely") or []
        if not options:
            continue
        tid = it["txn"]["id"]
        out.append(Detection(kind="category_pattern", txn_ids=(tid,), detector="likely",
                             version=version, key=tid,
                             evidence=evidence(count=len(options), options=options,
                                               guess=it.get("guess"))))
    return out


# ── insights/recurring.py: subscriptions and bills ───────────────────────

def recurring(st, txns, today, version):
    """Regular charges at one merchant. A bill when its category is an
    essential, otherwise a subscription."""
    from ..categorize import group_of
    from ..insights.recurring import detect_recurring
    out = []
    for rec in detect_recurring(txns, as_of=today):
        days = set(rec["dates"])
        rows = _sorted(t for t in txns if t.merchant == rec["merchant"] and t.amount > 0
                       and t.date in days)
        kind = "bill" if group_of(rec["category"]) == "essentials" else "subscription"
        out.append(Detection(
            kind=kind, txn_ids=_ids(rows), detector="recurring", version=version,
            key=rec["merchant"], score=rec["confidence"],
            evidence=evidence(count=rec["occurrences"], first=rec["first_seen"],
                              last=rec["last_seen"], dates=rec["dates"],
                              amount=rec["typical_amount"], cadence=rec["cadence"],
                              category=rec["category"], active=rec["active"],
                              annual=rec["annual_cost"], next=rec["next_expected"],
                              price_change=bool(rec["price_change"]))))
    return out


# ── recurring_transfers.py: the same transfer on a schedule ──────────────

def recurring_transfers(st, txns, today, version):
    """Runs of transfers out still asked about ("Is this a recurring
    transfer?"), as review.build asks for them."""
    from ..recurring_transfers import series
    from ..transfers import transfer_pairs
    live = [t for t in txns if not t.excluded]
    paired = set(transfer_pairs(txns, today=today))
    out = []
    for s in series(live, st.recurring_transfers() or [], paired):
        out.append(Detection(
            kind="bill", txn_ids=tuple(s["ids"]), detector="recurring_transfers",
            version=version, key=s["key"],
            evidence=evidence(count=s["count"], first=s["first"], last=s["last"],
                              dates=s["dates"], amount=s["amount"], cadence=s["cadence"],
                              replaces=len(s.get("replaces") or []) or None)))
    return out


# ── income.py: how often pay arrives ──────────────────────────────────────

def income(st, txns, today, version):
    """Her pay's rhythm over the last six months, when there is one."""
    from .. import income as inc
    found = inc.cadence(txns, today)
    if not found:
        return []
    days = set(found["paydays"])
    rows = _sorted(t for t in txns if inc.is_income(t) and inc.kind_of(t) == "salary"
                   and t.date[:10] in days)
    return [Detection(
        kind="income", txn_ids=_ids(rows), detector="income.cadence", version=version,
        key="pay", evidence=evidence(count=len(found["paydays"]), first=found["paydays"][0],
                                     last=found["paydays"][-1], dates=found["paydays"],
                                     amount=found["paycheque"], cadence=found["cadence"],
                                     monthly=found["monthly"],
                                     three_pay_months=len(found["three_pay_months"]) or None))]


# ── income_bills.py: Is this your paycheque? and rent by e-Transfer ──────

def income_bills_pay(st, txns, today, version):
    """I-01's regular deposits that look like pay, strongest first."""
    from .. import income_bills as ib
    from ..transfers import transfer_pairs
    day = date.fromisoformat(today)
    found = ib.pay_candidates(txns, day, ib.load(st))
    if not found:
        return []
    pairs = transfer_pairs(txns, today=today)
    own = set(pairs) | set(pairs.values())
    since = (day - timedelta(days=ib.PAY_LOOKBACK_DAYS)).isoformat()
    out = []
    for c in found:
        rows = _sorted(t for t in txns if since <= t.date[:10] <= today
                       and ib.could_be_pay(t, own) and ib.payer_of(t) == c["payer"])
        out.append(Detection(
            kind="income", txn_ids=_ids(rows), detector="income_bills.pay", version=version,
            key=c["payer"],
            evidence=evidence(count=c["count"], last=c["last"], amount=c["amount"],
                              cadence=c["cadence"], next=c["next"], salary=c["salary"])))
    return out


def income_bills_rent(st, txns, today, version):
    """Monthly e-Transfers to one person at a rent-like amount."""
    from .. import income_bills as ib
    out = []
    for s in ib.rent_series(txns, date.fromisoformat(today)):
        out.append(Detection(
            kind="bill", txn_ids=tuple(s["ids"]), detector="income_bills.rent", version=version,
            key=s["key"], score=s["confidence"],
            evidence=evidence(count=s["occurrences"], first=s["first_seen"], last=s["last_seen"],
                              dates=s["dates"], amount=s["typical_amount"], cadence=s["cadence"])))
    return out


# ── income_kind_rules.py: Always for a payer ─────────────────────────────

def income_kind_rules(st, txns, today, version):
    """Deposits her "Always for …" rules count as income of their kind.
    Hers already, so confirmed."""
    from .. import income_kind_rules as ikr
    by_payer: dict[str, list] = {}
    kinds: dict[str, str] = {}
    for t, key, rule in ikr.targets(st, txns):
        by_payer.setdefault(key, []).append(t)
        kinds[key] = rule["kind"]
    out = []
    for key, rows in by_payer.items():
        rows = _sorted(rows)
        out.append(Detection(
            kind="income", txn_ids=_ids(rows), detector="income_kind_rules", version=version,
            key=key, status=CONFIRMED,
            evidence=evidence(count=len(rows), first=rows[0].date[:10], last=rows[-1].date[:10],
                              dates=[t.date[:10] for t in rows], income_kind=kinds[key])))
    return out


# ── trips.py: likely trips ────────────────────────────────────────────────

def trips(st, txns, today, version):
    """TR-01's likely trips: two kinds of signal agree."""
    from .. import trips as tr
    out = []
    for c in tr.candidates(st, txns, today):
        out.append(Detection(
            kind="trip", txn_ids=tuple(c["ids"]), detector="trips", version=version, key=c["id"],
            evidence=evidence(count=len(c["ids"]), first=c["start"], last=c["end"],
                              days=c["days"], place=c["place"], flight=c["flight"],
                              hotel=c["hotel"], fees=c["fees"])))
    return out


# ── transfers.py: both ends of one transfer ──────────────────────────────

def transfers(st, txns, today, version):
    """Money that left one of her accounts and arrived in another: a card
    payment when either end is a card's, otherwise a transfer."""
    from ..transfers import transfer_pairs
    from ..txlist import _is_card_payment
    by_id = {t.fingerprint: t for t in txns}
    out = []
    for out_id, in_id in transfer_pairs(txns, today=today).items():
        a, b = by_id.get(out_id), by_id.get(in_id)
        if a is None or b is None:
            continue
        kind = "card_payment" if _is_card_payment(a) or _is_card_payment(b) else "transfer_pair"
        gap = abs((date.fromisoformat(a.date[:10]) - date.fromisoformat(b.date[:10])).days)
        out.append(Detection(
            kind=kind, txn_ids=(out_id, in_id), detector="transfers.pairs", version=version,
            key=out_id,
            evidence=evidence(count=2, first=min(a.date[:10], b.date[:10]),
                              last=max(a.date[:10], b.date[:10]), dates=[a.date[:10], b.date[:10]],
                              amount=a.amount, days_apart=gap, linked=bool(a.transfer_link))))
    return out


# ── pairs.py: what the ledger says a money-in row is ─────────────────────

def pairs(st, txns, today, version, review=None):
    """Money in the evidence answers: a split's share, a refund, a payback."""
    review = review if review is not None else _review(st, today)
    by_id = {t.fingerprint: t for t in txns}
    out = []
    for it in review.get("money_in") or []:
        pair = it.get("pair")
        if not pair:
            continue
        tid = it["txn"]["id"]
        t = by_id.get(tid)
        out.append(Detection(kind="payback", txn_ids=(tid, pair["other"]), detector="pairs",
                             version=version, key=tid,
                             evidence=evidence(count=2, first=t.date[:10] if t else None,
                                               amount=-t.amount if t else None, case=pair["kind"])))
    return out


# ── etransfers.py: who an e-Transfer was from, or to ─────────────────────

def etransfers(st, txns, today, version):
    """The person the bank's words name on an e-Transfer. One she typed
    is hers already; only the bank's are detections."""
    from ..etransfers import party
    out = []
    for t in _sorted(txns):
        p = party(t)
        if not p or p.get("named_by") != "bank" or not p.get("name"):
            continue
        out.append(Detection(kind="party", txn_ids=(t.fingerprint,), detector="etransfers.party",
                             version=version, key=t.fingerprint,
                             evidence=evidence(count=1, first=t.date[:10], last=t.date[:10],
                                               options=(p["name"],), direction=p["direction"],
                                               handle=bool(p.get("handle")))))
    return out


# ── joint.py: a joint account's other owner paying her back ──────────────

def joint(st, txns, today, version):
    """TP-01: money in whose other end is money out of a joint account:
    one of its other owners could have paid her back."""
    from ..joint import payback_offer
    from ..transfers import transfer_pairs
    by_id = {t.fingerprint: t for t in txns}
    out = []
    for out_id, in_id in transfer_pairs(txns, today=today).items():
        offer = payback_offer(by_id.get(in_id), by_id.get(out_id))
        if not offer:
            continue
        t = by_id[in_id]
        out.append(Detection(kind="joint_theirs", txn_ids=(in_id, out_id),
                             detector="joint.payback_offer", version=version, key=in_id,
                             evidence=evidence(count=2, first=t.date[:10], amount=-t.amount,
                                               options=offer["people"])))
    return out


# ── duplicates.py: the same purchase twice ───────────────────────────────

def duplicates(st, txns, today, version):
    """Pairs she was asked about (and how she answered: Same purchase is a
    Yes, Two different purchases a Not this), and new ones not yet asked."""
    from .. import duplicates as dup
    by_id = {t.fingerprint: t for t in txns}
    out = []
    recorded = st.duplicates()
    status = {dup.PENDING: PROPOSED, dup.SAME: CONFIRMED, dup.DIFFERENT: REJECTED}
    for copy_id, rec in sorted(recorded.items()):
        t = by_id.get(copy_id)
        out.append(Detection(kind="duplicate", txn_ids=(copy_id, rec["twin"]), detector="duplicates",
                             version=version, key=copy_id, status=status.get(rec["state"], PROPOSED),
                             evidence=evidence(count=2, first=t.date[:10] if t else None,
                                               amount=t.amount if t else None,
                                               found_on=rec["found_on"] or None)))
    for copy, twin in dup.detect(txns, st.duplicate_ids()):
        out.append(Detection(kind="duplicate", txn_ids=(copy.fingerprint, twin.fingerprint),
                             detector="duplicates", version=version, key=copy.fingerprint,
                             evidence=evidence(count=2, first=copy.date[:10], amount=copy.amount)))
    return out


def _review(st, today):
    from ..review import for_store
    return for_store(st, today)


# ── AI Phase 4 (THL-309): new detectors ──────────────────────────────────

def _worth(st, today, pick):
    from .. import worth_a_look as wl
    return pick(wl._Ctx(st, date.fromisoformat(today)))


def price_rise(st, txns, today, version):
    """WL-20: a bill she counts whose last charge is more than she expects."""
    from .. import worth_a_look as wl
    out = []
    for it in _worth(st, today, wl._price_rises):
        d = it["_data"]
        rec = d.get("rec") or {}
        rows = _sorted(t for t in txns if t.merchant == rec.get("merchant") and t.amount > 0
                       and t.date in set(rec.get("dates") or ()))
        out.append(Detection(
            kind="bill", txn_ids=_ids(rows), detector="recurring.price_rise", version=version,
            key=it["id"].split(":", 1)[1],
            evidence=evidence(count=rec.get("occurrences"), first=rec.get("first_seen"),
                              last=rec.get("last_seen"), amount=d["amount"], cadence=d.get("cadence"),
                              before=d.get("before"))))
    return out


def forgotten(st, txns, today, version):
    """WL-21: a monthly subscription she has never answered, six months on."""
    from .. import worth_a_look as wl
    out = []
    for it in _worth(st, today, wl._forgotten):
        d = it["_data"]
        rec = d.get("rec") or {}
        rows = _sorted(t for t in txns if t.merchant == rec.get("merchant") and t.amount > 0
                       and t.date in set(rec.get("dates") or ()))
        out.append(Detection(
            kind="subscription", txn_ids=_ids(rows), detector="recurring.forgotten", version=version,
            key=it["id"].split(":", 1)[1],
            evidence=evidence(count=rec.get("occurrences"), first=rec.get("first_seen"),
                              last=rec.get("last_seen"), amount=d["amount"], cadence="monthly",
                              months=d.get("months"))))
    return out


def pair_asks(st, txns, today, version):
    """TR-30: two rows Pearl asks about as one payment between her accounts."""
    from .. import pair_asks as pa
    return [Detection(kind=p["kind"], txn_ids=(p["out"], p["in"]), detector=pa.DETECTOR,
                      version=version, key=p["out"],
                      evidence=evidence(count=2, first=p["out_date"], last=p["in_date"],
                                        dates=[p["out_date"], p["in_date"]], amount=p["amount"],
                                        days_apart=p["days"]))
            for p in pa.asks(st, txns, today)]
