"""JOINT-A, JOINT-B and SPLIT-C (product owner, 2026-11-09; Jira pending).

JOINT-A: "Shared with" picks people from her splits (GET /api/people/recent)
and contacts (on the phone only); the last person can go (decision 5).

JOINT-B: Split my part on a joint-account purchase. The joint share comes
off first, then her part is split: $100.00 at 50/50 three ways is You
$16.68, Priya $16.66, Jo $16.66 (handoff note 1110:6520's tests).

SPLIT-C: Not sure yet, a split with people and no amounts. Each payback
comes off what it costs her; Settle up and That's everything (S-45, S-46).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.analytics import spend_amount
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest
from ledger_files import set_plan

TODAY = date.today()


def day(n: int) -> str:
    """n days ago, kept inside this month so Allowance sees every row."""
    return max(TODAY - timedelta(days=n), TODAY.replace(day=1)).isoformat()


def tx(desc, amount, account="chq", when=None, merchant=None, category=""):
    return Transaction(date=when or day(3), description=desc, merchant=merchant or desc, amount=amount,
                       category=category, account_id=account, account_name=account,
                       raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "joint_unsure.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        set_plan(c, income=5200, savings=900)
        c.st = app.config["STORE"]
        yield c


def add(c, *rows, account="chq"):
    ingest(c.st, IngestResult(list(rows), account))
    return {t.description: t.fingerprint for t in c.st.all_transactions()}


def detail(c, tid):
    r = c.get(f"/api/transactions/{tid}")
    assert r.status_code == 200
    return r.get_json()


def people(c, tid):
    return {p["name"]: p for p in detail(c, tid)["splitting"]["people"]}


def adds_up(c, tid):
    """THL-181: Paid back + Owes = each share, on every set split."""
    for p in people(c, tid).values():
        assert round(min(p["paid"], p["amount"]) + p["owes"], 2) == round(p["amount"], 2), p


def counted(c, tid) -> float:
    """What Allowance and spending count for this purchase."""
    return round(spend_amount(c.st.get_transaction(tid)), 2)


def spent(c) -> float:
    """Home's "already spent" this month (Allowance's row)."""
    rows = c.get("/api/home").get_json()["safe_to_spend"]["rows"]
    return round(next(r["amount"] for r in rows if r["key"] == "spent"), 2)


def undo(c, reply):
    r = c.post("/api/transactions/undo", json=reply["undo"])
    assert r.status_code == 200, r.get_json()


def put_split(c, tid, body, ok=True):
    r = c.put(f"/api/transactions/{tid}/split", json=body)
    assert (r.status_code == 200) is ok, r.get_json()
    return r.get_json()


def link(c, charge, inflow, person=None, amount=None, ok=True):
    body = {}
    if person:
        body["person"] = person
    if amount is not None:
        body["amount"] = amount
    r = c.post(f"/api/transactions/{charge}/paybacks/{inflow}", json=body)
    assert (r.status_code == 200) is ok, r.get_json()
    return r.get_json()


# ── JOINT-B: Split my part ──────────────────────────────────────────────

def joint_dinner(c, share=50, more=()):
    """Pizza Nova, $100.00, on a joint account with Sam Lee at `share`%."""
    i = add(c, tx("PIZZA NOVA", 100.0, account="fam", category="Dining"), *more, account="fam")
    c.put("/api/accounts/fam/joint", json={"label": "Joint"})
    r = c.put("/api/accounts/fam/settings", json={"joint_people": ["Sam Lee"]})
    assert r.status_code == 200, r.get_json()
    r = c.put("/api/accounts/fam/settings", json={"joint_share": share if share is not None else "auto"})
    assert r.status_code == 200, r.get_json()
    return i


def three_ways(c, tid):
    return put_split(c, tid, {"mode": "even", "people": [{"name": "Priya"}, {"name": "Jo"}]})


class TestSplitMyPart:
    def test_her_part_is_split_three_ways_with_the_odd_cent(self, client):
        i = joint_dinner(client)
        pn = i["PIZZA NOVA"]
        before = spent(client)
        assert counted(client, pn) == 50.0
        three_ways(client, pn)
        ps = people(client, pn)
        assert ps["Priya"]["amount"] == 16.66 and ps["Jo"]["amount"] == 16.66
        s = detail(client, pn)["splitting"]
        assert s["you"] == 16.68 and s["base"] == 50.0
        assert s["joint"]["people"] == ["Sam Lee"] and s["joint"]["theirs"] == 50.0
        # Rule A (TEST-03): her part counts in full until Priya and Jo pay.
        assert counted(client, pn) == 50.0
        assert round(before - spent(client), 2) == 0.0
        adds_up(client, pn)

    def test_a_joint_holder_is_refused_by_name(self, client):
        pn = joint_dinner(client)["PIZZA NOVA"]
        r = put_split(client, pn, {"mode": "even", "people": [{"name": "Sam"}]}, ok=False)
        assert r["error"] == "Sam Lee’s part is already off."

    def test_none_of_it_hers_leaves_nothing_to_split(self, client):
        pn = joint_dinner(client)["PIZZA NOVA"]
        client.put(f"/api/transactions/{pn}/share", json={"my_share": 0})
        r = put_split(client, pn, {"mode": "even", "people": [{"name": "Priya"}]}, ok=False)
        assert r["error"] == "None of it is yours to split."

    def test_all_mine_unless_i_mark_it_splits_the_whole_purchase(self, client):
        pn = joint_dinner(client, share=None)["PIZZA NOVA"]
        three_ways(client, pn)
        s = detail(client, pn)["splitting"]
        assert s["base"] == 100.0 and s["you"] == 33.34

    def test_her_whose_was_it_answer_is_her_part(self, client):
        pn = joint_dinner(client)["PIZZA NOVA"]
        client.put(f"/api/transactions/{pn}/share", json={"my_share": 30, "always": False})
        three_ways(client, pn)
        assert detail(client, pn)["splitting"]["base"] == 30.0
        assert counted(client, pn) == 30.0

    def test_whose_was_it_changed_after_splitting_rescales(self, client):
        pn = joint_dinner(client)["PIZZA NOVA"]
        three_ways(client, pn)
        r = client.put(f"/api/transactions/{pn}/share", json={"my_share": 60, "always": False}).get_json()
        assert r["ok"] and counted(client, pn) == 60.0
        assert {p["amount"] for p in people(client, pn).values()} == {20.0}
        undo(client, r)
        assert counted(client, pn) == 50.0

    def test_paybacks_link_and_unlink_and_add_up(self, client):
        i = joint_dinner(client, more=[tx("E-TRANSFER FROM JO", -16.66, account="fam", merchant="Jo",
                                         when=day(1))])
        pn, jo = i["PIZZA NOVA"], i["E-TRANSFER FROM JO"]
        three_ways(client, pn)
        r = link(client, pn, jo, "Jo")
        assert people(client, pn)["Jo"]["owes"] == 0.0
        adds_up(client, pn)
        assert counted(client, pn) == 33.34
        undo(client, r)
        assert people(client, pn)["Jo"]["owes"] == 16.66


class TestShareChanges:
    def setup_paid(self, c):
        i = joint_dinner(c, more=[tx("E-TRANSFER FROM JO", -16.66, account="fam", merchant="Jo",
                                    when=day(1))])
        pn = i["PIZZA NOVA"]
        three_ways(c, pn)
        link(c, pn, i["E-TRANSFER FROM JO"], "Jo")
        return pn

    def test_50_to_60_asks_first_then_jo_owes_3_34(self, client):
        pn = self.setup_paid(client)
        r = client.put("/api/accounts/fam/settings", json={"joint_share": 60}).get_json()
        assert r["needs_confirm"] is True
        change = r["changes"][0]
        assert change["part_was"] == 50.0 and change["part_now"] == 60.0
        jo = next(p for p in change["people"] if p["name"] == "Jo")
        assert jo["paid"] == 16.66 and jo["share_now"] == 20.0
        # Nothing changed while it asked.
        assert client.st.joint_shares()["fam"] == 50.0 and counted(client, pn) == 33.34
        r = client.put("/api/accounts/fam/settings", json={"joint_share": 60, "confirm": True}).get_json()
        assert r["ok"]
        assert people(client, pn)["Jo"]["owes"] == 3.34
        assert counted(client, pn) == 43.34
        adds_up(client, pn)
        undo(client, r)
        assert client.st.joint_shares()["fam"] == 50.0
        assert people(client, pn)["Jo"]["amount"] == 16.66 and counted(client, pn) == 33.34

    def test_nobody_paid_changes_without_asking(self, client):
        pn = joint_dinner(client)["PIZZA NOVA"]
        three_ways(client, pn)
        r = client.put("/api/accounts/fam/settings", json={"joint_share": 60}).get_json()
        assert r["ok"] and "needs_confirm" not in r
        assert counted(client, pn) == 60.0

    def test_typed_amounts_stay_and_her_share_takes_the_rest(self, client):
        pn = joint_dinner(client)["PIZZA NOVA"]
        put_split(client, pn, {"mode": "amount", "people": [{"name": "Priya", "amount": 10},
                                                           {"name": "Jo", "amount": 10}], "you": 30})
        client.put("/api/accounts/fam/settings", json={"joint_share": 60})
        assert {p["amount"] for p in people(client, pn).values()} == {10.0}
        assert counted(client, pn) == 60.0

    def test_typed_amounts_over_her_new_part_are_refused(self, client):
        pn = joint_dinner(client)["PIZZA NOVA"]
        put_split(client, pn, {"mode": "amount", "people": [{"name": "Priya", "amount": 30},
                                                           {"name": "Jo", "amount": 15}], "you": 5})
        r = client.put("/api/accounts/fam/settings", json={"joint_share": 40})
        assert r.status_code == 400
        assert r.get_json()["error"] == "That’s more than your part now. Change the split first."
        assert client.st.joint_shares()["fam"] == 50.0

    def test_starting_today_changes_nothing_earlier(self, client):
        pn = joint_dinner(client)["PIZZA NOVA"]
        three_ways(client, pn)
        r = client.put("/api/accounts/fam/settings", json={"joint_share": 60, "apply": "from_today"}).get_json()
        assert r["ok"] and "needs_confirm" not in r
        assert counted(client, pn) == 50.0


class TestRemoveAndNotJoint:
    def test_remove_the_split_puts_her_part_back_and_paybacks_to_sort(self, client):
        i = joint_dinner(client, more=[tx("E-TRANSFER FROM JO", -16.66, account="fam", merchant="Jo",
                                         when=day(1))])
        pn, jo = i["PIZZA NOVA"], i["E-TRANSFER FROM JO"]
        three_ways(client, pn)
        link(client, pn, jo, "Jo")
        r = client.delete(f"/api/transactions/{pn}/split")
        assert r.status_code == 200
        reply = r.get_json()
        assert reply["toast"] == "Split removed"
        assert counted(client, pn) == 50.0
        assert client.st.get_transaction(jo).repays is None
        undo(client, reply)
        assert counted(client, pn) == 33.34
        assert client.st.get_transaction(jo).repays == pn
        assert people(client, pn)["Jo"]["owes"] == 0.0

    def test_remove_keeps_her_whose_was_it_answer(self, client):
        pn = joint_dinner(client)["PIZZA NOVA"]
        client.put(f"/api/transactions/{pn}/share", json={"my_share": 30, "always": False})
        three_ways(client, pn)
        client.delete(f"/api/transactions/{pn}/split")
        assert counted(client, pn) == 30.0

    def test_not_joint_any_more_keeps_the_splits(self, client):
        pn = joint_dinner(client)["PIZZA NOVA"]
        three_ways(client, pn)
        r = client.put("/api/accounts/fam/settings", json={"joint_share": None}).get_json()
        assert r["needs_confirm"] is True and r["not_joint"] is True
        assert r["changes"][0]["yours_now"] == 66.68
        r = client.put("/api/accounts/fam/settings", json={"joint_share": None, "confirm": True}).get_json()
        assert r["ok"]
        ps = people(client, pn)
        assert ps["Priya"]["amount"] == 16.66 and ps["Jo"]["amount"] == 16.66
        assert counted(client, pn) == 100.0
        assert "fam" not in client.st.joint_accounts()
        undo(client, r)
        assert client.st.joint_shares()["fam"] == 50.0
        assert client.st.joint_people()["fam"] == ["Sam Lee"]
        assert counted(client, pn) == 50.0


# ── JOINT-A: Shared with ────────────────────────────────────────────────

class TestSharedWith:
    def test_people_she_split_with_newest_first_and_once(self, client):
        i = add(client, tx("LOBLAWS", 60.0, when=day(9)), tx("PIZZA NOVA", 40.0, when=day(2)),
                tx("CINEPLEX", 30.0, when=day(5)))
        put_split(client, i["LOBLAWS"], {"mode": "even", "people": [{"name": "Sam"}, {"name": "Priya"}]})
        put_split(client, i["PIZZA NOVA"], {"mode": "even", "people": [{"name": "Sam Lee"}]})
        put_split(client, i["CINEPLEX"], {"mode": "even", "people": [{"name": "Jo"}]})
        got = client.get("/api/people/recent").get_json()["people"]
        assert [p["name"] for p in got] == ["Sam Lee", "Jo", "Priya"]
        assert got[0]["merchant"] == "PIZZA NOVA"

    def test_split_my_part_hides_the_joint_holders(self, client):
        i = joint_dinner(client, more=[tx("LOBLAWS", 60.0, account="fam")])
        client.put("/api/accounts/fam/settings", json={"joint_share": "auto"})
        put_split(client, i["LOBLAWS"], {"mode": "even", "people": [{"name": "Priya"}]})
        # Sam Lee on another of her splits, off the joint account.
        j = add(client, tx("CINEPLEX", 30.0))
        put_split(client, j["CINEPLEX"], {"mode": "even", "people": [{"name": "Sam"}]})
        got = client.get(f"/api/people/recent?txn={i['PIZZA NOVA']}").get_json()
        assert [p["name"] for p in got["people"]] == ["Priya"] or [p["name"] for p in got["people"]] == ["Priya"]
        assert got["hidden"] == ["Sam Lee"]

    def test_the_last_person_can_go_and_it_stays_joint(self, client):
        joint_dinner(client)
        r = client.put("/api/accounts/fam/settings", json={"joint_people": []})
        assert r.status_code == 200
        assert client.st.joint_people()["fam"] == []
        assert client.st.joint_shares()["fam"] == 50.0
        undo(client, r.get_json())
        assert client.st.joint_people()["fam"] == ["Sam Lee"]

    def test_removing_someone_has_undo(self, client):
        joint_dinner(client)
        client.put("/api/accounts/fam/settings", json={"joint_people": ["Sam Lee", "Maya Reyes"]})
        r = client.put("/api/accounts/fam/settings", json={"joint_people": ["Sam Lee"]}).get_json()
        assert client.st.joint_people()["fam"] == ["Sam Lee"]
        undo(client, r)
        assert client.st.joint_people()["fam"] == ["Sam Lee", "Maya Reyes"]


# ── SPLIT-C: Not sure yet ───────────────────────────────────────────────

def unsure_dinner(c, more=()):
    i = add(c, tx("PIZZA NOVA", 100.0, when=day(10), category="Dining"), *more)
    put_split(c, i["PIZZA NOVA"], {"mode": "unknown", "people": [{"name": "Sam"}, {"name": "Priya"}]})
    return i


def sam_paid(c, amount=20.0, when=None):
    return tx("E-TRANSFER FROM SAM", -amount, merchant="Sam", when=when or day(4))


class TestNotSureYet:
    def test_people_no_amounts_all_hers_until_paid(self, client):
        before = spent(client)
        pn = unsure_dinner(client)["PIZZA NOVA"]
        s = detail(client, pn)["splitting"]
        assert s["mode"] == "unknown" and s["still"] == 100.0
        assert all(p["owes"] == 0.0 for p in s["people"])
        assert counted(client, pn) == 100.0
        assert round(spent(client) - before, 2) == 100.0

    def test_it_needs_someone(self, client):
        i = add(client, tx("PIZZA NOVA", 100.0))
        r = put_split(client, i["PIZZA NOVA"], {"mode": "unknown", "people": []}, ok=False)
        assert r["error"] == "Add someone to split it with."

    def test_a_payback_comes_off_what_it_costs_her(self, client):
        i = unsure_dinner(client, more=[sam_paid(client)])
        pn = i["PIZZA NOVA"]
        r = link(client, pn, i["E-TRANSFER FROM SAM"], "Sam")
        s = detail(client, pn)["splitting"]
        assert s["still"] == 80.0 and counted(client, pn) == 80.0
        sam = people(client, pn)["Sam"]
        assert sam["paid"] == 20.0 and sam["owes"] == 0.0 and sam["over"] == 0.0
        undo(client, r)
        assert counted(client, pn) == 100.0

    def test_cash_any_amount_comes_off_too(self, client):
        pn = unsure_dinner(client)["PIZZA NOVA"]
        r = client.post(f"/api/transactions/{pn}/split/cash", json={"name": "Priya", "amount": 15})
        assert r.status_code == 201, r.get_json()
        assert counted(client, pn) == 85.0
        undo(client, r.get_json())
        assert counted(client, pn) == 100.0

    def test_paid_never_more_than_the_purchase(self, client):
        """Σ paid ≤ amount: a payback is capped at what it still costs her
        (decision 2); the rest of the deposit is sorted another way."""
        i = unsure_dinner(client, more=[sam_paid(client), tx("E-TRANSFER FROM PRIYA", -120.0,
                                                               merchant="Priya", when=day(3))])
        pn, pr = i["PIZZA NOVA"], i["E-TRANSFER FROM PRIYA"]
        link(client, pn, i["E-TRANSFER FROM SAM"], "Sam")
        r = link(client, pn, pr, "Priya", ok=False)
        assert r["error"].startswith("Only $80.00 of PIZZA NOVA still counts as yours")
        # S-09u2: $80.00 to Pizza Nova, the other $40.00 left to sort.
        r = client.post(f"/api/transactions/{pr}/parts",
                        json={"parts": [{"kind": "payback", "charge": pn, "amount": 80, "person": "Priya"}],
                              "later": True})
        assert r.status_code == 200, r.get_json()
        assert counted(client, pn) == 0.0
        s = detail(client, pn)["splitting"]
        assert round(sum(p["paid"] for p in s["people"]), 2) <= 100.0
        r = client.post(f"/api/transactions/{pr}/parts",
                        json={"parts": [{"kind": "payback", "charge": pn, "amount": 90, "person": "Priya"}],
                              "later": True, "replace": True})
        assert r.status_code == 400

    def test_a_payback_with_no_name_is_asked_about(self, client):
        i = unsure_dinner(client, more=[tx("INTERAC E-TRANSFER", -25.0, when=day(2), merchant="Interac")])
        pn, it = i["PIZZA NOVA"], i["INTERAC E-TRANSFER"]
        link(client, pn, it)
        assert detail(client, pn)["splitting"]["uncredited"][0]["id"] == it
        q = client.get(f"/api/transactions/{it}/credit").get_json()["question"]
        assert {s["person"] for s in q["shares"]} == {"Sam", "Priya"}
        assert all(s.get("unknown") for s in q["shares"])
        r = client.post(f"/api/transactions/{it}/credit", json={"person": "Priya"}).get_json()
        assert people(client, pn)["Priya"]["paid"] == 25.0
        undo(client, r)
        assert people(client, pn)["Priya"]["paid"] == 0.0

    def test_owed_to_you_lists_it_not_settled_without_an_amount(self, client):
        i = unsure_dinner(client, more=[sam_paid(client), tx("LOBLAWS", 60.0)])
        link(client, i["PIZZA NOVA"], i["E-TRANSFER FROM SAM"], "Sam")
        put_split(client, i["LOBLAWS"], {"mode": "even", "people": [{"name": "Sam"}]})
        owed = client.get("/api/owed").get_json()
        assert owed["total"] == 30.0
        assert [r["name"] for r in owed["owes_you"]] == ["Sam"]
        ns = owed["not_settled"]
        assert len(ns) == 1 and ns[0]["merchant"] == "PIZZA NOVA" and ns[0]["paid"] == 20.0
        assert ns[0]["people"] == ["Sam", "Priya"]

    def test_it_is_offered_for_the_senders_money_in(self, client):
        i = unsure_dinner(client, more=[sam_paid(client)])
        got = detail(client, i["E-TRANSFER FROM SAM"])["repayment"]
        assert got["suggestion"]["charge_id"] == i["PIZZA NOVA"] and got["suggestion"]["unknown"] is True
        assert got["splits"][0]["unknown"] is True and got["from_sender"] is True
        owing = client.get(f"/api/transactions/{i['E-TRANSFER FROM SAM']}/owing").get_json()
        assert owing["items"][0]["unknown"] is True and owing["items"][0]["owes"] == 100.0


class TestSettleUp:
    def test_use_what_each_paid(self, client):
        i = unsure_dinner(client, more=[sam_paid(client)])
        pn = i["PIZZA NOVA"]
        link(client, pn, i["E-TRANSFER FROM SAM"], "Sam")
        before = spent(client)
        r = put_split(client, pn, {"mode": "amount", "you": 80,
                                   "people": [{"name": "Sam", "amount": 20}, {"name": "Priya", "amount": 0}]})
        ps = people(client, pn)
        assert ps["Sam"]["owes"] == 0.0 and ps["Sam"]["paid"] == 20.0
        # Decision 3: someone who paid nothing stays, at $0.00, owing nothing.
        assert ps["Priya"]["amount"] == 0.0 and ps["Priya"]["owes"] == 0.0
        assert counted(client, pn) == 80.0 and spent(client) == before
        adds_up(client, pn)
        undo(client, r)
        s = detail(client, pn)["splitting"]
        assert s["mode"] == "unknown" and people(client, pn)["Sam"]["paid"] == 20.0

    def test_type_amounts_follow_the_save_rules(self, client):
        pn = unsure_dinner(client)["PIZZA NOVA"]
        r = put_split(client, pn, {"mode": "amount", "include_me": False,
                                   "people": [{"name": "Sam", "amount": 30}, {"name": "Priya", "amount": 30}]},
                      ok=False)
        assert r["error"] == "$40.00 left to assign."
        put_split(client, pn, {"mode": "even", "people": [{"name": "Sam"}, {"name": "Priya"}]})
        assert counted(client, pn) == 100.0
        adds_up(client, pn)

    def test_a_payer_is_locked_at_what_they_paid(self, client):
        """THL-303 (TEST-18, product owner 2026-11-10): settling can't set a
        share below or above what someone paid; that replaces S-45e's extra
        step when settling. Unlink first to change it."""
        i = unsure_dinner(client, more=[sam_paid(client)])
        pn = i["PIZZA NOVA"]
        link(client, pn, i["E-TRANSFER FROM SAM"], "Sam")
        for sam in (10, 30):
            r = put_split(client, pn, {"mode": "amount", "you": 50,
                                       "people": [{"name": "Sam", "amount": sam},
                                                  {"name": "Priya", "amount": 50 - sam}],
                                       "extra": {"Sam": [{"kind": "gift", "amount": 10}]}}, ok=False)
            assert r["error"] == "Sam’s $20.00 is linked. Unlink the payback to change Sam’s share."
        assert detail(client, pn)["splitting"]["mode"] == "unknown"
        r = put_split(client, pn, {"mode": "amount", "you": 50,
                                   "people": [{"name": "Sam", "amount": 20}, {"name": "Priya", "amount": 30}]})
        assert people(client, pn)["Sam"]["owes"] == 0.0 and people(client, pn)["Priya"]["owes"] == 30.0


class TestThatsEverything:
    def test_close_keeps_the_rest_hers_and_undo_reopens(self, client):
        i = unsure_dinner(client, more=[sam_paid(client)])
        pn = i["PIZZA NOVA"]
        link(client, pn, i["E-TRANSFER FROM SAM"], "Sam")
        before = spent(client)
        r = client.post(f"/api/transactions/{pn}/split/close")
        assert r.status_code == 200
        reply = r.get_json()
        assert reply["toast"] == "Split closed"
        s = detail(client, pn)["splitting"]
        assert s["closed_at"] and all(p["owes"] == 0.0 for p in s["people"])
        assert counted(client, pn) == 80.0 and spent(client) == before
        assert client.get("/api/owed").get_json()["not_settled"] == []
        undo(client, reply)
        assert detail(client, pn)["splitting"]["closed_at"] is None
        assert len(client.get("/api/owed").get_json()["not_settled"]) == 1

    def test_reopen(self, client):
        pn = unsure_dinner(client)["PIZZA NOVA"]
        client.post(f"/api/transactions/{pn}/split/close")
        r = client.delete(f"/api/transactions/{pn}/split/close")
        assert r.status_code == 200 and detail(client, pn)["splitting"]["closed_at"] is None
        undo(client, r.get_json())
        assert detail(client, pn)["splitting"]["closed_at"]

    def test_only_not_sure_yet_closes(self, client):
        i = add(client, tx("LOBLAWS", 60.0))
        put_split(client, i["LOBLAWS"], {"mode": "even", "people": [{"name": "Sam"}]})
        assert client.post(f"/api/transactions/{i['LOBLAWS']}/split/close").status_code == 400

    def test_closed_isnt_suggested_and_a_link_reopens_it_with_undo(self, client):
        i = unsure_dinner(client, more=[sam_paid(client)])
        pn, sam = i["PIZZA NOVA"], i["E-TRANSFER FROM SAM"]
        client.post(f"/api/transactions/{pn}/split/close")
        rep = detail(client, sam)["repayment"]
        assert rep["suggestion"] is None and all(s["charge_id"] != pn for s in rep["splits"])
        r = link(client, pn, sam, "Sam")
        assert r["toast"].endswith("PIZZA NOVA is open again")
        assert detail(client, pn)["splitting"]["closed_at"] is None
        undo(client, r)
        assert detail(client, pn)["splitting"]["closed_at"]
        assert client.st.get_transaction(sam).repays is None


class TestNotSureYetOnSplitMyPart:
    def test_her_part_less_paybacks(self, client):
        """Decision 7: Not sure yet in JOINT-B's Split my part."""
        i = joint_dinner(client, more=[tx("E-TRANSFER FROM PRIYA", -20.0, account="fam", merchant="Priya",
                                         when=day(1))])
        pn = i["PIZZA NOVA"]
        put_split(client, pn, {"mode": "unknown", "people": [{"name": "Priya"}]})
        assert detail(client, pn)["splitting"]["still"] == 50.0 and counted(client, pn) == 50.0
        link(client, pn, i["E-TRANSFER FROM PRIYA"], "Priya")
        assert counted(client, pn) == 30.0
        r = link(client, pn, i["E-TRANSFER FROM PRIYA"], "Priya", amount=20)
        assert r["toast"] == "Priya paid back $20.00"

    def test_quick_sort_holds_a_not_sure_yet_split(self, client):
        """Decision 7 (SPLIT-20): the card's Yes saves the held split."""
        i = add(client, tx("PIZZA NOVA", 100.0, category="Other"))
        pn = i["PIZZA NOVA"]
        put_split(client, pn, {"mode": "unknown", "people": [{"name": "Sam"}], "category": "Dining",
                               "settle": True})
        t = client.st.get_transaction(pn)
        assert t.category == "Dining" and t.split_mode == "unknown"


