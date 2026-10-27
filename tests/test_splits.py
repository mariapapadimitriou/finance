"""Splits and repayments (THL-124): only her share counts, a repayment is
never income, partial repayments stay open, and a suggestion needs the same
person, about the same amount and a recent charge."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
MONTH = TODAY.isoformat()[:7]


def day(n=0):
    return (TODAY - timedelta(days=n)).isoformat()


def charge(amount, description, merchant=None, when=None, category="Dining"):
    t = Transaction(date=when or TODAY.isoformat(), description=description, amount=amount,
                    account_id="card", account_name="card", raw={"account_type": "credit"},
                    merchant=merchant or "")
    t.category, t.category_source = category, "user"
    return t


def etransfer_in(amount, who, when=None):
    return Transaction(date=when or TODAY.isoformat(),
                       description=f"E-TRANSFER RECEIVED {who.upper()}", amount=-amount,
                       account_id="chq", account_name="chq",
                       raw={"account_type": "depository", "counterparty": who,
                            "issuer_category": "TRANSFER_IN_ACCOUNT_TRANSFER"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "splits.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def load(st, *rows):
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r.account_id, []).append(r)
    for acct, txns in by.items():
        ingest(st, IngestResult(transactions=txns, account_id=acct))
    return {t.description: t.fingerprint for t in st.all_transactions()}


def split(c, tid, people, mode="even", watch=True):
    return c.put(f"/api/transactions/{tid}/split",
                 json={"mode": mode, "people": people, "watch": watch})


def detail(c, tid):
    return c.get(f"/api/transactions/{tid}").get_json()


def listing(c):
    return c.get("/api/transactions/list", query_string={"month": MONTH}).get_json()


def test_even_split_counts_only_her_share(client):
    ids = load(client.st, charge(85, "SUSHI NAMI", "Sushi Nami"))
    tid = ids["SUSHI NAMI"]
    res = split(client, tid, [{"name": "Priya"}])
    assert res.status_code == 200, res.get_json()
    r = res.get_json()
    assert r["splitting"]["you"] == 42.5
    assert r["splitting"]["people"] == [{"name": "Priya", "amount": 42.5, "paid": 0.0,
                                         "owes": 42.5, "paid_on": None}]
    data = listing(client)
    assert data["totals"]["spent"] == 42.5
    assert data["transactions"][0]["note"] == "Your share of $85.00 · split with Priya"  # nobody paid yet


def test_an_odd_cent_stays_with_her(client):
    ids = load(client.st, charge(100, "DINNER"))
    r = split(client, ids["DINNER"], [{"name": "A"}, {"name": "B"}]).get_json()
    assert [p["amount"] for p in r["splitting"]["people"]] == [33.33, 33.33]
    assert r["splitting"]["you"] == 33.34


def test_by_amount_and_validation(client):
    ids = load(client.st, charge(120, "AIRBNB"))
    tid = ids["AIRBNB"]
    ok = split(client, tid, [{"name": "Sam", "amount": 80}], mode="amount").get_json()
    assert ok["splitting"]["you"] == 40
    bad = [
        ([{"name": "Sam", "amount": 200}], "amount"),
        ([{"name": "", "amount": 10}], "amount"),
        ([{"name": "Sam", "amount": -1}], "amount"),
        ([], "even"),
        ([{"name": f"P{i}"} for i in range(51)], "even"),
        ([{"name": "Sam"}], "thirds"),
    ]
    for people, mode in bad:
        assert split(client, tid, people, mode=mode).status_code == 400, (people, mode)


def test_suggestion_needs_same_person_amount_and_recent(client):
    ids = load(client.st,
               charge(85, "SUSHI NAMI", "Sushi Nami", when=day(3)),
               etransfer_in(42.5, "Priya"),
               etransfer_in(42.5, "Sam", when=day(1)),
               etransfer_in(20.0, "Priya", when=day(2)))
    split(client, ids["SUSHI NAMI"], [{"name": "Priya"}])
    # Two rows share a description; find each by amount.
    rows = {(t.description, -t.amount): t.fingerprint for t in client.st.all_transactions()
            if t.amount < 0}
    full = detail(client, rows[("E-TRANSFER RECEIVED PRIYA", 42.5)])["repayment"]
    assert full["suggestion"]["charge_id"] == ids["SUSHI NAMI"]
    assert full["suggestion"]["exact"] is True and full["from_sender"] is True
    assert detail(client, rows[("E-TRANSFER RECEIVED SAM", 42.5)])["repayment"]["suggestion"] is None
    # $20 is more than $1 off what Priya owes: no suggestion, but S-03 lists it.
    part = detail(client, rows[("E-TRANSFER RECEIVED PRIYA", 20.0)])["repayment"]
    assert part["suggestion"] is None
    assert [s["charge_id"] for s in part["splits"]] == [ids["SUSHI NAMI"]]


def test_too_old_is_not_suggested(client):
    ids = load(client.st, charge(85, "OLD DINNER", when=day(70)), etransfer_in(42.5, "Priya"))
    split(client, ids["OLD DINNER"], [{"name": "Priya"}])
    r = detail(client, ids["E-TRANSFER RECEIVED PRIYA"])["repayment"]
    assert r["suggestion"] is None


def test_partial_repayment_stays_open_and_never_income(client):
    ids = load(client.st, charge(90, "TRIP DINNER", when=day(5)),
               etransfer_in(20, "Priya", when=day(2)), etransfer_in(25, "Priya"))
    tid = ids["TRIP DINNER"]
    split(client, tid, [{"name": "Priya", "amount": 45}], mode="amount")
    ins = sorted((t for t in client.st.all_transactions() if t.amount < 0), key=lambda t: t.date)
    res = client.post(f"/api/transactions/{tid}/paybacks/{ins[0].fingerprint}",
                      json={"person": "Priya"})
    assert res.status_code == 200, res.get_json()
    p = detail(client, tid)["splitting"]["people"][0]
    assert p["paid"] == 20 and p["owes"] == 25 and p["paid_on"] is None
    # The rest is now exactly what she owes: suggested, and exact.
    sug = detail(client, ins[1].fingerprint)["repayment"]["suggestion"]
    assert sug and sug["owes"] == 25 and sug["exact"]
    client.post(f"/api/transactions/{tid}/paybacks/{ins[1].fingerprint}", json={"person": "Priya"})
    p = detail(client, tid)["splitting"]["people"][0]
    assert p["owes"] == 0 and p["paid_on"] == ins[1].date[:10]
    data = listing(client)
    assert data["totals"]["income"] == 0, "a repayment is never income"
    assert data["totals"]["spent"] == 45, "only her share counts"
    # A person who isn't in the split can't be named.
    assert client.post(f"/api/transactions/{tid}/paybacks/{ins[0].fingerprint}",
                       json={"person": "Mallory"}).status_code == 400


def test_review_suggests_the_split_first(client):
    ids = load(client.st, charge(85, "SUSHI NAMI", "Sushi Nami", when=day(3)),
               etransfer_in(42.5, "Priya"))
    split(client, ids["SUSHI NAMI"], [{"name": "Priya"}])
    items = client.get("/api/review").get_json()["money_in"]
    assert items and items[0]["guess"]["action"] == "split"
    assert items[0]["reason"] == "Priya owes you $42.50 for Sushi Nami."


def test_clearing_a_split_puts_the_whole_charge_back(client):
    ids = load(client.st, charge(85, "SUSHI NAMI"))
    tid = ids["SUSHI NAMI"]
    split(client, tid, [{"name": "Priya"}])
    r = client.delete(f"/api/transactions/{tid}/split").get_json()
    assert "splitting" not in r
    assert listing(client)["totals"]["spent"] == 85


# ── Paid back before the purchase posted ─────────────────────────────────

def test_money_before_the_charge_posted_can_pay_it_back(client):
    """Priya paid on Friday; the card purchase from Thursday posted Monday."""
    bought = charge(85, "SUSHI NAMI", "Sushi Nami", when=day(1))
    bought.post_date = day(4)                       # the bank feed's purchase date
    ids = load(client.st, bought, etransfer_in(42.5, "Priya", when=day(3)))
    split(client, ids["SUSHI NAMI"], [{"name": "Priya"}])
    r = detail(client, ids["E-TRANSFER RECEIVED PRIYA"])["repayment"]
    assert r["suggestion"]["charge_id"] == ids["SUSHI NAMI"]
    assert [s["charge_id"] for s in r["splits"]] == [ids["SUSHI NAMI"]]
    listed = client.get(f"/api/transactions/{ids['SUSHI NAMI']}/paybacks").get_json()
    assert ids["E-TRANSFER RECEIVED PRIYA"] in [p["id"] for p in listed["candidates"]]


def test_up_to_a_week_before_the_purchase(client):
    ids = load(client.st, charge(85, "DINNER", when=day(1)),
               etransfer_in(42.5, "Priya", when=day(8)), etransfer_in(42.5, "Sam", when=day(9)))
    split(client, ids["DINNER"], [{"name": "Priya", "amount": 42.5},
                                  {"name": "Sam", "amount": 42.5}], mode="amount")
    rows = {t.description: t.fingerprint for t in client.st.all_transactions()}
    assert detail(client, rows["E-TRANSFER RECEIVED PRIYA"])["repayment"]["suggestion"]
    assert detail(client, rows["E-TRANSFER RECEIVED SAM"])["repayment"]["suggestion"] is None


def test_bought_on_is_the_earlier_date():
    from finance.splits import bought_on
    t = charge(10, "X", when="2026-10-06")
    assert bought_on(t).isoformat() == "2026-10-06"
    t.post_date = "2026-10-03"
    assert bought_on(t).isoformat() == "2026-10-03"
    t.post_date = "2026-10-08"                       # a statement: posted later
    assert bought_on(t).isoformat() == "2026-10-06"


def test_up_to_fifty_people(client):
    """A split takes up to 50 paybacks (2026-10-26: was 8)."""
    ids = load(client.st, charge(5100, "WEDDING VENUE"))
    tid = ids["WEDDING VENUE"]
    r = split(client, tid, [{"name": f"Guest {n}"} for n in range(50)])
    assert r.status_code == 200, r.get_json()
    body = r.get_json()["splitting"]
    assert len(body["people"]) == 50 and body["you"] == 100.0
    too_many = split(client, tid, [{"name": f"Guest {n}"} for n in range(51)])
    assert too_many.status_code == 400
    assert too_many.get_json()["error"] == "Up to 50 people."


class TestTwoETransfersFromOnePerson:
    """2026-10-26: a friend can pay back their part in two e-Transfers."""

    def setup(self, client):
        ids = load(client.st, charge(120, "SUSHI NAMI", "Sushi Nami", when=day(1)),
                   etransfer_in(30, "Anna Lee", when=day(0)))
        st = client.st
        # The second one, a separate e-Transfer the same day.
        second = etransfer_in(30, "Anna Lee", when=day(0))
        second.description = "INTERAC E-TRANSFER 2 FROM ANNA LEE"
        second.raw = dict(second.raw, transaction_id="second")
        ids |= load(st, second)
        anna = [t.fingerprint for t in st.all_transactions() if t.amount == -30]
        assert len(anna) == 2
        return ids["SUSHI NAMI"], anna

    def mark(self, client, inflow, sushi):
        return client.post(f"/api/transactions/{inflow}/mark",
                           json={"case": "payback", "charge": sushi, "person": "Anna Lee"}).get_json()

    def test_both_come_off_a_purchase_that_was_not_split(self, client):
        sushi, (a1, a2) = self.setup(client)
        assert self.mark(client, a1, sushi)["title"] == "Sushi Nami is now split with Anna Lee."
        res = self.mark(client, a2, sushi)
        assert res["title"] == "Anna Lee has now paid you back $60.00 for Sushi Nami."
        d = detail(client, sushi)
        assert d["splitting"]["you"] == 60
        assert d["splitting"]["people"] == [{"name": "Anna Lee", "amount": 60.0, "paid": 60.0,
                                             "owes": 0.0, "paid_on": d["splitting"]["people"][0]["paid_on"]}]
        # Undo the second: back to one e-Transfer's worth.
        client.post("/api/transactions/undo", json=res["undo"])
        d = detail(client, sushi)
        assert d["splitting"]["you"] == 90 and d["splitting"]["people"][0]["amount"] == 30
        # Unlinking one of two leaves the other's.
        self.mark(client, a2, sushi)
        client.delete(f"/api/transactions/{sushi}/paybacks/{a1}")
        d = detail(client, sushi)
        assert d["splitting"]["you"] == 90 and d["splitting"]["people"][0]["amount"] == 30
        client.delete(f"/api/transactions/{sushi}/paybacks/{a2}")
        assert detail(client, sushi).get("splitting") is None

    def test_a_part_she_set_in_the_split_stays_what_she_said(self, client):
        sushi, (a1, a2) = self.setup(client)
        split(client, sushi, [{"name": "Anna Lee"}])          # $60 each
        self.mark(client, a1, sushi)
        self.mark(client, a2, sushi)
        d = detail(client, sushi)
        assert d["splitting"]["you"] == 60
        assert d["splitting"]["people"][0]["amount"] == 60 and d["splitting"]["people"][0]["owes"] == 0
