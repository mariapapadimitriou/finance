"""The payback question (Figma Proposals › "Payback question" 1418:88290,
note 1419:89986; THL-289, THL-291, THL-181, THL-231): "Is mPg paying you
back?" says why in the server's words, and lists the likely purchases as
tiles, best first, each with its card and how the money compares. A tile
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

    def test_why_pearl_is_asking_is_the_amount_and_the_timing(self, c):
        q = question(c)["payback"]
        assert q["why"] == ("mPg sent $20.00 two days after Añejo. That’s about a third of the $61.57, "
                            "like a share of a meal for three.")
        assert q["line"] == "You haven’t split Añejo, so Yes takes $20.00 off it: $41.57 stays yours."

    def test_the_purchase_is_a_dashed_tile_with_its_card_and_how_it_compares(self, c):
        q = question(c)["payback"]
        [tile] = q["tiles"]
        assert tile["title"] == "Yes, Añejo · $61.57"
        assert tile["guess"] is True and tile["category"] == "Dining"
        assert tile["card"] == "Amex Cobalt"
        assert tile["compare"] == "$20.00 is about a third"
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
        assert question(c)["payback"]["tiles"][0]["title"] == "Yes, Añejo · $61.57"

    def test_the_deposit_page_asks_it_as_a_question_card(self, c):
        out = c.get(f"/api/transactions/{ids(c)['deposit']}/payback-question").get_json()
        assert out["question"]["card"] == {
            "title": "Paying you back for Añejo?",
            "line": "Pearl’s guess: about a third of Añejo, $61.57 · tap to answer"}


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
        assert q["why"] == "mPg is on your Añejo split and still owes you $30.79. $20.00 is part of it."
        split, other = q["tiles"]
        assert split["title"] == "Yes, Añejo · mPg’s share" and split["guess"] is True
        assert split["compare"] == "$20.00 of mPg’s $30.79 · $10.79 still to come"
        assert other["title"] == "Yes, Uber Eats · $40.10" and "guess" not in other
        assert other["compare"] == "about half" and other["card"] == "Amex Cobalt"
        assert q["part"] is True

    def test_the_second_line_names_the_runner_up(self, c):
        assert question(c)["payback"]["line"] == "Uber Eats also fits: $20.00 is about half of $40.10, three days before."

    def test_the_card_on_the_page_says_the_split_guess(self, c):
        out = c.get(f"/api/transactions/{ids(c)['deposit']}/payback-question").get_json()
        assert out["question"]["card"]["line"] == \
            "Pearl’s guess: $20.00 of mPg’s $30.79 · $10.79 still to come · tap to answer"

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
        assert q["why"] == "Sam sent $30.00 the same day as Pizza Nova. That’s about half of the $60.00."
        t = etransfer("Sam", 30.00, 2)
        assert build(t, [buy("Pizza Nova", 60.00, "Shopping", 3), t])["why"].startswith(
            "Sam sent $30.00 the day after Pizza Nova.")

    def test_a_split_purchase_isnt_called_unsplit(self):
        c = buy("Pizza Nova", 60.00, "Shopping", 3)
        c.my_share = 30.00
        t = etransfer("Sam", 30.00, 1)
        assert build(t, [c, t])["line"] == "Yes takes $30.00 off Pizza Nova."

    def test_a_share_is_one_of_two_to_six(self):
        assert share_of(20.00, 61.57) == 3 and share_of(20.05, 40.10) == 2 and share_of(5.0, 61.57) is None