# ── The iPhone app (JOINT-A, JOINT-B, SPLIT-C) ──────────────────────────

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


def src(path: str) -> str:
    return (ROOT / path).read_text()


class TestTheApp:
    """Pearl views only (no stock dialogs), the words the designs use, and
    contacts asked for with the handoff's reason (note 1110:6520)."""

    NEW = ("ios/Pearl/Views/Transactions/JointSplitViews.swift",
           "ios/Pearl/Views/Transactions/SplitFlow.swift",
           "ios/Pearl/Views/Transactions/SplitMenus.swift")

    def test_no_stock_dialogs(self):
        for path in self.NEW:
            for stock in (".confirmationDialog(", ".alert(", ".actionSheet(", "ActionSheet("):
                assert stock not in src(path), (path, stock)
        joint = src("ios/Pearl/Views/Profile/JointMergeViews.swift")
        page = joint[joint.index("struct JointAccountView"):joint.index("// MARK: - AM-09")]
        assert ".alert(" not in page and ".confirmationDialog(" not in page

    def test_contacts_reason(self):
        plist = src("ios/Pearl/Info.plist")
        # REFRESH-03 (AM-08p1).
        assert "To pick people faster. Pearl keeps only the name." in plist

    def test_not_sure_is_the_fifth_method(self):
        split = src("ios/Pearl/Views/Transactions/SplitFlow.swift")
        assert '("unknown", "Not sure")' in split and "Not sure yet" in split
        assert "Any amount they send you" in split and "Save split" in split

    def test_split_my_part_words(self):
        detail = src("ios/Pearl/Views/Transactions/TransactionDetailView.swift")
        assert "Split my part" in detail and "Split with others" in detail
        assert "None of it is yours to split." in detail
        views = src("ios/Pearl/Views/Transactions/JointSplitViews.swift")
        for words in ("Remove the split?", "Keep the split", "Not a joint account?", "Keep it joint",
                      "How to settle?", "Use what each paid?", "That’s everything?", "Keep it open",
                      "Nothing to pay", "Contacts are off for Pearl", "Turn on in Settings", "Type a name"):
            assert words in views, words

    def test_allowance_never_safe_to_spend(self):
        for path in self.NEW + ("ios/Pearl/Views/Profile/JointMergeViews.swift",):
            assert "safe to spend" not in src(path).lower(), path
