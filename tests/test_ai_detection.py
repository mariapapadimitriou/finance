"""AI Phase 4, part 1: the detection upgrades (THL-309). Python only, no
model calls, and every detection still waits for her answer.

* WL-20 (AI4-PriceRise): a price rise with Got it / Not this and its sheet.
* WL-21 (AI4-Forgotten): a subscription she never answered, six months on,
  with Keep / Not mine anymore; a charge after Not mine anymore is asked
  about in Needs a look.
* TR-30 (AI4-Pair): one Quick sort card for two rows that are very likely
  the same money moving; a friend's e-Transfer never pairs.
* TR-20 (AI4-PastTrips): past trips after the rest, three a day, labelled.
"""

import json
import os
from datetime import date

import pytest

from finance import pair_asks, trips as tr
from finance.models import Transaction
from finance.signals import ledger
from test_worth_a_look import TODAY, client, crave, items, netflix, post, tx  # noqa: F401

FIXTURES = os.path.join(os.path.dirname(__file__), "eval", "fixtures")


def outcomes(c, detector):
    return [o["outcome"] for o in ledger.outcomes(c.st, detector)]


# ── WL-20 · a price rise ─────────────────────────────────────────────────

class TestPriceRise:
    def test_the_sheet_says_what_changed(self, client):
        netflix(client)
        [it] = items(client)
        assert it["sheet"] == {"title": "Netflix went up", "over": "Netflix · a month", "big": "$17.00",
                               "line": "Was $15.00 · $24 more a year", "now": 17.0, "before": 15.0}

    def test_got_it_is_recorded_against_the_detector(self, client):
        netflix(client)
        post(client, "yes", ["price_rise:Netflix:1700"])
        assert outcomes(client, "recurring.price_rise") == ["yes"]
        post(client, "undo_yes", ["price_rise:Netflix:1700"])
        assert outcomes(client, "recurring.price_rise") == ["yes", "undo"]

    def test_not_this_keeps_the_bill_and_the_item_goes(self, client):
        netflix(client)
        r = post(client, "no", ["price_rise:Netflix:1700"])
        assert r["items"] == [] and r.get("toast") is None
        bill = next(b for b in client.get("/api/income-bills").get_json()["bills"] if b["key"] == "Netflix")
        assert bill["amount"] == 15.0
        assert outcomes(client, "recurring.price_rise") == ["not_this"]

    def test_no_is_only_for_these_two(self, client):
        crave(client)
        [it] = items(client)
        post(client, "no", [it["id"]], status=400)


# ── WL-21 · a forgotten subscription ────────────────────────────────────

