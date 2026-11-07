"""Pair cards, Yes moving only what's on the card, and hand-set rows staying put."""

import pytest

from test_quick_sort import client, ledger, unsure  # noqa: F401
from test_safe_to_spend import tx


def review(c):
    return c.get("/api/review").get_json()


def guess_for(c, merchant):
    return [i for i in review(c)["unsure_category"] if i["txn"]["merchant"] == merchant]


class TestYesMovesWhatsOnTheCard:
    def test_the_card_lists_the_others_and_only_those_move(self, client):
        ledger(client, [unsure("2026-10-08", "Uber Eats", 30.00, "Food Delivery"),
                        unsure("2026-10-06", "Uber Eats", 20.00, "Food Delivery"),
                        tx("2026-10-02", "Uber Eats", 11.00, "Dining", category_source="rule")])
        item = guess_for(client, "Uber Eats")[0]
        others = [o["id"] for o in item["siblings"]]
        assert len(others) == 1
        out = client.put(f"/api/quick-sort/{item['txn']['id']}",
                         json={"action": "right", "every": True, "rows": others}).get_json()
        assert out["also"] == others and out["rule_saved"] is True
        # The rule is saved for new ones; a row nobody was shown didn't move.
        rows = {t.amount: t for t in client.st.all_transactions() if t.merchant == "Uber Eats"}
        assert rows[11.00].category == "Dining"
        assert client.st.overrides()["uber eats"] == "Food Delivery"

    def test_new_ones_off_saves_no_rule(self, client):
        ledger(client, [unsure("2026-10-08", "Bistro Nine", 30.00, "Dining")])
        item = guess_for(client, "Bistro Nine")[0]
        out = client.put(f"/api/quick-sort/{item['txn']['id']}",
                         json={"action": "right", "every": True, "rows": [], "new_ones": False}).get_json()
        assert out["rule_saved"] is False and "bistro nine" not in client.st.overrides()


class TestARuleLeavesHerAnswersAlone:
    def test_rows_set_by_hand_or_confirmed_stay(self, client):
        ledger(client, [unsure("2026-10-08", "Amazon", 24.80, "Shopping"),
                        unsure("2026-10-06", "Amazon", 31.10, "Shopping"),
                        unsure("2026-10-04", "Amazon", 18.00, "Shopping")])
        ids = {t.amount: t.fingerprint for t in client.st.all_transactions() if t.merchant == "Amazon"}
        client.st.set_transaction_category(ids[31.10], "Groceries")
        client.st.confirm_category(ids[18.00], "Shopping")
        client.st.set_override("Amazon", "Home")
        rows = {t.amount: t.category for t in client.st.all_transactions() if t.merchant == "Amazon"}
        assert rows == {24.80: "Home", 31.10: "Groceries", 18.00: "Shopping"}


class TestMixedComesFromTheLedger:
    """No list of stores: any merchant, from what the ledger says."""

    def test_any_merchant_has_a_yes_and_no_list_decides(self, client):
        ledger(client, [unsure("2026-10-08", "Amazon", 24.80, "Shopping"),
                        unsure("2026-10-06", "Amazon", 31.10, "Shopping")])
        item = guess_for(client, "Amazon")[0]
        assert item["guess"] == "Shopping" and item["txn"]["mixed"] is False
        assert len(item["siblings"]) == 1

    def test_the_banks_labels_disagreeing_makes_it_mixed(self, client):
        ledger(client, [unsure("2026-10-08", "Corner Store", 24.80, "Shopping"),
                        unsure("2026-10-06", "Corner Store", 31.10, "Groceries")])
        for item in guess_for(client, "Corner Store"):
            assert item["txn"]["mixed"] is True and item["siblings"] == []

    def test_her_answer_against_the_guess_makes_it_mixed(self, client):
        ledger(client, [unsure("2026-10-08", "Corner Store", 24.80, "Shopping"),
                        unsure("2026-10-06", "Corner Store", 31.10, "Shopping")])
        first = guess_for(client, "Corner Store")[0]
        client.put(f"/api/quick-sort/{first['txn']['id']}",
                   json={"action": "category", "category": "Groceries", "every": False})
        rest = guess_for(client, "Corner Store")
        assert len(rest) == 1 and rest[0]["txn"]["mixed"] is True


def inflow(day, merchant, amount, **kw):
    kw.setdefault("account_name", "bank")
    t = tx(day, merchant, -amount, "Transfers", category_source="issuer", **kw)
    t.raw = {**(t.raw or {}), "account_type": "depository"}
    return t


class TestPairCards:
    def test_a_refund_to_the_cent_at_the_same_store(self, client):
        ledger(client, [tx("2026-10-08", "Canada Computers", 129.99, "Shopping", category_source="issuer"),
                        inflow("2026-10-20", "Canada Computers", 129.99)])
        item = next(i for i in review(client)["money_in"] if i["txn"]["merchant"] == "Canada Computers")
        assert item["pair"]["question"] == "Money back for Canada Computers?"
        out = client.post(f"/api/review/pair/{item['txn']['id']}").get_json()
        assert out["ok"] is True and out["also"] == [item["pair"]["other"]]
        assert not [i for i in review(client)["money_in"] if i["txn"]["id"] == item["txn"]["id"]]

    def test_undo_brings_the_question_back(self, client):
        ledger(client, [tx("2026-10-08", "Canada Computers", 129.99, "Shopping", category_source="issuer"),
                        inflow("2026-10-20", "Canada Computers", 129.99)])
        item = next(i for i in review(client)["money_in"] if i["txn"]["merchant"] == "Canada Computers")
        out = client.post(f"/api/review/pair/{item['txn']['id']}").get_json()
        assert client.post("/api/transactions/undo", json=out["undo"]).status_code == 200
        assert [i for i in review(client)["money_in"] if i["txn"]["id"] == item["txn"]["id"]]

    def test_no_evidence_no_pair(self, client):
        ledger(client, [inflow("2026-10-20", "Mystery Deposit", 77.13)])
        item = next(i for i in review(client)["money_in"] if i["txn"]["merchant"] == "Mystery Deposit")
        assert "pair" not in item
        assert client.post(f"/api/review/pair/{item['txn']['id']}").status_code == 409


