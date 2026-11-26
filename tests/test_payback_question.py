"""The payback question (Figma Proposals › "Payback question" 1418:88290,
note 1419:89986; THL-289, THL-291, THL-181, THL-231): "Is mPg paying you
back?" lists the likely purchases as tiles, best first, each with the
reason in its own few words (LT-03, TEXT-01: no Why card). A tile
answers through the payback path that exists; the deposit's own page
(PQ-03p) shows Pearl's guess as a question card."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.models import Transaction
from finance.payback_question import build, share_of

TODAY = date.today()


def ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


def buy(merchant, amount, category, n, account="amex", account_name="American Express Cobalt® Card"):
    return Transaction(date=ago(n), description=merchant.upper(), merchant=merchant, amount=amount,
                       category=category, category_source="issuer", account_id=account,
                       account_name=account_name)


def etransfer(sender, amount, n):
    name = f"e-Transfer from {sender}" if sender else "Interac e-Transfer"
    return Transaction(date=ago(n), description=name, merchant=name,
                       amount=-amount, category="Transfers", category_source="issuer",
                       account_id="chq", account_name="TD Minimum Chequing",
                       raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "pq.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def ids(c):
    return {t.merchant if t.amount > 0 else "deposit": t.fingerprint for t in c.st.all_transactions()}


def question(c):
    items = c.get("/api/review").get_json()["money_in"]
    return next(i for i in items if i["txn"]["amount"] < 0 and i["txn"]["id"] == ids(c)["deposit"])


class TestNotOnASplit:
    """PQ-03 (1418:88292): mPg isn't on a split; one purchase is likely."""

    @pytest.fixture()
    def c(self, client):
        client.st.add_transactions([buy("Añejo", 61.57, "Dining", 3), etransfer("mPg", 20.00, 1)])
        return client

    def test_the_reason_sits_in_the_tile_not_a_why_card(self, c):
        # LT-03 (TEXT-01): "Oct 31 · about a third · 2 days before"; no Why
        # card and no "You haven’t split Añejo…" line.
        q = question(c)["payback"]
        assert "why" not in q and "line" not in q
        assert q["tiles"][0]["compare"] == "about a third · 2 days before"

    def test_the_purchase_is_a_dashed_tile_with_its_card_and_how_it_compares(self, c):
        q = question(c)["payback"]
        [tile] = q["tiles"]
        assert tile["title"] == "Añejo · $61.57"
        assert tile["guess"] is True and tile["category"] == "Dining"
        assert tile["card"] == "Amex Cobalt"
        assert tile["compare"] == "about a third · 2 days before"
        assert tile["toast"] == "mPg paid back $20.00 for Añejo"
        assert tile["date"] == ago(3) and tile["charge"] == ids(c)["Añejo"]

    def test_the_bank_named_them_so_she_can_name_them(self, c):
        q = question(c)["payback"]
        assert q["who"] == "mPg" and q["named"] is False and q["part"] is False

    def test_a_tap_answers_through_the_payback_path_with_undo(self, c):
        q = question(c)["payback"]
        deposit = ids(c)["deposit"]
        r = c.post(f"/api/transactions/{deposit}/mark",
                   json={"case": "payback", "charge": q["tiles"][0]["charge"]})
        assert r.status_code == 200
        assert not [i for i in c.get("/api/review").get_json()["money_in"] if i["txn"]["id"] == deposit]
        assert c.post("/api/transactions/undo", json=r.get_json()["undo"]).status_code == 200
        assert question(c)["payback"]["tiles"][0]["title"] == "Añejo · $61.57"

    def test_what_it_offers_is_likely_on_what_did_they_pay_back(self, c):
        """TEST-46: every purchase PQ-03 offers is LIKELY on PB-30 too, not
        only behind its search."""
        q = question(c)["payback"]
        out = c.get(f"/api/transactions/{ids(c)['deposit']}/owing").get_json()
        likely = {u["id"] for u in out["unsplit"] if u.get("likely")}
        assert {t["charge"] for t in q["tiles"]} <= likely

    def test_the_deposit_page_asks_it_as_a_question_card(self, c):
        out = c.get(f"/api/transactions/{ids(c)['deposit']}/payback-question").get_json()
        assert out["question"]["card"] == {
            "title": "Paying you back for Añejo?",
            "line": "Pearl’s guess · about a third"}

    def test_the_row_carries_the_question_so_the_page_opens_on_it(self, c):
        """2026-11-20: the page opened on the list's row ("Not sorted yet")
        and switched to the question when its own call came back. The list
        row and the detail row carry the same question the GET answers."""
        deposit = ids(c)["deposit"]
        asked = c.get(f"/api/transactions/{deposit}/payback-question").get_json()["question"]
        rows = c.get("/api/transactions/list?limit=1000").get_json()["transactions"]
        row = next(r for r in rows if r["id"] == deposit)
        assert row["payback_question"] == asked
        detail = c.get(f"/api/transactions/{deposit}").get_json()
        assert detail["payback_question"] == asked