class TestForgotten:
    def test_a_subscription_she_never_answered_six_months_on(self, client):
        crave(client, since="2026-04-20")
        [it] = items(client)
        assert it["id"] == "forgotten:Crave" and it["kind"] == "forgotten"
        assert it["title"] == "Still using Crave?" and it["sub"] == "$19.99 a month for 7 months."
        assert (it["yes"], it["no"], it["amount"]) == ("Keep", "Not mine anymore", "$19.99/mo")
        assert it["sheet"]["over"] == "Crave · since April" and it["sheet"]["big"] == "$139.93"
        assert it["sheet"]["line"].startswith("7 payments of $19.99 · next on Nov 20")
        assert it["sheet"]["note"] == "To stop it, cancel with Crave. Pearl can’t cancel for you."

    def test_not_yet_at_five_months(self, client):
        crave(client, since="2026-07-20")
        assert [i["kind"] for i in items(client)] != ["forgotten"]

    def test_one_she_answered_is_not_forgotten(self, client):
        crave(client, since="2026-04-20")
        client.put("/api/income-bills/bills", json={"ticked": {"Crave": True}})
        assert [i for i in items(client) if i["kind"] == "forgotten"] == []

    def test_one_at_a_time(self, client):
        crave(client, since="2026-04-20")
        rows = [tx(f"2026-{m:02d}-08", "Spotify", 11.99, "Streaming", account="visa") for m in range(3, 12)]
        client.st.add_transactions(rows)
        assert [i["id"] for i in items(client) if i["kind"] == "forgotten"] == ["forgotten:Crave"]

    def test_keep_counts_the_bill(self, client):
        crave(client, since="2026-04-20")
        r = post(client, "yes", ["forgotten:Crave"])
        assert r["toast"] == "Keeping Crave"
        assert [i for i in r["items"] if i["kind"] == "forgotten"] == []
        bill = next(b for b in client.get("/api/income-bills").get_json()["bills"] if b["key"] == "Crave")
        assert bill["counts"] is True
        assert outcomes(client, "recurring.forgotten") == ["not_this"]

    def test_not_mine_anymore_stops_the_bill_with_undo(self, client):
        crave(client, since="2026-04-20")
        r = post(client, "no", ["forgotten:Crave"])
        assert r["toast"] == "Crave marked as not yours anymore." and r["items"] == []
        bill = next(b for b in client.get("/api/income-bills").get_json()["bills"] if b["key"] == "Crave")
        assert bill["counts"] is False
        assert outcomes(client, "recurring.forgotten") == ["yes"]
        r = post(client, "undo_no", ["forgotten:Crave"])
        assert [i["id"] for i in r["items"]] == ["forgotten:Crave"]
        bill = next(b for b in client.get("/api/income-bills").get_json()["bills"] if b["key"] == "Crave")
        assert bill["counts"] is None
        assert outcomes(client, "recurring.forgotten") == ["yes", "undo"]

    def test_a_charge_after_not_mine_anymore_is_asked_about(self, client):
        crave(client, since="2026-04-20")
        post(client, "no", ["forgotten:Crave"])
        review = client.get("/api/review").get_json()
        assert not [u for u in review["unsure_category"] if u["txn"]["merchant"] == "Crave"]
        client.st.add_transactions([tx("2026-11-20", "Crave", 19.99, "Streaming", account="visa")])
        review = client.get("/api/review").get_json()
        [u] = [u for u in review["unsure_category"] if u["txn"]["merchant"] == "Crave"]
        assert u["txn"]["date"] == "2026-11-20"
        assert u["reason"] == "It charged again after you said it wasn’t yours anymore."


# ── TR-30 · same money moving? ──────────────────────────────────────────

def _fixture_rows(name):
    """A labelled replay fixture (tests/eval/fixtures)."""
    with open(os.path.join(FIXTURES, name + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


class TestPairs:
    @pytest.fixture
    def st(self, tmp_path):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "eval"))
        from signals_replay import fixture_store
        fx = _fixture_rows("pairs_to_ask")
        st = fixture_store(str(tmp_path), fx)
        st.ref = {(t.raw or {}).get("plaid_id"): t.fingerprint for t in st.all_transactions()}
        return st

    def test_a_friends_etransfer_never_pairs(self, st):
        from finance.transfers import transfer_pairs
        pairs = transfer_pairs(st.all_transactions(), today="2026-11-15")
        ref = st.ref
        assert ref["pal-out"] not in pairs and ref["pal2-out"] not in pairs
        assert ref["pal-in"] not in pairs.values() and ref["pal2-in"] not in pairs.values()

    def test_one_card_per_pair_and_only_sure_ones(self, st):
        ref = st.ref
        found = pair_asks.asks(st, st.all_transactions(), "2026-11-15")
        got = {(p["out"], p["in"]): (p["kind"], p["reason"]) for p in found}
        assert got == {(ref["card-out"], ref["card-in"]): ("card_payment", "Same amount, 6 days apart."),
                       (ref["eft-out"], ref["eft-in"]): ("transfer_pair", "Same amount, 4 days apart.")}
        [card] = [p for p in found if p["out"] == ref["card-out"]]
        assert (card["from_account"], card["to_account"], card["amount"]) == ("Chequing", "Visa", 412.3)

    def test_the_rows_own_questions_fold_into_the_pair(self, st):
        from finance.review import for_store
        ref = st.ref
        review = for_store(st, "2026-11-15")
        assert {p["key"] for p in review["pair_asks"]} == {f"pair:{ref['eft-out']}:{ref['eft-in']}",
                                                            f"pair:{ref['card-out']}:{ref['card-in']}"}
        asked = {t["id"] for t in review["unsorted"]["transfers"]}
        asked |= {it["txn"]["id"] for it in review["money_in"]}
        assert not asked & {ref["eft-out"], ref["eft-in"], ref["card-out"], ref["card-in"]}

    def test_answers_are_recorded_and_not_this_is_for_good(self, st):
        ref = st.ref
        p = pair_asks.lookup(st, ref["eft-out"], ref["eft-in"], "2026-11-15")
        pair_asks.not_this(st, p, "2026-11-15")
        assert pair_asks.lookup(st, ref["eft-out"], ref["eft-in"], "2026-11-15") is None
        assert [o["outcome"] for o in ledger.outcomes(st, "transfers.pair_ask")] == ["not_this"]
        pair_asks.undo(st, ref["eft-out"], ref["eft-in"], "2026-11-15")
        assert pair_asks.lookup(st, ref["eft-out"], ref["eft-in"], "2026-11-15") is not None