class TestQuestionsPearlWasntAsking:
    def test_money_in_with_nothing_to_refund_is_asked(self, client):
        t = inflow("2026-10-14", "ATM Deposit", 200.00)
        t.category = "Other"
        ledger(client, [t])
        item = next(i for i in review(client)["money_in"] if i["txn"]["merchant"] == "ATM Deposit")
        assert item["guess"]["action"] == "unknown" and "nothing to refund" in item["reason"]

    def test_money_out_of_savings_is_not_called_a_refund(self, client):
        t = inflow("2026-10-14", "Questrade", 800.00)
        t.category = "Saved"
        ledger(client, [t])
        assert not [i for i in review(client)["money_in"] if i["txn"]["merchant"] == "Questrade"]


class TestNames:
    def test_a_short_name_joins_the_full_one_only_when_it_can_be_one_person(self):
        from finance.etransfers import canonical_names
        def sent(name):
            t = tx("2026-10-10", name, -10.0, "Transfers", party=name)
            return t
        assert canonical_names([sent("Priya S"), sent("Priya Shah")]) == {"Priya S": "Priya Shah"}
        got = canonical_names([sent("Priya"), sent("Priya Shah"), sent("Priya Patel")])
        assert "Priya" not in got


class TestSortedLists:
    def test_an_answer_lands_in_sorted_today_and_undo_takes_it_out(self, client):
        ledger(client, [unsure("2026-10-08", "Bistro Nine", 30.00, "Dining")])
        item = guess_for(client, "Bistro Nine")[0]
        out = client.put(f"/api/quick-sort/{item['txn']['id']}",
                         json={"action": "right", "every": False, "rows": []}).get_json()
        rows = client.get("/api/review/sorted?view=today").get_json()["rows"]
        assert [r["id"] for r in rows] == [item["txn"]["id"]]
        assert review(client)["sorted_today"] == 1
        assert client.post("/api/transactions/undo", json=out["undo"]).status_code == 200
        assert client.get("/api/review/sorted?view=today").get_json()["rows"] == []

    def test_a_skip_is_not_an_answer(self, client):
        ledger(client, [unsure("2026-10-08", "Bistro Nine", 30.00, "Dining")])
        item = guess_for(client, "Bistro Nine")[0]
        client.put(f"/api/quick-sort/{item['txn']['id']}", json={"action": "skip"})
        assert client.get("/api/review/sorted?view=today").get_json()["rows"] == []

    def test_pearl_sorted_lists_rows_nobody_was_asked_about_with_a_reason(self, client):
        ledger(client, [tx("2026-10-09", "Loblaws", 40.00, "Groceries", category_source="issuer")])
        rows = client.get("/api/review/sorted?view=pearl").get_json()["rows"]
        row = next(r for r in rows if r["merchant"] == "Loblaws" and r["amount"] == 40.00)
        assert "your bank said so" in row["line"]
        assert review(client)["pearl_sorted"] == len(rows)

    def test_a_row_she_was_asked_about_is_not_in_pearl_sorted(self, client):
        ledger(client, [unsure("2026-10-08", "Bistro Nine", 30.00, "Dining")])
        rows = client.get("/api/review/sorted?view=pearl").get_json()["rows"]
        assert not [r for r in rows if r["merchant"] == "Bistro Nine"]


class TestPayFromAPiggyBank:
    def test_part_of_a_charge(self, client):
        ledger(client, [tx("2026-10-08", "Air Transat", 900.00, "Travel", category_source="issuer")])
        bank = client.post("/api/piggy", json={"name": "Japan trip", "target": 2000, "monthly": 100}).get_json()
        bank_id = bank.get("id") or bank["bank"]["id"]
        t = next(x for x in client.st.all_transactions() if x.merchant == "Air Transat")
        out = client.post(f"/api/piggy/{bank_id}/allocate", json={"txn_id": t.fingerprint, "amount": 300}).get_json()
        assert out["covered"] == 300
        assert client.post(f"/api/piggy/{bank_id}/allocate",
                           json={"txn_id": t.fingerprint, "amount": 901}).status_code == 400


class TestAThirdPaycheque:
    def test_is_a_note_and_counts_for_nothing(self, client):
        from finance.quick_sort import questions
        ledger(client)
        r = review(client)
        if r["three_pay_month"]:
            assert not [k for k, _ in questions(r) if k.startswith("pay3:")]


def test_a_row_shows_what_a_piggy_bank_left(client):
    ledger(client, [tx("2026-10-08", "Air Transat", 900.00, "Travel", category_source="issuer")])
    bank = client.post("/api/piggy", json={"name": "Japan trip", "target": 2000, "monthly": 100}).get_json()
    bank_id = bank.get("id") or bank["bank"]["id"]
    t = next(x for x in client.st.all_transactions() if x.merchant == "Air Transat")
    client.post(f"/api/piggy/{bank_id}/allocate", json={"txn_id": t.fingerprint, "amount": 300})
    row = next(r for r in client.get("/api/transactions/list?month=2026-10&limit=1000").get_json()["transactions"]
               if r["merchant"] == "Air Transat")
    assert row["amount"] == 600 and row["full_amount"] == 900 and "paid $300.00" in row["note"]
