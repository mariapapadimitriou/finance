"""One payback, several purchases (2026-10-28): her little sister pays one
lump sum for months of the gym membership Maria paid for."""

from __future__ import annotations

import sys
from datetime import date, timedelta

sys.path.insert(0, "tests")
from test_what_was_this import client, load, mark, row, undo  # noqa: E402,F401

TODAY = date.today()


def ago(n):
    return (TODAY - timedelta(days=n)).isoformat()


def gym(c, months=3, extra=()):
    rows = [row(50.0, f"GOODLIFE FITNESS {i}", account="cc", kind="credit", when=ago(30 * i + 10),
                merchant="GoodLife Fitness") for i in range(months)]
    for r in rows:
        r.category, r.category_source = "Fitness", "user"
    sent = row(-150.0, "E-TRANSFER RECEIVED ANNA", when=ago(2), who="Anna")
    ids = load(c.st, *rows, sent, *extra)
    return [ids[f"GOODLIFE FITNESS {i}"] for i in range(months)], ids["E-TRANSFER RECEIVED ANNA"]


def by_id(c):
    return {t.fingerprint: t for t in c.st.all_transactions()}


def test_one_lump_sum_pays_back_every_month(client):
    charges, inflow = gym(client)
    res = mark(client, inflow, case="payback", charges=[{"id": c} for c in charges])
    assert res["title"] == "Linked to 3 purchases at GoodLife Fitness. Not income."
    assert res["detail"] == "$150.00 comes off what you spent on them."
    rows = by_id(client)
    t = rows[inflow]
    assert set(t.repays_all) == set(charges) and t.paid_part == 150 and t.unlinked_part == 0
    for cid in charges:
        assert rows[cid].paid_back == 50
        assert abs(rows[cid].my_share or 0) < 0.005            # all hers to pay, all paid
        assert client.st.splits()[cid]["people"] == [{"name": "Anna", "amount": 50.0}]


def test_what_is_left_over_counts_as_money_in(client):
    charges, inflow = gym(client, months=2)
    res = mark(client, inflow, case="payback", charges=[{"id": c} for c in charges])
    assert res["detail"].endswith("The other $50.00 counts as money in, not income.")
    t = by_id(client)[inflow]
    assert t.paid_part == 100 and t.unlinked_part == 50


def test_more_purchases_than_the_money_covers_is_refused(client):
    charges, inflow = gym(client, months=4)
    r = client.post(f"/api/transactions/{inflow}/mark",
                    json={"case": "payback", "charges": [{"id": c} for c in charges]})
    assert r.status_code == 400
    assert "more purchases than the money covers" in r.get_json()["error"]
    assert by_id(client)[inflow].repays is None


def test_amounts_must_fit_the_purchase_and_the_money(client):
    charges, inflow = gym(client)
    r = client.post(f"/api/transactions/{inflow}/mark", json={"case": "payback", "charges": [
        {"id": charges[0], "amount": 60}, {"id": charges[1], "amount": 40}]})
    assert r.status_code == 400 and "only has $50.00 left" in r.get_json()["error"]
    r = client.post(f"/api/transactions/{inflow}/mark", json={"case": "payback", "amount": 80, "charges": [
        {"id": charges[0], "amount": 50}, {"id": charges[1], "amount": 50}]})
    assert r.status_code == 400 and "more than they sent" in r.get_json()["error"]


def test_a_purchase_already_paid_back_cannot_take_more(client):
    charges, inflow = gym(client, extra=[row(-50.0, "E-TRANSFER RECEIVED ANNA EARLY", when=ago(5), who="Anna")])
    early = next(t.fingerprint for t in client.st.all_transactions() if t.description.endswith("EARLY"))
    mark(client, early, case="payback", charge=charges[0])
    r = client.post(f"/api/transactions/{inflow}/mark",
                    json={"case": "payback", "charges": [{"id": charges[0]}, {"id": charges[1]}]})
    assert r.status_code == 400 and "already paid back" in r.get_json()["error"]
    # The picker says so too.
    found = client.get(f"/api/transactions/{inflow}/charges").get_json()["charges"]
    assert next(c for c in found if c["id"] == charges[0])["left"] == 0


def test_undo_puts_it_all_back(client):
    charges, inflow = gym(client)
    res = mark(client, inflow, case="payback", charges=[{"id": c} for c in charges])
    undo(client, res)
    rows = by_id(client)
    assert rows[inflow].repays is None and rows[inflow].also_repays == {}
    assert all(not rows[c].paid_back for c in charges)
    assert all(c not in client.st.splits() for c in charges)


def test_linking_it_again_to_one_purchase_drops_the_others(client):
    charges, inflow = gym(client)
    mark(client, inflow, case="payback", charges=[{"id": c} for c in charges])
    mark(client, inflow, case="payback", charge=charges[0], amount=50)
    rows = by_id(client)
    assert rows[inflow].repays_all == [charges[0]]
    assert rows[charges[1]].paid_back in (None, 0, 0.0) and charges[1] not in client.st.splits()


def test_a_single_pick_in_the_list_is_the_ordinary_payback(client):
    charges, inflow = gym(client, months=1)
    mark(client, inflow, case="payback", charges=[{"id": charges[0]}])
    assert by_id(client)[inflow].repays == charges[0]


def test_the_list_says_what_it_paid_for(client):
    charges, inflow = gym(client)
    mark(client, inflow, case="payback", charges=[{"id": c} for c in charges])
    month = ago(2)[:7]
    rows = client.get("/api/transactions/list", query_string={"month": month}).get_json()["transactions"]
    r = next(x for x in rows if x["id"] == inflow)
    assert r["note"] == "Paid back to me · for 3 GoodLife Fitness purchases · comes off your spending"