def test_yes_on_a_pair_links_them_with_undo(client):
    rows = [Transaction(date="2026-11-02", description="ONLINE BANKING TRANSFER", merchant="", amount=750.0,
                        category="Unsorted transfers", category_source="transfer_match", account_id="chq",
                        account_name="Chequing", raw={"account_type": "depository"}),
            Transaction(date="2026-11-06", description="DEPOSIT", merchant="", amount=-750.0,
                        category="Transfers", account_id="sav", account_name="Savings",
                        raw={"account_type": "depository"})]
    client.st.add_transactions(rows)
    found = pair_asks.asks(client.st, client.st.all_transactions(), TODAY.isoformat())
    assert len(found) == 1
    p = found[0]
    r = client.post(f"/api/quick-sort/pairs/{p['out']}/{p['in']}/yes")
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["undo"]
    linked = {t.fingerprint: t.transfer_link for t in client.st.all_transactions()}
    assert linked[p["out"]] and linked[p["out"]] == linked[p["in"]]
    assert [o["outcome"] for o in ledger.outcomes(client.st, "transfers.pair_ask")] == ["yes"]
    assert client.post(f"/api/quick-sort/pairs/{p['out']}/{p['in']}/maybe").status_code == 400


# ── TR-20 · past trips ──────────────────────────────────────────────────

def _cand(start, end):
    return {"id": f"{start}:{end}", "key": f"trip:{start}:{end}", "start": start, "end": end, "ids": []}


class TestPastTrips:
    def test_recent_first_then_three_past_a_day_labelled(self, tmp_path):
        from finance.store import Store
        st = Store(str(tmp_path / "t.db"), url="")
        today = "2026-11-15"
        cands = [_cand("2026-10-01", "2026-10-05")] + [_cand(f"20{y}-06-01", f"20{y}-06-05")
                                                       for y in (25, 24, 23, 22, 21, 20)]
        got = tr.asks(st, cands, today)
        assert [c["id"] for c in got] == [c["id"] for c in cands[:4]]
        assert got[0].get("past") is None
        assert [c["past"] for c in got[1:]] == [{"n": 1, "of": 6}, {"n": 2, "of": 6}, {"n": 3, "of": 6}]
        tr._count_past(st, cands[1], today)               # one past trip answered today
        got = tr.asks(st, cands[2:], today)
        assert [c["past"] for c in got] == [{"n": 2, "of": 6}, {"n": 3, "of": 6}]
        assert [c["past"]["n"] for c in tr.asks(st, cands[2:], "2026-11-16")] == [1, 2, 3]

    def test_a_recent_trip_is_not_counted(self, tmp_path):
        from finance.store import Store
        st = Store(str(tmp_path / "t.db"), url="")
        tr._count_past(st, _cand("2026-10-01", "2026-10-05"), "2026-11-15")
        assert tr._past_answered(st, "2026-11-15") == 0
