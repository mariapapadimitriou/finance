"""Quick sort when you come back (THL-244, THL-254)."""

from datetime import timedelta

import pytest

from finance import quick_sort, secrets_box
from test_plaid_link import KEY
from test_safe_to_spend import TODAY, history, october, tx


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import create_app
    from finance import api
    monkeypatch.setenv(secrets_box.KEY_ENV, KEY)
    app = create_app(str(tmp_path / "qs.db"))
    app.config.update(TESTING=True)
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    st = app.config["STORE"]
    with app.test_client() as c:
        c.st = st
        c.api = api
        yield c


def unsure(day, merchant, amount, category, **kw):
    """A row Plaid labelled without much confidence (THL-227)."""
    return tx(day, merchant, amount, category, category_source="issuer",
              raw={"category_confidence": "LOW"}, **kw)


def ledger(c, extra=()):
    rows = history() + october() + list(extra)
    c.st.add_transactions(rows)
    return rows


class TestThePrompt:
    def test_shows_only_for_new_unsure_rows(self, client):
        ledger(client)
        assert client.get("/api/quick-sort").get_json() == {
            "show": False, "count": 0, "items": [], "shown_today": False, "safe_to_spend": None}
        ledger(client, [unsure("2026-10-08", "Shoppers Drug Mart", 18.47, "Personal Care", account="visa"),
                        tx("2026-10-07", "MYSTERY SHOP", 42.00, "Other", category_source="issuer")])
        body = client.get("/api/quick-sort").get_json()
        assert body["show"] and body["count"] == 2
        first = body["items"][0]
        assert first["merchant"] == "Shoppers Drug Mart" and first["guess"] == "Personal Care"
        assert first["date"] == "2026-10-08" and first["amount"] == 18.47 and not first["inflow"]
        assert first["suggested"] == ["Personal Care"]
        assert body["items"][1]["guess"] == "Other" and body["items"][1]["suggested"] == []
        assert body["safe_to_spend"] is not None

    def test_once_a_day_and_never_the_same_rows_twice(self, client):
        rows = ledger(client, [unsure("2026-10-08", "Shoppers Drug Mart", 18.47, "Personal Care")])
        ids = [i["id"] for i in client.get("/api/quick-sort").get_json()["items"]]
        assert client.post("/api/quick-sort/seen", json={"ids": ids, "start": False}).get_json()["ok"]
        body = client.get("/api/quick-sort").get_json()
        assert not body["show"] and body["shown_today"] and body["items"] == []
        # The row stays in Needs a look.
        assert any(i["txn"]["id"] == ids[0]
                   for i in client.get("/api/review").get_json()["unsure_category"])
        # Tomorrow, a new unsure row is new; yesterday's isn't offered again.
        tomorrow = TODAY + timedelta(days=1)
        client.api._today_iso = lambda: tomorrow.isoformat()
        assert not client.get("/api/quick-sort").get_json()["show"]
        client.st.add_transactions([unsure("2026-10-10", "Dollarama", 9.50, "Shopping")])
        body = client.get("/api/quick-sort").get_json()
        assert body["show"] and [i["merchant"] for i in body["items"]] == ["Dollarama"]

    def test_suggested_and_recent_categories(self, client):
        ledger(client, [
            tx("2026-10-02", "Shoppers Drug Mart", 22.00, "Health", category_source="user"),
            tx("2026-10-04", "Uber", 14.00, "Transport", category_source="user"),
            unsure("2026-10-08", "Shoppers Drug Mart", 18.47, "Personal Care"),
        ])
        item = client.get("/api/quick-sort").get_json()["items"][0]
        assert item["suggested"] == ["Personal Care", "Health"]
        assert item["recent"] == ["Transport"]

    def test_at_most_ten_cards(self, client):
        ledger(client, [unsure(f"2026-10-{d:02d}", f"Shop {d}", 5.0 + d, "Shopping") for d in range(1, 9)]
               + [unsure("2026-09-30", f"Older {i}", 3.0 + i, "Shopping") for i in range(5)])
        body = client.get("/api/quick-sort").get_json()
        assert body["count"] == 10 and len(body["items"]) == 10


class TestTheCards:
    def test_right_confirms_and_a_new_category_saves_a_rule(self, client):
        rows = ledger(client, [unsure("2026-10-08", "Shoppers Drug Mart", 18.47, "Personal Care"),
                               unsure("2026-10-07", "Loblaws", 56.10, "Shopping")])
        items = client.get("/api/quick-sort").get_json()["items"]
        ids = [i["id"] for i in items]
        client.post("/api/quick-sort/seen", json={"ids": ids, "start": True})
        r = client.put(f"/api/quick-sort/{ids[0]}", json={"action": "right"}).get_json()
        assert r["ok"] and not r["rule_saved"]
        r = client.put(f"/api/quick-sort/{ids[1]}", json={"action": "category", "category": "Groceries"}).get_json()
        assert r["ok"] and r["rule_saved"]
        assert client.st.overrides().get("loblaws") == "Groceries"
        assert client.st.get_transaction(ids[1]).category == "Groceries"
        # Neither is a question any more.
        q = client.get("/api/review").get_json()["unsure_category"]
        assert not any(i["txn"]["id"] in ids for i in q)
        done = client.post("/api/quick-sort/done").get_json()
        assert done["sorted"] == 2 and done["skipped"] == 0 and done["rules"] == 1
        assert done["reason"] == "One was Groceries Pearl had counted as Shopping."
        assert done["before"] is not None and done["after"] is not None

    def test_skip_leaves_it_in_needs_a_look(self, client):
        ledger(client, [unsure("2026-10-08", "Shoppers Drug Mart", 18.47, "Personal Care")])
        ids = [i["id"] for i in client.get("/api/quick-sort").get_json()["items"]]
        client.post("/api/quick-sort/seen", json={"ids": ids, "start": True})
        r = client.put(f"/api/quick-sort/{ids[0]}", json={"action": "skip"}).get_json()
        assert r["ok"]
        assert any(i["txn"]["id"] == ids[0] and not i["skipped"]
                   for i in client.get("/api/review").get_json()["unsure_category"])
        done = client.post("/api/quick-sort/done").get_json()
        assert done["sorted"] == 0 and done["skipped"] == 1
        assert done["reason"] == "Every guess was right, so nothing moved."

    def test_bad_answers(self, client):
        ledger(client, [unsure("2026-10-08", "Shoppers Drug Mart", 18.47, "Personal Care")])
        ids = [i["id"] for i in client.get("/api/quick-sort").get_json()["items"]]
        assert client.put(f"/api/quick-sort/{ids[0]}", json={"action": "category"}).status_code == 400
        assert client.put(f"/api/quick-sort/{ids[0]}", json={"action": "dance"}).status_code == 400
        assert client.put("/api/quick-sort/nope", json={"action": "right"}).status_code == 404
        assert client.post("/api/quick-sort/seen", json={"ids": "x"}).status_code == 400


class TestWords:
    def test_reason_words(self):
        assert quick_sort.reason_words([]) == "Every guess was right, so nothing moved."
        changes = [{"action": "category", "from": "Shopping", "to": "Groceries"},
                   {"action": "category", "from": "Shopping", "to": "Groceries"},
                   {"action": "marked", "title": "Put away to savings"},
                   {"action": "right", "from": "Coffee", "to": "Coffee"}]
        assert quick_sort.reason_words(changes) == (
            "Two were Groceries Pearl had counted as Shopping, and one was “Put away to savings”.")
