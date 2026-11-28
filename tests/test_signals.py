"""Signals, one detection framework (AI Phase 3, THL-310).

* Each adapter's output on the demo ledger (and the labelled fixtures, for
  the detectors the demo has none of) is the old module's, row for row.
* Running the detectors changes nothing: no row, no setting, no version.
* The `detections` table: pattern sort's records go there instead of the
  `pattern_sort_log` setting, which is still read; every Yes, Skip, Not
  this, Undo and Stop is recorded against detector@version; Start over
  clears both tables; the summary's arithmetic.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "eval"))

from signals_replay import DEMO_TODAY, demo_store, fixture_store, load_fixtures  # noqa: E402

from finance import signals  # noqa: E402
from finance.signals import ledger  # noqa: E402
from finance.signals.model import Detection, Evidence, evidence  # noqa: E402

TODAY = DEMO_TODAY.isoformat()


@pytest.fixture(scope="module")
def ledgers(tmp_path_factory):
    """The demo ledger and every labelled fixture, with the day each is on."""
    where = str(tmp_path_factory.mktemp("signals"))
    out = [("demo", demo_store(where), TODAY)]
    for fx in load_fixtures():
        out.append((fx["name"], fixture_store(where, fx), fx["today"]))
    # Needs a look's one-time fixes happen on the first read (as when the
    # app opens), before anything is measured.
    from finance.review import for_store
    for _, st, day in out:
        for_store(st, day)
    return out


def found(st, name, day):
    return signals.run(name, st, st.all_transactions(), day)


# ── Adapters give what the modules give ──────────────────────────────────

class TestAdaptersMatchTheModules:
    def test_recurring(self, ledgers):
        from finance.insights.recurring import detect_recurring
        for _, st, day in ledgers:
            txns = st.all_transactions()
            old = detect_recurring(txns, as_of=day)
            new = found(st, "recurring", day)
            assert [(r["merchant"], r["dates"], r["confidence"], r["typical_amount"], r["cadence"])
                    for r in old] == \
                [(d.key, list(d.evidence.dates), d.score, d.evidence.amount, d.evidence.cadence)
                 for d in new]
            for d in new:
                assert len(d.txn_ids) >= d.evidence.count

    def test_recurring_transfers(self, ledgers):
        from finance.recurring_transfers import series
        from finance.transfers import transfer_pairs
        for _, st, day in ledgers:
            txns = st.all_transactions()
            old = series([t for t in txns if not t.excluded], st.recurring_transfers(),
                         set(transfer_pairs(txns, today=day)))
            new = found(st, "recurring_transfers", day)
            assert [(s["key"], s["ids"], s["amount"], s["cadence"]) for s in old] == \
                [(d.key, list(d.txn_ids), d.evidence.amount, d.evidence.cadence) for d in new]
        assert any(found(st, "recurring_transfers", day) for _, st, day in ledgers)

    def test_income_cadence(self, ledgers):
        from finance import income
        for _, st, day in ledgers:
            old = income.cadence(st.all_transactions(), day)
            new = found(st, "income.cadence", day)
            if old is None:
                assert new == []
                continue
            (d,) = new
            assert (list(d.evidence.dates), d.evidence.cadence, d.evidence.amount) == \
                (old["paydays"], old["cadence"], old["paycheque"])

    def test_pay_candidates(self, ledgers):
        from finance import income_bills as ib
        for _, st, day in ledgers:
            old = ib.pay_candidates(st.all_transactions(), date.fromisoformat(day), ib.load(st))
            new = found(st, "income_bills.pay", day)
            assert [(c["payer"], c["amount"], c["cadence"], c["count"]) for c in old] == \
                [(d.key, d.evidence.amount, d.evidence.cadence, d.evidence.count) for d in new]
            for c, d in zip(old, new):
                assert len({t[:10] for t in (st.get_transaction(i).date for i in d.txn_ids)}) == c["count"]

    def test_rent_series(self, ledgers):
        from finance import income_bills as ib
        for _, st, day in ledgers:
            old = ib.rent_series(st.all_transactions(), date.fromisoformat(day))
            new = found(st, "income_bills.rent", day)
            assert [(s["key"], s["ids"]) for s in old] == [(d.key, list(d.txn_ids)) for d in new]
        assert any(found(st, "income_bills.rent", day) for _, st, day in ledgers)

    def test_trips(self, ledgers):
        from finance import trips
        for _, st, day in ledgers:
            old = trips.candidates(st, st.all_transactions(), day)
            new = found(st, "trips", day)
            assert [(c["id"], c["ids"]) for c in old] == [(d.key, list(d.txn_ids)) for d in new]

    def test_transfer_pairs(self, ledgers):
        from finance.transfers import transfer_pairs
        for _, st, day in ledgers:
            old = transfer_pairs(st.all_transactions(), today=day)
            new = found(st, "transfers.pairs", day)
            assert {d.txn_ids for d in new} == set(old.items())
        kinds = {d.kind for _, st, day in ledgers for d in found(st, "transfers.pairs", day)}
        assert kinds == {"card_payment", "transfer_pair"}

    def test_duplicates(self, ledgers):
        from finance import duplicates as dup
        for _, st, day in ledgers:
            txns = st.all_transactions()
            new = found(st, "duplicates", day)
            recorded = {(k, v["twin"]) for k, v in st.duplicates().items()}
            fresh = {(a.fingerprint, b.fingerprint) for a, b in dup.detect(txns, st.duplicate_ids())}
            assert {d.txn_ids for d in new} == recorded | fresh
        assert any(found(st, "duplicates", day) for _, st, day in ledgers)

    def test_pattern_sort(self, ledgers):
        from finance import pattern_sort as ps
        for _, st, day in ledgers:
            txns = st.all_transactions()
            ready = {pid: p for pid, p in ps.patterns(st, txns).items() if p["ready"]}
            new = found(st, "pattern_sort.category", day) + found(st, "pattern_sort.joint", day)
            assert {d.key: list(d.txn_ids) for d in new} == {pid: p["answered"] for pid, p in ready.items()}
            asks = {a["id"] for a in ps.pending(st, day, txns)}
            assert {d.key for d in new if d.status == "proposed" and not d.evidence.fact("held")} == asks
        assert any(found(st, "pattern_sort.category", day) for _, st, day in ledgers)

    def test_etransfer_party(self, ledgers):
        from finance.etransfers import party
        for _, st, day in ledgers:
            named = {t.fingerprint: party(t)["name"] for t in st.all_transactions()
                     if party(t) and party(t)["named_by"] == "bank" and party(t)["name"]}
            assert {d.key: d.evidence.options[0] for d in found(st, "etransfers.party", day)} == named

    def test_the_review_readers(self, ledgers):
        """likely and pairs: what Needs a look already says, card for card."""
        from finance.review import for_store
        for _, st, day in ledgers:
            review = for_store(st, day)
            likely = {i["txn"]["id"]: i["likely"] for i in review.get("unsure_category") or [] if i.get("likely")}
            assert {d.key: list(d.evidence.options) for d in found(st, "likely", day)} == likely
            pairs = {i["txn"]["id"]: i["pair"]["other"] for i in review.get("money_in") or [] if i.get("pair")}
            assert {d.key: d.txn_ids[1] for d in found(st, "pairs", day)} == pairs

    def test_income_kind_rules_and_joint_report_what_they_cover(self, ledgers):
        from finance import income_kind_rules as ikr
        for _, st, day in ledgers:
            covered = {t.fingerprint for t, _, _ in ikr.targets(st, st.all_transactions())}
            assert {i for d in found(st, "income_kind_rules", day) for i in d.txn_ids} == covered
            assert all(d.kind == "joint_theirs" for d in found(st, "joint.payback_offer", day))

    def test_every_detector_runs_and_names_its_version(self, ledgers):
        for _, st, day in ledgers:
            for name, ds in signals.run_all(st, today=day).items():
                for d in ds:
                    assert d.detector == name and d.version == signals.DETECTORS[name].version
                    assert d.kind in signals.DETECTORS[name].kinds
                    assert d.tag == f"{name}@{d.version}"

    def test_running_them_changes_nothing(self, ledgers):
        for _, st, day in ledgers:
            before = (st.version(), sorted((t.fingerprint, t.category, t.category_source)
                                           for t in st.all_transactions()))
            with st.conn() as c:
                settings = c.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
            signals.run_all(st, today=day)
            with st.conn() as c:
                assert c.execute("SELECT key, value FROM settings ORDER BY key").fetchall() == settings
                assert c.execute("SELECT COUNT(*) AS n FROM detections").fetchone()["n"] == 0
            assert (st.version(), sorted((t.fingerprint, t.category, t.category_source)
                                         for t in st.all_transactions())) == before


class TestTheRecord:
    def test_kinds_and_statuses_are_checked(self):
        with pytest.raises(ValueError):
            Detection(kind="vibes", txn_ids=(), evidence=evidence(), detector="x", version="1", key="k")
        with pytest.raises(ValueError):
            Detection(kind="trip", txn_ids=(), evidence=evidence(), detector="x", version="1", key="k",
                      status="maybe")

    def test_evidence_round_trips(self):
        ev = evidence(count=3, first="2026-10-01", dates=["2026-10-01"], amount=12.345,
                      series=[("2026-10-01", 12.345)], options=["Coffee"], place="Lisbon", ignored=None)
        assert ev.amount == 12.35 and ev.fact("place") == "Lisbon" and ev.fact("ignored") is None
        assert Evidence.from_dict(json.loads(json.dumps(ev.to_dict()))) == ev


# ── The table and her answers ────────────────────────────────────────────

from test_pattern_sort import add, client, day, farm_boy_history, ids, on, run, tx  # noqa: E402,F401


def outcomes(c, detector=None):
    return [(o["detector"], o["version"], o["outcome"]) for o in ledger.outcomes(c.st, detector)]


class TestPatternSortRecords:
    def test_new_records_go_to_the_table_not_the_setting(self, client):
        farm_boy_history(client)
        on(client)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        rec = run(client)["rows"][0]
        assert client.st.setting("pattern_sort_log") in (None, "")
        (row,) = [r for r in ledger.rows(client.st) if r["parent"]]
        assert row["status"] == "confirmed" and row["txn_ids"] == [rec["txn"]]
        assert row["detector"] == "pattern_sort.category" and row["version"] == "1"
        assert json.loads(row["payload"])["id"] == rec["id"]
        assert client.get("/api/pattern-sort").get_json()["rows"][0]["id"] == rec["id"]
        assert outcomes(client) == [("pattern_sort.category", "1", "yes"),
                                    ("pattern_sort.category", "1", "applied")]

    def test_undo_and_stop_are_recorded(self, client):
        farm_boy_history(client)
        on(client)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)), tx("NORTHSIDE PANTRY", 33.10, day(2)))
        rows = run(client)["rows"]
        assert client.post(f"/api/pattern-sort/{rows[0]['id']}/undo").status_code == 200
        pid = rows[0]["pattern"]
        assert client.post(f"/api/pattern-sort/rules/{pid}/stop").status_code == 200
        assert [o[2] for o in outcomes(client)] == ["yes", "applied", "applied", "undo", "stop"]
        statuses = {r["key"]: r["status"] for r in ledger.rows(client.st)}
        assert statuses[pid] == "undone"
        assert all(statuses[f"row:{r['id']}"] == "undone" for r in rows)
        assert client.get("/api/pattern-sort").get_json()["rows"] == []

    def test_skip_twice_is_rejected_and_undo_on_yes_asks_again(self, client):
        farm_boy_history(client)
        from finance import pattern_sort as ps
        ps.switched_on(client.st)
        pid = client.get("/api/pattern-sort/asks").get_json()["asks"][0]["id"]
        client.post(f"/api/pattern-sort/asks/{pid}/yes")
        client.post(f"/api/pattern-sort/asks/{pid}/undo")
        assert ledger.get(client.st, f"pattern_sort.category:{pid}")["status"] == "proposed"
        client.post(f"/api/pattern-sort/asks/{pid}/skip")
        assert ledger.get(client.st, f"pattern_sort.category:{pid}")["status"] == "proposed"
        for i in range(5):                                   # five more agreeing answers
            add(client, tx("NORTHSIDE PANTRY", 70.0 + i, day(20 - i)))
        for tid in ids(client, "NORTHSIDE PANTRY"):
            client.post(f"/api/transactions/{tid}/mark",
                        json={"case": "spending", "category": "Groceries", "remember": False})
        client.post(f"/api/pattern-sort/asks/{pid}/skip")
        assert ledger.get(client.st, f"pattern_sort.category:{pid}")["status"] == "rejected"
        assert [o[2] for o in outcomes(client)] == ["yes", "undo", "skip", "skip"]

    def test_the_old_setting_is_still_read_and_its_undo_still_works(self, client):
        from finance import pattern_sort as ps
        farm_boy_history(client)
        on(client)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        run(client)
        (old,) = ledger._table_log(client.st)
        # Move it to where a record written before THL-310 sits: the setting.
        with client.st.conn() as c:
            c.execute("DELETE FROM detections WHERE parent IS NOT NULL")
        ps._save(client.st, ps.LOG_KEY, [old])
        assert [r["id"] for r in ps.records(client.st)] == [old["id"]]
        assert client.post(f"/api/pattern-sort/{old['id']}/undo").status_code == 200
        assert json.loads(client.st.setting(ps.LOG_KEY))[0]["undone"] is True
        assert ps.records(client.st) == []
        assert client.st.get_transaction(old["txn"]).category_source != "pattern"
        # The table took no copy of the record, only her Undo, against the pattern's detector.
        assert ledger._table_log(client.st) == []
        assert outcomes(client)[-1] == ("pattern_sort.category", "1", "undo")


class TestOtherAnswers:
    def test_a_duplicate_answer_and_its_undo(self, client):
        from finance import duplicates as dup
        rows = add(client, tx("OSTERIA NOVE", 86.20, day(3)))
        copy, twin = rows[0].fingerprint, "twin-x"
        client.st.add_duplicate(copy, twin)
        r = client.post(f"/api/review/duplicates/{copy}", json={"answer": dup.DIFFERENT})
        assert r.status_code == 200
        assert ledger.get(client.st, f"duplicates:{copy}")["status"] == "rejected"
        assert client.post("/api/transactions/undo", json=r.get_json()["undo"]).status_code == 200
        assert outcomes(client, "duplicates") == [("duplicates", "1", "not_this"), ("duplicates", "1", "undo")]
        assert ledger.get(client.st, f"duplicates:{copy}")["status"] == "proposed"

    def test_a_recurring_transfer_yes_not_this_one_and_stop(self, tmp_path):
        from test_recurring_transfers import asked, rent
        from app import create_app
        app = create_app(str(tmp_path / "rt.db"))
        app.config.update(TESTING=True)
        with app.test_client() as c:
            c.st = app.config["STORE"]
            ids_ = rent(c)
            [it] = asked(c)
            c.post("/api/recurring-transfers", json={"key": it["key"], "kind": "saved"})
            assert c.post(f"/api/transactions/{ids_['SEND E-TFR ***R1k']}/not-recurring").status_code == 200
            did = f"recurring_transfers:{it['key']}"
            # One row is not the rule: still confirmed.
            assert ledger.get(c.st, did)["status"] == "confirmed"
            assert c.delete(f"/api/recurring-transfers/{it['key']}").status_code == 200
            assert ledger.get(c.st, did)["status"] == "undone"
            assert outcomes(c) == [("recurring_transfers", "1", "yes"),
                                   ("recurring_transfers", "1", "not_this"),
                                   ("recurring_transfers", "1", "stop")]

    def test_outcomes_are_bookkeeping_not_a_change(self, client):
        add(client, tx("OSTERIA NOVE", 86.20, day(3)))
        v = client.st.version()
        signals.outcome(client.st, "trips", "2026-10-01:2026-10-05", "trip", "skip")
        assert client.st.version() == v
        with pytest.raises(ValueError):
            signals.outcome(client.st, "trips", "k", "trip", "maybe")


class TestSummary:
    def test_precision_undo_rate_and_volume(self, client):
        st = client.st
        for k in range(4):
            signals.outcome(st, "trips", f"t{k}", "trip", "yes")
        signals.outcome(st, "trips", "t9", "trip", "not_this")
        signals.outcome(st, "trips", "t8", "trip", "skip")
        signals.outcome(st, "trips", "t0", "trip", "undo")
        (row,) = signals.summary(st)["detectors"]
        assert row["detector"] == "trips" and row["version"] == "1"
        assert row["yes"] == 4 and row["not_this"] == 1 and row["skip"] == 1
        assert row["precision"] == 0.8 and row["undo_rate"] == 0.25
        assert row["detections"] == 6 and row["answered"] == 7

    def test_empty(self, client):
        assert signals.summary(client.st) == {"detectors": [], "answered": 0, "applied": 0}


class TestStartOver:
    def test_detections_go_with_her_answers(self, client):
        signals.outcome(client.st, "trips", "k", "trip", "yes")
        client.st.start_over()
        assert ledger.rows(client.st) == [] and ledger.outcomes(client.st) == []
        assert signals.summary(client.st)["detectors"] == []


def test_no_model_here():
    """Python detects (THL-310): nothing in signals imports a model SDK."""
    root = os.path.join(os.path.dirname(__file__), "..", "finance", "signals")
    for name in os.listdir(root):
        if name.endswith(".py"):
            with open(os.path.join(root, name), encoding="utf-8") as fh:
                text = fh.read()
            assert "anthropic" not in text and "finance.ai" not in text and "from ..ai" not in text, name
