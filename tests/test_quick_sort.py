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
    def test_counts_what_needs_a_look_counts(self, client):
        """2026-10-24: one number. The prompt counts every question Needs a
        look asks, not only the unsure categories, and lists them as keys."""
        ledger(client)
        review = client.get("/api/review").get_json()
        body = client.get("/api/quick-sort").get_json()
        assert body["count"] == review["count"] == client.get("/api/home").get_json()["review_count"]
        assert body["show"] == (review["count"] > 0) and len(body["keys"]) == body["count"]
        assert body["items"] == []                       # no unsure categories yet
        ledger(client, [unsure("2026-10-08", "Shoppers Drug Mart", 18.47, "Personal Care", account="visa"),
                        tx("2026-10-07", "MYSTERY SHOP", 42.00, "Other", category_source="issuer")])
        body = client.get("/api/quick-sort").get_json()
        assert body["show"] and body["count"] == client.get("/api/review").get_json()["count"] == review["count"] + 2
        first = body["items"][0]
        assert first["merchant"] == "Shoppers Drug Mart" and first["guess"] == "Personal Care"
        assert first["date"] == "2026-10-08" and first["amount"] == 18.47 and not first["inflow"]
        assert first["suggested"] == ["Personal Care"]
        assert body["items"][1]["guess"] == "Other" and body["items"][1]["suggested"] == []
        assert body["safe_to_spend"] is not None

    def test_once_a_day_and_never_the_same_rows_twice(self, client):
        rows = ledger(client, [unsure("2026-10-08", "Shoppers Drug Mart", 18.47, "Personal Care")])
        first = client.get("/api/quick-sort").get_json()
        ids = [i["id"] for i in first["items"]]
        assert client.post("/api/quick-sort/seen", json={"ids": first["keys"], "start": False}).get_json()["ok"]
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
        # Every question counts; the category cards older apps use stop at ten.
        assert body["count"] == client.get("/api/review").get_json()["count"] and len(body["items"]) == 10


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

    def test_yes_on_one_card_saves_no_rule(self, client):
        """T-90: a swipe right sorts this card only, however many others there are."""
        ledger(client, [unsure("2026-10-08", "Uber Eats", 24.80, "Dining"),
                        unsure("2026-10-06", "Uber Eats", 31.10, "Dining")])
        review = client.get("/api/review").get_json()
        assert all(i["txn"]["learnable"] for i in review["unsure_category"])
        first, second = [i["txn"]["id"] for i in review["unsure_category"]]
        r = client.put(f"/api/quick-sort/{first}", json={"action": "right", "every": False}).get_json()
        assert r["ok"] and not r["rule_saved"] and r["also"] == []
        assert "uber eats" not in client.st.overrides()
        open_ids = {i["txn"]["id"] for i in client.get("/api/review").get_json()["unsure_category"]}
        assert open_ids == {second}

    def test_a_merchant_sorted_different_ways_is_mixed(self, client):
        """T-97: once she has said two categories for a merchant, its guesses are mixed."""
        ledger(client, [unsure("2026-10-08", "Amazon", 24.80, "Shopping"),
                        unsure("2026-10-06", "Amazon", 31.10, "Groceries"),
                        unsure("2026-10-04", "Amazon", 18.00, "Shopping"),
                        unsure("2026-10-07", "Loblaws", 56.10, "Groceries")])
        def guesses():
            return {i["txn"]["id"]: i for i in client.get("/api/review").get_json()["unsure_category"]}
        rows = [i for i in guesses().values() if i["txn"]["merchant"] == "Amazon"]
        assert len(rows) == 3 and not any(i["txn"]["mixed"] for i in rows)
        shopping = next(i for i in rows if i["guess"] == "Shopping")["txn"]["id"]
        groceries = next(i for i in rows if i["guess"] == "Groceries")["txn"]["id"]
        client.put(f"/api/quick-sort/{shopping}", json={"action": "right", "every": False})
        assert not any(i["txn"]["mixed"] for i in guesses().values())
        client.put(f"/api/quick-sort/{groceries}", json={"action": "right", "every": False})
        now = guesses()
        left = [i for i in now.values() if i["txn"]["merchant"] == "Amazon"]
        assert len(left) == 1 and left[0]["txn"]["mixed"]
        assert client.get(f"/api/transactions/{left[0]['txn']['id']}/cases").get_json()["mixed"]
        # Only Amazon: Loblaws stays one category.
        assert not next(i for i in now.values() if i["txn"]["merchant"] == "Loblaws")["txn"]["mixed"]

    def test_a_generic_name_cannot_have_a_rule(self, client):
        """T-90: Always isn't offered for a name every transfer shares."""
        ledger(client, [unsure("2026-10-08", "Interac e-Transfer", 24.80, "Dining")])
        items = client.get("/api/review").get_json()["unsure_category"]
        assert items and not items[0]["txn"]["learnable"]

    def test_yes_for_every_one_from_the_merchant_and_undo(self, client):
        """T-85 / T-86 (THL-254): Yes with every sorts the other Uber Eats
        guesses too, saves a rule, and Undo puts all of it back."""
        ledger(client, [unsure("2026-10-08", "Uber Eats", 24.80, "Dining"),
                        unsure("2026-10-06", "Uber Eats", 31.10, "Dining"),
                        unsure("2026-10-04", "UBER EATS", 18.00, "Dining"),
                        unsure("2026-10-07", "Loblaws", 56.10, "Shopping")])
        items = client.get("/api/quick-sort").get_json()["items"]
        uber = [i["id"] for i in items if i["merchant"].lower() == "uber eats"]
        assert len(uber) == 3
        client.post("/api/quick-sort/seen", json={"ids": [i["id"] for i in items], "start": True})
        r = client.put(f"/api/quick-sort/{uber[0]}", json={"action": "right", "every": True}).get_json()
        assert r["ok"] and r["rule_saved"] and sorted(r["also"]) == sorted(uber[1:])
        assert client.st.overrides().get("uber eats") == "Dining"
        open_ids = {i["txn"]["id"] for i in client.get("/api/review").get_json()["unsure_category"]}
        assert not open_ids & set(uber)
        # Undo: the rule goes, and all three are questions again.
        undo = client.post("/api/transactions/undo", json=r["undo"])
        assert undo.status_code == 200, undo.get_json()
        assert client.put(f"/api/quick-sort/{uber[0]}", json={"action": "undo"}).get_json()["ok"]
        assert "uber eats" not in client.st.overrides()
        open_ids = {i["txn"]["id"] for i in client.get("/api/review").get_json()["unsure_category"]}
        assert set(uber) <= open_ids
        assert client.post("/api/quick-sort/done").get_json()["sorted"] == 0

    def test_done_counts_the_ones_sorted_together(self, client):
        ledger(client, [unsure("2026-10-08", "Uber Eats", 24.80, "Dining"),
                        unsure("2026-10-06", "Uber Eats", 31.10, "Dining")])
        items = client.get("/api/quick-sort").get_json()["items"]
        client.post("/api/quick-sort/seen", json={"ids": [i["id"] for i in items], "start": True})
        r = client.put(f"/api/quick-sort/{items[0]['id']}",
                       json={"action": "category", "category": "Groceries", "every": True}).get_json()
        assert r["also"] == [items[1]["id"]]
        assert client.st.get_transaction(items[1]["id"]).category == "Groceries"
        done = client.post("/api/quick-sort/done").get_json()
        assert done["sorted"] == 2 and done["rules"] == 1

    def test_just_this_one_saves_no_rule(self, client):
        """Something else with every False (T-79's Just this one)."""
        ledger(client, [unsure("2026-10-08", "Uber Eats", 24.80, "Dining"),
                        unsure("2026-10-06", "Uber Eats", 31.10, "Dining")])
        items = client.get("/api/quick-sort").get_json()["items"]
        r = client.put(f"/api/quick-sort/{items[0]['id']}",
                       json={"action": "category", "category": "Groceries", "every": False}).get_json()
        assert r["ok"] and not r["rule_saved"] and r["also"] == []
        assert "uber eats" not in client.st.overrides()
        assert client.st.get_transaction(items[0]["id"]).category == "Groceries"
        open_ids = {i["txn"]["id"] for i in client.get("/api/review").get_json()["unsure_category"]}
        assert items[1]["id"] in open_ids and items[0]["id"] not in open_ids

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
