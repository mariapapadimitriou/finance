"""A+ G5b (2026-11-18): a rule edit says how many earlier transactions it
moves ("Also moves the 14 earlier ones."), moves them or only new ones, and
has Undo; "Rule deleted" and "No longer recurring" have Undo too."""

from __future__ import annotations

import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, "tests")
from test_recurring_transfers import asked, rent  # noqa: E402

from finance.ingest.base import IngestResult  # noqa: E402
from finance.models import Transaction  # noqa: E402
from finance.pipeline import ingest  # noqa: E402

TODAY = date.today()


def row(amount, description, n=1):
    d = max(TODAY - timedelta(days=n), TODAY.replace(day=1)).isoformat()
    return Transaction(date=d, description=description, amount=amount, account_id="card",
                       account_name="card", raw={"account_type": "credit"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "aplus-rules.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def loblaws(c, n=3):
    ingest(c.st, IngestResult([row(20 + i, "LOBLAWS #123", n=i + 1) for i in range(n)], "card"))
    merchant = next(t.merchant for t in c.st.all_transactions())
    c.st.set_override(merchant, "Groceries")
    return next(r for r in c.get("/api/rules").get_json()["rules"] if r["kind"] == "merchant")


def cats(c):
    return sorted(t.category for t in c.st.all_transactions() if t.description == "LOBLAWS #123")


def undo(c, payload):
    r = c.post("/api/transactions/undo", json=payload)
    assert r.status_code == 200, r.get_json()


class TestEarlier:
    def test_counts_what_would_move(self, client):
        r = loblaws(client)
        got = client.get("/api/rules/earlier", query_string={"id": r["id"], "category": "Shopping"})
        assert got.status_code == 200 and got.get_json() == {"count": 3}
        # Nothing moves to where they already are.
        same = client.get("/api/rules/earlier", query_string={"id": r["id"], "category": "Groceries"})
        assert same.get_json() == {"count": 0}

    def test_one_she_set_herself_doesnt_count(self, client):
        r = loblaws(client)
        one = next(t for t in client.st.all_transactions() if t.description == "LOBLAWS #123")
        client.st.write_categories({one.fingerprint: ("Dining", "user")})
        got = client.get("/api/rules/earlier", query_string={"id": r["id"], "category": "Shopping"})
        assert got.get_json() == {"count": 2}

    def test_bad_asks(self, client):
        r = loblaws(client)
        assert client.get("/api/rules/earlier", query_string={"id": r["id"], "category": "Boats"}).status_code == 400
        assert client.get("/api/rules/earlier",
                          query_string={"id": "merchant:nobody", "category": "Shopping"}).status_code == 404


class TestEdit:
    def test_save_moves_the_earlier_ones_and_undo_puts_them_back(self, client):
        r = loblaws(client)
        out = client.put(f"/api/rules/{r['id']}", json={"category": "Shopping"}).get_json()
        assert out["moved"] == 3 and out["rule"]["category"] == "Shopping"
        assert cats(client) == ["Shopping"] * 3
        undo(client, out["undo"])
        assert cats(client) == ["Groceries"] * 3
        assert next(iter(client.st.overrides().values())) == "Groceries"

    def test_only_new_ones_keeps_the_earlier_ones(self, client):
        r = loblaws(client)
        out = client.put(f"/api/rules/{r['id']}", json={"category": "Shopping", "earlier": False}).get_json()
        assert out["moved"] == 0 and out["rule"]["category"] == "Shopping"
        assert cats(client) == ["Groceries"] * 3
        # A new one follows the rule.
        ingest(client.st, IngestResult([row(50, "LOBLAWS #123", n=0)], "card"))
        assert cats(client).count("Shopping") == 1
        undo(client, out["undo"])
        assert next(iter(client.st.overrides().values())) == "Groceries"

    def test_a_recurring_rule_edit_undoes(self, client):
        rent(client)
        [it] = asked(client)
        client.post("/api/recurring-transfers", json={"key": it["key"], "kind": "rent"})
        r = next(x for x in client.get("/api/rules").get_json()["rules"] if x["kind"] == "recurring")
        n = client.get("/api/rules/earlier", query_string={"id": r["id"], "category": "Saved"}).get_json()["count"]
        out = client.put(f"/api/rules/{r['id']}", json={"category": "Saved"}).get_json()
        assert out["moved"] == n == 3
        undo(client, out["undo"])
        assert client.st.recurring_transfers()[0]["category"] == "Rent & Housing"
        assert {t.category for t in client.st.all_transactions() if t.amount == 1500} == {"Rent & Housing"}


class TestDeleteUndo:
    def test_rule_deleted_comes_back(self, client):
        r = loblaws(client)
        out = client.delete(f"/api/rules/{r['id']}").get_json()
        assert not any(x["id"] == r["id"] for x in client.get("/api/rules").get_json()["rules"])
        undo(client, out["undo"])
        assert any(x["id"] == r["id"] for x in client.get("/api/rules").get_json()["rules"])

    def test_no_longer_recurring_comes_back(self, client):
        rent(client)
        [it] = asked(client)
        client.post("/api/recurring-transfers", json={"key": it["key"], "kind": "rent"})
        rule = client.st.recurring_transfers()[0]
        out = client.delete(f"/api/recurring-transfers/{rule['id']}").get_json()
        assert client.st.recurring_transfers() == []
        undo(client, out["undo"])
        assert client.st.recurring_transfers()[0]["id"] == rule["id"]
        assert {t.category_source for t in client.st.all_transactions() if t.amount == 1500} != {"user"}

    def test_a_hidden_category_shows_again(self, client):
        # "<category> hidden" Undo is the same call the other way.
        assert client.put("/api/rules/categories", json={"category": "Fitness", "hidden": True}).status_code == 200
        assert "Fitness" in client.get("/api/rules").get_json()["hidden"]
        client.put("/api/rules/categories", json={"category": "Fitness", "hidden": False})
        assert "Fitness" not in client.get("/api/rules").get_json()["hidden"]
