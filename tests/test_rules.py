"""Profile › Categories and rules (Pearl S-03): every rule she saved — by
merchant, by where a transfer went, and what she leaves out — listed, edited
and deleted. Deleting a sorting rule doesn't change what it already sorted."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest, recategorize_all

TODAY = date.today()


def row(amount, description, account="card", n=1, raw=None):
    d = max(TODAY - timedelta(days=n), TODAY.replace(day=1)).isoformat()
    return Transaction(date=d, description=description, amount=amount, account_id=account,
                       account_name=account, raw=raw or {"account_type": "credit"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "rules.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        st = c.application.config["STORE"]
        ingest(st, IngestResult([row(80, "LOBLAWS #123"), row(40, "LOBLAWS #123", n=2),
                                 row(15, "PRESTO FARE"), row(9, "NETFLIX.COM")], "card"))
        yield c


def store(c):
    return c.application.config["STORE"]


def rules(c):
    return c.get("/api/rules").get_json()


def category_of(c, description):
    return {t.description: t.category for t in store(c).all_transactions()}[description]


def merchant_of(c, description):
    return next(t.merchant for t in store(c).all_transactions() if t.description == description)


def test_no_rules_yet(client):
    assert rules(client) == {"rules": [], "count": 0}
    assert client.get("/api/profile").get_json()["rules"] == 0


def test_a_merchant_rule_is_listed_by_its_name(client):
    store(client).set_override(merchant_of(client, "LOBLAWS #123"), "Groceries")
    data = rules(client)
    assert data["count"] == 1
    r = data["rules"][0]
    assert r["kind"] == "merchant" and r["category"] == "Groceries"
    assert r["name"] == merchant_of(client, "LOBLAWS #123")
    assert client.get("/api/profile").get_json()["rules"] == 1


def test_editing_a_merchant_rule_refiles_its_rows(client):
    store(client).set_override(merchant_of(client, "PRESTO FARE"), "Shopping")
    rid = rules(client)["rules"][0]["id"]
    r = client.put(f"/api/rules/{rid}", json={"category": "Transport"})
    assert r.status_code == 200 and r.get_json()["rule"]["category"] == "Transport"
    assert category_of(client, "PRESTO FARE") == "Transport"


def test_editing_needs_a_real_category(client):
    store(client).set_override(merchant_of(client, "PRESTO FARE"), "Transport")
    rid = rules(client)["rules"][0]["id"]
    assert client.put(f"/api/rules/{rid}", json={"category": "Boats"}).status_code == 400
    assert client.put("/api/rules/merchant:nobody", json={"category": "Dining"}).status_code == 404


def test_deleting_a_merchant_rule_keeps_what_it_sorted(client):
    st = store(client)
    st.set_override(merchant_of(client, "NETFLIX.COM"), "Dining")
    assert category_of(client, "NETFLIX.COM") == "Dining"
    rid = rules(client)["rules"][0]["id"]
    r = client.delete(f"/api/rules/{rid}")
    assert r.status_code == 200 and r.get_json()["count"] == 0
    assert st.overrides() == {}
    assert category_of(client, "NETFLIX.COM") == "Dining"
    # And a re-check of every category doesn't undo it.
    recategorize_all(st)
    assert category_of(client, "NETFLIX.COM") == "Dining"
    assert client.delete(f"/api/rules/{rid}").status_code == 404


def test_a_transfer_destination_rule(client):
    st = store(client)
    st.set_destination("to:m. papas", "Saved", "M. Papas")
    r = rules(client)["rules"][0]
    assert r == {"id": "destination:to:m. papas", "kind": "destination",
                 "name": "Transfers to M. Papas", "category": "Saved"}
    client.put(f"/api/rules/{r['id']}", json={"category": "Gifts & Charity"})
    assert st.destinations()["to:m. papas"] == "Gifts & Charity"
    assert client.delete(f"/api/rules/{r['id']}").status_code == 200
    assert st.destinations() == {}


def test_leave_out_rules_are_listed_and_removing_one_puts_rows_back(client):
    client.post("/api/exclusions", json={"keyword": "netflix", "reason": "Work expense"})
    r = next(x for x in rules(client)["rules"] if x["kind"] == "exclusion")
    assert r["name"] == "Netflix" and r["reason"] == "Work expense" and r["matched"] == 1
    assert r["category"] is None
    assert category_of(client, "NETFLIX.COM")       # still has its category
    assert client.delete(f"/api/rules/{r['id']}").status_code == 200
    assert not any(t.excluded for t in store(client).all_transactions())


def test_unknown_rules(client):
    assert client.delete("/api/rules/bogus:1").status_code == 404
    assert client.delete("/api/rules/exclusion:abc").status_code == 404
    assert client.delete("/api/rules/exclusion:99").status_code == 404