class TestOnTheSplit:
    """PQ-03b (1418:88874): mPg is on the Añejo split and pays part of what
    they owe; Uber Eats also fits."""

    @pytest.fixture()
    def c(self, client):
        client.st.add_transactions([buy("Añejo", 61.57, "Dining", 3), buy("Uber Eats", 40.10, "Food Delivery", 4),
                                    etransfer("mPg", 20.00, 1)])
        r = client.put(f"/api/transactions/{ids(client)['Añejo']}/split",
                       json={"mode": "amount", "people": [{"name": "mPg", "amount": 30.79}]})
        assert r.status_code == 200, r.get_json()
        return client

    def test_the_split_comes_first_with_what_is_still_to_come(self, c):
        q = question(c)["payback"]
        split, other = q["tiles"]
        assert split["title"] == "Añejo · mPg’s share" and split["guess"] is True
        assert split["compare"] == "$20.00 of mPg’s $30.79 · mPg still owes $10.79"
        # P5e (fewer taps): the Quick sort card's line under the question.
        assert split["after"] == "mPg still owes $10.79 after this"
        assert other["title"] == "Uber Eats · $40.10" and "guess" not in other
        assert other["compare"] == "about half · 3 days before" and other["card"] == "Amex Cobalt"
        assert q["part"] is True

    def test_the_runner_up_is_its_own_tile_not_a_line(self, c):
        # TEXT-01: "Uber Eats also fits: …" is cut; the second tile says it.
        assert "line" not in question(c)["payback"]

    def test_the_card_on_the_page_says_the_split_guess(self, c):
        out = c.get(f"/api/transactions/{ids(c)['deposit']}/payback-question").get_json()
        assert out["question"]["card"]["line"] == \
            "Pearl’s guess · $20.00 of mPg’s $30.79 · mPg still owes $10.79"

    def test_yes_on_the_split_credits_mpg(self, c):
        q = question(c)["payback"]
        r = c.post(f"/api/transactions/{ids(c)['deposit']}/mark",
                   json={"case": "payback", "charge": q["tiles"][0]["charge"]})
        assert r.status_code == 200, r.get_json()
        people = c.get(f"/api/transactions/{ids(c)['Añejo']}").get_json()["splitting"]["people"]
        mpg = next(p for p in people if p["name"] == "mPg")
        assert round(mpg["owes"], 2) == 10.79


class TestNothingToAsk:
    def test_no_likely_purchase_no_question(self, client):
        client.st.add_transactions([etransfer("mPg", 77.13, 1)])
        assert "payback" not in question(client)

    def test_a_nameless_etransfer_isnt_interac_paying_her_back(self):
        t = etransfer("", 20.00, 1)
        assert build(t, [t, buy("Añejo", 61.57, "Dining", 3)]) is None

    def test_at_most_three_tiles_and_only_the_first_is_dashed(self):
        rows = [buy(f"Bistro {i}", 40.00 + i, "Dining", 2 + i) for i in range(5)]
        t = etransfer("mPg", 20.00, 1)
        q = build(t, rows + [t])
        assert len(q["tiles"]) == 3
        assert [x.get("guess", False) for x in q["tiles"]] == [True, False, False]


class TestWords:
    def test_the_same_day_and_the_day_after(self):
        t = etransfer("Sam", 30.00, 3)
        q = build(t, [buy("Pizza Nova", 60.00, "Shopping", 3), t])
        assert q["tiles"][0]["compare"] == "about half · the same day"
        t = etransfer("Sam", 30.00, 2)
        assert build(t, [buy("Pizza Nova", 60.00, "Shopping", 3), t])["tiles"][0]["compare"] == \
            "about half · the day before"

    def test_a_share_is_one_of_two_to_six(self):
        assert share_of(20.00, 61.57) == 3 and share_of(20.05, 40.10) == 2 and share_of(5.0, 61.57) is None
